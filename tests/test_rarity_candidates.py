"""Tests para scripts/audit/rarity_candidates.py.

Reemplaza la copia duplicada de `uncertainty_reason()` embebida dos veces en
watch-validate-rarity/SKILL.md (auditoría Fable 2026-07-08, hallazgo F5).

Cobertura:
  1. Test de COHERENCIA tracer↔derive_rarity_tier — un fixture por rama de la
     cascada de `derive_rarity_tier()` (manga_watch.py). Si la cascada cambia
     de orden/condición sin actualizar `rarity_uncertainty_reason()`, este
     test lo detecta.
  2. Selección (`select_pending`): filtra por rarity=='rare', sin
     rarity_verified_at, sin approved_at.
  3. Agrupación + prioridad (`group_and_prioritize`): agrupa por edition_key,
     prioriza retailer_exclusive > occidental > tamaño de grupo, respeta
     --limit.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))
if str(_ROOT / "scripts" / "audit") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts" / "audit"))

try:
    from manga_watch import derive_rarity_tier  # type: ignore
except ImportError:  # pragma: no cover
    from scripts.manga_watch import derive_rarity_tier  # type: ignore
import rarity_candidates as rc  # type: ignore


def _item(**kwargs) -> dict:
    base = {
        "title": "Test Manga",
        "description": "",
        "signal_types": [],
        "source": "Some Store",
        "sources": [],
        "publisher": "Editorial X",
        "stock_status": "",
        "edition_key": "test-manga-x-special",
        "slug": "test-manga-x-special-1",
        "url": "https://example.com/item",
        "country": "España",
        "rarity": "rare",
    }
    base.update(kwargs)
    return base


def _tier(item: dict) -> str:
    return derive_rarity_tier(
        signal_types=item.get("signal_types") or [],
        source=item.get("source") or "",
        description=item.get("description") or "",
        title=item.get("title") or "",
        publisher=item.get("publisher") or "",
        stock_status=item.get("stock_status") or "",
        sources=rc.item_sources(item),
    )


# ── 1. Coherencia tracer ↔ derive_rarity_tier (un fixture por rama) ─────────

def test_print_run_ultra_rare_is_structural_not_candidate():
    it = _item(description="Edición limitada a 100 copias numeradas.")
    assert rc.rarity_uncertainty_reason(it) is None
    assert _tier(it) == "ultra_rare"


def test_print_run_super_rare_is_structural_not_candidate():
    it = _item(description="Limitada a 1000 copias.")
    assert rc.rarity_uncertainty_reason(it) is None
    assert _tier(it) == "super_rare"


def test_print_run_documented_but_not_short_is_structural_not_candidate():
    it = _item(description="Limitada a 5000 copias.")
    assert rc.rarity_uncertainty_reason(it) is None
    assert _tier(it) == "rare"


def test_out_of_stock_already_has_evidence_not_candidate():
    it = _item(stock_status="out_of_stock")
    assert rc.rarity_uncertainty_reason(it) is None
    assert _tier(it) == "rare"


def test_retailer_exclusive_without_stock_is_candidate():
    it = _item(signal_types=["retailer_exclusive"], stock_status="")
    assert rc.rarity_uncertainty_reason(it) == "retailer_exclusive"
    assert _tier(it) == "rare"


def test_retailer_exclusive_out_of_stock_not_candidate_already_resolved():
    """out_of_stock se chequea ANTES que retailer_exclusive en la cascada —
    ya hay evidencia (y de hecho PROMUEVE a super_rare), no es candidato."""
    it = _item(signal_types=["retailer_exclusive"], stock_status="out_of_stock")
    assert rc.rarity_uncertainty_reason(it) is None
    assert _tier(it) == "super_rare"


def test_tokuten_source_is_structural_not_candidate():
    it = _item(source="BooksPrivilege JP")
    assert rc.rarity_uncertainty_reason(it) is None
    assert _tier(it) == "rare"


def test_single_run_keyword_is_structural_not_candidate():
    it = _item(description="Tirada única, no se reimprimirá.")
    assert rc.rarity_uncertainty_reason(it) is None
    assert _tier(it) == "rare"


def test_single_run_pattern_is_structural_not_candidate():
    it = _item(description="This edition is now out of print.")
    assert rc.rarity_uncertainty_reason(it) is None
    assert _tier(it) == "rare"


def test_reference_only_source_fallback_is_candidate():
    it = _item(source="Mangavariant", sources=[{"name": "Mangavariant"}])
    assert rc.rarity_uncertainty_reason(it) == "referencia"
    assert _tier(it) == "rare"


def test_reference_only_source_in_stock_not_candidate():
    """El fallback de referencia exige stock_status != 'in_stock' — con stock
    verificado la incertidumbre ya está resuelta (común)."""
    it = _item(source="Mangavariant", sources=[{"name": "Mangavariant"}],
               stock_status="in_stock")
    assert rc.rarity_uncertainty_reason(it) is None
    assert _tier(it) == "common"


def test_mixed_sources_not_all_reference_only_not_candidate():
    it = _item(source="Mangavariant",
               sources=[{"name": "Mangavariant"}, {"name": "Amazon.it"}])
    assert rc.rarity_uncertainty_reason(it) is None
    assert _tier(it) == "common"


def test_no_evidence_at_all_is_common_not_candidate():
    it = _item()
    assert rc.rarity_uncertainty_reason(it) is None
    assert _tier(it) == "common"


def test_retailer_exclusive_in_stock_with_tokuten_source_equal_case():
    """Caso documentado '=' del SKILL.md: retailer_exclusive con stock
    in_stock deja de calificar por SU propia rama, pero si el item TAMBIÉN
    tiene evidencia más abajo en la cascada (acá: fuente tokuten, sin guard de
    stock), el tier sigue siendo 'rare' aunque la razón reportada sea
    'retailer_exclusive' — el tracer encuentra la razón ANTES en el orden,
    pero el resultado final coincide con derive_rarity_tier."""
    it = _item(signal_types=["retailer_exclusive"], stock_status="in_stock",
               source="BooksPrivilege JP")
    assert rc.rarity_uncertainty_reason(it) == "retailer_exclusive"
    assert _tier(it) == "rare"


# ── 2. Selección ─────────────────────────────────────────────────────────────

def test_select_pending_filters_common_verified_and_approved():
    items = [
        _item(slug="a", rarity="rare", signal_types=["retailer_exclusive"]),
        _item(slug="b", rarity="common"),  # no es rare
        _item(slug="c", rarity="rare", signal_types=["retailer_exclusive"],
              rarity_verified_at="2026-01-01T00:00:00+00:00"),  # ya verificado
        _item(slug="d", rarity="rare", signal_types=["retailer_exclusive"],
              approved_at="2026-01-01T00:00:00+00:00"),  # golden record
        _item(slug="e", rarity="rare"),  # sin razón de incertidumbre (common candidate real)
    ]
    pending = rc.select_pending(items)
    slugs = {it["slug"] for _, it in pending}
    assert slugs == {"a"}


# ── 3. Agrupación + prioridad ────────────────────────────────────────────────

def test_group_and_prioritize_groups_by_edition_key():
    items = [
        _item(slug="a-1", edition_key="ed-a", rarity="rare",
              signal_types=["retailer_exclusive"], score=10),
        _item(slug="a-2", edition_key="ed-a", rarity="rare",
              signal_types=["retailer_exclusive"], score=5),
        _item(slug="b-1", edition_key="ed-b", rarity="rare",
              source="Mangavariant", sources=[{"name": "Mangavariant"}], score=1),
    ]
    candidates = rc.group_and_prioritize(items, limit=0)
    by_gid = {c["group_id"]: c for c in candidates}
    assert by_gid["ed-a"]["n_volumes"] == 2
    assert by_gid["ed-a"]["reason"] == "retailer_exclusive"
    assert by_gid["b-1" if "b-1" in by_gid else "ed-b"]["n_volumes"] == 1


def test_group_and_prioritize_orders_retailer_exclusive_first():
    items = [
        _item(slug="ref-1", edition_key="ed-ref", rarity="rare",
              source="Mangavariant", sources=[{"name": "Mangavariant"}],
              country="Japón"),
        _item(slug="rex-1", edition_key="ed-rex", rarity="rare",
              signal_types=["retailer_exclusive"], country="Japón"),
    ]
    candidates = rc.group_and_prioritize(items, limit=0)
    assert candidates[0]["group_id"] == "ed-rex"
    assert candidates[1]["group_id"] == "ed-ref"


def test_group_and_prioritize_respects_limit():
    items = [
        _item(slug=f"s-{i}", edition_key=f"ed-{i}", rarity="rare",
              signal_types=["retailer_exclusive"])
        for i in range(5)
    ]
    candidates = rc.group_and_prioritize(items, limit=2)
    assert len(candidates) == 2


# ── G2: el output humano imprime el group_id exacto ─────────────────────────

def test_main_text_output_prints_exact_group_id(tmp_path, capsys):
    items = [
        _item(slug="a-1", edition_key="ed-a-especial", rarity="rare",
              signal_types=["retailer_exclusive"]),
    ]
    items_path = tmp_path / "items.jsonl"
    with items_path.open("w", encoding="utf-8") as f:
        for it in items:
            import json
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    out_path = tmp_path / "candidates.json"
    ret = rc.main(["--items", str(items_path), "--out", str(out_path)])
    assert ret == 0
    out = capsys.readouterr().out
    assert "group_id: ed-a-especial" in out


def test_group_and_prioritize_western_before_japan():
    items = [
        _item(slug="jp-1", edition_key="ed-jp", rarity="rare",
              signal_types=["retailer_exclusive"], country="Japón"),
        _item(slug="es-1", edition_key="ed-es", rarity="rare",
              signal_types=["retailer_exclusive"], country="España"),
    ]
    candidates = rc.group_and_prioritize(items, limit=0)
    assert candidates[0]["group_id"] == "ed-es"
    assert candidates[1]["group_id"] == "ed-jp"
