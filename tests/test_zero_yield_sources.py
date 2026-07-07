"""Tests para scripts/audit/zero_yield_sources.py.

Cubre el detector de fuentes "siempre cero" que cierra el hueco del baseline
de source_health.py (una fuente sin pasado "bueno" con que compararse):

- clasificación: sospechosa (200 sin error) / error HTTP / esperada (may_be_empty).
- fuentes con items en el corpus no aparecen en el reporte.
- agrupación de sufijos [search: <query>] por nombre base (no falsos positivos
  por-keyword).
- fuentes disabled quedan fuera del análisis.
- exit 0 / read-only aunque falten sources.yml, items.jsonl o logs/.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.audit import zero_yield_sources as zy


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _write_sources_yaml(path: Path, entries: list[dict]) -> Path:
    path.write_text(yaml.safe_dump({"sources": entries}, allow_unicode=True), encoding="utf-8")
    return path


def _write_items(path: Path, items: list[dict]) -> Path:
    lines = [json.dumps(item, ensure_ascii=False) for item in items]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def _item(source_names: list[str]) -> dict:
    """Item mínimo con `sources[]` (fuente única de agrupación multi-fuente)."""
    return {
        "title": "Item de prueba",
        "sources": [{"name": name, "url": f"https://example.com/{i}"} for i, name in enumerate(source_names)],
    }


def _make_run(logs_root: Path, name: str, sources: dict[str, int | None],
              errors: dict[str, str] | None = None,
              skips: dict[str, str] | None = None) -> Path:
    """Crea un run dir con un log en el formato ACTUAL (combined), como en
    test_source_health.py, para que collect_run_dirs/parse_run_log lo levanten.
    """
    run_dir = logs_root / name
    run_dir.mkdir(parents=True)
    lines: list[str] = []
    for src, cand in sources.items():
        if cand is not None:
            lines.append(f"    [{src}] candidatos con señales: {cand}")
    for src, msg in (errors or {}).items():
        lines.append(f"[ERROR] {src}: {msg}")
    for src, msg in (skips or {}).items():
        lines.append(f"[SKIP-js] {src}: {msg}")
    (run_dir / "01-scrape.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return run_dir


def _source(name: str, enabled: bool = True, kind: str = "html", **extra) -> dict:
    d = {
        "name": name,
        "url": f"https://example.com/{name}",
        "enabled": enabled,
        "kind": kind,
    }
    d.update(extra)
    return d


# --------------------------------------------------------------------------- #
# group_key()
# --------------------------------------------------------------------------- #

def test_group_key_strips_search_suffix():
    assert zy.group_key("MX - Panini México (search) [search: deluxe]") == "MX - Panini México (search)"


def test_group_key_no_suffix_is_identity():
    assert zy.group_key("AR - Ivrea Argentina") == "AR - Ivrea Argentina"


# --------------------------------------------------------------------------- #
# classify_group()
# --------------------------------------------------------------------------- #

def test_classify_ok_when_enough_items():
    g = zy.SourceGroup(key="X", variant_names=["X"])
    assert zy.classify_group(g, total_items=5, min_items=1, status={"status": "ran"}) == "ok"


def test_classify_suspicious_on_200_no_error():
    g = zy.SourceGroup(key="X", variant_names=["X"])
    status = {"status": "ran", "run": "r1", "detail": "16 candidatos (HTTP 200, sin error)"}
    assert zy.classify_group(g, total_items=0, min_items=1, status=status) == "suspicious"


def test_classify_known_error_on_http_error():
    g = zy.SourceGroup(key="X", variant_names=["X"])
    status = {"status": "error", "run": "r1", "detail": "X: 403 blocked"}
    assert zy.classify_group(g, total_items=0, min_items=1, status=status) == "known_error"


def test_classify_expected_when_may_be_empty_overrides_error():
    g = zy.SourceGroup(key="X", variant_names=["X"], may_be_empty=True)
    status = {"status": "error", "run": "r1", "detail": "whatever"}
    assert zy.classify_group(g, total_items=0, min_items=1, status=status) == "expected"


def test_classify_suspicious_on_no_data():
    g = zy.SourceGroup(key="X", variant_names=["X"])
    status = {"status": "no_data", "run": "", "detail": "sin entradas"}
    assert zy.classify_group(g, total_items=0, min_items=1, status=status) == "suspicious"


# --------------------------------------------------------------------------- #
# End-to-end: analyze()
# --------------------------------------------------------------------------- #

def test_zero_with_200_is_suspicious(tmp_path):
    sources_yaml = _write_sources_yaml(tmp_path / "sources.yml", [
        _source("FR - Glénat Art Books", kind="js"),
    ])
    items_path = _write_items(tmp_path / "items.jsonl", [])  # 0 items, nadie referencia la fuente
    logs_root = tmp_path / "logs"
    _make_run(logs_root, "scrape-delta-2026-07-07-000000",
              {"FR - Glénat Art Books": 16})

    reports, total_groups = zy.analyze(
        sources_yaml=sources_yaml, items_path=items_path, logs_root=logs_root,
        last_n_runs=10, min_items=1,
    )
    assert total_groups == 1
    assert len(reports) == 1
    r = reports[0]
    assert r.key == "FR - Glénat Art Books"
    assert r.classification == "suspicious"
    assert r.status["status"] == "ran"
    assert r.total_items == 0


def test_zero_with_http_error_is_known_error(tmp_path):
    sources_yaml = _write_sources_yaml(tmp_path / "sources.yml", [
        _source("ES - Misión Tokyo"),
    ])
    items_path = _write_items(tmp_path / "items.jsonl", [])
    logs_root = tmp_path / "logs"
    _make_run(logs_root, "scrape-delta-2026-07-07-000000",
              sources={}, errors={"ES - Misión Tokyo": "error inesperado Timeout"})

    reports, _ = zy.analyze(
        sources_yaml=sources_yaml, items_path=items_path, logs_root=logs_root,
        last_n_runs=10, min_items=1,
    )
    assert len(reports) == 1
    assert reports[0].classification == "known_error"
    assert reports[0].status["status"] == "error"


def test_source_with_items_does_not_appear(tmp_path):
    sources_yaml = _write_sources_yaml(tmp_path / "sources.yml", [
        _source("AR - Ivrea Argentina"),
    ])
    items_path = _write_items(tmp_path / "items.jsonl", [
        _item(["AR - Ivrea Argentina"]),
    ])
    logs_root = tmp_path / "logs"
    _make_run(logs_root, "scrape-delta-2026-07-07-000000",
              {"AR - Ivrea Argentina": 10})

    reports, total_groups = zy.analyze(
        sources_yaml=sources_yaml, items_path=items_path, logs_root=logs_root,
        last_n_runs=10, min_items=1,
    )
    assert total_groups == 1
    assert reports == []  # tiene >= min_items: no es zero-yield


def test_may_be_empty_is_expected(tmp_path):
    sources_yaml = _write_sources_yaml(tmp_path / "sources.yml", [
        _source("ES - Milky Way Próximamente", may_be_empty=True),
    ])
    items_path = _write_items(tmp_path / "items.jsonl", [])
    logs_root = tmp_path / "logs"
    _make_run(logs_root, "scrape-delta-2026-07-07-000000",
              {"ES - Milky Way Próximamente": 0})

    reports, _ = zy.analyze(
        sources_yaml=sources_yaml, items_path=items_path, logs_root=logs_root,
        last_n_runs=10, min_items=1,
    )
    assert len(reports) == 1
    assert reports[0].classification == "expected"


def test_disabled_source_is_excluded(tmp_path):
    sources_yaml = _write_sources_yaml(tmp_path / "sources.yml", [
        _source("FR - Fuente Muerta", enabled=False),
    ])
    items_path = _write_items(tmp_path / "items.jsonl", [])
    logs_root = tmp_path / "logs"

    reports, total_groups = zy.analyze(
        sources_yaml=sources_yaml, items_path=items_path, logs_root=logs_root,
        last_n_runs=10, min_items=1,
    )
    assert total_groups == 0
    assert reports == []


def test_search_suffix_grouping_no_false_positive(tmp_path):
    """Una keyword sin hits no debe marcar sospechoso al GRUPO si otra keyword
    de la misma fuente sí produjo items en el corpus."""
    sources_yaml = _write_sources_yaml(tmp_path / "sources.yml", [
        _source(
            "MX - Panini México (search)",
            search_template="https://tiendapanini.com.mx/search?q={query}",
            keywords=["deluxe", "edicion especial"],
        ),
    ])
    items_path = _write_items(tmp_path / "items.jsonl", [
        _item(["MX - Panini México (search) [search: deluxe]"]),
    ])
    logs_root = tmp_path / "logs"
    _make_run(logs_root, "scrape-delta-2026-07-07-000000", {
        "MX - Panini México (search) [search: deluxe]": 6,
        "MX - Panini México (search) [search: edicion especial]": 0,
    })

    reports, total_groups = zy.analyze(
        sources_yaml=sources_yaml, items_path=items_path, logs_root=logs_root,
        last_n_runs=10, min_items=1,
    )
    # Un solo grupo ("MX - Panini México (search)"), y como el TOTAL sumado
    # (1 item) >= min_items, no aparece como zero-yield en absoluto.
    assert total_groups == 1
    assert reports == []


def test_search_suffix_grouping_flags_whole_group_when_all_zero(tmp_path):
    sources_yaml = _write_sources_yaml(tmp_path / "sources.yml", [
        _source(
            "MX - Panini México (search)",
            search_template="https://tiendapanini.com.mx/search?q={query}",
            keywords=["deluxe", "edicion especial"],
        ),
    ])
    items_path = _write_items(tmp_path / "items.jsonl", [])  # 0 items para cualquier variante
    logs_root = tmp_path / "logs"
    _make_run(logs_root, "scrape-delta-2026-07-07-000000", {
        "MX - Panini México (search) [search: deluxe]": 0,
        "MX - Panini México (search) [search: edicion especial]": 0,
    })

    reports, total_groups = zy.analyze(
        sources_yaml=sources_yaml, items_path=items_path, logs_root=logs_root,
        last_n_runs=10, min_items=1,
    )
    assert total_groups == 1
    assert len(reports) == 1  # UNA sola entrada para el grupo, no una por keyword
    r = reports[0]
    assert r.key == "MX - Panini México (search)"
    assert len(r.variant_names) == 2
    assert r.classification == "suspicious"


def test_min_items_threshold(tmp_path):
    """Con --min-items 2, una fuente con 1 item cae como zero-yield."""
    sources_yaml = _write_sources_yaml(tmp_path / "sources.yml", [
        _source("AR - Ivrea Argentina"),
    ])
    items_path = _write_items(tmp_path / "items.jsonl", [
        _item(["AR - Ivrea Argentina"]),
    ])
    logs_root = tmp_path / "logs"
    _make_run(logs_root, "scrape-delta-2026-07-07-000000", {"AR - Ivrea Argentina": 1})

    reports_default, _ = zy.analyze(
        sources_yaml=sources_yaml, items_path=items_path, logs_root=logs_root,
        last_n_runs=10, min_items=1,
    )
    assert reports_default == []

    reports_strict, _ = zy.analyze(
        sources_yaml=sources_yaml, items_path=items_path, logs_root=logs_root,
        last_n_runs=10, min_items=2,
    )
    assert len(reports_strict) == 1


def test_no_data_when_source_absent_from_logs(tmp_path):
    sources_yaml = _write_sources_yaml(tmp_path / "sources.yml", [
        _source("IT - Nueva Fuente Nunca Corrida"),
    ])
    items_path = _write_items(tmp_path / "items.jsonl", [])
    logs_root = tmp_path / "logs"
    _make_run(logs_root, "scrape-delta-2026-07-07-000000", {"otra fuente": 5})

    reports, _ = zy.analyze(
        sources_yaml=sources_yaml, items_path=items_path, logs_root=logs_root,
        last_n_runs=10, min_items=1,
    )
    assert len(reports) == 1
    assert reports[0].status["status"] == "no_data"
    assert reports[0].classification == "suspicious"


def test_missing_files_are_handled_read_only(tmp_path):
    """Sin sources.yml/items.jsonl/logs: no explota, no escribe nada, 0 reports."""
    reports, total_groups = zy.analyze(
        sources_yaml=tmp_path / "no-existe.yml",
        items_path=tmp_path / "no-existe.jsonl",
        logs_root=tmp_path / "no-existe-logs",
        last_n_runs=10, min_items=1,
    )
    assert total_groups == 0
    assert reports == []


# --------------------------------------------------------------------------- #
# Rendering (smoke)
# --------------------------------------------------------------------------- #

def test_render_markdown_has_sections():
    g = zy.GroupReport(
        key="FR - Glénat Art Books", kind="js", variant_names=["FR - Glénat Art Books"],
        total_items=0, status={"status": "ran", "run": "r1", "detail": "16 candidatos"},
        classification="suspicious",
    )
    out = zy.render_markdown([g], total_groups=1, min_items=1)
    assert "🔴 CERO SOSPECHOSO" in out
    assert "🟡 CERO CON ERROR HTTP" in out
    assert "⚪ CERO ESPERADO" in out
    assert "Glénat Art Books" in out


def test_render_text_has_sections():
    g = zy.GroupReport(
        key="ES - Milky Way Próximamente", kind="html", variant_names=["ES - Milky Way Próximamente"],
        total_items=0, status={"status": "ran", "run": "r1", "detail": "0 candidatos"},
        classification="expected",
    )
    out = zy.render_text([g], total_groups=1, min_items=1)
    assert "CERO ESPERADO" in out
    assert "Milky Way" in out


# --------------------------------------------------------------------------- #
# CLI end-to-end (main())
# --------------------------------------------------------------------------- #

def test_main_exits_zero_even_with_missing_inputs(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["zero_yield_sources.py", "--sources-yaml", "no.yml", "--items", "no.jsonl",
         "--logs-root", "no-logs"],
    )
    rc = zy.main()
    assert rc == 0
