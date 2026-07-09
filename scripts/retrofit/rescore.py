#!/usr/bin/env python3
"""rescore.py — re-aplica score_candidate (signal_types, product_type, score)
a todos los items de items.jsonl con el código actual.

Esto limpia residuos de bugs viejos (substring contamination, source-name
leak, etc.) sin necesidad de re-scrapear ninguna fuente. Sólo recomputa
campos derivados de title+description.

Lo que SE recomputa (con el código actual):
    signal_types, signals, score, product_type, stock_type, content_hash

Lo que NO se toca:
    title, url, source, publisher, country, language, image_url, isbn,
    release_date, author, tags, status, detected_at, *_at fields.

GUARD (gotcha #61): los items con `standardized_at` NO se re-scorean por
defecto — la estandarización reescribe title/description a etiquetas limpias
("Yawara! Ultimate 18") donde detect_signals no encuentra nada, así que
recomputar signal_types desde ese texto LAVA las señales. La verdad
post-estandarización vive en la etiqueta de edición, no en el texto.
`--include-standardized` fuerza incluirlos (sólo para reparaciones puntuales).

Uso:
    python scripts/retrofit/rescore.py                    # ejecuta
    python scripts/retrofit/rescore.py --dry-run          # solo reporta drift
    python scripts/retrofit/rescore.py --input X --output Y
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import (  # type: ignore
    Candidate,
    score_candidate,
    candidate_to_json,
    backup_and_rotate,
    is_approved,
    write_lines_atomic,
)
import image_store  # type: ignore


def _item_to_candidate(item: dict) -> Candidate:
    """Reconstituye un Candidate desde un dict persistido para re-scorear."""
    return Candidate(
        title=item.get("title", "") or "",
        url=item.get("url", "") or "",
        source=item.get("source", "") or "",
        source_url=item.get("source_url", "") or "",
        country=item.get("country", "") or "",
        language=item.get("language", "") or "",
        publisher=item.get("publisher", "") or "",
        source_class=item.get("source_class", "") or "",
        tags=list(item.get("tags", []) or []),
        description=item.get("description", "") or "",
        # Portada = images[0] (única fuente de verdad). Reconstruimos el
        # Candidate runtime desde ahí para que score_candidate la vea.
        image_url=image_store.cover_url(item),
        image_local=image_store.cover_local(item),
        images=list(item.get("images") or []),
        release_date=item.get("release_date", "") or "",
        author=item.get("author", "") or "",
        isbn=item.get("isbn", "") or "",
        published_at=item.get("published_at", "") or "",
        status=item.get("status", "") or "",
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default="data/items.jsonl")
    p.add_argument("--output", default="data/items.jsonl")
    p.add_argument("--dry-run", action="store_true",
                   help="No escribe; sólo reporta drift de signal_types y product_type.")
    p.add_argument("--include-approved", action="store_true",
                   help="Procesar también items aprobados (golden records). Por "
                        "defecto se saltean para no pisar metadata aprobada.")
    p.add_argument("--include-standardized", action="store_true",
                   help="Procesar también items estandarizados. Por defecto se "
                        "saltean: re-scorear texto estandarizado lava las "
                        "señales (gotcha #61).")
    args = p.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    lines = src.read_text(encoding="utf-8").splitlines()

    out_lines: list[str] = []
    drift_st = 0
    drift_pt = 0
    drift_score = 0
    drift_hash = 0
    skipped_approved = 0
    skipped_standardized = 0
    pt_changes: Counter[tuple[str, str]] = Counter()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue

        # Golden records: el owner aprobó esta card; no la re-scoreamos.
        if is_approved(item) and not args.include_approved:
            skipped_approved += 1
            out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            continue

        # Items estandarizados: re-scorear su texto limpio lava las señales
        # (gotcha #61) — se saltean salvo override explícito.
        if item.get("standardized_at") and not args.include_standardized:
            skipped_standardized += 1
            out_lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            continue

        old_st = set(item.get("signal_types") or [])
        old_pt = item.get("product_type", "") or ""
        old_score = int(item.get("score") or 0)
        old_hash = item.get("content_hash", "") or ""

        cand = _item_to_candidate(item)
        score_candidate(cand)
        new_st = set(cand.signal_types or [])
        new_pt = cand.product_type or ""
        new_score = cand.score

        if new_st != old_st:
            drift_st += 1
        if new_pt != old_pt:
            drift_pt += 1
            pt_changes[(old_pt or "(empty)", new_pt or "(empty)")] += 1
        if new_score != old_score:
            drift_score += 1

        # Reescribir item con valores frescos (preservando campos no derivados).
        updated = dict(item)
        updated_from_cand = candidate_to_json(cand)
        # Solo overwrite los campos que el rescore controla.
        for k in ("signal_types", "signals", "score", "product_type",
                  "stock_type", "content_hash"):
            updated[k] = updated_from_cand.get(k, updated.get(k))
        # B13 (Fable 2026-07-08): si sólo el content_hash recomputado difiere
        # (drift silencioso — signal_types/product_type/score iguales pero el
        # hash cambió, p.ej. tras un fix upstream que afecta el hash sin
        # afectar la derivación), el chequeo de arriba no lo contaba como
        # drift → "nada cambió" y el item quedaba stale. Se cuenta acá
        # también, sin duplicar el contador de score.
        new_hash = updated_from_cand.get("content_hash", "") or ""
        if new_hash != old_hash and new_st == old_st and new_pt == old_pt and new_score == old_score:
            drift_hash += 1
        out_lines.append(json.dumps(updated, ensure_ascii=False, sort_keys=True))

    total = len(out_lines)
    print(f"[INFO] {total} items procesados")
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados (usa --include-approved para incluirlos)")
    if skipped_standardized:
        print(f"[INFO] {skipped_standardized} estandarizados saltados — gotcha #61 "
              "(usa --include-standardized para incluirlos)")
    print(f"[INFO] signal_types cambió:  {drift_st} ({drift_st*100//max(total,1)}%)")
    print(f"[INFO] product_type cambió:  {drift_pt} ({drift_pt*100//max(total,1)}%)")
    print(f"[INFO] score cambió:         {drift_score} ({drift_score*100//max(total,1)}%)")
    if drift_hash:
        print(f"[INFO] sólo content_hash cambió: {drift_hash} ({drift_hash*100//max(total,1)}%)")

    if pt_changes:
        print("\nTop product_type transitions (old → new):")
        for (old, new), n in pt_changes.most_common(15):
            print(f"  {n:4d}  {old:15s} → {new}")

    if args.dry_run:
        print("\n[DRY-RUN] No se escribió ningún archivo.")
        return 0

    if drift_st + drift_pt + drift_score + drift_hash == 0:
        print("\n[OK] Nada cambió. items.jsonl ya está al día.")
        return 0

    out_path = Path(args.output)
    if out_path == src and out_path.exists():
        backup = backup_and_rotate(out_path, "rescore")
        print(f"\n[OK] Backup en {backup}")

    write_lines_atomic(out_path, out_lines)
    print(f"[OK] Escribí {out_path} con {total} items refrescados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
