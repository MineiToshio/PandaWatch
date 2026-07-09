"""Tests para la corrección de sufijo país EQUIVOCADO en fix_edition_country.

Regla dura país=edición: el sufijo país del edition_key debe reflejar
`item.country` (fuente de verdad). El motor viejo sólo APENDABA el país cuando
faltaba; si el edition_key ya terminaba en un country_slug válido pero
EQUIVOCADO (caso real: Jade Dynasty HK con `…-tw` tras el standardize) lo daba
por "ya sufijado" y nunca lo arreglaba. Ahora también corrige el equivocado.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_RETROFIT_DIR = _ROOT / "scripts" / "retrofit"
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))
if str(_RETROFIT_DIR) not in sys.path:
    sys.path.insert(0, str(_RETROFIT_DIR))

import fix_edition_country as fec  # noqa: E402


# ── Unit: _suffix_country ─────────────────────────────────────────────────

def test_wrong_country_suffix_is_corrected():
    # Caso real Jade Dynasty: edición de Hong Kong con sufijo tw stale.
    assert (fec._suffix_country("rozen-maiden-jadedynasty-boxset-tw", "Hong Kong")
            == "rozen-maiden-jadedynasty-boxset-hk")
    assert (fec._suffix_country("hana-no-keiji-jadedynasty-kanzenban-tw", "Hong Kong")
            == "hana-no-keiji-jadedynasty-kanzenban-hk")


def test_correct_country_suffix_is_untouched():
    ek = "rozen-maiden-jadedynasty-boxset-hk"
    assert fec._suffix_country(ek, "Hong Kong") == ek


def test_missing_country_suffix_is_appended():
    # Comportamiento histórico intacto: sin sufijo país → apendar.
    assert (fec._suffix_country("seriea-panini-regular", "España")
            == "seriea-panini-regular-es")


def test_non_country_last_segment_is_not_replaced():
    # "glob" no es un country_slug conocido → NO se toca como país; se apenda
    # el país correcto (glob se preserva, no se clobberea).
    assert (fec._suffix_country("seriea-panini-glob", "España")
            == "seriea-panini-glob-es")
    # Un token de edición como último segmento tampoco se confunde con país.
    assert (fec._suffix_country("seriea-panini-boxset", "España")
            == "seriea-panini-boxset-es")


def test_collision_suffix_is_preserved():
    # El sufijo opcional de colisión "-cN" se separa, se corrige el país y se
    # re-apenda (nunca se interpreta como país).
    assert (fec._suffix_country("rozen-maiden-jadedynasty-boxset-tw-c2", "Hong Kong")
            == "rozen-maiden-jadedynasty-boxset-hk-c2")
    # Con país faltante + colisión, el país se inserta antes del -cN.
    assert (fec._suffix_country("seriea-panini-regular-c3", "España")
            == "seriea-panini-regular-es-c3")


def test_unknown_country_does_not_clobber_existing_suffix():
    # País vacío/desconocido (cs=xx): NO reemplazar un sufijo país real por xx.
    assert fec._suffix_country("seriea-panini-tw", "") == "seriea-panini-tw"
    # Sin sufijo y país desconocido → apendar xx (histórico).
    assert fec._suffix_country("seriea-panini-regular", "") == "seriea-panini-regular-xx"


def test_xx_placeholder_is_left_alone_scope():
    # Placeholder explícito -xx: fuera de scope de esta corrección (lo maneja
    # fix_edition_key_anomalies con reglas duras). No se convierte a país acá.
    assert fec._suffix_country("seriea-panini-xx", "Hong Kong") == "seriea-panini-xx"


def test_idempotent_double_apply():
    ek = "hana-no-keiji-jadedynasty-kanzenban-tw"
    once = fec._suffix_country(ek, "Hong Kong")
    twice = fec._suffix_country(once, "Hong Kong")
    assert once == twice == "hana-no-keiji-jadedynasty-kanzenban-hk"


# ── Integración: main() vía CLI (guard approved) ──────────────────────────

def _run_main(module, argv):
    old = sys.argv
    sys.argv = [module.__name__ + ".py", *argv]
    try:
        return module.main()
    finally:
        sys.argv = old


@pytest.fixture
def items_path(tmp_path, monkeypatch):
    p = tmp_path / "items.jsonl"
    monkeypatch.setattr(fec, "ITEMS", p)
    return p


def _write(path, items):
    path.write_text("\n".join(json.dumps(it) for it in items) + "\n", encoding="utf-8")


def _read(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def test_main_corrects_wrong_suffix_and_respects_approved(items_path):
    items = [
        {"title": "Rozen Maiden", "url": "https://jd-intl.com/a",
         "edition_key": "rozen-maiden-jadedynasty-boxset-tw",
         "country": "Hong Kong", "volume": "", "sources": [{"url": "https://jd-intl.com/a"}]},
        {"title": "Hoshin Engi", "url": "https://jd-intl.com/b",
         "edition_key": "hoshin-engi-jadedynasty-kanzenban-tw",
         "country": "Hong Kong", "volume": "1", "sources": [{"url": "https://jd-intl.com/b"}],
         "approved_at": "2026-06-01T00:00:00+00:00"},
    ]
    _write(items_path, items)
    assert _run_main(fec, []) == 0
    out = {it["title"]: it for it in _read(items_path)}
    # No aprobado: sufijo corregido tw→hk.
    assert out["Rozen Maiden"]["edition_key"] == "rozen-maiden-jadedynasty-boxset-hk"
    # Aprobado: intacto por defecto (golden record).
    assert out["Hoshin Engi"]["edition_key"] == "hoshin-engi-jadedynasty-kanzenban-tw"


def test_main_include_approved_corrects_approved(items_path):
    items = [
        {"title": "Hoshin Engi", "url": "https://jd-intl.com/b",
         "edition_key": "hoshin-engi-jadedynasty-kanzenban-tw",
         "country": "Hong Kong", "volume": "1", "sources": [{"url": "https://jd-intl.com/b"}],
         "approved_at": "2026-06-01T00:00:00+00:00"},
    ]
    _write(items_path, items)
    assert _run_main(fec, ["--include-approved"]) == 0
    out = _read(items_path)[0]
    assert out["edition_key"] == "hoshin-engi-jadedynasty-kanzenban-hk"


def test_main_idempotent(items_path):
    items = [
        {"title": "Rozen Maiden", "url": "https://jd-intl.com/a",
         "edition_key": "rozen-maiden-jadedynasty-boxset-tw",
         "country": "Hong Kong", "volume": "", "sources": [{"url": "https://jd-intl.com/a"}]},
    ]
    _write(items_path, items)
    assert _run_main(fec, []) == 0
    first = items_path.read_text()
    assert _run_main(fec, []) == 0
    assert items_path.read_text() == first
