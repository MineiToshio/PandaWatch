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
3. Verificación de identidad ENDURECIDA (2026-06-10, precisión > recall):
   una candidata se acepta como "misma portada" SOLO si pasa TODAS estas capas:
     R6 — dimensiones computables (bytes → fallback PIL; GIF animado de
          referencia = rechazo) + aspect ratio ±25% (sin bypass).
     R3 — gate de entropía: stddev de grises a 32×32 >= 20 en AMBAS imágenes
          (portadas sólidas/casi-blancas no son verificables → rechazo).
     R1 — AND de 3 familias de hash: aHash 8×8 Hamming <= --max-hash-dist
          (default 6/64), dHash 8×8 <= 8/64, pHash (DCT 32×32 → 8×8 low-freq)
          <= 8/64. Un solo hash NO alcanza: distintos volúmenes de la misma
          serie colisionan en aHash con dist 0 (Berserk Deluxe 1 vs 10).
     R2 — confirmación estructural: normalized cross-correlation en grises
          64×64 >= 0.90.
     R7 — denylist exacta de placeholders conocidos (_PLACEHOLDER_HASHES).
   Cualquier capa incomputable → rechazo (default-deny). Adicionalmente, la
   candidata debe tener >= --min-gain × más píxeles que la existente, y no debe
   declarar metadata en conflicto (volumen/ISBN distinto) en su URL/título
   (candidate_metadata_conflict).

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
import math
import os
import re
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
# El wrapper manga_watch.py de la RAÍZ puede estar ya cacheado en sys.modules
# (no expone estos símbolos) → fallback al módulo real, como sync_cover_images.
try:
    from manga_watch import IMAGE_URL_BAD_PATTERNS, backup_and_rotate  # noqa: E402
except ImportError:
    from scripts.manga_watch import IMAGE_URL_BAD_PATTERNS, backup_and_rotate  # noqa: E402
import image_store  # noqa: E402
_ITEMS_PATH = _HERE / "data" / "items.jsonl"
_IMAGES_DIR = _HERE / "data" / "images"

# ── Parámetros de calidad ─────────────────────────────────────────────────────
DEFAULT_MIN_PIXELS = 100_000   # imágenes por debajo de este umbral son candidatas
DEFAULT_MIN_GAIN = 1.5         # candidata debe tener >= 1.5× los píxeles actuales
DEFAULT_MAX_HASH_DIST = 6      # aHash: distancia Hamming máxima (de 64 bits) para aceptar
DHASH_MAX_DIST = 8             # dHash 8×8: cota fija (no configurable por CLI)
PHASH_MAX_DIST = 8             # pHash DCT: cota fija (no configurable por CLI)
NCC_MIN = 0.90                 # correlación cruzada normalizada mínima (64×64 grises)
ENTROPY_MIN_STDDEV = 20.0      # stddev de grises 32×32 mínima para que sea verificable
# Gate de calidad de DISPLAY (gotcha #94): una candidata con MÁS píxeles que la
# actual puede verse PEOR (pixelada/blanda) — el px count sobreestima su calidad.
# El defecto se da SOLO con la combinación CHICA + BLANDA:
#   - "blanda" = poco detalle real para su tamaño (escaneo sobre-comprimido o
#     upscale). Se mide con _detail_ratio: residual del roundtrip downscale½→
#     upscale a un tamaño común (lado largo 384px), normalizado por la stddev de
#     grises → fracción de energía en la octava superior.
#   - "chica" = por debajo de SOFT_GUARD_PX. Una imagen chica se MUESTRA AGRANDADA
#     (modal/tarjeta la upscalean) y ahí su falta de detalle se nota. Una imagen
#     GRANDE pero blanda NO es problema: se muestra REDUCIDA y se ve nítida — por
#     eso el ratio solo se aplica por debajo del guard (si no, falsos positivos
#     en escaneos grandes legítimos: whakoom 637k y planeta 6M miden ~0.10 igual
#     que la casadellibro 80k, pero se ven bien reducidos).
# Calibrado 2026-06-13 con casos reales: casadellibro 78-90k (blandas) ratio
# 0.05-0.10 → rechazadas; whakoom/norma/buscalibre buenas ≥150k px o ratio ≥0.12
# → pasan.
DETAIL_EVAL_LONGSIDE = 384     # lado largo (px) al que se normaliza para medir detalle
DETAIL_RATIO_MIN = 0.115       # por debajo = blanda (solo importa si además es chica)
SOFT_GUARD_PX = 150_000        # ≥ esto se muestra reducida → el ratio bajo no molesta
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
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            # Mismo parsing VP8 que _get_pixels_from_bytes — sin esta rama las
            # candidatas WebP devolvían (0,0) y se saltaban el check de aspect
            # ratio de _same_cover.
            vp8 = data[data.index(b"VP8 ") + 8 :]  # type: ignore[arg-type]
            w = (struct.unpack("<H", vp8[6:8])[0] & 0x3FFF) + 1
            h = (struct.unpack("<H", vp8[8:10])[0] & 0x3FFF) + 1
            return w, h
    except Exception:
        pass
    # Fallback PIL para formatos que el parser de bytes no cubre (GIF, AVIF,
    # WebP lossless/VP8L, PNGs raros). Sin esto, GIF/AVIF devolvían (0,0) y
    # se SALTABAN el gate de aspect ratio de _same_cover (R6).
    if _HAS_PIL:
        try:
            from PIL import Image  # noqa: PLC0415

            with Image.open(io.BytesIO(data)) as im:
                return im.width, im.height
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


try:
    import PIL  # noqa: F401
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


def _ahash(data: bytes, hash_size: int = 8) -> Optional[int]:
    """Average hash — perceptual hash simple (hash_size^2 bits)."""
    try:
        from PIL import Image  # noqa: PLC0415

        img = Image.open(io.BytesIO(data)).convert("L").resize(
            (hash_size, hash_size), Image.LANCZOS
        )
        pixels = list(img.tobytes())
        avg = sum(pixels) / len(pixels)
        return sum(1 << i for i, px in enumerate(pixels) if px >= avg)
    except Exception:
        return None


def _hamming(h1: int, h2: int) -> int:
    return bin(h1 ^ h2).count("1")


