"""Tests de los fixes per-fuente del audit 2026-06-10.

Cubre:
- Manga-Sanctuary: mapeo canónico de labels de edición "bare" (Perfect,
  Prestige, limitée…) → frases que detect_signals SÍ reconoce.
- SocialAnime: prezzo "0" / "0.00" / "0,00" / "€0" = precio desconocido → "".
- PRH Comics: release_date con mes abreviado + tabs/newlines embebidos.
- Sumikko: gate anti falso-positivo (marcador de edición FUERA de 『』「」)
  + filtro de títulos junk.
- Manga-Passion: day=null con year/month válidos → release_date "YYYY-MM".
"""

from __future__ import annotations

from scripts.manga_watch import detect_signals


# ---------------------------------------------------------------------------
# FIX 1 — Manga-Sanctuary: canonical edition label mapping
# ---------------------------------------------------------------------------


def test_ms_canonical_edition_phrases_score_positive():
    """Cada frase canónica del mapeo debe levantar señal en detect_signals
    (ése es el punto del mapeo: el label bare 'Prestige' puntúa 0)."""
    from wikis.manga_sanctuary import _EDITION_LABEL_CANONICAL

    assert detect_signals("Prestige")[0] == 0  # el bug original
    for label, phrase in _EDITION_LABEL_CANONICAL.items():
        score, _, _ = detect_signals(phrase)
        assert score > 0, f"frase canónica sin señal: {label!r} → {phrase!r}"


def test_ms_canonical_edition_phrase_lookup():
    from wikis.manga_sanctuary import canonical_edition_phrase

    # Case-insensitive, con strip.
    assert canonical_edition_phrase("Perfect") == "perfect edition"
    assert canonical_edition_phrase("ULTIMATE") == "ultimate edition"
    assert canonical_edition_phrase(" prestige ") == "édition prestige"
    assert canonical_edition_phrase("limitée") == "édition limitée"
    assert canonical_edition_phrase("Limitée") == "édition limitée"
    assert canonical_edition_phrase("unlimited double") == "limited edition"
    assert canonical_edition_phrase("Deluxe") == "deluxe"
    assert canonical_edition_phrase("Collector") == "collector edition"
    # Intégrale = omnibus, fuera de scope (gotcha #18) → sin mapeo.
    assert canonical_edition_phrase("Intégrale") == ""
    # Labels desconocidos → sin mapeo (quedan verbatim en la description).
    assert canonical_edition_phrase("simple") == ""
    assert canonical_edition_phrase("") == ""


def test_ms_parse_post_appends_canonical_phrase_keeps_original_label():
    """El _parse_post appendea la frase canónica SIN reemplazar el label
    original (display no degradado) y el candidate gana señal."""
    from wikis.manga_sanctuary import parse_planning_page

    html = """
    <div class="sortie-date subtitle">mercredi 6 mai 2026</div>
    <div class="post sortie sorties-liste">
      <div class="post-thumbnail">
        <a href="/manga-berserk-vol-1-prestige.html">
          <img src="https://img.sanctuary.fr/objet/300/441375.jpg"/>
        </a>
      </div>
      <div class="post-block">
        <div class="post-title-container">
          <h2 class="post-title"><a href="/manga-berserk-vol-1-prestige.html">Berserk 1</a></h2>
          <span class="sortie-edition">
            <a class="sortie-editeur" href="/editeur/44/">glenat</a> / Prestige
          </span>
        </div>
        <div class="post-meta"><span class="badge_sm">Manga</span></div>
        <div class="affiliation" ean="9791041114405">19,95€</div>
      </div>
    </div>
    """
    cands = parse_planning_page(html)
    assert len(cands) == 1
    c = cands[0]
    assert "Prestige" in c.description          # label original conservado
    assert "édition prestige" in c.description  # frase canónica appendeada
    score, _, _ = detect_signals(f"{c.title}\n{c.description}")
    assert score > 0


def test_ms_parse_post_does_not_duplicate_when_label_is_canonical():
    """Si el label YA es la frase canónica (p.ej. 'deluxe'), no se duplica."""
    from wikis.manga_sanctuary import parse_planning_page

    html = """
    <div class="sortie-date subtitle">mercredi 6 mai 2026</div>
    <div class="post sortie sorties-liste">
      <div class="post-block">
        <div class="post-title-container">
          <h2 class="post-title"><a href="/manga-x-vol-2-deluxe.html">Some Manga 2</a></h2>
          <span class="sortie-edition">
            <a class="sortie-editeur" href="/editeur/9/">pika</a> / Deluxe
          </span>
        </div>
        <div class="post-meta"><span class="badge_sm">Manga</span></div>
      </div>
    </div>
    """
    cands = parse_planning_page(html)
    assert len(cands) == 1
    assert cands[0].description.lower().count("deluxe") == 1


# ---------------------------------------------------------------------------
# FIX 2 — SocialAnime: precios ELIMINADOS del pipeline (decisión 2026-06-11,
# architecture.md). Los tests de _normalize_price se removieron junto con la
# función; este guard fija que `prezzo` NUNCA llegue al Candidate.
# ---------------------------------------------------------------------------


def test_sa_parse_feed_item_never_captures_price():
    from wikis import socialanime as sa

    item = {
        "nome": "Berserk Collection Serie Nera 1 Variant",
        "link": "https://www.amazon.it/dp/8828766397",
        "prezzo": "12,90",
        "editore": "Panini",
        "PublicationDate": "10 Oct 2026",
    }
    cand = sa.parse_feed_item(item, "variant")
    assert cand is not None
    assert cand.price == ""


