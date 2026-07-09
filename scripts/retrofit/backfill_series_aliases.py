#!/usr/bin/env python3
"""backfill_series_aliases.py — remapea series_key/series_display de items.jsonl
a su forma canónica según data/series_aliases.yml y re-consolida lo dependiente.

Reemplaza el snippet embebido de ~60 líneas del skill /watch-enrich-series-aliases
(Step 4). Ese snippet, además de remapear, **deduplicaba con un comparador propio**
(`comp()`), reimplementando la consolidación — lo que viola la decisión #1: el merge
de productos tiene FUENTE ÚNICA (`merge_cluster`/`consolidate_by_cluster` en
manga_watch.py). Acá NO se reimplementa nada:

  1. Remap por serie: `canonical_series_key(title, series_key, series_display)`
     (fuente única de la resolución de aliases, importada de series_aliases.py).
  2. Si cambió `series_key`, se re-alinea el prefijo del `edition_key` y se
     re-deriva `cluster_key` con `manga_watch.derive_cluster_key`.
  3. La consolidación (1 fila por producto con `sources[]`) se DELEGA en
     `manga_watch.consolidate_by_cluster` (misma primitiva que usa la ingesta),
     SOLO sobre el corpus cargado — igual que consolidate_sources.py.

## Alcance ACOTADO por default — regla dura

`--only-keys key1,key2` es REQUERIDO por default: es la lista EXACTA de series_keys
que la corrida del skill acaba de procesar. SOLO se remapean los items cuyo
`series_key` actual está en esa lista; el resto del corpus NO se toca — aunque un
alias recién agregado también les aplicaría.

Sin `--only-keys` (ni `--all`) el script **ABORTA**. Es intencional: la memoria del
proyecto (auditoría post-scrape 2026-07-07) dejó la regla explícita
    "backfill de aliases NUNCA sobre todo el corpus (colapsos colaterales reales)".
Un alias nuevo mal elegido, aplicado a TODO el corpus, puede colapsar series ajenas
en toda la base. `--all` existe para el caso excepcional pero exige
`--yes-i-know-collateral` e imprime una advertencia fuerte.

Guard `approved_at` (golden records): las filas aprobadas NO se remapean salvo
`--include-approved` (patrón homogéneo de conventions.md).

Uso:
    backfill_series_aliases.py --only-keys atelier-des-sorciers,apothicaire
    backfill_series_aliases.py --only-keys foo --dry-run
    backfill_series_aliases.py --all --yes-i-know-collateral
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    import series_aliases  # type: ignore
    from manga_watch import (  # type: ignore
        backup_and_rotate,
        consolidate_by_cluster,
        derive_cluster_key,
        is_approved,
        rebuild_edition_key_prefix,
        write_items_atomic,
    )
except ImportError:  # pragma: no cover
    from scripts import series_aliases  # type: ignore
    from scripts.manga_watch import (  # type: ignore
        backup_and_rotate,
        consolidate_by_cluster,
        derive_cluster_key,
        is_approved,
        rebuild_edition_key_prefix,
        write_items_atomic,
    )


def _default_items_path() -> Path:
    """Resuelve items.jsonl respetando MANGA_WATCH_DATA_DIR (aislamiento en tests)."""
    data_dir = os.environ.get("MANGA_WATCH_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "items.jsonl"
    return _SCRIPTS.parent / "data" / "items.jsonl"


def _remap_item(it: dict) -> tuple[bool, bool]:
    """Aplica canonical_series_key a un item in-place.

    Devuelve (series_key_cambio, algun_cambio). Re-alinea el prefijo del
    edition_key y re-deriva cluster_key SOLO si cambió el series_key.
    """
    old_sk = it.get("series_key", "") or ""
    old_sd = it.get("series_display", "") or ""
    new_sk, new_sd = series_aliases.canonical_series_key(
        it.get("title", "") or "", old_sk, old_sd
    )
    if new_sk != old_sk:
        it["series_key"] = new_sk
        it["series_display"] = new_sd
        old_ek = it.get("edition_key", "") or ""
        # Re-alinear el prefijo del edition_key con la FUENTE ÚNICA
        # (manga_watch.rebuild_edition_key_prefix, la misma que usa
        # standardize_apply.py): parsea la cola `-{pub}-{slug}-{country}` desde
        # la derecha y re-arma con el series_key nuevo — cubre prefijos STALE
        # (serie truncada a 35 chars al acuñar la key) que el reemplazo por
        # startswith no detecta. Si devuelve None (key no parseable / formato
        # ajeno), fallback al startswith exacto; si tampoco, no se toca
        # (precisión > recall).
        rebuilt = rebuild_edition_key_prefix(old_ek, new_sk)
        if rebuilt:
            it["edition_key"] = rebuilt
        elif old_ek.startswith(old_sk + "-"):
            it["edition_key"] = new_sk + old_ek[len(old_sk):]
        # cluster_key viejo queda stale (edition_key cambió); re-derivar para que
        # consolidate_by_cluster fusione contra la fila canónica hermana.
        it["cluster_key"] = derive_cluster_key(it)
        return True, True
    if new_sd != old_sd:
        it["series_display"] = new_sd
        return False, True
    return False, False


def run(
    items_path: Path,
    *,
    only_keys: set[str] | None,
    all_corpus: bool,
    include_approved: bool,
    dry_run: bool,
) -> int:
    if not items_path.exists():
        print(f"[ERROR] no existe {items_path}", file=sys.stderr)
        return 1

    items: list[dict] = [
        json.loads(l) for l in items_path.read_text(encoding="utf-8").splitlines() if l.strip()
    ]
    print(f"[INFO] {len(items)} items en {items_path}")

    # series_aliases cachea el YAML; el skill acaba de editarlo → invalidar caches.
    series_aliases._load_aliases.cache_clear()
    series_aliases._build_lookup.cache_clear()
    series_aliases._build_aggressive_lookup.cache_clear()

    remapped = 0
    display_only = 0
    skipped_approved = 0
    series_changed = False
    for it in items:
        if is_approved(it) and not include_approved:
            skipped_approved += 1
            continue
        if not all_corpus:
            # Scope acotado: SOLO los series_key que la corrida procesó.
            if (it.get("series_key", "") or "") not in (only_keys or set()):
                continue
        sk_changed, any_changed = _remap_item(it)
        if sk_changed:
            remapped += 1
            series_changed = True
        elif any_changed:
            display_only += 1

    print(f"[INFO] series_key remapeados: {remapped}")
    print(f"[INFO] solo-display actualizados: {display_only}")
    if skipped_approved:
        print(f"[INFO] aprobados saltados (golden records): {skipped_approved}")

    out = items
    if series_changed:
        # Consolidación DELEGADA en la fuente única — nunca lógica propia (decisión #1).
        before = len(items)
        out = consolidate_by_cluster(items)
        collapsed = before - len(out)
        print(f"[INFO] consolidación: {before} → {len(out)} filas "
              f"({collapsed} colapsadas por la fuente única)")

    if remapped == 0 and display_only == 0:
        print("[OK] Sin cambios — no se escribe.")
        return 0

    if dry_run:
        print("[DRY-RUN] No se escribió nada.")
        return 0

    backup = backup_and_rotate(items_path, "series-aliases")
    print(f"[OK] Backup: {backup}")
    write_items_atomic(items_path, out)
    print(f"[OK] Escrito {items_path} ({len(out)} filas).")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=None,
                    help="items.jsonl a leer (default: data/items.jsonl / "
                         "MANGA_WATCH_DATA_DIR).")
    ap.add_argument("--only-keys", default="",
                    help="Lista separada por comas de los series_key a remapear "
                         "(EXACTAMENTE los que la corrida del skill procesó). "
                         "REQUERIDO salvo --all.")
    ap.add_argument("--all", dest="all_corpus", action="store_true",
                    help="Remapea TODO el corpus (caso excepcional). Exige "
                         "--yes-i-know-collateral. Riesgo de colapsos colaterales.")
    ap.add_argument("--yes-i-know-collateral", action="store_true",
                    help="Confirma que entendés el riesgo de --all sobre todo el corpus.")
    ap.add_argument("--include-approved", action="store_true",
                    help="También remapea items aprobados (golden records). Por "
                         "defecto se saltean.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Muestra qué cambiaría sin escribir.")
    args = ap.parse_args(argv)

    only_keys = {k.strip() for k in args.only_keys.split(",") if k.strip()}

    if not args.all_corpus and not only_keys:
        print(
            "[ABORTA] Falta --only-keys.\n"
            "  Este backfill remapea aliases de forma ACOTADA a las series_key que\n"
            "  se acaban de procesar. Correrlo sobre todo el corpus puede colapsar\n"
            "  series ajenas (regla dura, auditoría post-scrape 2026-07-07:\n"
            "  \"backfill de aliases NUNCA sobre todo el corpus\").\n"
            "  Pasá --only-keys key1,key2 (lo que hizo el skill) o, para el caso\n"
            "  excepcional, --all --yes-i-know-collateral.",
            file=sys.stderr,
        )
        return 2

    if args.all_corpus and not args.yes_i_know_collateral:
        print(
            "[ABORTA] --all sobre TODO el corpus requiere --yes-i-know-collateral.\n"
            "  ADVERTENCIA: un alias nuevo mal elegido puede colapsar series ajenas\n"
            "  en toda la base. Preferí --only-keys salvo que sepas exactamente qué\n"
            "  estás haciendo.",
            file=sys.stderr,
        )
        return 2

    if args.all_corpus:
        print("[WARN] --all: remapeando TODO el corpus. Riesgo de colapsos colaterales.",
              file=sys.stderr)

    items_path = args.input if args.input is not None else _default_items_path()
    return run(
        items_path,
        only_keys=only_keys,
        all_corpus=args.all_corpus,
        include_approved=args.include_approved,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
