"""Tests para el retrofit de títulos basura CONGELADOS de IT - Funside Variant.

Contexto (post-mortem delta 2026-08-24, gotcha #148): el `title_selector` viejo
de Funside capturaba el badge de preventa/descuento en vez del título real
("USCITA: dd/mm/yy" / "Sconto"). El fix de selector no corrige los items que ya
tienen `standardized_at` (title congelado por `_CURATED_FIELDS` en el upsert),
así que este retrofit los arregla leyendo el título real de la `description`
(patrón "Confrontare TÍTULO Prezzo normale").
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _ROOT / "scripts"
_RETROFIT_DIR = _SCRIPTS_DIR / "retrofit"

# Asegurar que scripts/ resuelva ANTES que la raíz del repo para
# `import manga_watch` (el import interno del retrofit) — pytest puede
# insertar la raíz del repo en sys.path[0] al importar este módulo de test
# (tests/ tiene __init__.py), lo que haría ganar al wrapper de compat
# manga_watch.py de la raíz (sólo expone parse_args/run) en vez del módulo
# real scripts/manga_watch.py. Se limpia el cache y se fuerza el orden.
sys.modules.pop("manga_watch", None)
for _p in (str(_RETROFIT_DIR), str(_SCRIPTS_DIR)):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

import fix_funside_frozen_titles_20260824 as fx  # noqa: E402


# ── Unit: extract_real_title ────────────────────────────────────────────────

def test_extracts_title_from_confrontare_pattern():
    desc = ("USCITA: 30/09/26 Vai alla pagina Confrontare SAKAMOTO DAYS VOL.26 - "
            "VARIANT Prezzo normale €7,90 Prezzo di vendita €7,90")
    assert fx.extract_real_title(desc) == "SAKAMOTO DAYS VOL.26 - VARIANT"


def test_extracts_title_when_sconto_prefix_at_start():
    desc = ("Sconto Aggiungi al carrello Confrontare A TUTTO GAS VOL.2 - VARIANT "
            "Prezzo normale €11,20 Prezzo di vendita €11,20")
    assert fx.extract_real_title(desc) == "A TUTTO GAS VOL.2 - VARIANT"


def test_returns_empty_when_no_pattern_match():
    assert fx.extract_real_title("Descripción cualquiera sin el patrón esperado.") == ""


def test_returns_empty_on_empty_description():
    assert fx.extract_real_title("") == ""
    assert fx.extract_real_title(None) == ""  # type: ignore[arg-type]


def test_rejects_absurdly_long_capture():
    # Si el patrón matchea pero el resultado es sospechosamente largo (falta
    # de límite en el texto real), no se devuelve — mejor no tocar el título.
    desc = "Confrontare " + ("X " * 100) + " Prezzo normale €1"
    assert fx.extract_real_title(desc) == ""


# ── Unit: JUNK_TITLE_RE ─────────────────────────────────────────────────────

def test_junk_title_matches_uscita_pattern():
    assert fx.JUNK_TITLE_RE.match("USCITA: 28/10/26")
    assert fx.JUNK_TITLE_RE.match("Sconto")


def test_junk_title_does_not_match_real_titles():
    assert not fx.JUNK_TITLE_RE.match("SAKAMOTO DAYS VOL.26 - VARIANT")
    assert not fx.JUNK_TITLE_RE.match("USCITA: 28/10/26 - EXTRA")  # no exact match


# ── Unit: is_funside_item ───────────────────────────────────────────────────

def test_is_funside_item_by_top_level_url():
    assert fx.is_funside_item({"url": "https://funside.it/products/x-variant"})
    assert not fx.is_funside_item({"url": "https://otherstore.it/products/x"})


def test_is_funside_item_by_sources_entry():
    item = {"url": "", "sources": [{"url": "https://funside.it/products/x-variant"}]}
    assert fx.is_funside_item(item)


# ── Integration: main() end-to-end sobre un items.jsonl de prueba ──────────

def _write_items(path: Path, items: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item) + "\n")


def _read_items(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_apply_fixes_only_standardized_junk_titles(tmp_path, monkeypatch):
    items = [
        {
            # Frozen: standardized_at truthy -> se corrige.
            "url": "https://funside.it/products/sakamoto-days-vol-26-variant",
            "slug": "sakamoto-days-panini-variant-it-26",
            "title": "USCITA: 30/09/26",
            "description": ("USCITA: 30/09/26 Vai alla pagina Confrontare SAKAMOTO "
                             "DAYS VOL.26 - VARIANT Prezzo normale €7,90"),
            "standardized_at": "2026-08-23T21:33:07.053700+00:00",
        },
        {
            # Raw: sin standardized_at -> NO se toca (se auto-corrige en el
            # próximo scrape).
            "url": "https://funside.it/products/daidara-1-variant",
            "slug": "isbn-daidara",
            "title": "USCITA: 30/09/26",
            "description": ("USCITA: 30/09/26 Vai alla pagina Confrontare DAIDARA 1 "
                             "- VARIANT Prezzo normale €7,00"),
            "standardized_at": None,
        },
        {
            # Aprobado (golden record) -> NUNCA se toca aunque esté
            # standardized_at + title basura.
            "url": "https://funside.it/products/otro-item-variant",
            "slug": "otro-item-variant",
            "title": "Sconto",
            "description": "Sconto Aggiungi al carrello Confrontare OTRO ITEM - VARIANT Prezzo normale €5,00",
            "standardized_at": "2026-06-08T03:34:23.644171+00:00",
            "approved_at": "2026-06-09T00:00:00+00:00",
        },
        {
            # No es de Funside -> no se toca aunque el título matchee el patrón.
            "url": "https://otherstore.it/products/x",
            "slug": "otro-x",
            "title": "Sconto",
            "standardized_at": "2026-06-08T03:34:23.644171+00:00",
        },
        {
            # Funside, standardized, título ok (no junk) -> no se toca.
            "url": "https://funside.it/products/normal-variant",
            "slug": "normal-variant",
            "title": "NORMAL TITLE - VARIANT",
            "standardized_at": "2026-06-08T03:34:23.644171+00:00",
        },
    ]
    src = tmp_path / "items.jsonl"
    _write_items(src, items)

    # dry-run: no escribe.
    argv_backup = sys.argv
    try:
        sys.argv = ["fix_funside_frozen_titles_20260824.py", "--input", str(src), "--output", str(src)]
        rc = fx.main()
    finally:
        sys.argv = argv_backup
    assert rc == 0
    # dry-run no modifica el archivo.
    unchanged = _read_items(src)
    assert unchanged[0]["title"] == "USCITA: 30/09/26"

    # --apply: sólo corrige el item frozen (idx 0).
    evidence_path = tmp_path / "evidence.jsonl"
    try:
        sys.argv = [
            "fix_funside_frozen_titles_20260824.py",
            "--input", str(src), "--output", str(src),
            "--apply", "--evidence", str(evidence_path),
        ]
        rc = fx.main()
    finally:
        sys.argv = argv_backup
    assert rc == 0

    result = _read_items(src)
    by_slug = {r["slug"]: r for r in result}
    assert by_slug["sakamoto-days-panini-variant-it-26"]["title"] == "SAKAMOTO DAYS VOL.26 - VARIANT"
    assert by_slug["isbn-daidara"]["title"] == "USCITA: 30/09/26"  # raw: intocado
    assert by_slug["otro-item-variant"]["title"] == "Sconto"  # aprobado: intocado
    assert by_slug["otro-x"]["title"] == "Sconto"  # no-funside: intocado
    assert by_slug["normal-variant"]["title"] == "NORMAL TITLE - VARIANT"  # ya ok

    assert evidence_path.exists()
    evidence = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines()]
    assert len(evidence) == 1
    assert evidence[0]["slug"] == "sakamoto-days-panini-variant-it-26"


def test_apply_is_idempotent(tmp_path):
    items = [
        {
            "url": "https://funside.it/products/sakamoto-days-vol-26-variant",
            "slug": "sakamoto-days-panini-variant-it-26",
            "title": "USCITA: 30/09/26",
            "description": ("USCITA: 30/09/26 Vai alla pagina Confrontare SAKAMOTO "
                             "DAYS VOL.26 - VARIANT Prezzo normale €7,90"),
            "standardized_at": "2026-08-23T21:33:07.053700+00:00",
        },
    ]
    src = tmp_path / "items.jsonl"
    _write_items(src, items)

    argv_backup = sys.argv
    try:
        sys.argv = ["x", "--input", str(src), "--output", str(src), "--apply",
                    "--evidence", str(tmp_path / "ev1.jsonl")]
        assert fx.main() == 0
        first_pass = _read_items(src)

        sys.argv = ["x", "--input", str(src), "--output", str(src), "--apply",
                    "--evidence", str(tmp_path / "ev2.jsonl")]
        assert fx.main() == 0
        second_pass = _read_items(src)
    finally:
        sys.argv = argv_backup

    assert first_pass == second_pass
    # La segunda corrida no debería generar evidencia (0 cambios).
    assert not (tmp_path / "ev2.jsonl").exists() or (tmp_path / "ev2.jsonl").read_text() == ""
