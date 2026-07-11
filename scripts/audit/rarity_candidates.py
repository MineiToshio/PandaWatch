#!/usr/bin/env python3
"""rarity_candidates.py — selecciona y prioriza los items `rarity="rare"` por
INCERTIDUMBRE (candidatos del skill `/watch-validate-rarity`), agrupados por
edición.

Compila a código el Step 0 + Step 1 embebidos del skill (auditoría Fable
2026-07-08, hallazgo F5): `uncertainty_reason()` vivía DUPLICADA dos veces en
`watch-validate-rarity/SKILL.md` (Step 0 y Step 3), como una copia manual del
orden de ramas `rare` de `manga_watch.derive_rarity_tier()`. Si esa cascada
cambia (se agrega una keyword estructural, se reordena una rama), la copia del
skill queda eligiendo candidatos equivocados sin que ningún test lo detecte —
el mismo patrón que causó los falsos positivos de search-covers pre-2026-06-11.

`rarity_uncertainty_reason(item)` es ahora la ÚNICA implementación: vive acá,
la importan tanto este script (selección) como `apply_rarity_verdicts.py`
(re-selección antes de aplicar, para no aplicar sobre items que dejaron de ser
candidatos entre la selección y el veredicto). Un test de coherencia
(`tests/test_rarity_candidates.py`) fija, con un fixture por rama, que el
orden acá coincide con el de `derive_rarity_tier()` — cualquier drift futuro
rompe el test en vez de silenciosamente elegir mal.

Universo (ver derive_rarity_tier, modelo default-common 2026-06-10): un item
`rare` lo es por (a) EVIDENCIA estructural (print run, keyword de
no-reimpresión, patrón de evento/furoku/OOP, fuente tokuten) — esos NO son
candidatos, ya están resueltos; o (b) INCERTIDUMBRE — `retailer_exclusive` sin
stock verificado, o el item viene ÚNICAMENTE de fuentes de referencia
(Mangavariant/Sumikko/BooksPrivilege) sin evidencia en ningún sentido — esos SÍ
son candidatos, la web puede resolver la incertidumbre en cualquier sentido.

Uso:
    rarity_candidates.py                      # top 40 (default), texto humano
    rarity_candidates.py --limit 10 --output json
    rarity_candidates.py --out data/diagnostics/rarity_validation_candidates.json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# El wrapper manga_watch.py de la RAÍZ puede estar ya cacheado en sys.modules
# bajo pytest (no expone estos símbolos) → fallback al módulo real (mismo
# patrón que fetch_better_covers.py / backfill_series_aliases.py).
try:
    from manga_watch import (  # type: ignore
        _extract_print_run,
        _is_reference_only_source,
        _SINGLE_RUN_KEYWORDS,
        _SINGLE_RUN_PATTERNS,
        _TOKUTEN_SOURCES,
        is_approved,
    )
except ImportError:  # pragma: no cover
    from scripts.manga_watch import (  # type: ignore
        _extract_print_run,
        _is_reference_only_source,
        _SINGLE_RUN_KEYWORDS,
        _SINGLE_RUN_PATTERNS,
        _TOKUTEN_SOURCES,
        is_approved,
    )

DEFAULT_LIMIT = 40
_WESTERN_EXCLUDED_COUNTRIES = ("Japón", "Tailandia", "Taiwán", "Vietnam")


def item_sources(item: dict[str, Any]) -> list[str]:
    """Nombres de TODAS las fuentes del item (para el fallback de referencia)."""
    names = [s.get("name") or s.get("source") or "" for s in (item.get("sources") or [])]
    return [n for n in names if n] or [item.get("source") or ""]


def rarity_uncertainty_reason(item: dict[str, Any]) -> str | None:
    """'referencia' | 'retailer_exclusive' | None si el 'rare' del item tiene
    evidencia ESTRUCTURAL (no depende de verificación web).

    Replica el ORDEN EXACTO de las ramas `rare` de `derive_rarity_tier()`
    (manga_watch.py) hasta el punto en que la evidencia deja de ser
    estructural y pasa a ser incertidumbre. Fuente única — ver docstring del
    módulo.

    NOTA: un item `retailer_exclusive` puede tener ADEMÁS una keyword
    estructural más abajo en la cascada — sigue siendo candidato porque un
    veredicto `out_of_stock` lo PROMUEVE a `super_rare` (con `in_stock` se
    queda en `rare` por la keyword: resultado '=' esperado, ver SKILL.md).
    """
    text = f"{item.get('title', '')} {item.get('description', '')}".lower()
    src = (item.get("source") or "").lower()

    if _extract_print_run(text) is not None:
        return None  # tirada documentada — evidencia estructural, no candidato
    if item.get("stock_status") == "out_of_stock":
        return None  # ya hay evidencia de agotamiento
    if "retailer_exclusive" in (item.get("signal_types") or []):
        return "retailer_exclusive"
    if any(t in src for t in _TOKUTEN_SOURCES):
        return None
    if any(kw in text for kw in _SINGLE_RUN_KEYWORDS):
        return None
    if any(p.search(text) for p in _SINGLE_RUN_PATTERNS):
        return None
    # NOTA (fix del drift 2026-07-08): la copia embebida del skill NO tenía el
    # guard `stock_status != "in_stock"` acá, a diferencia de la rama real de
    # derive_rarity_tier — exactamente la clase de bug que este script existe
    # para prevenir (F5). Con stock verificado in_stock, la incertidumbre de
    # fuente-de-referencia ya está resuelta (no es candidato).
    if (item.get("stock_status") != "in_stock" and item_sources(item)
            and all(_is_reference_only_source(s) for s in item_sources(item))):
        return "referencia"
    return None


def select_pending(items: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """(reason, item) para cada item candidato: rare, sin rarity_verified_at,
    no aprobado, y con razón de incertidumbre."""
    pending = []
    for it in items:
        if it.get("rarity") != "rare" or it.get("rarity_verified_at") or is_approved(it):
            continue
        reason = rarity_uncertainty_reason(it)
        if reason:
            pending.append((reason, it))
    return pending


def _priority(group: list[tuple[str, dict[str, Any]]]) -> tuple[int, int, int]:
    """retailer_exclusive primero (puede PROMOVER a super_rare); luego
    mercados occidentales (verificación más confiable que JP); luego impacto."""
    reasons = {r for r, _ in group}
    rep = max((it for _, it in group), key=lambda it: it.get("score") or 0)
    western = rep.get("country") not in _WESTERN_EXCLUDED_COUNTRIES
    return (0 if "retailer_exclusive" in reasons else 1, 0 if western else 1, -len(group))


def group_and_prioritize(
    items: list[dict[str, Any]], limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Agrupa los candidatos por edición (edition_key > slug > url) y
    devuelve la lista priorizada de candidatos-edición (uno por grupo,
    representado por el item de mayor score), tope `limit`."""
    pending = select_pending(items)
    by_group: dict[str, list[tuple[str, dict[str, Any]]]] = collections.defaultdict(list)
    for reason, it in pending:
        gid = it.get("edition_key") or it.get("slug") or it.get("url")
        by_group[gid].append((reason, it))

    groups = sorted(by_group.items(), key=lambda kv: _priority(kv[1]))
    if limit:
        groups = groups[:limit]

    candidates = []
    for gid, group in groups:
        rep = max((it for _, it in group), key=lambda it: it.get("score") or 0)
        candidates.append({
            "group_id": gid,
            "reason": sorted({r for r, _ in group})[0],
            "title": rep.get("title", ""),
            "series_display": rep.get("series_display", ""),
            "edition_display": rep.get("edition_display", ""),
            "publisher": rep.get("publisher", ""),
            "country": rep.get("country", ""),
            "release_date": rep.get("release_date", ""),
            "isbn": rep.get("isbn", ""),
            "n_volumes": len(group),
            "url": rep.get("url", ""),
            "price": rep.get("price", ""),
        })
    return candidates


