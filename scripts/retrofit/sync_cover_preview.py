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

sys.path.insert(0, str(ROOT / "scripts" / "retrofit"))
import fetch_better_covers as fbc  # noqa: E402  (fuente única del umbral)

_SCRIPTS_DIR = ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    from manga_watch import backup_and_rotate  # noqa: E402
except ImportError:  # pragma: no cover
    from scripts.manga_watch import backup_and_rotate  # noqa: E402

# F16 — umbral ÚNICO de baja calidad: se IMPORTA del motor, no se redefine.
# La banda 90k-100k generaba churn (el motor buscaba candidatas que sync podaba
# al instante); por eso los tres consumidores comparten el mismo valor.
LOW_QUALITY_PX = fbc.LOW_QUALITY_PX  # mismo umbral del skill / panel de calidad

# Hallazgo #1 (auditoría 2026-07-08): si items.jsonl no cargó (ausente/vacío/
# truncado) o cargó con líneas corruptas, cada slug de la cola se ve como "item
# borrado" y sync_preview() la purga entera (Regla 1). Guard duro: abortar si
# el catálogo no parece sano ANTES de sincronizar/persistir.
MISSING_SLUG_RATIO_MAX = 0.20  # >20% de slugs sin match en el catálogo → abortar


# ---------------------------------------------------------------------------
# PIL (solo para recalcular píxeles del archivo local)
# ---------------------------------------------------------------------------

# Hallazgo #13 (perf): el panel llama sync_preview() en CADA GET /api/cover-preview
# (serve.py mantiene el proceso vivo entre requests), y sync_preview() abre con PIL
# CADA imagen de CADA galería del catálogo para recalcular píxeles. Cache en memoria
# por (ruta, mtime_ns) — se invalida sola si el archivo cambia (re-mirror/upgrade),
# y evita reabrir con PIL algo que no cambió desde el último request.
_PIXELS_CACHE: dict[str, tuple[int, int]] = {}


def _get_local_pixels(local: str | None, images_dir: Path) -> int:
    """Devuelve píxeles de la imagen local, 0 si no existe o no hay PIL."""
    if not local or local == "[dry-run]":
        return 0
    path = images_dir / local
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return 0
    key = str(path)
    cached = _PIXELS_CACHE.get(key)
    if cached is not None and cached[0] == mtime_ns:
        return cached[1]
    try:
        from PIL import Image  # type: ignore
        with Image.open(path) as img:
            w, h = img.size
            px = w * h
    except Exception:
        px = 0
    _PIXELS_CACHE[key] = (mtime_ns, px)
    return px


# ---------------------------------------------------------------------------
# Función principal importable
# ---------------------------------------------------------------------------

def _ledger_record_from_candidate(entry: dict, cand: dict, images_dir: Path) -> dict:
    """Arma el record del ledger de rechazos desde una candidata rechazada
    (mismo formato que apply_preview; a_hash del archivo local si existe)."""
    new_local = cand.get("new_image", "")
    a_hash_hex = None
    if new_local and new_local != "[dry-run]":
        f = images_dir / new_local
        if f.exists():
            try:
                a_hash_hex = fbc._ahash_hex(f.read_bytes())
            except OSError:
                a_hash_hex = None
    return {
        "slug": entry.get("slug", ""),
        # Identidad secundaria (hallazgo #7): url canónica del item, estable a
        # re-slugs → el veto sobrevive un generate_slugs. Mismo campo que escribe
        # apply_preview; is_rejected_candidate matchea por slug O por esta url.
        "url": entry.get("url", ""),
        "action": cand.get("action", "replace_cover"),
        "target": cand.get("target", ""),
        "rejected_url": cand.get("new_url", ""),
        "a_hash": a_hash_hex,
        "match_dist": cand.get("match_dist"),
        "ref_pixels": entry.get("old_pixels"),
        "new_pixels": cand.get("new_pixels"),
        "page_title": cand.get("page_title", ""),
        "query": cand.get("query", ""),
        "reason": cand.get("reject_reason"),
        "rejected_at": fbc._now_iso(),
    }


def _index_by_url(items_by_slug: dict[str, dict]) -> dict[str, dict]:
    """Índice url_canónica→item (identidad secundaria estable a re-slugs, #7).
    Sólo items con `url` no vacía; ante colisiones (poco probable) gana el último."""
    by_url: dict[str, dict] = {}
    for it in items_by_slug.values():
        u = it.get("url", "")
        if u:
            by_url[u] = it
    return by_url


