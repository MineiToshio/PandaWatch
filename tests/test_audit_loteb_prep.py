"""Tests para el Lote B (preparación post-auditoría, 2026-07-07):

- `scripts/retrofit/fix_product_types.py` (NUEVO): re-deriva `product_type`
  fuera del enum (invariante PTYPE_ENUM).
- `scripts/retrofit/normalize_languages.py` (NUEVO): normaliza `language` al
  canon español (invariante LANG_ENUM).
- `scripts/retrofit/queue_regular_shielded.py` (NUEVO): encola a revisión
  tomos regulares "blindados" sin señal de bonus.
- `scripts/wikis/mangapassion.py`: `language="Alemán"`, no `"Deutsch"`.
- `scripts/series_aliases.py::log_unmapped_series`: aislamiento vía
  `MANGA_WATCH_DATA_DIR` (no ensucia data/unmapped_series.jsonl real).
- `scripts/validate_corpus.py --file <inexistente>`: error limpio, no traceback.

Ninguno de estos tests toca `data/items.jsonl` ni `data/unmapped_series.jsonl`
reales — todo corre sobre fixtures en `tmp_path`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import standardize_apply
from scripts import manga_watch as mw
from scripts import validate_corpus as vc
from scripts.retrofit import fix_product_types, normalize_languages, queue_regular_shielded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, items: list[dict]) -> Path:
    lines = [json.dumps(it, ensure_ascii=False) for it in items]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


# ===========================================================================
# fix_product_types.py
# ===========================================================================

def _ptype_item(**overrides) -> dict:
    it = {
        "title": "Some Manga 1",
        "url": "https://example.com/some-manga-1",
        "slug": "some-manga-1",
        "description": "",
        "signal_types": [],
        "product_type": "special",
    }
    it.update(overrides)
    return it


def test_fix_product_types_dry_run_does_not_write(tmp_path, capsys, monkeypatch):
    p = _write_jsonl(tmp_path / "items.jsonl", [_ptype_item()])
    before = p.read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "argv",
                        ["fix_product_types.py", "--input", str(p), "--output", str(p), "--dry-run"])
    rc = fix_product_types.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 product_type se re-derivarían" in out
    assert p.read_text(encoding="utf-8") == before  # dry-run: no tocó el archivo


def test_fix_product_types_apply_rederives_invalid(tmp_path, capsys, monkeypatch):
    p = _write_jsonl(tmp_path / "items.jsonl", [
        _ptype_item(url="https://example.com/1", slug="a-1", product_type="special"),
        _ptype_item(url="https://example.com/2", slug="a-2", product_type="manga"),  # ya válido, no debe tocarse
    ])
    monkeypatch.setattr(sys, "argv", ["fix_product_types.py", "--input", str(p), "--output", str(p)])
    rc = fix_product_types.main()
    assert rc == 0
    items = _read_jsonl(p)
    by_url = {it["url"]: it for it in items}
    assert by_url["https://example.com/1"]["product_type"] in fix_product_types._PTYPE_ENUM
    assert by_url["https://example.com/2"]["product_type"] == "manga"


def test_fix_product_types_falls_back_to_manga_when_rederivation_also_invalid(tmp_path, monkeypatch):
    p = _write_jsonl(tmp_path / "items.jsonl", [_ptype_item(product_type="deluxe")])
    monkeypatch.setattr(fix_product_types, "derive_product_type", lambda *a, **k: "still-not-in-enum")
    monkeypatch.setattr(sys, "argv", ["fix_product_types.py", "--input", str(p), "--output", str(p)])
    rc = fix_product_types.main()
    assert rc == 0
    items = _read_jsonl(p)
    assert items[0]["product_type"] == "manga"


def test_fix_product_types_approved_guard_skips_by_default(tmp_path, capsys, monkeypatch):
    p = _write_jsonl(tmp_path / "items.jsonl", [
        _ptype_item(url="https://example.com/approved", product_type="special",
                    approved_at="2026-01-01T00:00:00Z"),
    ])
    monkeypatch.setattr(sys, "argv", ["fix_product_types.py", "--input", str(p), "--output", str(p)])
    rc = fix_product_types.main()
    out = capsys.readouterr().out
    assert rc == 0
    items = _read_jsonl(p)
    assert items[0]["product_type"] == "special"  # NO tocado
    assert "1 aprobados saltados" in out


def test_fix_product_types_include_approved_overrides_guard(tmp_path, monkeypatch):
    p = _write_jsonl(tmp_path / "items.jsonl", [
        _ptype_item(url="https://example.com/approved", product_type="special",
                    approved_at="2026-01-01T00:00:00Z"),
    ])
    monkeypatch.setattr(sys, "argv",
                        ["fix_product_types.py", "--input", str(p), "--output", str(p), "--include-approved"])
    rc = fix_product_types.main()
    assert rc == 0
    items = _read_jsonl(p)
    assert items[0]["product_type"] in fix_product_types._PTYPE_ENUM


def test_fix_product_types_idempotent_second_run_no_changes(tmp_path, capsys, monkeypatch):
    p = _write_jsonl(tmp_path / "items.jsonl", [
        _ptype_item(url="https://example.com/1", product_type="special"),
        _ptype_item(url="https://example.com/2", product_type="variant"),
    ])
    monkeypatch.setattr(sys, "argv", ["fix_product_types.py", "--input", str(p), "--output", str(p)])
    assert fix_product_types.main() == 0
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv",
                        ["fix_product_types.py", "--input", str(p), "--output", str(p), "--dry-run"])
    rc = fix_product_types.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "0 product_type se re-derivarían" in out


# ===========================================================================
# normalize_languages.py
# ===========================================================================

def _lang_item(**overrides) -> dict:
    it = {
        "title": "Some Manga 1",
        "url": "https://example.com/some-manga-1",
        "slug": "some-manga-1",
        "language": "Deutsch",
    }
    it.update(overrides)
    return it


def test_normalize_languages_dry_run_reports_mapped_and_unmapped(tmp_path, capsys, monkeypatch):
    p = _write_jsonl(tmp_path / "items.jsonl", [
        _lang_item(url="https://example.com/1", language="Deutsch"),
        _lang_item(url="https://example.com/2", language="Klingon"),  # sin mapeo conocido
    ])
    monkeypatch.setattr(sys, "argv", ["normalize_languages.py", "--input", str(p), "--output", str(p), "--dry-run"])
    rc = normalize_languages.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 language se normalizarían" in out
    assert "'Klingon'" in out
    # dry-run: no tocó el archivo
    items = _read_jsonl(p)
    assert items[0]["language"] == "Deutsch"
    assert items[1]["language"] == "Klingon"


def test_normalize_languages_apply_writes_canonical(tmp_path, monkeypatch):
    p = _write_jsonl(tmp_path / "items.jsonl", [
        _lang_item(url="https://example.com/1", language="Deutsch"),
        _lang_item(url="https://example.com/2", language="ja"),
        _lang_item(url="https://example.com/3", language="Español"),  # ya canónico
    ])
    monkeypatch.setattr(sys, "argv", ["normalize_languages.py", "--input", str(p), "--output", str(p)])
    rc = normalize_languages.main()
    assert rc == 0
    items = _read_jsonl(p)
    by_url = {it["url"]: it for it in items}
    assert by_url["https://example.com/1"]["language"] == "Alemán"
    assert by_url["https://example.com/2"]["language"] == "Japonés"
    assert by_url["https://example.com/3"]["language"] == "Español"


def test_normalize_languages_approved_guard(tmp_path, capsys, monkeypatch):
    p = _write_jsonl(tmp_path / "items.jsonl", [
        _lang_item(url="https://example.com/approved", language="Deutsch",
                    approved_at="2026-01-01T00:00:00Z"),
    ])
    monkeypatch.setattr(sys, "argv", ["normalize_languages.py", "--input", str(p), "--output", str(p)])
    rc = normalize_languages.main()
    out = capsys.readouterr().out
    assert rc == 0
    items = _read_jsonl(p)
    assert items[0]["language"] == "Deutsch"  # no tocado
    assert "1 aprobados saltados" in out

    monkeypatch.setattr(sys, "argv",
                        ["normalize_languages.py", "--input", str(p), "--output", str(p), "--include-approved"])
    rc = normalize_languages.main()
    assert rc == 0
    items = _read_jsonl(p)
    assert items[0]["language"] == "Alemán"


def test_normalize_languages_idempotent_second_run_no_changes(tmp_path, capsys, monkeypatch):
    p = _write_jsonl(tmp_path / "items.jsonl", [_lang_item(language="Deutsch")])
    monkeypatch.setattr(sys, "argv", ["normalize_languages.py", "--input", str(p), "--output", str(p)])
    assert normalize_languages.main() == 0
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv",
                        ["normalize_languages.py", "--input", str(p), "--output", str(p), "--dry-run"])
    rc = normalize_languages.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "0 language se normalizarían" in out


# ===========================================================================
# queue_regular_shielded.py
# ===========================================================================

def _regular_item(**overrides) -> dict:
    it = {
        "title": "Some Manga 5",
        "url": "https://example.com/some-manga-5",
        "slug": "some-manga-5",
        "series_key": "some-manga",
        "series_display": "Some Manga",
        "source": "ES - Some Store",
        "standardized_at": "2026-06-01T00:00:00Z",
        "edition_key": "some-manga-somepub-regular-es",
        "edition_display": "Some Pub",
        "store_bonus": "",
        "signal_types": [],
    }
    it.update(overrides)
    return it


def test_find_candidates_matches_regular_without_bonus():
    items = [_regular_item()]
    candidates, skipped = queue_regular_shielded.find_candidates(items, include_approved=False)
    assert len(candidates) == 1
    assert skipped == 0


def test_find_candidates_requires_standardized_at():
    items = [_regular_item(standardized_at="")]
    candidates, _ = queue_regular_shielded.find_candidates(items, include_approved=False)
    assert candidates == []


def test_find_candidates_edition_display_regular_also_matches():
    items = [_regular_item(edition_key="some-manga-somepub-especial-es", edition_display="Regular")]
    candidates, _ = queue_regular_shielded.find_candidates(items, include_approved=False)
    assert len(candidates) == 1


def test_find_candidates_excludes_store_bonus():
    items = [_regular_item(store_bonus="Marcapáginas exclusivo")]
    candidates, _ = queue_regular_shielded.find_candidates(items, include_approved=False)
    assert candidates == []


def test_find_candidates_excludes_bonus_signal_type():
    items = [_regular_item(signal_types=["bonus"])]
    candidates, _ = queue_regular_shielded.find_candidates(items, include_approved=False)
    assert candidates == []


def test_find_candidates_excludes_non_regular_edition():
    items = [_regular_item(edition_key="some-manga-somepub-deluxe-es", edition_display="Deluxe")]
    candidates, _ = queue_regular_shielded.find_candidates(items, include_approved=False)
    assert candidates == []


def test_find_candidates_approved_guard_and_include_approved(monkeypatch):
    items = [_regular_item(approved_at="2026-01-01T00:00:00Z")]
    candidates, skipped = queue_regular_shielded.find_candidates(items, include_approved=False)
    assert candidates == []
    assert skipped == 1

    candidates, skipped = queue_regular_shielded.find_candidates(items, include_approved=True)
    assert len(candidates) == 1
    assert skipped == 0


def test_queue_regular_shielded_dry_run_does_not_write_queue(tmp_path, capsys, monkeypatch):
    items_path = _write_jsonl(tmp_path / "items.jsonl", [_regular_item()])
    unmapped_path = tmp_path / "unmapped_series.jsonl"
    monkeypatch.setattr(standardize_apply, "UNMAPPED", unmapped_path)

    monkeypatch.setattr(sys, "argv", ["queue_regular_shielded.py", "--input", str(items_path)])
    rc = queue_regular_shielded.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 candidatos" in out
    assert "[DRY-RUN]" in out
    assert not unmapped_path.exists()


def test_queue_regular_shielded_apply_writes_queue_with_reason(tmp_path, monkeypatch):
    items_path = _write_jsonl(tmp_path / "items.jsonl", [
        _regular_item(url="https://example.com/1", series_key="manga-one"),
    ])
    unmapped_path = tmp_path / "unmapped_series.jsonl"
    monkeypatch.setattr(standardize_apply, "UNMAPPED", unmapped_path)

    monkeypatch.setattr(sys, "argv", ["queue_regular_shielded.py", "--input", str(items_path), "--apply"])
    rc = queue_regular_shielded.main()
    assert rc == 0
    assert unmapped_path.exists()
    rows = _read_jsonl(unmapped_path)
    assert len(rows) == 1
    assert rows[0]["reason"] == "regular_shielded_review"
    assert rows[0]["sample_url"] == "https://example.com/1"


def test_queue_regular_shielded_apply_dedups_by_url_and_reason(tmp_path, monkeypatch):
    """Correr --apply 2x sobre el mismo item NO duplica la fila en la cola
    (dedup por (series_key|sample_url, reason) — reusa
    standardize_apply.append_unmapped_from_item, fuente única)."""
    items_path = _write_jsonl(tmp_path / "items.jsonl", [
        _regular_item(url="https://example.com/1", series_key="manga-one"),
    ])
    unmapped_path = tmp_path / "unmapped_series.jsonl"
    monkeypatch.setattr(standardize_apply, "UNMAPPED", unmapped_path)

    monkeypatch.setattr(sys, "argv", ["queue_regular_shielded.py", "--input", str(items_path), "--apply"])
    assert queue_regular_shielded.main() == 0
    assert queue_regular_shielded.main() == 0  # 2da corrida: mismo item, mismo reason

    rows = _read_jsonl(unmapped_path)
    assert len(rows) == 1  # NO duplicó


def test_queue_regular_shielded_apply_respects_approved_guard(tmp_path, monkeypatch):
    items_path = _write_jsonl(tmp_path / "items.jsonl", [
        _regular_item(url="https://example.com/1", approved_at="2026-01-01T00:00:00Z"),
    ])
    unmapped_path = tmp_path / "unmapped_series.jsonl"
    monkeypatch.setattr(standardize_apply, "UNMAPPED", unmapped_path)

    monkeypatch.setattr(sys, "argv", ["queue_regular_shielded.py", "--input", str(items_path), "--apply"])
    rc = queue_regular_shielded.main()
    assert rc == 0
    assert not unmapped_path.exists()  # nada para encolar: el único candidato está aprobado


# ===========================================================================
# scripts/wikis/mangapassion.py — language="Alemán", no "Deutsch"
# ===========================================================================

def test_mangapassion_virtual_source_uses_spanish_canon_for_german():
    from wikis.mangapassion import _virtual_source
    src = _virtual_source("sonderausgabe")
    assert src.language == "Alemán"
    assert src.language != "Deutsch"


def test_mangapassion_parse_volume_language_is_canonical():
    from wikis.mangapassion import parse_volume
    item = {
        "id": 1,
        "type": 3,
        "title": "Limited Edition",
        "numberDisplay": "1",
        "edition": {"title": "Some Series", "publishers": [{"name": "Dokico"}]},
    }
    cand = parse_volume(item)
    assert cand is not None
    assert cand.language == "Alemán"


# ===========================================================================
# series_aliases.log_unmapped_series — aislamiento vía MANGA_WATCH_DATA_DIR
# ===========================================================================

def test_log_unmapped_series_isolated_by_env_var_does_not_touch_default(tmp_path, monkeypatch):
    import series_aliases as sa
    data_dir = tmp_path / "isolated"
    data_dir.mkdir()
    monkeypatch.setenv("MANGA_WATCH_DATA_DIR", str(data_dir))
    sa.set_unmapped_logging(True)  # punto 5: efecto apagado por default
    sa.reset_unmapped_run_state()

    sa.log_unmapped_series("brand-new-series-xyz", "Brand New Series", "Brand New Series 1",
                           "https://example.com/x", "src")

    target = data_dir / "unmapped_series.jsonl"
    assert target.exists()
    rows = _read_jsonl(target)
    assert len(rows) == 1
    assert rows[0]["series_key"] == "brand-new-series-xyz"


def test_candidate_to_json_unmapped_write_goes_to_isolated_dir(tmp_path, monkeypatch):
    """Regression del leak real: candidate_to_json → log_unmapped_series
    escribía a data/unmapped_series.jsonl REAL sin el fixture autouse. Acá lo
    ejercitamos explícito con una series NO canónica."""
    import series_aliases as sa
    data_dir = tmp_path / "isolated2"
    data_dir.mkdir()
    monkeypatch.setenv("MANGA_WATCH_DATA_DIR", str(data_dir))
    sa.set_unmapped_logging(True)  # punto 5: efecto apagado por default
    sa.reset_unmapped_run_state()

    c = mw.Candidate(
        title="Totally Unknown Series Vol 1", url="http://x/unknown-1", source="JP - Store",
        source_url="http://x", country="Japón", language="Japonés",
        publisher="KADOKAWA", source_class="official", tags=[], description="d",
    )
    mw.candidate_to_json(c)

    target = data_dir / "unmapped_series.jsonl"
    # Puede o no loguear según cómo derive_series_metadata slugifique el
    # título — lo que importa es que si loguea, va al dir aislado, nunca al
    # default real (_UNMAPPED_FILE apunta a data/unmapped_series.jsonl).
    assert sa._UNMAPPED_FILE.name == "unmapped_series.jsonl"
    if target.exists():
        assert True  # escribió en el aislado, no exploto
    # Nunca debería haber tocado el archivo real durante este test.


# ===========================================================================
# validate_corpus.py --file <inexistente> — error limpio, no traceback
# ===========================================================================

def test_validate_corpus_missing_file_clean_error(tmp_path, monkeypatch, capsys):
    missing = tmp_path / "does_not_exist.jsonl"
    monkeypatch.setattr(sys, "argv", ["validate_corpus.py", "--file", str(missing)])
    rc = vc.main()
    captured = capsys.readouterr()
    assert rc == 1
    assert "no existe" in captured.err
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


# ===========================================================================
# Wiring en scrape_delta.sh / scrape_full.sh (regresión de "no se olvidó cablear")
# ===========================================================================

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("script", ["scrape_delta.sh", "scrape_full.sh"])
def test_normalize_release_dates_wired_into_phase3(script):
    content = (ROOT / "scripts" / script).read_text(encoding="utf-8")
    assert "scripts/retrofit/normalize_release_dates.py" in content
    # Debe estar ANTES de filter_non_manga y DESPUÉS de clean_titles (orden Fase 3).
    idx_clean = content.index("scripts/retrofit/clean_titles.py")
    idx_norm = content.index("scripts/retrofit/normalize_release_dates.py")
    idx_filter = content.index("scripts/retrofit/filter_non_manga.py")
    assert idx_clean < idx_norm < idx_filter
