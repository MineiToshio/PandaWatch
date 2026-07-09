#!/usr/bin/env python3
"""filter_non_manga.py — descarta items que no son mangas/artbooks/light novels.

Usa is_likely_manga() de manga_watch.py para clasificar los items existentes
en items.jsonl y mover los no-mangas a un archivo separado para revisión.

Uso:
    python scripts/retrofit/filter_non_manga.py                    # ejecuta y escribe
    python scripts/retrofit/filter_non_manga.py --dry-run          # solo cuenta
    python scripts/retrofit/filter_non_manga.py --input X --kept-output Y --rejected-output Z

Por defecto:
    - keeps items en data/items.jsonl
    - rejected items en data/diagnostics/items.non_manga.jsonl (para revisar)
    - backup en data/backups/items.jsonl/items.jsonl.pre-filter-bak (rotación max 3)
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

from manga_watch import (  # type: ignore
    is_likely_manga, load_sources, backup_and_rotate, is_approved,
    write_lines_atomic,
)


def _build_source_purity_map() -> dict[str, str]:
    """Lee sources.yml y devuelve {source_name: purity} (default manga_only).

    Para los items históricos en items.jsonl, el campo 'source' es el name
    de la fuente. Como las sources con search-template expanden a múltiples
    nombres ('AR - X (search) [search: variant]'), también guardamos
    prefijos: si una source con purity='mixed' se llama 'US - Dark Horse
    Direct', todos los 'US - Dark Horse Direct...' heredan 'mixed'.
    """
    purity_map: dict[str, str] = {}
    try:
        sources = load_sources(Path("sources.yml"))
    except Exception:
        return purity_map
    for s in sources:
        if s.purity and s.purity != "manga_only":
            purity_map[s.name] = s.purity
    return purity_map


def _purity_for(source_name: str, purity_map: dict[str, str]) -> str:
    """Devuelve purity para un item; chequea exact match + prefix match."""
    if not source_name:
        return "manga_only"
    if source_name in purity_map:
        return purity_map[source_name]
    # Prefix match para items de search-template ("X [search: variant]"
    # hereda de "X").
    for name, purity in purity_map.items():
        if source_name.startswith(name):
            return purity
    return "manga_only"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--kept-output", default="data/items.jsonl")
    parser.add_argument("--rejected-output", default="data/diagnostics/items.non_manga.jsonl")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe nada; solo reporta cuántos se filtrarían.")
    parser.add_argument("--include-approved", action="store_true",
                        help="Procesar también items aprobados (golden records). Por "
                             "defecto se saltean para no pisar metadata aprobada.")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    lines = src.read_text(encoding="utf-8").splitlines()
    kept_lines: list[str] = []
    rejected_lines: list[str] = []
    skipped_approved = 0
    reason_counter: Counter[str] = Counter()
    sample_rejected: list[tuple[str, str, str]] = []

    purity_map = _build_source_purity_map()
    if purity_map:
        print(f"[INFO] Cargando purity para {len(purity_map)} sources con purity ≠ manga_only")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            kept_lines.append(line)
            continue

        # Golden records: el owner aprobó esta card; SIEMPRE se conserva.
        if is_approved(item) and not args.include_approved:
            skipped_approved += 1
            kept_lines.append(line)
            continue

        title = item.get("title", "")
        description = item.get("description", "")
        tags = item.get("tags", []) or []
        purity = _purity_for(item.get("source", ""), purity_map)
        is_manga, reason = is_likely_manga(
            title, description, tags=tags, source_purity=purity,
            publisher=item.get("publisher", ""),
            url=item.get("url", ""),
        )
        if is_manga:
            kept_lines.append(line)
        else:
            rejected_lines.append(line)
            # Tomamos el "bucket" del reason (ej. "non_manga_hard")
            bucket = reason.split(":", 1)[0]
            reason_counter[bucket] += 1
            if len(sample_rejected) < 15:
                sample_rejected.append((reason, title[:90], item.get("source", "")))

    total = len(kept_lines) + len(rejected_lines)
    print(f"[INFO] {total} items totales")
    print(f"[INFO] {len(kept_lines)} mangas (kept)")
    print(f"[INFO] {len(rejected_lines)} non-manga (rejected)")
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados (kept; usa --include-approved para incluirlos)")
    print(f"\nMotivos de descarte:")
    for bucket, n in reason_counter.most_common():
        print(f"  {bucket:25s}  {n}")

    if sample_rejected:
        print(f"\nMuestra de descartes:")
        for reason, title, source in sample_rejected:
            print(f"  [{reason}]")
            print(f"    {title}")
            print(f"    ← {source}")

    if args.dry_run:
        print("\n[DRY-RUN] No se escribió ningún archivo.")
        return 0

    if not rejected_lines:
        print("\n[OK] Nada que filtrar.")
        return 0

    # Backup defensivo del input
    kept_path = Path(args.kept_output)
    rejected_path = Path(args.rejected_output)
    if kept_path.exists() and kept_path == src:
        backup = backup_and_rotate(kept_path, "filter")
        print(f"\n[OK] Backup guardado en {backup}")
    # B12 (Fable 2026-07-08): el diagnóstico de rechazados también se rota
    # (no se pisa en silencio) — así la evidencia de la corrida anterior
    # sigue disponible en data/backups/ para comparar/revisar.
    if rejected_path.exists():
        backup_and_rotate(rejected_path, "filter-rejected")

    # A7 (Fable 2026-07-08): escribir `rejected` ANTES que `kept` — un crash
    # entre ambos writes no deja los rechazados fuera de AMBOS archivos.
    write_lines_atomic(rejected_path, rejected_lines)
    print(f"[OK] Escribí {rejected_path} con {len(rejected_lines)} non-manga (para revisión).")

    write_lines_atomic(kept_path, kept_lines)
    print(f"[OK] Escribí {kept_path} con {len(kept_lines)} mangas.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
