#!/usr/bin/env python3
"""sync_cover_preview.py — sincroniza data/cover_preview.json con el estado actual
del catálogo (data/items.jsonl).

La cola de candidatas guarda una FOTO CONGELADA del item al momento de encolar.
El catálogo evoluciona (upgrades, mirror, applies) y la cola queda desincronizada,
causando dos bugs: (a) sugiere candidatas para portadas que ya están en alta calidad;
(b) el botón de eliminar foto de galería falla porque la foto ya no existe en el item.

Función importable:
    sync_preview(preview, items_by_slug, images_dir) -> (preview_sincronizado, stats)

CLI:
    python scripts/retrofit/sync_cover_preview.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent.parent
ITEMS_PATH = ROOT / "data" / "items.jsonl"
PREVIEW_PATH = ROOT / "data" / "cover_preview.json"
IMAGES_DIR = ROOT / "data" / "images"

LOW_QUALITY_PX = 90_000  # mismo umbral del skill / panel de calidad


# ---------------------------------------------------------------------------
# PIL (solo para recalcular píxeles del archivo local)
# ---------------------------------------------------------------------------

def _get_local_pixels(local: str | None, images_dir: Path) -> int:
    """Devuelve píxeles de la imagen local, 0 si no existe o no hay PIL."""
    if not local or local == "[dry-run]":
        return 0
    path = images_dir / local
    if not path.exists():
        return 0
    try:
        from PIL import Image  # type: ignore
        with Image.open(path) as img:
            w, h = img.size
            return w * h
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Función principal importable
# ---------------------------------------------------------------------------

def sync_preview(
    preview: list[dict],
    items_by_slug: dict[str, dict],
    images_dir: Path,
) -> tuple[list[dict], dict[str, int]]:
    """Sincroniza la cola de candidatas con el estado actual del catálogo.

    Parámetros
    ----------
    preview:        lista de entries de cover_preview.json.
    items_by_slug:  dict slug→item cargado de items.jsonl.
    images_dir:     Path al directorio data/images/.

    Devuelve
    --------
    (preview_sincronizado, stats) donde stats es un dict con counters:
      - dropped_missing_item:  entries cuyo slug ya no existe en el catálogo.
      - dropped_empty:         entries que quedaron sin candidatas tras la poda.
      - pruned_cover_ok:       candidatas pending de replace-cover podadas porque
                               la portada actual ya es ≥ LOW_QUALITY_PX.
      - pruned_target_gone:    candidatas pending de replace_image podadas porque
                               la foto target ya no está en la galería.
      - pruned_target_ok:      candidatas pending de replace_image podadas porque
                               la foto target ya es ≥ LOW_QUALITY_PX.
      - pruned_already_current: candidatas cuya new_url ya es la portada actual.
    """
    stats: dict[str, int] = {
        "dropped_missing_item": 0,
        "dropped_empty": 0,
        "pruned_cover_ok": 0,
        "pruned_target_gone": 0,
        "pruned_target_ok": 0,
        "pruned_already_current": 0,
    }

    _REPLACE_COVER_ACTIONS = frozenset({
        "replace_cover",
        "replace_cover_demote",
        "replace_and_add",
    })

    result: list[dict] = []

    for entry in preview:
        slug = entry.get("slug", "")
        item = items_by_slug.get(slug)

        # Regla 1: slug no existe → eliminar
        if item is None:
            stats["dropped_missing_item"] += 1
            continue

        # Regla 2: refrescar estado actual del item en la entry
        item_images: list[dict] = item.get("images") or []

        # old_url/old_image → from images[0]
        cover_img: dict = item_images[0] if item_images else {}
        new_old_url = cover_img.get("url", "")
        new_old_image = cover_img.get("local", "")
        new_old_pixels = _get_local_pixels(new_old_image, images_dir)

        # current_images regenerado desde item.images[]
        new_current_images: list[dict] = []
        for idx, img in enumerate(item_images):
            new_current_images.append({
                "url": img.get("url", ""),
                "local": img.get("local", ""),
                "kind": img.get("kind", "gallery"),
                "is_cover": (idx == 0),
            })

        # Set de urls de la galería actual (para lookup eficiente)
        gallery_urls: set[str] = {img.get("url", "") for img in item_images if img.get("url")}
        # Píxeles por url de galería (para pruning de target_ok)
        gallery_px_by_url: dict[str, int] = {}
        for img in item_images:
            url = img.get("url", "")
            if url:
                local = img.get("local", "")
                gallery_px_by_url[url] = _get_local_pixels(local, images_dir)

        # URL de la portada actual
        current_cover_url = cover_img.get("url", "")

        # Regla 3: podar candidatas PENDING con premisa caída
        # (approved/rejected se conservan intactos — son decisiones del owner)
        new_candidates: list[dict] = []
        for cand in entry.get("candidates", []):
            status = cand.get("status", "pending")
            action = cand.get("action", "")
            new_url = cand.get("new_url", "")

            if status != "pending":
                # Las aprobadas/rechazadas no se tocan nunca
                new_candidates.append(cand)
                continue

            # Poda 3a: new_url ya es la portada actual (ya aplicada de facto)
            if new_url and new_url == current_cover_url:
                stats["pruned_already_current"] += 1
                continue

            if action in _REPLACE_COVER_ACTIONS:
                # Poda 3b: portada actual ya en alta calidad → candidata innecesaria
                if new_old_pixels >= LOW_QUALITY_PX:
                    stats["pruned_cover_ok"] += 1
                    continue

            elif action == "replace_image":
                target_url = cand.get("target", "")
                if target_url:
                    # Poda 3c: foto target ya no está en la galería
                    if target_url not in gallery_urls:
                        stats["pruned_target_gone"] += 1
                        continue
                    # Poda 3d: foto target ya en alta calidad
                    px = gallery_px_by_url.get(target_url, 0)
                    if px >= LOW_QUALITY_PX:
                        stats["pruned_target_ok"] += 1
                        continue

            new_candidates.append(cand)

        # Regla 4: entry sin candidatas → eliminar
        if not new_candidates:
            stats["dropped_empty"] += 1
            continue

        # Construir entry actualizada (preservando todos los campos extra)
        updated = dict(entry)
        updated["old_url"] = new_old_url
        updated["old_image"] = new_old_image
        updated["old_pixels"] = new_old_pixels
        updated["current_images"] = new_current_images
        updated["candidates"] = new_candidates
        # Backfill publisher/country desde el item cuando la entry los tiene vacíos
        # (entries creadas antes de que el skill empezara a escribir esos campos).
        if not updated.get("publisher") and item:
            updated["publisher"] = item.get("publisher", "")
        if not updated.get("country") and item:
            updated["country"] = item.get("country", "")
        result.append(updated)

    return result, stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_items_by_slug(items_path: Path) -> dict[str, dict]:
    items_by_slug: dict[str, dict] = {}
    if not items_path.exists():
        return items_by_slug
    with items_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
                slug = item.get("slug", "")
                if slug:
                    items_by_slug[slug] = item
            except json.JSONDecodeError:
                pass
    return items_by_slug


def _write_atomic(path: Path, data: Any) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sincroniza data/cover_preview.json con el estado actual del catálogo."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra los stats sin escribir el archivo.")
    args = parser.parse_args(argv)

    if not PREVIEW_PATH.exists():
        print("cover_preview.json no existe — nada que sincronizar.")
        return 0

    preview: list[dict] = json.loads(PREVIEW_PATH.read_text(encoding="utf-8"))
    print(f"Entries cargadas: {len(preview)}")

    items_by_slug = _load_items_by_slug(ITEMS_PATH)
    print(f"Items en catálogo: {len(items_by_slug)} (con slug)")

    synced, stats = sync_preview(preview, items_by_slug, IMAGES_DIR)

    total_pruned = (
        stats["pruned_cover_ok"]
        + stats["pruned_target_gone"]
        + stats["pruned_target_ok"]
        + stats["pruned_already_current"]
    )
    total_dropped = stats["dropped_missing_item"] + stats["dropped_empty"]
    print()
    print("=== Resultados ===")
    print(f"  Entries eliminadas — slug no existe:  {stats['dropped_missing_item']}")
    print(f"  Entries eliminadas — quedaron vacías: {stats['dropped_empty']}")
    print(f"  Candidatas podadas — portada ok:      {stats['pruned_cover_ok']}")
    print(f"  Candidatas podadas — target gone:     {stats['pruned_target_gone']}")
    print(f"  Candidatas podadas — target ok px:    {stats['pruned_target_ok']}")
    print(f"  Candidatas podadas — ya es portada:   {stats['pruned_already_current']}")
    print(f"  Entries resultado: {len(synced)} (de {len(preview)})")
    print(f"  Cambios: {total_pruned + total_dropped} operaciones")

    if args.dry_run:
        print("\n[dry-run] No se escribió ningún archivo.")
        return 0

    if total_pruned + total_dropped == 0 and len(synced) == len(preview):
        print("\nCola ya sincronizada — sin cambios.")
        return 0

    _write_atomic(PREVIEW_PATH, synced)
    print(f"\n✓ cover_preview.json actualizado: {len(synced)} entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
