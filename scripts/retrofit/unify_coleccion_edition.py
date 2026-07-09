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
import json, re, sys, argparse, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import manga_watch as mw  # noqa: E402
    mw._COUNTRY_SLUG_MAP  # type: ignore  # el wrapper raíz no lo tiene (en pytest)
except (ImportError, AttributeError):
    import scripts.manga_watch as mw  # type: ignore  # noqa: E402
# FUENTE ÚNICA del patrón de folleto promocional gratuito (gotcha #103): NO se
# copia, se importa del parser de colecciones.
try:
    from wikis.listadomanga_collections import FREE_PRICE_PATTERN  # noqa: E402
except ImportError:  # pragma: no cover
    from scripts.wikis.listadomanga_collections import FREE_PRICE_PATTERN  # type: ignore  # noqa: E402

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


_LMC_RE = re.compile(r"^lmc:\d+:([a-z]+):(.*)$")


def _kind_of(it: dict) -> str:
    """kind para el cluster: del &item= URL (new-format), del kind ya persistido en
    el `cluster_key` lmc (old-format), o del edition_slug como último recurso.

    Preferir el kind del cluster_key EXISTENTE (que este script NO toca) sobre el
    edition_slug es lo que hace idempotente el auto-corte de variantes especiales:
    cuando carvamos un tomo cambiándole el edition_slug de `regular` a
    `special`/`limited`, el `lm_kind` recomputado en la pasada siguiente NO debe
    heredar ese slug nuevo (eso movería el cluster y rompería la idempotencia). El
    cluster ya lleva el kind correcto de la /coleccion, así que lo echamos de ahí.
    En la primera corrida cluster_kind == edition_slug (ambos derivan del mismo
    parseo), así que no cambia el comportamiento de los items no-carvados."""
    m = _ITEM_RE.search(it.get("url") or "")
    if m:
        return m.group(1)
    mc = _LMC_RE.match(it.get("cluster_key", "") or "")
    if mc:
        return mc.group(1)
    return _edition_slug(it.get("edition_key") or "") or "regular"


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


# Tipos de edición que se venden APARTE (con bonus físico) y por eso se carvan en
# su PROPIA página de edición dentro de la coleccion, en vez de plegarse al
# `regular`. No incluye `boxset` (ya lo separa `_is_box`) ni `variant`/`pack`
# (portada alternativa / pack conviven en la MISMA edición, regla del owner).
_CARVE_SLUGS = {"special", "limited", "deluxe"}
# kind del synthetic/cluster (español) → slug de tipo canónico.
_CANON_KIND = {"especial": "special", "limitada": "limited", "alternativa": "variant"}
_PROMO_DESC_RE = re.compile(r"edici[oó]n\s+promocional", re.IGNORECASE)


def _is_promo(it: dict) -> bool:
    """Folleto PROMOCIONAL gratuito (gotcha #103): NO es una edición coleccionable
    aunque el título lleve una palabra de tipo. Se detecta por el precio crudo
    `Número Gratuito` (patrón único importado del parser) o por `Edición
    Promocional` en la descripción (distinto de `Edición Especial`). Estos NO se
    carvan como especial: quedan fuera del corte (siguen como regular)."""
    if FREE_PRICE_PATTERN.match((it.get("price") or "").strip()):
        return True
    if _PROMO_DESC_RE.search(it.get("description") or ""):
        return True
    return False


def _carve_ek(base_ek: str, slug: str, cole: str) -> str:
    """edition_key de la variante especial carvada, NAMESPACEADO por coleccion.

    Cada /coleccion es su PROPIA edición (coleccion=edición): sin el disambiguador
    `-c{cole}`, dos colecciones de la MISMA serie+publisher carvadas al mismo tipo
    (ej. el tomo-14 especial de una y un `Mini libro de Ilustraciones Edición
    Especial` de otra) colisionarían en el mismo edition_key → DUPVOL. El
    cluster_key ya está namespaceado (`lmc:{cole}:…`); el edition_key también debe
    estarlo. Preserva un `-cNNNN` ya presente (mismo cole)."""
    ek = _with_slug(base_ek, slug)
    parts = ek.split("-")
    country = parts.pop() if parts and parts[-1] in _VALID_COUNTRY else ""
    if not (parts and re.fullmatch(r"c\d+", parts[-1])):
        parts.append(f"c{cole}")
    if country:
        parts.append(country)
    return "-".join(parts)


