#!/usr/bin/env python3
"""apply_approvals.py — re-aplica el log durable de aprobaciones sobre items.jsonl.

Las aprobaciones manuales hechas desde el dashboard (botón 👍 / candado) escriben
`approved_at`/`approved_by` en items.jsonl **y** appendean un registro a
`data/approvals.jsonl` (log durable, gitignored). Como items.jsonl es regenerable
(se reconstruye de cero al re-scrapear o importar), este script permite
**re-materializar** las aprobaciones sobre un items.jsonl fresco a partir del log.

Idempotente: correrlo dos veces deja el mismo resultado.

Cómo matchea cada aprobación a las filas de items.jsonl:
    1. por `cluster_key` (todas las filas del cluster reciben el flag), y
    2. por `url` (fallback para la fila canónica si el cluster_key cambió).
Last-wins por clave: una entrada `unapprove` posterior limpia el flag.

Uso:
    python scripts/retrofit/apply_approvals.py              # ejecuta
    python scripts/retrofit/apply_approvals.py --dry-run    # solo reporta
    python scripts/retrofit/apply_approvals.py --approvals X --items Y
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import backup_and_rotate  # type: ignore


def _cluster_of(item: dict) -> str:
    return item.get("cluster_key") or f"url:{item.get('url', '')}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--approvals", default="data/approvals.jsonl")
    p.add_argument("--items", default="data/items.jsonl")
    p.add_argument("--dry-run", action="store_true",
                   help="No escribe; sólo reporta cuántos items se marcarían.")
    args = p.parse_args()

    log_path = Path(args.approvals)
    items_path = Path(args.items)

    if not log_path.exists():
        print(f"[INFO] no existe {log_path} — nada que aplicar.")
        return 0
    if not items_path.exists():
        print(f"[ERROR] no existe {items_path}", file=sys.stderr)
        return 1

    # 1. Reducir el log a estado final por cluster_key y por url (last-wins).
    #    valor = (approved_at, approved_by) si aprobado, o None si desaprobado.
    by_cluster: dict[str, tuple[str, str] | None] = {}
    by_url: dict[str, tuple[str, str] | None] = {}
    n_log = 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        n_log += 1
        approved = entry.get("action") == "approve"
        state = (entry.get("approved_at", ""), entry.get("approved_by", "owner")) if approved else None
        ck = entry.get("cluster_key", "")
        url = entry.get("url", "")
        if ck:
            by_cluster[ck] = state
        if url:
            by_url[url] = state

    print(f"[INFO] {n_log} entradas en el log → "
          f"{len(by_cluster)} clusters, {len(by_url)} urls con estado final.")

    # 2. Aplicar a items.jsonl.
    items = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    set_count = 0
    clear_count = 0
    for it in items:
        ck = _cluster_of(it)
        url = it.get("url", "")
        # Prioridad: cluster_key; fallback a url.
        if ck in by_cluster:
            state = by_cluster[ck]
        elif url in by_url:
            state = by_url[url]
        else:
            continue
        cur = it.get("approved_at", "")
        if state is not None:
            if not cur:
                set_count += 1
            it["approved_at"], it["approved_by"] = state
        else:
            if cur:
                clear_count += 1
            it["approved_at"] = ""
            it["approved_by"] = ""

    print(f"[INFO] {set_count} items recibirían approved_at, {clear_count} se limpiarían.")

    if args.dry_run:
        print("[DRY-RUN] No se escribió ningún archivo.")
        return 0
    if set_count + clear_count == 0:
        print("[OK] Nada cambió. items.jsonl ya refleja el log.")
        return 0

    backup = backup_and_rotate(items_path, "apply-approvals")
    print(f"[OK] Backup en {backup}")
    items_path.write_text(
        "\n".join(json.dumps(it, ensure_ascii=False) for it in items) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] Escribí {items_path} con {len(items)} items.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
