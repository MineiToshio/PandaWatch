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

import re as _re  # noqa: E402


def _stub_img_stem(url: str) -> str:
    """Reimplementación fiel (no mock) de `manga_watch._img_stem` para este
    stub liviano — dedupe_item_images (gotcha #181) la necesita con semántica
    REAL (no un MagicMock) para que los tests de dedup por-stem sean
    significativos. Misma normalización que el original: strip de sufijos de
    thumb conocidos + query params irrelevantes, sin protocolo, lowercase."""
    if not url:
        return ""
    u = _re.sub(
        r"_(?:\d+x\d+|small|medium|grande|large|master|compact|original|x\d+|pico|icon|thumb|mini|crop_center)"
        r"(?=\.(?:jpe?g|png|webp|gif|avif)(?:\?|$))",
        "",
        url,
        flags=_re.IGNORECASE,
    )
    if "?" in u:
        base, q = u.split("?", 1)
        keep = []
        for pair in q.split("&"):
            k = pair.split("=", 1)[0].lower()
            if k in {"v", "version", "_", "t", "rev", "cache", "ts"}:
                continue
            keep.append(pair)
        u = base + ("?" + "&".join(keep) if keep else "")
    return _re.sub(r"^https?://", "", u.split("?", 1)[0]).lower()


# Crear stubs mínimos si los módulos no están cargados aún
if "manga_watch" not in sys.modules or not all(
    hasattr(sys.modules.get("manga_watch"), sym)
    for sym in ("backup_and_rotate", "is_approved", "_img_stem")
):
    _mw_stub = types.ModuleType("manga_watch")
    _mw_stub.backup_and_rotate = _mock.MagicMock()  # type: ignore[attr-defined]
    _mw_stub.make_session = _mock.MagicMock()  # type: ignore[attr-defined]
    # is_approved: WO-D (2026-07-07) agregó el guard de items aprobados al script;
    # el import de nivel de módulo lo necesita aunque este archivo solo pruebe
    # las funciones puras (derive_original_url / needs_same_cover_validation).
    _mw_stub.is_approved = _mock.MagicMock(return_value=False)  # type: ignore[attr-defined]
    # _img_stem: dedupe_item_images (gotcha #181) la necesita con semántica real.
    _mw_stub._img_stem = _stub_img_stem  # type: ignore[attr-defined]
    sys.modules["manga_watch"] = _mw_stub

if "image_store" not in sys.modules:
    _is_stub = types.ModuleType("image_store")
    _is_stub.download_image = _mock.MagicMock()  # type: ignore[attr-defined]
    # known_placeholder_url_reason: el patrón Rakuten r10s.jp (#11) lo usa como
    # guard anti-.gif. Stub devuelve "" (no-placeholder) por defecto.
    _is_stub.known_placeholder_url_reason = _mock.MagicMock(return_value="")  # type: ignore[attr-defined]
    sys.modules["image_store"] = _is_stub

# Limpiar caché si upgrade_image_resolution fue importado antes (de otra corrida)
if "upgrade_image_resolution" in sys.modules:
    del sys.modules["upgrade_image_resolution"]

if _RETROFIT not in sys.path:
    sys.path.insert(0, _RETROFIT)

