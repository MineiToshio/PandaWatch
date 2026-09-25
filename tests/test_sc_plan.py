"""Tests para scripts/retrofit/sc_plan.py — planificador del Step 1 del skill
/watch-search-covers (auditoría Fable 2026-07-08, hallazgo F9).

Cobertura:
  1. Skip por estado: un (slug, action, target) que ya tiene una candidata DEL
     SKILL (campo match_dist) en pending/approved/rejected se salta.
  2. Guard MIN_REF_PX: referencia degenerada (< 2 500 px, típico placeholder
     1x1) se salta por default; con include_no_image entra con referencia
     blanqueada y SIN variante yandex-reverse.
  3. Exclusión de 30 días: target con último intento 0-matches reciente se
     salta; uno viejo (> 30 días) entra; --retry-failed ignora la exclusión.
  4. Orden de variantes por idioma: Español → whakoom primero, luego
     yandex-reverse; otros idiomas → yandex-reverse primero, sin whakoom.
  5. Galería: se incluye POR DEFECTO (portada + galería); --only-covers acota
     a portadas y --gallery-only acota a galería.
  6. Guard de referencia placeholder (gotcha #171/#176a/#178): una referencia
     detectada como placeholder conocido (por URL — regla `.gif` de Rakuten —
     o por contenido/firma) se saltea DURO por default (con contador), entra
     con `--include-no-image` como `reference_kind == "placeholder"` sin
     variante yandex-reverse, y `reference_sha256` sólo se persiste para
     referencia `"real"`.
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

from PIL import Image

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))
if str(_ROOT / "scripts" / "retrofit") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import sc_plan  # type: ignore


def _make_image(path: Path, w: int, h: int) -> None:
    """Imagen sintética de prueba, NO sólida (gotcha nueva, 2026-09-02): el
    guard de referencia placeholder de `sc_plan.py` corre
    `image_store.placeholder_reason()` sobre TODA referencia, que clasifica
    imágenes casi-de-un-solo-color (std de luminancia < 3) como placeholder
    "solid:...". Un fill sólido (el fixture original) dispararía ese guard en
    CUALQUIER test de este archivo, sin relación con lo que el test prueba.
    Se dibuja un cuadrante negro sobre fondo blanco (alto contraste de
    luminancia incluso apenas comprimido a JPEG) — determinístico y O(1), sin
    el costo de un gradiente pixel a pixel."""
    im = Image.new("RGB", (w, h), color=(255, 255, 255))
    if w > 1 and h > 1:
        from PIL import ImageDraw
        ImageDraw.Draw(im).rectangle([0, 0, max(w // 2, 1), max(h // 2, 1)], fill=(0, 0, 0))
    im.save(path)


def _item(slug="test-1", lang="Español", images=None, **extra) -> dict:
    it = {
        "slug": slug,
        "title": "Test Manga 1",
        "title_original": "テスト",
        "series_display": "Test Manga",
        "volume": "1",
        "language": lang,
        "publisher": "Editorial X",
        "edition_key": "test-manga-x-special",
        "images": images if images is not None else [],
        "signal_types": [],
    }
    it.update(extra)
    return it


# ── 1. Skip por estado ───────────────────────────────────────────────────────

def test_skip_when_already_in_preview_pending(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "cover.jpg", 100, 100)  # 10_000 px: baja calidad
    item = _item(images=[{"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg"}])

    already = {("test-1", "replace_cover", "")}
    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=already, recently_failed=set())
    assert targets == []


def test_included_when_not_in_preview(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "cover.jpg", 100, 100)
    item = _item(images=[{"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg"}])

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set())
    assert len(targets) == 1
    assert targets[0]["slug"] == "test-1"


# ── 2. Guard MIN_REF_PX (referencia degenerada) ─────────────────────────────

def test_degenerate_reference_skipped_by_default(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "tiny.jpg", 1, 1)  # 1 px < MIN_REF_PX
    item = _item(images=[{"url": "https://cdn.example.com/tiny.jpg", "local": "tiny.jpg"}])

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set())
    assert targets == []


def test_degenerate_reference_included_with_include_no_image_and_no_yandex_variant(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "tiny.jpg", 1, 1)
    item = _item(images=[{"url": "https://cdn.example.com/tiny.jpg", "local": "tiny.jpg"}])

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set(),
                                 include_no_image=True)
    assert len(targets) == 1
    t = targets[0]
    assert t["image_ref_local"] == ""
    assert t["pixels"] == 0
    labels = [v["label"] for v in t["variants"]]
    assert "yandex-reverse" not in labels


# ── 3. Exclusión de 30 días ──────────────────────────────────────────────────

def _attempts_line(slug, action, target, days_ago, matches=0):
    ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago))
    return json.dumps({
        "slug": slug, "action": action, "target": target,
        "attempted_at": ts.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "matches": matches,
    })


def test_recently_failed_target_skipped(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "cover.jpg", 100, 100)
    attempts_path = tmp_path / "attempts.jsonl"
    attempts_path.write_text(_attempts_line("test-1", "replace_cover", "", days_ago=5) + "\n",
                             encoding="utf-8")

    recently_failed = sc_plan._load_recently_failed(attempts_path, retry_failed=False)
    item = _item(images=[{"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg"}])
    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=recently_failed)
    assert targets == []


def test_old_failed_target_included(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "cover.jpg", 100, 100)
    attempts_path = tmp_path / "attempts.jsonl"
    attempts_path.write_text(_attempts_line("test-1", "replace_cover", "", days_ago=45) + "\n",
                             encoding="utf-8")

    recently_failed = sc_plan._load_recently_failed(attempts_path, retry_failed=False)
    assert recently_failed == set()
    item = _item(images=[{"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg"}])
    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=recently_failed)
    assert len(targets) == 1


def test_retry_failed_ignores_recent_exclusion(tmp_path):
    attempts_path = tmp_path / "attempts.jsonl"
    attempts_path.write_text(_attempts_line("test-1", "replace_cover", "", days_ago=5) + "\n",
                             encoding="utf-8")
    recently_failed = sc_plan._load_recently_failed(attempts_path, retry_failed=True)
    assert recently_failed == set()


# ── 4. Orden de variantes por idioma ─────────────────────────────────────────

def test_spanish_variant_order_whakoom_then_yandex():
    item = _item(lang="Español")
    variants = sc_plan.build_variants(item, ref_url="https://cdn.example.com/cover.jpg")
    labels = [v["label"] for v in variants]
    assert labels[0] == "whakoom"
    assert labels[1] == "yandex-reverse"


def test_non_spanish_variant_order_yandex_first_no_whakoom():
    item = _item(lang="Inglés")
    variants = sc_plan.build_variants(item, ref_url="https://cdn.example.com/cover.jpg")
    labels = [v["label"] for v in variants]
    assert labels[0] == "yandex-reverse"
    assert "whakoom" not in labels


# ── 4b. Motor primario de texto = Bing (decisión 2026-07-11) ─────────────────

def test_text_variants_use_bing_engine():
    """Las variantes de TEXTO apuntan a Bing image search (motor primario), no a
    Google udm=2. Google quedó como fallback de emergencia (riesgo de cuenta al
    scrapear Google con las cookies del owner)."""
    item = _item(lang="Inglés")
    variants = sc_plan.build_variants(item, ref_url="")
    text_variants = [v for v in variants if v["kind"] == "text"]
    assert text_variants, "debe haber al menos una variante de texto"
    for v in text_variants:
        assert v["engine"] == "bing"
        assert "bing.com/images/search" in v["url"]
        assert "google.com" not in v["url"]


def test_whakoom_variant_uses_bing_and_honors_site_operator():
    """whakoom sigue primero para ES, ahora vía Bing (que honra `site:`)."""
    item = _item(lang="Español")
    variants = sc_plan.build_variants(item, ref_url="")
    wk = next(v for v in variants if v["label"] == "whakoom")
    assert wk["engine"] == "bing"
    assert "bing.com/images/search" in wk["url"]
    assert wk["query"].startswith("site:whakoom.com ")


def test_reverse_variant_tagged_yandex_engine():
    item = _item(lang="Inglés")
    variants = sc_plan.build_variants(item, ref_url="https://cdn.example.com/cover.jpg")
    yx = next(v for v in variants if v["label"] == "yandex-reverse")
    assert yx["engine"] == "yandex"
    assert yx["kind"] == "reverse"


def test_listadomanga_thumbnail_reference_skips_yandex_variant():
    item = _item(lang="Inglés")
    variants = sc_plan.build_variants(
        item, ref_url="https://static.listadomanga.com/thumb.jpg")
    labels = [v["label"] for v in variants]
    assert "yandex-reverse" not in labels


def test_no_ref_url_skips_yandex_variant():
    item = _item(lang="Inglés")
    variants = sc_plan.build_variants(item, ref_url="")
    labels = [v["label"] for v in variants]
    assert "yandex-reverse" not in labels


# ── 5. Galería incluida por defecto / --only-covers / --gallery-only ─────────

def _item_cover_and_gallery(images_dir: Path) -> dict:
    """Item con portada (img_idx 0) y una foto de galería (img_idx 1), ambas
    de baja calidad para que sean candidatas a búsqueda."""
    _make_image(images_dir / "cover.jpg", 100, 100)    # 10_000 px
    _make_image(images_dir / "gallery.jpg", 120, 120)  # 14_400 px
    return _item(images=[
        {"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg", "kind": "cover"},
        {"url": "https://cdn.example.com/gallery.jpg", "local": "gallery.jpg", "kind": "gallery"},
    ])


def test_gallery_included_by_default(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    item = _item_cover_and_gallery(images_dir)

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set())
    idxs = sorted(t["img_idx"] for t in targets)
    assert idxs == [0, 1]  # portada Y galería por defecto


def test_only_covers_skips_gallery(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    item = _item_cover_and_gallery(images_dir)

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set(),
                                 only_covers=True)
    idxs = sorted(t["img_idx"] for t in targets)
    assert idxs == [0]  # solo portada


def test_gallery_only_skips_cover(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    item = _item_cover_and_gallery(images_dir)

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set(),
                                 gallery_only=True)
    idxs = sorted(t["img_idx"] for t in targets)
    assert idxs == [1]  # solo galería


# ── 6. Criterio de PORTADA: `scale` (default, Etapa 1) vs `area` (compat) ────
#
# Etapa 1 de triage de imágenes (2026-09-02, docs/reference/images.md § "Etapa
# 1 — resultados", gotcha #172): el ÁREA sola marca 579 portadas como "baja
# calidad" de las que el 91,2% se ven BIEN en la card real del catálogo. El
# factor de reescalado en card (`fetch_better_covers.cover_upscale_factor`)
# separa correctamente lo bueno de lo malo — es el criterio nuevo por defecto.

def _item_with_cover(images_dir: Path, w: int, h: int, slug="test-1", **extra) -> dict:
    _make_image(images_dir / "cover.jpg", w, h)
    return _item(slug=slug, images=[
        {"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg", "kind": "cover"},
    ], **extra)


def test_scale_rule_excludes_good_looking_low_area_thumbnail(tmp_path):
    """210x300 (thumbnail típico de static.listadomanga.com — área 63 000
    < 90 000, pero factor 1.4x < UPSCALE_TARGET_MIN): bajo el criterio nuevo
    (default) NO es target, aunque el criterio viejo de área sí lo marcaba."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    item = _item_with_cover(images_dir, 210, 300)

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set())
    assert targets == []


