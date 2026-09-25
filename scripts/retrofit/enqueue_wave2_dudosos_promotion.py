#!/usr/bin/env python3
"""enqueue_wave2_dudosos_promotion.py — encola como candidatas
`replace_cover_demote` los pares "dudosos" de OLA 2 (`dedup_carousel_images.py
--redteam-auto`, 2026-09-01, `data/diagnostics/dedup-wave2-dudosos.json`) que
`enqueue_wave2_dudosos_removal.py` NO pudo encolar como `remove_image` porque
la imagen de MENOR resolución del par era la PORTADA vigente (`images[0]`).

Ese caso no es "borrar galería" — es una MEJORA DE PORTADA con material que ya
vive en el item: la gemela de MAYOR resolución del mismo par está en la propia
`images[]` (idx≥1). Es el mismo patrón que la "cola de promoción local" de la
OLA 3 (ver `docs/reference/images.md` § "3. Cola de promoción local") — misma
infraestructura (`action="replace_cover_demote"`, ya soportada por el schema
multi-candidato de `cover_preview.json` sin tocar `fetch_better_covers.py`,
`serve.py` ni el dashboard), pero la FUENTE acá son los 44 pares excluidos de
la ola 2 (no el barrido general de portadas <90 000 px de la ola 3).

Reconstrucción: se re-deriva `keep`/`target` con la MISMA lógica que
`enqueue_wave2_dudosos_removal.build_entries` (más píxeles gana; empate →
gana el índice menor) sobre el corpus ACTUAL de `items.jsonl` — no se confía
en el diagnóstico viejo, que puede estar stale (items borrados, galería
cambiada por otra pasada). Sólo se consideran los pares donde `target_idx==0`
(la de menor resolución ES la portada actual): ahí `keep` es la candidata a
promover (nueva portada) y `target` (la portada vigente) se conserva en la
galería como `kind="extra"` — nada se pierde.

Filtros duros del red-team (clasifican fuerte/débil, NO descartan — se
encolan AMBOS, fuertes primero; mismo criterio que la ola 3):
  - alt.kind == "extra"                    → débil
  - alt es .gif                            → débil
  - alt.área == 90 000 px exacto (montajes 300×300 de listadomanga)  → débil
  - alt.aspect_ratio fuera de [0.60, 0.78]  → débil
  fuerte = pasa las 4 reglas.

Escritura: `fetch_better_covers.preview_write_lock`/`_write_preview(entries,
merge=True)` (mismo lock cross-proceso + merge anti-carrera que usa el motor
real y `enqueue_wave2_dudosos_removal.py`) + `backup_and_rotate` sobre
`cover_preview.json` (label `enqueue-44-demote`) antes de escribir. NUNCA
toca `data/items.jsonl`.

Uso:
    .venv/bin/python scripts/retrofit/enqueue_wave2_dudosos_promotion.py --dry-run
    .venv/bin/python scripts/retrofit/enqueue_wave2_dudosos_promotion.py
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
import enqueue_wave2_dudosos_removal as ew  # noqa: E402 (reusa loaders/paths)
try:
    from manga_watch import backup_and_rotate  # noqa: E402
except ImportError:  # pragma: no cover
    from scripts.manga_watch import backup_and_rotate  # noqa: E402

DUDOSOS_PATH = ew.DUDOSOS_PATH
ITEMS_PATH = ew.ITEMS_PATH
IMAGES_DIR = ew.IMAGES_DIR
PREVIEW_PATH = ew.PREVIEW_PATH

ASPECT_MIN, ASPECT_MAX = 0.60, 0.78
LISTADOMANGA_MONTAGE_AREA = 90_000


def _read_bytes_cached(local: str, images_dir: Path, cache: dict) -> bytes:
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


def find_promotion_pairs(
    pairs: list[dict], items_by_slug: dict[str, dict],
) -> tuple[list[dict], dict[str, int]]:
    """Re-deriva keep/target (misma lógica que build_entries de
    enqueue_wave2_dudosos_removal) y se queda SOLO con los pares donde
    target_idx==0 (la portada vigente es la de menor resolución)."""
    stats = {
        "total_pairs": len(pairs),
        "promotion_candidates": 0,
        "skipped_item_missing": 0,
        "skipped_image_gone": 0,
        "not_a_cover_case": 0,
    }
    out: list[dict] = []
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
            keep, target, keep_idx, target_idx = a, b, idx_a, idx_b
        elif px_b > px_a:
            keep, target, keep_idx, target_idx = b, a, idx_b, idx_a
        elif idx_a <= idx_b:
            keep, target, keep_idx, target_idx = a, b, idx_a, idx_b
        else:
            keep, target, keep_idx, target_idx = b, a, idx_b, idx_a

        if target_idx != 0:
            stats["not_a_cover_case"] += 1
            continue

        out.append({
            "slug": slug, "item": item, "keep": keep, "target": target,
            "keep_idx": keep_idx, "target_idx": target_idx,
            "dhash_dist": pair.get("dhash_dist"), "same_dims": pair.get("same_dims"),
        })
        stats["promotion_candidates"] += 1

    return out, stats


def classify_strength(
    case: dict, images_dir: Path, bytes_cache: dict,
) -> tuple[bool, list[str]]:
    """Clasifica un caso de promoción como fuerte/débil según los filtros
    duros del red-team. Devuelve (is_strong, reasons_debil)."""
    item = case["item"]
    images = item.get("images") or []
    keep_img = images[case["keep_idx"]] if case["keep_idx"] < len(images) else {}
    reasons: list[str] = []

    kind = keep_img.get("kind", "gallery")
    if kind == "extra":
        reasons.append("kind=extra")

    keep_local = keep_img.get("local", "") or ""
    keep_url = keep_img.get("url", "") or ""
    if keep_local.lower().endswith(".gif") or keep_url.lower().endswith(".gif"):
        reasons.append("gif")

    data = _read_bytes_cached(keep_local, images_dir, bytes_cache)
    w, h = fbc._get_dims_from_bytes(data) if data else (0, 0)
    aspect = (w / h) if h else 0.0
    area = w * h

    if area == LISTADOMANGA_MONTAGE_AREA:
        reasons.append("area=90000")
    if not (w > 0 and h > 0 and ASPECT_MIN <= aspect <= ASPECT_MAX):
        reasons.append(f"aspect={aspect:.4f}" if h else "aspect=unknown")

    case["keep_dims"] = [w, h] if w > 0 and h > 0 else None
    case["aspect_ratio"] = round(aspect, 4) if h else None
    return (len(reasons) == 0), reasons


def build_entries(
    cases: list[dict], images_dir: Path,
) -> tuple[list[dict], dict[str, int]]:
    """Construye las entries de cover_preview.json (schema multi-candidato,
    action=replace_cover_demote) para los casos de promoción vigentes."""
    stats = {"queued_candidates": 0, "skipped_duplicate_target": 0,
              "strong": 0, "weak": 0}
    entries: dict[str, dict] = {}
    bytes_cache: dict[str, bytes] = {}

    for case in cases:
        slug = case["slug"]
        item = case["item"]
        images = item.get("images") or []
        keep, target = case["keep"], case["target"]
        keep_idx, target_idx = case["keep_idx"], case["target_idx"]
        keep_img = images[keep_idx] if keep_idx < len(images) else {}
        target_img = images[target_idx] if target_idx < len(images) else {}

        is_strong, reasons = classify_strength(case, images_dir, bytes_cache)
        stats["strong" if is_strong else "weak"] += 1

        entry = entries.get(slug)
        if entry is None:
            current_images = [
                {
                    "url": im.get("url", ""), "local": im.get("local", ""),
                    "kind": im.get("kind", "gallery"), "is_cover": i == 0,
                }
                for i, im in enumerate(images) if isinstance(im, dict)
            ]
            old_local = target_img.get("local", "") or ""
            old_pixels = fbc._get_pixels_from_bytes(
                _read_bytes_cached(old_local, images_dir, bytes_cache)
            ) if old_local else 0
            entry = {
                "slug": slug,
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "title_original": item.get("title_original", ""),
                "series_display": item.get("series_display", ""),
                "publisher": item.get("publisher", ""),
                "country": item.get("country", ""),
                "old_url": target_img.get("url", "") or "",
                "old_image": old_local,
                "old_pixels": old_pixels,
                "current_images": current_images,
                "candidates": [],
            }
            entries[slug] = entry

        new_url = keep_img.get("url", "") or ""
        existing_targets = {c["new_url"] for c in entry["candidates"]}
        if new_url in existing_targets:
            stats["skipped_duplicate_target"] += 1
            continue

        new_local = keep_img.get("local", "") or ""
        new_pixels = fbc._get_pixels_from_bytes(
            _read_bytes_cached(new_local, images_dir, bytes_cache)
        ) if new_local else (keep.get("px", 0) or 0)

        entry["candidates"].append({
            "new_image": new_local,
            "new_url": new_url,
            "new_pixels": new_pixels,
            "page_title": "", "domain": "", "query": "",
            "confidence": "low", "verified": False,
            "match_dist": case.get("dhash_dist"),
            "ref_pixels": entry["old_pixels"],
            "action": "replace_cover_demote",
            "target": entry["old_url"],
            "kind": "extra",
            "status": "pending",
            "strong": is_strong,
            "weak_reasons": reasons,
            "aspect_ratio": case.get("aspect_ratio"),
            "same_dims": bool(case.get("same_dims")),
            "source": "wave2-dudosos-promotion",
        })
        stats["queued_candidates"] += 1

    return list(entries.values()), stats


def _sorted_cases(cases: list[dict], images_dir: Path, bytes_cache: dict) -> list[dict]:
    """Fuertes primero, después débiles; dentro de cada grupo, dHash ascendente
    (mismo criterio de orden que las olas 2 y 3)."""
    decorated = []
    for c in cases:
        is_strong, _ = classify_strength(c, images_dir, bytes_cache)
        decorated.append((0 if is_strong else 1, c.get("dhash_dist", 99), c))
    decorated.sort(key=lambda t: (t[0], t[1]))
    return [c for _, _, c in decorated]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                     help="No escribe nada; solo reporta qué encolaría.")
    args = ap.parse_args()

    if not DUDOSOS_PATH.exists():
        print(f"No existe {DUDOSOS_PATH} — nada que encolar.")
        return 1

    raw = json.loads(DUDOSOS_PATH.read_text(encoding="utf-8"))
    pairs = raw.get("pairs", [])
    print(f"Pares en {DUDOSOS_PATH.name}: {len(pairs)}")

    items_by_slug = ew._load_items_by_slug(ITEMS_PATH)
    print(f"Items en catálogo: {len(items_by_slug)}")

    cases, find_stats = find_promotion_pairs(pairs, items_by_slug)
    print()
    print("=== Reconstrucción sobre el corpus actual ===")
    print(f"  Pares totales:                        {find_stats['total_pairs']}")
    print(f"  Casos de promoción (target==images[0]): {find_stats['promotion_candidates']}")
    print(f"  Saltados — item ya no existe:          {find_stats['skipped_item_missing']}")
    print(f"  Saltados — imagen ya no está en galería: {find_stats['skipped_image_gone']}")
    print(f"  No es caso de portada (target_idx!=0): {find_stats['not_a_cover_case']}")

    bytes_cache: dict[str, bytes] = {}
    cases = _sorted_cases(cases, IMAGES_DIR, bytes_cache)

    entries, build_stats = build_entries(cases, IMAGES_DIR)

    print()
    print("=== Resultado ===")
    print(f"  Candidatas encoladas (replace_cover_demote): {build_stats['queued_candidates']}")
    print(f"    — fuertes:                     {build_stats['strong']}")
    print(f"    — débiles:                     {build_stats['weak']}")
    print(f"  Saltados — target duplicado:      {build_stats['skipped_duplicate_target']}")
    print(f"  Entries (productos) afectadas:    {len(entries)}")

    if args.dry_run:
        print("\n[dry-run] No se escribió cover_preview.json.")
        return 0

    if not entries:
        print("\nNada para encolar — no se toca cover_preview.json.")
        return 0

    backup_and_rotate(PREVIEW_PATH, "enqueue-44-demote")
    fbc._PREVIEW_PATH = PREVIEW_PATH
    fbc._write_preview(entries, merge=True)
    print(f"\n✓ cover_preview.json actualizado (merge) con "
          f"{build_stats['queued_candidates']} candidatas replace_cover_demote "
          f"nuevas en {len(entries)} productos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
