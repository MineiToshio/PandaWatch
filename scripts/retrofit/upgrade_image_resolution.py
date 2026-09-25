#!/usr/bin/env python3
"""upgrade_image_resolution.py — re-fetch cover images in higher resolution.

Para cada item en items.jsonl, detecta si image_url o alguna URL en images[]
tiene parámetros o sufijos de redimensionado propios de CDNs de retailers
y prueba descargar la versión sin redimensionar.  Si la nueva imagen es
claramente más grande (más píxeles), reemplaza el archivo local y la URL.

Patrones soportados:
  • Magento CDN (Panini IT, etc.):
      image.jpg?quality=80&bg-color=...&height=222&width=222&canvas=222:222
      → image.jpg

  • WordPress / WooCommerce (Mangavariant, MangaLine, JBC BR, etc.):
      image-300x300.jpg  →  image.jpg
      image-150x228.jpg  →  image.jpg

  • Shopify (BlogBBM y similares):
      image_520x520.jpg  →  image.jpg
      image_540x.jpg     →  image.jpg

  • Amazon CDN embedded size modifiers (sumikko, booksprivilege):
      91XYZ._SY300_.jpg  →  91XYZ.jpg
      91XYZ._SL165_.jpg  →  91XYZ.jpg

  • Rakuten Books CDN (thumbnail.image.rakuten.co.jp):
      ...cabinet/9312/2100014729312.jpg?_ex=200x200  →  (sin ?_ex=)
      Mejora típica: 164×200 → 988×1200 (×36 más píxeles)

  • Buscalibre CDN (images.cdn{N}.buscalibre.com):
      .../fit-in/<W>x<H>/...  →  fit-in/1200x1200/ (NO se quita el segmento
      entero — gotcha #167, 2026-09-01: quitarlo del todo devuelve un tamaño
      "base" intermedio del CDN, bastante menor que pedir 1200x1200 explícito;
      verificado en vivo: fit-in/360x360→92 160px, sin fit-in→207 360px,
      fit-in/1200x1200→1 023 600px). No re-capa si el fit-in pedido ya es
      ≥1200 en ambas dimensiones.

  • Cultura CDN (cdn.cultura.com):
      .../cdn-cgi/image/width=<N>/...  →  quitar segmento cdn-cgi/image/...
      Mejora típica: hasta 2× (verificado empíricamente 2026-06-11)

  • Whakoom CDN (i1.whakoom.com):
      .../small/... o .../thumb/... o .../medium/...  →  .../large/...
      Mejora típica: 3× (verificado empíricamente 2026-06-11)

  • Magento cache path (bdfugue y similares):
      /media/catalog/product/cache/<hex>/...  →  quitar segmento cache/<hex>/
      ⚠️  ~20% devuelve imagen distinta → se valida con _same_cover antes
      de aceptar.

  • Aladin CDN (image.aladin.co.kr, KR - fuente Corea del Sur):
      .../cover150/<archivo>  →  .../cover500/<archivo>
      .../cover200/<archivo>  →  .../cover500/<archivo>
      Mismo archivo, carpeta de tamaño mayor en la misma ruta (NO es una
      candidata externa — gotcha #177). Verificado con requests reales
      (2026-09-02): `cover800`/`cover1000`/`cover1200` dan 404 (cover500 es
      el techo real del CDN); `coversum` y `letslook` son variantes MÁS
      chicas o de archivo DISTINTO, no se usan como target. La ganancia
      varía por producto — algunos ya estaban al tope real bajo cover150/200
      (mismas dimensiones, el min-gain los descarta sin aplicar), otros
      suben hasta 6× los píxeles.

  • Rakuten Books CDN familia r10s.jp (tshop.r10s.jp, shop.r10s.jp — distinto
    del host thumbnail.image.rakuten.co.jp de arriba, misma tienda):
      ...cabinet/4771/9784040764771_1_15.jpg?downsize=130:*  →  (sin query)
      ...cabinet/3733/9784758023733_1_3.jpg?fitin=560:400&composite-to=...
        →  (sin query)
      Quita la query ENTERA, no un downsize=N más grande (gotcha #180).
      Verificado con requests reales (2026-09-02): downsize=130:* → 130×184;
      downsize=1000:* → 844×1200 (igual a la nativa, no upscala); sin query
      (sigue el 302 tshop→shop) → 844×1200 (misma imagen); downsize=9999:* →
      HTTP 400 (el param SÍ tiene techo, pero no hace falta buscarlo — quitar
      la query entera da la nativa directo). Excluye `.gif` (tarjeta de
      título placeholder generada por Rakuten cuando no tiene la portada
      real, gotcha #171/#176) vía `image_store.known_placeholder_url_reason()`.

La comparación usa dimensiones de imagen (Pillow si está instalado, o
tamaño de archivo como proxy) para evitar reemplazar con imágenes iguales
o peores (algunos CDNs sirven la misma thumbnail con y sin parámetros).

El script es IDEMPOTENTE: una URL ya actualizada (sin sufijo/params) no
se vuelve a procesar.  Los archivos locales originales se vuelven orphans
y pueden limpiarse con `mirror_images.py --gc` en el próximo run.

Uso:
    python scripts/retrofit/upgrade_image_resolution.py             # todo
    python scripts/retrofit/upgrade_image_resolution.py --dry-run   # solo reporta
    python scripts/retrofit/upgrade_image_resolution.py --workers 8
    python scripts/retrofit/upgrade_image_resolution.py --limit 200 # prueba rápida
    python scripts/retrofit/upgrade_image_resolution.py --min-gain 0.5  # >50% más pix
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qsl, urlparse, urlencode

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import image_store  # type: ignore
try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    from manga_watch import (  # type: ignore  # noqa: E402
        _img_stem, backup_and_rotate, make_session, is_approved, write_lines_atomic,
    )
except ImportError:  # pragma: no cover
    from scripts.manga_watch import (  # type: ignore  # noqa: E402
        _img_stem, backup_and_rotate, make_session, is_approved, write_lines_atomic,
    )

DEFAULT_USER_AGENT = "manga-watch-personal/0.2 (+personal-use)"

# ─────────────────────────────────────────────────────────
# Patrones de URL redimensionada
# ─────────────────────────────────────────────────────────

# Params de Magento / imagen CDN genérica que solo controlan tamaño/calidad.
# Strippear estos devuelve la imagen original almacenada.
_MAGENTO_RESIZE_PARAMS = frozenset({
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

# WordPress genera sufijos -NxM (con guion) antes de la extensión.
# Shopify genera sufijos _Nx o _NxN (con guion bajo) antes de la extensión.
_WP_SUFFIX_RE = re.compile(
    r"^(.+?)-(\d{2,4}x\d{2,4})(\.\w{2,5})$",
    re.IGNORECASE,
)
_SHOPIFY_SUFFIX_RE = re.compile(
    r"^(.+?)_(\d{2,4}x\d*|x\d{2,4})(\.\w{2,5})$",
    re.IGNORECASE,
)
# Amazon CDN size modifiers embedded in path: ._SY300_. ._SL165_. ._SS120_. etc.
_AMAZON_HOSTS = frozenset({
    "m.media-amazon.com", "images-amazon.com",
    "images-fe.ssl-images-amazon.com", "images-na.ssl-images-amazon.com",
})
_AMAZON_SIZE_RE = re.compile(r"(\._[A-Z]{2}\d*_)+", re.IGNORECASE)
# Rakuten Books CDN: ?_ex=NxN thumbnail resize param
_RAKUTEN_THUMB_HOSTS = frozenset({"thumbnail.image.rakuten.co.jp"})
_RAKUTEN_EX_RE = re.compile(r"^\d+x\d+$")

# Buscalibre CDN: images.cdnN.buscalibre.com con segmento fit-in/<W>x<H>/
# Ejemplo: https://images.cdn1.buscalibre.com/fit-in/360x360/...imagen...
# → https://images.cdn1.buscalibre.com/fit-in/1200x1200/...imagen...
# (gotcha #167, 2026-09-01: reescribir a un fit-in explícito grande, NO quitar
# el segmento — quitarlo del todo NO da la imagen en máxima resolución, ver
# docstring del módulo).
_BUSCALIBRE_HOSTS_RE = re.compile(r"^images\.cdn\d+\.buscalibre\.com$", re.IGNORECASE)
_BUSCALIBRE_FIT_RE = re.compile(r"/fit-in/(\d+)x(\d+)(/|$)")
_BUSCALIBRE_MAX_FIT = 1200


def _buscalibre_fit_replacement(m: "re.Match[str]") -> str:
    """Reescribe fit-in/<W>x<H>/ a fit-in/1200x1200/, preservando el separador
    que cerraba el match (`/` o fin de string). No re-capa si el fit-in pedido
    ya es ≥1200 en ambas dimensiones (evita empeorar una URL ya en alta res)."""
    w, h = int(m.group(1)), int(m.group(2))
    if w >= _BUSCALIBRE_MAX_FIT and h >= _BUSCALIBRE_MAX_FIT:
        return m.group(0)
    return f"/fit-in/{_BUSCALIBRE_MAX_FIT}x{_BUSCALIBRE_MAX_FIT}{m.group(3)}"

# Cultura CDN: cdn.cultura.com con segmento cdn-cgi/image/width=N/ (Cloudflare Polish).
# Ejemplo: https://cdn.cultura.com/cdn-cgi/image/width=300/...imagen...
# → https://cdn.cultura.com/...imagen...
_CULTURA_HOST = "cdn.cultura.com"
_CULTURA_CDNCGI_RE = re.compile(r"/cdn-cgi/image/[^/]+/")

# Whakoom CDN: i1.whakoom.com con segmentos small/thumb/medium → large
# Ejemplo: https://i1.whakoom.com/small/...  → https://i1.whakoom.com/large/...
_WHAKOOM_HOST = "i1.whakoom.com"
_WHAKOOM_SIZE_RE = re.compile(r"/(small|thumb|medium)/", re.IGNORECASE)

# Magento cache path: /media/catalog/product/cache/<hex>/...
# Ejemplo: .../media/catalog/product/cache/abc123def456/i/m/imagen.jpg
# → .../media/catalog/product/imagen.jpg
# ⚠️  ~20% de CDNs Magento sirven imagen distinta sin el cache path.
# Requiere validación same_cover antes de aceptar.
_MAGENTO_CACHE_RE = re.compile(r"/media/catalog/product/cache/[^/]+/")

# Aladin CDN (KR): image.aladin.co.kr/product/<id>/<sub>/cover<N>/<archivo>
# Mismo archivo, carpeta de tamaño mayor en la misma ruta — no una candidata
# externa (gotcha #177). Verificado en vivo (2026-09-02): cover500 es el
# techo real (cover800/1000/1200 → 404); no re-capa si ya es >= 500.
_ALADIN_HOST = "image.aladin.co.kr"
_ALADIN_COVER_RE = re.compile(r"/cover(\d{2,4})/")
_ALADIN_MAX_COVER = 500

# Rakuten Books CDN (familia r10s.jp, distinta del host thumbnail.image.rakuten.co.jp
# del patrón #5): tshop.r10s.jp / shop.r10s.jp sirven la MISMA imagen con params de
# resize propios de su CDN — `?downsize=<N>:*` (el más común, ~177 items) y
# `?fitin=<W>:<H>&composite-to=...`. Verificado con requests reales (2026-09-02):
#   downsize=130:*  → 130×184   (thumbnail de card)
#   downsize=1000:* → 844×1200  (igual a la nativa, no upscala)
#   sin query (sigue el 302 tshop→shop) → 844×1200  (misma nativa)
#   downsize=9999:* → HTTP 400 (el param SÍ tiene techo, pero no hace falta
#     buscarlo: quitar la query entera da directo la nativa sin ese riesgo)
# → la reescritura es quitar la query COMPLETA (no sólo el param), igual que el
# patrón #5 de thumbnail.image.rakuten.co.jp — mismo mecanismo, host CDN distinto
# de la misma tienda. `requests`/`image_store.download_image` siguen el 302
# automáticamente (allow_redirects por defecto), así que no hace falta resolverlo
# a mano. Excluye `.gif` (tarjeta de título generada sin portada real, gotcha
# #171/#176) vía `image_store.known_placeholder_url_reason()` — no tiene sentido
# "mejorar la resolución" de un placeholder.
_RAKUTEN_R10S_HOSTS = frozenset({"tshop.r10s.jp", "shop.r10s.jp"})
_RAKUTEN_RESIZE_PARAMS = frozenset({"downsize", "fitin", "composite-to"})


def derive_original_url(url: str) -> str | None:
    """Devuelve la URL sin parámetros de redimensionado, o None si no aplica.

    Para el patrón Magento cache path (que puede devolver otra imagen ~20% de
    las veces), devuelve la URL limpia igual — el caller (_try_upgrade) es
    responsable de validar con same_cover cuando el resultado viene de ese patrón.
    Usa `needs_same_cover_validation(url)` para detectarlo.
    """
    if not url:
        return None

    parsed = urlparse(url)
    path = parsed.path

    # ── 1. Magento-style query params ──
    if parsed.query:
        qs_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        qs_keys = {k.lower() for k, _ in qs_pairs}
        # Solo strippeamos si hay al menos un param de dimensión explícita
        if qs_keys & {"width", "height", "w", "h"} and qs_keys & _MAGENTO_RESIZE_PARAMS:
            cleaned = parsed._replace(query=urlencode([(k, v) for k, v in qs_pairs if k.lower() not in _MAGENTO_RESIZE_PARAMS])).geturl()
            return cleaned if cleaned != url else None

    # ── 2. WordPress-style -NxM suffix ──
    filename = path.rsplit("/", 1)[-1]
    m = _WP_SUFFIX_RE.match(filename)
    if m:
        clean_filename = m.group(1) + m.group(3)
        clean_path = path[: path.rfind("/") + 1] + clean_filename
        cleaned = parsed._replace(path=clean_path).geturl()
        return cleaned if cleaned != url else None

    # ── 3. Shopify-style _Nx suffix ──
    m = _SHOPIFY_SUFFIX_RE.match(filename)
    if m:
        clean_filename = m.group(1) + m.group(3)
        clean_path = path[: path.rfind("/") + 1] + clean_filename
        cleaned = parsed._replace(path=clean_path).geturl()
        return cleaned if cleaned != url else None

    # ── 4. Amazon CDN embedded size modifiers (._SY300_. ._SL165_. etc.) ──
    if parsed.netloc in _AMAZON_HOSTS:
        if _AMAZON_SIZE_RE.search(path):
            clean_path = _AMAZON_SIZE_RE.sub("", path)
            cleaned = parsed._replace(path=clean_path).geturl()
            return cleaned if cleaned != url else None

    # ── 5. Rakuten Books CDN: ?_ex=NxN ──
    if parsed.netloc in _RAKUTEN_THUMB_HOSTS and parsed.query:
        qs = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if "_ex" in qs and _RAKUTEN_EX_RE.match(qs["_ex"]):
            cleaned = parsed._replace(query="").geturl()
            return cleaned if cleaned != url else None

    # ── 6. Buscalibre CDN: fit-in/<W>x<H>/ → fit-in/1200x1200/ (gotcha #167) ──
    if _BUSCALIBRE_HOSTS_RE.match(parsed.netloc):
        if _BUSCALIBRE_FIT_RE.search(path):
            clean_path = _BUSCALIBRE_FIT_RE.sub(_buscalibre_fit_replacement, path, count=1)
            cleaned = parsed._replace(path=clean_path).geturl()
            return cleaned if cleaned != url else None

    # ── 7. Cultura CDN: cdn-cgi/image/width=N/ segment (Cloudflare Polish) ──
    if parsed.netloc == _CULTURA_HOST:
        if _CULTURA_CDNCGI_RE.search(path):
            clean_path = _CULTURA_CDNCGI_RE.sub("/", path)
            cleaned = parsed._replace(path=clean_path).geturl()
            return cleaned if cleaned != url else None

    # ── 8. Whakoom CDN: small/thumb/medium → large ──
    if parsed.netloc == _WHAKOOM_HOST:
        if _WHAKOOM_SIZE_RE.search(path):
            clean_path = _WHAKOOM_SIZE_RE.sub("/large/", path)
            cleaned = parsed._replace(path=clean_path).geturl()
            return cleaned if cleaned != url else None

    # ── 9. Magento cache path: /media/catalog/product/cache/<hex>/ ──
    # ⚠️  Este patrón requiere validación same_cover (usa needs_same_cover_validation).
    if _MAGENTO_CACHE_RE.search(path):
        clean_path = _MAGENTO_CACHE_RE.sub("/media/catalog/product/", path)
        cleaned = parsed._replace(path=clean_path).geturl()
        return cleaned if cleaned != url else None

    # ── 10. Aladin CDN: cover<N>/ → cover500/ (gotcha #177) ──
    if parsed.netloc.lower() == _ALADIN_HOST:
        m = _ALADIN_COVER_RE.search(path)
        if m and int(m.group(1)) < _ALADIN_MAX_COVER:
            clean_path = _ALADIN_COVER_RE.sub(f"/cover{_ALADIN_MAX_COVER}/", path, count=1)
            cleaned = parsed._replace(path=clean_path).geturl()
            return cleaned if cleaned != url else None

    # ── 11. Rakuten Books CDN familia r10s.jp: downsize/fitin → sin query ──
    if parsed.netloc.lower() in _RAKUTEN_R10S_HOSTS and parsed.query:
        qs_keys = {k.lower() for k, _ in parse_qsl(parsed.query, keep_blank_values=True)}
        if qs_keys & _RAKUTEN_RESIZE_PARAMS:
            # Guard: nunca "mejorar" una tarjeta de título .gif (gotcha #171/#176) —
            # image_store es la fuente única para detectar placeholders conocidos.
            if not image_store.known_placeholder_url_reason(url):
                cleaned = parsed._replace(query="").geturl()
                return cleaned if cleaned != url else None

    return None


def needs_same_cover_validation(url: str) -> bool:
    """Devuelve True si la URL fue resuelta por el patrón Magento cache path.

    Este patrón requiere validación same_cover porque ~20% de CDNs Magento
    devuelven una imagen distinta al quitar el cache path (imagen distinta,
    no solo diferente resolución).
    """
    if not url:
        return False
    parsed = urlparse(url)
    return bool(_MAGENTO_CACHE_RE.search(parsed.path))


# ─────────────────────────────────────────────────────────
# Comparación de dimensiones de imagen
# ─────────────────────────────────────────────────────────

def _pixels(path: Path) -> int | None:
    """Devuelve el total de píxeles de la imagen en `path`, o None si falla.

    Delega en `fetch_better_covers._get_pixels_from_bytes` (hallazgo #1,
    2026-07-08, ALTA) en vez de reimplementar un 3er parser binario: éste era
    el ÚNICO de los tres (junto a `upscale_images.py`/`fetch_better_covers.py`)
    que no tenía rama AVIF ni fallback PIL. Como el espejo local está ~100%
    AVIF, el gate `--min-gain` terminaba comparando tamaño de ARCHIVO en vez
    de píxeles reales (mismo bug que gotchas #124/#132, ya cerrado en los
    otros dos scripts). Fallback final a `len(data)` (proxy de tamaño) si no
    se puede determinar — mismo comportamiento degradado que antes cuando
    ningún parser reconoce el formato.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    try:
        # Import tardío (mismo patrón que _try_upgrade abajo): fetch_better_covers
        # es un módulo de retrofit con dependencias opcionales (PIL/bs4).
        import fetch_better_covers as _fbc  # type: ignore  # noqa: PLC0415
        px = _fbc._get_pixels_from_bytes(data)
        if px:
            return px
    except ImportError:
        pass
    return None


