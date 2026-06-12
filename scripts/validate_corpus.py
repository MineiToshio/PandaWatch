#!/usr/bin/env python3
"""validate_corpus.py — validador ESTRUCTURAL exhaustivo del corpus (sin red).

Chequea TODAS las invariantes que un corpus correcto debe cumplir, en UNA pasada,
y reporta cada violación agrupada por tipo con ejemplos. Pensado para correr tras
cualquier scrape/retrofit y como prueba objetiva de "está bien hecho".

Invariantes (cada una con su id corto):
  SLUG   todo item tiene slug no vacío.
  CLKEY  el `cluster_key` guardado == `derive_cluster_key(item)` (auto-consistente:
         es lo que el scraper volvería a generar → estable ante re-ingesta).
  DUPCL  ningún `cluster_key` aparece en >1 fila (consolidate es punto fijo).
  DUPSYN ninguna fuente sintética de listadomanga `{cole}|{item=}` en >1 fila
         (gotcha #54). El token va cualificado por cole (el hash NO es único).
  LMCKIND el kind del `cluster_key` lmc == canon(kind de su fuente sintética).
  TITLE  título de tomo de listadomanga estable bajo `normalize_display_title`
         (sin "nº"; "Edición Especial" ⇔ kind especial/special) (gotcha #52/#54).
  ONECOLE las fuentes sintéticas de una fila son TODAS de la misma colección
         (no hay filas sobre-mergeadas que crucen colecciones).
  DUPVOL dentro de un edition_key, ningún volumen se repite de forma visible —
         mismo kind o MISMO título exacto = tomo duplicado (gotcha #56/#57).
  COLED  una /coleccion = UNA edición: todos sus items comparten edition_key
         (gotcha #48). [warning: cross-source puede variar — se inspecciona]
  PAIS   edition_key termina en sufijo de país conocido (gotcha #46). [warning]
  EDSLUG el slug de TIPO del edition_key no contradice el término del título
         (tabla edition_slug_from_text, gotcha #69; special/limited/collector/
         deluxe). [warning — lo corrige canonicalize_edition_slugs.py]
  SERIESDUP series_keys distintos que colapsan bajo aggressive_series_norm
         (gotcha #70: "the-", apóstrofes, vocales largas romaji). [warning —
         lo corrige merge_duplicate_series.py / curación del YAML]
  PUBMIX >1 string de publisher dentro de una misma edition_key. [warning —
         lo corrige normalize_edition_publishers.py]
  ISBNDUP el mismo ISBN-13 en >1 fila con cluster distinto (mismo producto
         físico duplicado). [warning — lo corrige merge_isbn_duplicates.py]
  EKPREFIX el edition_key empieza con el series_key del item (formato
         `{series}-{pub}-{slug}-{pais}`). [warning — lo corrige
         fix_edition_key_prefix.py; excluye approved]

Exit code != 0 si hay violaciones DURAS (warnings no fallan).

Uso:
  .venv/bin/python scripts/validate_corpus.py
  .venv/bin/python scripts/validate_corpus.py --examples 10
"""
from __future__ import annotations
import json, re, sys, argparse
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402
from series_aliases import aggressive_series_norm  # noqa: E402
from wikis.listadomanga_collections import normalize_display_title  # noqa: E402

# Slugs de TIPO confundibles (gotcha #69) — en sync con
# scripts/retrofit/canonicalize_edition_slugs.py.
_CONFUSABLE_SLUGS = {"special", "limited", "collector", "deluxe"}

ITEMS = ROOT / "data" / "items.jsonl"
_COLE = re.compile(r"coleccion\.php\?id=(\d+)")
_SYN = re.compile(r"item=([a-z]+)-([^-&]+)-([0-9a-f]{8,})")
_ITEM_KV = re.compile(r"item=([a-z]+)-([^-&]+)")
_CL_LMC = re.compile(r"^lmc:(\d+):([a-z]+):(.*)$")
_CANON = {"especial": "special", "alternativa": "variant", "limitada": "limited"}
# sufijos de país válidos en edition_key (gotcha #46). Se derivan del MISMO mapa
# que usa el scraper para no desincronizarse; `xx` (desconocido) NO es válido.
_COUNTRIES = set(mw._COUNTRY_SLUG_MAP.values())


