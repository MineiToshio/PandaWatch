#!/usr/bin/env python3
"""queue_regular_shielded.py — encola a revisión tomos regulares "blindados" sospechosos.

Detecta items YA estandarizados (`standardized_at` presente) que tienen pinta
de tomo regular blindado por la estandarización —`edition_key` con el segmento
`-regular-` o `edition_display == "Regular"`— pero SIN ninguna señal de bonus
(`store_bonus` vacío y "bonus" ausente de `signal_types`). Un tomo regular sin
extras no debería estar en este catálogo de coleccionables (el 2º gate,
`is_collectible_edition`, los rechaza en items crudos) — que uno haya llegado
a `standardized_at` sugiere una mala clasificación aguas arriba (regular
etiquetado como especial por error, o bonus real que el heurístico no
detectó).

Este script NO borra ni reclasifica nada — sólo ENCOLA a
`data/unmapped_series.jsonl` (regla dura: cola ÚNICA de "registro incierto",
ver docs/reference/conventions.md § "Flagear un registro incierto") con
`reason="regular_shielded_review"` para que un humano (o el skill de
standardize en su próxima pasada) decida. Reusa
`standardize_apply.append_unmapped_from_item()` — la MISMA función que ya usa
el merge del skill para curación con `reason` — en vez de reimplementar el
writer (fuente única, dedup por `(series_key, reason)` / `(sample_url,
reason)` cross-run).

Uso:
    python scripts/retrofit/queue_regular_shielded.py              # solo lista/cuenta
    python scripts/retrofit/queue_regular_shielded.py --apply       # escribe la cola
    python scripts/retrofit/queue_regular_shielded.py --include-approved
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import is_approved  # type: ignore
import standardize_apply  # type: ignore

REASON = "regular_shielded_review"


def _has_bonus_signal(item: dict) -> bool:
    """¿El item ya tiene evidencia de bonus/extra de primera edición?"""
    if (item.get("store_bonus") or "").strip():
        return True
    if "bonus" in (item.get("signal_types") or []):
        return True
    return False


def _looks_like_regular(item: dict) -> bool:
    ek = item.get("edition_key") or ""
    ed = item.get("edition_display") or ""
    return "-regular-" in ek or ed == "Regular"


def find_candidates(items: list[dict], *, include_approved: bool) -> tuple[list[dict], int]:
    """Devuelve (candidatos, aprobados_saltados)."""
    candidates: list[dict] = []
    skipped_approved = 0
    for item in items:
        if not item.get("standardized_at"):
            continue
        if not _looks_like_regular(item):
            continue
        if _has_bonus_signal(item):
            continue
        if is_approved(item) and not include_approved:
            skipped_approved += 1
            continue
        candidates.append(item)
    return candidates, skipped_approved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/items.jsonl")
    parser.add_argument("--apply", action="store_true",
                        help="Escribe a data/unmapped_series.jsonl. Sin este flag, "
                             "solo lista/cuenta (default = dry-run).")
    parser.add_argument("--include-approved", action="store_true",
                        help="Encolar también items aprobados (golden records). Por "
                             "defecto se saltean — el owner ya los revisó.")
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
          f"(estandarizados + pinta de regular + sin señal de bonus).")
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados (usa --include-approved para incluirlos)")

    if not candidates:
        print("[OK] Nada para encolar.")
        return 0

    sample = candidates[:10]
    print("\nMuestra de candidatos:")
    for it in sample:
        print(f"  {it.get('slug') or it.get('url', '')[:60]}: "
              f"edition_key={it.get('edition_key')!r} edition_display={it.get('edition_display')!r}")
    if len(candidates) > 10:
        print(f"  ... y {len(candidates) - 10} más")

    if not args.apply:
        print("\n[DRY-RUN] No se escribió la cola. Usa --apply para encolar de verdad.")
        return 0

    seen = standardize_apply._existing_unmapped_keys()
    queued = 0
    already_queued = 0
    for it in candidates:
        wrote = standardize_apply.append_unmapped_from_item(
            it, REASON, note="edition_key/edition_display con pinta de regular sin bonus", seen=seen,
        )
        if wrote:
            queued += 1
        else:
            already_queued += 1

    print(f"\n[OK] Encolados {queued} nuevos a {standardize_apply.UNMAPPED} "
          f"(reason={REASON!r}); {already_queued} ya estaban en la cola (dedup por url+reason).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