def catalog_is_sane(
    preview: list[dict],
    items_by_slug: dict[str, dict],
    malformed_lines: int,
) -> tuple[bool, str]:
    """Hallazgo #1 (ALTA, auditoría 2026-07-08): guard duro ANTES de sincronizar.

    `sync_preview()` trata cualquier slug ausente de `items_by_slug` como "item
    borrado" (Regla 1: elimina la entry, sus approved-sin-aplicar se pierden, las
    rejected van al ledger). Si `items.jsonl` no cargó bien (falta, está vacío,
    quedó truncado a mitad de escritura, o el loader tragó líneas con
    `JSONDecodeError`), TODOS los slugs de la cola matchean como "borrados" y un
    solo request purga la cola entera. Este guard corre un pre-scan barato (sin
    tocar disco de nuevo) y aborta si el catálogo no parece sano.

    Devuelve (ok, motivo). `ok=False` ⇒ el caller NO debe llamar sync_preview()
    ni persistir nada (CLI: abortar; GET: degradar a solo-lectura).
    """
    if malformed_lines > 0:
        return False, (
            f"{malformed_lines} línea(s) de items.jsonl no parsearon como JSON "
            "(archivo truncado/corrupto)"
        )
    if not items_by_slug:
        if not preview:
            return True, ""  # nada que sincronizar, catálogo vacío es inofensivo
        return False, "items_by_slug vacío pero la cola tiene entries — catálogo no cargó"
    if preview:
        # Una entry cuenta como "match" si su slug existe O si su url canónica
        # (identidad secundaria, #7) rescata un item — así un re-slug masivo no
        # dispara el guard del 20% mientras las urls sigan resolviendo.
        items_by_url = _index_by_url(items_by_slug)
        missing = 0
        for e in preview:
            if e.get("slug", "") in items_by_slug:
                continue
            eu = e.get("url", "")
            if eu and eu in items_by_url:
                continue
            missing += 1
        ratio = missing / len(preview)
        if ratio > MISSING_SLUG_RATIO_MAX:
            return False, (
                f"{missing}/{len(preview)} entries de la cola ({ratio:.0%}) no matchean "
                f"ningún item del catálogo (ni por slug ni por url) — supera el "
                f"{MISSING_SLUG_RATIO_MAX:.0%}"
            )
    return True, ""


