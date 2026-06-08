#!/usr/bin/env python3
"""disambiguate_coleccion_editions.py — coleccion distinta = edición distinta
(gotcha #57). Cuando standardize asigna el MISMO edition_key a /coleccion DISTINTAS
(ediciones realmente distintas: Biomega "Ultimate" cole 2572 vs "Master" cole 4501;
Magic Knight Rayearth cole 245 vs Rayearth 2 cole 322), sus tomos del mismo volumen
aparecen DUPLICADOS en la vista de edición (mismo edition_key+vol).

Fix: si un edition_key abarca >1 colección, se desambigua insertando `-c{cole}` antes
del sufijo de país en CADA item (todos los de una cole comparten su edition_key
propio → coleccion=edición se mantiene, pero cada cole es su edición). Re-deriva
cluster_key. Idempotente (si ya lleva `-cNNNN`, no re-inserta). Respeta `approved_at`.

Uso:
  .venv/bin/python scripts/retrofit/disambiguate_coleccion_editions.py --dry-run
  .venv/bin/python scripts/retrofit/disambiguate_coleccion_editions.py
"""
from __future__ import annotations
import json, re, sys, argparse, shutil, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import manga_watch as mw  # noqa: E402
    mw._COUNTRY_SLUG_MAP  # type: ignore
except (ImportError, AttributeError):
    import scripts.manga_watch as mw  # type: ignore  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
_COLE = re.compile(r"coleccion\.php\?id=(\d+)")
_LMC = re.compile(r"^lmc:(\d+):")
_VALID = set(mw._COUNTRY_SLUG_MAP.values()) | {"xx"}


def _cole_of(it) -> str | None:
    m = _LMC.match(it.get("cluster_key", "") or "")
    if m:
        return m.group(1)
    coles = {_COLE.search(u).group(1) for u in
             [it.get("url", "")] + [s.get("url", "") for s in (it.get("sources") or [])]
             if _COLE.search(u or "")}
    return next(iter(coles)) if len(coles) == 1 else None


def _insert_cole(ek: str, cole: str) -> str:
    parts = ek.split("-")
    if any(re.fullmatch(r"c\d+", p) for p in parts):
        return ek  # ya desambiguado
    if parts and parts[-1] in _VALID:  # insertar antes del país
        return "-".join(parts[:-1] + [f"c{cole}", parts[-1]])
    return f"{ek}-c{cole}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    by_ek = collections.defaultdict(list)
    for it in items:
        ek = it.get("edition_key") or ""
        if ek:
            by_ek[ek].append(it)

    changed, ex = 0, []
    for ek, grp in by_ek.items():
        coles = {c for it in grp if (c := _cole_of(it))}
        if len(coles) < 2:
            continue
        for it in grp:
            if it.get("approved_at"):
                continue
            cole = _cole_of(it)
            if not cole:
                continue
            new = _insert_cole(ek, cole)
            if new != ek:
                if len(ex) < 20:
                    ex.append((ek, new, it.get("title")))
                it["edition_key"] = new
                it["cluster_key"] = mw.derive_cluster_key(it)
                changed += 1

    print(f"[disambig-cole] edition_key desambiguados por colección: {changed}")
    for o, n, t in ex:
        print(f"    {o}  →  {n}   ({t!r})")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    if changed:
        shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-disambigcole-bak"))
        tmp = ITEMS.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        tmp.replace(ITEMS)
        print(f"[disambig-cole] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