def _gray_pixels(data: bytes, size: int) -> Optional[list]:
    """Imagen → lista de píxeles en escala de grises a size×size (LANCZOS)."""
    try:
        from PIL import Image  # noqa: PLC0415

        img = Image.open(io.BytesIO(data)).convert("L").resize(
            (size, size), Image.LANCZOS
        )
        # tobytes() en modo "L" = secuencia plana de píxeles (getdata está
        # deprecado y se elimina en Pillow 14).
        return list(img.tobytes())
    except Exception:
        return None


def _dhash(data: bytes, hash_size: int = 8) -> Optional[int]:
    """Difference hash — gradientes horizontales (hash_size^2 bits)."""
    try:
        from PIL import Image  # noqa: PLC0415

        img = Image.open(io.BytesIO(data)).convert("L").resize(
            (hash_size + 1, hash_size), Image.LANCZOS
        )
        px = list(img.tobytes())
        bits = 0
        bit = 0
        for row in range(hash_size):
            base = row * (hash_size + 1)
            for col in range(hash_size):
                if px[base + col] > px[base + col + 1]:
                    bits |= 1 << bit
                bit += 1
        return bits
    except Exception:
        return None


# Tablas de cosenos precomputadas para el DCT del pHash (32×32 → 8×8 low-freq).
_DCT_SIZE = 32
_DCT_KEEP = 8
_DCT_COS = [
    [math.cos((2 * x + 1) * u * math.pi / (2 * _DCT_SIZE)) for x in range(_DCT_SIZE)]
    for u in range(_DCT_KEEP)
]


