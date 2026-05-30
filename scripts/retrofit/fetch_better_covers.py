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

    # Perceptual hash
    h1 = _ahash(original_bytes)
    h2 = _ahash(candidate_bytes)
    if h1 is not None and h2 is not None:
        dist = _hamming(h1, h2)
        return dist <= max_hash_dist

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

    # Base: nombre de la serie (sin sufijos de edición)
    if series:
        parts.append(series)
    elif title_orig and title_orig != title:
        parts.append(title_orig)
    elif title:
        parts.append(title)

    # Tipo de edición en el idioma correcto
    if edition_hint:
        parts.append(edition_hint)

    # Volumen
    if volume:
        parts.append(str(volume))

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
) -> list[str]:
    """
    Usa Serper (Google Images API) para buscar portadas hi-res.
    Recibe el query ya construido por _build_search_query().
    Ventaja vs Tavily: devuelve dimensiones en el JSON — pre-filtra thumbnails.
    2 500 queries gratis sin tarjeta de crédito. API key en serper.dev.
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

    result: list[str] = []
    for img in data.get("images", []):
        url = img.get("imageUrl", "")
        if not url or not _is_plausible_cover(url):
            continue
        # Serper incluye dimensiones — pre-filtra thumbnails antes de descargar
        w = img.get("imageWidth", 0)
        h = img.get("imageHeight", 0)
        if w > 0 and h > 0 and w * h < 50_000:
            continue
        result.append(url)
        if len(result) >= 5:
            break

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Tavily search
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
) -> Optional[tuple[str, str]]:
    """
    Retorna (new_image_url, new_image_local) si se mejoró el item, None si no.
    Orden de estrategias:
      1. ISBN → Amazon CDN + PRH CDN + OpenLibrary (gratis, sin cuota)
      2. Sin ISBN → Serper (2 500 gratis) → Tavily (1 000/mes)
    """
    signals = item.get("signal_types", [])

    # Saltar variantes/exclusivos
    if _SKIP_SIGNALS & set(signals):
        return None

    # Verificar que la imagen actual es pequeña
    curr_px = _get_current_pixels(item, images_dir)
    if curr_px >= min_pixels:
        return None  # ya tiene buena calidad

    isbn = item.get("isbn", "")
    title = item.get("title", "")
    publisher = item.get("publisher", "")

    candidates: list[str] = []

    # Estrategia 1a: Amazon CDN + PRH CDN (rápido, sin cuota)
    if isbn:
        candidates.extend(_candidates_from_isbn(isbn, session))

    # Estrategia 1b: OpenLibrary — siempre que haya ISBN, se añade al final de la lista
    # (así se prueba aunque Amazon/PRH fallen por píxeles)
    if isbn:
        ol = _candidates_from_isbn_openlibrary(isbn, session)
        if ol:
            if verbose:
                print(f"  OpenLibrary: {len(ol)} candidata(s) disponible(s)")
            candidates.extend(ol)

    # Estrategia 2: búsqueda web para ítems sin ISBN (o ISBN sin mejora en CDN)
    if not candidates and not no_search and (title or publisher):
        query = _build_search_query(item)
        if verbose:
            print(f"  Query: {query}", flush=True)
        # Orden: Serper (2500 gratis) → Tavily (1000/mes)
        if serper_key:
            candidates.extend(_search_serper_for_cover(query, serper_key, session))
        if not candidates and tavily_key:
            candidates.extend(_search_tavily_for_cover(query, tavily_key, session))

    if not candidates:
        return None

    return _try_candidates(
        item, candidates, session, images_dir,
        min_gain, max_hash_dist, dry_run, verbose,
    )


def run(
    items_path: Path,
    images_dir: Path,
    min_pixels: int = DEFAULT_MIN_PIXELS,
    min_gain: float = DEFAULT_MIN_GAIN,
    max_hash_dist: int = DEFAULT_MAX_HASH_DIST,
    no_search: bool = False,
    serper_key: str = "",
    tavily_key: str = "",
    dry_run: bool = False,
    limit: int = 0,
    verbose: bool = False,
) -> None:
    # Auto-cargar keys desde .env si no se pasaron explícitamente
    _load_dotenv()
    if not serper_key:
        serper_key = os.environ.get("SERPER_API_KEY", "")
    if not tavily_key:
        tavily_key = os.environ.get("TAVILY_API_KEY", "")

    items = [json.loads(l) for l in items_path.open(encoding="utf-8")]

    # Candidatos: imagen chica, sin signals que excluyen
    candidates_idx = [
        i for i, item in enumerate(items)
        if _SKIP_SIGNALS.isdisjoint(item.get("signal_types", []))
        and _get_current_pixels(item, images_dir) < min_pixels
        and _get_current_pixels(item, images_dir) > 0  # tiene imagen
    ]

    total = len(candidates_idx)
    if limit > 0:
        candidates_idx = candidates_idx[:limit]

    with_isbn = sum(1 for i in candidates_idx if items[i].get("isbn"))
    without_isbn = len(candidates_idx) - with_isbn

    print(f"Candidatos: {len(candidates_idx)}/{total} (con ISBN: {with_isbn}, sin: {without_isbn})", flush=True)
    print(f"Modo: {'dry-run' if dry_run else 'escritura'}, min_gain={min_gain}×, max_hash_dist={max_hash_dist}", flush=True)
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

    if not dry_run:
        backup_and_rotate(items_path, "fetch-better-covers")

    session = requests.Session()
    session.headers.update({"User-Agent": _UA})

    improved = 0
    skipped = 0
    errors = 0
    flush_count = 0  # cuántas mejoras se han guardado a disco

    def _apply_improvement(idx: int, new_url: str, new_local: str) -> None:
        """Aplica una mejora directamente sobre la lista items[] en memoria."""
        item = items[idx]
        item["image_url"] = new_url
        if item.get("images"):
            for img_entry in item["images"]:
                if img_entry.get("kind") == "cover":
                    img_entry["url"] = new_url
                    img_entry["local"] = new_local
                    break
        if new_local != "[dry-run]":
            item["image_local"] = new_local

    for pos, idx in enumerate(candidates_idx):
        item = items[idx]
        title = item.get("title", "")[:50]
        if verbose:
            print(f"[{pos+1}/{len(candidates_idx)}] {title}", flush=True)
        elif pos % 50 == 0:
            print(f"  {pos}/{len(candidates_idx)} procesados... ({improved} mejorados)", flush=True)

        try:
            result = _process_item(
                item, session, images_dir,
                min_pixels, min_gain, max_hash_dist,
                no_search, serper_key, tavily_key, dry_run, verbose,
            )
            if result:
                improved += 1
                new_url, new_local = result
                if not dry_run:
                    _apply_improvement(idx, new_url, new_local)
                    _atomic_write(items_path, items)  # flush inmediato
                    flush_count += 1
                if verbose:
                    print(f"  ✓ mejorado → guardado ({flush_count} total)", flush=True)
            else:
                skipped += 1
        except Exception as e:
            errors += 1
            if verbose:
                print(f"  ERROR: {e}", flush=True)

    print()
    print(f"✓ Resultado:")
    print(f"  Mejoradas:  {improved}")
    print(f"  Sin mejora: {skipped}")
    print(f"  Errores:    {errors}")
    if not dry_run:
        print(f"  Guardados:  {flush_count} flushes a items.jsonl")


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

    run(
        items_path=Path(args.items),
        images_dir=Path(args.images_dir),
        min_pixels=args.min_pixels,
        min_gain=args.min_gain,
        max_hash_dist=args.max_hash_dist,
        no_search=args.no_search,
        serper_key=args.serper_key,
        tavily_key=args.tavily_key,
        dry_run=args.dry_run,
        limit=args.limit,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
