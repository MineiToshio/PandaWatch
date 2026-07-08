#!/usr/bin/env python3
"""purge_op_import_foreign.py — desblinda + encola residuos de serie ajena del
import manual de One Piece (GRUPO 3 de la auditoría post-scrape, 2026-07-07).

Contexto (causa raíz verificada). Un import manual one-shot ("Research import
(One Piece special publications/volumes/Jump Remix)", scripts
`scripts/import_op_remix.py` / `scripts/fix_op_special_vols.py`, fuera del
pipeline canónico) arrastró ~11 series ajenas: índices de antologías Jump
Remix/GIGA con ISBN mal resuelto — el ISBN apuntaba al volumen real de OTRA
serie (地獄楽/Hell's Paradise, 終末のハーレム, RURIDRAGON, 青の祓魔師, 遊☆戯☆王,
逃げ上手の若君, etc.) pero el item quedó etiquetado con `series_key`/
`edition_key` de "One Piece Gakuen"/"Kobiyama"/"Episode A". No es una simple
mala clasificación de edición — es un mismatch título↔ISBN: el `title`/
`title_original` de estos items describe una obra COMPLETAMENTE distinta a la
que dice el `series_display`/`edition_key`. Evento único (import manual, no
recurrente); la prevención estructural para que no vuelva a pasar vive en
`scripts/op_series_guard.py` (guard en los 2 scripts de import).

Detección: items cuyo `source` empieza con "Research import (One Piece" y cuyo
`title`/`title_original` NO matchea `op_series_guard.is_one_piece_title()`
(keywords: "one piece", "ワンピース", "尾田" — case-insensitive).

Vía elegida (documentada, ver docstring del prompt): AMBAS acciones, no una
sola —
  1. Remueve `standardized_at` (desblindar) para que el pipeline determinista
     (rescore → filter_non_manga/filter_collectible) los reevalúe desde cero
     en la próxima corrida, igual que `purge_false_artbook_residuals.py`
     (GRUPO 2).
  2. Encola a `data/unmapped_series.jsonl` (reason `op_import_foreign`, vía
     `standardize_apply.append_unmapped_from_item` — fuente única de la cola,
     dedup cross-run por `(series_key, reason)`/`(sample_url, reason)`).

Por qué las dos y no sólo una: a diferencia del GRUPO 2 (bug de señal simple,
el texto post-estandarización ya no dispara el falso positivo y el mecanismo
determinista alcanza solo), acá el dato de origen está CORROMPIDO — el
`title`/`description`/ISBN no describen la misma obra entre sí, así que no hay
garantía de que el texto libre dispare (o no dispare) las señales correctas al
re-derivar. Este es exactamente el caso que motivó la convención "el LLM
propone, el determinismo dispone" (`standardize_apply.py`): un veredicto
`is_manga=false` del LLM deja el item PENDIENTE (sin `standardized_at`) +
registrado en `unmapped_series.jsonl` para curación — el mismo patrón dual se
aplica acá. Desblindar solo es best-effort (puede o no expulsar el item vía
los gates); encolar garantiza que un humano (o el skill de standardize en su
próxima pasada) lo vea y decida si el registro pertenece a OTRA serie
(re-mapeo) o se borra directo por no ser un producto válido de este catálogo.

Idempotente. Guard `approved_at` (golden records) + `--include-approved`.
Backup vía `backup_and_rotate` antes de escribir. Escritura atómica.

Uso:
  .venv/bin/python scripts/retrofit/purge_op_import_foreign.py           # dry-run (default)
  .venv/bin/python scripts/retrofit/purge_op_import_foreign.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import backup_and_rotate, is_approved  # type: ignore
from op_series_guard import is_one_piece_title  # type: ignore
import standardize_apply  # type: ignore

ITEMS = _SCRIPTS.parent / "data" / "items.jsonl"
REASON = "op_import_foreign"

_OP_IMPORT_SOURCE_PREFIX = "Research import (One Piece"


def is_op_import_foreign(item: dict) -> bool:
    """True si el item viene del import manual de OP pero NO es One Piece."""
    src = item.get("source") or ""
    if not src.startswith(_OP_IMPORT_SOURCE_PREFIX):
        return False
    return not is_one_piece_title(item.get("title", ""), item.get("title_original", ""))


def find_candidates(items: list[dict], *, include_approved: bool) -> tuple[list[dict], int]:
    """Devuelve (candidatos, aprobados_saltados)."""
    candidates: list[dict] = []
    skipped_approved = 0
    for item in items:
        if not is_op_import_foreign(item):
            continue
        if is_approved(item) and not include_approved:
            skipped_approved += 1
            continue
        candidates.append(item)
    return candidates, skipped_approved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(ITEMS))
    parser.add_argument("--apply", action="store_true",
                        help="Escribe: desblinda (remueve standardized_at) + encola a "
                             "unmapped_series.jsonl. Sin este flag, solo lista/cuenta "
                             "(default = dry-run).")
    parser.add_argument("--include-approved", action="store_true",
                        help="Procesar también items aprobados (golden records). "
                             "Por defecto se saltean.")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    items: list[dict] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    candidates, skipped_approved = find_candidates(items, include_approved=args.include_approved)

    print(f"[INFO] {len(items)} items totales, {len(candidates)} candidatos "
          f"(source del import de One Piece + título sin keyword de la serie).")
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados (usa --include-approved para incluirlos)")

    if not candidates:
        print("[OK] Nada que procesar.")
        return 0

    print("\nCandidatos:")
    for it in candidates:
        print(f"  {it.get('slug') or it.get('url', '')[:60]}: title={it.get('title')!r} "
              f"edition_key={it.get('edition_key')!r}")

    if not args.apply:
        print("\n[DRY-RUN] No se escribió nada. Usa --apply para desblindar + encolar de verdad.")
        return 0

    backup_and_rotate(src, "purge-op-import-foreign")

    # 1. Desblindar: remover standardized_at para que el pipeline determinista
    #    reevalúe desde cero en la próxima corrida.
    ids = {id(it) for it in candidates}
    out: list[dict] = []
    for it in items:
        if id(it) in ids:
            it = dict(it)
            it.pop("standardized_at", None)
        out.append(it)

    tmp = src.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in out:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(src)

    # 2. Encolar a la cola única de curación (dedup cross-run).
    seen = standardize_apply._existing_unmapped_keys()
    queued = 0
    already_queued = 0
    for it in candidates:
        wrote = standardize_apply.append_unmapped_from_item(
            it, REASON,
            note="import manual de One Piece con ISBN/título de OTRA serie (ver op_series_guard.py)",
            seen=seen,
        )
        if wrote:
            queued += 1
        else:
            already_queued += 1

    print(f"\n[OK] Desblindados {len(candidates)} items (standardized_at removido) en {src}. "
          f"Encolados {queued} nuevos a {standardize_apply.UNMAPPED} (reason={REASON!r}); "
          f"{already_queued} ya estaban en la cola (dedup por url+reason).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