def _carve_slug(it: dict) -> str | None:
    """Slug de TIPO con que carvar este tomo en su PROPIA edición (variante
    especial/limitada/de lujo que se vende aparte, con bonus físico), o None si
    debe plegarse al `regular` de la coleccion.

    Disparador = EVIDENCIA FUERTE de tipo:
      1) la FRASE de tipo de edición en el TÍTULO (`edition_slug_from_text`,
         tabla única gotcha #69) — "Edición Especial"/"Especial Limitada"/
         "Edición Limitada"/"Edición de Lujo". Estable (el título no muta), lo que
         hace idempotente el corte.
      2) el kind inequívoco especial/limitada del synthetic/cluster (`_kind_of`),
         canonizado a special/limited.
    NUNCA dispara por una palabra de BONUS suelta (cofre/caja/lámina/chapas): un
    `+ Cofre` sin frase de tipo queda regular (cofre 1ª ed = regular, regla dura
    del owner). Los folletos promocionales gratuitos quedan fuera (gotcha #103)."""
    if _is_promo(it):
        return None
    by_title = mw.edition_slug_from_text(it.get("title") or "")
    if by_title in _CARVE_SLUGS:
        return by_title
    kind = _kind_of(it)
    kind = _CANON_KIND.get(kind, kind)
    if kind in _CARVE_SLUGS:
        return kind
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-approved", action="store_true",
                     help="También reasigna edition_key/series_key de items aprobados "
                          "(golden records). Por defecto se saltean por completo (ni "
                          "siquiera se les recalcula lm_kind — eso alimenta el cluster_key "
                          "que tampoco se toca). Riesgo de fragmentación: ver el paso final "
                          "'apply_approvals' en enforce_listadomanga_rules.py.")
    args = ap.parse_args()
    # B11 (Fable 2026-07-08): una línea corrupta se preserva tal cual en vez
    # de tumbar el script; se mantiene fuera de `items` (el resto del código
    # asume dicts reales) y se reinyecta verbatim al escribir.
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
        print(f"[unify-coleccion][WARN] {len(raw_lines)} línea(s) corrupta(s) preservada(s) tal cual.")

    by_cole: dict[str, list[dict]] = collections.defaultdict(list)
    for it in items:
        c = _cole_of_item(it)
        if c:
            by_cole[c].append(it)

    # Mapa edition_key → colecciones dueñas (para namespacear SÓLO las variantes
    # especiales carvadas que colisionarían con OTRA coleccion; ver `_carve_ek`).
    # Se construye del estado ACTUAL: es idempotente porque, una vez namespaceada
    # una variante colisionante, deja de reclamar el ek plano en la pasada siguiente.
    ek_coles: dict[str, set[str]] = collections.defaultdict(set)
    for cc, grp in by_cole.items():
        for it in grp:
            ek = it.get("edition_key")
            if ek:
                ek_coles[ek].add(cc)

    changed, diffs, skipped_approved = 0, [], 0
    for c, grp in by_cole.items():
        # 1) persistir lm_kind en cada item NO aprobado (para el cluster de
        # old-format; alimenta derive_cluster_key, así que un item aprobado no
        # lo recibe — no queremos que su cluster_key derive distinto sin que
        # nosotros lo hayamos decidido explícitamente).
        for it in grp:
            if mw.is_approved(it) and not args.include_approved:
                continue
            it["lm_kind"] = _kind_of(it)
        # 2) separar BOX SETS (= edición aparte, gotcha #58) y VARIANTES ESPECIALES
        # (special/limited/deluxe con evidencia FUERTE de título — se venden aparte
        # con bonus físico) de los tomos regulares. El base de la edición se calcula
        # SÓLO con los tomos regulares (ni box ni carve); box → su edición `boxset`,
        # cada variante especial → su edición del tipo. Lee TODOS los items del grupo
        # (aprobados incluidos) — es solo lectura, y excluir aprobados de esta
        # agregación sesgaría la elección del edition_key base de la coleccion.
        box = [it for it in grp if _is_box(it)]
        rest = [it for it in grp if not _is_box(it) and not _carve_slug(it)]
        # candidatos del base: los tomos regulares; preferir país CONOCIDO (no `-xx`, #46).
        pool = rest or [it for it in grp if not _is_box(it)] or grp
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

        # 3) asignar: tomos regulares → base_ek; box sets → box_ek; variantes
        # especiales → base_ek con su slug de tipo (special/limited/deluxe). Box y
        # variantes especiales conservan su edition_display propio (su nombre de
        # edición: "X Box Set", "Edición Especial"…); la serie sí se unifica.
        # CRÍTICO: NO se toca el cluster_key (ya lleva el kind de la /coleccion —
        # lmc:cole:special:N); sólo se separa el edition_key. La agrupación para
        # dedup sigue por cluster.
        for it in grp:
            if mw.is_approved(it) and not args.include_approved:
                skipped_approved += 1
                continue
            is_box = _is_box(it)
            cs = None if is_box else _carve_slug(it)
            if is_box:
                tgt_ek = box_ek
            elif cs:
                # variante especial → base con su slug de tipo. Se namespacea por
                # coleccion (-c{cole}) SÓLO si el ek plano ya lo reclama OTRA
                # coleccion (coleccion=edición; evita el DUPVOL cross-coleccion,
                # ej. Las Quintillizas cole 3406 vs Mini libro cole 5028). Sin
                # colisión se deja plano — no se churnea a las especiales ya bien
                # keyeadas del resto del corpus.
                flat = _with_slug(base_ek, cs)
                if ek_coles.get(flat, set()) - {c}:
                    tgt_ek = _carve_ek(base_ek, cs, c)
                else:
                    tgt_ek = flat
            else:
                tgt_ek = base_ek
            if it.get("edition_key") == tgt_ek and it.get("series_key") == base_sk:
                it["cluster_key"] = mw.derive_cluster_key(it)  # refresca (tier-0)
                continue
            if len(diffs) < 40:
                diffs.append((c, it.get("edition_key"), tgt_ek, it.get("title")))
            if not args.dry_run:
                it["series_key"] = base_sk
                it["edition_key"] = tgt_ek
                if not is_box:  # los box conservan su series_display + edition_display propios
                    it["series_display"] = base_sd  # misma serie (regular y variante especial)
                    if not cs:  # tomo regular → display de la edición base; variante → propio
                        it["edition_display"] = base_ed
            it["cluster_key"] = mw.derive_cluster_key(it)
            changed += 1

    print(f"[unify-coleccion] items re-asignados al edition_key de su coleccion: {changed}")
    if skipped_approved:
        print(f"[unify-coleccion] items aprobados saltados (usar --include-approved): {skipped_approved}")
    for c, oek, nek, t in diffs[:40]:
        print(f"    cole {c}: {oek}  →  {nek}   ({t!r})")
    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0
    # A13 (Fable 2026-07-08): antes escribía SIEMPRE (bak + reescritura
    # completa) aunque `changed==0` — no-op en cada delta. Ahora early-return
    # si nada cambió, igual que el resto de los retrofits compute-only.
    if changed == 0:
        print("[OK] Nada que unificar. items.jsonl ya está al día.")
        return 0
    before = len(items)
    items = mw.consolidate_by_cluster(items)
    print(f"[unify-coleccion] consolidate: {before} → {len(items)}")
    # A13: backup_and_rotate en vez de shutil.copy a un path propio sin rotar.
    mw.backup_and_rotate(ITEMS, "unify-coleccion")
    out_lines = [json.dumps(it, ensure_ascii=False, sort_keys=True) for it in items] + raw_lines
    mw.write_lines_atomic(ITEMS, out_lines)
    print(f"[unify-coleccion] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
