#!/usr/bin/env python3
"""staleness_report.py — reporte read-only de URLs "rancias" por fuente.

`data/state.json` guarda 1 entrada por URL (`url:<url>` → dict con `source` y
`last_seen_at`). Una URL que dejó de aparecer en los runs recientes es señal de
que la fuente cambió, la despublicó, o el parser dejó de encontrarla. Este script
cuenta, por fuente, cuántas URLs llevan >N días sin verse.

Es INFORMATIVO: no propone borrar nada, no escribe nada, siempre sale con 0.

Anclaje temporal (`--reference`):
- `corpus` (default): la referencia es el `last_seen_at` MÁS RECIENTE de todo el
  corpus, o sea "al momento del último scrape". Aísla las URLs que dejaron de
  verse MIENTRAS el scraper corría, sin que un scraper que no corre hace semanas
  haga parecer rancio TODO el corpus.
- `now`: reloj de pared (`datetime.now`). Útil para "¿hace cuánto no scrapeo?".

Uso:
    python scripts/audit/staleness_report.py                 # --days 90, corpus
    python scripts/audit/staleness_report.py --days 60
    python scripts/audit/staleness_report.py --reference now
    python scripts/audit/staleness_report.py --top 30
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/audit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Mismo patrón de import dual que source_health.py (ver su nota).
try:
    from manga_watch import load_sources  # type: ignore
except ImportError:  # pragma: no cover
    from scripts.manga_watch import load_sources  # type: ignore


def parse_iso(value: str) -> datetime | None:
    """Parsea un ISO-8601; garantiza tz-aware (naive → UTC). None si no parsea."""
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_state(path: Path) -> dict:
    """Carga data/state.json. {} si no existe o está corrupto."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def reference_timestamp(state: dict, mode: str, now_iso: str) -> datetime:
    """Resuelve el timestamp de referencia contra el que se mide la rancidez."""
    if now_iso:
        dt = parse_iso(now_iso)
        if dt is not None:
            return dt
    if mode == "now":
        return datetime.now(timezone.utc)
    # corpus: el last_seen_at más reciente = "al momento del último scrape".
    latest: datetime | None = None
    for entry in state.values():
        if not isinstance(entry, dict):
            continue
        dt = parse_iso(entry.get("last_seen_at", ""))
        if dt is not None and (latest is None or dt > latest):
            latest = dt
    return latest or datetime.now(timezone.utc)


def compute_staleness(state: dict, reference: datetime, days: int) -> dict[str, dict]:
    """Agrupa por fuente y calcula stats de rancidez.

    Returns {source: {total, stale, no_ts, oldest_days, stale_urls}} donde
    stale_urls es [(url, age_days)] sólo de las que superan el umbral.
    """
    agg: dict[str, dict] = defaultdict(lambda: {
        "total": 0,
        "stale": 0,
        "no_ts": 0,
        "oldest_days": 0,
        "stale_urls": [],
    })

    for key, entry in state.items():
        if not isinstance(entry, dict):
            continue
        source = entry.get("source") or "(sin source)"
        a = agg[source]
        a["total"] += 1
        dt = parse_iso(entry.get("last_seen_at", ""))
        if dt is None:
            a["no_ts"] += 1
            continue
        age_days = (reference - dt).days
        if age_days < 0:
            age_days = 0
        if age_days > a["oldest_days"]:
            a["oldest_days"] = age_days
        if age_days > days:
            a["stale"] += 1
            url = entry.get("url") or key[len("url:"):] if key.startswith("url:") else key
            a["stale_urls"].append((url, age_days))

    # Ordenar las URLs rancias de cada fuente por antigüedad desc.
    for a in agg.values():
        a["stale_urls"].sort(key=lambda t: -t[1])
    return dict(agg)


