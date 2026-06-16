"""Tests para image_store.normalize_image — estandarización al ingresar.

Sin red — usan imágenes sintéticas PIL en memoria.

Cubre:
  - resize-DOWN al máximo (1600px lado largo) + conversión a AVIF.
  - NUNCA agranda (imagen chica queda igual de chica).
  - idempotencia: ya AVIF y ≤max → devuelta sin re-encodear; doble pasada estable.
  - placeholders (tiny / solid / broken) → pasan CRUDOS sin convertir (preserva firmas).
  - alpha preservado; fallback elegante ante bytes no-imagen.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import image_store  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────────────

def _textured(w: int, h: int) -> bytes:
    """PNG con estructura (std alta → no placeholder)."""
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 5) % 256)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _photo_png(w: int, h: int) -> bytes:
    """PNG estructurado grande, generado rápido (tile 64×64 escalado)."""
    small = Image.open(io.BytesIO(_textured(64, 64)))
    buf = io.BytesIO()
    small.resize((w, h)).save(buf, "PNG")
    return buf.getvalue()


def _avif(w: int, h: int) -> bytes:
    small = Image.open(io.BytesIO(_textured(64, 64))).resize((w, h))
    buf = io.BytesIO()
    small.save(buf, "AVIF", quality=60)
    return buf.getvalue()


def _solid(w: int, h: int, color=(255, 255, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


def _dims(body: bytes):
    with Image.open(io.BytesIO(body)) as im:
        return im.size


def _fmt(body: bytes):
    with Image.open(io.BytesIO(body)) as im:
        return im.format


# ── resize + formato ────────────────────────────────────────────────────────────

def test_large_image_capped_and_avif():
    out, ext = image_store.normalize_image(_photo_png(2000, 3000))
    assert ext == ".avif"
    assert _fmt(out) == "AVIF"
    assert max(_dims(out)) <= image_store.NORMALIZE_MAX_LONG_SIDE


def test_small_image_not_upscaled():
    out, ext = image_store.normalize_image(_photo_png(300, 400))
    assert ext == ".avif" and _fmt(out) == "AVIF"
    assert _dims(out) == (300, 400)  # NUNCA agranda


def test_avif_smaller_than_png_for_heavy():
    png = _photo_png(1500, 2100)
    out, _ = image_store.normalize_image(png)
    assert len(out) < len(png)


# ── idempotencia ─────────────────────────────────────────────────────────────────

def test_already_avif_small_is_idempotent():
    body = _avif(200, 300)
    out, ext = image_store.normalize_image(body)
    assert ext == ".avif"
    assert out == body  # devuelto sin re-encodear


def test_already_avif_large_gets_resized():
    out, ext = image_store.normalize_image(_avif(2000, 2000))
    assert ext == ".avif"
    assert max(_dims(out)) <= image_store.NORMALIZE_MAX_LONG_SIDE


def test_double_normalize_is_stable():
    out1, _ = image_store.normalize_image(_photo_png(2000, 3000))
    out2, ext2 = image_store.normalize_image(out1)
    assert ext2 == ".avif"
    assert out2 == out1  # segunda pasada: ya AVIF y ≤max → no-op


# ── placeholders pasan crudos (preserva firmas sha1) ─────────────────────────────

def test_placeholder_tiny_passthrough():
    body = _solid(1, 1)
    out, ext = image_store.normalize_image(body)
    assert out == body and ext == ".png"  # NO convertido a AVIF


def test_placeholder_solid_passthrough():
    body = _solid(120, 120)  # blanco pequeño → solid
    assert image_store.placeholder_reason(body)  # sanity
    out, ext = image_store.normalize_image(body)
    assert out == body and ext == ".png"


# ── alpha + fallback ─────────────────────────────────────────────────────────────

def test_alpha_preserved():
    im = Image.open(io.BytesIO(_textured(64, 64))).convert("RGBA").resize((1800, 1800))
    im.putalpha(128)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    out, ext = image_store.normalize_image(buf.getvalue())
    assert ext == ".avif"
    with Image.open(io.BytesIO(out)) as o:
        assert "A" in o.mode  # alpha conservado
        assert max(o.size) <= image_store.NORMALIZE_MAX_LONG_SIDE


def test_non_image_falls_back():
    raw = b"this is definitely not an image"
    out, ext = image_store.normalize_image(raw)
    assert out == raw and ext == ".bin"  # degrada con gracia, no rompe


# ── integración: el cuello de botella download_image normaliza al ingresar ───────

def test_download_image_writes_normalized_avif(tmp_path):
    big_png = _photo_png(2400, 3000)

    class _Resp:
        status_code = 200

        def iter_content(self, n):
            yield big_png

        def close(self):
            pass

    class _Sess:
        def get(self, url, timeout=None, stream=None, headers=None):
            return _Resp()

    fn = image_store.download_image(
        "https://example.com/cover.png", tmp_path, session=_Sess()
    )
    assert fn.endswith(".avif")  # convertido desde PNG, no guardado crudo
    out = (tmp_path / fn).read_bytes()
    assert _fmt(out) == "AVIF"
    assert max(_dims(out)) <= image_store.NORMALIZE_MAX_LONG_SIDE
    assert len(out) < len(big_png)  # mucho más liviano
