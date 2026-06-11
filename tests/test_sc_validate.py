"""Tests del validador permanente sc_validate.py (skill watch-search-covers).

Todos los tests son SIN red — monkeypatch de fbc._fetch.
Las imágenes sintéticas se generan con PIL en memoria, igual que test_same_cover.py.

Cobertura:
  1. test_rejects_metadata_conflict  — R5: reject ANTES del fetch (no llega a _fetch)
  2. test_accepts_same_cover_better_res — candidata = misma imagen escalada → verified True
  3. test_rejects_different_cover    — candidata = imagen distinta → descartada
  4. test_skip_domains               — candidata en pinterest.com → descartada sin fetch
  5. test_uses_production_threshold  — candado anti-drift MAX_HASH_DIST == fbc.DEFAULT_MAX_HASH_DIST
  6. test_upgrade_whakoom            — small→large (upgrade aplicado)
  7. test_upgrade_buscalibre         — fit-in se quita
  8. test_upgrade_wordpress          — sufijo -600x900.jpg se quita
  9. test_upgrade_no_pattern         — URL sin patrón devuelve [url] (original al final)
 10. test_upgrade_original_is_last   — la URL original siempre aparece al final
 11. test_upgrade_integrated_validate — URL small falla min-gain; variante large pasa → new_url = large
"""

import io
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import fetch_better_covers as fbc  # noqa: E402
import sc_validate                 # noqa: E402


# ── helpers de imágenes sintéticas (mismo estilo que test_same_cover.py) ──────

