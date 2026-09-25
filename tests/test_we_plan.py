"""Tests para scripts/retrofit/we_plan.py — planificador del Step 1 del skill
/watch-whakoom-covers (owner, 2026-09-02: vía "whakoom por página de edición"
para portadas ES).

Cobertura:
  1. Sólo items con country == "España" entran al plan.
  2. Filtro de volumen resoluble: volume <= 11 o vacío entra; volume > 11 se
     excluye (no resoluble sin login, ver docstring del módulo).
  3. Selección de targets: sin imagen, o portada de baja calidad (área,
     default acá) entran; portada de buena calidad no.
  4. Exclusión de approved_at (salvo --include-approved).
  5. total_tomos: heurística local por conteo de edition_key en el corpus.
  6. Caché: edition_url ya resuelta se reutiliza sin re-generar búsqueda.
  7. Skip de (slug, action, target) ya adjudicado por ESTE skill (candidata
     con via == "whakoom_edicion") en cover_preview.json.
  8. --slugs filtra por identidad exacta, ignorando --limit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

_ROOT = Path(__file__).resolve().parent.parent
for p in (_ROOT / "scripts", _ROOT / "scripts" / "retrofit"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import we_plan  # type: ignore


def _make_image(path: Path, w: int, h: int) -> None:
    im = Image.new("RGB", (w, h), color=(255, 255, 255))
    if w > 1 and h > 1:
        ImageDraw.Draw(im).rectangle([0, 0, max(w // 2, 1), max(h // 2, 1)], fill=(0, 0, 0))
    im.save(path)


def _item(slug="test-es-1", volume="1", images=None, **extra) -> dict:
    it = {
        "slug": slug,
        "title": "Dragon Ball",
        "series_display": "Dragon Ball",
        "series_key": "dragon-ball",
        "volume": volume,
        "language": "Español",
        "country": "España",
        "publisher": "Planeta Cómic",
        "edition_key": "dragon-ball-planeta-es",
        "url": "https://www.listadomanga.es/coleccion.php?id=1832",
        "images": images if images is not None else [],
    }
    it.update(extra)
    return it


# ── 1. Sólo España ───────────────────────────────────────────────────────────

def test_only_spain_items(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [
        _item(slug="es-1", country="España"),
        _item(slug="jp-1", country="Japón"),
    ]
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
    )
    slugs = {t["slug"] for t in targets}
    assert "es-1" in slugs
    assert "jp-1" not in slugs


# ── 2. Filtro de volumen resoluble ──────────────────────────────────────────

def test_volume_over_11_excluded(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [
        _item(slug="vol-5", volume="5"),
        _item(slug="vol-11", volume="11"),
        _item(slug="vol-12", volume="12"),
        _item(slug="vol-empty", volume=""),
    ]
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
    )
    slugs = {t["slug"] for t in targets}
    assert "vol-5" in slugs
    assert "vol-11" in slugs
    assert "vol-empty" in slugs
    assert "vol-12" not in slugs


def test_volume_resolvable_helper():
    assert we_plan.volume_resolvable(_item(volume=""))
    assert we_plan.volume_resolvable(_item(volume="11"))
    assert not we_plan.volume_resolvable(_item(volume="12"))
    assert not we_plan.volume_resolvable(_item(volume="1-4"))  # no numérico → conservador


# ── 3. Selección de targets por calidad ─────────────────────────────────────

def test_no_image_is_target(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [_item(slug="no-img", images=[])]
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
    )
    assert len(targets) == 1
    assert targets[0]["pixels"] == 0
    assert targets[0]["reference_kind"] == "none"


def test_low_area_cover_is_target_default_area_rule(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "small.jpg", 100, 100)  # 10_000 px < LOW_QUALITY_PX
    items = [_item(slug="low-px", images=[{"local": "small.jpg", "url": "https://x/small.jpg"}])]
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
    )
    assert len(targets) == 1
    assert targets[0]["reference_kind"] == "real"
    assert targets[0]["pixels"] == 10_000


def test_good_quality_cover_not_a_target(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    _make_image(images_dir / "big.jpg", 1000, 1400)  # 1.4M px, bien por encima de 90k
    items = [_item(slug="good-px", images=[{"local": "big.jpg", "url": "https://x/big.jpg"}])]
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
    )
    assert targets == []


def test_target_rule_scale_is_stricter(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    # 210x300: static.listadomanga.com típico — área baja (63_000 < 90_000)
    # pero factor de reescalado bajo (no se estira mal en la card real).
    _make_image(images_dir / "thumb.jpg", 210, 300)
    items = [_item(slug="thumb-1", images=[{"local": "thumb.jpg", "url": "https://x/thumb.jpg"}])]
    targets_area = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
        target_rule="area",
    )
    targets_scale = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
        target_rule="scale",
    )
    assert len(targets_area) == 1
    assert targets_scale == []


# ── 4. approved_at ───────────────────────────────────────────────────────────

def test_approved_excluded_by_default(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [_item(slug="approved-1", images=[], approved_at="2026-01-01T00:00:00+00:00")]
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
    )
    assert targets == []
    targets2 = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
        include_approved=True,
    )
    assert len(targets2) == 1


# ── 5. total_tomos por conteo local de edition_key ──────────────────────────

def test_total_tomos_local_heuristic(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [
        _item(slug=f"db-{i}", volume=str(i), edition_key="dragon-ball-planeta-es", images=[])
        for i in range(1, 6)
    ]
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
    )
    assert len(targets) == 5
    for t in targets:
        assert t["listado"]["total_tomos"] == 5


# ── 6. Caché de edición ya resuelta ─────────────────────────────────────────

def test_cached_edition_url_reused(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [_item(slug="cached-1", images=[])]
    cache = {
        1832: {
            "listado_coleccion_id": 1832,
            "whakoom_edition_url": "https://www.whakoom.com/ediciones/1/x",
            "method": "whakoom_edicion_page",
            "formato": "Rústica",
        }
    }
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion=cache, already_in_preview=set(),
    )
    assert len(targets) == 1
    assert targets[0]["edition_url"] == "https://www.whakoom.com/ediciones/1/x"
    assert targets[0]["listado"]["formato"] == "Rústica"


def test_cache_not_reused_when_method_is_not_resolved(tmp_path):
    """Una fila de caché con method != whakoom_edicion_page (ambiguo/no
    encontrado) NO debe proponerse como edition_url ya resuelta."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [_item(slug="not-resolved-1", images=[])]
    cache = {1832: {"listado_coleccion_id": 1832, "whakoom_edition_url": "", "method": "ambiguous_multiple_editions"}}
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion=cache, already_in_preview=set(),
    )
    assert targets[0]["edition_url"] == ""


