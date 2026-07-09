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
import json, sys, argparse, collections, re
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
_COLLISION_RE = re.compile(r"c\d+")  # sufijo opcional de colisión de slug ("-c2")


def _has_country_suffix(ek: str, country_slug: str = "") -> bool:
    """True si el edition_key ya termina en un sufijo país RECONOCIBLE.

    (Se conserva por compat/legibilidad; la lógica autoritativa vive en
    `_suffix_country`, que además CORRIGE un sufijo país equivocado.)
    """
    tail = ek.rsplit("-", 1)[-1] if "-" in ek else ""
    # Idempotencia ROBUSTA (gotcha #91): además de los códigos del mapa,
    # aceptar el código COMPUTADO para el país de este item — si el país no
    # está en el mapa, el fallback de 4 letras (cheq/turq/core…) seguía sin
    # reconocerse y cada corrida del enforcer re-apendeaba otro sufijo
    # (caso real: "…-cheq-cheq-cheq" tras 3 corridas).
    if country_slug and tail == country_slug:
        return True
    return tail in _VALID_SLUGS or tail == "xx"


def _suffix_country(ek: str, country: str) -> str:
    """Deja el sufijo país del edition_key reflejando `item.country` (país=edición).

    Dos comportamientos (idempotentes):
      1. APENDA `-{slug}` si el edition_key no termina en un sufijo país
         reconocible (comportamiento histórico: separar mercados).
      2. CORRIGE el sufijo país cuando el último segmento ES un country_slug
         CONOCIDO pero DISTINTO del correcto — reemplaza el equivocado por el
         de `item.country` (fuente de verdad). Caso real: Jade Dynasty (HK)
         quedó con `…-tw` tras el standardize; el sufijo `tw` es un slug válido,
         así que el motor viejo lo daba por "ya sufijado" y NUNCA lo arreglaba.

    Cautela (agrupación): sólo se REEMPLAZA el último segmento si es un
    country_slug CONOCIDO (`_VALID_SLUGS`), el mismo conjunto que la invariante
    PAISKEY de validate_corpus vigila. Un segmento corto que NO es país conocido
    (un token de edición, `xx` placeholder, un sufijo roto tipo `glob`) NO se
    toca como país → se cae al comportamiento de apendar. Se respeta un sufijo
    de colisión opcional `-cN` (se separa, se corrige el país, se re-apenda).
    """
    cs = mw._country_slug(country)
    if cs == "xx":
        # País desconocido: no sabemos el correcto → no clobbereamos un sufijo
        # existente ni inventamos país. Comportamiento histórico: apendar `-xx`
        # sólo si no hay ningún sufijo país reconocible.
        if _has_country_suffix(ek, cs):
            return ek
        return f"{ek}-{cs}"

    segs = ek.split("-")
    coll = ""
    if len(segs) >= 2 and _COLLISION_RE.fullmatch(segs[-1]):
        coll = segs.pop()  # separar el sufijo de colisión "-cN"
    if not segs:
        return ek  # degenerado (edition_key vacío o sólo "-cN")

    tail = segs[-1]
    if tail == cs:
        return ek  # ya correcto (idempotente)
    if tail in _VALID_SLUGS:
        segs[-1] = cs  # sufijo país EQUIVOCADO (p.ej. tw) → corregir a `cs` (hk)
    elif tail == "xx":
        # placeholder explícito de "país desconocido": scope acotado, no lo
        # convertimos aquí (lo maneja fix_edition_key_anomalies con reglas duras).
        return ek
    else:
        segs.append(cs)  # sin sufijo país reconocible → apendar (histórico)

    new_ek = "-".join(segs)
    return f"{new_ek}-{coll}" if coll else new_ek


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
    backup = mw.backup_and_rotate(ITEMS, "editioncountry")
    print(f"[edition-country] backup: {backup}")
    mw.write_items_atomic(ITEMS, new_rows)
    print(f"[edition-country] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
