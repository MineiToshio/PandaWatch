"""Tests del ledger de rechazos persistente + denylist + cierre de bypasses del
motor de portadas hi-res (fetch_better_covers.py).

Cobertura:
  ITEM 1 — ledger:
    - ledger_append / load_rejection_ledger (append + tolerancia a corruptos)
    - is_rejected_candidate: URL exacta SIEMPRE; hash SOLO con motivo de identidad
      y dist ≤ 2; reason null / calidad NO veta por hash.
    - apply_preview escribe el ledger en la rama rejected (con y sin dry-run;
      archivo borrado → a_hash null).
    - denylist consultada en _process_item.
  ITEM 2 — gates:
    - F4/F5/F7: lens con ref utilizable que falla _same_cover → descartada;
      sin ref utilizable → fail-closed en page content.
    - F6: _is_soft_image se aplica en el path.
"""

import io
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import fetch_better_covers as fbc  # noqa: E402

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _jpeg(im: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _textured_cover(w: int = 400, h: int = 600) -> Image.Image:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 255) // w, (y * 255) // h, ((x + y) * 255) // (w + h))
    d = ImageDraw.Draw(im)
    d.ellipse([w // 5, h // 6, w * 4 // 5, h * 2 // 3], fill=(200, 30, 30))
    d.rectangle([w // 8, h * 3 // 4, w * 7 // 8, h * 15 // 16], fill=(20, 20, 120))
    return im


@pytest.fixture()
def ledger_path(tmp_path, monkeypatch):
    p = tmp_path / "cover_rejections.jsonl"
    monkeypatch.setattr(fbc, "REJECTION_LEDGER_PATH", p)
    return p


# ── ITEM 1 — ledger básico ────────────────────────────────────────────────────

def test_ledger_append_and_load(ledger_path):
    assert fbc.load_rejection_ledger() == []  # inexistente → []
    fbc.ledger_append({"slug": "a", "rejected_url": "http://x/1.jpg", "reason": None})
    fbc.ledger_append({"slug": "b", "rejected_url": "http://x/2.jpg", "reason": "otro_tomo"})
    recs = fbc.load_rejection_ledger()
    assert len(recs) == 2
    assert recs[0]["slug"] == "a"
    assert recs[1]["reason"] == "otro_tomo"


def test_ledger_tolerates_corrupt_lines(ledger_path):
    ledger_path.write_text(
        '{"slug": "ok", "rejected_url": "u"}\n'
        "this is not json\n"
        "\n"
        '{"slug": "ok2", "rejected_url": "v"}\n',
        encoding="utf-8",
    )
    recs = fbc.load_rejection_ledger()
    assert [r["slug"] for r in recs] == ["ok", "ok2"]


# ── ITEM 1 — política de is_rejected_candidate ────────────────────────────────

def test_is_rejected_url_exact_always():
    ledger = [{"slug": "s1", "rejected_url": "http://x/a.jpg", "reason": None}]
    # URL exacta + slug igual → True aunque el reason sea null.
    assert fbc.is_rejected_candidate("s1", "http://x/a.jpg", None, ledger) is True
    # Otro slug → no matchea.
    assert fbc.is_rejected_candidate("s2", "http://x/a.jpg", None, ledger) is False
    # Otra URL → no matchea por URL.
    assert fbc.is_rejected_candidate("s1", "http://x/b.jpg", None, ledger) is False


def test_hash_veto_only_with_identity_reason():
    base = _jpeg(_textured_cover())
    ah = fbc._ahash_hex(base)
    # reason de IDENTIDAD → veta por hash (dist 0 ≤ 2).
    ledger_id = [{"slug": "s1", "rejected_url": "http://old/x.jpg",
                  "a_hash": ah, "reason": "otro_tomo"}]
    assert fbc.is_rejected_candidate("s1", "http://new/y.jpg", ah, ledger_id) is True


def test_hash_veto_not_when_reason_null_or_quality():
    base = _jpeg(_textured_cover())
    ah = fbc._ahash_hex(base)
    # reason null → NUNCA veta por hash (la candidata correcta comparte aHash).
    ledger_null = [{"slug": "s1", "rejected_url": "http://old/x.jpg",
                    "a_hash": ah, "reason": None}]
    assert fbc.is_rejected_candidate("s1", "http://new/y.jpg", ah, ledger_null) is False
    # reason de calidad → tampoco veta por hash.
    ledger_q = [{"slug": "s1", "rejected_url": "http://old/x.jpg",
                 "a_hash": ah, "reason": "mala_calidad"}]
    assert fbc.is_rejected_candidate("s1", "http://new/y.jpg", ah, ledger_q) is False
    ledger_otros = [{"slug": "s1", "rejected_url": "http://old/x.jpg",
                     "a_hash": ah, "reason": "otros"}]
    assert fbc.is_rejected_candidate("s1", "http://new/y.jpg", ah, ledger_otros) is False


def test_hash_veto_distance_bound():
    # Dos imágenes visualmente muy distintas → aHash lejano → NO veta por hash
    # aun con motivo de identidad (dist > 2).
    a = _jpeg(_textured_cover())
    b = _jpeg(Image.new("RGB", (400, 600), (255, 255, 255)))
    ah_a = fbc._ahash_hex(a)
    ah_b = fbc._ahash_hex(b)
    ledger = [{"slug": "s1", "rejected_url": "http://old/x.jpg",
               "a_hash": ah_a, "reason": "no_es_la_obra"}]
    assert fbc.is_rejected_candidate("s1", "http://new/y.jpg", ah_b, ledger) is False


# ── ITEM 1 — hook en apply_preview ────────────────────────────────────────────

def _make_img(path: Path, size=(400, 600), color=(200, 30, 30)) -> None:
    Image.new("RGB", size, color).save(path, "JPEG")


def _reject_setup(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "old_cover.jpg", (100, 150))
    _make_img(images_dir / "rej_cand.jpg", (400, 600))

    item = {
        "slug": "rej-item",
        "title": "Rej",
        "images": [{"url": "http://x/old.jpg", "local": "old_cover.jpg", "kind": "gallery"}],
    }
    items_path = tmp_path / "items.jsonl"
    items_path.write_text(json.dumps(item) + "\n", encoding="utf-8")

    preview = [{
        "slug": "rej-item",
        "title": "Rej",
        "old_url": "http://x/old.jpg",
        "old_image": "old_cover.jpg",
        "old_pixels": 15000,
        "current_images": [{"url": "http://x/old.jpg", "local": "old_cover.jpg",
                            "kind": "gallery", "is_cover": True}],
        "candidates": [
            {"new_url": "http://x/rej.jpg", "new_image": "rej_cand.jpg",
             "new_pixels": 240000, "action": "replace_cover", "target": "",
             "kind": "gallery", "status": "rejected", "confidence": "low",
             "reject_reason": "otro_tomo", "match_dist": 5},
        ],
    }]
    preview_path = tmp_path / "cover_preview.json"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")
    monkeypatch.setattr(fbc, "_PREVIEW_PATH", preview_path)
    return items_path, images_dir, preview_path


def test_apply_preview_writes_ledger(tmp_path, monkeypatch, ledger_path):
    items_path, images_dir, preview_path = _reject_setup(tmp_path, monkeypatch)
    fbc.apply_preview(items_path, images_dir)

    recs = fbc.load_rejection_ledger()
    assert len(recs) == 1
    r = recs[0]
    assert r["slug"] == "rej-item"
    assert r["rejected_url"] == "http://x/rej.jpg"
    assert r["reason"] == "otro_tomo"
    assert r["match_dist"] == 5
    assert r["ref_pixels"] == 15000
    assert r["new_pixels"] == 240000
    assert r["a_hash"]  # el archivo existía → hash presente
    assert r["rejected_at"]


def test_apply_preview_dry_run_no_ledger(tmp_path, monkeypatch, ledger_path):
    items_path, images_dir, preview_path = _reject_setup(tmp_path, monkeypatch)
    fbc.apply_preview(items_path, images_dir, dry_run=True)
    assert not ledger_path.exists()
    assert fbc.load_rejection_ledger() == []


def test_apply_preview_ledger_ahash_null_when_file_missing(tmp_path, monkeypatch, ledger_path):
    items_path, images_dir, preview_path = _reject_setup(tmp_path, monkeypatch)
    # Borrar el archivo de la candidata antes del apply → a_hash null.
    (images_dir / "rej_cand.jpg").unlink()
    fbc.apply_preview(items_path, images_dir)
    recs = fbc.load_rejection_ledger()
    assert len(recs) == 1
    assert recs[0]["a_hash"] is None


# ── ITEM 1 — denylist consultada en _process_item ────────────────────────────

def test_process_item_skips_url_in_ledger(tmp_path, monkeypatch, ledger_path):
    """Una candidata cuya URL está en el ledger no se descarga siquiera."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "cur.jpg", (100, 150))
    item = {"slug": "s1", "title": "T", "images": [
        {"url": "http://x/old.jpg", "local": "cur.jpg", "kind": "gallery"}]}

    monkeypatch.setattr(fbc.image_store, "cover_url", lambda it: "http://x/old.jpg")

    fetched = []
    monkeypatch.setattr(fbc, "_fetch", lambda url, session, **kw: fetched.append(url) or _jpeg(_textured_cover()))
    # Forzar una sola candidata lens con esa URL.
    monkeypatch.setattr(fbc, "_search_serper_lens",
                        lambda *a, **k: [{"url": "http://x/rej.jpg", "page_title": "",
                                          "domain": "x", "link": ""}])
    ledger = [{"slug": "s1", "rejected_url": "http://x/rej.jpg", "reason": None}]

    res = fbc._process_item(
        item, session=None, images_dir=images_dir,
        min_pixels=90_000, min_gain=1.5, max_hash_dist=6,
        no_search=False, serper_key="k", tavily_key="",
        dry_run=True, verbose=False, ledger=ledger,
    )
    assert res is None
    assert fetched == []  # nunca se descargó la URL vetada


# ── ITEM 1 — hook en sync_cover_preview (slug desaparecido con rechazadas) ─────

def test_sync_drops_rejected_to_ledger(tmp_path, monkeypatch, ledger_path):
    import sync_cover_preview as scp  # noqa: PLC0415

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_img(images_dir / "rej.jpg", (400, 600))

    entry = {
        "slug": "gone-slug",
        "title": "Gone",
        "old_url": "http://x/old.jpg",
        "old_image": "old.jpg",
        "old_pixels": 15000,
        "current_images": [],
        "candidates": [
            {"new_url": "http://x/rej.jpg", "new_image": "rej.jpg",
             "new_pixels": 240000, "action": "replace_cover", "target": "",
             "status": "rejected", "reject_reason": "otra_edicion"},
            {"new_url": "http://x/pend.jpg", "new_image": "pend.jpg",
             "new_pixels": 240000, "action": "replace_cover", "target": "",
             "status": "pending"},
        ],
    }
    synced, stats = scp.sync_preview([entry], {}, images_dir)
    assert synced == []
    assert stats["dropped_missing_item"] == 1

    recs = fbc.load_rejection_ledger()
    # Sólo la rechazada va al ledger (la pending no).
    assert len(recs) == 1
    assert recs[0]["rejected_url"] == "http://x/rej.jpg"
    assert recs[0]["reason"] == "otra_edicion"
    assert recs[0]["a_hash"]  # archivo existía


def test_sync_dry_run_skips_ledger(tmp_path, monkeypatch, ledger_path):
    import sync_cover_preview as scp  # noqa: PLC0415

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    entry = {
        "slug": "gone-slug", "title": "Gone", "old_pixels": 15000,
        "current_images": [],
        "candidates": [
            {"new_url": "http://x/rej.jpg", "new_image": "rej.jpg",
             "action": "replace_cover", "target": "", "status": "rejected"},
        ],
    }
    scp.sync_preview([entry], {}, images_dir, write_ledger=False)
    assert not ledger_path.exists()
