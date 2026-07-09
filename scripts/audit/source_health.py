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

Detección de regresiones de yield (contexto: con --last-n 1 el clasificador
sólo detecta broken_http; una fuente que cae de 300 a 0 items con HTTP 200
sale "healthy"). Dos piezas nuevas:

    # 1) acumular una métrica por fuente del run más reciente (idempotente)
    python scripts/audit/source_health.py --last-n 1 \\
        --metrics-file logs/metrics.jsonl

    # 2) alertar cuando el yield actual cae <50% de la mediana histórica
    #    del MISMO modo (delta-vs-delta, full-vs-full) con >=3 runs de historia
    python scripts/audit/source_health.py --last-n 1 \\
        --metrics-file logs/metrics.jsonl --baseline-alert --mode delta
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
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
#   [SKIP-no-links] ListadoManga (colecciones): Sin enlaces con texto significativo...
#   [CHALLENGE_DETECTED] source=ES - Foo Tienda type=cloudflare
#
# Formato LEGACY (overnight runs antiguos, source en línea propia):
#   [12/184] ES - Listado Manga Calendario :: https://...
#       candidatos con señales: 5 (3 págs)
#
# Formato WIKIS (_run_wiki_bootstrap, un log por wiki, ver manga_watch.py:8469):
#   [BOOTSTRAP-WIKI] fuente: manga-sanctuary
#   ...
#   [RESUMEN BOOTSTRAP-WIKI]
#     candidates totales: 719
_CANDIDATES_COMBINED_RE = re.compile(
    r"^\s*\[(?P<name>.+?)\]\s+candidatos con señales:\s*(?P<n>\d+)"
)
_SOURCE_LINE_RE = re.compile(r"^\s*\[(\d+)/(\d+)\]\s+([^:]+?)\s*::\s*(\S+)\s*$")
_CANDIDATES_RE = re.compile(r"^\s+candidatos con señales:\s*(\d+)")

# (#3, 2026-07-08) Los nombres de search-templates llevan ":" adentro (p.ej.
# "US - Dark Horse Direct (search) [search: limited edition]"). Un split naive
# en el primer ":" corta el nombre ahí y trunca el resto contra el mensaje →
# error atribuido a una fuente fantasma. Se ancla el MENSAJE a los prefijos
# conocidos que emite manga_watch.py (grep `[ERROR]` ahí para la lista
# completa) para que el backtracking de `.+?` salte de largo los ":" falsos
# dentro del nombre.
_ERROR_MSG_PREFIXES = (
    "HTTP error",
    "request error",
    "error inesperado",
    "bloqueada con 403",
    "Playwright no instalado",
    "URL de Bluesky sin handle",
    "error en worker",
)
_ERROR_RE = re.compile(
    r"^\[ERROR\]\s+(?P<name>.+?):\s+(?P<msg>(?:"
    + "|".join(re.escape(p) for p in _ERROR_MSG_PREFIXES)
    + r").*)$"
)
# Fallback: split naive (comportamiento pre-fix) para un mensaje NUEVO que no
# esté en la lista de arriba — mejor una atribución imperfecta que perder el
# error por completo.
_ERROR_RE_LEGACY = re.compile(r"^\[ERROR\]\s+([^:]+):\s+(.+)$")

# (#1, 2026-07-08) `\w+` no capturaba categorías con guion — manga_watch.py
# emite `no-links` y `js-shell` (ver detect_empty_or_js, manga_watch.py:6297)
# además de `empty`; sólo `empty`/`js` matcheaban antes, dejando invisible el
# síntoma más común de ListadoManga.
_SKIP_RE = re.compile(r"^\[SKIP-([\w-]+)\]\s+([^:]+):\s+(.+)$")

# (#2, 2026-07-08) Un 200 OK que es en realidad un challenge anti-bot
# (Cloudflare/WAF, gotcha #107) NO imprime `[ERROR]` ni la línea de
# candidatos — sólo esta línea (manga_watch.py:9063). Sin parsearla, una
# fuente bloqueada quedaba con stats todo-None → "healthy".
_CHALLENGE_RE = re.compile(
    r"^\[CHALLENGE_DETECTED\]\s+source=(?P<name>.+?)\s+type=(?P<type>\S+)\s*$"
)

