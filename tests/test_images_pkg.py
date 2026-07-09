"""Tests para el paquete IMG de la auditoría Fable 2026-07-08
(data/diagnostics/fable-audit-images-20260708.md): image_store.py,
upscale_images.py, upgrade_image_resolution.py, sitemap_miner.py,
shopify_variants.py.

Sin red — todo con imágenes sintéticas PIL / HTML fabricado en tmp_path.
"""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

# Si otro test dejó un stub incompleto de manga_watch/image_store en
# sys.modules, lo quitamos para importar los módulos reales — mismo patrón
# que test_promote_hires_cover.py / test_dedup_carousel_images.py.
_mw = sys.modules.get("manga_watch")
if _mw is not None and not all(
    hasattr(_mw, sym) for sym in ("backup_and_rotate", "is_approved", "make_session")
):
    del sys.modules["manga_watch"]
_is = sys.modules.get("image_store")
if _is is not None and not hasattr(_is, "THUMB_ASPECT_TOL"):
    del sys.modules["image_store"]
for mod_name in ("upscale_images", "upgrade_image_resolution"):
    if mod_name in sys.modules:
        del sys.modules[mod_name]

import image_store  # noqa: E402
import upscale_images as ui  # noqa: E402
import upgrade_image_resolution as uir  # noqa: E402
import fetch_better_covers as fbc  # noqa: E402
import sitemap_miner as sm  # noqa: E402
import shopify_variants as sv  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
# image_store.py
# ══════════════════════════════════════════════════════════════════════════

class TestNormalizeImageUrlIdentityParams:
    """Hallazgo #2 (ALTA): patrón 1 borraba la query COMPLETA — dos imágenes
    DISTINTAS con params de identidad + resize colapsaban al mismo stem."""

    def test_preserves_identity_param(self):
        url = "https://x.com/img.php?id=123&width=300"
        out = image_store.normalize_image_url(url)
        assert "id=123" in out
        assert "width=300" not in out

    def test_different_identity_yields_different_stem(self):
        a = image_store.image_stem("https://x.com/img.php?id=123&width=300")
        b = image_store.image_stem("https://x.com/img.php?id=456&width=300")
        assert a != b  # antes del fix, ambos colapsaban a sha256("/img.php")

    def test_pure_resize_query_still_fully_stripped(self):
        # Sin params de identidad, el comportamiento es el mismo que antes:
        # la query queda vacía (no queda un "?" colgando).
        url = "https://example.com/image.jpg?quality=80&width=222&height=222&bg-color=ffffff"
        out = image_store.normalize_image_url(url)
        assert out == "https://example.com/image.jpg"

    def test_idempotent(self):
        url = "https://images.yenpress.com/imgs/x.jpg?w=408&h=612&type=books&s=abc"
        once = image_store.normalize_image_url(url)
        twice = image_store.normalize_image_url(once)
        assert once == twice

    def test_real_corpus_example_yenpress(self):
        # Ejemplo real del análisis de impacto (2026-07-08): identity keys
        # "type"/"s" deben sobrevivir, "w"/"h" deben caer.
        url = "https://images.yenpress.com/imgs/9781975328863.jpg?w=408&h=612&type=books&s=cf42b96f5364c3d5c50da8df"
        out = image_store.normalize_image_url(url)
        assert "type=books" in out
        assert "s=cf42b96f5364c3d5c50da8df" in out
        assert "w=408" not in out and "h=612" not in out


class TestExistingLocalImageLegacyCompat:
    """Hallazgo #2: compat hacia atrás — ~67 archivos del corpus real ya
    están espejados bajo el stem LEGACY (query completa borrada). El fix no
    debe huerfanarlos ni forzar una re-descarga."""

    def test_falls_back_to_legacy_stem_when_new_stem_missing(self, tmp_path):
        url = "https://x.com/img.php?id=123&width=300"
        legacy_stem = image_store._legacy_image_stem(url)
        new_stem = image_store.image_stem(url)
        assert legacy_stem != new_stem
        (tmp_path / f"{legacy_stem}.avif").write_bytes(b"fake-avif-bytes")

        found = image_store.existing_local_image(tmp_path, url)
        assert found == f"{legacy_stem}.avif"

    def test_prefers_new_stem_when_both_exist(self, tmp_path):
        url = "https://x.com/img.php?id=123&width=300"
        legacy_stem = image_store._legacy_image_stem(url)
        new_stem = image_store.image_stem(url)
        (tmp_path / f"{legacy_stem}.avif").write_bytes(b"old")
        (tmp_path / f"{new_stem}.avif").write_bytes(b"new")

        found = image_store.existing_local_image(tmp_path, url)
        assert found == f"{new_stem}.avif"

    def test_no_file_anywhere_returns_empty(self, tmp_path):
        url = "https://x.com/img.php?id=999&width=300"
        assert image_store.existing_local_image(tmp_path, url) == ""