def sync_preview(
    preview: list[dict],
    items_by_slug: dict[str, dict],
    images_dir: Path,
    write_ledger: bool = True,
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
      - gc_orphans_removed:    archivos de candidatas podadas/dropeadas borrados del
                               espejo porque quedaron huérfanos (hallazgo #14) — sólo
                               si `write_ledger=True` (mismo flag que gatea el ledger;
                               ver nota en el parámetro).

    `write_ledger` controla TODOS los efectos secundarios reales (ledger append +
    GC de huérfanos), no sólo el ledger — así `revalidate_cover_preview.py` puede
    llamar esta función como probe puro (`write_ledger=False`) sobre una copia sin
    tocar disco.
    """
    stats: dict[str, int] = {
        "dropped_missing_item": 0,
        "dropped_empty": 0,
        "pruned_cover_ok": 0,
        "pruned_target_gone": 0,
        "pruned_target_ok": 0,
        "pruned_already_current": 0,
        "pixels_recomputed": 0,
        "gc_orphans_removed": 0,
        # Hallazgo #7 — identidad secundaria (url canónica, estable a re-slugs):
        "slug_migrated": 0,   # entry rescatada por url tras un re-slug (slug actualizado)
        "url_backfilled": 0,  # entry legacy sin url; se pobló al matchear por slug
    }

    # Índice url_canónica→item para rescatar entries cuyo slug cambió (#7).
    items_by_url = _index_by_url(items_by_slug)

    _REPLACE_COVER_ACTIONS = frozenset({
        "replace_cover",
        "replace_cover_demote",
        "replace_and_add",
    })

    result: list[dict] = []
    # Hallazgo #14: filenames de candidatas que dejaron de estar referenciadas por
    # la cola tras podar/dropear — se GC-ean al final SI no las usa nada más
    # (ni el catálogo real, ni otra entry/candidata que sobrevivió).
    _gc_candidates: list[str] = []

    for entry in preview:
        # Copia local mutable: la migración de slug / backfill de url no debe
        # tocar el `preview` de entrada (el caller compara synced vs preview).
        entry = dict(entry)
        slug = entry.get("slug", "")
        item = items_by_slug.get(slug)

        # Identidad secundaria (#7): el matching intenta slug primero; si el slug
        # ya no existe (típicamente tras un generate_slugs), busca por la url
        # canónica de la entry y, si la encuentra, MIGRA el slug de la entry al
        # nuevo en vez de podarla — así las decisiones del owner (approved/pending)
        # y el veto del ledger sobreviven el re-slug.
        if item is None:
            entry_url = entry.get("url", "")
            if entry_url:
                by_url = items_by_url.get(entry_url)
                if by_url is not None:
                    new_slug = by_url.get("slug", "")
                    if new_slug and new_slug != slug:
                        print(f"[sync-cover-preview] re-slug detectado: entry migrada "
                              f"{slug!r} → {new_slug!r} (url {entry_url[:60]})",
                              file=sys.stderr)
                        entry["slug"] = new_slug
                        slug = new_slug
                        stats["slug_migrated"] += 1
                    item = by_url
        elif not entry.get("url"):
            # Entry legacy sin url: backfill al vuelo cuando el slug SÍ matchea,
            # para que futuros re-slugs tengan la identidad secundaria disponible.
            item_url = item.get("url", "")
            if item_url:
                entry["url"] = item_url
                stats["url_backfilled"] += 1

        # Regla 1: item no existe (ni por slug ni por url) → eliminar. Antes de
        # dropear la entry, si contiene candidatas rechazadas, apendearlas al
        # ledger de rechazos para que no se re-propongan (ITEM 1).
        if item is None:
            if write_ledger:
                for cand in entry.get("candidates", []):
                    if cand.get("status") == "rejected":
                        fbc.ledger_append(
                            _ledger_record_from_candidate(entry, cand, images_dir)
                        )
            # Toda la entry (y sus candidatas, decididas o no) se va — sus archivos
            # descargados quedan huérfanos (hallazgo #14).
            for cand in entry.get("candidates", []):
                ni = cand.get("new_image")
                if ni:
                    _gc_candidates.append(ni)
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
                if cand.get("new_image"):
                    _gc_candidates.append(cand["new_image"])
                continue

            if action in _REPLACE_COVER_ACTIONS:
                # Poda 3b: portada actual ya en alta calidad → candidata innecesaria
                if new_old_pixels >= LOW_QUALITY_PX:
                    stats["pruned_cover_ok"] += 1
                    if cand.get("new_image"):
                        _gc_candidates.append(cand["new_image"])
                    continue

            elif action == "replace_image":
                target_url = cand.get("target", "")
                if target_url:
                    # Poda 3c: foto target ya no está en la galería
                    if target_url not in gallery_urls:
                        stats["pruned_target_gone"] += 1
                        if cand.get("new_image"):
                            _gc_candidates.append(cand["new_image"])
                        continue
                    # Poda 3d: foto target ya en alta calidad
                    px = gallery_px_by_url.get(target_url, 0)
                    if px >= LOW_QUALITY_PX:
                        stats["pruned_target_ok"] += 1
                        if cand.get("new_image"):
                            _gc_candidates.append(cand["new_image"])
                        continue

            # Recompute new_pixels desde el archivo YA NORMALIZADO en disco (AVIF ≤1600px),
            # así el panel muestra la resolución REAL que quedará guardada, no la del
            # original pre-resize. Solo es el campo de display; la decisión no se toca.
            ni = cand.get("new_image") or ""
            if ni and ni != "[dry-run]":
                real_px = _get_local_pixels(ni, images_dir)
                if real_px and real_px != cand.get("new_pixels"):
                    cand = {**cand, "new_pixels": real_px}
                    stats["pixels_recomputed"] += 1
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

    # Hallazgo #14: GC de archivos de candidatas huérfanas. SOLO corre si
    # write_ledger (mismo flag que gatea todo efecto secundario real — ver
    # docstring); nunca en un probe puro ni en dry-run. Antes de borrar,
    # verificamos que el filename no esté en uso por NADA más: ni el catálogo
    # real (items_by_slug — los archivos del espejo comparten el mismo
    # directorio `data/images/` que las descargas de candidatas, así que un
    # borrado ciego podría arrancarle la portada a un item real), ni otra
    # entry/candidata que sobrevivió la sincronización.
    if write_ledger and _gc_candidates:
        in_use: set[str] = set()
        for it in items_by_slug.values():
            for im in (it.get("images") or []):
                if isinstance(im, dict):
                    loc = im.get("local")
                    if loc:
                        in_use.add(loc)
            # sources[].image_local: la ref per-fuente también apunta a archivos
            # del MISMO espejo (~5.9k items del corpus la tienen poblada) — el GC
            # de mirror_images la protege y este debe hacer lo mismo (revisión del
            # orquestador 2026-07-08, misma clase de bug que el hallazgo #3 del
            # reporte de imágenes: la ref legacy per-source olvidada por un GC).
            for s in (it.get("sources") or []):
                if isinstance(s, dict):
                    sloc = s.get("image_local")
                    if sloc:
                        in_use.add(sloc)
        for e in result:
            old_img = e.get("old_image")
            if old_img:
                in_use.add(old_img)
            for c in e.get("candidates", []):
                ni = c.get("new_image")
                if ni:
                    in_use.add(ni)

        images_dir_resolved = images_dir.resolve() if images_dir.exists() else None
        removed: list[str] = []
        seen_gc: set[str] = set()
        for fn in _gc_candidates:
            if not fn or fn == "[dry-run]" or fn in seen_gc:
                continue
            seen_gc.add(fn)
            if fn in in_use:
                continue
            path = images_dir / fn
            if not path.exists():
                continue
            try:
                resolved = path.resolve()
            except OSError:
                continue
            # Guard de path-traversal: sólo borramos archivos DIRECTAMENTE bajo
            # images_dir (el espejo es flat), nunca fuera de ese directorio.
            if images_dir_resolved is None or resolved.parent != images_dir_resolved:
                continue
            try:
                path.unlink()
                removed.append(fn)
            except OSError:
                pass
        stats["gc_orphans_removed"] = len(removed)
        if removed:
            # stderr (no stdout): esta función corre también dentro del proceso
            # largo de serve.py en cada GET — un log de diagnóstico, no output de CLI.
            print(f"[sync-cover-preview] GC candidatas huérfanas: {len(removed)} "
                  f"archivo(s) borrados de {images_dir}: {', '.join(removed[:10])}"
                  + (" ..." if len(removed) > 10 else ""), file=sys.stderr)

    return result, stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_items_by_slug(items_path: Path) -> tuple[dict[str, dict], int]:
    """Devuelve (items_by_slug, malformed_lines). `malformed_lines` cuenta líneas
    no vacías que NO parsearon como JSON — el guard de catalog_is_sane() (#1)
    aborta si es >0, así un items.jsonl truncado a mitad de escritura nunca se
    lee silenciosamente como "catálogo válido pero más chico"."""
    items_by_slug: dict[str, dict] = {}
    malformed = 0
    if not items_path.exists():
        return items_by_slug, malformed
    with items_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                malformed += 1
                continue
            slug = item.get("slug", "")
            if slug:
                items_by_slug[slug] = item
    return items_by_slug, malformed


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

    items_by_slug, malformed = _load_items_by_slug(ITEMS_PATH)
    print(f"Items en catálogo: {len(items_by_slug)} (con slug)"
          + (f" — {malformed} línea(s) corrupta(s) ignoradas" if malformed else ""))

    # Hallazgo #1 (ALTA): abortar ANTES de sincronizar si el catálogo no parece
    # sano — evita que un items.jsonl ausente/truncado purgue la cola entera.
    ok, reason = catalog_is_sane(preview, items_by_slug, malformed)
    if not ok:
        print(f"\n[ABORT] catálogo no parece sano — no se sincroniza nada: {reason}")
        return 1

    # En dry-run no se toca el ledger de rechazos ni se hace GC (side-effect-free).
    synced, stats = sync_preview(preview, items_by_slug, IMAGES_DIR,
                                 write_ledger=not args.dry_run)

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
    print(f"  new_pixels recomputados (archivo real):{stats['pixels_recomputed']}")
    print(f"  Candidatas huérfanas borradas del espejo: {stats['gc_orphans_removed']}")
    print(f"  Entries migradas por re-slug (url):    {stats['slug_migrated']}")
    print(f"  Entries legacy con url backfilleada:   {stats['url_backfilled']}")
    print(f"  Entries resultado: {len(synced)} (de {len(preview)})")
    print(f"  Cambios: {total_pruned + total_dropped + stats['pixels_recomputed']} operaciones")

    if args.dry_run:
        print("\n[dry-run] No se escribió ningún archivo.")
        return 0

    # Hallazgo #4: la detección de "sin cambios" antes sólo miraba los counters
    # de poda + pixels_recomputed, así que un refresh de Regla 2 (old_url/
    # old_pixels/current_images/publisher/country stale, sin ninguna poda) NUNCA
    # se persistía y el CLI mentía "sin cambios". Comparación profunda en vez de
    # counters — igual que revalidate_cover_preview.py.
    if synced == preview:
        print("\nCola ya sincronizada — sin cambios.")
        return 0

    # Hallazgo #5: backup_and_rotate antes de mutar (antes este escritor no
    # tenía backup — los otros 2 escritores de cover_preview.json sí).
    backup_and_rotate(PREVIEW_PATH, "sync-cover-preview")
    _write_atomic(PREVIEW_PATH, synced)
    print(f"\n✓ cover_preview.json actualizado: {len(synced)} entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
