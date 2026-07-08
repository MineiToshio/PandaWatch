#!/usr/bin/env python3
"""unmapped_series.py — listado agrupado de series sin canonical en aliases.yml.

Fuentes:
1. `data/unmapped_series.jsonl` — log incremental escrito por el scraper
   (vía `series_aliases.log_unmapped_series`). Cada nueva series_key que no
   está en `data/series_aliases.yml` se appendea acá.
2. `data/items.jsonl` — fuente de verdad. Para cada series_key del log,
   contamos cuántos items afecta, sample titles, fuentes, idiomas.

Output:
- Tabla agrupada por series_key, ordenada por count DESC (prioridad alta).
- Por cada candidata: best fuzzy-match contra los canonicals existentes
  (ayuda al skill de enrichment a sugerir "merge into X").

Uso:
    python scripts/audit/unmapped_series.py              # tabla markdown
    python scripts/audit/unmapped_series.py --json       # JSON estructurado
    python scripts/audit/unmapped_series.py --min-count N  # solo series con >=N items
"""

from __future__ import annotations

import argparse
import difflib
import itertools
import json
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

import yaml  # noqa: E402

from series_aliases import _load_aliases, _normalize  # noqa: E402


ITEMS_FILE = _REPO / "data" / "items.jsonl"
UNMAPPED_FILE = _REPO / "data" / "unmapped_series.jsonl"


