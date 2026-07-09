"""Tests para scripts/retrofit/apply_rarity_verdicts.py.

Reemplaza el Step 3 embebido del skill /watch-validate-rarity (auditoría
Fable 2026-07-08, hallazgo F5). Cobertura:
  - in_stock -> re-deriva (común, salvo evidencia estructural extra).
  - out_of_stock -> confirma rare / promueve a super_rare (retailer_exclusive).
  - inconclusive -> NO toca nada (ni stock_status ni rarity_verified_at).
  - guard approved_at (con y sin --include-approved).
  - falta el archivo de resultados -> error, no escribe.
  - verdict inválido en el JSON de resultados -> error, no escribe.
  - --dry-run no escribe.
  - log de auditoría (append) con las entradas aplicadas.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))
if str(_ROOT / "scripts" / "retrofit") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import apply_rarity_verdicts as arv  # type: ignore


def _item(**kwargs) -> dict:
    base = {
        "title": "Test Manga",
        "description": "",
        "signal_types": [],
        "source": "Some Store",
        "sources": [],
        "publisher": "Editorial X",
        "stock_status": "",
        "edition_key": "test-manga-x-special",
        "slug": "test-manga-x-special-1",
        "url": "https://example.com/item",
        "country": "España",
        "rarity": "rare",
    }
    base.update(kwargs)
    return base


def _write_items(path: Path, items: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def _read_items(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _write_results(path: Path, results: list[dict]) -> None:
    path.write_text(json.dumps(results), encoding="utf-8")


def _run(tmp_path, items, results, *, extra_args=None):
    items_path = tmp_path / "items.jsonl"
    results_path = tmp_path / "results.json"
    log_path = tmp_path / "log.jsonl"
    _write_items(items_path, items)
    _write_results(results_path, results)
    argv = ["--items", str(items_path), "--results", str(results_path), "--log", str(log_path)]
    argv += extra_args or []
    rc = arv.main(argv)
    return rc, items_path, log_path


def test_missing_results_file_errors(tmp_path):
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [_item()])
    rc = arv.main(["--items", str(items_path), "--results", str(tmp_path / "nope.json"),
                   "--log", str(tmp_path / "log.jsonl")])
    assert rc == 1


def test_invalid_verdict_errors_without_writing(tmp_path):
    items = [_item(signal_types=["retailer_exclusive"])]
    results = [{"group_id": "test-manga-x-special", "verdict": "definitely-maybe"}]
    rc, items_path, _ = _run(tmp_path, items, results)
    assert rc == 1
    assert _read_items(items_path)[0]["rarity"] == "rare"


def test_in_stock_rederives_to_common(tmp_path):
    items = [_item(signal_types=["retailer_exclusive"])]
    results = [{"group_id": "test-manga-x-special", "verdict": "in_stock",
                "rationale": "en stock del publisher", "evidence_url": "https://x"}]
    rc, items_path, log_path = _run(tmp_path, items, results)
    assert rc == 0
    updated = _read_items(items_path)[0]
    assert updated["stock_status"] == "in_stock"
    assert updated["rarity"] == "common"
    assert updated["rarity_verified_at"]
    log_lines = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(log_lines) == 1
    assert log_lines[0]["new"] == "common"


def test_out_of_stock_confirms_rare(tmp_path):
    items = [_item(source="Mangavariant", sources=[{"name": "Mangavariant"}])]
    results = [{"group_id": "test-manga-x-special", "verdict": "out_of_stock"}]
    rc, items_path, _ = _run(tmp_path, items, results)
    assert rc == 0
    updated = _read_items(items_path)[0]
    assert updated["stock_status"] == "out_of_stock"
    assert updated["rarity"] == "rare"
    assert updated["rarity_verified_at"]


def test_out_of_stock_promotes_retailer_exclusive_to_super_rare(tmp_path):
    items = [_item(signal_types=["retailer_exclusive"])]
    results = [{"group_id": "test-manga-x-special", "verdict": "out_of_stock"}]
    rc, items_path, _ = _run(tmp_path, items, results)
    assert rc == 0
    updated = _read_items(items_path)[0]
    assert updated["rarity"] == "super_rare"


def test_not_found_confirms_rare(tmp_path):
    items = [_item(signal_types=["retailer_exclusive"])]
    results = [{"group_id": "test-manga-x-special", "verdict": "not_found"}]
    rc, items_path, _ = _run(tmp_path, items, results)
    assert rc == 0
    updated = _read_items(items_path)[0]
    assert updated["rarity"] == "rare"
    assert updated["rarity_verified_at"]
    # not_found no es evidencia de stock -> no se toca stock_status
    assert "stock_status" not in updated or updated["stock_status"] == ""


def test_inconclusive_touches_nothing(tmp_path):
    items = [_item(signal_types=["retailer_exclusive"])]
    results = [{"group_id": "test-manga-x-special", "verdict": "inconclusive"}]
    rc, items_path, log_path = _run(tmp_path, items, results)
    assert rc == 0
    updated = _read_items(items_path)[0]
    assert updated["rarity"] == "rare"
    assert "rarity_verified_at" not in updated
    assert "stock_status" not in updated or updated["stock_status"] == ""
    assert not log_path.exists() or log_path.read_text(encoding="utf-8").strip() == ""


def test_approved_item_skipped_by_default(tmp_path):
    items = [_item(signal_types=["retailer_exclusive"], approved_at="2026-01-01T00:00:00+00:00")]
    results = [{"group_id": "test-manga-x-special", "verdict": "in_stock"}]
    rc, items_path, _ = _run(tmp_path, items, results)
    assert rc == 0
    updated = _read_items(items_path)[0]
    assert updated["rarity"] == "rare"
    assert "rarity_verified_at" not in updated


def test_approved_item_updated_with_include_approved(tmp_path):
    items = [_item(signal_types=["retailer_exclusive"], approved_at="2026-01-01T00:00:00+00:00")]
    results = [{"group_id": "test-manga-x-special", "verdict": "in_stock"}]
    rc, items_path, _ = _run(tmp_path, items, results, extra_args=["--include-approved"])
    assert rc == 0
    updated = _read_items(items_path)[0]
    assert updated["rarity"] == "common"


def test_dry_run_does_not_write(tmp_path):
    items = [_item(signal_types=["retailer_exclusive"])]
    results = [{"group_id": "test-manga-x-special", "verdict": "in_stock"}]
    items_path = tmp_path / "items.jsonl"
    results_path = tmp_path / "results.json"
    log_path = tmp_path / "log.jsonl"
    _write_items(items_path, items)
    _write_results(results_path, results)
    before = items_path.read_bytes()
    rc = arv.main(["--items", str(items_path), "--results", str(results_path),
                   "--log", str(log_path), "--dry-run"])
    assert rc == 0
    assert items_path.read_bytes() == before
    assert not log_path.exists()


def test_group_id_not_in_results_left_untouched(tmp_path):
    items = [_item(signal_types=["retailer_exclusive"])]
    results = [{"group_id": "some-other-edition", "verdict": "in_stock"}]
    rc, items_path, _ = _run(tmp_path, items, results)
    assert rc == 0
    updated = _read_items(items_path)[0]
    assert updated["rarity"] == "rare"
    assert "rarity_verified_at" not in updated


def test_item_no_longer_candidate_is_skipped(tmp_path):
    """Un item pudo dejar de ser candidato entre selección y aplicación (p.ej.
    ganó evidencia estructural). apply_rarity_verdicts re-evalúa con la misma
    rarity_uncertainty_reason y lo salta."""
    items = [_item(description="Tirada única, no se reimprimirá.")]  # evidencia estructural
    results = [{"group_id": "test-manga-x-special", "verdict": "in_stock"}]
    rc, items_path, _ = _run(tmp_path, items, results)
    assert rc == 0
    updated = _read_items(items_path)[0]
    assert updated["rarity"] == "rare"
    assert "rarity_verified_at" not in updated