# (#4, 2026-07-08) Los wikis (26, fuera de sources.yml) van por
# `_run_wiki_bootstrap` — un log distinto por wiki con un header + resumen
# uniformes (ver arriba). IDs = choices= de `--bootstrap-wiki` en
# manga_watch.py:9536; actualizar esta lista si se agrega/quita un wiki (no
# hay constante exportada para importar sin tocar manga_watch.py, que está
# fuera de scope de este script).
_WIKI_IDS = frozenset({
    "listadomanga", "listadomanga-blog", "whakoom", "manga-sanctuary",
    "otaku-calendar", "manga-mexico", "mangavariant", "socialanime",
    "blogbbm", "booksprivilege", "sumikko", "listadomanga-collections",
    "mangapassion", "animeclick", "prhcomics", "kinokuniya", "yenpress",
    "shueisha", "viz", "sevenseas", "kodansha-us", "jd-intl", "spp-tw",
    "kimdong", "ipm", "yaakz",
})
_WIKI_HEADER_RE = re.compile(r"^\[BOOTSTRAP-WIKI\]\s+fuente:\s*(?P<name>\S+)\s*$")
_WIKI_SUMMARY_RE = re.compile(r"^\s*candidates totales:\s*(?P<n>\d+)\s*$")


def _parse_error_line(line: str) -> tuple[str, str] | None:
    """Extrae (nombre_fuente, mensaje) de una línea `[ERROR] ...`.

    Intenta primero `_ERROR_RE` (anclado a prefijos conocidos, corrige #3); si
    el mensaje no matchea ninguno (línea nueva no catalogada), cae al split
    naive `_ERROR_RE_LEGACY`.
    """
    m = _ERROR_RE.match(line)
    if m:
        return m.group("name").strip(), m.group("msg").strip()
    m = _ERROR_RE_LEGACY.match(line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None


# Nombres entre corchetes que NO son sources (markers de estado del scraper).
_NON_SOURCE_BRACKETS = {"ERROR", "OK", "WARN", "INFO", "SKIP"}

# Fecha (y hora opcional) embebida en el nombre del run dir:
#   scrape-delta-2026-06-12-021300 → 2026-06-12T02:13:00
#   overnight-2026-05-21-023019    → 2026-05-21T02:30:19
_RUN_TS_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:-(\d{2})(\d{2})(\d{2}))?")


def infer_run_ts(run_name: str) -> str:
    """Deriva un timestamp ISO del nombre del run dir (mejor esfuerzo).

    Devuelve `YYYY-MM-DDTHH:MM:SS` si el nombre trae hora, `YYYY-MM-DD` si sólo
    trae fecha, o "" si no hay fecha parseable.
    """
    m = _RUN_TS_RE.search(run_name)
    if not m:
        return ""
    y, mo, d = m.group(1), m.group(2), m.group(3)
    if m.group(4):
        return f"{y}-{mo}-{d}T{m.group(4)}:{m.group(5)}:{m.group(6)}"
    return f"{y}-{mo}-{d}"


def infer_run_mode(run_name: str) -> str:
    """Clasifica el modo del run por el prefijo de su nombre.

    scrape-delta-* → delta, scrape-full-* → full, resto (overnight/retry/…) → other.
    """
    if run_name.startswith("scrape-delta-"):
        return "delta"
    if run_name.startswith("scrape-full-"):
        return "full"
    return "other"


def _run_date(run_name: str) -> str:
    """Sólo la parte de fecha (YYYY-MM-DD) del run, para anotaciones legibles."""
    return infer_run_ts(run_name)[:10]


def collect_run_dirs(log_root: Path, last_n: int = 10) -> list[Path]:
    """Devuelve los directorios de run más recientes.

    Ordena por el timestamp embebido en el NOMBRE del run dir (`infer_run_ts`,
    ISO → ordena igual lexicográfica que cronológicamente), NO por mtime
    (#10, 2026-07-08): un restore, un `cp -r`, o cualquier operación que toque
    el filesystem después del run corrompe el orden basado en mtime sin tocar
    el nombre. Esto también intercala correctamente prefijos legacy distintos
    (overnight-/retry-/scrape-delta-/scrape-full-) por fecha real en vez de
    por el orden alfabético del prefijo.
    """
    candidates: list[Path] = []
    for d in log_root.iterdir():
        if not d.is_dir():
            continue
        if d.name.startswith(("overnight-", "retry-", "scrape-delta-", "scrape-full-")):
            candidates.append(d)
    candidates.sort(key=lambda d: infer_run_ts(d.name), reverse=True)
    return candidates[:last_n]


