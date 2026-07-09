#!/usr/bin/env python3
"""prune_state.py — poda opt-in de entradas muertas de data/state.json.

`state.json` es el ledger de detección del scraper: 1 clave por candidato visto
(URL normalizada), con `first_seen_at`/`last_seen_at`/`content_hash`. Como
`process_state` NUNCA borra claves, crece sin límite: al 2026-07-08 tenía ~23 863
claves vs ~13 465 items del corpus (~10k entradas de productos que ya no están en
ninguna fuente). Se parsea y reescribe entero en CADA run/bootstrap (23 MB).

Este retrofit poda las entradas cuyo `last_seen_at` supera un umbral (default 12
meses). Es HOUSEKEEPING MANUAL — NUNCA entra al pipeline canónico:

  - `last_seen_at` viejo tampoco es ruido puro: es señal de "desapareció del
    mercado" (un producto agotado/descatalogado). Por eso NO es agresivo y el
    default es dry-run.
  - Podar una clave sólo hace que, si esa URL reaparece en una fuente, el próximo
    run la reporte como "new" otra vez (re-detección benigna) — no se pierde
    ningún dato del corpus (items.jsonl no se toca).

Uso:
    python scripts/retrofit/prune_state.py                    # dry-run (default)
    python scripts/retrofit/prune_state.py --older-than-months 18
    python scripts/retrofit/prune_state.py --apply            # escribe (con backup)
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import load_state, save_state, backup_and_rotate  # type: ignore


def _parse_ts(value: str) -> dt.datetime | None:
    """Parsea un ISO-8601 (con o sin tz) a datetime aware (UTC)."""
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default="data/state.json")
    parser.add_argument("--output", default="data/state.json")
    parser.add_argument("--older-than-months", type=int, default=12,
                        help="Poda entradas con last_seen_at más viejo que N meses (default 12).")
    parser.add_argument("--apply", action="store_true",
                        help="Escribe el state podado (con backup). Sin este flag: dry-run.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Explícito; es el comportamiento por DEFECTO (sin --apply no escribe).")
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    state = load_state(src)
    total = len(state)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30 * args.older_than_months)

    to_prune: list[str] = []
    no_ts = 0
    for key, entry in state.items():
        if not isinstance(entry, dict):
            continue
        ts = _parse_ts(str(entry.get("last_seen_at", "") or ""))
        if ts is None:
            # Sin last_seen_at parseable → conservador: NO podar (se cuenta aparte).
            no_ts += 1
            continue
        if ts < cutoff:
            to_prune.append(key)

    print(f"[INFO] state: {total} claves. Umbral: last_seen_at < {cutoff.date()} "
          f"(> {args.older_than_months} meses).")
    print(f"[INFO] {len(to_prune)} podables, {no_ts} sin last_seen_at (conservadas), "
          f"{total - len(to_prune)} sobrevivirían.")
    for key in to_prune[:10]:
        print(f"  - {key}  (last_seen_at={state[key].get('last_seen_at')})")

    if not args.apply:
        print("[DRY-RUN] No se escribió nada. Usa --apply para podar.")
        return 0

    if not to_prune:
        print("[OK] Nada que podar.")
        return 0

    backup = backup_and_rotate(dst, "prune-state", timestamped=True)
    print(f"[OK] Backup guardado en {backup}")
    for key in to_prune:
        del state[key]
    save_state(dst, state)
    print(f"[OK] Escribí {dst}: {len(state)} claves ({len(to_prune)} podadas).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