def test_area_rule_flag_restores_old_behavior_for_same_thumbnail(tmp_path):
    """`--target-rule area` es la vía de compatibilidad: el mismo thumbnail de
    arriba SÍ vuelve a ser target bajo el criterio viejo."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    item = _item_with_cover(images_dir, 210, 300)

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set(),
                                 target_rule="area")
    assert len(targets) == 1
    assert targets[0]["img_idx"] == 0


def test_scale_rule_includes_stretched_small_cover(tmp_path):
    """100x100 (factor 3.0x >= 1.6) sí es target bajo el criterio nuevo, y el
    target trae el factor calculado."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    item = _item_with_cover(images_dir, 100, 100)

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set())
    assert len(targets) == 1
    assert targets[0]["scale"] == 3.0
    assert targets[0]["width"] == 100
    assert targets[0]["height"] == 100


def test_scale_rule_excludes_large_cover_that_already_fits(tmp_path):
    """Portada grande (600x800, ya buena bajo el criterio viejo) tampoco es
    target bajo el criterio nuevo (factor 0.5x < 1.6)."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    item = _item_with_cover(images_dir, 600, 800)

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set())
    assert targets == []


def test_gallery_always_uses_area_rule_regardless_of_target_rule(tmp_path):
    """La galería (img_idx >= 1) conserva el criterio de área SIEMPRE — la
    Etapa 1 sólo evaluó portadas. Una foto de galería 210x300 (área 63 000
    < 90 000, factor 1.4x < 1.6) SÍ es target aunque la portada use el
    criterio nuevo por defecto."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "cover.jpg", 100, 100)     # portada: factor 3.0 -> target
    _make_image(images_dir / "gallery.jpg", 210, 300)   # galería: área 63 000 < 90k -> target
    item = _item(images=[
        {"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg", "kind": "cover"},
        {"url": "https://cdn.example.com/gallery.jpg", "local": "gallery.jpg", "kind": "gallery"},
    ])

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set())
    idxs = sorted(t["img_idx"] for t in targets)
    assert idxs == [0, 1]