class TestMaxImagePixelsCap:
    """Hallazgo #16: `Image.MAX_IMAGE_PIXELS = None` desactivaba el guard
    anti-decompression-bomb de PIL en los 3 sitios de image_store.py."""

    def test_cap_is_finite(self):
        assert image_store.MAX_IMAGE_PIXELS_CAP is not None
        assert 0 < image_store.MAX_IMAGE_PIXELS_CAP < 200_000_000

    def test_normal_image_still_normalizes_under_cap(self):
        im = Image.new("RGB", (400, 600))
        px = im.load()
        for y in range(600):
            for x in range(400):
                px[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 5) % 256)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        body, ext = image_store.normalize_image(buf.getvalue())
        assert ext == ".avif"
        assert body

    def test_placeholder_reason_still_works_under_cap(self):
        im = Image.new("RGB", (1, 1), (255, 255, 255))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        assert image_store.placeholder_reason(buf.getvalue()).startswith("tiny")


def test_thumb_aspect_tol_lives_in_image_store():
    assert image_store.THUMB_ASPECT_TOL == 0.06


# ══════════════════════════════════════════════════════════════════════════
# upscale_images.py — hallazgo #3 (--delete-original protege refs extra)
# ══════════════════════════════════════════════════════════════════════════

def _avif_bytes(w: int, h: int, color=(10, 20, 30)) -> bytes:
    im = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


class TestUpscaleProtectedLocalsHelpers:
    def test_sources_image_locals_collects_across_items(self):
        items = [
            {"slug": "a", "sources": [{"image_local": "x.avif"}]},
            {"slug": "b", "sources": [{"image_local": "y.avif"}, {"image_local": ""}]},
            {"slug": "c", "images": [{"local": "z.avif"}]},  # no sources[]
        ]
        assert ui._sources_image_locals(items) == {"x.avif", "y.avif"}

    def test_cover_preview_locals_collects_all_three_refs(self, tmp_path):
        preview = tmp_path / "cover_preview.json"
        preview.write_text(json.dumps([
            {
                "slug": "a",
                "old_image": "old.avif",
                "candidates": [{"new_image": "cand1.avif"}, {"new_image": ""}],
                "current_images": [{"local": "cur1.avif"}, {"local": ""}, {}],
            },
        ]), encoding="utf-8")
        refs = ui._cover_preview_locals(preview)
        assert refs == {"old.avif", "cand1.avif", "cur1.avif"}

    def test_cover_preview_locals_missing_file_returns_empty(self, tmp_path):
        assert ui._cover_preview_locals(tmp_path / "nope.json") == set()

    def test_protected_locals_is_union(self, tmp_path):
        preview = tmp_path / "cover_preview.json"
        preview.write_text(json.dumps([{"old_image": "p.avif"}]), encoding="utf-8")
        items = [{"sources": [{"image_local": "s.avif"}]}]
        assert ui._protected_locals(items, preview) == {"s.avif", "p.avif"}


