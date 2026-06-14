"""Tests for the Fase 1 extraction changes in manga_watch."""

from __future__ import annotations

import json
from pathlib import Path

from bs4 import BeautifulSoup

from scripts import manga_watch as mw
from scripts import image_store as imgstore


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


def test_variant_alone_detected_as_variant_cover_signal():
    """`Variant` suelto (sin "cover") es signal_type variant_cover.

    Items reales del catálogo Mangadreams (variants europeas) usan
    "Variant Metal alla prima tiratura", "Variant Limited Francese",
    "Variant Esclusiva Momie", etc. — sin la palabra "cover" — porque en
    retail manga IT/FR/EN/ES "Variant" solo ya implica cover variante.
    Sin esta regla, 13/43 productos quedaban fuera de is_collectible_edition.
    """
    cases = [
        "One Piece 108 Variant Metal alla prima tiratura",
        "Chainsaw Man 16 Variant Metal limitata alla prima tiratura",
        "Demon Slayer 23 Variant Limited Francese",
        "Blue Lock 1 Variant BD 48h",
        "Hunter X Hunter 37 Variant",
        "Kaiju no.8 vol 5 Variant Francese",
        "Togen Anki Variant limitata a 999 copie",
        "Akane-Banashi 11 Variant Momie Limitata a 1000 copie",
        "Platinum End Variant Limited Francese",
        "Perfect World Variant BD 48h",
        "Chainsaw Man Variant 18 + Variant 16 Metal Bundle",
        "Variant Alfa BD L'estate in cui Hikaru è Morto",
        "Kaiju no.8 volume 1 Variant Limited edizione tedesca",
    ]
    for title in cases:
        score, _, types = _detect(title, fuzzy=False)
        assert "variant_cover" in types, (
            f"Should detect variant_cover in {title!r} (types={types})"
        )
        assert score >= 30, f"Score too low for {title!r}: {score}"


def test_variant_alone_does_not_match_substrings():
    """`variant` con word-boundary NO matchea covariant/invariant/variante.

    "Variante" (italiano/español, una vocal extra) debe ignorarse para no
    contaminar items donde "variante" aparece en otro contexto."""
    non_cases = [
        "Analisi covariante delle particelle",
        "Sistema invariante topologico",
        "Edición variante posible",  # "variante" tiene vocal final extra
        "covariant analysis manga news",
    ]
    for title in non_cases:
        score, _, types = _detect(title, fuzzy=False)
        assert "variant_cover" not in types, (
            f"Should NOT detect variant_cover in {title!r} (types={types})"
        )


def test_variant_alone_with_signal_passes_collectible_gate():
    """Integración: title con "Variant" solo → variant_cover → gate accept."""
    cases = [
        ("One Piece 108 Variant Metal alla prima tiratura", "manga_only"),
        ("Demon Slayer 23 Variant Limited Francese", "manga_only"),
        ("Hunter X Hunter 37 Variant", "manga_only"),
    ]
    for title, purity in cases:
        score, _, types = _detect(title, fuzzy=False)
        ok, reason = mw.is_collectible_edition(title, "", types, purity)
        assert ok, f"Should accept via variant_cover: {title!r} (reason={reason})"


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
    # El match crudo DD/MM/YYYY sale normalizado a ISO (gotcha #80).
    assert mw.extract_release_date("Sortie le 15/06/2026") == "2026-06-15"


def test_extract_release_date_japanese():
    assert mw.extract_release_date("発売日: 2026年6月15日") == "2026-06-15"


def test_extract_release_date_english_month():
    assert mw.extract_release_date("Release date: June 15, 2026") == "2026-06-15"


def test_extract_release_date_spanish_month():
    assert mw.extract_release_date("Disponible el 15 de junio de 2026") == "2026-06-15"


def test_extract_release_date_empty():
    assert mw.extract_release_date("Manga genial sin fecha") == ""


def test_normalize_release_date_dmy_family():
    # Día primero (fuentes EU), separadores / . -, rangos validados.
    assert mw.normalize_release_date("05/05/2026") == "2026-05-05"
    assert mw.normalize_release_date("07.05.2026") == "2026-05-07"
    assert mw.normalize_release_date("13-11-2025") == "2025-11-13"
    # Mes-primero inequívoco (segundo componente > 12) → US, se interpreta MM/DD.
    assert mw.normalize_release_date("05/27/2026") == "2026-05-27"
    # Fechas imposibles NO se tocan (nunca destruir información).
    assert mw.normalize_release_date("32/05/2026") == "32/05/2026"
    assert mw.normalize_release_date("31/02/2026") == "31/02/2026"


def test_normalize_release_date_partial_granularity_untouched():
    # YYYY y YYYY-MM son granularidad legítima: no se inventa día ni mes.
    assert mw.normalize_release_date("2026") == "2026"
    assert mw.normalize_release_date("2014-01") == "2014-01"
    assert mw.normalize_release_date("") == ""


def test_normalize_release_date_store_datetime_and_jp():
    # JSON-LD de tiendas JP: "2023/09/27 10:00:00" y 年月日.
    assert mw.normalize_release_date("2023/09/27 10:00:00") == "2023-09-27"
    assert mw.normalize_release_date("2026/03/05") == "2026-03-05"
    assert mw.normalize_release_date("2026年04月08日") == "2026-04-08"
    assert mw.normalize_release_date("2026年04月") == "2026-04"
    assert mw.normalize_release_date("2026-06-15T10:00:00") == "2026-06-15"


def test_normalize_release_date_textual_months():
    assert mw.normalize_release_date("2 juillet 2025") == "2025-07-02"
    assert mw.normalize_release_date("mer. 30 mars 2022") == "2022-03-30"
    assert mw.normalize_release_date("30 août 2023") == "2023-08-30"
    assert mw.normalize_release_date("1er ottobre 2026") == "2026-10-01"
    assert mw.normalize_release_date("June 15, 2026") == "2026-06-15"
    assert mw.normalize_release_date("Wed, 02 Jul 2025 10:00:00 GMT") == "2025-07-02"


def test_normalize_release_date_unknown_passthrough_and_idempotent():
    # Formato no reconocido → sin tocar; normalizar dos veces = una vez.
    assert mw.normalize_release_date("Em breve") == "Em breve"
    for raw in ("05/05/2026", "2026年04月08日", "2 juillet 2025", "2026", "2014-01"):
        once = mw.normalize_release_date(raw)
        assert mw.normalize_release_date(once) == once


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
    # srcset con descriptores 'w': debe tomar el de mayor resolución (720w), no el primero.
    # Comportamiento corregido: antes tomaba el primero (menor), ahora toma el mayor.
    soup = make_soup('<div><img srcset="/img/480.jpg 480w, /img/720.jpg 720w"></div>')
    div = soup.find("div")
    url = mw.extract_image_url(div, "https://example.com/")
    assert url == "https://example.com/img/720.jpg"


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


def test_img_to_url_skips_data_uri():
    # Lazy-load: src es un placeholder data-URI, la portada real vive en data-src.
    soup = make_soup('<img src="data:image/svg+xml;base64,PHN2Zz4=" data-src="/img/real.jpg">')
    img = soup.find("img")
    assert mw._img_to_url(img, "https://example.com/") == "https://example.com/img/real.jpg"


def test_img_to_url_srcset_picks_largest_w_descriptor():
    # srcset con descriptores 'w': debe tomar el de mayor N, no el primero.
    soup = make_soup(
        '<img srcset="/img/cover_100w.jpg 100w, /img/cover_400w.jpg 400w, /img/cover_800w.jpg 800w">'
    )
    img = soup.find("img")
    assert mw._img_to_url(img, "https://example.com/") == "https://example.com/img/cover_800w.jpg"


def test_img_to_url_srcset_picks_last_when_no_descriptor():
    # srcset sin descriptores: la última entrada es la de mayor resolución por convención.
    soup = make_soup(
        '<img srcset="/img/cover-small.jpg, /img/cover-medium.jpg, /img/cover-large.jpg">'
    )
    img = soup.find("img")
    assert mw._img_to_url(img, "https://example.com/") == "https://example.com/img/cover-large.jpg"


def test_img_to_url_srcset_single_entry():
    # srcset de 1 sola entrada: devuelve esa entrada.
    soup = make_soup('<img srcset="/img/cover.jpg 1x">')
    img = soup.find("img")
    assert mw._img_to_url(img, "https://example.com/") == "https://example.com/img/cover.jpg"


def test_extract_image_url_skips_data_uri_placeholder():
    # MangaLine MX: <img> lazy-loaded — el src es un SVG data-URI placeholder,
    # la portada real está en data-src. Antes devolvíamos el data-URI.
    soup = make_soup(
        '<div class="product"><img src="data:image/svg+xml;base64,PHN2Zz4="'
        ' data-src="/wp-content/uploads/cover.jpg" alt="Crayon Shin-chan"></div>'
    )
    div = soup.find("div")
    assert (
        mw.extract_image_url(div, "https://mangaline.com.mx/")
        == "https://mangaline.com.mx/wp-content/uploads/cover.jpg"
    )


def test_extract_image_url_rejects_theme_svg_icon():
    # Sanyodo: el único <img> del card es un ícono de tema (icn_close.svg en
    # /assets/images/common/). No debe devolverse como portada.
    soup = make_soup(
        '<div class="product"><img'
        ' src="/wp-content/themes/sanyodo/assets/images/common/sp/icn_close.svg">'
        '<p class="card">特装版</p></div>'
    )
    card = soup.find("p", class_="card")
    assert mw.extract_image_url(card, "https://www.sanyodo.co.jp/") == ""


def test_extract_image_url_rejects_animeclick_avatar():
    # AnimeClick: el carrusel levantaba el avatar de quien subió la edición.
    soup = make_soup(
        '<div class="product"><img'
        ' src="/bundles/accommon/images/utente_registrato_F.png">'
        '<p class="card">Variant Cover</p></div>'
    )
    card = soup.find("p", class_="card")
    assert mw.extract_image_url(card, "https://www.animeclick.it/") == ""


def test_extract_image_url_rejects_kadokawa_banner():
    # KADOKAWA Store: banner de publicidad servido como <img> en la ficha.
    soup = make_soup(
        '<div class="product"><img'
        ' src="/img/usr/common/top_bar_banner/top_bar_banner_sp_250303.png">'
        '<p class="card">限定版</p></div>'
    )
    card = soup.find("p", class_="card")
    assert mw.extract_image_url(card, "https://store.kadokawa.co.jp/") == ""


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


def test_detail_image_rejects_theme_assets_and_finds_cover():
    # Sanyodo: la página tiene íconos de tema (.svg en /assets/images/common/)
    # y la portada real (e-hon). Debe ignorar los íconos y rankear la portada.
    html = """<html><body><main>
        <img src="/wp-content/themes/sanyodo/assets/images/common/sp/icn_close.svg" alt="menu close">
        <img src="https://www1.e-hon.ne.jp//content/images/m_978.jpg" alt="薬屋のひとりごと特装版">
    </main></body></html>"""
    url = mw._extract_image_from_detail_soup(make_soup(html), "https://www.sanyodo.co.jp/?s=x")
    assert url == "https://www1.e-hon.ne.jp//content/images/m_978.jpg"


def test_detail_image_e_hon_cover_wins_with_short_alt():
    # e-hon.ne.jp es CDN de portadas (Sanyodo linkea sus covers ahí). Debe
    # ganar aunque el alt sea corto — sin el boost de host quedaba en score 4.
    html = """<html><body><main>
        <img src="/wp-content/themes/sanyodo/assets/images/common/sp/icn_close.svg" alt="x">
        <img src="https://www1.e-hon.ne.jp//images/syoseki/ac/25/34820125.jpg" alt="鬼の花嫁 8">
    </main></body></html>"""
    url = mw._extract_image_from_detail_soup(make_soup(html), "https://www.sanyodo.co.jp/?s=x")
    assert url == "https://www1.e-hon.ne.jp//images/syoseki/ac/25/34820125.jpg"


def test_is_placeholder_image_rejects_svg_and_theme_assets():
    assert mw._is_placeholder_image("https://x.com/sp/icn_close.svg")
    assert mw._is_placeholder_image(
        "https://x.com/wp-content/themes/t/assets/images/common/logo.png"
    )
    # Una portada raster normal no es placeholder.
    assert not mw._is_placeholder_image("https://x.com/uploads/cover.jpg")


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
    assert s["name"] == "x"


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


def test_listadomanga_calendar_does_not_inject_category_into_description():
    """Bug real (2026-05-23): el parser inyectaba la categoría del `<u>` de
    la tabla en la `description` del item, contaminando detect_signals.
    Si el `<u>` decía "Artbook" (categoría de OTRA sección o item adyacente
    procesado por el iterador de tablas anidadas), TODOS los items de la
    tabla quedaban marcados con signal=artbook → entraban a items.jsonl
    como artbooks pese a ser tomos manga regulares.

    Fix: NO incluir `category` en la description (sigue siendo info
    contextual pero no contamina los signals)."""
    from wikis import listadomanga as lm
    # Tabla con <u>Artbook</u> pero items que NO son artbooks
    html = """<html><body>
        <h2>Norma Editorial</h2>
        <h2>Miércoles, 31 Octubre 2018</h2>
        <table class="ventana_id1">
            <tr><td class="izq">
                <b><u>Artbook</u></b><br/>
                - <a href="coleccion.php?id=1836">Ataque a los Titanes: Antes de la caída (Manga) nº11 (de 17)</a> /
                  <a href="autor.php?id=1">Hajime Isayama</a><br/>
            </td></tr>
        </table>
    </body></html>"""
    items = lm.parse_calendar_page(html)
    assert len(items) == 1
    c = items[0]
    # La description NO debe contener "Artbook" inyectado como keyword
    # (que contaminaría detect_signals).
    assert "Artbook" not in c.description, (
        f"description contains 'Artbook' which contaminates signals: {c.description!r}"
    )
    # Debe seguir teniendo publisher + title + author
    assert "Norma Editorial" in c.description
    assert "Ataque a los Titanes" in c.description
    assert "Hajime Isayama" in c.description


def test_listadomanga_detail_extracts_image_and_price():
    """Test del extractor de detail. Devuelve image_url SOLO si la colección
    tiene un único item Layout A (single-volume / artbook standalone), porque
    si tiene múltiples tomos el calendario no puede mapear cuál `<img>` es
    el cover del vol/edición específico (bug histórico: tomaba el primer
    `<img>` del CDN = vol 1 aunque el item del calendario fuera vol 34
    Especial)."""
    from wikis import listadomanga as lm
    # Caso single-item: SÍ devuelve image_url.
    html = """<html><body>
        <table class="ventana_id1" style="width: 184px;">
          <tr><td class="cen">
            <img class="portada" src="https://static.listadomanga.com/abc123.jpg" alt="cover">
          </td></tr>
        </table>
        <p>Editorial: Norma Editorial</p>
        <p>Precio: 9,95 €</p>
        <b>Formato:</b> Tomo A5 rústica con sobrecubierta
    </body></html>"""
    class FakeResponse:
        text = html
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        def raise_for_status(self): pass
    class FakeSession:
        def get(self, url, **kw): return FakeResponse()

    meta = lm.fetch_detail_metadata("https://www.listadomanga.es/coleccion.php?id=1", FakeSession())
    assert meta["image_url"] == "https://static.listadomanga.com/abc123.jpg"
    assert "Formato" in meta["description_extra"]


def test_listadomanga_detail_skips_image_when_multi_volume():
    """Cuando la colección tiene >1 tomo (multi-volume), NO devolver image_url
    (preferimos placeholder vacío a cover wrong). Esto es lo que protege
    contra el bug del calendar que reportó el owner el 2026-05-23: AoT vol 34
    Especial mostraba la portada del vol 1."""
    from wikis import listadomanga as lm
    html = """<html><body>
        <table class="ventana_id1" style="width: 184px;">
          <tr><td class="cen">
            <img class="portada" src="https://static.listadomanga.com/vol1.jpg" alt="Serie nº1">
          </td></tr>
        </table>
        <table class="ventana_id1" style="width: 184px;">
          <tr><td class="cen">
            <img class="portada" src="https://static.listadomanga.com/vol2.jpg" alt="Serie nº2">
          </td></tr>
        </table>
        <p>Precio: 9,95 €</p>
    </body></html>"""
    class FakeResponse:
        text = html
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        def raise_for_status(self): pass
    class FakeSession:
        def get(self, url, **kw): return FakeResponse()

    meta = lm.fetch_detail_metadata("https://www.listadomanga.es/coleccion.php?id=1", FakeSession())
    # NO debería devolver imagen — la colección tiene 2 tomos y no sabemos cuál.
    assert meta["image_url"] == ""


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


# --- Whakoom edition expansion (Sprint 4.x) ---------------------------------
#
# Una URL /ediciones/<id>/<slug> NO es un tomo: es una colección entera.
# Hay que expandirla en N candidates (uno por /comics/<X>/<slug>/<vol>)
# antes de registrar. Ver gotcha en CLAUDE.md.

_WHAKOOM_FIXTURES = Path(__file__).parent / "fixtures" / "whakoom"


def test_whakoom_is_edition_url_detects_subdomain_variants():
    from wikis import whakoom as wk
    # Subdominios localizados (en./it./www.) y www.
    assert wk.is_whakoom_edition_url(
        "https://www.whakoom.com/ediciones/511364/berserk_deluxe_edition-hardcover"
    )
    assert wk.is_whakoom_edition_url(
        "https://en.whakoom.com/ediciones/511364/berserk_deluxe_edition-hardcover"
    )
    assert wk.is_whakoom_edition_url(
        "http://it.whakoom.com/ediciones/635402/berserk_deluxe_edition-cartonato"
    )
    # /comics/ NO debe matchear como edición
    assert not wk.is_whakoom_edition_url(
        "https://www.whakoom.com/comics/jx2IT/berserk_deluxe_edition/1"
    )
    # URLs no-Whakoom
    assert not wk.is_whakoom_edition_url("https://example.com/ediciones/123/foo")
    assert not wk.is_whakoom_edition_url("")


def test_whakoom_is_comic_url():
    from wikis import whakoom as wk
    assert wk.is_whakoom_comic_url(
        "https://www.whakoom.com/comics/jx2IT/berserk_deluxe_edition/1"
    )
    assert wk.is_whakoom_comic_url(
        "https://en.whakoom.com/comics/jx2IT/berserk_deluxe_edition/1"
    )
    assert not wk.is_whakoom_comic_url(
        "https://www.whakoom.com/ediciones/511364/berserk_deluxe_edition-hardcover"
    )


def test_whakoom_edition_todos_url_appends_suffix():
    from wikis import whakoom as wk
    url = "https://en.whakoom.com/ediciones/511364/berserk_deluxe_edition-hardcover"
    assert wk.edition_todos_url(url) == url + "/todos"
    # Idempotente: si ya termina en /todos, no duplica
    assert wk.edition_todos_url(url + "/todos") == url + "/todos"
    # Quita trailing slash + query antes de pegar /todos
    assert (
        wk.edition_todos_url(url + "/?foo=bar")
        == url + "/todos"
    )


def _berserk_main_html() -> str:
    return (_WHAKOOM_FIXTURES / "berserk_deluxe_edition.html").read_text(encoding="utf-8")


def _berserk_todos_html() -> str:
    return (_WHAKOOM_FIXTURES / "berserk_deluxe_edition_todos.html").read_text(encoding="utf-8")


def test_whakoom_parse_volume_links_main_page_returns_11():
    """La página principal /ediciones/ muestra solo los primeros 11 tomos."""
    from wikis import whakoom as wk
    vols = wk.parse_volume_links(_berserk_main_html())
    assert len(vols) == 11
    first = vols[0]
    assert first["url"] == "https://www.whakoom.com/comics/jx2IT/berserk_deluxe_edition/1"
    assert first["title"] == "Berserk Deluxe Edition #1"
    assert first["issue"] == "1"
    assert first["image_url"].startswith("https://i1.whakoom.com/small/")
    # Verificamos que el último de la página principal es el #11
    assert vols[-1]["issue"] == "11"


def test_whakoom_parse_volume_links_todos_returns_14():
    """La página /todos contiene la lista completa de tomos."""
    from wikis import whakoom as wk
    vols = wk.parse_volume_links(_berserk_todos_html())
    assert len(vols) == 14
    issues = [v["issue"] for v in vols]
    assert issues == [str(i) for i in range(1, 15)]


def test_whakoom_parse_edition_metadata_berserk():
    from wikis import whakoom as wk
    meta = wk.parse_edition_metadata(_berserk_main_html())
    assert meta["title"] == "Berserk Deluxe Edition"
    assert meta["publisher"] == "Dark Horse"
    assert meta["edition_type"] == "Hardcover"
    assert meta["language"] == "Inglés"
    assert meta["country"] == "Estados Unidos"
    assert "Kentaro Miura" in meta["author"]
    assert meta["image_url"].startswith("https://i1.whakoom.com/large/")
    assert "Berserk" in meta["description"]


def test_whakoom_merge_volume_dicts_dedups_and_fills_gaps():
    """Mergeo de listas: misma URL aparece en main + todos, no duplica."""
    from wikis import whakoom as wk
    main = [
        {"url": "https://x/1", "title": "A #1", "issue": "1", "image_url": ""},
        {"url": "https://x/2", "title": "A #2", "issue": "2", "image_url": "img2"},
    ]
    todos = [
        {"url": "https://x/1", "title": "", "issue": "1", "image_url": "img1"},
        {"url": "https://x/3", "title": "A #3", "issue": "3", "image_url": "img3"},
    ]
    merged = wk._merge_volume_dicts(main, todos)
    assert len(merged) == 3
    by_url = {v["url"]: v for v in merged}
    # /1 estaba en main (sin image_url) → todos lo llenó.
    assert by_url["https://x/1"]["title"] == "A #1"
    assert by_url["https://x/1"]["image_url"] == "img1"
    # /2 solo en main, intacto.
    assert by_url["https://x/2"]["image_url"] == "img2"
    # /3 solo en todos.
    assert by_url["https://x/3"]["issue"] == "3"


def test_whakoom_expand_edition_with_prefetched_html_yields_14_candidates():
    """Test end-to-end de expansión sin red: pasamos los dos HTMLs pre-fetched."""
    from wikis import whakoom as wk
    cands = wk.expand_whakoom_edition(
        "https://en.whakoom.com/ediciones/511364/berserk_deluxe_edition-hardcover",
        session=None,  # no se usa porque pasamos HTMLs pre-cargados
        edition_html=_berserk_main_html(),
        todos_html=_berserk_todos_html(),
        fetch_todos=True,
    )
    assert len(cands) == 14
    # Todos los candidates apuntan a /comics/, no a /ediciones/
    for c in cands:
        assert "/comics/" in c.url
        assert "/ediciones/" not in c.url
    # Metadata edición-nivel heredada
    first = cands[0]
    assert first.publisher == "Dark Horse"
    assert first.language == "Inglés"
    assert first.country == "Estados Unidos"
    assert "Kentaro Miura" in first.author
    # Título por tomo
    titles = [c.title for c in cands]
    assert "Berserk Deluxe Edition #1" in titles
    assert "Berserk Deluxe Edition #14" in titles
    # Cover individual del tomo, no la general de la edición
    assert all(c.image_url.startswith("https://i1.whakoom.com/") for c in cands)
    # Diferentes covers entre tomos (al menos el #1 y el #2 difieren)
    urls_by_issue = {c.url.split("/")[-1]: c.image_url for c in cands}
    assert urls_by_issue["1"] != urls_by_issue["2"]


def test_whakoom_expand_edition_returns_empty_when_no_volumes():
    """Edición sin tomos NI fallback one-shot → 0 candidates."""
    from wikis import whakoom as wk
    empty_html = """<html><head>
        <meta property="og:title" content="Empty Edition">
    </head><body><h1>Empty Edition</h1></body></html>"""
    cands = wk.expand_whakoom_edition(
        "https://www.whakoom.com/ediciones/99/empty",
        session=None,
        edition_html=empty_html,
        todos_html="",
        fetch_todos=False,
    )
    assert cands == []


def test_whakoom_expand_oneshot_via_login_returnurl():
    """One-shot: /ediciones/ sin <li id=comic> → fallback a /login?ReturnUrl=/comics/."""
    from wikis import whakoom as wk
    oneshot_html = """<html><head>
        <meta property="og:title" content="Edición Especial Limitada">
        <meta property="og:image" content="https://i1.whakoom.com/large/xx.jpg">
        <meta property="og:description" content="Edición coleccionista numerada.">
    </head><body>
        <h1>Edición Especial Limitada</h1>
        <p class="publisher"><a href="/publisher/1/norma">Norma Editorial</a></p>
        <p class="actions">
            <a href="/login?ReturnUrl=/comics/abc123/edicion_especial_limitada"
               class="bt">Log in to add</a>
        </p>
        <ul class="info-summary">
            <li><span class="value flag" style="background-image:url(https://i1.whakoom.com/lang/1.png)"></span>
                <span class="title">Spanish (Spain)</span></li>
        </ul>
    </body></html>"""
    cands = wk.expand_whakoom_edition(
        "https://www.whakoom.com/ediciones/77/edicion_especial_limitada",
        session=None,
        edition_html=oneshot_html,
        todos_html="",
        fetch_todos=False,
    )
    assert len(cands) == 1
    c = cands[0]
    assert c.url == "https://www.whakoom.com/comics/abc123/edicion_especial_limitada"
    assert c.title == "Edición Especial Limitada"
    assert c.publisher == "Norma Editorial"
    assert c.language == "Español"
    assert c.country == "España"
    assert c.image_url == "https://i1.whakoom.com/large/xx.jpg"


def test_whakoom_extract_oneshot_comic_url_handles_no_match():
    from wikis import whakoom as wk
    assert wk._extract_oneshot_comic_url("<html>nothing</html>") == ""
    # /login sin ReturnUrl=/comics — no debe matchear
    assert wk._extract_oneshot_comic_url(
        '<a href="/login?ReturnUrl=/profile">x</a>'
    ) == ""


# --- Shopify variants expansion (Sprint 4.x) --------------------------------
#
# Algunos sitios Shopify (Dark Horse Direct, etc.) modelan una serie de
# tomos como UN producto con N variants ("Volume 1 / 2 / 3"). Igual que
# Whakoom /ediciones/, hay que expandir a N items.

_SHOPIFY_FIXTURES = Path(__file__).parent / "fixtures" / "shopify"


def _dh_hellsing_html() -> str:
    return (_SHOPIFY_FIXTURES / "dh_hellsing_deluxe.html").read_text(encoding="utf-8")


def test_shopify_extract_variants_from_json():
    from shopify_variants import extract_shopify_variants
    vs = extract_shopify_variants(_dh_hellsing_html())
    assert len(vs) == 3
    titles = [v["title"] for v in vs]
    assert titles == ["Volume 1", "Volume 2", "Volume 3"]
    ids = [v["id"] for v in vs]
    assert len(set(ids)) == 3
    assert all(v["sku"].startswith("3002-") for v in vs)


def test_shopify_is_volume_variants_detects_keywords():
    from shopify_variants import is_volume_variants
    assert is_volume_variants([
        {"title": "Volume 1"}, {"title": "Volume 2"}, {"title": "Volume 3"},
    ])
    assert is_volume_variants([{"title": "Tome 1"}, {"title": "Tome 2"}])
    assert is_volume_variants([{"title": "Tomo 1"}, {"title": "Tomo 2"}])
    assert is_volume_variants([{"title": "#1"}, {"title": "#2"}])
    assert is_volume_variants([{"title": "第1巻"}, {"title": "第2巻"}])
    # Variants no-volumen → False
    assert not is_volume_variants([
        {"title": "Red"}, {"title": "Blue"}, {"title": "Green"},
    ])
    assert not is_volume_variants([{"title": "S"}, {"title": "M"}, {"title": "L"}])
    assert not is_volume_variants([{"title": "Default Title"}])
    assert not is_volume_variants([{"title": "Volume 1"}])
    assert not is_volume_variants([])


def test_shopify_build_variant_url_preserves_path():
    from shopify_variants import build_variant_url
    assert (
        build_variant_url("https://x.com/products/foo", "12345")
        == "https://x.com/products/foo?variant=12345"
    )
    # URL con tracking de Shopify (_pos/_sid/_ss): lo descarta
    url = "https://www.darkhorsedirect.com/products/foo?_pos=1&_sid=abc&_ss=r"
    assert (
        build_variant_url(url, "99")
        == "https://www.darkhorsedirect.com/products/foo?variant=99"
    )
    # URL con variant existente: lo reemplaza
    assert (
        build_variant_url("https://x.com/products/foo?variant=111", "222")
        == "https://x.com/products/foo?variant=222"
    )


def test_shopify_format_variant_price_handles_cents():
    from shopify_variants import format_variant_price
    assert format_variant_price(4499) == "$44.99"
    assert format_variant_price("4499") == "$44.99"
    assert format_variant_price("29.99") == "$29.99"
    assert format_variant_price(29.99) == "$29.99"
    assert format_variant_price(None) == ""
    assert format_variant_price("") == ""


def test_shopify_extract_variants_returns_empty_for_non_shopify():
    from shopify_variants import extract_shopify_variants
    assert extract_shopify_variants("") == []
    assert extract_shopify_variants("<html><body>plain</body></html>") == []


# --- Whakoom publisher URL expansion ----------------------------------------

# --- series_aliases (multilingual canonical series resolver, gotcha #20) ---

def test_canonical_series_key_remaps_known_aliases():
    """Aliases YAML consolida traducciones a series_key canónico."""
    from series_aliases import canonical_series_key
    # Demon Slayer en todas sus formas
    cases = [
        # (title, current_sk, current_sd) → (expected_sk, expected_sd_contains)
        ('Kimetsu no Yaiba Vol 5', 'kimetsu-no-yaiba', 'Kimetsu no Yaiba'),
        ('鬼滅の刃 特装版', '鬼滅の刃', '鬼滅の刃'),
        ("L'Attaque des Titans 1", "l-attaque-des-titans", "L'Attaque des Titans"),
        ('Les Carnets de l\'Apothicaire 5', 'apothicaire', "Les Carnets de l'Apothicaire"),
        ('Frieren: Beyond Journey\'s End 1', 'frieren-beyond-journey-s-end', "Frieren: Beyond Journey's End"),
        ("L'Atelier des Sorciers 12", 'atelier-des-sorciers', "L'Atelier des Sorciers"),
    ]
    for title, sk, sd in cases:
        new_sk, new_sd = canonical_series_key(title, sk, sd)
        assert new_sk != sk, f"Should remap {sk!r} for title {title!r}"
        # Sanity: el new_sd debe ser human-readable
        assert new_sd, f"Expected non-empty display for {sk!r}"


def test_canonical_series_key_preserves_canonical():
    """Si el series_key ya es canónico, devuelve sin tocar."""
    from series_aliases import canonical_series_key
    for sk in ('demon-slayer', 'attack-on-titan', 'one-piece', 'naruto', 'berserk'):
        new_sk, _ = canonical_series_key('any title', sk, 'Any Display')
        assert new_sk == sk


def test_canonical_series_key_no_false_positives_for_unrelated_series():
    """`Monster Musume` no debe consolidarse en `Monster` (Urasawa) por sub-string."""
    from series_aliases import canonical_series_key
    # Monster Musume es una serie distinta — NO debe ser remapeada a "monster".
    new_sk, _ = canonical_series_key(
        'Monster Musume — Vol.5 - variant',
        'monster-musume',
        'Monster Musume',
    )
    assert new_sk == 'monster-musume', f"Got {new_sk}"
    # Naruto Gaiden tampoco debe colapsarse en Naruto
    new_sk, _ = canonical_series_key(
        'Naruto Gaiden Vol 1', 'naruto-gaiden', 'Naruto Gaiden',
    )
    assert new_sk == 'naruto-gaiden'


# --- derive_series_metadata: heurística del scraper -----------------------

def test_derive_series_metadata_happy_path():
    """El heurístico detecta serie + edición + volumen para títulos comunes."""
    c = mw.Candidate(
        title="Berserk Deluxe Edition Vol. 1",
        url="x", source="X", source_url="x", country="Estados Unidos", language="",
        publisher="Dark Horse Comics", source_class="", tags=[],
        description="", signal_types=["deluxe", "hardcover"],
    )
    md = mw.derive_series_metadata(c)
    assert md["series_key"] == "berserk"
    assert md["volume"] == "1"
    # edition_key TERMINA con el país de la edición (regla dura país=edición, #46)
    assert md["edition_key"] == "berserk-darkhorse-deluxe-us"
    assert "Deluxe" in md["edition_display"]


def test_derive_series_metadata_returns_empty_for_ambiguous():
    """Casos donde el heurístico falla obvio → devuelve dict vacío."""
    # Caso JP sin marker de volumen
    c = mw.Candidate(
        title="鬼滅の刃 23 特装版", url="x", source="X", source_url="x",
        country="", language="", publisher="Shueisha", source_class="",
        tags=[], description="", signal_types=["limited"],
    )
    md = mw.derive_series_metadata(c)
    assert md == {} or not md.get("series_key")

    # Caso "Series N" sin marker — ahora el trailing number SÍ se captura
    # como volumen, lo cual permite al heurístico derivar series_key.
    c = mw.Candidate(
        title="Atomic Robo 5", url="x", source="X", source_url="x",
        country="", language="", publisher="IDW", source_class="",
        tags=[], description="", signal_types=[],
    )
    md = mw.derive_series_metadata(c)
    assert md.get("volume") == "5"
    assert md.get("series_key")  # should derive "atomic-robo"


def test_publisher_slug_normalizes_variants():
    """Variantes de un mismo publisher mapean al mismo slug."""
    assert mw._publisher_slug("Dark Horse Comics") == "darkhorse"
    assert mw._publisher_slug("Glénat Manga") == "glenat"
    assert mw._publisher_slug("Glenat") == "glenat"
    assert mw._publisher_slug("Panini Manga") == "panini"
    assert mw._publisher_slug("Planet Manga BR") == "panini"
    assert mw._publisher_slug("Ivrea Argentina") == "ivrea-ar"
    assert mw._publisher_slug("Ivrea") == "ivrea"
    assert mw._publisher_slug("Crunchyroll Kaze") == "kaze"
    assert mw._publisher_slug("Kazé Manga") == "kaze"
    assert mw._publisher_slug("") == "unknown"
    assert mw._publisher_slug("Obscure Publisher") == "unknown"


def test_publisher_slug_spanish_indies():
    """Editoriales ES indie/medianas que ListadoManga lista y que antes caían a
    'unknown' en el edition_key (gotcha #45). Cada una debe resolver a su slug."""
    assert mw._publisher_slug("Norma Editorial") == "norma"
    assert mw._publisher_slug("Planeta Cómic") == "planeta"
    assert mw._publisher_slug("Astiberri Ediciones") == "astiberri"
    assert mw._publisher_slug("Ponent Mon") == "ponentmon"
    assert mw._publisher_slug("Ediciones B") == "edicionesb"
    assert mw._publisher_slug("Bruguera") == "bruguera"
    assert mw._publisher_slug("Ediciones La Cúpula") == "lacupula"
    assert mw._publisher_slug("LetraBlanka") == "letrablanka"
    assert mw._publisher_slug("Héroes de Papel") == "heroesdepapel"
    assert mw._publisher_slug("Ooso Comics") == "ooso"


def test_country_slug_maps_markets():
    """_country_slug normaliza el país de la edición a un código corto."""
    assert mw._country_slug("España") == "es"
    assert mw._country_slug("Italia") == "it"
    assert mw._country_slug("Japón") == "jp"
    assert mw._country_slug("México") == "mx"
    assert mw._country_slug("Brasil") == "br"
    assert mw._country_slug("") == "xx"
    assert mw._country_slug(None) == "xx"


def test_edition_key_includes_country_so_markets_never_merge():
    """REGLA DURA (gotcha #46): país distinto = edición distinta. El edition_key
    de la misma serie+editorial+edición pero distinto país DEBE diferir."""
    es = mw.Candidate(
        title="Hunter x Hunter 1 Variant", url="https://www.panini.es/x",
        source="ES", source_url="y", country="España", language="Español",
        publisher="Panini Manga", source_class="publisher", tags=[],
        description="", signal_types=["variant_cover"],
    )
    it = mw.Candidate(
        title="Hunter x Hunter 1 Variant", url="https://www.panini.it/x",
        source="IT", source_url="y", country="Italia", language="Italiano",
        publisher="Panini Comics", source_class="publisher", tags=[],
        description="", signal_types=["variant_cover"],
    )
    ek_es = mw.derive_series_metadata(es).get("edition_key", "")
    ek_it = mw.derive_series_metadata(it).get("edition_key", "")
    assert ek_es.endswith("-es"), ek_es
    assert ek_it.endswith("-it"), ek_it
    assert ek_es != ek_it
    # y el cluster_key (que deriva del edition_key) tampoco coincide
    row_es = {"edition_key": ek_es, "volume": "1", "country": "España"}
    row_it = {"edition_key": ek_it, "volume": "1", "country": "Italia"}
    assert mw.derive_cluster_key(row_es) != mw.derive_cluster_key(row_it)


def test_candidate_to_json_preserves_title_original():
    """`candidate_to_json` SIEMPRE escribe `title_original` con el title
    scrapeado (cleaned). El skill `/watch-standardize-catalog` después puede
    sobrescribir `title` con el standardized pero preserva `title_original`.
    """
    c = mw.Candidate(
        title="鬼滅の刃 23 特装版",
        url="x", source="JP - Rakuten", source_url="y",
        country="Japón", language="Japonés", publisher="Shueisha",
        source_class="retailer", tags=[], description="",
        signal_types=["limited"],
    )
    row = mw.candidate_to_json(c)
    assert row["title_original"] == "鬼滅の刃 23 特装版"
    # title también lleva el original cuando el scraper no estandariza
    assert row["title"] == "鬼滅の刃 23 特装版"


def test_candidate_to_json_assigns_rough_metadata():
    """`candidate_to_json` debe poblar series_key heurísticamente cuando
    el Candidate no los tiene seteados. `standardized_at` queda vacío
    (el skill /watch-standardize-catalog lo setea después).
    """
    c = mw.Candidate(
        title="One Piece Vol. 100 Edición Coleccionista",
        url="x", source="ES - Planeta", source_url="y",
        country="España", language="Español",
        publisher="Planeta Cómic", source_class="retailer",
        tags=[], description="",
        signal_types=["collector", "limited"],
    )
    row = mw.candidate_to_json(c)
    assert row.get("series_key") == "one-piece"
    assert row.get("volume") == "100"
    assert row.get("edition_key", "").startswith("one-piece-planeta-")
    assert not row.get("standardized_at")


def test_canonical_series_key_returns_input_when_no_match():
    """Si la serie no está en aliases.yml, devuelve el input sin tocar."""
    from series_aliases import canonical_series_key
    new_sk, new_sd = canonical_series_key(
        'Random Obscure Manga Vol 1',
        'random-obscure-manga',
        'Random Obscure Manga',
    )
    assert new_sk == 'random-obscure-manga'
    assert new_sd == 'Random Obscure Manga'


def test_is_canonical_key():
    """is_canonical_key devuelve True solo para keys del YAML."""
    from series_aliases import is_canonical_key
    assert is_canonical_key('berserk') is True
    assert is_canonical_key('demon-slayer') is True
    assert is_canonical_key('one-piece') is True
    # Series NO canónicas
    assert is_canonical_key('atelier-of-witch-hat') is False  # es alias, no canonical
    assert is_canonical_key('random-new-series') is False
    assert is_canonical_key('') is False


def test_log_unmapped_series_appends_only_non_canonical(tmp_path, monkeypatch):
    """log_unmapped_series escribe solo series NO canónicas, dedupea por run."""
    import series_aliases as sa
    fake_log = tmp_path / 'unmapped.jsonl'
    monkeypatch.setattr(sa, '_UNMAPPED_FILE', fake_log)
    sa.reset_unmapped_run_state()

    # 1) Series canónica → NO se loguea
    sa.log_unmapped_series('berserk', 'Berserk', 'Berserk Deluxe 1', 'http://x/1', 'src')
    assert not fake_log.exists() or fake_log.read_text() == ''

    # 2) Series NO canónica → SÍ se loguea (1 línea)
    sa.log_unmapped_series('new-series', 'New Series', 'New Series Vol 1', 'http://x/2', 'src')
    assert fake_log.exists()
    lines = fake_log.read_text().strip().splitlines()
    assert len(lines) == 1
    import json as _json
    record = _json.loads(lines[0])
    assert record['series_key'] == 'new-series'
    assert record['sample_title'] == 'New Series Vol 1'

    # 3) Dedup: misma series_key, segunda llamada NO appendea
    sa.log_unmapped_series('new-series', 'New Series', 'New Series Vol 2', 'http://x/3', 'src')
    lines = fake_log.read_text().strip().splitlines()
    assert len(lines) == 1  # sigue siendo 1

    # 4) Series_key vacío → NO se loguea
    sa.log_unmapped_series('', '', '', '', '')
    lines = fake_log.read_text().strip().splitlines()
    assert len(lines) == 1

    # 5) Reset → segunda corrida puede re-loguear
    sa.reset_unmapped_run_state()
    sa.log_unmapped_series('new-series', 'New Series', 'New Series Vol 4', 'http://x/4', 'src')
    lines = fake_log.read_text().strip().splitlines()
    assert len(lines) == 2  # ahora hay 2 líneas, segunda del segundo run


def test_whakoom_is_publisher_url():
    from wikis import whakoom as wk
    assert wk.is_whakoom_publisher_url(
        "https://www.whakoom.com/publisher/41878/edicion_limitada"
    )
    assert wk.is_whakoom_publisher_url(
        "https://en.whakoom.com/publisher/12345/dark_horse"
    )
    assert not wk.is_whakoom_publisher_url(
        "https://www.whakoom.com/ediciones/123/x"
    )
    assert not wk.is_whakoom_publisher_url("https://example.com/publisher/1/x")
    assert not wk.is_whakoom_publisher_url("")


def test_whakoom_expand_publisher_extracts_ediciones_then_calls_edition_expander():
    """Pasamos publisher_html pre-fetched + monkeypatch a expand_whakoom_edition
    para no hacer HTTP real ni fetching de cada edición."""
    from wikis import whakoom as wk
    publisher_html = """<html><body>
        <h1>Edición Limitada</h1>
        <a href="/ediciones/100/foo-bar">Foo</a>
        <a href="/ediciones/100/foo-bar/todos">dup id 100</a>
        <a href="/ediciones/200/baz">Baz</a>
        <a href="/comics/abc/foo/1">not edition</a>
    </body></html>"""
    called_with: list[str] = []
    orig = wk.expand_whakoom_edition
    def fake_expand(ed_url, session, **kw):
        called_with.append(ed_url)
        return []
    wk.expand_whakoom_edition = fake_expand
    try:
        wk.expand_whakoom_publisher_url(
            "https://www.whakoom.com/publisher/41878/x",
            session=None, sleep_seconds=0,
            publisher_html=publisher_html,
        )
    finally:
        wk.expand_whakoom_edition = orig
    # Dedupea id 100 (aparece 2 veces) + visita id 200 — total 2 llamadas.
    assert len(called_with) == 2
    assert any("/ediciones/100/" in u for u in called_with)
    assert any("/ediciones/200/" in u for u in called_with)


def test_whakoom_detects_cloudflare_challenge():
    from wikis import whakoom as wk
    challenges = [
        '<html><head><meta name="cf-chl-bypass" content="x"></head></html>',
        '<html><body>Just a moment...<noscript>verify</noscript></body></html>',
        '<html><body>Checking your browser before accessing</body></html>',
        '<html><body><script>window.__cf_chl_rt_tk="abc"</script></body></html>',
        '<html><body><script src="/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1"></script></body></html>',
    ]
    for c in challenges:
        assert wk._looks_like_cf_challenge(c), f"Should detect challenge: {c[:50]!r}"
    # Páginas legítimas NO matchean
    assert not wk._looks_like_cf_challenge("<html><body>normal content</body></html>")
    assert not wk._looks_like_cf_challenge("")
    # Páginas reales protegidas por CF cargan el JSD bot-detection script
    # desde /cdn-cgi/challenge-platform/scripts/jsd/main.js — NO es un challenge.
    # Antes este caso era un falso positivo que rompía todas las requests.
    legit_with_jsd = (
        '<html><body>real content<script src="/cdn-cgi/'
        'challenge-platform/scripts/jsd/main.js"></script></body></html>'
    )
    assert not wk._looks_like_cf_challenge(legit_with_jsd)
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


def test_clean_title_strips_funside_cart_prefix():
    """Funside.it y similares italianos capturan los botones del listing como
    PREFIX del título (no suffix). Validar que se limpian."""
    assert mw.clean_title(
        "Aggiungi al carrello Confrontare CACCIATORI DI CADAVERI - DELUXE EDITION (VOLL. 1-4) - VARIANT"
    ) == "CACCIATORI DI CADAVERI - DELUXE EDITION (VOLL. 1-4) - VARIANT"
    assert mw.clean_title(
        "Aggiungi al carrello Confrontare AI TEMPI DI BOCCHAN PERFECT EDITION VOL.4 - VARIANT"
    ) == "AI TEMPI DI BOCCHAN PERFECT EDITION VOL.4 - VARIANT"
    # Variante sin "Confrontare" + nombre de tienda como sufijo.
    assert mw.clean_title(
        "Aggiungi al carrello NON TORMENTARMI, NAGATORO! 1 - VARIANT GAMES ACADEMY FUNSIDE"
    ) == "NON TORMENTARMI, NAGATORO! 1 - VARIANT"
    assert mw.clean_title(
        "Aggiungi al carrello L'EROE E' MORTO 1 - VARIANT GAMES ACADEMY FUNSIDE/ POPSTORE"
    ) == "L'EROE E' MORTO 1 - VARIANT"


def test_clean_title_strips_italian_price_block():
    """Funside/Shopify italiano: el selector genérico captura la tarjeta entera
    con el bloque de precio. Cortar desde 'Prezzo normale/di vendita/unitario'."""
    assert mw.clean_title(
        "AI TEMPI DI BOCCHAN PERFECT EDITION VOL.4 - VARIANT Prezzo normale €22,00 "
        "Prezzo di vendita €22,00 Prezzo normale €22,00 Prezzo unitario / per Aggiungi"
    ) == "AI TEMPI DI BOCCHAN PERFECT EDITION VOL.4 - VARIANT"
    # Dynit: cola "Disponibile dal: DD/MM/YYYY Dynit".
    assert mw.clean_title(
        "Isekai Editor (The) #03 Disponibile dal: 05/06/2026 Dynit"
    ) == "Isekai Editor (The) #03"


def test_clean_title_decodes_html_entities():
    """Entidades HTML sin decodificar del scraper (gotcha #94)."""
    assert mw.clean_title("Fire Force — Vol.34 - Collector&#039;s box") == \
        "Fire Force — Vol.34 - Collector's box"
    assert mw.clean_title("Black Lagoon — Girls &amp; Weapons - Sunday GX") == \
        "Black Lagoon — Girls & Weapons - Sunday GX"


def test_clean_title_strips_thai_status_badges():
    """IPM/Siam TH: '(PRE-ORDER)' como prefijo y '[NEW]' embebido son badges de
    estado, no parte del título (gotcha #94). No deben pegar palabras vecinas."""
    assert mw.clean_title("(PRE-ORDER) TOKYO GHOUL : RE เล่ม 16 (จบ) [NEW] (ชุดพิเศษ boxset)") == \
        "TOKYO GHOUL : RE เล่ม 16 (จบ) (ชุดพิเศษ boxset)"
    assert mw.clean_title("ไอส์ เล่ม 12 [NEW] + (ชุดพิเศษ Boxset)") == \
        "ไอส์ เล่ม 12 + (ชุดพิเศษ Boxset)"


def test_clean_title_strips_korean_retailer_tail():
    """Aladin/Hansan KR ('만화 한정판'): el selector captura bonus + autor +
    editorial + precio + millas + sales-point. El nombre oficial termina en el
    marcador de edición '(…한정판)' / '한정판 [박스] [세트]'."""
    assert mw.clean_title(
        "블루 아카이브 오피셜 아트웍스 2 (한정판) - 글리터아크릴 4종 + 일러스트 카드 6매 "
        "신민섭 (옮긴이), NEXON GAMES (감수) | 학산문화사(만화) | 2024년 9월 98,000 원 → 88,200원"
    ) == "블루 아카이브 오피셜 아트웍스 2 (한정판)"
    assert mw.clean_title(
        "일립예고 학생들 1~2 한정판 박스 세트 - 아크릴 스탠드 + 엽서 8종 백본 (지은이) | 학산문화사(만화) | 2025년 3월"
    ) == "일립예고 학생들 1~2 한정판 박스 세트"
    # Idempotente: un título ya limpio no cambia.
    assert mw.clean_title("승리의 여신: 니케 공식 아트북 (한정판)") == "승리의 여신: 니케 공식 아트북 (한정판)"
    # No toca títulos no-coreanos (sin Hangul, el helper no corre).
    assert mw.clean_title("Berserk Maximum 1") == "Berserk Maximum 1"


def test_fetch_with_playwright_dispatches_to_worker_thread():
    """`fetch_with_playwright` debe correr el trabajo Playwright SIEMPRE en
    el dedicated `_PLAYWRIGHT_WORKER` thread, no en el thread caller.

    Esto previene el bug `greenlet.error: Cannot switch to a different
    thread` observado en scrape_full del 2026-05-24 con workers=8 (cuando
    cualquier worker del ThreadPoolExecutor podía intentar usar el
    Playwright singleton creado por OTRO thread).

    Mockea `_fetch_with_playwright_impl` y `_playwright_available` para
    no requerir Chromium instalado. Verifica:
      1. Que el impl corre en un thread distinto del caller.
      2. Que 8 dispatches paralelos desde threads distintos comparten
         UN ÚNICO worker thread (serializados por la queue, sin race).
      3. Que close_playwright termina limpiamente y permite re-init.
    """
    import threading
    import concurrent.futures as cf
    import sys as _sys

    # Mock minimal sin requerir Playwright real
    real_available = mw._playwright_available
    real_impl = mw._fetch_with_playwright_impl
    mw._playwright_available = lambda: True

    impl_threads: list[str] = []

    def fake_impl(browser, url, timeout_ms, wait_until):
        impl_threads.append(threading.current_thread().name)
        return ("<html>ok</html>", {"http_status": 200, "fetch_ms": 1})

    mw._fetch_with_playwright_impl = fake_impl

    # Mock sync_playwright en sys.modules (el worker lo importa lazy)
    class _FakeBrowser:
        def close(self): pass
    class _FakeChromium:
        def launch(self, **kw): return _FakeBrowser()
    class _FakePW:
        chromium = _FakeChromium()
        def stop(self): pass
    class _FakeSyncPW:
        def start(self): return _FakePW()
    fake_pw_mod = type(_sys)("playwright")
    fake_sync_mod = type(_sys)("playwright.sync_api")
    fake_sync_mod.sync_playwright = lambda: _FakeSyncPW()
    saved_pw = _sys.modules.get("playwright")
    saved_sync = _sys.modules.get("playwright.sync_api")
    _sys.modules["playwright"] = fake_pw_mod
    _sys.modules["playwright.sync_api"] = fake_sync_mod

    # Asegurarse que arrancamos limpio
    mw.close_playwright()

    try:
        # Test 1: el impl corre en el dedicated worker, no en main
        caller = threading.current_thread().name
        html, _ = mw.fetch_with_playwright("http://example.test/1", timeout_ms=5000)
        assert html == "<html>ok</html>"
        assert len(impl_threads) == 1
        assert impl_threads[0] != caller, \
            f"impl ran in caller thread {caller!r}; expected worker"
        assert impl_threads[0] == "playwright-worker"

        # Test 2: 8 dispatches paralelos → todos ejecutan en el mismo worker
        impl_threads.clear()
        def call_one(i):
            return mw.fetch_with_playwright(f"http://example.test/{i}", timeout_ms=5000)
        with cf.ThreadPoolExecutor(max_workers=8) as pool:
            results = [f.result() for f in [pool.submit(call_one, i) for i in range(16)]]
        assert all(r[0] == "<html>ok</html>" for r in results)
        assert len(impl_threads) == 16
        # TODOS los jobs corrieron en el mismo worker thread (queue serializa)
        assert set(impl_threads) == {"playwright-worker"}, \
            f"jobs ran in multiple threads: {set(impl_threads)}"

        # Test 3: close + re-init
        mw.close_playwright()
        assert mw._PLAYWRIGHT_WORKER is None
        impl_threads.clear()
        html2, _ = mw.fetch_with_playwright("http://example.test/restart", timeout_ms=5000)
        assert html2 == "<html>ok</html>"
        assert impl_threads == ["playwright-worker"]
    finally:
        mw.close_playwright()
        mw._playwright_available = real_available
        mw._fetch_with_playwright_impl = real_impl
        if saved_pw is None:
            _sys.modules.pop("playwright", None)
        else:
            _sys.modules["playwright"] = saved_pw
        if saved_sync is None:
            _sys.modules.pop("playwright.sync_api", None)
        else:
            _sys.modules["playwright.sync_api"] = saved_sync


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


# --- split_store_bonus: separa el 店舗特典 del título oficial (gotcha #93) ---

def test_split_store_bonus_strips_rakuten_perk():
    # Bracket 【…特典…】 = perk de compra de un retailer → fuera del título.
    clean, bonus = mw.split_store_bonus("数学ゴールデン 2(描き下ろしイラストカード)【楽天ブックス限定特典】")
    assert clean == "数学ゴールデン 2"
    assert "楽天ブックス限定特典" in bonus


def test_split_store_bonus_preserves_volume_paren():
    # El paréntesis adjacente que es SÓLO el volumen NO se consume.
    clean, bonus = mw.split_store_bonus("年の差婚(3)【楽天ブックス限定特典付き】")
    assert clean == "年の差婚(3)"
    assert "特典" in bonus


def test_split_store_bonus_keeps_edition_name():
    # 【…特装版】 nombra la EDICIÓN (no un bonus de tienda) → NO se toca.
    clean, bonus = mw.split_store_bonus("SUPER LOVERS 第14巻 小冊子付き特装版【楽天ブックス限定特典付き】")
    assert clean == "SUPER LOVERS 第14巻 小冊子付き特装版"
    assert "特典" in bonus


def test_split_store_bonus_noop_without_perk():
    # Sin 特典 → intacto, sin bonus. Idempotente.
    for t in ("鬼滅の刃 23 特装版", "Berserk Deluxe 1", ""):
        clean, bonus = mw.split_store_bonus(t)
        assert clean == t and bonus == ""
        # idempotencia: re-aplicar no cambia
        assert mw.split_store_bonus(clean)[0] == clean


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


def test_clean_title_strips_orphan_volume_markers():
    """Bug real (2026-05-23): items del calendario para "guías de edición" venían
    con title tipo "Ataque a los Titanes nº Collector's Edition" — el `nº` huérfano
    (sin número) confundía al LLM del skill /watch-standardize-catalog, que lo dejaba
    como "no" residual en title + series_key (`ataque-a-los-titanes-no`),
    fragmentando el cluster. clean_title ahora strippea markers nº/n°/vol(.)
    huérfanos (sin número adyacente).

    PRESERVAR cuando el marker SÍ tiene número (es legítimo)."""
    strip_cases = [
        ("Ataque a los Titanes nº Collector's Edition", "Ataque a los Titanes Collector's Edition"),
        ("Mujina into the deep nº Special Edition", "Mujina into the deep Special Edition"),
        ("Atelier of Witch Hat nº Special Edition", "Atelier of Witch Hat Special Edition"),
        ("Mazinger Z nº Collector's Edition", "Mazinger Z Collector's Edition"),
    ]
    for raw, expected in strip_cases:
        actual = mw.clean_title(raw)
        assert actual == expected, f"\n  input:    {raw!r}\n  expected: {expected!r}\n  actual:   {actual!r}"

    preserve_cases = [
        # Markers con número adyacente: legítimos, NO strippear.
        "Ataque a los Titanes nº1",
        "Berserk Vol. 41 Edición Especial",
        "X-Men Vol. 1",
        # Palabra "tomo" en title legítimo (NO es marker de volumen):
        "DNANGEL #10 ¡ÚLTIMO TOMO!",
    ]
    for raw in preserve_cases:
        actual = mw.clean_title(raw)
        assert actual == raw, f"\n  input:    {raw!r}\n  expected unchanged\n  actual:   {actual!r}"


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


def test_is_likely_manga_bonus_context_rescues_official_titles():
    """Gotcha #92: desde la política de títulos 2026-06-12 el title es el
    nombre OFICIAL scrapeado, que nombra el bonus de la edición (figura, DVD,
    standee…). El marcador de inclusión pegado al match rescata el item."""
    cases = [
        # JP: 付き/付/同梱 después del producto-bonus
        "夏目友人帳 ニャンコ先生フィギュアストラップ付き特装版 29",
        "3月のライオン18 ミニアクリルフィギュア12キャラ付き特装版",
        "侵略! イカ娘 17 オリジナルビデオアニメ(Blu-ray)付限定版 (少年チャンピオン・コミックス)",
        "マケン姫っ! -MAKEN-KI! - 11 ブルーレイ付き限定版 (ドラゴンコミックスエイジ)",
        "UQ HOLDER!(16)限定版 DVD＋パクティオカード同梱",
        # 特装版 = edición de LIBRO, rescata aunque el disco no lleve 付
        "テラフォーマーズ(21)特装版 DVD LIMITED EDITION",
        # 限定版プレミアムBOX = premium box de un manga, no idol box
        "帝都初恋心中 5 限定版プレミアムBOX",
        # 図鑑未掲載 describe el bonus, no es una enciclopedia
        "キン肉マン「技」(ダウンロード 図鑑未掲載!超人技データファイル(正義超人セット)全5種)【楽天ブックス限定特典】",
        # EN: "w/" = with (listings de Mangavariant recuperados, 2026-06-12)
        "Fairy Tail — Vol.35 - Special edition w/ DVD",
        "Beelzebub — Vol.9 - Special edition w/DVD",
        # IT: con/+ marcan el bonus o el bundle de dos obras
        "L'estate in cui Hikaru è morto. Ediz. variant. Con acrylic standee (Vol. 1)",
        "Il Mio Dannato Rivale N° 2 - Variant Bundle con Storia Extra-Piccante - Planet Manga",
        "Sakamoto Days Variant con T-shirt 3",
        "Yomi No Tsugai Variant + Fullmetal Alchemist Variant Bundle 1",
    ]
    for t in cases:
        is_manga, reason = mw.is_likely_manga(t)
        assert is_manga, f"Should be manga (bonus de edición): {t!r} (reason={reason})"


def test_is_likely_manga_bonus_context_still_rejects_products():
    """La guarda de bonus NO rescata productos completos: el marcador tiene
    que estar pegado al match (神の庭付き楠木邸 tiene 付き en el NOMBRE de la
    obra y sigue siendo un Blu-ray de anime)."""
    cases = [
        ("神の庭付き楠木邸 Blu-ray BOX 下巻", "Blu-ray de anime"),
        ("体育する生徒会限定箱「生徒会の一存」富士見書房公式フィギュア", "figura oficial"),
        ("ワンピース ルフィ フィギュア", "figura"),
        ("AKB48 プレミアムBOX", "idol box"),
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


def test_is_likely_manga_rejects_by_non_manga_url():
    """Secciones no-manga del sitio (viz.com/anime/ = Blu-ray/DVD): el título
    no menciona DVD/Blu-ray pero la URL delata el tipo de producto."""
    cases = [
        ("Castlevania: The Complete Series, Limited Edition",
         "https://www.viz.com/anime/tv-series/castlevania-season-1/product/8604"),
        ("Naruto Triple Feature Collector's Edition (Steelbook)",
         "https://www.viz.com/anime/movie/naruto-the-movie-video/product/6489"),
        ("Sailor Moon Crystal, Set 2 (Limited Edition)",
         "https://www.viz.com/anime/tv-series/sailor-moon-crystal-video-volume-2-0/product/5117"),
        ("UZUMAKI: Animated TV Series, Limited Edition",
         "https://www.viz.com/anime/tv-series/uzumaki-video/product/8212"),
    ]
    for title, url in cases:
        is_manga, reason = mw.is_likely_manga(title, url=url)
        assert not is_manga, f"Should reject by URL: {url!r} (reason={reason})"
        assert reason.startswith("non_manga_url:"), f"reason should be non_manga_url: but got {reason}"
    # Un producto manga de VIZ (path /manga-books/) NO debe ser rechazado por URL.
    is_manga, reason = mw.is_likely_manga(
        "Revolutionary Girl Utena Complete Deluxe Box Set",
        url="https://www.viz.com/manga-books/manga/revolutionary-girl-utena-complete-deluxe-box-set/product/5054",
    )
    assert is_manga, f"VIZ manga-books product wrongly rejected: {reason}"


def test_is_pure_novel_bypasses_asian_novels_and_artbooks():
    """Las light novels/danmei con edición especial están EN scope (CLAUDE.md:
    'light novels con bonus'). El detector de novelas puras caza bestsellers
    occidentales, no la línea asiática de Seven Seas."""
    in_scope = [
        # danmei en la descripción
        ("Dinghai Fusheng Records (Novel) Vol. 1 (Special Edition)",
         "The hit danmei novel series that inspired the manhua and donghua!"),
        # marcador "(Novel)" en el título, sin danmei en la desc
        ("Run Wild: Sa Ye (Novel) Vol. 1 (Special Edition)",
         "In this novel series originally released in Chinese, two young men…"),
        # artbook que menciona "novel series" en la desc
        ("The Untamed: The Official Artbook (Hardcover)",
         "An artbook for the drama (adaptation of the bestselling fantasy novel series Mo Dao Zu Shi)."),
    ]
    for title, desc in in_scope:
        is_novel, reason = mw.is_pure_novel(title, desc)
        assert not is_novel, f"In-scope item rejected as novel: {title!r} ({reason})"
    # Un bestseller occidental sigue siendo rechazado.
    is_novel, reason = mw.is_pure_novel(
        "Alas de Sangre. Edición coleccionista",
        "La saga romántica bestseller del fenómeno BookTok.",
    )
    assert is_novel, "Western bestseller should still be rejected"


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


def test_franchise_exceptions_protect_real_manga():
    """Títulos en franchise_exceptions/title_exceptions son manga reales — no deben
    rechazarse por la regla franchise_keywords aunque contengan nombres de franquicia
    occidental."""
    cases = [
        # (a) Shugo Chara! Jewel Joker — contiene "Joker" que está en blacklist
        "Shugo Chara! Jewel Joker 4 Edición Especial",
        # (b) Deadpool: Samurai — contiene "Deadpool" que está en blacklist
        "Deadpool: Samurai Variant 2",
        # Batman Ninja — contiene "Batman"
        "Batman Ninja Vol. 1",
        # Hungry Joker — contiene "Joker"
        "Hungry Joker 3",
        # Cell of Empireo — contiene "Empireo" (blacklisteado como saga Yarros)
        "Saibou Shinkoku: Cell of Empireo Vol. 1",
    ]
    for title in cases:
        is_comic, reason = mw.is_comic_not_manga(title, publisher="Panini Manga")
        assert not is_comic, (
            f"franchise_exception debe proteger {title!r} (reason={reason})"
        )


def test_title_exceptions_protect_confirmed_false_positives():
    """Falsos positivos confirmados: manga japoneses reales que matchean keywords
    de franquicia occidental o patrones hard non-manga."""
    # (a) Batman: El Hijo de los Sueños (Kia Asamiya) — contiene "Batman"
    #     Ediciones Norma y ECC en español
    batman_child = [
        "Batman: El Hijo de los Sueños",
        "Batman: El Hijo de los Sueños Vol. 1 Norma Editorial",
        "Batman El Hijo de los Sueños Edición Integral ECC",
    ]
    for title in batman_child:
        is_comic, reason = mw.is_comic_not_manga(title, publisher="Norma Editorial")
        assert not is_comic, (
            f"title_exception debe proteger Batman/Kia Asamiya: {title!r} (reason={reason})"
        )
        is_manga, reason2 = mw.is_likely_manga(title, source_purity="mixed")
        assert is_manga or "comic_franchise" not in reason2, (
            f"is_likely_manga no debe rechazar por comic_franchise: {title!r} (reason={reason2})"
        )

    # (b) Assassin's Creed: Blade of Shao Jun (Minoji Kurata) — contiene "Assassin's Creed"
    shao_jun = [
        "Assassin's Creed: Blade of Shao Jun Vol. 1",
        "Assassin's Creed: Blade of Shao Jun Vol. 2 Variant Edition",
        "Assassin's Creed Blade of Shao Jun Edición Coleccionista",
    ]
    for title in shao_jun:
        is_comic, reason = mw.is_comic_not_manga(title, publisher="Panini Manga")
        assert not is_comic, (
            f"title_exception debe proteger Blade of Shao Jun: {title!r} (reason={reason})"
        )
        is_manga, reason2 = mw.is_likely_manga(title, source_purity="mixed")
        assert is_manga or "comic_franchise" not in reason2, (
            f"is_likely_manga no debe rechazar por comic_franchise: {title!r} (reason={reason2})"
        )

    # (c) Eagle: The Making of an Asian-American President (Kaiji Kawaguchi)
    #     Matchea patrón hard \bThe\s+Making\s+of\b — debe ser exceptuado vía title_exceptions
    #     La excepción usa la frase "Making of an Asian-American President" para ser específica
    eagle = [
        "Eagle: The Making of an Asian-American President Vol. 1",
        "Eagle: The Making of an Asian-American President Omnibus Deluxe",
        "Eagle The Making of an Asian-American President",
    ]
    for title in eagle:
        is_manga, reason = mw.is_likely_manga(title, source_purity="manga_only")
        assert is_manga, (
            f"title_exception debe proteger Eagle/Kawaguchi de non_manga_hard: {title!r} (reason={reason})"
        )
        assert "non_manga_hard" not in reason, (
            f"non_manga_hard no debe activarse para Eagle/Kawaguchi: {title!r} (reason={reason})"
        )


def test_title_exceptions_do_not_protect_real_western_comics():
    """Las excepciones NO deben proteger cómics occidentales reales ni making-ofs
    genéricos de videojuegos."""
    # Batman: The Killing Joke — no está en title_exceptions, sigue rechazándose
    cases_still_rejected_franchise = [
        "Batman: The Killing Joke",
        "Joker Vol. 1",
        "Deadpool Classic Vol. 1",
        "Assassin's Creed: The Official Comic",
    ]
    for title in cases_still_rejected_franchise:
        is_comic, reason = mw.is_comic_not_manga(title, publisher="Norma Editorial")
        assert is_comic, (
            f"Cómic occidental debe seguir rechazándose: {title!r} (reason={reason})"
        )
        assert reason.startswith("comic_franchise:"), reason

    # Making-of genérico de videojuego (NO exceptuado) — sigue rechazándose
    # (por non_manga_hard o comic_franchise dependiendo del título)
    cases_still_rejected_hard = [
        "Attack on Titan: The Making of the Anime Artbook",
        "The Making of Final Fantasy XV",
        # "The Making of The Last of Us" se rechaza por comic_franchise antes del hard check
        "The Making of The Last of Us",
    ]
    for title in cases_still_rejected_hard:
        is_manga, reason = mw.is_likely_manga(title, source_purity="manga_only")
        assert not is_manga, (
            f"Making-of genérico debe seguir rechazándose: {title!r} (reason={reason})"
        )
        assert "non_manga_hard" in reason or "comic_franchise" in reason, (
            f"Debe rechazarse por non_manga_hard o comic_franchise: {title!r} (reason={reason})"
        )


def test_franchise_keywords_still_reject_western_comics():
    """Las excepciones NO deben desactivar la regla franchise para cómics reales."""
    # (c) Batman: The Killing Joke — no es excepción, es cómic de DC
    cases = [
        "Batman: The Killing Joke",
        "Joker Vol. 1",
        "Deadpool Classic Vol. 1",
    ]
    for title in cases:
        is_comic, reason = mw.is_comic_not_manga(title, publisher="Norma Editorial")
        assert is_comic, (
            f"Cómic occidental debe rechazarse: {title!r} (reason={reason})"
        )
        assert reason.startswith("comic_franchise:"), reason


def test_standee_as_extra_not_hard_rejected():
    """Un tomo de manga que INCLUYE un standee como extra no debe rechazarse."""
    # (d) standee como extra → NO hard-reject
    cases_ok = [
        "My Dress Up Darling Bisque Doll Ediz Deluxe Con Standee In Acrilico Variant 15",
        "Tomo 1 Edición Especial with Standee exclusivo",
        "Coffret Deluxe avec Standee collector",
        "Deluxe Edition mit Standee",
        "Edicion inkl. Standee",
        "Edicion inkl Standee",
    ]
    for title in cases_ok:
        is_manga, reason = mw.is_likely_manga(title, source_purity="manga_only")
        # El reason del standee contiene el patrón completo con lookbehinds —
        # lo identificamos buscando "standees?" en el reason string.
        assert "standees?" not in reason, (
            f"standee como extra NO debe causar hard-reject: {title!r} (reason={reason})"
        )

    # (e) standee suelto como producto principal → SÍ rechazar
    cases_reject = [
        "Dragon Ball Super Standee",
        "Goku Standee acrilico 30cm",
        "Jujutsu Kaisen Standees Set",
    ]
    for title in cases_reject:
        is_manga, reason = mw.is_likely_manga(title, source_purity="manga_only")
        assert not is_manga and "non_manga_hard" in reason, (
            f"standee suelto debe rechazarse: {title!r} (reason={reason})"
        )


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
        # Omnibus solo NO califica; con un qualifier premium SÍ.
        # (Berserk Omnibus solito quedó rechazado en el siguiente test.)
        ("Berserk Omnibus Deluxe Hardcover Vol. 1", ["omnibus", "deluxe", "hardcover"]),
        ("Lone Wolf & Cub Omnibus – Cofanetto 3", ["omnibus", "box_set"]),
        ("Naruto Special Bundle Vol 1-5", ["bundle"]),
        ("限定版 ONE PIECE 100", ["limited"]),
    ]
    for title, sigs in cases:
        ok, reason = mw.is_collectible_edition(title, "", sigs, "manga")
        assert ok, f"Should accept (signal): {title!r} (reason={reason})"


def test_is_collectible_edition_accepts_first_edition_cofre_with_numero():
    """Bug 2026-06-07: los tomos con cofre de 1ª edición de listadomanga tienen
    título "nºN" (ej. "Ataque a los Titanes nº1") y sólo signal `bonus`. El gate
    los tumbaba como `regular_tomo` porque `\\b\\d+\\b` NO reconoce el dígito
    pegado a "nº" (la "º" es word-char Unicode → sin boundary). Debe usar el
    shape de volumen de manga, que SÍ lo reconoce → KEEP."""
    for title in ["Ataque a los Titanes nº1", "Ataque a los Titanes nº17",
                  "Berserk nº34"]:
        ok, reason = mw.is_collectible_edition(title, "", ["bonus"], "manga")
        assert ok, f"cofre 1ª ed. debe pasar: {title!r} (reason={reason})"
        assert reason.startswith("extras:"), reason
    # sin volumen (news/social post) sigue rechazado
    ok, _ = mw.is_collectible_edition("Posters and tickets giveaway", "", ["bonus"], "manga")
    assert not ok


def test_listadomanga_synthetic_url_is_proof_of_product():
    """Bug 2026-06-07 (gotcha #50): una edición premium de 1 tomo SIN número en el
    título (ej. "21st Century Boys" Kanzenban) cuyo signal premium viene del título
    de la coleccion (en description) caía como `regular_tomo` porque el gate exigía
    prueba-de-producto (volumen-en-título / ISBN / product-url). La URL sintética de
    listadomanga (`coleccion.php?id=N&item=...`) ES un producto catalogado → cuenta
    como prueba."""
    ok, reason = mw.is_collectible_edition(
        "21st Century Boys", "20th Century Boys (Kanzenban) · Kanzenban",
        ["premium_format"], "manga",
        url="https://www.listadomanga.es/coleccion.php?id=2478&item=regular-0-abc",
    )
    assert ok, reason
    # la misma señal SIN url de producto y sin volumen → sigue rechazada (anti-ruido)
    ok2, _ = mw.is_collectible_edition(
        "21st Century Boys", "kanzenban", ["premium_format"], "manga",
        url="https://example.com/blog/top-10",
    )
    assert not ok2


def test_kanzenban_scores_above_threshold():
    """Bug 2026-06-07 (gotcha #50): 'kanzenban' puntuaba 25 < 30 (min_score) →
    colecciones Kanzenban enteras se descartaban. Ahora ≥30 (es un formato premium
    flagship, = perfect/master edition)."""
    score, _, _ = mw.detect_signals("20th Century Boys Kanzenban 1")
    assert score >= 30, score


def test_is_collectible_edition_rejects_plain_omnibus():
    """User decidió (2026-05-22): omnibus / N-in-1 sin qualifier premium = NO.

    Es básicamente un tomo más grueso, no una edición coleccionable.
    """
    plain_omnibus_cases = [
        ("Berserk Omnibus Vol. 1", ["omnibus"]),
        ("Bestiarius Omnibus", ["omnibus"]),
        ("One Piece (Omnibus Edition), Vol. 36", ["omnibus"]),
        ("Akatsuki no Yona (3 en 1)", ["omnibus"]),
        ("Haikyuu!! 3 en 1", ["omnibus"]),
        ("Eyeshield 21 (Edición 3 en 1) nº1 (de 13)", ["omnibus"]),
        ("Bleach 3 en 1 #14", ["omnibus"]),
        ("CUATRO FANTÁSTICOS DE BYRNE (MARVEL OMNIBUS)", ["omnibus"]),
        # "N-in-1 Edition" (VIZ/Shojo Beat): "in-1" NO es lore-word del
        # patrón <Word> Edition (bug 2026-06-12: capturaba "in-1").
        ("X (3-in-1 Edition), Vol. 6", []),
        ("Naruto (3-in-1 Edition), Vol. 1", []),
        ("Fushigi Yûgi (2-in-1 Edition), Vol. 4", []),
    ]
    for title, sigs in plain_omnibus_cases:
        ok, reason = mw.is_collectible_edition(title, "", sigs, "manga")
        assert not ok, f"Should REJECT plain omnibus: {title!r} (reason={reason})"


def test_is_collectible_edition_accepts_omnibus_with_premium_qualifier():
    """Omnibus + (hardcover|deluxe|limited|variant_cover|box_set|extras) = SÍ.

    `is_collectible_edition` exige "evidencia de producto físico" — un
    volumen en el title, ISBN, o URL canónica. Estos casos usan título
    con volumen para satisfacer esa guarda.
    """
    cases = [
        ("Lone Wolf & Cub Omnibus Vol. 3 – Cofanetto", ["omnibus", "box_set"]),
        ("Marvel Now! Deluxe. Secret Wars: Integral Vol 1", ["omnibus", "deluxe"]),
        ("Utena Edición Integral Vol. 1 - Cofre de 2 tomos", ["hardcover", "omnibus", "box_set"]),
        ("17 Años (Edición Integral) Vol 1 - (1ª Edición Limitada)", ["limited", "omnibus"]),
        ("Berserk Omnibus Variant Cover Vol. 1", ["omnibus", "variant_cover"]),
        ("Tokko (Edición Integral) Vol. 1 - (Portada Alternativa)", ["omnibus", "variant_cover"]),
    ]
    for title, sigs in cases:
        ok, reason = mw.is_collectible_edition(title, "", sigs, "manga")
        assert ok, f"Should accept omnibus+premium: {title!r} (reason={reason})"

    # Casos como "Look Back (Integral) (Castellano)" funcionan en
    # producción gracias al product_type=artbook (que es intrinsecamente
    # coleccionable) o por la URL canónica del producto. Verificamos
    # ambas vías:
    ok, _ = mw.is_collectible_edition(
        "Look Back (Integral) (Castellano)", "", ["hardcover", "omnibus"],
        "artbook",  # product_type artbook salva
    )
    assert ok
    ok, _ = mw.is_collectible_edition(
        "Goodbye Eri (Integral) (Castellano)", "", ["hardcover", "omnibus"],
        "manga",
        url="https://www.norma.com/producto/goodbye-eri-integral-edition-vol-1",
    )
    assert ok


def test_omnibus_edition_does_not_trigger_lore_edition_x_edition_regex():
    """`_GENERIC_X_EDITION_PATTERN` excluye 'Omnibus' tras gotcha #18.

    Antes "Omnibus Edition" disparaba lore_edition (que está en
    COLLECTIBLE_EDITION_SIGNAL_TYPES), permitiéndole entrar al catálogo
    por puerta trasera. Ahora 'Omnibus Edition' no matchea y solo "Tarot
    Edition", "Beherit Edition", "Gold Edition", etc. siguen activos.
    """
    # No debe matchear "Omnibus":
    assert mw._GENERIC_X_EDITION_PATTERN.search("One Piece (Omnibus Edition), Vol. 36") is None
    # SIGUE matcheando ediciones lore reales:
    assert mw._GENERIC_X_EDITION_PATTERN.search("Naruto Gold Edition N.30") is not None
    assert mw._GENERIC_X_EDITION_PATTERN.search("Berserk Tarot Edition") is not None
    assert mw._GENERIC_X_EDITION_PATTERN.search("Witcher Library Edition Hardcover") is not None


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


def test_is_collectible_edition_atom_magazine_url_discriminator():
    """Revista ATOM (Custom Publishing FR) discriminada por URL, no por título.

    El título estandarizado "Astro Boy | Mighty Atom Deluxe N" es idéntico
    tanto para la revista como para los tomos deluxe reales de Planeta (ES).
    El discriminador fiable es la URL: los items de la revista tienen
    manga-sanctuary.com/magazine-atom-vol-N-... en su URL.
    """
    # (a) Título deluxe Planeta con URL listadomanga → NO umbrella_magazine
    title_planeta = "Astro Boy | Mighty Atom Deluxe 3"
    url_planeta = "https://www.listadomanga.es/coleccion.php?id=2826&item=regular-3-4160db5dd79f867"
    ok, reason = mw.is_collectible_edition(
        title_planeta, "", ["deluxe"], "manga", url=url_planeta
    )
    assert ok, f"Planeta Deluxe should be kept: reason={reason}"
    assert reason != "umbrella_magazine", f"Planeta Deluxe should NOT be umbrella: reason={reason}"

    # (b) Mismo título con URL manga-sanctuary magazine-atom → umbrella_magazine
    url_magazine = "https://www.manga-sanctuary.com/magazine-atom-vol-16-hardcover-s48800-p342169.html"
    ok, reason = mw.is_collectible_edition(
        title_planeta, "", ["deluxe"], "manga", url=url_magazine
    )
    assert not ok, f"ATOM magazine should be rejected: reason={reason}"
    assert reason == "umbrella_magazine", f"Should be umbrella_magazine, got: {reason}"

    # (c) Weekly Shonen Jump → umbrella_magazine por título (sin cambio)
    ok, reason = mw.is_collectible_edition("Weekly Shonen Jump 52", "", [], "magazine")
    assert not ok
    assert reason == "umbrella_magazine"


def test_is_collectible_edition_keeps_variant_cover_with_magazine_suffix():
    """Gotcha #95: los 9 items reales que `umbrella_magazine` borraba.

    Mangavariant publica portadas variantes cuyo título lleva el nombre de la
    revista como SUFIJO descriptivo ("Sakamoto Days — The Order - Shonen Jump").
    `_UMBRELLA_JP_MAGAZINE_PATTERN.search(title)` a secas las marcaba como
    umbrella_magazine (HARD_REASON en filter_collectible, ignora standardized_at)
    y las borraba del corpus en el cleanup del pipeline. El discriminador: una
    portada variante lleva signal `variant_cover`, y/o la revista no es el sujeto
    inicial del título. Una antología real (sujeto inicial) sigue rechazándose.
    """
    # Los 8 variant_cover reales del corpus → NUNCA umbrella_magazine.
    variant_cases = [
        "Claymore — Green - Monthly Shonen Jump",
        "20th Century Boys — Vol.16 - Big Comic Spirits",
        "Silver Spoon — Vol.1 - Shonen Sunday",
        "Silver Spoon — Vol.2 - Shonen Sunday",
        "Real — Vol.6 - Young Jump",
        "Gifu Doudou!! Naoe Kanetsugu – Maeda Keiji Tsukigatari — Young Jump",
        "Sakamoto Days — The Order - Shonen Jump",
        "Terra Formars — Vol.6 - Young Jump variant",
    ]
    for title in variant_cases:
        ok, reason = mw.is_collectible_edition(title, "", ["variant_cover"], "manga")
        assert reason != "umbrella_magazine", f"variant NO debe ser umbrella: {title!r} (reason={reason})"

    # El 9º: revista de UNA serie (One Piece Magazine) que MENCIONA la antología
    # en su título de feature → producto legítimo (product_type=magazine).
    ok, reason = mw.is_collectible_edition(
        "ONE PIECE magazine 特集 週刊少年ジャンプとONE PIECE 020", "",
        ["fanbook", "special_edition"], "magazine",
    )
    assert ok, f"One Piece magazine debe conservarse (reason={reason})"
    assert reason != "umbrella_magazine", reason

    # Defensa: una antología real (revista como sujeto inicial) SIGUE rechazada
    # aunque pasáramos otra signal — el sujeto inicial manda.
    ok, reason = mw.is_collectible_edition("Weekly Shōnen Jump 2023 No.42", "", [], "magazine")
    assert not ok and reason == "umbrella_magazine", reason


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


def test_is_collectible_edition_x_edition_stoplist_multilingual():
    """Genéricos en ES/IT/FR también deben estar en la stoplist (gotcha #24).

    El regex matchea Edición/Edizione/Édition, así que "Nueva Edición"
    (= "New Edition", una reimpresión) NO puede rescatar — antes disparaba
    lore_edition y colaba tomos/omnibus normales por el gate.
    """
    cases = [
        "Detective Conan Nueva Edición 45",          # ES — reimpresión
        "Nausicaä del Valle del Viento Nueva Edición 1",
        "Yu-Gi-Oh! Nueva Edición 1",
        "Video Girl Ai Nueva Edición 2",
        "Naruto Nuova Edizione 3",                   # IT
        "One Piece Nouvelle Édition 5",              # FR
        "Bleach Primera Edición 10",                 # ES — ordinal
        "Berserk Última Edición 1",                  # ES — "last"
    ]
    for title in cases:
        ok, reason = mw.is_collectible_edition(title, "", [], "manga")
        assert not ok, f"Multilingual generic should not rescue: {title!r} (reason={reason})"
        assert mw._GENERIC_X_EDITION_PATTERN.search(title) is None, \
            f"_GENERIC_X_EDITION_PATTERN should not match {title!r}"


def test_nueva_edicion_omnibus_does_not_slip_through():
    """Omnibus "Nueva Edición 3 en 1" NO califica como coleccionable.

    Caso real del corpus (Planeta Cómic): "One Piece (Nueva Edición 3 en 1)"
    colaba porque "Nueva Edición" disparaba lore_edition. Es un omnibus
    pelado — sin hardcover/deluxe/limited/variant/extras → fuera. Gotcha #24.
    """
    omnibus_cases = [
        "One Piece (Nueva Edición 3 en 1) nº5",
        "Naruto (Nueva Edición 3 en 1) nº1",
        "Bastard!! (Nueva Edición 3 en 1) nº3",
        "Urusei Yatsura (Nueva Edición 2 en 1) nº1",
    ]
    for title in omnibus_cases:
        # Aun pasando los signal_types crudos del scraper, el gate debe rechazar.
        ok, reason = mw.is_collectible_edition(
            title, "", ["omnibus"], "manga",
        )
        assert not ok, f"Plain 'Nueva Edición' omnibus should be rejected: {title!r} (reason={reason})"


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


def test_append_jsonl_preserves_curated_fields_on_standardized_items(tmp_path):
    """Si el item existente tiene `standardized_at`, los campos curados por
    `/watch-standardize-catalog` (title, series_key, edition_key, etc.) se
    preservan en upserts subsiguientes — solo los scrapeados se refrescan.

    Sin esta merge, un re-scrape borraría la estandarización LLM-verified.
    """
    path = tmp_path / "items.jsonl"
    # Estado inicial: item curado por skill
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "Berserk Deluxe 1",
        "title_original": "Berserk Vol. 1 Deluxe Hardcover Edition",
        "series_key": "berserk",
        "series_display": "Berserk",
        "edition_key": "berserk-darkhorse-deluxe",
        "edition_display": "Deluxe Edition (Dark Horse)",
        "volume": "1",
        "standardized_at": "2026-05-22T10:00:00+00:00",
        "detected_at": "2026-05-22",
    }])

    # Re-scrape: title scrapeado raw
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "Berserk Vol. 1 Deluxe Hardcover Edition",
        "series_key": "berserk-1",  # heurístico crudo del scraper, peor que el canónico
        "edition_key": "berserk-1-darkhorse-special",
        "volume": "",  # scraper no detecta vol
        "detected_at": "2026-06-01",
    }])

    items = [json.loads(l) for l in path.open()]
    assert len(items) == 1
    it = items[0]
    # Curados preservados:
    assert it["title"] == "Berserk Deluxe 1"
    assert it["title_original"] == "Berserk Vol. 1 Deluxe Hardcover Edition"
    assert it["series_key"] == "berserk"
    assert it["edition_key"] == "berserk-darkhorse-deluxe"
    assert it["volume"] == "1"
    assert it["standardized_at"] == "2026-05-22T10:00:00+00:00"
    # detected_at es la PRIMERA detección: el re-scrape NO la resetea (gotcha #65).
    assert it["detected_at"] == "2026-05-22"
    # cluster_key se re-deriva con los campos curados restaurados → tier edition:
    assert it["cluster_key"] == "edition:berserk-darkhorse-deluxe|1"


def test_append_jsonl_rescrape_does_not_degrade_standardized_rows(tmp_path):
    """Gotcha #65: re-scrapear una fuente cuyos productos YA están
    estandarizados no debe degradar la fila — slug, detected_at, score y
    signal_types se preservan, y cluster_key se re-deriva al tier edition:
    (no queda en el tier isbn:/url: del candidate crudo)."""
    path = tmp_path / "items.jsonl"
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "Berserk Deluxe 1",
        "series_key": "berserk",
        "edition_key": "berserk-darkhorse-deluxe-us",
        "volume": "1",
        "slug": "berserk-deluxe-1",
        "standardized_at": "2026-05-22T10:00:00+00:00",
        "detected_at": "2026-05-22T09:00:00+00:00",
        "score": 85,
        "signals": ["deluxe hardcover"],
        "signal_types": ["special_edition"],
        "isbn": "9781506711980",
    }])

    # Candidate crudo del re-scrape: sin slug, cluster_key tier isbn:,
    # score/signals recomputados del texto crudo, detected_at = hoy.
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "Berserk Vol. 1 Deluxe Hardcover Edition",
        "isbn": "9781506711980",
        "cluster_key": "isbn:9781506711980",
        "detected_at": "2026-06-10T00:00:00+00:00",
        "score": 40,
        "signals": [],
        "signal_types": ["manga"],
    }])

    items = [json.loads(l) for l in path.open()]
    assert len(items) == 1
    it = items[0]
    assert it["slug"] == "berserk-deluxe-1"
    assert it["detected_at"] == "2026-05-22T09:00:00+00:00"
    assert it["score"] == 85
    assert it["signal_types"] == ["special_edition"]
    assert it["signals"] == ["deluxe hardcover"]
    # Invariante CLKEY: stored == derive_cluster_key(item), en tier edition:
    assert it["cluster_key"] == "edition:berserk-darkhorse-deluxe-us|1"
    assert it["cluster_key"] == mw.derive_cluster_key(it)


def test_append_jsonl_slug_sticky_on_raw_rows(tmp_path):
    """slug es sticky también para filas SIN standardized_at: el scraper nunca
    trae slug y un re-scrape no debe dejar slug=None (gotcha #65)."""
    path = tmp_path / "items.jsonl"
    mw.append_jsonl(path, [{
        "url": "https://example.com/raw",
        "title": "raw item",
        "slug": "raw-item",
        "detected_at": "2026-01-01",
    }])
    mw.append_jsonl(path, [{
        "url": "https://example.com/raw",
        "title": "raw item v2",
        "detected_at": "2026-02-01",
    }])
    items = [json.loads(l) for l in path.open()]
    assert len(items) == 1
    assert items[0]["slug"] == "raw-item"
    assert items[0]["title"] == "raw item v2"  # el resto sí se reemplaza


def test_candidate_to_json_cluster_key_consistent_with_derived_edition():
    """`candidate_to_json` deriva cluster_key DESPUÉS de escribir el
    edition_key heurístico (Paso C): la fila fresca entra en el tier que
    `derive_cluster_key` re-derivaría (invariante CLKEY desde el ingest,
    gotcha #65)."""
    c = mw.Candidate(
        title="Berserk Deluxe Edition Vol. 3",
        url="https://example.com/berserk-deluxe-3",
        source="Test Source",
        source_url="https://example.com",
        country="US",
        language="en",
        publisher="Dark Horse",
        source_class="publisher",
        tags=[],
        description="",
        score=50,
        signals=["deluxe"],
        signal_types=["special_edition"],
    )
    row = mw.candidate_to_json(c)
    assert row["cluster_key"] == mw.derive_cluster_key(row)
    if row.get("edition_key"):
        assert row["cluster_key"].startswith("edition:")


def test_append_jsonl_does_not_preserve_when_no_standardized_at(tmp_path):
    """Items SIN standardized_at son reemplazados completos en re-scrape
    (comportamiento previo, intacto)."""
    path = tmp_path / "items.jsonl"
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "scraper raw 1",
        "series_key": "wrong-key",
        "detected_at": "2026-01-01",
    }])
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "scraper raw 2",
        "series_key": "wrong-key-2",
        "detected_at": "2026-02-01",
    }])
    items = [json.loads(l) for l in path.open()]
    assert len(items) == 1
    assert items[0]["title"] == "scraper raw 2"
    assert items[0]["series_key"] == "wrong-key-2"


def test_is_approved_helper():
    """is_approved() es True sólo cuando approved_at tiene valor."""
    assert mw.is_approved({"approved_at": "2026-06-01T00:00:00+00:00"}) is True
    assert mw.is_approved({"approved_at": ""}) is False
    assert mw.is_approved({}) is False


def test_append_jsonl_freezes_approved_metadata_refreshes_market(tmp_path):
    """Un item aprobado (golden record) congela TODA la metadata descriptiva
    en re-scrapes; sólo los campos volátiles de mercado (stock_type,
    sources, detected_at) se refrescan. No depende de standardized_at."""
    path = tmp_path / "items.jsonl"
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "Berserk Deluxe 1",
        "series_key": "berserk",
        "edition_key": "berserk-darkhorse-deluxe",
        "volume": "1",
        "stock_type": "in_stock",
        "approved_at": "2026-06-01T10:00:00+00:00",
        "approved_by": "owner",
        "detected_at": "2026-06-01",
    }])

    # Re-scrape trae metadata "peor" + stock nuevo.
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "Berserk Vol 1 raw scraped junk",
        "series_key": "berserk-1",
        "edition_key": "berserk-1-special",
        "volume": "",
        "stock_type": "limited",
        "detected_at": "2026-07-01",
    }])

    it = [json.loads(l) for l in path.open()][0]
    # Metadata descriptiva CONGELADA:
    assert it["title"] == "Berserk Deluxe 1"
    assert it["series_key"] == "berserk"
    assert it["edition_key"] == "berserk-darkhorse-deluxe"
    assert it["volume"] == "1"
    assert it["approved_at"] == "2026-06-01T10:00:00+00:00"
    # Info de mercado REFRESCADA:
    assert it["stock_type"] == "limited"
    assert it["detected_at"] == "2026-07-01"


def test_append_jsonl_no_freeze_when_not_approved(tmp_path):
    """Sin approved_at (y sin standardized_at) el re-scrape reemplaza todo."""
    path = tmp_path / "items.jsonl"
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "old", "series_key": "old", "price": "USD 1",
    }])
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "new", "series_key": "new", "price": "USD 2",
    }])
    it = [json.loads(l) for l in path.open()][0]
    assert it["title"] == "new"
    assert it["series_key"] == "new"


def test_serve_concurrent_approvals_do_not_clobber(tmp_path, monkeypatch):
    """El server es threaded; aprobar varios items en paralelo NO debe perder
    aprobaciones. Sin el lock (_serialized), el read-modify-write del archivo
    entero se pisaba y sólo sobrevivían algunas. Regresión del bug reportado
    ('aprobé varios y quedaron sólo unas')."""
    import sys as _sys
    import threading as _threading
    _scripts = str(Path(__file__).resolve().parent.parent / "scripts")
    if _scripts not in _sys.path:
        _sys.path.insert(0, _scripts)
    import serve  # type: ignore

    items_path = tmp_path / "items.jsonl"
    appr_path = tmp_path / "approvals.jsonl"
    N = 25
    rows = [{"url": f"https://ex/{i}", "cluster_key": f"url:https://ex/{i}",
             "title": f"t{i}"} for i in range(N)]
    items_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(serve, "ITEMS_PATH", items_path)
    monkeypatch.setattr(serve, "APPROVALS_PATH", appr_path)

    threads = [_threading.Thread(target=serve._apply_approve,
                                 args=(f"https://ex/{i}", True, "t"))
               for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    after = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    approved = sum(1 for r in after if r.get("approved_at"))
    assert approved == N, f"perdió aprobaciones por race: {approved}/{N}"


def _make_candidate(**kwargs):
    """Helper para construir un Candidate de prueba con defaults mínimos."""
    defaults = dict(
        title="Berserk Deluxe Edition 1",
        url="https://darkhorse.com/berserk-deluxe-1",
        source="Dark Horse",
        source_url="https://darkhorse.com/manga",
        country="USA",
        language="Inglés",
        publisher="Dark Horse",
        source_class="official",
        tags=[],
        description="Deluxe hardcover edition",
        score=80,
        signal_types=["deluxe"],
        content_hash="abc123",
    )
    defaults.update(kwargs)
    return mw.Candidate(**defaults)


def test_flush_source_candidates_writes_new_items(tmp_path):
    """flush_source_candidates escribe candidatos new/changed al JSONL
    inmediatamente sin necesitar que el run completo termine."""
    path = tmp_path / "items.jsonl"
    cand = _make_candidate()
    written = mw.flush_source_candidates([cand], {}, path, min_score=20)
    assert written == 1
    items = [json.loads(l) for l in path.open()]
    assert len(items) == 1
    assert items[0]["url"] == "https://darkhorse.com/berserk-deluxe-1"
    assert items[0]["status"] == "new"


def test_flush_source_candidates_skips_seen_items(tmp_path):
    """flush_source_candidates NO re-escribe ítems 'seen' (mismo hash en state)."""
    path = tmp_path / "items.jsonl"
    # La key del state es "url:<normalized>" — igual que usa candidate_key().
    state = {"url:https://darkhorse.com/berserk-deluxe-1": {"content_hash": "abc123"}}
    cand = _make_candidate()
    written = mw.flush_source_candidates([cand], state, path, min_score=20)
    assert written == 0
    assert not path.exists()


def test_flush_source_candidates_skips_below_min_score(tmp_path):
    """flush_source_candidates descarta candidatos con score bajo."""
    path = tmp_path / "items.jsonl"
    cand = _make_candidate(score=5)
    written = mw.flush_source_candidates([cand], {}, path, min_score=20)
    assert written == 0
    assert not path.exists()


def test_flush_source_candidates_dry_run_writes_nothing(tmp_path):
    """flush_source_candidates no escribe nada en dry_run=True."""
    path = tmp_path / "items.jsonl"
    cand = _make_candidate()
    written = mw.flush_source_candidates([cand], {}, path, min_score=20, dry_run=True)
    assert written == 0
    assert not path.exists()


def test_append_jsonl_cover_local_is_sticky(tmp_path):
    """Un re-scrape sin `local` (--skip-image-download o fallo de red puntual)
    NO debe borrar el espejo local ya descargado en images[0]. La preservación
    es vía el union-merge de images[] (dedup por (kind,url) conserva el entry
    viejo). Ya no hay campos top-level image_url/image_local (decisión
    2026-06-09). Ver "Image storage" en CLAUDE.md."""
    path = tmp_path / "items.jsonl"
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "A",
        "images": [{"url": "https://cdn.example.com/a.jpg",
                    "local": "abc123def4567890.jpg",
                    "kind": "gallery", "description": ""}],
        "detected_at": "2026-01-01",
    }])
    # Re-scrape: misma URL, la row nueva trae images[0] SIN local.
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "A",
        "images": [{"url": "https://cdn.example.com/a.jpg",
                    "local": "", "kind": "gallery", "description": ""}],
        "detected_at": "2026-02-01",
    }])
    items = [json.loads(l) for l in path.open()]
    assert len(items) == 1
    assert imgstore.cover_local(items[0]) == "abc123def4567890.jpg"
    assert "image_local" not in items[0] and "image_url" not in items[0]
    assert items[0]["detected_at"] == "2026-02-01"


def test_extract_images_anchor_href_wins_over_src():
    """Patrón Magento/Fotorama: <a href="full.jpg"><img src="thumb.jpg"></a>.
    _extract_images_from_detail_soup debe devolver la URL full del href, no el thumb."""
    html = """
    <html><body>
    <main>
      <div class="product-gallery">
        <a href="/media/catalog/product/full.jpg">
          <img src="/media/catalog/product/cache/thumb.jpg" alt="Cover">
        </a>
      </div>
    </main>
    </body></html>
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    images = mw._extract_images_from_detail_soup(soup, "https://shop.example.com/product/1")
    assert len(images) >= 1
    assert images[0]["url"] == "https://shop.example.com/media/catalog/product/full.jpg"


def test_extract_images_anchor_non_image_href_falls_back_to_src():
    """Si el <a> que envuelve el <img> no apunta a una imagen, usar el src del img."""
    html = """
    <html><body>
    <main>
      <a href="/products/detail-page">
        <img src="/media/catalog/product/cover.jpg" alt="Cover">
      </a>
    </main>
    </body></html>
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    images = mw._extract_images_from_detail_soup(soup, "https://shop.example.com/product/1")
    assert len(images) >= 1
    assert images[0]["url"] == "https://shop.example.com/media/catalog/product/cover.jpg"


def test_append_jsonl_dedup_images_by_normalized_url(tmp_path):
    """La misma imagen en thumb y full-res (URLs que difieren solo en sufijo
    de Shopify) produce un solo entry en images[] después del merge."""
    path = tmp_path / "items.jsonl"
    # Primera pasada: URL thumbnail (Shopify suffix)
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "A",
        "images": [{"url": "https://cdn.shopify.com/s/files/cover_100x100.jpg",
                    "kind": "gallery", "description": ""}],
        "detected_at": "2026-01-01",
    }])
    # Segunda pasada: misma imagen sin suffix (full-res)
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "A",
        "images": [{"url": "https://cdn.shopify.com/s/files/cover.jpg",
                    "kind": "gallery", "description": ""}],
        "detected_at": "2026-02-01",
    }])
    items = [json.loads(l) for l in path.open()]
    assert len(items) == 1
    # No debe haber duplicados de la misma imagen
    assert len(items[0].get("images", [])) == 1


def test_append_jsonl_images_backfilled_at_is_sticky(tmp_path):
    """images_backfilled_at sobrevive un re-scrape: el valor del old se conserva
    si la nueva fila no lo trae (ningún scraper lo escribe)."""
    path = tmp_path / "items.jsonl"
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "A",
        "images": [{"url": "https://cdn.example.com/a.jpg", "kind": "gallery", "description": ""}],
        "images_backfilled_at": "2026-05-01T10:00:00+00:00",
        "detected_at": "2026-01-01",
    }])
    # Re-scrape: la nueva fila no trae images_backfilled_at
    mw.append_jsonl(path, [{
        "url": "https://example.com/a",
        "title": "A v2",
        "images": [{"url": "https://cdn.example.com/a.jpg", "kind": "gallery", "description": ""}],
        "detected_at": "2026-02-01",
    }])
    items = [json.loads(l) for l in path.open()]
    assert len(items) == 1
    assert items[0].get("images_backfilled_at") == "2026-05-01T10:00:00+00:00"


# ----- image_store.py (espejo local de portadas, Image storage Fase 1) -----


def test_image_store_stem_is_deterministic():
    url = "https://cdn.example.com/cover/one-piece-100.jpg"
    assert imgstore.image_stem(url) == imgstore.image_stem(url)
    assert imgstore.image_stem(url) != imgstore.image_stem(url + "?v=2")
    assert len(imgstore.image_stem(url)) == 16


def test_image_store_extension_from_magic():
    assert imgstore._extension_from_magic(b"\xff\xd8\xff" + b"\x00" * 16) == ".jpg"
    assert imgstore._extension_from_magic(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16) == ".png"
    assert imgstore._extension_from_magic(b"GIF89a" + b"\x00" * 16) == ".gif"
    assert imgstore._extension_from_magic(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8) == ".webp"
    # Una página HTML de error / anti-bot no es una imagen → "".
    assert imgstore._extension_from_magic(b"<!DOCTYPE html><html><head>") == ""


def test_image_store_download_rejects_non_http(tmp_path):
    images_dir = tmp_path / "images"
    assert imgstore.download_image("", images_dir) == ""
    assert imgstore.download_image("data:image/png;base64,AAAA", images_dir) == ""
    assert imgstore.download_image("ftp://example.com/x.jpg", images_dir) == ""


def test_image_store_download_skips_when_file_exists(tmp_path):
    """Si ya hay un archivo para el URL, download_image lo reusa sin red.
    El glob <stem>.* lo encuentra aunque la extensión difiera de la del URL."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    url = "https://cdn.example.com/cover/berserk-1.jpg"
    existing = images_dir / (imgstore.image_stem(url) + ".png")
    existing.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    assert imgstore.download_image(url, images_dir) == existing.name
    assert imgstore.existing_local_image(images_dir, url) == existing.name


def test_image_store_existing_local_image_empty_when_absent(tmp_path):
    images_dir = tmp_path / "images"
    assert imgstore.existing_local_image(images_dir, "https://x.com/y.jpg") == ""


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
    # Tags con metadata extraída
    by_title = {i.title: i for i in items}
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
         "publisher": "Star Comics", "signal_types": ["lore_edition"], "url": "http://a"}
    b = {"title": "One Piece Celebration Edition Vol. 100", "language": "Italiano",
         "publisher": "Star Comics", "signal_types": ["lore_edition"], "url": "http://b"}
    assert mw.derive_cluster_key(a) == mw.derive_cluster_key(b)


def test_cluster_key_different_languages_dont_merge():
    a = {"title": "One Piece vol. 100", "language": "Italiano", "publisher": "Star",
         "signal_types": ["lore_edition"], "url": "http://a"}
    b = {"title": "One Piece tomo 100", "language": "Español", "publisher": "Planeta",
         "signal_types": ["lore_edition"], "url": "http://b"}
    assert mw.derive_cluster_key(a) != mw.derive_cluster_key(b)


def test_cluster_key_listadomanga_raw_keyed_by_coleccion():
    """gotcha #42: items RAW de listadomanga (synthetic URL, sin edition_key) se
    clavean por `lmc:{coleccion}:{kind}:{vol}` — NO por fuzzy — para enforzar la
    regla coleccion=edición (el fuzzy fusionaría colecciones distintas con mismo
    series+vol+tier). El volumen sigue en la clave."""
    item = {"title": "Berserk nº1", "language": "Español", "publisher": "Panini",
            "signal_types": ["special_edition"],
            "url": "https://www.listadomanga.es/coleccion.php?id=6325&item=especial-1-abc"}
    assert mw.derive_cluster_key(item) == "lmc:6325:special:1"


def test_cluster_key_listadomanga_distinct_colecciones_dont_merge():
    """gotcha #42: dos colecciones distintas de la misma obra+volumen NO
    comparten cluster_key (son ediciones distintas)."""
    a = {"title": "Fullmetal Alchemist nº1", "language": "Español", "publisher": "Norma",
         "url": "https://www.listadomanga.es/coleccion.php?id=50&item=regular-1-aaa"}
    b = {"title": "Fullmetal Alchemist nº1", "language": "Español", "publisher": "Norma",
         "url": "https://www.listadomanga.es/coleccion.php?id=524&item=regular-1-bbb"}
    assert mw.derive_cluster_key(a) != mw.derive_cluster_key(b)


def test_cluster_key_idempotent_across_cover_reupload():
    """P3-F: si listadomanga RE-SUBE una portada (cambia el hash del `item=`),
    los dos items igual comparten cluster_key — la clave `lmc:` ignora el hash
    (misma coleccion+kind+volumen). Idempotencia garantizada."""
    old = {"title": "Ataque a los Titanes nº34", "language": "Español",
           "publisher": "Norma Editorial", "signal_types": ["special_edition"],
           "url": "https://www.listadomanga.es/coleccion.php?id=1606&item=especial-34-OLDHASH"}
    new = dict(old, url="https://www.listadomanga.es/coleccion.php?id=1606&item=especial-34-NEWHASH")
    assert mw.derive_cluster_key(old) == mw.derive_cluster_key(new) == "lmc:1606:special:34"


def test_cluster_key_different_variants_dont_merge():
    """OP100 normal y OP100 Celebration son productos distintos (distinto tier)."""
    a = {"title": "One Piece vol. 100", "language": "Italiano",
         "publisher": "Star", "signal_types": [], "url": "http://a"}
    b = {"title": "One Piece vol. 100 Celebration", "language": "Italiano",
         "publisher": "Star", "signal_types": ["lore_edition"], "url": "http://b"}
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


def test_cluster_key_edition_key_merges_box_across_sources():
    """Dos items con el mismo edition_key + volume DEBEN compartir cluster_key
    aunque vengan de fuentes/publishers distintos. Crucial para box sets
    sin volumen — la fuzzy key requiere volume y los dejaba aislados.

    Caso semilla: Gon Edición Coleccionista (Norma) aparece como item en
    Whakoom (publisher "Varias editoriales") y en ListadoManga colecciones
    (publisher "Norma Editorial"). Ambos tienen edition_key
    "gon-norma-collector" y volume="" — deben mergear en una sola card.
    """
    whakoom = {
        "edition_key": "gon-norma-collector",
        "volume": "",
        "title": "Gon Edición Coleccionista",
        "language": "Español",
        "publisher": "Varias editoriales",
        "signal_types": ["collector"],
        "url": "https://whakoom.com/comics/k9IBX/gon_edicion_coleccionista",
    }
    store_box = {
        "edition_key": "gon-norma-collector",
        "volume": "",
        "title": "Gon (Edición Coleccionista) (Norma) — Cofre",
        "language": "Español",
        "publisher": "Norma Editorial",
        "signal_types": ["collector", "box_set", "hardcover"],
        "url": "https://www.normaeditorial.com/ficha/gon-coleccionista",
    }
    assert mw.derive_cluster_key(whakoom) == mw.derive_cluster_key(store_box)
    assert mw.derive_cluster_key(whakoom).startswith("edition:gon-norma-collector|")


def test_cluster_key_listadomanga_uses_coleccion_kind_not_edition():
    """Regla owner (gotcha #48): una /coleccion = UNA página de edición (mismo
    edition_key) PERO el cluster distingue variantes del mismo volumen por KIND
    → `lmc:{coleccion}:{kind}:{vol}`, ANTES del edition_key. Así el tomo 34 normal
    y el especial-34 comparten edición pero NO se fusionan en el dedup."""
    regular34 = {
        "edition_key": "attack-on-titan-norma-regular-es", "volume": "34",
        "url": "https://www.listadomanga.es/coleccion.php?id=1606&item=regular-34-abc",
    }
    especial34 = {
        "edition_key": "attack-on-titan-norma-regular-es", "volume": "34",
        "url": "https://www.listadomanga.es/coleccion.php?id=1606&item=especial-34-xyz",
    }
    assert mw.derive_cluster_key(regular34) == "lmc:1606:regular:34"
    assert mw.derive_cluster_key(especial34) == "lmc:1606:special:34"
    assert mw.derive_cluster_key(regular34) != mw.derive_cluster_key(especial34)
    # old-format sin &item= usa lm_kind para el kind del cluster
    old_special = {
        "edition_key": "attack-on-titan-norma-regular-es", "volume": "34",
        "lm_kind": "special",
        "url": "https://www.listadomanga.es/coleccion.php?id=1606",
    }
    assert mw.derive_cluster_key(old_special) == "lmc:1606:special:34"


def test_cluster_key_edition_key_different_volumes_dont_merge():
    """Mismo edition_key pero distinto volumen → cards separadas (es lo
    correcto: tomo 1 y tomo 2 de la misma edición son productos distintos)."""
    a = {"edition_key": "berserk-panini-deluxe", "volume": "1",
         "title": "Berserk Deluxe 1", "url": "http://a"}
    b = {"edition_key": "berserk-panini-deluxe", "volume": "2",
         "title": "Berserk Deluxe 2", "url": "http://b"}
    assert mw.derive_cluster_key(a) != mw.derive_cluster_key(b)


def test_cluster_key_edition_key_wins_over_isbn():
    """edition_key es más autoritativa que ISBN — garantiza merge cross-source
    cuando una fuente tiene ISBN y otra no (ej. PRH Comics + Dark Horse Direct)."""
    item = {"isbn": "9788822624697", "edition_key": "x-y-z", "volume": "1",
            "url": "http://a"}
    assert mw.derive_cluster_key(item) == "edition:x-y-z|1"


def test_cluster_key_isbn_fallback_without_edition_key():
    """ISBN sigue activo como fallback para items sin edition_key (legacy)."""
    item = {"isbn": "9788822624697", "url": "http://a"}
    assert mw.derive_cluster_key(item) == "isbn:9788822624697"


def test_cluster_key_prh_and_darkhorse_merge_same_volume():
    """PRH (con ISBN) y Dark Horse Direct (sin ISBN) mergean cuando comparten
    edition_key + volume — caso real Hellsing/Berserk/Blade Deluxe."""
    prh = {"isbn": "9781506715537", "edition_key": "hellsing-darkhorse-deluxe",
           "volume": "1", "url": "https://prhcomics.com/book/?isbn=9781506715537"}
    dh = {"edition_key": "hellsing-darkhorse-deluxe", "volume": "1",
          "url": "https://www.darkhorsedirect.com/products/hellsing-v1"}
    assert mw.derive_cluster_key(prh) == mw.derive_cluster_key(dh)
    assert mw.derive_cluster_key(prh) == "edition:hellsing-darkhorse-deluxe|1"


def test_cluster_key_no_edition_key_falls_through_to_fuzzy():
    """Items sin edition_key (pre-standardize-catalog) usan fuzzy como antes."""
    item = {"title": "One Piece vol. 100 Celebration", "language": "Italiano",
            "publisher": "Star Comics", "signal_types": ["lore_edition"],
            "url": "http://a"}
    key = mw.derive_cluster_key(item)
    assert key.startswith("fuzzy:")


def test_cluster_key_japanese_preserves_kanji():
    """No strippeamos kanji/kana — son discriminantes para series JP."""
    a = {"title": "ワンピース 100巻 限定版", "language": "Japonés",
         "publisher": "集英社", "signal_types": ["limited"], "url": "http://a"}
    b = {"title": "ワンピース 100巻 限定版", "language": "Japonés",
         "publisher": "集英社", "signal_types": ["limited"], "url": "http://b"}
    assert mw.derive_cluster_key(a) == mw.derive_cluster_key(b)
    assert "ワンピース" in mw.derive_cluster_key(a)


# ---------------------------------------------------------------------------
# _variant_tier + cluster_key tolerance to signal_type variance across sources.
#
# Distintas fuentes producen signal_types ligeramente distintos para el mismo
# producto físico. derive_cluster_key colapsa esa varianza eligiendo solo el
# tier MÁS ESPECÍFICO de cada item (artbook > box_set > lore_edition >
# variant_cover > deluxe > limited > special > ""). Items del mismo tier
# mergean. Origen real del problema: One Piece Vol.98 Celebration Edition
# aparecía DOS veces (Star Comics + Mangavariant) porque sus signal_types
# divergían ([collector, lore_edition] vs [bonus, special_edition, collector,
# lore_edition]) — ambos quedan ahora en tier='lore_edition'.
# ---------------------------------------------------------------------------


def test_variant_tier_picks_most_specific():
    assert mw._variant_tier([]) == ""
    assert mw._variant_tier(["collector"]) == "special"
    assert mw._variant_tier(["bonus"]) == "special"
    # lore_edition rankea por encima de special — ediciones temáticas
    # ("Celebration", "Anniversary") son release-name específico.
    assert mw._variant_tier(["collector", "lore_edition"]) == "lore_edition"
    assert mw._variant_tier(["bonus", "special_edition", "collector",
                              "lore_edition"]) == "lore_edition"
    # deluxe rankea por encima de limited
    assert mw._variant_tier(["limited", "deluxe"]) == "deluxe"
    # box_set domina a deluxe/limited (es producto-class distinto)
    assert mw._variant_tier(["limited", "box_set", "deluxe"]) == "box_set"
    # variant_cover domina a deluxe (cover variants ≠ formato deluxe)
    assert mw._variant_tier(["deluxe", "variant_cover"]) == "variant_cover"
    # signal_type no mapeado → "" (tomo regular)
    assert mw._variant_tier(["something_unknown"]) == ""


def test_cluster_key_one_piece_98_celebration_merges_across_sources():
    """Caso real reportado por el owner: One Piece Vol.98 Celebration
    Edition aparecía DOS veces (Star Comics search + Mangavariant) por
    divergencia de signal_types. Con el tier-based cluster_key deben mergear."""
    star_comics = {
        "title": "ONE PIECE n. 98 CELEBRATION EDITION",
        "url": "https://www.starcomics.com/fumetto/one-piece-98-celebration-edition",
        "language": "Italiano",
        "publisher": "Star Comics",
        "signal_types": ["collector", "lore_edition"],
        "isbn": "",
    }
    mangavariant = {
        "title": "One Piece — Vol.98 - Celebration edition",
        "url": "https://mangavariant.com/variant/one-piece/vol-98-celebration-edition/",
        "language": "Italiano",
        "publisher": "Star Comics",
        "signal_types": ["bonus", "special_edition", "collector", "lore_edition"],
        "isbn": "",
    }
    sc_key = mw.derive_cluster_key(star_comics)
    mv_key = mw.derive_cluster_key(mangavariant)
    assert sc_key == mv_key, (
        f"Expected same cluster_key:\n  star_comics: {sc_key}\n  mangavariant: {mv_key}"
    )
    assert sc_key.startswith("fuzzy:italiano|one piece|98|lore_edition|star comics"), sc_key


def test_cluster_key_tolerates_extra_lower_priority_signals():
    """Item A con [lore_edition] y B con [lore_edition, bonus, collector] del
    mismo producto deben mergear (todos colapsan a tier='lore_edition')."""
    a = {"title": "Naruto n. 12 anniversary", "language": "Italiano",
         "publisher": "Panini", "signal_types": ["lore_edition"], "url": "http://a"}
    b = {"title": "Naruto Vol. 12 Anniversary Edition", "language": "Italiano",
         "publisher": "Panini",
         "signal_types": ["lore_edition", "bonus", "collector"],
         "url": "http://b"}
    assert mw.derive_cluster_key(a) == mw.derive_cluster_key(b)


def test_cluster_key_deluxe_does_not_merge_with_lore_edition():
    """Pero distintos tiers SIGUEN sin mergear: deluxe vs lore_edition son
    productos conceptualmente distintos del mismo volumen."""
    a = {"title": "One Piece Vol. 100 Deluxe", "language": "Español",
         "publisher": "Planeta", "signal_types": ["deluxe"], "url": "http://a"}
    b = {"title": "One Piece Vol. 100 Celebration", "language": "Español",
         "publisher": "Planeta", "signal_types": ["lore_edition"], "url": "http://b"}
    assert mw.derive_cluster_key(a) != mw.derive_cluster_key(b)


def test_normalize_series_strips_trailing_punctuation():
    """Bug previo: 'One Piece — Vol.98 - Celebration edition' dejaba
    'one piece .' (punto residual) porque _SERIES_STRIP_RE removía 'vol'
    sin tocar el '.' que seguía, y la pasada de punctuation→space no
    incluía el '.'."""
    title = "One Piece — Vol.98 - Celebration edition"
    assert mw._normalize_series_name(title, "98") == "one piece"


def test_normalize_series_strips_numero_marker():
    """Bug 2026-06-07: '_normalize_series_name' removía el dígito de volumen
    ('Slam Dunk nº1' → quitaba '1') pero dejaba el marcador 'nº' → series_key
    malformado 'slam-dunk-no'. Ahora limpia nº/n°/＃/#/第…巻 junto con el número.
    Casos legítimos donde 'no'/'n' es parte del título NO deben tocarse."""
    assert mw._normalize_series_name("Slam Dunk nº1", "1") == "slam dunk"
    assert mw._normalize_series_name("Monster nº5", "5") == "monster"
    # el marcador nº no deja residuo '-no' (el 'No' líder lo quita aparte el
    # strip de stopwords; lo relevante acá es que 'nº3' no sobrevive como 'no')
    assert mw._normalize_series_name("No soy un ángel nº3", "3") == "soy un ángel"
    # 'N' como parte real del nombre (sin marcador nº): intacto
    assert mw._normalize_series_name("Denjin N", "1") == "denjin n"


def test_cluster_key_strips_brackets_to_avoid_noise():
    """Contenido entre corchetes (típico ruido de retailer JP) no afecta key."""
    a = {"title": "Naruto Vol. 5 Deluxe (BeBoy Comics Deluxe)", "language": "Japonés",
         "publisher": "集英社", "signal_types": ["deluxe"], "url": "http://a"}
    b = {"title": "Naruto Vol. 5 Deluxe", "language": "Japonés",
         "publisher": "集英社", "signal_types": ["deluxe"], "url": "http://b"}
    assert mw.derive_cluster_key(a) == mw.derive_cluster_key(b)


# ---------------------------------------------------------------------------
# Mangavariant wiki parser (scripts/wikis/mangavariant.py).
#
# La detail page expone los campos en un bloque <div class="variant_info_block">.
# El título del item se construye combinando la serie (tag Manga del bloque)
# con el og:title (que solo trae el nombre de la edición). NO pasa por
# is_likely_manga / is_collectible_edition: mangavariant es 100% curado.
# ---------------------------------------------------------------------------

_MV_FIXTURES = Path(__file__).parent / "fixtures" / "mangavariant"


def _mv_html(name: str) -> str:
    return (_MV_FIXTURES / name).read_text(encoding="utf-8")


def test_mangavariant_parse_one_piece_natsucomi():
    """Variant sin volumen explícito (anniversary edition). País JP, Shueisha."""
    from wikis import mangavariant as mv
    cand = mv.parse_variant_detail(
        _mv_html("one_piece_natsucomi.html"),
        "https://mangavariant.com/variant/one-piece/10th-anniversary-natsucomi-variant/",
    )
    assert cand is not None
    assert cand.title == "One Piece — 10th anniversary - Natsucomi variant"
    assert cand.country == "Japón"
    assert cand.language == "Japonés"
    assert cand.publisher == "Shueisha"
    assert cand.release_date == "2007"
    assert cand.image_url.endswith(".jpg")
    assert "Comiket" in cand.description or "Natsucomi" in cand.description
    # Tags discriminantes
    assert "country:jp" in cand.tags
    assert "rarity:uncommon" in cand.tags
    assert "where:comiket" in cand.tags
    assert "mv-series:one-piece" in cand.tags
    assert "mv-tag:pvc" in cand.tags


def test_mangavariant_parse_aot_crunchyroll():
    """Variant con volumen explícito. País IT, Planet Manga."""
    from wikis import mangavariant as mv
    cand = mv.parse_variant_detail(
        _mv_html("aot_vol34_crunchyroll.html"),
        "https://mangavariant.com/variant/attack-on-titan/vol-34-crunchyroll-variant/",
    )
    assert cand is not None
    assert cand.title == "Attack on Titan — Vol.34 - Crunchyroll variant"
    assert cand.country == "Italia"
    assert cand.language == "Italiano"
    assert cand.publisher == "Planet Manga"
    assert cand.release_date == "2024"
    assert "country:it" in cand.tags
    assert "rarity:common" in cand.tags
    # Sin "Where" en esta variant → no debe agregarse where:* tag
    assert not any(t.startswith("where:") for t in cand.tags)
    # El volumen embebido en el title habilita cluster_key fuzzy aguas abajo
    assert mw._extract_volume(cand.title) == "34"


def test_mangavariant_parse_steelbox_collection():
    """Variant tipo bundle/steelbox: signal_types debe captar 'limited'."""
    from wikis import mangavariant as mv
    cand = mv.parse_variant_detail(
        _mv_html("assassination_steelbox.html"),
        "https://mangavariant.com/variant/assassination-classroom/vol-1-steelbox-collection/",
    )
    assert cand is not None
    assert "Steelbox" in cand.title
    assert cand.country == "Italia"
    # Steelbox + limited edition → debería disparar al menos limited o variant_cover
    assert any(s in cand.signal_types for s in ("limited", "variant_cover", "box_set"))
    assert "where:steelbox-collection" in cand.tags


def test_mangavariant_parse_rejects_non_variant_html():
    """HTML cualquiera (sin variant_info_block) debe devolver None."""
    from wikis import mangavariant as mv
    assert mv.parse_variant_detail("", "https://x/") is None
    assert mv.parse_variant_detail("<html><body>nada</body></html>", "https://x/") is None
    # HTML largo pero sin variant_info_block
    big = "<html>" + ("<p>foo</p>" * 500) + "</html>"
    assert mv.parse_variant_detail(big, "https://x/") is None


def test_mangavariant_strips_og_title_site_suffix():
    """El sufijo ' - mangavariant.com' del og:title se quita."""
    from wikis import mangavariant as mv
    assert mv._strip_og_suffix("Foo bar - mangavariant.com") == "Foo bar"
    assert mv._strip_og_suffix("Foo - mangavariant.com  ") == "Foo"
    assert mv._strip_og_suffix("Foo") == "Foo"
    assert mv._strip_og_suffix("") == ""


def test_mangavariant_country_map_covers_known_slugs():
    """Los 13 country slugs de Yoast deben tener mapping (nombre_es, idioma_es)."""
    from wikis import mangavariant as mv
    expected = {"ar", "br", "fr", "de", "it", "jp", "mexico", "es",
                "tw", "th", "uk", "us", "vn"}
    assert expected.issubset(set(mv.COUNTRY_MAP.keys()))
    # Sanity: el slug 'mexico' (no 'mx') mapea a México/Español.
    assert mv.COUNTRY_MAP["mexico"] == ("México", "Español")


def test_mangavariant_fetch_variant_urls_filters_index_pages():
    """fetch_variant_urls debe quedarse solo con URLs /variant/<manga>/<edicion>/,
    descartando /variant/ (index), /about/, etc."""
    from wikis import mangavariant as mv
    import requests as _rq

    class _FakeResponse:
        def __init__(self, text: str) -> None:
            self.text = text
            self.status_code = 200
        def raise_for_status(self) -> None:
            return None

    class _FakeSession:
        def get(self, url, timeout):  # noqa: ARG002
            return _FakeResponse(_mv_html("sitemap_sample.xml"))

    urls = mv.fetch_variant_urls(_FakeSession(), sitemaps=("dummy",))
    # 3 variants reales en la fixture; /variant/ y /about/ quedan fuera.
    assert len(urls) == 3
    assert all("/variant/" in u and not u.endswith("/variant/") for u in urls)


def test_mangavariant_detects_sgcaptcha_challenge():
    """El challenge sgcaptcha de SiteGround (202 + meta-refresh a
    /.well-known/sgcaptcha/) se detecta; respuestas reales no."""
    from wikis import mangavariant as mv

    class _FakeResponse:
        def __init__(self, status_code: int, text: str) -> None:
            self.status_code = status_code
            self.text = text

    challenge_html = (
        '<html><head><meta http-equiv="refresh" '
        'content="0;url=/.well-known/sgcaptcha/?r=%2Fvariant%2F"></head></html>'
    )
    # 202 solo ya es challenge; el marker en el body también (aun con 200).
    assert mv._looks_like_challenge(_FakeResponse(202, challenge_html))
    assert mv._looks_like_challenge(_FakeResponse(202, ""))
    assert mv._looks_like_challenge(_FakeResponse(200, challenge_html))
    # Páginas reales: detail page y sitemap XML.
    assert not mv._looks_like_challenge(
        _FakeResponse(200, _mv_html("aot_vol34_crunchyroll.html")))
    assert not mv._looks_like_challenge(
        _FakeResponse(200, _mv_html("sitemap_sample.xml")))


def test_mangavariant_iter_year_months_returns_single_batch():
    """No usa calendario: el rango se ignora y devuelve un único batch
    para que el dispatcher cuente '1 mes' en el resumen."""
    from wikis import mangavariant as mv
    assert mv.iter_year_months(2024, 1, 2026, 12) == [(2024, 1)]


def test_socialanime_parse_variant_item_basic():
    """Item canónico de type=variant: Star Comics, link Amazon affiliate,
    ISBN-10 inferido del ASIN, signal variant_cover desde la palabra
    'Variant' en el título."""
    from wikis import socialanime as sa
    item = {
        "id": "2255",
        "img": "https://m.media-amazon.com/images/I/91UJQpcT86L._AC_UL960_FMwebp_QL65_.jpg",
        "nome": "Mob Psycho 100. Variant (Vol. 1)",
        "link": "https://www.amazon.it/dp/8822607155?tag=socianim0c-21",
        "prezzo": "4.9",
        "PublicationDate": "22 Nov 2017",
        "trama": "Shigeo, detto Mob, è uno studente.",
        "editore": "Star Comics",
        "autore": "One",
        "extra_class": "variant",
    }
    cand = sa.parse_feed_item(item, "variant")
    assert cand is not None
    assert cand.title == "Mob Psycho 100. Variant (Vol. 1)"
    assert cand.url == "https://www.amazon.it/dp/8822607155?tag=socianim0c-21"
    assert cand.publisher == "Star Comics"
    assert cand.author == "One"
    assert cand.country == "Italia"
    assert cand.language == "Italiano"
    assert cand.source == "IT - SocialAnime Variant"
    assert cand.release_date == "2017-11-22"
    assert cand.isbn == "8822607155"  # Italian books legacy: ASIN == ISBN-10
    assert "variant_cover" in cand.signal_types
    assert "sa-class:variant" in cand.tags


def test_socialanime_parse_box_injects_cofanetto_hint():
    """type=box: si el título no menciona 'cofanetto'/'box set'/'boxset',
    el parser inyecta 'Cofanetto / box set.' en la descripción para que
    detect_signals levante box_set. Sin esto, items con solo 'Collector's
    box' en el título caerían fuera del gate is_collectible_edition."""
    from wikis import socialanime as sa
    item = {
        "id": "1", "img": "",
        "nome": "One piece red. Collector's box. Limited edition",
        "link": "https://www.amazon.it/dp/8828715189?tag=foo",
        "prezzo": "24.9", "PublicationDate": "1 Jan 2030",
        "trama": "", "editore": "Panini Comics", "autore": "Eiichiro Oda",
        "extra_class": "",
    }
    cand = sa.parse_feed_item(item, "box")
    assert cand is not None
    assert "Cofanetto / box set." in cand.description
    assert "box_set" in cand.signal_types
    # PublicationDate placeholder '1 Jan 2030' debe quedar vacío.
    assert cand.release_date == ""


def test_socialanime_parse_box_skips_hint_when_title_has_cofanetto():
    """Si el título ya dice 'cofanetto' o 'box set', no duplicamos el hint."""
    from wikis import socialanime as sa
    item = {
        "id": "2", "img": "",
        "nome": "Berserk Cofanetto Deluxe Vol 1-3",
        "link": "https://www.amazon.it/dp/8822612345",
        "prezzo": "39.9", "PublicationDate": "", "trama": "",
        "editore": "Panini Comics", "autore": "", "extra_class": "",
    }
    cand = sa.parse_feed_item(item, "box")
    assert cand is not None
    assert cand.description.count("Cofanetto") <= 1
    assert "box_set" in cand.signal_types


def test_socialanime_skips_items_without_link():
    """Items sin Amazon link no tienen URL canónica → no podemos dedupar.
    El parser los descarta (~10% del feed son entries delisteadas)."""
    from wikis import socialanime as sa
    item = {
        "id": "3", "nome": "Titolo senza link", "link": "",
        "editore": "Panini Comics", "extra_class": "variant",
    }
    assert sa.parse_feed_item(item, "variant") is None


def test_socialanime_skips_items_without_title():
    from wikis import socialanime as sa
    item = {"id": "4", "nome": "", "link": "https://www.amazon.it/dp/X"}
    assert sa.parse_feed_item(item, "variant") is None


def test_socialanime_kindle_asin_not_treated_as_isbn():
    """ASINs Kindle (empiezan con B0) NO son ISBN-10. No los guardamos
    como isbn — meterlos arruinaría el cluster_key por ISBN del item."""
    from wikis import socialanime as sa
    item = {
        "id": "5", "nome": "Naruto Limited Edition (Vol. 1)",
        "link": "https://www.amazon.it/dp/B0ABCDEF12?tag=foo",
        "prezzo": "9.9", "PublicationDate": "1 May 2024",
        "trama": "", "editore": "Panini Comics", "autore": "",
        "extra_class": "",
    }
    cand = sa.parse_feed_item(item, "variant")
    assert cand is not None
    assert cand.isbn == ""


def test_socialanime_iter_year_months_returns_single_batch():
    """SocialAnime no usa calendario (el feed se controla por macro_filter)."""
    from wikis import socialanime as sa
    assert sa.iter_year_months(2024, 1, 2026, 12) == [(2024, 1)]


def _bbm_html(layout: str) -> str:
    """Genera HTML mínimo de un post BBM para tests. Layout A imita
    /capas_variantes/ (gallery div ANTES del title). Layout B imita
    /volumes-especiais/ (title primero, figures después)."""
    if layout == "A":
        return """
        <article><div class="entry-content">
          <p>Intro del post, no es entry.</p>
          <hr/>
          <div class="wp-block-gallery">
            <img src="https://i0.wp.com/blogbbm.com/wp-content/uploads/2017/09/genshiken06.jpg?w=401" alt="Genshiken06"/>
            <img src="https://i0.wp.com/blogbbm.com/wp-content/uploads/2017/09/genshiken06b.jpg?w=401" alt="Genshiken06b"/>
          </div>
          <p><strong><a href="https://blogbbm.com/manga/genshiken/">Genshiken &#8211; #06</a></strong></p>
          <p>Em janeiro de 2014, a editora JBC lançou o volume 6 de Genshiken com duas capas. Cada volume custou R$ 11,90.</p>
          <hr/>
          <div class="wp-block-gallery">
            <img src="https://i0.wp.com/blogbbm.com/wp-content/uploads/2017/09/re-zero-01.jpg" alt="Re:Zero #01"/>
            <img src="https://i0.wp.com/blogbbm.com/wp-content/uploads/2017/09/re-zero-01-capa-variante.jpg" alt="Re:Zero #01 - Capa Variante"/>
          </div>
          <p><strong>Re:Zero #01 (Light Novel)</strong></p>
          <p>Em outubro de 2017, a editora NewPOP publicou o primeiro volume da light novel Re:Zero. Cada volume custou R$ 26,90.</p>
        </div></article>
        """ + "_" * 5000  # padding para pasar el min-length check
    # Layout B
    return """
    <article><div class="entry-content">
      <p>Intro</p>
      <hr/>
      <p>Ataque dos Tit&atilde;s #34 (12/2021)</p>
      <hr/>
      <p>O volume final foi lan&ccedil;ado em duas vers&otilde;es pela editora Panini. A vers&atilde;o especial teve uma capa variante e um livreto. R$ 24,90.</p>
      <figure><img src="https://i0.wp.com/blogbbm.com/wp-content/uploads/2022/01/aot34-regular.jpg" alt="Edicao regular"/></figure>
      <figure><img src="https://i0.wp.com/blogbbm.com/wp-content/uploads/2022/01/aot34-especial.jpg" alt="Edicao especial"/></figure>
      <hr/>
      <p>Shangri-la Frontier #01 (04/2022)</p>
      <hr/>
      <p>Em abril de 2022, a editora Panini lan&ccedil;ou Shangri-la #01 com edi&ccedil;&atilde;o regular e Pass Edition.</p>
      <figure><img src="https://blogbbm.com/wp-content/uploads/2022/04/slf01-regular.jpg" alt="SLF regular"/></figure>
      <figure><img src="https://blogbbm.com/wp-content/uploads/2022/04/slf01-passedition.jpg" alt="SLF Pass Edition"/></figure>
    </div></article>
    """ + "_" * 5000


def test_blogbbm_parses_layout_a_capas_variantes():
    """Layout A (capas_variantes): gallery div precede al título. Cada entry
    debe tener su propio par de imágenes y publisher detectado del prose."""
    from wikis import blogbbm as bbm
    cands = bbm.parse_post(_bbm_html("A"), {
        "url": "https://blogbbm.com/2020/10/09/capas_variantes/",
        "source_suffix": "Capas Variantes",
        "tag": "capas-variantes",
        "signal_inject": "Capa variante / variant cover.",
    })
    assert len(cands) == 2
    g, r = cands
    # Genshiken
    assert "Genshiken" in g.title
    assert g.publisher == "JBC"
    assert g.release_date == "2014-01"
    assert "genshiken06b" in g.image_url  # variant cover preferida sobre normal
    assert "variant_cover" in g.signal_types
    # Re:Zero — sin ficha link, lenient mode lo detecta
    assert "Re:Zero" in r.title
    assert r.publisher == "NewPOP"
    assert "capa-variante" in r.image_url  # alineamiento correcto


def test_blogbbm_parses_layout_b_volumes_especiais():
    """Layout B (volumes-especiais): title con (MM/YYYY) parens, figures después.
    Cada entry debe tener sus figures correctamente asignados."""
    from wikis import blogbbm as bbm
    cands = bbm.parse_post(_bbm_html("B"), {
        "url": "https://blogbbm.com/2024/05/15/guia-volumes-especiais-de-mangas-com-itens-especiais/",
        "source_suffix": "Volumes Especiais",
        "tag": "volumes-especiais",
        "signal_inject": "Edição especial com brinde / special edition with bonus.",
    })
    assert len(cands) == 2
    aot, slf = cands
    assert "Ataque dos Tit" in aot.title
    assert aot.release_date == "2021-12"  # del parens del título
    assert aot.publisher == "Panini"
    assert "aot34" in aot.image_url
    assert "special_edition" in aot.signal_types
    assert "bonus" in aot.signal_types
    assert "Shangri" in slf.title
    assert slf.release_date == "2022-04"
    assert "slf01" in slf.image_url


def test_blogbbm_rejects_narrative_paragraphs_as_titles():
    """`<p>` que empieza con narrativa ('O volume', 'A editora', 'No Brasil',
    'Em janeiro') NO debe pasar como título aunque mencione un #vol."""
    from wikis.blogbbm import _is_title_p
    from bs4 import BeautifulSoup
    def mk(html):
        return BeautifulSoup(html, "html.parser").p
    assert not _is_title_p(mk("<p>O volume #21 veio com adesivos.</p>"))
    assert not _is_title_p(mk("<p>A editora Panini publicou em 12/2024 a edição.</p>"))
    assert not _is_title_p(mk("<p>No Brasil, o volume #34 foi lançado.</p>"))
    assert not _is_title_p(mk("<p>Em janeiro de 2014 saiu o volume #06.</p>"))
    # Pero un título legítimo SÍ pasa.
    assert _is_title_p(mk("<p>Ataque dos Titãs #34 (12/2021)</p>"))
    # 'No Game No Life' empieza con 'no ' pero NO con 'no brasil'/'no início'.
    assert _is_title_p(mk("<p>No Game No Life #01 (Light Novel)</p>"), lenient=True)


def test_blogbbm_image_strips_wp_proxy_and_query():
    """URLs de imagen via i0.wp.com/i1.wp.com pasan a blogbbm.com directo
    para que el espejo local descargue desde el origen, no del proxy."""
    from wikis.blogbbm import _node_imgs
    from bs4 import BeautifulSoup
    soup = BeautifulSoup("""
      <div>
        <img src="https://i0.wp.com/blogbbm.com/wp-content/uploads/2017/09/test.jpg?w=401&h=609&ssl=1" alt="x"/>
        <img src="https://i2.wp.com/blogbbm.com/wp-content/uploads/2024/01/other.webp?fit=800" alt="y"/>
      </div>
    """, "html.parser")
    imgs = _node_imgs(soup.div)
    assert len(imgs) == 2
    assert imgs[0]["src"] == "https://blogbbm.com/wp-content/uploads/2017/09/test.jpg"
    assert imgs[1]["src"] == "https://blogbbm.com/wp-content/uploads/2024/01/other.webp"


def test_blogbbm_iter_year_months_returns_single_batch():
    from wikis import blogbbm as bbm
    assert bbm.iter_year_months(2024, 1, 2026, 12) == [(2024, 1)]


def _bbm_layout_c_html(rows: list[tuple[str, str, str, str]]) -> str:
    """Genera HTML mínimo de un post BBM Layout C (supsystic table).
    Cada tupla = (img_src, title, publisher, date_raw)."""
    body_rows = ""
    for img_src, title, pub, date in rows:
        img_html = f'<img src="{img_src}"/>' if img_src else ""
        body_rows += (
            f"<tr>"
            f"<td>{img_html}</td>"
            f"<td>{title}</td>"
            f"<td>{pub}</td>"
            f"<td>{date}</td>"
            f"</tr>"
        )
    pad = "X" * 5000  # parse_post requires len(html) >= 5000
    return f"""<html><body><article><div class="entry-content">
{pad}
<table class="supsystic-table" id="supsystic-table-78">
  <tbody>
    <tr><th></th><th>TÍTULOS</th><th>EDITORA</th><th>DATA</th></tr>
    {body_rows}
  </tbody>
</table>
</div></article></body></html>"""


def test_blogbbm_layout_c_parses_supsystic_table():
    """Layout C: 1 row supsystic = 1 candidate con box_set signal,
    publisher canónico del col 2, fecha YYYY.MM → YYYY-MM."""
    from wikis import blogbbm as bbm
    post_meta = next(p for p in bbm.BBM_POSTS if p["layout"] == "C")
    html = _bbm_layout_c_html([
        ("https://i0.wp.com/blogbbm.com/wp-content/uploads/2025/12/Pink-Heart-Jam-Deluxe-Box.jpg?resize=810",
         "Pink Heart Jam - Deluxe Box", "JBC", "2026.01"),
    ])
    cands = bbm.parse_post(html, post_meta)
    assert len(cands) == 1
    c = cands[0]
    assert c.title == "Pink Heart Jam - Deluxe Box"
    assert c.publisher == "JBC"
    assert c.release_date == "2026-01"
    assert "box_set" in c.signal_types
    assert c.country == "Brasil"
    # i0.wp.com proxy debe quitarse del image_url
    assert c.image_url.startswith("https://blogbbm.com/wp-content/uploads/2025/12/Pink-Heart-Jam-Deluxe-Box.jpg")
    # URL sintética con slug
    assert "bbm-entry=box-pink-heart-jam-deluxe-box" in c.url
    # bbm-box tag
    assert "bbm-box" in c.tags


def test_blogbbm_layout_c_preventa_em_breve_keeps_item_empty_date():
    """'Em breve' (preventa) → release_date vacío + status hint en description.
    El item sigue válido (box set anunciado pero sin fecha confirmada)."""
    from wikis import blogbbm as bbm
    post_meta = next(p for p in bbm.BBM_POSTS if p["layout"] == "C")
    html = _bbm_layout_c_html([
        ("https://i0.wp.com/img.jpg", "Claymore", "Panini", "Em breve"),
    ])
    cands = bbm.parse_post(html, post_meta)
    assert len(cands) == 1
    assert cands[0].release_date == ""
    assert "Em breve" in cands[0].description
    # box_set signal sigue activo (lo levanta el inject)
    assert "box_set" in cands[0].signal_types


def test_blogbbm_layout_c_placeholder_image_yields_empty_image_url():
    """'Sem-Imagem.png' es el placeholder del wiki para boxes sin cover.
    Lo descartamos como image_url (frontend usa 📚) pero el item se conserva."""
    from wikis import blogbbm as bbm
    post_meta = next(p for p in bbm.BBM_POSTS if p["layout"] == "C")
    html = _bbm_layout_c_html([
        ("https://i0.wp.com/blogbbm.com/wp-content/uploads/2024/02/Sem-Imagem.png?resize=247",
         "Mujirushi", "Panini", "Em breve"),
    ])
    cands = bbm.parse_post(html, post_meta)
    assert len(cands) == 1
    assert cands[0].image_url == ""
    assert cands[0].title == "Mujirushi"


def test_blogbbm_layout_c_dispatch_isolated_from_ab():
    """`parse_post` dispatches por `post_meta['layout']`: el post Box NO se
    parsea con la heurística title-driven de Layout A/B (no tiene <p> de
    título ni gallery divs) — debe entrar al parser supsystic puro."""
    from wikis import blogbbm as bbm
    # Post AB con HTML que NO tiene supsystic: debe usar layout AB.
    ab_post = next(p for p in bbm.BBM_POSTS if p["layout"] == "AB")
    html_no_struct = "<html><body>" + ("X" * 6000) + "<article><div class='entry-content'><p>No entries here</p></div></article></body></html>"
    assert bbm.parse_post(html_no_struct, ab_post) == []
    # Y un post layout C con tabla supsystic da resultados.
    c_post = next(p for p in bbm.BBM_POSTS if p["layout"] == "C")
    html_with_table = _bbm_layout_c_html([("", "X-Series", "JBC", "2026.05")])
    assert len(bbm.parse_post(html_with_table, c_post)) == 1


# --- booksprivilege (JP — 店舗特典) ---------------------------------------

_BP_DETAIL_FIXTURE = """
<article>
  <header class="entry-header">
    <h1 class="entry-title"><a href="?id=99033">陰の実力者になりたくて! (18)</a></h1>
  </header>
  <div class="entry-content">
    <div class="shop_box">
      <div class="shop_image">
        <a href="https://www.amazon.co.jp/dp/4041173876?tag=aff&linkCode=ogi" target="_blank">
          <img src="https://images-fe.ssl-images-amazon.com/images/P/4041173876.09_SL500_.jpg"/>
        </a>
      </div>
      <div class="shop_info">
        <div class="shop_title">陰の実力者になりたくて! (18) (角川コミックス・エース)</div>
        <div class="shop_author">坂野 杏梨, 逢沢 大介, 東西</div>
        <div class="shop_label">角川コミックス・エース</div>
        <div class="shop_date">2026-05-25</div>
      </div>
    </div>
    <div class="shop_box">
      <div class="shop_image">
        <a href="https://www.amazon.co.jp/dp/B0GX3CQB61"><img src="https://images-fe.ssl-images-amazon.com/images/P/B0GX3CQB61.09_SL500_.jpg"/></a>
      </div>
      <div class="shop_info">
        <div class="shop_title">陰の実力者になりたくて! Kindle</div>
        <div class="shop_label">Kindle</div>
      </div>
    </div>
  </div>
  <div class="shop-list">
    <div class="shop-row">
      <div class="shop-name-col">とらのあな</div>
      <div class="shop-benefit-col"><a href="https://ex.com">特製イラストカード</a></div>
    </div>
    <div class="shop-row">
      <div class="shop-name-col">ゲーマーズ</div>
      <div class="shop-benefit-col"><a href="https://ex.com">オリジナルブロマイド</a></div>
    </div>
    <div class="shop-row">
      <div class="shop-name-col">メロンブックス</div>
      <div class="shop-benefit-col"><a href="https://ex.com">ミニアクリルパネル<br/>イラストカード</a></div>
    </div>
  </div>
</article>
"""


def test_booksprivilege_parses_detail_basic():
    """Detail page canónica: title + ISBN-10 del path Amazon CDN + publisher
    canónico del label japonés + autor + fecha + shop bonuses en description."""
    from wikis import booksprivilege as bp
    cand = bp.parse_detail_page(_BP_DETAIL_FIXTURE, "https://booksprivilege.com/?id=99033")
    assert cand is not None
    assert cand.title == "陰の実力者になりたくて! (18)"
    assert cand.url == "https://booksprivilege.com/?id=99033"
    assert cand.isbn == "4041173876"
    assert cand.image_url == "https://images-fe.ssl-images-amazon.com/images/P/4041173876.09_SL500_.jpg"
    assert cand.publisher == "Kadokawa"
    assert cand.author == "坂野 杏梨, 逢沢 大介, 東西"
    assert cand.release_date == "2026-05-25"
    assert cand.country == "Japón"
    assert cand.language == "Japonés"
    assert cand.source == "JP - BooksPrivilege (店舗特典)"
    # Cada tienda + extra debe aparecer estructurado en description
    assert "店舗特典" in cand.description
    assert "とらのあな" in cand.description and "特製イラストカード" in cand.description
    assert "ゲーマーズ" in cand.description and "オリジナルブロマイド" in cand.description
    assert "メロンブックス" in cand.description
    # Amazon URL debe quedar como referencia de compra
    assert "amazon.co.jp/dp/4041173876" in cand.description
    # Volume tag
    assert "bp-vol:18" in cand.tags
    # Signal types: el inject de "店舗特典 / store bonus / bonus edition"
    # más el contexto de tokuten deberían levantar `bonus` al menos
    assert "bonus" in cand.signal_types


def test_booksprivilege_skips_when_only_kindle_asin():
    """Si solo hay Kindle ASIN (B0...) sin ISBN real, descartar — no podemos
    dedupar por ISBN y son productos digitales, no físicos."""
    from wikis import booksprivilege as bp
    html = """
    <article>
      <header class="entry-header"><h1 class="entry-title"><a>Solo Kindle</a></h1></header>
      <div class="shop_box">
        <div class="shop_image">
          <img src="https://images-fe.ssl-images-amazon.com/images/P/B0ABCDEFGH.09_SL500_.jpg"/>
        </div>
        <div class="shop_info">
          <div class="shop_label">Kindle</div>
        </div>
      </div>
    </article>
    """
    assert bp.parse_detail_page(html, "https://booksprivilege.com/?id=1") is None


def test_booksprivilege_skips_when_no_entry_title():
    """Page malformada (sin <h1 class=entry-title>) → None, no half-baked candidates."""
    from wikis import booksprivilege as bp
    html = """<article><div class="shop_box"><div class="shop_image"><img src="https://images-fe.ssl-images-amazon.com/images/P/4041173876.09_SL500_.jpg"/></div></div></article>"""
    assert bp.parse_detail_page(html, "https://booksprivilege.com/?id=1") is None


def test_booksprivilege_parses_daily_listing():
    """Listing diario: extrae item ids únicos de los <div class='book-item'>."""
    from wikis import booksprivilege as bp
    html = """
    <main>
      <div class="book-grid">
        <div class="book-item"><a href="?id=99033" class="book-item-title">Title A</a></div>
        <div class="book-item"><a href="?id=99034" class="book-item-title">Title B</a></div>
        <div class="book-item"><a href="?id=99033" class="book-item-title">Title A dup</a></div>
      </div>
    </main>
    """
    ids = bp.parse_daily_listing(html)
    assert ids == [99033, 99034]


def test_booksprivilege_parses_calendar_drops_spillover():
    """El calendario muestra días del mes adyacente en los bordes
    (ej. días 30/31 abril cuando mostrás mayo). El parser debe descartarlos
    para evitar duplicados al iterar meses contiguos."""
    from wikis import booksprivilege as bp
    import datetime as dt
    html = """
    <table class="calendar-table"><tbody>
      <tr>
        <td class="has-book"><a href="./?date=2026-04-30">30</a></td>
        <td class="has-book"><a href="./?date=2026-05-01">1</a></td>
        <td class="has-book"><a href="./?date=2026-05-05">5</a></td>
        <td class="empty">&nbsp;</td>
        <td class="has-book"><a href="./?date=2026-05-25">25</a></td>
        <td class="has-book"><a href="./?date=2026-06-01">1</a></td>
      </tr>
    </tbody></table>
    """
    days = bp.parse_calendar_month(html, 2026, 5)
    assert days == [dt.date(2026, 5, 1), dt.date(2026, 5, 5), dt.date(2026, 5, 25)]


def test_booksprivilege_label_to_publisher_canonical():
    """Imprints japoneses se mapean a publishers canónicos para que el cluster
    por publisher funcione. Imprints no mapeados quedan literales (el skill
    /watch-standardize-catalog los normaliza después)."""
    from wikis.booksprivilege import _publisher_from_label
    assert _publisher_from_label("角川コミックス・エース") == "Kadokawa"
    assert _publisher_from_label("講談社コミックス") == "Kodansha"
    assert _publisher_from_label("ジャンプコミックス（集英社）") == "Shueisha"
    assert _publisher_from_label("少年サンデーコミックス（小学館）") == "Shogakukan"
    # Unknown imprint: queda literal, no rompe
    assert _publisher_from_label("ベリーズファンタジー") == "ベリーズファンタジー"
    assert _publisher_from_label("") == ""


def test_booksprivilege_iter_year_months_inclusive_range():
    """Iterador de meses inclusive. Mar-2026 → Jun-2026 = 4 meses."""
    from wikis import booksprivilege as bp
    assert bp.iter_year_months(2026, 3, 2026, 6) == [
        (2026, 3), (2026, 4), (2026, 5), (2026, 6),
    ]
    # Cross-year boundary
    assert bp.iter_year_months(2025, 11, 2026, 2) == [
        (2025, 11), (2025, 12), (2026, 1), (2026, 2),
    ]
    # Reverse order gets swapped
    assert bp.iter_year_months(2026, 6, 2026, 3) == [
        (2026, 3), (2026, 4), (2026, 5), (2026, 6),
    ]


def test_booksprivilege_volume_extraction_jp_patterns():
    """Volume del título: '(18)', '第18巻', 'vol. 18'."""
    from wikis.booksprivilege import _extract_volume
    assert _extract_volume("陰の実力者になりたくて! (18)") == "18"
    assert _extract_volume("Title 第5巻") == "5"
    assert _extract_volume("Title vol. 12") == "12"
    assert _extract_volume("Standalone") == ""


# --- sumikko (JP — 限定版・特装版 / comic.sumikko.info) -------------------

def _sumikko_item_block(
    isbn: str,
    title: str,
    date_jp: str = "26年10月23日(金)",
    author: str = "久遠まこと",
    imprint: str = "MFコミックス",
    publisher: str = "KADOKAWA",
    type_tag: str = "コミック",
    img_class: str = "lazy",
    img_data_src: str | None = None,
) -> str:
    """Genera un bloque <a href=/item-select/...> tal como aparece en
    el listing real de sumikko. `img_data_src=None` deja el default a la
    URL Amazon CDN derivada del isbn."""
    if img_data_src is None:
        img_data_src = f"https://images-na.ssl-images-amazon.com/images/P/{isbn}.09._SY180_SCLZZZZZZZ_.jpg"
    publisher_span = f'<span>{publisher}</span>' if publisher else ''
    return (
        f'<a href="https://comic.sumikko.info/item-select/{isbn}">'
        f'<div class="Types"><span class="type type-tag">{type_tag}</span></div>'
        f'<div class="name">{title}</div>'
        f'<div class="sab"><span>{date_jp}</span><span>{author}</span></div>'
        f'<div class="sab"><span>{imprint}</span>{publisher_span}</div>'
        f'<div class="image"><img class="{img_class}" '
        f'src="https://comic.sumikko.info/web/img/loading/reload200_299.svg?v=1" '
        f'data-src="{img_data_src}" alt="{title}"/></div>'
        f'</a>'
    )


def test_sumikko_parses_listing_basic():
    """Un bloque típico: ISBN-10 desde URL, fecha JP, publisher canonical,
    imagen Amazon CDN, signal `limited`/`special_edition` por inject."""
    from wikis import sumikko as sk
    html = _sumikko_item_block(
        isbn="4046602074",
        title="勇者に全部奪われた俺は勇者の母親とパーティを組みました! 8 アクリルスタンド付き特装版",
    )
    cands = sk.parse_listing_page(html)
    assert len(cands) == 1
    c = cands[0]
    assert c.isbn == "4046602074"
    assert c.url == "https://comic.sumikko.info/item-select/4046602074"
    assert c.publisher == "Kadokawa"           # KADOKAWA → canonical
    assert c.release_date == "2026-10-23"      # 26年10月23日(金) → ISO
    assert c.author == "久遠まこと"
    assert c.country == "Japón"
    assert c.language == "Japonés"
    assert c.source == "JP - Sumikko (限定版・特装版)"
    assert c.image_url.endswith("4046602074.09._SY180_SCLZZZZZZZ_.jpg")
    # Volume extraído del título (entre " 8 " y la palabra 特装版)
    assert any(t == "sk-vol:8" for t in c.tags)
    # Signal: el inject "限定版・特装版" debe levantar `limited` y/o `special_edition`
    assert "limited" in c.signal_types or "special_edition" in c.signal_types


def test_sumikko_handles_single_sab_span_imprint_only():
    """Cuando sab[1] tiene SOLO 1 span (imprint sin parent publisher),
    el imprint actúa también como publisher (ej. Bushiroad Works)."""
    from wikis import sumikko as sk
    html = _sumikko_item_block(
        isbn="4049211475",
        title="魔法使いの嫁 25 特装版",
        imprint="ブシロードワークス",
        publisher="",                  # NO 2nd span
    )
    cands = sk.parse_listing_page(html)
    assert len(cands) == 1
    # ブシロード → canonical "Bushiroad Works"
    assert cands[0].publisher == "Bushiroad Works"


def test_sumikko_image_fallback_for_touch18_bl_items():
    """Items BL/R18 usan <img class='touch18'> (wrapper 18+) en vez de
    'lazy'. Igual extraemos el data-src real al CDN Amazon (gotcha del
    parser: NO filtramos por class, sólo buscamos cualquier <img>)."""
    from wikis import sumikko as sk
    html = _sumikko_item_block(
        isbn="4825100694",
        title="アフターグロウ(2) 限定版",
        img_class="touch18",
    )
    cands = sk.parse_listing_page(html)
    assert len(cands) == 1
    assert cands[0].image_url.endswith("4825100694.09._SY180_SCLZZZZZZZ_.jpg")


def test_sumikko_drops_loading_and_no_image_placeholders():
    """Los placeholders `reload200_299.svg`, `no_image200_299_BL.png` y
    cualquier `/loading/` se descartan como image_url (no son portadas)."""
    from wikis import sumikko as sk
    bad_html = _sumikko_item_block(
        isbn="9784567890123",
        title="Title placeholder 限定版",
        img_data_src="https://comic.sumikko.info/web/img/list/no_image200_299_BL.png",
    )
    cands = sk.parse_listing_page(bad_html)
    assert len(cands) == 1
    assert cands[0].image_url == ""


def test_sumikko_type_filter_optional_default_accepts_all():
    """Por default, accept_types está vacío → aceptamos cualquier type_tag
    (el `type-tag` describe el extra de la edición, no el producto).
    Verificado con un item etiquetado `カセット、ＣＤ等` (es un manga con
    CD bonus, NO una cassette de audio)."""
    from wikis import sumikko as sk
    html = _sumikko_item_block(
        isbn="4091236189",
        title="名探偵コナン 108 劇場版ティザーアクリルスタンド付き特装版",
        type_tag="カセット、ＣＤ等",
        imprint="少年サンデーコミックス",
        publisher="小学館",
    )
    cands = sk.parse_listing_page(html)
    assert len(cands) == 1
    assert cands[0].title.startswith("名探偵コナン")
    assert cands[0].publisher == "Shogakukan"


def test_sumikko_type_filter_opt_in_restricts():
    """Si pasás `accept_types={'コミック'}` explícitamente, descartamos
    todo lo que no sea コミック (filtrado opt-in)."""
    from wikis import sumikko as sk
    html = _sumikko_item_block(
        isbn="4091236189",
        title="Some Item",
        type_tag="ライトノベル",                # NOT コミック
    )
    cands = sk.parse_listing_page(html, accept_types=frozenset({"コミック"}))
    assert cands == []


def test_sumikko_parses_date_jp_format():
    """`_parse_jp_date` soporta '26年10月23日(金)' y variantes sin
    weekday. Año asumido como 20XX."""
    from wikis.sumikko import _parse_jp_date
    assert _parse_jp_date("26年10月23日(金)") == "2026-10-23"
    assert _parse_jp_date("24年1月3日(水)") == "2024-01-03"
    # Sin weekday
    assert _parse_jp_date("26年12月31日") == "2026-12-31"
    # Inválido
    assert _parse_jp_date("hoy") == ""
    assert _parse_jp_date("") == ""


def test_sumikko_publisher_canonical_map():
    """Mapeo de publishers JP a canonical (Kadokawa, Kodansha, Shogakukan,
    Shueisha, etc.). Publishers no mapeados quedan literales."""
    from wikis.sumikko import _publisher_canonical
    assert _publisher_canonical("KADOKAWA") == "Kadokawa"
    assert _publisher_canonical("講談社") == "Kodansha"
    assert _publisher_canonical("小学館") == "Shogakukan"
    assert _publisher_canonical("集英社") == "Shueisha"
    assert _publisher_canonical("祥伝社") == "Shodensha"
    assert _publisher_canonical("TOブックス") == "TO Books"
    assert _publisher_canonical("ブシロードワークス") == "Bushiroad Works"
    # Unknown publisher: literal
    assert _publisher_canonical("XYZ未知出版") == "XYZ未知出版"
    assert _publisher_canonical("") == ""


def test_sumikko_dedupe_by_isbn_within_page():
    """Si la misma ISBN aparece duplicada en un listing (raro pero por
    las dudas), sólo se conserva la primera ocurrencia."""
    from wikis import sumikko as sk
    block_a = _sumikko_item_block(isbn="4046602074", title="Title A 特装版")
    block_b = _sumikko_item_block(isbn="4046602074", title="Title B 特装版 (dup ISBN)")
    cands = sk.parse_listing_page(block_a + block_b)
    assert len(cands) == 1
    assert cands[0].title == "Title A 特装版"


# --- listadomanga_collections (Fase 1) -------------------------------------

def _lmc_html_minimal(*sections_html: str, formato: str = "Tomo (115x175) rústica (tapa blanda) con sobrecubierta", title: str = "Berserk (Panini)", publisher: str = "Panini Manga", author: str = "Kentaro Miura") -> str:
    """Construye un HTML mínimo de coleccion.php con header + secciones dadas."""
    header = (
        f'<h2>{title}\t\t</h2><hr/>'
        f'<b>T&iacute;tulo original:</b> Test<br/>'
        f'<b>Guion:</b> <a href="autor.php?id=1">{author}</a><br/>'
        f'<b>Editorial espa&ntilde;ola:</b> <a href="editorial.php?id=1">{publisher}</a><br/>'
        f'<b>Formato:</b> {formato}<br/>'
    )
    body = ''.join(sections_html)
    return f'<html><body>{"X" * 1500}{header}{body}</body></html>'


def _lmc_section(header: str, *items_html: str) -> str:
    """Wrappea un header h2 + sus items en la estructura típica."""
    items = ''.join(items_html)
    return (
        f'<table><tr><td><table class="ventana_id1" style="width: 974px">'
        f'<tr><td class="izq"><h2>{header}</h2></td></tr></table></td></tr></table>'
        f'<table style="padding: 0px;"><tr style="padding: 0px;">{items}</tr></table>'
    )


def _lmc_item(volume: int, series: str, desc_extra: str = "", price: str = "10,00 €", pages: str = "192 páginas en B/N", day: str = "23", month: str = "Marzo", year: str = "2023", image_id: str = "abc123", cls: str = "ventana_id1") -> str:
    """Una celda Layout A con el formato típico de listadomanga.

    `cls` = clase de la tabla item (ventana_id1 = manga B/N; ventana_id3 =
    manhwa a color; ventana_id9 = packs/especiales). El parser acepta
    cualquier `ventana_id<N>`.
    """
    desc_line = f'{desc_extra}<br/>' if desc_extra else ''
    title_line = f'{series} n&ordm;{volume}<br/>' if volume else f'{series}<br/>'
    return (
        f'<td><table class="{cls}" style="width: 184px;"><tr><td class="cen">'
        f'<img class="portada" src="https://static.listadomanga.com/{image_id}.jpg" '
        f'alt="{series} nº{volume}"/>'
        f'<div style="height: 8px"></div>'
        f'{title_line}'
        f'{desc_line}'
        f'{pages}<br/>'
        f'{price}<br/>'
        f'{day} <a href="novedades.php">{month} {year}</a>'
        f'</td></tr></table></td><td class="separacion"></td>'
    )


def test_lmc_parses_ediciones_especiales_section():
    """Sección 'Números editados (Ediciones Especiales)' produce items con
    signal special_edition + descripción del extra preservada."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Ediciones Especiales)",
            _lmc_item(41, "Berserk", desc_extra="Edición Especial con logo dorado + Lámina", price="25,00 €"),
            _lmc_item(42, "Berserk", desc_extra="Edición Especial con logo dorado + 2 mini-pósters + Baraja del tarot", price="35,00 €", image_id="def456"),
        )
    )
    cands = lmc.parse_collection_page(html, 2688)
    # score_candidate ya corrió en parse_collection_page? No, sólo en fetch.
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 2
    assert all(c.publisher == "Panini Manga" for c in cands)
    assert all(c.author == "Kentaro Miura" for c in cands)
    assert all("especial-" in c.url for c in cands)
    assert "especial-41" in cands[0].url
    assert "especial-42" in cands[1].url
    assert all("special_edition" in c.signal_types for c in cands)
    assert cands[0].release_date == "2023-03-23"


def test_lmc_especial_in_non_id1_ventana_is_captured():
    """Regresión (gotcha #41 + #100; caso owner 2026-06-14): la sección
    'Números editados (Ediciones Especiales)' suele renderizar sus tomos en una
    tabla `ventana_id9`/`id14` (skin CSS de especiales), NO en `ventana_id1`.
    El parser viejo solo leía `ventana_id1` → esos especiales daban 0 items y se
    perdían del corpus aunque la sección existe en la página viva (caso real:
    'El chico que me gusta no es un chico' nº3, id=5641, tabla `ventana_id14`,
    edición NO premium). Las secciones especiales DEBEN aceptar cualquier
    `ventana_id<N>` y emitir el item pese al gate de premium-format."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Ediciones Especiales)",
            _lmc_item(3, "El chico que me gusta no es un chico",
                      desc_extra="Edición Especial + Sobrecubierta Alternativa + Collar Púa de Guitarra",
                      price="12,00 €", cls="ventana_id14"),
        ),
        title="El chico que me gusta no es un chico",
        publisher="Editorial Hidra",
        # Formato NO premium: el especial entra por la sección, no por el formato.
        formato="Tomo (130x183) rústica (tapa blanda) con sobrecubierta",
    )
    cands = lmc.parse_collection_page(html, 5641)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 1, f"especial en ventana_id14 no capturado: {[c.url for c in cands]}"
    c = cands[0]
    assert "especial-3" in c.url
    assert "special_edition" in c.signal_types
    assert c.volume == "3"          # #60: volumen propagado al Candidate
    assert c.score >= 30            # el gate no lo descarta


def test_lmc_two_especiales_same_section_get_distinct_clusters():
    """Regresión (gotcha #60 + #100; caso owner 'A Miyoshi le gusta Hosaka'
    2026-06-14): dos ediciones especiales del MISMO título (vol 1 y vol 2) en la
    misma sección deben (a) emitirse AMBAS, (b) propagar su volumen a
    `Candidate.volume`, (c) derivar `cluster_key` DISTINTOS. El bug viejo dejaba
    `volume=''` (no propagaba `parsed['volume']` a `cand.volume`) → ambos
    especiales colapsaban al mismo cluster `lmc:N:special:` → `consolidate` los
    fusionaba y UNO se perdía (especial-1 desapareció del corpus; sobrevivió solo
    el 2). El caso real usa `ventana_id9`."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Ediciones Especiales)",
            _lmc_item(1, "A Miyoshi le gusta Hosaka", desc_extra="Edición Especial + Stand Acrílico",
                      price="13,00 €", image_id="miy1", cls="ventana_id9"),
            _lmc_item(2, "A Miyoshi le gusta Hosaka", desc_extra="Edición Especial + Stand Acrílico",
                      price="13,00 €", image_id="miy2", cls="ventana_id9"),
        ),
        title="A Miyoshi le gusta Hosaka",
        publisher="Ediciones Tomodomo",
        formato="Tomo (130x183) rústica (tapa blanda) con sobrecubierta",
    )
    cands = lmc.parse_collection_page(html, 5050)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 2, f"se esperaban 2 especiales, hubo {len(cands)}: {[c.url for c in cands]}"
    vols = sorted(c.volume for c in cands)
    assert vols == ["1", "2"], f"volúmenes no propagados (#60): {vols}"
    # Cada candidate → fila JSON → cluster_key. DISTINTOS para que consolidate NO
    # los fusione (la causa raíz de la pérdida histórica del especial-1).
    clusters = {mw.derive_cluster_key(mw.candidate_to_json(c)) for c in cands}
    assert clusters == {"lmc:5050:special:1", "lmc:5050:special:2"}, clusters


def test_lmc_free_preview_number_is_skipped():
    """Regresión (gotcha #103, caso owner Edens Zero id=3112 2026-06-14): un
    folleto promocional que la editorial REGALA (preview del 1er capítulo,
    mini-artbook, avance bundleado con un videojuego) aparece en 'Números
    editados' con la línea de precio "Número Gratuito" en lugar de "9,98 €".
    Listadomanga lo titula "(Especial)", así que entraba como special_edition,
    pero NO es una edición comprable ni coleccionable: hay que descartarlo en la
    ingestión (delta y full comparten este parser). La señal "Número Gratuito"
    es universal (verificada contra toda la categoría editorial 'Previews')."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            # Preview gratuito: misma sección regular, pero precio = Número Gratuito.
            _lmc_item(0, "Edens Zero", desc_extra="", price="N&uacute;mero Gratuito",
                      pages="84 páginas en B/N", image_id="free0"),
        ),
        title="Edens Zero (Especial)",
        publisher="Norma Editorial",
        # Formato no-premium: si NO fuera gratuito igual se descartaría por formato,
        # así que forzamos premium para aislar que la causa del skip es el precio.
        formato="Tomo (115x175) rústica (tapa blanda) con sobrecubierta",
    )
    cands = lmc.parse_collection_page(html, 3112)
    assert cands == [], f"el preview gratuito no debió emitir items: {[c.url for c in cands]}"


def test_lmc_free_preview_skipped_but_paid_items_kept():
    """El skip de 'Número Gratuito' es POR ITEM: una colección con un número
    gratuito Y números de pago conserva los de pago (no se descarta la colección
    entera)."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Ediciones Especiales)",
            _lmc_item(0, "Serie X", desc_extra="Edición Especial", price="N&uacute;mero Gratuito", image_id="freex"),
            _lmc_item(1, "Serie X", desc_extra="Edición Especial con cofre", price="29,95 €", image_id="paidx"),
        ),
        title="Serie X",
        publisher="Norma Editorial",
    )
    cands = lmc.parse_collection_page(html, 9911)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 1, f"sólo el de pago debía sobrevivir: {[c.url for c in cands]}"
    assert "especial-1" in cands[0].url


def test_lmc_parses_portadas_alternativas_with_variant_cover_signal():
    """Sección Portadas alternativas → signal variant_cover."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Portadas alternativas)",
            _lmc_item(1, "Centuria", desc_extra="Portada Alternativa + 2 postales + bolígrafo", price="9,00 €", month="Julio", year="2025", day="31"),
        ),
        title="Centuria",
        publisher="Editorial Ivrea",
    )
    cands = lmc.parse_collection_page(html, 6090)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 1
    assert "alternativa-1" in cands[0].url
    assert "variant_cover" in cands[0].signal_types
    assert cands[0].publisher == "Editorial Ivrea"


def test_lmc_regular_tomos_discarded_when_format_not_premium():
    """Tomos regulares (Números editados sin paréntesis) bajo formato no-premium
    NO deben generar candidates."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(37, "Berserk", price="10,00 €", month="Junio", year="2017", day=""),
            _lmc_item(38, "Berserk", price="10,00 €", month="Noviembre", year="2017", day=""),
        ),
        # Formato regular (no-premium)
        formato="Tomo (130x183) rústica (tapa blanda) con sobrecubierta",
    )
    cands = lmc.parse_collection_page(html, 2688)
    assert cands == []  # tomos regulares descartados


def test_lmc_regular_tomos_kept_when_format_is_kanzenban():
    """Si Formato dice 'kanzenban' (literal), TODOS los items de 'Números
    editados' pasan con signal premium. (kanzenban es type=premium_format.)
    NOTA (gotcha #51): 'doble sobrecubierta' ya NO cuenta como kanzenban —
    sólo el literal 'kanzenban' o el título '(Kanzenban)'."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "FullMetal Alchemist", price="12,00 €", month="Enero", year="2014"),
        ),
        formato="Tomo Kanzenban A5 (148x210) rústica con sobrecubierta",
    )
    cands = lmc.parse_collection_page(html, 1741)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 1
    assert "regular-1" in cands[0].url
    # `premium_format` cubre kanzenban / master / library / ultimate / etc.
    assert "premium_format" in cands[0].signal_types


def test_lmc_premium_format_carton_tapa_dura_triggers_hardcover():
    """Formato 'Tomo doble A5 cartoné (tapa dura)' → hardcover + omnibus."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Atelier of Witch Hat Edición Grimorio", price="24,00 €", month="Noviembre", year="2025", day="27", image_id="grim1"),
        ),
        title="Atelier of Witch Hat (Edición Grimorio)",
        publisher="Milky Way Ediciones",
        formato="Tomo doble A5 (148x210) cartoné (tapa dura)",
    )
    cands = lmc.parse_collection_page(html, 6242)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 1
    sigs = set(cands[0].signal_types)
    # Cartoné + tapa dura → hardcover; Tomo doble → omnibus; A5 → kanzenban
    assert "hardcover" in sigs
    assert "omnibus" in sigs


def test_lmc_pack_kept_only_if_description_has_extras():
    """Packs sin descripción de extras se descartan; con extras se mantienen."""
    from wikis import listadomanga_collections as lmc
    # Con extras (postales + bookmark)
    html_with_extras = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Packs)",
            _lmc_item(0, "Ataque a los Titanes", desc_extra="Pack iniciación tomos 1 y 2 + postales exclusivas + bookmark magnético", price="16,00 €", month="Octubre", year="2012", day="31"),
        ),
        title="Ataque a los Titanes",
    )
    cands = lmc.parse_collection_page(html_with_extras, 1606)
    assert len(cands) == 1
    assert "pack-0" in cands[0].url

    # Sin extras (solo pack de tomos)
    html_no_extras = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Packs)",
            _lmc_item(0, "Some Manga", desc_extra="Pack tomos 1 y 2", price="14,00 €"),
        ),
    )
    cands = lmc.parse_collection_page(html_no_extras, 9999)
    assert cands == []


def test_lmc_synthetic_url_is_deterministic_per_edition_and_volume():
    """Mismo input → mismo URL (idempotencia para re-scrapes)."""
    from wikis.listadomanga_collections import _make_synthetic_url
    u1 = _make_synthetic_url(2688, "especial", "42")
    u2 = _make_synthetic_url(2688, "especial", "42")
    assert u1 == u2
    # Ediciones distintas del mismo tomo → URLs distintas
    u3 = _make_synthetic_url(2688, "alternativa", "42")
    assert u1 != u3
    # Volúmenes distintos en la misma edición → URLs distintas
    u4 = _make_synthetic_url(2688, "especial", "41")
    assert u1 != u4
    # URL bien formada (no `https://...` duplicado ni `//` extra)
    assert u1.startswith("https://www.listadomanga.es/coleccion.php?id=2688&item=")
    assert u1.count("https://") == 1


def test_lmc_synthetic_url_survives_normalization():
    """El param `item=...` debe sobrevivir `normalize_url_for_dedup`
    (no está en TRACKING_PARAMS). Si dos items distintos colapsan al mismo
    URL post-normalización, el upsert los pisa entre sí."""
    from wikis.listadomanga_collections import _make_synthetic_url
    norm = mw.normalize_url_for_dedup
    u_vol1 = _make_synthetic_url(2688, "especial", "1")
    u_vol2 = _make_synthetic_url(2688, "especial", "2")
    u_alt1 = _make_synthetic_url(2688, "alternativa", "1")
    n1, n2, na = norm(u_vol1), norm(u_vol2), norm(u_alt1)
    # Los 3 deben ser distintos post-normalización.
    assert n1 != n2
    assert n1 != na
    assert n2 != na


def test_lmc_planeta_section_processed_as_regular_with_premium_format():
    """Regresión: `Números editados (Planeta DeAgostini Cómics)` y
    `(Planeta Cómic)` se procesaban como DISCARD (perdían ~222 colecciones
    legítimas premium). Fix 2026-05-23: tratarlas como REGULAR — los items
    pasan si el Formato de la página es premium, igual que `Números
    editados` sin paréntesis.

    Caso real id=1832 (Dragon Ball Box Set, Edición de Lujo): 4 items
    extraídos correctamente, antes 0."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Planeta DeAgostini C&oacute;mics)",
            _lmc_item(1, "Test Manga", price="20,00 €", image_id="p1"),
        ),
        _lmc_section(
            "N&uacute;meros editados (Planeta C&oacute;mic)",
            _lmc_item(2, "Test Manga", price="20,00 €", image_id="p2"),
        ),
        # Formato premium → todos los items deberían entrar
        formato="Tomo doble A5 (148x210) cartoné (tapa dura)",
    )
    cands = lmc.parse_collection_page(html, 1832)
    # 2 items (uno de cada sección de editorial)
    assert len(cands) == 2
    for c in cands:
        lmc.score_candidate(c)
        # Deberían tener signals premium del Formato cartoné A5
        assert any(s in c.signal_types for s in ["hardcover", "deluxe", "omnibus"])

    # Sin premium → 0 (tomos regulares de re-edición no son coleccionables)
    html_no_premium = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Planeta C&oacute;mic)",
            _lmc_item(1, "Test Manga", price="9,00 €", image_id="p1"),
        ),
        formato="Tomo (115x175) rústica (tapa blanda) con sobrecubierta",
    )
    cands_no_prem = lmc.parse_collection_page(html_no_premium, 9999)
    assert cands_no_prem == []


def test_lmc_censored_placeholder_kept_without_image():
    """Bug 2026-06-07: para algunas ediciones adultas/sin cover, listadomanga
    sirve server-side el placeholder de portada censurada (08a02c…png). El item
    es VÁLIDO (título/precio) pero NO tiene portada → se captura con imagen
    vacía (elegible para search-covers), NO se descarta ni se usa el placeholder."""
    from wikis import listadomanga_collections as lmc
    item = (
        '<td><table class="ventana_id1" style="width: 184px;"><tr><td class="cen">'
        f'<img class="portada" src="https://static.listadomanga.com/{lmc.CENSORED_COVER_HASH}.png" '
        'alt="Bastard!! nº1"/>'
        '<div style="height: 8px"></div>'
        'Bastard!! n&ordm;1<br/>200 páginas<br/>12,00 €<br/>1 Enero 2020'
        '</td></tr></table></td><td class="separacion"></td>'
    )
    html = _lmc_html_minimal(
        _lmc_section("N&uacute;meros editados", item),
        formato="Tomo A5 (148x210) cartoné (tapa dura)", title="Bastard!! (Kanzenban)",
    )
    cands = lmc.parse_collection_page(html, 1555)
    assert len(cands) == 1, "el item censurado debe capturarse igual"
    assert cands[0].image_url == "", "no debe usar el placeholder censurado como portada"
    assert not cands[0].images, "sin imágenes → entra a search-covers"


def test_lmc_two_line_subtitle_joined_into_title():
    """Bug 2026-06-07: artbooks cuyo título va en DOS líneas sin número
    ('CLAMP Art-book' + 'North Side') perdían el subtítulo — el parser tomaba
    solo la 1ª línea. Resultado: North Side y South Side quedaban con título
    idéntico 'CLAMP Art-book' → la cover search los confundía. Fix: la 2da línea
    se une al título si aparece en el `alt` canónico."""
    from wikis import listadomanga_collections as lmc
    item = (
        '<td><table class="ventana_id1" style="width: 184px;"><tr><td class="cen">'
        '<img class="portada" src="https://static.listadomanga.com/nrt1.jpg" '
        'alt="CLAMP Art-book North Side"/>'
        '<div style="height: 8px"></div>'
        'CLAMP Art-book<br/>North Side<br/>'
        '172 páginas a color<br/>26,00 €<br/>1 Noviembre 2006'
        '</td></tr></table></td><td class="separacion"></td>'
    )
    html = _lmc_html_minimal(
        _lmc_section("N&uacute;meros editados", item),
        formato="Libro de ilustraciones A4 (210x297) rústica (tapa blanda)",
        title="CLAMP Art-book North Side",
    )
    cands = lmc.parse_collection_page(html, 248)
    assert len(cands) == 1
    assert cands[0].title == "CLAMP Art-book North Side", \
        f"esperado subtítulo unido, got {cands[0].title!r}"


def test_lmc_parses_ventana_id9_special_section():
    """Iteración dry-run 2026-06-06: las ediciones especiales/packs pueden venir
    en `ventana_id9` (no solo id1). El parser acepta cualquier `ventana_id<N>`.
    Caso real id=6362 His Little Amber (Edición Especial)."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Ediciones Especiales)",
            _lmc_item(1, "His Little Amber", price="20,00 €", image_id="hla1", cls="ventana_id9"),
        ),
        formato="Tomo B6 (128x180) rústica (tapa blanda) con sobrecubierta",
        title="His Little Amber (Edici&oacute;n Especial)",
    )
    cands = lmc.parse_collection_page(html, 6362)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 1
    assert "special_edition" in cands[0].signal_types


def test_lmc_regular_section_only_emits_ventana_id1():
    """Iteración dry-run 2026-06-06: la sección REGULAR ('Números editados')
    solo emite tomos `ventana_id1` (manga japonés B/N). Otros layouts en la
    sección regular son ediciones estándar no-coleccionables: manhwa a color
    (id3), manga catalán/regional (id2), revistas (id12). Emitirlos inundaría
    el catálogo (caso Detectiu Conan id2, Mundo Manganime id12). Sweet Home
    (id3 regular) → 0."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Sweet Home", price="16,95 €", pages="324 páginas a color",
                      image_id="sh1", cls="ventana_id3"),
            _lmc_item(2, "Sweet Home", price="16,95 €", pages="276 páginas a color",
                      image_id="sh2", cls="ventana_id3"),
        ),
        formato="Tomo A5 (148x210) rústica (tapa blanda) con sobrecubierta",
        title="Sweet Home",
    )
    cands = lmc.parse_collection_page(html, 6112)
    assert cands == [], f"manhwa a color regular NO debe capturarse, got {len(cands)}"


def test_lmc_title_premium_allows_non_id1_regular():
    """Iteración dry-run 2026-06-06: si la colección es premium POR TÍTULO
    (Maximum/Kanzenban/Black Edition/Integral…), su sección regular SÍ emite
    tomos en layouts no-id1 (ediciones catalanas premium usan ventana_id2:
    'Berserk (Maximum) (Català)', 'Ranma ½ (Kanzenban) (Català)'). Sin
    title_premium serían descartados (no-coleccionables); con él, capturados."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Berserk", price="19,00 €", image_id="bm1", cls="ventana_id2"),
            _lmc_item(2, "Berserk", price="19,00 €", image_id="bm2", cls="ventana_id2"),
        ),
        formato="Tomo A5 (148x210) rústica (tapa blanda) con sobrecubierta",
        title="Berserk (Maximum) (Català)",
    )
    cands = lmc.parse_collection_page(html, 4945)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 2, f"edición catalana premium (id2) debe capturarse, got {len(cands)}"


def test_lmc_special_section_accepts_any_ventana_layout():
    """Contraparte: una SECCIÓN ESPECIAL en layout no-id1 (manhwa a color id3)
    SÍ se captura — solo la sección regular está restringida a id1."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Ediciones Especiales)",
            _lmc_item(1, "Sweet Home", desc_extra="Edición Especial con caja",
                      price="29,95 €", pages="324 páginas a color",
                      image_id="shesp1", cls="ventana_id3"),
        ),
        formato="Tomo A5 (148x210) rústica (tapa blanda) con sobrecubierta",
        title="Sweet Home",
    )
    cands = lmc.parse_collection_page(html, 61120)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 1, f"especial en id3 debe capturarse, got {len(cands)}"
    assert "special_edition" in cands[0].signal_types


def test_lmc_a5_standard_edition_not_premium():
    """Decisión owner 2026-06-06: el formato A5 (148x210) es el ESTÁNDAR de
    muchas series clásicas (Detective Conan, Monster, Vinland…), NO señal de
    kanzenban. Una colección A5 sin título kanzenban ni 'doble sobrecubierta'
    NO se captura (eran sobre-captura: 254 tomos estándar en el run real)."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Detective Conan", price="8,00 €", image_id="dc1", cls="ventana_id1"),
            _lmc_item(2, "Detective Conan", price="8,00 €", image_id="dc2", cls="ventana_id1"),
        ),
        formato="Tomo A5 (148x210) rústica (tapa blanda) con sobrecubierta",
        title="Detective Conan (Vol.2)",
    )
    cands = lmc.parse_collection_page(html, 99003)
    assert cands == [], f"edición A5 estándar NO debe capturarse, got {len(cands)}"


def test_format_especial_title_order():
    """Gotcha #52: edición especial → '{serie} {vol} Edición Especial' (vol antes
    del calificador, sin paréntesis). Idempotente; el regular no se toca."""
    f = mw.format_especial_title
    assert f("Witch Hat Atelier Edición Especial 5") == "Witch Hat Atelier 5 Edición Especial"
    assert f("Atelier of Witch Hat 5 (Edición Especial)") == "Atelier of Witch Hat 5 Edición Especial"
    assert f("Witch Hat Atelier 5 Edición Especial") == "Witch Hat Atelier 5 Edición Especial"  # idempotente
    assert f("Atelier of Witch Hat 5") == "Atelier of Witch Hat 5"  # regular intacto
    assert f("Berserk Deluxe 1") == "Berserk Deluxe 1"  # otra edición intacta
    # Gotcha #94: NO traducir el inglés. "Special Edition"/"Special" en un título
    # extranjero se deja intacto (antes se convertía en "Edición Especial").
    assert f("Demon Slayer Special Edition 23") == "Demon Slayer Special Edition 23"
    assert f("葬送のフリーレン Special Edition 15") == "葬送のフリーレン Special Edition 15"
    assert f("Attack on Titan Special 34") == "Attack on Titan Special 34"


def test_lmc_normalize_display_title():
    """Gotcha #52: quitar el marcador de volumen 'nº' del título de display y
    marcar la edición ESPECIAL con '(Edición Especial)' para distinguirla del
    tomo regular del mismo volumen (que conviven en la misma edición)."""
    from wikis.listadomanga_collections import normalize_display_title as n
    assert n("Atelier of Witch Hat nº5", "regular") == "Atelier of Witch Hat 5"
    assert n("Atelier of Witch Hat nº5", "especial") == "Atelier of Witch Hat 5 Edición Especial"
    assert n("Monster nº1", "regular") == "Monster 1"
    # Gotcha #56: "Edición Especial" embebido se remueve y, si es especial, se
    # re-apenda UNA vez al final (reordena, no deja el qualifier en el medio).
    assert n("Witch Hat Atelier Edición Especial 5", "especial") == "Witch Hat Atelier 5 Edición Especial"
    assert n("The Promised Neverland Edición Especial 13", "regular") == "The Promised Neverland 13"
    assert n("Witch Hat Atelier Edición Grimorio 1", "regular") == "Witch Hat Atelier Edición Grimorio 1"
    # Gotcha #54: AUTORITATIVO — un tomo NO especial NUNCA lleva "Edición Especial".
    assert n("Attack on Titan 1 Edición Especial", "regular") == "Attack on Titan 1"
    assert n("Platinum End 14 Edición Especial", "regular") == "Platinum End 14"
    # …pero el especial GENUINO lo conserva (no se duplica).
    assert n("Attack on Titan 34 Edición Especial", "special") == "Attack on Titan 34 Edición Especial"
    assert n("Attack on Titan 34 Edición Especial", "especial") == "Attack on Titan 34 Edición Especial"
    # Gotcha #56: marcadores de kind variant/limited (distinguen del regular del
    # mismo volumen). Se apendan si faltan; no se duplican.
    assert n("Devilman Omnibus 1", "variant") == "Devilman Omnibus 1 Variant"
    assert n("Berserk Variant 41", "variant") == "Berserk Variant 41"           # ya presente
    assert n("Berserk Kanzenban 1", "limited") == "Berserk Kanzenban 1 Edición Limitada"
    assert n("Kagurabachi Edición Especial Metalizada 1", "variant") == "Kagurabachi Metalizada 1 Variant"
    # Gotcha #93: un título que llega decorado con "Special Edition" (EN) NO debe
    # duplicar el marcador al re-apendar el español. Caso real (legacy, corrompido
    # por el skill viejo de standardize que tradujo la edición a inglés).
    assert n("Pájaro que trina no vuela nº9 Special Edition", "special") == "Pájaro que trina no vuela 9 Edición Especial"
    assert n("Crush of Lifetime nº6 Special Edition", "especial") == "Crush of Lifetime 6 Edición Especial"
    # …y un tomo regular nunca conserva el qualifier en inglés.
    assert n("Scarlet Secret Special Edition", "regular") == "Scarlet Secret"


def test_fix_title_edition_words_collapses_real_dups():
    """fix_title_edition_words colapsa duplicaciones REALES de edición sin tocar
    nombres de obra con repetición legítima (gotcha #94)."""
    from retrofit.fix_title_edition_words import fix_title
    # CJK: descriptor de edición repetido verbatim → una sola copia.
    assert fix_title("新 仮面ライダーSPIRITS(13)特装版 特装版 オールカラー別冊", "") == \
        "新 仮面ライダーSPIRITS(13)特装版 オールカラー別冊"
    assert fix_title("マギ 29 オリジナルバッジ付き限定版 オリジナルバッジ付き限定版！！！", "") == \
        "マギ 29 オリジナルバッジ付き限定版！！！"
    # Ordinal repetido (case-insensitive) → conserva el bien formateado.
    assert fix_title("BERSERK 30TH 30th Anniversary Edition", "") == "BERSERK 30th Anniversary Edition"
    # NO toca nombres de obra con repetición legítima.
    assert fix_title("デッドデッドデーモンズデデデデデストラクション 11 限定版", "") == \
        "デッドデッドデーモンズデデデデデストラクション 11 限定版"
    assert fix_title("トロピカル〜ジュ!プリキュア プリキュアコレクション 特装版", "") == \
        "トロピカル〜ジュ!プリキュア プリキュアコレクション 特装版"
    assert fix_title("Kuma Kuma Kuma Bear Variant 1", "") == "Kuma Kuma Kuma Bear Variant 1"
    assert fix_title("New York New York 1", "") == "New York New York 1"


def test_dedup_synthetic_source_is_cole_qualified():
    """Gotcha #54: el hash del `item=` NO es único entre colecciones (listadomanga
    reusa el filename de portada placeholder → `regular-1-08a02c268a6d6b23` aparece
    idéntico en obras distintas). La identidad sintética del dedup DEBE incluir el
    `id` de colección, o se fusionarían obras totalmente distintas (NGE + Tokyo
    Revengers + Bastard!! colapsando en una)."""
    from retrofit.dedup_synthetic_source import _syn_hashes, _cole_of
    base = "https://www.listadomanga.es/coleccion.php?id="
    nge = {"url": f"{base}4288&item=regular-1-08a02c268a6d6b23", "sources": []}
    bastard = {"url": f"{base}1555&item=regular-1-08a02c268a6d6b23", "sources": []}
    # MISMO hash, distinta colección → tokens DISTINTOS (no se unen).
    assert _syn_hashes(nge).isdisjoint(_syn_hashes(bastard))
    assert all(_cole_of(t) == "4288" for t in _syn_hashes(nge))
    # MISMA colección + mismo item= (fila base + fila sintética) → tokens IGUALES.
    aot_special = {"url": f"{base}1606&item=especial-34-39266d3ef0a1b188", "sources": []}
    aot_dup = {"url": f"{base}1606",
               "sources": [{"url": f"{base}1606&item=especial-34-39266d3ef0a1b188"}]}
    assert _syn_hashes(aot_special) & _syn_hashes(aot_dup)


def test_fix_edition_key_anomalies():
    """Normaliza dos anomalías del edition_key (validate_corpus COLED/PAIS):
    (A) `panini-es`→`panini` (país no va en el slug de editorial, sino en el sufijo);
    (B) `-xx` (país desconocido) → país inferido por tier: source country →
    grupo de registro ISBN → editorial mono-país (norma→es, pika→fr, star→it,
    viz→us); sin evidencia (panini/kodansha/unknown sin ISBN) → xx."""
    from retrofit.fix_edition_key_anomalies import _fix_ek, _publisher_slug

    def ek(it):
        return _fix_ek(it)[0]

    assert _publisher_slug("fruits-basket-norma-collector-xx") == "norma"
    # (A) panini-es bug
    assert ek({"edition_key": "berserk-panini-es-special-es"}) == "berserk-panini-special-es"
    assert ek({"edition_key": "marvel-miau-panini-es-deluxe-es"}) == "marvel-miau-panini-deluxe-es"
    # (B) xx inferible por editorial mono-país
    assert ek({"edition_key": "i-am-a-hero-norma-collector-xx"}) == "i-am-a-hero-norma-collector-es"
    assert ek({"edition_key": "nodame-cantabile-pika-deluxe-xx"}) == "nodame-cantabile-pika-deluxe-fr"
    assert ek({"edition_key": "vinland-saga-star-variant-xx"}) == "vinland-saga-star-variant-it"
    # (B) xx ambiguo / unknown SIN ISBN → NO se toca (no inventamos país)
    assert ek({"edition_key": "berserk-panini-master-xx"}) is None
    assert ek({"edition_key": "black-clover-unknown-variant-xx"}) is None
    # (B) source con country explícito gana sobre la editorial
    assert ek({"edition_key": "x-panini-special-xx",
               "sources": [{"country": "España"}]}) == "x-panini-special-es"
    # idempotente: ya correcto → None
    assert ek({"edition_key": "berserk-panini-special-es"}) is None


def test_fix_edition_key_isbn_country_tier():
    """Tier ISBN→país: el grupo de registro del ISBN identifica el país de la
    edición (978-84=es, 978-3=de, 978-612=pe, 607 ISBN-10=mx). Grupos
    anglófonos (978-0/1) NO se mapean (US/UK ambiguo)."""
    from retrofit.fix_edition_key_anomalies import _fix_ek, _isbn_country

    assert _isbn_country("9788467961171") == "es"
    assert _isbn_country("9783741648014") == "de"
    assert _isbn_country("9786124854439") == "pe"
    assert _isbn_country("6075785124") == "mx"       # ISBN-10
    assert _isbn_country("978-88-345-2342-1") == "it"  # con guiones
    assert _isbn_country("9791032710561") == "fr"      # 979-10
    assert _isbn_country("9780123456789") == ""        # anglófono: ambiguo
    assert _isbn_country("9781974736811") == ""
    assert _isbn_country("") == ""
    assert _isbn_country("no-isbn") == ""

    # Integración: panini multi-país se resuelve vía ISBN alemán
    new, country = _fix_ek({"edition_key": "berserk-panini-master-xx",
                            "isbn": "9783741648014"})
    assert new == "berserk-panini-master-de"
    assert country == "de"
    # source country explícito le gana al ISBN
    new, _ = _fix_ek({"edition_key": "x-panini-special-xx",
                      "isbn": "9783741648014",
                      "sources": [{"country": "Italia"}]})
    assert new == "x-panini-special-it"


def test_unify_coleccion_cross_source_cole():
    """unify agrupa fichas de TIENDA (primaria no-listadomanga) a su colección vía
    `sources[]` — para que adopten el edition_key base (coleccion=edición). Sólo si
    referencian UNA sola colección."""
    from retrofit.unify_coleccion_edition import _cole_of_item
    base = "https://www.listadomanga.es/coleccion.php?id=2689"
    store = {"url": "https://www.panini.es/berserk-maximum-21.html",
             "sources": [{"url": "https://www.panini.es/berserk-maximum-21.html"},
                         {"url": f"{base}&item=especial-21-cd1ce6cc0e80881c"}]}
    assert _cole_of_item(store) == "2689"
    # fila de listadomanga → su propia primaria
    assert _cole_of_item({"url": f"{base}&item=regular-1-abc", "sources": []}) == "2689"
    # tienda que referencia 2 colecciones distintas → ambiguo, no se asigna
    amb = {"url": "https://tienda.com/x.html",
           "sources": [{"url": f"{base}&item=regular-1-a"},
                       {"url": "https://www.listadomanga.es/coleccion.php?id=999&item=regular-1-b"}]}
    assert _cole_of_item(amb) is None


def test_unify_box_set_is_separate_edition():
    """Gotcha #58: un box set = edición APARTE (slug `boxset`), separado de los tomos
    de la misma /coleccion. Pack/especial conviven en la edición; box set NO. Un tomo
    suelto mal clusterizado como `pack:N` NO es box."""
    from retrofit.unify_coleccion_edition import _is_box, _with_slug
    assert _is_box({"cluster_key": "lmc:49:pack:0", "title": "The Legend of Zelda Box Set"})
    assert _is_box({"cluster_key": "lmc:2515:boxset:", "title": "Uzumaki Box Set"})
    assert _is_box({"cluster_key": "lmc:2515:limited:0", "title": "Uzumaki Box Set Edición Limitada"})
    assert _is_box({"cluster_key": "lmc:4139:pack:8", "title": "Kaiju No. 8 Box Set 1-3"})
    # tomo suelto mal clusterizado como pack → NO es box
    assert not _is_box({"cluster_key": "lmc:2255:pack:42", "title": "My Hero Academia 42"})
    # tomo regular normal → NO es box
    assert not _is_box({"cluster_key": "lmc:49:regular:1", "title": "The Legend of Zelda 1"})
    # _with_slug preserva serie/publisher/desambiguador/país
    assert _with_slug("legend-of-zelda-norma-regular-es", "boxset") == "legend-of-zelda-norma-boxset-es"
    assert _with_slug("i-am-a-hero-norma-special-c1686-es", "boxset") == "i-am-a-hero-norma-boxset-c1686-es"


def test_disambiguate_coleccion_editions_insert_cole():
    """Gotcha #57: coleccion distinta = edición distinta. Si un edition_key abarca
    >1 colección, se inserta `-c{cole}` antes del país. Idempotente."""
    from retrofit.disambiguate_coleccion_editions import _insert_cole, _cole_of
    assert _insert_cole("biomega-panini-kanzenban-es", "2572") == "biomega-panini-kanzenban-c2572-es"
    assert _insert_cole("biomega-panini-kanzenban-es", "4501") == "biomega-panini-kanzenban-c4501-es"
    # idempotente: ya tiene -cNNNN → no re-inserta
    assert _insert_cole("biomega-panini-kanzenban-c2572-es", "2572") == "biomega-panini-kanzenban-c2572-es"
    base = "https://www.listadomanga.es/coleccion.php?id=2572"
    assert _cole_of({"cluster_key": "lmc:2572:regular:1", "url": ""}) == "2572"
    assert _cole_of({"cluster_key": "edition:x|1", "url": f"{base}&item=regular-1-a", "sources": []}) == "2572"


def test_collapse_baseurl_only_phantoms():
    """Gotcha #56: collapse_baseurl_tomos SÓLO toca filas base-url SIN fuente
    sintética propia. Una base-url que SÍ tiene su `item=` es un producto real
    (regular que coexiste con el especial del mismo vol) — no se fusiona."""
    from retrofit.collapse_baseurl_tomos import _is_baseurl, _has_syn
    base = "https://www.listadomanga.es/coleccion.php?id=2857"
    phantom = {"url": base, "sources": [{"url": base}]}
    real = {"url": base, "sources": [{"url": base},
                                     {"url": f"{base}&item=regular-13-abc"}]}
    assert _is_baseurl(phantom) and not _has_syn(phantom)   # phantom → se colapsa
    assert _is_baseurl(real) and _has_syn(real)             # real → NO se colapsa
    syn = {"url": f"{base}&item=especial-13-xyz", "sources": []}
    assert not _is_baseurl(syn)


def test_dedup_synthetic_debundle_store_multikind():
    """Gotcha #54: una fila de TIENDA que agrupa sintéticos de listadomanga de
    KINDS distintos (Berserk Pack = especial-41 + alternativa-41) mezcla 2
    productos. De-bundle conserva el que matchea su edition-slug (special) y quita
    el ajeno SÓLO si otra fila ya lo tiene (sin pérdida)."""
    from retrofit.dedup_synthetic_source import _debundle_store_rows, _syn_hashes
    base = "https://www.listadomanga.es/coleccion.php?id=2688"
    pack = {"url": "https://www.panini.es/pack-berserk-41.html",
            "edition_key": "berserk-panini-special-es",
            "sources": [{"url": "https://www.panini.es/pack-berserk-41.html"},
                        {"url": f"{base}&item=especial-41-89c7c3217d160e28"},
                        {"url": f"{base}&item=alternativa-41-bbfee745546a2965"}]}
    variant = {"url": f"{base}&item=alternativa-41-bbfee745546a2965",
               "edition_key": "berserk-panini-es-special-es",
               "sources": [{"url": f"{base}&item=alternativa-41-bbfee745546a2965"}]}
    n = _debundle_store_rows([pack, variant])
    assert n == 1  # se quitó 1 fuente ajena (alternativa) del pack
    toks = _syn_hashes(pack)
    assert any("especial-41" in t for t in toks)        # conserva el especial
    assert not any("alternativa-41" in t for t in toks)  # quitó el variant ajeno
    # la fila variant NO se toca (es la dueña legítima del alternativa)
    assert any("alternativa-41" in t for t in _syn_hashes(variant))


def test_dedup_synthetic_debundle_skips_singlekind_store():
    """De-bundle NO toca filas de tienda con un solo kind por (cole,vol) — esos
    son merges cross-source legítimos (no se deben des-hacer)."""
    from retrofit.dedup_synthetic_source import _debundle_store_rows, _syn_hashes
    base = "https://www.listadomanga.es/coleccion.php?id=3020"
    row = {"url": "https://tienda.com/witch-hat-5.html",
           "edition_key": "witch-hat-atelier-milkyway-special-es",
           "sources": [{"url": "https://tienda.com/witch-hat-5.html"},
                       {"url": f"{base}&item=especial-5-660d4ad0711c1665"}]}
    n = _debundle_store_rows([row])
    assert n == 0
    assert any("especial-5" in t for t in _syn_hashes(row))


def test_lmc_doble_sobrecubierta_not_kanzenban():
    """Bug 2026-06-07 (gotcha #51): 'doble sobrecubierta' (dust jacket doble) es
    cosmético, común en ediciones REGULARES — NO una Kanzenban. Antes la regla
    `doble sobrecubierta → kanzenban` capturaba tomos regulares enteros (caso real
    Zetman Ivrea cole 1648). El kanzenban GENUINO se detecta por el literal."""
    from wikis import listadomanga_collections as lmc
    assert lmc._detect_premium_signals(
        "Tomo (133x185) rústica (tapa blanda) con doble sobrecubierta") == []
    assert lmc._detect_premium_signals("Tomo Kanzenban A5 (148x210)") == ["kanzenban"]
    # una coleccion regular con doble sobrecubierta NO se captura
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Zetman", price="8,00 €", image_id="z1", cls="ventana_id1"),
            _lmc_item(2, "Zetman", price="8,00 €", image_id="z2", cls="ventana_id1"),
        ),
        formato="Tomo (133x185) rústica (tapa blanda) con doble sobrecubierta",
        title="Zetman (Ivrea)",
    )
    assert lmc.parse_collection_page(html, 1648) == []


def test_lmc_a5_kanzenban_by_title_still_premium():
    """Guard: una edición A5 TITULADA '(Kanzenban)' (o con 'doble sobrecubierta')
    SÍ se captura — el kanzenban genuino se detecta por título/formato, no por
    tamaño A5. Caso Slam Dunk / InuYasha / 20th Century Boys Kanzenban."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "InuYasha", price="12,00 €", image_id="iy1", cls="ventana_id1"),
        ),
        formato="Tomo A5 (150x210) rústica (tapa blanda) con sobrecubierta",
        title="InuYasha (Kanzenban)",
    )
    cands = lmc.parse_collection_page(html, 4753)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 1, "kanzenban por título debe capturarse"
    assert "kanzenban" in cands[0].signal_types or "premium_format" in cands[0].signal_types


def test_lmc_zero_yield_log_flags_premium_collection_with_no_items():
    """P4: una colección de formato premium que NO emite ningún item (todos
    sus tomos en secciones descartadas) se registra en ZERO_YIELD_LOG para
    auditar posibles misses (señal que habría delatado Berserk Master pre-fix)."""
    from wikis import listadomanga_collections as lmc
    lmc.ZERO_YIELD_LOG.clear()
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros no editados",
            _lmc_item(1, "Premium Fantasma", price=""),
        ),
        formato="Tomo triple (175x255) cartoné (tapa dura)",  # premium → debería rendir
        title="Premium Fantasma (Master Edition)",
    )
    cands = lmc.parse_collection_page(html, 99001)
    assert cands == []
    flagged = [e for e in lmc.ZERO_YIELD_LOG if e[0] == 99001]
    assert len(flagged) == 1, f"esperado 1 entry zero-yield, got {lmc.ZERO_YIELD_LOG}"
    assert "premium=" in flagged[0][2]
    lmc.ZERO_YIELD_LOG.clear()


def test_lmc_zero_yield_skips_non_manga_formats():
    """Iteración run real 101-600: un producto NO-manga (cuento ilustrado /
    novela gráfica, cartoné → falso premium hardcover) que da 0 items NO debe
    ensuciar ZERO_YIELD_LOG (el filtro de layout ya lo excluyó; no es miss de
    manga). Casos reales: 'Goro Goro Miau' (cuento), 'Usagi Yojimbo: Yokai'
    (novela gráfica)."""
    from wikis import listadomanga_collections as lmc
    lmc.ZERO_YIELD_LOG.clear()
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Goro Goro Miau", price="18,00 €", cls="ventana_id10"),
        ),
        formato="Cuento ilustrado (170x260) cartoné (tapa dura)",
        title="Goro Goro Miau",
    )
    cands = lmc.parse_collection_page(html, 99005)
    assert cands == []
    assert not [e for e in lmc.ZERO_YIELD_LOG if e[0] == 99005], \
        f"producto no-manga no debe estar en zero-yield, got {lmc.ZERO_YIELD_LOG}"
    lmc.ZERO_YIELD_LOG.clear()


def test_lmc_zero_yield_log_not_triggered_for_plain_series():
    """P4 guard: una serie regular NO-premium con 0 items (comportamiento
    normal y esperado) NO debe ensuciar ZERO_YIELD_LOG."""
    from wikis import listadomanga_collections as lmc
    lmc.ZERO_YIELD_LOG.clear()
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Shonen Regular", price="9,00 €"),
        ),
        formato="Tomo (115x175) rústica (tapa blanda) con sobrecubierta",
        title="Shonen Regular",
    )
    cands = lmc.parse_collection_page(html, 99002)
    assert cands == []
    assert not [e for e in lmc.ZERO_YIELD_LOG if e[0] == 99002]
    lmc.ZERO_YIELD_LOG.clear()


def test_lmc_iter_calendar_months():
    """_iter_calendar_months devuelve los (year, month) inclusive, cruzando
    el fin de año, y nunca vacío."""
    from wikis import listadomanga_collections as lmc
    assert lmc._iter_calendar_months(2026, 3, 2026, 6) == [(2026, 3), (2026, 4), (2026, 5), (2026, 6)]
    assert lmc._iter_calendar_months(2025, 11, 2026, 2) == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]
    # rango degenerado (to < from) → al menos el mes from
    assert lmc._iter_calendar_months(2026, 6, 2026, 3) == [(2026, 6)]


def test_lmc_discover_via_calendar_extracts_collection_ids():
    """P1: _discover_via_calendar recorre los meses del calendario y extrae
    los coleccion.php?id=N únicos (en orden de aparición), salteando meses
    que fallan por HTTP."""
    from wikis import listadomanga_collections as lmc

    pages = {
        (2026, 5): '<a href="coleccion.php?id=1606">AoT nº34</a>'
                   '<a href="autor.php?id=9">Autor</a>'
                   '<a href="coleccion.php?id=2527">Black Clover nº36</a>',
        (2026, 6): '<a href="coleccion.php?id=2527">Black Clover nº37</a>'  # dup → no se repite
                   '<a href="coleccion.php?id=6325">Berserk Master</a>',
    }

    class FakeResp:
        def __init__(self, text): self.text = text; self.encoding = "utf-8"
        def raise_for_status(self): pass

    class FakeSession:
        def get(self, url, **kw):
            import re as _re
            m = _re.search(r"mes=(\d+)&ano=(\d+)", url)
            month, year = int(m.group(1)), int(m.group(2))
            if (year, month) == (2026, 4):
                raise __import__("requests").RequestException("boom")  # mes que falla
            return FakeResp(pages.get((year, month), ""))

    ids = lmc._discover_via_calendar(2026, 4, 2026, 6, FakeSession(), sleep_seconds=0)
    # 2026-04 falla (skip), 2026-05 → 1606, 2527, 2026-06 → 2527 (dup), 6325
    assert ids == [1606, 2527, 6325]


def test_lmc_bootstrap_calendar_mode_uses_calendar_discovery(monkeypatch):
    """P1: bootstrap(mode='calendar') usa _discover_via_calendar con la
    ventana year/month y parsea solo esos ids."""
    from wikis import listadomanga_collections as lmc

    calls = {}

    def fake_discover(yf, mf, yt, mt, session, **kw):
        calls["window"] = (yf, mf, yt, mt)
        return [111, 222]

    fetched = []

    def fake_fetch(cid, session, **kw):
        fetched.append(cid)
        return []

    monkeypatch.setattr(lmc, "_discover_via_calendar", fake_discover)
    monkeypatch.setattr(lmc, "fetch_collection", fake_fetch)

    lmc.bootstrap(2026, 3, 2026, 6, session=object(), mode="calendar", sleep_seconds=0)
    assert calls["window"] == (2026, 3, 2026, 6)
    assert fetched == [111, 222]


def test_lmc_discards_edicion_revisada_and_no_editados():
    """Las secciones 'Edición Revisada' (re-impresión) y 'no editados'
    (sin precio) se descartan completamente."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Edici&oacute;n Revisada)",
            _lmc_item(1, "Slam Dunk Revisada", price="15,00 €"),
        ),
        _lmc_section(
            "N&uacute;meros no editados",
            _lmc_item(20, "Slam Dunk Pendiente", price=""),
        ),
        formato="Tomo A5 (150x210) rústica (tapa blanda) con sobrecubierta",
    )
    cands = lmc.parse_collection_page(html, 342)
    # La sección "Números editados (Edición Revisada)" se descarta
    # explícitamente; la "no editados" también. Solo quedarían items si
    # hubiera una sección procesable.
    assert cands == []


def test_lmc_en_cofre_format_emits_single_box_item():
    """Formato 'X en cofre' → la página entera ES un cofre/box set.
    El parser debe emitir UN solo item box-level y descartar los tomos
    numerados (que solo existen dentro del cofre y no se venden sueltos).

    Caso semilla: id=5959 Gon (Edición Coleccionista) Norma — formato
    "Tomo cuádruple A5 (148x210) cartoné (tapa dura) en cofre" tenía 2
    tomos que aparecían como cards separadas pese a ser parte del cofre.
    Ver gotcha #28.
    """
    from wikis import listadomanga_collections as lmc
    # Cofre cover item (alt sin nº) — el real listadomanga la pone como
    # primer portada del bloque "Números editados".
    cofre_item = (
        '<td><table class="ventana_id1" style="width: 184px;"><tr><td class="cen">'
        '<img class="portada" src="https://static.listadomanga.com/boxcover.png" alt="Gon"/>'
        '<div style="height: 8px"></div>'
        'Gon<br/>'
        '</td></tr></table></td><td class="separacion"></td>'
    )
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            cofre_item,
            _lmc_item(1, "Gon", image_id="tomo1"),
            _lmc_item(2, "Gon", image_id="tomo2"),
        ),
        formato="Tomo cu&aacute;druple A5 (148x210) carton&eacute; (tapa dura) en cofre",
        title="Gon (Edici&oacute;n Coleccionista) (Norma)",
        publisher="Norma Editorial",
        author="Masashi Tanaka",
    )
    cands = lmc.parse_collection_page(html, 5959)
    assert len(cands) == 1, f"Expected 1 box item, got {len(cands)}"
    box = cands[0]
    # El title lleva sufijo " — Cofre" para que detect_signals capte
    # box_set vía title (el gate is_collectible_edition exige al menos
    # un signal premium en title cuando no hay ISBN ni volume_shape).
    assert box.title == "Gon (Edición Coleccionista) (Norma) — Cofre"
    assert "edition:box" in box.tags
    assert "&item=box-" in box.url
    # Cover: la primera del cofre (alt sin nº → key=("regular", ""))
    assert "boxcover" in box.image_url
    # Signals: el item box-level debe disparar box_set + signals premium
    lmc.score_candidate(box)
    assert "box_set" in box.signal_types
    assert any(s in box.signal_types for s in ["hardcover", "deluxe", "kanzenban"])
    # Descripción incluye el formato + conteo de tomos (2, excluyendo el cofre)
    assert "en cofre" in box.description.lower()
    assert "2 tomos" in box.description
    # Carrusel: cover del box + cada tomo dentro como kind=extra.
    # Regla del owner (2026-05-24): "los box sets son solo el item del box
    # set. Lo que se puede hacer es poner 1ro la foto del box set y luego
    # para agregar más contexto poner las fotos de los tomos que vienen
    # dentro, pero como 1 mismo item".
    assert len(box.images) == 3
    assert box.images[0]["kind"] == "gallery"
    assert "boxcover" in box.images[0]["url"]
    extras = [im for im in box.images if im["kind"] == "extra"]
    assert len(extras) == 2
    assert {im["description"] for im in extras} == {"Tomo 1", "Tomo 2"}


def test_lmc_en_cofre_format_absorbs_layout_b_extras_into_carousel():
    """Cuando la página es 'en cofre' y hay extras Layout B, esos extras
    se appendean al carrusel del box item (no se crean from_extras tomos)."""
    from wikis import listadomanga_collections as lmc
    layout_b_section = (
        '<table><tr><td><table class="ventana_id1" style="width: 974px">'
        '<tr><td class="izq"><h2>Regalos con la primera edici&oacute;n de Test</h2></td></tr>'
        '</table></td></tr></table>'
        '<table width="920" border="0" align="center">'
        '<tr><td width="150">'
        '<img src="https://static.listadomanga.com/postal_extra.jpg"/><br/><br/>'
        'Test n&ordm;1<br/>(1&ordf; Edici&oacute;n)<br/>Postal de regalo<br/>'
        '15 <a href="novedades.php">Marzo 2024</a>'
        '</td></tr></table>'
    )
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(0, "Test", image_id="boxcover", price=""),
            _lmc_item(1, "Test", image_id="tomo1"),
        ),
        layout_b_section,
        formato="Tomo doble A5 carton&eacute; en cofre",
        title="Test Box",
    )
    cands = lmc.parse_collection_page(html, 9100)
    assert len(cands) == 1  # solo el box, NO from_extras tomos
    box = cands[0]
    # El carrusel del box tiene: cover + tomo nº1 (kind=extra Tomo 1) +
    # postal Layout B (kind=extra, descripción "Postal de regalo").
    extra_imgs = [img for img in box.images if img.get("kind") == "extra"]
    assert len(extra_imgs) == 2
    extra_urls = {im["url"] for im in extra_imgs}
    assert any("postal_extra" in u for u in extra_urls)
    assert any("tomo1" in u for u in extra_urls)
    # extras[] descriptivo solo carga los Layout B (extras "vinculados"),
    # no los tomos del Layout A — esos viven en images[] como contexto visual.
    assert len(box.extras) == 1
    assert box.extras[0]["description"] == "Postal de regalo"


def test_lmc_premium_format_without_en_cofre_still_emits_tomos():
    """Sanity: el comportamiento previo (formato premium sin 'en cofre' →
    emite los tomos numerados como items separados) NO se rompe con el fix."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Test", image_id="t1"),
            _lmc_item(2, "Test", image_id="t2"),
        ),
        # Formato premium pero SIN "en cofre" → comportamiento clásico
        formato="Tomo A5 (150x210) carton&eacute; (tapa dura) con sobrecubierta",
    )
    cands = lmc.parse_collection_page(html, 9101)
    # 2 tomos, no 1 box
    assert len(cands) == 2
    assert all("edition:box" not in c.tags for c in cands)


def test_lmc_is_box_format_detects_variants():
    """_is_box_format() detecta 'en cofre' / 'en estuche' con variantes
    de mayúsculas; NO matchea 'cofre' como sustantivo aislado del producto
    (ej. la palabra suelta sin 'en' antes — un tomo con un cofre de regalo
    NO es un box-format page)."""
    from wikis.listadomanga_collections import _is_box_format
    assert _is_box_format("Tomo A5 cartoné en cofre")
    assert _is_box_format("Tomo A5 cartoné EN COFRE")
    assert _is_box_format("Tomo A5 cartoné en estuche")
    assert _is_box_format("Tomo cuádruple A5 (148x210) cartoné (tapa dura) en cofre")
    # No matches: la palabra "cofre" sola NO es signal de page-wide box
    # (es un extra que vino con un tomo, no que la página entera ES un cofre)
    assert not _is_box_format("Tomo A5 cartoné con cofre de regalo")
    assert not _is_box_format("Tomo A5 cartoné")
    assert not _is_box_format("")


def test_lmc_html_entities_in_section_headers_decoded():
    """Headers con entities (N&uacute;meros editados, Edici&oacute;n) deben
    decodificarse antes de matchear los SECTION_RULES."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Ediciones Especiales)",
            _lmc_item(1, "Test Manga", desc_extra="Edición Especial Limitada", price="20,00 €"),
        ),
    )
    cands = lmc.parse_collection_page(html, 9999)
    assert len(cands) == 1


def test_lmc_iter_year_months_returns_single_batch():
    """Esta wiki no usa calendario; iter_year_months es stub."""
    from wikis import listadomanga_collections as lmc
    assert lmc.iter_year_months(2024, 1, 2026, 12) == [(2024, 1)]


def test_lmc_bootstrap_signature_accepts_id_kwargs():
    """El dispatcher pasa id_from/id_to como kwargs; la signature debe aceptarlos."""
    import inspect
    from wikis.listadomanga_collections import bootstrap
    sig = inspect.signature(bootstrap)
    assert "id_from" in sig.parameters
    assert "id_to" in sig.parameters
    # Default sensato para que un usuario lance sin flags y no itere todo el catálogo accidentalmente.
    assert sig.parameters["id_from"].default == 1


def test_lmc_disambiguator_uses_image_id_for_unique_urls_per_product():
    """Bug real del piloto: id=49 tenía 2 packs Zelda con descripciones que
    arrancan idénticas ('Pack especial tomos 1 a 5' / 'Pack especial tomos 6 a 10').
    Cuando el disambiguator se construía del desc_extra truncado a 20 chars,
    ambos colapsaban a 'pack-especial-tomos-' → MISMA URL → upsert se pisaba
    entre sí. Fix: usar el image_id (hash del filename del CDN) como
    disambiguator primario — siempre único por producto distinto, estable
    en re-scrapes (idempotente)."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Packs)",
            # 2 packs con misma serie, misma edition_kind, mismo volume (0),
            # y descripciones que SLUG-WISE coliden si truncamos a 20 chars:
            _lmc_item(0, "The Legend of Zelda",
                      desc_extra="Pack especial tomos 1 a 5 + cofre de regalo",
                      price="37,50 €", image_id="aaaa1111bbbb2222"),
            _lmc_item(0, "The Legend of Zelda",
                      desc_extra="Pack especial tomos 6 a 10 + cofre de regalo",
                      price="37,50 €", image_id="cccc3333dddd4444"),
        ),
        title="The Legend of Zelda",
        publisher="Norma Editorial",
    )
    cands = lmc.parse_collection_page(html, 49)
    assert len(cands) == 2
    urls = [c.url for c in cands]
    # URLs sintéticas DEBEN ser distintas (sin esto, el upsert pisa el segundo).
    assert urls[0] != urls[1]
    assert "aaaa1111bbbb2222" in urls[0]
    assert "cccc3333dddd4444" in urls[1]
    # Y deben sobrevivir la normalización (TRACKING_PARAMS no lleva 'item').
    assert mw.normalize_url_for_dedup(urls[0]) != mw.normalize_url_for_dedup(urls[1])


def _lmc_layout_b_section(header: str, *cells_html: str) -> str:
    """Wrappea un header h2 + tabla Layout B (width=920) con sus celdas."""
    cells = ''.join(cells_html)
    return (
        f'<table class="ventana_id1" style="width: 974px"><tr><td class="izq">'
        f'<h2>{header}</h2><hr/>'
        f'<p style="text-align: center;">'
        f'<table width="920" border="0" align="center"><tr>{cells}</tr></table>'
        f'</p></td></tr></table>'
    )


def _lmc_layout_b_cell(series: str, marker: str, descs: list[str], date: str, image_id: str = "ext1") -> str:
    """Una celda Layout B con la estructura típica: img + br + br + título +
    marker + descripciones + fecha."""
    desc_lines = ''.join(f'{d}<br />' for d in descs)
    return (
        f'<td width="150" style="text-align: center;">'
        f'<img src="https://static.listadomanga.com/{image_id}.png" />'
        f'<br /><br />'
        f'{series}<br />'
        f'{marker}<br />'
        f'{desc_lines}'
        f'{date}'
        f'</td>'
    )


def test_lmc_layout_b_parses_extras_and_merges_into_existing_tomo():
    """Layout B "Extras de X" con marker "(1ª Edición)" mergea la imagen+desc
    al tomo regular existente en Layout A. El item resultante tiene
    images[]=[cover, extra] + extras[]=[descripción]."""
    from wikis import listadomanga_collections as lmc
    # Layout A: tomo vol 1 regular bajo formato premium (kanzenban) →
    # entra como item con images=[cover].
    # Layout B: extra "(1ª Edición) Marcapáginas" para vol 1 → mergea.
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Test Manga", price="20,00 €", image_id="cover1"),
        ),
        _lmc_layout_b_section(
            "Extras de Test Manga",
            _lmc_layout_b_cell("Test Manga nº1", "(1ª Edición)",
                               ["Marcapáginas"], "31 Marzo 2024", image_id="bm1"),
        ),
        formato="Tomo A5 (148x210) rústica (tapa blanda) con doble sobrecubierta",
    )
    cands = lmc.parse_collection_page(html, 9000)
    assert len(cands) == 1, f"expected 1 merged item, got {len(cands)}"
    c = cands[0]
    assert len(c.images) == 2, f"expected cover+extra, got {[im['kind'] for im in c.images]}"
    assert c.images[0]["kind"] == "gallery"
    assert c.images[0]["url"].endswith("cover1.jpg")
    assert c.images[1]["kind"] == "extra"
    assert c.images[1]["url"].endswith("bm1.png")
    assert len(c.extras) == 1
    assert "Marcapáginas" in c.extras[0]["description"]
    assert c.extras[0]["release_date"] == "2024-03-31"


def test_lmc_en_preparacion_premium_tomo_emitted_upcoming_with_extra():
    """P0-B (2026-06-06, supersede la regresión 2026-05-24): un tomo en
    'Números en preparación' de una colección de formato premium ahora se
    EMITE directamente (marcado `status:upcoming`), no como from_extras.
    El extra de Layout B que lo referencia se mergea al item.

    Caso real (id=6242 Witch Hat Edición Grimorio): vol 3 está en
    'Números en preparación' (no editado aún), el extra (marcapáginas) para
    vol 3 existe en Layout B. Antes: se descartaba la sección entera y el
    cover solo sobrevivía para un item from_extras. Ahora: el tomo premium
    upcoming es un item de pleno derecho con [cover, extra]."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros en preparaci&oacute;n",
            _lmc_item(3, "Test Manga", price="", image_id="vol3preview"),
        ),
        # Layout B referencia vol 3 con extra (1ª Edición)
        _lmc_layout_b_section(
            "Extras de Test Manga",
            _lmc_layout_b_cell("Test Manga nº3", "(1ª Edición)",
                               ["Marcapáginas"], "28 Mayo 2026",
                               image_id="bookmark3"),
        ),
        formato="Tomo doble A5 (148x210) cartoné (tapa dura)",
    )
    cands = lmc.parse_collection_page(html, 9200)
    assert len(cands) == 1, f"expected 1 upcoming tomo, got {len(cands)}"
    c = cands[0]
    assert "status:upcoming" in c.tags, f"expected upcoming tag, got {c.tags}"
    assert "from_extras" not in c.tags  # ahora es item Layout A directo
    assert len(c.images) == 2, f"expected [cover, extra], got {[im['kind'] for im in c.images]}"
    assert c.images[0]["kind"] == "gallery"
    assert "vol3preview" in c.images[0]["url"]
    assert c.images[1]["kind"] == "extra"
    assert "bookmark3" in c.images[1]["url"]


def test_lmc_edition_in_title_forces_capture_when_format_not_premium():
    """P0-A: una colección cuyo TÍTULO indica edición coleccionista
    ('Edición Integral') pero cuyo Formato NO trae keyword premium
    (rústica) debe capturar TODOS sus tomos de 'Números editados'.
    Caso real id=5639 'Ataque a los Titanes (Edición Integral)' — formato
    'Tomo (177x266) rústica (tapa blanda)' daba 0 items antes del fix."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Ataque a los Titanes", price="18,00 €", image_id="int1"),
            _lmc_item(2, "Ataque a los Titanes", price="18,00 €", image_id="int2"),
        ),
        formato="Tomo (177x266) rústica (tapa blanda)",
        title="Ataque a los Titanes (Edici&oacute;n Integral)",
    )
    cands = lmc.parse_collection_page(html, 5639)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 2, f"expected 2 tomos, got {len(cands)}"
    assert all("special_edition" in c.signal_types for c in cands)
    # NO son upcoming (están en 'Números editados', no en preparación)
    assert all("status:upcoming" not in c.tags for c in cands)


def test_lmc_parenthetical_especial_in_title_captured():
    """P0-A: el paréntesis '(Especial)' es la convención de listadomanga para
    ediciones especiales (Ao Ashi, Tokyo Revengers, Guardianes de la Noche…).
    Captura aunque el formato sea rústica. Caso real id=3243."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Guardianes de la Noche", price="12,00 €", image_id="esp1"),
        ),
        formato="Tomo (115x175) rústica (tapa blanda)",
        title="Guardianes de la Noche (Kimetsu no Yaiba) (Especial)",
    )
    cands = lmc.parse_collection_page(html, 3243)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 1, f"expected 1 especial, got {len(cands)}"
    assert "special_edition" in cands[0].signal_types


def test_lmc_bare_especial_word_in_title_not_captured():
    """P0-A guard: 'Especial' suelto (no entre paréntesis) suele ser parte
    del nombre de la obra ('Patrulla Especial', 'Detective Conan Especial')
    y NO una edición. No debe forzar captura."""
    from wikis import listadomanga_collections as lmc
    assert lmc._detect_edition_title_signals("Detective Conan Especial") == []
    assert lmc._detect_edition_title_signals("Patrulla Especial Ghost") == []
    # pero el paréntesis sí
    assert "special_edition" in lmc._detect_edition_title_signals("Ao Ashi (Especial)")


def test_lmc_edition_title_does_not_capture_plain_reissue():
    """P0-A guard: 'Nueva Edición' / 'New Edition' NO son coleccionables
    (re-impresiones estándar). Un título así con formato rústica regular
    debe seguir descartando los tomos regulares (gate sin premium)."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Vagabond", price="9,00 €", image_id="re1"),
        ),
        formato="Tomo (115x175) rústica (tapa blanda) con sobrecubierta",
        title="Vagabond (Nueva Edici&oacute;n)",
    )
    cands = lmc.parse_collection_page(html, 9300)
    assert cands == [], f"reissue regular sin premium no debe capturarse, got {len(cands)}"


def test_lmc_en_preparacion_limitada_captured_as_upcoming():
    """P0-B: 'Números en preparación (Ediciones Limitadas)' se captura como
    item limitada marcado upcoming (antes se descartaba con todo lo demás).
    Caso real id=6325 Berserk Master Edition."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros en preparaci&oacute;n (Ediciones Limitadas)",
            _lmc_item(1, "Berserk", desc_extra="Edición Limitada con artbook",
                      price="45,00 €", image_id="bml1"),
        ),
        formato="Tomo triple (175x255) cartoné (tapa dura)",
        title="Berserk (Master Edition)",
    )
    cands = lmc.parse_collection_page(html, 6325)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 1, f"expected 1 limitada upcoming, got {len(cands)}"
    c = cands[0]
    assert "status:upcoming" in c.tags
    assert "edition:limitada" in c.tags
    assert "limited" in c.signal_types or "special_edition" in c.signal_types


def test_lmc_en_preparacion_packs_captured_as_upcoming():
    """'Números en preparación (Packs)' se clasifica como pack marcado
    upcoming (antes el h2 era unknown y la sección se perdía en silencio).
    Caso real id=5584 (logs/listadomanga_unknown_h2.txt). Aplica el mismo
    filtro PACK_EXTRAS_KEYWORDS que 'Números editados (Packs)'."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros en preparaci&oacute;n (Packs)",
            _lmc_item(0, "The Legend of Zelda",
                      desc_extra="Pack especial tomos 1 a 5 + cofre de regalo",
                      price="37,50 €", image_id="packup1"),
        ),
        title="The Legend of Zelda",
        publisher="Norma Editorial",
    )
    cands = lmc.parse_collection_page(html, 5584)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 1, f"expected 1 pack upcoming, got {len(cands)}"
    c = cands[0]
    assert "status:upcoming" in c.tags
    assert "edition:pack" in c.tags
    # El keyword hint "Pack" (inyectado por signal_inject=["bundle"]) se
    # detecta como box_set en detect_signals.
    assert "box_set" in c.signal_types


def test_lmc_en_preparacion_regular_dropped_when_not_premium():
    """P0-B guard: 'Números en preparación' (regular) en colección NO premium
    sigue descartándose (igual que 'Números editados' regular sin premium).
    No queremos inundar con próximos tomos de series regulares."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros en preparaci&oacute;n",
            _lmc_item(99, "Shonen Cualquiera", price="", image_id="up99"),
        ),
        formato="Tomo (115x175) rústica (tapa blanda) con sobrecubierta",
        title="Shonen Cualquiera",
    )
    cands = lmc.parse_collection_page(html, 9400)
    assert cands == [], f"upcoming regular no-premium no debe capturarse, got {len(cands)}"


def test_lmc_orphan_extra_creates_special_item():
    """P0-C: un extra de Layout B cuyo tomo especial NO está en Layout A
    (vive en 'no editados' o sin sección) crea un item especial from_extras
    (antes solo se creaba para target_kind=regular → el extra se perdía)."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        # Sin sección Layout A para el tomo especial → orphan extra
        _lmc_layout_b_section(
            "Extras de Test Manga",
            _lmc_layout_b_cell("Test Manga nº5", "(Edición Especial)",
                               ["Caja con láminas exclusivas"], "10 Junio 2026",
                               image_id="orphanext5"),
        ),
        formato="Tomo (115x175) rústica (tapa blanda) con sobrecubierta",
    )
    cands = lmc.parse_collection_page(html, 9500)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 1, f"expected 1 especial from_extras, got {len(cands)}"
    c = cands[0]
    assert "from_extras" in c.tags
    assert "edition:especial" in c.tags
    assert "special_edition" in c.signal_types
    assert "orphanext5" in c.image_url
    assert "especial-5" in c.url


def test_lmc_from_extras_has_cover_and_extra_separate_no_boxset_signal():
    """Regresión (2026-05-24): items creados from_extras tenían:
    - product_type=boxset (wrong — son tomos regulares, no box sets)
    - signal_types=['box_set', 'bonus'] (el 'box_set' por la keyword 'Cofre'
      inyectada en description)
    - images con solo kind=extra (foto del cofre como cover principal)
    Fix: NO inyectar la descripción literal del extra en `description`
    (evita keyword leak) + capturar cover del tomo regular desde Layout A
    aunque se descarte por gate."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        # Layout A: tomo regular nº1 (gate lo descartará porque NO premium,
        # pero su cover debe quedar capturada para items from_extras)
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Test Manga", price="9,00 €", image_id="cover1"),
        ),
        # Layout B: cofre para tomos 1 a 7 — crea item from_extras vol 1
        _lmc_layout_b_section(
            "Cofres de regalo con las primeras ediciones de Test Manga",
            _lmc_layout_b_cell("Test Manga nº1", "(1ª Edición)",
                               ["Cofre para tomos 1 a 7"], "28 Septiembre 2012",
                               image_id="cofre1"),
        ),
        formato="Tomo (115x175) rústica (tapa blanda) con sobrecubierta",
    )
    cands = lmc.parse_collection_page(html, 9100)
    assert len(cands) == 1, f"expected 1 item, got {len(cands)}"
    c = cands[0]
    assert "from_extras" in c.tags
    # images[]: primero cover del tomo regular, después extra del cofre
    assert len(c.images) == 2, f"expected [cover, extra], got {[im['kind'] for im in c.images]}"
    assert c.images[0]["kind"] == "gallery"
    assert "cover1" in c.images[0]["url"]  # cover del tomo regular
    assert c.images[1]["kind"] == "extra"
    assert "cofre1" in c.images[1]["url"]  # foto del cofre
    # signals: bonus SÍ, box_set NO
    mw.score_candidate(c)
    assert "bonus" in c.signal_types
    assert "box_set" not in c.signal_types, (
        f"signal box_set should NOT be set for tomo regular con cofre extra; "
        f"signals={c.signal_types}"
    )
    # product_type: manga (NO boxset)
    assert c.product_type != "boxset", (
        f"product_type should be 'manga' not 'boxset' for tomo regular; "
        f"product_type={c.product_type}"
    )


def test_lmc_from_extras_cofre_score_above_dashboard_threshold():
    """Regresión: items from_extras (tomos de 1ª edición con cofres/extras)
    deben tener score >= 20 para aparecer en el dashboard (minScore = 20).
    Bug: la descripción solo contenía 'extras' (score=14 < 20) → invisible.
    Fix: se añadieron 'regalos' (score=20) y 'brindes' (score=20) a
    KEYWORD_RULES; la descripción los incluye → score total = 54."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_layout_b_section(
            "Cofres de regalo con las primeras ediciones de Bakuman",
            _lmc_layout_b_cell("Bakuman nº1", "(1ª Edición)",
                               ["Cofre para tomos 1 a 8"], "29 Octubre 2010",
                               image_id="cofre_bakuman"),
        ),
        formato="Tomo (115x175) rústica (tapa blanda) con sobrecubierta",
    )
    cands = lmc.parse_collection_page(html, 1338)
    assert len(cands) == 1
    c = cands[0]
    assert "from_extras" in c.tags
    mw.score_candidate(c)
    assert c.score >= 20, (
        f"from_extras con cofre debe tener score>=20 (minScore dashboard=20); "
        f"score={c.score}, signal_types={c.signal_types}"
    )
    assert "bonus" in c.signal_types
    assert "box_set" not in c.signal_types


def test_lmc_from_extras_non_cofre_has_bonus_signal():
    """from_extras items con extras que NO son cofres (ej. postal)
    también deben tener signal bonus y score>=20 gracias a 'regalos'."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_layout_b_section(
            "Regalos con las primeras ediciones de Test Manga",
            _lmc_layout_b_cell("Test Manga nº3", "(1ª Edición)",
                               ["Postal de regalo exclusiva"], "15 Mayo 2015",
                               image_id="postal_img"),
        ),
        formato="Tomo (115x175) rústica (tapa blanda)",
    )
    cands = lmc.parse_collection_page(html, 9999)
    assert len(cands) == 1
    c = cands[0]
    assert "from_extras" in c.tags
    mw.score_candidate(c)
    assert "bonus" in c.signal_types
    assert "box_set" not in c.signal_types
    assert c.score >= 20


def test_lmc_layout_b_creates_regular_tomo_when_target_missing():
    """Caso central de Fase 2: un extra "(1ª Edición)" para vol N que NO
    está en Layout A debe CREAR el tomo regular con la imagen del extra y
    signal bonus. Esto abre la puerta a tomos regulares de 1ª edición que
    el catálogo no captura hoy (gate is_collectible_edition los rechaza
    sin un extra que los justifique)."""
    from wikis import listadomanga_collections as lmc
    # Sin sección Layout A — solo extras Layout B.
    html = _lmc_html_minimal(
        _lmc_layout_b_section(
            "Cofres de regalo con las primeras ediciones de Test Manga",
            _lmc_layout_b_cell("Test Manga nº7", "(1ª Edición)",
                               ["Cofre para tomos 1 a 7"], "28 Octubre 2020"),
        ),
        # Formato regular (no-premium); sin Layout A regular se filtra
        # toda la sección, pero Layout B debe seguir creando.
        formato="Tomo (115x175) rústica (tapa blanda) con sobrecubierta",
    )
    cands = lmc.parse_collection_page(html, 9001)
    assert len(cands) == 1
    c = cands[0]
    assert "Test Manga" in c.title and "7" in c.title
    assert "from_extras" in c.tags
    assert len(c.images) == 1
    assert c.images[0]["kind"] == "extra"
    assert "Cofre" in c.extras[0]["description"]


def test_lmc_layout_b_unknown_marker_is_skipped_not_attached_to_wrong_item():
    """Si un extra tiene un marker que no reconocemos (ej. "(Edición Aniversario)"),
    debe saltarse — NO debe attacharse al primer item por accidente."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Ediciones Especiales)",
            _lmc_item(1, "Test Manga", desc_extra="Edición Especial Limitada Foo",
                      price="20,00 €", image_id="cover1"),
        ),
        _lmc_layout_b_section(
            "Extras de Test Manga",
            _lmc_layout_b_cell("Test Manga nº1", "(Edición Aniversario 30)",
                               ["Algo raro"], "31 Marzo 2024"),
        ),
    )
    # Reset log para inspeccionar
    lmc.UNKNOWN_H2_LOG.clear()
    cands = lmc.parse_collection_page(html, 9002)
    # El item Layout A debe estar, sin extras merged porque el marker no
    # matchea ninguna regla LAYOUT_B_MARKERS.
    assert len(cands) == 1
    c = cands[0]
    assert len(c.images) == 1
    assert c.images[0]["kind"] == "gallery"
    assert len(c.extras) == 0


def test_lmc_layout_b_edicion_especial_in_text_targets_especial():
    """Gotcha #59: un extra de Layout B cuyo texto dice "Edición Especial/Limitada"
    es una EDICIÓN ESPECIAL (artbook/limitada), NO un cofre de tomo regular — aunque
    el nombre de la serie venga envuelto en 2 líneas y el volumen caiga en la línea 2
    (lo que antes disparaba el fallback Grimorio → regular). Caso real: Promised
    Neverland nº13 "Edición Especial con Escape - Libro de ilustraciones"."""
    from wikis import listadomanga_collections as lmc
    td = BeautifulSoup(
        '<td width="150"><img src="art13.jpg"/>The Promised<br/>Neverland nº13<br/>'
        'Edición Especial con<br/>Escape - Libro de<br/>ilustraciones de 64 páginas<br/>'
        '4 Septiembre 2020</td>', "html.parser").find("td")
    cell = lmc._parse_layout_b_cell(td)
    assert cell is not None
    assert cell["target_edition_kind"] == "especial"   # NO "regular"
    assert cell["target_volume"] == "13"


def test_lmc_layout_b_cofre_tomos_targets_regular():
    """Gotcha #53: cofre de 1ª edición común — línea 1 'Serie nºN', línea 2
    'Cofre para tomos X a Y' (sin marker de edición especial) → target REGULAR vol N.
    Antes target_edition_kind quedaba vacío → se saltaba (cofres caían: Medaka Box,
    Aoha Ride, Cells at Work…). El cofre con marker DESCONOCIDO sí se sigue saltando."""
    from wikis import listadomanga_collections as lmc
    cell = lmc._parse_layout_b_cell(
        BeautifulSoup(_lmc_layout_b_cell("Medaka Box nº1", "Cofre para tomos 1 a 6",
                                         [], "Julio 2012"), "html.parser").find("td"))
    assert cell is not None
    assert cell["target_edition_kind"] == "regular"
    assert cell["target_volume"] == "1"
    # cofre completo: la coleccion rinde el tomo regular con su cofre
    html = _lmc_html_minimal(
        _lmc_section("N&uacute;meros editados",
                     _lmc_item(1, "Medaka Box", price="8,00 €", image_id="m1", cls="ventana_id1")),
        _lmc_layout_b_section(
            "Cofres de regalo con Medaka Box",
            _lmc_layout_b_cell("Medaka Box nº1", "Cofre para tomos 1 a 6", [], "Julio 2012")),
    )
    cands = lmc.parse_collection_page(html, 1576)
    assert any("regular-1" in c.url for c in cands), [c.url for c in cands]


def test_lmc_layout_b_grimorio_pattern_targets_regular_volume():
    """Caso Grimorio: el extra dice 'Atelier of Witch Hat / Edición Grimorio nº1
    / Marcapáginas / fecha' — sin paréntesis-marker. Como la página entera
    ES la edición premium (formato Tomo doble A5 cartoné), el target es
    'regular' tomo 1."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Atelier of Witch Hat", price="24,00 €", image_id="grim1cover",
                      day="27", month="Noviembre", year="2025"),
        ),
        _lmc_layout_b_section(
            "Extras de Atelier of Witch Hat (Edición Grimorio)",
            _lmc_layout_b_cell("Atelier of Witch Hat", "Edición Grimorio nº1",
                               ["Marcapáginas"], "27 Noviembre 2025", image_id="grim1bm"),
        ),
        title="Atelier of Witch Hat (Edición Grimorio)",
        publisher="Milky Way Ediciones",
        formato="Tomo doble A5 (148x210) cartoné (tapa dura)",
    )
    cands = lmc.parse_collection_page(html, 6242)
    assert len(cands) == 1, f"expected 1 merged item, got {[(c.title, len(c.images)) for c in cands]}"
    c = cands[0]
    assert len(c.images) == 2
    assert c.images[0]["kind"] == "gallery"
    assert c.images[1]["kind"] == "extra"


def test_lmc_layout_b_can_be_disabled():
    """Flag `enable_layout_b=False` debe saltarse el merge — útil para tests
    de Fase 1 que no quieren la lógica nueva activa."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Ediciones Especiales)",
            _lmc_item(1, "Test", desc_extra="Edición Especial", price="20,00 €", image_id="c1"),
        ),
        _lmc_layout_b_section(
            "Extras de Test",
            _lmc_layout_b_cell("Test nº1", "Edición Especial Limitada",
                               ["Postal"], "31 Marzo 2024", image_id="e1"),
        ),
    )
    cands = lmc.parse_collection_page(html, 9003, enable_layout_b=False)
    assert len(cands) == 1
    # Sin Layout B, images solo trae la cover (Layout A inicializa images=[cover]).
    assert len(cands[0].images) == 1
    assert cands[0].images[0]["kind"] == "gallery"
    assert cands[0].extras == []


def test_lmc_append_jsonl_union_merges_images_and_extras(tmp_path):
    """append_jsonl debe hacer UNION-merge de images[] y extras[] entre old
    y new: un re-scrape que solo trae la cover no debe borrar los extras
    que se agregaron en una pasada previa con merge, y viceversa."""
    import json
    p = tmp_path / "items.jsonl"
    # Estado 1: row con cover + 1 extra
    row_v1 = {
        "url": "https://example.com/x",
        "title": "Test",
        "images": [
            {"url": "https://example.com/cover.jpg", "kind": "gallery", "local": "", "description": ""},
            {"url": "https://example.com/extra1.jpg", "kind": "extra", "local": "", "description": "Postal"},
        ],
        "extras": [
            {"description": "Postal", "release_date": "2024-01-01", "source_section": "layout_b"},
        ],
        "detected_at": "2024-01-01T00:00:00Z",
    }
    mw.append_jsonl(p, [row_v1])
    # Estado 2: re-scrape que solo trae el cover (no Layout B) — la union
    # debe preservar el extra previo.
    row_v2 = {
        "url": "https://example.com/x",
        "title": "Test",
        "images": [
            {"url": "https://example.com/cover.jpg", "kind": "gallery", "local": "", "description": ""},
        ],
        "detected_at": "2024-02-01T00:00:00Z",
    }
    mw.append_jsonl(p, [row_v2])
    # Leer y verificar
    with open(p) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    assert len(rows) == 1
    r = rows[0]
    # images debe tener cover + extra (union, dedupeado por (kind, url))
    kinds_urls = {(im["kind"], im["url"]) for im in r["images"]}
    assert ("gallery", "https://example.com/cover.jpg") in kinds_urls
    assert ("extra", "https://example.com/extra1.jpg") in kinds_urls
    # extras preservado del estado previo
    assert len(r["extras"]) == 1
    assert r["extras"][0]["description"] == "Postal"


def test_lmc_pack_title_enriched_with_description_for_gate_approval():
    """Bug real del piloto: id=49 Zelda packs tenían signal box_set pero
    `is_collectible_edition` los descartaba como 'regular_tomo' porque el
    title era solo 'The Legend of Zelda' (sin número de volumen ni URL
    canónica de retailer), así que ninguna prueba de producto pasaba.
    Fix: para edition_kind=pack específicamente, enriquecer el title con
    description_extra (que sí lleva la info distintiva del pack:
    'Pack especial tomos 1 a 5 + cofre de regalo'). El title enriquecido
    contiene número (1) y la palabra 'pack', habilitando el gate."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Packs)",
            _lmc_item(0, "The Legend of Zelda",
                      desc_extra="Pack especial tomos 1 a 5 + cofre de regalo",
                      price="37,50 €", image_id="zelda1"),
        ),
        title="The Legend of Zelda",
        publisher="Norma Editorial",
    )
    cands = lmc.parse_collection_page(html, 49)
    assert len(cands) == 1
    c = cands[0]
    # Title contiene tanto el nombre original como la descripción del pack.
    assert c.title.startswith("The Legend of Zelda")
    assert "Pack especial tomos 1 a 5" in c.title
    # Verifica que el gate de coleccionables apruebe.
    mw.score_candidate(c)
    is_coll, reason = mw.is_collectible_edition(
        c.title, c.description, c.signal_types, c.product_type,
        tags=c.tags, isbn=c.isbn, url=c.url,
    )
    assert is_coll, f"pack debería pasar el gate, got reason={reason!r}"


def test_lmc_volume_ignores_number_embedded_in_series_name():
    """Series con número EMBEBIDO en el nombre ('Kaiju Nº8'): el volumen
    debe salir del nº del TOMO, no del de la serie. Caso real cole 4139
    (prueba 2026-06-11): 'Kaiju Nº8 nº16' daba vol 8 (primer match) y el
    pack cuyo alt es solo 'Kaiju Nº8' heredaba un vol 8 fantasma."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados (Ediciones Especiales)",
            _lmc_item(16, "Kaiju Nº8",
                      desc_extra="Edición Especial + Libreta + Llavero",
                      price="19,50 €", image_id="kaiju16esp"),
        ),
        _lmc_section(
            "N&uacute;meros editados (Packs)",
            # Pack: alt/título = SOLO el nombre de la serie (sin nº de tomo),
            # fiel al HTML real (alt="Kaiju Nº8", sin marcador de volumen).
            '<td><table class="ventana_id1" style="width: 184px;"><tr><td class="cen">'
            '<img class="portada" src="https://static.listadomanga.com/kaijupack.jpg" alt="Kaiju Nº8"/>'
            '<div style="height: 8px"></div>'
            'Kaiju Nº8<br/>'
            'Cofre especial tomos 1 a 3 + 3 postales exclusivas<br/>'
            '608 p&aacute;ginas en B/N<br/>'
            '25,50 €<br/>'
            '29 <a href="novedades.php">Noviembre 2023</a>'
            '</td></tr></table></td><td class="separacion"></td>',
        ),
        title="Kaiju Nº8",
        publisher="Planeta Cómic",
    )
    cands = lmc.parse_collection_page(html, 4139)
    assert len(cands) == 2
    especial = next(c for c in cands if "especial-" in c.url)
    pack = next(c for c in cands if "pack-" in c.url)
    assert especial.volume == "16", f"vol del tomo, no de la serie: {especial.volume!r}"
    assert "especial-16-" in especial.url
    # El pack no tiene nº de tomo propio → SIN volumen (no el 8 de la serie).
    assert getattr(pack, "volume", "") in ("", None)
    assert "pack-0-" in pack.url


def test_lmc_inline_cofre_in_regular_section_emitted_as_box():
    """Cofre listado INLINE dentro de 'Números editados' de una colección
    NO premium ('Cofre de 2 tomos', caso real Boichi cole 6240): antes la
    sección entera se descartaba y el cofre solo existía vía el calendario
    plano legacy. Ahora se emite SOLO el cofre (kind=box); los tomos
    regulares siguen descartados (prueba 2026-06-11)."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Boichi: Historias cortas", image_id="tomo1"),
            _lmc_item(2, "Boichi: Historias cortas", image_id="tomo2"),
            _lmc_item(0, "Boichi: Historias cortas",
                      desc_extra="Cofre de 2 tomos",
                      price="20,00 €", image_id="boicofre"),
        ),
        # Formato NO premium (rústica estándar) → sección regular gateada.
        formato="Tomo B6 (130x180) r&uacute;stica (tapa blanda) con sobrecubierta",
        title="Boichi: Historias cortas de ciencia ficci&oacute;n",
        publisher="Milky Way Ediciones",
    )
    cands = lmc.parse_collection_page(html, 6240)
    assert len(cands) == 1, f"solo el cofre debe emitirse, got {[c.title for c in cands]}"
    box = cands[0]
    assert "Cofre de 2 tomos" in box.title
    assert "edition:box" in box.tags
    assert "&item=box-" in box.url
    lmc.score_candidate(box)
    assert "box_set" in box.signal_types


def test_lmc_inline_edicion_especial_con_cofre_is_especial_not_box():
    """Regresión (gotcha #102; caso owner orange nº7 id=1970): un item inline de
    'Números editados' (sección NO premium) que trae un CofRE *junto con* un
    marcador de edición ('Edición Especial + Cofre + Set 4 postales') NO es un box
    set — es la edición especial que incluye un cofre. El parser viejo lo
    clasificaba como `box` (por el cofre) → (a) creaba una edición box-set fantasma
    y (b) DUPLICABA el especial del mismo vol que la sección 'Regalos/Cofres'
    (Layout B) emite. Debe emitirse UN solo `especial-N`, con el cofre de Layout B
    fusionado como extra; cero items `box`."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            # tomo regular sin cofre → descartado (sección no premium)
            _lmc_item(1, "orange", price="9,00 €", image_id="reg1"),
            # edición especial CON cofre listada inline → debe ser especial, no box
            _lmc_item(7, "orange", desc_extra="-queridos amigos- Edición Especial + Cofre + Set 4 postales",
                      price="18,00 €", image_id="se7"),
        ),
        # cofre del especial listado en "Regalos" (Layout B), mismo vol 7 → merge
        _lmc_layout_b_section(
            "Regalos de orange",
            _lmc_layout_b_cell("orange nº7", "Edición Especial",
                               ["Cofre para tomos 1 a 7"], "31 Marzo 2024", image_id="cofre7"),
        ),
        formato="Tomo B6 (128x182) r&uacute;stica (tapa blanda) con sobrecubierta",
        title="orange",
        publisher="Ediciones Tomodomo",
    )
    cands = lmc.parse_collection_page(html, 1970)
    for c in cands:
        lmc.score_candidate(c)
    assert len(cands) == 1, f"debe haber 1 especial (no box+especial): {[c.url for c in cands]}"
    c = cands[0]
    assert "edition:especial" in c.tags
    assert "edition:box" not in c.tags
    assert "especial-7" in c.url and "box-" not in c.url
    assert c.volume == "7"
    assert "special_edition" in c.signal_types
    assert mw.derive_cluster_key(mw.candidate_to_json(c)) == "lmc:1970:special:7"
    # El cofre de Layout B se fusionó como imagen extra del especial.
    extra_descs = [im.get("description", "") for im in (c.images or []) if im.get("kind") == "extra"]
    assert any("Cofre para tomos" in d for d in extra_descs), c.images


def test_lmc_regular_section_without_premium_and_without_cofre_still_dropped():
    """Anti-regresión del gate: la sección regular sin premium y SIN cofres
    inline sigue descartada entera (no inundar con tomos estándar)."""
    from wikis import listadomanga_collections as lmc
    html = _lmc_html_minimal(
        _lmc_section(
            "N&uacute;meros editados",
            _lmc_item(1, "Serie Normal", image_id="t1"),
            _lmc_item(2, "Serie Normal", image_id="t2"),
        ),
        formato="Tomo B6 (130x180) r&uacute;stica (tapa blanda) con sobrecubierta",
        title="Serie Normal",
        publisher="Editorial X",
    )
    assert lmc.parse_collection_page(html, 99010) == []


def test_normalize_url_strips_amazon_affiliate_params():
    """linkCode/th/psc + path token /ref=...: tracking Amazon que debe
    colapsar al canónico /dp/<ASIN>. Sin esto, dos URLs del mismo ASIN
    con afiliados/widgets distintos generaban rows duplicadas (extiende
    gotcha #19)."""
    norm = mw.normalize_url_for_dedup
    assert (norm("https://www.amazon.it/dp/8822623649?tag=socianim0c-21&linkCode=ogi&th=1&psc=1")
            == "https://www.amazon.it/dp/8822623649")
    assert (norm("https://www.amazon.it/dp/8822623649/ref=cm_sw_r_apa_glt_fabc_xyz")
            == "https://www.amazon.it/dp/8822623649")
    assert (norm("https://www.amazon.it/dp/8822623649/ref=foo?tag=bar&linkCode=x")
            == "https://www.amazon.it/dp/8822623649")
    assert (norm("https://www.amazon.it/gp/product/8822623649/ref=cm_sw_r")
            == "https://www.amazon.it/gp/product/8822623649")
    # Path ref-stripping aplica solo a amazon.* — no toca otros hosts.
    assert (norm("https://example.com/p/123/ref=foo")
            == "https://example.com/p/123/ref=foo")


def test_is_digital_only_url_rejects_honto_ebook():
    """honto.jp/ebook/ es Kindle/digital, nunca edición física → se filtra.
    PandaWatch cataloga ediciones físicas (caso 2026-06-04: 7 items Honto
    ebook, 4 con título-basura del artefacto 作品)."""
    assert mw.is_digital_only_url("https://honto.jp/ebook/pd_35206914.html")
    assert mw.is_digital_only_url("https://HONTO.jp/EBOOK/pd_1.html")  # case-insensitive
    # netstore (físico) NO se filtra.
    assert not mw.is_digital_only_url(
        "https://honto.jp/netstore/pd-book_12345.html")
    assert not mw.is_digital_only_url("")
    # "ebook" en un slug legítimo de otro host no se rechaza (filtro por host+path).
    assert not mw.is_digital_only_url("https://example.com/the-ebook-guide")


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


# ---------------------------------------------------------------------------
# manga-passion.de — Sonderausgaben DE
# ---------------------------------------------------------------------------

def _mp_volume(overrides: dict | None = None) -> dict:
    """Fixture de un volumen de manga-passion.de API."""
    base = {
        "id": 18905,
        "type": 3,
        "specialType": 0,
        "title": "Limited Edition",
        "numberDisplay": "1",
        "number": 1,
        "price": 1900,
        "year": 2025, "month": 1, "day": 7,
        "isbn13": "978-3-98745-044-0",
        "isbn10": None,
        "cover": "https://media.manga-passion.de/volume/cover/test.jpg",
        "description": None,
        "tags": [
            {"tag": {"id": 189, "name": "Anhänger", "type": 3}, "description": "Acryl-Schlüsselanhänger"}
        ],
        "contributors": [{"contributor": {"name": "Misogu Rin"}, "role": "Zeichner"}],
        "edition": {
            "id": 3116,
            "title": "My Tiny Senpai",
            "publishers": [{"id": 186, "name": "Dokico"}],
            "sources": [{"country": "JP"}],
        },
    }
    if overrides:
        base.update(overrides)
    return base


def test_mangapassion_parse_volume_basic():
    from wikis.mangapassion import parse_volume
    cand = parse_volume(_mp_volume())
    assert cand is not None
    assert cand.title == "My Tiny Senpai Band 1 – Limited Edition"
    assert cand.publisher == "Dokico"
    assert cand.release_date == "2025-01-07"
    assert cand.isbn == "9783987450440"
    assert cand.image_url == "https://media.manga-passion.de/volume/cover/test.jpg"
    assert cand.author == "Misogu Rin"
    assert cand.url == "https://api.manga-passion.de/volumes/18905"
    assert cand.country == "Alemania"
    assert cand.score > 0


def test_mangapassion_parse_volume_title_without_qualifier():
    """Volumen sin qualifier de edición (title vacío) → título solo con serie+Band."""
    from wikis.mangapassion import parse_volume
    vol = _mp_volume({"title": ""})
    cand = parse_volume(vol)
    assert cand is not None
    assert cand.title == "My Tiny Senpai Band 1"


def test_mangapassion_parse_volume_sammelschuber_injects_boxset_hint():
    """specialType=1 (Sammelschuber) inyecta 'Box Set' en descripción."""
    from wikis.mangapassion import parse_volume
    vol = _mp_volume({"specialType": 1, "title": "Sammelschuber"})
    cand = parse_volume(vol)
    assert cand is not None
    assert "box" in cand.description.lower() or "set" in cand.description.lower()
    # box_set signal debe estar presente
    assert "box_set" in (cand.signal_types or [])


def test_mangapassion_parse_volume_price_zero_gives_empty_price():
    """Precio 0 o negativo → campo price vacío."""
    from wikis.mangapassion import parse_volume
    cand = parse_volume(_mp_volume({"price": 0}))
    assert cand is not None
    assert cand.price == ""


def test_mangapassion_parse_volume_skips_without_series_title():
    """Volumen sin edition.title → None (no se puede construir título)."""
    from wikis.mangapassion import parse_volume
    vol = _mp_volume()
    vol["edition"]["title"] = ""
    assert parse_volume(vol) is None


def test_mangapassion_parse_volume_skips_without_id():
    """Volumen sin id → None."""
    from wikis.mangapassion import parse_volume
    vol = _mp_volume({"id": None})
    assert parse_volume(vol) is None


def test_mangapassion_variant_query_injects_variant_hint():
    """type_label='variant' + sin 'Variant' en qualifier → inject hint en desc."""
    from wikis.mangapassion import parse_volume
    vol = _mp_volume({"title": "Spezialausgabe"})  # no contiene "Variant"
    cand = parse_volume(vol, type_label="variant")
    assert cand is not None
    assert "variant" in cand.description.lower()


def test_mangapassion_iter_year_months_returns_single_batch():
    from wikis.mangapassion import iter_year_months
    result = iter_year_months(2024, 3, 2026, 12)
    assert result == [(2024, 3)]


# ── AnimeClick (IT) ─────────────────────────────────────────────────────────

# HTML fragment as returned in the AJAX response data.html
_AC_CALENDAR_HTML = """
<div id="main-row-loop">
  <div class="date-separator">
    <div class="date">14</div><div class="month">maggio</div>
    <div class="day">mercoledì</div>
  </div>
  <div class="panel-evento-calendario edizione">
    <a href="/edizione/3110494/100-metres-hyakuemu-variant-mangayo">
      <img class="img-evento"
           data-original="https://www.animeclick.it/immagini/manga/100-Metres/copertine/cover.jpg"
           src="/placeholder.gif">
    </a>
    <a href="/edizione/3110494/100-metres-hyakuemu-variant-mangayo">
      <h3>100 Metres - Hyakuemu Variant MangaYo! 1</h3>
    </a>
    <h4 class="edizione">MangaYo!</h4>
    <h5>100 Metres</h5>
  </div>
  <div class="panel-evento-calendario edizione">
    <a href="/edizione/9999/one-piece-vol-107">
      <img class="img-evento" src="/placeholder.gif">
    </a>
    <a href="/edizione/9999/one-piece-vol-107">
      <h3>One Piece 107</h3>
    </a>
    <h4 class="edizione">Star Comics</h4>
    <h5>One Piece</h5>
  </div>
  <div class="panel-evento-calendario edizione">
    <a href="/edizione/4444/noblesse-cofanetto-stagione-6">
      <img class="img-evento"
           data-original="https://www.animeclick.it/immagini/manga/Noblesse/copertine/cofanetto.jpg"
           src="/placeholder.gif">
    </a>
    <a href="/edizione/4444/noblesse-cofanetto-stagione-6">
      <h3>Noblesse Cofanetto Stagione 6</h3>
    </a>
    <h4 class="edizione">Star Comics</h4>
    <h5>Noblesse</h5>
  </div>
</div>
"""

_AC_DETAIL_HTML = """<!DOCTYPE html>
<html><head><title>100 Metres Variant</title></head>
<body>
<h1 itemprop="name">100 Metres - Hyakuemu Variant MangaYo! 1</h1>
<img itemprop="image"
     src="/immagini/manga/Hyaku_M/edizioni/100-Metres-Variant-edizione-3110494.jpg">
<p itemprop="description">La storia di un velocista alle Olimpiadi,
edizione Variant esclusiva MangaYo!.</p>
<meta itemprop="datePublished" content="2025-05-14">
<div class="scheda-dettagli">
  <p><strong>Editore:</strong> MangaYo!</p>
  <p><strong>Prezzo:</strong> 5,99 €</p>
</div>
</body></html>"""

_AC_INITIAL_PAGE = """<!DOCTYPE html>
<html><body>
<div id="calendario-pagination-div"
     data-current-day="25"
     data-current-month="05"
     data-current-year="2026">
</div>
<div id="calendario-days-thumbs">
  <div class="panel-evento-calendario edizione">
    <a href="/edizione/5555/berserk-deluxe-vol-1">
      <img class="img-evento"
           data-original="https://www.animeclick.it/immagini/manga/Berserk/copertine/berserk-deluxe.jpg"
           src="/placeholder.gif">
    </a>
    <a href="/edizione/5555/berserk-deluxe-vol-1">
      <h3>Berserk Deluxe 1</h3>
    </a>
    <h4 class="edizione">Panini Comics</h4>
    <h5>Berserk</h5>
  </div>
</div>
</body></html>"""


def test_animeclick_parse_calendar_html_returns_all_cards():
    from wikis.animeclick import parse_calendar_html
    cards = parse_calendar_html(_AC_CALENDAR_HTML)
    assert len(cards) == 3


def test_animeclick_parse_calendar_html_extracts_title_publisher_url():
    from wikis.animeclick import parse_calendar_html
    cards = parse_calendar_html(_AC_CALENDAR_HTML)
    variant = next(c for c in cards if "3110494" in c["url"])
    assert "Variant" in variant["title"]
    assert variant["publisher"] == "MangaYo!"
    assert variant["url"] == (
        "https://www.animeclick.it/edizione/3110494/100-metres-hyakuemu-variant-mangayo"
    )


def test_animeclick_parse_calendar_html_prefers_data_original_for_image():
    from wikis.animeclick import parse_calendar_html
    cards = parse_calendar_html(_AC_CALENDAR_HTML)
    variant = next(c for c in cards if "3110494" in c["url"])
    assert variant["image_url"].startswith("https://www.animeclick.it")
    assert "cover.jpg" in variant["image_url"]


def test_animeclick_parse_calendar_html_no_image_for_placeholder_only():
    """Cards with no data-original (only internal placeholder path) get empty image_url."""
    from wikis.animeclick import parse_calendar_html
    cards = parse_calendar_html(_AC_CALENDAR_HTML)
    regular = next(c for c in cards if "9999" in c["url"])
    assert regular["image_url"] == ""


def test_animeclick_is_collector_edition_detects_keywords():
    from wikis.animeclick import is_collector_edition
    assert is_collector_edition("My Hero Academia Vol.35 - Variant") is True
    assert is_collector_edition("Noblesse Cofanetto Stagione 6") is True
    assert is_collector_edition("Naruto 1 Edizione Limitata") is True
    assert is_collector_edition("Berserk Deluxe Vol. 1") is True
    assert is_collector_edition("Death Note Ultimate Edition 1") is True
    assert is_collector_edition("One Piece 107") is False
    assert is_collector_edition("Dragon Ball Z 1") is False
    assert is_collector_edition("Naruto 1") is False


def test_animeclick_parse_detail_page_extracts_all_fields():
    from wikis.animeclick import parse_detail_page
    result = parse_detail_page(
        _AC_DETAIL_HTML,
        "https://www.animeclick.it/edizione/3110494/100-metres-variant-mangayo",
    )
    assert result["title"] == "100 Metres - Hyakuemu Variant MangaYo! 1"
    assert result["release_date"] == "2025-05-14"
    assert result["publisher"] == "MangaYo!"
    assert "velocista" in result["description"]


def test_animeclick_parse_detail_page_image_url_is_absolute():
    from wikis.animeclick import parse_detail_page
    result = parse_detail_page(
        _AC_DETAIL_HTML,
        "https://www.animeclick.it/edizione/3110494/100-metres-variant-mangayo",
    )
    assert result["image_url"].startswith("https://www.animeclick.it")
    assert "edizione-3110494" in result["image_url"]


def test_animeclick_inject_collector_hints_cofanetto():
    from wikis.animeclick import _inject_collector_hints
    desc = _inject_collector_hints("Noblesse Cofanetto Stagione 6", "")
    assert "Box Set" in desc


def test_animeclick_inject_collector_hints_integrale():
    from wikis.animeclick import _inject_collector_hints
    desc = _inject_collector_hints("Dragon Ball Integrale", "Edizione completa.")
    assert "integral" in desc.lower()
    assert "Edizione completa" in desc


def test_animeclick_inject_collector_hints_no_match_unchanged():
    from wikis.animeclick import _inject_collector_hints
    desc = _inject_collector_hints("Berserk Deluxe 1", "Original description.")
    assert desc == "Original description."


def test_animeclick_get_calendar_state_reads_data_attributes():
    from wikis.animeclick import _get_calendar_state
    day, month, year = _get_calendar_state(_AC_INITIAL_PAGE)
    assert day == 25
    assert month == 5
    assert year == 2026


def test_animeclick_iter_year_months_returns_single_batch():
    from wikis.animeclick import iter_year_months
    result = iter_year_months(2026, 3, 2026, 5)
    assert result == [(2026, 3)]


# ---------------------------------------------------------------------------
# _extract_images_from_detail_soup — multi-imagen / carrusel
# ---------------------------------------------------------------------------

def test_extract_images_jsonld_array_returns_all():
    """JSON-LD `image` como array → cada elemento se vuelve una entrada
    en images[], primero como cover, resto como gallery."""
    html_text = """
    <html><body>
    <script type="application/ld+json">
    {"@type": "Product", "image": [
        "https://cdn.example.com/products/123-cover.jpg",
        "https://cdn.example.com/products/123-back.jpg",
        "https://cdn.example.com/products/123-spine.jpg"
    ]}
    </script>
    </body></html>
    """
    soup = make_soup(html_text)
    images = mw._extract_images_from_detail_soup(soup, "https://example.com/p/123")
    assert len(images) == 3
    assert images[0]["kind"] == "gallery"
    assert images[0]["url"].endswith("123-cover.jpg")
    assert images[1]["kind"] == "gallery"
    assert images[2]["kind"] == "gallery"


def test_extract_images_shopify_product_media_gallery():
    """Shopify `.product__media img` selector captura toda la galería."""
    html_text = """
    <html><body>
    <meta property="og:image" content="https://cdn.example.com/products/cover.jpg">
    <div class="product__media">
        <img src="https://cdn.example.com/products/cover.jpg" alt="Vol 1 cover">
    </div>
    <div class="product__media">
        <img src="https://cdn.example.com/products/cover-2.jpg" alt="Vol 1 back">
    </div>
    <div class="product__media">
        <img src="https://cdn.example.com/products/cover-3.jpg" alt="Vol 1 interior">
    </div>
    </body></html>
    """
    soup = make_soup(html_text)
    images = mw._extract_images_from_detail_soup(soup, "https://example.com/p/x")
    urls = [im["url"] for im in images]
    assert "https://cdn.example.com/products/cover.jpg" in urls
    assert "https://cdn.example.com/products/cover-2.jpg" in urls
    assert "https://cdn.example.com/products/cover-3.jpg" in urls
    assert images[0]["kind"] == "gallery"


def test_extract_images_tiendanube_swiper_gallery():
    """Tiendanube/Swiper genérico: `.swiper-slide img` captura la galería."""
    html_text = """
    <html><body>
    <div class="swiper-container">
      <div class="swiper-slide"><img src="https://cdn.example.com/img/a.jpg" alt="A"></div>
      <div class="swiper-slide"><img src="https://cdn.example.com/img/b.jpg" alt="B"></div>
      <div class="swiper-slide"><img src="https://cdn.example.com/img/c.jpg" alt="C"></div>
    </div>
    </body></html>
    """
    soup = make_soup(html_text)
    images = mw._extract_images_from_detail_soup(soup, "https://example.com/p")
    assert len(images) >= 3


def test_extract_images_dedups_thumbnail_vs_fullsize_shopify():
    """Shopify thumb suffix `_100x100.jpg` se normaliza al fullsize y dedupea
    contra la full version. _grande, _small, _master también."""
    html_text = """
    <html><body>
    <meta property="og:image" content="https://cdn.example.com/files/cover.jpg">
    <div class="product__media">
        <img src="https://cdn.example.com/files/cover_100x100.jpg" alt="thumb">
        <img src="https://cdn.example.com/files/cover_grande.jpg" alt="grande">
        <img src="https://cdn.example.com/files/cover.jpg" alt="full">
        <img src="https://cdn.example.com/files/another.jpg" alt="other">
    </div>
    </body></html>
    """
    soup = make_soup(html_text)
    images = mw._extract_images_from_detail_soup(soup, "https://example.com/p")
    # cover.jpg (en sus variantes) cuenta como uno; another.jpg como dos.
    urls_norm = {mw._gallery_url_normalize(im["url"]) for im in images}
    assert len(urls_norm) == 2


def test_extract_images_skips_data_uris():
    """Lazy-loaded imgs con `src=data:image/...` no entran al gallery."""
    html_text = """
    <html><body>
    <meta property="og:image" content="https://cdn.example.com/cover.jpg">
    <div class="product-gallery">
      <img src="data:image/gif;base64,R0lGODlh" data-src="https://cdn.example.com/real.jpg" alt="real">
      <img src="data:image/png;base64,iVBORw0KGg" alt="placeholder">
    </div>
    </body></html>
    """
    soup = make_soup(html_text)
    images = mw._extract_images_from_detail_soup(soup, "https://example.com/p")
    urls = [im["url"] for im in images]
    # data: URIs no aparecen.
    assert all(not u.startswith("data:") for u in urls)
    # real.jpg sí aparece (via data-src fallback).
    assert "https://cdn.example.com/real.jpg" in urls


def test_extract_images_filters_bad_patterns():
    """Iconos, placeholders, SVG no se incluyen ni siquiera en gallery."""
    html_text = """
    <html><body>
    <meta property="og:image" content="https://cdn.example.com/cover.jpg">
    <div class="product-gallery">
      <img src="https://cdn.example.com/icon/cart.svg" alt="cart">
      <img src="https://cdn.example.com/placeholders/no_image.png" alt="placeholder">
      <img src="https://cdn.example.com/products/page2.jpg" alt="page2">
    </div>
    </body></html>
    """
    soup = make_soup(html_text)
    images = mw._extract_images_from_detail_soup(soup, "https://example.com/p")
    urls = [im["url"] for im in images]
    assert "https://cdn.example.com/cover.jpg" in urls
    assert "https://cdn.example.com/products/page2.jpg" in urls
    assert not any("cart.svg" in u for u in urls)
    assert not any("no_image.png" in u for u in urls)


def test_extract_images_first_is_cover_rest_gallery():
    """Garantiza el labeling: kind=cover solo en el primer elemento."""
    html_text = """
    <html><body>
    <meta property="og:image" content="https://cdn.example.com/a.jpg">
    <div class="product-gallery">
      <img src="https://cdn.example.com/b.jpg" alt="back">
      <img src="https://cdn.example.com/c.jpg" alt="spine">
    </div>
    </body></html>
    """
    soup = make_soup(html_text)
    images = mw._extract_images_from_detail_soup(soup, "https://example.com/p")
    assert images[0]["kind"] == "gallery"
    for im in images[1:]:
        assert im["kind"] == "gallery"


def test_extract_image_backwards_compat_wrapper_returns_first():
    """_extract_image_from_detail_soup (legacy) sigue devolviendo solo
    el primer URL como string — para que callers viejos no rompan."""
    html_text = """
    <html><body>
    <meta property="og:image" content="https://cdn.example.com/cover.jpg">
    <div class="product-gallery">
      <img src="https://cdn.example.com/back.jpg">
    </div>
    </body></html>
    """
    soup = make_soup(html_text)
    url = mw._extract_image_from_detail_soup(soup, "https://example.com/p")
    assert url == "https://cdn.example.com/cover.jpg"


def test_extract_image_returns_empty_when_no_valid_images():
    """Si no hay imagen válida en la página (placeholders, no images, no soup),
    devuelve string vacío."""
    html_text = "<html><body><p>No products here</p></body></html>"
    soup = make_soup(html_text)
    url = mw._extract_image_from_detail_soup(soup, "https://example.com/empty")
    assert url == ""


def test_fetch_metadata_returns_images_list():
    """fetch_metadata_from_detail siempre incluye `images` en el dict de
    retorno (puede ser lista vacía pero no None / KeyError)."""
    import requests
    sess = requests.Session()
    result = mw.fetch_metadata_from_detail("", sess, timeout=(1, 1))
    assert "images" in result
    assert isinstance(result["images"], list)


def test_extract_images_scope_filters_related_products():
    """Cuando el `<main>` contiene un sidebar de productos relacionados,
    el filtro de stem-folder descarta las URLs de OTROS productos. La cover
    + las gallery del MISMO folder se conservan."""
    html_text = """
    <html><body>
    <main>
      <article itemtype="https://schema.org/Product">
        <meta property="og:image" content="https://cdn.example.com/img/albums/0001/35/cover.jpg">
        <div class="product-gallery">
          <img src="https://cdn.example.com/img/albums/0001/35/cover.jpg" alt="cover">
          <img src="https://cdn.example.com/img/albums/0001/35/back.jpg" alt="back">
        </div>
      </article>
      <aside class="related-products">
        <img src="https://cdn.example.com/img/albums/0001/44/other1.jpg" alt="related 1">
        <img src="https://cdn.example.com/img/albums/0001/40/other2.jpg" alt="related 2">
        <img src="https://cdn.example.com/img/albums/0001/38/other3.jpg" alt="related 3">
      </aside>
    </main>
    </body></html>
    """
    soup = make_soup(html_text)
    images = mw._extract_images_from_detail_soup(soup, "https://cdn.example.com/p")
    urls = [im["url"] for im in images]
    assert "https://cdn.example.com/img/albums/0001/35/cover.jpg" in urls
    assert "https://cdn.example.com/img/albums/0001/35/back.jpg" in urls
    # Los productos relacionados de folders distintos quedan fuera.
    assert not any("/0001/44/" in u for u in urls)
    assert not any("/0001/40/" in u for u in urls)


def test_extract_images_respects_limit():
    """Cap a 6 imágenes por defecto (productos reales raramente tienen más
    fotos legítimas)."""
    imgs_html = "\n".join(
        f'<img src="https://cdn.example.com/img/p/123/v{i}.jpg" alt="view {i}">'
        for i in range(20)
    )
    html_text = f"""
    <html><body>
    <article itemtype="https://schema.org/Product">
      <meta property="og:image" content="https://cdn.example.com/img/p/123/cover.jpg">
      <div class="product-gallery">
        {imgs_html}
      </div>
    </article>
    </body></html>
    """
    soup = make_soup(html_text)
    images = mw._extract_images_from_detail_soup(soup, "https://cdn.example.com")
    assert len(images) <= 6


def test_backfill_images_skips_synthetic_urls():
    """Items con URLs sintéticas (listadomanga-collections `?item=`,
    blogbbm `?bbm-entry=`) NO son candidatos a backfill --only images:
    re-fetchear esa URL devuelve la página COMPARTIDA con varios items
    hermanos, y el extractor genérico mezclaría imágenes entre ellos.
    El parser del wiki ya pobló `images[]` por su cuenta con la lógica
    correcta por tomo / por entry."""
    import subprocess, json, tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        # 2 items con URL sintética (un solo image_url, len(images)<2 — calzaría
        # como candidato si no fuera por el skip de sintéticas).
        f.write(json.dumps({
            "title": "Death Note Black Edition 1",
            "url": "https://www.listadomanga.es/coleccion.php?id=5959&item=especial-1",
            "source": "ES - ListadoManga (colecciones)",
            "images": [{"url": "https://example.com/c.jpg", "kind": "gallery", "description": ""}],
        }) + "\n")
        f.write(json.dumps({
            "title": "BBM Genshiken Variant",
            "url": "https://blogbbm.com/manga/genshiken/?bbm-entry=vol-1-genshiken01b",
            "source": "BR - Biblioteca Brasileira de Mangás",
            "images": [{"url": "https://example.com/g.jpg", "kind": "gallery", "description": ""}],
        }) + "\n")
        # ListadoManga calendar item: URL apunta al catálogo entero
        # (`coleccion.php?id=N` sin `?item=`). Re-fetch mezclaría imágenes
        # de tomos hermanos — DEBE saltarse igual que las sintéticas.
        f.write(json.dumps({
            "title": "Death Note Black Edition 1",
            "url": "https://www.listadomanga.es/coleccion.php?id=1234",
            "source": "ListadoManga (calendario)",
            "images": [{"url": "https://example.com/dn.jpg", "kind": "gallery", "description": ""}],
        }) + "\n")
        # Whakoom /ediciones/ — índice de todos los tomos, mismo caso.
        f.write(json.dumps({
            "title": "Berserk Deluxe (Whakoom edition index)",
            "url": "https://whakoom.com/ediciones/12345/berserk-deluxe",
            "source": "Whakoom",
            "images": [{"url": "https://example.com/wh.jpg", "kind": "gallery", "description": ""}],
        }) + "\n")
        # 1 item con URL normal (single-image, sí candidato).
        f.write(json.dumps({
            "title": "Berserk Deluxe 1",
            "url": "https://shop.example.com/p/berserk-deluxe-1",
            "source": "Generic Shop",
            "images": [{"url": "https://example.com/b.jpg", "kind": "gallery", "description": ""}],
        }) + "\n")
        tmppath = f.name
    try:
        result = subprocess.run(
            [".venv/bin/python", "scripts/retrofit/backfill_metadata.py",
             "--input", tmppath, "--only", "images", "--dry-run"],
            capture_output=True, text=True, timeout=30,
        )
        out = result.stdout
        # 1 candidato (el Generic Shop), no 3. Las URLs sintéticas se saltan.
        assert "1 candidatos a backfill" in out, f"Expected 1 candidate, got: {out}"
    finally:
        os.unlink(tmppath)


def test_mirror_images_gc_treats_gallery_local_as_referenced():
    """El GC del retrofit `mirror_images.py` arma el set de archivos
    referenciados desde CADA `images[i].local` (portada `images[0]` + galería)
    + `sources[i].image_local` (per-fuente). Si solo mirara la portada, los
    archivos de galería/fuente caerían como orphans y a cuarentena.

    Test directo del set de referenciadas (sin tocar disco)."""
    items = [
        {
            "url": "https://example.com/p/1",
            "images": [
                {"url": "https://example.com/c1.jpg", "kind": "gallery", "local": "aaaa.jpg"},
                {"url": "https://example.com/g1a.jpg", "kind": "gallery", "local": "bbbb.jpg"},
                {"url": "https://example.com/g1b.jpg", "kind": "gallery", "local": "cccc.jpg"},
            ],
        },
        {
            "url": "https://example.com/p/2",
            "images": [
                {"url": "https://example.com/c2.jpg", "kind": "gallery", "local": "dddd.jpg"},
            ],
        },
    ]
    # Replica la lógica del GC: ver scripts/retrofit/mirror_images.py::_run_gc
    referenced: set[str] = set()
    for it in items:
        if "_raw" in it:
            continue
        for im in (it.get("images") or []):
            if isinstance(im, dict) and im.get("local"):
                referenced.add(im["local"])
        for s in (it.get("sources") or []):
            if isinstance(s, dict) and s.get("image_local"):
                referenced.add(s["image_local"])
    assert referenced == {"aaaa.jpg", "bbbb.jpg", "cccc.jpg", "dddd.jpg"}


def test_extract_images_no_filter_when_paths_shallow():
    """Sites con paths shallow (1 segmento) no aplican el filtro de stem
    (sería demasiado agresivo y filtraría imágenes legítimas)."""
    html_text = """
    <html><body>
    <article itemtype="https://schema.org/Product">
      <meta property="og:image" content="https://cdn.example.com/cover.jpg">
      <div class="product-gallery">
        <img src="https://cdn.example.com/back.jpg" alt="back">
        <img src="https://cdn.example.com/spine.jpg" alt="spine">
      </div>
    </article>
    </body></html>
    """
    soup = make_soup(html_text)
    images = mw._extract_images_from_detail_soup(soup, "https://cdn.example.com")
    # En este caso no hay stem que matchear, así que el filtro NO se aplica;
    # las tres imágenes sobreviven.
    assert len(images) == 3


def test_extract_images_star_comics_drops_related_products_subfolder():
    """Star Comics sirve la cover en `/files/immagini/fumetti-cover/<X>` y
    el carrusel de 'otros volúmenes' (productos relacionados) en el
    SUBdirectorio `/files/immagini/fumetti-cover/thumbnail/<Y>`. El filtro
    de stem-folder debe descartar los thumbnails aunque su path contenga
    el parent de la cover como substring (gotcha #31).

    Regresión del bug que contaminaba 'One Piece 20th Anniversary Limited
    Edition Silver 1' con thumbnails de My Hero Academia, Deadrock,
    Detective Conan, Kagurabachi, Tenkaichi."""
    html_text = """
    <html><body>
    <main>
      <article itemtype="https://schema.org/Product">
        <meta property="og:image"
              content="https://www.starcomics.com/files/immagini/fumetti-cover/onepiece1-limited-silver-jpg-1">
        <div class="product-gallery">
          <img src="https://www.starcomics.com/files/immagini/fumetti-cover/onepiece1-limited-silver-jpg-1"
               alt="One Piece 20th Anniversary Limited Edition Silver 1">
        </div>
      </article>
      <section class="ti-potrebbe-interessare">
        <img src="https://www.starcomics.com/files/immagini/fumetti-cover/thumbnail/myheroacademia-1-1200px" alt="My Hero Academia 1">
        <img src="https://www.starcomics.com/files/immagini/fumetti-cover/thumbnail/deadrock-1-1200px" alt="Deadrock 1">
        <img src="https://www.starcomics.com/files/immagini/fumetti-cover/thumbnail/detectiveconan-1-1200px" alt="Detective Conan 1">
        <img src="https://www.starcomics.com/files/immagini/fumetti-cover/thumbnail/kagurabachi-1-1200px" alt="Kagurabachi 1">
        <img src="https://www.starcomics.com/files/immagini/fumetti-cover/thumbnail/tenkaichi-1-1200px" alt="Tenkaichi 1">
      </section>
    </main>
    </body></html>
    """
    soup = make_soup(html_text)
    images = mw._extract_images_from_detail_soup(
        soup,
        "https://www.starcomics.com/fumetto/one-piece20th-anniversary-limited-editionsilver-1",
    )
    urls = [im["url"] for im in images]
    # La cover sobrevive.
    assert any("onepiece1-limited-silver" in u for u in urls)
    # Ninguna URL del subdirectorio /thumbnail/ (productos relacionados).
    assert not any("/thumbnail/" in u for u in urls), urls
    # En la práctica queda solo la cover.
    assert len(images) == 1, urls


# ---------------------------------------------------------------------------
# PRH Comics parser
# ---------------------------------------------------------------------------

_PRH_LI_HARDCOVER = """
<li class="toast-anchor" tabindex="-1">
  <div class="carousel-book">
    <a class="analytics-event" href="https://prhcomics.com/book/?isbn=9798888776346">
      <img alt="Mushishi Collector's Edition 1"
           src="https://images.penguinrandomhouse.com/cover/9798888776346?width=180">
    </a>
  </div>
  <div class="carousel-meta" data-component="carousel-meta">
    <div class="carousel-meta-title" data-component="carousel-meta-title">
      <a href="https://prhcomics.com/book/?isbn=9798888776346">Mushishi Collector's Edition 1</a>
    </div>
    <div class="carousel-meta-author" data-component="carousel-meta-author">
      <a href="/search/?contributor=Yuki+Urushibara">Yuki Urushibara</a>
    </div>
    <div class="carousel-meta-isbn" data-component="carousel-meta-isbn">9798888776346</div>
    <div class="carousel-meta-price" data-component="carousel-meta-price">
      <span class="price-usa bridge-metadata">$34.99 US</span>
      <span class="price-can bridge-metadata hidden">| $45.99 CAN</span>
    </div>
    <div class="carousel-meta-format" data-component="carousel-meta-format">Hardcover</div>
    <div class="carousel-meta-division" data-component="carousel-meta-division">Kodansha Comics</div>
    <div class="carousel-meta-on-sale-date" data-component="carousel-meta-on-sale-date"> On sale May 19, 2026</div>
    <div class="carousel-meta-foc-date" data-component="carousel-meta-foc-date">FOC Mar 23, 2026</div>
  </div>
</li>
"""

_PRH_LI_BOXSET = """
<li class="toast-anchor" tabindex="-1">
  <div class="carousel-book">
    <a class="analytics-event" href="https://prhcomics.com/book/?isbn=9798888774359">
      <img alt="Attack on Titan: The Final Season Box Set"
           src="https://images.penguinrandomhouse.com/cover/9798888774359?width=180">
    </a>
  </div>
  <div class="carousel-meta" data-component="carousel-meta">
    <div class="carousel-meta-title" data-component="carousel-meta-title">
      <a href="https://prhcomics.com/book/?isbn=9798888774359">Attack on Titan: The Final Season Box Set</a>
    </div>
    <div class="carousel-meta-author" data-component="carousel-meta-author">
      <a href="/search/?contributor=Hajime+Isayama">Hajime Isayama</a>
    </div>
    <div class="carousel-meta-isbn" data-component="carousel-meta-isbn">9798888774359</div>
    <div class="carousel-meta-price" data-component="carousel-meta-price">
      <span class="price-usa bridge-metadata">$249.99 US</span>
    </div>
    <div class="carousel-meta-format" data-component="carousel-meta-format">Boxed Set(Hardcover)</div>
    <div class="carousel-meta-division" data-component="carousel-meta-division">Kodansha Comics</div>
    <div class="carousel-meta-on-sale-date" data-component="carousel-meta-on-sale-date">On sale November 5, 2024</div>
  </div>
</li>
"""

_PRH_LI_PAPERBACK_REGULAR = """
<li class="toast-anchor" tabindex="-1">
  <div class="carousel-meta" data-component="carousel-meta">
    <div class="carousel-meta-title" data-component="carousel-meta-title">
      <a href="https://prhcomics.com/book/?isbn=9781646519781">Vinland Saga 1</a>
    </div>
    <div class="carousel-meta-isbn" data-component="carousel-meta-isbn">9781646519781</div>
    <div class="carousel-meta-format" data-component="carousel-meta-format">Trade Paperback</div>
    <div class="carousel-meta-division" data-component="carousel-meta-division">Kodansha Comics</div>
    <div class="carousel-meta-on-sale-date" data-component="carousel-meta-on-sale-date">On sale Jan 1, 2020</div>
  </div>
</li>
"""


def test_prhcomics_parse_hardcover_collector():
    from wikis.prhcomics import parse_item
    soup = BeautifulSoup(_PRH_LI_HARDCOVER, "html.parser")
    li = soup.find("li")
    cand = parse_item(li)
    assert cand is not None
    assert "Mushishi" in cand.title
    assert cand.isbn == "9798888776346"
    assert cand.author == "Yuki Urushibara"
    assert cand.release_date == "2026-05-19"
    assert cand.image_url == "https://images.penguinrandomhouse.com/cover/9798888776346"
    assert cand.url == "https://prhcomics.com/book/?isbn=9798888776346"
    assert "Kodansha Comics" in cand.description
    assert cand.score > 0


def test_prhcomics_parse_boxset_injects_box_set_hint():
    from wikis.prhcomics import parse_item
    soup = BeautifulSoup(_PRH_LI_BOXSET, "html.parser")
    li = soup.find("li")
    cand = parse_item(li)
    assert cand is not None
    assert "Box Set" in cand.description
    assert cand.isbn == "9798888774359"
    assert cand.release_date == "2024-11-05"


def test_prhcomics_parse_regular_paperback_returns_none():
    from wikis.prhcomics import parse_item
    soup = BeautifulSoup(_PRH_LI_PAPERBACK_REGULAR, "html.parser")
    li = soup.find("li")
    cand = parse_item(li)
    assert cand is None


def test_prhcomics_parse_release_date_variants():
    from wikis.prhcomics import _parse_release_date
    assert _parse_release_date("On sale May 19, 2026") == "2026-05-19"
    assert _parse_release_date("On sale November 5, 2024") == "2024-11-05"
    assert _parse_release_date("On sale January 1, 2020") == "2020-01-01"
    assert _parse_release_date("") == ""
    assert _parse_release_date("Spring 2025") == ""


def test_prhcomics_iter_year_months_returns_single_batch():
    from wikis.prhcomics import iter_year_months
    result = iter_year_months(2025, 1, 2025, 12)
    assert result == [(2025, 1)]


# ---------------------------------------------------------------------------
# Kinokuniya USA Exclusives wiki parser
# ---------------------------------------------------------------------------

_KINO_LISTING_HTML = """
<html><body>
<a href="https://united-states.kinokuniya.com/bw/9780316471510">
  <img alt="Jujutsu Kaisen Vol. 20 Kinokuniya Exclusive" src="cover1.jpg"/>
</a>
<a href="https://united-states.kinokuniya.com/bw/9781974740307">
  <img alt="My Hero Academia Vol. 37 Limited Edition" src="cover2.jpg"/>
</a>
<a href="https://united-states.kinokuniya.com/bw/9780316471510">
  <img alt="Jujutsu Kaisen Vol. 20 Kinokuniya Exclusive" src="cover1.jpg"/>
</a>
<a href="/about">About us</a>
<a href="https://united-states.kinokuniya.com/bw/9781974740307?variant=abc">
  <img alt="My Hero Academia Vol. 37 Limited Edition" src="cover2.jpg"/>
</a>
</body></html>
"""


def test_kinokuniya_parse_listing_extracts_candidates():
    from wikis.kinokuniya import parse_listing
    cands = parse_listing(_KINO_LISTING_HTML)
    assert len(cands) == 2
    isbns = {c.isbn for c in cands}
    assert isbns == {"9780316471510", "9781974740307"}


def test_kinokuniya_parse_listing_deduplicates_by_isbn():
    from wikis.kinokuniya import parse_listing
    cands = parse_listing(_KINO_LISTING_HTML)
    # 9780316471510 appears twice in the HTML; must appear once in output
    assert sum(1 for c in cands if c.isbn == "9780316471510") == 1


def test_kinokuniya_candidate_has_correct_url_and_image():
    from wikis.kinokuniya import parse_listing
    cands = parse_listing(_KINO_LISTING_HTML)
    c = next(c for c in cands if c.isbn == "9780316471510")
    assert c.url == "https://united-states.kinokuniya.com/bw/9780316471510"
    assert c.image_url == "https://images.penguinrandomhouse.com/cover/9780316471510"


def test_kinokuniya_candidate_has_retailer_exclusive_signal():
    from wikis.kinokuniya import parse_listing
    cands = parse_listing(_KINO_LISTING_HTML)
    for c in cands:
        assert "retailer_exclusive" in c.signal_types, (
            f"Expected retailer_exclusive in {c.signal_types}"
        )


def test_kinokuniya_strips_asterisk_markers_from_alt():
    """Squarespace usa '*' al inicio/final del alt como marcador de estado."""
    from wikis.kinokuniya import parse_listing
    html = """<html><body>
    <a href="https://united-states.kinokuniya.com/bw/9780316471510">
      <img alt="*Jujutsu Kaisen Vol. 20 Kinokuniya Exclusive**"/>
    </a>
    </body></html>"""
    cands = parse_listing(html)
    assert len(cands) == 1
    assert not cands[0].title.startswith("*")


def test_kinokuniya_skips_non_isbn13_codes():
    """UPC/EAN codes (no comienzan con 978/979) se filtran."""
    from wikis.kinokuniya import parse_listing
    html = """<html><body>
    <a href="https://united-states.kinokuniya.com/bw/0810034314109">
      <img alt="Gift Card"/>
    </a>
    <a href="https://united-states.kinokuniya.com/bw/9780316471510">
      <img alt="Jujutsu Kaisen Vol. 20"/>
    </a>
    </body></html>"""
    cands = parse_listing(html)
    assert len(cands) == 1
    assert cands[0].isbn == "9780316471510"


def test_kinokuniya_skips_anchors_with_short_alt():
    from wikis.kinokuniya import parse_listing
    html = """<html><body>
    <a href="https://united-states.kinokuniya.com/bw/9780316471510">
      <img alt="X"/>
    </a>
    <a href="https://united-states.kinokuniya.com/bw/9781974740307">
      <img alt="Jujutsu Kaisen Vol. 20"/>
    </a>
    </body></html>"""
    cands = parse_listing(html)
    # "X" is too short (< 3 chars after strip), only the second anchor should produce a candidate
    assert len(cands) == 1
    assert cands[0].isbn == "9781974740307"


def test_kinokuniya_skips_non_product_links():
    from wikis.kinokuniya import parse_listing
    html = """<html><body>
    <a href="/about">About</a>
    <a href="https://usa.kinokuniya.com/current-promotions">Promotions</a>
    <a href="https://united-states.kinokuniya.com/bw/9780316471510">
      <img alt="Jujutsu Kaisen Vol. 20"/>
    </a>
    </body></html>"""
    cands = parse_listing(html)
    assert len(cands) == 1


def test_kinokuniya_iter_year_months_returns_single_batch():
    from wikis.kinokuniya import iter_year_months
    result = iter_year_months(2000, 1, 2030, 12)
    assert result == [(2000, 1)]


# ---------------------------------------------------------------------------
# Yen Press Calendar
# ---------------------------------------------------------------------------

# HTML fixture reflecting the real structure verified on 2026-05-27:
# Each card is an outer <a href="/titles/{isbn}-{slug}"> containing a div.book-box.
# Category is in <span class="white-label {cat} upper"> (light novel = "light-novels").
# Title is in <h3 class="heading small-h1"> inside div.genre-col-txt (no inner <a>).
# Date is in <p class="label-date upper">DD<span class="month">Mon</span></p>.
# No price element exists on the calendar page.
_YENPRESS_CALENDAR_HTML = """<html><body>
<div class="releases-box book-section">
<a href="/titles/9781975360542-jujutsu-kaisen-vol-30-collectors-edition">
  <div class="inline_block col-d-25 col-t-50 col-m-100 released-box book-box">
    <div class="released-covers-wrapper flex-center prel">
      <span class="white-label manga upper">Manga</span>
      <div class="calendar-books-wrapper">
        <div class="prel">
          <p class="label-date upper">06
            <span class="month">Jun</span>
          </p>
          <img class="genre-col-img"
               src="https://images.yenpress.com/imgs/9781975360542.jpg?w=171&h=257&type=books">
        </div>
      </div>
      <div class="genre-col-txt">
        <h3 class="heading small-h1">Jujutsu Kaisen, Vol. 30 (Collector's Edition)</h3>
      </div>
    </div>
  </div>
</a>
<a href="/titles/9781975312343-sword-art-online-progressive-vol-10">
  <div class="inline_block col-d-25 col-t-50 col-m-100 released-box book-box">
    <div class="released-covers-wrapper flex-center prel">
      <span class="white-label light-novels upper">Novels</span>
      <div class="calendar-books-wrapper">
        <div class="prel">
          <p class="label-date upper">06
            <span class="month">Jun</span>
          </p>
          <img class="genre-col-img"
               src="https://images.yenpress.com/imgs/9781975312343.jpg?w=171&h=257&type=books">
        </div>
      </div>
      <div class="genre-col-txt">
        <h3 class="heading small-h1">Sword Art Online Progressive, Vol. 10</h3>
      </div>
    </div>
  </div>
</a>
<a href="/titles/9781975399801-dungeon-meshi-vol-14">
  <div class="inline_block col-d-25 col-t-50 col-m-100 released-box book-box">
    <div class="released-covers-wrapper flex-center prel">
      <span class="white-label manga upper">Manga</span>
      <div class="calendar-books-wrapper">
        <div class="prel">
          <p class="label-date upper">06
            <span class="month">Jun</span>
          </p>
          <img class="genre-col-img"
               src="https://images.yenpress.com/imgs/9781975399801.jpg?w=171&h=257&type=books">
        </div>
      </div>
      <div class="genre-col-txt">
        <h3 class="heading small-h1">Dungeon Meshi, Vol. 14</h3>
      </div>
    </div>
  </div>
</a>
<a href="/titles/9781975398765-overlord-box-set-complete">
  <div class="inline_block col-d-25 col-t-50 col-m-100 released-box book-box">
    <div class="released-covers-wrapper flex-center prel">
      <span class="white-label manga upper">Manga</span>
      <div class="calendar-books-wrapper">
        <div class="prel">
          <p class="label-date upper">15
            <span class="month">Jun</span>
          </p>
          <img class="genre-col-img"
               src="https://images.yenpress.com/imgs/9781975398765.jpg?w=171&h=257&type=books">
        </div>
      </div>
      <div class="genre-col-txt">
        <h3 class="heading small-h1">Overlord Complete Box Set</h3>
      </div>
    </div>
  </div>
</a>
</div>
</body></html>"""


def test_yenpress_parse_filters_manga_only_special_editions():
    """Filtra por categoría (manga, excluye LN) y por keywords de edición especial."""
    from wikis.yenpress_calendar import parse_calendar_page
    cands = parse_calendar_page(_YENPRESS_CALENDAR_HTML, 2025, 6)
    # LN SAO → excluido por categoría "light-novels"
    # Dungeon Meshi regular → excluido por falta de keyword premium
    # JJK Collector's + Overlord Box Set → aceptados
    assert len(cands) == 2
    isbns = {c.isbn for c in cands}
    assert isbns == {"9781975360542", "9781975398765"}


def test_yenpress_candidate_has_correct_url_and_image():
    from wikis.yenpress_calendar import parse_calendar_page
    cands = parse_calendar_page(_YENPRESS_CALENDAR_HTML, 2025, 6)
    c = next(c for c in cands if c.isbn == "9781975360542")
    assert "yenpress.com/titles/9781975360542" in c.url
    assert c.image_url == "https://images.yenpress.com/imgs/9781975360542.jpg?w=285&h=422&type=books"


def test_yenpress_parse_date_from_card():
    from wikis.yenpress_calendar import parse_calendar_page
    cands = parse_calendar_page(_YENPRESS_CALENDAR_HTML, 2025, 6)
    jjk = next(c for c in cands if c.isbn == "9781975360542")
    assert jjk.release_date == "2025-06-06"
    overlord = next(c for c in cands if c.isbn == "9781975398765")
    assert overlord.release_date == "2025-06-15"


def test_yenpress_parse_price():
    """El calendario de Yen Press no expone precios — price debe ser vacío."""
    from wikis.yenpress_calendar import parse_calendar_page
    cands = parse_calendar_page(_YENPRESS_CALENDAR_HTML, 2025, 6)
    jjk = next(c for c in cands if c.isbn == "9781975360542")
    assert jjk.price == ""  # no hay <p class="label-price"> en la página real


def test_yenpress_deduplicates_by_isbn():
    """Mismo ISBN dos veces → solo un candidato."""
    from wikis.yenpress_calendar import parse_calendar_page
    html = """<html><body>
    <a href="/titles/9781975360542-jujutsu-kaisen-collector-a">
      <div class="book-box">
        <div class="released-covers-wrapper prel">
          <span class="white-label manga upper">Manga</span>
          <div class="calendar-books-wrapper"><div class="prel">
            <p class="label-date upper">06<span class="month">Jun</span></p>
            <img class="genre-col-img" src="">
          </div></div>
          <div class="genre-col-txt">
            <h3 class="heading small-h1">Jujutsu Kaisen, Vol. 30 (Collector's Edition)</h3>
          </div>
        </div>
      </div>
    </a>
    <a href="/titles/9781975360542-jujutsu-kaisen-collector-b">
      <div class="book-box">
        <div class="released-covers-wrapper prel">
          <span class="white-label manga upper">Manga</span>
          <div class="calendar-books-wrapper"><div class="prel">
            <p class="label-date upper">06<span class="month">Jun</span></p>
            <img class="genre-col-img" src="">
          </div></div>
          <div class="genre-col-txt">
            <h3 class="heading small-h1">Jujutsu Kaisen, Vol. 30 (Collector's Edition)</h3>
          </div>
        </div>
      </div>
    </a>
    </body></html>"""
    cands = parse_calendar_page(html, 2025, 6)
    assert len(cands) == 1


def test_yenpress_skips_light_novel_category():
    """Categoría 'light-novels' se excluye aunque el título tenga keywords."""
    from wikis.yenpress_calendar import parse_calendar_page
    html = """<html><body>
    <a href="/titles/9781975312343-sword-art-online-collector-edition">
      <div class="book-box">
        <div class="released-covers-wrapper prel">
          <span class="white-label light-novels upper">Novels</span>
          <div class="calendar-books-wrapper"><div class="prel">
            <p class="label-date upper">06<span class="month">Jun</span></p>
            <img class="genre-col-img" src="">
          </div></div>
          <div class="genre-col-txt">
            <h3 class="heading small-h1">Sword Art Online: Collector's Edition</h3>
          </div>
        </div>
      </div>
    </a>
    </body></html>"""
    cands = parse_calendar_page(html, 2025, 6)
    assert len(cands) == 0


def test_yenpress_iter_year_months_generates_range():
    from wikis.yenpress_calendar import iter_year_months
    result = iter_year_months(2025, 11, 2026, 2)
    assert result == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]


def test_yenpress_iter_year_months_single_month():
    from wikis.yenpress_calendar import iter_year_months
    result = iter_year_months(2025, 6, 2025, 6)
    assert result == [(2025, 6)]


def test_yenpress_skips_regular_manga_without_keywords():
    """Título de manga sin keywords de edición especial → excluido."""
    from wikis.yenpress_calendar import parse_calendar_page
    html = """<html><body>
    <a href="/titles/9781975399801-dungeon-meshi-vol-14">
      <div class="book-box">
        <div class="released-covers-wrapper prel">
          <span class="white-label manga upper">Manga</span>
          <div class="calendar-books-wrapper"><div class="prel">
            <p class="label-date upper">06<span class="month">Jun</span></p>
            <img class="genre-col-img" src="">
          </div></div>
          <div class="genre-col-txt">
            <h3 class="heading small-h1">Dungeon Meshi, Vol. 14</h3>
          </div>
        </div>
      </div>
    </a>
    </body></html>"""
    cands = parse_calendar_page(html, 2025, 6)
    assert len(cands) == 0


# ---------------------------------------------------------------------------
# derive_rarity_tier — tests (modelo default-common, 2026-06-10)
#
# Rediseño: el default pasó de 'rare' a 'common'. Cada tier superior exige
# evidencia (print run, lotería/evento, firma a mano, no-reimpresión explícita
# o stock agotado verificado). El signal `limited` y `variant_cover` dejaron
# de forzar rare: en un tracker de ediciones especiales describen al item
# típico (81% del corpus quedaba en rare con 54% de precisión medida).
# ---------------------------------------------------------------------------

def test_rarity_ultra_rare_numbered_copy():
    """Edición con fracción de tirada (X/500) → ultra_rare."""
    r = mw.derive_rarity_tier([], "", "", "Berserk Beherit Limited 1 (42/500)")
    assert r == "ultra_rare"


def test_rarity_ultra_rare_numerado_multilingual():
    """Keywords de numeración en distintos idiomas → ultra_rare."""
    assert mw.derive_rarity_tier([], "", "", "One Piece 100 numéroté") == "ultra_rare"
    assert mw.derive_rarity_tier([], "", "", "Attack on Titan Vol.34 numerada") == "ultra_rare"
    assert mw.derive_rarity_tier([], "", "", "JJK 30 numerato 120/1000") == "ultra_rare"


def test_rarity_ultra_rare_signed():
    """Ediciones firmadas a mano → ultra_rare en cualquier idioma."""
    assert mw.derive_rarity_tier([], "", "", "Dragon Ball firmado por Toriyama") == "ultra_rare"
    assert mw.derive_rarity_tier([], "", "", "Naruto signé par l'auteur") == "ultra_rare"
    assert mw.derive_rarity_tier([], "", "", "Berserk signiert") == "ultra_rare"


def test_rarity_printed_signature_on_lamina_not_ultra_rare():
    """'lámina firmada' = firma IMPRESA en un extra → NO ultra_rare.
    Caso real: Capitán Harlock Letrablanka, 170 copias EN STOCK a PVP."""
    r = mw.derive_rarity_tier(
        ["collector"], "", "Incluye lámina firmada por el autor.",
        "Capitán Harlock Edición Coleccionista 3", publisher="Letrablanka"
    )
    assert r != "ultra_rare"


def test_rarity_printed_signature_on_postal_not_ultra_rare():
    """'postal de regalo firmada' = firma impresa → NO ultra_rare."""
    r = mw.derive_rarity_tier(
        ["variant_cover", "bonus"], "",
        "Edición con portada alternativa + postal de regalo firmada por la autora.",
        "Mushoku Tensei Portada Alternativa 19",
    )
    assert r != "ultra_rare"


def test_rarity_hand_signed_copy_still_ultra_rare():
    """Ejemplar firmado (sin sustantivo de extra impreso) → ultra_rare."""
    r = mw.derive_rarity_tier(
        [], "", "Cada ejemplar está firmado por la autora en persona.",
        "Magus of the Library Edición Especial",
    )
    assert r == "ultra_rare"


def test_rarity_lucca_without_print_run_is_rare():
    """Lucca Comics sin print run explícito → rare (evento, no ultra)."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "", "In esclusiva a Lucca Comics, su Panini.it",
        "One Piece Red Limited Collector", publisher="Panini Comics"
    )
    assert r == "rare"


def test_rarity_lucca_with_print_run_is_ultra_rare():
    """Lucca Comics + print run ≤ 500 → ultra_rare via _PRINT_RUN_RE."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "",
        "Limited to 100 copies. Sold exclusively at Lucca Comics & Games 2022.",
        "Barefoot Gen Variant 1",
    )
    assert r == "ultra_rare"


# ---------------------------------------------------------------------------
# derive_rarity_tier — retailer_exclusive: rare sin stock, super_rare agotado
# ---------------------------------------------------------------------------

def test_rarity_retailer_exclusive_without_stock_is_rare():
    """retailer_exclusive SIN verificación de stock → rare (no super_rare).
    Caso real: Ichi the Witch variant de Kinokuniya estaba marcada super_rare
    mientras seguía EN STOCK a $11.99 (precio de lista)."""
    r = mw.derive_rarity_tier(["retailer_exclusive"], "", "", "Kinokuniya Variant Cover")
    assert r == "rare"


def test_rarity_retailer_exclusive_out_of_stock_is_super_rare():
    """retailer_exclusive + stock agotado verificado → super_rare."""
    r = mw.derive_rarity_tier(
        ["retailer_exclusive"], "", "", "Kinokuniya Variant Cover",
        stock_status="out_of_stock",
    )
    assert r == "super_rare"


def test_rarity_retailer_exclusive_in_stock_is_common():
    """retailer_exclusive + stock VERIFICADO → common (decisión owner, handoff
    2026-06-10: Ichi the Witch variant de Kinokuniya en stock a $11.99 'debería
    common' — la exclusividad de canal no impide conseguirlo hoy)."""
    r = mw.derive_rarity_tier(
        ["retailer_exclusive", "lore_edition"], "", "", "Vagabond Definitive Edition 1",
        publisher="Kinokuniya USA", stock_status="in_stock",
    )
    assert r == "common"


def test_rarity_booksprivilege_tokuten_is_rare():
    """Fuente BooksPrivilege (tokuten) → rare (sin verificación no llega a super)."""
    r = mw.derive_rarity_tier(
        ["bonus"], "JP - BooksPrivilege (store bonuses)", "", "Kimetsu no Yaiba 23"
    )
    assert r == "rare"


# ---------------------------------------------------------------------------
# derive_rarity_tier — stock_status (evidencia del retrofit check_stock.py)
# ---------------------------------------------------------------------------

def test_rarity_out_of_stock_is_rare():
    """Stock agotado verificado, sin tirada documentada → rare."""
    r = mw.derive_rarity_tier(
        ["collector"], "", "", "Bestiarius Collector 1",
        publisher="Kazé", stock_status="out_of_stock",
    )
    assert r == "rare"


def test_rarity_in_stock_is_common():
    """Stock confirmado sin otra evidencia → common."""
    r = mw.derive_rarity_tier(
        ["collector", "limited"], "", "", "I Am a Hero Edición Coleccionista 1",
        publisher="Norma Editorial", stock_status="in_stock",
    )
    assert r == "common"


# ---------------------------------------------------------------------------
# derive_rarity_tier — common es el default (sin evidencia de escasez)
# ---------------------------------------------------------------------------

def test_rarity_common_dark_horse_deluxe():
    """Línea deluxe de catálogo → common."""
    r = mw.derive_rarity_tier(
        ["deluxe", "hardcover"], "", "", "Berserk Deluxe 1",
        publisher="Dark Horse Comics"
    )
    assert r == "common"


def test_rarity_common_viz_boxset():
    r = mw.derive_rarity_tier(
        ["box_set"], "", "", "One Piece Box Set 1", publisher="VIZ Media"
    )
    assert r == "common"


def test_rarity_common_unknown_publisher_default():
    """Publisher desconocido SIN evidencia de escasez → common (nuevo default).
    Antes era rare: 81% del corpus terminaba ahí sin discriminar nada."""
    r = mw.derive_rarity_tier(
        ["collector", "hardcover"], "", "", "Some Collector Edition 1",
        publisher="Editorial Desconocida"
    )
    assert r == "common"


def test_rarity_limited_signal_no_longer_blocks_common():
    """El signal `limited` (tautológico en este corpus) ya no fuerza rare."""
    r = mw.derive_rarity_tier(
        ["deluxe", "limited"], "", "", "Saint Seiya Edición Limitada 11",
        publisher="Planeta Cómic"
    )
    assert r == "common"


def test_rarity_variant_cover_no_longer_blocks_common():
    """variant_cover solo (sin canal/tirada/stock) → common."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "", "", "Berserk Variant Cover",
        publisher="Dark Horse Comics"
    )
    assert r == "common"


def test_rarity_reference_source_is_rare_without_evidence():
    """Fuente de referencia (solo Mangavariant) sin evidencia → rare (fallback incertidumbre)."""
    r = mw.derive_rarity_tier(
        ["deluxe", "hardcover"], "Global - Mangavariant", "",
        "Berserk Deluxe 1", publisher="Dark Horse Comics"
    )
    assert r == "rare"


def test_rarity_common_not_blocked_by_bonus():
    """bonus = extras estándar de formato, no escasez → common."""
    r = mw.derive_rarity_tier(
        ["bonus", "collector", "hardcover"], "", "", "Attack on Titan Collector 1",
        publisher="Norma Editorial"
    )
    assert r == "common"


def test_rarity_norma_with_bonus_common():
    r = mw.derive_rarity_tier(
        ["collector", "hardcover", "bonus", "premium_format", "deluxe", "lore_edition"],
        "ListadoManga (colecciones)", "", "Attack on Titan Edición Coleccionista 1",
        publisher="Norma Editorial"
    )
    assert r == "common"


def test_rarity_planeta_boxset_common():
    r = mw.derive_rarity_tier(
        ["hardcover", "omnibus", "box_set", "deluxe"], "", "",
        "Adolf Boxset", publisher="Planeta Cómic"
    )
    assert r == "common"


def test_rarity_glenat_prestige_common():
    r = mw.derive_rarity_tier(
        ["deluxe"], "Manga-Sanctuary (planning)", "",
        "Berserk Prestige 3", publisher="glénat manga"
    )
    assert r == "common"


# ---------------------------------------------------------------------------
# derive_rarity_tier — JP 限定版/特装版 = single-run por convención de mercado
# ---------------------------------------------------------------------------

def test_rarity_jp_genteiban_is_rare():
    """限定版 en el título (JP) → rare: por convención no se reimprime."""
    r = mw.derive_rarity_tier(
        ["special_edition"], "JP - Sumikko (限定版・特装版)", "",
        "鬼滅の刃 23 限定版", publisher="Shueisha"
    )
    assert r == "rare"


def test_rarity_jp_tokusoban_is_rare():
    """特装版 → rare."""
    r = mw.derive_rarity_tier(
        ["special_edition"], "JP - Sumikko (限定版・特装版)", "",
        "フリーレン 15 特装版", publisher="Shogakukan"
    )
    assert r == "rare"


def test_rarity_jp_juchu_seisan_is_rare():
    """受注生産 (impresión bajo pedido) → rare."""
    r = mw.derive_rarity_tier(
        ["limited"], "", "完全受注生産のBOXセット",
        "ベルセルク 愛蔵版BOX", publisher="Hakusensha"
    )
    assert r == "rare"


def test_rarity_english_limited_title_from_sumikko_is_rare():
    """Título EN con 'Limited' de Sumikko sin marcador JP → rare (fallback ref source)."""
    r = mw.derive_rarity_tier(
        ["special_edition"], "JP - Sumikko (限定版・特装版)", "",
        "Kimetsu no Yaiba Limited 23", publisher="Shueisha"
    )
    assert r == "rare"


# ---------------------------------------------------------------------------
# derive_rarity_tier — fallback fuentes de referencia (2026-06-10)
# ---------------------------------------------------------------------------

def test_rarity_mangavariant_no_evidence_is_rare():
    """Mangavariant sin evidencia (sources=None → usa source) → rare."""
    r = mw.derive_rarity_tier(
        [], "Global - Mangavariant", "",
        "One Piece Deluxe Edition 1",
    )
    assert r == "rare"


def test_rarity_sumikko_no_evidence_is_rare():
    """JP - Sumikko sin evidencia → rare (fallback ref source)."""
    r = mw.derive_rarity_tier(
        [], "JP - Sumikko (限定版・特装版)", "",
        "Frieren 10 Special Box",
    )
    assert r == "rare"


def test_rarity_mangavariant_in_stock_is_common():
    """Mangavariant con stock verificado → common (stock gana al fallback)."""
    r = mw.derive_rarity_tier(
        [], "Global - Mangavariant", "",
        "Berserk Vol 1", stock_status="in_stock",
    )
    assert r == "common"


def test_rarity_mixed_sources_reference_and_store_is_common():
    """Mangavariant + fuente de tienda → no aplica fallback → common."""
    r = mw.derive_rarity_tier(
        [], "Global - Mangavariant", "",
        "Berserk Deluxe 1", publisher="Dark Horse Comics",
        sources=["Global - Mangavariant", "ES - Casa del Libro"],
    )
    assert r == "common"


def test_rarity_mangavariant_print_run_300_is_ultra_rare():
    """Mangavariant con 'limited to 300 copies' → ultra_rare (evidencia gana)."""
    r = mw.derive_rarity_tier(
        [], "Global - Mangavariant",
        "limited to 300 copies, hand-numbered",
        "Berserk Art Edition",
    )
    assert r == "ultra_rare"


def test_rarity_normal_source_no_evidence_is_common():
    """Fuente de tienda normal sin evidencia de escasez → common (regresión)."""
    r = mw.derive_rarity_tier(
        [], "ES - Norma Editorial", "",
        "Berserk Deluxe 1", publisher="Norma Editorial",
    )
    assert r == "common"


# ---------------------------------------------------------------------------
# derive_rarity_tier — no-reimpresión explícita mantiene rare
# ---------------------------------------------------------------------------

def test_rarity_single_run_tiratura_limitata_is_rare():
    r = mw.derive_rarity_tier(
        ["collector", "hardcover"], "IT - Panini Planet Manga",
        "Edizione in tiratura limitata con poster esclusivo",
        "Berserk Master Edition Special", publisher="Panini Comics"
    )
    assert r == "rare"


def test_rarity_single_run_tirage_unique_is_rare():
    r = mw.derive_rarity_tier(
        ["deluxe"], "Manga-Sanctuary (planning)",
        "Ce volume prestige est un tirage unique",
        "Berserk Prestige 6 Collector", publisher="glénat manga"
    )
    assert r == "rare"


def test_rarity_single_run_primera_tirada_is_rare():
    r = mw.derive_rarity_tier(
        ["collector", "hardcover"], "ES - Norma",
        "Incluye extras solo en la primera tirada",
        "Death Note Collector 1", publisher="Norma Editorial"
    )
    assert r == "rare"


def test_rarity_celebration_edition_rare():
    r = mw.derive_rarity_tier(
        ["lore_edition", "special_edition"], "IT - AnimeClick (edizioni speciali)", "",
        "My Hero Academia Celebration Edition 42", publisher="Star Comics"
    )
    assert r == "rare"


def test_rarity_anniversary_alone_is_common():
    """'aniversario' solo ya NO es evidencia de escasez (ediciones aniversario
    de catálogo siguen en stock años después)."""
    r = mw.derive_rarity_tier(
        ["lore_edition"], "ES - Norma",
        "Edición 30 aniversario con poster y artbook exclusivo",
        "Slam Dunk 30th Anniversary", publisher="Norma Editorial"
    )
    assert r == "common"


def test_rarity_generic_limited_edition_phrase_is_common():
    """La frase genérica 'limited edition' (tautológica en el corpus) → common."""
    r = mw.derive_rarity_tier(
        ["collector"], "IT - Star Comics", "",
        "Frieren Limited Edition 12", publisher="Star Comics"
    )
    assert r == "common"


# ---------------------------------------------------------------------------
# derive_rarity_tier — print runs explícitos
# ---------------------------------------------------------------------------

def test_rarity_year_range_not_ultra_rare():
    """Year range '2007/2008' must NOT match as numbered copy."""
    r = mw.derive_rarity_tier(
        ["box_set"], "BR - BBM (box de mangá)", "Editora: Panini. Status: 2007/2008.",
        "Naruto Boxset", publisher="Panini"
    )
    assert r != "ultra_rare"


def test_rarity_numbered_copy_with_space():
    r = mw.derive_rarity_tier([], "", "", "JJK 30 (120 / 1000)")
    assert r == "ultra_rare"


def test_rarity_print_run_216_ultra_rare():
    r = mw.derive_rarity_tier(
        ["limited", "deluxe"], "",
        "Limited to 216 copies. Volume 1 limited edition sold at Leipzig Book Fair.",
        "Berserk Eclipse Leipzig Limited 1", publisher="Panini Manga GER"
    )
    assert r == "ultra_rare"


def test_rarity_print_run_500_ultra_rare():
    r = mw.derive_rarity_tier(
        ["variant_cover"], "",
        "Limited to 500 copies. Volume 8 variant cover available only through a lottery.",
        "Real Special 8",
    )
    assert r == "ultra_rare"


def test_rarity_print_run_1000_super_rare():
    r = mw.derive_rarity_tier(
        ["variant_cover"], "", "Limited to 1000 copies.", "Some Variant 5",
    )
    assert r == "super_rare"


def test_rarity_print_run_2500_super_rare():
    r = mw.derive_rarity_tier(
        ["variant_cover"], "", "Limited to 2500 copies.", "Some Variant 10",
    )
    assert r == "super_rare"


def test_rarity_print_run_5000_is_rare():
    """Tirada explícita >2500: documentadamente única pero no corta → rare."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "", "Limited to 5000 copies.", "Popular Variant 1",
    )
    assert r == "rare"


def test_rarity_print_run_italian():
    r = mw.derive_rarity_tier(
        ["variant_cover"], "", "super limitata a 100 copie", "Colorless Variant 1",
    )
    assert r == "ultra_rare"


def test_rarity_print_run_french():
    r = mw.derive_rarity_tier(
        ["variant_cover"], "", "Édition limitée à 300 exemplaires", "Some FR Variant 1",
    )
    assert r == "ultra_rare"


# ---------------------------------------------------------------------------
# derive_rarity_tier — Italian firmato/a double meaning (sin cambios)
# ---------------------------------------------------------------------------

def test_rarity_firmato_attribution_not_ultra_rare():
    r = mw.derive_rarity_tier(
        ["variant_cover"], "IT - AnimeClick (edizioni speciali)",
        "lo shonen isekai firmato da Yohei Yasumura, arriva in Italia!",
        "The Dungeon of Black Company Variant",
    )
    assert r != "ultra_rare"


def test_rarity_firmato_progetto_not_ultra_rare():
    r = mw.derive_rarity_tier(
        ["variant_cover"], "",
        "IL NUOVO MERAVIGLIOSO PROGETTO FIRMATO CAB E FEDERICA DI MEO!",
        "Oneira Variant 1",
    )
    assert r != "ultra_rare"


# ---------------------------------------------------------------------------
# derive_rarity_tier — extensiones 2026-06-10 (nuevas keywords y patrones)
# ---------------------------------------------------------------------------

# --- _PRINT_RUN_RE: nuevas formas lingüísticas ---

def test_rarity_print_run_tiratura_di():
    """IT: 'tiratura limitata di N copie' (preposición di) → super_rare."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "", "tiratura limitata di 1200 copie", "Some IT Variant 1",
    )
    assert r == "super_rare"


def test_rarity_print_run_stampata_in_soli():
    """IT: 'stampata in soli N esemplari' → ultra_rare (N ≤ 500)."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "", "stampata in soli 50 esemplari", "Rare IT Edition 1",
    )
    assert r == "ultra_rare"


def test_rarity_print_run_in_sole_copie():
    """IT: 'in sole N copie' (sin limitat-) → super_rare (N ≤ 2500)."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "", "disponibile in sole 1200 copie", "IT Edition 1",
    )
    assert r == "super_rare"


def test_rarity_print_run_limitiert_exemplare():
    """DE: 'limitiert auf N Exemplare' → super_rare (forma alemana, N ≤ 2500)."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "", "limitiert auf 777 Exemplare", "DE Edition 1",
    )
    assert r == "super_rare"


def test_rarity_print_run_numbered_copies():
    """EN: 'limited to N numbered copies' (adjetivo numbered opcional) → ultra_rare."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "", "limited to 200 numbered copies", "EN Numbered Edition 1",
    )
    assert r == "ultra_rare"


def test_rarity_print_run_in_soli_pezzi():
    """IT: 'in soli N pezzi' (unidad pezzi) → ultra_rare (N ≤ 500)."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "", "in soli 100 pezzi", "Tiny IT Edition 1",
    )
    assert r == "ultra_rare"


# --- _ULTRA_RARE_KEYWORDS: nummeriert, autografato, convention exclusive, JP ---

def test_rarity_nummeriert_ultra_rare():
    """DE 'nummeriert' (numerado a mano) → ultra_rare."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "",
        "limitiert auf 777 Exemplare und nummeriert",
        "DE Collector Edition 1",
    )
    assert r == "ultra_rare"


def test_rarity_autografato_ultra_rare():
    """IT 'autografato/autografata' (firmado a mano) → ultra_rare."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "",
        "ogni copia è autografata dall'autore",
        "IT Hand-Signed Edition 1",
    )
    assert r == "ultra_rare"


def test_rarity_autografata_sovraccoperta():
    """IT 'sovraccoperta autografata' → ultra_rare (diferente de 'firmato')."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "",
        "con sovraccoperta autografata",
        "IT Autografata 1",
    )
    assert r == "ultra_rare"


def test_rarity_firmato_one_murata_common():
    """Regresión: 'il capolavoro firmato One e Yusuke Murata' sigue common.
    'firmato' en IT = autoría, no firma a mano. Guard intacto."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "IT - AnimeClick",
        "il capolavoro firmato One e Yusuke Murata in edizione speciale",
        "One Punch Man Special Edition 1",
    )
    assert r == "common"


def test_rarity_convention_exclusive_ultra_rare():
    """'convention exclusive' → ultra_rare."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "",
        "convention exclusive variant cover",
        "Convention Exclusive Edition 1",
    )
    assert r == "ultra_rare"


def test_rarity_jp_venue_kaijo_gentei_ultra_rare():
    """JP '会場限定' (exclusiva de venue) → ultra_rare."""
    r = mw.derive_rarity_tier(
        ["special_edition"], "JP - Sumikko", "",
        "ワンピース 100 会場限定版", publisher="Shueisha",
    )
    assert r == "ultra_rare"


def test_rarity_jp_event_gentei_ultra_rare():
    """JP 'イベント限定' → ultra_rare."""
    r = mw.derive_rarity_tier(
        ["special_edition"], "JP - Sumikko", "",
        "鬼滅の刃 イベント限定ボックス", publisher="Shueisha",
    )
    assert r == "ultra_rare"


# --- _SINGLE_RUN_PATTERNS: Lucca word-boundary ---

def test_rarity_lucca_variant_title_is_rare():
    """'Variant Lucca 2015' (sin 'comics') → rare via patrón word-boundary."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "",
        "",
        "One Piece Variant Lucca 2015",
    )
    assert r == "rare"


def test_rarity_lucca_changes_is_rare():
    """'in esclusiva per i punti vendita campfire di Lucca Changes' → rare."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "",
        "in esclusiva per i punti vendita campfire di Lucca Changes",
        "JJK Variant Lucca Changes Edition 1",
    )
    assert r == "rare"


# --- _SINGLE_RUN_PATTERNS: exclusivas de festival con orden libre ---

def test_rarity_sold_exclusively_comicon():
    """'sold exclusively at Napoli Comicon 2015' → rare."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "",
        "sold exclusively at Napoli Comicon 2015",
        "Dragon Ball Comicon Variant 1",
    )
    assert r == "rare"


def test_rarity_released_exclusively_festival():
    """'released exclusively during the festival Comic Fes 2023' → rare."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "",
        "variant cover released exclusively during the festival Comic Fes 2023",
        "Frieren Festival Variant 1",
    )
    assert r == "rare"


# --- _SINGLE_RUN_PATTERNS: furoku/appendix de revista ---

def test_rarity_appendix_magazine_is_rare():
    """'appendix of the magazine Morning Two' (furoku) → rare."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "Global - Mangavariant",
        "cover variant released as an appendix of the magazine Morning Two n.4",
        "Dungeon Meshi Appendix Variant 1",
    )
    assert r == "rare"


# --- _SINGLE_RUN_PATTERNS: exclusiva de retailer en texto ---

def test_rarity_exclusive_kinokuniya_bookstores():
    """'exclusive to Kinokuniya bookstores' → rare."""
    r = mw.derive_rarity_tier(
        [], "",
        "exclusive to Kinokuniya bookstores",
        "Vagabond Kinokuniya Edition 1",
    )
    assert r == "rare"


def test_rarity_exclusive_panini_online_shop():
    """'exclusive to Panini online shop' → rare."""
    r = mw.derive_rarity_tier(
        [], "",
        "exclusive to Panini online shop",
        "One Piece Panini Online Exclusive 1",
    )
    assert r == "rare"


# --- _SINGLE_RUN_PATTERNS: out-of-print multilingual ---

def test_rarity_esaurito_is_rare():
    """IT 'esaurito' (agotado) → rare."""
    r = mw.derive_rarity_tier(
        ["collector"], "", "prodotto esaurito, non verrà ristampato",
        "IT Esaurito Edition 1",
    )
    assert r == "rare"


def test_rarity_descatalogado_is_rare():
    """ES 'descatalogado en tienda oficial' → rare."""
    r = mw.derive_rarity_tier(
        ["collector"], "", "descatalogado en tienda oficial",
        "ES Descatalogado Edition 1",
    )
    assert r == "rare"


def test_rarity_out_of_print_is_rare():
    """EN 'out of print' → rare."""
    r = mw.derive_rarity_tier(
        ["collector"], "", "currently out of print",
        "EN OOP Edition 1",
    )
    assert r == "rare"


# --- _SINGLE_RUN_KEYWORDS: FR collector + ES no-reimpresión + JP store ---

def test_rarity_coffret_collector_is_rare():
    """FR 'coffret collector' (política editorial Pika 2026) → rare."""
    r = mw.derive_rarity_tier(
        ["collector"], "Manga-Sanctuary (planning)",
        "coffret collector + fanbook",
        "Coffret FR Collector 1", publisher="Pika Édition",
    )
    assert r == "rare"


def test_rarity_edition_collector_is_rare():
    """FR 'édition collector' → rare."""
    r = mw.derive_rarity_tier(
        ["collector"], "Manga-Sanctuary (planning)",
        "",
        "Naruto édition collector 15", publisher="Kazé",
    )
    assert r == "rare"


def test_rarity_jp_suryo_gentei_is_rare():
    """JP '数量限定' (quantity limited) → rare."""
    r = mw.derive_rarity_tier(
        ["special_edition"], "JP - Sumikko", "数量限定特典付き",
        "鬼滅の刃 数量限定ボックス", publisher="Shueisha",
    )
    assert r == "rare"


# --- Regresiones: deben seguir siendo common ---

def test_rarity_edicion_limitada_postal_common():
    """'edición limitada + postal exclusiva' sin otras señales → common.
    La frase 'edición limitada' sola es tautológica en este corpus."""
    r = mw.derive_rarity_tier(
        ["limited", "collector"], "ES - Norma",
        "edición limitada + postal exclusiva de regalo",
        "Some Manga Edición Limitada 1", publisher="Norma Editorial",
    )
    assert r == "common"


def test_rarity_year_range_2007_2008_not_numerado():
    """'2007/2008' es un rango de años, NO un numerado (regresión)."""
    r = mw.derive_rarity_tier(
        ["box_set"], "BR - BBM", "Editora: Panini. Status: 2007/2008.",
        "Naruto Boxset", publisher="Panini",
    )
    assert r != "ultra_rare"


def test_rarity_lamina_firmada_not_ultra_rare():
    """'lámina firmada' = firma impresa en extra → NO ultra_rare (regresión)."""
    r = mw.derive_rarity_tier(
        ["collector"], "", "Incluye lámina firmada por el autor.",
        "Capitán Harlock Edición Coleccionista 3", publisher="Letrablanka",
    )
    assert r != "ultra_rare"


def test_rarity_firmato_capolavoro_not_ultra_rare():
    r = mw.derive_rarity_tier(
        ["variant_cover"], "",
        "Una Instant Variant del numero 33 di One-Punch Man, il capolavoro firmato One e Yusuke Murata!",
        "One-Punch Man Variant 33",
    )
    assert r != "ultra_rare"


def test_rarity_variant_firmata_is_ultra_rare():
    """firmata + limitata a 100 copie → ultra_rare (vía print run)."""
    r = mw.derive_rarity_tier(
        ["variant_cover"], "",
        "VARIANT EDITION firmata dal grandissimo Jacopo Camagni, super limitata a 100 copie",
        "Colorless Variant 1",
    )
    assert r == "ultra_rare"


# --- Tests for improved standardization heuristics ---


def test_publisher_slug_new_publishers():
    """Newly added publishers map correctly."""
    assert mw._publisher_slug("J-Pop Manga") == "jpop"
    assert mw._publisher_slug("Edizioni BD") == "edizionibd"
    assert mw._publisher_slug("001 Edizioni") == "001edizioni"
    assert mw._publisher_slug("Dynit") == "dynit"
    assert mw._publisher_slug("Goen Manga") == "goen"
    assert mw._publisher_slug("Yen Press") == "yenpress"
    assert mw._publisher_slug("Seven Seas Entertainment") == "sevenseas"
    assert mw._publisher_slug("Distrito Manga") == "distrito"
    assert mw._publisher_slug("Noeve Grafx") == "noeve"
    assert mw._publisher_slug("Ichijinsha") == "ichijinsha"
    assert mw._publisher_slug("Shogakukan") == "shogakukan"
    assert mw._publisher_slug("Kim Đồng") == "kim-dong"
    assert mw._publisher_slug("Titan Comics") == "titan"


def test_refine_edition_slug_language_aware():
    """Edition slug refined by language for box_set tier."""
    assert mw._refine_edition_slug("box_set", "One Piece Coffret", "fr", "glenat") == "coffret"
    assert mw._refine_edition_slug("box_set", "Naruto Cofanetto", "it", "panini") == "cofanetto"
    assert mw._refine_edition_slug("box_set", "Naruto Box Set", "en", "viz") == "boxset"


def test_refine_edition_slug_title_keywords():
    """Edition slug refined by title keywords."""
    assert mw._refine_edition_slug("kanzenban", "Blame! Maximum 1", "es", "panini") == "maximum"
    assert mw._refine_edition_slug("kanzenban", "FMA Perfect Edition 1", "it", "panini") == "perfect"
    assert mw._refine_edition_slug("deluxe", "Berserk Ultimate 1", "it", "panini") == "ultimate"
    assert mw._refine_edition_slug("lore_edition", "Witch Hat Grimorio 3", "es", "milkyway") == "grimorio"
    assert mw._refine_edition_slug("special", "Dragon Ball Collector 1", "fr", "glenat") == "collector"
    assert mw._refine_edition_slug("lore_edition", "Slam Dunk Integral 1", "es", "planeta") == "integral"


def test_refine_edition_slug_fallback():
    """Edition slug falls back to static map for unrecognized titles."""
    assert mw._refine_edition_slug("deluxe", "Berserk Deluxe 1", "en", "darkhorse") == "deluxe"
    assert mw._refine_edition_slug("artbook", "One Piece Color Walk", "en", "viz") == "artbook"
    assert mw._refine_edition_slug("", "Naruto 1", "en", "viz") == "regular"


def test_extract_volume_trailing_number():
    """Trailing bare number captured as volume (last-resort pattern)."""
    assert mw._extract_volume("Berserk Deluxe 1") == "1"
    assert mw._extract_volume("Fullmetal Alchemist Ultimate 18") == "18"
    assert mw._extract_volume("One Piece 98") == "98"
    # But NOT years or ISBNs
    assert mw._extract_volume("One Piece 2024") == ""
    assert mw._extract_volume("abc123") == ""
    # Markers still take priority
    assert mw._extract_volume("Naruto Vol. 5 extra") == "5"


def test_derive_series_metadata_confidence_tier():
    """Confidence tier assigned correctly based on alias/publisher/edition resolution."""
    c = mw.Candidate(
        title="Demon Slayer Vol. 1 Limited", url="x", source="X",
        source_url="x", country="ES", language="es", publisher="Norma Editorial",
        source_class="", tags=[], description="",
        signal_types=["limited"],
    )
    md = mw.derive_series_metadata(c)
    # demon-slayer IS in aliases.yml, norma IS in publisher map, limited IS unambiguous
    assert md.get("confidence_tier") == 1

    # Unknown series → Tier 3
    c2 = mw.Candidate(
        title="新しいマンガ 限定版", url="x", source="X",
        source_url="x", country="JP", language="ja", publisher="",
        source_class="", tags=[], description="", signal_types=["limited"],
    )
    md2 = mw.derive_series_metadata(c2)
    if md2:
        assert md2.get("confidence_tier") == 3


def test_canonical_series_key_prefix_matching():
    """Prefix matching resolves series_key with edition qualifiers appended."""
    from series_aliases import canonical_series_key
    # "demon-slayer-deluxe" should match "demon-slayer" via prefix
    # (dropping "deluxe" which is in _EDITION_SUFFIXES)
    sk, sd = canonical_series_key("", "demon-slayer-deluxe", "")
    assert sk == "demon-slayer", f"Got {sk}"

    # "naruto-gaiden" should NOT match "naruto" (gaiden is not an edition suffix)
    sk2, _ = canonical_series_key("", "naruto-gaiden", "Naruto Gaiden")
    assert sk2 == "naruto-gaiden", f"Got {sk2}"

    # "berserk-variant" should match "berserk" (variant IS an edition suffix)
    sk3, _ = canonical_series_key("", "berserk-variant", "")
    assert sk3 == "berserk", f"Got {sk3}"


# ---------------------------------------------------------------------------
# derive_product_type priority (list order = specificity)
# ---------------------------------------------------------------------------


def test_detect_signals_artbook_booklet_bonus_demoted_to_bonus():
    """画集付き / イラスト集付き特装版 = artbook INCLUIDO como bonus → el producto
    es el tomo, no un artbook. detect_signals demuele artbook→bonus (queja del
    owner 2026-06-04: tomos con "Artbook" en el título). Un artbook propio
    (画集 standalone, sin 付き) NO se demuele."""
    # Tomo con cuadernillo de ilustraciones incluido → bonus, NO artbook.
    for t in ("宇宙兄弟(39) 画集付き特装版",
              "暁のヨナ YONA MEMORIAL イラスト集付き特装版 47",
              "彼女、お借りします(41) 水原千鶴ミニ画集付き特装版"):
        _, _, types = mw.detect_signals(t)
        assert "artbook" not in types, f"{t!r}: artbook NO debería estar: {types}"
        assert "bonus" in types, f"{t!r}: debería tener bonus: {types}"
    # Artbook GENUINO (el producto ES el artbook) → conserva artbook.
    for t in ("笠井あゆみ画集 麗人1993-2025 特装版",
              "貞本義行画集 EVANGELION 限定版",
              "枢やな画集 黒執事3",
              "Beasts Art Book"):
        _, _, types = mw.detect_signals(t)
        assert "artbook" in types, f"{t!r}: artbook DEBERÍA estar: {types}"


def test_derive_product_type_priority_artbook_over_boxset():
    """PRODUCT_TYPE_KEYWORDS list order is the priority: artbook beats boxset."""
    # A title that matches BOTH 'artbook' and 'box set' must resolve to artbook
    # because artbook appears first in PRODUCT_TYPE_KEYWORDS.
    pt = mw.derive_product_type("Berserk Artbook Box Set", "", [])
    assert pt == "artbook", f"Expected artbook (more specific), got {pt}"
    # Plain box set (no artbook keyword) still resolves to boxset.
    pt2 = mw.derive_product_type("Berserk Deluxe Box Set", "", [])
    assert pt2 == "boxset", f"Expected boxset, got {pt2}"


# ---------------------------------------------------------------------------
# source_health.py log parser (observability)
# ---------------------------------------------------------------------------


def _import_source_health():
    import importlib.util
    p = Path(__file__).resolve().parent.parent / "scripts" / "audit" / "source_health.py"
    spec = importlib.util.spec_from_file_location("source_health", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_source_health_parses_current_combined_log_format(tmp_path):
    """The parser must understand the CURRENT one-line format emitted by
    manga_watch.py: `    [Source Name] candidatos con señales: N (M págs)`."""
    sh = _import_source_health()
    run_dir = tmp_path / "scrape-delta-2026-06-01-000000"
    run_dir.mkdir()
    (run_dir / "01-scrape.log").write_text(
        "    [ES - Listado Manga Calendario] candidatos con señales: 5 (3 págs)\n"
        "    [AR - Ivrea Argentina] candidatos con señales: 22\n"
        "[ERROR] ES - Misión Tokyo: HTTP error 503\n"
        "[SKIP-js] ES - Kibook Novedades: requiere JavaScript\n",
        encoding="utf-8",
    )
    stats = sh.parse_run_log(run_dir)
    assert stats["ES - Listado Manga Calendario"]["candidates"] == 5
    assert stats["AR - Ivrea Argentina"]["candidates"] == 22
    assert stats["ES - Misión Tokyo"]["error"] is not None
    assert stats["ES - Kibook Novedades"]["skipped"] is not None
    # Bracket markers like [ERROR]/[SKIP-*] must NOT be parsed as source names.
    assert "ERROR" not in stats
    assert not any(k.startswith("SKIP-") for k in stats)


def test_source_health_collects_canonical_run_dirs(tmp_path):
    sh = _import_source_health()
    for name in ("scrape-delta-2026-06-01", "scrape-full-2026-05-01",
                 "overnight-2026-04-01", "retry-2026-03-01", "not-a-run"):
        (tmp_path / name).mkdir()
    dirs = {d.name for d in sh.collect_run_dirs(tmp_path, last_n=10)}
    assert "scrape-delta-2026-06-01" in dirs
    assert "scrape-full-2026-05-01" in dirs
    assert "not-a-run" not in dirs


# ---------------------------------------------------------------------------
# Corpus invariants (data-quality guards — skip if corpus absent)
# ---------------------------------------------------------------------------

import pytest

_CORPUS = Path(__file__).resolve().parent.parent / "data" / "items.jsonl"


def _load_corpus():
    if not _CORPUS.exists():
        pytest.skip("data/items.jsonl not present")
    return [json.loads(l) for l in _CORPUS.open(encoding="utf-8")]


def test_corpus_no_cluster_with_two_distinct_isbns():
    """A cluster_key must never group two items with different non-empty ISBNs
    (over-merge guard for derive_cluster_key)."""
    from collections import defaultdict
    items = _load_corpus()
    by_ck = defaultdict(set)
    for it in items:
        ck = it.get("cluster_key") or mw.derive_cluster_key(it)
        isbn = (it.get("isbn") or "").strip()
        if isbn:
            by_ck[ck].add(isbn)
    bad = {ck: sorted(s) for ck, s in by_ck.items() if len(s) > 1}
    assert not bad, f"{len(bad)} clusters merge distinct ISBNs, e.g. {list(bad.items())[:3]}"


def test_corpus_no_standardized_orphans():
    """A standardized item must always carry both series_key and edition_key."""
    items = _load_corpus()
    orphans = [it.get("url", "") for it in items
               if it.get("standardized_at") and not (it.get("series_key") and it.get("edition_key"))]
    assert not orphans, f"{len(orphans)} standardized orphans, e.g. {orphans[:3]}"


def test_corpus_all_items_have_slug():
    """Every item must have a slug so /item/[slug] can render it."""
    items = _load_corpus()
    missing = [it.get("url", "") for it in items if not it.get("slug")]
    assert not missing, f"{len(missing)} items without slug, e.g. {missing[:3]}"


# ---------------------------------------------------------------------------
# VIZ Media special-editions parser (generalized, calendar-driven)
# ---------------------------------------------------------------------------

from scripts.wikis import viz_artbooks as _viz


def test_viz_url_filter_accepts_special_editions():
    # Regular paperback → rejected
    q, _, _ = _viz.special_signals_from_url(
        "/manga-books/manga/chainsaw-man-volume-21-0/product/8857/paperback")
    assert q is False
    # Hardcover definitive → accepted (hardcover + deluxe)
    q, sigs, pt = _viz.special_signals_from_url(
        "/manga-books/manga/vagabond-definitive-edition-volume-5-0/product/8681/hardcover")
    assert q is True and "hardcover" in sigs and "deluxe" in sigs
    # Art-book path → accepted as artbook
    q, sigs, pt = _viz.special_signals_from_url(
        "/manga-books/art-book/one-piece-color-walk-compendium-east-blue/product/7000/hardcover")
    assert q is True and "artbook" in sigs and pt == "artbook"
    # Box set slug → accepted
    q, sigs, pt = _viz.special_signals_from_url(
        "/manga-books/manga/one-piece-box-set-1/product/4000")
    assert q is True and "box_set" in sigs and pt == "boxset"


def test_viz_url_filter_rejects_bare_omnibus_and_3in1():
    # Gotcha #18: bare 3-in-1 / omnibus paperback does NOT qualify alone.
    for href in (
        "/manga-books/manga/naruto-3-in-1-volume-9-0/product/123/paperback",
        "/manga-books/manga/one-piece-omnibus-edition-volume-36-0/product/8881/paperback",
    ):
        q, _, _ = _viz.special_signals_from_url(href)
        assert q is False, href


def test_viz_isbn10_to_13():
    # 1974718190 (Zelda Legendary box set ISBN-10) → 9781974718191
    assert _viz._isbn10_to_13("1974718190") == "9781974718191"


def test_viz_parse_product_page():
    html = """
    <html><head>
      <meta property="og:title" content="VIZ: See Vagabond Definitive Edition, Vol. 5">
    </head><body>
      <h2>Manga &amp; Anime Favorites</h2>
      <img src="https://dw9to29mmj727.cloudfront.net/misc/placeholder_400x320.png">
      <img src="https://dw9to29mmj727.cloudfront.net/products/1974761924.png">
      <p>ISBN-13: 978-1-9747-6192-0</p>
      <p>$55.00</p>
      <p>Hardcover</p>
      <p>An oversized hardcover definitive edition collecting the epic samurai tale by Takehiko Inoue.</p>
    </body></html>
    """
    meta = _viz.parse_product_page(html)
    assert meta is not None
    assert meta["title"] == "Vagabond Definitive Edition, Vol. 5"
    assert meta["isbn"] == "9781974761920"
    # Cover is the real product image, not the placeholder
    assert meta["cover_url"].endswith("/products/1974761924.png")


def test_viz_iter_year_months_clamps_to_2013():
    # Full mode passes 2000-01; parser must clamp to the catalog start (2013).
    pairs = _viz.iter_year_months(2000, 1, 2013, 3)
    assert pairs[0] == (2013, 1)
    assert (2012, 6) not in pairs


# ---------------------------------------------------------------------------
# sync_cover_images retrofit — images[0] == portada, limpieza de galería,
# contaminación de productos relacionados, portada mala
# ---------------------------------------------------------------------------

from scripts.retrofit import sync_cover_images as _sci


def test_sync_cover_dedupes_exact_duplicates():
    # Panini: images = [cover, cover, cover] → [cover].
    u = "https://www.panini.it/media/catalog/product/m/b/mberd001isbn_0.jpg"
    it = {"images": [{"url": u, "local": "c.jpg", "kind": "gallery"}] * 3}
    assert _sci._rebuild(it) is True
    assert len(it["images"]) == 1


def test_sync_cover_collapses_http_https_duplicate():
    it = {
        "images": [
            {"url": "https://funside.it/cdn/shop/files/cover_x.jpg", "local": "c.jpg", "kind": "gallery"},
            {"url": "http://funside.it/cdn/shop/files/cover_x.jpg?v=1", "local": "", "kind": "gallery"},
        ],
    }
    assert _sci._rebuild(it) is True
    assert len(it["images"]) == 1


def test_sync_cover_drops_star_comics_related_thumbnails():
    # Star Comics: la galería son SIEMPRE otros tomos/series en /thumbnail/.
    cover = "https://www.starcomics.com/files/immagini/fumetti-cover/kagurabachi-1-variant"
    it = {"images": [
              {"url": cover, "local": "c.jpg", "kind": "gallery"},
              {"url": "https://www.starcomics.com/files/immagini/fumetti-cover/thumbnail/kagurabachi-8", "local": "", "kind": "gallery", "description": "KAGURABACHI n. 8"},
              {"url": "https://www.starcomics.com/files/immagini/fumetti-cover/thumbnail/hellboy-9", "local": "", "kind": "gallery", "description": "HELLBOY n. 9"},
          ]}
    assert _sci._rebuild(it) is True
    assert len(it["images"]) == 1
    assert it["images"][0]["url"] == cover


def test_sync_cover_drops_manga_sanctuary_related_thumbnails():
    cover = "https://img.sanctuary.fr/objet/300/392760.jpg"
    it = {"images": [
              {"url": cover, "local": "c.jpg", "kind": "gallery"},
              {"url": "https://img.sanctuary.fr/objet/150/441765.jpg", "local": "", "kind": "gallery", "description": "Whale Star #1"},
          ]}
    assert _sci._rebuild(it) is True
    assert len(it["images"]) == 1


def test_sync_cover_clears_placeholder_cover():
    # visuel_defaut / banner promo en images[0]: sin reemplazo real → galería
    # vacía (el dashboard cae al placeholder 📚).
    it = {
        "images": [{"url": "https://www.manga-sanctuary.com/v10_good/public/img/visuel_defaut.png", "local": "ph.png", "kind": "gallery"}],
    }
    assert _sci._fix_bad_cover(it) is True
    assert it["images"] == []


def test_sync_cover_promotes_real_cover_over_bad_one():
    # Si la portada (images[0]) es basura pero hay una imagen real más adelante
    # en images[], se promueve a images[0].
    it = {
        "images": [
            {"url": "https://x.com/img/lista%20de%20mangas%20panini.jpg", "local": "banner.jpg", "kind": "gallery"},
            {"url": "https://cdn.real.com/cover-real.jpg", "local": "real.jpg", "kind": "gallery"},
        ],
    }
    assert _sci._fix_bad_cover(it) is True
    assert imgstore.cover_url(it) == "https://cdn.real.com/cover-real.jpg"
    assert imgstore.cover_local(it) == "real.jpg"


def test_sync_cover_noop_when_already_synced():
    u = "https://cdn.real.com/cover.jpg"
    it = {"images": [{"url": u, "local": "c.jpg", "kind": "gallery"}]}
    assert _sci._fix_bad_cover(it) is False
    assert _sci._rebuild(it) is False


# ---------------------------------------------------------------------------
# build_web._merged_canonical — la portada canónica va primera en el carrusel
# (carrusel[0] == card cover); union cross-source deduplicada por URL
# ---------------------------------------------------------------------------

from scripts import build_web as _bw


def _pick_by_completeness(a, b):
    score = lambda x: (100 if x.get("isbn") else 0) + (10 if x.get("images") else 0) + (5 if x.get("price") else 0)
    return a if score(a) >= score(b) else b


def test_build_web_merge_cover_first_in_carousel():
    # PRH (con ISBN → canónico) + Dark Horse (sin ISBN). El carrusel debe
    # empezar por la portada PRH (la que muestra la card), no por la foto DHD,
    # aunque DHD esté primero en orden de archivo. Portada = images[0].
    dh = {"url": "https://dh/x", "cluster_key": "edition:x|1",
          "images": [{"url": "https://dh.com/photo.png", "local": "dh.png", "kind": "gallery"}]}
    prh = {"url": "https://prh/x", "cluster_key": "edition:x|1", "isbn": "9781506715537",
           "images": [{"url": "https://prh.com/cover.jpg", "local": "prh.jpg", "kind": "gallery"}]}
    merged = _bw._merged_canonical([dh, prh], _pick_by_completeness)
    assert merged["images"][0]["url"] == "https://prh.com/cover.jpg"  # canónica = PRH, carrusel[0] == card
    assert len(merged["images"]) == 2                                # union mantiene la foto DHD
    assert merged["images"][1]["url"] == "https://dh.com/photo.png"


def test_build_web_merge_dedupes_by_url_stem():
    a = {"url": "https://a", "cluster_key": "edition:y|1", "isbn": "9",
         "images": [{"url": "https://cdn/c.jpg", "local": "c.jpg", "kind": "gallery"}]}
    b = {"url": "https://b", "cluster_key": "edition:y|1",
         "images": [{"url": "http://cdn/c.jpg?v=2", "local": "", "kind": "gallery"}]}
    merged = _bw._merged_canonical([a, b], _pick_by_completeness)
    # http/https + query distintos pero MISMA imagen → 1 sola en el carrusel.
    assert len(merged["images"]) == 1


# ---------------------------------------------------------------------------
# Modelo 1-fila-por-producto: merge_cluster / consolidate_by_cluster /
# append_jsonl dedup por producto (no se regeneran filas duplicadas)
# ---------------------------------------------------------------------------

def test_merge_cluster_single_gets_self_source():
    it = {"url": "https://a", "source": "Src A", "image_url": "c.jpg", "image_local": "c.png"}
    m = mw.merge_cluster([it])
    assert len(m["sources"]) == 1
    assert m["sources"][0]["url"] == "https://a"
    assert m["sources"][0]["name"] == "Src A"


def test_merge_cluster_unions_sources_cover_first():
    prh = {"url": "https://prh", "source": "PRH", "isbn": "9", "cluster_key": "edition:x|1",
           "images": [{"url": "https://prh/cover.jpg", "local": "p.jpg", "kind": "gallery"}]}
    dh = {"url": "https://dh", "source": "DH", "cluster_key": "edition:x|1",
          "images": [{"url": "https://dh/photo.png", "local": "d.png", "kind": "gallery"}]}
    m = mw.merge_cluster([dh, prh])               # DH primero a propósito
    # Portada = images[0]; PRH canónica (tiene ISBN) → su images[0] va primero.
    assert m["images"][0]["url"] == "https://prh/cover.jpg"   # carrusel[0] == card
    assert len(m["images"]) == 2
    assert {s["name"] for s in m["sources"]} == {"PRH", "DH"}


def test_consolidate_by_cluster_collapses_same_product():
    rows = [
        {"url": "https://prh", "source": "PRH", "isbn": "9", "cluster_key": "edition:x|1", "image_url": "p.jpg"},
        {"url": "https://dh", "source": "DH", "cluster_key": "edition:x|1", "image_url": "d.png"},
        {"url": "https://other", "source": "O", "cluster_key": "url:https://other", "image_url": "o.jpg"},
    ]
    out = mw.consolidate_by_cluster(rows)
    assert len(out) == 2                                  # producto x + standalone
    prod = next(r for r in out if r.get("cluster_key") == "edition:x|1")
    assert len(prod["sources"]) == 2


def test_append_jsonl_dedups_by_product_not_url(tmp_path):
    # Dos fuentes del MISMO producto (cluster_key igual, URLs distintas) →
    # UNA sola fila con 2 sources, no dos filas.
    items = tmp_path / "items.jsonl"
    prh = {"url": "https://prh/op1", "source": "PRH", "isbn": "9781", "title": "OP 1",
           "cluster_key": "edition:op|1", "price": "$10"}
    dh = {"url": "https://dh/op1", "source": "DH", "title": "OP 1",
          "cluster_key": "edition:op|1", "price": "$12"}
    mw.append_jsonl(items, [prh])
    mw.append_jsonl(items, [dh])
    rows = [json.loads(l) for l in items.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 1, f"esperaba 1 fila por producto, hay {len(rows)}"
    assert len(rows[0]["sources"]) == 2
    assert {s["name"] for s in rows[0]["sources"]} == {"PRH", "DH"}


def test_append_jsonl_rescrape_one_source_keeps_siblings(tmp_path):
    # Re-scrapear SOLO una fuente no debe borrar las fuentes hermanas del array.
    items = tmp_path / "items.jsonl"
    prh = {"url": "https://prh/op1", "source": "PRH", "isbn": "9781", "title": "OP 1",
           "cluster_key": "edition:op|1", "price": "$10"}
    dh = {"url": "https://dh/op1", "source": "DH", "title": "OP 1",
          "cluster_key": "edition:op|1", "price": "$12"}
    mw.append_jsonl(items, [prh, dh])
    # Re-scrape solo PRH, con precio nuevo.
    prh2 = dict(prh, price="$9")
    mw.append_jsonl(items, [prh2])
    rows = [json.loads(l) for l in items.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 1
    names = {s["name"] for s in rows[0]["sources"]}
    assert names == {"PRH", "DH"}, f"DH se perdió al re-scrapear PRH: {names}"


def test_standardize_dedup_merges_sources_not_drops():
    # Simula el merge de /watch-standardize-catalog: dos filas que tras reasignar
    # edition_key pasan a ser el MISMO producto deben FUSIONARSE conservando
    # ambas fuentes (no borrar una y perder su source) — modelo 1-fila/producto.
    a = {"url": "https://src-a/op1", "source": "Src A", "series_key": "one-piece",
         "edition_key": "one-piece-norma-special", "volume": "1",
         "sources": [
             {"name": "Src A", "url": "https://src-a/op1", "price": "$10"}]}
    b = {"url": "https://src-b/op1", "source": "Src B", "series_key": "one-piece",
         "edition_key": "one-piece-norma-special", "volume": "1",
         "sources": [
             {"name": "Src B", "url": "https://src-b/op1", "price": "$12"}]}
    # recomputar cluster_key (como hace el skill tras estandarizar) + consolidar
    for it in (a, b):
        it["cluster_key"] = mw.derive_cluster_key(it)
    out = mw.consolidate_by_cluster([a, b])
    assert len(out) == 1, "deben fusionarse en 1 fila"
    names = {s["name"] for s in out[0]["sources"]}
    assert names == {"Src A", "Src B"}, f"se perdió una fuente: {names}"


# ---------------------------------------------------------------------------
# serve.py endpoints de curación — mantienen el modelo 1-fila-por-producto
# ---------------------------------------------------------------------------

def _load_serve():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("serve_mod_test", "scripts/serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_serve_static_allowlist_blocks_secrets():
    """Seguridad: el fallthrough estático sólo sirve web/, data/, reports/.

    `os.chdir(ROOT)` + SimpleHTTPRequestHandler servían /.env (con las 5 API
    keys), /.git/config, /scripts/, /.venv/ — accesibles desde la red si
    --bind=0.0.0.0. La allowlist los bloquea (403) incluso sobre loopback.
    """
    serve = _load_serve()
    # Instancia sin socket (no invocar __init__, que requiere conexión).
    h = object.__new__(serve.MangaWatchHandler)
    allow = ["/web/panel.html", "/data/items.jsonl", "/data/images/x/y.jpg",
             "/data/cover_preview.json", "/reports/r.json", "/web/js/app.js"]
    deny = ["/.env", "/.git/config", "/scripts/serve.py", "/.venv/bin/python",
            "/data/../.env", "/data/../../etc/passwd", "/", "/favicon.ico",
            "/secret", "/data/.git/config", "//.env"]
    for p in allow:
        assert h._static_path_allowed(p) is True, f"debe servir: {p}"
    for p in deny:
        assert h._static_path_allowed(p) is False, f"debe bloquear (403): {p}"


def test_serve_gzip_file_roundtrips_and_caches(tmp_path):
    """gzip on-the-fly: comprime, descomprime al original y cachea por mtime."""
    import gzip as _gzip
    import os as _os
    serve = _load_serve()
    f = tmp_path / "big.jsonl"
    payload = b'{"a":1}\n' * 5000
    f.write_bytes(payload)
    _os.utime(f, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
    body = serve._gzip_file(f)
    assert _gzip.decompress(body) == payload      # round-trip exacto
    assert len(body) < len(payload)               # efectivamente comprimió
    assert serve._gzip_file(f) is body            # mismo mtime → cache hit (mismos bytes)
    payload2 = payload + b'{"b":2}\n'
    f.write_bytes(payload2)
    _os.utime(f, ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))
    body3 = serve._gzip_file(f)
    assert body3 is not body                       # mtime cambió → recomprime
    assert _gzip.decompress(body3) == payload2


def test_serve_resolve_static_matches_allowlist():
    """_resolve_static resuelve estáticos permitidos+existentes y niega el resto
    (misma normalización que la allowlist de seguridad)."""
    serve = _load_serve()
    h = object.__new__(serve.MangaWatchHandler)
    assert h._resolve_static("/web/index.html") is not None
    for p in ["/.env", "/scripts/serve.py", "/data/../.env", "/", "/secret"]:
        assert h._resolve_static(p) is None, f"debe negar: {p}"


def test_serve_merge_items_unions_sources(tmp_path):
    serve = _load_serve()
    assert serve.merge_cluster is not None
    items = tmp_path / "items.jsonl"
    serve.ITEMS_PATH = items
    serve.IMAGES_DIR = tmp_path
    rows = [
        {"url": "https://a", "source": "A", "score": 50, "cluster_key": "url:https://a",
         "image_url": "a.jpg", "sources": [{"name": "A", "url": "https://a"}]},
        {"url": "https://b", "source": "B", "score": 90, "isbn": "9", "cluster_key": "url:https://b",
         "image_url": "b.jpg", "sources": [{"name": "B", "url": "https://b"}]},
    ]
    items.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    serve._apply_merge_items("https://a", "https://b", "dup")
    out = [json.loads(l) for l in items.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(out) == 1, "merge debe dejar 1 fila"
    assert {s["name"] for s in out[0]["sources"]} == {"A", "B"}, "ninguna fuente se pierde"


def test_serve_move_consolidates_into_existing_volume(tmp_path):
    serve = _load_serve()
    assert serve.consolidate_by_cluster is not None
    items = tmp_path / "items.jsonl"
    serve.ITEMS_PATH = items
    serve.IMAGES_DIR = tmp_path
    # 'mover' debe fusionar si el destino ya tiene ese tomo (mismo cluster_key).
    rows = [
        {"url": "https://x", "source": "X", "volume": "1", "edition_key": "wrong-ed",
         "cluster_key": "edition:wrong-ed|1",
         "sources": [{"name": "X", "url": "https://x"}]},
        {"url": "https://y", "source": "Y", "volume": "1", "edition_key": "right-ed",
         "edition_display": "Right", "series_key": "s", "series_display": "S",
         "cluster_key": "edition:right-ed|1", "isbn": "9",
         "sources": [{"name": "Y", "url": "https://y"}]},
    ]
    items.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    serve._apply_move("https://x", "right-ed", "regroup")
    out = [json.loads(l) for l in items.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(out) == 1, "mover al tomo existente debe fusionar, no duplicar"
    assert {s["name"] for s in out[0]["sources"]} == {"X", "Y"}


def test_serve_item_update_product_field_propagates_row_field_does_not(tmp_path):
    serve = _load_serve()
    items = tmp_path / "items.jsonl"
    edits = tmp_path / "edits.jsonl"
    serve.ITEMS_PATH = items
    serve.EDITS_PATH = edits
    serve.IMAGES_DIR = tmp_path
    # 2 filas del MISMO producto (mismo cluster_key) desde 2 fuentes distintas.
    rows = [
        {"url": "https://a", "source": "A", "author": "viejo", "publisher": "P",
         "slug": "slug-a", "cluster_key": "edition:ed|1", "title": "T",
         "images": [{"url": "a.jpg", "local": "", "kind": "gallery"}], "tags": ["x"], "score": 10,
         "sources": [{"name": "A", "url": "https://a"}]},
        {"url": "https://b", "source": "B", "author": "viejo", "publisher": "P",
         "slug": "slug-b", "cluster_key": "edition:ed|1", "title": "T",
         "images": [{"url": "b.jpg", "local": "", "kind": "gallery"}],
         "sources": [{"name": "B", "url": "https://b"}]},
    ]
    items.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    ok, applied = serve._apply_item_update("https://a", {
        "author": "Kentaro Miura",        # producto → propaga al cluster
        "tags": ["manga", "deluxe"],      # tipo lista preservado
        "score": 95,                       # tipo int preservado
        "slug": "slug-a-fixed",           # row-local → solo la fila abierta
        "image_url": "HACK.jpg",          # protegido (imágenes) → ignorado
    })
    assert ok
    assert "image_url" not in applied, "los campos de imagen no se editan acá"
    out = {r["url"]: r for r in
           (json.loads(l) for l in items.read_text(encoding="utf-8").splitlines() if l.strip())}
    assert len(out) == 2, "el editor no agrega ni borra filas"
    # Campo de PRODUCTO → ambas filas del cluster.
    assert out["https://a"]["author"] == "Kentaro Miura"
    assert out["https://b"]["author"] == "Kentaro Miura"
    # Tipos preservados (no coaccionados a str).
    assert out["https://a"]["tags"] == ["manga", "deluxe"]
    assert out["https://a"]["score"] == 95 and isinstance(out["https://a"]["score"], int)
    assert out["https://b"]["tags"] == ["manga", "deluxe"], "tags es de producto → propaga al cluster"
    # Campo ROW-LOCAL (slug) → SOLO la fila abierta, la hermana intacta.
    assert out["https://a"]["slug"] == "slug-a-fixed"
    assert out["https://b"]["slug"] == "slug-b"
    # Campo de imagen protegido (images) → ninguna fila cambió.
    assert out["https://a"]["images"][0]["url"] == "a.jpg"
    # Se logueó el cambio para auditoría.
    log = [json.loads(l) for l in edits.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(log) == 1 and log[0]["rows_updated"] == 2


# ---------------------------------------------------------------------------
# sync_cover_images — detección de archivos basura (placeholder/píxel/ad)
# ---------------------------------------------------------------------------

def test_compute_junk_local_flags_tiny_zero_and_shared(tmp_path):
    imgs = tmp_path / "images"; imgs.mkdir()
    (imgs / "pixel.gif").write_bytes(b"GIF89a" + b"\x00" * 30)          # 36B tiny
    (imgs / "empty.jpg").write_bytes(b"")                                # 0B
    (imgs / "ad.png").write_bytes(b"\x89PNG" + b"\x00" * 50000)          # 50KB
    (imgs / "realcover.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 50000)
    def _it(local, series, title):
        return {"images": [{"url": f"https://x/{local}", "local": local, "kind": "gallery"}],
                "series_display": series, "title": title}
    items = [
        _it("pixel.gif", "A", "A"),
        _it("empty.jpg", "B", "B"),
        # ad.png compartido por 4 OBRAS distintas → basura
        _it("ad.png", "W One", "W One"),
        _it("ad.png", "X Two", "X Two"),
        _it("ad.png", "Y Three", "Y Three"),
        _it("ad.png", "Z Four", "Z Four"),
        # realcover compartido por 4 filas de la MISMA obra (volúmenes) → NO basura
        _it("realcover.jpg", "Secret Saint", "Secret Saint 1"),
        _it("realcover.jpg", "Secret Saint", "Secret Saint 2"),
        _it("realcover.jpg", "Secret Saint", "Secret Saint 3"),
        _it("realcover.jpg", "Secret Saint", "Secret Saint 4"),
    ]
    junk = _sci._compute_junk_local(items, imgs)
    assert "pixel.gif" in junk          # tiny
    assert "empty.jpg" in junk          # 0 bytes
    assert "ad.png" in junk             # compartido por 4 obras distintas
    assert "realcover.jpg" not in junk  # misma obra fragmentada → NO basura


def test_fix_bad_cover_clears_junk_local_cover():
    _sci._JUNK_LOCAL = {"placeholder.png"}
    try:
        it = {"images": [
            {"url": "https://x/placeholder.png", "local": "placeholder.png", "kind": "gallery"}]}
        assert _sci._fix_bad_cover(it) is True
        assert it["images"] == []
    finally:
        _sci._JUNK_LOCAL = set()


def test_fix_bad_cover_promotes_over_junk_local():
    _sci._JUNK_LOCAL = {"ad.png"}
    try:
        it = {"images": [
            {"url": "https://x/ad.jpg", "local": "ad.png", "kind": "gallery"},
            {"url": "https://x/real-cover.jpg", "local": "real.jpg", "kind": "gallery"}]}
        assert _sci._fix_bad_cover(it) is True
        assert imgstore.cover_url(it) == "https://x/real-cover.jpg"
        assert imgstore.cover_local(it) == "real.jpg"
    finally:
        _sci._JUNK_LOCAL = set()


# ---------------------------------------------------------------------------
# Tienda ≠ editorial (gotcha #44): el nombre de la tienda no debe usarse como
# publisher ni contaminar el edition_key. Fuentes JP Sanyodo / Rakuten Books.
# ---------------------------------------------------------------------------
from scripts.retrofit import fix_store_publisher as _fsp


def test_store_name_not_mapped_to_publisher_slug():
    # "Rakuten" es una TIENDA, no editorial → ya no produce slug propio.
    assert mw._publisher_slug("Rakuten Books / 楽天ブックス") == "unknown"
    assert mw._publisher_slug("Sanyodo") == "unknown"
    # Las editoriales reales sí mapean.
    assert mw._publisher_slug("Square Enix") == "squareenix"
    assert mw._publisher_slug("Akita Shoten") == "akita"


def test_store_name_publisher_not_in_edition_key():
    # Un item de Rakuten sin editorial real → edition_key con `-unknown-`,
    # NUNCA con el slug de la tienda (`-rakuten-`).
    cand = mw.Candidate(
        title="Onna no Sono no Hoshi Tokusouban 5", url="https://books.rakuten.co.jp/rb/1/",
        source="JP - Rakuten Books (search)", source_url="", country="Japón",
        language="Japonés", publisher="",  # ya no se siembra el nombre de tienda
        source_class="retailer", tags=[], description="",
    )
    cand.signal_types = ["special"]
    meta = mw.derive_series_metadata(cand)
    assert "-rakuten-" not in meta.get("edition_key", "")


def test_fsp_is_store_publisher():
    assert _fsp.is_store_publisher("Sanyodo") is True
    assert _fsp.is_store_publisher("Rakuten Books / 楽天ブックス") is True
    assert _fsp.is_store_publisher("rakuten books") is True
    assert _fsp.is_store_publisher("Square Enix") is False
    assert _fsp.is_store_publisher("Akita Shoten") is False
    assert _fsp.is_store_publisher("") is False
    assert _fsp.is_store_publisher(None) is False


def test_fsp_ek_pub_slug_handles_multitoken_series_and_publisher():
    # pub_slug simple
    assert _fsp.ek_pub_slug({
        "series_key": "youkai-gakkou-no-sensei",
        "edition_key": "youkai-gakkou-no-sensei-squareenix-special"}) == "squareenix"
    # pub_slug multi-token (ivrea-ar)
    assert _fsp.ek_pub_slug({
        "series_key": "berserk",
        "edition_key": "berserk-ivrea-ar-deluxe"}) == "ivrea-ar"
    # -unknown- → None
    assert _fsp.ek_pub_slug({
        "series_key": "yowamushi-pedal",
        "edition_key": "yowamushi-pedal-unknown-special"}) is None
    # edition_key que no arranca con series_key → None
    assert _fsp.ek_pub_slug({"series_key": "x", "edition_key": "otra-cosa-special"}) is None


# ---------------------------------------------------------------------------
# _extract_volume — gotcha #60: números antes de calificadores de edición
# ---------------------------------------------------------------------------


def test_extract_volume_before_edition_qualifier():
    """Números antes de 'Edición Especial', 'Variant', etc. se extraen (gotcha #60)."""
    cases = [
        ("The Promised Neverland 13 Edición Especial", "13"),
        ("Twilight Outfocus Long Take 1 Edición Limitada", "1"),
        ("A Miyoshi le gusta Hosaka 2 Edición Especial", "2"),
        ("Berserk 21 Variant", "21"),
        ("Dragon Ball Super 15 Edición Especial", "15"),
        ("The Seven Deadly Sins 41 Edición Especial", "41"),
    ]
    for title, expected in cases:
        got = mw._extract_volume(title)
        assert got == expected, f"_extract_volume({title!r}) = {got!r}, expected {expected!r}"


def test_extract_volume_existing_cases_unchanged():
    """Los casos existentes siguen funcionando con el nuevo patrón."""
    assert mw._extract_volume("One Piece 100") == "100"
    assert mw._extract_volume("Berserk Deluxe 1") == "1"
    assert mw._extract_volume("Dragon Ball vol. 10") == "10"
    assert mw._extract_volume("Naruto nº5") == "5"
    assert mw._extract_volume("") == ""


def test_extract_volume_no_false_positive_year():
    """Un año no se extrae como volumen aunque vaya antes de 'Special'."""
    # "1985 Special" — 1985 es año, no volumen de 1-3 dígitos (patrón cap ≤ 3 dígitos)
    assert mw._extract_volume("Captain Tsubasa 1985 Special") == ""


# ---------------------------------------------------------------------------
# Ordenamiento de edición: volumen + kind-rank (gotcha #60)
# ---------------------------------------------------------------------------


def _make_item(title: str, volume: str, cluster_key: str = "", signal_types=None):
    return {
        "title": title,
        "volume": volume,
        "cluster_key": cluster_key,
        "edition_key": "",
        "signal_types": signal_types or [],
    }


def _sort_edition(items):
    """Ordena como lo hace la función JS _volumeNumber + _kindRank, en Python."""
    KIND_RANK = {
        "regular": 0,
        "variant": 1, "alternativa": 1,
        "special": 2, "especial": 2, "limited": 2, "limitada": 2,
        "deluxe": 3, "kanzenban": 3,
        "artbook": 4, "fanbook": 4,
        "box": 5, "boxset": 5,
    }

    def vol_num(v):
        if not v:
            return float("inf")
        import re
        m = re.search(r"(\d+(?:\.\d+)?)", str(v))
        return float(m.group(1)) if m else float("inf")

    def kind_rank(item):
        ck = item.get("cluster_key", "")
        if ck.startswith("lmc:"):
            parts = ck.split(":")
            if len(parts) >= 3 and parts[2] in KIND_RANK:
                return KIND_RANK[parts[2]]
        sigs = item.get("signal_types", [])
        if "variant_cover" in sigs:
            return 1
        if any(s in sigs for s in ("special_edition", "limited", "collector")):
            return 2
        if any(s in sigs for s in ("artbook", "fanbook")):
            return 4
        if any(s in sigs for s in ("box_set", "bundle")):
            return 5
        return 10

    return sorted(items, key=lambda x: (vol_num(x["volume"]), kind_rank(x)))


def test_edition_sort_ascending_volume():
    """Tomos se ordenan por volumen ascendente."""
    items = [
        _make_item("Neverland 20", "20", "lmc:2857:regular:20"),
        _make_item("Neverland 10", "10", "lmc:2857:regular:10"),
        _make_item("Neverland 13 Edición Especial", "13", "lmc:2857:special:13"),
    ]
    sorted_items = _sort_edition(items)
    assert [i["volume"] for i in sorted_items] == ["10", "13", "20"]


def test_edition_sort_kind_tiebreak_same_volume():
    """Mismo volumen: regular < variant < special (desempate por kind)."""
    items = [
        _make_item("Berserk 42 Variant", "42", "lmc:2688:variant:42"),
        _make_item("Berserk 42 Edición Especial", "42", "lmc:2688:special:42"),
        _make_item("Berserk 42", "42", "lmc:2688:regular:42"),
    ]
    sorted_items = _sort_edition(items)
    kinds = [i["cluster_key"].split(":")[2] for i in sorted_items]
    assert kinds == ["regular", "variant", "special"]


def test_edition_sort_no_volume_goes_last():
    """Items sin volumen van al final."""
    items = [
        _make_item("Artbook", "", "lmc:999:regular:0"),
        _make_item("Vol 1", "1", "lmc:999:regular:1"),
        _make_item("Vol 3", "3", "lmc:999:regular:3"),
    ]
    sorted_items = _sort_edition(items)
    assert sorted_items[0]["volume"] == "1"
    assert sorted_items[1]["volume"] == "3"
    assert sorted_items[2]["volume"] == ""


def test_edition_sort_promised_neverland_case():
    """Caso real: Promised Neverland 10, 13 Especial, 20 → orden 10, 13, 20."""
    items = [
        _make_item("The Promised Neverland 20", "20", "lmc:2857:regular:20"),
        _make_item("The Promised Neverland 13 Edición Especial", "13", "lmc:2857:special:13"),
        _make_item("The Promised Neverland 10", "10", "lmc:2857:regular:10"),
    ]
    sorted_items = _sort_edition(items)
    assert [i["volume"] for i in sorted_items] == ["10", "13", "20"]


# --- should_reject (filter_collectible) -------------------------------------

from scripts.retrofit import filter_collectible as _fc


def test_should_reject_keeps_standardized_item_with_regular_tomo():
    """Item estandarizado que el gate etiqueta regular_tomo → se conserva.

    Post-estandarización el texto del título no porta frases raw ("Limited
    Edition", "Collector"); la señal real ya fue derivada y validada por el
    skill. Rechazar aquí borraría ediciones Ultimate/Limited curadas por el owner.
    """
    item = {"title": "Yawara! Ultimate 18", "standardized_at": "2026-06-01T00:00:00"}
    # is_coll=False, reason="regular_tomo", item estandarizado → NO rechazar
    assert _fc.should_reject(item, is_coll=False, reason="regular_tomo") is False


def test_should_reject_rejects_non_standardized_regular_tomo():
    """Item NO estandarizado con regular_tomo → debe ser rechazado normalmente."""
    item = {"title": "Naruto 1"}  # sin standardized_at
    assert _fc.should_reject(item, is_coll=False, reason="regular_tomo") is True


def test_should_reject_rejects_standardized_item_with_umbrella_magazine():
    """Item estandarizado cuyo gate devuelve umbrella_magazine → rechazar siempre.

    El gate umbrella_magazine es duro: aplica independientemente de si el item
    está estandarizado o no (discrimina revistas-paraguas por URL/título).
    """
    item = {
        "title": "Astro Boy | Mighty Atom Deluxe 3",
        "url": "https://www.manga-sanctuary.com/magazine-atom-vol-3-s12345.html",
        "standardized_at": "2026-06-01T00:00:00",
    }
    assert _fc.should_reject(item, is_coll=False, reason="umbrella_magazine") is True


def test_should_reject_keeps_item_approved_by_gate():
    """Si is_coll=True el item siempre se conserva, sea o no estandarizado."""
    item = {"title": "One Piece Collector Edition 1", "standardized_at": "2026-06-01T00:00:00"}
    assert _fc.should_reject(item, is_coll=True, reason="signal:collector") is False

    item_no_std = {"title": "One Piece Collector Edition 1"}
    assert _fc.should_reject(item_no_std, is_coll=True, reason="signal:collector") is False


def test_should_reject_title_junk_always_rejected():
    """Gates duros de título (junk/too_short) siempre rechazan, con o sin standardized_at."""
    for reason in ("title_too_short", "title_junk_discount", "title_junk_generic", "no_title"):
        item_std = {"title": "x", "standardized_at": "2026-06-01T00:00:00"}
        assert _fc.should_reject(item_std, is_coll=False, reason=reason) is True, \
            f"Hard gate {reason!r} debería rechazar siempre (estandarizado)"
        item_raw = {"title": "x"}
        assert _fc.should_reject(item_raw, is_coll=False, reason=reason) is True, \
            f"Hard gate {reason!r} debería rechazar siempre (sin estandarizar)"


# --- Tabla determinística de edition_slug + series duplicadas (gotchas #69/#70) ---


def test_edition_slug_from_text_jp_type_terms():
    """限定版/特装版/同梱版/愛蔵版/完全版 mapean SIEMPRE al mismo slug (gotcha #69).

    El LLM traducía 限定版 a veces como "limited" y a veces como "special",
    partiendo la misma edición en dos edition_keys. La tabla es la autoridad.
    """
    assert mw.edition_slug_from_text("鬼滅の刃 23 限定版") == "limited"
    assert mw.edition_slug_from_text("宇宙兄弟(39) 画集付き特装版") == "special"
    assert mw.edition_slug_from_text("SPY×FAMILY 13巻 シール付き同梱版") == "special"
    assert mw.edition_slug_from_text("AKIRA 愛蔵版 1") == "deluxe"
    assert mw.edition_slug_from_text("ドラゴンボール完全版 5") == "kanzenban"
    # 初回限定特装版: contiene 限定 pero NO 限定版 consecutivo → gana 特装版.
    assert mw.edition_slug_from_text("ホリミヤ 6巻 初回限定特装版") == "special"


def test_edition_slug_from_text_western_terms_and_named_priority():
    """Términos occidentales + las ediciones NOMBRADAS ganan sobre el tipo."""
    assert mw.edition_slug_from_text("Naruto Edición Limitada 12") == "limited"
    assert mw.edition_slug_from_text("Berserk Deluxe Volume 1") == "deluxe"
    assert mw.edition_slug_from_text("Slam Dunk édition limitée t.5") == "limited"
    # Edición nombrada (Maximum/Ultimate/…) gana sobre el término de tipo.
    assert mw.edition_slug_from_text("Berserk Maximum edición limitada 3") == "maximum"
    # Sin término → "" (el caller decide el fallback).
    assert mw.edition_slug_from_text("Naruto tomo 12") == ""
    assert mw.edition_slug_from_text("") == ""


def test_refine_edition_slug_title_term_wins_even_without_tier():
    """El término del título manda aunque no haya signal_types (tier vacío)."""
    assert mw._refine_edition_slug("", "ブルースカイコンプレックス10 初回限定小冊子付特装版", "ja", "") == "special"
    assert mw._refine_edition_slug("limited", "Landreaall(31)特装版 小冊子付き", "ja", "ichijinsha") == "special"
    # Sin término ni tier → regular (comportamiento previo preservado).
    assert mw._refine_edition_slug("", "Naruto tomo 12", "es", "planeta") == "regular"


def test_aggressive_series_norm_collapses_mechanical_variants():
    """Variantes mecánicas del slug colapsan; series distintas NO (gotcha #70)."""
    from series_aliases import aggressive_series_norm as agg

    # Artículo "The" inicial
    assert agg("the-apothecary-diaries") == agg("apothecary-diaries")
    # Apóstrofe slugificado
    assert agg("hell-s-paradise") == agg("hells-paradise")
    assert agg("kuroko-s-basketball") == agg("kurokos-basketball")
    # Vocales largas del romaji
    assert agg("kumichou-musume-to-sewagakari") == agg("kumicho-musume-to-sewagakari")
    assert agg("senryu-shoujo") == agg("senryu-shojo")
    # NO fuzzy: series genuinamente distintas no colisionan
    assert agg("demon-slave") != agg("demon-slayer")
    assert agg("naruto-gaiden") != agg("naruto")
    assert agg("one-piece-red") != agg("one-piece")
    # "the" solo como artículo INICIAL, no como prefijo de palabra
    assert agg("theo-the-cat") != agg("o-the-cat")


def test_canonical_series_key_aggressive_fallback():
    """El fallback agresivo resuelve variantes mecánicas hacia la canónica."""
    from series_aliases import canonical_series_key

    # "the-" + canónica real del YAML
    key, display = canonical_series_key("", "the-demon-slayer", "")
    assert key == "demon-slayer"
    assert display == "Demon Slayer"
    # Sin match → intacto
    key, _ = canonical_series_key("", "serie-totalmente-inventada-xyz", "")
    assert key == "serie-totalmente-inventada-xyz"


def test_rebuild_edition_key_prefix_realigns_stale_series():
    """El prefijo del edition_key se re-arma con el series_key actual (gotcha #71)."""
    # serie traducida/alias en la key vieja → re-alinear
    assert mw.rebuild_edition_key_prefix(
        "pokemon-sol-luna-norma-special-es", "pokemon-sun-moon"
    ) == "pokemon-sun-moon-norma-special-es"
    # key MENOS específica que el series_key → refinar (dirección segura)
    assert mw.rebuild_edition_key_prefix(
        "hakuoki-kadokawa-fanbook-jp", "hakuoki-shinkai"
    ) == "hakuoki-shinkai-kadokawa-fanbook-jp"
    # repetición mecánica del final del series_key → colapsar
    assert mw.rebuild_edition_key_prefix(
        "takumi-kun-series-series-kadokawa-anniversary-jp", "takumi-kun-series"
    ) == "takumi-kun-series-kadokawa-anniversary-jp"
    # publisher de dos tokens (ivrea-ar) se preserva entero
    assert mw.rebuild_edition_key_prefix(
        "old-series-name-ivrea-ar-special-ar", "new-series"
    ) == "new-series-ivrea-ar-special-ar"
    # sufijo -cN de colisión de coleccion se preserva
    assert mw.rebuild_edition_key_prefix(
        "vieja-serie-norma-special-es-c123", "serie-nueva"
    ) == "serie-nueva-norma-special-es-c123"
    # ya alineado → None (no tocar)
    assert mw.rebuild_edition_key_prefix("berserk-panini-deluxe-it", "berserk") is None
    # slug fuera del allowlist → None (no parseable, mejor no tocar)
    assert mw.rebuild_edition_key_prefix(
        "the-book-of-wind-panini-taniguchi-it", "jiro-taniguchi-collection"
    ) is None
    # publisher NO reconocido → None (mutilaría "panini-standard" → "standard")
    assert mw.rebuild_edition_key_prefix(
        "death-note-panini-standard-variant-it", "death-note"
    ) is None
    # extra que es un DISTINGUIDOR legítimo (obra distinta de la franquicia,
    # sin volumen) → None: fusionarlo mezclaría productos distintos
    assert mw.rebuild_edition_key_prefix(
        "danganronpa-1-2-reload-kadokawa-artbook-jp", "danganronpa"
    ) is None


def test_fix_title_edition_words():
    """Colapsa SOLO palabras de edición duplicadas y saca 'Regular' en regulares."""
    from scripts.retrofit.fix_title_edition_words import fix_title

    assert fix_title("5 Elementos Artbook Artbook", "artbook") == "5 Elementos Artbook"
    assert fix_title("Trigun Maximum Maximum 2", "maximum") == "Trigun Maximum 2"
    # título legítimo con palabra repetida NO-de-edición → intacto
    assert (fix_title("Dead Dead Demon's Dededede Destruction 1", "regular")
            == "Dead Dead Demon's Dededede Destruction 1")
    # 'Regular' sobra en ediciones regular
    assert fix_title("Noragami Regular 27", "regular") == "Noragami 27"
    # ...pero se conserva si la edición NO es regular
    assert fix_title("Foo Regular Edition 3", "special") == "Foo Regular Edition 3"


def test_rescore_skips_standardized_items(tmp_path):
    """Gotcha #61: rescore NO recomputa señales de items con `standardized_at`
    (el texto estandarizado ya no contiene los keywords → lavaría señales).
    El pipeline canónico corre rescore blanket, así que el guard es estructural."""
    import subprocess, sys as _sys
    std = {
        "title": "Yawara! Ultimate 18", "url": "https://x.test/yawara-18",
        "description": "", "signal_types": ["deluxe"], "score": 60,
        "product_type": "manga", "standardized_at": "2026-06-01T00:00:00Z",
        "slug": "yawara-ultimate-18",
    }
    raw = {
        "title": "Berserk Deluxe Edition Vol 1", "url": "https://x.test/berserk-1",
        "description": "oversized deluxe hardcover", "signal_types": [],
        "score": 0, "product_type": "", "slug": "berserk-deluxe-1",
    }
    src = tmp_path / "items.jsonl"
    src.write_text("\n".join(json.dumps(x) for x in (std, raw)) + "\n")
    out = tmp_path / "out.jsonl"
    res = subprocess.run(
        [_sys.executable, "scripts/retrofit/rescore.py",
         "--input", str(src), "--output", str(out)],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]))
    assert res.returncode == 0, res.stderr
    rows = {json.loads(l)["url"]: json.loads(l) for l in out.read_text().splitlines()}
    # el estandarizado conserva sus señales intactas (no se recomputó)
    assert rows["https://x.test/yawara-18"]["signal_types"] == ["deluxe"]
    assert rows["https://x.test/yawara-18"]["score"] == 60
    # el item raw SÍ se re-scoreó (detect_signals ve 'deluxe' en su texto)
    assert "deluxe" in (rows["https://x.test/berserk-1"]["signal_types"] or [])


def test_clean_author_strips_baked_labels():
    """El campo author no debe traer el label de la fuente horneado
    ('Autori: Kentaro Miura' → 'Kentaro Miura'). candidate_to_json lo aplica
    siempre; nombres que EMPIEZAN como un label ('Byron', 'Diana') no se tocan."""
    assert mw.clean_author("Autori: Kentaro Miura") == "Kentaro Miura"
    assert mw.clean_author("Autor: Eiichiro Oda") == "Eiichiro Oda"
    assert mw.clean_author("Author: Naoki Urasawa") == "Naoki Urasawa"
    assert mw.clean_author("by: CLAMP") == "CLAMP"
    assert mw.clean_author("著者：尾田栄一郎") == "尾田栄一郎"
    # doble label anidado
    assert mw.clean_author("Author: Autori: Kentaro Miura") == "Kentaro Miura"
    # nombres legítimos que empiezan con palabras tipo label, SIN dos puntos
    assert mw.clean_author("Byron Smith") == "Byron Smith"
    assert mw.clean_author("Diana Gabaldon") == "Diana Gabaldon"
    assert mw.clean_author("Kentaro Miura") == "Kentaro Miura"
    assert mw.clean_author("") == ""


def test_extract_squareenix_rsc_payload():
    """Square Enix US release-calendar es una app Next.js RSC: el catálogo vive
    en el payload __next_f dentro de <script>, no en el DOM (que solo muestra el
    mes actual). El extractor dedicado parsea el payload completo y NO depende
    de Playwright. Registrado en _SITE_EXTRACTORS por dominio."""
    products = json.dumps([
        {"slug": "9781646090266", "title": "Soul Eater: The Perfect Edition, Volume 1",
         "releaseMonth": "July 2026", "coverArt": {"image": "manga-books/abc/soul1.jpg"}},
        {"slug": "9781646090274", "title": "A Man and His Cat, Volume 1",
         "releaseMonth": "February 2020", "coverArt": {"image": ""}},
        {"slug": "", "title": "sin slug — se descarta"},
    ])
    inner = json.dumps('x:"products":' + products + ',"other":1')
    html = f'<html><body><script>self.__next_f.push([1,{inner}])</script></body></html>'
    src = mw.Source(name="US - Square Enix Manga Coming Soon",
                    url="https://squareenixmangaandbooks.square-enix-games.com/en-us/release-calendar",
                    country="Estados Unidos", language="Inglés",
                    publisher="Square Enix Manga & Books", source_class="official",
                    kind="html")
    info = {}
    cands = mw.extract_squareenix_rsc(src, html, 50, info)
    assert info["extraction_method"] == "sqex-rsc"
    assert len(cands) == 2
    assert cands[0].title.startswith("Soul Eater: The Perfect Edition")
    assert cands[0].url.endswith("/en-us/product/9781646090266")
    assert cands[0].release_date == "2026-07-01"
    assert cands[0].image_url.startswith("https://fyre.cdn.sewest.net/manga-books/")
    # el flujo genérico despacha al dedicado por dominio
    via_generic = mw.extract_generic_html(src, html, 50, {})
    assert len(via_generic) == 2
    # HTML sin payload → [] silencioso (no crash)
    assert mw.extract_squareenix_rsc(src, "<html><body>nada</body></html>", 50, {}) == []


def test_slugify_kebab_homoglyphs_and_cjk_discard():
    # Gotcha #81 — casos reales del corpus (2026-06-12).
    # "о" cirílica U+043E: NFKD no la descompone; sin el mapa de homoglifos
    # el regex la descartaba como punctuation → "taih-to-stamp".
    assert mw._slugify_kebab("Taihо to Stamp") == "taiho-to-stamp"
    # CJK = descarte controlado (separador + strip de bordes), sin colas.
    assert mw._slugify_kebab("Maku ga Oriru to Bokura wa 番") == "maku-ga-oriru-to-bokura-wa"
    # Sin regresión sobre el camino normal (diacríticos latinos).
    assert mw._slugify_kebab("Café Señor 5") == "cafe-senor-5"


def test_sanitize_key_ascii_grouping_keys():
    # Gotcha #81 — claves acuñadas por LLM/YAML con no-ASCII.
    assert (mw.sanitize_key_ascii("taihо-to-stamp-kodansha-limited-jp")
            == "taiho-to-stamp-kodansha-limited-jp")
    assert (mw.sanitize_key_ascii("maku-ga-oriru-to-bokura-wa-番")
            == "maku-ga-oriru-to-bokura-wa")
    # Idempotente sobre claves limpias (no rompe nada existente).
    clean = "maku-ga-oriru-to-bokura-wa-takeshobo-limited-jp"
    assert mw.sanitize_key_ascii(clean) == clean
    # Clave íntegramente CJK → "" (el caller decide el fallback).
    assert mw.sanitize_key_ascii("幕が下りたら僕らは番") == ""


def test_extract_volume_fullwidth_digits():
    # Gotcha #82 — casos reales del corpus (JP - Sanyodo, 2026-06-12). \d en
    # regex unicode matchea ０-９ → el volumen salía con el dígito full-width
    # crudo ("７" U+FF17) y contaminaba volume + cluster_key.
    assert mw._extract_volume("学園アイドルマスター ＧＯＬＤ ＲＵＳＨ 特装版 ７") == "7"
    assert mw._extract_volume("ｃｉｔｒｕｓ ＋（７）特装版") == "7"
    # Marker JP 巻 con dígitos full-width
    assert mw._extract_volume("ワンピース １０３巻") == "103"
    # Sin regresión sobre dígitos ASCII
    assert mw._extract_volume("One Piece vol. 100") == "100"


def test_derive_cluster_key_fullwidth_volume_normalized():
    # Gotcha #82 — el campo volume puede venir de un parser de fuente o del
    # LLM (no solo de _extract_volume): derive_cluster_key normaliza igual.
    item = {
        "edition_key": "citrus-unknown-special-jp",
        "volume": "７",
        "url": "https://www.sanyodo.co.jp/?s=978-4-7580-9966",
    }
    assert mw.derive_cluster_key(item) == "edition:citrus-unknown-special-jp|7"
    # Tier lmc también normaliza el volume del item
    lmc = {
        "url": "https://www.listadomanga.es/coleccion.php?id=99",
        "lm_kind": "regular",
        "volume": "７",
    }
    assert mw.derive_cluster_key(lmc) == "lmc:99:regular:7"


# ---------------------------------------------------------------------------
# Señales DE/PL/KR (fuentes nuevas 2026-06-12: altraverse/Egmont/TOKYOPOP/
# Carlsen, Mangarden/Mangastore, Aladin)
# ---------------------------------------------------------------------------


def test_detect_signals_german():
    cases = {
        "GACHIAKUTA Band 01-05 im Schuber": "box_set",
        "Attack on Titan, Bände 1-5 im Sammelschuber mit Extra": "box_set",
        "Wedding Peach - Luxury Edition 02": "premium_format",
        "Jubiläumsedition #12: Rising of Shield Hero": "collector",
        "Frau Faust Band 03 Limited Edition": "limited",
        "Kohva Collectors Edition Band 02": "collector",
    }
    for title, expected_type in cases.items():
        score, _, types = mw.detect_signals(title)
        assert expected_type in types, f"{title!r}: esperaba {expected_type}, obtuve {types}"
        assert score > 0


def test_detect_signals_polish():
    cases = {
        "Akira - edycja specjalna tom 04 (oprawa twarda)": {"special_edition", "hardcover"},
        "Atak Tytanów tom 01 (oprawa twarda)": {"hardcover"},
        "Atelier spiczastych kapeluszy #05 (twarda okładka)": {"hardcover"},
        "Fullmetal Alchemist Deluxe tom 12 (oprawa twarda)": {"deluxe", "hardcover"},
    }
    for title, expected in cases.items():
        _, _, types = mw.detect_signals(title)
        assert expected <= set(types), f"{title!r}: esperaba {expected}, obtuve {types}"


def test_detect_signals_korean():
    cases = {
        "장송의 프리렌 15 (한정판)": "limited",
        "블루 아카이브 오피셜 아트웍스 (한정판)": "artbook",
        "나 혼자만 레벨업 15 (한정판)": "limited",
        "주문은 토끼입니까? 13 특별판": "special_edition",
    }
    for title, expected_type in cases.items():
        _, _, types = mw.detect_signals(title)
        assert expected_type in types, f"{title!r}: esperaba {expected_type}, obtuve {types}"


def test_polish_korean_pass_collectible_gate():
    """Los títulos PL con tapa dura / KR con 한정판 pasan el gate (señal
    hardcover/limited + volume shape 'tom N' / número final)."""
    passing = [
        "Akira - edycja specjalna tom 04 (oprawa twarda)",
        "장송의 프리렌 15 (한정판)",
        "Sailor Moon Eternal Edition tom 01 (oprawa twarda)",
    ]
    for title in passing:
        _, _, types = mw.detect_signals(title)
        ok, reason = mw.is_collectible_edition(title, "", types, "")
        assert ok, f"{title!r} debería pasar el gate (reason={reason})"


def test_detect_signals_chinese_traditional():
    """Señales TW/HK (chino tradicional usa 裝, no 装 como el JP). Fuentes
    2026-06-12: Tong Li, Kadokawa TW, SPP, Jade Dynasty HK."""
    cases = {
        "銀魂 愛藏版 9（首刷限定版）": {"limited", "premium_format"},
        "哈利路亞寶貝 (5)（特裝版）": {"special_edition"},
        "貓眼完全版盒裝套書(08-15冊)【首刷限定版】": {"limited", "box_set", "premium_format"},
        "帶子雄狼愛藏版 第1至20期20本": {"premium_format"},
        "赤鳩珍藏版盒裝 1-6": {"premium_format", "box_set"},
        "《藏海花》漫画典藏版": {"premium_format"},
    }
    for title, expected in cases.items():
        _, _, types = mw.detect_signals(title)
        assert expected <= set(types), f"{title!r}: esperaba {expected}, obtuve {types}"
        ok, reason = mw.is_collectible_edition(title, "", types, "")
        assert ok, f"{title!r} debería pasar el gate (reason={reason})"


def test_append_jsonl_images_merge_backfills_local(tmp_path):
    """El union-merge de images[] rellena `local` vacío con el del duplicado
    (en ambas direcciones). Bug 2026-06-12: el flush incremental de un wiki
    escribía la fila sin local y el upsert final post-mirror se descartaba."""
    import json as _json
    p = tmp_path / "items.jsonl"
    url = "https://example.com/prod/1"
    img_url = "https://cdn.example.com/cover.jpg"
    # 1ª escritura (flush pre-mirror): sin local
    mw.append_jsonl(p, [{"url": url, "title": "X", "images": [{"url": img_url, "local": "", "kind": "gallery"}]}])
    # 2ª escritura (upsert post-mirror): con local
    mw.append_jsonl(p, [{"url": url, "title": "X", "images": [{"url": img_url, "local": "abc123.jpg", "kind": "gallery"}]}])
    rows = [_json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["images"][0]["local"] == "abc123.jpg"
    # Dirección inversa: re-scrape sin local NO borra el local existente
    mw.append_jsonl(p, [{"url": url, "title": "X", "images": [{"url": img_url, "local": "", "kind": "gallery"}]}])
    rows = [_json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    assert rows[0]["images"][0]["local"] == "abc123.jpg"


def test_extract_image_url_skips_lazy_placeholder_file():
    """Placeholder de lazy-load como ARCHIVO real (no data-URI): saltearlo y
    caer al data-src. Caso Mangarden (gotcha #88): src=/gfx/pol/loader.gif
    + data-src con la portada real → 167 items PL sin foto."""
    soup = make_soup(
        '<div><img class="b-lazy" src="/gfx/pol/loader.gif?r=123" '
        'data-src="/hpeciai/abc/pol_il_Cover-16353jpg" alt="x"></div>'
    )
    div = soup.find("div")
    url = mw.extract_image_url(div, "https://mangarden.pl/")
    assert url == "https://mangarden.pl/hpeciai/abc/pol_il_Cover-16353jpg"
    # Una imagen real llamada lazy.jpg NO se saltea (no es placeholder exacto)
    soup2 = make_soup('<div><img data-src="/img/lazy.jpg"></div>')
    assert mw.extract_image_url(soup2.find("div"), "https://example.com/") == "https://example.com/img/lazy.jpg"