def test_scale_rule_orders_landscape_first(tmp_path):
    """Apaisada (w > h, recorte destruido — p.ej. cover150/ de Aladin) primero,
    aunque su factor sea menor que el de una portrait con factor mayor: la
    orientación pesa más que el valor exacto del factor (Etapa 1)."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "portrait.jpg", 60, 90)    # factor 5.0x, retrato
    _make_image(images_dir / "landscape.jpg", 150, 76)  # factor 2.0x, apaisada
    item_portrait = _item(slug="portrait-item", images=[
        {"url": "https://cdn.example.com/portrait.jpg", "local": "portrait.jpg", "kind": "cover"}])
    item_landscape = _item(slug="landscape-item", images=[
        {"url": "https://cdn.example.com/landscape.jpg", "local": "landscape.jpg", "kind": "cover"}])

    targets = sc_plan.build_plan([item_portrait, item_landscape], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set())
    assert [t["slug"] for t in targets] == ["landscape-item", "portrait-item"]


def test_scale_rule_orders_worse_scale_first_within_orientation_group(tmp_path):
    """Dentro del mismo grupo de orientación, factor DESCENDENTE (peor,
    más estirado, primero)."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "a.jpg", 100, 100)  # factor 3.0
    _make_image(images_dir / "b.jpg", 150, 150)  # factor 2.0
    item_a = _item(slug="item-a", images=[
        {"url": "https://cdn.example.com/a.jpg", "local": "a.jpg", "kind": "cover"}])
    item_b = _item(slug="item-b", images=[
        {"url": "https://cdn.example.com/b.jpg", "local": "b.jpg", "kind": "cover"}])

    targets = sc_plan.build_plan([item_b, item_a], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set())
    assert [t["slug"] for t in targets] == ["item-a", "item-b"]


