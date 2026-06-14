"""Tests del gate de calidad de display (fetch_better_covers._detail_ratio /
_is_soft_image) — gotcha #94.

El px count sobreestima la calidad: una candidata con MÁS píxeles que la actual
puede verse peor (pixelada/blanda). El defecto se da SOLO con la combinación
CHICA + BLANDA: una imagen chica se muestra agrandada (modal/tarjeta la
upscalean) y ahí su falta de detalle salta a la vista; una grande pero blanda se
muestra reducida y se ve nítida.

`_detail_ratio` mide el detalle real (fracción de energía en la octava superior,
a tamaño de display común). `_is_soft_image` = chica (< SOFT_GUARD_PX) Y blanda
(ratio < DETAIL_RATIO_MIN). Calibrado 2026-06-13 con casos reales (casadellibro
80k blandas vs whakoom 340k-694k nítidas).

Imágenes generadas con PIL en memoria — sin red, sin fixtures.
"""

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import fetch_better_covers as fbc  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _jpeg(im: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _textured(w: int, h: int) -> Image.Image:
    """Portada sintética con estructura y detalle de alta frecuencia."""
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 255) // w, (y * 255) // h, ((x + y) * 255) // (w + h))
    d = ImageDraw.Draw(im)
    d.ellipse([w // 5, h // 6, w * 4 // 5, h * 2 // 3], fill=(200, 30, 30))
    d.rectangle([w // 8, h * 3 // 4, w * 7 // 8, h * 15 // 16], fill=(20, 20, 120))
    for k in range(0, h, 7):  # líneas finas → energía en la octava superior
        d.line([(0, k), (w, k)], fill=(255, 255, 255), width=1)
    return im


# px de referencia: chico (< guard) y grande (>= guard)
_SMALL = (300, 450)   # 135k px  < SOFT_GUARD_PX (150k)
_LARGE = (500, 750)   # 375k px  >= SOFT_GUARD_PX


def _crisp_small() -> bytes:
    return _jpeg(_textured(*_SMALL))


def _blurred(size, radius: float = 4.0) -> bytes:
    return _jpeg(_textured(*size).filter(ImageFilter.GaussianBlur(radius)))


def _upscaled_small() -> bytes:
    """Detalle real de una fuente chica estirada al tamaño nominal (upscale)."""
    base = _textured(*_SMALL)
    return _jpeg(base.resize((100, 150), Image.LANCZOS).resize(_SMALL, Image.LANCZOS))


# ── _detail_ratio ──────────────────────────────────────────────────────────────

def test_crisp_has_higher_detail_than_blurred_same_size():
    crisp = fbc._detail_ratio(_crisp_small())
    blurry = fbc._detail_ratio(_blurred(_SMALL))
    assert crisp is not None and blurry is not None
    assert crisp > blurry
    # el blando cae claramente por debajo del umbral; el nítido lo supera
    assert blurry < fbc.DETAIL_RATIO_MIN < crisp


def test_detail_ratio_incomputable_returns_none():
    assert fbc._detail_ratio(b"") is None
    assert fbc._detail_ratio(b"\x00\x01\x02" * 100) is None


def test_detail_ratio_solid_image_returns_none():
    # varianza cero → no verificable (no es "blanda", es incomputable)
    assert fbc._detail_ratio(_jpeg(Image.new("RGB", (300, 450), (128, 128, 128)))) is None


# ── _is_soft_image ──────────────────────────────────────────────────────────────

def test_small_and_soft_is_flagged():
    # CHICA + BLANDA → se vería pixelada al agrandarla → rechazo
    assert fbc._is_soft_image(_blurred(_SMALL)) is True
    assert fbc._is_soft_image(_upscaled_small()) is True


def test_small_and_crisp_not_flagged():
    # CHICA pero NÍTIDA → upgrade válido
    assert fbc._is_soft_image(_crisp_small()) is False


def test_large_soft_not_flagged_due_to_guard():
    # MISMA blandura que test_small_and_soft pero con px >= SOFT_GUARD_PX: se
    # muestra REDUCIDA → nítida. El guard de tamaño evita el falso positivo
    # (whakoom 637k / planeta 6M miden ~0.10 igual que la casadellibro 80k).
    small_soft = _blurred(_SMALL)
    large_soft = _blurred(_LARGE)
    # ambas igual de blandas por ratio…
    assert fbc._detail_ratio(large_soft) < fbc.DETAIL_RATIO_MIN
    # …pero solo la chica se marca
    assert fbc._is_soft_image(small_soft) is True
    assert fbc._is_soft_image(large_soft) is False


def test_incomputable_bytes_not_flagged_soft():
    # Sin detalle computable, el gate NO marca blando (la identidad la gobierna
    # _same_cover, que también requiere PIL → sin default-deny redundante aquí).
    assert fbc._is_soft_image(b"") is False
    assert fbc._is_soft_image(b"\x00\x01\x02" * 100) is False


def test_guard_boundary_uses_pixel_count():
    # Justo por debajo del guard cuenta como chica; por encima, no.
    below = fbc._is_soft_image(_blurred(_SMALL), guard_px=200_000)   # 135k < 200k
    above = fbc._is_soft_image(_blurred(_SMALL), guard_px=100_000)   # 135k >= 100k
    assert below is True
    assert above is False
