"""Tests for the Fase 1 extraction changes in manga_watch."""

from __future__ import annotations

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


def test_score_candidate_injects_search_keyword_signal():
    # Una card de Glénat search "edition collector" cuyo título NO incluye
    # "edition collector" debería igual recibir score gracias al tag.
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
    # 'edition collector' está en KEYWORD_RULES con score 45.
    assert cand.score >= 45
    assert any("edition collector" in s for s in cand.signals)


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


def test_is_likely_manga_keeps_special_manga_packs_from_wiki():
    # "type:produit spécial manga" SÍ es manga (packs manga + artbook, etc.).
    cases = [
        ("Naruto - Coffret des artbooks", ["type:produit spécial manga"]),
        ("The promised Neverland - Coffret manga + roman 1", ["type:produit spécial manga"]),
    ]
    for title, tags in cases:
        is_manga, _ = mw.is_likely_manga(title, "", tags=tags)
        assert is_manga, f"Should be kept: {title!r}"


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
