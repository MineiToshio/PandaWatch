#!/usr/bin/env python3
"""unify_coleccion_edition.py — una /coleccion de listadomanga = UNA página de
edición (gotcha #42/#48). Todos los items de la misma coleccion comparten el
MISMO `edition_key` (el de la edición BASE de la coleccion), de modo que la vista
de edición los muestre juntos: tomos regulares, especiales, cofres y variantes.

Antes el parser/skill separaba dentro de una coleccion `…-regular` vs
`…-special-c{id}` → la edición especial caía en otra página. El owner: "de una
misma /coleccion se agrupan TODOS esos tomos en una misma página de edición".

Distinción de variantes del mismo volumen (regular-34 vs especial-34): NO la da
el edition_key (ahora común) sino el `cluster_key` (tier-0 listadomanga =
`lmc:{coleccion}:{kind}:{vol}`). Para old-format sin `&item=` en la URL se
persiste el kind en `lm_kind` (derivado del edition_slug viejo) para que
`derive_cluster_key` lo use.

Base de la coleccion: el edition_key cuyo edition_slug es `regular` si existe;
si no, el más frecuente (la edición predominante, ej. Berserk Maximum).

Uso:
  .venv/bin/python scripts/retrofit/unify_coleccion_edition.py --dry-run
  .venv/bin/python scripts/retrofit/unify_coleccion_edition.py
"""
from __future__ import annotations
import json, re, sys, argparse, shutil, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import manga_watch as mw  # noqa: E402
    mw._COUNTRY_SLUG_MAP  # type: ignore  # el wrapper raíz no lo tiene (en pytest)
except (ImportError, AttributeError):
    import scripts.manga_watch as mw  # type: ignore  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"
_COLE_RE = re.compile(r"listadomanga\.es/coleccion\.php\?id=(\d+)")
_ITEM_RE = re.compile(r"[?&]item=([a-z]+)-([^-&]+)")
_VALID_COUNTRY = set(mw._COUNTRY_SLUG_MAP.values()) | {"xx"}


def _cole(u: str) -> str | None:
    m = _COLE_RE.search(u or "")
    return m.group(1) if m else None


def _cole_of_item(it: dict) -> str | None:
    """colección a la que pertenece la fila. Primaria si es de listadomanga; si no
    (fila de TIENDA cross-source), la única colección referenciada por sus
    `sources[]` — así la ficha de tienda (Panini Pack/Metalizada, Norma) se unifica
    al edition_key base de su colección (coleccion=edición, gotcha #48). Si referencia
    >1 colección distinta, NO se asigna (ambiguo)."""
    c = _cole(it.get("url", ""))
    if c:
        return c
    coles = {_cole(s.get("url", "")) for s in (it.get("sources") or [])}
    coles.discard(None)
    return next(iter(coles)) if len(coles) == 1 else None


def _edition_slug(ek: str) -> str:
    """edition_slug de un edition_key `series-publisher-edition[-cNNNN]-country`."""
    parts = (ek or "").split("-")
    if len(parts) < 2:
        return ""
    parts = parts[:-1] if parts[-1] in _VALID_COUNTRY else parts  # drop country
    if parts and re.fullmatch(r"c\d+", parts[-1]):
        parts = parts[:-1]  # drop -cNNNN
    return parts[-1] if parts else ""


def _kind_of(it: dict) -> str:
    """kind para el cluster: del &item= URL, o del edition_slug (old-format)."""
    m = _ITEM_RE.search(it.get("url") or "")
    if m:
        return m.group(1)
    return _edition_slug(it.get("edition_key") or "") or "regular"


_LMC_RE = re.compile(r"^lmc:\d+:([a-z]+):(.*)$")
_BOX_TITLE_RE = re.compile(r"box\s*set|boxset|\bcofre\b|estuche|\bcaja\b", re.IGNORECASE)


def _is_box(it: dict) -> bool:
    """True si el item es un BOX SET (= edición APARTE, gotcha #58). Regla del owner:
    pack/edición especial/portada alternativa conviven en la MISMA edición, pero un
    box set es una edición distinta. Box = cluster kind `boxset`, o `pack` con
    volumen-rango/vacío o título de cofre. Un `pack:42` (tomo suelto mal clusterizado)
    NO es box."""
    m = _LMC_RE.match(it.get("cluster_key", "") or "")
    if not m:
        return False
    kind, vol = m.group(1), m.group(2)
    title_box = bool(_BOX_TITLE_RE.search(it.get("title", "") or ""))
    multi_vol = "-" in vol or vol in ("", "0")  # rango/vacío, NO un tomo suelto
    if kind == "boxset":
        return True
    if kind == "pack":
        return multi_vol or title_box
    # otros kinds (limited/special/…): box sólo si el TÍTULO lo dice Y no es un tomo
    # numérico suelto (ej. "Uzumaki Box Set Edición Limitada" = limited:0).
    return title_box and multi_vol


