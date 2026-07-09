#!/usr/bin/env python3
"""merge_duplicate_series.py — fusiona series_keys partidas por variantes
mecánicas del slug (gotcha #70).

PROBLEMA: la misma obra terminaba con 2-3 series_key distintos según la
fuente/corrida: artículo "The" ("the-apothecary-diaries" vs
"apothecary-diaries", 32 items partidos), apóstrofes ("hell-s-paradise" vs
"hells-paradise"), romanización de vocales largas ("kumichou" vs "kumicho").
CAUSA RAÍZ (auditoría 2026-06-11): en la mayoría de los casos AMBAS variantes
existen como entradas canónicas DUPLICADAS en series_aliases.yml (el enrich
skill creó las dos en corridas distintas) — el corpus solo refleja eso.

FIX: agrupa los series_key del corpus bajo `aggressive_series_norm` (la MISMA
normalización que usa el fallback de canonical_series_key — fuente única).
Dentro de cada grupo con >1 key:
  - Si hay entradas canónicas duplicadas en el YAML y sus displays también
    colapsan bajo la normalización agresiva → se FUSIONAN en el YAML (gana la
    key con más items en el corpus; la perdedora pasa a alias de la ganadora).
    Si los displays NO colapsan → se reporta como ambiguo y no se toca
    (podrían ser obras distintas).
  - Si ninguna key es canónica → gana la key con más items (empate: la más
    corta, después alfabética) y el grupo se encola en
    data/unmapped_series.jsonl para que /watch-enrich-series-aliases cree la
    entrada canónica (si no, la variante renace en el próximo scrape).
  - Los items perdedores (nunca los approved) se reescriben: series_key,
    series_display, prefijo del edition_key, cluster_key. Consolidate fusiona
    los duplicados resultantes.

Uso:
  .venv/bin/python scripts/retrofit/merge_duplicate_series.py --dry-run
  .venv/bin/python scripts/retrofit/merge_duplicate_series.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402
from series_aliases import (  # noqa: E402
    _load_aliases,
    aggressive_series_norm,
)

ITEMS = ROOT / "data" / "items.jsonl"
UNMAPPED = ROOT / "data" / "unmapped_series.jsonl"
ALIASES = ROOT / "data" / "series_aliases.yml"


def plan_merges(items: list[dict], aliases_db: dict) -> tuple[
    dict[str, str], dict[str, str], list[tuple[str, ...]]
]:
    """Plan de fusión. Devuelve (key_mapping, yaml_merges, ambiguos).

    key_mapping: {loser_key: winner_key} para reescribir items.
    yaml_merges: {loser_canonical: winner_canonical} para fusionar el YAML.
    ambiguos: grupos con canónicas cuyos DISPLAYS no colapsan (no se tocan).
    """
    by_norm: dict[str, Counter] = defaultdict(Counter)
    for it in items:
        sk = it.get("series_key", "") or ""
        if sk:
            by_norm[aggressive_series_norm(sk)][sk] += 1

    mapping: dict[str, str] = {}
    yaml_merges: dict[str, str] = {}
    ambiguous: list[tuple[str, ...]] = []
    for counts in by_norm.values():
        if len(counts) < 2:
            continue
        keys = sorted(counts)
        canonicals = [k for k in keys if k in aliases_db]
        if len(canonicals) > 1:
            # Duplicado del YAML — solo fusionar si los displays también
            # colapsan (guard contra obras genuinamente distintas).
            displays = {
                aggressive_series_norm(
                    (aliases_db[k] or {}).get("display", "") or k
                )
                for k in canonicals
            }
            if len(displays) > 1:
                ambiguous.append(tuple(keys))
                continue
            winner = sorted(
                canonicals,
                key=lambda k: (
                    -counts[k],
                    -len((aliases_db[k] or {}).get("aliases", []) or []),
                    len(k),
                    k,
                ),
            )[0]
            for k in canonicals:
                if k != winner:
                    yaml_merges[k] = winner
        elif canonicals:
            winner = canonicals[0]
        else:
            winner = sorted(keys, key=lambda k: (-counts[k], len(k), k))[0]
        for k in keys:
            if k != winner:
                mapping[k] = winner
    return mapping, yaml_merges, ambiguous


def _merge_yaml(aliases_db: dict, yaml_merges: dict[str, str]) -> dict:
    """Funde cada entrada perdedora dentro de la ganadora (key+display+aliases
    pasan a aliases de la ganadora). Devuelve el dict nuevo, orden preservado."""
    merged = dict(aliases_db)
    for loser, winner in yaml_merges.items():
        w = dict(merged.get(winner) or {})
        l = merged.get(loser) or {}
        seen = {a.strip().lower() for a in (w.get("aliases") or [])}
        seen.add((w.get("display", "") or "").strip().lower())
        seen.add(winner)
        new_aliases = list(w.get("aliases") or [])
        for cand in [loser, (l.get("display", "") or ""), *(l.get("aliases") or [])]:
            c = str(cand).strip()
            if c and c.lower() not in seen:
                new_aliases.append(c)
                seen.add(c.lower())
        w["aliases"] = new_aliases
        merged[winner] = w
        merged.pop(loser, None)
    return merged


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    aliases_db = _load_aliases()

    mapping, yaml_merges, ambiguous = plan_merges(items, aliases_db)
    for grp in ambiguous:
        print(f"[series-dup] AMBIGUO (displays no colapsan, no fusiono): {grp}")
    print(f"[series-dup] grupos a fusionar: {len(set(mapping.values()))} "
          f"(items afectados via {len(mapping)} keys perdedoras; "
          f"{len(yaml_merges)} entradas duplicadas del YAML)")
    for loser, winner in sorted(mapping.items())[:40]:
        tag = " [YAML]" if loser in yaml_merges else ""
        print(f"    {loser}  →  {winner}{tag}")

    # Display ganador: YAML si es canónica; si no, el más común del corpus.
    disp_counts: dict[str, Counter] = defaultdict(Counter)
    for it in items:
        sk, sd = it.get("series_key", ""), it.get("series_display", "")
        if sk and sd:
            disp_counts[sk][sd] += 1
    display_of: dict[str, str] = {}
    for winner in set(mapping.values()):
        if winner in aliases_db:
            display_of[winner] = (aliases_db[winner] or {}).get("display", "") or winner
        elif disp_counts[winner]:
            display_of[winner] = disp_counts[winner].most_common(1)[0][0]

    changed = 0
    sample_of: dict[str, dict] = {}
    for it in items:
        sk = it.get("series_key", "") or ""
        winner = mapping.get(sk)
        if not winner:
            continue
        sample_of.setdefault(winner, it)
        if it.get("approved_at"):
            continue
        old_ek = it.get("edition_key", "") or ""
        if old_ek.startswith(sk + "-"):
            it["edition_key"] = winner + old_ek[len(sk):]
        it["series_key"] = winner
        if display_of.get(winner):
            it["series_display"] = display_of[winner]
        it["cluster_key"] = mw.derive_cluster_key(it)
        changed += 1
    print(f"[series-dup] items reescritos: {changed}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0

    if yaml_merges:
        shutil.copy(ALIASES, ALIASES.with_suffix(".yml.pre-seriesdup-bak"))
        merged = _merge_yaml(aliases_db, yaml_merges)
        tmp = ALIASES.with_suffix(".yml.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(merged, fh, allow_unicode=True, sort_keys=False,
                           default_flow_style=False)
        tmp.replace(ALIASES)
        print(f"[series-dup] {len(yaml_merges)} entradas duplicadas fusionadas en "
              f"{ALIASES.name} (backup .pre-seriesdup-bak).")

    if changed:
        before = len(items)
        items = mw.consolidate_by_cluster(items)
        print(f"[series-dup] consolidate: {before} → {len(items)}")
        mw.backup_and_rotate(ITEMS, "seriesdup")
        mw.write_items_atomic(ITEMS, items)
        print(f"[series-dup] escrito {ITEMS}.")

    # Cola de curación SOLO para ganadores no canónicos (que el enrich skill
    # cree la entrada del YAML; si no, la variante renace en el próximo scrape).
    pending_queue = {w: sorted(l for l, ww in mapping.items() if ww == w)
                     for w in set(mapping.values()) if w not in aliases_db}
    if pending_queue and not args.dry_run:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        with UNMAPPED.open("a", encoding="utf-8") as fh:
            for winner, losers in sorted(pending_queue.items()):
                sample = sample_of.get(winner, {})
                fh.write(json.dumps({
                    "series_key": winner,
                    "series_display": display_of.get(winner, ""),
                    "sample_title": sample.get("title", ""),
                    "sample_url": sample.get("url", ""),
                    "source": sample.get("source", ""),
                    "detected_at": now,
                    "merged_from": losers,
                }, ensure_ascii=False) + "\n")
        print(f"[series-dup] {len(pending_queue)} grupos sin canónica encolados en "
              f"{UNMAPPED.name} (correr /watch-enrich-series-aliases).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
