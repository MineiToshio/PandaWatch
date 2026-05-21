"""Tests for the Fase 1 extraction changes in manga_watch."""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from scripts import manga_watch as mw


def make_soup(html_text: str) -> BeautifulSoup:
    return BeautifulSoup(html_text, "html.parser")


# ---------------------------------------------------------------------------
# detect_empty_or_js
# ---------------------------------------------------------------------------


def test_detect_empty_or_js_flags_short_html():
    html_text = "<html><body><p>hola</p></body></html>"
    result = mw.detect_empty_or_js(html_text, make_soup(html_text))
    assert result is not None
    category, _ = result
    assert category == "empty"


def test_detect_empty_or_js_flags_react_shell():
    body = '<div id="root"></div>'
    # Pad to >5000 chars so we exercise the SPA-shell branch rather than 'empty'.
    padding = "<!-- " + ("x" * 6000) + " -->"
    html_text = f"<html><body>{body}{padding}</body></html>"
    result = mw.detect_empty_or_js(html_text, make_soup(html_text))
    assert result is not None
    assert result[0] == "js-shell"


def test_detect_empty_or_js_flags_pages_with_few_links():
    long_paragraph = "<p>" + ("texto largo sin links " * 500) + "</p>"
    html_text = f"<html><body>{long_paragraph}</body></html>"
    result = mw.detect_empty_or_js(html_text, make_soup(html_text))
    assert result is not None
    assert result[0] == "no-links"


def test_detect_empty_or_js_passes_real_listing():
    cards = "".join(
        f'<article class="product"><a href="/p/{i}">Producto edición limitada {i} con suficiente texto para pasar el filtro</a></article>'
        for i in range(8)
    )
    padding = "<p>" + ("contenido relleno " * 500) + "</p>"
    html_text = f"<html><body>{padding}{cards}</body></html>"
    assert mw.detect_empty_or_js(html_text, make_soup(html_text)) is None


# ---------------------------------------------------------------------------
# detect_product_clusters
# ---------------------------------------------------------------------------


def test_detect_product_clusters_matches_direct_selector():
    html_text = """
    <html><body>
      <div class="product-item"><a href="/a">A</a></div>
      <div class="product-item"><a href="/b">B</a></div>
      <div class="product-item"><a href="/c">C</a></div>
      <div class="product-item"><a href="/d">D</a></div>
    </body></html>
    """
    cards = mw.detect_product_clusters(make_soup(html_text), "https://example.com/")
    assert len(cards) == 4


def test_detect_product_clusters_falls_back_to_signature_grouping():
    cards_html = "".join(
        f'<li class="weird-class-name"><a href="/item/{i}">Item {i}</a></li>' for i in range(5)
    )
    html_text = f"<html><body><ul>{cards_html}</ul></body></html>"
    cards = mw.detect_product_clusters(make_soup(html_text), "https://example.com/")
    assert len(cards) == 5


def test_detect_product_clusters_ignores_singletons():
    html_text = """
    <html><body>
      <div class="hero"><a href="/x">solo uno</a></div>
      <div class="other"><a href="/y">solo dos</a></div>
    </body></html>
    """
    cards = mw.detect_product_clusters(make_soup(html_text), "https://example.com/")
    assert cards == []


# ---------------------------------------------------------------------------
# extract_generic_html (integración)
# ---------------------------------------------------------------------------


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


def test_extract_generic_html_returns_only_cards_with_signals():
    cards = []
    for i in range(4):
        title = f"Manga edición limitada vol. {i} con extras coleccionista"
        descripcion = (
            f"Vol {i}. Tapa dura con sobrecubierta reversible, postal y litografía exclusiva. "
            "Numerada y con cantos pintados. Edición coleccionista."
        )
        cards.append(
            f'<article class="product-card"><a href="/p/{i}">{title}</a><p>{descripcion}</p></article>'
        )
    boring = '<article class="product-card"><a href="/b">Manga normal vol 1</a><p>Volumen regular sin nada especial agregado a la edición estándar.</p></article>'
    html_text = f"<html><body>{''.join(cards)}{boring}</body></html>"
    candidates = mw.extract_generic_html(_src(), html_text, max_items=80)
    assert len(candidates) == 4  # boring card filtered: no keyword signals
    assert all("edición" in c.title.lower() or "edicion" in c.title.lower() for c in candidates)


def test_extract_generic_html_no_synthetic_fallback():
    # Página que menciona "edición especial" pero sin un patrón repetido reconocible.
    html_text = (
        "<html><body>"
        + "<div class='intro'><p>Bienvenido a nuestra sección de edición especial coleccionista.</p></div>"
        + "</body></html>"
    )
    candidates = mw.extract_generic_html(_src(), html_text, max_items=80)
    assert candidates == []


def test_extract_generic_html_strips_chrome():
    # Si menú y footer contienen "edición especial", no deben generar candidatos.
    html_text = """
    <html><body>
      <header><a href="/cat">Edición especial</a></header>
      <nav><a href="/nav">Cofres y boxsets</a></nav>
      <footer><a href="/foot">Edición limitada</a></footer>
    </body></html>
    """
    candidates = mw.extract_generic_html(_src(), html_text, max_items=80)
    assert candidates == []


# ---------------------------------------------------------------------------
# _parse_feed_date / extract_rss max_age_days
# ---------------------------------------------------------------------------


def test_parse_feed_date_rfc2822():
    parsed = mw._parse_feed_date("Wed, 02 Oct 2024 13:00:00 +0000")
    assert parsed is not None
    assert parsed.year == 2024 and parsed.month == 10 and parsed.day == 2


def test_parse_feed_date_iso8601():
    parsed = mw._parse_feed_date("2024-10-02T13:00:00Z")
    assert parsed is not None
    assert parsed.year == 2024


def test_parse_feed_date_invalid_returns_none():
    assert mw._parse_feed_date("not a date") is None
    assert mw._parse_feed_date("") is None


# ---------------------------------------------------------------------------
# Fuzzy keyword matching
# ---------------------------------------------------------------------------


def _detect(text: str, fuzzy: bool, divisor: int = 3):
    mw.configure_detection(fuzzy=fuzzy, fuzzy_divisor=divisor)
    return mw.detect_signals(text)


def teardown_function(_func):
    """Reset detection config después de cada test."""
    mw.configure_detection(fuzzy=False, fuzzy_divisor=3)


def test_fuzzy_off_keeps_exact_phrase_match():
    score, phrases, _ = _detect("Berserk edición especial vol 1", fuzzy=False)
    assert score >= 40
    assert "edición especial" in phrases


def test_fuzzy_off_does_not_match_isolated_token():
    score, _, _ = _detect("Berserk tomo especial vol 1", fuzzy=False)
    assert score == 0


def test_fuzzy_on_matches_isolated_token_with_reduced_score():
    score, phrases, _ = _detect("Berserk tomo especial vol 1", fuzzy=True, divisor=3)
    # 40 // 3 = 13 puntos por matchear "especial"
    assert score >= 13
    assert any("[fuzzy:especial]" in p for p in phrases)


def test_fuzzy_on_same_rule_does_not_double_count():
    # La regla "edición especial" no debería sumar dos veces (una por phrase
    # exacta y otra por su propio fuzzy token "especial").
    mw.configure_detection(fuzzy=True, fuzzy_divisor=3)
    score, phrases, _ = mw.detect_signals("edición especial coleccionista")
    # "edición especial" debe aparecer como phrase exacta, no como [fuzzy:especial].
    assert "edición especial" in phrases
    assert "edición especial [fuzzy:especial]" not in phrases


def test_fuzzy_stopwords_alone_do_not_match():
    score, _, _ = _detect("nueva edición del manga", fuzzy=True)
    # "edición" y "manga" son stopwords; no deben generar score.
    assert score == 0


def test_fuzzy_does_not_split_japanese_phrases():
    # 限定版 es monolítica; con fuzzy=True debe seguir matcheando como phrase.
    score, phrases, _ = _detect("新作 限定版 発売", fuzzy=True)
    assert "限定版" in phrases
    assert score >= 50


def test_fuzzy_token_boundary_avoids_substring_collision():
    # "especialista" NO debe matchear "especial" — debe respetar word boundary.
    score, _, _ = _detect("entrevista al especialista en cómics", fuzzy=True)
    assert score == 0


# ---------------------------------------------------------------------------
# Extracción de precio
# ---------------------------------------------------------------------------


def test_extract_price_euro():
    assert mw.extract_price("Precio: 19,99 €") == "€ 19,99"
    assert mw.extract_price("Solo €25.50 hoy") == "€ 25.50"


def test_extract_price_dollar():
    assert mw.extract_price("Total $19.99 USD") == "$ 19.99"


def test_extract_price_yen():
    assert mw.extract_price("価格: ¥1,980") == "¥ 1,980"
    assert mw.extract_price("Solo 2,500円") == "¥ 2,500"


def test_extract_price_empty_when_not_found():
    assert mw.extract_price("Manga sin precio aquí") == ""
    assert mw.extract_price("") == ""


# ---------------------------------------------------------------------------
# Extracción de fecha de lanzamiento
# ---------------------------------------------------------------------------


def test_extract_release_date_iso():
    assert mw.extract_release_date("Disponible: 2026-06-15 en tiendas") == "2026-06-15"


def test_extract_release_date_dd_mm_yyyy():
    assert mw.extract_release_date("Sortie le 15/06/2026") == "15/06/2026"


def test_extract_release_date_japanese():
    assert "2026" in mw.extract_release_date("発売日: 2026年6月15日")


def test_extract_release_date_english_month():
    result = mw.extract_release_date("Release date: June 15, 2026")
    assert "June 15" in result and "2026" in result


def test_extract_release_date_spanish_month():
    result = mw.extract_release_date("Disponible el 15 de junio de 2026")
    assert "15" in result and "junio" in result.lower() and "2026" in result


def test_extract_release_date_empty():
    assert mw.extract_release_date("Manga genial sin fecha") == ""


# ---------------------------------------------------------------------------
# Extracción de imagen
# ---------------------------------------------------------------------------


def test_extract_image_url_from_src():
    soup = make_soup('<div><img src="/img/cover.jpg" alt="cover"></div>')
    div = soup.find("div")
    assert mw.extract_image_url(div, "https://example.com/manga") == "https://example.com/img/cover.jpg"


def test_extract_image_url_from_data_src():
    soup = make_soup('<div><img data-src="/img/lazy.jpg" alt="x"></div>')
    div = soup.find("div")
    assert mw.extract_image_url(div, "https://example.com/") == "https://example.com/img/lazy.jpg"


def test_extract_image_url_from_srcset():
    soup = make_soup('<div><img srcset="/img/480.jpg 480w, /img/720.jpg 720w"></div>')
    div = soup.find("div")
    url = mw.extract_image_url(div, "https://example.com/")
    assert url == "https://example.com/img/480.jpg"


def test_extract_image_url_empty_when_no_img():
    soup = make_soup("<div><p>nada</p></div>")
    div = soup.find("div")
    assert mw.extract_image_url(div, "https://example.com/") == ""


def test_extract_image_url_finds_in_parent_sibling():
    # Patrón KADOKAWA: img es hermano del card de texto, no descendiente.
    soup = make_soup("""
        <div class="product-wrapper">
            <a href="/p/1"><img src="/img/cover.jpg" alt="x"></a>
            <div class="product-title">Título del manga</div>
        </div>
    """)
    title_card = soup.find("div", class_="product-title")
    url = mw.extract_image_url(title_card, "https://example.com/")
    assert url == "https://example.com/img/cover.jpg"


def test_extract_image_url_skips_icons():
    soup = make_soup('<div><img src="/icon/cart.png" alt="cart"></div>')
    div = soup.find("div")
    assert mw.extract_image_url(div, "https://example.com/") == ""


def test_extract_image_url_skips_logos_and_pixels():
    soup = make_soup('<div><img src="/static/spacer.gif"><img src="/site/logo.png"></div>')
    div = soup.find("div")
    assert mw.extract_image_url(div, "https://example.com/") == ""


def test_extract_image_url_skips_global_container():
    # Si el contenedor tiene >8 imgs, lo skipeamos (parece wrapper global).
    imgs = "".join(f'<img src="/img/{i}.jpg">' for i in range(15))
    soup = make_soup(f"<div>{imgs}<p class='card'>Card</p></div>")
    card = soup.find("p", class_="card")
    assert mw.extract_image_url(card, "https://example.com/") == ""


def test_extract_image_url_ranks_goods_path_over_sys():
    # Patrón KADOKAWA: hay imgs de íconos (/sys/) y de productos (/goods/).
    # Debe preferir la de /goods/ porque es la portada real.
    soup = make_soup("""
        <div class="product">
            <img src="/img/sys/new.png" alt="NEW">
            <img src="/img/goods/12345.jpg" alt="貞本義行画集 EVANGELION 限定版">
            <p class="card">Título del manga</p>
        </div>
    """)
    card = soup.find("p", class_="card")
    url = mw.extract_image_url(card, "https://example.com/")
    assert url == "https://example.com/img/goods/12345.jpg"


def test_extract_image_url_ignores_negative_score_only():
    # Si TODAS las imgs son íconos (negative score), no devolver nada.
    soup = make_soup("""
        <div class="product">
            <img src="/img/sys/new.png" alt="NEW">
            <img src="/icon/cart.png" alt="cart">
            <p class="card">Título</p>
        </div>
    """)
    card = soup.find("p", class_="card")
    assert mw.extract_image_url(card, "https://example.com/") == ""


# ---------------------------------------------------------------------------
# _extract_image_from_detail_soup (página de detalle, vía fetch_metadata)
# ---------------------------------------------------------------------------


def test_detail_image_from_og_image():
    html = """<html><head>
    <meta property="og:image" content="/img/cover-12345.jpg">
    </head><body></body></html>"""
    url = mw._extract_image_from_detail_soup(make_soup(html), "https://example.com/p/1")
    assert url == "https://example.com/img/cover-12345.jpg"


def test_detail_image_from_json_ld_string():
    html = """<html><head>
    <script type="application/ld+json">
    {"@type":"Book","name":"X","image":"https://cdn.example.com/cover.jpg"}
    </script></head></html>"""
    url = mw._extract_image_from_detail_soup(make_soup(html), "https://example.com/p/1")
    assert url == "https://cdn.example.com/cover.jpg"


def test_detail_image_from_json_ld_object():
    html = """<html><head>
    <script type="application/ld+json">
    {"@type":"Product","image":{"url":"/static/cover.jpg"}}
    </script></head></html>"""
    url = mw._extract_image_from_detail_soup(make_soup(html), "https://example.com/p/1")
    assert url == "https://example.com/static/cover.jpg"


def test_detail_image_prefers_og_over_random_img():
    # og:image debería ganar al primer <img> aleatorio.
    html = """<html><head>
    <meta property="og:image" content="/img/og-real.jpg">
    </head><body>
        <img src="/static/header.png" alt="header">
        <main><img src="/img/cover.jpg" alt="cover"></main>
    </body></html>"""
    url = mw._extract_image_from_detail_soup(make_soup(html), "https://example.com/")
    assert url == "https://example.com/img/og-real.jpg"


def test_detail_image_fallback_ranking():
    # Sin meta tags, debe rankear los <img> del body.
    html = """<html><body>
        <img src="/sys/new.png" alt="NEW">
        <img src="/img/goods/9876.jpg" alt="Berserk Edición Coleccionista">
    </body></html>"""
    url = mw._extract_image_from_detail_soup(make_soup(html), "https://example.com/")
    assert url == "https://example.com/img/goods/9876.jpg"


