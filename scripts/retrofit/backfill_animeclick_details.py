#!/usr/bin/env python3
"""Backfill de campos faltantes en items AnimeClick (release_date, price, description).

Problema: los 1406 items de AnimeClick se ingirieron sin fetch_details=True,
así que tienen release_date/price/description vacíos. El bootstrap completo
perdería tiempo navegando 521 semanas de AJAX antes de hitear los detail pages.

Este script lee directamente los items AnimeClick de items.jsonl que tienen
release_date vacío y hace SOLO los fetches de detail pages necesarios,
con workers en paralelo.

Uso:
    python scripts/retrofit/backfill_animeclick_details.py [--workers N] [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

from manga_watch import append_jsonl  # type: ignore[import]
from wikis.animeclick import parse_detail_page, _inject_collector_hints  # type: ignore[import]

ITEMS_PATH = _ROOT / "data" / "items.jsonl"

UA = "Mozilla/5.0 (compatible; manga-watch-personal/0.2)"


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "it-IT,it;q=0.9",
        "Accept": "text/html,application/xhtml+xml,*/*",
    })
    return s


def _fetch_and_merge(
    item: dict,
    session: requests.Session,
    timeout: tuple[int, int] = (15, 45),
    sleep_seconds: float = 0.3,
) -> dict | None:
    """Fetcha el detail page y devuelve el item actualizado, o None si no hay nada nuevo."""
    url = item.get("url", "")
    if not url:
        return None

    try:
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        detail = parse_detail_page(resp.text, url)
    except requests.RequestException as exc:
        print(f"  WARN {url}: {exc}", flush=True)
        return None

    if not detail:
        return None

    updated = dict(item)
    changed = False

    # Aplicar campos del detail solo si el item los tiene vacíos
    for field in ("release_date", "price", "publisher"):
        if detail.get(field) and not item.get(field):
            updated[field] = detail[field]
            changed = True

    # description: inyectar hints del título + lo que llegue del detail
    if not item.get("description") or item.get("description") == "":
        raw_desc = detail.get("description") or ""
        title = updated.get("title") or ""
        new_desc = _inject_collector_hints(title, raw_desc)
        if new_desc:
            updated["description"] = new_desc
            changed = True

    # Actualizar image_url solo si el item no tenía ninguna
    if detail.get("image_url") and not item.get("image_url"):
        updated["image_url"] = detail["image_url"]
        changed = True

    return updated if changed else None


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill AnimeClick detail fields")
    ap.add_argument("--workers", type=int, default=4, help="Workers paralelos (default: 4)")
    ap.add_argument("--dry-run", action="store_true", help="No modifica items.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="Procesa solo los primeros N items (debug)")
    ap.add_argument("--sleep", type=float, default=0.3, help="Segundos entre fetches por worker")
    args = ap.parse_args()

    # 1. Leer items AnimeClick sin release_date
    print("Leyendo items.jsonl...", flush=True)
    targets: list[dict] = []
    with open(ITEMS_PATH) as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            source = item.get("source", "")
            if not (source.startswith("IT - AnimeClick") or "animeclick" in item.get("url", "").lower()):
                continue
            # Backfill si falta alguno de los campos clave
            if item.get("release_date") and item.get("price") and item.get("description"):
                continue
            targets.append(item)

    if args.limit:
        targets = targets[: args.limit]

    print(f"Items a backfill: {len(targets)}", flush=True)
    if not targets:
        print("Nada que hacer.")
        return

    # Estimar tiempo
    est_secs = len(targets) * (1.0 + args.sleep) / args.workers
    print(f"Estimado: ~{est_secs/60:.1f} min con {args.workers} worker(s)", flush=True)

    if args.dry_run:
        print("DRY RUN — no se modificará items.jsonl")

    # 2. Fetch en paralelo
    # Cada worker tiene su propia Session para evitar contención
    sessions = [_make_session() for _ in range(args.workers)]

    updated_items: list[dict] = []
    done = 0
    failed = 0

    def _task(item: dict, idx: int) -> dict | None:
        sess = sessions[idx % len(sessions)]
        return _fetch_and_merge(item, sess, sleep_seconds=args.sleep)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_task, item, i): item for i, item in enumerate(targets)}
        for fut in as_completed(futures):
            done += 1
            result = fut.result()
            if result is not None:
                updated_items.append(result)
            else:
                failed += 1
            if done % 50 == 0 or done == len(targets):
                print(
                    f"  {done}/{len(targets)} fetched, {len(updated_items)} con cambios, {failed} sin cambios/error",
                    flush=True,
                )

    print(f"\nTotal actualizados: {len(updated_items)}", flush=True)

    if args.dry_run:
        print("DRY RUN — preview de los primeros 5:")
        for item in updated_items[:5]:
            print(f"  {item.get('url','')[:70]}")
            print(f"    release_date={item.get('release_date','')}")
            print(f"    price={item.get('price','')}")
            print(f"    description={item.get('description','')[:80]}")
        return

    # 3. Upsert en items.jsonl
    print("Escribiendo en items.jsonl...", flush=True)
    append_jsonl(ITEMS_PATH, updated_items)
    print("Listo.", flush=True)

    # 4. Stats finales
    with open(ITEMS_PATH) as f:
        all_items = [json.loads(line) for line in f]

    ac_items = [
        i for i in all_items
        if i.get("source", "").startswith("IT - AnimeClick") or "animeclick" in i.get("url", "")
    ]
    print(f"\nEstado final AnimeClick ({len(ac_items)} items):")
    print(f"  release_date: {sum(1 for i in ac_items if i.get('release_date'))}/{len(ac_items)}")
    print(f"  price:        {sum(1 for i in ac_items if i.get('price'))}/{len(ac_items)}")
    print(f"  description:  {sum(1 for i in ac_items if i.get('description'))}/{len(ac_items)}")


if __name__ == "__main__":
    main()
