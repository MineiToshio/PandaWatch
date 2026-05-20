#!/usr/bin/env python3
"""backfill_metadata.py — rellena metadata faltante de items.jsonl via detail-fetch.

Para cada item con campos vacíos (image_url, author, isbn, release_date, price),
si tiene una URL accesible, hace HTTP GET al detalle y rellena los campos
faltantes. NO sobreescribe valores ya presentes.

Uso:
    python scripts/backfill_metadata.py                  # rellena todo
    python scripts/backfill_metadata.py --dry-run        # solo cuenta
    python scripts/backfill_metadata.py --only image_url # solo cover
    python scripts/backfill_metadata.py --limit 50       # primeros 50 candidatos
    python scripts/backfill_metadata.py --max-per-source 20  # max 20/source
    python scripts/backfill_metadata.py --sleep 0.5      # 500ms entre requests
    python scripts/backfill_metadata.py --skip-domain darkhorse.com  # excluir dominios

Campos targeteables: image_url, author, isbn, release_date, price.
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

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import fetch_metadata_from_detail, make_session  # type: ignore

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; manga-watch-backfill/1.0; "
    "+https://github.com/sergiomineiro/manga-watch)"
)

# Campos que pueden ser rellenados desde el detail-fetch.
BACKFILL_FIELDS = ("image_url", "author", "isbn", "release_date", "price")


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
        help="Segundos entre requests (default: 0.3)."
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

    def needs_backfill(item: dict) -> bool:
        if "_raw" in item or not item.get("url"):
            return False
        return any(not item.get(f) for f in target_fields)

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
    by_index = {id(item): idx for idx, item in enumerate(items)}

    print()
    for idx, item in enumerate(candidates, start=1):
        url = item["url"]
        try:
            md = fetch_metadata_from_detail(url, session, timeout=timeout)
        except Exception as e:
            fetch_errors += 1
            print(f"  [{idx}/{len(candidates)}] FETCH-ERR: {e!s:.60}  ({url[:70]})")
            continue

        # Solo rellena campos vacíos del item, no sobreescribe lo ya presente.
        changed = False
        for field in target_fields:
            if not item.get(field) and md.get(field):
                item[field] = md[field]
                fields_filled[field] += 1
                changed = True
        if changed:
            updated += 1

        if idx % 25 == 0:
            print(f"  [{idx}/{len(candidates)}] updated={updated}  errors={fetch_errors}")

        if args.sleep > 0 and idx < len(candidates):
            time.sleep(args.sleep)

    print(f"\n[OK] Procesados: {len(candidates)}")
    print(f"[OK] Items con cambios: {updated}")
    print(f"[OK] Errores HTTP: {fetch_errors}")
    print(f"\nCampos rellenados:")
    for field, n in fields_filled.most_common():
        print(f"  {field:15s}  {n}")

    if updated == 0:
        print("\n[OK] Nada que escribir.")
        return 0

    dst = Path(args.output)
    backup = dst.with_suffix(dst.suffix + ".pre-backfill-bak")
    if dst.exists():
        backup.write_text(dst.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"\n[OK] Backup guardado en {backup}")

    out_lines: list[str] = []
    for item in items:
        if "_raw" in item:
            out_lines.append(item["_raw"])
        else:
            out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
    dst.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"[OK] Escribí {dst} con {len(out_lines)} items ({updated} con backfill).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
