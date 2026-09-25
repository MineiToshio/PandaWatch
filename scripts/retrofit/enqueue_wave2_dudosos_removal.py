#!/usr/bin/env python3
"""enqueue_wave2_dudosos_removal.py — encola como candidatas `remove_image`
PENDIENTES los 327 pares "dudosos" de `dedup_carousel_images.py --redteam-auto`
(OLA 2, 2026-09-01) para revisión manual en el dashboard cover-preview.html.

Fuente: `data/diagnostics/dedup-wave2-dudosos.json` (327 pares: dHash<=8 dentro
de la banda de interés, pero que NO cumplen la regla AUTO del script — dims
iguales, o dHash 3-8 — así que dedup_carousel_images.py los reportó SIN
tocarlos). Esto NO auto-elimina nada: cada par queda `status=pending`, acción
`remove_image` (ver docs/reference/dashboard.md § "Cover-preview — eliminar
imagen sin reemplazo" y docs/reference/images.md); el owner aprueba/rechaza
por par desde el dashboard, igual que cualquier otra candidata de portada.

Por cada par, ANTES de encolar:
  - Verifica que el item (`slug`) siga existiendo en `data/items.jsonl`.
  - Verifica que AMBAS imágenes del par (`image_a`/`image_b`) sigan presentes
    en `images[]` del item (otra pasada — purge_placeholder/ola 3/el owner —
    pudo haberlas sacado desde que corrió la ola 2).
  - Determina keep (se conserva) / target (se propone eliminar): la de MÁS
    píxeles gana; empate en píxeles → gana la que aparece PRIMERO en la
    galería actual (índice menor).
  - Regla dura: si `target` resultara ser `images[0]` (la portada), el par se
    SALTEA por completo — nunca se propone remover la portada.

Orden de encolado (más informativo primero): primero los pares con
`same_dims=true` (137 — más probables de ser DOS FOTOS DISTINTAS, no una
resolución vs otra, así que la decisión del owner aporta más), después el
resto (banda dHash 3-8); dentro de cada grupo, dHash ascendente.

Escritura: `fetch_better_covers._write_preview(entries, merge=True)` (toma
`preview_write_lock` internamente) — SIEMPRE merge, nunca reescritura total:
otros procesos (dashboard, el motor, otro agente) pueden estar escribiendo
`cover_preview.json` en paralelo. NUNCA toca `data/items.jsonl`.

Uso:
    .venv/bin/python scripts/retrofit/enqueue_wave2_dudosos_removal.py --dry-run
    .venv/bin/python scripts/retrofit/enqueue_wave2_dudosos_removal.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent.parent
for _p in (_HERE / "scripts" / "retrofit", _HERE / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import fetch_better_covers as fbc  # noqa: E402
try:
    from manga_watch import backup_and_rotate  # noqa: E402
except ImportError:  # pragma: no cover
    from scripts.manga_watch import backup_and_rotate  # noqa: E402

DUDOSOS_PATH = _HERE / "data" / "diagnostics" / "dedup-wave2-dudosos.json"
ITEMS_PATH = _HERE / "data" / "items.jsonl"
IMAGES_DIR = _HERE / "data" / "images"
PREVIEW_PATH = _HERE / "data" / "cover_preview.json"


def _load_items_by_slug(path: Path) -> dict[str, dict]:
    by_slug: dict[str, dict] = {}
    if not path.exists():
        return by_slug
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                it = json.loads(line)
            except json.JSONDecodeError:
                continue
            slug = it.get("slug")
            if slug:
                by_slug[slug] = it
    return by_slug


def _read_local_bytes_cached(local: str, images_dir: Path, cache: dict) -> bytes:
    if local in cache:
        return cache[local]
    data = b""
    if local:
        p = images_dir / local
        try:
            data = p.read_bytes()
        except OSError:
            data = b""
    cache[local] = data
    return data


def _dims_or_none(data: bytes) -> list[int] | None:
    if not data:
        return None
    w, h = fbc._get_dims_from_bytes(data)
    return [w, h] if w > 0 and h > 0 else None


def build_entries(
    pairs: list[dict], items_by_slug: dict[str, dict], images_dir: Path,
) -> tuple[list[dict], dict[str, int]]:
    """Construye las entries de cover_preview.json (schema multi-candidato)
    para los pares vigentes. Función pura salvo por la lectura de bytes del
    espejo local (sólo lectura, para computar dims) — testeable sin tocar
    items.jsonl/cover_preview.json."""
    stats = {
        "total_pairs": len(pairs),
        "queued_pairs": 0,
        "skipped_item_missing": 0,
        "skipped_image_gone": 0,
        "skipped_would_remove_cover": 0,
        "skipped_duplicate_target": 0,
    }
    entries: dict[str, dict] = {}
    bytes_cache: dict[str, bytes] = {}

    for pair in pairs:
        slug = pair.get("slug", "")
        item = items_by_slug.get(slug)
        if item is None:
            stats["skipped_item_missing"] += 1
            continue

        images = item.get("images") or []
        url_to_idx = {
            im.get("url"): i for i, im in enumerate(images) if isinstance(im, dict)
        }
        a, b = pair.get("image_a", {}), pair.get("image_b", {})
        idx_a = url_to_idx.get(a.get("url"))
        idx_b = url_to_idx.get(b.get("url"))
        if idx_a is None or idx_b is None:
            stats["skipped_image_gone"] += 1
            continue

        px_a, px_b = a.get("px", 0) or 0, b.get("px", 0) or 0
        if px_a > px_b:
            keep, target, target_idx = a, b, idx_b
        elif px_b > px_a:
            keep, target, target_idx = b, a, idx_a
        elif idx_a <= idx_b:
            keep, target, target_idx = a, b, idx_b
        else:
            keep, target, target_idx = b, a, idx_a

        # Regla dura: JAMÁS proponer eliminar images[0] (la portada).
        if target_idx == 0:
            stats["skipped_would_remove_cover"] += 1
            continue

        entry = entries.get(slug)
        if entry is None:
            current_images = [
                {
                    "url": im.get("url", ""), "local": im.get("local", ""),
                    "kind": im.get("kind", "gallery"), "is_cover": i == 0,
                }
                for i, im in enumerate(images) if isinstance(im, dict)
            ]
            old_local = current_images[0]["local"] if current_images else ""
            old_pixels = fbc._get_pixels_from_bytes(
                _read_local_bytes_cached(old_local, images_dir, bytes_cache)
            ) if old_local else 0
            entry = {
                "slug": slug,
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "title_original": item.get("title_original", ""),
                "series_display": item.get("series_display", ""),
                "publisher": item.get("publisher", ""),
                "country": item.get("country", ""),
                "old_url": current_images[0]["url"] if current_images else "",
                "old_image": old_local,
                "old_pixels": old_pixels,
                "current_images": current_images,
                "candidates": [],
            }
            entries[slug] = entry

        existing_targets = {c["target"] for c in entry["candidates"]}
        if target.get("url") in existing_targets:
            # Mismo target propuesto 2 veces (dos pares distintos coinciden en
            # la imagen "peor") — no duplicar la candidata.
            stats["skipped_duplicate_target"] += 1
            continue

        remove_dims = _dims_or_none(
            _read_local_bytes_cached(target.get("local", ""), images_dir, bytes_cache)
        )
        keep_dims = _dims_or_none(
            _read_local_bytes_cached(keep.get("local", ""), images_dir, bytes_cache)
        )

        entry["candidates"].append({
            "new_image": target.get("local", ""),
            "new_url": target.get("url", ""),
            "new_pixels": target.get("px", 0) or 0,
            "page_title": "", "domain": "", "query": "",
            "confidence": "low", "verified": False,
            "match_dist": pair.get("dhash_dist"),
            "ref_pixels": keep.get("px", 0) or 0,
            "action": "remove_image",
            "target": target.get("url", ""),
            "kind": "gallery",
            "status": "pending",
            "keep_url": keep.get("url", ""),
            "keep_local": keep.get("local", ""),
            "remove_dims": remove_dims,
            "keep_dims": keep_dims,
            "same_dims": bool(pair.get("same_dims")),
        })
        stats["queued_pairs"] += 1

    return list(entries.values()), stats


def _sorted_pairs(pairs: list[dict]) -> list[dict]:
    """Primero same_dims=true (más informativos), después el resto; dentro de
    cada grupo, dHash ascendente. Sort estable: desempata por orden original."""
    return sorted(
        pairs,
        key=lambda p: (0 if p.get("same_dims") else 1, p.get("dhash_dist", 99)),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                     help="No escribe nada; solo reporta qué encolaría.")
    args = ap.parse_args()

    if not DUDOSOS_PATH.exists():
        print(f"No existe {DUDOSOS_PATH} — nada que encolar.")
        return 1

    raw = json.loads(DUDOSOS_PATH.read_text(encoding="utf-8"))
    pairs = _sorted_pairs(raw.get("pairs", []))
    print(f"Pares en {DUDOSOS_PATH.name}: {len(pairs)}")

    items_by_slug = _load_items_by_slug(ITEMS_PATH)
    print(f"Items en catálogo: {len(items_by_slug)}")

    entries, stats = build_entries(pairs, items_by_slug, IMAGES_DIR)

    print()
    print("=== Resultado ===")
    print(f"  Pares totales:                 {stats['total_pairs']}")
    print(f"  Encolados (candidatas nuevas): {stats['queued_pairs']}")
    print(f"  Saltados — item ya no existe:  {stats['skipped_item_missing']}")
    print(f"  Saltados — imagen ya no está en la galería: {stats['skipped_image_gone']}")
    print(f"  Saltados — removería la portada: {stats['skipped_would_remove_cover']}")
    print(f"  Saltados — target duplicado:   {stats['skipped_duplicate_target']}")
    print(f"  Entries (productos) afectadas: {len(entries)}")

    if args.dry_run:
        print("\n[dry-run] No se escribió cover_preview.json.")
        return 0

    if not entries:
        print("\nNada para encolar — no se toca cover_preview.json.")
        return 0

    # Backup antes de mutar (convención dura — ver docs/reference/conventions.md
    # § Backups). El write real va bajo preview_write_lock + merge=True dentro
    # de _write_preview: relee el disco y funde con lo que haya (otro proceso
    # puede estar guardando decisiones del owner AHORA MISMO) — nunca pisa.
    backup_and_rotate(PREVIEW_PATH, "wave2-dudosos-enqueue")
    fbc._PREVIEW_PATH = PREVIEW_PATH
    fbc._write_preview(entries, merge=True)
    print(f"\n✓ cover_preview.json actualizado (merge) con {stats['queued_pairs']} "
          f"candidatas remove_image nuevas en {len(entries)} productos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