def _urls(it):
    return [it.get("url", "") or ""] + [s.get("url", "") or "" for s in (it.get("sources") or [])]


def _syn_tokens(it):
    out = set()
    for u in _urls(it):
        mc, ms = _COLE.search(u), _SYN.search(u)
        if mc and ms:
            out.add(f"{mc.group(1)}|{ms.group(0)[len('item='):]}")
    return out


def _is_ldm(it):
    return any("listadomanga.es/coleccion.php" in u for u in _urls(it))


# Qualifiers de edición que contaminan el título de un tomo regular (gotcha #56),
# en sync con `fix_lmc_display_titles._CONTAM`.
_CONTAM = re.compile(
    r"\s*\b(?:Edici[oó]n\s+Especial\s+Limitada|Edici[oó]n\s+Limitada|"
    r"Edici[oó]n\s+Coleccionista|Artbook|Coleccionista)\b\s*", re.IGNORECASE)


def _slug_of_ek(ek):
    parts = (ek or "").split("-")
    parts = parts[:-1] if parts and parts[-1] in (_COUNTRIES | {"xx"}) else parts
    if parts and re.fullmatch(r"c\d+", parts[-1]):
        parts = parts[:-1]
    return parts[-1] if parts else ""


def _edition_slug(it):
    return _slug_of_ek(it.get("edition_key", "") or "")


def _lmc_kind(it):
    """kind del cluster lmc (canon) o None si no es lmc."""
    m = _CL_LMC.match(it.get("cluster_key", "") or "")
    return m.group(2) if m else None