# ─────────────────────────────────────────────────────────
# IO
# ─────────────────────────────────────────────────────────

def _load_items(src: Path) -> list[dict]:
    from image_snapshot import read_snapshot
    return read_snapshot(src)


def _write_items(dst: Path, items: list[dict]) -> None:
    from image_snapshot import write_snapshot
    write_snapshot(dst, items)


def _try_upgrade(
    old_url: str,
    old_local: str,
    images_dir: Path,
    session,
    timeout: tuple[int, int],
    min_gain: float,
    item_url: str = "",
) -> tuple[str, str] | None:
    """Intenta conseguir la versión de mayor resolución de `old_url`.

    Devuelve (new_url, new_local) si la nueva imagen es notablemente más
    grande que la actual, o None si no hay mejora o la descarga falla.

    item_url: URL canónica del item (se usa como Referer para evitar 403
    de CDNs con anti-hotlink). Si no se provee, se usa el old_url como fallback.
    """
    new_url = derive_original_url(old_url)
    if not new_url:
        return None  # URL ya era la original

    # Referer: los CDNs con anti-hotlink (buscalibre, cultura, whakoom)
    # devuelven 403 si el Referer está vacío. Usamos la URL del item como
    # Referer; si no la tenemos, usamos la URL origen de la imagen.
    referer = item_url or old_url

    # Descarga la versión sin redimensionar.
    # download_image() es idempotente: si ya tenemos ese archivo no re-descarga.
    new_local = image_store.download_image(
        new_url, images_dir, session=session, timeout=timeout, referer=referer
    )
    if not new_local:
        return None  # Error de red, anti-bot, o no es imagen válida

    # Every unattended transform must prove the same asset and retain logos,
    # typography, colours and borders. Missing reference is never permission.
    from cover_identity import automatic_upgrade
    new_path = images_dir / new_local
    old_path = images_dir / old_local if old_local else None
    if not old_path or not old_path.is_file():
        return None
    old_px, new_px = _pixels(old_path), _pixels(new_path)
    if not old_px or not new_px or new_px < old_px * (1 + min_gain):
        return None
    evidence = automatic_upgrade(old_url, new_url, old_path.read_bytes(), new_path.read_bytes())
    if not evidence['ok']:
        return None

    return new_url, new_local