def _load_unmapped_log() -> dict[str, list[dict]]:
    """Lee unmapped_series.jsonl y agrupa por series_key.

    Devuelve `{series_key: [record, ...]}` con todas las apariciones logueadas.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    if not UNMAPPED_FILE.exists():
        return groups
    for line in UNMAPPED_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        sk = rec.get("series_key", "")
        if sk:
            groups[sk].append(rec)
    return groups


def _scan_items_for_unmapped(canonical_keys: set[str]) -> dict[str, dict]:
    """Scan items.jsonl para series_keys que NO están en aliases.yml.

    Devuelve `{series_key: {count, displays, titles, urls, sources, languages}}`.
    Más confiable que el log (que puede tener gaps si el scraper saltó).
    """
    info: dict[str, dict] = defaultdict(lambda: {
        "count": 0,
        "displays": Counter(),
        "sample_titles": [],
        "sample_urls": [],
        "sources": Counter(),
        "languages": Counter(),
        "publishers": Counter(),
    })
    if not ITEMS_FILE.exists():
        return info
    for line in ITEMS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            it = json.loads(line)
        except json.JSONDecodeError:
            continue
        sk = it.get("series_key", "")
        if not sk or sk in canonical_keys:
            continue
        bucket = info[sk]
        bucket["count"] += 1
        if it.get("series_display"):
            bucket["displays"][it["series_display"]] += 1
        if it.get("title") and len(bucket["sample_titles"]) < 5:
            bucket["sample_titles"].append(it["title"][:80])
        if it.get("url") and len(bucket["sample_urls"]) < 3:
            bucket["sample_urls"].append(it["url"])
        if it.get("source"):
            bucket["sources"][it["source"]] += 1
        if it.get("language"):
            bucket["languages"][it["language"]] += 1
        if it.get("publisher"):
            bucket["publishers"][it["publisher"]] += 1
    return info


def find_canonical_duplicates(aliases_db: dict) -> list[dict]:
    """Detecta canonicals del YAML que colapsan a la MISMA forma normalizada.

    El skill de enrichment acuñó pares de canonicals DUPLICADAS en corridas
    distintas (gotcha #70): dos canonicals cuyo display / key / algún alias
    normalizan idéntico bajo `series_aliases._normalize` — la MISMA normalización
    que usa el resolver en su lookup EXACTO (`_build_lookup`). Cuando eso pasa el
    resolver sólo puede mapear a UNA (la primera declarada) y la otra queda
    sombreada → son duplicados a fusionar (merge gateado del Lote B).

    Comparación EXACTA post-normalización, NO substring: `gto` y
    `gto-paradise-lost` NO colisionan (spin-offs distintos, normalizan a
    strings distintos). Sólo se reporta cuando la forma normalizada coincide
    entera.

    Devuelve una lista de `{a, b, via}` (un dict por PAR de canonicals),
    ordenada; `via` es la forma normalizada compartida.
    """
    norm_to_keys: dict[str, set] = defaultdict(set)
    for ck, info in aliases_db.items():
        display = (info or {}).get("display", "") or ck
        variants = [display, ck, *((info or {}).get("aliases") or [])]
        for variant in variants:
            n = _normalize(str(variant))
            if not n:
                continue
            # Indexar la forma normalizada y su versión slugificada, igual que
            # `series_aliases._build_lookup` (que además guarda el slug con
            # guiones) — así el conjunto de colisiones es el que ve el resolver.
            for form in {n, re.sub(r"\s+", "-", n)}:
                norm_to_keys[form].add(ck)

    pairs: dict[tuple[str, str], str] = {}
    for form, keys in norm_to_keys.items():
        if len(keys) < 2:
            continue
        for a, b in itertools.combinations(sorted(keys), 2):
            pairs.setdefault((a, b), form)
    return [{"a": a, "b": b, "via": via} for (a, b), via in sorted(pairs.items())]


def _best_canonical_match(
    series_key: str, displays: list[str], canonical_keys: set[str], canonical_displays: dict[str, str]
) -> tuple[str, float]:
    """Devuelve `(best_canonical_key, confidence)` o `("", 0.0)`.

    Usa difflib.SequenceMatcher como fuzzy match. Score >= 0.8 = probable alias.
    """
    candidates: list[tuple[str, float]] = []
    for ck in canonical_keys:
        cd = canonical_displays.get(ck, ck)
        for compare_to in [series_key] + displays:
            if not compare_to:
                continue
            r1 = difflib.SequenceMatcher(None, compare_to.lower(), ck.lower()).ratio()
            r2 = difflib.SequenceMatcher(None, compare_to.lower(), cd.lower()).ratio()
            candidates.append((ck, max(r1, r2)))
    if not candidates:
        return "", 0.0
    best = max(candidates, key=lambda x: x[1])
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true",
                    help="Output JSON estructurado en vez de markdown.")
    ap.add_argument("--min-count", type=int, default=1,
                    help="Solo reporta series_keys con >=N items (default 1).")
    ap.add_argument("--max-suggestions", type=int, default=50,
                    help="Limita a las top N (default 50; útil para skill batch).")
    args = ap.parse_args()

    aliases_db = _load_aliases()
    canonical_keys = set(aliases_db.keys())
    canonical_displays = {ck: (info or {}).get("display", ck) for ck, info in aliases_db.items()}

    canonical_dups = find_canonical_duplicates(aliases_db)

    log_groups = _load_unmapped_log()
    items_info = _scan_items_for_unmapped(canonical_keys)

    # Compose: empezar con lo que items.jsonl dice, enriquecer con first_seen del log.
    rows = []
    for sk, info in items_info.items():
        if info["count"] < args.min_count:
            continue
        log_records = log_groups.get(sk, [])
        first_seen = min((r.get("detected_at", "") for r in log_records), default="")
        displays = [d for d, _ in info["displays"].most_common(3)]
        best_canonical, confidence = _best_canonical_match(
            sk, displays, canonical_keys, canonical_displays,
        )
        rows.append({
            "series_key": sk,
            "primary_display": displays[0] if displays else sk,
            "all_displays": displays,
            "item_count": info["count"],
            "first_seen": first_seen,
            "sample_titles": info["sample_titles"],
            "sample_urls": info["sample_urls"],
            "top_sources": [s for s, _ in info["sources"].most_common(3)],
            "languages": [l for l, _ in info["languages"].most_common(3)],
            "publishers": [p for p, _ in info["publishers"].most_common(3)],
            "best_canonical_guess": best_canonical,
            "confidence": round(confidence, 2),
        })

    rows.sort(key=lambda r: -r["item_count"])
    if args.max_suggestions > 0:
        rows = rows[: args.max_suggestions]

    if args.json:
        json.dump(
            {
                "unmapped_series": rows,
                "canonical_duplicates": canonical_dups,
                "total": len(rows),
            },
            sys.stdout, ensure_ascii=False, indent=2,
        )
        print()
        return 0

    # Markdown table
    total_items = sum(r["item_count"] for r in rows)
    print(f"# Unmapped series — {len(rows)} candidates ({total_items} items afectados)\n")
    print(f"Generado por `scripts/audit/unmapped_series.py`. ")
    print(f"Total canonical entries en `data/series_aliases.yml`: {len(canonical_keys)}.\n")

    # Sección: canonicals DUPLICADOS (colapsan a la misma forma normalizada del
    # resolver → uno queda sombreado). Insumo para el merge gateado del Lote B.
    print(f"## Canonicals duplicados — {len(canonical_dups)} pares\n")
    if canonical_dups:
        print("Pares de canonicals que normalizan idéntico bajo el resolver "
              "(`series_aliases._normalize`, comparación EXACTA): el resolver sólo "
              "puede mapear a uno, el otro queda sombreado. Candidatos a merge.\n")
        for d in canonical_dups:
            print(f"- `{d['a']}`  ⇄  `{d['b']}`  (via `{d['via']}`)")
        print()
    else:
        print("✓ Sin canonicals duplicados.\n")

    if not rows:
        print("✓ No hay series sin canonical. Todo está mapeado.")
        return 0

    print("Ordenado por `item_count` DESC (atender las de arriba primero).\n")
    print("Para cada candidata, `best_canonical_guess` sugiere un alias existente "
          "que podría matchear (confidence > 0.8 = probable alias; < 0.6 = serie nueva).\n")

    for i, r in enumerate(rows, 1):
        guess = r["best_canonical_guess"]
        guess_disp = canonical_displays.get(guess, guess)
        conf_emoji = "🟢" if r["confidence"] >= 0.8 else "🟡" if r["confidence"] >= 0.6 else "🔴"
        print(f"## {i}. `{r['series_key']}` — {r['item_count']} items")
        print(f"- Primary display: **{r['primary_display']}**")
        if len(r["all_displays"]) > 1:
            print(f"- Otros displays: {', '.join(r['all_displays'][1:])}")
        if guess:
            print(f"- Best guess: {conf_emoji} `{guess}` ({guess_disp!r}) — confidence {r['confidence']}")
        print(f"- Languages: {', '.join(r['languages']) or '?'}")
        print(f"- Publishers: {', '.join(r['publishers']) or '?'}")
        print(f"- Top sources: {', '.join(r['top_sources']) or '?'}")
        if r["sample_titles"]:
            print("- Sample titles:")
            for t in r["sample_titles"][:3]:
                print(f"    - {t}")
        if r["sample_urls"]:
            print(f"- Sample URL: <{r['sample_urls'][0]}>")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
