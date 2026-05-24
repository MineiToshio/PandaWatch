#!/usr/bin/env python3
"""mirror_images.py — backfill + GC del espejo local de portadas.

Image storage Fase 1, pasos restantes (ver "Image storage" en CLAUDE.md):

1. BACKFILL — para cada item de items.jsonl con `image_url` y sin
   `image_local`, descarga la portada a data/images/ y setea
   `image_local`. El scrape (`manga_watch.py`) ya hace esto para items
   nuevos; este retrofit cubre el corpus histórico (los items previos
   a la Fase 1, que tienen `image_local` vacío).

2. GC mark-and-sweep — busca en data/images/ los archivos que NINGÚN
   item de items.jsonl referencia (orphans, típicamente de items que
   se quitaron del corpus) y los saca de la carpeta. Por defecto los
   manda a una cuarentena (data/images/_orphans/) — reversible;
   `--gc-delete` los borra de verdad.

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
from manga_watch import make_session  # type: ignore

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
    workers: int,
    timeout: tuple[int, int],
    limit: int,
    user_agent: str,
    dry_run: bool,
) -> int:
    """Descarga las portadas faltantes. Devuelve cuántos items se actualizaron."""
    targets = [
        it for it in items
        if "_raw" not in it and it.get("image_url") and not it.get("image_local")
    ]
    if limit > 0:
        targets = targets[:limit]

    # Dedup por image_url: muchos items comparten la misma portada (tomos
    # de una misma edición, mismo cover cross-source). Bajamos cada URL
    # única una sola vez y mapeamos el filename a todos sus items.
    by_url: dict[str, list[dict]] = {}
    for it in targets:
        by_url.setdefault(it["image_url"], []).append(it)

    print(f"[BACKFILL] {len(targets)} items sin image_local "
          f"({len(by_url)} URLs de imagen únicas).")
    if not by_url:
        return 0
    if dry_run:
        src_counter = Counter(t.get("source", "?") for t in targets)
        print("[BACKFILL] Top sources pendientes:")
        for source, n in src_counter.most_common(10):
            print(f"  {n:5d}  {source}")
        print("[DRY-RUN] No se descargó nada.")
        return 0

    session = make_session(user_agent)

    def _one(entry: tuple[str, list[dict]]) -> tuple[list[dict], str]:
        url, group = entry
        filename = image_store.download_image(
            url, images_dir, session=session,
            timeout=timeout, referer=group[0].get("url", ""),
        )
        return group, filename

    updated = 0
    failed_urls = 0
    done = 0
    total = len(by_url)
    with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="mirror") as pool:
        for fut in as_completed(pool.submit(_one, e) for e in by_url.items()):
            group, filename = fut.result()
            done += 1
            if filename:
                for it in group:
                    it["image_local"] = filename
                updated += len(group)
            else:
                failed_urls += 1
            if done % 200 == 0:
                print(f"  [{done}/{total}] URLs procesadas, {updated} items con portada")

    print(f"[BACKFILL] {updated} items con image_local, {failed_urls} URLs "
          f"fallidas (esos items quedan con image_url como fallback).")
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

    referenced = {
        it["image_local"] for it in items
        if "_raw" not in it and it.get("image_local")
    }
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

    updated = 0
    if not args.gc_only:
        updated = _run_backfill(
            items, images_dir,
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

    dst = Path(args.output)
    backup = dst.with_suffix(dst.suffix + ".pre-mirror-bak")
    if dst.exists():
        backup.write_text(dst.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[OK] Backup en {backup}")
    _write_items(dst, items)
    print(f"[OK] Escribí {dst} — {updated} items con image_local nuevo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
