#!/usr/bin/env python3
"""source_health.py — auditoría de salud de las sources del scraper.

Lee los logs de los últimos N runs (logs/scrape-delta-*, logs/scrape-full-*,
y los legacy logs/overnight-*, logs/retry-*) y reporta:
- Sources con 0 candidatos en los últimos N runs seguidos → "probable
  selector roto o sitio cambió HTML".
- Sources con tasa de errores HTTP > 50% → "probable bloqueo o caída".
- Sources que vienen produciendo cada vez menos items → "deprecación".
- Sources que siguen funcionando bien → "healthy".

Uso:
    python scripts/audit/source_health.py                # auditoría completa
    python scripts/audit/source_health.py --last-n 5     # últimos 5 runs
    python scripts/audit/source_health.py --output md    # markdown (default)
    python scripts/audit/source_health.py --output json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/audit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# El módulo `manga_watch` puede resolver al wrapper de la raíz del repo
# (manga_watch.py, que sólo reexporta parse_args/run) cuando la raíz está en
# sys.path — p.ej. bajo pytest. En ese caso `load_sources` no existe ahí;
# caemos al paquete real scripts.manga_watch. Ver gotcha de import dual.
try:
    from manga_watch import load_sources  # type: ignore
except ImportError:
    from scripts.manga_watch import load_sources  # type: ignore


# Regex para parsear líneas de log del scraper.
#
# Formato ACTUAL (manga_watch.py emite source + candidatos en UNA línea):
#   [ES - Listado Manga Calendario] candidatos con señales: 5 (3 págs)
#   [ERROR] ES - Misión Tokyo: error inesperado Page.goto: Timeout ...
#   [SKIP-js] ES - Kibook Novedades: requiere JavaScript
#
# Formato LEGACY (overnight runs antiguos, source en línea propia):
#   [12/184] ES - Listado Manga Calendario :: https://...
#       candidatos con señales: 5 (3 págs)
_CANDIDATES_COMBINED_RE = re.compile(
    r"^\s*\[(?P<name>.+?)\]\s+candidatos con señales:\s*(?P<n>\d+)"
)
_SOURCE_LINE_RE = re.compile(r"^\s*\[(\d+)/(\d+)\]\s+([^:]+?)\s*::\s*(\S+)\s*$")
_CANDIDATES_RE = re.compile(r"^\s+candidatos con señales:\s*(\d+)")
_ERROR_RE = re.compile(r"^\[ERROR\]\s+([^:]+):\s+(.+)$")
_SKIP_RE = re.compile(r"^\[SKIP-(\w+)\]\s+([^:]+):\s+(.+)$")

# Nombres entre corchetes que NO son sources (markers de estado del scraper).
_NON_SOURCE_BRACKETS = {"ERROR", "OK", "WARN", "INFO", "SKIP"}


def collect_run_dirs(log_root: Path, last_n: int = 10) -> list[Path]:
    """Devuelve los directorios de run más recientes."""
    candidates: list[tuple[float, Path]] = []
    for d in log_root.iterdir():
        if not d.is_dir():
            continue
        if d.name.startswith(("overnight-", "retry-", "scrape-delta-", "scrape-full-")):
            candidates.append((d.stat().st_mtime, d))
    candidates.sort(reverse=True)
    return [d for _, d in candidates[:last_n]]


def parse_run_log(run_dir: Path) -> dict[str, dict]:
    """Parsea logs de un run y devuelve {source_name: stats}.

    Stats per-source: {candidates, errors, skipped, status}.
    """
    sources: dict[str, dict] = defaultdict(lambda: {
        "candidates": None,
        "error": None,
        "skipped": None,
    })

    # Buscar logs típicos del scrape (01-scrape.log, 02b-*, etc.)
    log_files = list(run_dir.glob("*.log"))
    for log_file in log_files:
        try:
            content = log_file.read_text(encoding="utf-8")
        except OSError:
            continue
        current_source: str | None = None
        for line in content.splitlines():
            # Formato ACTUAL: source + candidatos en una sola línea.
            m_comb = _CANDIDATES_COMBINED_RE.match(line)
            if m_comb:
                name = m_comb.group("name").strip()
                if name not in _NON_SOURCE_BRACKETS and not name.startswith("SKIP-"):
                    if name not in sources:
                        sources[name] = {"candidates": None, "error": None, "skipped": None}
                    sources[name]["candidates"] = int(m_comb.group("n"))
                continue
            # Formato LEGACY: header de source en su propia línea.
            m_src = _SOURCE_LINE_RE.match(line)
            if m_src:
                current_source = m_src.group(3).strip()
                if current_source not in sources:
                    sources[current_source] = {"candidates": None, "error": None, "skipped": None}
                continue
            if current_source:
                m_cand = _CANDIDATES_RE.match(line)
                if m_cand:
                    sources[current_source]["candidates"] = int(m_cand.group(1))
                    continue
            m_err = _ERROR_RE.match(line)
            if m_err:
                name = m_err.group(1).strip()
                sources[name]["error"] = m_err.group(2).strip()[:80]
                continue
            m_skip = _SKIP_RE.match(line)
            if m_skip:
                sources[m_skip.group(2).strip()]["skipped"] = (
                    f"{m_skip.group(1)}: {m_skip.group(3).strip()[:60]}"
                )
    return sources


def aggregate_health(
    runs: list[tuple[Path, dict[str, dict]]],
    sources_yaml: list,
) -> dict[str, dict]:
    """Combina N runs en estadísticas agregadas por source.

    Returns: {source_name: {
        runs_seen, runs_with_zero, runs_with_error, runs_with_skip,
        total_candidates, avg_candidates, last_status, trend, enabled, kind
    }}
    """
    yaml_lookup = {s.name: s for s in sources_yaml}

    agg: dict[str, dict] = defaultdict(lambda: {
        "runs_seen": 0,
        "runs_with_zero": 0,
        "runs_with_error": 0,
        "runs_with_skip": 0,
        "total_candidates": 0,
        "candidates_per_run": [],
        "errors": [],
        "skips": [],
        "enabled": True,
        "kind": "",
    })

    for run_dir, source_stats in runs:
        for name, stats in source_stats.items():
            a = agg[name]
            a["runs_seen"] += 1
            if stats["error"]:
                a["runs_with_error"] += 1
                a["errors"].append((run_dir.name, stats["error"]))
            elif stats["skipped"]:
                a["runs_with_skip"] += 1
                a["skips"].append((run_dir.name, stats["skipped"]))
            elif stats["candidates"] is not None:
                a["total_candidates"] += stats["candidates"]
                a["candidates_per_run"].append(stats["candidates"])
                if stats["candidates"] == 0:
                    a["runs_with_zero"] += 1

    # Enrichment from sources.yml
    for name, a in agg.items():
        src = yaml_lookup.get(name)
        # Para search-templates, el name expandido tiene formato "X (search) [search: Y]"
        # — buscamos por prefijo si el directo falla.
        if src is None:
            for k, v in yaml_lookup.items():
                if name.startswith(k):
                    src = v
                    break
        if src:
            a["enabled"] = src.enabled
            a["kind"] = src.kind
        # Stats derivadas
        cpr = a["candidates_per_run"]
        a["avg_candidates"] = round(sum(cpr) / len(cpr), 1) if cpr else 0.0
        # Trend: comparar primera mitad vs segunda mitad de los runs con candidatos
        if len(cpr) >= 4:
            half = len(cpr) // 2
            first_avg = sum(cpr[:half]) / half if half else 0
            second_avg = sum(cpr[half:]) / (len(cpr) - half)
            if second_avg < first_avg * 0.5:
                a["trend"] = "↓ declining"
            elif second_avg > first_avg * 1.5:
                a["trend"] = "↑ growing"
            else:
                a["trend"] = "→ stable"
        else:
            a["trend"] = "—"

    return dict(agg)


def classify(stats: dict) -> str:
    """Clasifica una source en una categoría de salud."""
    runs = stats["runs_seen"]
    if runs == 0:
        return "unseen"
    error_rate = stats["runs_with_error"] / runs
    skip_rate = stats["runs_with_skip"] / runs
    zero_rate = stats["runs_with_zero"] / runs
    if error_rate >= 0.5:
        return "broken_http"   # bloqueado / caído
    if skip_rate >= 0.5:
        return "broken_skip"   # JS requerido sin --enable-js, etc.
    if zero_rate >= 0.8 and runs >= 2:
        return "selector_dead" # devuelve siempre 0 — selector probablemente roto
    if stats["avg_candidates"] < 1.0 and runs >= 2:
        return "low_yield"
    if stats["trend"] == "↓ declining":
        return "declining"
    return "healthy"


def render_markdown(runs: list[Path], agg: dict[str, dict]) -> str:
    """Genera reporte en markdown."""
    lines: list[str] = []
    lines.append(f"# Source Health Audit")
    lines.append(f"")
    lines.append(f"Generated: `{datetime.now().isoformat(timespec='seconds')}`")
    lines.append(f"")
    lines.append(f"Analyzed {len(runs)} runs:")
    for r in runs:
        lines.append(f"- `{r.name}`")
    lines.append(f"")
    lines.append(f"Total sources observed: {len(agg)}")
    lines.append(f"")

    # Categorize
    by_class: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for name, stats in agg.items():
        by_class[classify(stats)].append((name, stats))

    order = [
        ("broken_http", "🔴 Broken (HTTP errors)"),
        ("broken_skip", "🟠 Broken (skip/JS issues)"),
        ("selector_dead", "🟡 Selector probably dead (always 0 candidates)"),
        ("low_yield", "🟤 Low yield (avg < 1 candidate/run)"),
        ("declining", "📉 Declining trend"),
        ("healthy", "🟢 Healthy"),
        ("unseen", "⚪ Not seen in recent runs"),
    ]

    for cls, label in order:
        items = by_class.get(cls, [])
        if not items:
            continue
        items.sort(key=lambda x: -x[1]["runs_with_error"] - x[1]["runs_with_zero"])
        lines.append(f"## {label} ({len(items)})")
        lines.append(f"")
        lines.append("| Source | Kind | Enabled | Runs | Avg cand | Errors | Skips | Zero runs | Last issue |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|---|")
        for name, s in items[:30]:  # cap por categoría
            last_issue = ""
            if s["errors"]:
                last_issue = f"`{s['errors'][-1][1][:60]}`"
            elif s["skips"]:
                last_issue = f"`{s['skips'][-1][1][:60]}`"
            enabled = "✓" if s["enabled"] else "✗"
            lines.append(
                f"| {name[:55]} | {s['kind'] or '?'} | {enabled} "
                f"| {s['runs_seen']} | {s['avg_candidates']} "
                f"| {s['runs_with_error']} | {s['runs_with_skip']} "
                f"| {s['runs_with_zero']} | {last_issue} |"
            )
        lines.append(f"")
        if len(items) > 30:
            lines.append(f"_+ {len(items) - 30} more_")
            lines.append(f"")

    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--logs-root", default="logs")
    p.add_argument("--last-n", type=int, default=10,
                   help="Cuántos runs más recientes considerar (default: 10).")
    p.add_argument("--output", choices=["md", "json"], default="md")
    p.add_argument("--output-file", default="",
                   help="Si se especifica, escribe a archivo (default: stdout).")
    args = p.parse_args()

    log_root = Path(args.logs_root)
    if not log_root.exists():
        print(f"[ERROR] no existe {log_root}", file=sys.stderr)
        return 1

    runs = collect_run_dirs(log_root, last_n=args.last_n)
    if not runs:
        print(
            f"[ERROR] sin runs en {log_root}/ (busca scrape-delta-*, scrape-full-*, "
            f"overnight-*, retry-*)",
            file=sys.stderr,
        )
        return 1

    parsed = [(run, parse_run_log(run)) for run in runs]
    sources_yaml = load_sources(Path("sources.yml"))
    agg = aggregate_health(parsed, sources_yaml)

    if args.output == "md":
        out = render_markdown(runs, agg)
    else:
        # JSON serializable
        agg_clean = {}
        for k, v in agg.items():
            agg_clean[k] = {kk: vv for kk, vv in v.items() if kk not in ("errors", "skips")}
            agg_clean[k]["errors"] = [e[1] for e in v["errors"][-3:]]
            agg_clean[k]["skips"] = [s[1] for s in v["skips"][-3:]]
            agg_clean[k]["classification"] = classify(v)
        out = json.dumps({"runs": [r.name for r in runs], "sources": agg_clean},
                         indent=2, ensure_ascii=False)

    if args.output_file:
        Path(args.output_file).write_text(out, encoding="utf-8")
        print(f"[OK] Escrito a {args.output_file}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