@pytest.fixture
def upscale_harness(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    old_local = "old123456789abcd.png"
    (images_dir / old_local).write_bytes(_avif_bytes(40, 60))

    def _fake_upscale_file(upscaler_path, upscaler_kind, src, dst, scale, denoise):
        with Image.open(src) as im:
            im2 = im.resize((im.width * scale, im.height * scale))
            im2.save(dst, "PNG")
        return True

    monkeypatch.setattr(ui, "_find_upscaler", lambda: ("fake-bin", "waifu2x"))
    monkeypatch.setattr(ui, "_upscale_file", _fake_upscale_file)
    return images_dir, old_local


def test_delete_original_keeps_file_protected_by_sources(tmp_path, upscale_harness, monkeypatch):
    images_dir, old_local = upscale_harness
    items_path = tmp_path / "items.jsonl"
    item_a = {"slug": "a", "images": [{"url": "http://x/o.png", "local": old_local, "kind": "gallery"}]}
    # item_b no referencia images[] con este local, pero SÍ vía sources[]
    # (ref legacy per-fuente que este script no actualiza) — debe protegerlo.
    item_b = {"slug": "b", "sources": [{"image_local": old_local, "image_url": "http://x/o.png"}]}
    items_path.write_text(
        json.dumps(item_a) + "\n" + json.dumps(item_b) + "\n", encoding="utf-8",
    )

    ui.run(
        items_path=items_path, images_dir=images_dir,
        max_pixels=100_000, scale=2, denoise=1, limit=0,
        dry_run=False, delete_original=True,
    )

    assert (images_dir / old_local).exists(), "sources[].image_local debía proteger el original"
    saved = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines()]
    saved_a = next(it for it in saved if it["slug"] == "a")
    assert saved_a["images"][0]["local"] != old_local
    assert saved_a["images"][0]["upscaled"] is True


def test_delete_original_keeps_file_protected_by_cover_preview(tmp_path, upscale_harness):
    images_dir, old_local = upscale_harness
    items_path = tmp_path / "items.jsonl"
    item_a = {"slug": "a", "images": [{"url": "http://x/o.png", "local": old_local, "kind": "gallery"}]}
    items_path.write_text(json.dumps(item_a) + "\n", encoding="utf-8")

    preview_path = tmp_path / "cover_preview.json"
    preview_path.write_text(json.dumps([{"slug": "a", "old_image": old_local}]), encoding="utf-8")

    ui.run(
        items_path=items_path, images_dir=images_dir,
        max_pixels=100_000, scale=2, denoise=1, limit=0,
        dry_run=False, delete_original=True, preview_path=preview_path,
    )

    assert (images_dir / old_local).exists(), "cover_preview.json debía proteger el original"


def test_delete_original_removes_unreferenced_original(tmp_path, upscale_harness):
    """Regresión: sin ninguna ref extra, --delete-original sigue borrando el
    archivo viejo como antes (el fix no debe sobre-proteger todo)."""
    images_dir, old_local = upscale_harness
    items_path = tmp_path / "items.jsonl"
    item_a = {"slug": "a", "images": [{"url": "http://x/o.png", "local": old_local, "kind": "gallery"}]}
    items_path.write_text(json.dumps(item_a) + "\n", encoding="utf-8")

    ui.run(
        items_path=items_path, images_dir=images_dir,
        max_pixels=100_000, scale=2, denoise=1, limit=0,
        dry_run=False, delete_original=True,
        preview_path=tmp_path / "cover_preview.json",  # no existe → sin refs
    )

    assert not (images_dir / old_local).exists()


# ══════════════════════════════════════════════════════════════════════════
# upgrade_image_resolution.py — hallazgo #1 (AVIF) y #4 (fail-closed)
# ══════════════════════════════════════════════════════════════════════════

class TestPixelsDelegatesToFetchBetterCovers:
    def test_measures_avif_correctly(self, tmp_path):
        im = Image.new("RGB", (300, 500), (5, 6, 7))
        buf = io.BytesIO()
        im.save(buf, "AVIF", quality=60)
        p = tmp_path / "cover.avif"
        p.write_bytes(buf.getvalue())

        px = uir._pixels(p)
        assert px == 300 * 500  # antes medía len(bytes) (proxy), no píxeles reales

    def test_falls_back_to_file_size_when_unparseable(self, tmp_path):
        p = tmp_path / "junk.bin"
        p.write_bytes(b"not an image, just filler bytes 1234567890")
        px = uir._pixels(p)
        assert px == len(p.read_bytes())

    def test_missing_file_returns_none(self, tmp_path):
        assert uir._pixels(tmp_path / "nope.avif") is None


