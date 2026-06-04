#!/usr/bin/env python3
"""fetch_better_covers.py — busca portadas en mayor resolución para items con imagen chica.

Estrategia por prioridad (orden de aplicación):
1. Items CON ISBN → CDN determinístico (sin búsqueda web, gratis/ilimitado):
   a. Amazon CDN  (m.media-amazon.com)
   b. PRH CDN     (images.penguinrandomhouse.com) — solo prefijos 978-0/978-1 (EN)
   c. OpenLibrary (covers.openlibrary.org)         — cobertura ~40-60% ISBNs globales
2. Items SIN ISBN (y sin signal variant_cover/retailer_exclusive) → búsqueda web:
   a. Serper      (SERPER_API_KEY en .env o --serper-key) — 2 500 queries gratis sin tarjeta
   b. Tavily      (TAVILY_API_KEY en .env o --tavily-key) — 1 000 queries/mes gratis
   Se usa el primero disponible según prioridad.
3. Verificación por perceptual hash (aHash 8×8): si la imagen candidata tiene hamming
   distance <= --max-hash-dist (default 12 de 64 bits), se acepta como "misma portada".
   Adicionalmente, la candidata debe tener >= --min-gain × más píxeles que la existente.

Items con signal variant_cover o retailer_exclusive se saltan siempre — web search
devuelve la portada regular, no la variante.

Uso:
    .venv/bin/python scripts/retrofit/fetch_better_covers.py --dry-run
    .venv/bin/python scripts/retrofit/fetch_better_covers.py --limit 50
    .venv/bin/python scripts/retrofit/fetch_better_covers.py          # todos
    .venv/bin/python scripts/retrofit/fetch_better_covers.py --no-search  # solo CDN ISBN
    .venv/bin/python scripts/retrofit/fetch_better_covers.py --serper-key abc123...
    .venv/bin/python scripts/retrofit/fetch_better_covers.py --tavily-key tvly-...

Requiere: Pillow (pip install Pillow)
APIs opcionales (se auto-cargan desde .env):
  SERPER_API_KEY  — Serper Google Images API, 2 500 queries gratis sin tarjeta (serper.dev)
  TAVILY_API_KEY  — Tavily Search API, 1 000 queries/mes gratis
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import struct
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, quote_plus, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

# ── Rutas del proyecto ────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = _HERE / "scripts"
if str(_SCRIPTS) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_SCRIPTS))
from manga_watch import backup_and_rotate  # noqa: E402
_ITEMS_PATH = _HERE / "data" / "items.jsonl"
_IMAGES_DIR = _HERE / "data" / "images"

# ── Parámetros de calidad ─────────────────────────────────────────────────────
DEFAULT_MIN_PIXELS = 100_000   # imágenes por debajo de este umbral son candidatas
DEFAULT_MIN_GAIN = 1.5         # candidata debe tener >= 1.5× los píxeles actuales
DEFAULT_MAX_HASH_DIST = 12     # distancia Hamming máxima (de 64 bits) para aceptar
DEFAULT_WORKERS = 2            # requests HTTP paralelos
_MAX_BYTES = 10 * 1024 * 1024 # máximo de bytes a descargar por imagen

# ── User-Agent ────────────────────────────────────────────────────────────────
_UA = "manga-watch-personal/0.2"
_HEADERS = {"User-Agent": _UA, "Accept-Language": "es,en;q=0.8,ja;q=0.6"}

# ── Signals que NO deben recibir web-search (riesgo de cover equivocada) ──────
_SKIP_SIGNALS = frozenset({"variant_cover", "retailer_exclusive"})


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades de imagen
# ──────────────────────────────────────────────────────────────────────────────

def _get_pixels_from_bytes(data: bytes) -> int:
    """Devuelve el área en píxeles del primer frame de la imagen."""
    try:
        if data[:3] == b"\xff\xd8\xff":  # JPEG
            i = 2
            while i < len(data) - 10:
                if data[i] != 0xFF:
                    break
                marker = data[i : i + 2]
                i += 2
                if marker in (b"\xff\xc0", b"\xff\xc1", b"\xff\xc2"):
                    h, w = struct.unpack(">HH", data[i + 3 : i + 7])
                    return w * h
                length = struct.unpack(">H", data[i : i + 2])[0]
                i += length
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", data[16:24])
            return w * h
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            # VP8 frame: ancho y alto en bits 14..29 y 30..43 del VP8 bitstream
            vp8 = data[data.index(b"VP8 ") + 8 :]  # type: ignore[arg-type]
            w = (struct.unpack("<H", vp8[6:8])[0] & 0x3FFF) + 1
            h = (struct.unpack("<H", vp8[8:10])[0] & 0x3FFF) + 1
            return w * h
    except Exception:
        pass
    return 0


def _get_dims_from_bytes(data: bytes) -> tuple[int, int]:
    """Devuelve (width, height)."""
    try:
        if data[:3] == b"\xff\xd8\xff":
            i = 2
            while i < len(data) - 10:
                if data[i] != 0xFF:
                    break
                marker = data[i : i + 2]
                i += 2
                if marker in (b"\xff\xc0", b"\xff\xc1", b"\xff\xc2"):
                    h, w = struct.unpack(">HH", data[i + 3 : i + 7])
                    return w, h
                length = struct.unpack(">H", data[i : i + 2])[0]
                i += length
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", data[16:24])
            return w, h
    except Exception:
        pass
    return 0, 0


def _extension_from_magic(data: bytes) -> str:
    if len(data) < 12:
        return ""
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[4:12] in (b"ftypavif", b"ftypavis"):
        return ".avif"
    return ""


def _ahash(data: bytes, hash_size: int = 8) -> Optional[int]:
    """Average hash — perceptual hash simple (hash_size^2 bits)."""
    try:
        from PIL import Image  # noqa: PLC0415

        img = Image.open(io.BytesIO(data)).convert("L").resize(
            (hash_size, hash_size), Image.LANCZOS
        )
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        return sum(1 << i for i, px in enumerate(pixels) if px >= avg)
    except Exception:
        return None


def _hamming(h1: int, h2: int) -> int:
    return bin(h1 ^ h2).count("1")


def _aspect_ratio(w: int, h: int) -> float:
    return w / h if h else 1.0


def _same_cover(
    original_bytes: bytes,
    candidate_bytes: bytes,
    max_hash_dist: int,
) -> bool:
    """
    True si la candidata parece la misma portada que la original.
    Verifica:
      1. Aspect ratio dentro del 20% de tolerancia.
      2. Perceptual hash (aHash 8×8) con distancia Hamming <= max_hash_dist.
    Si PIL no está disponible, solo verifica el aspect ratio.
    """
    ow, oh = _get_dims_from_bytes(original_bytes)
    cw, ch = _get_dims_from_bytes(candidate_bytes)

    # Check aspect ratio
    if ow > 0 and oh > 0 and cw > 0 and ch > 0:
        orig_ar = _aspect_ratio(ow, oh)
        cand_ar = _aspect_ratio(cw, ch)
        diff = abs(orig_ar - cand_ar) / orig_ar
        if diff > 0.25:  # más del 25% diferente → rechazar
            return False

    # Perceptual hash — relajar umbral para imágenes muy pequeñas.
    # Cuando la original es < 30k px (~170×176), el escalado a 8×8 para
    # aHash es tan lossy que la distancia sube 3-5 bits vs una imagen
    # idéntica de mayor resolución. Relajamos +4 bits en esos casos.
    h1 = _ahash(original_bytes)
    h2 = _ahash(candidate_bytes)
    if h1 is not None and h2 is not None:
        dist = _hamming(h1, h2)
        orig_px = ow * oh if ow > 0 and oh > 0 else 0
        effective_threshold = max_hash_dist + (4 if orig_px < 30_000 else 0)
        return dist <= effective_threshold

    # Sin PIL: si aspect ratio OK, aceptamos
    return True


# ──────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────────────────────────────────────

def _fetch(url: str, session: requests.Session, timeout: tuple = (8, 20)) -> Optional[bytes]:
    """Descarga una URL y devuelve los bytes. None si falla."""
    try:
        r = session.get(url, timeout=timeout, stream=True, headers=_HEADERS)
        if r.status_code != 200:
            return None
        body = bytearray()
        for chunk in r.iter_content(65536):
            if chunk:
                body.extend(chunk)
            if len(body) > _MAX_BYTES:
                return None
        return bytes(body)
    except requests.RequestException:
        return None
    finally:
        try:
            r.close()  # type: ignore[possibly-undefined]
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# ISBN → CDN lookup
# ──────────────────────────────────────────────────────────────────────────────

def _isbn10_to_13(isbn10: str) -> Optional[str]:
    """Convierte ISBN-10 a ISBN-13 (con prefijo 978)."""
    clean = str(isbn10).replace("-", "").replace(" ", "")
    if len(clean) != 10 or not clean[:9].isdigit():
        return None
    base = "978" + clean[:9]
    total = sum(int(base[i]) * (1 if i % 2 == 0 else 3) for i in range(12))
    check = (10 - total % 10) % 10
    return base + str(check)


def _isbn13_to_10(isbn13: str) -> Optional[str]:
    """Convierte ISBN-13 con prefijo 978 a ISBN-10."""
    clean = str(isbn13).replace("-", "").replace(" ", "")
    if len(clean) != 13 or not clean.startswith("978") or not clean[:12].isdigit():
        return None
    body = clean[3:12]
    total = sum(int(body[i]) * (i + 1) for i in range(9))
    check = total % 11
    check_char = "X" if check == 10 else str(check)
    return body + check_char


def _candidates_from_isbn(isbn: str, session: requests.Session) -> list[str]:
    """
    Devuelve URLs candidatas de portadas para el ISBN dado.
    Prueba: Amazon CDN (m.media-amazon.com), PRH CDN.
    """
    candidates: list[str] = []
    clean = str(isbn).replace("-", "").replace(" ", "")

    # ISBN-10 para Amazon CDN
    isbn10: Optional[str] = None
    isbn13: Optional[str] = None
    if len(clean) == 10:
        isbn10 = clean
        isbn13 = _isbn10_to_13(clean)
    elif len(clean) == 13 and clean.startswith(("978", "979")):
        isbn13 = clean
        isbn10 = _isbn13_to_10(clean)

    if isbn10:
        # Amazon global CDN — libro físico
        candidates.append(f"https://m.media-amazon.com/images/P/{isbn10}.09.SCLZZZZZZZ.jpg")
        candidates.append(f"https://images-na.ssl-images-amazon.com/images/P/{isbn10}.09.SCLZZZZZZZ.jpg")

    if isbn13 and isbn13.startswith(("9780", "9781")):
        # PRH CDN — solo EN publishers (prefijo 978-0 / 978-1)
        candidates.append(f"https://images.penguinrandomhouse.com/cover/{isbn13}")

    return candidates


def _candidates_from_isbn_openlibrary(isbn: str, session: requests.Session) -> list[str]:
    """
    Prueba OpenLibrary Covers API — gratis, sin API key, cobertura ~40-60% ISBNs globales.
    URL: https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg
    Devuelve 302→imagen real si existe, 404 si no. Soporta ISBN-10 e ISBN-13.
    """
    clean = str(isbn).replace("-", "").replace(" ", "")
    candidates: list[str] = []

    # OpenLibrary acepta tanto ISBN-10 como ISBN-13 directamente
    if len(clean) in (10, 13):
        candidates.append(f"https://covers.openlibrary.org/b/isbn/{clean}-L.jpg")

    # Si era ISBN-13, probar también la versión ISBN-10
    if len(clean) == 13 and clean.startswith("978"):
        isbn10 = _isbn13_to_10(clean)
        if isbn10:
            candidates.append(f"https://covers.openlibrary.org/b/isbn/{isbn10}-L.jpg")

    # Filtrar: verificar que la URL responde antes de pasar al evaluador principal
    # (OpenLibrary devuelve una imagen de "no cover" de 1×1 px en vez de 404 para algunos)
    valid: list[str] = []
    for url in candidates:
        try:
            r = session.head(url, timeout=(4, 8), allow_redirects=True)
            # Si redirige a la imagen placeholder (no-cover) la descartamos
            final = r.url
            if "nophoto" in final or "no-cover" in final or r.status_code == 404:
                continue
            content_type = r.headers.get("content-type", "")
            if "image" in content_type and r.status_code == 200:
                valid.append(url)
                break  # con uno válido basta
        except Exception:
            continue

    return valid


def _candidates_from_isbn_google_books(isbn: str, session: requests.Session) -> list[str]:
    """
    Google Books API — gratis, sin API key, 6 tamaños de cover.
    Busca por ISBN y extrae `extraLarge` (~800×1200 px) o `large` (~575×800).
    Sin cuota significativa (1,000 req/día sin key).
    """
    clean = str(isbn).replace("-", "").replace(" ", "")
    if len(clean) not in (10, 13):
        return []

    try:
        r = session.get(
            f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean}&maxResults=1",
            timeout=(5, 10),
        )
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []

    items = data.get("items", [])
    if not items:
        return []

    links = items[0].get("volumeInfo", {}).get("imageLinks", {})
    candidates: list[str] = []

    # Priorizar tamaños grandes → chicos
    for size in ("extraLarge", "large", "medium"):
        url = links.get(size, "")
        if url:
            # Google Books usa HTTP — forzar HTTPS
            url = url.replace("http://", "https://")
            # Quitar &edge=curl (efecto visual de página curvada)
            url = url.replace("&edge=curl", "")
            candidates.append(url)
            break  # con el más grande basta

    return candidates



# ──────────────────────────────────────────────────────────────────────────────
# Query builder — construye la búsqueda óptima por item
# ──────────────────────────────────────────────────────────────────────────────

# Término "portada" según idioma del item
_COVER_TERM = {
    "Español":    "portada",
    "Francés":    "couverture",
    "Italiano":   "copertina",
    "Japonés":    "表紙",
    "Portugués":  "capa",
    "Alemán":     "cover",
}

# Cómo referirse al tipo de edición según idioma
# Clave = último segmento del edition_key (edition slug)
_EDITION_HINT = {
    "boxset":    {"Español": "box set",    "Francés": "coffret",   "Italiano": "cofanetto", "default": "box set"},
    "coffret":   {"default": "coffret"},
    "integral":  {"Español": "integral",   "Francés": "intégrale", "default": "integral"},
    "kanzenban": {"default": "kanzenban"},
    "deluxe":    {"Español": "deluxe",     "Francés": "deluxe",    "Italiano": "deluxe",    "default": "deluxe"},
    "collector": {"Español": "coleccionista", "Francés": "collector", "Italiano": "collector", "default": "collector"},
    "hardcover": {"default": "hardcover"},
    "artbook":   {"default": "artbook"},
    "fanbook":   {"default": "fanbook"},
    "limited":   {"Español": "limitada",   "Francés": "limitée",   "Italiano": "limitata",  "default": "limited edition"},
    "omnibus":   {"default": "omnibus"},
    "cofanetto": {"default": "cofanetto"},
    "tankobon":  {"default": ""},
    "regular":   {"default": ""},
}

# Palabras genéricas a quitar del nombre del publisher para la búsqueda
_PUBLISHER_STRIP = frozenset({
    "editorial", "ediciones", "edizioni", "editions", "éditions",
    "manga", "comics", "cómics", "comix", "verlag",
})


def _simplify_publisher(publisher: str) -> str:
    """'Norma Editorial' → 'Norma', 'Panini Manga México' → 'Panini México'."""
    words = [w for w in publisher.split() if w.lower() not in _PUBLISHER_STRIP]
    return " ".join(words[:3])  # máx 3 palabras


def _edition_slug(edition_key: str) -> str:
    """'fullmetal-alchemist-norma-kanzenban' → 'kanzenban'."""
    if not edition_key:
        return ""
    return edition_key.split("-")[-1]


def _build_search_query(item: dict) -> str:
    """
    Construye el query óptimo para buscar la portada de un item.

    Estrategia:
    1. Usa `title_original` si difiere de `title` — el título local (FR/IT/ES)
       es lo que Google Images indexa en los retailers de ese país.
    2. Usa `series_display` como nombre base de la serie (sin sufijos de edición).
    3. Extrae el tipo de edición del `edition_key` y lo adapta al idioma.
    4. Simplifica el publisher (quita palabras genéricas).
    5. Usa el término de "portada" correcto según el idioma del item.
    """
    title       = item.get("title", "")
    title_orig  = item.get("title_original", "")
    series      = item.get("series_display", "")
    publisher   = item.get("publisher", "")
    language    = item.get("language", "")
    edition_key = item.get("edition_key", "")
    volume      = item.get("volume", "")

    cover_term    = _COVER_TERM.get(language, "cover")
    pub_short     = _simplify_publisher(publisher)
    ed_slug       = _edition_slug(edition_key)
    ed_hints      = _EDITION_HINT.get(ed_slug, {})
    edition_hint  = ed_hints.get(language, ed_hints.get("default", ""))

    parts: list[str] = []

    # Base: el título original tal como lo tiene indexado el retailer.
    # NO le agregamos edition hints (artbook, boxset, etc.) porque:
    # 1. El título ya los contiene cuando corresponde
    # 2. Agregarlos duplica ("Artbook artbook") o confunde ("Special" → "artbook")
    # 3. Google busca mejor con el nombre natural del producto
    if title_orig and title_orig != title:
        parts.append(title_orig)
    elif title:
        parts.append(title)
    elif series:
        parts.append(series)

    # Publisher simplificado
    if pub_short:
        parts.append(pub_short)

    # Término de portada en el idioma local
    parts.append(cover_term)

    return " ".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# Serper (Google Images API)
# ──────────────────────────────────────────────────────────────────────────────

_SERPER_API_URL = "https://google.serper.dev/images"


def _search_serper_for_cover(
    query: str,
    api_key: str,
    session: requests.Session,
) -> list[dict]:
    """
    Usa Serper (Google Images API) para buscar portadas hi-res.
    Devuelve lista de dicts con metadata: {url, page_title, domain, width, height}.
    """

    try:
        r = session.post(
            _SERPER_API_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 10},
            timeout=(8, 20),
        )
        if r.status_code != 200:
            return []
        data = r.json()
    except requests.RequestException:
        return []

    result: list[dict] = []
    for img in data.get("images", []):
        url = img.get("imageUrl", "")
        if not url or not _is_plausible_cover(url):
            continue
        w = img.get("imageWidth", 0)
        h = img.get("imageHeight", 0)
        if w > 0 and h > 0 and w * h < 50_000:
            continue
        result.append({
            "url": url,
            "page_title": img.get("title", ""),
            "domain": img.get("domain", ""),
            "width": w,
            "height": h,
        })
        if len(result) >= 5:
            break

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Serper Lens (reverse image search via Google Lens)
# ──────────────────────────────────────────────────────────────────────────────

_SERPER_LENS_URL = "https://google.serper.dev/lens"

# Dominios de baja calidad para reverse image search.
# Estos NUNCA devuelven portadas hi-res útiles — son fotos de usuario,
# ropa, SVGs, videos, o retailers genéricos que no venden manga.
# Lista refinada con feedback real del usuario (2026-05-30).
_LENS_LOW_QUALITY_DOMAINS = frozenset({
    # Social media / UGC — fotos de usuario, memes, screenshots
    "reddit.com", "redd.it", "facebook.com", "fbsbx.com",
    "twitter.com", "x.com", "pbs.twimg.com",
    "instagram.com", "pinterest.com", "pinimg.com",
    "tiktok.com", "flickr.com",
    # Video — thumbnails, no portadas
    "youtube.com", "ytimg.com",
    # Marketplaces de segunda mano — fotos de usuario, no portadas oficiales
    "picclick.com", "picclickimg.com", "mercari.com", "mercdn.net",
    # Retailers genéricos (no manga) — Lens matchea objetos visualmente similares
    "target.com", "walmart.com", "nordstrom.com", "nordstrommedia.com",
    "cettire.com",
    # Herramientas de diseño / assets genéricos
    "mediamodifier.com", "adobe.com", "stock.adobe.com",
    # Documentos legales / servicios
    "foreigndocumentsexpress.com",
    # Libros no-manga
    "goodreads.com", "gr-assets.com",
    # Anime wallpapers / fan art (no portadas oficiales)
    "zerochan.net", "donmai.us", "danbooru",
    # Gaming / indie (no manga)
    "itch.io",
    # Fashion retailers
    "wconcept.com", "redbubble.net", "redbubble.com",
    # Google cache / thumbnails (siempre baja resolución)
    "gstatic.com",
})


# Mapeo idioma → locale de Google (gl/hl) para Lens
_LANG_TO_GL = {
    "Español": "es", "Francés": "fr", "Italiano": "it",
    "Japonés": "jp", "Portugués": "br", "Alemán": "de",
    "Inglés": "us",
}

# Dominios preferidos por mercado — resultados de estos dominios van primero
# porque son del mismo publisher/mercado que el item
_MARKET_PREFERRED_DOMAINS = {
    "es": ["normaeditorial.com", "normacomics.com", "panini.es", "planetadelibros.com",
           "casadellibro.com", "buscalibre.com", "whakoom.com", "listadomanga.es",
           "amazon.es", "agapea.com", "fnac.es"],
    "fr": ["glenat.com", "kana.fr", "ki-oon.com", "meian.fr", "kurokawa.fr",
           "amazon.fr", "fnac.com", "cultura.com", "bdfugue.com"],
    "it": ["starcomics.com", "panini.it", "jpopedizioni.com", "amazon.it",
           "mangadreams.it", "fumetto-online.it"],
    "jp": ["amazon.co.jp", "rakuten.co.jp", "honto.jp", "kinokuniya.co.jp"],
    "de": ["amazon.de", "carlsen.de", "manga-passion.de"],
    "br": ["amazon.com.br", "panini.com.br"],
}


def _search_serper_lens(
    image_url: str,
    api_key: str,
    session: requests.Session,
    language: str = "",
) -> list[dict]:
    """
    Reverse image search via Google Lens (Serper /lens endpoint).
    Usa gl/hl locale para priorizar resultados del mercado correcto.
    Devuelve resultados ordenados: primero los del mismo mercado, después el resto.
    """
    if not image_url or image_url.startswith("data:"):
        return []

    payload: dict = {"url": image_url}
    gl = _LANG_TO_GL.get(language, "")
    if gl:
        payload["gl"] = gl
        payload["hl"] = gl

    try:
        r = session.post(
            _SERPER_LENS_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=(8, 25),
        )
        if r.status_code != 200:
            return []
        data = r.json()
    except requests.RequestException:
        return []

    result: list[dict] = []
    for entry in data.get("organic", []):
        url = entry.get("imageUrl", "")
        if not url:
            continue

        # Filtrar dominios de baja calidad
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if any(bad in domain for bad in _LENS_LOW_QUALITY_DOMAINS):
            continue

        # Filtrar por link de la página (no solo imageUrl domain)
        page_link = entry.get("link", "")
        if page_link:
            page_domain = urlparse(page_link).netloc.lower()
            if any(bad in page_domain for bad in _LENS_LOW_QUALITY_DOMAINS):
                continue

        # Debe tener extensión de imagen o ser de un CDN conocido
        path = parsed.path.lower()
        has_ext = any(path.endswith(e) or f"{e}?" in path or f"{e};" in path
                      for e in (".jpg", ".jpeg", ".png", ".webp"))
        is_cdn = any(h in domain for h in (
            "amazon.com", "media-amazon", "whakoom.com", "normaeditorial.com",
            "normacomics.com", "planetadelibros", "panini", "buscalibre",
            "agapea.com", "casadellibro", "penguin", "abebooks.com",
            "cdn.shopify", "woocommerce", "cloudfront.net",
        ))
        if not has_ext and not is_cdn:
            continue

        result.append({
            "url": url,
            "page_title": entry.get("title", ""),
            "domain": entry.get("source", domain),
            "link": page_link,
        })

    # Priorizar resultados del mismo mercado que el item
    preferred = _MARKET_PREFERRED_DOMAINS.get(gl, [])
    if preferred:
        def _market_score(r: dict) -> int:
            link = (r.get("link", "") + r.get("url", "")).lower()
            for i, pref in enumerate(preferred):
                if pref in link:
                    return i  # más bajo = mejor
            return 999
        result.sort(key=_market_score)

    return result[:8]


# ──────────────────────────────────────────────────────────────────────────────
# Tavily search (fallback de texto)
# ──────────────────────────────────────────────────────────────────────────────

_TAVILY_API_URL = "https://api.tavily.com/search"
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})
_BAD_IMAGE_HOSTS = frozenset({
    "duckduckgo.com", "google.com", "amazon.com", "facebook.com",
    "twitter.com", "youtube.com", "instagram.com",
})
_SKIP_IMAGE_PATHS = frozenset({
    "/images/common/", "/assets/", "/icons/", "/static/", "/ui/",
    "placeholder", "no-image", "noimage", "default",
})


def _load_dotenv() -> None:
    """Carga variables de .env desde la raíz del proyecto si existe."""
    env_path = _HERE / ".env"
    if not env_path.exists():
        return
    with env_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def _is_plausible_cover(url: str) -> bool:
    """Filtra URLs de imagen que probablemente NO son portadas de manga."""
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Debe tener extensión de imagen
    ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
    if ext not in _IMAGE_EXTENSIONS:
        return False

    # Rechazar hosts de redes sociales / trackers
    if any(bad in parsed.netloc for bad in _BAD_IMAGE_HOSTS):
        return False

    # Rechazar paths de assets de UI
    if any(skip in path for skip in _SKIP_IMAGE_PATHS):
        return False

    # Rechazar SVGs
    if path.endswith(".svg"):
        return False

    return True


def _search_tavily_for_cover(
    query: str,
    api_key: str,
    session: requests.Session,
) -> list[str]:
    """
    Usa Tavily Search API con include_images=True para obtener URLs de imagen
    directas sin necesidad de fetchear cada página de resultado.
    Recibe el query ya construido por _build_search_query().
    Límite del plan gratuito: 1 000 queries/mes.
    """

    try:
        r = session.post(
            _TAVILY_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_images": True,
                "include_answer": False,
            },
            timeout=(8, 20),
        )
        if r.status_code != 200:
            return []
        data = r.json()
    except requests.RequestException:
        return []

    # Tavily retorna "images" como lista de strings (URLs directas)
    # cuando include_images=True. Ocasionalmente puede ser lista de dicts
    # con clave "url" — soportamos ambos formatos.
    raw_images = data.get("images", [])
    result: list[str] = []
    for img in raw_images:
        if isinstance(img, str):
            url = img
        elif isinstance(img, dict):
            url = img.get("url", "")
        else:
            continue
        if url and _is_plausible_cover(url):
            result.append(url)
        if len(result) >= 5:
            break
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Guardar imagen y actualizar items.jsonl
# ──────────────────────────────────────────────────────────────────────────────

def _save_image(data: bytes, images_dir: Path) -> Optional[str]:
    """Guarda los bytes como archivo en images_dir. Devuelve el filename."""
    from hashlib import sha256  # noqa: PLC0415

    ext = _extension_from_magic(data)
    if not ext:
        return None
    # Nombre determinístico no colisiona con el existente porque viene de una URL distinta
    stem = sha256(data).hexdigest()[:16]
    filename = stem + ext
    dest = images_dir / filename
    if dest.exists():
        return filename  # ya existe (idempotente)
    tmp = dest.with_name(f"{filename}.{uuid.uuid4().hex}.tmp")
    images_dir.mkdir(parents=True, exist_ok=True)
    try:
        tmp.write_bytes(data)
        tmp.replace(dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        return None
    return filename




def _atomic_write(items_path: Path, rows: list[dict]) -> None:
    tmp = items_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp.replace(items_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ──────────────────────────────────────────────────────────────────────────────
# Validación de página (scraping ligero para verificar publisher/volumen)
# ──────────────────────────────────────────────────────────────────────────────


def _validate_page_content(page_url: str, item: dict, session: requests.Session,
                           verbose: bool = False) -> bool:
    """
    Fetchea la página del resultado de Lens y verifica que el texto mencione
    el publisher o la serie del item. Descarta candidatas de editoriales equivocadas.
    Timeout corto (5s) para no frenar el pipeline.
    """
    if not page_url:
        return True  # sin URL de página, no podemos verificar → aceptar

    publisher = item.get("publisher", "").lower()
    series = item.get("series_display", "").lower()
    title_orig = item.get("title_original", "").lower()
    volume = str(item.get("volume", ""))

    # Palabras clave del publisher que deberían aparecer en la página
    pub_keywords = [w for w in publisher.split() if len(w) >= 4]
    # Palabras clave de la serie (al menos 1 debe aparecer)
    series_keywords = [w for w in series.split() if len(w) >= 4]

    try:
        r = session.get(page_url, timeout=(3, 5), headers={
            "User-Agent": _UA,
            "Accept": "text/html",
        })
        if r.status_code != 200:
            return True  # no pudimos verificar → aceptar
        # Solo leer los primeros 50KB de texto
        text = r.text[:50_000].lower()
    except Exception:
        return True  # timeout/error → aceptar (no penalizar)

    # Verificar que la página mencione la serie
    if series_keywords:
        series_match = sum(1 for w in series_keywords if w in text)
        if series_match == 0:
            if verbose:
                print(f"      page validation: serie '{series[:30]}' no encontrada", flush=True)
            return False

    # Verificar volumen si lo tiene
    if volume and volume.isdigit():
        # Buscar el número del volumen en contexto de "vol", "tome", "tomo", "n°", "#"
        import re
        vol_patterns = [
            rf'\b(?:vol|volume|tomo|tome|n[°ºo]|#)\s*\.?\s*{re.escape(volume)}\b',
            rf'\b{re.escape(volume)}\b',  # al menos el número debe aparecer
        ]
        # Con el primer pattern (estricto) es suficiente si matchea
        # Si no matchea, verificamos que el número al menos aparezca
        if not re.search(vol_patterns[0], text) and not re.search(vol_patterns[1], text):
            if verbose:
                print(f"      page validation: volumen {volume} no encontrado", flush=True)
            return False

    return True


# ──────────────────────────────────────────────────────────────────────────────
# Leer estado actual del image_local
# ──────────────────────────────────────────────────────────────────────────────

def _get_current_pixels(item: dict, images_dir: Path) -> int:
    fname = item.get("image_local", "")
    if not fname:
        return 0
    path = images_dir / fname
    if not path.exists():
        return 0
    try:
        return _get_pixels_from_bytes(path.read_bytes())
    except Exception:
        return 0


def _get_current_bytes(item: dict, images_dir: Path) -> bytes:
    fname = item.get("image_local", "")
    if not fname:
        return b""
    path = images_dir / fname
    try:
        return path.read_bytes()
    except Exception:
        return b""


# ──────────────────────────────────────────────────────────────────────────────
# Procesamiento por item
# ──────────────────────────────────────────────────────────────────────────────

def _try_candidates(
    item: dict,
    candidates: list[str],
    session: requests.Session,
    images_dir: Path,
    min_gain: float,
    max_hash_dist: int,
    dry_run: bool,
    verbose: bool,
) -> Optional[tuple[str, str]]:
    """
    Prueba cada URL candidata.
    Devuelve (new_image_url, new_image_local) si se encontró mejora, None si no.
    """
    orig_bytes = _get_current_bytes(item, images_dir)
    orig_px = _get_pixels_from_bytes(orig_bytes) if orig_bytes else _get_current_pixels(item, images_dir)

    for url in candidates:
        data = _fetch(url, session)
        if not data:
            continue
        ext = _extension_from_magic(data)
        if not ext:
            continue
        cand_px = _get_pixels_from_bytes(data)
        if cand_px <= 0:
            continue
        if orig_px > 0 and cand_px < orig_px * min_gain:
            if verbose:
                print(f"    skip {url[:60]}: {cand_px}px vs {orig_px}px (no mejora suficiente)")
            continue

        # Verificar que es la misma portada
        if orig_bytes:
            if not _same_cover(orig_bytes, data, max_hash_dist):
                if verbose:
                    print(f"    skip {url[:60]}: hash diff demasiado grande")
                continue

        if verbose:
            print(f"    MEJOR: {url[:60]} → {cand_px}px (vs {orig_px}px)")

        if dry_run:
            return (url, "[dry-run]")

        # Guardar
        filename = _save_image(data, images_dir)
        if not filename:
            continue
        return (url, filename)

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Procesamiento principal
# ──────────────────────────────────────────────────────────────────────────────

def _text_matches_item(page_title: str, item: dict) -> bool:
    """Verifica que el título de la página de la candidata sea relevante al item."""
    if not page_title:
        return True  # sin metadata, no podemos verificar → aceptar
    pt = page_title.lower()
    series = item.get("series_display", "").lower()
    title_orig = item.get("title_original", "").lower()
    # Al menos el nombre de la serie (o parte significativa) debe aparecer en el título de la página
    series_words = [w for w in series.split() if len(w) >= 4]
    if series_words:
        matches = sum(1 for w in series_words if w in pt)
        return matches >= max(1, len(series_words) // 2)
    # Si no tenemos series_display, probar con title_original
    title_words = [w for w in title_orig.split() if len(w) >= 4]
    if title_words:
        matches = sum(1 for w in title_words if w in pt)
        return matches >= max(1, len(title_words) // 2)
    return True


def _process_item(
    item: dict,
    session: requests.Session,
    images_dir: Path,
    min_pixels: int,
    min_gain: float,
    max_hash_dist: int,
    no_search: bool,
    serper_key: str,
    tavily_key: str,
    dry_run: bool,
    verbose: bool,
    preview: bool = False,
) -> Optional[dict]:
    """
    Busca una portada mejor para el item.
    Retorna un dict con los datos del resultado (para preview o aplicación directa).
    None si no encontró mejora.
    """
    signals = item.get("signal_types", [])

    if _SKIP_SIGNALS & set(signals):
        return None

    curr_px = _get_current_pixels(item, images_dir)
    is_upscaled_item = _is_upscaled(item, images_dir)
    # Solo buscamos para imágenes que GENUINAMENTE necesitan mejora: las que
    # están por debajo del umbral de píxeles. Antes había un bypass que hacía
    # buscar reemplazo para CUALQUIER imagen upscaleada por AI aunque ya fuera de
    # 2 MP — y terminaba aplicando portadas web equivocadas/de peor calidad sobre
    # portadas que estaban bien. El tamaño manda; una imagen ya grande no se toca.
    if curr_px >= min_pixels:
        return None

    isbn = item.get("isbn", "")
    title = item.get("title", "")
    publisher = item.get("publisher", "")

    # Candidatas: lista de {url, page_title, domain} o URLs planas
    search_results: list[dict] = []
    plain_candidates: list[str] = []

    # Estrategia 1a: Amazon CDN + PRH CDN
    if isbn:
        for u in _candidates_from_isbn(isbn, session):
            plain_candidates.append(u)

    # Estrategia 1b: OpenLibrary
    if isbn:
        for u in _candidates_from_isbn_openlibrary(isbn, session):
            plain_candidates.append(u)

    # Estrategia 1c: Google Books API (extraLarge ~800×1200, gratis sin key)
    if isbn:
        gb = _candidates_from_isbn_google_books(isbn, session)
        if gb:
            if verbose:
                print(f"  Google Books: {len(gb)} candidata(s)", flush=True)
            plain_candidates.extend(gb)

    # Estrategia 2: reverse image search (Google Lens via Serper /lens)
    # Preferido sobre text search — Google ya hace el matching visual,
    # las candidatas son la MISMA portada en mayor resolución.
    image_url = item.get("image_url", "")
    language = item.get("language", "")
    query = ""
    if not plain_candidates and not no_search and serper_key and image_url:
        if verbose:
            gl = _LANG_TO_GL.get(language, "")
            print(f"  Lens: {image_url[:50]} (gl={gl or 'auto'})", flush=True)
        search_results = _search_serper_lens(image_url, serper_key, session, language)
        if verbose and search_results:
            print(f"  Lens devolvió {len(search_results)} candidatas", flush=True)

    # Estrategia 3 (fallback): text search si Lens no encontró nada
    if not plain_candidates and not search_results and not no_search and (title or publisher):
        query = _build_search_query(item)
        if verbose:
            print(f"  Text fallback: {query}", flush=True)
        if serper_key:
            search_results = _search_serper_for_cover(query, serper_key, session)
        if not search_results and tavily_key:
            for u in _search_tavily_for_cover(query, tavily_key, session):
                search_results.append({"url": u, "page_title": "", "domain": ""})

    # Unir candidatas: CDN primero, luego búsqueda (Lens o texto)
    # Marcamos el origen para saber qué verificación aplicar
    all_candidates: list[dict] = []
    for u in plain_candidates:
        all_candidates.append({"url": u, "page_title": "", "domain": "", "via": "cdn"})
    for sr in search_results:
        sr.setdefault("via", "lens" if not query else "text")
        all_candidates.append(sr)

    if not all_candidates:
        return None

    # Evaluar candidatas
    orig_bytes = _get_current_bytes(item, images_dir)
    orig_px = _get_pixels_from_bytes(orig_bytes) if orig_bytes else curr_px

    for cand in all_candidates:
        url = cand["url"]
        data = _fetch(url, session)
        if not data:
            continue
        ext = _extension_from_magic(data)
        if not ext:
            continue
        cand_px = _get_pixels_from_bytes(data)
        if cand_px <= 0:
            continue
        # Para upscaleados: aceptar candidatas más chicas en px si son imágenes
        # reales (no pastel). Un JPG real de 200k px se ve mejor que un PNG
        # waifu2x de 600k px. Umbral: al menos 50k px (= imagen usable).
        effective_gain = min_gain
        if is_upscaled_item and cand_px >= 50_000:
            effective_gain = 0  # aceptar cualquier imagen real ≥ 50k px
        if orig_px > 0 and effective_gain > 0 and cand_px < orig_px * effective_gain:
            if verbose:
                print(f"    skip {url[:60]}: {cand_px}px vs {orig_px}px (no mejora)", flush=True)
            continue

        via = cand.get("via", "text")
        confidence = "high"

        if via == "lens":
            # Lens: Google ya hizo el matching visual.
            # Verificación en 2 capas:
            #   1. Aspect ratio (descarta banners, cuadrados, etc.)
            #   2. Validación de página (fetchea la URL de la página y verifica
            #      que mencione la serie/publisher — descarta editoriales equivocadas)
            confidence = "low"
            if orig_bytes:
                ow, oh = _get_dims_from_bytes(orig_bytes)
                cw, ch = _get_dims_from_bytes(data)
                if ow > 0 and oh > 0 and cw > 0 and ch > 0:
                    orig_ar = _aspect_ratio(ow, oh)
                    cand_ar = _aspect_ratio(cw, ch)
                    if abs(orig_ar - cand_ar) / orig_ar > 0.30:
                        if verbose:
                            print(f"    skip {url[:60]}: aspect ratio diff ({orig_ar:.2f} vs {cand_ar:.2f})", flush=True)
                        continue
            # Validar contenido de la página del resultado
            page_link = cand.get("link", "")
            if page_link and not _validate_page_content(page_link, item, session, verbose):
                if verbose:
                    print(f"    skip {url[:60]}: página no menciona serie/publisher", flush=True)
                continue
        elif via == "cdn":
            # CDN determinístico (Amazon/PRH/OpenLibrary): hash confiable
            if orig_bytes and orig_px > 0:
                if not _same_cover(orig_bytes, data, max_hash_dist):
                    if verbose:
                        print(f"    skip {url[:60]}: hash diff demasiado grande", flush=True)
                    continue
        else:
            # Text search: hash si imagen grande, aspect ratio si chica
            if orig_bytes and orig_px > 0:
                if orig_px >= 30_000:
                    if not _same_cover(orig_bytes, data, max_hash_dist):
                        if verbose:
                            print(f"    skip {url[:60]}: hash diff demasiado grande", flush=True)
                        continue
                else:
                    confidence = "low"
                    ow, oh = _get_dims_from_bytes(orig_bytes)
                    cw, ch = _get_dims_from_bytes(data)
                    if ow > 0 and oh > 0 and cw > 0 and ch > 0:
                        orig_ar = _aspect_ratio(ow, oh)
                        cand_ar = _aspect_ratio(cw, ch)
                        if abs(orig_ar - cand_ar) / orig_ar > 0.25:
                            if verbose:
                                print(f"    skip {url[:60]}: aspect ratio diff", flush=True)
                            continue

        if verbose:
            tag = "✓" if confidence == "high" else "⚠"
            print(f"    MEJOR [{tag}]: {url[:60]} → {cand_px}px (vs {orig_px}px)")

        # Guardar la imagen (siempre — necesitamos el archivo para display/comparación)
        filename = _save_image(data, images_dir) if not dry_run else "[dry-run]"

        return {
            "new_url": url,
            "new_local": filename or "[failed]",
            "candidate_pixels": cand_px,
            "current_pixels": orig_px,
            "page_title": cand.get("page_title", ""),
            "domain": cand.get("domain", ""),
            "query": query,
            "confidence": confidence,
        }

    return None


_PREVIEW_PATH = _HERE / "data" / "cover_preview.json"


def _apply_improvement(item: dict, new_url: str, new_local: str) -> None:
    """Aplica una mejora directamente sobre el item dict."""
    item["image_url"] = new_url
    if item.get("images"):
        if item["images"]:
            item["images"][0]["url"] = new_url
            item["images"][0]["local"] = new_local
    if new_local != "[dry-run]":
        item["image_local"] = new_local


def _is_upscaled(item: dict, images_dir: Path) -> bool:
    """Detecta si la imagen actual es un PNG upscaleado por waifu2x (look pastel)."""
    local = item.get("image_local", "")
    if not local or not local.endswith(".png"):
        return False
    # Los upscaleados de waifu2x producen PNGs grandes (> 200k px)
    # a partir de fuentes chicas. Si la image_url original es de un CDN
    # que sirve thumbnails, probablemente fue upscaleada.
    px = _get_current_pixels(item, images_dir)
    return px >= 200_000


def run(
    items_path: Path,
    images_dir: Path,
    min_pixels: int = DEFAULT_MIN_PIXELS,
    min_gain: float = DEFAULT_MIN_GAIN,
    max_hash_dist: int = DEFAULT_MAX_HASH_DIST,
    no_search: bool = False,
    include_upscaled: bool = False,
    serper_key: str = "",
    tavily_key: str = "",
    dry_run: bool = False,
    preview: bool = True,   # SEGURO por defecto: nada se aplica sin aprobación
    limit: int = 0,
    verbose: bool = False,
) -> None:
    _load_dotenv()
    if not serper_key:
        serper_key = os.environ.get("SERPER_API_KEY", "")
    if not tavily_key:
        tavily_key = os.environ.get("TAVILY_API_KEY", "")

    items = [json.loads(l) for l in items_path.open(encoding="utf-8")]

    def _is_candidate(i: int) -> bool:
        item = items[i]
        if not _SKIP_SIGNALS.isdisjoint(item.get("signal_types", [])):
            return False
        px = _get_current_pixels(item, images_dir)
        if px <= 0:
            return False
        # Candidato normal: imagen chica
        if px < min_pixels:
            return True
        # Candidato extra: imagen upscaleada (pastel) — buscar reemplazo real
        if include_upscaled and _is_upscaled(item, images_dir):
            return True
        return False

    all_candidates_idx = [i for i in range(len(items)) if _is_candidate(i)]

    total = len(all_candidates_idx)

    # --limit aplica a items que realmente necesitan búsqueda web (sin ISBN),
    # no a los que solo hacen CDN check local. Así no se desperdician créditos.
    if limit > 0:
        candidates_idx: list[int] = []
        search_count = 0
        for idx in all_candidates_idx:
            has_isbn = bool(items[idx].get("isbn"))
            candidates_idx.append(idx)
            if not has_isbn:
                search_count += 1
                if search_count >= limit:
                    break
    else:
        candidates_idx = all_candidates_idx

    with_isbn = sum(1 for i in candidates_idx if items[i].get("isbn"))
    without_isbn = len(candidates_idx) - with_isbn

    mode_label = "PREVIEW" if preview else ("dry-run" if dry_run else "escritura")
    print(f"Candidatos: {len(candidates_idx)}/{total} (con ISBN: {with_isbn}, sin: {without_isbn})", flush=True)
    print(f"Modo: {mode_label}, min_gain={min_gain}×, max_hash_dist={max_hash_dist}", flush=True)
    if no_search:
        print("  --no-search activo: solo CDN lookup por ISBN + OpenLibrary", flush=True)
    else:
        search_info = []
        if serper_key:
            search_info.append(f"Serper (key …{serper_key[-6:]})")
        if tavily_key:
            search_info.append(f"Tavily (key …{tavily_key[-6:]})")
        if search_info:
            print(f"  Búsqueda web: {' → '.join(search_info)} (en orden de prioridad)", flush=True)
        else:
            print("  ⚠️  Sin API de búsqueda — solo CDN ISBN + OpenLibrary", flush=True)
    print(flush=True)

    if not dry_run and not preview:
        backup_and_rotate(items_path, "fetch-better-covers")

    session = requests.Session()
    session.headers.update({"User-Agent": _UA})

    applied_high = 0  # alta confianza + --apply → aplicadas directo
    previewed = 0     # van a preview SIN aplicar (esperan aprobación manual)
    skipped = 0
    errors = 0
    flush_count = 0
    preview_entries: list[dict] = []

    for pos, idx in enumerate(candidates_idx):
        item = items[idx]
        title = item.get("title", "")[:50]
        if verbose:
            print(f"[{pos+1}/{len(candidates_idx)}] {title}", flush=True)
        elif pos % 50 == 0:
            total_applied = applied_high + applied_low
            print(f"  {pos}/{len(candidates_idx)} procesados... ({total_applied} mejorados)", flush=True)

        try:
            result = _process_item(
                item, session, images_dir,
                min_pixels, min_gain, max_hash_dist,
                no_search, serper_key, tavily_key,
                dry_run=dry_run, verbose=verbose,
            )
            if result:
                new_url = result["new_url"]
                new_local = result["new_local"]
                confidence = result.get("confidence", "high")

                # Regla de seguridad (2026-06-03): NUNCA reemplazar la portada
                # automáticamente sin aprobación. El item conserva su portada
                # vieja hasta que el owner apruebe en cover-preview.html. Única
                # excepción: alta confianza (CDN/ISBN, hash-verificada = misma
                # imagen en mayor resolución) EN modo --apply explícito. La baja
                # confianza NUNCA se auto-aplica — era la fuente de las portadas
                # equivocadas (un kit de magia para "Negima", etc.).
                old_local = item.get("image_local", "")
                old_url = item.get("image_url", "")
                if confidence == "high" and not preview and not dry_run:
                    applied_high += 1
                    _apply_improvement(item, new_url, new_local)
                    _atomic_write(items_path, items)
                    flush_count += 1
                    if verbose:
                        print(f"  ✓ aplicada [alta confianza, --apply] ({flush_count})", flush=True)
                else:
                    # A preview, SIN tocar items.jsonl (la portada vieja se queda).
                    previewed += 1
                    preview_entries.append({
                        "slug": item.get("slug", ""),
                        "title": item.get("title", ""),
                        "title_original": item.get("title_original", ""),
                        "series_display": item.get("series_display", ""),
                        "publisher": item.get("publisher", ""),
                        "country": item.get("country", ""),
                        "old_image": old_local,
                        "old_url": old_url,
                        "old_pixels": result["current_pixels"],
                        "new_image": new_local,
                        "new_url": new_url,
                        "new_pixels": result["candidate_pixels"],
                        "page_title": result.get("page_title", ""),
                        "domain": result.get("domain", ""),
                        "query": result.get("query", ""),
                        "confidence": confidence,
                        "status": "pending",
                    })
                    if not dry_run:
                        _PREVIEW_PATH.write_text(
                            json.dumps(preview_entries, ensure_ascii=False, indent=2),
                            encoding="utf-8")
                    if verbose:
                        tag = "alta" if confidence == "high" else "baja"
                        print(f"  → preview [{tag} confianza, NO aplicada] ({len(preview_entries)})", flush=True)
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            if verbose:
                print(f"  ERROR: {e}", flush=True)

    print(flush=True)
    print(f"✓ Resultado:")
    print(f"  Aplicadas (alta confianza, --apply): {applied_high}")
    print(f"  En preview (esperan tu aprobación):  {previewed}")
    print(f"  Sin mejora:                          {skipped}")
    print(f"  Errores:                             {errors}")
    if not dry_run:
        print(f"  Guardados:  {flush_count} flushes a items.jsonl")
    if previewed > 0:
        print(f"\n  ⚠  {previewed} candidatas NO aplicadas — revisalas y aprobá:")
        print(f"  Preview:    {_PREVIEW_PATH}")
        print(f"  Abrir:      http://localhost:8000/web/cover-preview.html")
        print(f"  Después:    .venv/bin/python scripts/retrofit/fetch_better_covers.py --apply-preview")


def apply_preview(items_path: Path, images_dir: Path) -> None:
    """
    Procesa el preview JSON con 3 estados por item:
    - APPROVED: ya está aplicada la nueva. Borra la imagen vieja (cleanup).
    - REJECTED: revierte a la imagen vieja. Borra la imagen nueva.
    - PENDING:  no se toca. Queda en el preview para decidir después.
    """
    if not _PREVIEW_PATH.exists():
        print(f"No hay preview en {_PREVIEW_PATH}.")
        return

    preview = json.loads(_PREVIEW_PATH.read_text(encoding="utf-8"))
    approved = [e for e in preview if e.get("status") == "approved"]
    rejected = [e for e in preview if e.get("status") == "rejected"]
    pending  = [e for e in preview if e.get("status", "pending") == "pending"]

    print(f"Preview: {len(preview)} items — {len(approved)} aprobados, "
          f"{len(rejected)} rechazados, {len(pending)} pendientes", flush=True)

    if not approved and not rejected:
        print("Nada que procesar (todo pendiente).")
        return

    items = [json.loads(l) for l in items_path.open(encoding="utf-8")]
    backup_and_rotate(items_path, "fetch-better-covers")

    items_by_slug: dict[str, list[dict]] = {}
    for item in items:
        s = item.get("slug", "")
        if s:
            items_by_slug.setdefault(s, []).append(item)

    reverted = 0
    cleaned_old = 0
    cleaned_new = 0

    for entry in rejected:
        slug = entry.get("slug", "")
        for item in items_by_slug.get(slug, []):
            _apply_improvement(item, entry["old_url"], entry["old_image"])
            reverted += 1
        new_file = images_dir / entry.get("new_image", "")
        old_file = entry.get("old_image", "")
        if new_file.name and new_file.name != old_file and new_file.exists():
            new_file.unlink()
            cleaned_new += 1

    for entry in approved:
        old_file = images_dir / entry.get("old_image", "")
        new_file = entry.get("new_image", "")
        if old_file.name and old_file.name != new_file and old_file.exists():
            old_file.unlink()
            cleaned_old += 1

    _atomic_write(items_path, items)

    print(f"✓ Resultado:")
    print(f"  Aprobados:              {len(approved)} (imagen vieja eliminada: {cleaned_old})")
    print(f"  Rechazados (revertidos): {reverted} (imagen nueva eliminada: {cleaned_new})")

    if pending:
        # Guardar solo los pendientes para futura revisión
        _PREVIEW_PATH.write_text(
            json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Pendientes:             {len(pending)} (siguen en preview para después)")
    else:
        _PREVIEW_PATH.unlink()
        print(f"  Preview limpiado (todo procesado).")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Busca portadas en mayor resolución para items con imagen chica."
    )
    ap.add_argument(
        "--items", default=str(_ITEMS_PATH),
        help="Ruta a items.jsonl (default: data/items.jsonl)",
    )
    ap.add_argument(
        "--images-dir", default=str(_IMAGES_DIR),
        help="Directorio de imágenes locales (default: data/images/)",
    )
    ap.add_argument(
        "--min-pixels", type=int, default=DEFAULT_MIN_PIXELS,
        help=f"Umbral de calidad baja (default: {DEFAULT_MIN_PIXELS})",
    )
    ap.add_argument(
        "--min-gain", type=float, default=DEFAULT_MIN_GAIN,
        help=f"Ganancia mínima de píxeles para aceptar candidata (default: {DEFAULT_MIN_GAIN}×)",
    )
    ap.add_argument(
        "--max-hash-dist", type=int, default=DEFAULT_MAX_HASH_DIST,
        help=f"Distancia Hamming máxima para aceptar candidata como 'misma portada' "
             f"(default: {DEFAULT_MAX_HASH_DIST}/64)",
    )
    ap.add_argument(
        "--include-upscaled", action="store_true",
        help="Incluir imágenes PNG upscaleadas por waifu2x como candidatas. "
             "Busca reemplazos reales hi-res para portadas con look pastel.",
    )
    ap.add_argument(
        "--no-search", action="store_true",
        help="Solo CDN lookup por ISBN + OpenLibrary, sin búsqueda web",
    )
    ap.add_argument(
        "--serper-key", default="",
        help="Serper API key (si no se pasa, se lee SERPER_API_KEY del .env). "
             "Google Images API — 2 500 queries gratis sin tarjeta en serper.dev",
    )
    ap.add_argument(
        "--tavily-key", default="",
        help="Tavily API key (si no se pasa, se lee TAVILY_API_KEY del .env). "
             "Fallback si no hay Serper key. 1 000 queries/mes gratis.",
    )
    ap.add_argument(
        "--apply", action="store_true",
        help="Aplicar DIRECTO solo las candidatas de ALTA confianza (CDN/ISBN, "
             "hash-verificadas = misma portada en mayor resolución). Por defecto "
             "(sin este flag) NADA se aplica: TODO va a preview para tu aprobación "
             "manual en http://localhost:8000/web/cover-preview.html. La baja "
             "confianza NUNCA se auto-aplica.",
    )
    ap.add_argument(
        "--apply-preview", action="store_true",
        help="Aplicar las mejoras aprobadas del preview a items.jsonl",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="No modificar archivos, solo mostrar qué se haría",
    )
    ap.add_argument(
        "--limit", type=int, default=0,
        help="Procesar solo los primeros N candidatos (0 = todos)",
    )
    ap.add_argument(
        "--verbose", "-v", action="store_true",
        help="Mostrar detalle de cada item procesado",
    )
    args = ap.parse_args()

    if args.apply_preview:
        apply_preview(Path(args.items), Path(args.images_dir))
        return

    run(
        items_path=Path(args.items),
        images_dir=Path(args.images_dir),
        min_pixels=args.min_pixels,
        min_gain=args.min_gain,
        max_hash_dist=args.max_hash_dist,
        no_search=args.no_search,
        include_upscaled=args.include_upscaled,
        preview=not args.apply,
        serper_key=args.serper_key,
        tavily_key=args.tavily_key,
        dry_run=args.dry_run,
        limit=args.limit,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
