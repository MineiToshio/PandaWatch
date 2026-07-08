#!/usr/bin/env python3
"""fix_edition_country.py — REGLA DE NEGOCIO DURA: país distinto = edición distinta.

Hornea el país (de la EDICIÓN = `item.country`) en el `edition_key` como sufijo
(`…-{country_slug}`), de modo que dos mercados NUNCA compartan edición/cluster
aunque coincidan series+publisher+edición (gotcha #46). Caso real: Hunter x Hunter
Panini mezclaba tomos de España e Italia bajo `hunter-x-hunter-panini-variant`.

SUFIJA país: a cada fila se le apenda `-{country_slug(item.country)}` al
edition_key si aún no lo tiene. Idempotente. Esto separa, en la vista de edición
(que agrupa por edition_key), las filas de mercados distintos que antes compartían
edition_key (Hunter x Hunter ES vs IT). Luego recomputa cluster_key y consolida.

El país que importa es el de la EDICIÓN (`item.country`, derivado de editorial/
idioma), NO el de cada tienda: una tienda italiana puede revender la edición
francesa (Manga Dreams) y eso sigue siendo UNA edición. Por eso NO escindimos
`sources[]` por país automáticamente (es frágil con publishers sucios) — las
fusiones cross-país REALES (misma editorial matriz, dos mercados) se separan a
mano / las previene el motor nuevo de aquí en más.

Uso:
  .venv/bin/python scripts/retrofit/fix_edition_country.py --dry-run
  .venv/bin/python scripts/retrofit/fix_edition_country.py
"""
from __future__ import annotations
import json, sys, argparse, shutil, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
try:  # import dual robusto (CLI directo vs wrapper raíz bajo pytest)
    import manga_watch as mw  # noqa: E402
    mw._COUNTRY_SLUG_MAP  # type: ignore  # el wrapper raíz no lo tiene (en pytest)
except (ImportError, AttributeError):  # pragma: no cover
    import scripts.manga_watch as mw  # type: ignore  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
_VALID_SLUGS = set(mw._COUNTRY_SLUG_MAP.values())


def _has_country_suffix(ek: str, country_slug: str = "") -> bool:
    tail = ek.rsplit("-", 1)[-1] if "-" in ek else ""
    # Idempotencia ROBUSTA (gotcha #91): además de los códigos del mapa,
    # aceptar el código COMPUTADO para el país de este item — si el país no
    # está en el mapa, el fallback de 4 letras (cheq/turq/core…) seguía sin
    # reconocerse y cada corrida del enforcer re-apendeaba otro sufijo
    # (caso real: "…-cheq-cheq-cheq" tras 3 corridas).
    if country_slug and tail == country_slug:
        return True
    return tail in _VALID_SLUGS or (len(tail) in (2, 4) and tail == "xx")


def _suffix_country(ek: str, country: str) -> str:
    cs = mw._country_slug(country)
    if _has_country_suffix(ek, cs):
        return ek  # ya sufijado (idempotente)
    return f"{ek}-{cs}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-approved", action="store_true",
                     help="También sufija el país de items aprobados (golden records). Por "
                          "defecto se saltean: sufijar cambia edition_key/cluster_key, la "
                          "identidad que approved_at confirma. Riesgo de fragmentación: ver "
                          "el paso final 'apply_approvals' en enforce_listadomanga_rules.py.")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    # --- Sufijar país en edition_key + recompute cluster_key ---
    changed = 0
    skipped_approved = 0
    for it in items:
        if mw.is_approved(it) and not args.include_approved:
            skipped_approved += 1
            continue
        ek = it.get("edition_key") or ""
        if not ek:
            continue
        new_ek = _suffix_country(ek, it.get("country") or "")
        if new_ek != ek:
            it["edition_key"] = new_ek
            it["cluster_key"] = mw.derive_cluster_key(it)
            changed += 1

    print(f"[edition-country] edition_key sufijados con país: {changed}")
    if skipped_approved:
        print(f"[edition-country] items aprobados saltados (usar --include-approved): {skipped_approved}")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    before = len(items)
    new_rows = mw.consolidate_by_cluster(items)
    print(f"[edition-country] consolidate: {before} → {len(new_rows)}")
    shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-editioncountry-bak"))
    tmp = ITEMS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in new_rows:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(ITEMS)
    print(f"[edition-country] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
