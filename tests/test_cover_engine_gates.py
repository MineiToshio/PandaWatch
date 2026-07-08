"""Tests del cierre de bypasses del motor de portadas (ITEM 2/3/4).

  F4 — lens con ref utilizable EXIGE _same_cover (antes: sólo aspect + page content).
  F5 — page content fail-closed para candidatas sin verificación visual.
  F6 — _is_soft_image se aplica en el path de _process_item.
  F7 — text con ref utilizable EXIGE _same_cover (antes: bypass < 30k con aspect).
  F16 — candado de umbral único (DEFAULT_MIN_PIXELS == LOW_QUALITY_PX en los 3 consumidores).
  F19 — merge anti-carrera en _write_preview.
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
import sync_cover_preview          # noqa: E402
import promote_hires_cover         # noqa: E402

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _jpeg(im: Image.Image, quality: int = 92) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _textured(w: int, h: int, seed: int = 0) -> Image.Image:
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (((x + seed) * 255) // w, (y * 255) // h, ((x + y) * 255) // (w + h))
    d = ImageDraw.Draw(im)
    d.ellipse([w // 5, h // 6, w * 4 // 5, h * 2 // 3], fill=(200, 30, 30))
    d.rectangle([w // 8, h * 3 // 4, w * 7 // 8, h * 15 // 16], fill=(20, 20, 120))
    return im


class _FakeSession:
    """session.get siempre falla (para probar el page-content fail-closed)."""
    def get(self, *a, **k):
        raise RuntimeError("network down")


def _item_with_cover(images_dir: Path, w: int, h: int, seed: int = 0) -> dict:
    """Escribe una portada real en disco y devuelve el item apuntándola."""
    cover = _jpeg(_textured(w, h, seed))
    fn = f"cover_{w}x{h}_{seed}.jpg"
    (images_dir / fn).write_bytes(cover)
    return {
        "slug": "s1", "title": "Serie X", "series_display": "Serie X",
        "publisher": "Pub", "language": "Español",
        "images": [{"url": "http://x/old.jpg", "local": fn, "kind": "gallery"}],
    }


# ── F4 — lens EXIGE _same_cover con ref utilizable ────────────────────────────

def test_lens_usable_ref_different_cover_discarded(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    item = _item_with_cover(images_dir, 120, 180)   # 21600 px → ref utilizable

    different = _jpeg(_textured(400, 600, seed=200))  # imagen distinta, mismo aspect
    monkeypatch.setattr(fbc, "_fetch", lambda url, session, **kw: different)
    monkeypatch.setattr(fbc, "_search_serper_lens",
                        lambda *a, **k: [{"url": "http://x/cand.jpg", "page_title": "",
                                          "domain": "x", "link": ""}])

    res = fbc._process_item(
        item, session=_FakeSession(), images_dir=images_dir,
        min_pixels=90_000, min_gain=1.5, max_hash_dist=6,
        no_search=False, serper_key="k", tavily_key="",
        dry_run=True, verbose=False,
    )
    assert res is None  # _same_cover falla → descartada (antes pasaba por aspect)


def test_lens_usable_ref_same_cover_verified(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    base = _textured(400, 600)
    ref_bytes = _jpeg(base.resize((150, 225), Image.LANCZOS))
    (images_dir / "cur.jpg").write_bytes(ref_bytes)
    item = {"slug": "s1", "title": "Serie X", "series_display": "Serie X",
            "publisher": "Pub", "language": "Español",
            "images": [{"url": "http://x/old.jpg", "local": "cur.jpg", "kind": "gallery"}]}

    cand_bytes = _jpeg(base)  # misma imagen, hi-res
    monkeypatch.setattr(fbc, "_fetch", lambda url, session, **kw: cand_bytes)
    monkeypatch.setattr(fbc, "_search_serper_lens",
                        lambda *a, **k: [{"url": "http://x/cand.jpg", "page_title": "",
                                          "domain": "x", "link": ""}])

    res = fbc._process_item(
        item, session=_FakeSession(), images_dir=images_dir,
        min_pixels=90_000, min_gain=1.5, max_hash_dist=6,
        no_search=False, serper_key="k", tavily_key="",
        dry_run=True, verbose=False,
    )
    assert res is not None
    assert res["verified"] is True
    assert res["confidence"] == "low"   # lens NO auto-aplica aunque verifique
    # Schema del preview (paridad con sc_validate.py, gotcha #131/#132): con ref
    # utilizable y _same_cover verificado, match_dist es un int (aHash real) y
    # ref_pixels es la resolución de la referencia usada para verificar.
    assert isinstance(res["match_dist"], int)
    assert res["ref_pixels"] == res["current_pixels"]


# ── verified/match_dist/ref_pixels sin referencia utilizable ──────────────────

def test_no_usable_ref_verified_false_match_dist_none(tmp_path, monkeypatch):
    """Path degradado (_passes_no_ref_gate): sin referencia utilizable la
    candidata puede pasar igual, pero queda verified=False y match_dist=None
    (no hay con qué comparar aHash) — mismo schema que sc_validate.py."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    # Ref chica < 10k px (90x90 = 8100) → sin ref utilizable.
    (images_dir / "tiny.jpg").write_bytes(_jpeg(_textured(90, 90)))
    item = {"slug": "s1", "title": "Serie X", "series_display": "Serie X",
            "publisher": "Pub", "language": "Español",
            "images": [{"url": "http://x/old.jpg", "local": "tiny.jpg", "kind": "gallery"}]}

    # 400x600 con detalle real (no soft) para no pisar el gate F6, que es
    # ortogonal a lo que este test verifica.
    cand_bytes = _jpeg(_textured(400, 600, seed=9))
    monkeypatch.setattr(fbc, "_fetch", lambda url, session, **kw: cand_bytes)
    monkeypatch.setattr(fbc, "_search_serper_lens",
                        lambda *a, **k: [{"url": "http://x/cand.jpg", "page_title": "",
                                          "domain": "x", "link": "http://page/x"}])
    # Aislar el gate degradado del resto de sus checks (aspect/page-content) —
    # ya cubiertos por test_no_usable_ref_page_content_fail_closed.
    monkeypatch.setattr(fbc, "_passes_no_ref_gate", lambda *a, **k: True)

    res = fbc._process_item(
        item, session=_FakeSession(), images_dir=images_dir,
        min_pixels=90_000, min_gain=1.5, max_hash_dist=6,
        no_search=False, serper_key="k", tavily_key="",
        dry_run=True, verbose=False,
    )
    assert res is not None
    assert res["verified"] is False
    assert res["match_dist"] is None
    assert res["ref_pixels"] == res["current_pixels"] == 8100


