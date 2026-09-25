"""Tests para scripts/retrofit/sync_cover_images.py.

Sin red — imágenes sintéticas PIL en tmp_path. Cubre el fix de mecanismo del
gotcha #185 (2026-09-02): `_compute_junk_local` dejó de usar un umbral de bytes
crudo (<6000) como criterio de basura y pasó a delegar en el detector
ESTRUCTURAL único `image_store.placeholder_reason()` — mismo criterio que
`purge_placeholder_images.py`. Casos clave:

  - archivo <6000 bytes pero con estructura real (dims > 8px, no casi-sólido,
    sin firma conocida) → se CONSERVA (antes se purgaba, ese era el bug).
  - placeholder estructural real (tiny/solid/broken/firma) → se purga igual
    que antes, con o sin reemplazo de galería.
  - portada compartida por >=4 obras distintas → se purga igual que antes
    (señal independiente de bytes).
  - `_is_junk` también detecta un placeholder conocido por URL
    (`image_store.known_placeholder_url_reason`), no sólo IMAGE_URL_BAD_PATTERNS.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import image_store  # noqa: E402
import sync_cover_images as sci  # noqa: E402


# ── helpers de imágenes sintéticas ────────────────────────────────────────────

def _png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _solid(w: int, h: int, color=(255, 255, 255)) -> bytes:
    return _png_bytes(Image.new("RGB", (w, h), color))


def _textured(w: int, h: int) -> bytes:
    """Imagen con estructura (std alta) — como una portada/thumbnail real."""
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 5) % 256)
    return _png_bytes(im)


def _tiny_real_thumb() -> bytes:
    """Simula un thumbnail chico pero REAL: dims tipo listadomanga (208x300),
    con textura suficiente para pesar poco pero no ser casi-sólido. El bug
    viejo lo marcaba junk por pesar <6000 bytes; el fix no debe tocarlo."""
    body = _textured(208, 300)
    assert len(body) < sci._EVAL_MAX_BYTES  # liviano, como el caso real
    return body


@pytest.fixture(autouse=True)
def _isolate_signatures(monkeypatch):
    """`placeholder_reason` cachea `data/placeholder_signatures.json` — nos
    aseguramos de que ningún test dependa de firmas reales del repo."""
    monkeypatch.setattr(image_store, "_signatures_cache", {})


# ── _compute_junk_local: criterio estructural, no bytes ───────────────────────

def test_tiny_but_real_thumbnail_is_not_junk(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "thumb.png").write_bytes(_tiny_real_thumb())
    items = [{"slug": "a", "title": "Some Manga 1",
              "images": [{"url": "http://x/thumb.png", "local": "thumb.png", "kind": "gallery"}]}]
    junk = sci._compute_junk_local(items, images_dir)
    assert "thumb.png" not in junk


def test_structural_placeholder_is_junk_regardless_of_size(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "white.png").write_bytes(_solid(300, 450))  # casi-sólido, > 6000 bytes típicamente chico igual
    items = [{"slug": "a", "title": "Some Manga 1",
              "images": [{"url": "http://x/white.png", "local": "white.png", "kind": "gallery"}]}]
    junk = sci._compute_junk_local(items, images_dir)
    assert "white.png" in junk


def test_tiny_pixel_is_junk(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "pixel.gif").write_bytes(_solid(1, 1))
    items = [{"slug": "a", "title": "Some Manga 1",
              "images": [{"url": "http://x/pixel.gif", "local": "pixel.gif", "kind": "gallery"}]}]
    junk = sci._compute_junk_local(items, images_dir)
    assert "pixel.gif" in junk


def test_broken_file_is_junk(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "broken.png").write_bytes(b"")
    items = [{"slug": "a", "title": "Some Manga 1",
              "images": [{"url": "http://x/broken.png", "local": "broken.png", "kind": "gallery"}]}]
    junk = sci._compute_junk_local(items, images_dir)
    assert "broken.png" in junk


def test_signature_match_is_junk(tmp_path, monkeypatch):
    body = _textured(150, 200)  # con textura, no caería por tiny/solid
    sha1 = hashlib.sha1(body).hexdigest()
    monkeypatch.setattr(image_store, "load_placeholder_signatures",
                         lambda refresh=False: {sha1: "fake-placeholder"})
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "sig.png").write_bytes(body)
    items = [{"slug": "a", "title": "Some Manga 1",
              "images": [{"url": "http://x/sig.png", "local": "sig.png", "kind": "gallery"}]}]
    junk = sci._compute_junk_local(items, images_dir)
    assert "sig.png" in junk


def test_shared_across_many_works_is_junk_even_if_real_looking(tmp_path):
    """Señal independiente de bytes: mismo archivo referenciado por >=4 obras
    distintas se considera basura aunque estructuralmente parezca una imagen
    real (banner/poster con textura genuina compartido por error)."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "shared.png").write_bytes(_textured(300, 450))
    items = [
        {"slug": f"s{i}", "title": f"Series {i} 1",
         "images": [{"url": "http://x/shared.png", "local": "shared.png", "kind": "gallery"}]}
        for i in range(4)
    ]
    junk = sci._compute_junk_local(items, images_dir)
    assert "shared.png" in junk


