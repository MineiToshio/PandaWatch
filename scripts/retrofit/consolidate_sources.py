#!/usr/bin/env python3
"""Consolida items.jsonl al modelo 1-FILA-POR-PRODUCTO con `sources[]` guardado.

Decisión del owner (2026-06-02): un producto físico (cluster) debe ser UNA sola
fila en items.jsonl, con un array `sources[]` que liste todas las fuentes donde
se encontró (cada una con su URL, precio, país, stock, etc.). Antes el repo
guardaba 1 fila por URL y fusionaba al mostrar — eso generaba filas duplicadas
del mismo producto y fue la raíz de los bugs de fotos (cada fila tenía sus
imágenes y había que unirlas al leer).

Este retrofit agrupa por `cluster_key` y:
  - Cluster con varias filas → las fusiona en UNA (la más completa como base),
    con `sources[]` = union de las fuentes, imágenes union (portada canónica
    primera) y extras union. Reusa `build_web._merged_canonical` para que el
    resultado sea idéntico a lo que la presentación ya producía.
  - Cluster de 1 fila → se le agrega `sources[]` = [self] (uniformidad: TODA
    fila tiene su array de fuentes).
  - Clusters `url:` (standalone) → quedan como 1 fila cada uno (son 1 producto
    por URL por definición).

Idempotente: re-correrlo no cambia nada (el merge une `sources[]` ya guardado).
Backup vía backup_and_rotate. Es el paso de datos del refactor; la ingesta
(`append_jsonl`) deduplica por producto para que no se regeneren duplicados.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from manga_watch import backup_and_rotate, consolidate_by_cluster, derive_cluster_key  # noqa: E402
except ImportError:  # pragma: no cover
    from scripts.manga_watch import backup_and_rotate, consolidate_by_cluster, derive_cluster_key  # noqa: E402

DEFAULT_ITEMS = _SCRIPTS_DIR.parent / "data" / "items.jsonl"


def _cluster_key(it: dict) -> str:
    return it.get("cluster_key") or derive_cluster_key(it)


def consolidate(rows: list[dict]) -> tuple[list[dict], dict]:
    # Delega en la primitiva central (misma que usa append_jsonl al ingestar).
    from collections import Counter
    sizes = Counter(_cluster_key(r) for r in rows)
    out = consolidate_by_cluster(rows)
    stats = {
        "clusters": len(sizes),
        "multi": sum(1 for n in sizes.values() if n > 1),
        "rows_collapsed": sum(n - 1 for n in sizes.values() if n > 1),
    }
    return out, stats


def run(items_path: Path, *, dry_run: bool) -> None:
    rows = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    out, stats = consolidate(rows)

    print(f"Filas antes:           {len(rows)}")
    print(f"Filas después:         {len(out)}")
    print(f"Productos (clusters):  {stats['clusters']}")
    print(f"Clusters multi-fuente: {stats['multi']}")
    print(f"Filas colapsadas:      {stats['rows_collapsed']}")
    multi_examples = [r for r in out if isinstance(r.get("sources"), list) and len(r["sources"]) > 1][:6]
    for r in multi_examples:
        print(f"  • {r.get('title','')}: {len(r['sources'])} fuentes "
              f"({', '.join(s.get('name','') for s in r['sources'])})")

    if dry_run:
        print("\n[dry-run] No se escribió nada.")
        return
    if len(out) == len(rows) and stats["rows_collapsed"] == 0:
        # Igual reescribimos si faltaba poblar sources[] en singles; comparamos.
        if all(isinstance(r.get("sources"), list) and r["sources"] for r in rows):
            print("\nNada que consolidar (ya está en el modelo 1-fila-por-producto).")
            return

    backup_and_rotate(items_path, "consolidate-sources")
    with items_path.open("w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n✓ Escrito {items_path} ({len(out)} filas, 1 por producto, con sources[]).")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(args.items, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
