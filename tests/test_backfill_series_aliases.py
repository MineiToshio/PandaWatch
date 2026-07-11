"""Tests para scripts/retrofit/backfill_series_aliases.py.

Cubre el reemplazo del snippet embebido del skill /watch-enrich-series-aliases:
  - --only-keys remapea SOLO esas keys (scope acotado; regla anti-colapso).
  - Sin --only-keys ni --all → aborta (regla dura de memoria del proyecto).
  - --all sin --yes-i-know-collateral → aborta.
  - Guard approved (con y sin --include-approved).
  - cluster_key re-derivado + consolidación DELEGADA en la fuente única cuando
    el remapeo une dos filas del mismo producto (sources[] fusionadas).
  - Idempotencia: 2ª corrida → 0 cambios, archivo byte-idéntico.
  - MANGA_WATCH_DATA_DIR respetado.
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

import series_aliases  # type: ignore
import backfill_series_aliases as bsa  # type: ignore


_YAML = """\
witch-hat-atelier:
  display: Witch Hat Atelier
  aliases:
    - atelier-des-sorciers
    - L'Atelier des Sorciers
apothecary-diaries:
  display: The Apothecary Diaries
  aliases:
    - apothicaire
"""


@pytest.fixture
def aliases_yaml(tmp_path, monkeypatch):
    """Apunta series_aliases al YAML sintético e invalida sus caches."""
    yml = tmp_path / "series_aliases.yml"
    yml.write_text(_YAML, encoding="utf-8")
    monkeypatch.setattr(series_aliases, "_ALIASES_FILE", yml)
    series_aliases._load_aliases.cache_clear()
    series_aliases._build_lookup.cache_clear()
    series_aliases._build_aggressive_lookup.cache_clear()
    yield yml
    series_aliases._load_aliases.cache_clear()
    series_aliases._build_lookup.cache_clear()
    series_aliases._build_aggressive_lookup.cache_clear()


def _item(sk, ek, url, **extra):
    it = {
        "title": extra.pop("title", f"{sk} 1"),
        "series_key": sk,
        "series_display": extra.pop("series_display", sk),
        "edition_key": ek,
        "volume": extra.pop("volume", "1"),
        "url": url,
        "sources": extra.pop("sources", [{"url": url, "name": "src"}]),
    }
    it.update(extra)
    return it


def _write(path: Path, items):
    with path.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")


def _read(path: Path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _by_url(items):
    return {it["url"]: it for it in items}


# ── --only-keys: scope acotado ──────────────────────────────────────────────

def test_only_keys_remaps_just_those_keys(tmp_path, aliases_yaml):
    items_path = tmp_path / "items.jsonl"
    _write(items_path, [
        _item("atelier-des-sorciers", "atelier-des-sorciers-regular-fr", "urlA"),
        _item("apothicaire", "apothicaire-regular-fr", "urlB"),
    ])

    rc = bsa.main(["--input", str(items_path), "--only-keys", "atelier-des-sorciers"])
    assert rc == 0

    out = _by_url(_read(items_path))
    # A (en scope) remapeado a la canónica.
    assert out["urlA"]["series_key"] == "witch-hat-atelier"
    assert out["urlA"]["series_display"] == "Witch Hat Atelier"
    assert out["urlA"]["edition_key"] == "witch-hat-atelier-regular-fr"
    # B (fuera de scope) NO se toca, aunque su alias también aplicaría.
    assert out["urlB"]["series_key"] == "apothicaire"


# ── Abortos ─────────────────────────────────────────────────────────────────

def test_aborts_without_only_keys_or_all(tmp_path, aliases_yaml):
    items_path = tmp_path / "items.jsonl"
    _write(items_path, [_item("atelier-des-sorciers", "atelier-des-sorciers-regular-fr", "urlA")])
    before = items_path.read_bytes()

    rc = bsa.main(["--input", str(items_path)])
    assert rc == 2
    # No tocó el archivo.
    assert items_path.read_bytes() == before


def test_aborts_all_without_confirmation(tmp_path, aliases_yaml):
    items_path = tmp_path / "items.jsonl"
    _write(items_path, [_item("atelier-des-sorciers", "atelier-des-sorciers-regular-fr", "urlA")])
    before = items_path.read_bytes()

    rc = bsa.main(["--input", str(items_path), "--all"])
    assert rc == 2
    assert items_path.read_bytes() == before


def test_all_with_confirmation_runs(tmp_path, aliases_yaml):
    items_path = tmp_path / "items.jsonl"
    _write(items_path, [
        _item("atelier-des-sorciers", "atelier-des-sorciers-regular-fr", "urlA"),
        _item("apothicaire", "apothicaire-regular-fr", "urlB"),
    ])
    rc = bsa.main(["--input", str(items_path), "--all", "--yes-i-know-collateral"])
    assert rc == 0
    out = _by_url(_read(items_path))
    # --all remapea TODO el corpus.
    assert out["urlA"]["series_key"] == "witch-hat-atelier"
    assert out["urlB"]["series_key"] == "apothecary-diaries"


# ── Guard approved ──────────────────────────────────────────────────────────

def test_approved_is_skipped_by_default(tmp_path, aliases_yaml):
    items_path = tmp_path / "items.jsonl"
    _write(items_path, [
        _item("atelier-des-sorciers", "atelier-des-sorciers-regular-fr", "urlA",
              approved_at="2026-07-08T00:00:00Z"),
    ])
    rc = bsa.main(["--input", str(items_path), "--only-keys", "atelier-des-sorciers"])
    assert rc == 0
    out = _by_url(_read(items_path))
    # Golden record intacto.
    assert out["urlA"]["series_key"] == "atelier-des-sorciers"


def test_approved_remapped_with_include_flag(tmp_path, aliases_yaml):
    items_path = tmp_path / "items.jsonl"
    _write(items_path, [
        _item("atelier-des-sorciers", "atelier-des-sorciers-regular-fr", "urlA",
              approved_at="2026-07-08T00:00:00Z"),
    ])
    rc = bsa.main(["--input", str(items_path), "--only-keys", "atelier-des-sorciers",
                   "--include-approved"])
    assert rc == 0
    out = _by_url(_read(items_path))
    assert out["urlA"]["series_key"] == "witch-hat-atelier"


# ── Consolidación DELEGADA en la fuente única ───────────────────────────────

def test_remap_consolidates_via_single_source(tmp_path, aliases_yaml):
    """A (no canónica) y B (ya canónica) son el MISMO producto: tras remapear A,
    su cluster_key re-derivado matchea el de B → consolidate_by_cluster (fuente
    única) las fusiona en 1 fila con sources[] unidas."""
    items_path = tmp_path / "items.jsonl"
    _write(items_path, [
        _item("atelier-des-sorciers", "atelier-des-sorciers-regular-fr", "urlA",
              sources=[{"url": "urlA", "name": "srcA"}],
              cluster_key="edition:atelier-des-sorciers-regular-fr|1"),
        _item("witch-hat-atelier", "witch-hat-atelier-regular-fr", "urlB",
              series_display="Witch Hat Atelier",
              sources=[{"url": "urlB", "name": "srcB"}],
              cluster_key="edition:witch-hat-atelier-regular-fr|1"),
    ])

    rc = bsa.main(["--input", str(items_path), "--only-keys", "atelier-des-sorciers"])
    assert rc == 0

    out = _read(items_path)
    # Las 2 filas del mismo producto colapsaron en 1.
    assert len(out) == 1
    merged = out[0]
    assert merged["series_key"] == "witch-hat-atelier"
    urls = {s["url"] for s in merged["sources"]}
    assert urls == {"urlA", "urlB"}  # sources[] fusionadas por la fuente única


# ── Re-alineación del edition_key vía fuente única ──────────────────────────

def test_stale_truncated_prefix_realigned_via_single_source(tmp_path, aliases_yaml):
    """El edition_key fue acuñado con la serie TRUNCADA ("atelier-des-sorcier",
    sin la 's' final) → NO empieza con old_sk + "-", así que el fallback por
    startswith no lo detectaría. rebuild_edition_key_prefix (fuente única)
    parsea la cola `-{pub}-{slug}-{country}` y re-arma con el series_key nuevo."""
    items_path = tmp_path / "items.jsonl"
    _write(items_path, [
        _item("atelier-des-sorciers", "atelier-des-sorcier-glenat-regular-fr", "urlA"),
    ])

    rc = bsa.main(["--input", str(items_path), "--only-keys", "atelier-des-sorciers"])
    assert rc == 0

    out = _by_url(_read(items_path))
    assert out["urlA"]["series_key"] == "witch-hat-atelier"
    # Re-alineado por la fuente única, no por startswith (que habría fallado).
    assert out["urlA"]["edition_key"] == "witch-hat-atelier-glenat-regular-fr"


def test_foreign_format_edition_key_not_corrupted(tmp_path, aliases_yaml):
    """Un edition_key con formato ajeno al canónico (no parseable por la fuente
    única Y sin el prefijo exacto old_sk + '-') NO se toca: precisión > recall."""
    items_path = tmp_path / "items.jsonl"
    _write(items_path, [
        _item("atelier-des-sorciers", "foo-bar", "urlA"),
    ])

    rc = bsa.main(["--input", str(items_path), "--only-keys", "atelier-des-sorciers"])
    assert rc == 0

    out = _by_url(_read(items_path))
    # La serie sí se remapea…
    assert out["urlA"]["series_key"] == "witch-hat-atelier"
    # …pero el edition_key ajeno queda intacto (ni rebuild ni startswith aplican).
    assert out["urlA"]["edition_key"] == "foo-bar"


# ── Idempotencia ────────────────────────────────────────────────────────────

def test_idempotent_second_run_byte_identical(tmp_path, aliases_yaml):
    items_path = tmp_path / "items.jsonl"
    _write(items_path, [
        _item("atelier-des-sorciers", "atelier-des-sorciers-regular-fr", "urlA"),
        _item("apothicaire", "apothicaire-regular-fr", "urlB"),
    ])

    assert bsa.main(["--input", str(items_path), "--only-keys", "atelier-des-sorciers"]) == 0
    after_first = items_path.read_bytes()

    assert bsa.main(["--input", str(items_path), "--only-keys", "atelier-des-sorciers"]) == 0
    after_second = items_path.read_bytes()

    assert after_first == after_second


# ── Backup timestamped (no slot fijo, se conserva entre corridas) ───────────

def test_backup_is_timestamped_not_fixed_slot(tmp_path, aliases_yaml):
    """El backup pre-escritura usa timestamped=True: nombre con timestamp, NO el
    slot fijo `.pre-series-aliases-bak` que se pisaría en cada corrida."""
    items_path = tmp_path / "items.jsonl"
    _write(items_path, [
        _item("atelier-des-sorciers", "atelier-des-sorciers-regular-fr", "urlA"),
    ])

    rc = bsa.main(["--input", str(items_path), "--only-keys", "atelier-des-sorciers"])
    assert rc == 0

    backups_dir = items_path.parent / "backups" / items_path.name
    made = list(backups_dir.glob("items.jsonl.*.pre-series-aliases-bak"))
    assert made, "debería existir al menos un backup timestamped"
    # El slot FIJO (que se pisa entre corridas) NO debe usarse.
    assert not (backups_dir / "items.jsonl.pre-series-aliases-bak").exists()


# ── Summary line de convergencia ────────────────────────────────────────────

def test_summary_line_reports_change_count(tmp_path, aliases_yaml, capsys):
    """El backfill imprime `[SUMMARY] items cambiados: N` — insumo de la prueba
    de idempotencia del skill (segunda corrida debe reportar 0)."""
    items_path = tmp_path / "items.jsonl"
    _write(items_path, [
        _item("atelier-des-sorciers", "atelier-des-sorciers-regular-fr", "urlA"),
    ])

    assert bsa.main(["--input", str(items_path), "--only-keys", "atelier-des-sorciers"]) == 0
    first = capsys.readouterr().out
    assert "[SUMMARY] items cambiados: 1" in first

    # Segunda corrida: ya canónica → 0 cambios (convergencia).
    assert bsa.main(["--input", str(items_path), "--only-keys", "atelier-des-sorciers"]) == 0
    second = capsys.readouterr().out
    assert "[SUMMARY] items cambiados: 0" in second


# ── MANGA_WATCH_DATA_DIR ────────────────────────────────────────────────────

def test_respects_data_dir_env(tmp_path, aliases_yaml, monkeypatch):
    data_dir = tmp_path / "datadir"
    data_dir.mkdir()
    items_path = data_dir / "items.jsonl"
    _write(items_path, [_item("atelier-des-sorciers", "atelier-des-sorciers-regular-fr", "urlA")])
    monkeypatch.setenv("MANGA_WATCH_DATA_DIR", str(data_dir))

    # Sin --input: debe resolver items.jsonl vía la env var.
    rc = bsa.main(["--only-keys", "atelier-des-sorciers"])
    assert rc == 0
    out = _by_url(_read(items_path))
    assert out["urlA"]["series_key"] == "witch-hat-atelier"
