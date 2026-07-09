"""Tests del paquete A3-fbc (auditoría Fable 2026-07-08) sobre
fetch_better_covers.py:

  F1  — `--apply-preview --dry-run` es un dry-run REAL: no muta items.jsonl,
        no hace unlink() de imágenes, no escribe preview/ledger. Antes la CLI
        ni siquiera pasaba `dry_run` a `apply_preview()`.
  F4  — gate fail-closed sin referencia: `_validate_page_content("")` ahora
        respeta `fail_open` (antes aceptaba de forma vacua siempre). La vía
        CDN (sin página que scrapear) se preserva vía
        `require_page_validation=False`.
  F10 — `_fetch` requotea URLs no-ASCII y no crashea con UnicodeError.
"""

import json
import sys
from pathlib import Path

import pytest
import requests

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import fetch_better_covers as fbc  # noqa: E402

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _make_img(path: Path, size=(100, 150), color=(200, 30, 30)) -> None:
    img = Image.new("RGB", size, color)
    img.save(path, "JPEG")


# ── F1 — apply-preview + dry-run: dry-run REAL ────────────────────────────────

@pytest.fixture()
def dry_run_setup(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "old_cover.jpg", (100, 150))
    _make_img(images_dir / "new_cover.jpg", (400, 600))
    _make_img(images_dir / "rejected_cand.jpg", (300, 450))

    item = {
        "slug": "dry-item",
        "title": "Dry",
        "images": [{"url": "http://x/old.jpg", "local": "old_cover.jpg", "kind": "gallery"}],
    }
    items_path = tmp_path / "items.jsonl"
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    preview = [{
        "slug": "dry-item",
        "title": "Dry",
        "old_url": "http://x/old.jpg",
        "old_image": "old_cover.jpg",
        "old_pixels": 15000,
        "current_images": [{"url": "http://x/old.jpg", "local": "old_cover.jpg",
                            "kind": "gallery", "is_cover": True}],
        "candidates": [
            {"new_url": "http://x/new.jpg", "new_image": "new_cover.jpg",
             "new_pixels": 240000, "action": "replace_cover", "target": "",
             "kind": "gallery", "status": "approved", "confidence": "low"},
            {"new_url": "http://x/rejected.jpg", "new_image": "rejected_cand.jpg",
             "new_pixels": 135000, "action": "replace_cover", "target": "",
             "kind": "gallery", "status": "rejected", "confidence": "low",
             "reject_reason": "otro_tomo"},
        ],
    }]
    preview_path = tmp_path / "cover_preview.json"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")
    monkeypatch.setattr(fbc, "_PREVIEW_PATH", preview_path)
    ledger_path = tmp_path / "cover_rejections.jsonl"
    monkeypatch.setattr(fbc, "REJECTION_LEDGER_PATH", ledger_path)
    return item, items_path, images_dir, preview, preview_path, ledger_path


def test_apply_preview_dry_run_does_not_mutate_anything(dry_run_setup):
    item, items_path, images_dir, preview, preview_path, ledger_path = dry_run_setup

    summary = fbc.apply_preview(items_path, images_dir, dry_run=True)

    # items.jsonl: byte-idéntico al original (ni portada reemplazada ni nada).
    on_disk_item = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    assert on_disk_item == item

    # cover_preview.json: sin tocar (ni recorte de decididas, ni unlink final).
    assert json.loads(preview_path.read_text(encoding="utf-8")) == preview

    # Ningún archivo se borró (ni la portada vieja reemplazada, ni la
    # candidata rechazada).
    assert (images_dir / "old_cover.jpg").exists()
    assert (images_dir / "new_cover.jpg").exists()
    assert (images_dir / "rejected_cand.jpg").exists()

    # El ledger de rechazos no se escribió.
    assert not ledger_path.exists()

    # El resumen SÍ refleja lo que haría una corrida real (útil como reporte).
    assert summary["ok"] is True
    assert summary["dry_run"] is True
    assert summary["replaced"] == 1
    assert summary["reverted"] == 1
    assert summary["cleaned_old"] == 1     # "se limpiaría" — no se limpió de verdad
    assert summary["cleaned_new"] == 1


def test_apply_preview_real_run_still_mutates(dry_run_setup):
    """Control: SIN dry_run, el mismo escenario sí aplica de verdad — para
    dejar claro que el test de arriba prueba la ausencia real de side-effects,
    no un bug que hiciera que apply_preview nunca mutara nada."""
    item, items_path, images_dir, preview, preview_path, ledger_path = dry_run_setup

    fbc.apply_preview(items_path, images_dir, dry_run=False)

    on_disk_item = json.loads(items_path.read_text(encoding="utf-8").splitlines()[0])
    assert on_disk_item["images"][0]["local"] == "new_cover.jpg"
    assert not (images_dir / "old_cover.jpg").exists()
    assert not (images_dir / "rejected_cand.jpg").exists()
    assert ledger_path.exists()


