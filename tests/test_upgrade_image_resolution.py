"""Tests para derive_original_url / needs_same_cover_validation.

Solo prueban la lógica de reescritura de URL — sin red ni fixtures en disco.
Cubre los 4 patrones nuevos verificados empíricamente (2026-06-11):
  buscalibre, cultura, whakoom, magento-cache-path.
Y los 5 patrones anteriores (regresión):
  magento-query-params, wordpress, shopify, amazon, rakuten.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = str(_ROOT / "scripts")
_RETROFIT = str(_ROOT / "scripts" / "retrofit")

# upgrade_image_resolution.py importa manga_watch y image_store al nivel de módulo.
# Para poder importar SOLO las funciones puras (derive_original_url,
# needs_same_cover_validation) sin ejecutar esos imports, usamos un mock liviano
# que satisface el `from manga_watch import backup_and_rotate, make_session`
# del script antes de que corra en el contexto de pytest.
import types  # noqa: E402
import unittest.mock as _mock  # noqa: E402

# Crear stubs mínimos si los módulos no están cargados aún
if "manga_watch" not in sys.modules or not hasattr(sys.modules.get("manga_watch"), "backup_and_rotate"):
    _mw_stub = types.ModuleType("manga_watch")
    _mw_stub.backup_and_rotate = _mock.MagicMock()  # type: ignore[attr-defined]
    _mw_stub.make_session = _mock.MagicMock()  # type: ignore[attr-defined]
    sys.modules["manga_watch"] = _mw_stub

if "image_store" not in sys.modules:
    _is_stub = types.ModuleType("image_store")
    _is_stub.download_image = _mock.MagicMock()  # type: ignore[attr-defined]
    sys.modules["image_store"] = _is_stub

# Limpiar caché si upgrade_image_resolution fue importado antes (de otra corrida)
if "upgrade_image_resolution" in sys.modules:
    del sys.modules["upgrade_image_resolution"]

if _RETROFIT not in sys.path:
    sys.path.insert(0, _RETROFIT)

from upgrade_image_resolution import derive_original_url, needs_same_cover_validation  # noqa: E402


# ── Patrones anteriores (regresión) ───────────────────────────────────────────

class TestMagentoQueryParams:
    def test_strips_width_height(self):
        url = "https://example.com/image.jpg?quality=80&width=222&height=222&bg-color=ffffff"
        result = derive_original_url(url)
        assert result == "https://example.com/image.jpg"

    def test_no_dimension_param_unchanged(self):
        url = "https://example.com/image.jpg?quality=80"
        assert derive_original_url(url) is None

    def test_already_clean(self):
        url = "https://example.com/image.jpg"
        assert derive_original_url(url) is None


class TestWordPress:
    def test_strips_NxM_suffix(self):
        url = "https://mangavariant.com/wp-content/uploads/image-300x450.jpg"
        result = derive_original_url(url)
        assert result == "https://mangavariant.com/wp-content/uploads/image.jpg"

    def test_strips_150x228(self):
        url = "https://example.com/image-150x228.png"
        result = derive_original_url(url)
        assert result == "https://example.com/image.png"

    def test_no_wp_suffix(self):
        assert derive_original_url("https://example.com/image.jpg") is None


class TestShopify:
    def test_strips_520x520(self):
        url = "https://example.myshopify.com/image_520x520.jpg"
        result = derive_original_url(url)
        assert result == "https://example.myshopify.com/image.jpg"

    def test_strips_540x(self):
        url = "https://example.com/image_540x.jpg"
        result = derive_original_url(url)
        assert result == "https://example.com/image.jpg"


class TestAmazon:
    def test_strips_SY300(self):
        url = "https://m.media-amazon.com/images/P/91XYZ._SY300_.jpg"
        result = derive_original_url(url)
        assert result == "https://m.media-amazon.com/images/P/91XYZ.jpg"

    def test_not_amazon_host_unchanged(self):
        url = "https://example.com/91XYZ._SY300_.jpg"
        assert derive_original_url(url) is None


class TestRakuten:
    def test_strips_ex_param(self):
        url = "https://thumbnail.image.rakuten.co.jp/cabinet/9312/2100014729312.jpg?_ex=200x200"
        result = derive_original_url(url)
        assert result == "https://thumbnail.image.rakuten.co.jp/cabinet/9312/2100014729312.jpg"

    def test_non_rakuten_host_unchanged(self):
        url = "https://example.com/image.jpg?_ex=200x200"
        assert derive_original_url(url) is None


# ── Patrones nuevos verificados empíricamente (2026-06-11) ────────────────────

class TestBuscalibre:
    def test_strips_fit_in_segment(self):
        url = "https://images.cdn1.buscalibre.com/fit-in/360x360/e4/ab/e4ab1234567890.jpg"
        result = derive_original_url(url)
        assert result == "https://images.cdn1.buscalibre.com/e4/ab/e4ab1234567890.jpg"

    def test_strips_fit_in_cdn2(self):
        url = "https://images.cdn2.buscalibre.com/fit-in/200x300/abc/def/image.png"
        result = derive_original_url(url)
        assert result == "https://images.cdn2.buscalibre.com/abc/def/image.png"

    def test_not_buscalibre_host_unchanged(self):
        url = "https://images.example.com/fit-in/360x360/image.jpg"
        assert derive_original_url(url) is None

    def test_no_fit_in_unchanged(self):
        url = "https://images.cdn1.buscalibre.com/e4/ab/e4ab1234567890.jpg"
        assert derive_original_url(url) is None

    def test_does_not_need_same_cover(self):
        url = "https://images.cdn1.buscalibre.com/fit-in/360x360/image.jpg"
        assert not needs_same_cover_validation(url)


class TestCultura:
    def test_strips_cdncgi_segment(self):
        url = "https://cdn.cultura.com/cdn-cgi/image/width=300/media/catalog/product/image.jpg"
        result = derive_original_url(url)
        assert result == "https://cdn.cultura.com/media/catalog/product/image.jpg"

    def test_strips_cdncgi_with_format(self):
        url = "https://cdn.cultura.com/cdn-cgi/image/width=500,format=webp/img/product.png"
        result = derive_original_url(url)
        assert result == "https://cdn.cultura.com/img/product.png"

    def test_not_cultura_host_unchanged(self):
        url = "https://cdn.example.com/cdn-cgi/image/width=300/image.jpg"
        assert derive_original_url(url) is None

    def test_no_cdncgi_unchanged(self):
        url = "https://cdn.cultura.com/media/catalog/product/image.jpg"
        assert derive_original_url(url) is None


class TestWhakoom:
    def test_small_to_large(self):
        url = "https://i1.whakoom.com/small/abc123/cover.jpg"
        result = derive_original_url(url)
        assert result == "https://i1.whakoom.com/large/abc123/cover.jpg"

    def test_thumb_to_large(self):
        url = "https://i1.whakoom.com/thumb/def456/cover.jpg"
        result = derive_original_url(url)
        assert result == "https://i1.whakoom.com/large/def456/cover.jpg"

    def test_medium_to_large(self):
        url = "https://i1.whakoom.com/medium/ghi789/cover.jpg"
        result = derive_original_url(url)
        assert result == "https://i1.whakoom.com/large/ghi789/cover.jpg"

    def test_large_unchanged(self):
        url = "https://i1.whakoom.com/large/abc123/cover.jpg"
        assert derive_original_url(url) is None

    def test_not_whakoom_host_unchanged(self):
        url = "https://example.com/small/abc123/cover.jpg"
        assert derive_original_url(url) is None


class TestMagentoCachePath:
    def test_strips_cache_path(self):
        url = "https://www.bdfugue.com/media/catalog/product/cache/abc123def456/i/m/image.jpg"
        result = derive_original_url(url)
        assert result == "https://www.bdfugue.com/media/catalog/product/i/m/image.jpg"

    def test_needs_same_cover_validation(self):
        url = "https://www.bdfugue.com/media/catalog/product/cache/abc123def456/i/m/image.jpg"
        assert needs_same_cover_validation(url)

    def test_clean_url_no_validation_needed(self):
        url = "https://www.bdfugue.com/media/catalog/product/i/m/image.jpg"
        assert not needs_same_cover_validation(url)

    def test_no_cache_path_unchanged(self):
        url = "https://www.example.com/media/catalog/product/image.jpg"
        # No tiene cache/<hex>/ — devuelve None
        assert derive_original_url(url) is None

    def test_buscalibre_does_not_need_validation(self):
        # Aseguramos que el marcador same_cover solo aplique a Magento cache,
        # no a otros patrones.
        url = "https://images.cdn1.buscalibre.com/fit-in/360x360/image.jpg"
        assert not needs_same_cover_validation(url)


class TestEdgeCases:
    def test_empty_string(self):
        assert derive_original_url("") is None

    def test_none_like_empty(self):
        # La función acepta str según typing; pasamos vacío
        assert derive_original_url("") is None

    def test_no_http_unchanged(self):
        # URLs no-http no se procesan (no tienen netloc parseable)
        assert derive_original_url("ftp://example.com/image.jpg") is None
