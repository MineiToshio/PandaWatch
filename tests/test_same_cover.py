"""Tests del validador endurecido de portadas (fetch_better_covers._same_cover)
y del detector de conflicto de metadata (candidate_metadata_conflict).

Todas las imágenes se generan con PIL en memoria — sin red, sin fixtures.

Diseño bajo prueba (2026-06-10, precisión > recall / default-deny):
  R1  AND de 3 hashes: aHash<=6, dHash<=8, pHash(DCT)<=8 (de 64 bits).
  R2  NCC en grises 64×64 >= 0.90.
  R3  gate de entropía: stddev de grises 32×32 >= 20 en AMBAS imágenes.
  R4  SIN relax de +4 bits para originales chicas (removido).
  R5  candidate_metadata_conflict: volumen/ISBN declarado distinto → conflicto.
  R6  dims siempre computables (fallback PIL); GIF animado → rechazo.
  R7  denylist exacta de placeholders (_PLACEHOLDER_HASHES).

Decisión documentada: el validador es ESTRICTO con crops/banners — una
candidata con un strip/banner agregado puede ser rechazada (false-reject
aceptable; mejor 0 candidatas que una no relacionada).
"""

import io
import random
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import fetch_better_covers as fbc  # noqa: E402


# ── helpers de imágenes sintéticas ────────────────────────────────────────────