def _default_items_path() -> Path:
    import os

    data_dir = os.environ.get("MANGA_WATCH_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "items.jsonl"
    return _SCRIPTS.parent / "data" / "items.jsonl"


def _default_out_path() -> Path:
    import os

    data_dir = os.environ.get("MANGA_WATCH_DATA_DIR")
    base = Path(data_dir) if data_dir else _SCRIPTS.parent / "data"
    return base / "diagnostics" / "rarity_validation_candidates.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", type=Path, default=None,
                    help="items.jsonl a leer (default: data/items.jsonl / MANGA_WATCH_DATA_DIR).")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help=f"Tope de ediciones a priorizar (default {DEFAULT_LIMIT}; 0 = sin tope).")
    ap.add_argument("--out", type=Path, default=None,
                    help="Ruta de salida del JSON de candidatos (default: "
                         "data/diagnostics/rarity_validation_candidates.json).")
    ap.add_argument("--output", choices=["text", "json"], default="text",
                    help="Formato de stdout: texto humano (default) o JSON puro.")
    args = ap.parse_args(argv)

    items_path = args.items if args.items is not None else _default_items_path()
    if not items_path.exists():
        print(f"[ERROR] no existe {items_path}", file=sys.stderr)
        return 1

    items = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    total_pending = select_pending(items)
    candidates = group_and_prioritize(items, limit=args.limit)

    out_path = args.out if args.out is not None else _default_out_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=1), encoding="utf-8")

    if args.output == "json":
        print(json.dumps(candidates, ensure_ascii=False))
        return 0

    print(f"Total items: {len(items)}")
    print(f"Rares por incertidumbre pendientes: {len(total_pending)}")
    print(dict(collections.Counter(r for r, _ in total_pending)))
    print(f"\nEdiciones a verificar ({len(candidates)}):")
    for c in candidates:
        print(f"  [{c['reason']:18s}] {c['title'][:50]:50s} "
              f"({c['publisher'][:18]}, {c['country']}) — {c['n_volumes']} item(s)")
        print(f"      group_id: {c['group_id']}")
        print(f"      url: {c['url'][:90]}  isbn: {c['isbn'] or '-'}")
    print(f"\n[OK] Escrito {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
