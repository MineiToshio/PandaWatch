#!/usr/bin/env python3
"""Separa el homónimo `series_key = "uzumaki"` (gotcha #194).

La clave agrupaba CUATRO items de DOS obras sin relación:

  | Item                          | Autor              | Tipo    | Obra real                  |
  |-------------------------------|--------------------|---------|----------------------------|
  | Uzumaki Deluxe 3 (Viz, US)    | —                  | manga   | *Uzumaki* de Junji Ito     |
  | Uzumaki (Planeta, ES)         | Junji Ito          | manga   | *Uzumaki* de Junji Ito     |
  | Uzumaki (Glénat, ES)          | Masashi Kishimoto  | artbook | artbook de NARUTO          |
  | UZUMAKI 岸本斉史画集 (JP)       | 岸本斉史            | artbook | artbook de NARUTO          |

El artbook se llama うずまき por el APELLIDO del protagonista de Naruto; nada
tiene que ver con el manga de terror. La colisión no la trajo el item nuevo de
2026-09-07: el de Glénat ya estaba mal agrupado desde antes.

Evidencia dura, del propio corpus (no se infiere nada):
  - Glénat: `description` = "Uzumaki, Libro de Ilustraciones de Naruto · 146
    páginas a color · Artbook".
  - JP: `description` = "UZUMAKI 岸本斉史画集 … 岸本斉史 ISBN：9784088737065 …
    集英社" (Shueisha, el 画集 de Kishimoto).

Los dos artbooks pasan a `series_key = "naruto"` (86 items ya en el corpus). Los
dos de Junji Ito se quedan en `uzumaki`. Después hay que correr
`enforce_listadomanga_rules.py`, que re-deriva edition_key/cluster_key/slug.

Uso:
    .venv/bin/python scripts/retrofit/fix_uzumaki_homonym_20260907.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from manga_watch import backup_and_rotate, write_items_atomic  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"

WRONG_SERIES_KEY = "uzumaki"
TARGET_SERIES_KEY = "naruto"
TARGET_SERIES_DISPLAY = "Naruto"

# Slugs verificados a mano contra su `description` (ver docstring). Denylist
# explícita en vez de heurística: la diferencia entre las dos obras no es
# deducible del título, que es idéntico.
NARUTO_ARTBOOK_SLUGS = {
    "uzumaki-glenat-artbook-es",
    "uzumaki-unknown-artbook-jp",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    items = [json.loads(line) for line in ITEMS.read_text().splitlines() if line.strip()]

    moved = 0
    for it in items:
        if it.get("slug") not in NARUTO_ARTBOOK_SLUGS:
            continue
        if (it.get("series_key") or "") != WRONG_SERIES_KEY:
            continue
        old_ek = it.get("edition_key") or ""
        it["series_key"] = TARGET_SERIES_KEY
        it["series_display"] = TARGET_SERIES_DISPLAY
        # El prefijo del edition_key tiene que seguir a la serie (invariante
        # EKPREFIX). El enforcer recalcula cluster_key y slug después.
        if old_ek.startswith(f"{WRONG_SERIES_KEY}-"):
            it["edition_key"] = f"{TARGET_SERIES_KEY}-{old_ek[len(WRONG_SERIES_KEY) + 1:]}"
        print(f"  {it.get('slug')}: {WRONG_SERIES_KEY} → {TARGET_SERIES_KEY}"
              f" | edition_key {old_ek!r} → {it.get('edition_key')!r}")
        moved += 1

    print(f"\nArtbooks de Naruto separados del homónimo: {moved}")
    remaining = [
        it for it in items if (it.get("series_key") or "") == WRONG_SERIES_KEY
    ]
    print(f"Items que quedan en '{WRONG_SERIES_KEY}' (Junji Ito): {len(remaining)}")
    for it in remaining:
        print(f"  {it.get('slug')} | {it.get('author') or '-'}")

    if args.dry_run:
        print("[DRY-RUN] No se escribió nada.")
        return 0
    if moved:
        backup_and_rotate(ITEMS, "uzumaki-homonym")
        write_items_atomic(ITEMS, items)
        print("items.jsonl actualizado. Correr enforce_listadomanga_rules.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