def _phash(data: bytes) -> Optional[int]:
    """Perceptual hash por DCT: 32×32 grises → 8×8 coeficientes de baja
    frecuencia → 64 bits (bit = coef > mediana de los AC). DCT separable en
    Python puro — son solo 64 coeficientes, no necesita numpy."""
    px = _gray_pixels(data, _DCT_SIZE)
    if px is None:
        return None
    try:
        # tmp[u][y] = Σ_x cos[u][x] · px[y][x]   (transformada sobre filas)
        tmp = [[0.0] * _DCT_SIZE for _ in range(_DCT_KEEP)]
        for u in range(_DCT_KEEP):
            cu = _DCT_COS[u]
            for y in range(_DCT_SIZE):
                row_off = y * _DCT_SIZE
                tmp[u][y] = sum(cu[x] * px[row_off + x] for x in range(_DCT_SIZE))
        # F[u][v] = Σ_y cos[v][y] · tmp[u][y]    (transformada sobre columnas)
        coeffs: list[float] = []
        for u in range(_DCT_KEEP):
            tu = tmp[u]
            for v in range(_DCT_KEEP):
                cv = _DCT_COS[v]
                coeffs.append(sum(cv[y] * tu[y] for y in range(_DCT_SIZE)))
        ac = sorted(coeffs[1:])  # excluir DC para la mediana
        median = ac[len(ac) // 2]
        bits = 0
        for i, c in enumerate(coeffs):
            if c > median:
                bits |= 1 << i
        return bits
    except Exception:
        return None


def _gray_stddev(data: bytes, size: int = 32) -> Optional[float]:
    """Desviación estándar de la imagen en grises a size×size."""
    px = _gray_pixels(data, size)
    if not px:
        return None
    n = len(px)
    mean = sum(px) / n
    return (sum((p - mean) ** 2 for p in px) / n) ** 0.5


def _ncc(data1: bytes, data2: bytes, size: int = 64) -> Optional[float]:
    """Normalized cross-correlation en grises size×size. None si incomputable
    (imagen ilegible o varianza cero)."""
    a = _gray_pixels(data1, size)
    b = _gray_pixels(data2, size)
    if a is None or b is None:
        return None
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    if da == 0 or db == 0:
        return None
    return num / (da * db)


def _detail_ratio(data: bytes, longside: int = DETAIL_EVAL_LONGSIDE) -> Optional[float]:
    """Detalle efectivo de la imagen: fracción de energía que vive en la octava
    superior, medida a un tamaño de display común (lado largo = ``longside``).

    Mide cuánto detalle real pierde la imagen al bajar a media resolución y
    volver a subir: una portada nítida en alta resolución conserva mucho
    (residual alto); un escaneo blando / upscale casi no tiene detalle en esa
    octava (residual bajo). Se normaliza por la stddev de grises para que sea
    invariante al contraste/contenido. ``None`` si es incomputable (sin PIL o
    imagen ilegible). Ver gotcha #94 y DETAIL_RATIO_MIN."""
    if not _HAS_PIL or not data:
        return None
    try:
        from PIL import Image  # noqa: PLC0415

        img = Image.open(io.BytesIO(data)).convert("L")
        w, h = img.size
        if w <= 0 or h <= 0:
            return None
        # Normalizar al tamaño de display común (LANCZOS sube o baja). Bajar una
        # imagen grande y nítida concentra su detalle; subir una chica y blanda
        # no inventa detalle → ambos extremos quedan bien separados.
        scale = longside / max(w, h)
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        img = img.resize((nw, nh), Image.LANCZOS)
        gp = list(img.tobytes())
        n = len(gp)
        mean = sum(gp) / n
        var = sum((p - mean) ** 2 for p in gp) / n
        if var <= 0:
            return None
        small = img.resize((max(1, nw // 2), max(1, nh // 2)), Image.LANCZOS)
        back = small.resize((nw, nh), Image.LANCZOS)
        bp = list(back.tobytes())
        resid = sum(abs(a - b) for a, b in zip(gp, bp)) / n
        return resid / math.sqrt(var)
    except Exception:
        return None


def _is_soft_image(
    data: bytes,
    min_ratio: float = DETAIL_RATIO_MIN,
    guard_px: int = SOFT_GUARD_PX,
) -> bool:
    """True si la candidata se verá BLANDA/pixelada al mostrarla: es CHICA (se
    mostrará agrandada, así que su falta de detalle salta a la vista) Y tiene
    poco detalle real para su tamaño. Una candidata así NO es upgrade aunque
    tenga más píxeles que la actual (gotcha #94).

    Una imagen GRANDE (≥ ``guard_px``) con detalle bajo NO cuenta como blanda:
    se muestra reducida → nítida. Aplicar el ratio a cualquier tamaño daba
    falsos positivos en escaneos grandes legítimos (whakoom 637k, planeta 6M
    miden ~0.10 igual que la casadellibro 80k pero se ven bien reducidos).

    Incomputable (sin PIL / ilegible) → ``False``: no se trata como blanda; la
    identidad ya la gobierna ``_same_cover`` (que también requiere PIL), así que
    este gate no agrega un default-deny redundante."""
    px = _get_pixels_from_bytes(data)
    if px <= 0 or px >= guard_px:
        return False
    r = _detail_ratio(data)
    if r is None:
        return False
    return r < min_ratio


def _is_animated_gif(data: bytes) -> bool:
    """True si los bytes son un GIF con más de un frame."""
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        return False
    try:
        from PIL import Image  # noqa: PLC0415

        with Image.open(io.BytesIO(data)) as im:
            return bool(getattr(im, "is_animated", False)) or getattr(im, "n_frames", 1) > 1
    except Exception:
        return True  # GIF ilegible → tratarlo como no verificable


# R7 — denylist exacta de placeholders conocidos. Se puebla en runtime cuando
# una URL candidata matchea IMAGE_URL_BAD_PATTERNS (register_placeholder_image)
# y puede sembrarse con hashes conocidos. Cualquier imagen cuyo aHash esté acá
# se rechaza siempre.
_PLACEHOLDER_HASHES: set = set()


def register_placeholder_image(data: bytes) -> None:
    """Registra el aHash exacto de un placeholder conocido en la denylist."""
    h = _ahash(data)
    if h is not None:
        _PLACEHOLDER_HASHES.add(h)


def _maybe_register_placeholder(url: str, data: bytes) -> bool:
    """Si la URL matchea IMAGE_URL_BAD_PATTERNS, registra su aHash en la
    denylist de placeholders y devuelve True (es placeholder, descartar)."""
    low = (url or "").lower()
    if any(p in low for p in IMAGE_URL_BAD_PATTERNS):
        register_placeholder_image(data)
        return True
    return False


def _aspect_ratio(w: int, h: int) -> float:
    return w / h if h else 1.0


def _same_cover(
    original_bytes: bytes,
    candidate_bytes: bytes,
    max_hash_dist: int = DEFAULT_MAX_HASH_DIST,
) -> bool:
    """
    True si la candidata es la MISMA portada que la original (misma imagen,
    idealmente en mejor resolución). Regla del flujo: precisión > recall —
    cualquier capa incomputable rechaza (default-deny, owner 2026-06-10).

    Capas (TODAS deben pasar):
      R6  dimensiones computables en ambas (bytes → fallback PIL) y la
          referencia NO es un GIF animado; aspect ratio dentro de ±25%.
      R3  entropía: stddev de grises a 32×32 >= ENTROPY_MIN_STDDEV en ambas
          (sólidos blanco/negro y placeholders lisos NO son verificables).
      R7  ninguno de los aHash está en la denylist _PLACEHOLDER_HASHES.
      R1  AND de hashes: aHash <= max_hash_dist (default 6/64) y
          dHash <= DHASH_MAX_DIST (8/64) y pHash <= PHASH_MAX_DIST (8/64).
          aHash solo NO alcanza: volúmenes distintos de la misma serie
          (trade dress) colisionan con dist 0 (Berserk Deluxe 1 vs 10).
      R2  estructura: NCC en grises 64×64 >= NCC_MIN (0.90).

    El relax de +4 bits para originales < 30k px se ELIMINÓ (R4): era la vía
    de entrada de los falsos positivos (efectivo 16/64).
    """
    if not original_bytes or not candidate_bytes:
        return False
    if not _HAS_PIL:
        # Sin PIL no hay verificación de identidad posible → default-deny.
        return False

    # R6 — GIF animado como referencia no sirve (frames ≠ portada); candidata
    # animada tampoco es una portada (sticker sheets, banners animados).
    if _is_animated_gif(original_bytes) or _is_animated_gif(candidate_bytes):
        return False

    # R6 — dims SIEMPRE necesarias; si no se pueden parsear (ni por bytes ni
    # por PIL) se rechaza — nunca se saltea el gate de aspect ratio.
    ow, oh = _get_dims_from_bytes(original_bytes)
    cw, ch = _get_dims_from_bytes(candidate_bytes)
    if ow <= 0 or oh <= 0 or cw <= 0 or ch <= 0:
        return False
    orig_ar = _aspect_ratio(ow, oh)
    cand_ar = _aspect_ratio(cw, ch)
    if abs(orig_ar - cand_ar) / orig_ar > 0.25:
        return False

    # R3 — gate de entropía: una imagen casi-lisa no es verificable por hash
    # (blanco sólido vs negro sólido = aHash dist 0). Cubre placeholder vs
    # placeholder y portadas minimalistas sin estructura.
    s1 = _gray_stddev(original_bytes)
    s2 = _gray_stddev(candidate_bytes)
    if s1 is None or s2 is None or s1 < ENTROPY_MIN_STDDEV or s2 < ENTROPY_MIN_STDDEV:
        return False

    # R1 — AND de las 3 familias de hash.
    h1 = _ahash(original_bytes)
    h2 = _ahash(candidate_bytes)
    if h1 is None or h2 is None:
        return False
    # R7 — denylist exacta de placeholders conocidos.
    if h1 in _PLACEHOLDER_HASHES or h2 in _PLACEHOLDER_HASHES:
        return False
    if _hamming(h1, h2) > max_hash_dist:
        return False
    d1 = _dhash(original_bytes)
    d2 = _dhash(candidate_bytes)
    if d1 is None or d2 is None or _hamming(d1, d2) > DHASH_MAX_DIST:
        return False
    p1 = _phash(original_bytes)
    p2 = _phash(candidate_bytes)
    if p1 is None or p2 is None or _hamming(p1, p2) > PHASH_MAX_DIST:
        return False

    # R2 — confirmación estructural (correlación píxel a píxel normalizada).
    corr = _ncc(original_bytes, candidate_bytes)
    if corr is None or corr < NCC_MIN:
        return False

    return True


# ──────────────────────────────────────────────────────────────────────────────
# R5 — conflicto de metadata candidata vs item (volumen / ISBN declarados)
# ──────────────────────────────────────────────────────────────────────────────

# Marcadores explícitos de volumen en URL/título: vol/volume/volumen, tome/tomo,
# nº/n°/no./nr/num, #N. Capturan 1-3 dígitos.
_VOL_EXPLICIT_RE = re.compile(
    r"(?:\b(?:vol(?:ume|umen)?|tome|tomo|n[°º]|n[or]\.|nr|num(?:ero)?|#)\s*\.?\s*[-_ ]?\s*0*(\d{1,3}))(?!\d)",
    re.IGNORECASE,
)
# Patrones "bare" SOLO en el filename: -1-, _01_, -02. (1-2 dígitos delimitados).
# Se usan únicamente si NO hay marcador explícito (son más ambiguos).
_VOL_BARE_RE = re.compile(r"[-_]0*(\d{1,2})(?=[-_.])")
# Dimensiones tipo 600x800 — los números que las componen NO son volúmenes.
_DIMENSION_RE = re.compile(r"\d+\s*[x×]\s*\d+", re.IGNORECASE)
# ISBN-13 (con o sin guiones/espacios internos) e ISBN-10.
_ISBN13_RE = re.compile(r"\b(97[89](?:[- ]?\d){10})\b")
_ISBN10_RE = re.compile(r"\b(\d(?:[- ]?\d){8}[- ]?[\dXx])\b")


def _norm_isbn13(raw: str) -> Optional[str]:
    """Normaliza un ISBN (10 o 13) a ISBN-13 sin separadores, VALIDANDO el
    checksum — un número de 10/13 dígitos cualquiera (ID de producto, teléfono)
    NO debe tratarse como ISBN (conservador: ambiguo → no conflicto)."""
    clean = re.sub(r"[^0-9Xx]", "", str(raw or "")).upper()
    if len(clean) == 13 and clean.isdigit() and clean.startswith(("978", "979")):
        total = sum(int(clean[i]) * (1 if i % 2 == 0 else 3) for i in range(13))
        return clean if total % 10 == 0 else None
    if len(clean) == 10 and clean[:9].isdigit() and (clean[9].isdigit() or clean[9] == "X"):
        total = sum((10 - i) * int(d) for i, d in enumerate(clean[:9]))
        total += 10 if clean[9] == "X" else int(clean[9])
        return _isbn10_to_13(clean) if total % 11 == 0 else None
    return None


def _extract_candidate_volumes(text: str) -> tuple[set, set]:
    """Devuelve (vols_explícitos, vols_bare) declarados en el texto."""
    text = _DIMENSION_RE.sub(" ", text)
    explicit = {int(m) for m in _VOL_EXPLICIT_RE.findall(text) if 0 < int(m) <= 999}
    # Bare: solo en el último segmento del path (filename), valores chicos.
    bare: set = set()
    filename = text.rsplit("/", 1)[-1]
    for m in _VOL_BARE_RE.findall(filename):
        v = int(m)
        if 0 < v <= 60:
            bare.add(v)
    return explicit, bare


def candidate_metadata_conflict(
    item: dict, candidate_url: str, page_title: str = ""
) -> bool:
    """
    True si la metadata DECLARADA por la candidata (en su URL o título de
    página) contradice la del item:
      - el item tiene volumen y la candidata declara claramente OTRO volumen
        (marcador explícito vol/tome/tomo/nº/nr/#; fallback a patrones bare
        -1- / _01_ del filename solo si no hay marcador explícito), o
      - el item tiene ISBN y la candidata declara un ISBN distinto.

    Conservador por diseño: ambiguo → False (no conflicto). El conflicto es un
    hard-reject ADICIONAL a _same_cover (precisión > recall); pensado para que
    el skill watch-search-covers lo llame por candidata.
    """
    from urllib.parse import unquote  # noqa: PLC0415

    text = unquote(candidate_url or "") + " " + (page_title or "")

    # ── Volumen ──
    item_vol = str(item.get("volume", "") or "").strip()
    if item_vol.isdigit():
        v = int(item_vol)
        explicit, bare = _extract_candidate_volumes(text)
        if explicit:
            if v not in explicit:
                return True
        elif bare and v not in bare:
            return True

    # ── ISBN ──
    item_isbn = _norm_isbn13(item.get("isbn", ""))
    if item_isbn:
        cand_isbns: set = set()
        for m in _ISBN13_RE.findall(text):
            n = _norm_isbn13(m)
            if n:
                cand_isbns.add(n)
        for m in _ISBN10_RE.findall(text):
            n = _norm_isbn13(m)
            if n:
                cand_isbns.add(n)
        if cand_isbns and item_isbn not in cand_isbns:
            return True

    return False


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
        # El read-timeout de requests se resetea con cada chunk recibido: un
        # server que gotea bytes lentamente puede colgar el batch entero sin
        # dispararlo. Tope duro de tiempo total por descarga.
        deadline = time.monotonic() + 60
        for chunk in r.iter_content(65536):
            if chunk:
                body.extend(chunk)
            if len(body) > _MAX_BYTES:
                return None
            if time.monotonic() > deadline:
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

    # Volumen: agrega el número de volumen cuando es numérico para anclar la
    # búsqueda al tomo correcto (evita resultados de otros volúmenes de la misma
    # serie). Se agrega después de la serie/título y antes del hint de edición.
    vol_str = str(volume).strip() if volume else ""
    if vol_str.isdigit():
        parts.append(vol_str)

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
    fname = image_store.cover_local(item)
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
    fname = image_store.cover_local(item)
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
        # R7: si la URL matchea un pattern de placeholder, registrar su hash
        # exacto en la denylist y descartar.
        if _maybe_register_placeholder(url, data):
            if verbose:
                print(f"    skip {url[:60]}: placeholder (URL pattern)")
            continue
        # R5: la candidata declara volumen/ISBN en conflicto con el item.
        if candidate_metadata_conflict(item, url):
            if verbose:
                print(f"    skip {url[:60]}: metadata en conflicto (vol/ISBN)")
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

        # Gate de detalle efectivo (gotcha #94): aunque tenga más px, una
        # candidata blanda (escaneo comprimido / upscale) NO es upgrade real.
        if _is_soft_image(data):
            if verbose:
                print(f"    skip {url[:60]}: imagen blanda "
                      f"(detalle {_detail_ratio(data):.3f} < {DETAIL_RATIO_MIN})")
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
    image_url = image_store.cover_url(item)
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
        # R7: placeholder conocido por URL pattern → denylist + descarte.
        if _maybe_register_placeholder(url, data):
            if verbose:
                print(f"    skip {url[:60]}: placeholder (URL pattern)", flush=True)
            continue
        # R5: la candidata declara volumen/ISBN en conflicto con el item.
        if candidate_metadata_conflict(item, url, cand.get("page_title", "")):
            if verbose:
                print(f"    skip {url[:60]}: metadata en conflicto (vol/ISBN)", flush=True)
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
            "via": cand.get("via", "text"),
        }

    return None


_PREVIEW_PATH = _HERE / "data" / "cover_preview.json"


def _write_preview(entries: list[dict]) -> None:
    """Escribe cover_preview.json de forma ATÓMICA (tmp + os.replace).

    El preview se flushea después de CADA item: un crash a mitad de un
    write_text directo dejaba el JSON truncado y se perdía toda la cola
    de candidatas pendientes.
    """
    tmp = _PREVIEW_PATH.with_name(f"{_PREVIEW_PATH.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(_PREVIEW_PATH)


def _apply_improvement(item: dict, new_url: str, new_local: str) -> None:
    """Reemplaza la PORTADA del item (images[0] = única fuente de verdad)."""
    # En dry-run el local es un placeholder: preserva el local actual en vez
    # de persistir "[dry-run]" como filename del espejo.
    local = image_store.cover_local(item) if new_local == "[dry-run]" else new_local
    image_store.set_cover(item, new_url, local)


def _ensure_cover_slot(item: dict) -> None:
    """
    Garantiza que `images[]` exista antes de agregar a la galería. La portada es
    images[0] (única fuente de verdad): si el item ya tiene images[], la posición
    0 ya es la portada y no hay nada que sembrar. Si images[] está vacío, no hay
    portada previa que proteger (la 1ª que se agregue será la portada).
    """
    item.setdefault("images", [])


def _add_gallery_image(item: dict, new_url: str, new_local: str, kind: str) -> None:
    """
    Agrega una imagen a la galería (images[-1]) SIN tocar la portada.
    Idempotente: si la URL ya está en images[], no la duplica.
    """
    _ensure_cover_slot(item)
    images = item.setdefault("images", [])
    if any(img.get("url") == new_url for img in images):
        return
    entry = {"url": new_url, "kind": kind if kind in ("gallery", "extra") else "gallery"}
    if new_local and new_local != "[dry-run]":
        entry["local"] = new_local
    images.append(entry)


def _remove_gallery_image(item: dict, url: str) -> None:
    """Quita de images[] cualquier entrada de galería (idx>=1) con esa URL.
    Nunca toca images[0] (la portada)."""
    images = item.get("images")
    if not images or len(images) <= 1:
        return
    item["images"] = images[:1] + [img for img in images[1:] if img.get("url") != url]


def _replace_at_target(item: dict, target_url: str, new_url: str, new_local: str) -> bool:
    """
    Reemplaza la imagen de images[] cuya url == target_url por la nueva
    (url + local). Si el target es images[0] es la portada (única fuente de
    verdad). Conserva el `kind` del slot reemplazado.
    Devuelve True si encontró el target. Si no lo encuentra (la galería cambió
    desde que se armó el preview), devuelve False — el caller decide el fallback.
    """
    images = item.get("images") or []
    for i, img in enumerate(images):
        if img.get("url") == target_url:
            img["url"] = new_url
            if new_local and new_local != "[dry-run]":
                img["local"] = new_local
            return True
    return False


def _entry_current_images(item: dict) -> list[dict]:
    """Galería actual del item para mostrar en la página de review. images[0] es
    la portada (is_cover) — única fuente de verdad. Si el item no tiene images[],
    no hay portada que mostrar."""
    imgs = item.get("images") or []
    out: list[dict] = []
    for k, im in enumerate(imgs):
        if not isinstance(im, dict):
            continue
        out.append({
            "url": im.get("url", ""),
            "local": im.get("local", ""),
            "kind": im.get("kind", "gallery"),
            "is_cover": k == 0,
        })
    return out


def _normalize_preview_entry(entry: dict) -> dict:
    """
    Devuelve la entry en el schema multi-candidato (con `candidates[]`).
    Backwards-compat: si la entry trae los campos planos del schema viejo
    (new_image/new_url/...), los envuelve en un único candidato con
    action="replace_cover".

    Garantiza `current_images[]` (galería actual del item, para que la UI deje
    elegir qué imagen reemplazar). Si falta, la sintetiza desde old_image/old_url.
    """
    def _fallback_current(e):
        if e.get("old_url") or e.get("old_image"):
            return [{
                "url": e.get("old_url", ""),
                "local": e.get("old_image", ""),
                "kind": "gallery",
                "is_cover": True,
            }]
        return []

    if isinstance(entry.get("candidates"), list):
        # Ya es multi-candidato; rellenar defaults por candidato.
        for c in entry["candidates"]:
            c.setdefault("action", "replace_cover")
            c.setdefault("target", "")
            c.setdefault("kind", "gallery")
            c.setdefault("status", "pending")
            c.setdefault("confidence", "low")
            c.setdefault("page_title", "")
            c.setdefault("domain", "")
            c.setdefault("query", "")
        if not isinstance(entry.get("current_images"), list) or not entry["current_images"]:
            entry["current_images"] = _fallback_current(entry)
        return entry
    candidate = {
        "new_image": entry.get("new_image", ""),
        "new_url": entry.get("new_url", ""),
        "new_pixels": entry.get("new_pixels", 0),
        "page_title": entry.get("page_title", ""),
        "domain": entry.get("domain", ""),
        "query": entry.get("query", ""),
        "confidence": entry.get("confidence", "low"),
        "action": entry.get("action", "replace_cover"),
        "target": entry.get("target", ""),
        "kind": entry.get("kind", "gallery"),
        "status": entry.get("status", "pending"),
    }
    current = entry.get("current_images")
    if not isinstance(current, list) or not current:
        current = _fallback_current(entry)
    return {
        "slug": entry.get("slug", ""),
        "title": entry.get("title", ""),
        "title_original": entry.get("title_original", ""),
        "series_display": entry.get("series_display", ""),
        "publisher": entry.get("publisher", ""),
        "country": entry.get("country", ""),
        "old_image": entry.get("old_image", ""),
        "old_url": entry.get("old_url", ""),
        "old_pixels": entry.get("old_pixels", 0),
        "current_images": current,
        "candidates": [candidate],
    }


def _collect_referenced_locals(items: list[dict]) -> set:
    """Todos los filenames locales referenciados por el corpus (images[].local
    —portada + galería— y sources[].image_local). Usado para borrar archivos
    huérfanos de forma segura tras aplicar el preview."""
    referenced: set = set()
    for it in items:
        for img in (it.get("images") or []):
            if isinstance(img, dict) and img.get("local"):
                referenced.add(img["local"])
        for s in (it.get("sources") or []):
            if isinstance(s, dict) and s.get("image_local"):
                referenced.add(s["image_local"])
    return referenced


def _is_upscaled(item: dict, images_dir: Path) -> bool:
    """Detecta si la portada actual es un PNG upscaleado por waifu2x (look pastel)."""
    local = image_store.cover_local(item)
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
    hits_by_engine: dict[str, int] = {}  # candidatas APROBADAS por via (cdn/lens/text/…)

    # Acumulación de preview (schema multi-candidato). Sembramos desde el
    # cover_preview.json existente — así múltiples pasadas de búsqueda van
    # juntando candidatas por producto en vez de pisarse. Dedup por new_url.
    preview_entries: list[dict] = []
    preview_by_slug: dict[str, dict] = {}
    if not dry_run and _PREVIEW_PATH.exists():
        try:
            for e in json.loads(_PREVIEW_PATH.read_text(encoding="utf-8")):
                e = _normalize_preview_entry(e)
                preview_entries.append(e)
                if e.get("slug"):
                    preview_by_slug[e["slug"]] = e
        except (ValueError, OSError):
            pass

    for pos, idx in enumerate(candidates_idx):
        item = items[idx]
        title = item.get("title", "")[:50]
        if verbose:
            print(f"[{pos+1}/{len(candidates_idx)}] {title}", flush=True)
        elif pos % 50 == 0:
            print(f"  {pos}/{len(candidates_idx)} procesados... "
                  f"({applied_high} aplicadas, {previewed} a preview)", flush=True)

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
                # Telemetría: contabiliza por la vía que produjo esta candidata.
                via_key = result.get("via", "text")
                hits_by_engine[via_key] = hits_by_engine.get(via_key, 0) + 1

                # Regla de seguridad (2026-06-03): NUNCA reemplazar la portada
                # automáticamente sin aprobación. El item conserva su portada
                # vieja hasta que el owner apruebe en cover-preview.html. Única
                # excepción: alta confianza (CDN/ISBN, hash-verificada = misma
                # imagen en mayor resolución) EN modo --apply explícito. La baja
                # confianza NUNCA se auto-aplica — era la fuente de las portadas
                # equivocadas (un kit de magia para "Negima", etc.).
                old_local = image_store.cover_local(item)
                old_url = image_store.cover_url(item)
                if confidence == "high" and not preview and not dry_run:
                    applied_high += 1
                    _apply_improvement(item, new_url, new_local)
                    _atomic_write(items_path, items)
                    flush_count += 1
                    if verbose:
                        print(f"  ✓ aplicada [alta confianza, --apply] ({flush_count})", flush=True)
                else:
                    # A preview, SIN tocar items.jsonl (la portada vieja se queda).
                    # Schema multi-candidato: si el producto ya tiene una entry
                    # (misma slug), agregamos la candidata a su candidates[] en
                    # vez de crear una entry duplicada. Default action=replace_cover
                    # (el owner elige otra en la UI antes de aprobar).
                    previewed += 1
                    slug = item.get("slug", "")
                    candidate = {
                        "new_image": new_local,
                        "new_url": new_url,
                        "new_pixels": result["candidate_pixels"],
                        "page_title": result.get("page_title", ""),
                        "domain": result.get("domain", ""),
                        "query": result.get("query", ""),
                        "confidence": confidence,
                        "action": "replace_cover",
                        "target": "",
                        "kind": "gallery",
                        "status": "pending",
                    }
                    existing = preview_by_slug.get(slug) if slug else None
                    if existing is not None:
                        if not any(c.get("new_url") == new_url
                                   for c in existing["candidates"]):
                            existing["candidates"].append(candidate)
                    else:
                        entry = {
                            "slug": slug,
                            "title": item.get("title", ""),
                            "title_original": item.get("title_original", ""),
                            "series_display": item.get("series_display", ""),
                            "publisher": item.get("publisher", ""),
                            "country": item.get("country", ""),
                            "old_image": old_local,
                            "old_url": old_url,
                            "old_pixels": result["current_pixels"],
                            # galería actual completa (para elegir qué reemplazar)
                            "current_images": _entry_current_images(item),
                            "candidates": [candidate],
                        }
                        preview_entries.append(entry)
                        if slug:
                            preview_by_slug[slug] = entry
                    if not dry_run:
                        _write_preview(preview_entries)
                    if verbose:
                        tag = "alta" if confidence == "high" else "baja"
                        print(f"  → preview [{tag} confianza, NO aplicada] "
                              f"({previewed} candidatas)", flush=True)
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
    total_hits = applied_high + previewed
    if total_hits > 0 and hits_by_engine:
        print(f"\n  Candidatas aprobadas por motor:")
        for engine, count in sorted(hits_by_engine.items(), key=lambda x: -x[1]):
            print(f"    {engine:<12s}  {count}")
    if previewed > 0:
        print(f"\n  ⚠  {previewed} candidatas NO aplicadas — revisalas y aprobá:")
        print(f"  Preview:    {_PREVIEW_PATH}")
        print(f"  Abrir:      http://localhost:8000/web/cover-preview.html")
        print(f"  Después:    .venv/bin/python scripts/retrofit/fetch_better_covers.py --apply-preview")


def apply_preview(items_path: Path, images_dir: Path) -> None:
    """
    Procesa el preview JSON (schema multi-candidato). Cada producto puede tener
    N candidatas, cada una con su `action` y `status`:

      action:
        replace_cover  → la nueva reemplaza la portada (images[0] + image_url).
        add_gallery    → la nueva se agrega a la galería (kind="gallery").
        add_extra      → idem pero kind="extra" (bonus/regalo).
        replace_and_add→ reemplaza portada Y agrega la misma a la galería.

      status:
        approved → se aplica la acción.
        rejected → se revierte (replace_*: vuelve a la portada vieja;
                   add_*: quita la URL de la galería). Borra la imagen nueva.
        pending  → no se toca; queda en el preview.

    Backwards-compat: entries del schema viejo (campos planos) se normalizan a
    un único candidato con action="replace_cover".

    Una entry se quita del preview cuando TODAS sus candidatas están decididas
    (approved/rejected). Si queda alguna pending, la entry se conserva entera.
    """
    if not _PREVIEW_PATH.exists():
        print(f"No hay preview en {_PREVIEW_PATH}.")
        return {"ok": True, "applied": 0, "rejected": 0, "pending": 0,
                "message": "No hay preview."}

    raw = json.loads(_PREVIEW_PATH.read_text(encoding="utf-8"))
    preview = [_normalize_preview_entry(e) for e in raw]

    all_cands = [c for e in preview for c in e["candidates"]]
    n_approved = sum(1 for c in all_cands if c.get("status") == "approved")
    n_rejected = sum(1 for c in all_cands if c.get("status") == "rejected")
    n_pending  = sum(1 for c in all_cands if c.get("status", "pending") == "pending")

    print(f"Preview: {len(preview)} productos, {len(all_cands)} candidatas — "
          f"{n_approved} aprobadas, {n_rejected} rechazadas, {n_pending} pendientes",
          flush=True)

    if not n_approved and not n_rejected:
        print("Nada que procesar (todo pendiente).")
        return {"ok": True, "applied": 0, "rejected": 0, "pending": n_pending,
                "message": "Nada que procesar (todo pendiente)."}

    items = [json.loads(l) for l in items_path.open(encoding="utf-8")]
    backup_and_rotate(items_path, "apply-preview")

    items_by_slug: dict[str, list[dict]] = {}
    for item in items:
        s = item.get("slug", "")
        if s:
            items_by_slug.setdefault(s, []).append(item)

    replaced = 0
    galleried = 0
    reverted = 0
    skipped_missing_file = 0
    redownloaded = 0
    _redl_session = None   # sesión lazy para re-descargas del guard self-healing
    # Archivos candidatos a borrar tras aplicar (se filtran por orphan-check).
    old_to_drop: set = set()   # portadas viejas reemplazadas
    new_to_drop: set = set()   # imágenes nuevas rechazadas
    # Slugs de entries con candidatas aprobadas pero archivo faltante → conservar en preview.
    entries_with_missing: set = set()

    for entry in preview:
        slug = entry.get("slug", "")
        targets = items_by_slug.get(slug, [])
        old_url = entry.get("old_url", "")
        old_image = entry.get("old_image", "")
        # Mapa url→local de la galería actual (para borrar el archivo de la
        # imagen reemplazada cuando action == replace_image).
        cur_local_by_url = {
            ci.get("url", ""): ci.get("local", "")
            for ci in (entry.get("current_images") or [])
            if isinstance(ci, dict)
        }
        for cand in entry["candidates"]:
            status = cand.get("status", "pending")
            action = cand.get("action", "replace_cover")
            new_url = cand.get("new_url", "")
            new_local = cand.get("new_image", "")
            kind = cand.get("kind", "gallery")
            target = cand.get("target", "")

            if status == "approved":
                # Guard self-healing: si la candidata aprobada referencia un archivo
                # local que ya no existe en disco (p.ej. lo borró un apply previo y
                # una copia stale de la UI resucitó la entry), intentar RE-DESCARGAR
                # desde new_url antes de rendirse. Solo si la descarga falla se omite
                # (la entry se conserva en el preview y se reporta en el summary).
                if new_local and new_local != "[dry-run]" and not (images_dir / new_local).exists():
                    refetched = ""
                    if new_url.startswith("http"):
                        if _redl_session is None:
                            _redl_session = requests.Session()
                            _redl_session.headers.update({"User-Agent": _UA})
                        data_bytes = _fetch(new_url, _redl_session)
                        if data_bytes:
                            refetched = _save_image(data_bytes, images_dir) or ""
                    if refetched:
                        new_local = refetched
                        cand["new_image"] = refetched
                        redownloaded += 1
                    else:
                        skipped_missing_file += 1
                        entries_with_missing.add(slug)
                        continue
            if status == "approved":
                if action == "replace_cover":
                    for item in targets:
                        _apply_improvement(item, new_url, new_local)
                    replaced += 1
                    if old_image and old_image != new_local:
                        old_to_drop.add(old_image)
                elif action == "replace_image":
                    # Reemplaza una imagen específica de la galería (por su url).
                    # Si la galería cambió y no se encuentra, fallback a agregar.
                    hit = False
                    for item in targets:
                        if _replace_at_target(item, target, new_url, new_local):
                            hit = True
                        else:
                            _add_gallery_image(item, new_url, new_local,
                                               kind if kind == "extra" else "gallery")
                    replaced += 1
                    old_local = cur_local_by_url.get(target, "")
                    if hit and old_local and old_local != new_local:
                        old_to_drop.add(old_local)
                elif action == "add_gallery":
                    for item in targets:
                        _add_gallery_image(item, new_url, new_local, "gallery")
                    galleried += 1
                elif action == "add_extra":
                    for item in targets:
                        _add_gallery_image(item, new_url, new_local, "extra")
                    galleried += 1
                elif action == "replace_cover_demote":
                    # La nueva pasa a portada y la portada ACTUAL se conserva en
                    # la galería como extra (no se descarta). Es lo que el owner
                    # suele querer: "promové esta, pero guardame la vieja".
                    for item in targets:
                        _ensure_cover_slot(item)
                        prev_url = image_store.cover_url(item)
                        prev_local = image_store.cover_local(item)
                        _apply_improvement(item, new_url, new_local)
                        if prev_url and prev_url != new_url:
                            _add_gallery_image(item, prev_url, prev_local, "extra")
                    replaced += 1
                    galleried += 1
                    # NO borramos la portada vieja: ahora vive en la galería.
                elif action == "replace_and_add":
                    for item in targets:
                        _apply_improvement(item, new_url, new_local)
                        _add_gallery_image(item, new_url, new_local,
                                           kind if kind == "extra" else "gallery")
                    replaced += 1
                    galleried += 1
                    if old_image and old_image != new_local:
                        old_to_drop.add(old_image)
            elif status == "rejected":
                if action in ("replace_cover", "replace_and_add"):
                    # Revertir SOLO si la candidata rechazada es la portada
                    # vigente (una corrida previa la aplicó). Antes se revertía
                    # incondicional y pisaba la candidata APROBADA de la misma
                    # entry en la misma corrida (bug 2026-06-11).
                    for item in targets:
                        if image_store.cover_url(item) == new_url:
                            _apply_improvement(item, old_url, old_image)
                        _remove_gallery_image(item, new_url)
                    reverted += 1
                elif action in ("add_gallery", "add_extra", "replace_image",
                                "replace_cover_demote"):
                    # Nada se había aplicado todavía (safe-by-default): solo
                    # quitamos la url nueva por si una corrida previa la agregó.
                    for item in targets:
                        _remove_gallery_image(item, new_url)
                    reverted += 1
                if new_local and new_local != old_image and new_local != "[dry-run]":
                    new_to_drop.add(new_local)
            # pending: nada

    _atomic_write(items_path, items)

    # Borrado seguro de archivos: solo si NINGÚN item los referencia tras aplicar.
    referenced = _collect_referenced_locals(items)
    cleaned_old = 0
    cleaned_new = 0
    for fname in old_to_drop:
        if fname and fname not in referenced:
            f = images_dir / fname
            if f.exists():
                f.unlink()
                cleaned_old += 1
    for fname in new_to_drop:
        if fname and fname not in referenced:
            f = images_dir / fname
            if f.exists():
                f.unlink()
                cleaned_new += 1

    print(f"✓ Resultado:")
    print(f"  Reemplazos (portada/galería): {replaced} (imagen vieja eliminada: {cleaned_old})")
    print(f"  Agregadas a galería:          {galleried}")
    print(f"  Revertidas (rechazadas):      {reverted} (imagen nueva eliminada: {cleaned_new})")
    if redownloaded:
        print(f"  Re-descargadas (self-heal):   {redownloaded} (archivo faltante recuperado desde new_url)")
    if skipped_missing_file:
        print(f"  Omitidas (archivo faltante):  {skipped_missing_file} (re-descarga falló; siguen en preview)")

    # Conservar SOLO las candidatas pendientes de cada entry; las decididas
    # (aplicadas/revertidas) se quitan del JSON aunque la entry siga viva.
    # Excepción: entries con candidatas aprobadas cuyo archivo ya no existe en
    # disco — se conservan en el preview como "pendientes" para que una
    # corrida posterior pueda re-descargarlas (no se pierden).
    # Antes la entry con pendientes se conservaba ENTERA: la candidata aprobada
    # ya aplicada seguía mostrándose como "approved" en la UI (parecía pegada)
    # y su old_image podía apuntar a un archivo ya borrado (bug 2026-06-11).
    remaining = []
    for e in preview:
        e_slug = e.get("slug", "")
        # Candidatas a conservar: pending + approved-con-archivo-faltante (tratadas como pending).
        pend = [
            c for c in e["candidates"]
            if c.get("status", "pending") == "pending"
            or (
                c.get("status") == "approved"
                and c.get("new_image", "")
                and c.get("new_image") != "[dry-run]"
                and not (images_dir / c["new_image"]).exists()
            )
        ]
        if not pend and e_slug not in entries_with_missing:
            continue
        if len(pend) != len(e["candidates"]):
            e["candidates"] = pend
            # Alguna decidida se aplicó → refrescar el estado "actual" de la
            # entry (portada/galería post-apply) para que la comparación de las
            # pendientes sea contra la imagen vigente, no contra la reemplazada.
            targets = items_by_slug.get(e.get("slug", ""), [])
            if targets:
                imgs = targets[0].get("images") or []
                if imgs and isinstance(imgs[0], dict):
                    e["old_url"] = imgs[0].get("url", "")
                    e["old_image"] = imgs[0].get("local", "")
                    e["old_pixels"] = _get_current_pixels(targets[0], images_dir)
                e["current_images"] = [
                    {"url": im.get("url", ""), "local": im.get("local", ""),
                     "kind": im.get("kind", "gallery"), "is_cover": k == 0}
                    for k, im in enumerate(imgs) if isinstance(im, dict)
                ]
        remaining.append(e)
    n_rem = 0
    if remaining:
        _write_preview(remaining)
        n_rem = sum(1 for e in remaining for c in e["candidates"]
                    if c.get("status", "pending") == "pending")
        print(f"  Pendientes:              {n_rem} candidatas (siguen en preview)")
    else:
        _PREVIEW_PATH.unlink()
        print(f"  Preview limpiado (todo procesado).")

    return {
        "ok": True,
        "applied": n_approved,
        "rejected": n_rejected,
        "pending": n_rem,
        "replaced": replaced,
        "galleried": galleried,
        "reverted": reverted,
        "cleaned_old": cleaned_old,
        "cleaned_new": cleaned_new,
        "skipped_missing_file": skipped_missing_file,
        "redownloaded": redownloaded,
    }


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
        help=f"Cota Hamming del aHash para aceptar candidata como 'misma portada' "
             f"(default: {DEFAULT_MAX_HASH_DIST}/64). dHash<=8, pHash<=8, NCC>=0.90 y "
             f"el gate de entropía aplican SIEMPRE además de esta cota. Valores >6 "
             f"se honran pero con warning (riesgo de falsos positivos).",
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

    if args.max_hash_dist > DEFAULT_MAX_HASH_DIST:
        print(f"⚠️  --max-hash-dist {args.max_hash_dist} > {DEFAULT_MAX_HASH_DIST} "
              f"(default): se honra, pero sube el riesgo de falsos positivos del "
              f"aHash. dHash/pHash/NCC/entropía siguen aplicando igual.", flush=True)

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