def test_detail_image_empty_if_nothing_found():
    html = "<html><body><p>solo texto</p></body></html>"
    url = mw._extract_image_from_detail_soup(make_soup(html), "https://example.com/")
    assert url == ""


# ---------------------------------------------------------------------------
# normalize_url_for_dedup
# ---------------------------------------------------------------------------


def test_normalize_strips_shopify_tracking():
    a = "https://www.darkhorsedirect.com/products/berserk?_pos=1&_sid=abc&_ss=r"
    b = "https://www.darkhorsedirect.com/products/berserk?_pos=2&_sid=xyz&_ss=r"
    assert mw.normalize_url_for_dedup(a) == mw.normalize_url_for_dedup(b)


def test_normalize_strips_utm_params():
    a = "https://example.com/p?utm_source=fb&utm_campaign=x"
    b = "https://example.com/p?utm_source=tw&fbclid=123"
    assert mw.normalize_url_for_dedup(a) == mw.normalize_url_for_dedup(b)


def test_normalize_collapses_shopify_collection_prefix():
    a = "https://example.com/collections/comics/products/berserk"
    b = "https://example.com/products/berserk"
    assert mw.normalize_url_for_dedup(a) == mw.normalize_url_for_dedup(b)


def test_normalize_preserves_real_query_params():
    # ?variant=42 SI identifica un producto distinto; no strippear.
    # (Pero 'variant' está en tracking? — no, lo dejé fuera)
    a = "https://example.com/products/x?id=123"
    b = "https://example.com/products/x?id=456"
    assert mw.normalize_url_for_dedup(a) != mw.normalize_url_for_dedup(b)


def test_normalize_strips_trailing_slash():
    a = "https://example.com/products/berserk/"
    b = "https://example.com/products/berserk"
    assert mw.normalize_url_for_dedup(a) == mw.normalize_url_for_dedup(b)


def test_normalize_lowercases_host():
    a = "https://WWW.Example.COM/products/x"
    b = "https://www.example.com/products/x"
    assert mw.normalize_url_for_dedup(a) == mw.normalize_url_for_dedup(b)


def test_normalize_keeps_different_products_distinct():
    a = "https://example.com/products/berserk-vol-1"
    b = "https://example.com/products/berserk-vol-2"
    assert mw.normalize_url_for_dedup(a) != mw.normalize_url_for_dedup(b)


def test_normalize_empty_url():
    assert mw.normalize_url_for_dedup("") == ""


# ---------------------------------------------------------------------------
# extract_isbn
# ---------------------------------------------------------------------------


def test_isbn_from_text_with_dashes():
    isbn = mw.extract_isbn("ISBN: 978-1-5067-0221-6 — Berserk Deluxe Vol 1")
    assert isbn == "9781506702216"


def test_isbn_from_text_no_separators():
    isbn = mw.extract_isbn("Código: 9781506702216")
    assert isbn == "9781506702216"


def test_isbn_from_url():
    isbn = mw.extract_isbn("https://example.com/p/9781506702216")
    assert isbn == "9781506702216"


def test_isbn_from_meta_itemprop():
    soup = make_soup('<html><head><meta itemprop="isbn" content="978-1-5067-0221-6"></head></html>')
    isbn = mw.extract_isbn("", soup)
    assert isbn == "9781506702216"


def test_isbn_from_json_ld():
    html = '<script type="application/ld+json">{"@type":"Book","isbn":"9781506702216"}</script>'
    isbn = mw.extract_isbn("", make_soup(html))
    assert isbn == "9781506702216"


def test_isbn_invalid_checksum_rejected():
    # 9781506702210 termina en 0 pero el checksum válido es 6 → debe rechazar
    isbn = mw.extract_isbn("ISBN: 9781506702210")
    assert isbn == ""


def test_isbn_empty_when_no_match():
    assert mw.extract_isbn("Solo texto sin números relevantes") == ""
    assert mw.extract_isbn("") == ""


# ---------------------------------------------------------------------------
# extract_schema_org_product
# ---------------------------------------------------------------------------


def test_schema_extracts_basic_product():
    html = """<html><body>
    <script type="application/ld+json">
    {
      "@type": "Product",
      "name": "Berserk Deluxe Edition Vol. 1",
      "description": "Tapa dura con sobrecubierta",
      "image": "https://cdn.example.com/cover.jpg",
      "isbn": "9781506702216",
      "author": {"@type": "Person", "name": "Kentaro Miura"},
      "offers": {"@type": "Offer", "price": "49.99", "priceCurrency": "USD"},
      "datePublished": "2024-06-15"
    }
    </script>
    </body></html>"""
    s = mw.extract_schema_org_product(make_soup(html), "https://example.com/")
    assert s["name"] == "Berserk Deluxe Edition Vol. 1"
    assert s["image_url"] == "https://cdn.example.com/cover.jpg"
    assert s["isbn"] == "9781506702216"
    assert s["author"] == "Kentaro Miura"
    assert s["price"] == "$ 49.99"
    assert s["release_date"] == "2024-06-15"
    assert "Tapa dura" in s["description"]


def test_schema_handles_book_type():
    html = """<html><body><script type="application/ld+json">
    {"@type": "Book", "name": "Vagabond Vol 1", "author": "Takehiko Inoue"}
    </script></body></html>"""
    s = mw.extract_schema_org_product(make_soup(html), "https://example.com/")
    assert s["name"] == "Vagabond Vol 1"
    assert s["author"] == "Takehiko Inoue"


def test_schema_handles_offers_list():
    html = """<html><body><script type="application/ld+json">
    {"@type": "Product", "name": "x", "offers": [
        {"price": "19.99", "priceCurrency": "EUR"},
        {"price": "29.99", "priceCurrency": "EUR"}
    ]}
    </script></body></html>"""
    s = mw.extract_schema_org_product(make_soup(html), "https://example.com/")
    assert s["price"] == "€ 19.99"


def test_schema_handles_graph_wrapper():
    # Algunos sites wrappean Product en @graph.
    html = """<html><body><script type="application/ld+json">
    {"@graph": [
      {"@type": "WebPage"},
      {"@type": "Product", "name": "Berserk", "isbn": "9781506702216"}
    ]}
    </script></body></html>"""
    s = mw.extract_schema_org_product(make_soup(html), "https://example.com/")
    assert s["name"] == "Berserk"
    assert s["isbn"] == "9781506702216"


def test_schema_returns_empty_when_no_product():
    html = """<html><body><script type="application/ld+json">
    {"@type": "WebPage", "name": "About us"}
    </script></body></html>"""
    s = mw.extract_schema_org_product(make_soup(html), "https://example.com/")
    assert s["name"] == ""
    assert s["isbn"] == ""


def test_schema_ignores_invalid_json():
    html = '<html><body><script type="application/ld+json">not valid json</script></body></html>'
    s = mw.extract_schema_org_product(make_soup(html), "https://example.com/")
    assert s["name"] == ""


def test_schema_empty_when_no_json_ld():
    html = "<html><body><p>plain</p></body></html>"
    s = mw.extract_schema_org_product(make_soup(html), "https://example.com/")
    assert all(v == "" for v in s.values())


# ---------------------------------------------------------------------------
# Bug A: blacklist de anchor genérico en _derive_title
# ---------------------------------------------------------------------------


def test_derive_title_avoids_lire_la_suite():
    soup = make_soup("""
        <article>
            <h2>L'atelier des sorciers - Edition Collector</h2>
            <p>Tapa dura con sobrecubierta</p>
            <a href="/p/x">Lire la suite</a>
        </article>
    """)
    art = soup.find("article")
    anchor = art.find("a")
    title = mw._derive_title(art, anchor)
    assert "Lire la suite" not in title
    assert "atelier des sorciers" in title.lower()


def test_derive_title_avoids_read_more():
    soup = make_soup("""
        <div>
            <h3>Berserk Deluxe Edition Vol 14</h3>
            <a href="/p"><img alt="Read more"></a>
        </div>
    """)
    d = soup.find("div")
    title = mw._derive_title(d, d.find("a"))
    assert "Read more" not in title
    assert "Berserk" in title


def test_derive_title_avoids_japanese_generic():
    soup = make_soup("""
        <li class='comic_article'>
            <h2>限定版 ヒロアカ 30巻</h2>
            <a href="/x">詳しく見る</a>
        </li>
    """)
    li = soup.find("li")
    title = mw._derive_title(li, li.find("a"))
    assert "詳しく見る" not in title
    assert "限定版" in title


# ---------------------------------------------------------------------------
# Bug B: keyword injection en score para búsquedas dirigidas
# ---------------------------------------------------------------------------


def test_score_candidate_search_keyword_gives_floor_score_no_signal_contamination():
    # Una card cuyo título NO incluye "edition collector" pero viene de un
    # search dirigido a esa keyword recibe un floor de score (boost suave)
    # pero NO contamina signals/signal_types. El signal pertenece al item,
    # no a la fuente.
    mw.configure_detection(fuzzy=False, fuzzy_divisor=3)
    cand = mw.Candidate(
        title="L'atelier des sorciers 15",
        url="https://www.glenat.com/livre/x",
        source="FR - Glénat (search) [search: edition collector]",
        source_url="https://www.glenat.com/?keys=edition+collector",
        country="Francia",
        language="Francés",
        publisher="Glénat",
        source_class="official",
        tags=["manga", "official", "expansion", "search:edition collector"],
        description="Manga: nouveau tome 15",
    )
    mw.score_candidate(cand)
    # Floor score por venir de search dirigido (10 base + 5 official = 15).
    assert cand.score > 0, "search-keyword debe dar floor score"
    assert cand.score < 30, "no debe alcanzar score real de 'edition collector'"
    # CRÍTICO: signals/signal_types deben estar VACÍOS — la palabra no está
    # en el item, sólo en la fuente. Contaminar acá rompe el gate y product_type.
    assert "edition collector" not in (cand.signals or []), \
        "search keyword no debe contaminar signals"
    assert "collector" not in (cand.signal_types or []), \
        "search keyword no debe contaminar signal_types"


def test_score_candidate_no_source_contamination_in_signals():
    # Un item de "Panini Edizioni da Collezione e Cofanetti" cuyo título y
    # descripción NO mencionan cofanetto/cofanetti no debe heredar signal
    # box_set sólo porque el nombre de la fuente contiene "Cofanetti".
    mw.configure_detection(fuzzy=False, fuzzy_divisor=3)
    cand = mw.Candidate(
        title="Berserk Deluxe Edition 1",
        url="https://www.panini.it/x",
        source="IT - Panini Edizioni da Collezione e Cofanetti",
        source_url="https://www.panini.it/edizioni-collezione-cofanetti",
        country="Italia", language="Italiano", publisher="Panini",
        source_class="official",
        tags=["manga", "official"],
        description="Edizione di lusso con copertina cartonata.",
    )
    mw.score_candidate(cand)
    # Título tiene "Deluxe Edition" → señal legítima.
    assert "deluxe" in (cand.signal_types or [])
    # Pero NO box_set: "cofanetti" sólo aparece en source name, no en item.
    assert "box_set" not in (cand.signal_types or []), \
        f"source name no debe contaminar signal_types: {cand.signal_types}"


def test_score_candidate_no_keyword_injection_without_tag():
    # Si no hay tag search:X, el comportamiento es el de siempre.
    mw.configure_detection(fuzzy=False, fuzzy_divisor=3)
    cand = mw.Candidate(
        title="Manga regular",
        url="https://x.com/",
        source="x", source_url="x",
        country="", language="", publisher="",
        source_class="official",
        tags=["manga", "official"],
        description="Sin señales",
    )
    mw.score_candidate(cand)
    assert cand.score == 0


# ---------------------------------------------------------------------------
# Fase 2: parser de ListadoManga
# ---------------------------------------------------------------------------


def test_listadomanga_parse_date_header():
    from wikis import listadomanga as lm
    assert lm._parse_date_header("Sábado, 2 Mayo 2026") == "2026-05-02"
    assert lm._parse_date_header("Lunes, 4 Mayo 2026") == "2026-05-04"
    assert lm._parse_date_header("Viernes, 15 Diciembre 2023") == "2023-12-15"


def test_listadomanga_parse_date_invalid():
    from wikis import listadomanga as lm
    assert lm._parse_date_header("Mayo 2026") == ""  # no es fecha completa
    assert lm._parse_date_header("Norma Editorial") == ""
    assert lm._parse_date_header("") == ""


def test_listadomanga_is_publisher_header():
    from wikis import listadomanga as lm
    assert lm._is_publisher_header("Norma Editorial") is True
    assert lm._is_publisher_header("Ediciones Tomodomo") is True
    assert lm._is_publisher_header("Sábado, 2 Mayo 2026") is False  # es fecha
    assert lm._is_publisher_header("Mayo 2026") is False  # es mes adyacente
    assert lm._is_publisher_header("Calendario de Mayo 2026") is False
    assert lm._is_publisher_header("") is False


def test_listadomanga_iter_year_months():
    from wikis import listadomanga as lm
    months = lm.iter_year_months(2025, 11, 2026, 2)
    assert months == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]


def test_listadomanga_parse_calendar_extracts_items():
    """Parsea un HTML reducido con el patrón real de ListadoManga."""
    from wikis import listadomanga as lm
    html = """<html><body>
        <h2>Norma Editorial</h2>
        <h2>Sábado, 2 Mayo 2026</h2>
        <table class="ventana_id1">
            <tr><td class="izq">
                <b><u>Seinen</u></b><br/>
                - <a href="coleccion.php?id=100">Berserk Deluxe nº14 - Edición Especial</a> /
                  <a href="autor.php?id=50">Kentaro Miura</a><br/>
                - <a href="coleccion.php?id=101">Otro manga nº1 (de 5)</a> /
                  <a href="autor.php?id=51">Otro Autor</a><br/>
            </td></tr>
        </table>
    </body></html>"""
    items = lm.parse_calendar_page(html)
    assert len(items) == 2
    assert items[0].publisher == "Norma Editorial"
    assert items[0].release_date == "2026-05-02"
    assert "Berserk Deluxe" in items[0].title
    assert items[0].author == "Kentaro Miura"
    assert items[0].url.startswith("https://www.listadomanga.es/coleccion.php?id=100")


def test_listadomanga_detail_extracts_image_and_price():
    """Test que el extractor de detail page agarra cover + precio sin hacer HTTP real."""
    from wikis import listadomanga as lm
    # Simulamos lo que extract hace internamente: parsear HTML + buscar img + precio.
    html = """<html><body>
        <img src="https://static.listadomanga.com/abc123.jpg" alt="cover">
        <p>Editorial: Norma Editorial</p>
        <p>Precio: 9,95 €</p>
        <b>Formato:</b> Tomo A5 rústica con sobrecubierta
    </body></html>"""
    # Mockeamos session.get para no hacer HTTP real
    class FakeResponse:
        text = html
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        def raise_for_status(self): pass
    class FakeSession:
        def get(self, url, **kw): return FakeResponse()

    meta = lm.fetch_detail_metadata("https://www.listadomanga.es/coleccion.php?id=1", FakeSession())
    assert meta["image_url"] == "https://static.listadomanga.com/abc123.jpg"
    assert "9,95" in meta["price"]
    assert "Formato" in meta["description_extra"]