from upgrade_image_resolution import (  # noqa: E402
    derive_original_url, needs_same_cover_validation, _collect_targets,
    dedupe_item_images,
)


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
    def test_rewrites_fit_in_to_1200(self):
        """Gotcha #167 (2026-09-01): reescribe a fit-in/1200x1200/, NO quita el
        segmento entero — quitarlo del todo devuelve un tamaño "base"
        intermedio del CDN (verificado en vivo: 384×540), bastante menor que
        pedir 1200x1200 explícito (853×1200, 5× más píxeles)."""
        url = "https://images.cdn1.buscalibre.com/fit-in/360x360/e4/ab/e4ab1234567890.jpg"
        result = derive_original_url(url)
        assert result == "https://images.cdn1.buscalibre.com/fit-in/1200x1200/e4/ab/e4ab1234567890.jpg"

    def test_rewrites_fit_in_cdn2(self):
        url = "https://images.cdn2.buscalibre.com/fit-in/200x300/abc/def/image.png"
        result = derive_original_url(url)
        assert result == "https://images.cdn2.buscalibre.com/fit-in/1200x1200/abc/def/image.png"

    def test_not_buscalibre_host_unchanged(self):
        url = "https://images.example.com/fit-in/360x360/image.jpg"
        assert derive_original_url(url) is None

    def test_no_fit_in_unchanged(self):
        url = "https://images.cdn1.buscalibre.com/e4/ab/e4ab1234567890.jpg"
        assert derive_original_url(url) is None

    def test_does_not_downgrade_already_large(self):
        """Un fit-in que ya pide ≥1200 en ambas dimensiones no se re-capa."""
        url = "https://images.cdn1.buscalibre.com/fit-in/1500x1500/e4/ab/img.jpg"
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


class TestAladinCover:
    """gotcha #177 — image.aladin.co.kr/.../cover<N>/<archivo>, cover500 es el
    techo real del CDN (cover800/1000/1200 → 404, verificado en vivo)."""

    def test_cover150_to_cover500(self):
        url = "https://image.aladin.co.kr/product/34447/25/cover150/k242932338_1.jpg"
        result = derive_original_url(url)
        assert result == "https://image.aladin.co.kr/product/34447/25/cover500/k242932338_1.jpg"

    def test_cover200_to_cover500(self):
        url = "https://image.aladin.co.kr/product/101/30/cover200/8925806460_1.jpg"
        result = derive_original_url(url)
        assert result == "https://image.aladin.co.kr/product/101/30/cover500/8925806460_1.jpg"

    def test_cover500_already_max_unchanged(self):
        # No re-capa: cover500 ya es el techo real del CDN.
        url = "https://image.aladin.co.kr/product/34447/25/cover500/k242932338_1.jpg"
        assert derive_original_url(url) is None

    def test_not_aladin_host_unchanged(self):
        # Un host distinto con un path /coverNNN/ parecido no debe dispararse.
        url = "https://example.com/product/cover150/image.jpg"
        assert derive_original_url(url) is None

    def test_does_not_need_same_cover_validation(self):
        # Es un patrón determinístico (mismo archivo, misma ruta) — no requiere
        # el gate same_cover que sí exige el Magento cache path.
        url = "https://image.aladin.co.kr/product/34447/25/cover150/k242932338_1.jpg"
        assert not needs_same_cover_validation(url)


class TestRakutenR10s:
    """Rakuten Books CDN familia r10s.jp (tshop/shop.r10s.jp): downsize/fitin →
    sin query, misma imagen a resolución nativa (2026-09-02, verificado con
    requests reales: downsize=130:* → 130×184, sin query → 844×1200, mismo
    archivo). Distinto del host thumbnail.image.rakuten.co.jp del patrón #5
    (?_ex=), aunque sea la misma tienda."""

    def test_strips_downsize_param(self):
        url = "https://tshop.r10s.jp/book/cabinet/4771/9784040764771_1_15.jpg?downsize=130:*"
        result = derive_original_url(url)
        assert result == "https://tshop.r10s.jp/book/cabinet/4771/9784040764771_1_15.jpg"

    def test_strips_fitin_composite_to(self):
        url = (
            "https://shop.r10s.jp/book/cabinet/3733/9784758023733_1_3.jpg"
            "?fitin=560:400&composite-to=*,*|560:400"
        )
        result = derive_original_url(url)
        assert result == "https://shop.r10s.jp/book/cabinet/3733/9784758023733_1_3.jpg"

    def test_not_r10s_host_unchanged(self):
        url = "https://example.com/book/cabinet/4771/9784040764771_1_15.jpg?downsize=130:*"
        assert derive_original_url(url) is None

    def test_already_clean_unchanged(self):
        url = "https://tshop.r10s.jp/book/cabinet/4771/9784040764771_1_15.jpg"
        assert derive_original_url(url) is None

    def test_no_resize_param_unchanged(self):
        # Query presente pero sin ninguno de los params de resize conocidos.
        url = "https://tshop.r10s.jp/book/cabinet/4771/9784040764771_1_15.jpg?v=2"
        assert derive_original_url(url) is None

    def test_thumbnail_host_not_matched_by_this_pattern(self):
        # thumbnail.image.rakuten.co.jp lo cubre el patrón #5 (?_ex=), no éste.
        url = "https://thumbnail.image.rakuten.co.jp/@0_mall/book/cabinet/5019/x.jpg?downsize=130:*"
        assert derive_original_url(url) is None

    def test_gif_placeholder_excluded(self, monkeypatch):
        # Guard: nunca "mejorar" la tarjeta de título .gif (gotcha #171/#176).
        import upgrade_image_resolution as _uir
        monkeypatch.setattr(
            _uir.image_store, "known_placeholder_url_reason",
            lambda u: "known:rakuten:title-card-gif",
        )
        url = "https://tshop.r10s.jp/book/cabinet/0135/9784801990135.gif?downsize=130:*"
        assert derive_original_url(url) is None

    def test_does_not_need_same_cover_validation(self):
        url = "https://tshop.r10s.jp/book/cabinet/4771/9784040764771_1_15.jpg?downsize=130:*"
        assert not needs_same_cover_validation(url)