# ─────────────────────────────────────────────────────────
# Proceso principal
# ─────────────────────────────────────────────────────────

def _collect_targets(
    items: list[dict], *, include_approved: bool = False, host: str = "",
) -> tuple[list[tuple[dict, str, str, str, str]], int]:
    """Construye la lista de (item, campo, old_url, old_local, item_url) a procesar.

    campo es 'img:<index>' para cada entry de images[]. images[0] es la portada
    (única fuente de verdad); el resto es galería.
    item_url es la URL canónica del item (se usa como Referer en la descarga).

    Items aprobados (`approved_at`) se saltean por defecto (segundo valor
    devuelto = cuántos): este script reemplaza url/local de una entry existente
    sin cola de revisión, así que no debe pisar un golden record.

    `host`: si se pasa (substring case-insensitive), acota los targets a URLs
    cuyo netloc lo contenga (ej. "aladin.co.kr" para correr acotado a una
    sola fuente/CDN sin tocar el resto de los patrones soportados).
    """
    targets: list[tuple[dict, str, str, str, str]] = []
    skipped_approved = 0
    host_lower = host.lower()
    for it in items:
        if "_raw" in it:
            continue
        if is_approved(it) and not include_approved:
            skipped_approved += 1
            continue
        # URL canónica del item para usar como Referer
        item_url = it.get("url") or ""
        # images[0] = portada, images[1:] = galería/extra.
        for idx, img in enumerate(it.get("images") or []):
            if not isinstance(img, dict):
                continue
            img_url = img.get("url") or ""
            if not img_url:
                continue
            if host_lower and host_lower not in urlparse(img_url).netloc.lower():
                continue
            if derive_original_url(img_url):
                targets.append((it, f"img:{idx}", img_url, img.get("local") or "", item_url))
    return targets, skipped_approved