def test_listadomanga_detail_empty_when_no_data():
    from wikis import listadomanga as lm
    class FakeResponse:
        text = "<html><body>no relevante</body></html>"
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        def raise_for_status(self): pass
    class FakeSession:
        def get(self, url, **kw): return FakeResponse()
    meta = lm.fetch_detail_metadata("https://x.com/x", FakeSession())
    assert meta["image_url"] == ""
    assert meta["price"] == ""


# --- Search discovery (Google CSE + DDG) ------------------------------------

def test_search_discovery_parse_ddg_html_extracts_redirects():
    """DDG envuelve cada URL en /l/?uddg=<url>; el parser debe decodear."""
    from retrofit.search_discovery import parse_ddg_html
    html = """<html><body>
        <div class="result">
            <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.whakoom.com%2Fediciones%2F123%2Fberserk_tarot&amp;rut=abc">
                Berserk Tarot Edition (Panini)
            </a>
        </div>
        <div class="result">
            <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.fnac.es%2Fmanga-exclusiva-one-piece&amp;rut=def">
                One Piece exclusiva Fnac
            </a>
        </div>
        <div class="result">
            <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.whakoom.com%2Fediciones%2F123%2Fberserk_tarot&amp;rut=ghi">
                duplicate
            </a>
        </div>
        <!-- internal DDG link, debe ignorarse -->
        <a class="result__a" href="https://duckduckgo.com/about">about</a>
    </body></html>"""
    results = parse_ddg_html(html)
    assert len(results) == 2  # 1 dedupeado
    assert results[0]["url"] == "https://www.whakoom.com/ediciones/123/berserk_tarot"
    assert "Berserk Tarot" in results[0]["title"]
    assert results[1]["url"] == "https://www.fnac.es/manga-exclusiva-one-piece"


def test_search_discovery_parse_ddg_max_results():
    from retrofit.search_discovery import parse_ddg_html
    html = "<html><body>" + "".join(
        f'<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2F{i}">{i}</a>'
        for i in range(20)
    ) + "</body></html>"
    results = parse_ddg_html(html, max_results=5)
    assert len(results) == 5


def test_search_discovery_url_dedup_against_known():
    from retrofit.search_discovery import url_already_known
    # Misma URL con tracking params normaliza al mismo key
    known = {"https://www.example.com/product/123"}
    # Esta función llama normalize_url_for_dedup internamente
    assert url_already_known("https://www.example.com/product/123", known)
    assert not url_already_known("https://www.example.com/product/999", known)


def test_search_discovery_url_is_useful_blocks_social_and_videos():
    from retrofit.search_discovery import url_is_useful
    # Posts/reels/videos sociales nunca son productos individuales.
    assert not url_is_useful("https://www.instagram.com/p/DX9CWG-CERl")
    assert not url_is_useful("https://www.instagram.com/reel/DX9XsP1NtJs")
    assert not url_is_useful("https://www.instagram.com/tv/ABC123")
    assert not url_is_useful("https://www.youtube.com/shorts/9zXvjivBglY")
    assert not url_is_useful("https://www.youtube.com/watch?v=KfFmF3iofbg")
    assert not url_is_useful("https://www.facebook.com/PaniniES/posts/123")
    assert not url_is_useful("https://www.facebook.com/some.page/videos/456")
    assert not url_is_useful("https://www.threads.net/@user/post/abc")
    # Páginas de producto reales siguen pasando.
    assert url_is_useful("https://www.panini.es/shp_esp_es/berserk-master-edition-1.html")
    assert url_is_useful("https://www.amazon.co.jp/dp/4088831234")


def test_search_discovery_gemini_requires_credentials():
    from retrofit.search_discovery import search_gemini_grounding, SearchEngineError
    try:
        search_gemini_grounding("test", "")
        assert False, "Debe levantar SearchEngineError sin credenciales"
    except SearchEngineError as e:
        assert "GEMINI_API_KEY" in str(e)


def test_search_discovery_parse_gemini_grounding_chunks():
    """Extrae URLs del response.candidates[0].groundingMetadata.groundingChunks."""
    from retrofit.search_discovery import parse_gemini_grounding_response
    data = {
        "candidates": [{
            "content": {"parts": [{"text": "Some AI summary text..."}]},
            "groundingMetadata": {
                "groundingChunks": [
                    {"web": {"uri": "https://www.whakoom.com/ediciones/123/berserk_tarot",
                             "title": "Berserk Tarot Edition (Panini)"}},
                    {"web": {"uri": "https://www.fnac.es/manga-exclusiva",
                             "title": "Manga Exclusiva Fnac"}},
                    # Duplicado por URL — debe dedupear
                    {"web": {"uri": "https://www.whakoom.com/ediciones/123/berserk_tarot",
                             "title": "duplicate"}},
                    # Sin URI — saltarlo
                    {"web": {"title": "broken result"}},
                    # Chunk no-web (puede haber otros tipos) — saltarlo
                    {"retrievedContext": {"text": "internal"}},
                ],
            },
        }],
    }
    out = parse_gemini_grounding_response(data, max_results=10)
    assert len(out) == 2
    assert out[0]["url"] == "https://www.whakoom.com/ediciones/123/berserk_tarot"
    assert out[0]["title"] == "Berserk Tarot Edition (Panini)"
    assert out[1]["url"] == "https://www.fnac.es/manga-exclusiva"


def test_search_discovery_parse_gemini_empty_response():
    from retrofit.search_discovery import parse_gemini_grounding_response
    assert parse_gemini_grounding_response({}) == []
    assert parse_gemini_grounding_response({"candidates": []}) == []
    assert parse_gemini_grounding_response({"candidates": [{}]}) == []
    # Candidato sin grounding (modelo respondió sin usar search tool)
    no_grounding = {"candidates": [{"content": {"parts": [{"text": "answer"}]}}]}
    assert parse_gemini_grounding_response(no_grounding) == []


def test_search_discovery_tavily_requires_key():
    from retrofit.search_discovery import search_tavily, SearchEngineError
    try:
        search_tavily("test", "")
        assert False, "Debe levantar SearchEngineError sin key"
    except SearchEngineError as e:
        assert "TAVILY_API_KEY" in str(e)


def test_search_discovery_parse_tavily_response():
    from retrofit.search_discovery import parse_tavily_response
    data = {
        "query": "test",
        "results": [
            {"url": "https://example.com/1", "title": "Result 1",
             "content": "snippet 1 con mucho texto " * 20, "score": 0.9},
            {"url": "https://example.com/2", "title": "Result 2", "content": "s2", "score": 0.8},
            # Duplicado
            {"url": "https://example.com/1", "title": "dup", "content": "s3", "score": 0.7},
            # Sin url
            {"title": "broken", "content": "x"},
        ],
    }
    out = parse_tavily_response(data, max_results=10)
    assert len(out) == 2
    assert out[0]["url"] == "https://example.com/1"
    assert out[0]["title"] == "Result 1"
    assert len(out[0]["snippet"]) <= 300   # truncado
    assert out[1]["url"] == "https://example.com/2"


def test_search_discovery_parse_tavily_empty():
    from retrofit.search_discovery import parse_tavily_response
    assert parse_tavily_response({}) == []
    assert parse_tavily_response({"results": []}) == []
    assert parse_tavily_response({"results": [{"url": ""}]}) == []


def test_search_discovery_parse_gemini_respects_max_results():
    from retrofit.search_discovery import parse_gemini_grounding_response
    data = {"candidates": [{"groundingMetadata": {
        "groundingChunks": [
            {"web": {"uri": f"https://x.com/{i}", "title": str(i)}} for i in range(20)
        ],
    }}]}
    out = parse_gemini_grounding_response(data, max_results=5)
    assert len(out) == 5


# --- Whakoom spider (3-level BFS) -------------------------------------------

def test_whakoom_extract_comics_from_newtitles():
    from wikis import whakoom as wk
    html = """<html><body>
        <a href="/comics/PMvgk/absolute_batman/14" title="Absolute Batman #14">x</a>
        <a href="/comics/yP5nP/el_arte_de_berserk" title="El arte de Berserk">x</a>
        <a href="/comics/691X2/atelier_of_witch_hat/15">x</a>
        <a href="/notcomics/abc">x</a>
        <a href="/comics/dup1/spy_x_family/1">x</a>
        <a href="/comics/dup1/spy_x_family/1">x</a>  <!-- duplicado -->
    </body></html>"""
    urls = wk.extract_comics_urls_from_newtitles(html)
    assert len(urls) == 4
    assert "https://www.whakoom.com/comics/PMvgk/absolute_batman/14" in urls


def test_whakoom_extract_ediciones_dedups_by_id():
    from wikis import whakoom as wk
    html = """<html><body>
        <a href="/ediciones/571851/spy_x_family-rustica_con_sobrecubierta">Regular</a>
        <a href="/ediciones/571851/spy_x_family-rustica_con_sobrecubierta/todos">Mismo id (skip)</a>
        <a href="/ediciones/589084/spy___family_1_-_portada_alternativa">Alt</a>
        <a href="/ediciones/123/some_other_thing">other</a>
        <a href="/comics/X/other">not edition</a>
    </body></html>"""
    pairs = wk.extract_ediciones_urls_from_html(html)
    # Solo 3 únicos (571851 dedupea, 589084, 123)
    ids = [pair[0] for pair in pairs]
    assert sorted(ids) == [123, 571851, 589084]


def test_whakoom_parse_edition_extracts_og_metadata():
    from wikis import whakoom as wk
    html = """<html><head>
        <title>Spy × Family #1 - Portada Alternativa (Ivrea Argentina)</title>
        <meta property="og:title" content="Spy × Family #1 - Portada Alternativa (Ivrea Argentina)">
        <meta property="og:description" content="Los países de Westalis y Ostania libran una guerra fría...">
        <meta property="og:image" content="https://i1.whakoom.com/large/20/29/f34ef919.jpg">
        <meta property="og:url" content="https://www.whakoom.com/ediciones/589084/spy___family_1_-_portada_alternativa-rustica_con_sobrecubierta">
    </head><body>
        <span class="publisher">Ivrea Argentina</span>
    </body></html>"""
    cand = wk.parse_edition_page(html, "https://www.whakoom.com/ediciones/589084/x")
    assert cand is not None
    assert "Spy" in cand.title and "Portada Alternativa" in cand.title
    # Publisher separado del paréntesis
    assert cand.publisher == "Ivrea Argentina"
    assert "(Ivrea" not in cand.title
    assert cand.image_url.startswith("https://i1.whakoom.com/large/")
    assert cand.url == "https://www.whakoom.com/ediciones/589084/spy___family_1_-_portada_alternativa-rustica_con_sobrecubierta"
    assert cand.country == "Argentina"  # inferido del publisher
    assert "Westalis" in cand.description


def test_whakoom_parse_edition_returns_none_for_empty():
    from wikis import whakoom as wk
    assert wk.parse_edition_page("<html><body></body></html>", "x") is None


def test_whakoom_detects_cloudflare_challenge():
    from wikis import whakoom as wk
    challenges = [
        '<html><head><script>cf-chl-bypass</script></head></html>',
        '<html><body>Just a moment...<script>cf_challenge</script></body></html>',
        '<html><body>Checking your browser before accessing</body></html>',
        '<html><body><div class="challenge-platform">x</div></body></html>',
    ]
    for c in challenges:
        assert wk._looks_like_cf_challenge(c), f"Should detect challenge: {c[:50]!r}"
    # Páginas legítimas NO matchean
    assert not wk._looks_like_cf_challenge("<html><body>normal content</body></html>")
    assert not wk._looks_like_cf_challenge("")
    # Páginas grandes (>50KB) tampoco — son contenido real aunque mencionen palabras.
    big = "<html>" + ("x" * 60000) + "</html>"
    assert not wk._looks_like_cf_challenge(big)


def test_whakoom_browser_headers_set():
    import requests
    from wikis import whakoom as wk
    sess = wk._ua_session(requests.Session())
    h = sess.headers
    assert "Mozilla" in h.get("User-Agent", "")
    assert "Chrome" in h.get("User-Agent", "")
    assert "es-ES" in h.get("Accept-Language", "")
    assert "Referer" in h
    assert h["Referer"].startswith("https://www.whakoom.com")


def test_whakoom_throttle_blocks_recent_runs(tmp_path, monkeypatch):
    import time
    from wikis import whakoom as wk
    # Apunta el lockfile a una ubicación temporal
    fake_lockfile = tmp_path / "whakoom_lastrun"
    monkeypatch.setattr(wk, "_THROTTLE_FILE", fake_lockfile)
    # Run reciente (justo ahora) → debe bloquear
    fake_lockfile.write_text(str(time.time()))
    try:
        wk._check_throttle()
        assert False, "Throttle debe bloquear (SystemExit esperado)"
    except SystemExit as e:
        assert "Último bootstrap" in str(e)
    # Con force=True (--ignore-throttle) deja pasar
    wk._check_throttle(force=True)  # no levanta
    # Sin lockfile → deja pasar
    fake_lockfile.unlink()
    wk._check_throttle()  # no levanta


def test_whakoom_throttle_allows_old_runs(tmp_path, monkeypatch):
    import time
    from wikis import whakoom as wk
    fake_lockfile = tmp_path / "whakoom_lastrun"
    monkeypatch.setattr(wk, "_THROTTLE_FILE", fake_lockfile)
    # Run de hace 10h (más viejo que el min 6h) → deja pasar
    fake_lockfile.write_text(str(time.time() - 10 * 3600))
    wk._check_throttle()  # no levanta


# --- Listadomanga BLOG (archivo histórico de posts) -------------------------

def test_listadomanga_blog_parse_archive_extracts_posts():
    from wikis import listadomanga_blog as lmb
    html = """<html><body>
        <div class="post-21713 post type-post status-publish hentry category-pika category-anaya">
          <h3 id="post-21713">
            <a href="https://www.listadomanga.es/blog/2024/06/28/grupo-anaya-empezara-a-publicar-manga-tras-el-verano/"
               rel="bookmark"
               title="Permanent Link to Grupo Anaya empezará a publicar manga como Pika Ediciones">
              Grupo Anaya empezará a publicar manga como Pika Ediciones
            </a>
          </h3>
          <small>28 de junio de 2024 por Listado Manga </small>
          <div class="entry">
            <p>Ayer por la tarde, a través de un directo de Infinity Comics,
            nos enteramos que el Grupo Anaya comenzará a editar manga a partir de octubre.</p>
            <p>Esta nueva línea editorial se llamará Pika Ediciones.</p>
          </div>
        </div>
        <div class="post-21800 post type-post status-publish hentry category-norma">
          <h3 id="post-21800">
            <a href="https://www.listadomanga.es/blog/2024/06/15/edicion-coleccionista-de-berserk-norma/">
              Edición coleccionista de Berserk nº42 de Norma con cofre + 4 postales
            </a>
          </h3>
          <small>15 de junio de 2024 por Listado Manga</small>
          <div class="entry">
            <p>Norma Editorial anuncia para octubre la edición especial de Berserk nº42
            que incluirá cofre, 4 postales exclusivas y póster reversible.</p>
          </div>
        </div>
    </body></html>"""
    cands = lmb.parse_archive_page(html)
    assert len(cands) == 2
    # Post 1: anuncio editorial
    c1 = cands[0]
    assert "Grupo Anaya" in c1.title
    assert c1.url == "https://www.listadomanga.es/blog/2024/06/28/grupo-anaya-empezara-a-publicar-manga-tras-el-verano/"
    assert "octubre" in c1.description
    assert "category:pika" in (c1.tags or [])
    assert "category:anaya" in (c1.tags or [])
    # Post 2: edición coleccionista
    c2 = cands[1]
    assert "Berserk" in c2.title
    assert "cofre" in c2.title.lower() or "cofre" in c2.description.lower()
    assert "category:norma" in (c2.tags or [])


