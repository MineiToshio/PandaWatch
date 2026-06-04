#!/usr/bin/env python3
"""mirror_images.py — backfill + GC del espejo local de portadas.

Image storage Fase 1, pasos restantes (ver "Image storage" en CLAUDE.md):

1. BACKFILL — para cada item de items.jsonl:
   - **Cover**: si tiene `image_url` y le falta `image_local`, descarga
     la portada a data/images/ y setea `image_local`.
   - **Gallery** (multi-imagen, 2026-05-26): para cada entry en
     `images[]` (idx > 0) que tenga `url` pero le falte
     `local`, descarga la imagen y setea `images[i].local`. El scrape
     (`manga_watch.py::mirror_candidate_images`) ya lo hace para items
     nuevos; este retrofit cubre el corpus histórico que recién recibió
     `images[]` poblado por `backfill_metadata.py --only images`.

2. GC mark-and-sweep — busca en data/images/ los archivos que NINGÚN
   item de items.jsonl referencia (orphans, típicamente de items que
   se quitaron del corpus) y los saca de la carpeta. El set de
   "referenciadas" incluye tanto `image_local` (cover) como cada
   `images[i].local` (gallery) — si solo mirara cover, los archivos
   de gallery caerían como orphans. Por defecto los manda a una
   cuarentena (data/images/_orphans/) — reversible; `--gc-delete` los
   borra de verdad.

Idempotente: re-correrlo no re-descarga imágenes ya en disco (el nombre
de archivo es determinístico). Seguro de correr en el overnight.

Uso:
    python scripts/retrofit/mirror_images.py                # backfill + GC
    python scripts/retrofit/mirror_images.py --dry-run      # solo reporta
    python scripts/retrofit/mirror_images.py --no-gc        # solo backfill
    python scripts/retrofit/mirror_images.py --gc-only      # solo GC
    python scripts/retrofit/mirror_images.py --workers 8    # paralelismo
    python scripts/retrofit/mirror_images.py --limit 100    # primeros 100 (test)
    python scripts/retrofit/mirror_images.py --gc-delete    # GC borra (no cuarentena)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import image_store  # type: ignore
from manga_watch import make_session, backup_and_rotate  # type: ignore

# MISMO User-Agent que usa el scraper (`manga_watch.py --user-agent`).
# Algunas fuentes (Manga-Sanctuary, p.ej.) sirven 404 a UAs desconocidos
# pero 200 a este — el corpus entero se scrapeó con él, así que las
# imágenes hay que pedirlas con el mismo UA o fallan.
DEFAULT_USER_AGENT = "manga-watch-personal/0.2 (+personal-use)"

# Subdirectorio de cuarentena para orphans (dentro de data/images/, así
# que el GC lo ignora al escanear — solo mira archivos top-level).
QUARANTINE_DIRNAME = "_orphans"


def _load_items(src: Path) -> list[dict]:
    items: list[dict] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"_raw": line})  # preserva la línea ininteligible
    return items


def _write_items(dst: Path, items: list[dict]) -> None:
    out_lines: list[str] = []
    for item in items:
        if "_raw" in item:
            out_lines.append(item["_raw"])
        else:
            out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
    dst.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def _run_backfill(
    items: list[dict],
    images_dir: Path,
    *,
    items_path: Path | None = None,
    workers: int,
    timeout: tuple[int, int],
    limit: int,
    user_agent: str,
    dry_run: bool,
) -> int:
    """Descarga las portadas + gallery faltantes. Devuelve cuántos items
    se actualizaron.

    Procesa dos clases de targets:
    1) **Cover**: items con `image_url` y sin `image_local` (portada = images[0]).
    2) **Gallery**: items con `images[]` (idx > 0) que tienen `url` pero
       no `local`. Una imagen gallery = un download.
    """
    # 1) Cover targets (comportamiento original).
    cover_targets = [
        it for it in items
        if "_raw" not in it and it.get("image_url") and not it.get("image_local")
    ]
    # 2) Gallery targets: por item, recopilo los índices de images[] que
    # son non-cover y todavía no tienen `local` poblado.
    gallery_targets: list[tuple[dict, int]] = []
    for it in items:
        if "_raw" in it:
            continue
        imgs = it.get("images") or []
        for idx, im in enumerate(imgs):
            if not isinstance(im, dict):
                continue
            if idx == 0:
                continue
            if im.get("url") and not im.get("local"):
                gallery_targets.append((it, idx))

    if limit > 0:
        # Limit aplica al total de URLs únicas para ser fair entre cover
        # y gallery (no caemos en un sesgo dispar).
        cover_targets = cover_targets[:limit]
        # Si todavía hay capacidad, gallery hasta completar limit.
        remaining = max(0, limit - len(cover_targets))
        gallery_targets = gallery_targets[:remaining]

    # Dedup por URL: muchos items comparten la misma portada (tomos de
    # una edición, cross-source). Bajamos cada URL única una sola vez
    # y mapeamos el filename a todos sus consumers.
    # consumers: list of either "cover_for(it)" or "gallery_for(it, idx)".
    by_url: dict[str, list[tuple[str, dict, int]]] = {}
    for it in cover_targets:
        by_url.setdefault(it["image_url"], []).append(("cover", it, -1))
    for it, idx in gallery_targets:
        url = it["images"][idx]["url"]
        by_url.setdefault(url, []).append(("gallery", it, idx))

    n_cover = len(cover_targets)
    n_gallery = len(gallery_targets)
    print(f"[BACKFILL] {n_cover} covers + {n_gallery} gallery sin local "
          f"({len(by_url)} URLs de imagen únicas).")
    if not by_url:
        return 0
    if dry_run:
        src_counter = Counter(t.get("source", "?") for t in cover_targets)
        if src_counter:
            print("[BACKFILL] Top sources pendientes (covers):")
            for source, n in src_counter.most_common(10):
                print(f"  {n:5d}  {source}")
        if n_gallery:
            g_counter = Counter(t.get("source", "?") for t, _ in gallery_targets)
            print("[BACKFILL] Top sources pendientes (gallery):")
            for source, n in g_counter.most_common(10):
                print(f"  {n:5d}  {source}")
        print("[DRY-RUN] No se descargó nada.")
        return 0

    session = make_session(user_agent)

    def _one(entry: tuple[str, list[tuple[str, dict, int]]]) -> tuple[list[tuple[str, dict, int]], str]:
        url, consumers = entry
        referer = consumers[0][1].get("url", "")
        filename = image_store.download_image(
            url, images_dir, session=session,
            timeout=timeout, referer=referer,
        )
        return consumers, filename

    updated = 0
    failed_urls = 0
    done = 0
    total = len(by_url)
    _FLUSH_EVERY = 200  # flush items.jsonl cada N URLs procesadas (no pérdida si se cancela)
    with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="mirror") as pool:
        for fut in as_completed(pool.submit(_one, e) for e in by_url.items()):
            consumers, filename = fut.result()
            done += 1
            if filename:
                for role, it, idx in consumers:
                    if role == "cover":
                        it["image_local"] = filename
                        imgs = it.get("images") or []
                        if imgs and imgs[0].get("url") == it["image_url"]:
                            imgs[0]["local"] = filename
                    else:
                        it["images"][idx]["local"] = filename
                updated += len(consumers)
            else:
                failed_urls += 1
            if done % _FLUSH_EVERY == 0:
                print(f"  [{done}/{total}] URLs procesadas, {updated} consumers atendidos", flush=True)
                # Flush periódico: no pérdida de datos si se cancela mid-run
                if items_path is not None and not dry_run:
                    _write_items(items_path, items)
                    print(f"  → flush parcial ({done} procesadas)", flush=True)

    print(f"[BACKFILL] {updated} consumers actualizados, {failed_urls} URLs "
          f"fallidas (esos items quedan con image_url/images[].url como fallback).")
    return updated


def _run_gc(
    items: list[dict],
    images_dir: Path,
    *,
    delete: bool,
    dry_run: bool,
) -> int:
    """Saca de images_dir los archivos que ningún item referencia.

    Devuelve la cantidad de orphans encontrados."""
    if not images_dir.exists():
        print("[GC] data/images/ no existe todavía — nada que limpiar.")
        return 0

    # Referenciadas = cover (`image_local`) + gallery (`images[i].local`) +
    # CADA fuente (`sources[i].image_local`, modelo 1-fila-por-producto). Sin
    # incluir sources[], el GC borraría fotos que una fuente sí usa (58 archivos
    # de ese tipo detectados el 2026-06-02). Si solo mirara cover, los de gallery
    # quedarían como orphans.
    referenced: set[str] = set()
    for it in items:
        if "_raw" in it:
            continue
        if it.get("image_local"):
            referenced.add(it["image_local"])
        for im in (it.get("images") or []):
            if isinstance(im, dict) and im.get("local"):
                referenced.add(im["local"])
        for s in (it.get("sources") or []):
            if isinstance(s, dict) and s.get("image_local"):
                referenced.add(s["image_local"])

    # cover_preview.json referencia archivos del espejo por `old_image`/
    # `new_image` (revisión de portadas mejoradas, web/cover-preview.html). NO
    # están en items.jsonl — si no se incluyen, el GC borra las originales y la
    # página de review queda con todas las fotos rotas (bug 2026-06-03).
    preview = images_dir.parent / "cover_preview.json"
    if preview.exists():
        try:
            for e in json.loads(preview.read_text(encoding="utf-8")):
                for k in ("old_image", "new_image"):
                    v = e.get(k)
                    if v and v != "[dry-run]":
                        referenced.add(v)
        except (ValueError, OSError):
            pass

    on_disk = [p for p in images_dir.iterdir() if p.is_file()]
    orphans = [p for p in on_disk if p.name not in referenced]

    freed = sum(p.stat().st_size for p in orphans)
    print(f"[GC] {len(on_disk)} archivos en disco, {len(referenced)} referenciados, "
          f"{len(orphans)} orphans ({freed / 1024 / 1024:.1f} MB).")
    if not orphans:
        return 0
    if dry_run:
        for p in orphans[:10]:
            print(f"  orphan: {p.name}")
        if len(orphans) > 10:
            print(f"  … y {len(orphans) - 10} más.")
        print("[DRY-RUN] No se movió ni borró nada.")
        return len(orphans)

    if delete:
        for p in orphans:
            p.unlink()
        print(f"[GC] {len(orphans)} archivos borrados.")
    else:
        quarantine = images_dir / QUARANTINE_DIRNAME
        quarantine.mkdir(parents=True, exist_ok=True)
        for p in orphans:
            p.replace(quarantine / p.name)
        print(f"[GC] {len(orphans)} archivos movidos a cuarentena {quarantine}/ "
              f"(borralos a mano cuando estés seguro, o re-corré con --gc-delete).")
    return len(orphans)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--output", default="data/items.jsonl")
    parser.add_argument("--workers", type=int, default=8,
                        help="Descargas en paralelo (default: 8).")
    parser.add_argument("--limit", type=int, default=0,
                        help="Máximo de items a backfillear (0 = sin límite). Útil para probar.")
    parser.add_argument("--no-gc", action="store_true",
                        help="Solo backfill, sin la pasada de garbage collection.")
    parser.add_argument("--gc-only", action="store_true",
                        help="Solo GC, sin descargar nada.")
    parser.add_argument("--gc-delete", action="store_true",
                        help="GC borra los orphans en vez de mandarlos a cuarentena.")
    parser.add_argument("--connect-timeout", type=int, default=10)
    parser.add_argument("--read-timeout", type=int, default=30)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--dry-run", action="store_true",
                        help="No descarga, no mueve, no escribe — solo reporta.")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    images_dir = src.parent / image_store.IMAGES_DIRNAME
    items = _load_items(src)
    print(f"[INFO] {len(items)} items en {src}")
    print(f"[INFO] espejo local: {images_dir}/")
    print()

    dst = Path(args.output)

    # Backup antes del loop — así los flushes incrementales tienen un punto de retorno
    if not args.dry_run and not args.gc_only:
        if dst.exists():
            backup = backup_and_rotate(dst, "mirror")
            print(f"[OK] Backup en {backup}")

    updated = 0
    if not args.gc_only:
        updated = _run_backfill(
            items, images_dir,
            items_path=dst if not args.dry_run else None,
            workers=args.workers,
            timeout=(args.connect_timeout, args.read_timeout),
            limit=args.limit,
            user_agent=args.user_agent,
            dry_run=args.dry_run,
        )
        print()

    if not args.no_gc:
        _run_gc(items, images_dir, delete=args.gc_delete, dry_run=args.dry_run)
        print()

    if args.dry_run:
        print("[DRY-RUN] Nada se escribió a disco.")
        return 0

    if updated == 0:
        print("[OK] items.jsonl sin cambios (no hubo backfill que escribir).")
        return 0

    # Flush final (cubre el último bloque y cualquier cambio del GC)
    _write_items(dst, items)
    print(f"[OK] Escribí {dst} — {updated} items con image_local nuevo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
