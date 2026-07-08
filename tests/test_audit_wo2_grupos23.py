"""Tests para WO-2 (auditoría post-scrape, GRUPOS 2/3/4, 2026-07-07).

Cubre:
  - GRUPO 2: `scripts/retrofit/purge_false_artbook_residuals.py` — desblinda
    residuos de "category" inyectada (bug viejo del calendario legacy) que
    marcaron tomos regulares como artbook/boxset.
  - GRUPO 3: `scripts/retrofit/purge_op_import_foreign.py` — desblinda +
    encola items del import manual de One Piece cuyo título es de OTRA serie.
  - Guarda de `op_series_guard.is_one_piece_title()` reusada por
    `scripts/import_op_remix.py` / `scripts/fix_op_special_vols.py`.
  - GRUPO 4: guarda anti-folleto promocional en el módulo legacy del
    calendario (`scripts/wikis/listadomanga.py`).

Todas las escrituras van a `tmp_path` — JAMÁS a `data/items.jsonl` real.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import standardize_apply
from op_series_guard import is_one_piece_title
from scripts.retrofit import purge_false_artbook_residuals as pfar
from scripts.retrofit import purge_op_import_foreign as poif


def _write_jsonl(path: Path, items: list[dict]) -> Path:
    with path.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    return path


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ===========================================================================
# GRUPO 2 — purge_false_artbook_residuals.py
# ===========================================================================

def _false_artbook_item(**overrides) -> dict:
    it = {
        "title": "Fire Force 9",
        "url": "https://example.com/fire-force-9",
        "slug": "fire-force-9",
        "product_type": "artbook",
        "signal_types": ["artbook"],
        "standardized_at": "2026-06-01T00:00:00Z",
        "edition_key": "fire-force-somepub-regular-jp",
        "edition_display": "Some Pub",
    }
    it.update(overrides)
    return it


def test_is_false_artbook_residual_matches_baseline_case():
    assert pfar.is_false_artbook_residual(_false_artbook_item())


def test_is_false_artbook_residual_requires_standardized_at():
    assert not pfar.is_false_artbook_residual(_false_artbook_item(standardized_at=""))


def test_is_false_artbook_residual_requires_product_type_artbook_or_boxset():
    assert not pfar.is_false_artbook_residual(_false_artbook_item(product_type="manga"))
    assert pfar.is_false_artbook_residual(_false_artbook_item(product_type="boxset"))


def test_is_false_artbook_residual_edition_display_regular_also_matches():
    item = _false_artbook_item(edition_key="fire-force-somepub-especial-jp", edition_display="Regular")
    assert pfar.is_false_artbook_residual(item)


def test_is_false_artbook_residual_excludes_non_regular_edition():
    item = _false_artbook_item(edition_key="fire-force-somepub-especial-jp", edition_display="Especial")
    assert not pfar.is_false_artbook_residual(item)


def test_is_false_artbook_residual_requires_exact_signal_types_artbook():
    # Señal adicional (evidencia real) → fuera de alcance de este retrofit.
    item = _false_artbook_item(signal_types=["artbook", "bonus"])
    assert not pfar.is_false_artbook_residual(item)


@pytest.mark.parametrize("keyword", [
    "illustrations", "art book", "artbook", "ilustraciones",
    "libro de ilustraciones", "sketchbook", "fanbook", "guidebook", "databook",
])
def test_is_false_artbook_residual_excludes_real_artbook_keywords(keyword):
    item = _false_artbook_item(title=f"Some Series {keyword.title()}")
    assert not pfar.is_false_artbook_residual(item)


def test_strip_injected_category_removes_second_segment():
    item = _false_artbook_item(
        description="Norma Editorial · Artbook · Fire Force nº9 (de 34) · Atsushi Ohkubo",
        tags=["wiki", "listadomanga", "manga", "spain", "category:Artbook"],
    )
    assert pfar.strip_injected_category(item) == (
        "Norma Editorial · Fire Force nº9 (de 34) · Atsushi Ohkubo"
    )


def test_strip_injected_category_noop_when_no_category_tag():
    item = _false_artbook_item(
        description="Norma Editorial · Fire Force nº9", tags=["manga"]
    )
    assert pfar.strip_injected_category(item) is None


def test_strip_injected_category_noop_when_category_not_second_segment():
    # La categoría no está en la posición inyectada → no se toca.
    item = _false_artbook_item(
        description="Norma Editorial · Fire Force nº9 · Artbook mención",
        tags=["category:Artbook"],
    )
    assert pfar.strip_injected_category(item) is None


def test_apply_cleans_injected_category_so_signal_is_droppable(tmp_path, monkeypatch):
    item = _false_artbook_item(
        url="https://example.com/1",
        description="Norma Editorial · Artbook · Fire Force nº9 (de 34) · Atsushi Ohkubo",
        tags=["wiki", "listadomanga", "manga", "spain", "category:Artbook"],
    )
    items_path = _write_jsonl(tmp_path / "items.jsonl", [item])
    monkeypatch.setattr(sys, "argv", ["purge_false_artbook_residuals.py", "--input", str(items_path)])
    assert pfar.main() == 0
    row = _read_jsonl(items_path)[0]
    assert "standardized_at" not in row
    assert "Artbook" not in row["description"]
    assert row["description"] == "Norma Editorial · Fire Force nº9 (de 34) · Atsushi Ohkubo"


def test_find_candidates_approved_guard_and_include_approved():
    items = [_false_artbook_item(approved_at="2026-01-01T00:00:00Z")]
    candidates, skipped = pfar.find_candidates(items, include_approved=False)
    assert candidates == []
    assert skipped == 1

    candidates, skipped = pfar.find_candidates(items, include_approved=True)
    assert len(candidates) == 1
    assert skipped == 0


def test_purge_false_artbook_dry_run_does_not_write(tmp_path, monkeypatch):
    items_path = _write_jsonl(tmp_path / "items.jsonl", [_false_artbook_item()])
    mtime_before = items_path.stat().st_mtime_ns

    monkeypatch.setattr(sys, "argv", [
        "purge_false_artbook_residuals.py", "--input", str(items_path), "--dry-run",
    ])
    rc = pfar.main()
    assert rc == 0
    assert items_path.stat().st_mtime_ns == mtime_before
    rows = _read_jsonl(items_path)
    assert rows[0].get("standardized_at")  # intacto


def test_purge_false_artbook_apply_removes_standardized_at(tmp_path, monkeypatch):
    items_path = _write_jsonl(tmp_path / "items.jsonl", [
        _false_artbook_item(url="https://example.com/1"),
        {"title": "Real Artbook", "url": "https://example.com/2", "product_type": "artbook",
         "signal_types": ["artbook"], "standardized_at": "2026-06-01T00:00:00Z",
         "edition_key": "real-artbook-somepub-regular-jp", "edition_display": "Some Pub"},
    ])
    monkeypatch.setattr(sys, "argv", [
        "purge_false_artbook_residuals.py", "--input", str(items_path),
    ])
    rc = pfar.main()
    assert rc == 0
    rows = _read_jsonl(items_path)
    by_url = {r["url"]: r for r in rows}
    # El falso residuo perdió standardized_at (desblindado)...
    assert "standardized_at" not in by_url["https://example.com/1"]
    # ...el artbook LEGÍTIMO (título con keyword real) queda intacto.
    assert by_url["https://example.com/2"].get("standardized_at")


def test_purge_false_artbook_is_idempotent(tmp_path, monkeypatch):
    items_path = _write_jsonl(tmp_path / "items.jsonl", [_false_artbook_item(url="https://example.com/1")])
    monkeypatch.setattr(sys, "argv", ["purge_false_artbook_residuals.py", "--input", str(items_path)])
    assert pfar.main() == 0
    first_pass = _read_jsonl(items_path)

    monkeypatch.setattr(sys, "argv", ["purge_false_artbook_residuals.py", "--input", str(items_path)])
    assert pfar.main() == 0
    second_pass = _read_jsonl(items_path)
    assert first_pass == second_pass


# ===========================================================================
# op_series_guard.is_one_piece_title — reusada por import_op_remix.py /
# fix_op_special_vols.py / purge_op_import_foreign.py
# ===========================================================================

def test_is_one_piece_title_accepts_one_piece_variants():
    assert is_one_piece_title("One Piece Volume 794")
    assert is_one_piece_title("ONE PIECE THE MOVIE カラクリ城のメカ巨兵 アニメコミックス")
    assert is_one_piece_title("", "ワンピース・マガジン Vol.2")
    assert is_one_piece_title("WANTED! 尾田栄一郎短編集")


def test_is_one_piece_title_accepts_known_spinoff_shokugeki_no_sanji():
    # Spin-off oficial: sin allowlist se clasificaría como foreign.
    assert is_one_piece_title("Shokugeki no Sanji 1")
    assert is_one_piece_title("", "食戟のサンジ 2")


def test_is_one_piece_title_rejects_foreign_series():
    assert not is_one_piece_title("地獄楽 12", "地獄楽 12")
    assert not is_one_piece_title("ルリドラゴン = RURIDRAGON 1")
    assert not is_one_piece_title("遊☆戯☆王OCG(オフィシャルカードゲーム)ストラクチャーズ. 6")


# ===========================================================================
# GRUPO 3 — purge_op_import_foreign.py
# ===========================================================================

def _op_import_item(**overrides) -> dict:
    it = {
        "title": "地獄楽 12",
        "title_original": "地獄楽 12",
        "url": "https://example.com/gakuen-2",
        "slug": "one-piece-gakuen-shueisha-special-jp-2",
        "series_key": "one-piece-gakuen",
        "series_display": "One Piece Gakuen",
        "source": "Research import (One Piece special volumes)",
        "standardized_at": "2026-06-09T00:17:09Z",
        "edition_key": "one-piece-gakuen-shueisha-special-jp",
    }
    it.update(overrides)
    return it


def test_is_op_import_foreign_matches_foreign_title():
    assert poif.is_op_import_foreign(_op_import_item())


def test_is_op_import_foreign_requires_op_import_source_prefix():
    item = _op_import_item(source="ES - Some Store")
    assert not poif.is_op_import_foreign(item)


def test_is_op_import_foreign_accepts_genuine_one_piece():
    item = _op_import_item(title="One Piece Volume 794", title_original="ONE PIECE 巻七九四")
    assert not poif.is_op_import_foreign(item)


def test_op_import_foreign_find_candidates_approved_guard():
    items = [_op_import_item(approved_at="2026-01-01T00:00:00Z")]
    candidates, skipped = poif.find_candidates(items, include_approved=False)
    assert candidates == []
    assert skipped == 1

    candidates, skipped = poif.find_candidates(items, include_approved=True)
    assert len(candidates) == 1


def test_purge_op_import_foreign_dry_run_does_not_write(tmp_path, monkeypatch, capsys):
    items_path = _write_jsonl(tmp_path / "items.jsonl", [_op_import_item()])
    unmapped_path = tmp_path / "unmapped_series.jsonl"
    monkeypatch.setattr(standardize_apply, "UNMAPPED", unmapped_path)

    monkeypatch.setattr(sys, "argv", ["purge_op_import_foreign.py", "--input", str(items_path)])
    rc = poif.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "[DRY-RUN]" in out
    assert not unmapped_path.exists()
    rows = _read_jsonl(items_path)
    assert rows[0].get("standardized_at")  # intacto


def test_purge_op_import_foreign_apply_desblinda_y_encola(tmp_path, monkeypatch):
    items_path = _write_jsonl(tmp_path / "items.jsonl", [_op_import_item(url="https://example.com/1")])
    unmapped_path = tmp_path / "unmapped_series.jsonl"
    monkeypatch.setattr(standardize_apply, "UNMAPPED", unmapped_path)

    monkeypatch.setattr(sys, "argv", [
        "purge_op_import_foreign.py", "--input", str(items_path), "--apply",
    ])
    rc = poif.main()
    assert rc == 0

    rows = _read_jsonl(items_path)
    assert "standardized_at" not in rows[0]

    assert unmapped_path.exists()
    queue_rows = _read_jsonl(unmapped_path)
    assert len(queue_rows) == 1
    assert queue_rows[0]["reason"] == "op_import_foreign"
    assert queue_rows[0]["sample_url"] == "https://example.com/1"


def test_purge_op_import_foreign_apply_dedups_by_url_and_reason(tmp_path, monkeypatch):
    items_path = _write_jsonl(tmp_path / "items.jsonl", [_op_import_item(url="https://example.com/1")])
    unmapped_path = tmp_path / "unmapped_series.jsonl"
    monkeypatch.setattr(standardize_apply, "UNMAPPED", unmapped_path)

    monkeypatch.setattr(sys, "argv", [
        "purge_op_import_foreign.py", "--input", str(items_path), "--apply",
    ])
    assert poif.main() == 0
    # Re-crear el item con standardized_at (simula un re-scrape) y correr de nuevo.
    _write_jsonl(items_path, [_op_import_item(url="https://example.com/1")])
    assert poif.main() == 0
    queue_rows = _read_jsonl(unmapped_path)
    assert len(queue_rows) == 1  # no duplicado


# ===========================================================================
# GRUPO 4 — guarda anti-folleto promocional en el módulo legacy del calendario
# ===========================================================================

def test_listadomanga_calendar_skips_promotional_edition_link():
    from wikis import listadomanga as lm
    html = """<html><body>
        <h2>Norma Editorial</h2>
        <h2>Sábado, 2 Mayo 2026</h2>
        <table class="ventana_id1">
            <tr><td class="izq">
                <b><u>Seinen</u></b><br/>
                - <a href="coleccion.php?id=100">Berserk Deluxe nº14 - Edición Especial</a> /
                  <a href="autor.php?id=50">Kentaro Miura</a><br/>
                - <a href="coleccion.php?id=200">Preview Edición Promocional</a> /
                  <a href="autor.php?id=99">Autor X</a><br/>
            </td></tr>
        </table>
    </body></html>"""
    items = lm.parse_calendar_page(html)
    assert len(items) == 1
    assert "Berserk Deluxe" in items[0].title
    assert all("Promocional" not in it.title for it in items)


def test_listadomanga_calendar_free_price_pattern_reused_not_copied():
    """El módulo legacy debe importar FREE_PRICE_PATTERN de
    listadomanga_collections.py (fuente única, gotcha #103) — no redefinirlo."""
    from wikis import listadomanga as lm
    from wikis import listadomanga_collections as lmc
    assert lm.FREE_PRICE_PATTERN is lmc.FREE_PRICE_PATTERN