# ── F5 — page content fail-closed sin ref utilizable ──────────────────────────

def test_no_usable_ref_page_content_fail_closed(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    # Ref chica < 10k px (90x90 = 8100) → sin ref utilizable.
    (images_dir / "tiny.jpg").write_bytes(_jpeg(_textured(90, 90)))
    item = {"slug": "s1", "title": "Serie X", "series_display": "Serie X",
            "publisher": "Pub", "language": "Español",
            "images": [{"url": "http://x/old.jpg", "local": "tiny.jpg", "kind": "gallery"}]}

    # Candidata con mismo aspect (cuadrada) → pasa aspect, pero page content falla.
    cand_bytes = _jpeg(_textured(300, 300, seed=9))
    monkeypatch.setattr(fbc, "_fetch", lambda url, session, **kw: cand_bytes)
    monkeypatch.setattr(fbc, "_search_serper_lens",
                        lambda *a, **k: [{"url": "http://x/cand.jpg", "page_title": "",
                                          "domain": "x", "link": "http://page/x"}])

    res = fbc._process_item(
        item, session=_FakeSession(), images_dir=images_dir,   # session.get raises
        min_pixels=90_000, min_gain=1.5, max_hash_dist=6,
        no_search=False, serper_key="k", tavily_key="",
        dry_run=True, verbose=False,
    )
    assert res is None  # fail-closed: page no verificable → descartada


# ── F6 — _is_soft_image se aplica en el path ──────────────────────────────────

def test_soft_image_gate_in_path(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    base = _textured(400, 600)
    (images_dir / "cur.jpg").write_bytes(_jpeg(base.resize((150, 225), Image.LANCZOS)))
    item = {"slug": "s1", "title": "Serie X", "series_display": "Serie X",
            "publisher": "Pub", "language": "Español",
            "images": [{"url": "http://x/old.jpg", "local": "cur.jpg", "kind": "gallery"}]}
    cand_bytes = _jpeg(base)  # misma imagen → pasa _same_cover
    monkeypatch.setattr(fbc, "_fetch", lambda url, session, **kw: cand_bytes)
    monkeypatch.setattr(fbc, "_search_serper_lens",
                        lambda *a, **k: [{"url": "http://x/cand.jpg", "page_title": "",
                                          "domain": "x", "link": ""}])

    def _run():
        return fbc._process_item(
            item, session=_FakeSession(), images_dir=images_dir,
            min_pixels=90_000, min_gain=1.5, max_hash_dist=6,
            no_search=False, serper_key="k", tavily_key="",
            dry_run=True, verbose=False,
        )

    # Con _is_soft_image → True, la candidata se descarta (prueba que está en el path).
    monkeypatch.setattr(fbc, "_is_soft_image", lambda *a, **k: True)
    assert _run() is None
    # Con → False, la misma candidata pasa.
    monkeypatch.setattr(fbc, "_is_soft_image", lambda *a, **k: False)
    assert _run() is not None


# ── F7 — text EXIGE _same_cover con ref utilizable (bypass < 30k cerrado) ──────

def test_text_usable_ref_small_different_cover_discarded(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    # Ref 15000 px (< 30k, ≥ 10k) → antes: text con aspect-only aceptaba distinto.
    item = _item_with_cover(images_dir, 120, 180)  # 21600 px (< 30k, ≥ 10k)

    # Imagen DISTINTA pero MISMO aspect (0.667) → antes el bypass < 30k la aceptaba.
    different_same_ar = _jpeg(_textured(400, 600, seed=300))
    monkeypatch.setattr(fbc, "_fetch", lambda url, session, **kw: different_same_ar)
    # Sin lens → cae al text fallback (query no vacío → via="text").
    monkeypatch.setattr(fbc, "_search_serper_lens", lambda *a, **k: [])
    monkeypatch.setattr(fbc, "_search_serper_for_cover",
                        lambda *a, **k: [{"url": "http://x/txt.jpg", "page_title": "",
                                          "domain": "x"}])

    res = fbc._process_item(
        item, session=_FakeSession(), images_dir=images_dir,
        min_pixels=90_000, min_gain=1.5, max_hash_dist=6,
        no_search=False, serper_key="k", tavily_key="",
        dry_run=True, verbose=False,
    )
    assert res is None  # _same_cover corre y rechaza (bypass cerrado)


# ── F16 — candado de umbral único ─────────────────────────────────────────────

def test_low_quality_threshold_locked():
    assert fbc.DEFAULT_MIN_PIXELS == fbc.LOW_QUALITY_PX == 90_000
    assert sync_cover_preview.LOW_QUALITY_PX == fbc.LOW_QUALITY_PX
    assert promote_hires_cover.LOW_PX_THRESHOLD == fbc.LOW_QUALITY_PX


# ── F19 — merge anti-carrera en _write_preview ────────────────────────────────

def _cand(url, status="pending", **extra):
    c = {"new_url": url, "new_image": f"{url.rsplit('/', 1)[-1]}", "new_pixels": 100,
         "action": "replace_cover", "target": "", "kind": "gallery",
         "status": status, "confidence": "low"}
    c.update(extra)
    return c


def _entry(slug, cands):
    return {"slug": slug, "title": slug, "old_url": "", "old_image": "",
            "old_pixels": 0, "current_images": [], "candidates": cands}


def test_write_preview_merge_preserves_ui_decision(tmp_path, monkeypatch):
    preview_path = tmp_path / "cover_preview.json"
    monkeypatch.setattr(fbc, "_PREVIEW_PATH", preview_path)

    # Disco: la UI marcó la candidata como rejected con reject_reason.
    disk = [_entry("s1", [_cand("http://x/a.jpg", status="rejected",
                                reject_reason="otro_tomo")])]
    preview_path.write_text(json.dumps(disk), encoding="utf-8")

    # Memoria del motor: la MISMA candidata como pending (foto congelada al inicio).
    memory = [_entry("s1", [_cand("http://x/a.jpg", status="pending")])]
    fbc._write_preview(memory)

    out = json.loads(preview_path.read_text(encoding="utf-8"))
    c = out[0]["candidates"][0]
    assert c["status"] == "rejected"          # decisión de UI sobrevive
    assert c["reject_reason"] == "otro_tomo"


def test_write_preview_merge_keeps_skill_entry(tmp_path, monkeypatch):
    preview_path = tmp_path / "cover_preview.json"
    monkeypatch.setattr(fbc, "_PREVIEW_PATH", preview_path)

    # Disco: entry nueva de OTRO slug agregada por el skill durante la corrida.
    disk = [_entry("skill-slug", [_cand("http://x/s.jpg")])]
    preview_path.write_text(json.dumps(disk), encoding="utf-8")

    memory = [_entry("engine-slug", [_cand("http://x/e.jpg")])]
    fbc._write_preview(memory)

    out = json.loads(preview_path.read_text(encoding="utf-8"))
    slugs = {e["slug"] for e in out}
    assert slugs == {"skill-slug", "engine-slug"}  # ambas sobreviven


def test_write_preview_merge_no_duplicate_candidates(tmp_path, monkeypatch):
    preview_path = tmp_path / "cover_preview.json"
    monkeypatch.setattr(fbc, "_PREVIEW_PATH", preview_path)

    disk = [_entry("s1", [_cand("http://x/a.jpg", status="approved")])]
    preview_path.write_text(json.dumps(disk), encoding="utf-8")

    memory = [_entry("s1", [_cand("http://x/a.jpg", status="pending")])]
    fbc._write_preview(memory)

    out = json.loads(preview_path.read_text(encoding="utf-8"))
    urls = [c["new_url"] for c in out[0]["candidates"]]
    assert urls == ["http://x/a.jpg"]                 # no se duplica
    assert out[0]["candidates"][0]["status"] == "approved"


# ── --slugs — filtro de candidatos por slug (Parte B) ─────────────────────────

def test_filter_candidates_by_slugs_keeps_only_requested():
    items = [
        {"slug": "a"}, {"slug": "b"}, {"slug": "c"}, {"slug": "d"},
    ]
    candidate_idx = [0, 1, 2]  # 'd' no es candidato
    filtered, skipped = fbc.filter_candidates_by_slugs(items, candidate_idx, {"a", "c"})
    assert filtered == [0, 2]
    assert skipped == []


def test_filter_candidates_by_slugs_reports_non_candidate():
    items = [{"slug": "a"}, {"slug": "b"}, {"slug": "c"}]
    candidate_idx = [0, 1]  # 'c' existe pero NO es candidato (px ya buenos)
    filtered, skipped = fbc.filter_candidates_by_slugs(items, candidate_idx, {"a", "c"})
    assert filtered == [0]
    assert skipped == [("c", "no es candidato (px ya buenos / signal de skip)")]


def test_filter_candidates_by_slugs_reports_missing_slug():
    items = [{"slug": "a"}, {"slug": "b"}]
    candidate_idx = [0, 1]
    filtered, skipped = fbc.filter_candidates_by_slugs(items, candidate_idx, {"a", "zzz"})
    assert filtered == [0]
    assert skipped == [("zzz", "no existe en items.jsonl")]


# ── AVIF px measurement — el espejo local está normalizado a AVIF ─────────────

def _avif(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "AVIF")
    return buf.getvalue()


def test_get_pixels_from_bytes_measures_avif():
    """Regresión: una REFERENCIA local AVIF de ≥10k px debe medirse por su área
    real, no 0. Antes _get_pixels_from_bytes sólo cubría JPEG/PNG/WebP → todo el
    espejo (AVIF) medía 0 px, quedaba orig_px<10_000, usable_ref=False y TODAS las
    candidatas se saltaban _same_cover cayendo al gate degradado."""
    avif = pytest.importorskip("PIL.features")
    if not avif.check("avif"):  # pragma: no cover
        pytest.skip("PIL sin soporte AVIF en este entorno")
    data = _avif(_textured(357, 500))
    assert fbc._extension_from_magic(data) == ".avif"
    px = fbc._get_pixels_from_bytes(data)
    # Debe coincidir con lo que reporta _get_dims_from_bytes (fuente única).
    w, h = fbc._get_dims_from_bytes(data)
    assert px == w * h > 100_000
    assert px >= 10_000  # cruza el umbral usable_ref del motor


def test_get_pixels_from_bytes_fast_paths_intact():
    """El fallback no debe romper el fast path de bytes para JPEG/PNG."""
    assert fbc._get_pixels_from_bytes(_jpeg(_textured(120, 80))) == 120 * 80
    buf = io.BytesIO(); _textured(120, 80).save(buf, "PNG")
    assert fbc._get_pixels_from_bytes(buf.getvalue()) == 120 * 80
    assert fbc._get_pixels_from_bytes(b"not-an-image") == 0
