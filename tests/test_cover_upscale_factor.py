"""Tests para `fetch_better_covers.cover_upscale_factor` / `UPSCALE_TARGET_MIN`.

Contexto (Etapa 1 de triage de imágenes, 2026-09-02, ver docs/reference/images.md
§ "Etapa 1 — resultados" y gotchas #170-#172): el ÁREA (`LOW_QUALITY_PX`) NO
predice si una portada se ve mal en la card del catálogo (300×420 px,
`object-fit: contain`) — el factor de reescalado `min(300/w, 420/h)` sí, con
una distribución bimodal confirmada sobre 579 casos reales (528 con factor
<=1.6 se ven bien, 51 con factor >=2.0 se ven mal / son placeholder). Estos
tests fijan el contrato de la función pura; no tocan LOW_QUALITY_PX ni sus
otros consumidores (panel "pixelada", sync_cover_preview, promote_hires_cover).
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "scripts" / "retrofit") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import fetch_better_covers as fbc  # type: ignore  # noqa: E402


def test_upscale_target_min_is_1_6():
    """Umbral recomendado por el juez de visión de la Etapa 1 — el hueco real
    de la distribución bimodal (528 casos <=1.6, 51 casos >=2.0, sólo 2 en
    el medio)."""
    assert fbc.UPSCALE_TARGET_MIN == 1.6


def test_square_image_uses_the_tighter_dimension():
    # card 300x420: el lado limitante para un cuadrado es el ancho (300/300=1.0
    # < 420/300=1.4)
    assert fbc.cover_upscale_factor(300, 300) == 1.0
    # 100x100 -> min(300/100, 420/100) = min(3.0, 4.2) = 3.0 (bien por encima
    # del umbral 1.6, candidato claro a búsqueda)
    assert fbc.cover_upscale_factor(100, 100) == 3.0


def test_listadomanga_thumbnail_matches_documented_1_4x():
    """210x300 (thumbnail típico de static.listadomanga.com, el 84% del lote A
    de la Etapa 1) da 1.4x — por debajo del umbral 1.6, se ve bien. Confirma el
    número citado textualmente en docs/reference/images.md."""
    factor = fbc.cover_upscale_factor(210, 300)
    assert round(factor, 2) == 1.4
    assert factor < fbc.UPSCALE_TARGET_MIN


def test_landscape_aladin_cover150_crop_matches_documented_2x():
    """150x76 (cover150/ de image.aladin.co.kr, recorte apaisado destruido,
    citado en gotcha #171/docs) da exactamente 2.0x — el peor caso, muy por
    encima del umbral."""
    factor = fbc.cover_upscale_factor(150, 76)
    assert factor == 2.0
    assert factor >= fbc.UPSCALE_TARGET_MIN


def test_large_image_fits_without_stretching():
    # espejo normalizado AVIF (<=1600px de lado largo): la imagen entra sin
    # estirarse, factor < 1.0
    factor = fbc.cover_upscale_factor(1131, 1600)
    assert factor < 1.0


def test_small_portrait_image_above_threshold():
    # retrato chico y genuinamente blando (ej. 60x90) -> factor alto
    factor = fbc.cover_upscale_factor(60, 90)
    assert factor == min(300 / 60, 420 / 90)
    assert factor > fbc.UPSCALE_TARGET_MIN


def test_zero_or_negative_dims_return_infinity():
    """Dimensiones no computables (referencia degenerada/placeholder) se tratan
    como el peor caso posible, igual que 'sin imagen'."""
    assert fbc.cover_upscale_factor(0, 0) == float("inf")
    assert fbc.cover_upscale_factor(0, 300) == float("inf")
    assert fbc.cover_upscale_factor(300, 0) == float("inf")
    assert fbc.cover_upscale_factor(-10, 300) == float("inf")


def test_custom_card_size_is_respected():
    # función pura y parametrizable — no hardcodea 300x420 internamente
    assert fbc.cover_upscale_factor(100, 100, card_w=100, card_h=100) == 1.0
    assert fbc.cover_upscale_factor(50, 50, card_w=100, card_h=200) == 2.0
