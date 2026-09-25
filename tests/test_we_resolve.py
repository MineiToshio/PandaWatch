"""Tests para scripts/retrofit/we_resolve.py — resolución determinista del
Step 2 del skill /watch-whakoom-covers.

Cobertura:
  1. Match exacto (editorial + idioma + total_tomos) → resuelto, candidate_urls
     con la imagen del tomo correcto.
  2. Publisher distinto → no resuelve (publisher_mismatch).
  3. Idioma distinto de "Spanish (Spain)" → no resuelve (language_mismatch).
  4. total_tomos no coincide → no resuelve (total_tomos_mismatch).
  5. Ediciones hermanas ambiguas (misma editorial+país, sin total_tomos local
     para desambiguar) → no resuelve (ambiguous_no_total_tomos).
  6. Dos candidatas pasan todos los filtros → ambiguo (ambiguous_multiple_editions).
  7. Tomo fuera de rango / no listado → no resuelve (volume_not_listed).
  8. Oneshot: item sin volumen + edición con un único tomo → resuelve; con
     varios tomos y sin volumen declarado → no resuelve.
  9. Reescritura /small|thumb|medium/ → /large/ la hace sc_validate.py (no
     este script) — we_resolve.py sólo pasa la URL cruda de whakoom.
  10. Caché: cada resolución (exitosa o no) se apendea a
      data/whakoom_edition_map.jsonl con el `method` correcto.
  11. normalize_publisher / publisher_matches — casos reales.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for p in (_ROOT / "scripts", _ROOT / "scripts" / "retrofit"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import we_resolve  # type: ignore


def _item(**extra) -> dict:
    it = {
        "slug": "dragon-ball-planeta-es-3",
        "title": "Dragon Ball 3",
        "series_display": "Dragon Ball",
        "series_key": "dragon-ball",
        "publisher": "Planeta Cómic",
        "country": "España",
        "volume": "3",
    }
    it.update(extra)
    return it


def _edition(**extra) -> dict:
    ed = {
        "edition_id": 1001,
        "edition_url": "https://www.whakoom.com/ediciones/1001/dragon-ball",
        "title": "Dragon Ball",
        "publisher": "Planeta Cómic",
        "language": "Spanish (Spain)",
        "formato": "Rústica con sobrecubierta",
        "total_tomos": 25,
        "other_editions": [],
        "volumes": [
            {"n": "1", "img_url": "https://i1.whakoom.com/small/aa/bb/hash1.jpg"},
            {"n": "2", "img_url": "https://i1.whakoom.com/small/aa/bb/hash2.jpg"},
            {"n": "3", "img_url": "https://i1.whakoom.com/small/aa/bb/hash3.jpg"},
        ],
    }
    ed.update(extra)
    return ed


# ── 1. Match exacto ──────────────────────────────────────────────────────────

def test_resolves_exact_match():
    item = _item()
    listado = {"coleccion_id": 1832, "total_tomos": 25, "formato": ""}
    result = we_resolve.resolve_candidates(item, listado, [_edition()])
    assert result["resolved"] is True
    assert result["edition_id"] == 1001
    assert len(result["candidate_urls"]) == 1
    cand = result["candidate_urls"][0]
    assert cand["url"] == "https://i1.whakoom.com/small/aa/bb/hash3.jpg"
    assert cand["domain"] == "whakoom.com"
    assert "Dragon Ball" in cand["page_title"]
    assert "#3" in cand["page_title"]


# ── 2. Publisher distinto ────────────────────────────────────────────────────

def test_publisher_mismatch_not_resolved():
    item = _item(publisher="Norma Editorial")
    listado = {"coleccion_id": 1, "total_tomos": 25}
    result = we_resolve.resolve_candidates(item, listado, [_edition(publisher="Ivrea")])
    assert result["resolved"] is False
    assert result["reason"] == "publisher_mismatch"


# ── 3. Idioma distinto ───────────────────────────────────────────────────────

def test_language_mismatch_not_resolved():
    item = _item()
    listado = {"coleccion_id": 1, "total_tomos": 25}
    result = we_resolve.resolve_candidates(item, listado, [_edition(language="English (United States)")])
    assert result["resolved"] is False
    assert result["reason"] == "language_mismatch"


# ── 4. total_tomos no coincide ───────────────────────────────────────────────

def test_total_tomos_mismatch_not_resolved():
    item = _item()
    listado = {"coleccion_id": 1, "total_tomos": 25}
    result = we_resolve.resolve_candidates(item, listado, [_edition(total_tomos=42)])
    assert result["resolved"] is False
    assert result["reason"] == "total_tomos_mismatch"


# ── 5. Ambiguo sin total_tomos local ────────────────────────────────────────

def test_ambiguous_without_local_total_tomos():
    item = _item()
    listado = {"coleccion_id": 1, "total_tomos": None}
    sibling = {"language": "Spanish (Spain)", "publisher": "Planeta Cómic", "total_tomos": 25}
    result = we_resolve.resolve_candidates(
        item, listado, [_edition(other_editions=[sibling])],
    )
    assert result["resolved"] is False
    assert result["reason"] == "ambiguous_no_total_tomos"


def test_resolves_without_local_total_tomos_when_no_sibling():
    item = _item()
    listado = {"coleccion_id": 1, "total_tomos": None}
    result = we_resolve.resolve_candidates(item, listado, [_edition(other_editions=[])])
    assert result["resolved"] is True


# ── 6. Dos candidatas pasan todos los filtros ───────────────────────────────

def test_two_passing_candidates_is_ambiguous():
    item = _item()
    listado = {"coleccion_id": 1, "total_tomos": 25}
    ed1 = _edition(edition_id=1)
    ed2 = _edition(edition_id=2, edition_url="https://www.whakoom.com/ediciones/2/dragon-ball-b")
    result = we_resolve.resolve_candidates(item, listado, [ed1, ed2])
    assert result["resolved"] is False
    assert result["reason"] == "ambiguous_multiple_editions"


# ── 7. Tomo fuera de rango / no listado ─────────────────────────────────────

def test_volume_not_listed():
    item = _item(volume="99")
    listado = {"coleccion_id": 1, "total_tomos": 25}
    result = we_resolve.resolve_candidates(item, listado, [_edition()])
    assert result["resolved"] is False
    assert result["reason"] == "volume_not_listed"
    assert result["candidate_urls"] == []


# ── 8. Oneshot ───────────────────────────────────────────────────────────────

def test_oneshot_single_volume_resolves():
    item = _item(volume="")
    listado = {"coleccion_id": 1, "total_tomos": 1}
    ed = _edition(total_tomos=1, volumes=[{"n": "", "img_url": "https://i1.whakoom.com/small/x/y/z.jpg"}])
    result = we_resolve.resolve_candidates(item, listado, [ed])
    assert result["resolved"] is True
    assert result["candidate_urls"][0]["url"] == "https://i1.whakoom.com/small/x/y/z.jpg"


def test_oneshot_multi_volume_ambiguous_no_volume_declared():
    item = _item(volume="")
    listado = {"coleccion_id": 1, "total_tomos": 25}
    result = we_resolve.resolve_candidates(item, listado, [_edition()])
    assert result["resolved"] is False
    assert result["reason"] == "volume_not_listed"


# ── 9. sc_validate.py hace el upgrade a /large/, no we_resolve.py ──────────

def test_candidate_url_is_raw_not_upgraded():
    item = _item()
    listado = {"coleccion_id": 1, "total_tomos": 25}
    result = we_resolve.resolve_candidates(item, listado, [_edition()])
    assert "/small/" in result["candidate_urls"][0]["url"]


# ── 10. Caché ────────────────────────────────────────────────────────────────

def test_cache_row_written_on_resolve(tmp_path):
    cache_path = tmp_path / "whakoom_edition_map.jsonl"
    item = _item()
    listado = {"coleccion_id": 1832, "total_tomos": 25, "formato": "Rústica"}
    result = we_resolve.resolve_candidates(item, listado, [_edition()])
    we_resolve.append_cache_row(cache_path, item=item, listado=listado, result=result)
    rows = [json.loads(l) for l in cache_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["listado_coleccion_id"] == 1832
    assert row["method"] == "whakoom_edicion_page"
    assert row["whakoom_edition_url"] == "https://www.whakoom.com/ediciones/1001/dragon-ball"
    assert row["series_key"] == "dragon-ball"


def test_cache_row_written_on_failure_with_reason_as_method(tmp_path):
    cache_path = tmp_path / "whakoom_edition_map.jsonl"
    item = _item(publisher="Norma Editorial")
    listado = {"coleccion_id": 1, "total_tomos": 25}
    result = we_resolve.resolve_candidates(item, listado, [_edition(publisher="Ivrea")])
    we_resolve.append_cache_row(cache_path, item=item, listado=listado, result=result)
    rows = [json.loads(l) for l in cache_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert rows[0]["method"] == "publisher_mismatch"
    assert rows[0]["whakoom_edition_url"] == ""


def test_cache_append_only_multiple_rows(tmp_path):
    cache_path = tmp_path / "whakoom_edition_map.jsonl"
    item = _item()
    listado = {"coleccion_id": 1832, "total_tomos": 25}
    result = we_resolve.resolve_candidates(item, listado, [_edition()])
    we_resolve.append_cache_row(cache_path, item=item, listado=listado, result=result)
    we_resolve.append_cache_row(cache_path, item=item, listado=listado, result=result)
    rows = cache_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2


# ── 11. normalize_publisher / publisher_matches ─────────────────────────────

def test_normalize_publisher_strips_accents_and_stopwords():
    assert we_resolve.normalize_publisher("Editorial Ivrea España") == "ivrea"
    assert we_resolve.normalize_publisher("Planeta Cómic") == "planeta"  # "comic" es stopword genérica


def test_publisher_matches_by_containment():
    assert we_resolve.publisher_matches("Ivrea", "Editorial Ivrea España")
    assert we_resolve.publisher_matches("Norma Editorial", "Norma")
    assert not we_resolve.publisher_matches("Ivrea", "Panini Manga España")


def test_is_spanish_spain():
    assert we_resolve.is_spanish_spain("Spanish (Spain)")
    assert not we_resolve.is_spanish_spain("Spanish (Argentina)")
    assert not we_resolve.is_spanish_spain("English (United States)")
    assert not we_resolve.is_spanish_spain("")


def test_is_spanish_spain_locale_es_ui():
    """Whakoom en www.whakoom.com (locale ES) muestra 'Español (España)', no
    'Spanish (Spain)' — verificado en vivo en el piloto real, 2026-09-02."""
    assert we_resolve.is_spanish_spain("Español (España)")
    assert not we_resolve.is_spanish_spain("Español (Argentina)")
    assert not we_resolve.is_spanish_spain("Catalán (España)")
    assert not we_resolve.is_spanish_spain("Inglés (Estados Unidos)")


# ── main() / CLI ─────────────────────────────────────────────────────────────

def test_main_input_not_found(tmp_path, capsys):
    rc = we_resolve.main([str(tmp_path / "nonexistent.json"), "--no-cache-write"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["resolved"] is False
    assert "not found" in out["reason"]


def test_main_end_to_end(tmp_path, capsys):
    inp = tmp_path / "input.json"
    inp.write_text(json.dumps({
        "item": _item(),
        "listado": {"coleccion_id": 1832, "total_tomos": 25},
        "candidates": [_edition()],
    }), encoding="utf-8")
    cache_path = tmp_path / "cache.jsonl"
    rc = we_resolve.main([str(inp), "--cache", str(cache_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["resolved"] is True
    assert cache_path.exists()


# ── Fixtures reales (anonimizadas) ──────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures" / "whakoom"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_fixture_dragon_ball_resolves_with_matching_total_tomos():
    edition = _load_fixture("edition_dragon_ball_es.json")
    item = {
        "slug": "dragon-ball-planeta-es-7",
        "series_display": "Dragon Ball",
        "series_key": "dragon-ball",
        "publisher": "Planeta Cómic",
        "country": "España",
        "volume": "7",
    }
    listado = {"coleccion_id": 1832, "total_tomos": 34, "formato": ""}
    result = we_resolve.resolve_candidates(item, listado, [edition])
    assert result["resolved"] is True
    assert result["candidate_urls"][0]["url"].endswith(
        "aa22bb33cc44dd55ee66ff77aa88bb99.jpg"  # tomo n=7 en el fixture
    )


def test_fixture_dragon_ball_english_sibling_does_not_confuse_resolution():
    """La edición hermana en inglés (misma cantidad de tomos, publisher
    distinto) del fixture NO debe poder resolverse para un item ES — sólo se
    pasó la edición ES como candidata abierta, así que esto sólo confirma que
    el fixture completo (con su other_editions) no producer ambigüedad falsa."""
    edition = _load_fixture("edition_dragon_ball_es.json")
    item = {
        "slug": "dragon-ball-planeta-es-1",
        "series_display": "Dragon Ball",
        "publisher": "Planeta Cómic",
        "country": "España",
        "volume": "1",
    }
    listado = {"coleccion_id": 1832, "total_tomos": 34}
    result = we_resolve.resolve_candidates(item, listado, [edition])
    assert result["resolved"] is True


def test_fixture_berserk_deluxe_resolves_when_total_tomos_matches():
    edition = _load_fixture("edition_berserk_es_deluxe.json")
    item = {
        "slug": "berserk-ivrea-deluxe-es-1",
        "series_display": "Berserk Deluxe",
        "publisher": "Ivrea",
        "country": "España",
        "volume": "1",
    }
    # El corpus local sólo tiene 13 tomos ingestados de la deluxe -> coincide
    # con total_tomos=13 de la edición deluxe (no con los 42 de la hermana
    # regular, que ni siquiera se pasa como candidata abierta acá).
    listado = {"coleccion_id": 5959, "total_tomos": 13}
    result = we_resolve.resolve_candidates(item, listado, [edition])
    assert result["resolved"] is True
    assert result["edition_id"] == 700456


def test_fixture_berserk_deluxe_ambiguous_without_local_total_tomos():
    """Sin total_tomos local para desambiguar, la hermana ES del mismo
    publisher en other_editions vuelve el caso ambiguo (no se resuelve a
    ciegas entre deluxe y regular)."""
    edition = _load_fixture("edition_berserk_es_deluxe.json")
    item = {
        "slug": "berserk-ivrea-deluxe-es-1",
        "series_display": "Berserk Deluxe",
        "publisher": "Ivrea",
        "country": "España",
        "volume": "1",
    }
    listado = {"coleccion_id": 5959, "total_tomos": None}
    result = we_resolve.resolve_candidates(item, listado, [edition])
    assert result["resolved"] is False
    assert result["reason"] == "ambiguous_no_total_tomos"


# ── 12. Endurecimiento #1 (tanda 3): total_tomos con serie "ongoing" ────────

def test_ongoing_listado_accepts_whakoom_total_greater_or_equal():
    """`listado.ongoing=True` (serie en curso según listadomanga_meta remota)
    acepta `cand.total_tomos >= listado.total_tomos` en vez de igualdad
    estricta — caso real tanda 2: Shangri-La Frontier whakoom=11 vs
    heurístico local=27 (whakoom por delante), o el patrón inverso (whakoom
    detrás, gotcha #183 'Berserk Master Edition')."""
    item = _item()
    listado = {"coleccion_id": 1, "total_tomos": 8, "ongoing": True}
    result = we_resolve.resolve_candidates(item, listado, [_edition(total_tomos=11)])
    assert result["resolved"] is True


def test_ongoing_candidate_accepts_greater_total_even_if_listado_not_flagged():
    """El lado whakoom también puede declararse 'ongoing' (edición en curso
    con contador propio adelantado/atrasado) — basta que UNO de los dos lados
    esté en curso para relajar a `>=`."""
    item = _item()
    listado = {"coleccion_id": 1, "total_tomos": 8, "ongoing": False}
    result = we_resolve.resolve_candidates(item, listado, [_edition(total_tomos=11, ongoing=True)])
    assert result["resolved"] is True


def test_ongoing_still_rejects_when_whakoom_total_is_lower():
    """`>=` no es `!=` — si whakoom declara MENOS tomos que listadomanga
    (aun en curso), sigue sin resolver (whakoom no puede tener menos tomos
    reales que los ya publicados según listadomanga)."""
    item = _item()
    listado = {"coleccion_id": 1, "total_tomos": 20, "ongoing": True}
    result = we_resolve.resolve_candidates(item, listado, [_edition(total_tomos=11)])
    assert result["resolved"] is False
    assert result["reason"] == "total_tomos_mismatch"


def test_not_ongoing_keeps_strict_equality():
    """Sin ninguna señal de 'ongoing', se mantiene la igualdad estricta de
    siempre (no relaja el criterio para series cerradas)."""
    item = _item()
    listado = {"coleccion_id": 1, "total_tomos": 8, "ongoing": False}
    result = we_resolve.resolve_candidates(item, listado, [_edition(total_tomos=11)])
    assert result["resolved"] is False
    assert result["reason"] == "total_tomos_mismatch"


# ── 13. Endurecimiento #2 (tanda 3): guard de reedición ─────────────────────

def test_reedition_guard_blocks_oneshot_format_mismatch():
    """Oneshot (total_tomos==1) cuyo slug declara 'cartone_1282_pp' pero
    listadomanga (remoto) dice 'Rústica' + 240 páginas — formato
    inconsistente, no resuelve (mismo patrón que el caso real
    sensor-ecc-deluxe-es de la curación tanda 1)."""
    item = _item(volume="")
    listado = {"coleccion_id": 1, "total_tomos": 1, "formato": "Rústica con sobrecubierta", "paginas": "240 páginas en B/N"}
    ed = _edition(
        total_tomos=1,
        edition_url="https://www.whakoom.com/ediciones/700456/sensor-cartone_1282_pp",
        volumes=[{"n": "", "img_url": "https://i1.whakoom.com/small/x/y/z.jpg"}],
    )
    result = we_resolve.resolve_candidates(item, listado, [ed])
    assert result["resolved"] is False
    assert result["reason"] == "reedition_format_mismatch"


def test_reedition_guard_allows_oneshot_format_match():
    """Mismo caso pero con formato+páginas CONSISTENTES entre el slug
    whakoom y la ficha remota de listadomanga — resuelve normalmente."""
    item = _item(volume="")
    listado = {"coleccion_id": 1, "total_tomos": 1, "formato": "Rústica con sobrecubierta", "paginas": "240 páginas en B/N"}
    ed = _edition(
        total_tomos=1,
        edition_url="https://www.whakoom.com/ediciones/700456/sensor-rustica_240_pp",
        volumes=[{"n": "", "img_url": "https://i1.whakoom.com/small/x/y/z.jpg"}],
    )
    result = we_resolve.resolve_candidates(item, listado, [ed])
    assert result["resolved"] is True


def test_reedition_guard_ambiguous_sibling_without_enough_data():
    """Oneshot con una hermana ES del MISMO publisher y MISMO total_tomos
    (reedición plausible), pero el slug whakoom no trae el patrón
    `_NNN_pp` (sin datos suficientes para comparar formato/páginas) → no
    se resuelve a ciegas (`ambiguous_sibling_same_publisher`)."""
    item = _item(volume="")
    listado = {"coleccion_id": 1, "total_tomos": 1, "formato": "Rústica", "paginas": "240 páginas en B/N"}
    # Publisher de la hermana debe coincidir con el de la CANDIDATA (Planeta
    # Cómic, default de _edition()), no con el del item.
    sibling = {"language": "Spanish (Spain)", "publisher": "Planeta Cómic", "total_tomos": 1}
    ed = _edition(
        total_tomos=1,
        edition_url="https://www.whakoom.com/ediciones/700456/sensor-reedicion",  # sin _NNN_pp
        other_editions=[sibling],
        volumes=[{"n": "", "img_url": "https://i1.whakoom.com/small/x/y/z.jpg"}],
    )
    result = we_resolve.resolve_candidates(item, listado, [ed])
    assert result["resolved"] is False
    assert result["reason"] == "ambiguous_sibling_same_publisher"


def test_reedition_guard_does_not_apply_without_oneshot_or_sibling():
    """Edición NO oneshot (total_tomos=25) y sin hermanas del mismo
    publisher+total_tomos — el guard de reedición no aplica, no bloquea
    aunque el slug no tenga el patrón `_NNN_pp`."""
    item = _item()
    listado = {"coleccion_id": 1, "total_tomos": 25, "formato": "", "paginas": ""}
    result = we_resolve.resolve_candidates(item, listado, [_edition(total_tomos=25, other_editions=[])])
    assert result["resolved"] is True


def test_slug_format_pages_helper():
    assert we_resolve._slug_format_pages(
        "https://www.whakoom.com/ediciones/1/sensor-rustica_240_pp"
    ) == ("rustica", 240)
    assert we_resolve._slug_format_pages(
        "https://www.whakoom.com/ediciones/2/sunny-cartone_1282_pp"
    ) == ("cartone", 1282)
    assert we_resolve._slug_format_pages(
        "https://www.whakoom.com/ediciones/3/frankenstein-flexibook_192_pp"
    ) == ("flexibook", 192)
    assert we_resolve._slug_format_pages(
        "https://www.whakoom.com/ediciones/4/no-pattern-here"
    ) == ("", None)


# ── 14. Endurecimiento #3 (tanda 3): publisher por conjunto de tokens ───────

def test_publisher_matches_tolerates_reordered_imprint():
    """Hallazgo tanda 2 (task_07e139d6): imprint co-editado con el orden de
    tokens invertido debe matchear igual (Trigun Maximum, 4 targets
    rechazados por publisher_mismatch sin motivo real)."""
    assert we_resolve.publisher_matches(
        "EDT Editores de Tebeos / Ediciones Glénat",
        "Glénat España - Editores de Tebeos",
    )


def test_publisher_matches_requires_shared_token():
    """Dos publishers sin ningún token en común (tras stopwords) NO
    matchean, aunque ninguno de los conjuntos esté vacío."""
    assert not we_resolve.publisher_matches("Panini Cómic", "Planeta Cómic")


def test_publisher_matches_subset_either_direction():
    assert we_resolve.publisher_matches("Ivrea", "Editorial Ivrea España")
    assert we_resolve.publisher_matches("Editorial Ivrea España", "Ivrea")


def test_normalize_publisher_tokens_strips_accents_and_stopwords():
    assert we_resolve.normalize_publisher_tokens("Editorial Ivrea España") == frozenset({"ivrea"})


# ── 15. Endurecimiento #4 (tanda 3): sibling_urls desde Other Editions ──────

def test_sibling_urls_suggested_on_language_mismatch():
    """Ninguna candidata resuelve por idioma (todas LatAm/otro país), pero
    una de ellas lista en `other_editions[]` una hermana ES-España del MISMO
    publisher CON `edition_url` propia — se sugiere esa URL en
    `sibling_urls` para que el skill la abra sin repetir la búsqueda Bing
    (hallazgo tanda 2: 33 `language_mismatch`, Bing indexa mejor LatAm)."""
    item = _item(publisher="Ivrea")
    listado = {"coleccion_id": 1, "total_tomos": 25}
    latam_edition = _edition(
        language="Spanish (Mexico)",
        other_editions=[{
            "language": "Spanish (Spain)", "publisher": "Ivrea", "total_tomos": 25,
            "edition_url": "https://www.whakoom.com/ediciones/999/dragon-ball-es",
        }],
    )
    result = we_resolve.resolve_candidates(item, listado, [latam_edition])
    assert result["resolved"] is False
    assert result["reason"] == "language_mismatch"
    assert result["sibling_urls"] == ["https://www.whakoom.com/ediciones/999/dragon-ball-es"]


def test_sibling_urls_empty_when_no_es_sibling_listed():
    item = _item(publisher="Ivrea")
    listado = {"coleccion_id": 1, "total_tomos": 25}
    latam_edition = _edition(language="Spanish (Mexico)", other_editions=[])
    result = we_resolve.resolve_candidates(item, listado, [latam_edition])
    assert result["resolved"] is False
    assert result["sibling_urls"] == []


def test_sibling_urls_only_collected_for_language_mismatch_reason():
    """Si el motivo de no-resolución NO es language_mismatch (p.ej.
    publisher_mismatch), no tiene sentido sugerir hermanas por idioma —
    sibling_urls queda vacío aunque hubiera alguna hermana listada."""
    item = _item(publisher="Otro Publisher Inexistente")
    listado = {"coleccion_id": 1, "total_tomos": 25}
    ed = _edition(other_editions=[{
        "language": "Spanish (Spain)", "publisher": "Ivrea", "total_tomos": 25,
        "edition_url": "https://www.whakoom.com/ediciones/999/dragon-ball-es",
    }])
    result = we_resolve.resolve_candidates(item, listado, [ed])
    assert result["resolved"] is False
    assert result["reason"] == "publisher_mismatch"
    assert result["sibling_urls"] == []


def test_resolved_result_always_has_sibling_urls_key():
    item = _item()
    listado = {"coleccion_id": 1, "total_tomos": 25}
    result = we_resolve.resolve_candidates(item, listado, [_edition()])
    assert result["resolved"] is True
    assert result["sibling_urls"] == []
