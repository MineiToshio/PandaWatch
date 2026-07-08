"""WO-1 (auditoría post-scrape, grupo 1): prevención del bug "coleccion=edición
plegaba las variantes ESPECIALES al regular".

Cubre las tres piezas del fix:
  1. `manga_watch._EDITION_TYPE_TERM_RULES` reconoce las FRASES de tipo del título
     (Edición Especial / Especial Limitada / Edición Limitada / Edición de Lujo)
     sin dispararse con "especial" suelto (nombre de serie).
  2. `unify_coleccion_edition` carva esas variantes en su PROPIA edición (edition_key
     con el slug del tipo) en vez de plegarlas al regular — respetando cofre-1ªed=
     regular (bonus suelto NO dispara) y descartando el folleto promocional (gotcha
     #103) — sin tocar el cluster_key, de forma idempotente.
  3. `validate_corpus.SPECIALREG` marca el estado defectuoso (título especial ⇒
     edition_slug regular) y desaparece tras el carve.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import manga_watch as mw
from scripts.retrofit import unify_coleccion_edition as uce
from scripts import validate_corpus as vc


# ---------------------------------------------------------------------------
# 1) edition_slug_from_text — las FRASES de tipo, no "especial" suelto
# ---------------------------------------------------------------------------

def test_edition_slug_from_text_edicion_especial():
    assert mw.edition_slug_from_text("Ataque a los Titanes 34 Edición Especial") == "special"


def test_edition_slug_from_text_especial_limitada_is_limited():
    assert mw.edition_slug_from_text("Capitán Harlock Especial Limitada 1") == "limited"


def test_edition_slug_from_text_edicion_limitada_is_limited():
    assert mw.edition_slug_from_text("El hombre y el gato 1 Edición Limitada") == "limited"


def test_edition_slug_from_text_edicion_especial_limitada_prefers_limited():
    # "Edición Especial Limitada" contiene ambas frases; limited debe ganar
    # (la regla limited va ANTES que la de special en la tabla).
    assert mw.edition_slug_from_text("Serie Edición Especial Limitada") == "limited"


def test_edition_slug_from_text_edicion_de_lujo_is_deluxe():
    assert mw.edition_slug_from_text("Berserk Edición de Lujo 3") == "deluxe"


def test_edition_slug_from_text_especial_suelto_no_dispara():
    # "especial" como parte del NOMBRE (no la frase "edición especial") no debe
    # clasificar el tomo como una edición especial.
    assert mw.edition_slug_from_text("orange Especial 7") == ""
    assert mw.edition_slug_from_text("Especial de Navidad de Kimetsu") == ""


# ---------------------------------------------------------------------------
# 2a) _carve_slug — dispara por la frase de título; respeta cofre-1ªed y promo
# ---------------------------------------------------------------------------

def _lmc_item(title, cole="100", kind="especial", vol="1", price="€ 12,00",
              description="", ek="serie-pub-regular-es"):
    url = f"https://www.listadomanga.es/coleccion.php?id={cole}&item={kind}-{vol}-0af7d478f7"
    return {
        "title": title, "url": url, "volume": vol, "price": price,
        "description": description, "edition_key": ek,
        "cluster_key": f"lmc:{cole}:{mw_canon(kind)}:{vol}",
        "series_key": "serie", "sources": [{"url": url}],
    }


def mw_canon(kind):
    return {"especial": "special", "limitada": "limited"}.get(kind, kind)


def test_carve_slug_special_from_title():
    it = _lmc_item("Serie 34 Edición Especial", kind="especial", vol="34")
    assert uce._carve_slug(it) == "special"


def test_carve_slug_limited_from_title():
    it = _lmc_item("Serie 1 Edición Limitada", kind="limitada", vol="1")
    assert uce._carve_slug(it) == "limited"


def test_carve_slug_cofre_first_edition_stays_regular():
    # Cofre de 1ª edición = regular (regla dura del owner): un "+ Cofre" SIN la
    # frase de tipo de edición NO se carva. lm_kind/cluster regular, título sin
    # "Edición Especial".
    it = _lmc_item("Serie 1 + Cofre", kind="regular", vol="1")
    assert uce._carve_slug(it) is None


def test_carve_slug_bonus_words_without_type_phrase_stay_regular():
    it = _lmc_item("Serie 5 + Lámina + Chapas", kind="regular", vol="5")
    assert uce._carve_slug(it) is None


def test_carve_slug_free_promo_excluded():
    # Folleto promocional gratuito (gotcha #103): aunque el título dijera un tipo,
    # el precio "Número Gratuito" lo deja fuera del carve.
    it = _lmc_item("Serie 1 Edición Especial", kind="especial", price="Número Gratuito")
    assert uce._carve_slug(it) is None


def test_carve_slug_edicion_promocional_desc_excluded():
    it = _lmc_item("Serie 1 Edición Especial", kind="especial", price="€ 0,00",
                   description="Edición Promocional regalada con la revista")
    assert uce._carve_slug(it) is None


def test_carve_slug_edicion_especial_desc_not_confused_with_promocional():
    # "Edición Especial" en la descripción NO es "Edición Promocional": sí se carva.
    it = _lmc_item("Serie 1 Edición Especial", kind="especial",
                   description="Edición Especial + Artbook")
    assert uce._carve_slug(it) == "special"


# ---------------------------------------------------------------------------
# 2b) _carve_ek — namespacea por coleccion
# ---------------------------------------------------------------------------

def test_carve_ek_adds_cole_disambiguator():
    assert uce._carve_ek("serie-norma-regular-es", "special", "3406") == \
        "serie-norma-special-c3406-es"


def test_carve_ek_preserves_existing_disambiguator():
    assert uce._carve_ek("serie-panini-artbook-c4055-es", "special", "4055") == \
        "serie-panini-special-c4055-es"


# ---------------------------------------------------------------------------
# 2c) _kind_of — idempotencia: old-format lee el kind del cluster, no el slug
# ---------------------------------------------------------------------------

def test_kind_of_oldformat_reads_cluster_kind_not_edition_slug():
    # Sin item= en la URL (old-format) y con el edition_slug ya CARVADO a limited,
    # el kind para el cluster debe salir del cluster_key existente (regular), no del
    # slug carvado — esto es lo que hace idempotente el carve.
    it = {"url": "https://www.listadomanga.es/coleccion.php?id=3349",
          "edition_key": "serie-pub-limited-es",
          "cluster_key": "lmc:3349:regular:1"}
    assert uce._kind_of(it) == "regular"


def test_kind_of_newformat_reads_url_item():
    it = {"url": "https://www.listadomanga.es/coleccion.php?id=3349&item=especial-1-abcd1234",
          "edition_key": "serie-pub-regular-es",
          "cluster_key": "lmc:3349:special:1"}
    assert uce._kind_of(it) == "especial"


# ---------------------------------------------------------------------------
# 2d) integración: main() carva, no toca cluster, y es idempotente
# ---------------------------------------------------------------------------

def _write(tmp_path, items):
    p = tmp_path / "items.jsonl"
    p.write_text("\n".join(json.dumps(it, ensure_ascii=False) for it in items) + "\n",
                 encoding="utf-8")
    return p


def _run_main(monkeypatch, path, argv=("prog",)):
    monkeypatch.setattr(uce, "ITEMS", path)
    monkeypatch.setattr("sys.argv", list(argv))
    uce.main()
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_main_carves_special_out_of_regular_base(tmp_path, monkeypatch):
    regular = _lmc_item("Serie 1", cole="100", kind="regular", vol="1",
                        ek="serie-norma-regular-es")
    special = _lmc_item("Serie 1 Edición Especial", cole="100", kind="especial", vol="1",
                        ek="serie-norma-regular-es")
    p = _write(tmp_path, [regular, special])
    out = _run_main(monkeypatch, p)
    by_title = {it["title"]: it for it in out}
    # el tomo regular sigue regular; el especial se carva a su propia edición
    assert by_title["Serie 1"]["edition_key"] == "serie-norma-regular-es"
    assert by_title["Serie 1 Edición Especial"]["edition_key"] == "serie-norma-special-es"
    # el cluster_key NO se toca (sigue namespaceado por la coleccion+kind)
    assert by_title["Serie 1 Edición Especial"]["cluster_key"] == "lmc:100:special:1"
    assert by_title["Serie 1"]["cluster_key"] == "lmc:100:regular:1"


def test_main_cross_coleccion_special_gets_namespaced(tmp_path, monkeypatch):
    # Dos colecciones de la misma serie+publisher, ambas con un especial del vol 1:
    # deben terminar en edition_keys DISTINTOS (coleccion=edición → sin DUPVOL).
    reg_a = _lmc_item("Serie 1", cole="100", kind="regular", vol="1", ek="serie-norma-regular-es")
    sp_a = _lmc_item("Serie 1 Edición Especial", cole="100", kind="especial", vol="1",
                     ek="serie-norma-regular-es")
    sp_b = _lmc_item("Serie Mini libro Edición Especial", cole="200", kind="especial", vol="1",
                     ek="serie-norma-special-es")
    p = _write(tmp_path, [reg_a, sp_a, sp_b])
    out = _run_main(monkeypatch, p)
    eks = {it["title"]: it["edition_key"] for it in out}
    assert eks["Serie Mini libro Edición Especial"] == "serie-norma-special-es"
    assert eks["Serie 1 Edición Especial"] == "serie-norma-special-c100-es"


def test_main_is_idempotent(tmp_path, monkeypatch):
    regular = _lmc_item("Serie 1", cole="100", kind="regular", vol="1", ek="serie-norma-regular-es")
    special = _lmc_item("Serie 1 Edición Especial", cole="100", kind="especial", vol="1",
                        ek="serie-norma-regular-es")
    p = _write(tmp_path, [regular, special])
    _run_main(monkeypatch, p)
    after_1 = p.read_text(encoding="utf-8")
    _run_main(monkeypatch, p)
    after_2 = p.read_text(encoding="utf-8")
    assert after_1 == after_2


# ---------------------------------------------------------------------------
# 3) validate_corpus.SPECIALREG
# ---------------------------------------------------------------------------

def test_specialreg_regex_matches_strong_phrases():
    for t in ["Serie Edición Especial", "Serie Especial Limitada", "Serie Edición Limitada",
              "Serie Edición de Lujo", "Serie Coleccionista", "五等分の花嫁 完全版"]:
        assert vc._SPECIALREG_RE.search(t), t


def test_specialreg_regex_ignores_especial_suelto():
    assert not vc._SPECIALREG_RE.search("orange Especial 7")


def test_specialreg_carved_slugs_include_types():
    assert {"special", "limited", "deluxe", "boxset"} <= vc._CARVED_SLUGS
