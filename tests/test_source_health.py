"""Tests para scripts/audit/source_health.py y staleness_report.py.

Cubren las piezas nuevas de detección de regresiones de ingestión:
- metrics.jsonl: append + idempotencia por (run, source).
- baseline: warm-up (<3 runs) no alerta; caída <50% sí; filtrado por modo.
- inferencia de ts/modo desde el nombre del run + anotación de recencia.
- staleness_report: conteo por fuente contra un ancla temporal fija (tmp_path).
"""

from __future__ import annotations

import json
from pathlib import Path

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
