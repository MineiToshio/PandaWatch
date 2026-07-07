#!/usr/bin/env python3
"""zero_yield_sources.py — detector de fuentes "siempre cero" (selector roto / muerta).

Complementa `source_health.py --baseline-alert`: ese detector atrapa CAÍDAS de
yield (una fuente que RENDÍA y dejó de rendir), pero tiene un hueco — una fuente
que SIEMPRE rindió ~0 desde el día uno (selector roto de origen, migración a JS
sin `--enable-js`, página que dejó de existir, o candidatos que se generan pero
el filtro los descarta el 100% del tiempo) no tiene un pasado "bueno" con que
comparar, así que el baseline nunca la marca. Este script SÍ la atrapa: cruza
las fuentes `enabled` de `sources.yml` contra cuántos items tienen HOY en
`data/items.jsonl`, y contra el último status observado en los logs recientes.

Es 100% INFORMATIVO: no modifica `sources.yml`, no modifica `items.jsonl`, no
auto-deshabilita nada. Sólo lee y reporta. Exit code siempre 0.

Clasificación (para cada fuente `enabled` con < `--min-items` en el corpus):

    🔴 CERO SOSPECHOSO   — el último run observado NO tuvo error HTTP (corrió con
                            200, con candidatos o sin ellos, o directamente no hay
                            datos de log recientes). Candidata a selector roto,
                            migración a JS, página muerta con 200, o candidatos
                            que el filtro rechaza el 100% del tiempo. ESTE es el
                            caso que se le escapaba al baseline (p.ej. Glénat Art
                            Books: 14-16 candidatos por run, 0 items en el corpus).
    🟡 CERO CON ERROR HTTP — el último run tuvo un error HTTP o un skip (JS
                            requerido, etc.) — ya lo cubre `source_health.py`
                            (broken_http/broken_skip); se lista acá sólo para
                            contexto, no es el gap que este script cierra.
    ⚪ CERO ESPERADO       — la fuente declara `may_be_empty: true` en sources.yml
                            (opt-out manual, ver más abajo). No se re-analiza.

Sufijos `[search: <query>]`: las fuentes con `search_template` + `keywords` en
sources.yml se expanden (vía `load_sources()`) a UNA fuente por keyword. Evaluar
cada keyword-fuente de forma aislada daría falsos sospechosos: es normal que
ALGUNA keyword puntual no encuentre nada en un run dado sin que la fuente esté
rota. Por eso este script agrupa por el nombre BASE (antes del sufijo) y suma
items/candidatos de TODAS sus variantes — sólo se marca sospechoso el GRUPO
completo si NINGUNA keyword produjo items en el corpus.

Opt-out `may_be_empty` (flag opcional, no forma parte del dataclass `Source` de
manga_watch.py — este script lee sources.yml crudo sólo para este campo):

    - name: "ES - Milky Way Próximamente"
      ...
      may_be_empty: true  # página "Próximamente": vacía sin preventas activas

Candidatas conocidas para este marcador (páginas "Próximamente"/"Art Books" sin
catálogo estable, legítimamente vacías a veces): Milky Way Próximamente, Arechi
Manga Próximamente, Glénat Art Books, y cualquier página equivalente de Pika si
llega a tener su propia sección "Próximamente". Este script NO edita
sources.yml — el owner decide cuándo declarar el marcador tras revisar el
reporte.

Fuera de alcance (a propósito): las fuentes-wiki (listadomanga, mangavariant,
etc.) no viven en `sources.yml` — se bootstrapean con nombre propio en
`manga_watch.py::_run_wiki_bootstrap()`. Cubrirlas requeriría leer ese registro
aparte; el foco pedido son las fuentes de `sources.yml`.

Uso:
    python scripts/audit/zero_yield_sources.py                       # reporte md
    python scripts/audit/zero_yield_sources.py --min-items 2
    python scripts/audit/zero_yield_sources.py --output text
    python scripts/audit/zero_yield_sources.py --output-file logs/zero-yield.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/audit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Mismo patrón de import dual que source_health.py / staleness_report.py: bajo
# pytest `manga_watch` puede resolver al wrapper de la raíz (sólo reexporta
# parse_args/run); ahí caemos al paquete real scripts.manga_watch.
try:
    from manga_watch import Source, load_sources  # type: ignore
except ImportError:  # pragma: no cover
    from scripts.manga_watch import Source, load_sources  # type: ignore

try:
    from source_health import collect_run_dirs, parse_run_log  # type: ignore
except ImportError:  # pragma: no cover
    from scripts.audit.source_health import collect_run_dirs, parse_run_log  # type: ignore


# Sufijo que `_expand_search_template()` (manga_watch.py) le agrega al nombre
# base de una fuente con search_template+keywords: "<base> [search: <kw>]".
_SEARCH_SUFFIX_RE = re.compile(r"\s*\[search:.*\]\s*$")


def group_key(name: str) -> str:
    """Colapsa una fuente search-template expandida a su nombre base.

    'MX - Panini México (search) [search: deluxe]' -> 'MX - Panini México (search)'.
    Una fuente sin sufijo es su propio grupo (grupo de 1).
    """
    return _SEARCH_SUFFIX_RE.sub("", name).strip()


@dataclass
class SourceGroup:
    key: str
    variant_names: list[str] = field(default_factory=list)
    kind: str = "html"
    may_be_empty: bool = False


def load_may_be_empty_map(sources_yaml_path: Path) -> dict[str, bool]:
    """Lee sources.yml crudo y devuelve {name: may_be_empty}.

    `may_be_empty` no es un campo del dataclass Source (no tocamos
    manga_watch.py) — se lee directo del YAML por nombre DECLARADO (antes de la
    expansión search_template, que es exactamente el `group_key()` de sus
    variantes expandidas).
    """
    if not sources_yaml_path.exists():
        return {}
    try:
        raw = yaml.safe_load(sources_yaml_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    result: dict[str, bool] = {}
    for item in raw.get("sources", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        result[name] = bool(item.get("may_be_empty", False))
    return result


def build_groups(
    enabled_sources: list[Source], may_be_empty_map: dict[str, bool]
) -> dict[str, SourceGroup]:
    """Agrupa las fuentes enabled (ya expandidas) por su nombre base."""
    groups: dict[str, SourceGroup] = {}
    for s in enabled_sources:
        gk = group_key(s.name)
        g = groups.get(gk)
        if g is None:
            g = SourceGroup(key=gk, kind=s.kind, may_be_empty=may_be_empty_map.get(gk, False))
            groups[gk] = g
        g.variant_names.append(s.name)
    return groups


def count_items_by_source(items_path: Path) -> Counter:
    """Cuenta, por nombre de fuente, en cuántos items del corpus aparece.

    Usa `sources[].name` (fuente única de agrupación multi-fuente, decisión #1
    de architecture.md) — no el `source` top-level, que es sólo la primera.
    Tolera líneas corruptas (se saltean).
    """
    counts: Counter = Counter()
    if not items_path.exists():
        return counts
    with items_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            names = {
                s.get("name")
                for s in (item.get("sources") or [])
                if isinstance(s, dict) and s.get("name")
            }
            for name in names:
                counts[name] += 1
    return counts


def last_group_status(
    group: SourceGroup, parsed_runs: list[tuple[Path, dict[str, dict]]]
) -> dict:
    """Status más reciente observado en logs para CUALQUIER variante del grupo.

    `parsed_runs` ya viene más-reciente-primero (mismo orden de
    `collect_run_dirs`). Dentro del run más reciente donde aparece AL MENOS una
    variante: error > skip > candidatos (un error real en una keyword cuenta
    aunque otra keyword del mismo grupo haya rendido ese run).

    Devuelve {"status": "error"|"skip"|"ran"|"no_data", "run": str, "detail": str}.
    """
    for run_dir, source_stats in parsed_runs:
        seen = {
            name: source_stats[name] for name in group.variant_names if name in source_stats
        }
        if not seen:
            continue
        errors = {n: st["error"] for n, st in seen.items() if st.get("error")}
        if errors:
            detail = "; ".join(f"{n}: {msg}" for n, msg in errors.items())
            return {"status": "error", "run": run_dir.name, "detail": detail[:160]}
        skips = {n: st["skipped"] for n, st in seen.items() if st.get("skipped")}
        if skips:
            detail = "; ".join(f"{n}: {msg}" for n, msg in skips.items())
            return {"status": "skip", "run": run_dir.name, "detail": detail[:160]}
        cand_total = sum(
            st.get("candidates") or 0 for st in seen.values() if st.get("candidates") is not None
        )
        return {
            "status": "ran",
            "run": run_dir.name,
            "detail": f"{cand_total} candidatos (HTTP 200, sin error)",
        }
    return {"status": "no_data", "run": "", "detail": "sin entradas en los runs analizados"}


def classify_group(group: SourceGroup, total_items: int, min_items: int, status: dict) -> str:
    """Clasifica un grupo en: ok | expected | known_error | suspicious."""
    if total_items >= min_items:
        return "ok"
    if group.may_be_empty:
        return "expected"
    if status["status"] in ("error", "skip"):
        return "known_error"
    return "suspicious"  # incluye "ran" (200 sin error) y "no_data"


@dataclass
class GroupReport:
    key: str
    kind: str
    variant_names: list[str]
    total_items: int
    status: dict
    classification: str


def analyze(
    sources_yaml: Path,
    items_path: Path,
    logs_root: Path,
    last_n_runs: int,
    min_items: int,
) -> tuple[list[GroupReport], int]:
    """Corre el análisis completo. Devuelve (reports, total_groups_evaluados)."""
    try:
        enabled_sources = [s for s in load_sources(sources_yaml) if s.enabled]
    except FileNotFoundError:
        print(f"[WARN] no existe {sources_yaml}; 0 fuentes evaluadas.", file=sys.stderr)
        enabled_sources = []

    may_be_empty_map = load_may_be_empty_map(sources_yaml)
    groups = build_groups(enabled_sources, may_be_empty_map)
    item_counts = count_items_by_source(items_path)
    if not items_path.exists():
        print(f"[WARN] no existe {items_path}; se asume 0 items para todas las fuentes.",
              file=sys.stderr)

    parsed_runs: list[tuple[Path, dict[str, dict]]] = []
    if logs_root.exists():
        run_dirs = collect_run_dirs(logs_root, last_n=last_n_runs)
        parsed_runs = [(run, parse_run_log(run)) for run in run_dirs]
    else:
        print(f"[WARN] no existe {logs_root}; sin datos de logs (todo cae en no_data).",
              file=sys.stderr)

    reports: list[GroupReport] = []
    for gk, group in groups.items():
        total = sum(item_counts.get(name, 0) for name in group.variant_names)
        if total >= min_items:
            continue  # tiene items: no es zero-yield, no aparece en el reporte
        status = last_group_status(group, parsed_runs)
        cls = classify_group(group, total, min_items, status)
        reports.append(
            GroupReport(
                key=gk,
                kind=group.kind,
                variant_names=sorted(group.variant_names),
                total_items=total,
                status=status,
                classification=cls,
            )
        )
    return reports, len(groups)


_SECTIONS = [
    ("suspicious", "🔴 CERO SOSPECHOSO"),
    ("known_error", "🟡 CERO CON ERROR HTTP"),
    ("expected", "⚪ CERO ESPERADO"),
]


def render_markdown(reports: list[GroupReport], total_groups: int, min_items: int) -> str:
    lines: list[str] = []
    lines.append("# Zero-Yield Sources Audit")
    lines.append("")
    lines.append(
        f"Fuentes enabled evaluadas (agrupadas): {total_groups}. "
        f"Umbral `--min-items`: {min_items}. "
        f"Grupos con < {min_items} item(s) en el corpus: {len(reports)}."
    )
    lines.append("")
    by_class: dict[str, list[GroupReport]] = {"suspicious": [], "known_error": [], "expected": []}
    for r in reports:
        by_class.setdefault(r.classification, []).append(r)

    for cls, label in _SECTIONS:
        items = by_class.get(cls, [])
        lines.append(f"## {label} ({len(items)})")
        lines.append("")
        if not items:
            lines.append("_(ninguna)_")
            lines.append("")
            continue
        lines.append("| Fuente | Kind | Variantes | Último status | Detalle | Run |")
        lines.append("|---|---|---:|---|---|---|")
        for r in sorted(items, key=lambda x: x.key):
            lines.append(
                f"| {r.key[:60]} | {r.kind} | {len(r.variant_names)} "
                f"| {r.status['status']} | {r.status['detail'][:80]} | {r.status['run'] or '—'} |"
            )
        lines.append("")
    return "\n".join(lines)


def render_text(reports: list[GroupReport], total_groups: int, min_items: int) -> str:
    lines: list[str] = []
    lines.append("Zero-Yield Sources Audit")
    lines.append(
        f"Fuentes enabled evaluadas (agrupadas): {total_groups}. "
        f"Umbral --min-items: {min_items}. "
        f"Grupos con < {min_items} item(s) en el corpus: {len(reports)}."
    )
    lines.append("")
    by_class: dict[str, list[GroupReport]] = {"suspicious": [], "known_error": [], "expected": []}
    for r in reports:
        by_class.setdefault(r.classification, []).append(r)

    for cls, label in _SECTIONS:
        items = by_class.get(cls, [])
        lines.append(f"{label} ({len(items)})")
        if not items:
            lines.append("  (ninguna)")
        for r in sorted(items, key=lambda x: x.key):
            variants = f" [{len(r.variant_names)} variantes]" if len(r.variant_names) > 1 else ""
            lines.append(
                f"  - {r.key}{variants} | kind={r.kind} | status={r.status['status']} "
                f"| {r.status['detail']} | run={r.status['run'] or '—'}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sources-yaml", default="sources.yml")
    p.add_argument("--items", default="data/items.jsonl")
    p.add_argument("--logs-root", default="logs")
    p.add_argument("--last-n-runs", type=int, default=10,
                   help="Cuántos runs recientes escanear buscando el último status "
                        "observado (default: 10, igual que source_health.py).")
    p.add_argument("--min-items", type=int, default=1,
                   help="Umbral de 'cero' en el corpus: un grupo con menos de este "
                        "número de items entra al análisis (default: 1, o sea == 0).")
    p.add_argument("--output", choices=["md", "text"], default="md")
    p.add_argument("--output-file", default="",
                   help="Si se especifica, escribe el reporte a este archivo "
                        "(default: stdout). Es el único archivo que este script toca.")
    args = p.parse_args()

    reports, total_groups = analyze(
        sources_yaml=Path(args.sources_yaml),
        items_path=Path(args.items),
        logs_root=Path(args.logs_root),
        last_n_runs=args.last_n_runs,
        min_items=args.min_items,
    )

    if args.output == "md":
        out = render_markdown(reports, total_groups, args.min_items)
    else:
        out = render_text(reports, total_groups, args.min_items)

    if args.output_file:
        Path(args.output_file).write_text(out, encoding="utf-8")
        print(f"[OK] Escrito a {args.output_file}")
    else:
        print(out)

    return 0  # informativo: siempre 0, incluso sin sources.yml/items.jsonl/logs


if __name__ == "__main__":
    raise SystemExit(main())