def _kind_canon(it):
    """kind canónico del producto. MISMA prioridad que `fix_lmc_display_titles._kind`
    (la autoridad): cluster lmc → kind de la fuente sintética `item=` (cross-source
    como la metalizada Berserk que mergeó con `especial-21`) → slug del edition_key.
    Default 'regular'."""
    lk = _lmc_kind(it)
    if lk:
        return lk
    for u in _urls(it):
        m = re.search(r"item=([a-z]+)-", u)
        if m:
            return _CANON.get(m.group(1), m.group(1))
    parts = (it.get("edition_key", "") or "").split("-")
    return parts[-2] if len(parts) >= 2 else "regular"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--examples", type=int, default=6)
    args = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    N = len(items)

    V = defaultdict(list)          # id -> list[str ejemplos]
    counts = defaultdict(int)
    HARD = {"SLUG", "CLKEY", "DUPCL", "DUPSYN", "LMCKIND", "TITLE", "ONECOLE", "DUPVOL"}

    def flag(kind, msg):
        counts[kind] += 1
        if len(V[kind]) < args.examples:
            V[kind].append(msg)

    cl_owner = defaultdict(list)
    syn_owner = defaultdict(list)
    cole_editions = defaultdict(set)
    ev_owner = defaultdict(list)  # (edition_key, volume) -> items (para DUPVOL)
    sk_by_norm = defaultdict(set)  # aggressive_norm -> series_keys (SERIESDUP)
    ek_pubs = defaultdict(set)     # edition_key -> publisher strings (PUBMIX)

    for it in items:
        ek = it.get("edition_key", "") or ""
        ck = it.get("cluster_key", "") or ""
        title = it.get("title", "") or ""

        # SLUG
        if not (it.get("slug") or "").strip():
            flag("SLUG", f"{ck or it.get('url','')[-40:]} | {title!r}")

        # CLKEY auto-consistencia
        try:
            derived = mw.derive_cluster_key(it)
        except Exception as e:  # pragma: no cover
            derived = f"<error:{e}>"
        if derived != ck:
            flag("CLKEY", f"stored={ck!r} derived={derived!r} | {title!r}")

        cl_owner[ck].append(it)
        vol = (it.get("volume") or "").strip()
        if ek and vol:
            ev_owner[(ek, vol)].append(it)
        sk = (it.get("series_key") or "").strip()
        if sk:
            sk_by_norm[aggressive_series_norm(sk)].add(sk)
        # PUBMIX no audita filas approved (golden records — verdad del owner;
        # normalize_edition_publishers tampoco las toca).
        pub = (it.get("publisher") or "").strip()
        if ek and pub and not it.get("approved_at"):
            ek_pubs[ek].add(pub)

        # DUPSYN tokens + ONECOLE
        toks = _syn_tokens(it)
        coles = {t.split("|", 1)[0] for t in toks}
        if len(coles) > 1:
            flag("ONECOLE", f"{ck!r} coles={sorted(coles)} | {title!r}")
        for t in toks:
            syn_owner[t].append(it)

        # LMCKIND: kind del cluster lmc == canon(kind de su synthetic propio)
        lk = _lmc_kind(it)
        if lk is not None:
            mcole = _CL_LMC.match(ck)
            cole, vol = mcole.group(1), mcole.group(3)
            # buscar synthetic de ESTA fila para (cole, vol)
            own_kinds = set()
            for u in _urls(it):
                mc, mi = _COLE.search(u), _ITEM_KV.search(u)
                if mc and mi and mc.group(1) == cole and mi.group(2) == vol:
                    own_kinds.add(_CANON.get(mi.group(1), mi.group(1)))
            if own_kinds and lk not in own_kinds:
                flag("LMCKIND", f"{ck!r} synthetic_kinds={sorted(own_kinds)} | {title!r}")

        # TITLE estabilidad (sólo items de listadomanga). En ediciones REGULARES el
        # tomo no debe arrastrar qualifiers de edición embebidos (#56); el qualifier
        # "Edición Especial" ⇔ kind especial/special. Misma lógica que el fixer.
        if _is_ldm(it):
            kc = _kind_canon(it)
            base = title
            if _edition_slug(it) == "regular":
                base = re.sub(r"\s{2,}", " ", _CONTAM.sub(" ", title)).strip()
            norm = normalize_display_title(base, kc)  # kind REAL (incl. variant/limited)
            if norm != title:
                flag("TITLE", f"{title!r} → esperado {norm!r} (kind={kc})")

        # COLED / PAIS (warnings)
        for u in _urls(it):
            mc = _COLE.search(u)
            if mc and ek:
                cole_editions[mc.group(1)].add(ek)
                break
        if ek:
            last = ek.rsplit("-", 1)[-1]
            if last not in _COUNTRIES:
                flag("PAIS", f"{ek!r} | {title!r}")

        # EKPREFIX: el SEGMENTO de serie de la key == series_key del item
        # (parseo exacto vía rebuild_edition_key_prefix — el startswith deja
        # pasar basura de subtítulo pegada al series_key).
        sk_it = (it.get("series_key") or "").strip()
        if ek and sk_it and not it.get("approved_at"):
            if (mw.rebuild_edition_key_prefix(ek, sk_it)
                    or not ek.startswith(sk_it + "-")):
                flag("EKPREFIX", f"{sk_it!r} vs {ek!r} | {title[:50]!r}")

        # EDSLUG: el término del título manda sobre el slug de TIPO (gotcha #69).
        # No aplica a lmc (la /coleccion gobierna su key) ni a approved (curados).
        if ek and not it.get("approved_at") and not _is_ldm(it):
            slug = _slug_of_ek(ek)
            if slug in _CONFUSABLE_SLUGS:
                evidence = mw.edition_slug_from_text(
                    it.get("title_original") or title or "")
                if evidence in _CONFUSABLE_SLUGS and evidence != slug:
                    flag("EDSLUG", f"{ek!r} pero el título dice {evidence!r} | "
                                   f"{(it.get('title_original') or title)[:60]!r}")

    # DUPCL
    for ck, group in cl_owner.items():
        if ck.startswith("url:"):
            continue
        if len(group) > 1:
            flag("DUPCL", f"{ck!r} ×{len(group)}: {[g.get('title') for g in group][:3]}")

    # DUPSYN
    for t, group in syn_owner.items():
        if len(group) > 1:
            flag("DUPSYN", f"{t} ×{len(group)}: {[g.get('cluster_key') for g in group][:4]}")

    # DUPVOL: dentro de un edition_key, MISMO volumen repetido de forma visible —
    # mismo kind (dos regular:1 del mismo edition_key, ej. dos /coleccion colisionando)
    # o MISMO título exacto (ej. 'Fruits Basket Edición Coleccionista 7' ×2). Un
    # regular + un especial del mismo vol con títulos distintos coexisten (OK).
    for (ek, vol), group in ev_owner.items():
        if len(group) < 2:
            continue
        kinds = [_lmc_kind(it) for it in group]
        titles = [(it.get("title") or "").strip().lower() for it in group]
        dup_kind = any(k is not None and kinds.count(k) > 1 for k in kinds)
        dup_title = any(titles.count(t) > 1 for t in titles)
        if dup_kind or dup_title:
            flag("DUPVOL", f"{ek} vol{vol}: kinds={kinds} titles={[g.get('title') for g in group][:3]}")

    # COLED — un box set es una edición APARTE legítima (gotcha #58); sólo flag si
    # hay >1 edición NO-box compartiendo la colección.
    for cole, eks in cole_editions.items():
        non_box = {ek for ek in eks if _slug_of_ek(ek) != "boxset"}
        if len(non_box) > 1:
            flag("COLED", f"cole {cole}: {sorted(eks)}")

    # SERIESDUP — la misma obra partida en series_keys mecánicamente equivalentes
    # (gotcha #70). Una warning por grupo.
    for norm, sks in sk_by_norm.items():
        if len(sks) > 1:
            flag("SERIESDUP", f"{sorted(sks)}")

    # PUBMIX — strings de publisher mezclados dentro de una edición.
    for ek, pubs in ek_pubs.items():
        if len(pubs) > 1:
            flag("PUBMIX", f"{ek}: {sorted(pubs)[:4]}")

    # ISBNDUP — el mismo ISBN-13 en >1 fila con cluster distinto = el mismo
    # producto físico duplicado (lo corrige merge_isbn_duplicates.py; los
    # cruces con listadomanga los maneja merge_crosssource_into_lmc).
    isbn_owner = defaultdict(list)
    for it in items:
        raw = (it.get("isbn") or "").strip()
        if raw:
            isbn_owner[mw.isbn13(raw) or raw].append(it)
    for isbn, group in isbn_owner.items():
        if len(group) > 1 and len({g.get("cluster_key", "") for g in group}) > 1:
            flag("ISBNDUP", f"{isbn} ×{len(group)}: "
                 f"{[g.get('edition_key') or g.get('cluster_key','')[:40] for g in group][:3]}")

    # Reporte
    print(f"=== VALIDACIÓN DE CORPUS ({N} items) ===\n")
    order = ["SLUG", "CLKEY", "DUPCL", "DUPSYN", "LMCKIND", "TITLE", "ONECOLE", "DUPVOL",
             "COLED", "PAIS", "EDSLUG", "SERIESDUP", "PUBMIX", "EKPREFIX", "ISBNDUP"]
    hard_fail = 0
    for k in order:
        n = counts[k]
        tag = "DURA" if k in HARD else "warn"
        mark = "✗" if (n and k in HARD) else ("⚠" if n else "✓")
        print(f"  {mark} [{tag}] {k:8} violaciones: {n}")
        for ex in V[k]:
            print(f"        - {ex}")
        if n and k in HARD:
            hard_fail += n
    print()
    if hard_fail:
        print(f"RESULTADO: ✗ {hard_fail} violaciones DURAS — el corpus NO es válido.")
        return 1
    print("RESULTADO: ✓ corpus VÁLIDO (0 violaciones duras).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
