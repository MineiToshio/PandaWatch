"""Tests para scripts/standardize_audit.py — auditoría 2026-07-08 (paquete
I1-workflows-js, hallazgos F3/F6).

Cubre:
 1. F3 — `DEFAULT_BASE` vive en `data/standardize-run/` (persistente), NO en
    `/tmp/manga-standardize-run` (volátil ante reboot).
 2. F6 — `summary.json` es el CONTRATO que el workflow/skill deben leer en vez
    de parsear el reporte de texto libre de un subagente por regex. Se
    verifica su forma y sus valores tanto en la corrida normal como en el
    caso "nada pendiente".

JAMÁS toca `data/items.jsonl` real — todo corpus es sintético en `tmp_path`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import standardize_audit


def make_item(**overrides) -> dict:
    it = {
        "url": "https://example.com/x",
        "title": "Test Title",
        "title_original": "Test Title",
        "series_key": "",
        "series_display": "",
        "edition_key": "",
        "edition_display": "",
        "volume": "",
        "source": "AR - Some Store",
        "sources": [],
        "images": [],
        "signal_types": [],
        "tags": [],
        "country": "Argentina",
        "language": "Español",
        "publisher": "Some Pub",
        "product_type": "",
        "description": "",
        "isbn": "",
        "price": "",
        "score": 50,
        "status": "new",
    }
    it.update(overrides)
    return it


def write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def run_audit(base: Path, items_path: Path, monkeypatch, *, tier_by_url=None,
              extra_args=None):
    """Corre standardize_audit.main() con ITEMS aislado y tier forzado.

    `tier_by_url` — dict opcional `url -> confidence_tier`; default 3 para
    cualquier item no listado.
    """
    tier_by_url = tier_by_url or {}
    monkeypatch.setattr(standardize_audit, "ITEMS", items_path)
    monkeypatch.setattr(
        standardize_audit, "derive_series_metadata",
        lambda c: {
            "confidence_tier": tier_by_url.get(c.url, 3),
            "series_key": "audit-test-series",
            "series_display": "Audit Test Series",
            "edition_key": "audit-test-series-somepub-regular-ar",
            "edition_display": "Regular",
            "volume": "1",
        },
    )
    argv = ["standardize_audit.py", "--base", str(base)]
    if extra_args:
        argv += extra_args
    monkeypatch.setattr(sys, "argv", argv)
    return standardize_audit.main()


# ---------------------------------------------------------------------------
# F3 — run dir persistente, no /tmp
# ---------------------------------------------------------------------------


def test_default_base_is_persistent_under_data_dir():
    base = standardize_audit.DEFAULT_BASE
    assert base == standardize_audit.ROOT / "data" / "standardize-run"
    assert "/tmp" not in str(base)


# ---------------------------------------------------------------------------
# F6 — summary.json es el contrato de conteos (no regex sobre texto libre)
# ---------------------------------------------------------------------------


def test_summary_json_written_with_expected_counts(tmp_path, monkeypatch):
    items = [
        make_item(url="https://example.com/1"),
        make_item(url="https://example.com/2"),
        make_item(url="https://example.com/3"),
        # Ya estandarizado -> no pendiente, no debe contar.
        make_item(url="https://example.com/4", standardized_at="2026-01-01T00:00:00Z"),
        # Golden record aprobado -> nunca pendiente.
        make_item(url="https://example.com/5", approved_at="2026-01-01T00:00:00Z"),
    ]
    items_path = tmp_path / "items.jsonl"
    write_jsonl(items_path, items)

    base = tmp_path / "run"
    tier_by_url = {
        "https://example.com/1": 1,
        "https://example.com/2": 2,
        "https://example.com/3": 3,
    }
    rc = run_audit(base, items_path, monkeypatch, tier_by_url=tier_by_url)
    assert rc == 0

    summary_path = base / "summary.json"
    assert summary_path.exists(), "summary.json debe escribirse en el run dir"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary == {
        "total": 5,
        "pending": 3,
        "tier1": 1,
        "tier2": 1,
        "tier3": 1,
        "exhausted": 0,
    }

    # tier{1,2,3}.json también deben existir (contrato previo, sin romper).
    for t in (1, 2, 3):
        assert (base / f"tier{t}.json").exists()


def test_summary_json_written_when_nothing_pending(tmp_path, monkeypatch):
    items = [
        make_item(url="https://example.com/1", standardized_at="2026-01-01T00:00:00Z"),
        make_item(url="https://example.com/2", approved_at="2026-01-01T00:00:00Z"),
    ]
    items_path = tmp_path / "items.jsonl"
    write_jsonl(items_path, items)

    base = tmp_path / "run"
    rc = run_audit(base, items_path, monkeypatch)
    assert rc == 0

    summary = json.loads((base / "summary.json").read_text(encoding="utf-8"))
    assert summary == {
        "total": 2,
        "pending": 0,
        "tier1": 0,
        "tier2": 0,
        "tier3": 0,
        "exhausted": 0,
    }


def test_summary_json_respects_limit(tmp_path, monkeypatch):
    items = [make_item(url=f"https://example.com/{i}") for i in range(10)]
    items_path = tmp_path / "items.jsonl"
    write_jsonl(items_path, items)

    base = tmp_path / "run"
    rc = run_audit(base, items_path, monkeypatch, extra_args=["--limit", "4"])
    assert rc == 0

    summary = json.loads((base / "summary.json").read_text(encoding="utf-8"))
    assert summary["total"] == 10
    assert summary["pending"] == 4
    assert summary["tier1"] + summary["tier2"] + summary["tier3"] == 4
