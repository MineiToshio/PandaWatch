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
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402
from series_aliases import is_canonical_key  # noqa: E402  (fuente única del resolver)

ITEMS = ROOT / "data" / "items.jsonl"

# series_key con pinta de basura de extracción: cortito y puramente numérico,
# a lo sumo con un sufijo de 1-3 letras (ej. "4-2-ss", "12-3"). Un series_key así
# NUNCA debe ganar la selección de ganador de un grupo ISBN (guard del red team).
_JUNK_SK_RE = re.compile(r"^\d+(-\d+)*(-[a-z]{1,3})?$")


def _is_junk_series_key(series_key: str) -> bool:
    sk = (series_key or "").strip().lower()
    return bool(sk) and bool(_JUNK_SK_RE.match(sk))


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
        # series_key que más se repite DENTRO del grupo: señal de identidad real
        # frente a un slug que aparece en una sola fila (red team, criterio b).
        sk_group: Counter = Counter(
            (it.get("series_key") or "") for it in group if it.get("series_key")
        )
        # Scores precomputados: list.sort() vacía la lista mientras ordena,
        # así que _evidence NO puede iterar `group` dentro del key=.
        # Todos los criterios: MAYOR = mejor (sort reverse=True).
        scores = {
            id(it): (
                bool(it.get("approved_at")),
                # (b) nunca elegir un series_key con pinta de junk como ganador.
                not _is_junk_series_key(it.get("series_key") or ""),
                # (a) edition_key VACÍO = PEOR candidato: no puede ganar contra
                # una fila con keys reales (el bug era que ek vacío puntuaba como
                # "sin unknown" = True y ganaba).
                bool((it.get("edition_key") or "").strip()),
                # editorial real (sin 'unknown' en el ek): sólo desempata entre
                # los que YA tienen ek — los sin-ek ya perdieron en el criterio
                # anterior, así que el True vacuo de "".split('-') es inocuo.
                bool((it.get("edition_key") or "").strip())
                and "unknown" not in (it.get("edition_key") or "").split("-"),
                # (b) series_key canónico en series_aliases (fuente única).
                is_canonical_key(it.get("series_key") or ""),
                # (b) series_key que aparece en más filas del grupo.
                sk_group.get(it.get("series_key") or "", 0),
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


def apply_merges(items: list[dict]) -> dict:
    """Planifica y aplica las fusiones ISBN sobre `items` (mutación in-place de
    las filas + consolidación por cluster). PURA: no lee ni escribe archivos.

    Idempotente / CONVERGENTE: correr `apply_merges` sobre su propia salida
    consolidada → `changed == 0` (el grupo ISBN queda con 1 fila y se saltea; y
    aunque quedaran filas, sólo se cuenta un cambio cuando el row REALMENTE
    cambia — comparación before/after —, no incondicionalmente como antes).

    Devuelve `{items, changed, skipped, rewrites, mergeable}`.
    """
    mergeable, skipped = plan_groups(items)
    changed = 0
    rewrites: list[str] = []
    for group in mergeable:
        winner, losers = group[0], group[1:]
        # volumen unificado: el del ganador si está approved; si no, el único
        # no-vacío del grupo (plan_groups garantiza <=1 volumen distinto).
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
            before = (
                it.get("edition_key"), it.get("series_key"),
                it.get("series_display"), (it.get("volume") or "").strip(),
                it.get("cluster_key"),
            )
            old_ek, old_vol = it.get("edition_key"), it.get("volume", "")
            for field in ("edition_key", "series_key", "series_display"):
                if winner.get(field):
                    it[field] = winner[field]
            it["volume"] = vol
            it["cluster_key"] = mw.derive_cluster_key(it)
            after = (
                it.get("edition_key"), it.get("series_key"),
                it.get("series_display"), (it.get("volume") or "").strip(),
                it.get("cluster_key"),
            )
            if before != after:
                rewrites.append(
                    f"{old_ek}|{old_vol}  →  {winner.get('edition_key')}|{vol}"
                    f"  ({(it.get('title') or '')[:50]!r})")
                changed += 1
    if changed:
        items = mw.consolidate_by_cluster(items)
    return {
        "items": items, "changed": changed, "skipped": skipped,
        "rewrites": rewrites, "mergeable": len(mergeable),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    # B11 (Fable 2026-07-08): una línea corrupta se preserva tal cual en vez
    # de tumbar el script con una excepción sin capturar. Se mantiene FUERA
    # de `items` (apply_merges/consolidate_by_cluster/derive_cluster_key
    # esperan dicts reales) y se reinyecta verbatim al escribir.
    items: list[dict] = []
    raw_lines: list[str] = []
    with ITEMS.open(encoding="utf-8") as fh:
        for l in fh:
            if not l.strip():
                continue
            try:
                items.append(json.loads(l))
            except json.JSONDecodeError:
                raw_lines.append(l.rstrip("\n"))
    if raw_lines:
        print(f"[isbn-dup][WARN] {len(raw_lines)} línea(s) corrupta(s) preservada(s) tal cual.")

    before_n = len(items)
    result = apply_merges(items)
    for msg in result["skipped"]:
        print(f"[isbn-dup] SKIP {msg}")
    for msg in result["rewrites"]:
        print(f"[isbn-dup]   {msg}")

    changed = result["changed"]
    print(f"[isbn-dup] grupos fusionables: {result['mergeable']} | items reescritos: "
          f"{changed} | grupos saltados: {len(result['skipped'])}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    # A13 (Fable 2026-07-08): backup_and_rotate en vez de shutil.copy a un
    # path propio (data/items.jsonl.pre-isbndup-bak sin rotar, sumaba a los
    # 38 siblings sueltos / 1.1 GB del hallazgo). Sólo escribe si changed>0.
    if changed:
        new_items = result["items"]
        print(f"[isbn-dup] consolidate: {before_n} → {len(new_items)}")
        mw.backup_and_rotate(ITEMS, "isbn-dup")
        out_lines = [json.dumps(it, ensure_ascii=False, sort_keys=True) for it in new_items] + raw_lines
        mw.write_lines_atomic(ITEMS, out_lines)
        print(f"[isbn-dup] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