def _jpeg(im: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def _textured_cover(w: int = 400, h: int = 600) -> Image.Image:
    """Portada sintética con estructura y entropía suficiente (gradiente +
    formas), determinística. Pasa el gate de entropía (stddev >> 20)."""
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 255) // w, (y * 255) // h, ((x + y) * 255) // (w + h))
    d = ImageDraw.Draw(im)
    d.ellipse([w // 5, h // 6, w * 4 // 5, h * 2 // 3], fill=(200, 30, 30))
    d.rectangle([w // 8, h * 3 // 4, w * 7 // 8, h * 15 // 16], fill=(20, 20, 120))
    return im


# ── 1. test_rejects_metadata_conflict ─────────────────────────────────────────

def test_rejects_metadata_conflict(tmp_path, monkeypatch):
    """Item volumen 3 + URL declarando vol-11 → reject SIN llamar _fetch."""
    fetch_called = []

    def mock_fetch(url, session, **kwargs):
        fetch_called.append(url)
        return _jpeg(_textured_cover())

    monkeypatch.setattr(fbc, '_fetch', mock_fetch)

    # Referencia: no necesitamos archivo real; curr_bytes vacío → skip _same_cover
    # Pero sí necesitamos que llegue AL candidate_metadata_conflict antes del fetch.
    # Para que _get_current_bytes no truene, dejamos images vacío.
    item = {'volume': '3', 'images': []}
    data = {
        'item': item,
        'candidate_urls': [
            {'url': 'https://example.com/manga-vol-11.jpg', 'page_title': '', 'domain': 'example.com', 'query': 'q'}
        ],
        'curr_px': 0,
        'ref_image_local': '',
    }

    result = sc_validate.validate(data, images_dir=tmp_path)

    # La candidata debe ser descartada POR candidate_metadata_conflict (antes del fetch)
    assert result == [], f"Se esperaba 0 candidatas, got: {result}"
    assert fetch_called == [], (
        f"_fetch no debería haberse llamado para un conflicto de metadata, "
        f"pero se llamó con: {fetch_called}"
    )


# ── 2. test_accepts_same_cover_better_res ─────────────────────────────────────

def test_accepts_same_cover_better_res(tmp_path, monkeypatch):
    """Referencia pequeña + candidata = misma imagen escalada hi-res → verified True."""
    base = _textured_cover(400, 600)           # imagen base
    ref_bytes  = _jpeg(base.resize((160, 240), Image.LANCZOS), quality=80)   # pequeña (ref)
    cand_bytes = _jpeg(base)                                                   # full-res (candidata)

    # Guardar referencia en tmp_path para que validate() la lea
    ref_file = tmp_path / "ref.jpg"
    ref_file.write_bytes(ref_bytes)

    # curr_px de la referencia
    ref_px = fbc._get_pixels_from_bytes(ref_bytes)   # ~38 400

    monkeypatch.setattr(fbc, '_fetch', lambda url, session, **kw: cand_bytes)

    item = {'volume': '1', 'images': []}
    data = {
        'item': item,
        'candidate_urls': [
            {'url': 'https://example.com/cover-hi.jpg', 'page_title': '', 'domain': 'example.com', 'query': 'q'}
        ],
        'curr_px': ref_px,
        'ref_image_local': 'ref.jpg',   # relativo a images_dir (tmp_path)
    }

    result = sc_validate.validate(data, images_dir=tmp_path)

    assert len(result) == 1, f"Se esperaba 1 candidata aceptada, got: {result}"
    assert result[0]['verified'] is True
    assert result[0]['match_dist'] is not None
    assert result[0]['match_dist'] <= sc_validate.MAX_HASH_DIST


# ── 3. test_rejects_different_cover ───────────────────────────────────────────

def test_rejects_different_cover(tmp_path, monkeypatch):
    """Candidata con imagen visualmente distinta a la referencia → descartada."""
    import random

    base = _textured_cover(400, 600)
    ref_bytes = _jpeg(base)

    # Imagen diferente: colores completamente distintos + formas distintas
    rng = random.Random(42)
    other = Image.new("RGB", (400, 600))
    d = ImageDraw.Draw(other)
    for _ in range(30):
        x0, y0 = rng.randint(0, 350), rng.randint(0, 550)
        d.rectangle([x0, y0, x0 + 50, y0 + 50],
                    fill=(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)))
    cand_bytes = _jpeg(other)

    ref_px = fbc._get_pixels_from_bytes(ref_bytes)
    ref_file = tmp_path / "ref.jpg"
    ref_file.write_bytes(ref_bytes)

    monkeypatch.setattr(fbc, '_fetch', lambda url, session, **kw: cand_bytes)

    item = {'images': []}
    data = {
        'item': item,
        'candidate_urls': [
            {'url': 'https://example.com/other-cover.jpg', 'page_title': '', 'domain': 'example.com', 'query': 'q'}
        ],
        'curr_px': ref_px,
        'ref_image_local': 'ref.jpg',
    }

    result = sc_validate.validate(data, images_dir=tmp_path)
    assert result == [], f"La candidata diferente no debería aceptarse, got: {result}"


# ── 4. test_skip_domains ──────────────────────────────────────────────────────

def test_skip_domains(tmp_path, monkeypatch):
    """Candidata en dominio de la denylist → descartada sin llamar a _fetch."""
    fetch_called = []

    def mock_fetch(url, session, **kw):
        fetch_called.append(url)
        return _jpeg(_textured_cover())

    monkeypatch.setattr(fbc, '_fetch', mock_fetch)

    item = {'images': []}
    data = {
        'item': item,
        'candidate_urls': [
            {'url': 'https://pinterest.com/pin/12345.jpg', 'page_title': '',
             'domain': 'pinterest.com', 'query': 'q'}
        ],
        'curr_px': 0,
        'ref_image_local': '',
    }

    result = sc_validate.validate(data, images_dir=tmp_path)
    assert result == [], "pinterest.com debe estar en la denylist"
    assert fetch_called == [], "_fetch no debe llamarse para dominios en denylist"


# ── 5. test_uses_production_threshold ────────────────────────────────────────

def test_uses_production_threshold():
    """Candado anti-drift: sc_validate.MAX_HASH_DIST debe coincidir con producción."""
    assert sc_validate.MAX_HASH_DIST == fbc.DEFAULT_MAX_HASH_DIST, (
        f"sc_validate.MAX_HASH_DIST ({sc_validate.MAX_HASH_DIST}) != "
        f"fbc.DEFAULT_MAX_HASH_DIST ({fbc.DEFAULT_MAX_HASH_DIST}). "
        "El umbral drifteó — revisá sc_validate.py."
    )


# ── 6-10. Tests de upgrade_url_variants ───────────────────────────────────────

def test_upgrade_whakoom():
    """whakoom: small → large (CDN upgrade verificado 2026-06-11)."""
    url = 'https://i1.whakoom.com/small/ab/cd.jpg'
    variants = sc_validate.upgrade_url_variants(url)
    assert variants[0] == 'https://i1.whakoom.com/large/ab/cd.jpg'
    assert variants[-1] == url


def test_upgrade_buscalibre():
    """buscalibre: quita segmento fit-in/<W>x<H>/."""
    url = 'https://images.cdn3.buscalibre.com/fit-in/360x360/f6/da/x.jpg'
    variants = sc_validate.upgrade_url_variants(url)
    assert variants[0] == 'https://images.cdn3.buscalibre.com/f6/da/x.jpg'
    assert variants[-1] == url


def test_upgrade_wordpress():
    """WordPress genérico: quita sufijo -<W>x<H> del nombre de archivo."""
    url = 'https://example.com/wp-content/uploads/cover-600x900.jpg'
    variants = sc_validate.upgrade_url_variants(url)
    assert variants[0] == 'https://example.com/wp-content/uploads/cover.jpg'
    assert variants[-1] == url


def test_upgrade_no_pattern():
    """URL sin ningún patrón conocido → devuelve solo la original."""
    url = 'https://example.com/images/cover.jpg'
    variants = sc_validate.upgrade_url_variants(url)
    assert variants == [url]


def test_upgrade_original_is_last():
    """La URL original siempre aparece al final (es el fallback)."""
    url = 'https://i1.whakoom.com/thumb/xx/yy.png'
    variants = sc_validate.upgrade_url_variants(url)
    assert len(variants) == 2
    assert variants[-1] == url


# ── 11. Test de integración — upgrade aplicado en validate() ─────────────────

def test_upgrade_integrated_validate(tmp_path, monkeypatch):
    """URL 'small' falla el min-gain (imagen chica); variante 'large' devuelve imagen
    grande idéntica → se acepta, y new_url == la URL large (no la original small)."""
    base = _textured_cover(400, 600)
    ref_bytes   = _jpeg(base.resize((160, 240), Image.LANCZOS), quality=80)   # pequeña (ref)
    large_bytes = _jpeg(base)                                                   # full-res

    ref_px = fbc._get_pixels_from_bytes(ref_bytes)   # ~38 400

    # Guardar referencia en disco
    ref_file = tmp_path / "ref_small.jpg"
    ref_file.write_bytes(ref_bytes)

    small_url = 'https://i1.whakoom.com/small/ab/cover.jpg'
    large_url = 'https://i1.whakoom.com/large/ab/cover.jpg'

    def mock_fetch(url, session, **kw):
        if 'small' in url:
            # La URL small devuelve la imagen pequeña → falla el gate de min-gain
            return ref_bytes
        if 'large' in url:
            return large_bytes
        return b''

    monkeypatch.setattr(fbc, '_fetch', mock_fetch)

    item = {'volume': '1', 'images': []}
    data = {
        'item': item,
        'candidate_urls': [
            {'url': small_url, 'page_title': '', 'domain': 'i1.whakoom.com', 'query': 'q'}
        ],
        'curr_px': ref_px,
        'ref_image_local': 'ref_small.jpg',
    }

    result = sc_validate.validate(data, images_dir=tmp_path)

    assert len(result) == 1, f"Se esperaba 1 candidata aceptada, got: {result}"
    assert result[0]['new_url'] == large_url, (
        f"new_url debe ser la variante large, got: {result[0]['new_url']}"
    )
    assert result[0]['verified'] is True
