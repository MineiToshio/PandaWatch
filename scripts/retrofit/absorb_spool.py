#!/usr/bin/env python3
"""absorb_spool.py — absorbe un spool huérfano de items.jsonl (data/items.jsonl.spool).

Post-mortem 2026-08-22/24: el timeout de la Fase 1 mató el proceso principal
DESPUÉS de que `mirror_candidate_images` corriera pero ANTES del `append_jsonl`
final (manga_watch.py: el spool se flushea incremental por-fuente durante el
scrape — ver A10, `flush_source_candidates(..., spool=True)` — y sólo el
`append_jsonl` de cierre lo absorbe y lo borra). Resultado: 274 items quedaron
varados en `data/items.jsonl.spool` — invisibles para toda la Fase 3, porque
los retrofits de esa fase hacen dump-completo con `write_items_atomic`/
`write_lines_atomic` (regla A7), que NUNCA leen el spool; sólo `append_jsonl`
lo hace.

Este script es el "primer paso" explícito de la Fase 3: llama
`append_jsonl(items_path, [])` (mismo patrón que
`tests/test_perf_lock_20260708.py::test_spool_absorbed_by_leftover_on_next_write`)
así el spool de CUALQUIER corrida anterior interrumpida se absorbe antes de que
el resto de la cadena (rescore, clean_titles, filter_*, …) trabaje sobre el
corpus. Reintenta también items.jsonl.conflicts aunque el spool ya no exista.
No-op limpio (no toca items.jsonl) si no hay spool ni conflictos pendientes. Respeta
el flock inter-proceso de `items_write_lock` (A12) como cualquier otro writer
de items.jsonl.

Uso:
    python scripts/retrofit/absorb_spool.py                # ejecuta
    python scripts/retrofit/absorb_spool.py --dry-run       # solo reporta si hay spool pendiente
    python scripts/retrofit/absorb_spool.py --items data/items.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Gotcha #64: el wrapper de la raíz puede sombrear scripts/manga_watch.py.
try:
    from manga_watch import (  # type: ignore
        _items_spool_path,
        _read_spool,
        read_jsonl_strict,
        append_jsonl,
    )
except ImportError:
    from scripts.manga_watch import (  # type: ignore
        _items_spool_path,
        _read_spool,
        read_jsonl_strict,
        append_jsonl,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", default="data/items.jsonl",
                        help="Path a items.jsonl (default: data/items.jsonl).")
    parser.add_argument("--dry-run", action="store_true",
                        help="No absorbe nada; solo reporta si hay un spool pendiente y cuántas filas trae.")
    args = parser.parse_args()

    items_path = Path(args.items)
    spool_path = _items_spool_path(items_path)

    conflict_path = items_path.with_name(items_path.name + ".conflicts")
    conflicts = read_jsonl_strict(conflict_path)

    if not spool_path.exists() and not conflicts:
        print(f"[absorb_spool] sin spool pendiente ({spool_path}) — nada que hacer.")
        return 0

    pending = _read_spool(items_path)
    if spool_path.exists():
        print(f"[absorb_spool] spool huérfano encontrado: {spool_path} ({len(pending)} filas)")
    if conflicts:
        print(f"[absorb_spool] conflictos pendientes: {conflict_path} ({len(conflicts)} filas)")

    if args.dry_run:
        print("[absorb_spool] --dry-run: no se absorbe nada.")
        return 0

    if not items_path.exists():
        print(f"[WARN] {items_path} no existe — el spool se absorbe igual "
              f"(append_jsonl lo crea).")

    # append_jsonl([]) fuerza la lectura+absorción+borrado del spool aunque no
    # traigamos filas nuevas propias — mismo patrón que el append_jsonl final
    # de run()/_run_wiki_bootstrap() cuando el run SÍ termina normal.
    deferred = append_jsonl(items_path, [], defer_conflicts=True)
    if deferred:
        print(f"[ERROR] {len(deferred)} ambiguous URLs preserved in {items_path.name}.conflicts")
        return 1

    if spool_path.exists():
        print(f"[ERROR] el spool sigue existiendo tras append_jsonl — algo falló.")
        return 1

    print(f"[absorb_spool] absorbidas {len(pending)} filas de {spool_path.name} → {items_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