def _apply_upgrade(
    item: dict,
    campo: str,
    new_url: str,
    new_local: str,
) -> None:
    """Actualiza in-place el dict del item con la nueva URL/local.

    campo es 'img:<index>'; el índice 0 es la portada (images[0]).
    """
    if campo.startswith("img:"):
        idx = int(campo.split(":")[1])
        imgs = item.get("images") or []
        if idx < len(imgs) and isinstance(imgs[idx], dict):
            imgs[idx]["url"] = new_url
            imgs[idx]["local"] = new_local


# ─────────────────────────────────────────────────────────
# Dedup post-upgrade de images[] (gotcha #181, 2026-09-02)
# ─────────────────────────────────────────────────────────
#
# Causa raíz confirmada con datos reales (backup `items.jsonl.pre-aladin-
# upgrade-bak`): un item podía tener, ANTES de este script, dos entries de
# `images[]` apuntando al MISMO archivo del CDN de Aladin en dos carpetas de
# tamaño distintas — ej. `cover500/k382030457_1.jpg` en `images[0]` (la
# portada, ya en alta resolución por un camino previo — JSON-LD/og:image) y
# `cover150/k382030457_1.jpg` en `images[3]` (capturado por el selector de
# galería, todavía sin `local`). Antes del upgrade las dos URLs eran
# textualmente DISTINTAS, así que ningún dedup existente las veía como
# duplicado. `_apply_upgrade` reescribe cada entry de forma independiente
# (una por `campo`/índice) sin mirar el resto de `images[]` del mismo item —
# al normalizar `cover150/` → `cover500/`, la entry de galería termina con la
# MISMA url/local que la portada, y el `images[]] queda con la imagen
# literalmente duplicada (109 items / 151 entries, 100% KR-Aladin).
#
# Fix: tras aplicar upgrades, dedupear `images[]` de cada item TOCADO por
# clave canónica — misma familia de criterios que `fetch_better_covers.
# _apply_improvement` (gotcha #164): `_img_stem(url)` (fuente única de
# manga_watch), con fallback a `local` idéntico, y un 3er fallback de
# contenido (sha256 de los bytes del archivo local) para el caso en que dos
# entries con stem/local distintos terminen siendo la MISMA imagen en disco.
# Conserva SIEMPRE el primer sobreviviente en orden de aparición (así
# `images[0]`, la portada, nunca se pierde ni se reordena) y traslada
# `kind`/`description` del duplicado eliminado al sobreviviente cuando éste
# no los tenía — mismo comportamiento sticky que `_apply_improvement`.


