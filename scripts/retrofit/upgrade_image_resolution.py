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
      .../fit-in/<W>x<H>/...  →  quitar segmento fit-in/<W>x<H>
      Mejora típica: 2×-22× más píxeles (verificado empíricamente 2026-06-11)

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
import json
import re
import struct
import sys
import zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import image_store  # type: ignore
try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    from manga_watch import backup_and_rotate, make_session, is_approved  # type: ignore  # noqa: E402
except ImportError:  # pragma: no cover
    from scripts.manga_watch import backup_and_rotate, make_session, is_approved  # type: ignore  # noqa: E402

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
# → https://images.cdn1.buscalibre.com/...imagen...
_BUSCALIBRE_HOSTS_RE = re.compile(r"^images\.cdn\d+\.buscalibre\.com$", re.IGNORECASE)
_BUSCALIBRE_FIT_RE = re.compile(r"/fit-in/\d+x\d+(?:/|$)")

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
# Marcador para que _try_upgrade sepa que este patrón requiere same_cover
NEEDS_SAME_COVER_VALIDATION = "__needs_same_cover__"


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
            cleaned = parsed._replace(query="").geturl()
            return cleaned if cleaned != url else None

    # ── 2. WordPress-style -NxM suffix ──
    filename = path.rsplit("/", 1)[-1]
    m = _WP_SUFFIX_RE.match(filename)
    if m:
        clean_filename = m.group(1) + m.group(3)
        clean_path = path[: path.rfind("/") + 1] + clean_filename
        cleaned = parsed._replace(path=clean_path, query="").geturl()
        return cleaned if cleaned != url else None

    # ── 3. Shopify-style _Nx suffix ──
    m = _SHOPIFY_SUFFIX_RE.match(filename)
    if m:
        clean_filename = m.group(1) + m.group(3)
        clean_path = path[: path.rfind("/") + 1] + clean_filename
        cleaned = parsed._replace(path=clean_path, query="").geturl()
        return cleaned if cleaned != url else None

    # ── 4. Amazon CDN embedded size modifiers (._SY300_. ._SL165_. etc.) ──
    if parsed.netloc in _AMAZON_HOSTS:
        if _AMAZON_SIZE_RE.search(path):
            clean_path = _AMAZON_SIZE_RE.sub("", path)
            cleaned = parsed._replace(path=clean_path, query="").geturl()
            return cleaned if cleaned != url else None

    # ── 5. Rakuten Books CDN: ?_ex=NxN ──
    if parsed.netloc in _RAKUTEN_THUMB_HOSTS and parsed.query:
        qs = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if "_ex" in qs and _RAKUTEN_EX_RE.match(qs["_ex"]):
            cleaned = parsed._replace(query="").geturl()
            return cleaned if cleaned != url else None

    # ── 6. Buscalibre CDN: fit-in/<W>x<H>/ segment ──
    if _BUSCALIBRE_HOSTS_RE.match(parsed.netloc):
        if _BUSCALIBRE_FIT_RE.search(path):
            clean_path = _BUSCALIBRE_FIT_RE.sub("/", path)
            cleaned = parsed._replace(path=clean_path, query="").geturl()
            return cleaned if cleaned != url else None

    # ── 7. Cultura CDN: cdn-cgi/image/width=N/ segment (Cloudflare Polish) ──
    if parsed.netloc == _CULTURA_HOST:
        if _CULTURA_CDNCGI_RE.search(path):
            clean_path = _CULTURA_CDNCGI_RE.sub("/", path)
            cleaned = parsed._replace(path=clean_path, query="").geturl()
            return cleaned if cleaned != url else None

    # ── 8. Whakoom CDN: small/thumb/medium → large ──
    if parsed.netloc == _WHAKOOM_HOST:
        if _WHAKOOM_SIZE_RE.search(path):
            clean_path = _WHAKOOM_SIZE_RE.sub("/large/", path)
            cleaned = parsed._replace(path=clean_path, query="").geturl()
            return cleaned if cleaned != url else None

    # ── 9. Magento cache path: /media/catalog/product/cache/<hex>/ ──
    # ⚠️  Este patrón requiere validación same_cover (usa needs_same_cover_validation).
    if _MAGENTO_CACHE_RE.search(path):
        clean_path = _MAGENTO_CACHE_RE.sub("/media/catalog/product/", path)
        cleaned = parsed._replace(path=clean_path, query="").geturl()
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

def _image_dimensions_from_bytes(data: bytes) -> tuple[int, int] | None:
    """Extrae (width, height) de los primeros bytes de una imagen.

    Soporta JPEG, PNG, GIF, WebP, AVIF.  Devuelve None si no puede leer.
    No requiere dependencias externas — usa struct puro.
    """
    if len(data) < 24:
        return None

    # PNG: magic b'\x89PNG', ancho/alto en bytes 16-24 (big-endian uint32)
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            w, h = struct.unpack(">II", data[16:24])
            return w, h
        except struct.error:
            return None

    # GIF: magic GIF87a/GIF89a, ancho/alto en bytes 6-10 (little-endian uint16)
    if data[:6] in (b"GIF87a", b"GIF89a"):
        try:
            w, h = struct.unpack("<HH", data[6:10])
            return w, h
        except struct.error:
            return None

    # WebP: bytes 0-3 RIFF, 8-12 WEBP, ancho/alto en el chunk VP8/VP8L
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        # VP8 lossy: ancho/alto en bytes 26-30
        if data[12:16] == b"VP8 " and len(data) >= 30:
            try:
                w = (struct.unpack_from("<H", data, 26)[0] & 0x3FFF) + 1
                h = (struct.unpack_from("<H", data, 28)[0] & 0x3FFF) + 1
                return w, h
            except struct.error:
                pass
        # VP8L lossless: bits comprimidos, skip
        return None

    # JPEG: busca el marcador SOF (Start of Frame) — 0xFF 0xC0..0xC3
    if data[:3] == b"\xff\xd8\xff":
        i = 2
        while i + 4 < len(data):
            if data[i] != 0xFF:
                break
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                if i + 9 < len(data):
                    h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                    return w, h
                break
            # Saltamos al siguiente marcador
            if i + 4 > len(data):
                break
            length = struct.unpack(">H", data[i + 2 : i + 4])[0]
            i += 2 + length
        return None

    return None