class TestTryUpgradeFailClosed:
    """Hallazgo #4: needs_same_cover_validation (patrón Magento cache path)
    sin referencia local utilizable NO debe aceptar a ciegas."""

    def test_rejects_when_no_old_local_and_needs_validation(self, tmp_path, monkeypatch):
        magento_url = "https://www.bdfugue.com/media/catalog/product/cache/abc123/i/m/image.jpg"
        assert uir.needs_same_cover_validation(magento_url)

        class _FakeSession:
            pass

        # download_image "encuentra" una imagen nueva pero no hay old_local
        # para comparar (old_local="" → el bloque entero de gate se saltea
        # en la rama vieja, aceptando a ciegas).
        monkeypatch.setattr(
            uir.image_store, "download_image",
            lambda *a, **k: "newfile.avif",
        )
        (tmp_path / "newfile.avif").write_bytes(_dummy_avif(300, 400))

        result = uir._try_upgrade(
            magento_url, "", tmp_path, _FakeSession(), (5, 5), 0.1,
        )
        assert result is None  # fail-closed: sin ref, no se puede validar identidad

    def test_rejects_when_old_local_present_but_different_cover(self, tmp_path, monkeypatch):
        magento_url = "https://www.bdfugue.com/media/catalog/product/cache/abc123/i/m/image.jpg"
        old_local = "old.avif"
        (tmp_path / old_local).write_bytes(_dummy_avif(300, 400, seed=1))
        new_local = "newfile.avif"
        (tmp_path / new_local).write_bytes(_dummy_avif(300, 400, seed=99))  # imagen DISTINTA

        monkeypatch.setattr(uir.image_store, "download_image", lambda *a, **k: new_local)

        result = uir._try_upgrade(
            magento_url, old_local, tmp_path, object(), (5, 5), 0.0,
        )
        assert result is None  # _same_cover rechaza: no es la misma portada

    def test_accepts_when_old_local_present_and_same_cover_bigger(self, tmp_path, monkeypatch):
        magento_url = "https://www.bdfugue.com/media/catalog/product/cache/abc123/i/m/image.jpg"
        old_local = "old.avif"
        (tmp_path / old_local).write_bytes(_dummy_avif(100, 150, seed=1))
        new_local = "newfile.avif"
        # Misma imagen base, más grande — debe pasar el gate de píxeles y
        # _same_cover.
        (tmp_path / new_local).write_bytes(_dummy_avif(100, 150, seed=1, scale=3))

        monkeypatch.setattr(uir.image_store, "download_image", lambda *a, **k: new_local)

        result = uir._try_upgrade(
            magento_url, old_local, tmp_path, object(), (5, 5), 0.1,
        )
        assert result == (uir.derive_original_url(magento_url), new_local)


