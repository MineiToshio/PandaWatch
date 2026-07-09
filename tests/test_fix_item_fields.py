"""Tests para scripts/retrofit/fix_item_fields.py.

Reemplaza los snippets K/M embebidos del skill /watch-review-feedback
(auditoría Fable 2026-07-08, hallazgo F12). Cubre:
  - allowlist de campos: campo desconocido aborta (exit 2), sin escribir.
  - 'title' bloqueado salvo --allow-title (política de títulos, gotcha #92).
  - guard approved_at (con y sin --include-approved).
  - re-derivación de cluster_key cuando el --set toca uno de sus insumos.
  - --dry-run no escribe.
  - identificación por --url y por --slug.
  - enums conocidos (rarity/product_type) validados.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))
if str(_ROOT / "scripts" / "retrofit") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts" / "retrofit"))

import fix_item_fields as fif  # type: ignore


def _item(url="https://example.com/a", slug="test-item-1", **extra):
    it = {
        "url": url,
        "slug": slug,
        "title": extra.pop("title", "Test Item 1"),
        "series_key": extra.pop("series_key", "test-item"),
        "series_display": extra.pop("series_display", "Test Item"),
        "edition_key": extra.pop("edition_key", "test-item-pub-special"),
        "volume": extra.pop("volume", "1"),
        "country": extra.pop("country", "España"),
        "publisher": extra.pop("publisher", "Editorial X"),
    }
    it.update(extra)
    return it


def _write_items(path: Path, items: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def _read_items(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ── Allowlist ────────────────────────────────────────────────────────────────

def test_unknown_field_aborts(tmp_path):
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [_item()])
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a",
                   "--set", "totally_unknown_field=x"])
    assert rc == 2
    # No se tocó nada
    assert _read_items(items_path)[0]["title"] == "Test Item 1"


def test_title_blocked_without_allow_title(tmp_path):
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [_item()])
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a",
                   "--set", "title=Nuevo Título"])
    assert rc == 2
    assert _read_items(items_path)[0]["title"] == "Test Item 1"


def test_title_allowed_with_allow_title_flag(tmp_path):
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [_item()])
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a",
                   "--set", "title=Cleaned Title", "--allow-title"])
    assert rc == 0
    assert _read_items(items_path)[0]["title"] == "Cleaned Title"


def test_invalid_rarity_enum_aborts(tmp_path):
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [_item()])
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a",
                   "--set", "rarity=super-duper-rare"])
    assert rc == 2


def test_valid_rarity_enum_applies(tmp_path):
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [_item()])
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a",
                   "--set", "rarity=rare"])
    assert rc == 0
    assert _read_items(items_path)[0]["rarity"] == "rare"


# ── Guard approved_at ────────────────────────────────────────────────────────

def test_approved_item_skipped_by_default(tmp_path):
    items_path = tmp_path / "items.jsonl"
    it = _item()
    it["approved_at"] = "2026-01-01T00:00:00+00:00"
    _write_items(items_path, [it])
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a",
                   "--set", "series_key=other-key"])
    assert rc == 0
    assert _read_items(items_path)[0]["series_key"] == "test-item"


def test_approved_item_editable_with_include_approved(tmp_path):
    items_path = tmp_path / "items.jsonl"
    it = _item()
    it["approved_at"] = "2026-01-01T00:00:00+00:00"
    _write_items(items_path, [it])
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a",
                   "--set", "series_key=other-key", "--include-approved"])
    assert rc == 0
    assert _read_items(items_path)[0]["series_key"] == "other-key"


# ── cluster_key re-derivación ────────────────────────────────────────────────

def test_cluster_key_rederived_when_insumo_changes(tmp_path):
    items_path = tmp_path / "items.jsonl"
    it = _item(volume="1")
    it["cluster_key"] = "edition:test-item-pub-special|1"
    _write_items(items_path, [it])
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a",
                   "--set", "volume=2"])
    assert rc == 0
    updated = _read_items(items_path)[0]
    assert updated["volume"] == "2"
    assert updated["cluster_key"] == "edition:test-item-pub-special|2"


def test_cluster_key_untouched_when_non_insumo_changes(tmp_path):
    items_path = tmp_path / "items.jsonl"
    it = _item()
    it["cluster_key"] = "edition:test-item-pub-special|1"
    _write_items(items_path, [it])
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a",
                   "--set", "series_display=Other Display"])
    assert rc == 0
    updated = _read_items(items_path)[0]
    assert updated["series_display"] == "Other Display"
    assert updated["cluster_key"] == "edition:test-item-pub-special|1"


# ── --dry-run ────────────────────────────────────────────────────────────────

def test_dry_run_does_not_write(tmp_path):
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [_item()])
    before = items_path.read_bytes()
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a",
                   "--set", "series_key=other-key", "--dry-run"])
    assert rc == 0
    assert items_path.read_bytes() == before


# ── Identificación por --slug ────────────────────────────────────────────────

def test_identify_by_slug(tmp_path):
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [_item(slug="unique-slug-1")])
    rc = fif.main(["--input", str(items_path), "--slug", "unique-slug-1",
                   "--set", "series_key=renamed"])
    assert rc == 0
    assert _read_items(items_path)[0]["series_key"] == "renamed"


def test_item_not_found_errors(tmp_path):
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [_item()])
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/does-not-exist",
                   "--set", "series_key=renamed"])
    assert rc == 1


def test_no_change_when_value_already_set(tmp_path):
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [_item(series_key="test-item")])
    before = items_path.read_bytes()
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a",
                   "--set", "series_key=test-item"])
    assert rc == 0
    assert items_path.read_bytes() == before


def test_missing_url_and_slug_aborts(tmp_path):
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [_item()])
    rc = fif.main(["--input", str(items_path), "--set", "series_key=x"])
    assert rc == 2


# ── cover_url (campo sintético, categoría K) ────────────────────────────────

def test_cover_url_delegates_to_image_store(tmp_path):
    items_path = tmp_path / "items.jsonl"
    it = _item()
    it["images"] = [{"url": "https://old.example.com/cover.jpg", "local": "abc.jpg", "kind": "cover"}]
    _write_items(items_path, [it])
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a",
                   "--set", "cover_url=https://new.example.com/cover.jpg"])
    assert rc == 0
    updated = _read_items(items_path)[0]
    assert updated["images"][0]["url"] == "https://new.example.com/cover.jpg"
    # local se fuerza a "" para que mirror_images.py re-descargue
    assert updated["images"][0]["local"] == ""


def test_cover_url_no_change_when_already_current(tmp_path):
    items_path = tmp_path / "items.jsonl"
    it = _item()
    it["images"] = [{"url": "https://same.example.com/cover.jpg", "local": "abc.jpg", "kind": "cover"}]
    _write_items(items_path, [it])
    before = items_path.read_bytes()
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a",
                   "--set", "cover_url=https://same.example.com/cover.jpg"])
    assert rc == 0
    assert items_path.read_bytes() == before


def test_missing_set_aborts(tmp_path):
    items_path = tmp_path / "items.jsonl"
    _write_items(items_path, [_item()])
    rc = fif.main(["--input", str(items_path), "--url", "https://example.com/a"])
    assert rc == 2
