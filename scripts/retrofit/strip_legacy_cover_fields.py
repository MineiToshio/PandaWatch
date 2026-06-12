#!/usr/bin/env python3
"""strip_legacy_cover_fields.py — migración: elimina image_url/image_local top-level.

Migración one-shot del modelo de portada (decisión 2026-06-09): los campos
top-level `image_url`/`image_local` del item dejan de existir; `images[0]` pasa
a ser la ÚNICA fuente de verdad de la portada. Cada entry de `images[]` lleva
`url` (remota) + `local` (filename del espejo en data/images/).

Qué hace por cada item (sin red — solo reestructura el JSONL):
  1. Si NO tiene `images[]` pero sí `image_url` top-level → siembra
     `images[0] = {url, local, kind:gallery, description:""}`.
  2. Si tiene `images[]` y `images[0].url` está vacío → lo llena desde
     `image_url`/`image_local` top-level.
  3. Si `images[0].local` está vacío PERO el top-level `image_local` apunta a un
     archivo que EXISTE en data/images/ → lo backfillea en `images[0].local`
     (rescata el espejo de las ~810 filas drifteadas sin re-descargar).
  4. Elimina las keys top-level `image_url`/`image_local` del item.

NO toca los campos per-fuente de `sources[]` (cada entry conserva su propio
image_url/image_local — es otro layer).

Idempotente: correrlo dos veces no cambia nada (las keys ya no están). Para
llenar los `local` de TODAS las fotos (galería incluida) y los que no se
pudieron rescatar, correr después `retrofit/mirror_images.py`.

Uso:
    python scripts/retrofit/strip_legacy_cover_fields.py --dry-run   # solo cuenta
    python scripts/retrofit/strip_legacy_cover_fields.py             # aplica (con backup)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import backup_and_rotate  # type: ignore
import image_store  # type: ignore


def _migrate_item(item: dict, images_dir: Path, stats: Counter) -> bool:
    """Reestructura un item in-place. Devuelve True si cambió algo."""
    iu = item.pop("image_url", None)
    il = item.pop("image_local", None)
    if iu is not None:
        stats["had_image_url"] += 1
    if il is not None:
        stats["had_image_local"] += 1
    iu = (iu or "").strip()
    il = (il or "").strip()

    imgs = item.get("images")
    if not isinstance(imgs, list):
        imgs = []

    if not imgs:
        if iu:
            item["images"] = [{
                "url": iu, "local": il, "kind": "gallery", "description": "",
            }]
            stats["seeded_images0"] += 1
    else:
        first = imgs[0] if isinstance(imgs[0], dict) else None
        if first is not None:
            if not first.get("url") and iu:
                first["url"] = iu
                stats["filled_url"] += 1
            if not first.get("local") and il and (images_dir / il).is_file():
                first["local"] = il
                stats["rescued_local"] += 1

    # popear las keys ya cuenta como cambio si existían
    return iu is not None or il is not None or "images" in item


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe nada; solo reporta qué se migraría.")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    images_dir = src.parent / image_store.IMAGES_DIRNAME

    lines = src.read_text(encoding="utf-8").splitlines()
    out_lines: list[str] = []
    stats: Counter = Counter()
    changed = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            out_lines.append(line)
            continue
        try:
            item = json.loads(stripped)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue
        had = ("image_url" in item) or ("image_local" in item)
        _migrate_item(item, images_dir, stats)
        if had:
            changed += 1
        out_lines.append(json.dumps(item, ensure_ascii=False))

    total = sum(1 for ln in lines if ln.strip())
    print(f"[INFO] items totales:            {total}")
    print(f"[INFO] con image_url top-level:  {stats['had_image_url']}")
    print(f"[INFO] con image_local top-level:{stats['had_image_local']}")
    print(f"[INFO] images[0] sembrado:       {stats['seeded_images0']}")
    print(f"[INFO] images[0].url llenado:    {stats['filled_url']}")
    print(f"[INFO] images[0].local rescatado:{stats['rescued_local']}")
    print(f"[INFO] filas modificadas:        {changed}")

    if args.dry_run:
        print("\n[DRY-RUN] no se escribió nada.")
        return 0

    if changed == 0:
        print("\n[OK] nada que migrar (ya está en el modelo nuevo).")
        return 0

    backup = backup_and_rotate(src, "strip-legacy-cover")
    print(f"\n[OK] Backup guardado en {backup}")
    src.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"[OK] {src} migrado: image_url/image_local top-level eliminados.")
    print("[NEXT] correr retrofit/mirror_images.py para llenar los `local` "
          "faltantes (galería + portadas no rescatadas).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
