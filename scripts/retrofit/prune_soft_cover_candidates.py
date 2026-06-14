#!/usr/bin/env python3
"""prune_soft_cover_candidates.py — quita de la cola de aprobación
(`data/cover_preview.json`) las candidatas "blandas": imágenes con MÁS píxeles
que la portada actual pero poco detalle real (escaneos sobre-comprimidos o
upscales). El px count las hacía ganar aunque se vieran feas/pixeladas
(gotcha #94).

El criterio es la MISMA función que ahora bloquea estas candidatas upstream en
el validador del skill (`sc_validate.py`) y en el pipeline de producción
(`fetch_better_covers._try_candidates`): `fetch_better_covers._is_soft_image`.
Fuente ÚNICA — este retrofit solo re-aplica el gate a lo que ya estaba en la
cola antes de que el gate existiera (no reimplementa el criterio).

Comportamiento:
  - Evalúa cada candidata `pending` cuyo archivo local exista en data/images/.
  - Quita las que dan `_is_soft_image == True` (detalle < DETAIL_RATIO_MIN).
  - Si una entry se queda sin candidatas, se elimina (la portada actual se
    conserva intacta — nunca tocamos items.jsonl).
  - Idempotente: una segunda corrida no encuentra nada que podar.

Uso:
  .venv/bin/python scripts/retrofit/prune_soft_cover_candidates.py --dry-run
  .venv/bin/python scripts/retrofit/prune_soft_cover_candidates.py
"""
from __future__ import annotations
import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "retrofit"))
import fetch_better_covers as fbc  # noqa: E402  (fuente única del gate de detalle)

COVER_PREVIEW = ROOT / "data" / "cover_preview.json"
IMAGES = ROOT / "data" / "images"


def _candidate_eval(cand: dict) -> tuple[bool, float | None, int]:
    """(es_blanda, detail_ratio, px) de la candidata. es_blanda=False si no hay
    archivo legible. Delega el criterio en fbc._is_soft_image (chica Y blanda)."""
    fn = (cand.get("new_image") or "").strip()
    if not fn:
        return False, None, 0
    try:
        data = (IMAGES / fn).read_bytes()
    except OSError:
        return False, None, 0
    return fbc._is_soft_image(data), fbc._detail_ratio(data), fbc._get_pixels_from_bytes(data)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada, solo reporta")
    args = ap.parse_args()

    try:
        entries = json.loads(COVER_PREVIEW.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"[prune] no se pudo leer {COVER_PREVIEW}: {e}")
        return 1
    if not isinstance(entries, list):
        print("[prune] formato inesperado de cover_preview.json (se esperaba lista)")
        return 1

    kept_entries: list[dict] = []
    dropped_cands = 0
    dropped_entries = 0
    by_domain = Counter()
    examples: list[tuple[str, str, float, int]] = []

    for e in entries:
        cands = e.get("candidates", []) or []
        kept_cands = []
        for c in cands:
            # Solo re-evaluamos las pendientes: una decisión ya tomada por el
            # owner (approved/rejected) no se toca.
            if c.get("status", "pending") != "pending":
                kept_cands.append(c)
                continue
            is_soft, ratio, px = _candidate_eval(c)
            if is_soft:
                dropped_cands += 1
                by_domain[c.get("domain", "?")] += 1
                if len(examples) < 30:
                    examples.append((e.get("title", "")[:36], c.get("domain", "?"),
                                     ratio if ratio is not None else -1.0, px))
                continue
            kept_cands.append(c)

        if not kept_cands:
            dropped_entries += 1
            continue
        if len(kept_cands) != len(cands):
            e = {**e, "candidates": kept_cands}
        kept_entries.append(e)

    # ── reporte ────────────────────────────────────────────────────────────────
    print(f"[prune] criterio: chica (< {fbc.SOFT_GUARD_PX:,} px) Y blanda (detalle < {fbc.DETAIL_RATIO_MIN})")
    print(f"[prune] candidatas chicas+blandas quitadas: {dropped_cands}")
    print(f"[prune] entries eliminadas (sin candidatas restantes): {dropped_entries}")
    print(f"[prune] entries antes/después: {len(entries)} → {len(kept_entries)}")
    if by_domain:
        print(f"[prune] por dominio: {dict(by_domain.most_common())}")
    for title, domain, ratio, px in examples:
        print(f"   {title:36} [{domain:26}] {px:>7,}px detalle={ratio:.3f}")

    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if dropped_cands == 0 and dropped_entries == 0:
        print("[prune] nada que podar — cola ya limpia.")
        return 0

    backup = COVER_PREVIEW.with_suffix(".json.bak-prune-soft")
    shutil.copy(COVER_PREVIEW, backup)
    tmp = COVER_PREVIEW.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(kept_entries, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(COVER_PREVIEW)
    print(f"[prune] escrito {COVER_PREVIEW}. Backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
