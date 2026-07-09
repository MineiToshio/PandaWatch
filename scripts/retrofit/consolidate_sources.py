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
    primera) y extras union. Delega en `manga_watch.consolidate_by_cluster`
    (fuente única del merge — la misma que usa `append_jsonl` al ingestar),
    para que el resultado sea idéntico al que produce el pipeline normal.
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
    from manga_watch import (  # noqa: E402
        backup_and_rotate, consolidate_by_cluster, derive_cluster_key,
        write_lines_atomic,
    )
except ImportError:  # pragma: no cover
    from scripts.manga_watch import (  # noqa: E402
        backup_and_rotate, consolidate_by_cluster, derive_cluster_key,
        write_lines_atomic,
    )

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
    # B11 (Fable 2026-07-08): una línea corrupta ya no tumba el script — se
    # preserva tal cual (no participa del consolidate, que necesita dicts
    # válidos con cluster_key derivable) y se cuenta/warnea.
    rows: list[dict] = []
    raw_lines: list[str] = []
    corrupt = 0
    for l in items_path.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        try:
            rows.append(json.loads(l))
        except json.JSONDecodeError:
            raw_lines.append(l)
            corrupt += 1
    if corrupt:
        print(f"[WARN] {corrupt} línea(s) corrupta(s) preservada(s) tal cual (no consolidadas).")
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
    out_lines = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in out] + raw_lines
    write_lines_atomic(items_path, out_lines)
    print(f"\n✓ Escrito {items_path} ({len(out)} filas, 1 por producto, con sources[]).")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--items", type=Path, default=DEFAULT_ITEMS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(args.items, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