def test_no_image_targets_still_sort_first_under_scale_rule(tmp_path):
    """'Sin imagen' (< MIN_REF_PX) sigue teniendo la prioridad más alta bajo
    el criterio nuevo, igual que antes de esta tarea."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "tiny.jpg", 1, 1)  # < MIN_REF_PX, "sin imagen"
    _make_image(images_dir / "cover.jpg", 100, 100)
    item_no_image = _item(slug="no-image-item",
                          images=[{"url": "https://cdn.example.com/tiny.jpg", "local": "tiny.jpg"}])
    item_cover = _item(slug="cover-item",
                       images=[{"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg"}])

    targets = sc_plan.build_plan([item_cover, item_no_image], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set(),
                                 include_no_image=True)
    assert targets[0]["slug"] == "no-image-item"


# ── 6. Guard de referencia placeholder (gotcha #171/#176a/#178) ─────────────
# El juez encontró 9/9 candidatas basura cuando Yandex reverse-image usó como
# consulta una referencia placeholder (la "tarjeta de título" .gif de Rakuten).
# El guard MIN_REF_PX (tamaño) no lo atrapa: el .gif tiene canvas real. Se
# detecta con las DOS fuentes únicas de `image_store` (URL y contenido).

_RAKUTEN_GIF_URL = "https://tshop.r10s.jp/foo/cabinet/1234/9784091234567.gif?downsize=130:*"


def test_placeholder_by_url_skipped_by_default(tmp_path):
    """Referencia .gif de Rakuten (regla host+extensión conocida por URL) —
    canvas de tamaño REAL (no cae en MIN_REF_PX) pero igual se saltea DURO."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "titlecard.jpg", 1004, 1172)  # tamaño real, NO degenerado
    item = _item(images=[{"url": _RAKUTEN_GIF_URL, "local": "titlecard.jpg"}])

    skip_counts: dict[str, int] = {}
    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set(),
                                 skip_counts=skip_counts)
    assert targets == []
    assert skip_counts.get("placeholder_reference") == 1


