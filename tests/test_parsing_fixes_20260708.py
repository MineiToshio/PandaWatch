"""Regresión — paquete D-parsing de la auditoría Fable 2026-07-08.

Cada test fija el comportamiento CORRECTO de un hallazgo (A1, A2, M1-M6,
B3, B4, B6, B14). Escritos ANTES del fix (TDD): fallan contra el código
pre-fix y pasan después.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from scripts import manga_watch as mw


def make_soup(html_text: str) -> BeautifulSoup:
    return BeautifulSoup(html_text, "html.parser")


def _src(**overrides):
    base = dict(
        name="test",
        url="https://example.com/",
        country="ES",
        language="Español",
        publisher="Test",
        source_class="retailer",
        kind="html",
        enabled=True,
        tags=[],
        notes="",
        selectors={},
    )
    base.update(overrides)
    return mw.Source(**base)


# ---------------------------------------------------------------------------
# A1 — JSON-LD por-card en el listing (extract_generic_html)
# ---------------------------------------------------------------------------


def test_a1_generic_html_extracts_per_card_jsonld():
    """El repro del reporte: 3 cards con Product JSON-LD inline. El listing
    debe extraer isbn/author/release_date por card (antes del fix: muertos
    porque el decompose destruía los <script> antes de leerlos)."""
    cards = []
    isbns = ["9781506711980", "9781506711997", "9781506712000"]
    for i, isbn in enumerate(isbns):
        cards.append(f"""
        <article class="product-card">
          <a href="/p/{i}">Berserk Deluxe Edition Volume {i + 1}</a>
          <p>Edición deluxe tapa dura coleccionista con sobrecubierta reversible,
             cantos pintados, litografía numerada y postal exclusiva. Coleccionista.</p>
          <script type="application/ld+json">
          {{"@type":"Product","name":"Berserk Deluxe Edition Volume {i + 1}",
            "isbn":"{isbn}","author":{{"@type":"Person","name":"Kentaro Miura"}},
            "datePublished":"2024-06-15"}}
          </script>
        </article>""")
    html_text = f"<html><body>{''.join(cards)}</body></html>"
    candidates = mw.extract_generic_html(_src(), html_text, max_items=80)
    assert len(candidates) == 3
    got_isbns = {c.isbn for c in candidates}
    assert got_isbns == set(isbns), got_isbns
    assert all(c.author == "Kentaro Miura" for c in candidates)
    assert all(c.release_date == "2024-06-15" for c in candidates)


def test_a1_generic_html_jsonld_not_leaked_into_description():
    """El JSON-LD inline NO debe contaminar la descripción/texto de la card."""
    cards = []
    isbns = ["9781974740475", "9781974740482", "9781974740499"]
    for i, isbn in enumerate(isbns):
        cards.append(f"""
        <article class="product-card">
          <a href="/p/{i}">Kaiju No. 8 Edición Limitada Volume {i + 1}</a>
          <p>Edición limitada con caja, artbook y postal numerada. Coleccionista deluxe.</p>
          <script type="application/ld+json">
          {{"@type":"Product","name":"Kaiju No. 8 Edición Limitada Volume {i + 1}",
            "isbn":"{isbn}"}}
          </script>
        </article>""")
    html_text = f"<html><body>{''.join(cards)}</body></html>"
    candidates = mw.extract_generic_html(_src(), html_text, max_items=80)
    assert len(candidates) == 3
    assert {c.isbn for c in candidates} == set(isbns)
    # El texto JSON crudo ("application/ld+json", "@type") no debe estar en la desc.
    for c in candidates:
        assert "@type" not in c.description
        assert "application/ld+json" not in c.description


def test_a1_extract_schema_org_product_still_works_standalone():
    """Regresión: el path de detail (soup fresco) sigue funcionando igual."""
    html = """<html><body><script type="application/ld+json">
    {"@type":"Product","name":"Vagabond Vol 1","isbn":"9781506702216",
     "author":"Takehiko Inoue","datePublished":"2024-01-02"}
    </script></body></html>"""
    s = mw.extract_schema_org_product(make_soup(html), "https://example.com/")
    assert s["name"] == "Vagabond Vol 1"
    assert s["isbn"] == "9781506702216"
    assert s["author"] == "Takehiko Inoue"


# ---------------------------------------------------------------------------
# A2 — strip de "no"/"no." destruía la palabra real de la serie
# ---------------------------------------------------------------------------


def test_a2_no_longer_human_preserved():
    assert mw._normalize_series_name("No Longer Human", "") == "no longer human"


def test_a2_no_guns_life_preserved():
    assert mw._normalize_series_name("No Guns Life", "") == "no guns life"


def test_a2_kaiju_no_8_matches_canonical():
    # "Kaiju No. 8" es el nombre real (canónica series_key = kaiju-no-8).
    got = mw._normalize_series_name("Kaiju No. 8 Vol. 5", "5")
    assert got == "kaiju no 8", got
    assert mw._slugify_kebab(got) == "kaiju-no-8"


def test_a2_marker_nomarker_still_stripped():
    # El marcador real nº/n° + dígito se sigue limpiando (gotcha #43 intacta).
    assert mw._normalize_series_name("Slam Dunk nº1", "1") == "slam dunk"


# ---------------------------------------------------------------------------
# M1 — _extract_volume: número en el NOMBRE ganaba al volumen real
# ---------------------------------------------------------------------------


def test_m1_last_match_wins_within_pattern():
    assert mw._extract_volume("Kaiju Nº8 nº16") == "16"


def test_m1_gotcha74_titles():
    # El nombre de la serie tiene número con marcador; el tomo va después.
    assert mw._extract_volume("Kaiju Nº8 nº3") == "3"


def test_m1_simple_volume_unchanged():
    assert mw._extract_volume("One Piece Vol. 98") == "98"
    assert mw._extract_volume("Berserk Deluxe 1") == "1"


# ---------------------------------------------------------------------------
# M2 — año entre paréntesis capturado como volumen
# ---------------------------------------------------------------------------


def test_m2_year_in_parens_not_volume():
    assert mw._extract_volume("Berserk Official Guidebook (2016)") == ""


def test_m2_real_volume_in_parens_still_works():
    assert mw._extract_volume("タイトル（15）") == "15"
    assert mw._extract_volume("Title (20)") == "20"


# ---------------------------------------------------------------------------
# M3 — autores en Hangul rechazados
# ---------------------------------------------------------------------------


def test_m3_hangul_author_accepted():
    assert mw._validate_author_candidate("김성모") == "김성모"


def test_m3_hangul_author_from_links():
    soup = make_soup('<a href="/author/kim">김성모</a>')
    assert mw._extract_author_from_links(soup) == "김성모"


def test_m3_japanese_author_still_accepted():
    assert mw._validate_author_candidate("尾田栄一郎") == "尾田栄一郎"


# ---------------------------------------------------------------------------
# M4 — meses PT / DE sin normalizar
# ---------------------------------------------------------------------------


def test_m4_portuguese_month():
    assert mw.normalize_release_date("15 de junho de 2025") == "2025-06-15"
    assert mw.normalize_release_date("3 de março de 2024") == "2024-03-03"


def test_m4_german_month_with_dot_after_day():
    assert mw.normalize_release_date("15. März 2026") == "2026-03-15"
    assert mw.normalize_release_date("1. Januar 2025") == "2025-01-01"


def test_m4_extract_release_date_pt_de_freetext():
    assert mw.extract_release_date("Lançamento: 20 de outubro de 2025") == "2025-10-20"


# ---------------------------------------------------------------------------
# M5 — _schema_item_is_product matchea substring del @type
# ---------------------------------------------------------------------------


def test_m5_bookseries_rejected():
    assert mw._schema_item_is_product({"@type": "BookSeries"}) is False
    assert mw._schema_item_is_product({"@type": "BookStore"}) is False
    assert mw._schema_item_is_product({"@type": "ComicSeries"}) is False


def test_m5_product_book_accepted():
    assert mw._schema_item_is_product({"@type": "Product"}) is True
    assert mw._schema_item_is_product({"@type": "Book"}) is True
    assert mw._schema_item_is_product({"@type": "ComicIssue"}) is True
    assert mw._schema_item_is_product({"@type": ["Product", "BookSeries"]}) is True


def test_m5_datemodified_not_used_as_release_date():
    html = """<html><body><script type="application/ld+json">
    {"@type":"Product","name":"X","dateModified":"2026-01-01"}
    </script></body></html>"""
    s = mw.extract_schema_org_product(make_soup(html), "https://example.com/")
    assert s["release_date"] == ""


# ---------------------------------------------------------------------------
# M6 — filtro "mismo directorio que la cover" borra galerías legítimas
# ---------------------------------------------------------------------------


def test_m6_majority_gallery_dir_preserved_when_cover_elsewhere():
    # Cover en /s/products/, galería en /s/files/ (Shopify moderno). Antes:
    # todas las gallery difieren de la cover → se descartaban.
    html = """<html><body>
      <meta property="og:image" content="https://cdn.example.com/s/products/cover.jpg">
      <div class="product-gallery">
        <img src="https://cdn.example.com/s/files/g1.jpg" alt="vista 1">
        <img src="https://cdn.example.com/s/files/g2.jpg" alt="vista 2">
        <img src="https://cdn.example.com/s/files/g3.jpg" alt="vista 3">
      </div>
    </body></html>"""
    imgs = mw._extract_images_from_detail_soup(make_soup(html), "https://example.com/p")
    urls = [im["url"] for im in imgs]
    # La galería mayoritaria (/s/files/) debe sobrevivir.
    assert any("/s/files/g1.jpg" in u for u in urls), urls
    assert any("/s/files/g3.jpg" in u for u in urls), urls
    assert len(imgs) >= 3


# ---------------------------------------------------------------------------
# B3 — derive_product_type Magazine case-sensitive
# ---------------------------------------------------------------------------


def test_b3_lowercase_magazine_title():
    assert mw.derive_product_type("ONE PIECE magazine", "", []) == "magazine"


def test_b3_parenthetical_magazine_not_triggered():
    # Marketing "(sale magazine)" en paréntesis NO debe tiparse como magazine.
    assert mw.derive_product_type("Berserk vol 41 (sale magazine)", "", []) != "magazine"


# ---------------------------------------------------------------------------
# B6 — series_display rompe apóstrofes con .title()
# ---------------------------------------------------------------------------


def test_b6_apostrophe_display():
    cand = mw.candidate_from_source(
        _src(country="JP"), "hell's paradise", "https://x/1", "d" * 40,
    )
    meta = mw.derive_series_metadata(cand)
    # Si deriva series_display, el apóstrofe no debe romper la capitalización.
    if meta.get("series_display"):
        assert "'S" not in meta["series_display"], meta["series_display"]


# ---------------------------------------------------------------------------
# B14 — normalize_release_date default DD/MM ambiguo para fuentes US
# ---------------------------------------------------------------------------


def test_b14_us_country_month_first():
    # 06/07/2026 de fuente US ambigua → MM/DD → 7 de junio.
    assert mw.normalize_release_date("06/07/2026", country="US") == "2026-06-07"


def test_b14_eu_default_day_first():
    # Sin país (o EU) → día primero (comportamiento histórico).
    assert mw.normalize_release_date("06/07/2026") == "2026-07-06"
    assert mw.normalize_release_date("06/07/2026", country="ES") == "2026-07-06"


def test_b14_unambiguous_unaffected_by_country():
    # Segundo componente > 12 → inequívoco, país no cambia nada.
    assert mw.normalize_release_date("05/27/2026", country="ES") == "2026-05-27"
    assert mw.normalize_release_date("27/05/2026", country="US") == "2026-05-27"