def _with_slug(ek: str, new_slug: str) -> str:
    """Reemplaza el edition_slug de un edition_key, preservando serie, publisher,
    desambiguador `-cNNNN` y país."""
    parts = (ek or "").split("-")
    country = parts.pop() if parts and parts[-1] in _VALID_COUNTRY else ""
    disamb = parts.pop() if parts and re.fullmatch(r"c\d+", parts[-1]) else ""
    if parts:
        parts[-1] = new_slug
    if disamb:
        parts.append(disamb)
    if country:
        parts.append(country)
    return "-".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    by_cole: dict[str, list[dict]] = collections.defaultdict(list)
    for it in items:
        c = _cole_of_item(it)
        if c:
            by_cole[c].append(it)

    changed, diffs = 0, []
    for c, grp in by_cole.items():
        # 1) persistir lm_kind en cada item (para el cluster de old-format)
        for it in grp:
            it["lm_kind"] = _kind_of(it)
        # 2) separar BOX SETS (= edición aparte, gotcha #58) de los tomos. El base
        # de la edición se calcula SÓLO con los NO-box; los box van a su propia
        # edición (slug `boxset`).
        box = [it for it in grp if _is_box(it)]
        rest = [it for it in grp if not _is_box(it)]
        # candidatos del base: los NO-box; preferir país CONOCIDO (no `-xx`, #46).
        pool = rest or grp
        cand = [it for it in pool if it.get("edition_key")]
        non_xx = [it for it in cand if not (it.get("edition_key") or "").endswith("-xx")]
        cand = non_xx or cand
        if not cand:
            continue
        eks = [it.get("edition_key") for it in cand]
        regular = [it for it in cand if _edition_slug(it.get("edition_key") or "") == "regular"]
        if regular:
            base = max(regular, key=lambda it: int(bool(it.get("standardized_at"))))
        else:
            freq = collections.Counter(eks)
            top_ek = freq.most_common(1)[0][0]
            base = next(it for it in cand if it.get("edition_key") == top_ek)
        base_ek = base.get("edition_key")
        base_sk = base.get("series_key")
        base_sd = base.get("series_display", "")
        base_ed = base.get("edition_display", "")
        # Si el base de los TOMOS quedó con slug `boxset` (contaminado por un unify
        # viejo que lo colapsó con el box) y hay tomos no-box, normalizar a `regular`.
        if rest and box and _edition_slug(base_ek) == "boxset":
            base_ek = _with_slug(base_ek, "regular")
        box_ek = _with_slug(base_ek, "boxset")  # edición separada para los box

        # 3) asignar: tomos → base_ek; box sets → box_ek (misma serie, su display propio)
        for it in grp:
            is_box = _is_box(it)
            tgt_ek = box_ek if is_box else base_ek
            if it.get("edition_key") == tgt_ek and it.get("series_key") == base_sk:
                it["cluster_key"] = mw.derive_cluster_key(it)  # refresca (tier-0)
                continue
            if len(diffs) < 40:
                diffs.append((c, it.get("edition_key"), tgt_ek, it.get("title")))
            if not args.dry_run:
                it["series_key"] = base_sk
                it["edition_key"] = tgt_ek
                if not is_box:  # los box conservan su edition_display propio ("X Box Set")
                    it["series_display"] = base_sd
                    it["edition_display"] = base_ed
            it["cluster_key"] = mw.derive_cluster_key(it)
            changed += 1

    print(f"[unify-coleccion] items re-asignados al edition_key de su coleccion: {changed}")
    for c, oek, nek, t in diffs[:40]:
        print(f"    cole {c}: {oek}  →  {nek}   ({t!r})")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    from manga_watch import consolidate_by_cluster
    before = len(items)
    items = consolidate_by_cluster(items)
    print(f"[unify-coleccion] consolidate: {before} → {len(items)}")
    shutil.copy(ITEMS, ITEMS.with_suffix(".jsonl.pre-unifycole-bak"))
    tmp = ITEMS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(ITEMS)
    print(f"[unify-coleccion] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