def test_placeholder_by_url_included_with_include_no_image(tmp_path):
    """Con --include-no-image entra como reference_kind == 'placeholder', SIN
    variante yandex-reverse (nunca reverse-image contra un placeholder)."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "titlecard.jpg", 1004, 1172)
    item = _item(images=[{"url": _RAKUTEN_GIF_URL, "local": "titlecard.jpg"}])

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set(),
                                 include_no_image=True)
    assert len(targets) == 1
    t = targets[0]
    assert t["reference_kind"] == "placeholder"
    assert t["pixels"] == 0
    assert t["image_ref_local"] == ""
    assert t["image_ref_url"] == ""
    assert t["reference_sha256"] == ""
    labels = [v["label"] for v in t["variants"]]
    assert "yandex-reverse" not in labels


def test_placeholder_by_content_signature_skipped(tmp_path, monkeypatch):
    """Referencia sin nada raro en la URL, pero cuyo sha1 de contenido está
    fichado en placeholder_signatures.json (firma) → mismo skip DURO."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    img_path = images_dir / "signed.jpg"
    _make_image(img_path, 500, 700)  # tamaño real
    import hashlib
    digest = hashlib.sha1(img_path.read_bytes()).hexdigest()

    monkeypatch.setattr(
        sc_plan.fbc.image_store, "load_placeholder_signatures",
        lambda refresh=False: {digest: "test:fixture-signature"},
    )

    item = _item(images=[{"url": "https://cdn.example.com/signed.jpg", "local": "signed.jpg"}])
    skip_counts: dict[str, int] = {}
    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set(),
                                 skip_counts=skip_counts)
    assert targets == []
    assert skip_counts.get("placeholder_reference") == 1


def test_real_reference_not_skipped_and_gets_reference_kind_and_sha(tmp_path):
    """Una referencia normal (ni degenerada ni placeholder) entra como
    reference_kind == 'real' y lleva su reference_sha256 (guard anti-drift)."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    img_path = images_dir / "cover.jpg"
    _make_image(img_path, 100, 100)  # baja calidad (criterio scale/área) → target
    item = _item(images=[{"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg"}])

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set())
    assert len(targets) == 1
    t = targets[0]
    assert t["reference_kind"] == "real"
    import hashlib
    assert t["reference_sha256"] == hashlib.sha256(img_path.read_bytes()).hexdigest()


def test_gallery_placeholder_keeps_target_identity_but_blanks_search_reference(tmp_path):
    """Galería (img_idx >= 1): el guard blanquea la referencia de BÚSQUEDA
    pero preserva `candidate_target` (identidad del slot a reemplazar) —
    gotcha #176a confirma que la regla `.gif` de Rakuten también cae en
    posiciones de galería, no sólo portada."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "cover.jpg", 400, 600)   # portada real, buena calidad
    _make_image(images_dir / "extra.jpg", 1004, 1172)  # galería: tarjeta Rakuten
    item = _item(images=[
        {"url": "https://cdn.example.com/cover.jpg", "local": "cover.jpg", "kind": "cover"},
        {"url": _RAKUTEN_GIF_URL, "local": "extra.jpg", "kind": "extra"},
    ])

    targets = sc_plan.build_plan([item], images_dir=images_dir,
                                 already_in_preview=set(), recently_failed=set(),
                                 include_no_image=True, gallery_only=True)
    assert len(targets) == 1
    t = targets[0]
    assert t["img_idx"] == 1
    assert t["reference_kind"] == "placeholder"
    assert t["image_ref_local"] == ""
    assert t["image_ref_url"] == ""
    # candidate_target sigue siendo la URL ORIGINAL — identifica QUÉ foto de
    # galería se está reemplazando, independiente de que no sirva como
    # referencia de búsqueda.
    assert t["candidate_target"] == _RAKUTEN_GIF_URL


def test_get_dims_local_uses_canonical_dims_source(tmp_path):
    """`get_dims_local` (y por lo tanto `get_pixels_local`, que ahora lo
    envuelve) delega en `fbc._get_dims_from_bytes` — la fuente única de
    dimensiones del motor — en vez de duplicar el parsing PIL."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "cover.jpg", 210, 300)
    assert sc_plan.get_dims_local("cover.jpg", images_dir) == (210, 300)
    assert sc_plan.get_pixels_local("cover.jpg", images_dir) == 210 * 300
    assert sc_plan.get_dims_local("", images_dir) == (0, 0)
    assert sc_plan.get_dims_local("missing.jpg", images_dir) == (0, 0)