def _local_sha256(local: str, images_dir: Path) -> str | None:
    """sha256 del archivo `local` en `images_dir`, o None si no existe/legible."""
    if not local:
        return None
    p = images_dir / local
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def dedupe_item_images(item: dict, images_dir: Path) -> bool:
    """Dedupea `images[]` de UN item por clave canónica. Devuelve True si cambió.

    Clave de "misma foto" = cualquiera de:
      (a) `_img_stem(url)` idéntico (misma normalización que el resto del
          pipeline: strip de query irrelevante + sufijos de thumb conocidos),
      (b) `local` idéntico (mismo archivo del espejo),
      (c) sha256 de los bytes del archivo `local` idéntico (mismo contenido,
          aunque stem/local difieran — ej. dos hosts distintos sirviendo la
          misma imagen).
    Conserva el PRIMER sobreviviente en orden de aparición (nunca reordena ni
    vacía `images[]`); el duplicado eliminado dona `kind`/`description` al
    sobreviviente cuando éste no los tenía (sticky, igual que
    `_union_merge_images`/`_apply_improvement`). El sha256 sólo se calcula
    cuando stem/local no alcanzan para decidir, con cache por-`local` dentro
    de la llamada (barato: son unos pocos KB por imagen del espejo AVIF).
    """
    images = item.get("images")
    if not isinstance(images, list) or len(images) < 2:
        return False

    sha_cache: dict[str, str | None] = {}

    def _sha_of(local: str) -> str | None:
        if not local:
            return None
        if local not in sha_cache:
            sha_cache[local] = _local_sha256(local, images_dir)
        return sha_cache[local]

    kept: list[dict] = []
    kept_stems: list[str] = []
    kept_locals: list[str] = []
    kept_shas: list[str | None] = []
    changed = False

    for im in images:
        if not isinstance(im, dict):
            kept.append(im)
            kept_stems.append("")
            kept_locals.append("")
            kept_shas.append(None)
            continue

        stem = _img_stem(im.get("url", ""))
        local = im.get("local") or ""
        sha = None

        dup_idx = None
        for i in range(len(kept)):
            if stem and kept_stems[i] == stem:
                dup_idx = i
                break
            if local and kept_locals[i] == local:
                dup_idx = i
                break
            # sha256 sólo se calcula si stem/local no decidieron (evita I/O
            # innecesario en el camino feliz sin duplicados).
            if sha is None:
                sha = _sha_of(local)
            if sha and kept_shas[i] is None:
                kept_shas[i] = _sha_of(kept_locals[i])
            if sha and kept_shas[i] and sha == kept_shas[i]:
                dup_idx = i
                break

        if dup_idx is None:
            kept.append(im)
            kept_stems.append(stem)
            kept_locals.append(local)
            kept_shas.append(sha)
            continue

        # Duplicado: dona kind/description al sobreviviente (sticky) y descarta.
        survivor = kept[dup_idx]
        for f in ("kind", "description"):
            if not survivor.get(f) and im.get(f):
                survivor[f] = im[f]
        changed = True

    if changed:
        item["images"] = kept
    return changed