def test_large_file_never_evaluated_as_placeholder(tmp_path):
    """Un archivo > _EVAL_MAX_BYTES no se decodifica con PIL — se asume real sin
    evaluarlo (mismo bound que purge_placeholder_images.py, performance/seguridad,
    no un criterio de basura)."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    import os
    noisy = Image.frombytes("RGB", (900, 1200), os.urandom(900 * 1200 * 3))
    big = _png_bytes(noisy)
    assert len(big) > sci._EVAL_MAX_BYTES
    (images_dir / "big.png").write_bytes(big)
    items = [{"slug": "a", "title": "Some Manga 1",
              "images": [{"url": "http://x/big.png", "local": "big.png", "kind": "gallery"}]}]
    junk = sci._compute_junk_local(items, images_dir)
    assert "big.png" not in junk


def test_missing_file_is_not_junk(tmp_path):
    """No existe en el espejo (nunca se descargó / se borró) — skip legítimo, no basura."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [{"slug": "a", "title": "Some Manga 1",
              "images": [{"url": "http://x/missing.png", "local": "missing.png", "kind": "gallery"}]}]
    junk = sci._compute_junk_local(items, images_dir)
    assert "missing.png" not in junk


# ── _is_junk: también detecta known_placeholder_url_reason, no sólo BAD_PATTERNS ──

def test_is_junk_catches_known_placeholder_url_by_stem():
    known_hash = next(iter(image_store.KNOWN_PLACEHOLDER_URL_STEMS))
    url = f"https://static.listadomanga.com/{known_hash}.png"
    assert sci._is_junk(url) is True


def test_is_junk_catches_rakuten_gif_rule():
    assert sci._is_junk("http://tshop.r10s.jp/book/cabinet/1/9784001234567.gif") is True
    # el .jpg del mismo host NO es basura por esta regla
    assert sci._is_junk("http://tshop.r10s.jp/book/cabinet/1/9784001234567.jpg") is False


def test_is_junk_catches_bad_pattern_substring():
    assert sci._is_junk("https://cdn.example.com/icon/foo.png") is True


def test_is_junk_real_url_is_not_junk():
    assert sci._is_junk("https://static.listadomanga.com/deadbeefdeadbeefdeadbeefdeadbeef.jpg") is False


# ── _fix_bad_cover: integración end-to-end vía run() ───────────────────────────

def _write_items(path: Path, items: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(it) for it in items) + "\n", encoding="utf-8")


def _by_slug(path: Path) -> dict:
    return {json.loads(l)["slug"]: json.loads(l) for l in path.read_text().splitlines() if l.strip()}


def test_tiny_real_cover_is_never_touched(tmp_path):
    """Regresión directa del bug: una portada ES EL ÚNICO elemento de images[],
    chica pero real — sync_cover_images NO debe tocarla ni vaciar images[]."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "thumb.png").write_bytes(_tiny_real_thumb())
    items_path = tmp_path / "items.jsonl"
    items = [{"slug": "a", "title": "Some Manga 1", "images": [
        {"url": "https://static.listadomanga.com/realhash.png", "local": "thumb.png", "kind": "gallery"}
    ], "sources": []}]
    _write_items(items_path, items)

    sci.run(items_path, dry_run=False, include_approved=False)

    by = _by_slug(items_path)
    assert len(by["a"]["images"]) == 1
    assert by["a"]["images"][0]["local"] == "thumb.png"


def test_structural_placeholder_cover_promotes_real_gallery_image(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "white.png").write_bytes(_solid(300, 450))
    (images_dir / "real.png").write_bytes(_textured(280, 400))
    items_path = tmp_path / "items.jsonl"
    items = [{"slug": "a", "title": "Some Manga 1", "images": [
        {"url": "http://x/white.png", "local": "white.png", "kind": "gallery"},
        {"url": "http://x/real.png", "local": "real.png", "kind": "gallery"},
    ], "sources": []}]
    _write_items(items_path, items)

    sci.run(items_path, dry_run=False, include_approved=False)

    by = _by_slug(items_path)
    assert len(by["a"]["images"]) == 1
    assert by["a"]["images"][0]["local"] == "real.png"


def test_structural_placeholder_cover_without_replacement_empties_images(tmp_path):
    """Sin reemplazo real en galería, el placeholder ESTRUCTURAL genuino sí se
    quita (comportamiento preexistente e intencional — el dashboard cae al 📚).
    Esto es DISTINTO del bug: acá la portada SÍ es basura real."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "white.png").write_bytes(_solid(300, 450))
    items_path = tmp_path / "items.jsonl"
    items = [{"slug": "a", "title": "Some Manga 1", "images": [
        {"url": "http://x/white.png", "local": "white.png", "kind": "gallery"},
    ], "sources": []}]
    _write_items(items_path, items)

    sci.run(items_path, dry_run=False, include_approved=False)

    by = _by_slug(items_path)
    assert by["a"]["images"] == []


def test_run_reports_dry_run_without_writing(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "white.png").write_bytes(_solid(300, 450))
    items_path = tmp_path / "items.jsonl"
    items = [{"slug": "a", "title": "Some Manga 1", "images": [
        {"url": "http://x/white.png", "local": "white.png", "kind": "gallery"},
    ], "sources": []}]
    raw = "\n".join(json.dumps(it) for it in items) + "\n"
    items_path.write_text(raw, encoding="utf-8")

    sci.run(items_path, dry_run=True, include_approved=False)
    assert items_path.read_text() == raw