# ---------------------------------------------------------------------------
# FIX 3 — PRH Comics: fecha con mes abreviado + tabs embebidos
# ---------------------------------------------------------------------------


def test_prh_parse_release_date_abbreviated_month_with_tabs():
    from wikis.prhcomics import _parse_release_date

    # El HTML real renderiza tabs/newlines embebidos + mes abreviado.
    assert _parse_release_date("On sale \t\t\t\tNov 22, 2022") == "2022-11-22"
    assert _parse_release_date("On sale\n\t Jun 3, 2025") == "2025-06-03"


def test_prh_parse_release_date_full_month_still_works():
    from wikis.prhcomics import _parse_release_date

    assert _parse_release_date("On sale May 19, 2026") == "2026-05-19"
    assert _parse_release_date("On sale November 22, 2022") == "2022-11-22"


def test_prh_parse_release_date_month_year_fallback_and_garbage():
    from wikis.prhcomics import _parse_release_date

    assert _parse_release_date("May 2026") == "2026-05-01"
    assert _parse_release_date("Nov 2026") == "2026-11-01"
    assert _parse_release_date("TBD") == ""
    assert _parse_release_date("") == ""


# ---------------------------------------------------------------------------
# FIX 4 — Sumikko: gate de marcador de edición fuera de 『』「」 + junk
# ---------------------------------------------------------------------------


def test_sk_strip_bracketed_spans():
    from wikis.sumikko import _strip_bracketed_spans

    assert "限定" not in _strip_bracketed_spans("サツジンゲーム『配神限定』 1")
    assert "限定" not in _strip_bracketed_spans("作品「限定くん」 3")
    # Fuera de corchetes se conserva.
    assert "限定版" in _strip_bracketed_spans("魔法使いの嫁 25 限定版")
    # Mixto: el de adentro se va, el de afuera queda.
    out = _strip_bracketed_spans("『配神限定』スピンオフ 特装版")
    assert "配神限定" not in out and "特装版" in out


def test_sk_edition_marker_gate():
    from wikis.sumikko import _has_edition_marker_outside_brackets as gate

    # Falso positivo confirmado del audit: 限定 sólo DENTRO de 『』.
    assert gate("サツジンゲーム『配神限定』 1") is False
    assert gate("サツジンゲーム『配神限定』 2") is False
    # Marcadores reales fuera de corchetes.
    assert gate("魔法使いの嫁 25 特装版") is True
    assert gate("名探偵コナン 108 アクリルスタンド付き") is True
    assert gate("ワンピース 巻百八 BOX入り") is True
    assert gate("画集セット") is True
    # Sin marcador en absoluto.
    assert gate("ただのタイトル 5") is False
    assert gate("") is False


def test_sk_parser_skips_items_without_edition_marker():
    """Un item cuyo único 限定 está dentro de 『』 NO se emite (antes el
    boilerplate de description lo convertía en falso positivo)."""
    from tests.test_extraction import _sumikko_item_block
    from wikis import sumikko as sk

    fp = _sumikko_item_block(isbn="4253334067", title="サツジンゲーム『配神限定』 1")
    assert sk.parse_listing_page(fp) == []

    ok = _sumikko_item_block(isbn="4049211475", title="魔法使いの嫁 25 特装版")
    assert len(sk.parse_listing_page(ok)) == 1


def test_sk_parser_skips_junk_titles():
    """Títulos con <3 caracteres alfanuméricos/CJK son artefactos de
    parsing (p.ej. '>>>>>>&') y se descartan."""
    from tests.test_extraction import _sumikko_item_block
    from wikis import sumikko as sk

    # Junk puro: sin marcador de edición → lo mata el gate de marcador.
    junk = _sumikko_item_block(isbn="4253334067", title=">>>>>>&")
    assert sk.parse_listing_page(junk) == []

    # Junk con marcador pero <3 caracteres de contenido (付き = 2 CJK) →
    # lo mata el filtro de contenido mínimo.
    junk2 = _sumikko_item_block(isbn="4253334067", title=">>>>>>& 付き")
    assert sk.parse_listing_page(junk2) == []


# ---------------------------------------------------------------------------
# FIX 6 — Manga-Passion: day=null → release_date año-mes
# ---------------------------------------------------------------------------


def _mp_item(year, month, day):
    return {
        "id": 12345,
        "title": "Limited Edition",
        "numberDisplay": "1",
        "year": year, "month": month, "day": day,
        "edition": {"title": "Berserk Max", "publishers": [{"name": "Panini"}]},
    }


def test_mp_release_date_year_month_when_day_null():
    from wikis import mangapassion as mp

    cand = mp.parse_volume(_mp_item(2026, 9, None))
    assert cand is not None
    assert cand.release_date == "2026-09"


def test_mp_release_date_full_when_day_present():
    from wikis import mangapassion as mp

    cand = mp.parse_volume(_mp_item(2026, 9, 4))
    assert cand is not None
    assert cand.release_date == "2026-09-04"


def test_mp_release_date_empty_without_month():
    from wikis import mangapassion as mp

    cand = mp.parse_volume(_mp_item(2026, None, None))
    assert cand is not None
    assert cand.release_date == ""
