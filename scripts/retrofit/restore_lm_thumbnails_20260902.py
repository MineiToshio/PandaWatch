#!/usr/bin/env python3
"""restore_lm_thumbnails_20260902.py — repara el dato del bug de gotcha #185.

`sync_cover_images.py` corrió una sola vez el 2026-08-23 21:31 con el criterio
viejo de "junk = archivo local <6000 bytes" (sin mirar estructura/contenido).
Los thumbnails REALES de listadomanga (96-124×150-160px) comprimen en AVIF a
2.6-6KB y cayeron en esa clasificación: `_fix_bad_cover` vació `images[]` de
cada edición sin galería de respaldo, dejando la card sin portada (📚) aunque
el thumbnail real seguía existiendo en disco (movido a cuarentena
`data/images/_orphans/` por un GC posterior).

Este script es la REPARACIÓN DEL DATO puntual (one-off, NO parte del pipeline
canónico, no se agrega al registry) — el FIX DE MECANISMO vive en
`sync_cover_images.py` (gotcha #185): ese ya no puede volver a producir este
patrón.

Alcance: items con `images == []` HOY cuyo backup pre-bug
(`data/backups/items.jsonl/items.jsonl.pre-sync-cover-images-bak`, snapshot
2026-08-23 21:31, tomado ANTES de que `sync_cover_images.py` corriera) tenía
como `images[0]` una URL real de listadomanga (`static.listadomanga.com`,
distinta de cualquier placeholder conocido — `image_store.known_placeholder_url_reason`).
Deliberadamente NO toca items cuya pérdida de imagen viene de otra fuente/causa
— ver el diagnóstico en el encargo para el detalle de scoping.

Para cada candidato:
  1. Si el archivo local histórico (`local` del backup) existe en
     `data/images/` — se usa tal cual (verificado de nuevo con
     `image_store.placeholder_reason`, por las dudas).
  2. Si existe en `data/images/_orphans/` (cuarentena de un GC posterior) — se
     verifica con `placeholder_reason` y, si sigue siendo real, se MUEVE de
     vuelta a `data/images/` (si no, `images[].local` quedaría apuntando a un
     archivo que no está donde el resto del pipeline lo busca — MIRRORREF).
  3. Si no se encuentra en ningún lado — `local=""`, la URL remota queda como
     fallback; correr después `mirror_images.py --slugs <slugs>` para
     re-descargarlo (flujo canónico, `normalize_image`).

`images[0]` se reconstruye como `{url, local, kind: "gallery", description: ""}`
— mismo esquema que usa el resto del pipeline (`image_store.set_cover`).

Backup de items.jsonl (label `restore-lm-covers`) + una sola escritura atómica
(`write_items_atomic`, toma `items_write_lock`). Idempotente: re-correrlo no
vuelve a tocar items que ya tienen `images[0]`.

Uso:
    .venv/bin/python scripts/retrofit/restore_lm_thumbnails_20260902.py --dry-run
    .venv/bin/python scripts/retrofit/restore_lm_thumbnails_20260902.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import image_store  # noqa: E402
try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    from manga_watch import backup_and_rotate, write_items_atomic  # noqa: E402
except ImportError:  # pragma: no cover
    from scripts.manga_watch import backup_and_rotate, write_items_atomic  # noqa: E402

DEFAULT_ITEMS = _ROOT / "data" / "items.jsonl"
DEFAULT_BACKUP = _ROOT / "data" / "backups" / "items.jsonl" / "items.jsonl.pre-sync-cover-images-bak"


def _load_jsonl(path: Path) -> list[dict]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def _find_candidate(item: dict, backup_by_slug: dict[str, dict]) -> dict | None:
    """Devuelve el `images[0]` del backup si `item` es un candidato de
    restauración (images==[] hoy, backup con cover real de listadomanga), o
    None."""
    if item.get("images"):
        return None  # ya tiene portada — nada que reparar
    slug = item.get("slug") or ""
    old = backup_by_slug.get(slug)
    if not old:
        return None
    old_imgs = old.get("images") or []
    if not old_imgs or not isinstance(old_imgs[0], dict):
        return None
    im0 = old_imgs[0]
    url = im0.get("url") or ""
    if "static.listadomanga.com" not in url:
        return None  # fuera de alcance de esta reparación puntual
    if image_store.known_placeholder_url_reason(url):
        return None  # el backup YA tenía un placeholder conocido — correctamente vacío
    return im0


def run(items_path: Path, backup_path: Path, *, dry_run: bool) -> None:
    images_dir = items_path.parent / "images"
    orphans_dir = images_dir / "_orphans"  # mismo nombre de cuarentena que mirror_images.py / purge_placeholder_images.py

    items = _load_jsonl(items_path)
    if not backup_path.exists():
        print(f"[ABORT] no existe el backup {backup_path} — nada que restaurar.")
        return
    backup_by_slug = {it.get("slug"): it for it in _load_jsonl(backup_path) if it.get("slug")}

    by_source: Counter[str] = Counter()
    restored = 0
    reintroduced_placeholder = 0
    examples: list[str] = []

    for item in items:
        im0 = _find_candidate(item, backup_by_slug)
        if im0 is None:
            continue
        url = im0.get("url") or ""
        local = im0.get("local") or ""
        final_local = ""
        source = "missing"

        if local:
            disk_path = images_dir / local
            orphan_path = orphans_dir / local
            if disk_path.exists():
                reason = image_store.placeholder_reason(disk_path)
                if not reason:
                    final_local = local
                    source = "disk"
                else:
                    reintroduced_placeholder += 1
                    continue  # el archivo en disco resultó ser basura — no restaurar
            elif orphan_path.exists():
                reason = image_store.placeholder_reason(orphan_path)
                if not reason:
                    if not dry_run:
                        orphan_path.replace(disk_path)
                    final_local = local
                    source = "orphans"
                else:
                    reintroduced_placeholder += 1
                    continue

        # Doble chequeo defensivo (además del filtro en _find_candidate): la
        # regla host+extensión de Rakuten y cualquier otro placeholder
        # conocido por URL NUNCA debe reintroducirse como portada.
        if image_store.known_placeholder_url_reason(url):
            reintroduced_placeholder += 1
            continue

        item["images"] = [{"url": url, "local": final_local, "kind": "gallery", "description": ""}]
        restored += 1
        by_source[source] += 1
        if len(examples) < 10:
            examples.append(f"{item.get('slug')} ({source})")

    print(f"Items totales: {len(items)}")
    print(f"Items restaurados: {restored}")
    for source in ("disk", "orphans", "missing"):
        if by_source[source]:
            print(f"  · vía {source}: {by_source[source]}")
    if reintroduced_placeholder:
        print(f"Candidatos descartados por resultar placeholder al re-verificar: {reintroduced_placeholder}")
    for ex in examples:
        print(f"  • {ex}")
    if by_source["missing"]:
        missing_slugs = []
        for it in items:
            imgs = it.get("images") or []
            if imgs and isinstance(imgs[0], dict) and not imgs[0].get("local") \
                    and "static.listadomanga.com" in (imgs[0].get("url") or ""):
                missing_slugs.append(it.get("slug"))
        if missing_slugs:
            print("\nSlugs sin archivo local recuperable (correr mirror_images.py --slugs):")
            print("  --slugs " + ",".join(missing_slugs))

    if dry_run:
        print("\n[dry-run] No se escribió nada.")
        return
    if not restored:
        print("\nNada que escribir.")
        return

    backup_and_rotate(items_path, "restore-lm-covers")
    write_items_atomic(items_path, items)
    print(f"\n✓ Escrito {items_path} ({restored} items restaurados).")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    ap.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(args.items, args.backup, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
