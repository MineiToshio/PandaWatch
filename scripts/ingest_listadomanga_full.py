#!/usr/bin/env python3
"""ingest_listadomanga_full.py — ingesta COMPLETA de listadomanga recorriendo
lista.php (índice alfabético oficial) item por item, EN ORDEN, sin saltarse
ninguno, por chunks resumibles con checkpoint.

Por qué: el FULL scrape debe recorrer TODOS los items de
https://www.listadomanga.es/lista.php uno por uno (decisión del owner). El orden
es alfabético (NO numérico por id — ej. Azumanga id=542 está en posición 251).

Checkpoint (`data/listadomanga_full_progress.json`): guarda el orden de lista.php
descubierto UNA vez + el cursor. Si se corta (luz/internet/tokens), reanudar es
`--chunks N` otra vez: continúa desde el cursor. Determinístico.

NO corre la cadena de cleanup (unify/country/dedup/slugs) — eso va aparte para no
re-procesar todo el corpus por cada chunk. Sólo ingesta raw + cuenta cobertura.

Uso:
  # crear/refrescar el checkpoint (descubre lista.php):
  .venv/bin/python scripts/ingest_listadomanga_full.py --discover
  # procesar los próximos N chunks (default 1 chunk de 100):
  .venv/bin/python scripts/ingest_listadomanga_full.py --chunks 1 --chunk-size 100
  # estado:
  .venv/bin/python scripts/ingest_listadomanga_full.py --status
"""
from __future__ import annotations
import json, sys, argparse, subprocess, tempfile, os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
PROG = ROOT / "data" / "listadomanga_full_progress.json"
ITEMS = ROOT / "data" / "items.jsonl"
PYTHON = str(ROOT / ".venv" / "bin" / "python")
LOG_DIR = ROOT / "logs"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> dict:
    if PROG.exists():
        return json.loads(PROG.read_text())
    return {}


def _save(state: dict) -> None:
    tmp = PROG.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    tmp.replace(PROG)


def _discover() -> dict:
    import requests
    import wikis.listadomanga_collections as L
    s = requests.Session()
    s.headers["User-Agent"] = "manga-watch/0.2 (+lista-full-ingest)"
    ids = L._discover_via_lista(s)
    if not ids:
        raise SystemExit("lista.php devolvió 0 ids — abortando (no piso el checkpoint).")
    state = _load()
    state.update({
        "discovered_at": _now(),
        "lista_ids": ids,
        "total": len(ids),
        "cursor": state.get("cursor", 0),
        "chunk_size": state.get("chunk_size", 100),
        "history": state.get("history", []),
    })
    _save(state)
    print(f"[discover] lista.php: {len(ids)} colecciones. cursor={state['cursor']}.")
    return state


def _items_count() -> int:
    return sum(1 for l in ITEMS.open() if l.strip()) if ITEMS.exists() else 0


def _run_chunk(state: dict, chunk_size: int) -> bool:
    ids = state["lista_ids"]
    cur = state["cursor"]
    if cur >= len(ids):
        print("[chunk] cursor al final — nada que procesar.")
        return False
    chunk = ids[cur:cur + chunk_size]
    LOG_DIR.mkdir(exist_ok=True)
    before = _items_count()
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        fh.write("\n".join(str(x) for x in chunk))
        ids_file = fh.name
    log = LOG_DIR / f"lista-chunk-{cur}-{cur+len(chunk)}.log"
    print(f"[chunk] posiciones {cur}..{cur+len(chunk)} ({len(chunk)} colecciones) → {log.name}")
    cmd = [PYTHON, str(ROOT / "scripts" / "manga_watch.py"),
           "--bootstrap-wiki", "listadomanga-collections",
           "--coleccion-ids-file", ids_file]
    with log.open("w") as lf:
        rc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(ROOT)).returncode
    os.unlink(ids_file)
    after = _items_count()
    rec = {"at": _now(), "from": cur, "to": cur + len(chunk), "ids": len(chunk),
           "rc": rc, "items_before": before, "items_after": after, "delta": after - before,
           "log": log.name}
    state["history"].append(rec)
    state["cursor"] = cur + len(chunk)
    _save(state)
    print(f"[chunk] rc={rc} items {before}→{after} (+{after-before}). cursor={state['cursor']}/{len(ids)}.")
    return rc == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true", help="(re)descubrir lista.php y crear checkpoint")
    ap.add_argument("--status", action="store_true", help="mostrar estado")
    ap.add_argument("--chunks", type=int, default=0, help="cuántos chunks procesar esta corrida")
    ap.add_argument("--chunk-size", type=int, default=100)
    ap.add_argument("--reset-cursor", type=int, default=-1, help="forzar el cursor a una posición")
    args = ap.parse_args()

    if args.discover:
        _discover()
        return 0
    state = _load()
    if not state:
        print("No hay checkpoint; corré --discover primero.")
        return 1
    if args.reset_cursor >= 0:
        state["cursor"] = args.reset_cursor
        _save(state)
        print(f"cursor reseteado a {args.reset_cursor}.")
    if args.status or args.chunks == 0:
        done = state["cursor"]; tot = state["total"]
        print(f"[status] cursor {done}/{tot} ({100*done//max(tot,1)}%) · chunks corridos: {len(state['history'])}")
        for h in state["history"][-8:]:
            print(f"    {h['from']}..{h['to']}  +{h['delta']}  rc={h['rc']}  {h['log']}")
        return 0
    if "chunk_size" in state:
        state["chunk_size"] = args.chunk_size
    for _ in range(args.chunks):
        if not _run_chunk(state, args.chunk_size):
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