def _blank_stats() -> dict:
    return {"candidates": None, "error": None, "skipped": None, "challenge": None}


def parse_run_log(run_dir: Path) -> dict[str, dict]:
    """Parsea logs de un run y devuelve {source_name: stats}.

    Stats per-source: {candidates, error, skipped, challenge}. Los wikis
    (formato `[BOOTSTRAP-WIKI]`, #4) se agregan con la clave `wiki:<id>`.
    """
    sources: dict[str, dict] = defaultdict(_blank_stats)

    # Buscar logs típicos del scrape (01-scrape.log, 02b-*, etc.)
    log_files = list(run_dir.glob("*.log"))
    for log_file in log_files:
        try:
            content = log_file.read_text(encoding="utf-8")
        except OSError:
            continue
        current_source: str | None = None
        current_wiki: str | None = None
        for line in content.splitlines():
            # Formato ACTUAL: source + candidatos en una sola línea.
            m_comb = _CANDIDATES_COMBINED_RE.match(line)
            if m_comb:
                name = m_comb.group("name").strip()
                if name not in _NON_SOURCE_BRACKETS and not name.startswith("SKIP-"):
                    if name not in sources:
                        sources[name] = _blank_stats()
                    sources[name]["candidates"] = int(m_comb.group("n"))
                continue
            # Formato LEGACY: header de source en su propia línea.
            m_src = _SOURCE_LINE_RE.match(line)
            if m_src:
                current_source = m_src.group(3).strip()
                if current_source not in sources:
                    sources[current_source] = _blank_stats()
                continue
            if current_source:
                m_cand = _CANDIDATES_RE.match(line)
                if m_cand:
                    sources[current_source]["candidates"] = int(m_cand.group(1))
                    continue
            # Formato WIKIS: header identifica el wiki activo del resto del
            # archivo; el resumen final trae el total de candidates.
            m_wiki_hdr = _WIKI_HEADER_RE.match(line)
            if m_wiki_hdr:
                current_wiki = f"wiki:{m_wiki_hdr.group('name').strip()}"
                if current_wiki not in sources:
                    sources[current_wiki] = _blank_stats()
                continue
            if current_wiki:
                m_wiki_sum = _WIKI_SUMMARY_RE.match(line)
                if m_wiki_sum:
                    sources[current_wiki]["candidates"] = int(m_wiki_sum.group("n"))
                    continue
            m_challenge = _CHALLENGE_RE.match(line)
            if m_challenge:
                name = m_challenge.group("name").strip()
                sources[name]["challenge"] = m_challenge.group("type").strip()
                continue
            parsed_err = _parse_error_line(line)
            if parsed_err:
                name, msg = parsed_err
                sources[name]["error"] = msg[:80]
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
        runs_with_challenge, total_candidates, avg_candidates, last_status,
        trend, enabled, kind
    }}
    """
    yaml_lookup = {s.name: s for s in sources_yaml}

    agg: dict[str, dict] = defaultdict(lambda: {
        "runs_seen": 0,
        "runs_with_zero": 0,
        "runs_with_error": 0,
        "runs_with_skip": 0,
        "runs_with_challenge": 0,
        "total_candidates": 0,
        "candidates_per_run": [],
        "errors": [],
        "skips": [],
        "challenges": [],
        "enabled": True,
        "kind": "",
    })

    # (#4, 2026-07-08) Sembrado: las fuentes enabled del YAML y los wikis
    # conocidos que NO aparecen en ningún log del batch analizado deben
    # clasificar "unseen" en vez de faltar del reporte en silencio —
    # `runs_seen` sólo se poblaba antes desde los logs, así que la rama
    # "unseen" de `classify()` era código muerto (siempre runs_seen>=1).
    for s in sources_yaml:
        if getattr(s, "enabled", True):
            _ = agg[s.name]
    for wiki_id in _WIKI_IDS:
        _ = agg[f"wiki:{wiki_id}"]

    for run_dir, source_stats in runs:
        for name, stats in source_stats.items():
            a = agg[name]
            a["runs_seen"] += 1
            if stats["error"]:
                a["runs_with_error"] += 1
                a["errors"].append((run_dir.name, stats["error"]))
            elif stats.get("challenge"):
                a["runs_with_challenge"] += 1
                a["challenges"].append((run_dir.name, stats["challenge"]))
            elif stats["skipped"]:
                a["runs_with_skip"] += 1
                a["skips"].append((run_dir.name, stats["skipped"]))
            elif stats["candidates"] is not None:
                a["total_candidates"] += stats["candidates"]
                a["candidates_per_run"].append(stats["candidates"])
                if stats["candidates"] == 0:
                    a["runs_with_zero"] += 1

    # Enrichment from sources.yml / wiki registry
    for name, a in agg.items():
        if name.startswith("wiki:"):
            # Los wikis no viven en sources.yml (registro aparte, #4); se
            # tratan como siempre-enabled ya que no hay flag equivalente.
            a["kind"] = "wiki"
            a["enabled"] = True
        else:
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
    challenge_rate = stats.get("runs_with_challenge", 0) / runs
    skip_rate = stats["runs_with_skip"] / runs
    zero_rate = stats["runs_with_zero"] / runs
    # (#2, 2026-07-08) Anti-bot primero: una fuente bloqueada por Cloudflare/WAF
    # (gotcha #107) NO es "healthy" aunque nunca tire un [ERROR] HTTP — es el
    # síntoma más insidioso (200 OK que en realidad es un muro).
    if challenge_rate >= 0.5:
        return "broken_challenge"
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


def _single_run_agg(stats: dict) -> dict:
    """Arma el mini-agregado que `classify` espera, para UN solo run/fuente.

    Con runs_seen=1 el clasificador nunca dispara selector_dead/low_yield/decline
    (exigen >=2 runs); por eso la métrica per-run sólo distingue broken_http /
    broken_skip / broken_challenge / healthy. Ese es justamente el límite que
    metrics.jsonl + el baseline vienen a cubrir acumulando historia.
    """
    error = stats.get("error")
    challenge = stats.get("challenge")
    skipped = stats.get("skipped")
    candidates = stats.get("candidates")
    a = {
        "runs_seen": 1,
        "runs_with_error": 1 if error else 0,
        "runs_with_challenge": 1 if (challenge and not error) else 0,
        "runs_with_skip": 1 if (skipped and not error and not challenge) else 0,
        "runs_with_zero": 0,
        "avg_candidates": 0.0,
        "trend": "—",
    }
    if not error and not challenge and not skipped and candidates is not None:
        a["avg_candidates"] = float(candidates)
        if candidates == 0:
            a["runs_with_zero"] = 1
    return a


def _read_metrics(metrics_path: Path) -> list[dict]:
    """Lee metrics.jsonl tolerando líneas corruptas. [] si no existe."""
    if not metrics_path.exists():
        return []
    records: list[dict] = []
    for line in metrics_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def append_metrics(metrics_path: Path, run_dir: Path, source_stats: dict[str, dict]) -> tuple[int, int]:
    """Appendea una línea JSON por fuente del run dado a metrics.jsonl.

    Idempotente por (run, source): si ese par ya está en el archivo, no duplica.
    Devuelve (appended, skipped).
    """
    run_name = run_dir.name
    ts = infer_run_ts(run_name)
    mode = infer_run_mode(run_name)

    existing = {(r.get("run"), r.get("source")) for r in _read_metrics(metrics_path)}

    new_lines: list[str] = []
    skipped = 0
    for name, stats in source_stats.items():
        if (run_name, name) in existing:
            skipped += 1
            continue
        candidates = stats.get("candidates")
        rec = {
            "run": run_name,
            "ts": ts,
            "mode": mode,
            "source": name,
            "candidates": candidates if candidates is not None else 0,
            "errors": 1 if stats.get("error") else 0,
            "status": classify(_single_run_agg(stats)),
        }
        new_lines.append(json.dumps(rec, ensure_ascii=False))

    if new_lines:
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        # (#10, 2026-07-08) Guard de '\n' final: si el archivo existente NO
        # termina en newline (escritura externa interrumpida, edición manual),
        # un `open(..., 'a')` directo fusionaría la primera línea nueva con la
        # última vieja, corrompiendo ambos registros JSON.
        prefix = ""
        if metrics_path.exists() and metrics_path.stat().st_size > 0:
            with metrics_path.open("rb") as fh:
                fh.seek(-1, 2)
                if fh.read(1) != b"\n":
                    prefix = "\n"
        with metrics_path.open("a", encoding="utf-8") as fh:
            fh.write(prefix + "\n".join(new_lines) + "\n")
    return len(new_lines), skipped


def compute_yield_regressions(
    metrics_path: Path,
    current_run_name: str,
    current_stats: dict[str, dict],
    mode: str,
    min_history: int = 3,
    threshold: float = 0.5,
) -> list[dict]:
    """Compara el yield del run actual contra la mediana histórica del MISMO modo.

    Los yields de delta y full difieren radicalmente, así que sólo se comparan
    runs del mismo modo. Se exigen >=`min_history` runs históricos (distintos del
    actual) con mediana > 0; si el yield actual < `threshold`× esa mediana, es una
    regresión. Fuentes en 0 (con historial > 0) se destacan primero.
    """
    history: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for rec in _read_metrics(metrics_path):
        if rec.get("mode") != mode:
            continue
        if rec.get("run") == current_run_name:
            continue  # la historia excluye el run que estamos evaluando
        if rec.get("errors"):
            # (#5, 2026-07-08) Un run con error persiste candidates=0 (ver
            # append_metrics), pero ese 0 NO es yield real — es el run que
            # falló. Sin este filtro, una fuente flaky (429s intermitentes)
            # acumula ceros falsos → mediana se hunde a 0 → `median <= 0:
            # continue` más abajo apaga la detección de regresión justo para
            # la fuente que más la necesita.
            continue
        cand = rec.get("candidates")
        if cand is None:
            continue
        history[rec.get("source")].append((rec.get("run"), cand))

    regressions: list[dict] = []
    for name, stats in current_stats.items():
        current = stats.get("candidates")
        if current is None:
            continue  # errored/skipped: sin conteo de candidatos que comparar
        runs_for_source = history.get(name, [])
        distinct_runs = {r for r, _ in runs_for_source}
        if len(distinct_runs) < min_history:
            continue  # warm-up: no alertar con poca historia
        values = [c for _, c in runs_for_source]
        median = statistics.median(values)
        if median <= 0:
            continue  # sin baseline positivo no hay regresión que medir
        if current < median * threshold:
            regressions.append({
                "source": name,
                "current": current,
                "median": median,
                "pct": (current / median * 100.0) if median else 0.0,
                "history_runs": len(distinct_runs),
                "zero": current == 0,
            })

    # Zeros primero; luego por % de la mediana ascendente (peor caída arriba).
    regressions.sort(key=lambda r: (not r["zero"], r["pct"]))
    return regressions


def render_regressions_md(regressions: list[dict], mode: str) -> str:
    """Sección markdown de regresiones de yield."""
    lines: list[str] = []
    lines.append(f"## 🚨 YIELD REGRESSIONS ({mode}, {len(regressions)})")
    lines.append("")
    lines.append(
        f"Fuentes cuyo yield actual cayó por debajo del 50% de su mediana "
        f"histórica ({mode}, ≥3 runs). Un 200 → 0 con HTTP 200 aparece acá "
        f"aunque el clasificador lo marque `healthy`."
    )
    lines.append("")
    lines.append("| Source | Current | Median | % of median | Hist runs |")
    lines.append("|---|---:|---:|---:|---:|")
    for r in regressions:
        flag = "🔴 " if r["zero"] else ""
        lines.append(
            f"| {flag}{r['source'][:55]} | {r['current']} | {r['median']:g} "
            f"| {r['pct']:.0f}% | {r['history_runs']} |"
        )
    lines.append("")
    return "\n".join(lines)


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
        ("broken_challenge", "🛡️ Broken (anti-bot / challenge)"),
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
        items.sort(key=lambda x: (
            -x[1]["runs_with_challenge"] - x[1]["runs_with_error"] - x[1]["runs_with_zero"]
        ))
        lines.append(f"## {label} ({len(items)})")
        lines.append(f"")
        lines.append("| Source | Kind | Enabled | Runs | Avg cand | Errors | Challenge | Skips | Zero runs | Last issue |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---|")
        for name, s in items[:30]:  # cap por categoría
            # Recencia (#3): anotar la fecha del run MÁS RECIENTE donde se vio el
            # síntoma, para que un 403 viejo ya resuelto no parezca activo cuando
            # se corre con --last-n > 1. La fecha se deriva del nombre del run
            # (robusto al orden de iteración).
            last_issue = ""
            issues = s["errors"] or s.get("challenges") or s["skips"]
            if issues:
                text = max(issues, key=lambda ri: infer_run_ts(ri[0]))
                last_run = max((r for r, _ in issues), key=infer_run_ts, default="")
                date = _run_date(last_run)
                suffix = f" (last: {date})" if date else ""
                last_issue = f"`{text[1][:60]}`{suffix}"
            enabled = "✓" if s["enabled"] else "✗"
            lines.append(
                f"| {name[:55]} | {s['kind'] or '?'} | {enabled} "
                f"| {s['runs_seen']} | {s['avg_candidates']} "
                f"| {s['runs_with_error']} | {s.get('runs_with_challenge', 0)} "
                f"| {s['runs_with_skip']} | {s['runs_with_zero']} | {last_issue} |"
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
    p.add_argument("--metrics-file", default="",
                   help="Si se especifica, appendea una línea JSON por fuente del "
                        "run MÁS RECIENTE analizado a este archivo (logs/metrics.jsonl). "
                        "Idempotente por (run, source).")
    p.add_argument("--baseline-alert", action="store_true",
                   help="Compara el yield del run actual contra la mediana histórica "
                        "del mismo modo en --metrics-file y reporta regresiones "
                        "(caída por debajo de la mitad).")
    p.add_argument("--mode", choices=["delta", "full", "other"], default="",
                   help="Modo del run para el baseline (delta-vs-delta, full-vs-full). "
                        "Si se omite con --baseline-alert, se infiere del run más reciente.")
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

    # El run MÁS RECIENTE analizado (collect_run_dirs devuelve most-recent-first).
    latest_run, latest_stats = parsed[0]

    # --metrics-file: acumular la métrica per-source del run más reciente.
    if args.metrics_file:
        appended, skipped = append_metrics(Path(args.metrics_file), latest_run, latest_stats)
        print(
            f"[metrics] {latest_run.name}: +{appended} líneas "
            f"({skipped} ya presentes) → {args.metrics_file}",
            file=sys.stderr,
        )

    # --baseline-alert: regresiones de yield vs la mediana histórica del mismo modo.
    regressions: list[dict] | None = None
    baseline_mode = ""
    if args.baseline_alert:
        baseline_mode = args.mode or infer_run_mode(latest_run.name)
        if not args.metrics_file:
            print(
                "[baseline] --baseline-alert sin --metrics-file: sin historial que comparar.",
                file=sys.stderr,
            )
            regressions = []
        else:
            regressions = compute_yield_regressions(
                Path(args.metrics_file), latest_run.name, latest_stats, baseline_mode,
            )
            if regressions:
                print(
                    f"[baseline] {len(regressions)} regresión(es) de yield ({baseline_mode}).",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[baseline] sin regresiones de yield ({baseline_mode}).",
                    file=sys.stderr,
                )

    if args.output == "md":
        out = render_markdown(runs, agg)
        if regressions:
            # La sección de regresiones va arriba: es lo más accionable.
            out = render_regressions_md(regressions, baseline_mode) + "\n" + out
    else:
        # JSON serializable
        agg_clean = {}
        for k, v in agg.items():
            agg_clean[k] = {kk: vv for kk, vv in v.items() if kk not in ("errors", "skips", "challenges")}
            agg_clean[k]["errors"] = [e[1] for e in v["errors"][-3:]]
            agg_clean[k]["skips"] = [s[1] for s in v["skips"][-3:]]
            agg_clean[k]["challenges"] = [c[1] for c in v.get("challenges", [])[-3:]]
            agg_clean[k]["classification"] = classify(v)
        payload = {"runs": [r.name for r in runs], "sources": agg_clean}
        if regressions is not None:
            payload["yield_regressions"] = {"mode": baseline_mode, "items": regressions}
        out = json.dumps(payload, indent=2, ensure_ascii=False)

    if args.output_file:
        Path(args.output_file).write_text(out, encoding="utf-8")
        print(f"[OK] Escrito a {args.output_file}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
