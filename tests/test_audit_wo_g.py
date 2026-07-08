"""WO-G (auditoría post-scrape) — paridad de la clave de dedup de imágenes.

La clave de dedup del carrusel de imágenes DEBE ser la misma en TRES lugares
(invariante en docs/reference/images.md:47-52):

  - Python `mw._img_stem` (scripts/manga_watch.py), que delega en
    `mw._gallery_url_normalize` — la REFERENCIA CANÓNICA, usada por
    `merge_cluster` para unir `images[]` cross-fuente.
  - `imgKey` en web/index.html (dedup del carrusel a nivel cluster).
  - `imageKey` en web-next/lib/images.ts (dedup del carrusel a nivel cluster).

Este archivo NO reimplementa la lógica: importa scripts/manga_watch.py y
ejerce las funciones reales. La tabla de fixtures de abajo es la fuente
compartida con web-next/__tests__/images.test.ts (misma lista URL -> clave
esperada) — si agregás un caso acá, agregalo también allá.
"""

from __future__ import annotations

import pytest

from scripts import manga_watch as mw

# ---------------------------------------------------------------------------
# Tabla de fixtures compartida con web-next/__tests__/images.test.ts.
# (url, clave esperada de mw._img_stem == imgKey (index.html) == imageKey
# (web-next), nota)
# ---------------------------------------------------------------------------
IMAGE_KEY_FIXTURES: list[tuple[str, str, str]] = [
    (
        "https://cdn.shop.com/files/cover_600x600.jpg",
        "cdn.shop.com/files/cover.jpg",
        "Shopify thumb NxN (guion bajo) — dedupea contra la full",
    ),
    (
        "https://cdn.shop.com/files/cover.jpg",
        "cdn.shop.com/files/cover.jpg",
        "Shopify full (sin sufijo) — misma clave que el thumb de arriba",
    ),
    (
        "https://cdn.shop.com/files/cover_grande.jpg",
        "cdn.shop.com/files/cover.jpg",
        "Shopify sufijo con nombre (_grande) — también se stripea",
    ),
    (
        "https://example.com/wp-content/uploads/cover-800x600.jpg",
        "example.com/wp-content/uploads/cover-800x600.jpg",
        "WordPress -NxN (guion medio) — NO se stripea (gap conocido, ver "
        "test_gallery_url_normalize_does_not_strip_wordpress_hyphen_suffix)",
    ),
    (
        "https://example.com/wp-content/uploads/cover.jpg",
        "example.com/wp-content/uploads/cover.jpg",
        "WordPress full — clave DISTINTA a la de -800x600.jpg de arriba "
        "(no dedupean entre sí hoy)",
    ),
    (
        "https://example.com/img.jpg?v=12345&utm_source=x",
        "example.com/img.jpg",
        "query params se descartan por completo",
    ),
    (
        "https://example.com/img.jpg?v=1#main",
        "example.com/img.jpg",
        "fragment pegado a un query param que se descarta entero — "
        "coincide en las 3 implementaciones",
    ),
    (
        "http://example.com/img.jpg",
        "example.com/img.jpg",
        "scheme http se stripea",
    ),
    (
        "https://example.com/img.jpg",
        "example.com/img.jpg",
        "scheme https se stripea — misma clave que http de arriba",
    ),
    (
        "https://example.com/plain-cover.png",
        "example.com/plain-cover.png",
        "URL sin nada que strippear",
    ),
    (
        "https://EXAMPLE.com/IMG.JPG",
        "example.com/img.jpg",
        "case-insensitive (host + path se lowercasean)",
    ),
    (
        "https://cdn.shop.com/files/cover_100x100.jpg?v=99",
        "cdn.shop.com/files/cover.jpg",
        "sufijo Shopify + query combinados",
    ),
]


@pytest.mark.parametrize(
    "url,expected,note",
    IMAGE_KEY_FIXTURES,
    ids=[f"{i:02d}_{note[:40]}" for i, (_, _, note) in enumerate(IMAGE_KEY_FIXTURES)],
)
def test_img_stem_matches_fixture_table(url: str, expected: str, note: str) -> None:
    assert mw._img_stem(url) == expected, note


def test_gallery_url_normalize_strips_shopify_underscore_suffix() -> None:
    """`_gallery_url_normalize` (el helper de más bajo nivel que `_img_stem`
    delega) sólo strippea sufijos de tamaño con GUION BAJO estilo Shopify."""
    assert mw._gallery_url_normalize("https://x.com/a_600x600.jpg") == "https://x.com/a.jpg"
    assert mw._gallery_url_normalize("https://x.com/a_grande.jpg") == "https://x.com/a.jpg"


def test_gallery_url_normalize_does_not_strip_wordpress_hyphen_suffix() -> None:
    """Gap conocido de la referencia canónica: el docstring de `_img_stem`
    (scripts/manga_watch.py, comentario sobre `_gallery_url_normalize`)
    menciona "WP -NxM" como caso cubierto, pero la regex sólo tiene la rama
    con GUION BAJO (`_\\d+x\\d+`) — nunca implementó una rama con guion medio
    (`-\\d+x\\d+`, el patrón real que usa WordPress: `cover-800x600.jpg`).
    Documentamos el comportamiento REAL (no el aspiracional) porque este WO
    está scopeado a portar la semántica EXACTA a index.html/images.ts, no a
    arreglar scripts/manga_watch.py (fuera de dominio). Si alguien quiere
    cerrar el gap, hay que tocar los TRES lugares a la vez."""
    assert (
        mw._gallery_url_normalize("https://x.com/a-800x600.jpg")
        == "https://x.com/a-800x600.jpg"
    )


def test_img_stem_bare_fragment_without_query_is_a_python_only_quirk() -> None:
    """`_img_stem` NO stripea explícitamente un `#fragment` standalone (sin
    `?` antes) — sólo lo pierde como side-effect cuando el fragment queda
    pegado a un query param que `_gallery_url_normalize` descarta entero (ver
    fixture "fragment pegado a un query param" arriba). En datos reales esto
    nunca se ejercita: `canonicalize_url()` (scripts/manga_watch.py, usa
    `urldefrag()`) ya elimina el fragment ANTES de persistir la URL en
    `images[]`, así que ninguna URL guardada llega acá con un `#` bare.

    `imgKey` (web/index.html) e `imageKey` (web-next/lib/images.ts) SÍ
    stripean `#` explícitamente por robustez (piden esto en WO-G) — no rompe
    la paridad real porque este input nunca ocurre en el corpus; sólo diverge
    en este caso sintético que no representa datos reales."""
    assert mw._img_stem("https://example.com/img.jpg#main") == "example.com/img.jpg#main"