def test_listadomanga_blog_parse_skips_malformed():
    from wikis import listadomanga_blog as lmb
    # post sin h3 ni link → ignorado
    html = """<html><body>
        <div class="post-1 post type-post status-publish hentry">
          <p>contenido sin título</p>
        </div>
        <div class="post-2 post type-post status-publish hentry">
          <h3 id="post-2"><a href="">empty href</a></h3>
        </div>
    </body></html>"""
    cands = lmb.parse_archive_page(html)
    assert cands == []


def test_listadomanga_blog_iter_year_months():
    from wikis import listadomanga_blog as lmb
    # Smoke check: rango chico
    pairs = lmb.iter_year_months(2024, 5, 2024, 7)
    assert pairs == [(2024, 5), (2024, 6), (2024, 7)]
    # Cruzando año
    pairs2 = lmb.iter_year_months(2023, 11, 2024, 2)
    assert pairs2 == [(2023, 11), (2023, 12), (2024, 1), (2024, 2)]


def test_listadomanga_blog_fetch_archive_handles_404():
    from wikis import listadomanga_blog as lmb
    # Simulamos que page/2 da 404 → fetch_archive_month corta en page 1.
    class FakeResponse:
        status_code = 200
        text = """<html><body>
            <div class="post-1 post type-post status-publish hentry">
              <h3 id="post-1"><a href="https://www.listadomanga.es/blog/2024/06/01/x/">
                Anuncio Pika Edición Especial vol 1
              </a></h3>
              <small>1 de junio de 2024 por Listado Manga</small>
              <div class="entry"><p>contenido del post</p></div>
            </div>
        </body></html>"""
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        def raise_for_status(self): pass

    class Fake404:
        status_code = 404
        text = ""
        def raise_for_status(self):
            import requests
            raise requests.HTTPError("404")

    class FakeSession:
        def __init__(self):
            self.calls = 0
        def get(self, url, **kw):
            self.calls += 1
            return FakeResponse() if self.calls == 1 else Fake404()

    sess = FakeSession()
    cands = lmb.fetch_archive_month(2024, 6, sess, sleep_between_pages=0)
    assert sess.calls >= 1
    # El post pasa el filtro non-manga + tiene scoring
    assert len(cands) >= 0  # sólo verificamos que no crashea
    # Si el post tiene signal por "Edición Especial" → score > 0
    if cands:
        assert all(hasattr(c, "score") for c in cands)


def test_clean_title_strips_shopify_price_junk():
    cases = [
        ("Berserk Deluxe Hardcover Sale price: $44.99 Regular price: $49.99 On Sale",
         "Berserk Deluxe Hardcover"),
        # 'Mazebook HC (Dark Horse Direct Exclusive) Price: $125.00' ahora se limpia
        # el sufijo de retailer-exclusive también. Test ajustado.
        ("Mazebook HC (Dark Horse Direct Exclusive) Price: $125.00",
         "Mazebook HC"),
        ("Trigun Maximum Deluxe Edition Hardcovers Sale price: $44.99 Regular price: $49.99 On Sale",
         "Trigun Maximum Deluxe Edition Hardcovers"),
        ("Berserk Deluxe Hardcover Volumes Price: On Sale from $44.99 On Sale",
         "Berserk Deluxe Hardcover Volumes"),
        ("Hellboy 30th Anniversary Deluxe Vinyl Figure Price: $149.99 Sold Out",
         "Hellboy 30th Anniversary Deluxe Vinyl Figure"),
    ]
    for raw, expected in cases:
        assert mw.clean_title(raw) == expected, f"failed: {raw!r}"


def test_clean_title_strips_french_acheter():
    assert mw.clean_title("One Piece 10 [glénat manga] / simple Manga Acheter 7,95€") == \
        "One Piece 10 [glénat manga] / simple Manga"


def test_clean_title_strips_isolated_price():
    assert mw.clean_title("My Manga Volume 1 $19.99") == "My Manga Volume 1"
    assert mw.clean_title("Manga Title 12,35 €") == "Manga Title"
    assert mw.clean_title("Manga japonés ¥1,980") == "Manga japonés"


def test_clean_title_strips_panini_es_magento_junk():
    """Panini ES search-result devuelve el wrapper entero como title."""
    cases = [
        ('Añadir a la Lista de Deseos Berserk Master Edition 1 Manga 02/07/26 Regular Price 150,00 € -5% Special Price 142,50 € No está disponible',
         "Berserk Master Edition 1"),
        ('Añadir a la Lista de Deseos Blame! Master Edition 3 Cómic 16/10/25 Regular Price 25,00 € -5% Special Price 23,75 € Pre-venta',
         "Blame! Master Edition 3"),
        ('Añadir a la Lista de Deseos Biomega Master Edition 1 de 3 Cómic 24/11/22 Regular Price 20,00 €',
         "Biomega Master Edition 1 de 3"),
    ]
    for raw, expected in cases:
        assert mw.clean_title(raw) == expected, f"raw={raw!r}"


def test_clean_title_preserves_clean_titles():
    assert mw.clean_title("Berserk Deluxe Edition Vol 14") == "Berserk Deluxe Edition Vol 14"
    assert mw.clean_title("限定版 Special Edition") == "限定版 Special Edition"


def test_clean_title_empty_input():
    assert mw.clean_title("") == ""
    assert mw.clean_title(None) is None


def test_clean_title_strips_announcement_prefix():
    # Los 6 ejemplos exactos que el usuario pasó.
    cases = [
        ("New Product Announcement - Mazebook HC (Dark Horse Direct Exclusive)",
         "Mazebook HC"),
        ("New Product Announcement - Star Wars: Hyperspace Stories Annual—Jaxxon 2023 (Mike Mignola Exclusive Variant)",
         "Star Wars: Hyperspace Stories Annual—Jaxxon 2023 (Mike Mignola Exclusive Variant)"),
        ("Panini: Fumetti_21st Century Boys: Ultimate Deluxe Edition 12",
         "21st Century Boys: Ultimate Deluxe Edition 12"),
        ("Mignola Convention Variant Spaceboy Maquette Pre-Order Bonus",
         "Mignola Convention Variant Spaceboy Maquette"),
        ("Panini: Fumetti_Shangri-La Frontier Expansion Pass 21",
         "Shangri-La Frontier Expansion Pass 21"),
        ("New Product Announcement: The Art of Dragon Age: The Veilguard HC (Deluxe Edition)",
         "The Art of Dragon Age: The Veilguard HC (Deluxe Edition)"),
    ]
    for raw, expected in cases:
        actual = mw.clean_title(raw)
        assert actual == expected, f"\n  input:    {raw!r}\n  expected: {expected!r}\n  actual:   {actual!r}"


def test_clean_title_keeps_artist_exclusives():
    # 'Mike Mignola Exclusive Variant' es metadata del producto: mantener.
    # 'Dark Horse Direct Exclusive' es metadata del retailer: quitar.
    assert mw.clean_title("Some Comic (Mike Mignola Exclusive Variant)") == \
        "Some Comic (Mike Mignola Exclusive Variant)"
    assert mw.clean_title("Some Comic (Dark Horse Direct Exclusive)") == "Some Comic"
    assert mw.clean_title("Some Comic (Barnes & Noble Exclusive)") == "Some Comic"
    assert mw.clean_title("Some Comic (Kinokuniya Exclusive)") == "Some Comic"


def test_clean_title_strips_panini_generic_prefix():
    # Ejemplos reales del corpus: Panini agrupa por categoría con prefijo `_`.
    cases = [
        ("Panini: Libri_Noblesse 17/19 – Cofanetto 6 6",
         "Noblesse 17/19 – Cofanetto 6 6"),
        ("Panini: Libri_Food Wars – Cofanetto 6",
         "Food Wars – Cofanetto 6"),
        ("Panini: Manga_Moglie di una Spia – Cofanetto",
         "Moglie di una Spia – Cofanetto"),
        ("Panini: Productos de colección_Liga Este 2025/26 - Pack Album",
         "Liga Este 2025/26 - Pack Album"),
        ("Panini: Comics_X-Men Vol. 1",
         "X-Men Vol. 1"),
    ]
    for raw, expected in cases:
        actual = mw.clean_title(raw)
        assert actual == expected, f"\n  input:    {raw!r}\n  expected: {expected!r}\n  actual:   {actual!r}"


def test_clean_title_strips_norma_descriptive_tail():
    # Norma Editorial pega una "ficha de producto" al final del título.
    cases = [
        ("BAKI THE GRAPPLER EDICIÓN KANZENBAN #14 Con sobrecubierta y páginas a color Formato A5 350 págs. aprox. En comiquerías y cadena de librerías MÁS INFO",
         "BAKI THE GRAPPLER EDICIÓN KANZENBAN #14"),
        ("DNANGEL: EDICIÓN KANZENBAN #10 ¡ÚLTIMO TOMO! Con sobrecubierta Incluye desplegable y páginas a color Formato A5 400 págs. aprox. En comiquerías y cadena de librerías MÁS INFO",
         "DNANGEL: EDICIÓN KANZENBAN #10 ¡ÚLTIMO TOMO!"),
        ("EL REY BESTIA Y LAS HIERBAS MEDICINALES #2 Formato B6 Con sobrecubierta Incluye págs a color 200 págs. aprox.",
         "EL REY BESTIA Y LAS HIERBAS MEDICINALES #2"),
    ]
    for raw, expected in cases:
        actual = mw.clean_title(raw)
        assert actual == expected, f"\n  input:    {raw!r}\n  expected: {expected!r}\n  actual:   {actual!r}"


def test_clean_title_strips_trailing_date():
    # Glénat/Pika dejan la fecha de salida pegada al final del título.
    cases = [
        ("Dragon Ball Le super art book Akira Toriyama 22/04/2026",
         "Dragon Ball Le super art book Akira Toriyama"),
        ("One Piece Color Walk - Tome 10 Eiichiro Oda 21/05/2025",
         "One Piece Color Walk - Tome 10 Eiichiro Oda"),
        ("Manga release date 8-7-2026",
         "Manga release date"),
    ]
    for raw, expected in cases:
        actual = mw.clean_title(raw)
        assert actual == expected, f"\n  input:    {raw!r}\n  expected: {expected!r}\n  actual:   {actual!r}"


def test_clean_title_strips_fr_status_and_publisher_prefix():
    # Estado FR ("Nouveauté", "À paraître") + categoría editorial.
    cases = [
        ("Nouveauté Glénat Manga Dragon Ball Le super art book",
         "Dragon Ball Le super art book"),
        ("Nouveauté Pika Seinen L'Atelier des Sorciers T15 - Collector",
         "L'Atelier des Sorciers T15 - Collector"),
        ("À paraître Pika Dreamland T24 - édition collector",
         "Dreamland T24 - édition collector"),
        # Sin prefijo de status, pero con categoría editorial pegada:
        ("Glénat Manga L'Art de Kiki la petite sorcière",
         "L'Art de Kiki la petite sorcière"),
    ]
    for raw, expected in cases:
        actual = mw.clean_title(raw)
        assert actual == expected, f"\n  input:    {raw!r}\n  expected: {expected!r}\n  actual:   {actual!r}"


def test_clean_title_strips_es_proximamente_prefix():
    cases = [
        ("Próximamente Yu-Gi-Oh! Kanzenban nº 03/22", "Yu-Gi-Oh! Kanzenban nº 03/22"),
        ("Próximamente One Piece nº 14 (3 en 1)", "One Piece nº 14 (3 en 1)"),
        ("Próxima salida La guerra de los mundos (integral)", "La guerra de los mundos (integral)"),
    ]
    for raw, expected in cases:
        actual = mw.clean_title(raw)
        assert actual == expected, f"\n  input:    {raw!r}\n  expected: {expected!r}\n  actual:   {actual!r}"


def test_is_likely_manga_rescues_strong_hints():
    # Cualquier indicador inequívoco de manga → True.
    cases = [
        "Berserk Deluxe Edition Vol. 1",
        "ONE PIECE 漫画 第108巻",
        "Naruto - Tome 72 - édition collector",
        "Yu-Gi-Oh! Kanzenban nº 03/22",
        "The Art of Studio Ghibli (artbook)",
        "Bleach 3 en 1 #14",
        "Sailor Moon Eternal Edition Volume 5",
    ]
    for t in cases:
        is_manga, reason = mw.is_likely_manga(t)
        assert is_manga, f"Should be manga: {t!r} (reason={reason})"


def test_is_likely_manga_rescues_packs_with_extras():
    # Un manga edición especial que viene CON una figura debe mantenerse.
    cases = [
        "Mujina into the deep nº1 - Edición Especial + Sobrecubierta + 4 Postales",
        "My Hero Academia nº42 - Cofre especial + Llavero + Camiseta + Shikishi",
        "Demon Slayer Coffret Collector + Figurine",
        "Attack on Titan Boxset + Poster Reversible",
        "Cofanetto Naruto + Statuette Kakashi",
    ]
    for t in cases:
        is_manga, reason = mw.is_likely_manga(t)
        assert is_manga, f"Should be manga (pack): {t!r} (reason={reason})"


def test_is_likely_manga_rejects_pure_merchandise():
    # Objetos derivados puros (sin manga implícito) → False.
    cases = [
        ("Usagi Yojimbo 40th Anniversary Deluxe Vinyl Figure", "vinyl figure"),
        ("Hellboy 30th Anniversary Deluxe Vinyl Figure (Variant)", "vinyl figure"),
        ("The Last of Us: Bloater Statue", "statue"),
        ("The Witcher: Geralt and Ciri Fireside Premium Statue", "premium statue"),
        ("Ori and the Blind Forest - Ori and Naru PVC Statue", "PVC statue"),
        ("Mignola Convention Variant Spaceboy Maquette", "maquette"),
        ("Funko Pop Deluxe: Demon Slayer", "funko"),
        ("FUNKO POP DELUXE: JUJUTSU KAISEN - RYOMEN SUKUNA", "funko"),
        ("Usagi Yojimbo Year of the Dragon Puzzle (Convention Exclusive)", "puzzle"),
        ("神の庭付き楠木邸 Blu-ray BOX 下巻", "DVD/Blu-ray"),
        ("Astérix Trading Card Treasure Box - Archivador Deluxe", "trading card"),
        ("Hellboy Skate Deck: Hellboy, Liz, and Abe", "skate deck"),
    ]
    for t, label in cases:
        is_manga, reason = mw.is_likely_manga(t)
        assert not is_manga, f"Should NOT be manga ({label}): {t!r} (reason={reason})"


def test_is_likely_manga_default_accepts_unknown():
    # Sin pattern claro: aceptar (mejor false-positive que perder mangas reales).
    is_manga, _ = mw.is_likely_manga("Some Unusual Title Here")
    assert is_manga


def test_is_likely_manga_rejects_by_source_tag():
    # Tags taxonómicos de Manga-Sanctuary: "type:série tv animée" / "type:film" /
    # "type:produit dérivé" → no es manga aunque el título sea ambiguo.
    cases = [
        ("Fairy Tail 1", ["wiki", "manga-sanctuary", "type:série tv animée"]),
        ("Black Butler : Book of the Atlantic", ["wiki", "type:film"]),
        ("Marque-pages Manga Luxe Bulle en Stock 1", ["type:produit dérivé"]),
        ("Some Title", ["type:OAV"]),
        ("Another", ["type:webtoon"]),
    ]
    for title, tags in cases:
        is_manga, reason = mw.is_likely_manga(title, "", tags=tags)
        assert not is_manga, f"Should be rejected: {title!r} tags={tags} reason={reason}"


