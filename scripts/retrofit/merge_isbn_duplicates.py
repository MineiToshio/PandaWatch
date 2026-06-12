#!/usr/bin/env python3
"""merge_isbn_duplicates.py — fusiona items duplicados que comparten ISBN.

PROBLEMA (auditoría 2026-06-10): el mismo libro físico aparece 2 veces porque
cada fuente derivó un `edition_key` ligeramente distinto (drift de slug:
`akitashoten` vs `akita`, `unknown` vs editorial real, serie partida tipo
`jiro-taniguchi-collection` vs `the-book-of-wind`), o porque una fila tiene
volumen y la otra no (`...|1` vs `...|`). El ISBN-13 es único por
edición+mercado: dos items con el MISMO ISBN son el MISMO producto.

FIX: agrupa por `isbn13(isbn)` y dentro de cada grupo >1:
  - elige GANADOR por: approved > popularidad del edition_key en el corpus
    (cuántos items lo comparten — mantiene junta una edición multi-tomo) >
    editorial real (sin `unknown` en el ek) > standardized > nº sources;
  - reescribe en los perdedores: edition_key/series_key/series_display del
    ganador + volumen unificado (el único no-vacío del grupo; si el ganador
    está approved, SU volumen), y re-deriva cluster_key;
  - `consolidate_by_cluster` (merge canónico, decisión #1) fusiona las filas.

NO toca (reporta y salta):
  - grupos con algún item de listadomanga (tier `lmc:` — reglas propias,
    los cruces tienda→lmc los maneja merge_crosssource_into_lmc);
  - grupos con >1 país no-vacío (país=edición es regla dura; ISBN compartido
    entre países = dato sucio a investigar, no a fusionar);
  - grupos con >1 volumen no-vacío distinto (ISBN reusado o volumen mal
    extraído — fusionarlos violaría DUPVOL);
  - grupos con >1 item approved con edition_key distinto (approved no se toca).

Idempotente: segunda corrida → 0 cambios.

Uso:
  .venv/bin/python scripts/retrofit/merge_isbn_duplicates.py --dry-run
  .venv/bin/python scripts/retrofit/merge_isbn_duplicates.py
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"


def _norm_isbn(it: dict) -> str:
    isbn = (it.get("isbn") or "").strip()
    if not isbn:
        return ""
    return mw.isbn13(isbn) or isbn


def plan_groups(items: list[dict]) -> tuple[list[list[dict]], list[str]]:
    """→ (grupos fusionables, motivos de los grupos saltados)."""
    by_isbn: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        n = _norm_isbn(it)
        if n:
            by_isbn[n].append(it)

    ek_counts: Counter = Counter(
        (it.get("edition_key") or "") for it in items if it.get("edition_key")
    )

    mergeable: list[list[dict]] = []
    skipped: list[str] = []
    for isbn, group in sorted(by_isbn.items()):
        if len(group) < 2:
            continue
        # Ya fusionado (mismo cluster) — nada que hacer.
        if len({it.get("cluster_key", "") for it in group}) == 1:
            continue
        tiers = {(it.get("cluster_key", "") or "").split(":", 1)[0] for it in group}
        if "lmc" in tiers:
            skipped.append(f"{isbn}: toca listadomanga (lmc) — lo maneja "
                           "merge_crosssource_into_lmc")
            continue
        countries = {(it.get("country") or "").strip() for it in group} - {""}
        if len(countries) > 1:
            skipped.append(f"{isbn}: países en conflicto {sorted(countries)} — "
                           "dato sucio, investigar (país=edición)")
            continue
        vols = {(it.get("volume") or "").strip() for it in group} - {""}
        if len(vols) > 1:
            skipped.append(f"{isbn}: volúmenes en conflicto {sorted(vols)} — "
                           "ISBN reusado o volumen mal extraído")
            continue
        approved_eks = {(it.get("edition_key") or "") for it in group
                        if it.get("approved_at")}
        if len(approved_eks) > 1:
            skipped.append(f"{isbn}: >1 item approved con edition_key distinto")
            continue
        mergeable.append(group)

    # ordenar cada grupo: ganador primero
    def _blob_tokens(it: dict) -> set[str]:
        parts = [it.get("title") or "", it.get("url") or ""]
        for s in it.get("sources") or []:
            parts.append(s.get("url") or "")
        # tokens exactos, no substrings ('rave' NO debe matchear 'travel')
        return set(re.split(r"[^a-z0-9]+", " ".join(parts).lower())) - {""}

    def _evidence(series_key: str, group: list[dict]) -> float:
        """Cuántos items del grupo respaldan esta serie en su título/URL.
        Detecta identidades mal extraídas (ej. un 'Rave Variant' cuya URL es
        super-string-marco-polo → gana marco-polo aunque rave sea más popular)."""
        tokens = [t for t in series_key.split("-") if len(t) > 2]
        if not tokens:
            return 0.0
        total = 0.0
        for it in group:
            blob = _blob_tokens(it)
            total += sum(1 for t in tokens if t in blob) / len(tokens)
        return total

    for group in mergeable:
        # Scores precomputados: list.sort() vacía la lista mientras ordena,
        # así que _evidence NO puede iterar `group` dentro del key=.
        scores = {
            id(it): (
                bool(it.get("approved_at")),
                "unknown" not in (it.get("edition_key") or "").split("-"),
                round(_evidence(it.get("series_key") or "", group), 2),
                ek_counts[it.get("edition_key") or ""],
                (it.get("edition_key") or "").startswith(
                    (it.get("series_key") or "\x00") + "-"),
                bool(it.get("standardized_at")),
                len(it.get("sources") or []),
            )
            for it in group
        }
        group.sort(key=lambda it: scores[id(it)], reverse=True)
    return mergeable, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    mergeable, skipped = plan_groups(items)
    for msg in skipped:
        print(f"[isbn-dup] SKIP {msg}")

    changed = 0
    for group in mergeable:
        winner, losers = group[0], group[1:]
        # volumen unificado: el del ganador si está approved; si no, el único
        # no-vacío del grupo.
        vols = {(it.get("volume") or "").strip() for it in group} - {""}
        if winner.get("approved_at"):
            vol = (winner.get("volume") or "").strip()
        else:
            vol = next(iter(vols)) if vols else ""
        if not winner.get("approved_at") and (winner.get("volume") or "").strip() != vol:
            winner["volume"] = vol
            winner["cluster_key"] = mw.derive_cluster_key(winner)
            changed += 1
        for it in losers:
            if it.get("approved_at"):
                continue
            print(f"[isbn-dup]   {it.get('edition_key')}|{it.get('volume','')}"
                  f"  →  {winner.get('edition_key')}|{vol}"
                  f"  ({(it.get('title') or '')[:50]!r})")
            for field in ("edition_key", "series_key", "series_display"):
                if winner.get(field):
                    it[field] = winner[field]
            it["volume"] = vol
            it["cluster_key"] = mw.derive_cluster_key(it)
            changed += 1

    print(f"[isbn-dup] grupos fusionables: {len(mergeable)} | items reescritos: "
          f"{changed} | grupos saltados: {len(skipped)}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        before = len(items)
        items = mw.consolidate_by_cluster(items)
        print(f"[isbn-dup] consolidate: {before} → {len(items)}")
        shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-isbndup-bak"))
        tmp = ITEMS.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        tmp.replace(ITEMS)
        print(f"[isbn-dup] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