# ── 7. Skip de ya-adjudicado ─────────────────────────────────────────────────

def test_skip_already_in_preview(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [_item(slug="done-1", images=[])]
    already = {("done-1", "replace_cover", "")}
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=already,
    )
    assert targets == []


def test_preview_loader_only_counts_whakoom_via(tmp_path):
    preview_path = tmp_path / "cover_preview.json"
    preview_path.write_text(json.dumps([
        {"slug": "a", "candidates": [{"action": "replace_cover", "target": "", "via": "whakoom_edicion"}]},
        {"slug": "b", "candidates": [{"action": "replace_cover", "target": "", "match_dist": 2}]},
    ]), encoding="utf-8")
    already = we_plan._load_already_in_preview(preview_path)
    assert ("a", "replace_cover", "") in already
    assert ("b", "replace_cover", "") not in already


# ── 8. --slugs filtra por identidad, ignora --limit ─────────────────────────

def test_slugs_filter_ignores_limit(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [_item(slug=f"s-{i}", images=[]) for i in range(5)]
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
        limit=1, slugs=["s-0", "s-3"],
    )
    assert {t["slug"] for t in targets} == {"s-0", "s-3"}


# ── extract_coleccion_id ─────────────────────────────────────────────────────

def test_extract_coleccion_id_from_url():
    it = _item(url="https://www.listadomanga.es/coleccion.php?id=42")
    assert we_plan.extract_coleccion_id(it) == 42


def test_extract_coleccion_id_from_sources():
    it = _item(url="", sources=[{"url": "https://www.listadomanga.es/coleccion.php?id=99"}])
    assert we_plan.extract_coleccion_id(it) == 99


