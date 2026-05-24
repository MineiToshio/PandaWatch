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
import uuid
from pathlib import Path

import requests


# Subdirectorio bajo data/ donde vive el espejo local.
IMAGES_DIRNAME = "images"

# Cota de tamaño por portada. Una cover de manga rara vez pasa de 1-2 MB;
# 12 MB deja margen para escaneos grandes sin permitir descargas absurdas.
_MAX_IMAGE_BYTES = 12 * 1024 * 1024

# Tamaño de chunk al hacer streaming de la respuesta.
_CHUNK_BYTES = 64 * 1024


def image_stem(image_url: str) -> str:
    """Stem determinístico (16 hex) derivado del URL de la imagen."""
    digest = hashlib.sha256(image_url.strip().encode("utf-8")).hexdigest()
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