def run(
    items_path: Path,
    images_dir: Path,
    *,
    workers: int,
    timeout: tuple[int, int],
    limit: int,
    min_gain: float,
    dry_run: bool,
    user_agent: str,
    include_approved: bool = False,
    host: str = "",
) -> None:
    items = _load_items(items_path)
    targets, skipped_approved = _collect_targets(
        items, include_approved=include_approved, host=host,
    )
    if limit > 0:
        targets = targets[:limit]

    total = len(targets)
    print(f"Targets a procesar: {total} URLs candidatas a upgrade")
    if skipped_approved:
        print(f"Items aprobados saltados (usar --include-approved): {skipped_approved}")
    if dry_run:
        print("[DRY-RUN] No se harán cambios en disco.")
        # Muestra algunos ejemplos
        for it, campo, old_url, _, _item_url in targets[:10]:
            new_url = derive_original_url(old_url)
            print(f"  {campo:12s}  {old_url[:70]}")
            print(f"          →   {new_url[:70]}")
        if total > 10:
            print(f"  ... y {total - 10} más.")
        return

    backup_and_rotate(items_path, "upgrade-resolution")

    session = make_session(user_agent=user_agent)
    counter: Counter = Counter()

    # Dedup: si el mismo URL aparece en varios items, procesamos 1 vez y
    # aplicamos el resultado a todos.
    # Construimos una lista de (item, campo, old_url, old_local) con dedup por URL.
    # item_url se guarda para pasarlo como Referer en la descarga.
    unique_by_url: dict[str, list[tuple[dict, str, str]]] = {}
    url_to_item_url: dict[str, str] = {}
    for item, campo, old_url, old_local, item_url in targets:
        unique_by_url.setdefault(old_url, []).append((item, campo, old_local))
        if old_url not in url_to_item_url:
            url_to_item_url[old_url] = item_url

    unique_targets = [(old_url, entries[0][2]) for old_url, entries in unique_by_url.items()]
    print(f"URLs únicas a intentar: {len(unique_targets)}")

    completed = 0
    _FLUSH_EVERY = 50  # flush items.jsonl cada N mejoras (no pérdida si se cancela)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _try_upgrade, old_url, old_local, images_dir, session, timeout, min_gain,
                url_to_item_url.get(old_url, ""),
            ): old_url
            for old_url, old_local in unique_targets
        }
        for future in as_completed(futures):
            old_url = futures[future]
            completed += 1
            if completed % 100 == 0:
                print(f"  {completed}/{len(unique_targets)} procesadas...", flush=True)
            try:
                result = future.result()
                if result is not None:
                    # Aplica y guarda inmediatamente los items con esta URL
                    new_url, new_local = result
                    for item, campo, _ in unique_by_url[old_url]:
                        _apply_upgrade(item, campo, new_url, new_local)
                        # Dedup post-upgrade (gotcha #181): la entry recién
                        # reescrita puede haber colapsado con OTRA entry del
                        # mismo item que ya apuntaba a la misma foto bajo una
                        # URL distinta antes del upgrade (ver docstring de
                        # dedupe_item_images). Se corre por-item, apenas se
                        # toca ese item, para que ningún flush parcial
                        # persista un duplicado a mitad de camino.
                        if dedupe_item_images(item, images_dir):
                            counter["deduped"] += 1
                    counter["upgraded"] += 1
                    # Flush periódico: protege contra cancels mid-run
                    if not dry_run and counter["upgraded"] % _FLUSH_EVERY == 0:
                        _write_items(items_path, items)
                        print(f"  → flush parcial ({counter['upgraded']} mejoradas)", flush=True)
                else:
                    counter["no_gain"] += 1
            except Exception as exc:
                # Hallazgo #13 (2026-07-08): antes se tragaba sin log — una corrida
                # con muchos errores terminaba en "Errores: 40" sin ninguna pista.
                print(f"  ⚠ WARN [{old_url[:70]}]: {type(exc).__name__}: {exc}", flush=True)
                counter["no_gain"] += 1
                counter["errors"] += 1

    # Flush final con todas las mejoras (incluye las del último bloque < FLUSH_EVERY)
    if not dry_run:
        _write_items(items_path, items)

    print(
        f"\n✓ Resultado:"
        f"\n  Mejoradas:     {counter['upgraded']:>5}"
        f"\n  Sin mejora:    {counter['no_gain']:>5}  (misma resolución o descarga fallida)"
        f"\n  Errores:       {counter['errors']:>5}"
        f"\n  Items dedupeados post-upgrade: {counter['deduped']:>5}  (images[] con foto duplicada, gotcha #181)"
    )