class TestCollectTargetsHostFilter:
    """--host acota los targets por substring de netloc (sin tocar otros patrones)."""

    def _item(self, url: str, local: str = "abc.avif") -> dict:
        return {
            "url": "https://example.com/item",
            "images": [{"url": url, "local": local}],
        }

    def test_host_filter_keeps_matching(self):
        items = [
            self._item("https://image.aladin.co.kr/product/1/1/cover150/x_1.jpg"),
            self._item("https://images.cdn1.buscalibre.com/fit-in/360x360/y.jpg"),
        ]
        targets, _ = _collect_targets(items, host="aladin.co.kr")
        assert len(targets) == 1
        assert "aladin" in targets[0][2]

    def test_host_filter_empty_matches_all(self):
        items = [
            self._item("https://image.aladin.co.kr/product/1/1/cover150/x_1.jpg"),
            self._item("https://images.cdn1.buscalibre.com/fit-in/360x360/y.jpg"),
        ]
        targets, _ = _collect_targets(items, host="")
        assert len(targets) == 2


# ── dedupe_item_images (gotcha #181, 2026-09-02) ───────────────────────────────
# Causa raíz real: 109 items KR-Aladin quedaron con la MISMA foto duplicada en
# images[] tras el upgrade cover150→cover500 (patrón 10) — la portada
# (images[0]) ya estaba en cover500 por otro camino previo (JSON-LD/og:image) y
# una entry de galería en cover150/cover200 apuntaba al MISMO archivo bajo una
# URL textualmente distinta; al normalizar ambas colapsaron a la misma url/local.
# `_apply_upgrade` reescribe cada entry de forma independiente, sin mirar el
# resto de `images[]` del item — `dedupe_item_images` cierra el mecanismo tras
# cada upgrade aplicado.

