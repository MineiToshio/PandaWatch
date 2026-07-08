"""Tests para WO-B de la auditoría post-scrape — scripts/retrofit/translate_descriptions.py.

Cubre los 5 cambios del work order (todos con mocks de las APIs, sin red):
  1. Fallo de API ≠ ya-ES: si TODOS los servicios fallan, NO se escribe la key
     description_es (el item queda pendiente y se reintenta); "" queda RESERVADO
     para "el original ya es español".
  2. Hash de staleness: al escribir description_es (traducción O marca ya-ES "")
     se escribe description_es_src_hash = sha1(description).hexdigest()[:12].
  3. Regex IT segura: el botón "Aggiungi al Carrello" al PRINCIPIO (Funside Variant)
     ya no se come el título; el junk real al final sí se remueve.
  4. Determinismo: DetectorFactory.seed = 0 al importar el módulo.
  5. No-op barato: si la API devuelve texto idéntico (módulo espacios) al input,
     se trata como ya-ES ("" + hash), sin guardar copias byte-idénticas.
  + Flag --retry-empty: selección por-campo de los description_es=="" no-español.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "retrofit"))
sys.path.insert(0, str(ROOT / "scripts"))

import translate_descriptions as td  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures de texto (langdetect es determinista con seed=0)
# ---------------------------------------------------------------------------

EN = "This is a special collector's edition with slipcase and exclusive art cards."
ES = "Esta es una edición especial de coleccionista con estuche y láminas exclusivas de gran calidad."
IT = "Questo volume raccoglie una storia epica con illustrazioni a colori e sovraccoperta esclusiva."


def _sha12(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


# Helpers de mock (funciones nombradas → tracebacks legibles)
def _google_returns(value):
    def _fake(text):
        return value
    return _fake


def _google_raises(msg="down"):
    def _fake(text):
        raise td.TranslationError(f"google: {msg}")
    return _fake


def _deepl_raises(msg="down"):
    def _fake(text, translator):
        raise td.TranslationError(f"deepl: {msg}")
    return _fake


# ---------------------------------------------------------------------------
# Cambio 4 — determinismo de langdetect
# ---------------------------------------------------------------------------

def test_langdetect_seed_is_zero_on_import():
    from langdetect import DetectorFactory
    assert DetectorFactory.seed == 0


def test_detect_is_deterministic():
    from langdetect import detect
    assert detect(IT) == detect(IT)


# ---------------------------------------------------------------------------
# Cambio 3 — regex IT segura (_clean_description_for_translation)
# ---------------------------------------------------------------------------

FUNSIDE = ("Sconto Aggiungi al carrello Confrontare Berserk Deluxe Edition Vol 1 "
           "Prezzo regolare 18,90 euro Prezzo scontato 16,90 euro")
FUNSIDE_SHORT = "Sconto Aggiungi al carrello Confrontare Naruto Vol 3"
LEGIT = ("Questo volume raccoglie una storia epica di grande formato con "
         "illustrazioni a colori e sovraccoperta. Aggiungi al Carrello Disponibilità immediata")
DOUBLE = ("Questo volume raccoglie una storia epica di grande formato con "
          "illustrazioni a colori. Aggiungi Aggiungi al Carrello Disponibile")


def test_funside_prefix_junk_does_not_eat_title():
    """El junk al PRINCIPIO no debe colapsar el texto a 'Sconto'."""
    cleaned = td._clean_description_for_translation(FUNSIDE)
    assert "Berserk Deluxe Edition Vol 1" in cleaned
    assert cleaned.strip() != "Sconto"


def test_funside_short_title_survives():
    """Aunque el texto sea corto (<150 chars), el título sobrevive."""
    cleaned = td._clean_description_for_translation(FUNSIDE_SHORT)
    assert "Naruto Vol 3" in cleaned


def test_legit_trailing_cart_button_removed():
    """El botón real al final sí se remueve, con su cola de UI."""
    cleaned = td._clean_description_for_translation(LEGIT)
    assert "Questo volume raccoglie una storia epica" in cleaned
    assert "Aggiungi al Carrello" not in cleaned
    assert "Disponibilità" not in cleaned


def test_double_aggiungi_trailing_removed():
    cleaned = td._clean_description_for_translation(DOUBLE)
    assert "Questo volume raccoglie" in cleaned
    assert "Aggiungi" not in cleaned
    assert "Disponibile" not in cleaned


def test_strip_it_cart_suffix_no_match_is_noop():
    text = "Un manga estupendo sin ningún botón."
    assert td._strip_it_cart_suffix(text) == text


# ---------------------------------------------------------------------------
# Cambio 2 — hash de staleness
# ---------------------------------------------------------------------------

def test_src_hash_format():
    h = td._description_src_hash("hola mundo")
    assert h == _sha12("hola mundo")
    assert len(h) == 12
    assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# Wrappers de traducción — fallo = excepción o vacío para input no vacío
# ---------------------------------------------------------------------------

def test_translate_google_empty_raises(monkeypatch):
    import deep_translator

    class FakeGT:
        def __init__(self, source, target):
            pass

        def translate(self, text):
            return ""

    monkeypatch.setattr(deep_translator, "GoogleTranslator", FakeGT)
    with pytest.raises(td.TranslationError):
        td._translate_google("input no vacío")


def test_translate_google_exception_wrapped(monkeypatch):
    import deep_translator

    class FakeGT:
        def __init__(self, source, target):
            pass

        def translate(self, text):
            raise RuntimeError("boom de red")

    monkeypatch.setattr(deep_translator, "GoogleTranslator", FakeGT)
    with pytest.raises(td.TranslationError):
        td._translate_google("input")


def test_translate_google_success(monkeypatch):
    import deep_translator

    class FakeGT:
        def __init__(self, source, target):
            pass

        def translate(self, text):
            return "traducido"

    monkeypatch.setattr(deep_translator, "GoogleTranslator", FakeGT)
    assert td._translate_google("hello") == "traducido"


def test_translate_deepl_empty_raises():
    class FakeR:
        text = ""

    class FakeT:
        def translate_text(self, text, target_lang):
            return FakeR()

    with pytest.raises(td.TranslationError):
        td._translate_deepl("hola", FakeT())


def test_translate_deepl_exception_wrapped():
    class FakeT:
        def translate_text(self, text, target_lang):
            raise RuntimeError("boom")

    with pytest.raises(td.TranslationError):
        td._translate_deepl("hola", FakeT())


def test_translate_deepl_success():
    class FakeR:
        text = "traducido"

    class FakeT:
        def translate_text(self, text, target_lang):
            return FakeR()

    assert td._translate_deepl("hola", FakeT()) == "traducido"


# ---------------------------------------------------------------------------
# Cambio 1 — fallo de API ≠ ya-ES (translate_to_es)
# ---------------------------------------------------------------------------

def test_translate_to_es_all_services_fail(monkeypatch):
    monkeypatch.setattr(td, "_translate_google", _google_raises())
    res = td.translate_to_es(EN, None, sleep_secs=0)
    assert res.status == td._ST_FAILED
    assert res.service == "google"
    assert res.error  # mensaje presente para el log


def test_translate_to_es_deepl_fails_falls_back_to_google(monkeypatch):
    monkeypatch.setattr(td, "_translate_deepl", _deepl_raises())
    monkeypatch.setattr(td, "_translate_google", _google_returns("Edición especial."))
    res = td.translate_to_es(EN, object(), sleep_secs=0)  # deepl_translator truthy
    assert res.status == td._ST_TRANSLATED
    assert res.service == "google"
    assert res.text == "Edición especial."


def test_translate_to_es_already_spanish_skips_api(monkeypatch):
    called = {"n": 0}

    def _boom(text):
        called["n"] += 1
        return "no debería llamarse"

    monkeypatch.setattr(td, "_translate_google", _boom)
    res = td.translate_to_es(ES, None, sleep_secs=0)
    assert res.status == td._ST_ALREADY_ES
    assert res.text == ""
    assert called["n"] == 0  # no se gasta API con español


def test_translate_to_es_success(monkeypatch):
    monkeypatch.setattr(td, "_translate_google", _google_returns("Una traducción real."))
    res = td.translate_to_es(EN, None, sleep_secs=0)
    assert res.status == td._ST_TRANSLATED
    assert res.text == "Una traducción real."
    assert res.service == "google"


# ---------------------------------------------------------------------------
# Cambio 5 — no-op barato (API devuelve texto idéntico módulo espacios)
# ---------------------------------------------------------------------------

def test_translate_to_es_noop_identical_text(monkeypatch):
    # Google devuelve el mismo texto (con espacios distintos) → ya estaba en destino
    monkeypatch.setattr(td, "_translate_google", _google_returns("   " + EN + "  \n "))
    res = td.translate_to_es(EN, None, sleep_secs=0)
    assert res.status == td._ST_ALREADY_ES
    assert res.text == ""


# ---------------------------------------------------------------------------
# Cambio 1 + 2 — translate_item: escribe/omite key y hash según status
# ---------------------------------------------------------------------------

def test_translate_item_api_failure_does_not_write_key(monkeypatch):
    monkeypatch.setattr(td, "_translate_google", _google_raises())
    result, translated, already_es, failures = td.translate_item(
        {"description": EN}, None, force=False, sleep_secs=0
    )
    assert "description_es" not in result
    assert "description_es_src_hash" not in result
    assert translated == 0
    assert len(failures) == 1
    assert failures[0]["field"] == "description"
    assert failures[0]["service"] == "google"
    assert failures[0]["error"]


def test_translate_item_extra_failure_does_not_write_key(monkeypatch):
    monkeypatch.setattr(td, "_translate_google", _google_raises())
    item = {"extras": [{"description": EN}]}
    result, translated, already_es, failures = td.translate_item(
        item, None, force=False, sleep_secs=0
    )
    ex = result["extras"][0]
    assert "description_es" not in ex
    assert "description_es_src_hash" not in ex
    assert len(failures) == 1
    assert failures[0]["field"] == "extras[0]"


def test_translate_item_translated_writes_text_and_hash(monkeypatch):
    monkeypatch.setattr(td, "_translate_google", _google_returns("Edición especial de coleccionista."))
    result, translated, already_es, failures = td.translate_item(
        {"description": EN}, None, force=False, sleep_secs=0
    )
    assert result["description_es"] == "Edición especial de coleccionista."
    assert result["description_es_src_hash"] == _sha12(EN)
    assert translated == 1
    assert already_es == 0
    assert not failures


def test_translate_item_already_es_writes_empty_and_hash():
    result, translated, already_es, failures = td.translate_item(
        {"description": ES}, None, force=False, sleep_secs=0
    )
    assert result["description_es"] == ""
    assert result["description_es_src_hash"] == _sha12(ES)
    assert already_es == 1
    assert translated == 0
    assert not failures


# ---------------------------------------------------------------------------
# Flag --retry-empty — selección por-campo
# ---------------------------------------------------------------------------

def test_field_should_translate_new_key():
    assert td._field_should_translate({"description": IT}, False, False) is True


def test_field_should_translate_processed_skips():
    assert td._field_should_translate({"description": IT, "description_es": ""}, False, False) is False
    assert td._field_should_translate({"description": IT, "description_es": "algo"}, False, False) is False


def test_field_should_translate_force_reprocesses():
    assert td._field_should_translate({"description": IT, "description_es": "algo"}, True, False) is True


def test_field_should_translate_retry_empty_candidate():
    # description_es="" + description NO española → candidato
    assert td._field_should_translate({"description": IT, "description_es": ""}, False, True) is True


def test_field_should_translate_retry_empty_excludes_spanish():
    # description_es="" pero el original SÍ es español → skip legítimo, no candidato
    assert td._field_should_translate({"description": ES, "description_es": ""}, False, True) is False


def test_field_should_translate_retry_empty_excludes_translated():
    # ya tiene traducción real → --retry-empty no la toca
    assert td._field_should_translate({"description": IT, "description_es": "traducido"}, False, True) is False


def test_field_not_spanish_junk_only_is_false():
    # cleaned queda vacío → no hay qué salvar → no candidato
    assert td._field_not_spanish("Aggiungi alla lista desideri ") is False


def test_needs_translation_retry_empty_item_level():
    item = {"description": IT, "description_es": ""}
    assert td._needs_translation(item, False, False) is False
    assert td._needs_translation(item, False, True) is True


def test_retry_empty_preserves_existing_translation(monkeypatch):
    monkeypatch.setattr(td, "_translate_google", _google_returns("Traducción recuperada."))
    item = {
        "description": IT,                 # falló antes → description_es=""
        "description_es": "",
        "extras": [
            {"description": "Ceci est une histoire de grande qualité.",
             "description_es": "traducción previa buena"},  # ya traducido → intocable
        ],
    }
    result, translated, already_es, failures = td.translate_item(
        item, None, force=False, sleep_secs=0, retry_empty=True
    )
    # el campo fallido se recupera
    assert result["description_es"] == "Traducción recuperada."
    assert result["description_es_src_hash"] == _sha12(IT)
    assert translated == 1
    # la traducción previa del extra queda intacta (no se re-tradujo ni se le puso hash)
    ex = result["extras"][0]
    assert ex["description_es"] == "traducción previa buena"
    assert "description_es_src_hash" not in ex
