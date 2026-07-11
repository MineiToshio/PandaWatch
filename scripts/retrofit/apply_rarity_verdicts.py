#!/usr/bin/env python3
"""apply_rarity_verdicts.py — aplica los veredictos de verificación web (Step 2
del skill `/watch-validate-rarity`) a `data/items.jsonl`.

Compila a código el Step 3 embebido del skill (auditoría Fable 2026-07-08,
hallazgo F5): antes ese snippet reescribía `items.jsonl` inline y DUPLICABA
`uncertainty_reason()` por segunda vez (la primera copia vivía en el Step 0).
Ahora la re-selección de candidatos usa la MISMA `rarity_uncertainty_reason()`
de `scripts/audit/rarity_candidates.py` (fuente única) — se re-evalúa acá
porque el universo puede haber cambiado entre la selección (Step 0/1) y la
aplicación (este script): un item pudo aprobarse, verificarse por otra vía, o
dejar de ser `rare`.

El veredicto se escribe como EVIDENCIA (`stock_status` + `stock_checked_at`) y
la rareza se RE-DERIVA con `derive_rarity_tier()` — este script nunca asigna
un tier a mano (mismo principio que `set_rarity.py`).

Ruta de resultados: por default `data/diagnostics/rarity_validation_results.json`
(antes `/tmp/rarity_validation_results.json` en el SKILL.md — igual que el fix
de `data/standardize-run/` para el standardize, un run dir en `/tmp` es volátil
ante reboot; acá además es el ÚNICO artefacto que conecta la verificación web
con la escritura, así que perderlo tira todo el trabajo del Step 2).

Formato de `--results` (lista de objetos, uno por `group_id` del candidato):
```json
[
  {"group_id": "phantom-seer-star-limited-it",
   "verdict": "in_stock",
   "rationale": "starcomics.com (publisher) — 'Acquista ora', €10,50",
   "evidence_url": "https://..."}
]
```
`verdict` ∈ {in_stock, out_of_stock, not_found, inconclusive}. `inconclusive`
NO toca nada (ni stock_status ni rarity_verified_at) — el item queda pendiente
para una corrida futura.

Uso:
    apply_rarity_verdicts.py
    apply_rarity_verdicts.py --dry-run
    apply_rarity_verdicts.py --results data/diagnostics/rarity_validation_results.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
_AUDIT_DIR = _SCRIPTS / "audit"
if str(_AUDIT_DIR) not in sys.path:
    sys.path.insert(0, str(_AUDIT_DIR))

# El wrapper manga_watch.py de la RAÍZ puede estar ya cacheado en sys.modules
# bajo pytest (no expone estos símbolos) → fallback al módulo real (mismo
# patrón que fetch_better_covers.py / backfill_series_aliases.py).
try:
    from manga_watch import (  # type: ignore
        backup_and_rotate, derive_rarity_tier, is_approved, write_items_atomic,
    )
except ImportError:  # pragma: no cover
    from scripts.manga_watch import (  # type: ignore
        backup_and_rotate, derive_rarity_tier, is_approved, write_items_atomic,
    )
import rarity_candidates as rc  # type: ignore — fuente única de rarity_uncertainty_reason

VALID_VERDICTS = frozenset({"in_stock", "out_of_stock", "not_found", "inconclusive"})


def _default_items_path() -> Path:
    data_dir = os.environ.get("MANGA_WATCH_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "items.jsonl"
    return _SCRIPTS.parent / "data" / "items.jsonl"


def _default_results_path() -> Path:
    data_dir = os.environ.get("MANGA_WATCH_DATA_DIR")
    base = Path(data_dir) if data_dir else _SCRIPTS.parent / "data"
    return base / "diagnostics" / "rarity_validation_results.json"


def _default_log_path() -> Path:
    data_dir = os.environ.get("MANGA_WATCH_DATA_DIR")
    base = Path(data_dir) if data_dir else _SCRIPTS.parent / "data"
    return base / "diagnostics" / "rarity_validation_log.jsonl"


def run(
    items_path: Path,
    results_path: Path,
    log_path: Path,
    *,
    include_approved: bool,
    dry_run: bool,
) -> int:
    if not items_path.exists():
        print(f"[ERROR] no existe {items_path}", file=sys.stderr)
        return 1
    if not results_path.exists():
        print(
            f"[ERROR] no existe {results_path} — corré "
            f"scripts/audit/rarity_candidates.py y la verificación web (Step 2 "
            f"del skill) antes de aplicar.",
            file=sys.stderr,
        )
        return 1

    try:
        raw_results = json.loads(results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[ERROR] {results_path}: JSON inválido ({e}).", file=sys.stderr)
        return 1

    if not isinstance(raw_results, list):
        print(f"[ERROR] {results_path}: se esperaba una lista de objetos, se "
              f"encontró {type(raw_results).__name__}.", file=sys.stderr)
        return 1

    results: dict[str, dict[str, Any]] = {}
    for i, r in enumerate(raw_results):
        if not isinstance(r, dict):
            print(f"[ERROR] {results_path}: entrada #{i} no es un objeto (dict): "
                  f"{r!r}.", file=sys.stderr)
            return 1
        gid = r.get("group_id")
        if not isinstance(gid, str) or not gid.strip():
            print(f"[ERROR] {results_path}: entrada #{i} tiene group_id inválido "
                  f"o vacío: {gid!r}.", file=sys.stderr)
            return 1
        if r.get("verdict") not in VALID_VERDICTS:
            print(f"[ERROR] {results_path}: group_id={gid!r} tiene "
                  f"verdict={r.get('verdict')!r} inválido (esperado uno de "
                  f"{sorted(VALID_VERDICTS)}).", file=sys.stderr)
            return 1

        if gid in results:
            prev_verdict = results[gid]["verdict"]
            if prev_verdict != r["verdict"]:
                print(f"[ERROR] {results_path}: group_id={gid!r} duplicado con "
                      f"verdicts distintos ({prev_verdict!r} vs {r['verdict']!r}) "
                      f"— resolvé el conflicto en el archivo de resultados antes "
                      f"de aplicar.", file=sys.stderr)
                return 1
            print(f"[WARN] group_id={gid!r} duplicado en {results_path} (mismo "
                  f"verdict {r['verdict']!r}) — se usa la última entrada.")
        results[gid] = r

    items = [json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"[INFO] {len(items)} items en {items_path}, {len(results)} veredicto(s) en {results_path}")

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    updated = 0
    inconclusive = 0
    skipped_approved = 0
    consumed_gids: set[str] = set()
    log: list[dict[str, Any]] = []

    for item in items:
        if item.get("rarity") != "rare" or item.get("rarity_verified_at"):
            continue
        if is_approved(item) and not include_approved:
            if rc.rarity_uncertainty_reason(item):
                skipped_approved += 1
                gid = item.get("edition_key") or item.get("slug") or item.get("url")
                if gid in results:
                    consumed_gids.add(gid)
            continue
        if not rc.rarity_uncertainty_reason(item):
            continue  # dejó de ser candidato (evidencia estructural apareció entretanto)

        gid = item.get("edition_key") or item.get("slug") or item.get("url")
        res = results.get(gid)
        if not res:
            continue
        consumed_gids.add(gid)
        if res["verdict"] == "inconclusive":
            inconclusive += 1
            continue

        old = item.get("rarity", "")
        if res["verdict"] in ("in_stock", "out_of_stock"):
            item["stock_status"] = res["verdict"]
            item["stock_checked_at"] = now
        # Re-derivar con el modelo — este script no asigna tiers a mano.
        item["rarity"] = derive_rarity_tier(
            signal_types=item.get("signal_types") or [],
            source=item.get("source") or "",
            description=item.get("description") or "",
            title=item.get("title") or "",
            publisher=item.get("publisher") or "",
            stock_status=item.get("stock_status") or "",
            sources=rc.item_sources(item),
        )
        item["rarity_verified_at"] = now
        updated += 1
        log.append({
            "slug": item.get("slug"), "group_id": gid, "old": old,
            "new": item["rarity"], "verdict": res["verdict"],
            "rationale": res.get("rationale", ""),
            "evidence_url": res.get("evidence_url", ""), "at": now,
        })

    print(f"Items {'que cambiarían' if dry_run else 'actualizados'}: {updated} | "
          f"inconclusos (sin tocar): {inconclusive}")
    if skipped_approved:
        print(f"Items aprobados saltados (golden records): {skipped_approved}")
    for e in log:
        mark = "→" if e["old"] != e["new"] else "="
        print(f"  {e['old']:5s} {mark} {e['new']:10s} [{e['verdict']:12s}] {e['slug']}")

    # VR-1: un veredicto cuyo group_id no matchea NINGÚN item (ni aplicado, ni
    # inconclusive, ni skipped_approved) se perdía en silencio — se repetía el
    # trabajo de verificación web sin que nadie se enterara. Reportarlo siempre
    # (incluso con updated==0 o --dry-run) para que el Step 3 del skill lo
    # revise y corrija el group_id o descarte el veredicto a propósito.
    orphaned = [gid for gid in results if gid not in consumed_gids]
    if orphaned:
        print(f"[WARN] Veredictos sin match: {len(orphaned)} (group_id no "
              f"matchea ningún item pendiente — puede ser un typo, un item "
              f"que ya no es candidato, o que cambió de group_id entre la "
              f"selección y la aplicación):")
        for gid in orphaned:
            print(f"  - {gid} [{results[gid]['verdict']}]")

    if dry_run:
        print("[DRY-RUN] No se escribió nada.")
        return 0
    if updated == 0:
        print("[OK] Nada que escribir.")
        return 0

    backup = backup_and_rotate(items_path, "validate-rarity")
    print(f"[OK] Backup: {backup}")
    write_items_atomic(items_path, items)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        for e in log:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"[OK] {items_path} actualizado + log en {log_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", type=Path, default=None,
                    help="items.jsonl a leer/escribir (default: data/items.jsonl / "
                         "MANGA_WATCH_DATA_DIR).")
    ap.add_argument("--results", type=Path, default=None,
                    help="JSON de veredictos (default: "
                         "data/diagnostics/rarity_validation_results.json).")
    ap.add_argument("--log", type=Path, default=None,
                    help="Log de auditoría, append (default: "
                         "data/diagnostics/rarity_validation_log.jsonl).")
    ap.add_argument("--include-approved", action="store_true",
                    help="También aplica sobre items aprobados (golden records). "
                         "Por defecto se saltean.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Muestra qué cambiaría sin escribir.")
    args = ap.parse_args(argv)

    items_path = args.items if args.items is not None else _default_items_path()
    results_path = args.results if args.results is not None else _default_results_path()
    log_path = args.log if args.log is not None else _default_log_path()

    return run(
        items_path, results_path, log_path,
        include_approved=args.include_approved,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