def test_cli_apply_preview_wires_dry_run(monkeypatch):
    """F1 — antes la CLI nunca pasaba `dry_run` a apply_preview(); el flag
    `--apply-preview --dry-run` no tenía ningún efecto."""
    captured = {}

    def _fake_apply_preview(items_path, images_dir, *, include_approved=False, dry_run=False):
        captured["dry_run"] = dry_run
        captured["include_approved"] = include_approved
        return {"ok": True}

    monkeypatch.setattr(fbc, "apply_preview", _fake_apply_preview)
    monkeypatch.setattr(
        sys, "argv",
        ["fetch_better_covers.py", "--apply-preview", "--dry-run"],
    )
    fbc.main()
    assert captured["dry_run"] is True


# ── F4 — gate fail-closed sin referencia: sin link no pasa vacuo ─────────────

class _NeverCalledSession:
    """session.get NUNCA debería llamarse en estos escenarios (page_url vacío
    corta antes, o CDN no valida página)."""
    def get(self, *a, **k):
        raise AssertionError("session.get no debería llamarse acá")


def test_validate_page_content_empty_url_respects_fail_open():
    item = {"series_display": "Serie X", "publisher": "Pub"}
    sess = _NeverCalledSession()
    # fail_open=True (default, best-effort sobre candidata ya verificada) →
    # sin página, acepta.
    assert fbc._validate_page_content("", item, sess, fail_open=True) is True
    # fail_open=False (F4-fix): sin página que validar, NO puede "pasar" el
    # gate fail-closed de forma vacua.
    assert fbc._validate_page_content("", item, sess, fail_open=False) is False


def test_passes_no_ref_gate_text_without_link_rejected():
    """Vía text/lens (require_page_validation=True, default): candidata sin
    `link` y sin referencia utilizable ya NO pasa como si estuviera validada
    (antes: `_validate_page_content("")` aceptaba vacuamente)."""
    item = {"series_display": "Serie X"}
    cand = {"url": "http://x/cand.jpg", "page_title": ""}  # sin "link"
    ok = fbc._passes_no_ref_gate(
        item, cand, data=b"", orig_bytes=b"", session=_NeverCalledSession(),
    )
    assert ok is False


def test_passes_no_ref_gate_cdn_without_link_still_passes():
    """Vía CDN (require_page_validation=False): preserva su comportamiento
    documentado — no exige page-content porque no tiene página que scrapear
    (URL de imagen directa, confianza por ISBN determinístico)."""
    item = {"series_display": "Serie X"}
    cand = {"url": "http://cdn/x.jpg", "page_title": ""}  # sin "link"
    ok = fbc._passes_no_ref_gate(
        item, cand, data=b"", orig_bytes=b"", session=_NeverCalledSession(),
        require_page_validation=False,
    )
    assert ok is True


def test_search_serper_for_cover_captures_link(monkeypatch):
    """F4-fix — antes `_search_serper_for_cover` (vía text) descartaba el
    campo `link` que Serper trae en su respuesta; sin él, la vía text nunca
    podía correr `_validate_page_content` de verdad en modo fail-closed."""
    class _FakeResp:
        status_code = 200
        def json(self):
            return {"images": [{
                "imageUrl": "http://x/cover.jpg",
                "title": "Some Cover",
                "domain": "x.com",
                "link": "http://x.com/product/123",
                "imageWidth": 800,
                "imageHeight": 1200,
            }]}

    class _FakeSession:
        def post(self, *a, **k):
            return _FakeResp()

    result = fbc._search_serper_for_cover("query", "fake-key", _FakeSession())
    assert len(result) == 1
    assert result[0]["link"] == "http://x.com/product/123"


# ── F10 — _fetch: requote_uri + catch de UnicodeError ────────────────────────

class _CapturingSession:
    def __init__(self, chunks=(b"\xff\xd8\xff\xe0" + b"0" * 30,)):
        self.captured_url = None
        self._chunks = chunks

    def get(self, url, timeout=None, stream=None, headers=None):
        self.captured_url = url

        class _Resp:
            status_code = 200

            def iter_content(_self, chunk_size):
                yield from self._chunks

            def close(_self):
                pass

        return _Resp()


def test_fetch_requotes_non_ascii_url():
    sess = _CapturingSession()
    url = "http://example.com/covers/ปกหน้า.jpg"  # thai
    data = fbc._fetch(url, sess)
    assert data is not None
    assert sess.captured_url == requests.utils.requote_uri(url)
    assert "%" in sess.captured_url


class _UnicodeErrorSession:
    def get(self, *a, **k):
        raise UnicodeError("simulated encoding failure")


def test_fetch_catches_unicode_error_gracefully():
    sess = _UnicodeErrorSession()
    assert fbc._fetch("http://example.com/x.jpg", sess) is None


# ── F18 — --limit cuenta ISBN inválidos como "consume búsqueda" ─────────────

def test_isbn_len_ok_valid_lengths():
    assert fbc._isbn_len_ok("1234567890") is True          # 10 dígitos
    assert fbc._isbn_len_ok("9784091234561") is True        # 13, prefijo 978
    assert fbc._isbn_len_ok("9794091234561") is True        # 13, prefijo 979


def test_isbn_len_ok_rejects_garbage():
    assert fbc._isbn_len_ok("") is False
    assert fbc._isbn_len_ok("ABC123") is False
    assert fbc._isbn_len_ok("12345") is False                # ni 10 ni 13
    assert fbc._isbn_len_ok("1234567890123") is False        # 13 pero sin 978/979
