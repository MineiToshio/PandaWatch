#!/usr/bin/env python3
"""set_rarity.py — aplica el campo `rarity` a todos los items de items.jsonl.

Usa `derive_rarity_tier()` de manga_watch.py para clasificar cada item.
La función cubre los casos determinísticos (retailer_exclusive, BooksPrivilege,
keywords de edición numerada/firmada/evento). El resto queda en 'rare' como
default conservador — web search posterior puede elevarlo a 'common'.

Lo que SE recomputa:
    rarity  (solo si --force o el item no tiene rarity ya asignado)

Lo que NO se toca:
    Todos los demás campos. En particular respeta 'common' asignado por
    web search previo: nunca lo degrada a 'rare'.

Uso:
    python scripts/retrofit/set_rarity.py                  # solo items sin rarity
    python scripts/retrofit/set_rarity.py --force          # recalcula todos
    python scripts/retrofit/set_rarity.py --dry-run        # solo reporta drift
    python scripts/retrofit/set_rarity.py --input X --output Y
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import derive_rarity_tier, backup_and_rotate, is_approved  # type: ignore

RARITY_LABEL = {
    "common": "⬜ common",
    "rare": "🟦 rare",
    "super_rare": "🟪 super_rare",
    "ultra_rare": "🟨 ultra_rare",
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default="data/items.jsonl")
    p.add_argument("--output", default="data/items.jsonl")
    p.add_argument(
        "--dry-run", action="store_true",
        help="No escribe; sólo reporta qué cambiaría.",
    )
    p.add_argument(
        "--force", action="store_true",
        help="Recalcula rarity en TODOS los items, incluso los que ya tienen valor.",
    )
    p.add_argument("--include-approved", action="store_true",
                   help="Procesar también items aprobados (golden records). Por "
                        "defecto se saltean para no pisar metadata aprobada.")
    args = p.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    items: list[dict] = []
    with input_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    print(f"Items cargados: {len(items)}")

    before: Counter = Counter(i.get("rarity", "") for i in items)

    changed = 0
    skipped = 0
    skipped_approved = 0
    for item in items:
        # Golden records: el owner aprobó esta card; no recalculamos su rarity.
        # El item permanece sin cambios en la lista (in-place rewrite).
        if is_approved(item) and not args.include_approved:
            skipped_approved += 1
            continue

        old = item.get("rarity", "")

        # Sin --force: respetar el valor existente (incluido 'common' de web search).
        # Con --force: recalcular TODO, incluso 'common'. Las reglas de tirada única
        # (_SINGLE_RUN_KEYWORDS) pueden degradar un common incorrecto a rare cuando
        # el web search previo clasificó por disponibilidad momentánea en vez de por
        # probabilidad estructural de reimpresión.
        if old and not args.force:
            skipped += 1
            continue

        new = derive_rarity_tier(
            signal_types=item.get("signal_types") or [],
            source=item.get("source") or "",
            description=item.get("description") or "",
            title=item.get("title") or "",
            publisher=item.get("publisher") or "",
        )

        if new != old:
            if not args.dry_run:
                item["rarity"] = new
            changed += 1

    after: Counter = Counter(i.get("rarity", "") for i in items)

    print(f"Items con rarity ya asignado (saltados): {skipped}")
    if skipped_approved:
        print(f"Items aprobados (saltados; usa --include-approved para incluirlos): {skipped_approved}")
    print(f"Items {'que cambiarían' if args.dry_run else 'actualizados'}: {changed}")
    print()
    print("Distribución antes:")
    for r, n in sorted(before.items()):
        print(f"  {RARITY_LABEL.get(r, r or '(vacío)'):20s} {n:6d}")
    print()

    if args.dry_run:
        # Recalcular distribución simulada para el reporte
        sim: Counter = Counter()
        for item in items:
            old = item.get("rarity", "")
            if is_approved(item) and not args.include_approved:
                sim[old] += 1
            elif old and not args.force:
                sim[old] += 1
            else:
                sim[derive_rarity_tier(
                    signal_types=item.get("signal_types") or [],
                    source=item.get("source") or "",
                    description=item.get("description") or "",
                    title=item.get("title") or "",
                    publisher=item.get("publisher") or "",
                )] += 1
        print("Distribución simulada (dry-run):")
        for r, n in sorted(sim.items()):
            print(f"  {RARITY_LABEL.get(r, r or '(vacío)'):20s} {n:6d}")
        print("\n(dry-run) No se escribió nada.")
        return 0

    print("Distribución después:")
    for r, n in sorted(after.items()):
        print(f"  {RARITY_LABEL.get(r, r or '(vacío)'):20s} {n:6d}")

    if changed == 0:
        print("\nNada que escribir.")
        return 0

    if output_path == input_path:
        backup_and_rotate(input_path, "set-rarity")

    tmp = output_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    tmp.replace(output_path)
    print(f"\n✓ {output_path} actualizado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
