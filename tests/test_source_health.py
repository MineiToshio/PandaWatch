"""Tests para scripts/audit/source_health.py y staleness_report.py.

Cubren las piezas nuevas de detección de regresiones de ingestión:
- metrics.jsonl: append + idempotencia por (run, source).
- baseline: warm-up (<3 runs) no alerta; caída <50% sí; filtrado por modo.
- inferencia de ts/modo desde el nombre del run + anotación de recencia.
- staleness_report: conteo por fuente contra un ancla temporal fija (tmp_path).

Y la auditoría Fable 2026-07-08 (paquete B-observabilidad):
- #1: _SKIP_RE captura categorías con guion (no-links, js-shell).
- #2: [CHALLENGE_DETECTED] se parsea como categoría propia (broken_challenge).
- #3: _ERROR_RE no trunca nombres de search-template con ':' adentro.
- #4: unseen se siembra con las fuentes enabled del YAML + los wikis conocidos.
- #5: compute_yield_regressions saltea runs con error al armar la mediana.
- #10: append_metrics guarda '\\n' final; collect_run_dirs ordena por nombre.

Los fixtures de log de las 3 primeras usan líneas REALES copiadas de
logs/scrape-delta-2026-07-07-135134/.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from scripts import manga_watch as mw
from scripts.audit import source_health as sh
from scripts.audit import staleness_report as st


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_run(tmp_path: Path, name: str, sources: dict[str, int | None], errors: dict[str, str] | None = None) -> Path:
    """Crea un run dir con un scrape log en el formato ACTUAL (combined).

    sources: {source_name: candidates | None}. errors: {source_name: msg}.
    """
    run_dir = tmp_path / name
    run_dir.mkdir()
    lines: list[str] = []
    for src, cand in sources.items():
        if cand is not None:
            lines.append(f"    [{src}] candidatos con señales: {cand}")
    for src, msg in (errors or {}).items():
        lines.append(f"[ERROR] {src}: {msg}")
    (run_dir / "01-scrape.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return run_dir


def _write_metrics(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")


def _metric(run: str, source: str, candidates: int, mode: str = "delta") -> dict:
    return {"run": run, "ts": sh.infer_run_ts(run), "mode": mode,
            "source": source, "candidates": candidates, "errors": 0, "status": "healthy"}


# --------------------------------------------------------------------------- #
# infer_run_ts / infer_run_mode
# --------------------------------------------------------------------------- #

def test_infer_run_ts_with_time():
    assert sh.infer_run_ts("scrape-delta-2026-06-12-021300") == "2026-06-12T02:13:00"


def test_infer_run_ts_date_only():
    assert sh.infer_run_ts("weird-run-2026-06-12") == "2026-06-12"


def test_infer_run_ts_no_date():
    assert sh.infer_run_ts("no-date-here") == ""


def test_infer_run_mode():
    assert sh.infer_run_mode("scrape-delta-2026-06-12-021300") == "delta"
    assert sh.infer_run_mode("scrape-full-2026-05-24-020327") == "full"
    assert sh.infer_run_mode("overnight-2026-05-21-023019") == "other"
    assert sh.infer_run_mode("retry-2026-05-21-082236") == "other"


# --------------------------------------------------------------------------- #
# metrics append + idempotencia
# --------------------------------------------------------------------------- #

def test_metrics_append_writes_one_line_per_source(tmp_path):
    run = _make_run(tmp_path, "scrape-delta-2026-06-04-020000", {"AR - Foo": 200, "AR - Bar": 50})
    metrics = tmp_path / "logs" / "metrics.jsonl"

    appended, skipped = sh.append_metrics(metrics, run, sh.parse_run_log(run))
    assert (appended, skipped) == (2, 0)
    assert metrics.exists()  # crea el dir logs/ si no existía

    records = [json.loads(l) for l in metrics.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    by_source = {r["source"]: r for r in records}
    foo = by_source["AR - Foo"]
    assert foo["run"] == "scrape-delta-2026-06-04-020000"
    assert foo["ts"] == "2026-06-04T02:00:00"
    assert foo["mode"] == "delta"
    assert foo["candidates"] == 200
    assert foo["errors"] == 0
    assert foo["status"] == "healthy"


def test_metrics_append_is_idempotent(tmp_path):
    run = _make_run(tmp_path, "scrape-delta-2026-06-04-020000", {"AR - Foo": 200, "AR - Bar": 50})
    metrics = tmp_path / "metrics.jsonl"

    sh.append_metrics(metrics, run, sh.parse_run_log(run))
    # Segunda corrida del MISMO run: no debe duplicar.
    appended, skipped = sh.append_metrics(metrics, run, sh.parse_run_log(run))
    assert (appended, skipped) == (0, 2)
    assert len(metrics.read_text(encoding="utf-8").splitlines()) == 2


def test_metrics_append_new_run_extends_history(tmp_path):
    metrics = tmp_path / "metrics.jsonl"
    r1 = _make_run(tmp_path, "scrape-delta-2026-06-01-020000", {"AR - Foo": 200})
    r2 = _make_run(tmp_path, "scrape-delta-2026-06-02-020000", {"AR - Foo": 210})
    sh.append_metrics(metrics, r1, sh.parse_run_log(r1))
    sh.append_metrics(metrics, r2, sh.parse_run_log(r2))
    records = [json.loads(l) for l in metrics.read_text(encoding="utf-8").splitlines()]
    assert {r["run"] for r in records} == {
        "scrape-delta-2026-06-01-020000", "scrape-delta-2026-06-02-020000"}


def test_metrics_errored_source_records_zero_and_error(tmp_path):
    run = _make_run(tmp_path, "scrape-delta-2026-06-04-020000", {}, errors={"ES - Boom": "HTTP 403"})
    metrics = tmp_path / "metrics.jsonl"
    sh.append_metrics(metrics, run, sh.parse_run_log(run))
    rec = json.loads(metrics.read_text(encoding="utf-8").splitlines()[0])
    assert rec["source"] == "ES - Boom"
    assert rec["candidates"] == 0
    assert rec["errors"] == 1
    assert rec["status"] == "broken_http"


# --------------------------------------------------------------------------- #
# baseline: warm-up, caída, filtrado por modo, exclusión del run actual
# --------------------------------------------------------------------------- #

def test_baseline_below_min_history_no_alert(tmp_path):
    """Con <3 runs históricos del modo, no se alerta (warm-up)."""
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, [
        _metric("scrape-delta-2026-06-01-020000", "AR - Foo", 200),
        _metric("scrape-delta-2026-06-02-020000", "AR - Foo", 210),
    ])
    current = {"AR - Foo": {"candidates": 0, "error": None, "skipped": None}}
    regs = sh.compute_yield_regressions(metrics, "scrape-delta-2026-06-03-020000", current, "delta")
    assert regs == []


def test_baseline_drop_below_half_alerts(tmp_path):
    """Con >=3 runs y caída <50% de la mediana, se reporta la regresión."""
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, [
        _metric("scrape-delta-2026-06-01-020000", "AR - Foo", 200),
        _metric("scrape-delta-2026-06-02-020000", "AR - Foo", 210),
        _metric("scrape-delta-2026-06-03-020000", "AR - Foo", 190),
    ])
    current = {"AR - Foo": {"candidates": 0, "error": None, "skipped": None}}
    regs = sh.compute_yield_regressions(metrics, "scrape-delta-2026-06-04-020000", current, "delta")
    assert len(regs) == 1
    r = regs[0]
    assert r["source"] == "AR - Foo"
    assert r["current"] == 0
    assert r["median"] == 200
    assert r["zero"] is True
    assert r["history_runs"] == 3


def test_baseline_healthy_yield_no_alert(tmp_path):
    """Un yield que se mantiene (~96% de la mediana) NO es regresión."""
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, [
        _metric("scrape-delta-2026-06-01-020000", "AR - Bar", 50),
        _metric("scrape-delta-2026-06-02-020000", "AR - Bar", 52),
        _metric("scrape-delta-2026-06-03-020000", "AR - Bar", 48),
    ])
    current = {"AR - Bar": {"candidates": 48, "error": None, "skipped": None}}
    regs = sh.compute_yield_regressions(metrics, "scrape-delta-2026-06-04-020000", current, "delta")
    assert regs == []


def test_baseline_filters_by_mode(tmp_path):
    """Los yields de full (mucho mayores) no contaminan el baseline de delta."""
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, [
        # 3 runs full con yields altos
        _metric("scrape-full-2026-05-01-020000", "AR - Foo", 1000, mode="full"),
        _metric("scrape-full-2026-05-02-020000", "AR - Foo", 1100, mode="full"),
        _metric("scrape-full-2026-05-03-020000", "AR - Foo", 900, mode="full"),
        # 3 runs delta con yields bajos
        _metric("scrape-delta-2026-06-01-020000", "AR - Foo", 200),
        _metric("scrape-delta-2026-06-02-020000", "AR - Foo", 210),
        _metric("scrape-delta-2026-06-03-020000", "AR - Foo", 190),
    ])
    # Un run delta con 250: sano vs la mediana delta (200), aunque sería <50%
    # de la mediana full (1000). El filtro por modo debe evitar el falso positivo.
    current = {"AR - Foo": {"candidates": 250, "error": None, "skipped": None}}
    regs = sh.compute_yield_regressions(metrics, "scrape-delta-2026-06-04-020000", current, "delta")
    assert regs == []

    # El mismo 250 comparado contra el modo full (mediana 1000) SÍ es regresión.
    regs_full = sh.compute_yield_regressions(metrics, "scrape-full-2026-05-04-020000", current, "full")
    assert len(regs_full) == 1
    assert regs_full[0]["median"] == 1000


def test_baseline_excludes_current_run_from_history(tmp_path):
    """Si el run actual ya está en metrics.jsonl, no debe entrar en la mediana."""
    metrics = tmp_path / "metrics.jsonl"
    cur_run = "scrape-delta-2026-06-04-020000"
    _write_metrics(metrics, [
        _metric("scrape-delta-2026-06-01-020000", "AR - Foo", 200),
        _metric("scrape-delta-2026-06-02-020000", "AR - Foo", 210),
        _metric("scrape-delta-2026-06-03-020000", "AR - Foo", 190),
        # El run actual ya appendeado con su valor colapsado (0). No debe bajar la mediana.
        _metric(cur_run, "AR - Foo", 0),
    ])
    current = {"AR - Foo": {"candidates": 0, "error": None, "skipped": None}}
    regs = sh.compute_yield_regressions(metrics, cur_run, current, "delta")
    assert len(regs) == 1
    assert regs[0]["median"] == 200  # 0 del run actual excluido


def test_baseline_zero_median_no_alert(tmp_path):
    """Sin baseline positivo (mediana 0) no hay regresión que medir."""
    metrics = tmp_path / "metrics.jsonl"
    _write_metrics(metrics, [
        _metric("scrape-delta-2026-06-01-020000", "AR - Foo", 0),
        _metric("scrape-delta-2026-06-02-020000", "AR - Foo", 0),
        _metric("scrape-delta-2026-06-03-020000", "AR - Foo", 0),
    ])
    current = {"AR - Foo": {"candidates": 0, "error": None, "skipped": None}}
    regs = sh.compute_yield_regressions(metrics, "scrape-delta-2026-06-04-020000", current, "delta")
    assert regs == []


def test_baseline_no_metrics_file(tmp_path):
    """Sin archivo de métricas, no explota: devuelve []."""
    regs = sh.compute_yield_regressions(
        tmp_path / "missing.jsonl", "scrape-delta-2026-06-04-020000",
        {"AR - Foo": {"candidates": 0, "error": None, "skipped": None}}, "delta")
    assert regs == []


# --------------------------------------------------------------------------- #
# recencia: anotación de la fecha del último síntoma en el markdown
# --------------------------------------------------------------------------- #

def test_recency_date_annotation_in_markdown(tmp_path):
    """El markdown anota (last: fecha) con el run MÁS RECIENTE del síntoma."""
    old = _make_run(tmp_path, "scrape-delta-2026-05-01-020000", {}, errors={"ES - Boom": "HTTP 403 viejo"})
    new = _make_run(tmp_path, "scrape-delta-2026-06-10-020000", {}, errors={"ES - Boom": "HTTP 403 nuevo"})
    # aggregate_health espera runs most-recent-first
    parsed = [(new, sh.parse_run_log(new)), (old, sh.parse_run_log(old))]
    agg = sh.aggregate_health(parsed, [])
    md = sh.render_markdown([new, old], agg)
    assert "(last: 2026-06-10)" in md


# --------------------------------------------------------------------------- #
# staleness_report
# --------------------------------------------------------------------------- #

def _state_entry(source: str, last_seen: str, url: str) -> dict:
    return {"source": source, "last_seen_at": last_seen, "url": url}


def test_staleness_counts_stale_urls_per_source(tmp_path):
    state = {
        # Fuente A: 1 reciente + 1 rancia (respecto de ref 2026-06-01, days=30)
        "url:https://a.com/1": _state_entry("A", "2026-05-30T00:00:00+00:00", "https://a.com/1"),
        "url:https://a.com/2": _state_entry("A", "2026-03-01T00:00:00+00:00", "https://a.com/2"),
        # Fuente B: todas recientes
        "url:https://b.com/1": _state_entry("B", "2026-05-28T00:00:00+00:00", "https://b.com/1"),
    }
    ref = st.parse_iso("2026-06-01T00:00:00+00:00")
    agg = st.compute_staleness(state, ref, days=30)
    assert agg["A"]["total"] == 2
    assert agg["A"]["stale"] == 1
    assert agg["A"]["stale_urls"][0][0] == "https://a.com/2"
    assert agg["B"]["stale"] == 0


def test_staleness_missing_ts_counted_as_no_ts(tmp_path):
    state = {
        "url:https://a.com/1": {"source": "A", "url": "https://a.com/1"},  # sin last_seen_at
        "url:https://a.com/2": _state_entry("A", "2026-01-01T00:00:00+00:00", "https://a.com/2"),
    }
    ref = st.parse_iso("2026-06-01T00:00:00+00:00")
    agg = st.compute_staleness(state, ref, days=30)
    assert agg["A"]["no_ts"] == 1
    assert agg["A"]["stale"] == 1  # sólo la que tiene ts vieja
    assert agg["A"]["total"] == 2


def test_staleness_reference_corpus_is_latest_last_seen(tmp_path):
    state = {
        "url:https://a.com/1": _state_entry("A", "2026-05-30T00:00:00+00:00", "https://a.com/1"),
        "url:https://a.com/2": _state_entry("A", "2026-06-12T00:00:00+00:00", "https://a.com/2"),
    }
    ref = st.reference_timestamp(state, "corpus", "")
    assert ref == st.parse_iso("2026-06-12T00:00:00+00:00")


def test_staleness_now_iso_override(tmp_path):
    state = {"url:https://a.com/1": _state_entry("A", "2026-05-30T00:00:00+00:00", "https://a.com/1")}
    ref = st.reference_timestamp(state, "corpus", "2026-09-01T00:00:00+00:00")
    assert ref == st.parse_iso("2026-09-01T00:00:00+00:00")


def test_staleness_naive_iso_assumed_utc(tmp_path):
    dt = st.parse_iso("2026-06-01T00:00:00")  # sin tz
    assert dt is not None and dt.tzinfo is not None


def test_staleness_report_main_exits_zero(tmp_path, monkeypatch, capsys):
    state = {
        "url:https://a.com/1": _state_entry("A", "2026-01-01T00:00:00+00:00", "https://a.com/1"),
        "url:https://a.com/2": _state_entry("A", "2026-05-30T00:00:00+00:00", "https://a.com/2"),
    }
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr("sys.argv", [
        "staleness_report.py", "--state", str(state_path),
        "--sources", str(tmp_path / "no-sources.yml"),  # inexistente → lookup vacío, sin romper
        "--days", "30", "--now-iso", "2026-06-01T00:00:00+00:00",
    ])
    rc = st.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "Staleness Report" in out
    assert "URLs rancias:" in out


def test_staleness_report_empty_state_exits_zero(tmp_path, monkeypatch, capsys):
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["staleness_report.py", "--state", str(empty)])
    assert st.main() == 0


# --------------------------------------------------------------------------- #
# #1: _SKIP_RE captura categorías con guion (no-links, js-shell)
# --------------------------------------------------------------------------- #

def test_skip_re_captures_hyphenated_category():
    """Línea real: logs/scrape-delta-2026-07-07-135134/01-scrape.log:26.
    `\\w+` no capturaba el guion de `no-links`/`js-shell` (sólo `empty`/`js`
    matcheaban) — ListadoManga (la fuente más importante) quedaba invisible."""
    line = (
        "[SKIP-no-links] ListadoManga (colecciones): Sin enlaces con texto "
        "significativo (1 encontrados). JS o página vacía."
    )
    m = sh._SKIP_RE.match(line)
    assert m is not None
    assert m.group(1) == "no-links"
    assert m.group(2) == "ListadoManga (colecciones)"


def test_parse_run_log_records_hyphenated_skip(tmp_path):
    run_dir = tmp_path / "scrape-delta-2026-07-07-135134"
    run_dir.mkdir()
    (run_dir / "01-scrape.log").write_text(
        "[SKIP-no-links] ListadoManga (colecciones): Sin enlaces con texto "
        "significativo (1 encontrados). JS o página vacía.\n",
        encoding="utf-8",
    )
    stats = sh.parse_run_log(run_dir)
    assert stats["ListadoManga (colecciones)"]["skipped"].startswith("no-links:")


def test_skip_re_still_captures_non_hyphenated_categories():
    """No regresión: empty/js (sin guion) siguen andando."""
    m = sh._SKIP_RE.match("[SKIP-js] ES - Kibook Novedades: requiere JavaScript")
    assert m is not None
    assert m.group(1) == "js"


# --------------------------------------------------------------------------- #
# #2: [CHALLENGE_DETECTED] parsea como categoría propia (broken_challenge)
# --------------------------------------------------------------------------- #

def test_challenge_detected_parsed_not_error_not_candidates(tmp_path):
    """El path de challenge (manga_watch.py:9063) NO imprime [ERROR] ni la
    línea de candidatos — sólo esta línea. Sin parsearla, stats quedaba
    todo-None → 'healthy' pese a estar bloqueada (gotcha #107)."""
    run_dir = tmp_path / "scrape-delta-2026-07-07-135134"
    run_dir.mkdir()
    (run_dir / "01-scrape.log").write_text(
        "[CHALLENGE_DETECTED] source=ES - Foo Tienda type=cloudflare\n",
        encoding="utf-8",
    )
    stats = sh.parse_run_log(run_dir)
    assert stats["ES - Foo Tienda"]["challenge"] == "cloudflare"
    assert stats["ES - Foo Tienda"]["error"] is None
    assert stats["ES - Foo Tienda"]["candidates"] is None


def test_challenge_detected_classifies_broken_challenge(tmp_path):
    run_dir = tmp_path / "scrape-delta-2026-07-07-135134"
    run_dir.mkdir()
    (run_dir / "01-scrape.log").write_text(
        "[CHALLENGE_DETECTED] source=ES - Foo Tienda type=cloudflare\n",
        encoding="utf-8",
    )
    stats = sh.parse_run_log(run_dir)
    agg = sh.aggregate_health([(run_dir, stats)], [])
    assert sh.classify(agg["ES - Foo Tienda"]) == "broken_challenge"


# --------------------------------------------------------------------------- #
# #3: _ERROR_RE no trunca nombres de search-template con ':' adentro
# --------------------------------------------------------------------------- #

_DHD_ERROR_LINE = (
    "[ERROR] US - Dark Horse Direct (search) [search: limited edition]: "
    "HTTP error 429 Client Error: Too Many Requests for url: "
    "https://www.darkhorsedirect.com/search?page=5&q=limited+edition"
)  # línea real: logs/scrape-delta-2026-07-07-135134/01-scrape.log:246


def test_error_re_search_template_colon_in_name():
    parsed = sh._parse_error_line(_DHD_ERROR_LINE)
    assert parsed is not None
    name, msg = parsed
    assert name == "US - Dark Horse Direct (search) [search: limited edition]"
    assert msg.startswith("HTTP error 429")


def test_parse_run_log_attributes_error_to_full_search_template_name(tmp_path):
    run_dir = tmp_path / "scrape-delta-2026-07-07-135134"
    run_dir.mkdir()
    (run_dir / "01-scrape.log").write_text(_DHD_ERROR_LINE + "\n", encoding="utf-8")
    stats = sh.parse_run_log(run_dir)
    assert "US - Dark Horse Direct (search) [search: limited edition]" in stats
    # El bug viejo cortaba el nombre en el ':' de "[search:" y dejaba esta
    # clave fantasma en su lugar.
    assert "US - Dark Horse Direct (search) [search" not in stats


def test_error_re_falls_back_for_unknown_message_prefix():
    """Un mensaje no catalogado (línea nueva no vista) cae al split naive en
    vez de perder el error por completo."""
    line = "[ERROR] ES - Foo: algo nuevo que no está en la lista de prefijos"
    parsed = sh._parse_error_line(line)
    assert parsed == ("ES - Foo", "algo nuevo que no está en la lista de prefijos")


# --------------------------------------------------------------------------- #
# #4: unseen se siembra con fuentes enabled del YAML + wikis conocidos
# --------------------------------------------------------------------------- #

def test_unseen_seeded_from_enabled_yaml_sources(tmp_path):
    """Antes: runs_seen sólo se poblaba desde los logs → la rama 'unseen' de
    classify() era código muerto. Ahora una fuente enabled que nunca aparece
    en el batch analizado clasifica 'unseen' en vez de faltar en silencio."""
    run = _make_run(tmp_path, "scrape-delta-2026-06-04-020000", {"AR - Foo": 200})
    stats = sh.parse_run_log(run)
    yaml_sources = [
        mw.Source(name="AR - Foo", url="https://a.example", enabled=True, kind="html"),
        mw.Source(name="ES - NeverRan", url="https://b.example", enabled=True, kind="html"),
        mw.Source(name="ES - Disabled", url="https://c.example", enabled=False, kind="html"),
    ]
    agg = sh.aggregate_health([(run, stats)], yaml_sources)
    assert sh.classify(agg["ES - NeverRan"]) == "unseen"
    assert agg["ES - NeverRan"]["runs_seen"] == 0
    # Fuentes disabled no se siembran (no se espera que corran).
    assert "ES - Disabled" not in agg
    # La que SÍ corrió sigue healthy, no rota por el sembrado.
    assert sh.classify(agg["AR - Foo"]) == "healthy"


def test_unseen_seeded_from_wiki_registry(tmp_path):
    run = _make_run(tmp_path, "scrape-delta-2026-06-04-020000", {"AR - Foo": 200})
    stats = sh.parse_run_log(run)
    agg = sh.aggregate_health([(run, stats)], [])
    assert sh.classify(agg["wiki:whakoom"]) == "unseen"
    assert agg["wiki:whakoom"]["kind"] == "wiki"


def test_parse_run_log_wiki_format(tmp_path):
    """Los 26 wikis van por _run_wiki_bootstrap (manga_watch.py:8469,8647) —
    un log por wiki con header + resumen uniformes. Fixture real (recortado)
    de logs/scrape-delta-2026-07-07-135134/02b-manga-sanctuary.log."""
    run_dir = tmp_path / "scrape-delta-2026-07-07-135134"
    run_dir.mkdir()
    (run_dir / "02b-manga-sanctuary.log").write_text(
        "[BOOTSTRAP-WIKI] fuente: manga-sanctuary\n"
        "                rango: 2024-01 → 2026-07\n"
        "                min-score: 20\n"
        "\n"
        "[1/31] Manga-Sanctuary 2024-01\n"
        "    286 items totales, 34 con score >= 20\n"
        "[FLUSH-WIKI] 34 items escritos incrementalmente\n"
        "\n"
        "[BOOTSTRAP-WIKI] 719 candidates con score>=20 sobre 31 meses\n"
        "[GATE] 10/719 candidatos descartados por no ser edición coleccionable\n"
        "[DEDUP] 2 duplicados colapsados por ISBN coincidente\n"
        "[IMAGES] 126 portadas al espejo local data/images/ (0 fallidas)\n"
        "\n"
        "[RESUMEN BOOTSTRAP-WIKI]\n"
        "  candidates totales: 719\n"
        "  reportables (new/changed): 134\n"
        "  ya conocidos (seen): 0\n"
        "  jsonl: data/items.jsonl\n"
        "  state: data/state.json\n"
        "  reporte: reports/2026-07-07.md\n",
        encoding="utf-8",
    )
    stats = sh.parse_run_log(run_dir)
    assert stats["wiki:manga-sanctuary"]["candidates"] == 719

    agg = sh.aggregate_health([(run_dir, stats)], [])
    assert agg["wiki:manga-sanctuary"]["kind"] == "wiki"
    assert sh.classify(agg["wiki:manga-sanctuary"]) == "healthy"


# --------------------------------------------------------------------------- #
# #5: compute_yield_regressions saltea runs con error al armar la mediana
# --------------------------------------------------------------------------- #

def test_baseline_error_runs_excluded_from_median(tmp_path):
    """Sin el filtro: 4 runs con error (candidates=0 persistido por
    append_metrics) tumban la mediana a 0 y `if median <= 0: continue` deja la
    detección de regresión muda PARA SIEMPRE en esa fuente — justo la que más
    lo necesita (fuente flaky tipo Dark Horse 429). Con el filtro, sólo los 3
    runs sanos entran a la mediana y una caída real (a 0) sí se reporta."""
    metrics = tmp_path / "metrics.jsonl"
    records = [
        _metric("scrape-delta-2026-06-01-020000", "US - Dark Horse Direct", 200),
        _metric("scrape-delta-2026-06-02-020000", "US - Dark Horse Direct", 210),
        _metric("scrape-delta-2026-06-03-020000", "US - Dark Horse Direct", 190),
    ]
    for day in ("04", "05", "06", "07"):
        rec = _metric(f"scrape-delta-2026-06-{day}-020000", "US - Dark Horse Direct", 0)
        rec["errors"] = 1
        records.append(rec)
    _write_metrics(metrics, records)
    current = {"US - Dark Horse Direct": {"candidates": 0, "error": None, "skipped": None, "challenge": None}}
    regs = sh.compute_yield_regressions(
        metrics, "scrape-delta-2026-06-08-020000", current, "delta")
    assert len(regs) == 1
    assert regs[0]["median"] == 200
    assert regs[0]["zero"] is True


# --------------------------------------------------------------------------- #
# #10: append_metrics guard de '\n' final + collect_run_dirs por nombre
# --------------------------------------------------------------------------- #

def test_append_metrics_newline_guard(tmp_path):
    """Si metrics.jsonl existente NO termina en '\\n' (escritura externa
    interrumpida, edición manual), un open(...,'a') directo fusiona la última
    línea vieja con la primera nueva, corrompiendo ambos registros JSON."""
    metrics = tmp_path / "metrics.jsonl"
    metrics.write_text(
        json.dumps({"run": "old", "source": "X", "candidates": 1}, ensure_ascii=False),
        encoding="utf-8",
    )  # sin '\n' final, a propósito
    run = _make_run(tmp_path, "scrape-delta-2026-06-04-020000", {"AR - Foo": 200})
    sh.append_metrics(metrics, run, sh.parse_run_log(run))
    lines = metrics.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for ln in lines:
        json.loads(ln)  # cada línea debe seguir siendo JSON válido por separado


def test_collect_run_dirs_orders_by_embedded_timestamp_not_mtime(tmp_path):
    """Ordena por el timestamp EMBEBIDO EN EL NOMBRE, no por mtime — un
    restore/cp -r toca mtime sin tocar el nombre y corrompía el orden."""
    old = tmp_path / "scrape-delta-2026-06-01-020000"
    new = tmp_path / "scrape-delta-2026-06-10-020000"
    old.mkdir()
    new.mkdir()
    # Mtime invertido a propósito respecto del nombre.
    os.utime(new, (1_000_000_000, 1_000_000_000))
    os.utime(old, (2_000_000_000, 2_000_000_000))
    runs = sh.collect_run_dirs(tmp_path, last_n=10)
    assert runs[0].name == "scrape-delta-2026-06-10-020000"
