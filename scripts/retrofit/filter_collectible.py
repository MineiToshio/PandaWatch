#!/usr/bin/env python3
"""filter_collectible.py — aplica el gate `is_collectible_edition` a items existentes.

El producto del proyecto son SOLO ediciones especiales, variantes, coleccionistas,
artbooks, fanbooks, magazines de serie y tomos con extras de primera edición.
Este script revisa items.jsonl y mueve los "tomos regulares sin nada especial"
a un archivo separado para revisión.

Uso:
    python scripts/retrofit/filter_collectible.py                   # ejecuta
    python scripts/retrofit/filter_collectible.py --dry-run         # solo cuenta
    python scripts/retrofit/filter_collectible.py --input X --kept-output Y --rejected-output Z

Por defecto:
    - keeps items en data/items.jsonl
    - rejected items en data/diagnostics/items.non_collectible.jsonl (para revisar)
    - backup en data/backups/items.jsonl/items.jsonl.pre-collectible-bak (rotación max 3)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
_ROOT = _SCRIPTS.parent  # manga-watch/
# Asegurar que tanto la raíz como scripts/ están en el path, con scripts/
# primero para que `import manga_watch` resuelva scripts/manga_watch.py (el
# módulo real) en lugar del wrapper de raíz manga_watch.py.
for _p in (str(_SCRIPTS), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Importar explícitamente desde scripts.manga_watch para evitar que pytest
# (que ya tiene la raíz en sys.path) resuelva el wrapper manga_watch.py raíz.
try:
    from scripts.manga_watch import (  # type: ignore  # cuando se importa como paquete
        is_collectible_edition,
        derive_product_type,
        detect_signals,
        backup_and_rotate,
        is_approved,
    )
except ImportError:
    from manga_watch import (  # type: ignore  # cuando se ejecuta directamente
        is_collectible_edition,
        derive_product_type,
        detect_signals,
        backup_and_rotate,
        is_approved,
    )


def should_reject(item: dict, is_coll: bool, reason: str) -> bool:
    """Decide si un item debe ser rechazado, respetando el estado de estandarización.

    Post-estandarización, el texto del título ya no porta las frases raw que
    detect_signals necesita ("Limited Edition", "Collector", etc.); las señales
    reales ya fueron derivadas y validadas por el skill. Por eso, para items con
    `standardized_at` truthy, sólo aplicamos los gates duros de is_collectible_edition
    (junk de título y umbrella_magazine). Si el gate devuelve regular_tomo sobre un
    item estandarizado, lo conservamos: la verdad vive en la etiqueta de edición
    ya derivada, no en el texto crudo.
    """
    if is_coll:
        return False  # el gate lo aprobó → conservar siempre

    # Gates duros que aplican independientemente del estado de estandarización.
    HARD_REASONS = {"title_too_short", "title_junk_discount", "title_junk_generic",
                    "umbrella_magazine", "no_title"}
    if reason in HARD_REASONS:
        return True  # rechazar siempre, estandarizado o no

    # regular_tomo sobre un item estandarizado: la señal real ya fue validada
    # por el skill; conservar.
    if reason == "regular_tomo" and item.get("standardized_at"):
        return False

    return True  # cualquier otro reason sobre item no estandarizado → rechazar


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--kept-output", default="data/items.jsonl")
    parser.add_argument("--rejected-output", default="data/diagnostics/items.non_collectible.jsonl")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe nada; solo reporta cuántos se filtrarían.")
    parser.add_argument("--include-approved", action="store_true",
                        help="Procesar también items aprobados (golden records). Por "
                             "defecto se saltean para no pisar metadata aprobada.")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    lines = src.read_text(encoding="utf-8").splitlines()
    kept_lines: list[str] = []
    rejected_lines: list[str] = []
    skipped_approved = 0
    kept_standardized = 0
    reason_counter: Counter[str] = Counter()
    sample_rejected: list[tuple[str, str, str]] = []
    sample_kept: list[tuple[str, str, str]] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            kept_lines.append(line)
            continue

        # Golden records: el owner aprobó esta card; SIEMPRE se conserva.
        if is_approved(item) and not args.include_approved:
            skipped_approved += 1
            kept_lines.append(line)
            continue

        title = item.get("title", "")
        description = item.get("description", "")
        tags = item.get("tags", []) or []
        # Re-computamos signal_types y product_type desde title+description
        # porque los valores persistidos en items.jsonl pueden venir de runs
        # previos con bugs de contaminación (source name → box_set, etc.).
        _, _, fresh_signal_types = detect_signals(f"{title}\n{description}")
        fresh_product_type = derive_product_type(title, description, fresh_signal_types)
        is_coll, reason = is_collectible_edition(
            title, description, fresh_signal_types, fresh_product_type,
            tags=tags, isbn=item.get("isbn", "") or "",
            url=item.get("url", "") or "",
        )

        reject = should_reject(item, is_coll, reason)

        if not reject:
            kept_lines.append(line)
            # bucket = parte antes del primer ':'
            bucket = reason.split(":", 1)[0]
            if reason == "regular_tomo" and item.get("standardized_at"):
                kept_standardized += 1
            if len(sample_kept) < 8:
                sample_kept.append((reason, title[:90], item.get("source", "")))
        else:
            rejected_lines.append(line)
            bucket = reason.split(":", 1)[0]
            reason_counter[bucket] += 1
            if len(sample_rejected) < 15:
                sample_rejected.append((reason, title[:90], item.get("source", "")))

    total = len(kept_lines) + len(rejected_lines)
    print(f"[INFO] {total} items totales")
    print(f"[INFO] {len(kept_lines)} coleccionables (kept)  {len(kept_lines)*100//max(total,1)}%")
    print(f"[INFO] {len(rejected_lines)} tomos regulares (rejected)  {len(rejected_lines)*100//max(total,1)}%")
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados (kept; usa --include-approved para incluirlos)")
    if kept_standardized:
        print(f"[INFO] {kept_standardized} kept_standardized: regular_tomo ignorado porque el item ya tiene standardized_at")
    print(f"\nMotivos de descarte:")
    for bucket, n in reason_counter.most_common():
        print(f"  {bucket:25s}  {n}")

    if sample_kept:
        print(f"\nMuestra de KEPT (coleccionables):")
        for reason, title, source in sample_kept:
            print(f"  [{reason}]")
            print(f"    {title}")
            print(f"    ← {source}")

    if sample_rejected:
        print(f"\nMuestra de REJECTED (tomos regulares):")
        for reason, title, source in sample_rejected:
            print(f"  [{reason}]")
            print(f"    {title}")
            print(f"    ← {source}")

    if args.dry_run:
        print("\n[DRY-RUN] No se escribió ningún archivo.")
        return 0

    if not rejected_lines:
        print("\n[OK] Nada que filtrar.")
        return 0

    kept_path = Path(args.kept_output)
    rejected_path = Path(args.rejected_output)
    if kept_path.exists() and kept_path == src:
        backup = backup_and_rotate(kept_path, "collectible")
        print(f"\n[OK] Backup guardado en {backup}")

    kept_path.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")
    print(f"[OK] Escribí {kept_path} con {len(kept_lines)} coleccionables.")

    rejected_path.write_text("\n".join(rejected_lines) + "\n", encoding="utf-8")
    print(f"[OK] Escribí {rejected_path} con {len(rejected_lines)} no-coleccionables.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