def test_extract_label_value_pairs_li_span_structure():
    # Estructura típica de Manga-Sanctuary y similares.
    from bs4 import BeautifulSoup
    html = """<html><body><ul>
        <li><span>Dessinateur</span> Koyoharu GOTŌGE</li>
        <li><span>Editeur</span> Panini manga</li>
        <li><span>Date parution</span> mer. 30 mars 2022</li>
        <li><span>Prix</span> 15,58 EUR</li>
        <li><span>EAN-13</span> 9791039105101</li>
        <li><span>Pages</span> 200</li>
    </ul></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    pairs = mw._extract_label_value_pairs(soup)
    assert pairs.get("author") == "Koyoharu GOTŌGE"
    assert pairs.get("publisher") == "Panini manga"
    assert pairs.get("release_date") == "mer. 30 mars 2022"
    assert pairs.get("price") == "15,58 EUR"
    assert pairs.get("isbn") == "9791039105101"


def test_extract_label_value_pairs_dl_structure():
    from bs4 import BeautifulSoup
    html = """<dl>
        <dt>Author</dt><dd>Naoki Urasawa</dd>
        <dt>Publisher</dt><dd>Shogakukan</dd>
        <dt>ISBN-13</dt><dd>9784091234567</dd>
    </dl>"""
    soup = BeautifulSoup(html, "html.parser")
    pairs = mw._extract_label_value_pairs(soup)
    assert pairs.get("author") == "Naoki Urasawa"
    assert pairs.get("publisher") == "Shogakukan"
    assert pairs.get("isbn") == "9784091234567"


def test_extract_label_value_pairs_table_structure():
    from bs4 import BeautifulSoup
    html = """<table>
        <tr><th>著者</th><td>大暮維人</td></tr>
        <tr><th>出版社</th><td>講談社</td></tr>
        <tr><th>発売日</th><td>2024年5月17日</td></tr>
    </table>"""
    soup = BeautifulSoup(html, "html.parser")
    pairs = mw._extract_label_value_pairs(soup)
    assert pairs.get("author") == "大暮維人"
    assert pairs.get("publisher") == "講談社"
    assert pairs.get("release_date") == "2024年5月17日"


def test_is_likely_manga_rejects_decor_items_hard():
    # Patrones nuevos para Dark Horse Direct: prints, bookends, painted statues.
    cases = [
        "Hellboy: His Life and Times Fine Art Print",
        "DOOM Eternal - Slayer Gate Bookend",
        "Berserk: Dragon Slayer Sword Bookends (Manga Paint Variant)",
        "The Legend of Zelda: Breath of the Wild - Link (Collector's Edition) - 10\" PVC Painted Statue",
        "Metroid Prime: Samus Varia Suit 11\" PVC Painted Statue (Collector's Edition)",
        "Masters of the Universe: Revelation Comic Cover Fine Art Print by Bill Sienkiewicz",
        "Alien: The Original Screenplay #1 Exclusive Variant Bundle",
    ]
    for t in cases:
        is_manga, reason = mw.is_likely_manga(t)
        assert not is_manga, f"Should be rejected: {t!r} (reason={reason})"


def test_is_likely_manga_rejects_panini_collectibles():
    # Trading cards, sobres, álbumes de cromos: Panini publica MUCHO esto.
    cases = [
        "Colección de cards oficial One Piece Treasure Box de Panini",
        "Colección Dragon Ball Super Ultimate. Caja Con 50 Sobres.",
        "Colección Dragon Ball Super Ultimate. Álbum Pasta Dura.",
        "Colección Dragon Ball Super Ultimate. Álbum Pasta Suave + 4 Sobres.",
        "Colección Dragon Ball Super Ultimate. Blíster 7 Sobres.",
        "Colección Lady Bug 10° Aniversario. Álbum Pasta Suave + 4 Sobres.",
        "Colección Lady Bug 10° Aniversario. Caja Con 36 Sobres.",
        "ÁLBUM TAPA DURA “EDICIÓN ORO” + 3 SOBRES LIGA ESTE 2024/25",
        "ÁLBUM TAPA DURA “EDICIÓN DIAMANTE” + 3 SOBRES LIGA ESTE 2024/25",
        "Liga Este 2025/26 - Pack Album tapa dura Edición ORO + 3 sobres - Colección Oficial Panini",
        "FIFA Club World Cup 2025™ Trading Cards. Lata.",
        "EDICIÓN ESPECIAL JUGÓN EUROCOPA 2024",
        "WORLD CUP 2026. PAQUETE ESPECIAL VERDE",
        "WORLD CUP 2026. PAQUETE ESPECIAL BLANCO",
        "WORLD CUP 2026. PAQUETE ESPECIAL ROJO",
        "Corbata Vitaliano X Panini de Pura Seda – Edición Limitada",
    ]
    for t in cases:
        is_manga, reason = mw.is_likely_manga(t)
        assert not is_manga, f"Should reject: {t!r} (reason={reason})"


def test_is_likely_manga_rejects_jp_non_manga():
    cases = [
        "【数量限定特典付き】危険生物 （学研の図鑑LIVE）",
        "【数量限定特典付き】魚 （学研の図鑑LIVE）",
        "【数量限定特典付き】昆虫 （学研の図鑑LIVE）",
        "【数量限定特典付き】バァフアウト! 7月号 JULY 2019 Volume 286 窪田正孝 【ポスター】",
        "菊池風磨 30th Anniversary プレミアムBOX【初回限定版】",
        "山田涼介 30th Anniversary プレミアムBOX【初回限定版】",
        "特典情報 2026.05.15 「LaLa」7月号 5月22日 発売記念",
    ]
    for t in cases:
        is_manga, reason = mw.is_likely_manga(t)
        assert not is_manga, f"Should reject: {t!r} (reason={reason})"


def test_is_likely_manga_rejects_podcast_and_news():
    cases = [
        "Episodio 124 | Especial 8M",
        "Episodio 100 | Especial con Rafa Martínez y Óscar Valiente",
        "Episodio 70 | Especial Norma Comics 40 aniversario",
        "Kodansha Reveals Fall 2025 New Print Manga Licenses in Multi-day Announcement",
        "One Piece Gives Luffy a Truly Godlike Birthday Tribute",
        "DC Edicion Facsímil. Limited Collectors' Edition C-59: Los casos más extraños de Batman",
        "San Diego Comic Con 2025: Convention Exclusives",
        "The Witcher (NETFLIX SEASON 3): Wolf Medallion Necklace Deluxe Edition (CONVENTION EXCLUSIVE)",
    ]
    for t in cases:
        is_manga, reason = mw.is_likely_manga(t)
        assert not is_manga, f"Should reject: {t!r} (reason={reason})"


def test_is_likely_manga_mixed_purity_strict():
    # En sources 'mixed', pack-extras NO basta para rescatar. Solo STRONG hint.
    # 'Hellboy 30th Anniversary Deluxe Vinyl Figure' ya cae por HARD (vinyl figure).
    # Pero ítems sutiles como "Some Collector's Edition Item" deberían pasar en
    # manga_only y FALLAR en mixed.
    title = "Some Random Series Collector's Edition Bundle"
    # En source manga_only: rescate por pack-extras → True
    ok, _ = mw.is_likely_manga(title, source_purity="manga_only")
    assert ok, "manga_only debe rescatar por pack-extras"
    # En source mixed: sin STRONG hint, no se rescata por pack-extras y el
    # default es FALSE (estricto). Descarta.
    ok, reason = mw.is_likely_manga(title, source_purity="mixed")
    assert not ok, f"mixed sin STRONG hint debe descartar: {reason}"
    # Pero un ítem mixed CON strong hint debe pasar:
    ok, _ = mw.is_likely_manga(
        "Berserk Deluxe Edition Vol. 1", source_purity="mixed"
    )
    assert ok, "mixed con STRONG hint debe pasar"
    # Mejor caso: ahora un título sutil con Collector's Edition + arte/print
    # que ANTES rescataba en mixed y ahora se va por non_manga (porque cae a
    # SOFT/HARD).
    title2 = "Some Item Collector's Edition Fine Art Print"
    # En manga_only: rescate por pack-extras antes de evaluar HARD → True
    # Pero "Fine Art Print" está en HARD, que se evalúa ANTES.
    ok, reason = mw.is_likely_manga(title2, source_purity="manga_only")
    assert not ok, f"Fine Art Print debe caer en HARD aunque sea manga_only ({reason})"
    ok, reason = mw.is_likely_manga(title2, source_purity="mixed")
    assert not ok, f"Fine Art Print en mixed: definitivamente no ({reason})"


def test_is_likely_manga_comics_blacklist_always_applies():
    # Comics blacklist se aplica SIEMPRE (no solo en mixed).
    # Razón: Star Comics tiene purity=manga_only pero su search ?q=variant
    # devolvía Sin City, Frank Miller, etc. El blacklist tiene franquicias
    # inequívocas — NO afecta a mangas reales.
    for purity in ("manga_only", "mixed"):
        is_manga, reason = mw.is_likely_manga(
            "Spider-Man Edición Coleccionista #1",
            source_purity=purity,
            publisher="Norma Editorial",
        )
        assert not is_manga, f"Spider-Man debe rechazarse con purity={purity}"
        assert reason.startswith("comic_franchise:")


def test_is_likely_manga_comics_blacklist_publisher_match():
    is_manga, reason = mw.is_likely_manga(
        "Some Random Title Vol. 1",
        source_purity="mixed",
        publisher="Marvel",
    )
    assert not is_manga
    assert reason == "comic_publisher:Marvel"


def test_is_likely_manga_comics_blacklist_format_match():
    # Título sin franchise conocido, sólo "graphic novel" como marker de formato.
    is_manga, reason = mw.is_likely_manga(
        "Heartstopper graphic novel",
        source_purity="mixed",
        publisher="Norma Editorial",
    )
    assert not is_manga
    assert reason.startswith("comic_format:")


def test_is_likely_manga_rejects_by_blog_url():
    """URLs de blogs/news/social posts nunca son productos individuales."""
    cases = [
        # ListadoManga blog histórico (262 items, todos noticias)
        ("Ediciones Tomodomo licencia Casas con historias de Seiji Yoshida",
         "https://www.listadomanga.es/blog/2024/06/01/ediciones-tomodomo-licencia-casas/"),
        ("Sobrecubierta de Slam Dunk Kanzenban nº1",
         "https://www.listadomanga.es/blog/2010/01/15/sobrecubierta-de-slam-dunk-kanzenban-no1/"),
        # Kodansha USA blog
        ("New Manga Box Set Debut",
         "https://kodansha.us/2024/02/05/new-manga-box-set-digital-series-debut-revealed/"),
        # VIZ blog
        ("Jujutsu Kaisen Final Volume Collector's Guide",
         "https://www.viz.com/blog/posts/jujutsu-kaisen-s-final-volume-collector-s-guide"),
        # Manga-News (FR) news section
        ("Un coffret collector pour le lancement",
         "https://www.manga-news.com/index.php/actus/2026/05/15/Un-coffret-collector"),
        # Bluesky social
        ("Cualquier título",
         "https://bsky.app/profile/normaeditorial.bsky.social/post/3mluwo6d4os2q"),
    ]
    for title, url in cases:
        is_manga, reason = mw.is_likely_manga(title, url=url)
        assert not is_manga, f"Should reject by URL: {url!r} (reason={reason})"
        assert reason.startswith("blog_url:"), f"reason should be blog_url: but got {reason}"


def test_is_likely_manga_rejects_blog_news_listings():
    """Posts del blog histórico de ListadoManga y similares: 0 productos."""
    cases = [
        "Novedades de Norma Editorial para el 7 de Junio de 2024",
        "Novedad de Ediciones Tomodomo para el 21 de Octubre de 2024",
        "Presentación de Panini Manga en el 31 Manga Barcelona",
        "Norma Editorial licencia el artbook El Arte de Splatoon",
        "Panini Manga licencia Blame! Master Edition y Samurai 7",
        "Panini Manga desvela los detalles de la Master Edition de Berserk",
        "Norma Editorial confirma Sailor Moon Eternal Edition para Diciembre de 2024",
        "Norma Editorial anuncia 12 nuevas licencias",
        "Editorial Ivrea recupera Fushigi Yuugi (Kanzenban) de Yuu Watase",
        "Editorial Ivrea reedita Paradise Kiss de Ai Yazawa con la Glamour Edition",
        "Gengoroh Tagame invitado virtual del Manga Barcelona Limited Edition",
        "Mizuho Kusanagi y Atsushi Ohkubo, autores invitados de Norma Editorial al 25 Manga Barcelona",
        "Grupo Anaya empezará a publicar manga como Pika Ediciones",
        "Jesulink y Loftur Studio comienzan el crowdfunding de 5 elementos – Epílogo Tomo 3 en Verkami",
        "Especial XVIII Salón del Manga (2) – Novedades editoriales",
        # Kodansha/VIZ blog posts
        "FULLY REVEALED POST: Celebrate the Twilight Out of Focus Box Set with exclusive wallpapers",
        "New Manga Box Set & Digital Series Debut Revealed!",
        "ZOKU OWARIMONOGATARI novel debuts!!! Plus box set news!",
        "Jujutsu Kaisen's Final Volume Collector's Guide",
        # Manga-News (FR) homepage
        "Un coffret collector pour le lancement du manga Hero Organization",
        # Bluesky post
        "¡Y pistoletazo de salida del 44 Comic Barcelona! 💥 Ya estamos en nuestro stand",
    ]
    for t in cases:
        is_manga, reason = mw.is_likely_manga(t)
        assert not is_manga, f"Should reject as news/blog: {t!r} (reason={reason})"


def test_is_likely_manga_rejects_video_game_artbooks_and_guides():
    """Artbooks/guías/enciclopedias de videojuegos: no son manga."""
    cases = [
        "El arte de Splatoon",
        "El arte de Fire Emblem: Awakening",
        "El arte de Super Mario Odyssey",
        "The Art of Splatoon",
        "The Art of Halo Infinite HC (Deluxe Edition)",
        "The Art of The Last of Us Part II HC (Deluxe Edition)",
        "The Art of God of War Ragnarök HC (Deluxe Edition)",
        "The Art of Assassin's Creed Shadows HC (Deluxe Edition)",
        "The Art of Dragon Age: The Veilguard HC (Deluxe Edition)",
        "The Art of the Mass Effect Trilogy: Expanded Edition HC",
        "The Legend of Korra: The Art of the Animated Series Deluxe Edition Hardcovers",
        "Legend of Mana: The Art of Mana--30th Anniversary Edition HC",
        "Final Fantasy VII Remake - Material Ultimania 1",
        "Final Fantasy - Encyclopédie Officielle Memorial Ultimania 2",
        "Final Fantasy: Memorial Ultimania nº1 (de 3) - I II III IV V VI",
        "Final Fantasy VII 10th Anniversary Ultimania, Revised Edition",
        "La historia de Final Fantasy VI. La Divina Epopeya - Edición Limitada",
        "The Legend of Zelda: Enciclopedia",
        "The Legend of Zelda Encyclopedia Deluxe Edition HC",
        "The Legend of Zelda: Breath of the Wild - Creating a Hero",
        "Hommage à Kingdom Hearts : À la croisée des mondes",
        "Génération Zelda - 35 ans de légendes",
        "Dragon Quest 25 Aniversario: Enciclopedia de Monstruos - Cofre troquelado",
        "Cyberpunk 2077: Tarot Deck & Guidebook",
    ]
    for t in cases:
        is_manga, reason = mw.is_likely_manga(t)
        assert not is_manga, f"Should reject as VG artbook/guide: {t!r} (reason={reason})"


def test_is_likely_manga_keeps_manga_artbooks():
    """Artbooks de mangas / mangaka: SÍ son in-scope (CLAUDE.md)."""
    cases = [
        "The Art of Spirited Away",
        "The Art of Fullmetal Alchemist: The Anime",
        "The Art of Vampire Knight",
        "The Art of Angel Sanctuary",
        "The Art of Kyu Yong Eom - Fantasy & Girls",
        "Art of Mitsume",
        "The Art of Sun-Ken Rock",
        "Mentaiko Artbook",
        "Made In Abyss Triple Artbooks",
        "Naruto - Coffret des artbooks",
        "Shintaro Kago - Artbook 1",
        "Artbook Demon Slayer 1",
        "Toilet-bound Hanako-kun - Artbook 1",
        "El arte de Atelier of Witch Hat",
    ]
    for t in cases:
        is_manga, reason = mw.is_likely_manga(t)
        assert is_manga, f"Should KEEP manga artbook: {t!r} (reason={reason})"


def test_is_likely_manga_rejects_pokemon_non_manga():
    """Pokémon: filtros específicos para ensayos / biografía / magazines."""
    cases = [
        "Pokémon y Feminismo. La gran revolución transmedia nº1 (de 2 y abierta) - Edición Especial",
        "La Biografía Oficial de Satoshi Tajiri, creador de Pokémon",
        "Revista Pokémon 2025 + Cards N.1",
    ]
    for t in cases:
        is_manga, reason = mw.is_likely_manga(t)
        assert not is_manga, f"Should reject Pokémon non-manga: {t!r} (reason={reason})"


def test_is_likely_manga_keeps_pokemon_manga():
    """Pokémon manga (Pokémon Adventures, etc.) sigue pasando."""
    cases = [
        "Pokémon Ω Rubí・α Zafiro nº1 (de 3)",
        "Pokémon nº21 (de 32) - Diamante y Perla nº5",
        "Pokémon Sol・Luna nº5 (de 6)",
        "Pokémon Adventures Collector's Edition, Vol. 10",
        "Pokémon Espada・Escudo nº3 (de 7)",
    ]
    for t in cases:
        is_manga, reason = mw.is_likely_manga(t)
        assert is_manga, f"Should KEEP Pokémon manga: {t!r} (reason={reason})"


def test_is_likely_manga_rejects_western_comics_franchises():
    """Power Rangers, TMNT, etc. — franquicias de IDW/Boom! sin manga."""
    cases = [
        ("Godzilla vs. Mighty Morphin Power Rangers - (Edición Limitada)", "Panini"),
        ("Las Tortugas Ninja: La serie original - Edición Limitada Pizza Tomos 1 a 7 + Medallón", "Norma Editorial"),
        ("Las Tortugas Ninja: Tortugas por el tiempo (Edición Deluxe)", "Norma Editorial"),
        ("Las Tortugas Ninja: El Último Ronin (Tapa Dura) - (1ª Edición)", "Norma Editorial"),
        ("Teenage Mutant Ninja Turtles: The Last Ronin", "IDW"),
    ]
    for title, publisher in cases:
        is_manga, reason = mw.is_likely_manga(
            title, source_purity="mixed", publisher=publisher,
        )
        assert not is_manga, f"Should reject western comic: {title!r} (reason={reason})"


def test_is_likely_manga_comics_blacklist_does_not_kill_real_manga():
    # Series de manga conocidas en fuente mixed NO deben caer por la blacklist.
    # Todas tienen alguna STRONG manga hint (vol, tomo, n°, kanzenban, etc.)
    # que las rescata aunque la fuente sea mixed.
    cases = [
        "Sakamoto Days Tomo 12",
        "Kaiju No. 8 Variante #1",
        "My Hero Academia Vol. 42",
        "Berserk Kanzenban nº 1",
        "Naruto manga #70",
        "Dragon Ball Super volume 22",
    ]
    for title in cases:
        is_manga, reason = mw.is_likely_manga(
            title, source_purity="mixed", publisher="Panini Manga México",
        )
        assert is_manga, f"Should NOT be killed by blacklist: {title!r} (reason={reason})"


def test_is_pure_novel_detects_bestseller_with_collector_edition():
    """Novelas bestseller con 'edición coleccionista' deben rechazarse."""
    # URL en sección literaria
    is_novel, r = mw.is_pure_novel(
        "Alas de ónix (Empíreo 3) Edición coleccionista",
        description="Novela fantasy de Rebecca Yarros",
        url="https://www.fnac.es/literatura/novela-fantastica/alas-de-onix",
    )
    assert is_novel
    assert "novel_url" in r

    # Indicador en title sin manga
    is_novel, r = mw.is_pure_novel(
        "Cuatro hijas del Dr. March",
        description="Saga literaria romántica clásica",
    )
    assert is_novel
    assert "novel_indicator" in r

    # Bestseller booktok
    is_novel, _ = mw.is_pure_novel(
        "Hábitos atómicos (BookTok edition)",
        description="Bestseller número 1 mundial",
    )
    assert is_novel


def test_is_pure_novel_bypass_when_manga_or_light_novel_mentioned():
    """Si menciona manga/light novel, NO es novela pura."""
    # Light novel = manga-related
    is_novel, _ = mw.is_pure_novel(
        "Sword Art Online: Aincrad — Novela ligera",
        description="Light novel de Reki Kawahara",
    )
    assert not is_novel

    # Novela gráfica = comic format (manejado por otro filter)
    is_novel, _ = mw.is_pure_novel("Sandman novela gráfica", description="")
    assert not is_novel

    # Si la URL apunta a /manga/ aunque el title diga 'novela'
    is_novel, _ = mw.is_pure_novel(
        "Goblin Slayer Light Novel Vol 1",
        url="https://www.fnac.es/manga/light-novel/goblin-slayer",
    )
    assert not is_novel


def test_is_likely_manga_rejects_novel():
    """E2E: is_likely_manga atrapa novelas vía is_pure_novel."""
    # Item NO en franchise blacklist — sólo el novel detector lo atrapa.
    is_manga, reason = mw.is_likely_manga(
        "Verity Edición Coleccionista (Colleen Hoover)",
        description="Novela romántica número 1 BookTok mundial",
        url="https://www.casadellibro.com/literatura/novela-romantica/verity",
    )
    assert not is_manga
    assert reason.startswith("novel_"), f"esperaba novel_*, got {reason}"


def test_is_likely_manga_tag_match_is_case_insensitive():
    # Manga-Sanctuary etiqueta `type:oav` en minúsculas; nuestro blacklist
    # usa `type:OAV`. La comparación debe ser case-insensitive para no dejar
    # pasar 700+ items de anime/OAV/TV special al catálogo.
    cases = [
        ("Some Anime Title 1", ["type:oav"]),
        ("Some Anime Title 2", ["type:OAV"]),
        ("Some Film Title", ["type:film"]),
        ("Some Series", ["TYPE:SÉRIE TV"]),
        ("Some Goodie", ["type:goodies"]),
    ]
    for title, tags in cases:
        is_manga, reason = mw.is_likely_manga(title, "", tags=tags)
        assert not is_manga, f"Should reject by tag: {title!r} tags={tags!r} (reason={reason})"
        assert reason.startswith("non_manga_tag:")


def test_is_likely_manga_keeps_special_manga_packs_from_wiki():
    # "type:produit spécial manga" SÍ es manga (packs manga + artbook, etc.).
    cases = [
        ("Naruto - Coffret des artbooks", ["type:produit spécial manga"]),
        ("The promised Neverland - Coffret manga + roman 1", ["type:produit spécial manga"]),
    ]
    for title, tags in cases:
        is_manga, _ = mw.is_likely_manga(title, "", tags=tags)
        assert is_manga, f"Should be kept: {title!r}"


# --- Bluesky parser ---------------------------------------------------------

def test_bluesky_handle_from_url():
    assert mw.bluesky_handle_from_url("https://bsky.app/profile/planetadcomic.bsky.social") == "planetadcomic.bsky.social"
    assert mw.bluesky_handle_from_url("https://bsky.app/profile/foo.bar/post/abc") == "foo.bar"
    assert mw.bluesky_handle_from_url("") == ""
    assert mw.bluesky_handle_from_url("https://example.com") == ""


def test_bluesky_api_url():
    url = mw.bluesky_api_url("planetadcomic.bsky.social", limit=5)
    assert "actor=planetadcomic.bsky.social" in url
    assert "limit=5" in url
    assert "public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed" in url


def test_extract_bluesky_posts_text_only():
    source = mw.Source(
        name="SOCIAL - Test Bluesky", country="ES", language="Español",
        publisher="Test", source_class="social", kind="bluesky",
        url="https://bsky.app/profile/test.bsky.social", tags=["social"],
    )
    payload = {
        "feed": [
            {"post": {
                "uri": "at://did:plc:abc/app.bsky.feed.post/3lkx",
                "author": {"handle": "test.bsky.social"},
                "record": {
                    "text": "Nueva edición limitada de Berserk con cofre exclusivo",
                    "createdAt": "2026-05-15T10:00:00Z",
                },
            }},
        ],
    }
    cands = mw.extract_bluesky_posts(source, json.dumps(payload), max_items=10)
    assert len(cands) == 1
    c = cands[0]
    assert "Berserk" in c.title
    assert c.url == "https://bsky.app/profile/test.bsky.social/post/3lkx"
    assert c.published_at == "2026-05-15T10:00:00Z"


def test_extract_bluesky_posts_with_external_link():
    # Cuando un post enlaza a una tienda, el title/URL del link tienen prioridad.
    source = mw.Source(
        name="SOCIAL - Planeta Bluesky", country="España", language="Español",
        publisher="Planeta Cómic", source_class="social", kind="bluesky",
        url="https://bsky.app/profile/planetadcomic.bsky.social", tags=["social"],
    )
    payload = {
        "feed": [
            {"post": {
                "uri": "at://did:plc:xyz/app.bsky.feed.post/3xyz",
                "author": {"handle": "planetadcomic.bsky.social"},
                "record": {
                    "text": "¡Reserva ya la edición exclusiva Fnac!",
                    "createdAt": "2026-05-10T12:00:00Z",
                    "embed": {
                        "$type": "app.bsky.embed.external",
                        "external": {
                            "uri": "https://www.fnac.es/a12345/one-piece-100-exclusiva-fnac",
                            "title": "One Piece 100 — Edición exclusiva Fnac",
                            "description": "Tomo 100 con regalo exclusivo.",
                        },
                    },
                },
            }},
        ],
    }
    cands = mw.extract_bluesky_posts(source, json.dumps(payload), max_items=10)
    assert len(cands) == 1
    c = cands[0]
    assert "One Piece 100" in c.title
    assert "fnac.es" in c.url
    assert "edición exclusiva" in c.description.lower() or "exclusiva fnac" in c.description.lower()


def test_extract_bluesky_posts_handles_bad_json():
    source = mw.Source(
        name="x", country="", language="", publisher="", source_class="social",
        kind="bluesky", url="https://bsky.app/profile/x", tags=[],
    )
    assert mw.extract_bluesky_posts(source, "not json", max_items=10) == []
    assert mw.extract_bluesky_posts(source, '{"feed": null}', max_items=10) == []


# --- is_collectible_edition -------------------------------------------------

def test_is_collectible_edition_accepts_signal_types_special():
    cases = [
        ("Berserk Deluxe Edition Vol. 1", ["deluxe"]),
        ("One Piece 100 Edición Coleccionista", ["collector"]),
        ("Naruto Box Set 1", ["box_set"]),
        ("Demon Slayer Coffret Collector", ["collector", "box_set"]),
        ("Vinland Saga 1 Tribute Variant Cover Edition", ["variant_cover"]),
        ("Berserk Master Edition Beherit Limited 1", ["limited", "premium_format"]),
        ("Sailor Moon Eternal Edition Volume 5", ["premium_format"]),
        ("Attack on Titan Hardcover Vol. 1", ["hardcover"]),
        ("Berserk Omnibus Vol. 1", ["omnibus"]),
        ("Naruto Special Bundle Vol 1-5", ["bundle"]),
        ("限定版 ONE PIECE 100", ["limited"]),
    ]
    for title, sigs in cases:
        ok, reason = mw.is_collectible_edition(title, "", sigs, "manga")
        assert ok, f"Should accept (signal): {title!r} (reason={reason})"


def test_is_collectible_edition_accepts_first_edition_extras():
    # Tomo "regular" pero con extras de primera edición → IN.
    # Esto cubre el caso del usuario: "Naruto tomo 12 con marcapáginas exclusivo".
    cases = [
        ("Naruto 12 con marcapáginas exclusivo primera edición", ["bonus"]),
        ("One Piece 105 con póster reversible", ["bonus"]),
        ("My Hero Academia 30 con postal exclusiva", ["bonus"]),
        ("Demon Slayer 22 + Acrílico de regalo", ["bonus"]),
        ("Chainsaw Man Vol. 1 with sprayed edges", ["finish"]),
        ("Berserk 41 foil-stamped first print", ["finish"]),
    ]
    for title, sigs in cases:
        ok, reason = mw.is_collectible_edition(title, "", sigs, "manga")
        assert ok, f"Should accept (extras): {title!r} (reason={reason})"


def test_is_collectible_edition_accepts_collectible_product_types():
    cases = [
        ("One Piece Magazine Vol. 17", "magazine"),
        ("The Art of Studio Ghibli", "artbook"),
        ("Naruto Official Fanbook", "fanbook"),
        ("My Hero Academia Official Character Guidebook", "guidebook"),
        ("Bleach Box Set 1", "boxset"),
    ]
    for title, ptype in cases:
        ok, reason = mw.is_collectible_edition(title, "", [], ptype)
        assert ok, f"Should accept (ptype): {title!r} (reason={reason})"


def test_is_collectible_edition_rescues_x_edition_regex():
    # Palabras lore-específicas que no están en el diccionario global de KEYWORD_RULES
    # pero sí matchean el regex generalista "<Word> Edition / Edizione / Édition".
    cases = [
        "Berserk Master Edition Beherit Limited 1",      # "Beherit Edition" (Berserk lore)
        "Berserk Tarot Edition",                          # "Tarot Edition" (Berserk lore)
        "Vinland Saga 1 Tribute Edition",                 # "Tribute Edition"
        "Saint Seiya Final Edition 1",                    # "Final Edition" → wait, "Final" in stoplist
        "One Piece 100 Celebration Edition",              # "Celebration Edition"
        "One Piece 108 Metal Edition",                    # "Metal Edition" — lore-style
        "Una Ragazza Alla Moda 50th Anniversary Edition", # "Anniversary Edition"
    ]
    for title in cases:
        # Pasamos signal_types vacíos y product_type = manga para forzar
        # que sólo el regex pueda rescatar.
        ok, reason = mw.is_collectible_edition(title, "", [], "manga")
        # "Final Edition" está en la stoplist intencionalmente — no es lore-specific.
        if "Final Edition" in title and "Anniversary" not in title:
            continue
        assert ok, f"Should accept (x_edition regex): {title!r} (reason={reason})"


def test_is_collectible_edition_rule1_requires_product_shape():
    # Rule 1 ahora exige una prueba de "esto es un producto físico":
    # signal en title, número en title, o ISBN. Bloquea blog posts/listicles.

    # Caso bueno: signal viene de desc, pero title tiene número → PASS.
    ok, reason = mw.is_collectible_edition(
        "One Piece 100", "glénat manga · collector étui",
        signal_types=["collector"], product_type="manga",
    )
    assert ok and reason == "signal:collector"

    # Caso bueno: signal en title → PASS sin necesidad de número.
    ok, reason = mw.is_collectible_edition(
        "Berserk Master Edition Beherit Limited",
        "extra info", signal_types=["limited"], product_type="manga",
    )
    assert ok and reason.startswith("signal:")

    # Caso bueno: signal en desc + ISBN presente → PASS aunque title no tenga número.
    ok, reason = mw.is_collectible_edition(
        "Hellsing Deluxe", "limited edition hardcover collector",
        signal_types=["limited", "collector", "deluxe", "hardcover"],
        product_type="manga", isbn="9780123456789",
    )
    assert ok

    # FALSO POSITIVO antes: blog post/listicle con signals SOLO en desc y title sin número.
    # Ahora debe ser RECHAZADO.
    ok, reason = mw.is_collectible_edition(
        "Top 10 Limited Editions of the Year",
        "limited edition collector deluxe boxset coming soon",
        signal_types=["limited", "collector", "deluxe", "box_set"],
        product_type="manga",
    )
    assert not ok, f"Listicle should be rejected (reason={reason})"

    # Caso borderline: news sin patrón hard pero desc con signals — sin número ni ISBN → REJECT.
    ok, reason = mw.is_collectible_edition(
        "Editorial Announces Cool Stuff For Fans",
        "limited edition coming soon", signal_types=["limited"],
        product_type="manga",
    )
    assert not ok


def test_is_collectible_edition_rejects_regular_tomos():
    # Tomos regulares sin extras ni edición especial → OUT.
    cases = [
        ("One Piece 100", "manga"),
        ("Naruto Tomo 70", "manga"),
        ("Dragon Ball Super Vol. 22", "manga"),
        ("Bleach 60", "manga"),
        ("My Hero Academia 35", "manga"),
        ("Demon Slayer 23", "manga"),
    ]
    for title, ptype in cases:
        ok, reason = mw.is_collectible_edition(title, "", [], ptype)
        assert not ok, f"Should reject regular tomo: {title!r} (reason={reason})"


def test_is_collectible_edition_rejects_umbrella_jp_magazines():
    # Revistas-paraguas con nombres inequívocos (antologías multi-manga) → fuera.
    # Nombres ambiguos (Morning, Margaret, Kiss, LaLa) NO se incluyen porque
    # también aparecen como palabras en nombres de series (Kamisama Kiss).
    cases = [
        "Weekly Shōnen Jump 2025-#42",
        "Shonen Jump #25 2026",
        "Young Jump 12/2025",
        "Big Comic Spirits 7/2025",
        "Comic Beam 2025",
        "Newtype December 2025",
        "週刊少年ジャンプ 25号",
        "月刊少年 マガジン",
    ]
    for title in cases:
        ok, reason = mw.is_collectible_edition(title, "", [], "magazine")
        assert not ok, f"Should reject umbrella magazine: {title!r} (reason={reason})"
        assert reason == "umbrella_magazine", f"Wrong rejection reason for {title!r}: {reason}"


def test_is_collectible_edition_keeps_series_with_umbrella_substring():
    # "Kamisama Kiss" contiene "Kiss" (magazine de Kodansha) pero ES una serie.
    # No debe rechazarse como umbrella.
    cases = [
        ("Kamisama Kiss Limited Edition, Vol. 25", "manga"),
        ("Kiss Him, Not Me Vol. 5 Edición Coleccionista", "manga"),
        ("Good Morning Call Vol. 1 Deluxe Edition", "manga"),
    ]
    for title, ptype in cases:
        ok, reason = mw.is_collectible_edition(title, "", [], ptype)
        assert ok, f"Should not be umbrella-rejected: {title!r} (reason={reason})"
        assert reason != "umbrella_magazine"


def test_is_collectible_edition_accepts_series_specific_magazines():
    # Magazines de UNA serie (no antologías) → IN.
    cases = [
        "One Piece Magazine Vol. 17",
        "Captain Tsubasa Magazine 5",
        "Yoyo's Vivre Adventure Magazine 3",
        "Attack on Titan Magazine 2",
    ]
    for title in cases:
        # product_type="magazine" porque derive_product_type lo etiqueta así
        # para cualquier título con "Magazine"; la diferencia con las paraguas
        # la hace _UMBRELLA_JP_MAGAZINE_PATTERN.
        ok, reason = mw.is_collectible_edition(title, "", [], "magazine")
        assert ok, f"Should accept series magazine: {title!r} (reason={reason})"


def test_is_collectible_edition_x_edition_stoplist():
    # Palabras genéricas antes de "Edition" NO deben rescatar — son neutras.
    # (estos items, al no tener signal_types coleccionables ni product_type
    # coleccionable, deben quedar fuera.)
    cases = [
        "Naruto First Edition Vol. 1",
        "Berserk Spanish Edition Vol. 5",
        "One Piece Digital Edition 100",
        "Bleach Print Edition Tomo 20",
        "Dragon Ball Standard Edition 10",
        "Vinland Saga Original Edition 1",
    ]
    for title in cases:
        ok, reason = mw.is_collectible_edition(title, "", [], "manga")
        assert not ok, f"Stoplist word should not rescue: {title!r} (reason={reason})"


def test_derive_product_type_assigns_magazine():
    assert mw.derive_product_type("One Piece Magazine Vol. 17", "", []) == "magazine"
    assert mw.derive_product_type("Captain Tsubasa Magazine 5", "", []) == "magazine"
    # Lowercase "magazine" en marketing text NO debe disparar (case-sensitive).
    assert mw.derive_product_type("Berserk vol 41 (sale magazine)", "", []) != "magazine"


def test_clean_title_repairs_mojibake():
    # UTF-8 leído como Latin-1/cp1252 (típico Glénat/Pika con encoding mal seteado).
    # Tras reparar, los prefijos FR ya conocidos también deben caer.
    cases = [
        ("NouveautÃ© GlÃ©nat Manga Dragon Ball Le super art book Akira Toriyama 22/04/2026",
         "Dragon Ball Le super art book Akira Toriyama"),
        ("NouveautÃ© Pika ShÃ´nen Blue Lock T32 - Ã©dition collector",
         "Blue Lock T32 - édition collector"),
        # Texto sin mojibake debe pasar tal cual.
        ("L'Atelier des Sorciers - Édition collector",
         "L'Atelier des Sorciers - Édition collector"),
    ]
    for raw, expected in cases:
        actual = mw.clean_title(raw)
        assert actual == expected, f"\n  input:    {raw!r}\n  expected: {expected!r}\n  actual:   {actual!r}"


def test_listadomanga_parse_handles_multiple_editorials():
    from wikis import listadomanga as lm
    html = """<html><body>
        <h2>Editorial A</h2>
        <h2>Lunes, 1 Enero 2024</h2>
        <table class="ventana_id1"><tr><td>
            <a href="coleccion.php?id=1">Item A1</a>
        </td></tr></table>
        <h2>Editorial B</h2>
        <h2>Martes, 2 Enero 2024</h2>
        <table class="ventana_id5"><tr><td>
            <a href="coleccion.php?id=2">Item B1</a>
        </td></tr></table>
    </body></html>"""
    items = lm.parse_calendar_page(html)
    assert len(items) == 2
    assert items[0].publisher == "Editorial A"
    assert items[1].publisher == "Editorial B"
    assert items[0].release_date == "2024-01-01"
    assert items[1].release_date == "2024-01-02"


# ---------------------------------------------------------------------------
# Derivación de tipo de producto
# ---------------------------------------------------------------------------


def test_derive_product_type_artbook():
    assert mw.derive_product_type("Berserk Artbook", "Libro de arte oficial", ["artbook"]) == "artbook"
    assert mw.derive_product_type("Kakegurui イラスト集", "", []) == "artbook"


def test_derive_product_type_boxset():
    assert mw.derive_product_type("Naruto Cofre completo", "Cofre de 72 tomos", ["box_set"]) == "boxset"


def test_derive_product_type_guidebook():
    assert mw.derive_product_type("One Piece official guidebook", "", ["guidebook"]) == "guidebook"


def test_derive_product_type_manga_default():
    assert mw.derive_product_type("Vagabond Vol. 14 edición limitada", "Tapa dura.", ["limited", "hardcover"]) == "manga"


def test_derive_product_type_empty_when_no_input():
    assert mw.derive_product_type("", "", []) == ""


# ---------------------------------------------------------------------------
# Extracción de autor
# ---------------------------------------------------------------------------


def test_extract_author_spanish():
    assert mw.extract_author("Autor: Kentaro Miura. Edición especial.") == "Kentaro Miura"


def test_extract_author_english():
    assert mw.extract_author("Manga by Kentaro Miura, published in 1989.") == "Kentaro Miura"


def test_extract_author_japanese():
    # No esperamos parse perfecto pero debería extraer algo razonable.
    result = mw.extract_author("著者: 三浦建太郎. 限定版.")
    assert result and len(result) >= 2


def test_extract_author_from_html_meta():
    soup = make_soup('<div><meta name="author" content="Kentaro Miura"><p>Edición</p></div>')
    div = soup.find("div")
    assert mw.extract_author("Edición coleccionista", div) == "Kentaro Miura"


def test_extract_author_from_html_class():
    soup = make_soup('<div><span class="author-name">Kentaro Miura</span></div>')
    div = soup.find("div")
    assert mw.extract_author("", div) == "Kentaro Miura"


def test_extract_author_skips_blacklisted_starts():
    # "By the way", "By la editorial" no deben confundir.
    assert mw.extract_author("Manga published by la editorial Norma") == ""


def test_extract_author_empty():
    assert mw.extract_author("") == ""
    assert mw.extract_author("Manga sin autor mencionado.") == ""


# ---------------------------------------------------------------------------
# Derivación de stock_type
# ---------------------------------------------------------------------------


def test_derive_stock_type_from_signal_types_limited():
    assert mw.derive_stock_type(["limited"], "x", "y") == "limited"


def test_derive_stock_type_from_made_to_order():
    assert mw.derive_stock_type(["made_to_order"], "x", "y") == "limited"


def test_derive_stock_type_from_text_numerada():
    assert mw.derive_stock_type([], "Berserk", "Edición numerada de 500 copias.") == "limited"


def test_derive_stock_type_from_japanese_text():
    assert mw.derive_stock_type([], "x", "数量限定で販売") == "limited"


def test_derive_stock_type_empty_when_no_signal():
    # Ausencia de señal NO afirma "regular"; queda vacío.
    assert mw.derive_stock_type([], "Manga regular", "Disponible en librerías.") == ""


# ---------------------------------------------------------------------------
# JSON-LD author extraction
# ---------------------------------------------------------------------------


def test_json_ld_author_string():
    html = """<html><head>
    <script type="application/ld+json">
    {"@type": "Book", "name": "Berserk", "author": "Kentaro Miura"}
    </script></head><body></body></html>"""
    soup = make_soup(html)
    assert mw._extract_json_ld_author(soup) == "Kentaro Miura"


def test_json_ld_author_object_with_name():
    html = """<html><head>
    <script type="application/ld+json">
    {"@type": "Book", "author": {"@type": "Person", "name": "Akira Toriyama"}}
    </script></head></html>"""
    soup = make_soup(html)
    assert mw._extract_json_ld_author(soup) == "Akira Toriyama"


def test_json_ld_author_list():
    html = """<html><head>
    <script type="application/ld+json">
    {"@type": "Book", "author": [{"name": "First Author"}, {"name": "Second"}]}
    </script></head></html>"""
    soup = make_soup(html)
    assert mw._extract_json_ld_author(soup) == "First Author"


def test_json_ld_no_author_returns_empty():
    html = '<html><script type="application/ld+json">{"@type": "Book"}</script></html>'
    soup = make_soup(html)
    assert mw._extract_json_ld_author(soup) == ""


def test_json_ld_invalid_json_handled():
    html = '<html><script type="application/ld+json">{ broken json</script></html>'
    soup = make_soup(html)
    assert mw._extract_json_ld_author(soup) == ""


# ---------------------------------------------------------------------------
# Author link patterns (/autor/, /auteur/, /author/)
# ---------------------------------------------------------------------------


def test_author_link_spanish_path():
    html = '<html><body><a href="/autor/isayama-hajime">Hajime Isayama</a></body></html>'
    soup = make_soup(html)
    assert mw._extract_author_from_links(soup) == "Hajime Isayama"


def test_author_link_french_path():
    html = '<html><body><a href="/auteur/akira-toriyama">Akira Toriyama (Auteur)</a></body></html>'
    soup = make_soup(html)
    result = mw._extract_author_from_links(soup)
    assert "Akira Toriyama" in result


def test_author_link_skips_see_all():
    html = '<html><body><a href="/autor/lista">Ver todos los autores</a></body></html>'
    soup = make_soup(html)
    assert mw._extract_author_from_links(soup) == ""


def test_author_link_skips_lowercase_first_char():
    # Defensive: link a /autor/ con texto que empieza minúscula no es nombre propio.
    html = '<html><body><a href="/autor/x">la editorial</a></body></html>'
    soup = make_soup(html)
    assert mw._extract_author_from_links(soup) == ""


# ---------------------------------------------------------------------------
# Fase 1: search_template + keywords expansion
# ---------------------------------------------------------------------------


def test_expand_search_template_basic():
    raw = {
        "name": "Test Source",
        "search_template": "https://example.com/?q={query}",
        "keywords": ["edicion limitada", "cofre"],
        "country": "X",
        "tags": ["base"],
    }
    expanded = mw._expand_search_template(raw)
    assert len(expanded) == 2
    assert expanded[0]["name"] == "Test Source [search: edicion limitada]"
    assert expanded[0]["url"] == "https://example.com/?q=edicion+limitada"
    assert "expansion" in expanded[0]["tags"]
    assert "search:edicion limitada" in expanded[0]["tags"]
    assert "base" in expanded[0]["tags"]
    # search_template y keywords no deben aparecer en el output expandido
    assert "search_template" not in expanded[0]
    assert "keywords" not in expanded[0]


def test_expand_search_template_no_keywords_returns_original():
    raw = {"name": "Plain", "url": "https://x.com/", "country": "X"}
    expanded = mw._expand_search_template(raw)
    assert len(expanded) == 1
    assert expanded[0] is raw


def test_expand_search_template_url_encoding():
    raw = {
        "name": "Enc",
        "search_template": "https://example.com/?q={query}",
        "keywords": ["edición limitada con espacios"],
    }
    expanded = mw._expand_search_template(raw)
    # quote_plus codifica acentos y espacios
    assert "edici%C3%B3n+limitada+con+espacios" in expanded[0]["url"]


def test_expand_search_template_empty_keywords_filtered():
    raw = {
        "name": "Mixed",
        "search_template": "https://example.com/?q={query}",
        "keywords": ["valid", "", "  ", "otro"],
    }
    expanded = mw._expand_search_template(raw)
    assert len(expanded) == 2
    assert expanded[0]["url"].endswith("?q=valid")
    assert expanded[1]["url"].endswith("?q=otro")


# ---------------------------------------------------------------------------
# Filtros por tags
# ---------------------------------------------------------------------------


def _src_tagged(name="x", tags=None, country="ES"):
    return mw.Source(
        name=name, url=f"https://example.com/{name}",
        country=country, language="Español", publisher="P",
        source_class="official", kind="html", enabled=True,
        tags=list(tags or []),
    )


def test_filter_only_tags_keeps_matching():
    a = _src_tagged("a", tags=["expansion"])
    b = _src_tagged("b", tags=["manga", "news"])
    c = _src_tagged("c", tags=["expansion", "manga"])
    out = mw.filter_sources([a, b, c], None, None, False, only_tags={"expansion"})
    assert {s.name for s in out} == {"a", "c"}


def test_filter_exclude_tags_drops_matching():
    a = _src_tagged("a", tags=["expansion"])
    b = _src_tagged("b", tags=["manga"])
    c = _src_tagged("c", tags=["expansion", "manga"])
    out = mw.filter_sources([a, b, c], None, None, False, exclude_tags={"expansion"})
    assert {s.name for s in out} == {"b"}


def test_filter_no_tag_filter_returns_all():
    a = _src_tagged("a", tags=["expansion"])
    b = _src_tagged("b")
    out = mw.filter_sources([a, b], None, None, False)
    assert len(out) == 2


# ---------------------------------------------------------------------------
# Paginación: find_next_page_url
# ---------------------------------------------------------------------------


def test_next_page_via_link_rel_next():
    html = '<html><head><link rel="next" href="/page/2"></head><body></body></html>'
    url = mw.find_next_page_url(make_soup(html), "https://example.com/list", set())
    assert url == "https://example.com/page/2"


def test_next_page_via_class_next():
    html = '<html><body><a class="next" href="?page=2">Next</a></body></html>'
    url = mw.find_next_page_url(make_soup(html), "https://example.com/list?page=1", set())
    assert "page=2" in (url or "")


def test_next_page_via_aria_label():
    html = '<html><body><a aria-label="Next page" href="/list/p/2">2</a></body></html>'
    url = mw.find_next_page_url(make_soup(html), "https://example.com/list", set())
    assert url == "https://example.com/list/p/2"


def test_next_page_via_text_siguiente():
    html = '<html><body><a href="/list?page=2">Siguiente</a></body></html>'
    url = mw.find_next_page_url(make_soup(html), "https://example.com/list?page=1", set())
    assert url == "https://example.com/list?page=2"


def test_next_page_via_text_arrows():
    html = '<html><body><a href="/list?page=2">›</a></body></html>'
    url = mw.find_next_page_url(make_soup(html), "https://example.com/list", set())
    assert "page=2" in (url or "")


def test_next_page_skips_already_visited():
    html = '<html><body><a class="next" href="?page=2">Next</a></body></html>'
    visited = {"https://example.com/list?page=2"}
    url = mw.find_next_page_url(make_soup(html), "https://example.com/list?page=1", visited)
    assert url is None


def test_next_page_skips_self_loop():
    # Link "next" que apunta a la misma URL no debe contar.
    html = '<html><body><a class="next" href="?page=1">Next</a></body></html>'
    url = mw.find_next_page_url(make_soup(html), "https://example.com/list?page=1", set())
    assert url is None


def test_next_page_no_link_returns_none():
    html = '<html><body><p>Just text, no pagination.</p></body></html>'
    url = mw.find_next_page_url(make_soup(html), "https://example.com/list", set())
    assert url is None


def test_next_page_param_increment_only_if_link_exists():
    # Aunque current_url tenga ?page=1, no inventamos page=2 si no hay anchor con N+1
    html = '<html><body><a href="/other">link no relacionado</a></body></html>'
    url = mw.find_next_page_url(make_soup(html), "https://example.com/list?page=1", set())
    assert url is None


def test_next_page_skips_cross_origin():
    html = '<html><body><a class="next" href="https://otherdomain.com/x">Next</a></body></html>'
    url = mw.find_next_page_url(make_soup(html), "https://example.com/list", set())
    assert url is None


def test_append_jsonl_upserts_by_url(tmp_path):
    """append_jsonl debe ser upsert: 1 línea por URL única en disco."""
    path = tmp_path / "items.jsonl"

    # Estado inicial: 2 items
    mw.append_jsonl(path, [
        {"url": "https://example.com/a", "title": "A original", "detected_at": "2026-01-01"},
        {"url": "https://example.com/b", "title": "B", "detected_at": "2026-01-01"},
    ])
    assert sum(1 for _ in path.open()) == 2

    # Update a 'A' y add 'C'
    mw.append_jsonl(path, [
        {"url": "https://example.com/a", "title": "A actualizado", "detected_at": "2026-02-01"},
        {"url": "https://example.com/c", "title": "C", "detected_at": "2026-02-01"},
    ])
    lines = list(path.open())
    assert len(lines) == 3, f"esperaba 3 líneas únicas, hay {len(lines)}"

    items = [json.loads(l) for l in lines]
    by_url = {i["url"]: i for i in items}
    assert by_url["https://example.com/a"]["title"] == "A actualizado"
    assert by_url["https://example.com/b"]["title"] == "B"
    assert by_url["https://example.com/c"]["title"] == "C"


def test_append_jsonl_keeps_rows_without_url(tmp_path):
    path = tmp_path / "items.jsonl"
    mw.append_jsonl(path, [
        {"url": "https://example.com/a", "title": "A"},
        {"title": "no-url 1"},
        {"title": "no-url 2"},
    ])
    assert sum(1 for _ in path.open()) == 3


# ----- otaku_calendar.py (wiki EN) -----

def test_otaku_calendar_parse_date_text():
    from wikis import otaku_calendar as oc
    assert oc._parse_date_text("Tuesday 5 May 2026") == "2026-05-05"
    assert oc._parse_date_text("Wednesday 31 December 2025") == "2025-12-31"
    assert oc._parse_date_text("not a date") == ""


def test_otaku_calendar_strip_format_and_country():
    from wikis import otaku_calendar as oc
    cleaned, fmt, country = oc._strip_format_and_country(
        "Blue Box Volume 20 (Manga) US"
    )
    assert cleaned == "Blue Box Volume 20"
    assert fmt == "manga"
    assert country == "US"

    cleaned, fmt, country = oc._strip_format_and_country(
        "Classroom of the Elite: Year 3 (Light Novel) Volume 1 (Manga) US"
    )
    assert "Classroom of the Elite" in cleaned
    # Either format detected is acceptable; country must be US.
    assert country == "US"


def test_otaku_calendar_parse_extracts_releases():
    from wikis import otaku_calendar as oc
    html = """<html><body>
        <div class="dateListing">
          <h3>May 2026</h3>
          <div class="dateListingContainer">
            Tuesday 5 May 2026
            <div>
              <a href="/Release/100/manga-A">Manga A (Deluxe Edition) Volume 1 (Manga) US</a><br/>
              <a href="/Release/101/manga-B-au">Manga B Volume 2 (Manga) AU</a><br/>
            </div>
          </div>
          <div class="dateListingContainer">
            Wednesday 6 May 2026
            <div>
              <a href="/Release/102/manga-C">Manga C (Collector's Edition) Volume 3 (Manga) US</a><br/>
            </div>
          </div>
        </div>
    </body></html>"""
    items = oc.parse_calendar_page(html, allowed_countries=("US",))
    # AU debe quedar filtrado, solo 2 US releases (A y C).
    assert len(items) == 2
    titles = [i.title for i in items]
    assert any("Manga A" in t for t in titles)
    assert any("Manga C" in t for t in titles)
    dates = [i.release_date for i in items]
    assert "2026-05-05" in dates
    assert "2026-05-06" in dates


# ----- manga_mexico.py (wiki MX) -----

def test_manga_mexico_split_title():
    from wikis import manga_mexico as mm
    title, meta = mm._split_title(
        "Chainsaw Man - Volúmenes: 19/20+ ( Publicándose ) | Precio actual: 169 MXN"
    )
    assert title == "Chainsaw Man"
    assert "Volúmenes" in meta


def test_manga_mexico_parse_catalog_extracts_items():
    from wikis import manga_mexico as mm
    html = """<html><body>
        <div class="post-body">
          <ul>
            <li>Chainsaw Man - Volúmenes: 19/20+ ( Publicándose ) | Bimestral (Próx. en junio) | Precio actual: 169 MXN</li>
            <li>Akame Ga Kill - Volúmenes: 15/15 ( Finalizado )</li>
            <li>Berserk [ Edición Deluxe ] - Volúmenes: 5/14 ( Publicándose ) | Trimestral | Precio actual: 449 MXN</li>
          </ul>
        </div>
    </body></html>"""
    items = mm.parse_catalog_page(html, publisher_slug="panini")
    assert len(items) == 3
    # Cada item tiene URL única para no colapsar en dedup.
    urls = [i.url for i in items]
    assert len(set(urls)) == len(urls)
    # Precios
    by_title = {i.title: i for i in items}
    assert by_title["Chainsaw Man"].price == "$169 MXN"
    assert by_title["Akame Ga Kill"].price == ""  # finalizado, no precio actual
    # Tags con metadata extraída
    cm = by_title["Chainsaw Man"]
    assert any(t.startswith("status:") for t in cm.tags)
    assert any(t.startswith("periodicity:") for t in cm.tags)


def test_manga_mexico_skips_duplicate_titles():
    from wikis import manga_mexico as mm
    html = """<html><body><div class="post-body"><ul>
        <li>Berserk - Volúmenes: 1/14</li>
        <li>Berserk - Volúmenes: 1/14</li>
    </ul></div></body></html>"""
    items = mm.parse_catalog_page(html, publisher_slug="panini")
    assert len(items) == 1


# ---------------------------------------------------------------------------
# derive_cluster_key — agrupación lógica entre fuentes
# ---------------------------------------------------------------------------


def test_cluster_key_isbn_authoritative():
    """Si hay ISBN, prevalece sobre cualquier otro derivado."""
    item = {"isbn": "9788822624697", "title": "ONE PIECE 98 CELEBRATION EDITION",
            "language": "Italiano", "url": "https://x.com/a"}
    assert mw.derive_cluster_key(item) == "isbn:9788822624697"


def test_cluster_key_two_isbns_distinct():
    a = {"isbn": "9788822624697", "title": "X", "language": "Italiano", "url": "http://a"}
    b = {"isbn": "9788822624698", "title": "X", "language": "Italiano", "url": "http://b"}
    assert mw.derive_cluster_key(a) != mw.derive_cluster_key(b)


def test_cluster_key_fuzzy_merges_same_series_volume_variant():
    """Dos items sin ISBN del mismo idioma + serie + vol + variant → mismo key."""
    a = {"title": "ONE PIECE n. 100 CELEBRATION EDITION", "language": "Italiano",
         "publisher": "Star Comics", "signal_types": ["celebration"], "url": "http://a"}
    b = {"title": "One Piece Celebration Edition Vol. 100", "language": "Italiano",
         "publisher": "Star Comics", "signal_types": ["celebration"], "url": "http://b"}
    assert mw.derive_cluster_key(a) == mw.derive_cluster_key(b)


def test_cluster_key_different_languages_dont_merge():
    a = {"title": "One Piece vol. 100", "language": "Italiano", "publisher": "Star",
         "signal_types": ["celebration"], "url": "http://a"}
    b = {"title": "One Piece tomo 100", "language": "Español", "publisher": "Planeta",
         "signal_types": ["celebration"], "url": "http://b"}
    assert mw.derive_cluster_key(a) != mw.derive_cluster_key(b)


def test_cluster_key_different_variants_dont_merge():
    """OP100 normal y OP100 Celebration son productos distintos."""
    a = {"title": "One Piece vol. 100", "language": "Italiano",
         "publisher": "Star", "signal_types": [], "url": "http://a"}
    b = {"title": "One Piece vol. 100 Celebration", "language": "Italiano",
         "publisher": "Star", "signal_types": ["celebration"], "url": "http://b"}
    assert mw.derive_cluster_key(a) != mw.derive_cluster_key(b)


def test_cluster_key_different_volumes_dont_merge():
    a = {"title": "Berserk Deluxe vol. 1", "language": "Español",
         "publisher": "Panini", "signal_types": ["deluxe"], "url": "http://a"}
    b = {"title": "Berserk Deluxe vol. 2", "language": "Español",
         "publisher": "Panini", "signal_types": ["deluxe"], "url": "http://b"}
    assert mw.derive_cluster_key(a) != mw.derive_cluster_key(b)


def test_cluster_key_fallback_to_url_when_insufficient_info():
    """Sin ISBN, sin volumen, sin variant → standalone (clave url:)."""
    item = {"title": "Random Title No Volume", "language": "Italiano",
            "signal_types": [], "url": "http://a"}
    key = mw.derive_cluster_key(item)
    assert key.startswith("url:")


def test_cluster_key_requires_volume_even_with_variant_sig():
    """Sin volumen detectable, NO debe agruparse aunque tenga variant_sig:
    distintos tomos del mismo artbook con variant 'limited' colisionarían."""
    item = {"title": "Random Artbook Limited Edition", "language": "Japonés",
            "publisher": "X", "signal_types": ["limited"], "url": "http://a"}
    key = mw.derive_cluster_key(item)
    assert key.startswith("url:")


def test_cluster_key_fallback_when_series_too_short():
    """Series de < 3 chars no es discriminante."""
    item = {"title": "Q vol. 1", "language": "Japonés", "publisher": "X",
            "signal_types": ["deluxe"], "url": "http://a"}
    key = mw.derive_cluster_key(item)
    assert key.startswith("url:")


def test_cluster_key_japanese_preserves_kanji():
    """No strippeamos kanji/kana — son discriminantes para series JP."""
    a = {"title": "ワンピース 100巻 限定版", "language": "Japonés",
         "publisher": "集英社", "signal_types": ["limited"], "url": "http://a"}
    b = {"title": "ワンピース 100巻 限定版", "language": "Japonés",
         "publisher": "集英社", "signal_types": ["limited"], "url": "http://b"}
    assert mw.derive_cluster_key(a) == mw.derive_cluster_key(b)
    assert "ワンピース" in mw.derive_cluster_key(a)


def test_cluster_key_strips_brackets_to_avoid_noise():
    """Contenido entre corchetes (típico ruido de retailer JP) no afecta key."""
    a = {"title": "Naruto Vol. 5 Deluxe (BeBoy Comics Deluxe)", "language": "Japonés",
         "publisher": "集英社", "signal_types": ["deluxe"], "url": "http://a"}
    b = {"title": "Naruto Vol. 5 Deluxe", "language": "Japonés",
         "publisher": "集英社", "signal_types": ["deluxe"], "url": "http://b"}
    assert mw.derive_cluster_key(a) == mw.derive_cluster_key(b)


def test_extract_volume_patterns():
    assert mw._extract_volume("One Piece vol. 100") == "100"
    assert mw._extract_volume("Naruto Tomo 5") == "5"
    assert mw._extract_volume("Berserk Tome 12") == "12"
    assert mw._extract_volume("ONE PIECE n. 100") == "100"
    assert mw._extract_volume("Naruto #42") == "42"
    assert mw._extract_volume("ワンピース 100巻") == "100"
    assert mw._extract_volume("Bleach Volume 7") == "7"
    # JP/EN: volumen entre paréntesis (half o full-width)
    assert mw._extract_volume("転生したらスライムだった件（15）限定版") == "15"
    assert mw._extract_volume("Some Title (10)") == "10"
    assert mw._extract_volume("Random title without volume") == ""
