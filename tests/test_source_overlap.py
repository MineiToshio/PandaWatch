"""Tests para scripts/audit/source_overlap.py.

Cierra el hallazgo ES-1 (auditoría Fable 2026-07-11): el Step 2 de
`watch-evaluate-sources` le pedía al subagente "cruzar los ISBNs de la
muestra con existing_isbns" en prosa, pero el contrato JSON del Step 1 nunca
capturaba `isbn` por item muestreado — el % de overlap de la tabla final era
un número inventado por el LLM, no un cruce real contra el corpus.

Este script hace el cruce real (ISBN exacto + series_key) contra
`data/items.jsonl`, usando las MISMAS funciones canónicas que el pipeline
(`normalize_isbn`, `_slugify_kebab` de `manga_watch.py`) — nunca reimplementa
esa lógica. Es 100% de solo lectura: no escribe items.jsonl ni sources.yml.

Casos cubiertos:
- carga del corpus (ISBNs únicos normalizados, series_keys, conteo por país).
- overlap por ISBN: matched/total, clasificación 30/70, "sin_datos" si la
  muestra no trajo ningún ISBN.
- overlap por series_key: normaliza el `series_key_guess` crudo con el MISMO
  slugify que usa el pipeline antes de cruzar.
- lectura de un source-eval JSON (formato SKILL.md) vía --eval-file.
- listas manuales --isbns/--series como alternativa sin archivo.
- CLI: --help funciona, salida --json es JSON parseable, exit 0 siempre
  (informativo, nunca falla aunque falten inputs).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.audit import source_overlap as so


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _item(*, isbn: str = "", series_key: str = "", country: str = "es") -> dict:
    d: dict = {"title": "Item de prueba", "country": country}
    if isbn:
        d["isbn"] = isbn
    if series_key:
        d["series_key"] = series_key
    return d


def _write_items(path: Path, items: list[dict]) -> Path:
    lines = [json.dumps(item, ensure_ascii=False) for item in items]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


# ISBN-13 válido real (978 + checksum correcto) para no depender de que
# normalize_isbn() tolere basura — usamos valores que YA pasan su validación.
ISBN_A = "9784253000539"  # ISBN-13 válido (checksum correcto)
ISBN_B = "9781421506630"  # otro ISBN-13 válido


# --------------------------------------------------------------------------- #
# load_corpus()
# --------------------------------------------------------------------------- #

def test_load_corpus_collects_isbns_series_and_countries(tmp_path):
    items_path = _write_items(tmp_path / "items.jsonl", [
        _item(isbn=ISBN_A, series_key="one-piece", country="es"),
        _item(isbn=ISBN_B, series_key="naruto", country="fr"),
        _item(series_key="one-piece", country="es"),  # sin isbn, series repetida
    ])
    corpus = so.load_corpus(items_path)
    assert corpus.total_items == 3
    assert corpus.isbns == {ISBN_A, ISBN_B}
    assert corpus.series_keys == {"one-piece", "naruto"}
    assert corpus.country_counts["es"] == 2
    assert corpus.country_counts["fr"] == 1


def test_load_corpus_normalizes_isbn10_to_isbn13(tmp_path):
    # ISBN-10 válido conocido (Harry Potter, ampliamente citado) -> se guarda
    # normalizado a ISBN-13 por normalize_isbn(); el corpus debe reflejar esa
    # MISMA normalización para que el cruce con la muestra sea consistente.
    from scripts.manga_watch import normalize_isbn
    isbn10 = "0439708184"
    expected13 = normalize_isbn(isbn10)
    assert len(expected13) == 13
    items_path = _write_items(tmp_path / "items.jsonl", [_item(isbn=isbn10)])
    corpus = so.load_corpus(items_path)
    assert corpus.isbns == {expected13}


def test_load_corpus_missing_file_is_empty(tmp_path):
    corpus = so.load_corpus(tmp_path / "no-existe.jsonl")
    assert corpus.total_items == 0
    assert corpus.isbns == set()
    assert corpus.series_keys == set()
    assert corpus.country_counts == {}


def test_load_corpus_skips_corrupt_lines(tmp_path):
    path = tmp_path / "items.jsonl"
    path.write_text(
        json.dumps(_item(isbn=ISBN_A)) + "\n"
        "{esto no es json valido\n"
        + json.dumps(_item(isbn=ISBN_B)) + "\n",
        encoding="utf-8",
    )
    corpus = so.load_corpus(path)
    assert corpus.total_items == 2
    assert corpus.isbns == {ISBN_A, ISBN_B}


# --------------------------------------------------------------------------- #
# overlap_classification()
# --------------------------------------------------------------------------- #

def test_classification_buckets():
    assert so.overlap_classification(0.0) == "nuevo"
    assert so.overlap_classification(29.9) == "nuevo"
    assert so.overlap_classification(30.0) == "parcial"
    assert so.overlap_classification(70.0) == "parcial"
    assert so.overlap_classification(70.1) == "redundante"
    assert so.overlap_classification(100.0) == "redundante"


def test_classification_no_data_when_none():
    assert so.overlap_classification(None) == "sin_datos"


# --------------------------------------------------------------------------- #
# compute_overlap()
# --------------------------------------------------------------------------- #

def test_compute_overlap_isbn_and_series(tmp_path):
    items_path = _write_items(tmp_path / "items.jsonl", [
        _item(isbn=ISBN_A, series_key="one-piece", country="es"),
        _item(isbn=ISBN_B, series_key="naruto", country="fr"),
    ])
    corpus = so.load_corpus(items_path)

    result = so.compute_overlap(
        corpus,
        sample_isbns_raw=[ISBN_A, "9999999999999-no-matchea"],
        sample_series_raw=["One Piece", "Bleach"],  # 1 de 2 matchea (slugified)
    )
    assert result["isbn_overlap"]["sample_total"] == 2
    assert result["isbn_overlap"]["matched"] == 1
    assert result["isbn_overlap"]["pct"] == 50.0
    assert result["isbn_overlap"]["classification"] == "parcial"

    assert result["series_overlap"]["sample_total"] == 2
    assert result["series_overlap"]["matched"] == 1
    assert result["series_overlap"]["pct"] == 50.0


def test_compute_overlap_no_isbns_in_sample_is_sin_datos(tmp_path):
    items_path = _write_items(tmp_path / "items.jsonl", [_item(isbn=ISBN_A)])
    corpus = so.load_corpus(items_path)

    result = so.compute_overlap(corpus, sample_isbns_raw=[], sample_series_raw=[])
    assert result["isbn_overlap"]["pct"] is None
    assert result["isbn_overlap"]["classification"] == "sin_datos"
    assert result["series_overlap"]["pct"] is None
    assert result["series_overlap"]["classification"] == "sin_datos"


def test_compute_overlap_series_guess_is_slugified_before_matching(tmp_path):
    items_path = _write_items(tmp_path / "items.jsonl", [
        _item(series_key="jujutsu-kaisen", country="es"),
    ])
    corpus = so.load_corpus(items_path)
    result = so.compute_overlap(
        corpus, sample_isbns_raw=[], sample_series_raw=["Jujutsu Kaisen"],
    )
    assert result["series_overlap"]["matched"] == 1
    assert result["series_overlap"]["pct"] == 100.0


# --------------------------------------------------------------------------- #
# load_eval_file()
# --------------------------------------------------------------------------- #

def test_load_eval_file_extracts_isbn_and_series_guess(tmp_path):
    eval_path = tmp_path / "source-eval-nueva-tienda.json"
    eval_path.write_text(json.dumps({
        "source": "nueva-tienda.fr",
        "sample_items": [
            {"title": "One Piece Ed. Deluxe T1", "isbn": ISBN_A, "series_key_guess": "One Piece"},
            {"title": "Sin isbn", "isbn": "", "series_key_guess": "Naruto"},
            {"title": "Sin ningun campo extra"},
        ],
    }), encoding="utf-8")

    isbns, series = so.load_eval_file(eval_path)
    assert isbns == [ISBN_A]
    assert series == ["One Piece", "Naruto"]


def test_load_eval_file_missing_sample_items_is_empty(tmp_path):
    eval_path = tmp_path / "source-eval-x.json"
    eval_path.write_text(json.dumps({"source": "x"}), encoding="utf-8")
    isbns, series = so.load_eval_file(eval_path)
    assert isbns == []
    assert series == []


# --------------------------------------------------------------------------- #
# country breakdown
# --------------------------------------------------------------------------- #

def test_top_countries_sorted_desc(tmp_path):
    items_path = _write_items(tmp_path / "items.jsonl", [
        _item(country="es"), _item(country="es"), _item(country="es"),
        _item(country="fr"), _item(country="fr"),
        _item(country="it"),
    ])
    corpus = so.load_corpus(items_path)
    top = so.top_countries(corpus, n=2)
    assert top == [("es", 3), ("fr", 2)]


# --------------------------------------------------------------------------- #
# CLI (main())
# --------------------------------------------------------------------------- #

def test_main_json_output_with_manual_lists(tmp_path, monkeypatch, capsys):
    items_path = _write_items(tmp_path / "items.jsonl", [
        _item(isbn=ISBN_A, series_key="one-piece", country="es"),
    ])
    monkeypatch.setattr(
        sys, "argv",
        ["source_overlap.py", "--items", str(items_path),
         "--isbns", ISBN_A, "--series", "One Piece", "--json"],
    )
    rc = so.main()
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["isbn_overlap"]["matched"] == 1
    assert payload["corpus"]["total_items"] == 1


def test_main_with_eval_file(tmp_path, monkeypatch, capsys):
    items_path = _write_items(tmp_path / "items.jsonl", [
        _item(isbn=ISBN_A, series_key="one-piece", country="es"),
    ])
    eval_path = tmp_path / "source-eval-x.json"
    eval_path.write_text(json.dumps({
        "sample_items": [{"isbn": ISBN_A, "series_key_guess": "One Piece"}],
    }), encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv",
        ["source_overlap.py", "--items", str(items_path),
         "--eval-file", str(eval_path), "--json"],
    )
    rc = so.main()
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["isbn_overlap"]["matched"] == 1
    assert payload["isbn_overlap"]["classification"] == "redundante"


def test_main_no_input_reports_sin_datos_exit_zero(tmp_path, monkeypatch, capsys):
    items_path = _write_items(tmp_path / "items.jsonl", [_item(isbn=ISBN_A)])
    monkeypatch.setattr(
        sys, "argv",
        ["source_overlap.py", "--items", str(items_path), "--json"],
    )
    rc = so.main()
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["isbn_overlap"]["classification"] == "sin_datos"


def test_main_missing_items_file_is_read_only_ok(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv",
        ["source_overlap.py", "--items", str(tmp_path / "no-existe.jsonl"),
         "--isbns", "9999999999999", "--json"],
    )
    rc = so.main()
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["corpus"]["total_items"] == 0


def test_cli_help_runs_via_subprocess():
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "audit" / "source_overlap.py"), "--help"],
        capture_output=True, text=True, cwd=repo_root,
    )
    assert result.returncode == 0
    assert "--eval-file" in result.stdout