class TestDedupeItemImages:
    def test_duplicate_by_canonical_url(self):
        """Dos entries con exactamente la misma URL final (el caso real: la
        portada ya en cover500 + la entry de galería recién normalizada a la
        misma cover500) — la 2ª cae, la portada (images[0]) sobrevive."""
        item = {
            "images": [
                {"kind": "gallery", "url": "https://image.aladin.co.kr/p/1/cover500/k1_1.jpg",
                 "local": "aaa.avif"},
                {"kind": "gallery", "url": "https://image.aladin.co.kr/p/1/letslook/k1_b.jpg",
                 "local": "bbb.avif"},
                {"kind": "gallery", "url": "https://image.aladin.co.kr/p/1/cover500/k1_1.jpg",
                 "local": "aaa.avif"},
            ]
        }
        changed = dedupe_item_images(item, Path("/nonexistent"))
        assert changed is True
        imgs = item["images"]
        assert len(imgs) == 2
        # images[0] (portada) se conserva intacta, en su lugar.
        assert imgs[0]["url"] == "https://image.aladin.co.kr/p/1/cover500/k1_1.jpg"
        assert imgs[1]["url"] == "https://image.aladin.co.kr/p/1/letslook/k1_b.jpg"

    def test_duplicate_by_content_sha_distinct_stem(self, tmp_path):
        """Dos entries con URL/local COMPLETAMENTE distintos (distinto stem,
        distinto nombre de archivo) pero el MISMO contenido de bytes en disco
        (mismo sha256) — caso general de "misma foto en dos hosts/nombres",
        que ni el stem ni el local pueden ver, sólo el contenido."""
        images_dir = tmp_path
        content = b"same-photo-bytes-0123456789"
        (images_dir / "onehash.avif").write_bytes(content)
        (images_dir / "otherhash.avif").write_bytes(content)
        item = {
            "images": [
                {"kind": "gallery", "url": "https://cdn-a.example.com/photo-v1.jpg",
                 "local": "onehash.avif"},
                {"kind": "gallery", "url": "https://cdn-b.example.com/completely-different-name.jpg",
                 "local": "otherhash.avif"},
            ]
        }
        changed = dedupe_item_images(item, images_dir)
        assert changed is True
        imgs = item["images"]
        assert len(imgs) == 1
        assert imgs[0]["local"] == "onehash.avif"  # el primero en orden de aparición sobrevive

    def test_no_duplicate_left_untouched(self):
        """3 fotos genuinamente distintas — nada se toca, `changed` es False."""
        item = {
            "images": [
                {"kind": "gallery", "url": "https://example.com/a.jpg", "local": "a.avif"},
                {"kind": "gallery", "url": "https://example.com/b.jpg", "local": "b.avif"},
                {"kind": "gallery", "url": "https://example.com/c.jpg", "local": "c.avif"},
            ]
        }
        before = [dict(im) for im in item["images"]]
        changed = dedupe_item_images(item, Path("/nonexistent"))
        assert changed is False
        assert item["images"] == before

    def test_survivor_inherits_kind_description_from_dropped(self):
        """El duplicado eliminado dona kind/description al sobreviviente
        cuando éste no los tenía — mismo comportamiento sticky que
        `_apply_improvement`/`_union_merge_images` (gotcha #164)."""
        item = {
            "images": [
                {"kind": "gallery", "description": "", "url": "https://x.example.com/cover500/k_1.jpg",
                 "local": "cov.avif"},
                {"kind": "gallery", "description": "Contratapa", "url": "https://x.example.com/cover150/k_1.jpg",
                 "local": "cov.avif"},
            ]
        }
        changed = dedupe_item_images(item, Path("/nonexistent"))
        assert changed is True
        assert len(item["images"]) == 1
        assert item["images"][0]["description"] == "Contratapa"

    def test_fewer_than_two_images_noop(self):
        item = {"images": [{"kind": "gallery", "url": "https://x.example.com/a.jpg", "local": "a.avif"}]}
        assert dedupe_item_images(item, Path("/nonexistent")) is False

    def test_no_images_field_noop(self):
        item = {}
        assert dedupe_item_images(item, Path("/nonexistent")) is False

    def test_never_empties_images(self):
        """Guard defensivo: aunque TODAS las entries sean el mismo duplicado,
        siempre queda al menos 1 (nunca vacía images[])."""
        item = {
            "images": [
                {"kind": "gallery", "url": "https://x.example.com/a.jpg", "local": "a.avif"},
                {"kind": "gallery", "url": "https://x.example.com/a.jpg", "local": "a.avif"},
                {"kind": "gallery", "url": "https://x.example.com/a.jpg", "local": "a.avif"},
            ]
        }
        dedupe_item_images(item, Path("/nonexistent"))
        assert len(item["images"]) == 1
