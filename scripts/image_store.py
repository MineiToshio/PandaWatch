#!/usr/bin/env python3
"""image_store.py — espejo local de portadas (Image storage, Fase 1).

PandaWatch venía hotlinkeando las portadas directamente del sitio fuente
(retailers, wikis). Para un servicio desplegable multi-usuario queremos
**ser dueños de los bytes**: este módulo descarga cada imagen a
`data/images/` y el pipeline guarda el filename local en el campo `local`
del entry correspondiente de `images[]`. La URL remota (`url`) queda como
provenance + fallback (si la fuente muere o agrega anti-hotlink, la card
sigue mostrando la copia local).

**Portada = `images[0]`** (decisión 2026-06-09): se eliminaron los campos
top-level `image_url`/`image_local` del item; `images[0]` es la ÚNICA fuente
de verdad de la portada. Los helpers `cover_url`/`cover_local`/`set_cover` al
final del módulo centralizan el acceso.

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
import os
import re
import uuid
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import requests

# libvips por defecto usa TODOS los cores para UNA imagen. Cuando paralelizamos por
# ARCHIVO (ThreadPoolExecutor en el scrape y en los backfills de imágenes), eso
# oversuscribe la CPU y thrashea (N workers × M cores = N·M hilos peleando). Con
# VIPS_CONCURRENCY=1 cada imagen se procesa single-thread y la paralelización la da el
# pool → throughput mucho mayor. Debe setearse ANTES de importar pyvips (libvips lo lee
# al inicializar). `setdefault` deja overridearlo por env si alguien lo necesita.
os.environ.setdefault("VIPS_CONCURRENCY", "1")

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
    # URLs/referers con no-ASCII (slugs thai de yaakz, chinos de jd-intl)
    # rompen http.client con UnicodeEncodeError latin-1 — requote a
    # percent-encoding. El referer además se omite si sigue siendo no-ASCII.
    image_url = requests.utils.requote_uri(image_url)
    headers = None
    if referer:
        safe_ref = requests.utils.requote_uri(referer)
        try:
            safe_ref.encode("latin-1")
            headers = {"Referer": safe_ref}
        except UnicodeEncodeError:
            headers = None

    try:
        resp = getter(image_url, timeout=timeout, stream=True, headers=headers)
    except (requests.RequestException, UnicodeError):
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

    # Estandariza al ingresar: AVIF Q60, lado largo ≤ 1600px, sin metadata
    # (fuente única en normalize_image). Placeholders y errores pasan crudos,
    # con su extensión original.
    body, ext = normalize_image(body)

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


# ── Portada por posición — images[0] es la ÚNICA fuente de verdad ──────────────
# Decisión 2026-06-09: se eliminaron los campos top-level `image_url`/
# `image_local` del item. La portada es `images[0]`; cada entry de `images[]`
# lleva `url` (remota) + `local` (filename del espejo). Estos helpers centralizan
# la derivación para que ningún sitio la reimplemente (la divergencia entre
# sitios fue la raíz del drift de portadas). Operan sobre el dict del item/row;
# el `Candidate` runtime conserva `image_url`/`image_local` como input del
# scraper y `candidate_to_json` los convierte en `images[0]` al serializar.

def cover_image(item: dict) -> dict | None:
    """Primer elemento de `images[]` con `url` (la portada), o None."""
    for im in (item.get("images") or []):
        if im and im.get("url"):
            return im
    return None


def cover_url(item: dict) -> str:
    """URL remota de la portada (`images[0].url`), o "" si no hay."""
    im = cover_image(item)
    return im.get("url", "") if im else ""


def cover_local(item: dict) -> str:
    """Filename del espejo local de la portada (`images[0].local`), o ""."""
    im = cover_image(item)
    return im.get("local", "") if im else ""


def set_cover(item: dict, url: str, local: str = "") -> None:
    """Setea `images[0]` como la portada (crea `images[]` si falta).

    Preserva `kind`/`description` del elemento existente; el resto de la galería
    (`images[1:]`) queda intacta. Para BORRAR la portada usá `clear_cover`.
    """
    imgs = item.get("images")
    if not isinstance(imgs, list):
        imgs = []
        item["images"] = imgs
    if imgs:
        imgs[0] = {**imgs[0], "url": url, "local": local}
    else:
        imgs.append({"url": url, "local": local, "kind": "gallery", "description": ""})


def clear_cover(item: dict) -> None:
    """Quita la portada (`images[0]`). Si la galería tenía más fotos, la
    siguiente pasa a ser la portada; si no, `images[]` queda vacío."""
    imgs = item.get("images")
    if isinstance(imgs, list) and imgs:
        imgs.pop(0)


# ── Detección de imágenes-placeholder ─────────────────────────────────────────
# Algunas fuentes sirven una imagen genérica cuando NO tienen la portada real:
#   - un pixel 1×1 (Amazon devuelve un GIF 1×1 para ISBN sin carátula),
#   - una imagen casi sólida en blanco (listadomanga, varios CDNs),
#   - un placeholder CON texto/logo ("Cover Coming Soon", "Immagine non
#     disponibile", "Image coming soon").
# Ninguna es una portada: hay que quitarla de `images[]` para que la UI caiga al
# placeholder 📚 por defecto. La detección tiene dos capas:
#   1. ESTRUCTURAL (sin config): dims diminutas, casi-sólido (std<3), archivo roto.
#   2. FIRMAS (data/placeholder_signatures.json): sha1 del CONTENIDO de los
#      placeholders CON texto, que no caen por baja entropía.
# Fuente ÚNICA de la heurística: el retrofit purge_placeholder_images.py y el
# pipeline la importan de acá — nunca reimplementar la lógica en otro lado.

_PLACEHOLDER_MIN_SIDE = 8         # lado ≤ 8 px ⇒ tracking pixel / placeholder
_PLACEHOLDER_MAX_STD = 3.0        # std global de luminancia < 3 ⇒ casi un solo color
_PLACEHOLDER_STD_MAXBYTES = 200_000  # std solo en archivos chicos (un sólido comprime
                                     # mínimo; una portada real nunca es <200KB Y plana)

_signatures_cache: dict[str, str] | None = None


def _signatures_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "placeholder_signatures.json"


def load_placeholder_signatures(refresh: bool = False) -> dict[str, str]:
    """`{sha1_contenido: label}` de los placeholders CON texto registrados en
    data/placeholder_signatures.json. Cacheado; `refresh=True` recarga."""
    global _signatures_cache
    if _signatures_cache is not None and not refresh:
        return _signatures_cache
    sigs: dict[str, str] = {}
    try:
        import json
        data = json.loads(_signatures_path().read_text(encoding="utf-8"))
        for entry in data.get("signatures", []):
            h = (entry.get("sha1") or "").strip().lower()
            if h:
                sigs[h] = entry.get("label", "")
    except (OSError, ValueError):
        sigs = {}
    _signatures_cache = sigs
    return sigs


def placeholder_reason(source, *, signatures: dict | None = None) -> str:
    """Por qué `source` es un placeholder, o "" si parece una imagen real.

    `source` puede ser `bytes` (imagen ya descargada) o un `Path`/`str` a un
    archivo en disco. Devuelve uno de:

    - ``""``            la imagen parece real (no tocar).
    - ``"broken"``      0 bytes / no abre con PIL / truncado.
    - ``"tiny:WxH"``    algún lado ≤ 8 px (1×1 tracking pixel, etc.).
    - ``"solid:STD"``   std global de luminancia < 3 ⇒ imagen casi de un solo
      color (el blanco "sin portada"). Una portada de manga real tiene std ≫ 20.
    - ``"signature:LABEL"`` el sha1 del contenido está registrado en
      placeholder_signatures.json (placeholders CON texto/logo).
    """
    import io
    if isinstance(source, (bytes, bytearray)):
        body = bytes(source)
    else:
        try:
            body = Path(source).read_bytes()
        except OSError:
            return "broken"
    if not body:
        return "broken"
    sigs = load_placeholder_signatures() if signatures is None else signatures
    if sigs:
        digest = hashlib.sha1(body).hexdigest()
        if digest in sigs:
            return f"signature:{sigs[digest] or digest[:8]}"
    try:
        from PIL import Image, ImageStat
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(io.BytesIO(body)) as im:
            w, h = im.size
            if w <= _PLACEHOLDER_MIN_SIDE or h <= _PLACEHOLDER_MIN_SIDE:
                return f"tiny:{w}x{h}"
            if len(body) <= _PLACEHOLDER_STD_MAXBYTES:
                std = ImageStat.Stat(im.convert("L")).stddev[0]
                if std < _PLACEHOLDER_MAX_STD:
                    return f"solid:{std:.1f}"
    except Exception:
        return "broken"
    return ""


# ── Normalización de imágenes — estandarización al ingresar ────────────────────
# Toda imagen que entra al espejo se estandariza a un "master de display" único:
# AVIF calidad 60, lado largo ≤ NORMALIZE_MAX_LONG_SIDE px, sin metadata. AVIF pesa
# ~27% menos que WebP a la MISMA calidad visual (decisión owner 2026-06-15) → clave
# para Cloudflare R2 + velocidad web, y acota el crecimiento del catálogo. Fuente
# ÚNICA: download_image() y el retrofit optimize_images.py llaman acá — nunca
# reimplementar la lógica en otro lado.
#
# Soporte de navegador: AVIF ~93% (Chrome/Firefox/Edge/Safari 16.4+). El ~6-7% viejo
# (Safari pre-2023) NO se soporta a propósito (decisión owner): en web-next next/image
# transcodifica solo; el dashboard estático cae a la url remota.
#
# Reglas (importan):
#   - Solo redimensiona HACIA ABAJO (nunca agranda; el upscale AI es otro proceso,
#     manual y gateado — ver scripts/retrofit/upscale_images.py).
#   - NUNCA toca placeholders: si placeholder_reason(body) != "", devuelve los bytes
#     CRUDOS sin cambiar, para que la detección por FIRMA (sha1 del contenido) de
#     purge_placeholder_images siga matcheando aguas abajo. Si re-encodearamos, el
#     sha1 cambiaría y las firmas dejarían de funcionar.
#   - Idempotente: una imagen ya AVIF y ≤ max se devuelve sin re-encodear (cero
#     pérdida generacional en re-runs).
#   - Degrada con gracia: ante cualquier error de decode/encode (o sin pyvips/PIL)
#     devuelve los bytes originales con su extensión — nunca rompe el scrape.

NORMALIZE_MAX_LONG_SIDE = 1600
NORMALIZE_QUALITY = 60  # escala AVIF (Q~50-63 ≈ WebP q80 a igual calidad visual)


def _normalize_pyvips(body: bytes, max_long_side: int, quality: int) -> bytes:
    """Resize-down + AVIF via libvips/libheif. thumbnail_buffer auto-rota por EXIF y
    solo achica (size='down'); keep='none' strippea la metadata en el mismo save.
    compression='av1' = AVIF; effort 0-9 (4 = balance velocidad/peso)."""
    import pyvips

    img = pyvips.Image.thumbnail_buffer(
        body, max_long_side, height=max_long_side, size="down"
    )
    return img.heifsave_buffer(Q=quality, compression="av1", effort=4, keep="none")


def _normalize_pillow(body: bytes, max_long_side: int, quality: int) -> bytes:
    """Fallback con Pillow (>=11.3 trae AVIF nativo): respeta orientación EXIF,
    conserva alpha, solo achica, y al guardar AVIF sin pasar exif= la metadata no se
    copia (queda strippeada)."""
    import io

    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = None
    with Image.open(io.BytesIO(body)) as im:
        im = ImageOps.exif_transpose(im)
        has_alpha = im.mode in ("RGBA", "LA", "PA") or (
            im.mode == "P" and "transparency" in im.info
        )
        im = im.convert("RGBA" if has_alpha else "RGB")
        im.thumbnail((max_long_side, max_long_side), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "AVIF", quality=quality)
        return out.getvalue()


def normalize_image(
    body: bytes,
    *,
    max_long_side: int = NORMALIZE_MAX_LONG_SIDE,
    quality: int = NORMALIZE_QUALITY,
) -> tuple[bytes, str]:
    """Estandariza `body` a AVIF Q60 con lado largo ≤ max_long_side, sin metadata.

    Devuelve ``(bytes, extension_con_punto)`` listos para escribir a disco:

    - imagen real más grande que el máximo o en otro formato → AVIF redimensionado.
    - imagen ya AVIF y ≤ max → se devuelve igual (idempotente, sin re-encode).
    - placeholder (``placeholder_reason`` != "") → bytes CRUDOS sin tocar.
    - error / sin librerías → bytes originales con su extensión (fallback elegante).
    """
    orig_ext = _extension_from_magic(body) or ".bin"

    # 1. Placeholders: NO normalizar (preserva las firmas sha1 para el purge).
    if placeholder_reason(body):
        return body, orig_ext

    # 2. Idempotencia: ya AVIF y dentro del máximo → no re-encodear.
    if orig_ext == ".avif":
        try:
            import io

            from PIL import Image

            Image.MAX_IMAGE_PIXELS = None
            with Image.open(io.BytesIO(body)) as im:
                if max(im.size) <= max_long_side:
                    return body, ".avif"
        except Exception:
            return body, ".avif"

    # 3. Normalizar: pyvips (rápido, baja memoria) y, si falla, Pillow.
    for engine in (_normalize_pyvips, _normalize_pillow):
        try:
            out = engine(body, max_long_side, quality)
            if out:
                return out, ".avif"
        except Exception:
            continue

    # 4. Fallback: nada funcionó → bytes originales sin tocar.
    return body, orig_ext
