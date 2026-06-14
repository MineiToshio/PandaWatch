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
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import image_store  # noqa: E402  (fuente única de placeholder_reason)

ITEMS = ROOT / "data" / "items.jsonl"
IMAGES = ROOT / "data" / "images"
ORPHANS = IMAGES / "_orphans"
COVER_PREVIEW = ROOT / "data" / "cover_preview.json"

# Archivos por encima de este tamaño no se evalúan: un placeholder (1×1, blanco,
# o los registrados) pesa unos pocos KB; una portada real de >200KB jamás es
# casi-sólida ni matchea una firma. Evita leer/decodificar 14GB de portadas.
_EVAL_MAX_BYTES = 200_000


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
    args = ap.parse_args()

    items = [json.loads(l) for l in ITEMS.open(encoding="utf-8") if l.strip()]
    cache: dict[str, str] = {}

    removed_entries = 0
    items_changed = 0
    items_now_empty = 0
    reasons = Counter()
    removed_locals: set[str] = set()
    removed_urls: set[str] = set()
    surviving_locals: set[str] = set()  # refs que SOBREVIVEN (para el GC, fiel en dry-run)
    examples: list[tuple[str, str, str]] = []

    # Pasada 1 — clasificar imágenes y quitar las placeholder de images[].
    for it in items:
        imgs = it.get("images") or []
        kept = []
        dropped = []
        for im in imgs:
            local = (im.get("local") or "").strip()
            reason = classify_local(local, cache) if local else ""
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
        for src in it.get("sources") or []:
            sloc = (src.get("image_local") or "").strip()
            surl = (src.get("image_url") or "").strip()
            if sloc in removed_locals or (surl and surl in removed_urls):
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
    print(f"[purge] archivos huérfanos a {'(cuarentena)' if not args.keep_files else '(conservados)'}: {len(orphaned)}")
    for title, reason, ref in examples:
        print(f"   {title:34} [{reason:18}] {ref}")

    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0

    # backup + escritura atómica
    backup = ITEMS.with_suffix(".jsonl.pre-purge-placeholder-bak")
    shutil.copy(ITEMS, backup)
    tmp = ITEMS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(ITEMS)
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
