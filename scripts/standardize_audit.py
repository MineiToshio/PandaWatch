#!/usr/bin/env python3
"""standardize_audit.py — paso de AUDIT del skill /watch-standardize-catalog.

Fuente ÚNICA de la lógica de auditoría/tiering que antes vivía COPIADA en
SKILL.md y en el workflow (drift). Calcula los items pendientes (sin
`standardized_at` ni `approved_at`), re-deriva la metadata heurística para
obtener el `confidence_tier`, y escribe las proyecciones por tier a
`/tmp/manga-standardize-run/tier{1,2,3}.json`.

Cada proyección Tier 2/3 incluye además:
  - `proposed_*`: la propuesta heurística (Tier 2 la valida, no re-deriva).
  - `existing_edition_key`: edition_key YA asignado al item, si tiene — el LLM
    NO re-agrupa items con edición asignada (decisión owner 2026-06-07).
  - `known_edition_keys`: edition_keys YA existentes en el corpus para esa
    serie (gotcha #69) — el LLM debe REUSAR la key existente que matchee
    publisher+tipo+país en vez de acuñar una variante nueva (special vs
    limited partía la misma edición en dos).

Markers de salida (los parsea el workflow): TOTAL / PENDING / TIER1/2/3.

Uso:
  .venv/bin/python scripts/standardize_audit.py [--limit N] [--force-all]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manga_watch import Candidate, derive_series_metadata  # noqa: E402
from series_aliases import aggressive_series_norm  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
DEFAULT_BASE = Path("/tmp/manga-standardize-run")

# Máximo de keys conocidas adjuntadas por item (las más pobladas primero).
_KNOWN_KEYS_CAP = 8


def _known_keys_index(items: list[dict]) -> dict[str, Counter]:
    """`aggressive_series_norm(series_key)` → Counter de edition_keys del corpus.

    Solo cuenta items ya estandarizados (keys confiables). El índice va por
    normalización agresiva para que "the-apothecary-diaries" encuentre las
    keys de "apothecary-diaries" (gotcha #70).
    """
    index: dict[str, Counter] = defaultdict(Counter)
    for it in items:
        if not it.get("standardized_at"):
            continue
        sk, ek = it.get("series_key", ""), it.get("edition_key", "")
        if sk and ek:
            index[aggressive_series_norm(sk)][ek] += 1
    return index


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="máx. items pendientes (0 = todos)")
    ap.add_argument("--force-all", action="store_true",
                    help="re-procesar también los ya estandarizados (nunca los approved)")
    ap.add_argument("--base", type=Path, default=DEFAULT_BASE)
    args = ap.parse_args()

    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    if args.force_all:
        pending = [it for it in items if not it.get("approved_at")]
    else:
        pending = [it for it in items
                   if not it.get("standardized_at") and not it.get("approved_at")]
    if args.limit:
        pending = pending[: args.limit]

    print(f"TOTAL:{len(items)}")
    print(f"PENDING:{len(pending)}")
    if not pending:
        print("DONE:nothing_to_standardize")
        return 0

    known = _known_keys_index(items)

    tiers: dict[int, list[dict]] = {1: [], 2: [], 3: []}
    for it in pending:
        c = Candidate(
            title=it.get("title_original") or it.get("title", ""),
            url=it.get("url", ""), source=it.get("source", ""),
            source_url=it.get("source_url", ""), country=it.get("country", ""),
            language=it.get("language", ""), publisher=it.get("publisher", ""),
            source_class=it.get("source_class", ""), tags=it.get("tags", []),
            description=it.get("description", ""),
            signal_types=it.get("signal_types", []),
        )
        md = derive_series_metadata(c) or {}
        tier = md.get("confidence_tier", 3) or 3
        projected = {
            "url": it.get("url", ""), "title": it.get("title", ""),
            "title_original": it.get("title_original", ""),
            "source": it.get("source", ""), "publisher": it.get("publisher", ""),
            "country": it.get("country", ""), "language": it.get("language", ""),
            "isbn": it.get("isbn", ""), "signal_types": it.get("signal_types", []),
            "description_excerpt": (it.get("description", "") or "")[:200],
            "existing_edition_key": it.get("edition_key", "") or "",
            "tier": tier,
        }
        if md:
            projected["proposed_series_key"] = md.get("series_key", "")
            projected["proposed_series_display"] = md.get("series_display", "")
            projected["proposed_edition_key"] = md.get("edition_key", "")
            projected["proposed_edition_display"] = md.get("edition_display", "")
            projected["proposed_volume"] = md.get("volume", "")
            # NO se propone título: el title oficial scrapeado nunca se
            # renombra ni traduce (política de títulos 2026-06-12).
        # Keys existentes en el corpus para esta serie (reuso > acuñar).
        sk_for_lookup = md.get("series_key", "") or it.get("series_key", "")
        if sk_for_lookup:
            counter = known.get(aggressive_series_norm(sk_for_lookup))
            if counter:
                projected["known_edition_keys"] = [
                    k for k, _ in counter.most_common(_KNOWN_KEYS_CAP)
                ]
        tiers[tier].append(projected)

    args.base.mkdir(parents=True, exist_ok=True)
    for t in (1, 2, 3):
        with (args.base / f"tier{t}.json").open("w", encoding="utf-8") as fh:
            json.dump(tiers[t], fh, ensure_ascii=False)

    print(f"TIER1:{len(tiers[1])}")
    print(f"TIER2:{len(tiers[2])}")
    print(f"TIER3:{len(tiers[3])}")
    print(f"Proyecciones escritas en {args.base}/tier{{1,2,3}}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