def _pixels(path: Path) -> int | None:
    """Devuelve el total de píxeles de la imagen en `path`, o None si falla."""
    try:
        data = path.read_bytes()
        dims = _image_dimensions_from_bytes(data)
        if dims:
            return dims[0] * dims[1]
        # Fallback: size en bytes como proxy
        return len(data)
    except OSError:
        return None


# ─────────────────────────────────────────────────────────
# IO
# ─────────────────────────────────────────────────────────

def _load_items(src: Path) -> list[dict]:
    items: list[dict] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                items.append({"_raw": line})
    return items


def _write_items(dst: Path, items: list[dict]) -> None:
    lines = []
    for it in items:
        if "_raw" in it:
            lines.append(it["_raw"])
        else:
            lines.append(json.dumps(it, ensure_ascii=False, sort_keys=True))
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─────────────────────────────────────────────────────────
# Lógica de upgrade
# ─────────────────────────────────────────────────────────

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

    # Comparamos tamaño de imagen: nuevo vs viejo (si existe el local).
    new_path = images_dir / new_local
    old_path = images_dir / old_local if old_local else None

    if old_path and old_path.exists():
        old_px = _pixels(old_path)
        new_px = _pixels(new_path)
        if old_px and new_px:
            # Solo aceptamos si la nueva imagen es al menos (1 + min_gain) veces
            # más grande en píxeles (evita reemplazar por la misma imagen).
            if new_px < old_px * (1 + min_gain):
                # Nueva no es suficientemente mejor — descartamos.
                # El archivo descargado (new_local) queda en disco; se limpiará
                # con mirror_images.py --gc en el próximo run si no lo usa nadie.
                return None

        # ── Validación same_cover para Magento cache path ──
        # ~20% de los CDNs Magento devuelven una imagen distinta al quitar el
        # cache path (ej. bdfugue sirve la imagen de otro producto). Solo
        # rechazamos si hay old_path local para comparar.
        if needs_same_cover_validation(old_url):
            try:
                # Importación tardía: fetch_better_covers es un módulo de retrofit
                # que tiene PIL como dependencia opcional. Si no está disponible,
                # permitimos la imagen igualmente (la ganancia de píxeles ya es
                # un indicador razonable; el GC + dedup_carousel limpiarán errores).
                import fetch_better_covers as _fbc  # type: ignore  # noqa: PLC0415
                old_bytes = old_path.read_bytes() if old_path.exists() else b""
                new_bytes = new_path.read_bytes()
                if old_bytes and not _fbc._same_cover(old_bytes, new_bytes):
                    return None
            except (ImportError, Exception):
                pass  # Sin PIL o error: permitir; la comparación de píxeles es suficiente

    return new_url, new_local


# ─────────────────────────────────────────────────────────
# Proceso principal
# ─────────────────────────────────────────────────────────

def _collect_targets(
    items: list[dict], *, include_approved: bool = False,
) -> tuple[list[tuple[dict, str, str, str, str]], int]:
    """Construye la lista de (item, campo, old_url, old_local, item_url) a procesar.

    campo es 'img:<index>' para cada entry de images[]. images[0] es la portada
    (única fuente de verdad); el resto es galería.
    item_url es la URL canónica del item (se usa como Referer en la descarga).

    Items aprobados (`approved_at`) se saltean por defecto (segundo valor
    devuelto = cuántos): este script reemplaza url/local de una entry existente
    sin cola de revisión, así que no debe pisar un golden record.
    """
    targets: list[tuple[dict, str, str, str, str]] = []
    skipped_approved = 0
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
            if img_url and derive_original_url(img_url):
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
) -> None:
    items = _load_items(items_path)
    targets, skipped_approved = _collect_targets(items, include_approved=include_approved)
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
    url_to_result: dict[str, tuple[str, str] | None] = {}

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
                url_to_result[old_url] = result
                if result is not None:
                    # Aplica y guarda inmediatamente los items con esta URL
                    new_url, new_local = result
                    for item, campo, _ in unique_by_url[old_url]:
                        _apply_upgrade(item, campo, new_url, new_local)
                    counter["upgraded"] += 1
                    # Flush periódico: protege contra cancels mid-run
                    if not dry_run and counter["upgraded"] % _FLUSH_EVERY == 0:
                        _write_items(items_path, items)
                        print(f"  → flush parcial ({counter['upgraded']} mejoradas)", flush=True)
                else:
                    counter["no_gain"] += 1
            except Exception as exc:
                url_to_result[old_url] = None
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
    )