def render_report(
    agg: dict[str, dict],
    reference: datetime,
    ref_mode: str,
    days: int,
    top: int,
    enabled_lookup: dict[str, bool],
) -> str:
    total_urls = sum(a["total"] for a in agg.values())
    total_stale = sum(a["stale"] for a in agg.values())
    total_no_ts = sum(a["no_ts"] for a in agg.values())
    sources_affected = sum(1 for a in agg.values() if a["stale"] > 0)

    lines: list[str] = []
    lines.append("# Staleness Report (read-only)")
    lines.append("")
    lines.append(f"Generated:  {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append(f"Reference:  {reference.isoformat(timespec='seconds')}  ({ref_mode})")
    lines.append(f"Threshold:  URLs no vistas hace > {days} días")
    lines.append("")
    lines.append(f"URLs totales:        {total_urls}")
    lines.append(f"URLs rancias:        {total_stale}")
    lines.append(f"Sin last_seen_at:    {total_no_ts}")
    lines.append(f"Fuentes afectadas:   {sources_affected} / {len(agg)}")
    lines.append("")

    if total_stale == 0:
        lines.append(
            f"Ninguna URL supera los {days} días respecto de la referencia. "
            "Nada rancio que reportar."
        )
        lines.append("")
        return "\n".join(lines)

    # Ranking de fuentes por cantidad de URLs rancias.
    ranked = sorted(
        agg.items(),
        key=lambda kv: (-kv[1]["stale"], -kv[1]["oldest_days"]),
    )
    ranked = [kv for kv in ranked if kv[1]["stale"] > 0]

    lines.append(f"## Top {min(top, len(ranked))} fuentes por URLs rancias")
    lines.append("")
    lines.append("| # | Source | Enab | Rancias | Total | % | Más vieja (días) |")
    lines.append("|--:|---|:--:|--:|--:|--:|--:|")
    for i, (source, a) in enumerate(ranked[:top], start=1):
        enabled = enabled_lookup.get(source)
        enab = "?" if enabled is None else ("✓" if enabled else "✗")
        pct = (a["stale"] / a["total"] * 100.0) if a["total"] else 0.0
        lines.append(
            f"| {i} | {source[:50]} | {enab} | {a['stale']} | {a['total']} "
            f"| {pct:.0f}% | {a['oldest_days']} |"
        )
    lines.append("")

    # Detalle: la URL más vieja de las 20 fuentes más afectadas.
    detail_n = min(20, len(ranked))
    lines.append(f"## Detalle (URL más vieja de las {detail_n} fuentes top)")
    lines.append("")
    for source, a in ranked[:detail_n]:
        if not a["stale_urls"]:
            continue
        url, age = a["stale_urls"][0]
        lines.append(f"- **{source[:50]}** — {a['stale']} rancias, la más vieja ({age}d):")
        lines.append(f"  {url}")
    lines.append("")
    lines.append(
        "Nota: informativo. NO se propone borrar nada — una URL rancia puede ser "
        "una edición agotada válida (dato de referencia) o un parser que dejó de "
        "verla. Investigar la fuente antes de actuar."
    )
    lines.append("")
    return "\n".join(lines)


def build_enabled_lookup(sources_path: Path) -> dict[str, bool]:
    """{source_name: enabled} desde sources.yml. {} si no se puede cargar."""
    try:
        sources = load_sources(sources_path)
    except Exception:  # noqa: BLE001 — es contexto opcional; nunca romper el reporte
        return {}
    return {s.name: s.enabled for s in sources}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state", default="data/state.json",
                   help="Ruta a state.json (default: data/state.json).")
    p.add_argument("--sources", default="sources.yml",
                   help="Ruta a sources.yml para el flag enabled (default: sources.yml).")
    p.add_argument("--days", type=int, default=90,
                   help="Umbral de días sin verse para marcar una URL como rancia (default: 90).")
    p.add_argument("--reference", choices=["corpus", "now"], default="corpus",
                   help="Ancla temporal: 'corpus' = último last_seen del corpus (default), "
                        "'now' = reloj de pared.")
    p.add_argument("--now-iso", default="",
                   help="Override explícito de la referencia (ISO-8601). Para runs deterministas.")
    p.add_argument("--top", type=int, default=20,
                   help="Cuántas fuentes listar en el ranking (default: 20).")
    p.add_argument("--output-file", default="",
                   help="Si se especifica, escribe a archivo (default: stdout).")
    args = p.parse_args()

    state_path = Path(args.state)
    state = load_state(state_path)
    if not state:
        print(f"[WARN] {state_path} vacío o inexistente — nada que reportar.", file=sys.stderr)
        print("# Staleness Report (read-only)\n\nSin datos en state.json.")
        return 0

    ref = reference_timestamp(state, args.reference, args.now_iso)
    ref_mode = "now-iso" if args.now_iso else args.reference
    agg = compute_staleness(state, ref, args.days)
    enabled_lookup = build_enabled_lookup(Path(args.sources))
    out = render_report(agg, ref, ref_mode, args.days, args.top, enabled_lookup)

    if args.output_file:
        Path(args.output_file).write_text(out, encoding="utf-8")
        print(f"[OK] Escrito a {args.output_file}", file=sys.stderr)
    else:
        print(out)
    return 0  # siempre 0: es informativo


if __name__ == "__main__":
    raise SystemExit(main())
