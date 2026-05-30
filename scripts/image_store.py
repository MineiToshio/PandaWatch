#!/usr/bin/env python3
"""image_store.py — espejo local de portadas (Image storage, Fase 1).

PandaWatch venía hotlinkeando las portadas directamente del sitio fuente
(retailers, wikis). Para un servicio desplegable multi-usuario queremos
**ser dueños de los bytes**: este módulo descarga cada portada a
`data/images/` y el pipeline guarda el filename local en el campo
`image_local` de cada item. `image_url` queda intacto como provenance
+ fallback (si la fuente muere o agrega anti-hotlink, la card sigue
mostrando la copia local).

Diseño:

- **Nombre de archivo = `sha256(image_url)[:16]` + extensión.** El stem
  es determinístico, así que re-scrapear la misma imagen reutiliza el
  archivo en disco en vez de re-descargar (idempotente).
- **La extensión sale de los magic bytes** del archivo descargado, no
  de la URL ni del Content-Type — es lo más confiable. El chequeo de
  "ya existe" usa un glob `<stem>.*` para no depender de la extensión.
- **Validación por magic bytes**: si el body no empieza con una firma
  de imagen conocida (una página HTML de error / anti-bot, por ejemplo),
  se descarta y `image_local` queda vacío → la card cae al `image_url`
  remoto. Falla siempre de forma elegante, nunca rompe el scrape.

Fase 2 (subir el espejo a un bucket propio de Cloudflare R2) está
documentada en CLAUDE.md ("Image storage") pero NO implementada acá.
Cuando llegue, sólo cambia de dónde se sirven los archivos: el esquema
(`image_local` = nombre relativo) ya es agnóstico al entorno.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import requests

# ── CDN resize-param normalization ────────────────────────────────────────────
# These query params only control thumbnail size/quality, not image identity.
# Stripping them lets the scraper always hash the "canonical" URL so that
# the thumbnail (CDN URL with params) and the hi-res (clean URL) map to the
# same local filename — avoiding the situation where a re-scrape after
# upgrade_image_resolution stores a new thumbnail under a different hash.
_CDN_RESIZE_PARAMS = frozenset({
    "quality", "q",
    "width", "height", "w", "h",
    "fit", "fit_mode",
    "canvas",
    "bg-color", "bg_color", "background",
    "format", "auto",
    "dpr",
    "crop", "gravity",
    "resize",
    "upscale",
    "bounds",
})
# WordPress -NxM suffix  e.g.  image-300x300.jpg → image.jpg
_WP_SUFFIX_RE = re.compile(r"^(.+?)-(\d{2,4}x\d{2,4})(\.\w{2,5})$", re.IGNORECASE)
# Shopify _Nx or _NxN suffix  e.g.  image_540x.jpg → image.jpg
_SHOPIFY_SUFFIX_RE = re.compile(
    r"^(.+?)_(\d{2,4}x\d*|x\d{2,4})(\.\w{2,5})$", re.IGNORECASE
)
# Amazon CDN size modifiers embedded in filename: ._SY300_. ._SL165_. ._SS120_. etc.
# e.g.  91XYZ._SY300_.jpg → 91XYZ.jpg
_AMAZON_HOSTS = frozenset({
    "m.media-amazon.com", "images-amazon.com",
    "images-fe.ssl-images-amazon.com", "images-na.ssl-images-amazon.com",
})
_AMAZON_SIZE_RE = re.compile(r"(\._[A-Z]{2}\d*_)+", re.IGNORECASE)
# Rakuten Books CDN: ?_ex=NxN  e.g.  ...cabinet/9312/2100014729312.jpg?_ex=200x200
# Without _ex the CDN returns the full 988×1200 image (36× more pixels).
_RAKUTEN_THUMB_HOSTS = frozenset({"thumbnail.image.rakuten.co.jp"})
_RAKUTEN_EX_RE = re.compile(r"^\d+x\d+$")


def normalize_image_url(url: str) -> str:
    """Devuelve la URL sin parámetros de redimensionado de CDN.

    Idempotente: si la URL ya es la original, la devuelve sin cambios.
    Esto garantiza que sha256(normalize(url)) siempre produce el mismo
    stem tanto para la URL con parámetros CDN como para la URL limpia.
    """
    if not url:
        return url
    parsed = urlparse(url)
    path = parsed.path

    # 1. Magento-style query params
    if parsed.query:
        qs_keys = {k.lower() for k, _ in parse_qsl(parsed.query, keep_blank_values=True)}
        if qs_keys & {"width", "height", "w", "h"} and qs_keys & _CDN_RESIZE_PARAMS:
            return parsed._replace(query="").geturl()

    # 2. WordPress -NxM suffix
    filename = path.rsplit("/", 1)[-1]
    m = _WP_SUFFIX_RE.match(filename)
    if m:
        clean_path = path[: path.rfind("/") + 1] + m.group(1) + m.group(3)
        return parsed._replace(path=clean_path, query="").geturl()

    # 3. Shopify _Nx suffix
    m = _SHOPIFY_SUFFIX_RE.match(filename)
    if m:
        clean_path = path[: path.rfind("/") + 1] + m.group(1) + m.group(3)
        return parsed._replace(path=clean_path, query="").geturl()

    # 4. Amazon CDN embedded size modifiers (._SY300_. ._SL165_. ._SS120_. etc.)
    if parsed.netloc in _AMAZON_HOSTS:
        if _AMAZON_SIZE_RE.search(path):
            clean_path = _AMAZON_SIZE_RE.sub("", path)
            return parsed._replace(path=clean_path, query="").geturl()

    # 5. Rakuten Books CDN: ?_ex=NxN thumbnail resize param
    if parsed.netloc in _RAKUTEN_THUMB_HOSTS and parsed.query:
        qs = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if "_ex" in qs and _RAKUTEN_EX_RE.match(qs["_ex"]):
            return parsed._replace(query="").geturl()

    return url


# Subdirectorio bajo data/ donde vive el espejo local.
IMAGES_DIRNAME = "images"

# Cota de tamaño por portada. Una cover de manga rara vez pasa de 1-2 MB;
# 12 MB deja margen para escaneos grandes sin permitir descargas absurdas.
_MAX_IMAGE_BYTES = 12 * 1024 * 1024

# Tamaño de chunk al hacer streaming de la respuesta.
_CHUNK_BYTES = 64 * 1024


def image_stem(image_url: str) -> str:
    """Stem determinístico (16 hex) derivado del URL de la imagen.

    Normaliza los parámetros de redimensionado CDN antes de hashear, de modo
    que la URL con params y la URL limpia producen el mismo stem.
    """
    canonical = normalize_image_url(image_url.strip())
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:16]


def _extension_from_magic(body: bytes) -> str:
    """Devuelve la extensión (con punto) según los magic bytes del archivo.

    Devuelve "" si el body no parece una imagen conocida — el caller usa
    eso para descartar la descarga (típicamente una página HTML de error).
    """
    if len(body) < 12:
        return ""
    if body[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if body[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if body[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return ".webp"
    if body[4:12] in (b"ftypavif", b"ftypavis"):
        return ".avif"
    if body[:2] == b"BM":
        return ".bmp"
    return ""


def existing_local_image(images_dir: Path, image_url: str) -> str:
    """Si ya hay un archivo para este URL en images_dir, devuelve su nombre.

    Hace glob por `<stem>.*` para no depender de la extensión (que sólo
    se conoce tras descargar). Devuelve "" si no existe.
    """
    images_dir = Path(images_dir)
    if not images_dir.exists():
        return ""
    stem = image_stem(image_url)
    for path in sorted(images_dir.glob(stem + ".*")):
        if path.is_file() and not path.name.endswith(".tmp"):
            return path.name
    return ""


def download_image(
    image_url: str,
    images_dir: Path,
    session: requests.Session | None = None,
    timeout: tuple[int, int] = (10, 30),
    referer: str = "",
) -> str:
    """Descarga `image_url` a `images_dir` y devuelve el filename local.

    Devuelve "" ante cualquier problema (URL no http, no-2xx, body que no
    es imagen, timeout, archivo vacío). El caller trata "" como "no hay
    espejo local todavía" y conserva `image_url` como fallback.

    Idempotente: si ya existe un archivo para este URL, lo devuelve sin
    tocar la red.
    """
    if not image_url or not image_url.lower().startswith(("http://", "https://")):
        return ""

    # Normalize CDN resize params so we always fetch + hash the full-res URL.
    image_url = normalize_image_url(image_url)

    images_dir = Path(images_dir)
    already = existing_local_image(images_dir, image_url)
    if already:
        return already

    getter = session.get if session is not None else requests.get
    headers = {"Referer": referer} if referer else None

    try:
        resp = getter(image_url, timeout=timeout, stream=True, headers=headers)
    except requests.RequestException:
        return ""

    try:
        if resp.status_code != 200:
            return ""
        body = bytearray()
        for chunk in resp.iter_content(_CHUNK_BYTES):
            if not chunk:
                continue
            body.extend(chunk)
            if len(body) > _MAX_IMAGE_BYTES:
                return ""
    except requests.RequestException:
        return ""
    finally:
        resp.close()

    body = bytes(body)
    ext = _extension_from_magic(body)
    if not ext:
        # No es una imagen reconocible (probable HTML de error / anti-bot).
        return ""

    filename = image_stem(image_url) + ext
    images_dir.mkdir(parents=True, exist_ok=True)
    dest = images_dir / filename
    # tmp ÚNICO por descarga. Dos threads que bajan el MISMO image_url
    # comparten `dest` (el nombre deriva del hash del URL); si compartieran
    # también el `.tmp`, el primero en hacer rename deja al segundo con un
    # tmp inexistente → FileNotFoundError. El token uuid evita la colisión;
    # `os.replace` sigue siendo atómico y last-wins sobre `dest`.
    tmp = dest.with_name(f"{dest.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_bytes(body)
        tmp.replace(dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        return ""
    return filename
