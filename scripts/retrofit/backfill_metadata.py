#!/usr/bin/env python3
"""backfill_metadata.py — rellena metadata faltante de items.jsonl via detail-fetch.

Para cada item con campos vacíos (image_url, author, isbn, release_date),
si tiene una URL accesible, hace HTTP GET al detalle y rellena los campos
faltantes. NO sobreescribe valores ya presentes.

Uso:
    python scripts/retrofit/backfill_metadata.py                  # rellena todo
    python scripts/retrofit/backfill_metadata.py --dry-run        # solo cuenta
    python scripts/retrofit/backfill_metadata.py --only image_url # solo cover
    python scripts/retrofit/backfill_metadata.py --limit 50       # primeros 50 candidatos
    python scripts/retrofit/backfill_metadata.py --max-per-source 20  # max 20/source
    python scripts/retrofit/backfill_metadata.py --sleep 0.5      # 500ms entre requests
    python scripts/retrofit/backfill_metadata.py --skip-domain darkhorse.com  # excluir dominios

Campos targeteables: image_url, author, isbn, release_date.
Por defecto rellena todos los que estén vacíos.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import image_store  # type: ignore
from manga_watch import (  # type: ignore
    fetch_metadata_from_detail,
    make_session,
    backup_and_rotate,
    is_approved,
    write_lines_atomic,
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; manga-watch-backfill/1.0; "
    "+https://github.com/sergiomineiro/manga-watch)"
)

# Campos que pueden ser rellenados desde el detail-fetch.
BACKFILL_FIELDS = ("image_url", "author", "isbn", "release_date", "images")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--output", default="data/items.jsonl")
    parser.add_argument(
        "--only", choices=BACKFILL_FIELDS, default=None,
        help="Solo rellenar este campo (default: todos los vacíos)."
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Máximo de items a procesar (0 = sin límite)."
    )
    parser.add_argument(
        "--max-per-source", type=int, default=0,
        help="Máximo de items a procesar por source (0 = sin límite)."
    )
    parser.add_argument(
        "--sleep", type=float, default=0.3,
        help="Segundos entre requests (default: 0.3). Aplica entre lotes "
             "cuando hay --workers > 1."
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Paralelismo HTTP. Default 1 (secuencial). Para corpus grandes "
             "(--only images) usar 6-8."
    )
    parser.add_argument(
        "--per-host-limit", type=int, default=2,
        help="Máximo de requests concurrentes al mismo host. Protege a los "
             "retailers cuando varios items comparten dominio. Default 2."
    )
    parser.add_argument(
        "--connect-timeout", type=int, default=8,
        help="Timeout de conexión en segundos."
    )
    parser.add_argument(
        "--read-timeout", type=int, default=20,
        help="Timeout de lectura en segundos."
    )
    parser.add_argument(
        "--skip-domain", action="append", default=[],
        help="Dominios a saltar (puede repetirse). Match por substring."
    )
    parser.add_argument(
        "--skip-source", action="append", default=[],
        help="Sources a saltar (puede repetirse). Match por substring."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="No fetchea ni escribe; solo cuenta candidatos.")
    parser.add_argument("--include-approved", action="store_true",
                        help="Procesar también items aprobados (golden records). Por "
                             "defecto se saltean para no pisar metadata aprobada.")
    parser.add_argument(
        "--checkpoint-every", type=int, default=500,
        help="Cada N items procesados, escribe items.jsonl con el progreso "
             "actual. 0 = solo al final (riesgo de perder todo si killed). "
             "Default 500. Una corrida killed entre checkpoints solo pierde "
             "los últimos N items procesados; los anteriores se preservan."
    )
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    lines = src.read_text(encoding="utf-8").splitlines()
    items: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"_raw": line})  # preserve unparseable line as-is

    # Selección: items con URL y al menos un campo target vacío.
    target_fields = (args.only,) if args.only else BACKFILL_FIELDS

    # URLs no aptas para backfill de gallery: páginas que devuelven
    # MÚLTIPLES productos juntos (catálogo/índice) o que MÚLTIPLES items
    # de items.jsonl comparten (URLs sintéticas con query param para
    # distinguir). Re-fetchear cualquiera de estas con el extractor
    # genérico mezclaría imágenes de productos hermanos en un solo
    # item del JSONL.
    #
    # Caso "URL sintética": el wiki inventó un query param `?item=` /
    # `?bbm-entry=` para discriminar tomos hermanos en la misma página
    # real. Cada parser ya pobla `images[]` con la lógica correcta
    # por-tomo durante el scrape.
    #
    # Caso "URL de catálogo": un wiki guardó la URL del catálogo entero
    # (no del producto individual) como anclaje del item. Ej: el wiki
    # del calendario de listadomanga guarda `coleccion.php?id=N` que
    # lista TODOS los tomos; ahí no podemos disambiguar cuál tomo del
    # carrusel pertenece al calendario item.
    SYNTHETIC_URL_MARKERS = (
        "?item=",       # listadomanga-collections (Fase 2)
        "&item=",
        "?bbm-entry=",  # blogbbm Layout A/B/C
        "&bbm-entry=",
    )
    CATALOG_URL_MARKERS = (
        "listadomanga.es/coleccion.php",  # calendar items apuntan al índice
        "whakoom.com/ediciones/",         # índice de la edición (todos los tomos)
        "whakoom.com/publisher/",         # índice del publisher (todas las ediciones)
        "wwww.whakoom.com/ediciones/",
        "wwww.whakoom.com/publisher/",
    )

    def has_synthetic_url(item: dict) -> bool:
        url = item.get("url") or ""
        if any(m in url for m in SYNTHETIC_URL_MARKERS):
            return True
        if any(m in url for m in CATALOG_URL_MARKERS):
            return True
        return False

    def needs_backfill(item: dict) -> bool:
        if "_raw" in item or not item.get("url"):
            return False
        # Golden records: el owner aprobó esta card; no la re-fetcheamos.
        # Queda intacta en `items` y se reescribe sin cambios al final.
        if is_approved(item) and not args.include_approved:
            return False
        for f in target_fields:
            if f == "images":
                # Skip wikis con URL sintética: su `images[]` ya viene poblado
                # correctamente por el parser y un re-fetch mezclaría imágenes
                # de items hermanos en la misma página.
                if has_synthetic_url(item):
                    continue
                # Skip items ya procesados en una corrida previa de --only
                # images (con timestamp en `images_backfilled_at`). Cada item
                # se intenta exactamente una vez: si el detail-fetch confirmó
                # que es single-image, no vale la pena re-intentar. Para
                # forzar re-procesamiento (ej. tras mejoras al extractor),
                # eliminá el campo manualmente.
                if item.get("images_backfilled_at"):
                    continue
                # images[] cuenta como "necesita backfill" si tiene 0 o 1
                # entries (single-image que el extractor multi-image podría
                # expandir a galería completa). Si ya tiene 2+, asumimos
                # que una pasada previa lo procesó.
                if len(item.get("images") or []) < 2:
                    return True
            elif f == "image_url":
                # La portada es images[0] (única fuente de verdad), no un campo
                # top-level. "Falta portada" = images[] sin ninguna url.
                if not image_store.cover_url(item):
                    return True
            else:
                if not item.get(f):
                    return True
        return False

    skipped_approved = sum(
        1 for i in items
        if "_raw" not in i and is_approved(i) and not args.include_approved
    )

    candidates = [i for i in items if needs_backfill(i)]

    # Filtros adicionales: skip dominios / sources.
    def skipped(item: dict) -> bool:
        url = item.get("url", "")
        source = item.get("source", "")
        for d in args.skip_domain:
            if d in url:
                return True
        for s in args.skip_source:
            if s in source:
                return True
        return False

    candidates = [i for i in candidates if not skipped(i)]

    # Tope por source.
    if args.max_per_source > 0:
        per_source: Counter[str] = Counter()
        filtered: list[dict] = []
        for item in candidates:
            src_name = item.get("source", "")
            if per_source[src_name] < args.max_per_source:
                filtered.append(item)
                per_source[src_name] += 1
        candidates = filtered

    if args.limit > 0:
        candidates = candidates[: args.limit]

    print(f"[INFO] {len(items)} items totales en {src}")
    print(f"[INFO] {len(candidates)} candidatos a backfill " +
          (f"(campo: {args.only})" if args.only else "(todos los campos)"))
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados (usa --include-approved para incluirlos)")

    # Resumen por source (top 10)
    src_counter = Counter(c.get("source", "?") for c in candidates)
    if src_counter:
        print(f"\nTop 10 sources con backfill pendiente:")
        for source, n in src_counter.most_common(10):
            print(f"  {n:5d}  {source}")

    if args.dry_run or not candidates:
        if args.dry_run:
            print("\n[DRY-RUN] No se hicieron requests.")
        return 0

    # Fetch + merge
    session = make_session(args.user_agent)
    timeout = (args.connect_timeout, args.read_timeout)
    updated = 0
    fields_filled: Counter[str] = Counter()
    fetch_errors = 0

    # Per-host semáforo: protege a retailers cuando muchos items comparten
    # dominio (e.g. todas las URLs Amazon de SocialAnime, todas las
    # Mangavariant, etc.).
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    host_locks: dict[str, threading.Semaphore] = {}
    host_locks_mu = threading.Lock()

    def _sem_for(url: str) -> threading.Semaphore:
        host = urlparse(url).netloc.lower()
        with host_locks_mu:
            sem = host_locks.get(host)
            if sem is None:
                sem = threading.Semaphore(max(1, args.per_host_limit))
                host_locks[host] = sem
            return sem

    import datetime as _dt

    def _apply_metadata(item: dict, md: dict) -> bool:
        """Aplica metadata. Devuelve True si modificó algo. NO thread-safe;
        debe llamarse desde el thread principal después del fetch."""
        nonlocal updated
        changed = False
        for field in target_fields:
            if field == "images":
                new_imgs = md.get("images") or []
                existing = item.get("images") or []
                if len(new_imgs) > len(existing) and len(new_imgs) >= 2:
                    # images[0] de la metadata ya ES la portada (única fuente de
                    # verdad); reemplazamos la galería entera. No hay que tocar
                    # ningún campo top-level: la portada vive en images[0].
                    item["images"] = new_imgs
                    fields_filled[field] += 1
                    changed = True
                # SIEMPRE marcamos el item como "ya intentado" (con o sin
                # ganancia) para no re-procesarlo en futuras corridas. Si
                # el sitio genuinamente expone una sola imagen, el item no
                # mejorará y no tiene sentido pegarle de nuevo.
                item["images_backfilled_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
                changed = True
            elif field == "image_url":
                # La portada es images[0]: si falta, la sembramos desde la
                # metadata (sin local todavía; mirror_images.py lo espeja luego).
                if not image_store.cover_url(item) and md.get(field):
                    image_store.set_cover(item, md[field])
                    fields_filled[field] += 1
                    changed = True
            else:
                if not item.get(field) and md.get(field):
                    item[field] = md[field]
                    fields_filled[field] += 1
                    changed = True
        return changed

    def _fetch_one(item: dict) -> tuple[dict, dict, str]:
        """Worker thread-safe: solo hace HTTP. Devuelve (item, md, error_str)."""
        url = item["url"]
        try:
            sem = _sem_for(url)
            with sem:
                md = fetch_metadata_from_detail(url, session, timeout=timeout)
            return item, md, ""
        except Exception as e:
            return item, {}, str(e)[:80]

    dst = Path(args.output)

    def _write_items_jsonl(label: str = "") -> None:
        """Serializa la lista actual `items` a items.jsonl atómicamente.
        Llamable en mid-run (checkpoints) o al final."""
        out_lines: list[str] = []
        for it in items:
            if "_raw" in it:
                out_lines.append(it["_raw"])
            else:
                out_lines.append(json.dumps(it, ensure_ascii=False, sort_keys=True))
        write_lines_atomic(dst, out_lines)
        if label:
            print(f"  [CHECKPOINT] {label} — {len(out_lines)} items escritos a {dst}")

    if dst.exists():
        backup = backup_and_rotate(dst, "backfill")
        print(f"[OK] Backup guardado en {backup}")
    print()

    workers = max(1, int(args.workers))
    total = len(candidates)
    ckpt = max(0, int(args.checkpoint_every))

    def _maybe_checkpoint(done_count: int) -> None:
        if ckpt > 0 and done_count > 0 and done_count % ckpt == 0:
            _write_items_jsonl(label=f"{done_count}/{total} (updated={updated})")

    if workers == 1:
        for idx, item in enumerate(candidates, start=1):
            _, md, err = _fetch_one(item)
            if err:
                fetch_errors += 1
                print(f"  [{idx}/{total}] FETCH-ERR: {err}  ({item['url'][:70]})")
            else:
                if _apply_metadata(item, md):
                    updated += 1
            if idx % 25 == 0:
                print(f"  [{idx}/{total}] updated={updated}  errors={fetch_errors}")
            _maybe_checkpoint(idx)
            if args.sleep > 0 and idx < total:
                time.sleep(args.sleep)
    else:
        done = 0
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="backfill") as pool:
            futs = {pool.submit(_fetch_one, c): c for c in candidates}
            for fut in as_completed(futs):
                item, md, err = fut.result()
                done += 1
                if err:
                    fetch_errors += 1
                    if fetch_errors <= 50 or fetch_errors % 25 == 0:
                        print(f"  [{done}/{total}] FETCH-ERR: {err}  ({item['url'][:70]})")
                else:
                    if _apply_metadata(item, md):
                        updated += 1
                if done % 50 == 0:
                    print(f"  [{done}/{total}] updated={updated}  errors={fetch_errors}")
                _maybe_checkpoint(done)

    print(f"\n[OK] Procesados: {len(candidates)}")
    print(f"[OK] Items con cambios: {updated}")
    print(f"[OK] Errores HTTP: {fetch_errors}")
    print(f"\nCampos rellenados:")
    for field, n in fields_filled.most_common():
        print(f"  {field:15s}  {n}")

    if updated == 0:
        print("\n[OK] Nada que escribir.")
        return 0

    _write_items_jsonl()
    print(f"[OK] Escribí {dst} ({updated} items con backfill).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