# ─────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Re-fetch cover images in higher resolution (strip CDN resize params/suffixes)."
    )
    p.add_argument("--items", default="data/items.jsonl", help="Path a items.jsonl")
    p.add_argument("--images-dir", default="data/images", help="Directorio de imágenes locales")
    p.add_argument("--dry-run", action="store_true", help="Solo reporta, no escribe nada")
    p.add_argument("--workers", type=int, default=4, help="Hilos paralelos de descarga")
    p.add_argument("--timeout", type=int, default=20, help="Timeout HTTP en segundos")
    p.add_argument(
        "--min-gain",
        type=float,
        default=0.1,
        help="Fracción mínima de mejora en píxeles para aceptar la nueva imagen (default 0.10 = 10%%)",
    )
    p.add_argument("--limit", type=int, default=0, help="Limitar a los primeros N targets (test)")
    p.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="User-Agent HTTP")
    p.add_argument("--include-approved", action="store_true",
                    help="También sube la resolución de items aprobados (golden records). "
                         "Por defecto se saltean: este script reemplaza url/local de una "
                         "entry existente sin cola de revisión.")
    p.add_argument("--host", default="",
                    help="Acota a URLs cuyo netloc contenga este substring "
                         "(ej. --host aladin.co.kr). Vacío = todos los patrones/hosts.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    root = Path(__file__).resolve().parent.parent.parent
    run(
        items_path=root / args.items,
        images_dir=root / args.images_dir,
        workers=args.workers,
        timeout=(10, args.timeout),
        limit=args.limit,
        min_gain=args.min_gain,
        dry_run=args.dry_run,
        user_agent=args.user_agent,
        include_approved=args.include_approved,
        host=args.host,
    )