def test_extract_coleccion_id_none_when_absent():
    it = _item(url="https://example.com/product/1")
    assert we_plan.extract_coleccion_id(it) is None


# ── query ─────────────────────────────────────────────────────────────────

def test_build_query_includes_site_and_series():
    it = _item(series_display="Dragon Ball", publisher="Planeta Cómic")
    q = we_plan.build_query(it)
    assert "site:whakoom.com" in q
    assert "Dragon Ball" in q


# ── Endurecimiento #1 (tanda 3): total_tomos REMOTO vs heurística LOCAL ─────

def test_remote_meta_preferred_over_local_heuristic(tmp_path):
    """Con una fila en el caché remoto (listadomanga_meta.py) para el
    coleccion_id del item, `listado.total_tomos` usa ese valor REAL en vez
    del conteo local por edition_key — y lo marca `source:
    "listadomanga_remota"`. Motivación: el corpus local puede no tener
    todavía todos los tomos de una serie en curso (63/144 rechazos de la
    tanda 2 fueron `total_tomos_mismatch`, ver docs/reference/images.md)."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    # Corpus local sólo tiene 2 de los 25 tomos reales.
    items = [
        _item(slug=f"db-{i}", volume=str(i), edition_key="dragon-ball-planeta-es", images=[])
        for i in (1, 2)
    ]
    remote_meta = {1832: {"coleccion_id": 1832, "total_tomos": 25, "ongoing": False,
                          "formato": "Rústica con sobrecubierta", "paginas": "", "editorial": "Planeta Cómic"}}
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
        remote_meta_by_coleccion=remote_meta,
    )
    assert len(targets) == 2
    for t in targets:
        assert t["listado"]["total_tomos"] == 25
        assert t["listado"]["source"] == "listadomanga_remota"
        assert t["listado"]["local_total_tomos"] == 2
        assert t["listado"]["formato"] == "Rústica con sobrecubierta"
        assert t["listado"]["editorial"] == "Planeta Cómic"


def test_falls_back_to_local_heuristic_without_remote_cache(tmp_path):
    """Sin fila en el caché remoto para el coleccion_id (Step 1b del skill
    no corrió o esa colección no se fetcheó aún), `listado` cae al
    heurístico local de siempre — marcado `source: "local_count"`."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [
        _item(slug=f"db-{i}", volume=str(i), edition_key="dragon-ball-planeta-es", images=[])
        for i in range(1, 6)
    ]
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
        remote_meta_by_coleccion={},
    )
    assert len(targets) == 5
    for t in targets:
        assert t["listado"]["total_tomos"] == 5
        assert t["listado"]["source"] == "local_count"
        assert t["listado"]["ongoing"] is False
        assert t["listado"]["paginas"] == ""
        assert t["listado"]["editorial"] == ""


def test_remote_meta_ongoing_flag_propagates(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [_item(slug="db-1", volume="1", edition_key="dragon-ball-planeta-es", images=[])]
    remote_meta = {1832: {"coleccion_id": 1832, "total_tomos": 11, "ongoing": True,
                          "formato": "Rústica", "paginas": "", "editorial": "Planeta Cómic"}}
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
        remote_meta_by_coleccion=remote_meta,
    )
    assert targets[0]["listado"]["ongoing"] is True


def test_remote_meta_missing_total_tomos_falls_back_to_local(tmp_path):
    """Si la fila remota existe pero no pudo determinar total_tomos (None),
    igual cae al heurístico local — una fila remota "vacía" no debe pisar
    con None un dato local válido."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    items = [
        _item(slug=f"db-{i}", volume=str(i), edition_key="dragon-ball-planeta-es", images=[])
        for i in range(1, 4)
    ]
    remote_meta = {1832: {"coleccion_id": 1832, "total_tomos": None, "ongoing": False,
                          "formato": "", "paginas": "", "editorial": ""}}
    targets = we_plan.build_plan(
        items, images_dir=images_dir, cache_by_coleccion={}, already_in_preview=set(),
        remote_meta_by_coleccion=remote_meta,
    )
    for t in targets:
        assert t["listado"]["total_tomos"] == 3
        assert t["listado"]["source"] == "local_count"
