#!/usr/bin/env python3
"""purge_placeholder_images.py — quita de `images[]` las fotos que NO son
portadas reales: placeholders ("no disponible" / "coming soon"), pixeles 1×1
y archivos rotos, para que la UI caiga al placeholder 📚 por defecto.

Algunas fuentes sirven una imagen genérica cuando no tienen la carátula:
Amazon devuelve un GIF 1×1 para ISBN sin foto; listadomanga/otros CDNs sirven
un blanco; Penguin Random House un "Cover Coming Soon"; Funside un "Immagine
non disponibile"; SocialAnime un "Image coming soon". Todas terminan espejadas
en `data/images/` y mostradas como si fueran la portada. Este retrofit las
detecta y las quita de TODAS las filas del catálogo.

La detección vive en `image_store.placeholder_reason()` (fuente ÚNICA, también
usada por el pipeline): estructural (1×1, casi-sólido std<3, roto) + firmas de
contenido (data/placeholder_signatures.json) para los placeholders con texto.

Comportamiento:
  - Quita cada entry de `images[]` cuyo `local` sea placeholder/roto.
  - Limpia `sources[].image_local`/`image_url` que apunten al mismo archivo o
    URL placeholder (para que un re-merge no los re-siembre).
  - Re-marca la portada por posición (la primera foto que queda pasa a `images[0]`).
  - GC: los archivos que quedan huérfanos se mueven a cuarentena
    `data/images/_orphans/` (reversible) salvo `--keep-files`.
  - NUNCA inventa imágenes; un item que se queda sin fotos mostrará el 📚.

Uso:
  .venv/bin/python scripts/retrofit/purge_placeholder_images.py --dry-run
  .venv/bin/python scripts/retrofit/purge_placeholder_images.py
  .venv/bin/python scripts/retrofit/purge_placeholder_images.py --keep-files
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import image_store  # noqa: E402  (fuente única de placeholder_reason + placeholders conocidos)
try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    from manga_watch import (  # noqa: E402
        backup_and_rotate, is_approved, write_items_atomic,
    )
except ImportError:  # pragma: no cover
    from scripts.manga_watch import (  # noqa: E402
        backup_and_rotate, is_approved, write_items_atomic,
    )

ITEMS = ROOT / "data" / "items.jsonl"
IMAGES = ROOT / "data" / "images"
ORPHANS = IMAGES / "_orphans"
COVER_PREVIEW = ROOT / "data" / "cover_preview.json"

# Archivos por encima de este tamaño no se evalúan: un placeholder (1×1, blanco,
# o los registrados) pesa unos pocos KB; una portada real de >200KB jamás es
# casi-sólida ni matchea una firma. Evita leer/decodificar 14GB de portadas.
_EVAL_MAX_BYTES = 200_000

# Regla genérica (b): si la MISMA URL de imagen aparece como foto en items de al
# menos este número de series DISTINTAS, no puede pertenecer a ninguna → es un
# placeholder / imagen genérica compartida ("STOLENIMG"). Se agrupa por SERIE (no
# por item) para NO castigar el caso legítimo de un box y sus tomos de la misma
# serie/colección compartiendo una foto.
_CROSS_SERIES_MIN = 4

# Sufijo de volumen al final de un título ("… 5", "… nº5", "… #5") — se quita para
# derivar una clave de serie estable cuando el item no trae series_display.
_VOL_TAIL_RE = re.compile(r"[\s\-–—:]*\b(?:n[º°.]?|#|vol\.?)?\s*\d+\s*$", re.IGNORECASE)


def series_key(item: dict) -> str:
    """Clave de agrupación por SERIE (no por edición ni item). Preferimos el
    nombre de serie explícito; si falta, caemos al título sin el sufijo de
    volumen (para que vol 1/2/… de la misma serie agrupen). Cross-source-safe:
    dos ediciones de la misma serie comparten esta clave."""
    for f in ("series_display", "series_canonical"):
        v = (item.get(f) or "").strip()
        if v:
            return "s:" + v.lower()
    t = (item.get("title") or "").strip().lower()
    t = _VOL_TAIL_RE.sub("", t).strip()
    return "t:" + (t or (item.get("slug") or ""))


def _iter_item_image_urls(item: dict):
    """URLs (no vacías) de las fotos de un item, con su kind."""
    for im in (item.get("images") or []):
        if isinstance(im, dict):
            url = (im.get("url") or "").strip()
            if url:
                yield url, (im.get("kind") or "")


def build_shared_url_index(items: list[dict], cross_series_min: int) -> tuple[dict[str, str], dict[str, str | None]]:
    """Devuelve (url_reason, url_owner):

    - `url_reason[url]` = motivo por el que la URL es placeholder:
      "known:LABEL" (registro image_store) o "cross-series:N" (misma foto en N
      series distintas ≥ umbral). Solo contiene URLs marcadas como placeholder.
    - `url_owner[url]` = slug del DUEÑO legítimo a conservar, o None si no es
      identificable. Dueño = el ÚNICO item que lleva esa foto como `extra`/`bonus`
      de su propia colección (los demás la usan robada como portada/galería).
    """
    url_series: dict[str, set[str]] = defaultdict(set)
    url_extra_owners: dict[str, set[str]] = defaultdict(set)
    for it in items:
        skey = series_key(it)
        slug = it.get("slug") or ""
        for url, kind in _iter_item_image_urls(it):
            url_series[url].add(skey)
            if kind in ("extra", "bonus"):
                url_extra_owners[url].add(slug)

    url_reason: dict[str, str] = {}
    url_owner: dict[str, str | None] = {}
    for url, series in url_series.items():
        known = image_store.known_placeholder_url_reason(url)
        reason = ""
        if known:
            reason = known
        elif len(series) >= cross_series_min:
            reason = f"cross-series:{len(series)}"
        if not reason:
            continue
        url_reason[url] = reason
        owners = url_extra_owners.get(url) or set()
        # Dueño identificable solo si hay EXACTAMENTE uno que la lleva como extra.
        url_owner[url] = next(iter(owners)) if len(owners) == 1 else None
    return url_reason, url_owner


def classify_local(local: str, cache: dict[str, str]) -> str:
    """Razón de placeholder para un filename del espejo, o "" si es real."""
    if local in cache:
        return cache[local]
    reason = ""
    p = IMAGES / local
    try:
        size = p.stat().st_size
    except OSError:
        reason = "broken"
    else:
        if size == 0:
            reason = "broken"
        elif size <= _EVAL_MAX_BYTES:
            reason = image_store.placeholder_reason(p)
        # size > umbral ⇒ portada real, no se evalúa (reason="")
    cache[local] = reason
    return reason


def cover_preview_refs() -> set[str]:
    """Filenames referenciados por la cola de cover_preview (para no mover a
    cuarentena un archivo que el panel de review aún necesita)."""
    refs: set[str] = set()
    try:
        data = json.loads(COVER_PREVIEW.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return refs
    entries = data if isinstance(data, list) else data.get("items", data.get("entries", []))
    for e in entries or []:
        for k in ("old_image", "new_image"):
            v = e.get(k)
            if v:
                refs.add(v)
        for c in e.get("candidates", []) or []:
            v = c.get("new_image")
            if v:
                refs.add(v)
    return refs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada, solo reporta")
    ap.add_argument("--keep-files", action="store_true",
                    help="no mover los archivos huérfanos a cuarentena _orphans/")
    ap.add_argument("--cross-series-min", type=int, default=_CROSS_SERIES_MIN,
                    help=f"umbral de la regla genérica: misma foto en ≥N series "
                         f"distintas ⇒ placeholder (default {_CROSS_SERIES_MIN})")
    ap.add_argument("--include-approved", action="store_true",
                    help="También purga placeholders de items aprobados (golden records). "
                         "Por defecto se saltean: purgar quita/reordena entries de images[] "
                         "(images[0], la portada, incluida) de una fila que el owner confirmó.")
    args = ap.parse_args()

    items = [json.loads(l) for l in ITEMS.open(encoding="utf-8") if l.strip()]
    cache: dict[str, str] = {}

    # Índice de URLs-placeholder (rule a: registro conocido; rule b: misma foto
    # cross-series) + su dueño legítimo a conservar. Fuente de verdad de la URL.
    url_reason, url_owner = build_shared_url_index(items, args.cross_series_min)

    removed_entries = 0
    items_changed = 0
    items_now_empty = 0
    skipped_approved = 0
    reasons = Counter()
    removed_locals: set[str] = set()
    removed_urls: set[str] = set()
    surviving_locals: set[str] = set()  # refs que SOBREVIVEN (para el GC, fiel en dry-run)
    examples: list[tuple[str, str, str]] = []

    # Pasada 1 — clasificar imágenes y quitar las placeholder de images[].
    for it in items:
        imgs = it.get("images") or []
        slug = it.get("slug") or ""
        if is_approved(it) and not args.include_approved:
            skipped_approved += 1
            # No tocamos sus entries, pero sus archivos locales SÍ cuentan como
            # "sobrevivientes" — si no, el GC podría mandarlos a cuarentena
            # cuando otro item (no aprobado) que comparte el mismo archivo lo
            # pierde en su propia pasada.
            for im in imgs:
                loc = (im.get("local") or "").strip()
                if loc:
                    surviving_locals.add(loc)
            continue
        kept = []
        dropped = []
        for idx, im in enumerate(imgs):
            local = (im.get("local") or "").strip()
            url = (im.get("url") or "").strip()
            # (1) placeholder por ARCHIVO local (estructural/firma).
            reason = classify_local(local, cache) if local else ""
            # (2) placeholder por URL — funciona aunque la foto NUNCA se haya
            #     espejado (local=""), caso del placeholder censurado. Se CONSERVA
            #     en el dueño legítimo identificable (kind extra/bonus propio).
            if not reason and url in url_reason and url_owner.get(url) != slug:
                url_r = url_reason[url]
                if url_r.startswith("known:"):
                    # Placeholder CONOCIDO (registro image_store): nunca es una
                    # portada real → seguro purgarlo en cualquier posición.
                    reason = url_r
                elif idx > 0:
                    # Inferencia genérica cross-series: SOLO purgamos fotos de
                    # galería (idx>0). NUNCA tocamos la portada (images[0]) por una
                    # heurística — una misma foto puede ser la portada legítima de
                    # UNA serie y contaminar el carrusel de otras (bug de scrape de
                    # búsqueda, p.ej. Star Comics). Quitar la portada destruiría un
                    # cover real; quitar la copia de galería es siempre seguro.
                    reason = url_r
            if reason:
                dropped.append((im, reason))
            else:
                kept.append(im)
                if local:
                    surviving_locals.add(local)
        if not dropped:
            continue
        if not args.dry_run:
            it["images"] = kept
        items_changed += 1
        for im, reason in dropped:
            removed_entries += 1
            reasons[reason.split(":")[0]] += 1
            loc = (im.get("local") or "").strip()
            url = (im.get("url") or "").strip()
            if loc:
                removed_locals.add(loc)
            if url:
                removed_urls.add(url)
            if len(examples) < 30:
                examples.append((it.get("title", "")[:34], reason, loc or url[:40]))
        if imgs and not kept:
            items_now_empty += 1

    # Pasada 2 — limpiar refs en sources[] al mismo archivo/URL placeholder
    # (con removed_locals/removed_urls ya COMPLETOS) y juntar las que sobreviven.
    for it in items:
        slug = it.get("slug") or ""
        if is_approved(it) and not args.include_approved:
            # Igual que en la Pasada 1: no tocamos sources[] de un item aprobado,
            # pero protegemos sus locals del GC.
            for src in it.get("sources") or []:
                sloc = (src.get("image_local") or "").strip()
                if sloc:
                    surviving_locals.add(sloc)
            continue
        for src in it.get("sources") or []:
            sloc = (src.get("image_local") or "").strip()
            surl = (src.get("image_url") or "").strip()
            # No tocar el dueño legítimo: si conservamos la imagen en su images[],
            # tampoco limpiamos su referencia en sources[].
            is_owner_of_url = bool(surl) and url_owner.get(surl) == slug
            if not is_owner_of_url and (sloc in removed_locals or (surl and surl in removed_urls)):
                if not args.dry_run:
                    src["image_local"] = ""
                    src["image_url"] = ""
            elif sloc:
                surviving_locals.add(sloc)

    # GC: locals removidos que ya no tienen NINGUNA referencia viva (ni imágenes
    # que quedan, ni sources, ni la cola de cover_preview) → huérfanos.
    protected = surviving_locals | cover_preview_refs()
    orphaned = sorted(l for l in removed_locals if l not in protected)

    # ── reporte ──────────────────────────────────────────────────────────────
    print(f"[purge] items afectados: {items_changed} | entries quitadas: {removed_entries}")
    print(f"[purge] por razón: {dict(reasons)}")
    print(f"[purge] items que quedan SIN imagen (mostrarán 📚): {items_now_empty}")
    if skipped_approved:
        print(f"[purge] items aprobados saltados (usar --include-approved): {skipped_approved}")
    print(f"[purge] archivos huérfanos a {'(cuarentena)' if not args.keep_files else '(conservados)'}: {len(orphaned)}")
    for title, reason, ref in examples:
        print(f"   {title:34} [{reason:18}] {ref}")

    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0

    # backup (convención dura, hallazgo #6, 2026-07-08: backup_and_rotate en vez
    # de un slot fijo propio) + escritura atómica con sort_keys (idempotencia
    # byte-idéntica entre corridas).
    backup = backup_and_rotate(ITEMS, "purge-placeholder")
    write_items_atomic(ITEMS, items)
    print(f"[purge] escrito {ITEMS}. Backup: {backup}")

    # mover huérfanos a cuarentena
    if orphaned and not args.keep_files:
        ORPHANS.mkdir(parents=True, exist_ok=True)
        moved = 0
        for loc in orphaned:
            src = IMAGES / loc
            if src.exists():
                try:
                    src.replace(ORPHANS / loc)
                    moved += 1
                except OSError:
                    pass
        print(f"[purge] {moved} archivos movidos a {ORPHANS}/ (reversible)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