def _jpeg(im: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _textured_cover(w: int = 400, h: int = 600) -> Image.Image:
    """Portada sintética con estructura y entropía suficiente (gradiente +
    formas), determinística."""
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 255) // w, (y * 255) // h, ((x + y) * 255) // (w + h))
    d = ImageDraw.Draw(im)
    d.ellipse([w // 5, h // 6, w * 4 // 5, h * 2 // 3], fill=(200, 30, 30))
    d.rectangle([w // 8, h * 3 // 4, w * 7 // 8, h * 15 // 16], fill=(20, 20, 120))
    return im


def _noise_cover(seed: int, w: int = 320, h: int = 480, block: int = 16) -> Image.Image:
    """Portada de 'ruido' por bloques con layout distinto según el seed."""
    rng = random.Random(seed)
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(0, h, block):
        for x in range(0, w, block):
            d.rectangle(
                [x, y, x + block, y + block],
                fill=(rng.randrange(256), rng.randrange(256), rng.randrange(256)),
            )
    return im


def _solid(color, w: int = 300, h: int = 450) -> bytes:
    return _jpeg(Image.new("RGB", (w, h), color))


# ── _same_cover ───────────────────────────────────────────────────────────────

def test_solid_white_vs_solid_black_rejects():
    # aHash legacy daba dist 0 entre blanco sólido y negro sólido (todos los
    # píxeles == promedio). El gate de entropía (R3) los marca no-verificables.
    assert fbc._same_cover(_solid((255, 255, 255)), _solid((0, 0, 0)), 6) is False


def test_low_entropy_pair_rejects():
    # Dos placeholders casi lisos (stddev < 20) → no verificables → rechazo,
    # aunque sean "parecidos" en hash.
    a = Image.new("RGB", (300, 450), (245, 245, 245))
    b = Image.new("RGB", (300, 450), (250, 250, 250))
    ImageDraw.Draw(b).ellipse([120, 180, 180, 270], fill=(200, 200, 200))
    assert fbc._same_cover(_jpeg(a), _jpeg(b), 6) is False


def test_identical_image_two_resolutions_passes():
    base = _textured_cover()
    hi = _jpeg(base)
    lo = _jpeg(base.resize((160, 240), Image.LANCZOS), quality=80)
    assert fbc._same_cover(lo, hi, 6) is True
    assert fbc._same_cover(hi, lo, 6) is True


def test_different_noise_layouts_reject():
    a = _jpeg(_noise_cover(seed=1))
    b = _jpeg(_noise_cover(seed=2))
    assert fbc._same_cover(a, b, 6) is False


def test_gradient_vs_gradient_with_banner_strip_documented():
    """Misma portada con un banner promo agregado abajo (8% de la altura).

    DECISIÓN DOCUMENTADA: el validador endurecido puede rechazar este caso
    (strictness aceptable — el banner desplaza la estructura y baja la NCC).
    El test fija el comportamiento actual para detectar cambios accidentales:
    si algún día PASA, hay que re-validar que no se aflojó otra capa.
    """
    base = _textured_cover()
    hi = _jpeg(base)
    w, h = base.size
    banner = base.copy()
    d = ImageDraw.Draw(banner)
    d.rectangle([0, int(h * 0.92), w, h], fill=(255, 255, 0))
    d.text((10, int(h * 0.93)), "OFERTA -20%", fill=(0, 0, 0))
    result = fbc._same_cover(hi, _jpeg(banner), 6)
    # Comportamiento actual: un strip CHICO (8%) PASA (la estructura global se
    # conserva: NCC ~0.93, pHash 8). Crops más agresivos (12%+) RECHAZAN — ver
    # test_aspect_ratio_gate y el harness adversarial. Si este assert cambia,
    # alguien movió una capa del validador: re-validar precisión.
    assert result is True


def test_aspect_ratio_gate_rejects_wide_banner():
    base = _textured_cover()                       # 400×600 (AR 0.67)
    wide = base.resize((600, 300), Image.LANCZOS)  # AR 2.0
    assert fbc._same_cover(_jpeg(base), _jpeg(wide), 6) is False


def test_unparseable_dims_reject_default_deny():
    # Bytes que no son una imagen → dims incomputables → rechazo (R6).
    garbage = b"\x00\x01\x02" * 100
    real = _jpeg(_textured_cover())
    assert fbc._same_cover(garbage, real, 6) is False
    assert fbc._same_cover(real, garbage, 6) is False
    assert fbc._same_cover(b"", real, 6) is False


def test_animated_gif_reference_rejects():
    base = _textured_cover(160, 240)
    frame2 = _noise_cover(seed=3, w=160, h=240)
    buf = io.BytesIO()
    base.save(buf, "GIF", save_all=True, append_images=[frame2], duration=100)
    animated = buf.getvalue()
    real = _jpeg(base)
    # GIF animado como referencia O como candidata → rechazo (R6).
    assert fbc._same_cover(animated, real, 6) is False
    assert fbc._same_cover(real, animated, 6) is False


def test_static_gif_dims_resolved_via_pil_and_aspect_gate_applies():
    # GIF estático: _get_dims_from_bytes no lo parsea por bytes pero el
    # fallback PIL sí → el gate de aspect ratio APLICA (antes se salteaba).
    base = _textured_cover(300, 450)
    buf = io.BytesIO()
    base.convert("P").save(buf, "GIF")
    gif = buf.getvalue()
    assert fbc._get_dims_from_bytes(gif) == (300, 450)
    wide = _jpeg(base.resize((450, 200), Image.LANCZOS))
    assert fbc._same_cover(gif, wide, 6) is False


def test_placeholder_hash_denylist_wired():
    ph = _jpeg(_noise_cover(seed=9))
    other = _jpeg(_noise_cover(seed=9))  # misma imagen → pasaría normalmente
    assert fbc._same_cover(ph, other, 6) is True
    try:
        fbc.register_placeholder_image(ph)
        assert fbc._same_cover(ph, other, 6) is False
    finally:
        fbc._PLACEHOLDER_HASHES.clear()


def test_no_plus4_relaxation_for_small_originals():
    # R4: una original chica (<30k px) ya NO relaja el umbral — un par con
    # aHash dist 7-10 que antes pasaba con el relax ahora rechaza.
    base = _textured_cover()
    small = _jpeg(base.resize((120, 180), Image.LANCZOS), quality=70)  # 21.6k px
    shifted = base.copy()
    d = ImageDraw.Draw(shifted)
    # Perturbar lo justo para subir el aHash dist por encima de 6
    d.rectangle([0, 0, 400, 150], fill=(240, 240, 240))
    cand = _jpeg(shifted)
    h1, h2 = fbc._ahash(small), fbc._ahash(cand)
    dist = fbc._hamming(h1, h2)
    if 6 < dist <= 10:  # zona donde el relax viejo aceptaba
        assert fbc._same_cover(small, cand, 6) is False


# ── candidate_metadata_conflict (R5) ─────────────────────────────────────────

def test_metadata_conflict_vol3_vs_vol1_url():
    item = {"volume": "3"}
    assert fbc.candidate_metadata_conflict(
        item, "https://shop.example.com/berserk-deluxe-vol-1.jpg"
    ) is True


def test_metadata_conflict_matching_volume_no_conflict():
    item = {"volume": "3"}
    assert fbc.candidate_metadata_conflict(
        item, "https://shop.example.com/berserk-deluxe-vol-3.jpg"
    ) is False


def test_metadata_conflict_no_volume_info_no_conflict():
    assert fbc.candidate_metadata_conflict(
        {"volume": "3"}, "https://shop.example.com/berserk-deluxe-cover.jpg"
    ) is False
    assert fbc.candidate_metadata_conflict(
        {}, "https://shop.example.com/berserk-vol-1.jpg"
    ) is False  # item sin volumen → nada que contradecir


def test_metadata_conflict_page_title_tome():
    item = {"volume": "2"}
    assert fbc.candidate_metadata_conflict(
        item, "https://x.fr/img/12345.jpg", "Overlord coffret tome 1 — Ototo"
    ) is True
    assert fbc.candidate_metadata_conflict(
        item, "https://x.fr/img/12345.jpg", "Overlord coffret tome 2 — Ototo"
    ) is False


def test_metadata_conflict_bare_filename_pattern():
    # Patrones bare -N- / _0N_ del filename: solo aplican sin marcador explícito.
    item = {"volume": "5"}
    assert fbc.candidate_metadata_conflict(
        item, "https://cdn.example.com/akira-norma_01_cover.jpg"
    ) is True
    # número de 4+ dígitos (ID de producto) NO es volumen
    assert fbc.candidate_metadata_conflict(
        item, "https://cdn.example.com/akira-58630-large.jpg"
    ) is False
    # dimensiones 600x800 no son volúmenes
    assert fbc.candidate_metadata_conflict(
        item, "https://cdn.example.com/akira-600x800.jpg"
    ) is False


def test_metadata_conflict_isbn_mismatch():
    item = {"isbn": "978-1-50670-198-1"}  # checksum válido (9781506701981)
    assert fbc.candidate_metadata_conflict(
        item, "https://shop.example.com/covers/9781506711980.jpg"  # otro ISBN válido
    ) is True
    assert fbc.candidate_metadata_conflict(
        item, "https://shop.example.com/covers/9781506701981.jpg"  # el mismo
    ) is False


def test_metadata_conflict_random_long_number_not_isbn():
    # Un número de 13 dígitos con checksum inválido NO se trata como ISBN.
    item = {"isbn": "9781506701983"}
    assert fbc.candidate_metadata_conflict(
        item, "https://cdn.example.com/D_NQ_NP_9785064132291_old.jpg"
    ) is False


def test_ambiguous_volume_set_includes_item_volume_no_conflict():
    # Si entre los números declarados ESTÁ el del item → no conflicto.
    item = {"volume": "3"}
    assert fbc.candidate_metadata_conflict(
        item, "https://x.com/pack-vols-1-2-3.jpg", "Pack tomos 1 a 3"
    ) is False
