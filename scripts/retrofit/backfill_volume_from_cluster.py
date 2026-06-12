#!/usr/bin/env python3
"""backfill_volume_from_cluster.py — rellena `volume` desde el cluster_key para
items lmc que tienen el número de volumen en la clave pero vacío en el campo.

Caso real (gotcha #60): "The Promised Neverland 13 Edición Especial" tiene
cluster_key `lmc:2857:special:13` pero `volume: ""` porque `_extract_volume`
no capturaba números antes de calificadores de edición ("Edición Especial",
"Variant", etc.). Fix upstream en listadomanga_collections.py + _extract_volume;
este script repara los items existentes.

Solo toca items lmc donde `volume == ""` y el vol-segment del cluster_key es
un número real (no "0" ni vacío) — los "0" son artbooks/boxsets sin número
legítimo y NO deben tocarse.

Uso:
    python scripts/retrofit/backfill_volume_from_cluster.py           # aplica
    python scripts/retrofit/backfill_volume_from_cluster.py --dry-run # solo cuenta
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import backup_and_rotate  # type: ignore

# cluster_key lmc: lmc:<cole>:<kind>:<vol>
# Solo nos interesan los que tienen un vol numérico real (no "0" ni vacío).
# "0" es el placeholder de _make_synthetic_url cuando el item no tiene volumen —
# no se propaga como volumen real.
_LMC_REAL_VOL = re.compile(r"^lmc:\d+:[a-z]+:(\d+(?:\.\d+)?)$")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default="data/items.jsonl")
    p.add_argument("--output", default="data/items.jsonl")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    items: list[dict] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"_raw": line})

    print(f"[INFO] {len(items)} items en {src}")

    changed = 0
    for it in items:
        if "_raw" in it:
            continue
        if it.get("volume"):  # ya tiene volumen — no tocar
            continue
        ck = it.get("cluster_key", "")
        m = _LMC_REAL_VOL.match(ck)
        if not m:
            continue
        vol = m.group(1)
        if vol == "0":  # placeholder: item sin volumen real, no tocar
            continue
        if args.dry_run:
            print(f"  [DRY] {ck!r} → volume={vol!r}  {it.get('title','')[:60]}")
        else:
            it["volume"] = vol
        changed += 1

    print(f"[INFO] items {'que se actualizarían' if args.dry_run else 'actualizados'}: {changed}")

    if args.dry_run or not changed:
        return 0

    dest = Path(args.output)
    backup_and_rotate(dest, "backfill_volume_from_cluster")
    with dest.open("w", encoding="utf-8") as fh:
        for it in items:
            if "_raw" in it:
                fh.write(it["_raw"] + "\n")
            else:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")

    print(f"[OK] guardado en {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