def _dummy_avif(w: int, h: int, seed: int = 0, scale: int = 1) -> bytes:
    from PIL import ImageDraw
    im = Image.new("RGB", (w * scale, h * scale))
    px = im.load()
    for y in range(h * scale):
        for x in range(w * scale):
            px[x, y] = (
                ((x + seed) * 255 // max(w * scale, 1)) % 256,
                (y * 255 // max(h * scale, 1)) % 256,
                ((x + y + seed) * 255 // max((w + h) * scale, 1)) % 256,
            )
    d = ImageDraw.Draw(im)
    d.ellipse([w * scale // 5, h * scale // 6, w * scale * 4 // 5, h * scale * 2 // 3],
              fill=(200, 30 + seed, 30))
    buf = io.BytesIO()
    im.save(buf, "AVIF", quality=70)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════
# sitemap_miner.py — hallazgos #9, #10, #13
# ══════════════════════════════════════════════════════════════════════════

class TestLocPatternCdataAndEntities:
    def test_plain_loc(self):
        urls, nested = sm.parse_sitemap_xml(
            "<urlset><url><loc>https://x.com/a?b=1</loc></url></urlset>"
        )
        assert urls == ["https://x.com/a?b=1"]

    def test_cdata_loc(self):
        xml = "<urlset><url><loc><![CDATA[https://x.com/prod?a=1&b=2]]></loc></url></urlset>"
        urls, nested = sm.parse_sitemap_xml(xml)
        assert urls == ["https://x.com/prod?a=1&b=2"]

    def test_entity_unescape(self):
        xml = "<urlset><url><loc>https://x.com/a?b=1&amp;c=2</loc></url></urlset>"
        urls, nested = sm.parse_sitemap_xml(xml)
        assert urls == ["https://x.com/a?b=1&c=2"]

    def test_double_escaped_entity(self):
        # &amp;amp; → &amp; tras un unescape (el bug documentado en el hallazgo)
        xml = "<urlset><url><loc>https://x.com/a?b=1&amp;amp;c=2</loc></url></urlset>"
        urls, nested = sm.parse_sitemap_xml(xml)
        assert urls == ["https://x.com/a?b=1&amp;c=2"]


class _FakeResponse:
    def __init__(self, status_code=200, text="", content=b"", headers=None):
        self.status_code = status_code
        self.text = text
        self.content = content or text.encode("utf-8")
        self.headers = headers or {}
        self.encoding = "utf-8"

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            import requests
            raise requests.HTTPError(f"status {self.status_code}")


class _FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if not self.responses:
            return _FakeResponse(404)
        return self.responses.pop(0)


def test_fetch_text_retries_once_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(sm.time, "sleep", lambda s: None)
    sess = _FakeSession([
        _FakeResponse(429, headers={"Retry-After": "1"}),
        _FakeResponse(200, text="<urlset></urlset>"),
    ])
    text = sm._fetch_text("http://x.com/sitemap.xml", sess)
    assert text == "<urlset></urlset>"
    assert len(sess.calls) == 2


def test_fetch_text_gives_up_after_one_retry(monkeypatch):
    monkeypatch.setattr(sm.time, "sleep", lambda s: None)
    sess = _FakeSession([_FakeResponse(429), _FakeResponse(429)])
    text = sm._fetch_text("http://x.com/sitemap.xml", sess)
    assert text == ""
    assert len(sess.calls) == 2  # UN reintento, nunca un loop


def test_discover_and_filter_does_not_double_fetch_same_candidate(monkeypatch):
    """Hallazgo #10: el candidato elegido se descarga UNA sola vez."""
    xml = "<urlset><url><loc>https://x.com/product/1</loc></url></urlset>"
    sess = _FakeSession([_FakeResponse(200, text="")] * 0)  # robots.txt vacío primero

    call_log = []

    def _get(url, timeout=None):
        call_log.append(url)
        if url.endswith("/robots.txt"):
            return _FakeResponse(404)
        if url.endswith("/sitemap.xml"):
            return _FakeResponse(200, text=xml)
        return _FakeResponse(404)

    sess.get = _get
    result = sm.discover_and_filter("https://x.com", sess)
    assert result["all_urls"] == ["https://x.com/product/1"]
    sitemap_fetches = [c for c in call_log if c == "https://x.com/sitemap.xml"]
    assert len(sitemap_fetches) == 1, f"se descargó el sitemap 2 veces: {call_log}"


# ══════════════════════════════════════════════════════════════════════════
# shopify_variants.py — hallazgos #7, #8, #11
# ══════════════════════════════════════════════════════════════════════════

def test_format_variant_price_removed():
    assert not hasattr(sv, "format_variant_price")


def test_no_unused_imports():
    assert not hasattr(sv, "Path")
    assert not hasattr(sv, "Iterable")


def test_docstring_references_real_function_name():
    doc = sv.__doc__ or ""
    # La API pública ("provee: ...") ya no anuncia una función inexistente —
    # el nombre viejo puede seguir mencionado como nota histórica, pero no
    # como bullet de la lista de API pública ("- `expand_shopify_...`").
    assert "- `expand_shopify_variant_page(" not in doc
    assert "expand_shopify_variants_item" in doc


def test_extract_variants_prefers_product_scoped_block():
    """Hallazgo #11: si un widget AJENO trae su propio "variants" ANTES del
    bloque "product" en el HTML, el parser debe anclarse al de "product",
    no al primer "variants" suelto del documento."""
    html = """
    <script>
    var relatedWidget = {"recommendations": [{"id": 1}], "variants": [{"id": "999", "title": "WRONG"}]};
    var meta = {"product": {"id": 1, "variants": [
        {"id": "1001", "public_title": "Volume 1", "sku": "SKU-1", "price": 999},
        {"id": "1002", "public_title": "Volume 2", "sku": "SKU-2", "price": 999}
    ]}, "page": {}};
    </script>
    """
    variants = sv.extract_shopify_variants(html)
    assert [v["id"] for v in variants] == ["1001", "1002"]
    assert [v["title"] for v in variants] == ["Volume 1", "Volume 2"]


def test_extract_variants_real_fixture_still_works():
    fixture = _ROOT / "tests" / "fixtures" / "shopify" / "dh_hellsing_deluxe.html"
    html = fixture.read_text(encoding="utf-8")
    variants = sv.extract_shopify_variants(html)
    assert len(variants) == 3
    assert [v["title"] for v in variants] == ["Volume 1", "Volume 2", "Volume 3"]
