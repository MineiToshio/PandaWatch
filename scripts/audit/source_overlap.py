#!/usr/bin/env python3
"""source_overlap.py — overlap real del corpus para el Step 2 de `watch-evaluate-sources`.

Hallazgo ES-1 (auditoría Fable 2026-07-11): el contrato del subagente (SKILL.md
Step 1) nunca capturaba `isbn` ni `series_key` por item muestreado, pero el
Step 2 igual le pedía al LLM "cruza los ISBNs de la muestra con
existing_isbns" — el % de overlap de la tabla final era un número inventado,
no un cruce real. Este script hace el cruce de verdad contra `data/items.jsonl`
y devuelve porcentajes verificables (o `"sin_datos"` si la muestra no trajo
ningún ISBN/serie).

Reutiliza, sin reimplementar, las funciones canónicas del pipeline:
  - `normalize_isbn()` (scripts/manga_watch.py) — el MISMO normalizador
    ISBN-10→13 que usa el scraper para deduplicar. Se aplica tanto al corpus
    como a la muestra para que el cruce sea consistente.
  - `_slugify_kebab()` (scripts/manga_watch.py) — el MISMO slugify que deriva
    `series_key` en `derive_series_and_edition_keys()`. Un `series_key_guess`
    crudo ("One Piece") se normaliza con esta función ANTES de cruzarlo
    contra los `series_key` ya derivados del corpus.

100% de solo lectura: nunca escribe `data/items.jsonl` ni `sources.yml`.
Exit code siempre 0 (informativo — el propio SKILL.md decide qué hacer con
el resultado).

Input (uno de los dos, se pueden combinar):
  --eval-file PATH   JSON de source-eval (formato descrito en SKILL.md,
                      `data/diagnostics/source-eval-<id>.json`): lee
                      `sample_items[].isbn` y `.series_key_guess`.
  --isbns / --series Listas manuales coma-separadas, para uso ad-hoc sin
                      pasar por un archivo de eval completo.

Uso:
    python scripts/audit/source_overlap.py --eval-file data/diagnostics/source-eval-nueva-tienda-fr.json
    python scripts/audit/source_overlap.py --isbns 9784253000539,9781421506630 --series "One Piece,Bleach"
    python scripts/audit/source_overlap.py --eval-file ... --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/audit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Mismo patrón de import dual que source_health.py / zero_yield_sources.py:
# bajo pytest `manga_watch` resuelve vía el paquete `scripts`; en CLI directo
# (`python scripts/audit/source_overlap.py`) cae al import plano de arriba.
try:
    from manga_watch import _slugify_kebab, load_sources, normalize_isbn  # type: ignore
except ImportError:  # pragma: no cover
    from scripts.manga_watch import _slugify_kebab, load_sources, normalize_isbn  # type: ignore


# --------------------------------------------------------------------------- #
# Corpus
# --------------------------------------------------------------------------- #

@dataclass
class CorpusStats:
    total_items: int = 0
    isbns: set[str] = field(default_factory=set)
    series_keys: set[str] = field(default_factory=set)
    country_counts: Counter = field(default_factory=Counter)


def load_corpus(items_path: Path) -> CorpusStats:
    """Lee `data/items.jsonl` y agrega ISBNs/series_keys/países.

    Read-only — nunca escribe. Tolera archivo ausente (corpus vacío, no
    explota) y líneas corruptas (se saltean, igual que el resto de
    scripts/audit/*.py).

    ISBNs se re-normalizan con `normalize_isbn()` al cargar (idempotente
    sobre un ISBN-13 ya limpio) para que el cruce con la muestra sea
    consistente aunque el corpus tenga algún residuo sin normalizar.
    """
    stats = CorpusStats()
    if not items_path.exists():
        return stats
    with items_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            stats.total_items += 1
            isbn_raw = item.get("isbn") or ""
            if isbn_raw:
                normalized = normalize_isbn(str(isbn_raw))
                if normalized:
                    stats.isbns.add(normalized)
            series_key = item.get("series_key") or ""
            if series_key:
                stats.series_keys.add(str(series_key))
            country = item.get("country") or "?"
            stats.country_counts[str(country)] += 1
    return stats


def top_countries(corpus: CorpusStats, n: int = 10) -> list[tuple[str, int]]:
    return sorted(corpus.country_counts.items(), key=lambda kv: -kv[1])[:n]


# --------------------------------------------------------------------------- #
# sources.yml en vivo (F2 — reemplaza la tabla hardcodeada de "Fuentes ya activas")
# --------------------------------------------------------------------------- #

def load_active_sources_by_country(sources_yaml: Path) -> dict[str, list[dict]]:
    """Agrupa las fuentes `enabled` de sources.yml por país, con su kind/purity.

    Reemplaza la tabla "Fuentes ya activas" hardcodeada que el SKILL.md tenía
    inline (hallazgo ES-2): esa tabla quedaba desincronizada apenas se
    agregaba/quitaba una fuente. `sources.yml` es la fuente de verdad — este
    helper la lee en vivo. Devuelve `{country: [{"name", "kind", "purity"}, ...]}`
    ordenado por nombre dentro de cada país; `""` (país no declarado) agrupa
    fuentes wiki/globales que no tienen `country` en el YAML.
    """
    try:
        sources = [s for s in load_sources(sources_yaml) if s.enabled]
    except FileNotFoundError:
        return {}
    by_country: dict[str, list[dict]] = {}
    for s in sources:
        key = s.country or ""
        by_country.setdefault(key, []).append(
            {"name": s.name, "kind": s.kind, "purity": s.purity}
        )
    for entries in by_country.values():
        entries.sort(key=lambda e: e["name"])
    return by_country


# --------------------------------------------------------------------------- #
# Overlap
# --------------------------------------------------------------------------- #

def overlap_classification(pct: float | None) -> str:
    """Bucket de la regla de overlap del Step 2 (SKILL.md).

    < 30% → nuevo · 30-70% → parcial · > 70% → redundante · sin muestra → sin_datos.
    """
    if pct is None:
        return "sin_datos"
    if pct < 30.0:
        return "nuevo"
    if pct <= 70.0:
        return "parcial"
    return "redundante"


def _overlap_bucket(sample_raw: list[str], existing: set[str], normalize) -> dict:
    normalized = [normalize(v) for v in sample_raw]
    normalized = [v for v in normalized if v]
    total = len(normalized)
    if total == 0:
        return {"sample_total": 0, "matched": 0, "pct": None, "classification": "sin_datos"}
    matched = sum(1 for v in normalized if v in existing)
    pct = round(matched / total * 100, 1)
    return {
        "sample_total": total,
        "matched": matched,
        "pct": pct,
        "classification": overlap_classification(pct),
    }


def compute_overlap(
    corpus: CorpusStats,
    sample_isbns_raw: list[str],
    sample_series_raw: list[str],
) -> dict:
    """Cruza la muestra de una fuente candidata contra el corpus.

    `sample_isbns_raw`: ISBNs crudos de la muestra (se normalizan con
    `normalize_isbn()`, igual que el corpus).
    `sample_series_raw`: nombres de serie crudos (el `series_key_guess` del
    subagente, ej. "One Piece") — se slugifican con `_slugify_kebab()` (el
    MISMO slug que usa el pipeline para derivar `series_key`) antes de cruzar.
    """
    return {
        "isbn_overlap": _overlap_bucket(sample_isbns_raw, corpus.isbns, normalize_isbn),
        "series_overlap": _overlap_bucket(sample_series_raw, corpus.series_keys, _slugify_kebab),
    }


# --------------------------------------------------------------------------- #
# source-eval JSON (contrato del Step 1 del SKILL.md)
# --------------------------------------------------------------------------- #

def load_eval_file(eval_path: Path) -> tuple[list[str], list[str]]:
    """Extrae `isbn` y `series_key_guess` de `sample_items[]` de un source-eval JSON.

    Formato descrito en SKILL.md (Step 1, sección D). Tolerante: items sin
    esos campos, o el archivo sin `sample_items`, devuelven listas vacías en
    vez de explotar (el subagente puede haber dejado el campo afuera si la
    detail page no traía ISBN).
    """
    try:
        data = json.loads(eval_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    isbns: list[str] = []
    series: list[str] = []
    for item in data.get("sample_items", []) or []:
        if not isinstance(item, dict):
            continue
        isbn = str(item.get("isbn") or "").strip()
        if isbn:
            isbns.append(isbn)
        guess = str(item.get("series_key_guess") or "").strip()
        if guess:
            series.append(guess)
    return isbns, series


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def render_text(result: dict) -> str:
    lines: list[str] = []
    c = result["corpus"]
    lines.append(
        f"Corpus: {c['total_items']} items, {c['unique_isbns']} ISBNs únicos, "
        f"{c['unique_series']} series únicas."
    )
    lines.append("Top países:")
    for country, n in c["top_countries"]:
        lines.append(f"  {country}: {n}")
    for label, key in (("ISBN", "isbn_overlap"), ("Series", "series_overlap")):
        o = result[key]
        if o["classification"] == "sin_datos":
            lines.append(f"{label} overlap: sin datos (muestra sin {label.lower()})")
        else:
            lines.append(
                f"{label} overlap: {o['matched']}/{o['sample_total']} "
                f"({o['pct']}%) → {o['classification']}"
            )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _parse_csv(raw: str) -> list[str]:
    return [v.strip() for v in raw.split(",") if v.strip()]


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--items", default="data/items.jsonl", help="ruta a items.jsonl (default: data/items.jsonl)")
    p.add_argument("--sources-yaml", default="sources.yml", help="ruta a sources.yml (default: sources.yml)")
    p.add_argument("--eval-file", default="", help="JSON de source-eval (data/diagnostics/source-eval-<id>.json)")
    p.add_argument("--isbns", default="", help="lista manual de ISBNs, separados por coma")
    p.add_argument("--series", default="", help="lista manual de nombres de serie crudos, separados por coma")
    p.add_argument("--top-countries", type=int, default=10, help="cuántos países mostrar en el breakdown (default: 10)")
    p.add_argument("--json", action="store_true", help="output JSON en vez de texto legible")
    args = p.parse_args()

    corpus = load_corpus(Path(args.items))

    sample_isbns: list[str] = []
    sample_series: list[str] = []
    if args.eval_file:
        eval_isbns, eval_series = load_eval_file(Path(args.eval_file))
        sample_isbns.extend(eval_isbns)
        sample_series.extend(eval_series)
    if args.isbns:
        sample_isbns.extend(_parse_csv(args.isbns))
    if args.series:
        sample_series.extend(_parse_csv(args.series))

    overlap = compute_overlap(corpus, sample_isbns, sample_series)
    result = {
        "corpus": {
            "total_items": corpus.total_items,
            "unique_isbns": len(corpus.isbns),
            "unique_series": len(corpus.series_keys),
            "top_countries": top_countries(corpus, args.top_countries),
        },
        **overlap,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(render_text(result))

    return 0  # informativo: read-only, siempre 0


if __name__ == "__main__":
    raise SystemExit(main())
