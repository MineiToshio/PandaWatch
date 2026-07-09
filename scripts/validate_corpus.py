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
  SPECIALREG título con FRASE fuerte de tipo especial (Edición Especial/Especial
         Limitada/Edición Limitada/Edición de Lujo/Coleccionista/kanzenban) ⇒ el
         edition_slug NO debe ser `regular`: la variante especial se plegó al
         regular de su coleccion. [warning — lo corta el carve de
         unify_coleccion_edition.py; aplica también a lmc]
  SERIESDUP series_keys distintos que colapsan bajo aggressive_series_norm
         (gotcha #70: "the-", apóstrofes, vocales largas romaji). [warning —
         lo corrige merge_duplicate_series.py / curación del YAML]
  PUBMIX >1 string de publisher dentro de una misma edition_key. [warning —
         lo corrige normalize_edition_publishers.py]
  ISBNDUP mismo ISBN-13 compartido por >1 fila QUE ADEMÁS huelen a duplicado
         real (mismo edition_key, o mismo título+país+variante). Un ISBN
         compartido por sí solo NO es violación: en manga el mismo ISBN se
         reusa entre ediciones/series distintas (portadas variantes, especial
         vs normal, retailers que reciclan ISBN). [warning]
  EKPREFIX el edition_key empieza con el series_key del item (formato
         `{series}-{pub}-{slug}-{pais}`). [warning — lo corrige
         fix_edition_key_prefix.py; excluye approved]
  STOLENIMG la portada de un tomo NORMAL es la foto de un extra/bonus de OTRA
         fila (cofre/posavasos/miniartbook de otro volumen; gotcha #99). [warning
         — lo corrige remove_phantom_calendar_editions.py]

  Invariantes agregadas 2026-07-07 (auditoría post-scrape, WO-F) — TODAS warning
  a propósito: nacen con violaciones vivas en el corpus real (backlog conocido),
  promoverlas a dura ahora frenaría el build indefinidamente.
  DATEISO release_date presente que no matchea el patrón ISO parcial (año,
         año-mes o fecha completa: r"^\\d{4}(-\\d{2}(-\\d{2})?)?$"). [warning]
  PTYPE_ENUM product_type fuera del enum de `derive_product_type()`
         (manga_watch.py:3841-3872 + PRODUCT_TYPE_KEYWORDS:1679 + audiobook
         directo:2077-2078): {manga, artbook, fanbook, guidebook, boxset,
         novel, magazine, audiobook}. [warning]
  LANG_ENUM language fuera del set canónico de 14 idiomas del proyecto (nombres
         completos en español, ver CLAUDE.md "14 idiomas" + sources.yml). Reporta
         el TOP de valores no-canónicos (backlog de normalización — nombres en
         inglés, códigos ISO-639-1 sueltos, variantes no unificadas como
         "Deutsch" vs "Alemán"). [warning]
  VOLRANGE volume numérico fuera de (0, 350], con pinta de año (1990-2035), o
         absurdo (basura de research-import: 4000000000, 10089…). [warning]
  EKMALFORMED sufijo final del edition_key NO es un país conocido NI `xx`
         (separado de PAIS: PAIS también flaggea `xx` legítimo; EKMALFORMED
         sólo sufijos realmente rotos, ej. `glob`). [warning]
  SLUGUNIQ slug duplicado entre cluster_keys DISTINTOS (dos productos != con
         la misma URL). [warning]
  SLUGFMT slug que viola `^[a-z0-9][a-z0-9-]*[a-z0-9]$`. [warning]
  STDKEYS standardized_at presente con series_key o edition_key vacíos
         (procesado pero incompleto). [warning]
  MIRRORREF images[].local que no existe en `data/images/` (espejo local roto).
         [warning]
  SRCURL sources[] vacío, o con alguna entrada sin url. [warning]

  Invariantes agregadas 2026-07-08 (auditoría Fable, paquete E-standardize) —
  TODAS warning al nacer (backlog vivo; promoverlas a dura frenaría el build):
  PAISKEY el `country` del item, mapeado a slug (`_country_slug`), coincide con
         el sufijo país del `edition_key` — "país = edición" es regla DURA del
         owner pero sin enforcement hasta hoy. Sólo compara cuando el sufijo del
         edition_key ES un país conocido (si no es parseable, skip: no falso
         positivo — eso ya lo cubren PAIS/EKMALFORMED). [warning]
  URLDUP una misma URL (top-level o `sources[].url`) aparece en >1 item DISTINTO
         (cluster_key/slug distinto): el mismo producto partido en dos filas.
         Invisible para DUPCL (que saltea el tier `url:`) y para DUPSYN (sólo
         synthetic de listadomanga). [warning]
  IMGTOP residuo de `image_url`/`image_local` top-level (campos ELIMINADOS
         2026-06-09; cover unificado a `images[0]`). Detecta la regresión. [warning]
  COVER0 `images[]` no vacío pero `images[0]` no es un dict con url — el slot de
         cover (images[0] = portada, fuente única desde 2026-06-09) está roto.
         [warning]
  APPROVED coherencia de golden record: `approved_at` ⇒ `standardized_at`
         presente Y `series_key`/`edition_key` no vacías. [warning]
  TSISO  `standardized_at`/`approved_at` presentes parsean como ISO-8601
         (`datetime.fromisoformat`). DATEISO sólo cubría `release_date`. [warning]
  SRCFMT una entrada de `sources[]` que no es un dict (dato corrupto). Antes
         crasheaba el validador (exit 1); ahora se reporta. [warning]

Exit codes (contrato para el gate pre-build de scrape_delta/full):
  0  corpus VÁLIDO — 0 violaciones DURAS (los warnings NO fallan).
  2  hay violaciones DURAS — corpus INVÁLIDO (el pipeline OMITE el build).
  1  error del propio validador (excepción no controlada) — reservado; el
     shell lo trata también como fallo, pero distinto de "duras".

Uso:
  .venv/bin/python scripts/validate_corpus.py
  .venv/bin/python scripts/validate_corpus.py --examples 10
  .venv/bin/python scripts/validate_corpus.py --file data/backups/items.jsonl/items-2026-07-07.jsonl.bak
"""
from __future__ import annotations
import json, os, re, sys, argparse
import datetime as dt
from collections import Counter, defaultdict
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

# --- WO-F (2026-07-07): constantes de las invariantes nuevas -----------------

IMAGES_DIR = ROOT / "data" / "images"

# Enum de derive_product_type() — fuente ÚNICA: mw.PRODUCT_TYPE_ENUM (antes se
# copiaba a mano acá y en standardize_apply.py; el doble enum era el hallazgo #9
# de la auditoría 2026-07-08). Enumera los valores que derive_product_type puede
# devolver: {manga, artbook, fanbook, guidebook, boxset, novel, magazine, audiobook}.
_PTYPE_ENUM = mw.PRODUCT_TYPE_ENUM

_DATEISO_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")

# Set canónico de `language`: los 14 idiomas del proyecto (ver CLAUDE.md, "20
# países y 14 idiomas") tal como los declara sources.yml — nombre completo en
# ESPAÑOL (single-user app en español; gotcha: "Deutsch" viene hardcodeado por
# wikis/mangapassion.py en vez de "Alemán" — backlog de normalización, no se
# corrige acá). "Español / Catalán" es un valor compuesto legítimo declarado en
# sources.yml (0 filas hoy, pero válido). WARN — nunca dura: hay ~1200 filas con
# nombres en inglés, códigos ISO-639-1 sueltos ("ja","en","fr","es","de","it") o
# la variante "Deutsch" a la fecha de esta auditoría.
_LANG_CANON = {
    "Español", "Inglés", "Francés", "Japonés", "Italiano", "Portugués",
    "Alemán", "Polaco", "Turco", "Coreano", "Chino", "Checo", "Vietnamita",
    "Tailandés", "Español / Catalán",
}

# volume numérico válido: (0, 350]. 0 EXCLUIDO a propósito (algunos "volumen 0"
# reales de la industria quedan warn — el rango del research-import es la
# prioridad: 4000000001, 10089, años 1990-2035 colados como volumen).
_VOL_MIN, _VOL_MAX = 0, 350
_VOL_YEAR_MIN, _VOL_YEAR_MAX = 1990, 2035

_SLUGFMT_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")

# SPECIALREG: keywords FUERTES de tipo especial en el título ⇒ el edition_slug NO
# debe ser `regular` (la variante especial/limitada se pliega al regular = el bug
# que unify_coleccion_edition auto-corta con el carve). Lista ESTRICTA de FRASES —
# NUNCA "especial" suelto (rozaría nombres de serie). En sync con
# manga_watch._EDITION_TYPE_TERM_RULES (special/limited/deluxe/kanzenban).
_SPECIALREG_RE = re.compile(
    r"\bedici[oó]n\s+especial\b|\bespecial\s+limitada\b|\bedici[oó]n\s+limitada\b|"
    r"\bedici[oó]n\s+de\s+lujo\b|\bcoleccionista\b|\bkanzenban\b|完全版", re.I)

# Slugs de TIPO que son una edición APARTE legítima dentro de una /coleccion
# (box set + variantes especiales carvadas por unify_coleccion_edition). COLED sólo
# exige unicidad de la edición REGULAR-family por coleccion, no de estas.
_CARVED_SLUGS = {"boxset", "special", "limited", "deluxe"}


def _urls(it):
    # Guard isinstance: una entrada no-dict en sources[] (dato corrupto) antes
    # crasheaba el validador entero (exit 1) — hallazgo #11. Se ignora acá y la
    # invariante SRCFMT la reporta desde el loop principal.
    out = [it.get("url", "") or ""]
    for s in (it.get("sources") or []):
        if isinstance(s, dict):
            out.append(s.get("url", "") or "")
    return out


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


def _isbn_dup_signature(it):
    """Firma que distingue 'duplicado real' de 'ediciones distintas que
    comparten ISBN'. Preferimos edition_key; si falta, título+país+
    variante(kind). Módulo-level para poder testearlo."""
    ek = (it.get("edition_key") or "").strip()
    if ek:
        return ("ek", ek)
    title = (it.get("title") or "").strip().lower()
    country = (it.get("country") or "").strip().lower()
    return ("tpv", title, country, _kind_canon(it))


def isbn_dup_violations(items):
    """Devuelve [(isbn, [firmas duplicadas])] para ISBNs compartidos que
    huelen a DUPLICADO REAL: mismo ISBN Y misma firma de duplicado (edition_key,
    o título+país+variante) repartida en clusters distintos.

    Premisa corregida (2026-07-07): un ISBN compartido por sí solo NO es
    violación — en manga el mismo ISBN se reusa entre ediciones/series
    DISTINTAS (portadas variantes, especial vs normal, retailers que reciclan
    ISBN). Sólo es sospechoso cuando dos filas de CLUSTER distinto comparten
    firma de duplicado real."""
    isbn_owner = defaultdict(list)
    for it in items:
        raw = (it.get("isbn") or "").strip()
        if raw:
            isbn_owner[mw.isbn13(raw) or raw].append(it)
    out = []
    for isbn, group in isbn_owner.items():
        if len(group) < 2:
            continue
        by_sig = defaultdict(set)
        for g in group:
            by_sig[_isbn_dup_signature(g)].add(g.get("cluster_key", ""))
        dupes = [sig for sig, cks in by_sig.items() if len(cks) > 1]
        if dupes:
            out.append((isbn, dupes))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--examples", type=int, default=6)
    ap.add_argument("--file", default=str(ITEMS),
                    help="corpus a validar (default data/items.jsonl); "
                         "interfaz consumida por auditorías de backups — "
                         "mismos exit codes que el modo normal.")
    args = ap.parse_args()
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"[ERROR] no existe {file_path}", file=sys.stderr)
        return 1
    items = [json.loads(l) for l in file_path.open(encoding="utf-8") if l.strip()]
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
    slug_owner = defaultdict(set)   # slug -> cluster_keys distintos (SLUGUNIQ)
    lang_bad_counter = Counter()    # valores no-canónicos de `language` (LANG_ENUM)
    mirror_checked = 0              # entries de images[].local revisadas (MIRRORREF)
    ev_owner = defaultdict(list)  # (edition_key, volume) -> items (para DUPVOL)
    sk_by_norm = defaultdict(set)  # aggressive_norm -> series_keys (SERIESDUP)
    ek_pubs = defaultdict(set)     # edition_key -> publisher strings (PUBMIX)
    url_owner = defaultdict(set)   # url -> identidades distintas (URLDUP)

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

        # SPECIALREG (WO-1): título con FRASE fuerte de tipo especial ⇒ edition_slug
        # NO debe ser `regular`. Detecta la variante especial/limitada plegada al
        # regular de su coleccion (el bug que carva unify_coleccion_edition). Aplica
        # también a lmc (a diferencia de EDSLUG) — es justo el caso de listadomanga.
        # No audita approved (curados). WARN — nace con backlog vivo; la limpieza de
        # datos (el carve) corre aparte.
        # OJO: se mira `title` (el display) Y `title_original` — en listadomanga la
        # FRASE de tipo vive en el display estandarizado ("… Edición Especial"),
        # mientras que title_original es el crudo ("… nº34"). El carve keyea igual
        # sobre `title`.
        if ek and not it.get("approved_at") and _edition_slug(it) == "regular":
            if (_SPECIALREG_RE.search(title or "")
                    or _SPECIALREG_RE.search(it.get("title_original") or "")):
                flag("SPECIALREG",
                     f"{ek!r} slug=regular pero el título es de tipo especial | "
                     f"{(title or it.get('title_original'))[:60]!r}")

        # --- WO-F (2026-07-07): invariantes nuevas, todas WARN -------------

        # SLUGFMT + acumulación para SLUGUNIQ (post-loop).
        item_slug = (it.get("slug") or "").strip()
        if item_slug:
            slug_owner[item_slug].add(ck)
            if not _SLUGFMT_RE.match(item_slug):
                flag("SLUGFMT", f"{item_slug!r} | {ck}")

        # DATEISO
        rdate = (it.get("release_date") or "").strip()
        if rdate and not _DATEISO_RE.match(rdate):
            flag("DATEISO", f"{rdate!r} | {title!r}")

        # PTYPE_ENUM
        ptype = (it.get("product_type") or "").strip()
        if ptype and ptype not in _PTYPE_ENUM:
            flag("PTYPE_ENUM", f"{ptype!r} | {title!r}")

        # LANG_ENUM — el conteo total se lleva acá; el TOP de valores no-canónicos
        # se arma después del loop (más útil que N ejemplos repetidos del mismo
        # valor, ej. "Deutsch" x cientos).
        lang = (it.get("language") or "").strip()
        if lang and lang not in _LANG_CANON:
            counts["LANG_ENUM"] += 1
            lang_bad_counter[lang] += 1

        # VOLRANGE — (0, 350] es el rango válido; 0 EXCLUIDO a propósito (basura
        # real del research-import: años colados como volumen, 4000000001…).
        # OJO: no reusar `vol` (arriba) — el bloque LMCKIND lo pisa con
        # mcole.group(3) para items lmc, así que acá se relee fresco del item.
        vol_val = (it.get("volume") or "").strip()
        if vol_val:
            try:
                vf = float(vol_val)
            except ValueError:
                vf = None
            if vf is not None and (vf <= _VOL_MIN or vf > _VOL_MAX):
                if _VOL_YEAR_MIN <= vf <= _VOL_YEAR_MAX:
                    reason = "pinta de año"
                elif vf > 100000:
                    reason = "absurdo"
                else:
                    reason = "fuera de rango"
                flag("VOLRANGE", f"{vol_val!r} ({reason}) | {title!r}")

        # EKMALFORMED — separado de PAIS (arriba): PAIS también flaggea `xx`
        # (desconocido pero TOLERADO como placeholder explícito); EKMALFORMED
        # sólo sufijos rotos de verdad (caso real: "...-glob").
        if ek:
            last_ek = ek.rsplit("-", 1)[-1]
            if last_ek not in _COUNTRIES and last_ek != "xx":
                flag("EKMALFORMED", f"{ek!r} | sufijo {last_ek!r} | {title!r}")

        # STDKEYS
        if it.get("standardized_at") and (not sk or not ek):
            flag("STDKEYS", f"{ck or item_slug or it.get('url', '')[-40:]} | {title!r}")

        # MIRRORREF — cuenta también las entries revisadas (mirror_checked) para
        # dar contexto de denominador (NOTES, impreso junto al conteo).
        for img in (it.get("images") or []):
            loc = img.get("local") if isinstance(img, dict) else None
            if loc:
                mirror_checked += 1
                if not os.path.exists(IMAGES_DIR / loc):
                    flag("MIRRORREF", f"{ck or item_slug} | falta {loc!r}")

        # SRCURL + SRCFMT — dict-safe (una entrada no-dict antes crasheaba el
        # validador; ahora se reporta como SRCFMT). #11.
        srcs = it.get("sources") or []
        bad_fmt = [s for s in srcs if not isinstance(s, dict)]
        if bad_fmt:
            flag("SRCFMT", f"{ck or item_slug or it.get('url', '')[-40:]} | "
                           f"{len(bad_fmt)} entradas no-dict | {title!r}")
        dict_srcs = [s for s in srcs if isinstance(s, dict)]
        if not srcs or any(not (s.get("url") or "").strip() for s in dict_srcs):
            flag("SRCURL", f"{ck or item_slug or it.get('url', '')[-40:]} | {title!r}")

        # --- Paquete E-standardize (2026-07-08): invariantes nuevas, WARN -----

        ident = ck or item_slug or (it.get("url", "") or "")

        # URLDUP — acumular; una URL en >1 item distinto se reporta post-loop.
        for u in _urls(it):
            u = (u or "").strip()
            if u:
                url_owner[u].add(ident)

        # PAISKEY — country del item vs sufijo país del edition_key ("país =
        # edición", regla dura del owner). Sólo compara cuando el sufijo ES un
        # país conocido (si no es parseable → PAIS/EKMALFORMED ya lo cubren).
        if ek and (it.get("country") or "").strip():
            ek_suffix = ek.rsplit("-", 1)[-1]
            if ek_suffix in _COUNTRIES:
                want = mw._country_slug(it["country"])
                if want != ek_suffix:
                    flag("PAISKEY", f"country={it['country']!r}→{want!r} "
                                    f"pero edition_key termina en {ek_suffix!r} | {ek!r}")

        # IMGTOP — residuo de image_url/image_local top-level (eliminados
        # 2026-06-09; cover = images[0]). Detecta la regresión.
        if "image_url" in it or "image_local" in it:
            flag("IMGTOP", f"{ident} | tiene image_url/image_local top-level | {title!r}")

        # COVER0 — images[] no vacío ⇒ images[0] es un dict con url (slot de
        # cover, fuente única desde 2026-06-09).
        imgs0 = it.get("images") or []
        if imgs0:
            first = imgs0[0]
            if not isinstance(first, dict) or not (first.get("url") or "").strip():
                flag("COVER0", f"{ident} | images[0] sin url/no-dict | {title!r}")

        # APPROVED — golden record coherente: approved_at ⇒ standardized_at +
        # series_key/edition_key no vacías.
        if it.get("approved_at"):
            if (not (it.get("standardized_at") or "").strip()
                    or not sk_it or not ek):
                flag("APPROVED", f"{ident} | approved sin "
                                 f"standardized_at/series_key/edition_key | {title!r}")

        # TSISO — timestamps de estandarización/aprobación parsean como ISO.
        for _tsf in ("standardized_at", "approved_at"):
            _tsv = (it.get(_tsf) or "").strip()
            if _tsv:
                try:
                    dt.datetime.fromisoformat(_tsv)
                except ValueError:
                    flag("TSISO", f"{ident} | {_tsf}={_tsv!r} no es ISO | {title!r}")

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

    # COLED — box set y variantes especiales (special/limited/deluxe) carvadas son
    # ediciones APARTE legítimas dentro de la coleccion (gotcha #58 + WO-1: la
    # variante especial se vende aparte con bonus físico). Sólo flag si hay >1
    # edición REGULAR-family compartiendo la colección (dos regulares distintos = el
    # cruce que COLED protege).
    for cole, eks in cole_editions.items():
        non_box = {ek for ek in eks if _slug_of_ek(ek) not in _CARVED_SLUGS}
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

    # ISBNDUP — un ISBN compartido por varias filas NO es por sí solo una
    # violación. Premisa corregida (2026-07-07): en manga el mismo ISBN se
    # reusa entre ediciones/series DISTINTAS (portadas variantes comparten
    # ISBN, especial y normal comparten ISBN, y retailers como Mangaline MX
    # reciclan un ISBN en toda su línea — el mismo dígito en dos series). Por
    # eso ISBN dejó de ser criterio de fusión en derive_cluster_key. Acá sólo
    # marcamos (warning, nunca dura) los casos que de verdad huelen a
    # DUPLICADO real: mismo ISBN Y (mismo edition_key) o (mismo título+país+
    # variante) repartido en clusters distintos. Ver isbn_dup_violations().
    for isbn, dupes in isbn_dup_violations(items):
        flag("ISBNDUP", f"{isbn}: firmas duplicadas "
             f"{[list(sig)[:3] for sig in dupes[:2]]}")

    # STOLENIMG (gotcha #99) — la portada de un TOMO normal es, en realidad, la foto
    # de un extra/bonus (cofre, posavasos, miniartbook) de OTRA fila. Síntoma del bug
    # del calendario+estandarización que inventaba especiales y les pegaba el regalo de
    # otro volumen (caso Edens Zero "Especial 23"). Sólo se mira el tomo NORMAL: un
    # artbook/cofre/fanbook standalone comparte legítimamente la foto con el bonus que
    # ES (Witch Hat ArtWorks, Promised Neverland Escape…), eso NO es robo. Warning.
    extra_owner = defaultdict(set)
    for it in items:
        for img in (it.get("images") or []):
            if isinstance(img, dict) and img.get("kind") in ("extra", "bonus") and img.get("url"):
                extra_owner[img["url"]].add(it.get("slug"))
    for it in items:
        if _edition_slug(it) != "regular" and (it.get("product_type") or "") != "manga":
            continue
        imgs = it.get("images") or []
        if not imgs or not isinstance(imgs[0], dict):
            continue
        url = imgs[0].get("url")
        owners = extra_owner.get(url, set()) - {it.get("slug")}
        if url and owners:
            flag("STOLENIMG", f"{it.get('slug')} portada = extra de {sorted(owners)} | {(it.get('title') or '')[:50]!r}")

    # SLUGUNIQ — mismo slug en cluster_keys DISTINTOS (dos productos != con la
    # misma URL de catálogo). No usa flag() en el loop principal porque necesita
    # el set COMPLETO de cluster_keys por slug primero.
    for s, cks in slug_owner.items():
        if len(cks) > 1:
            flag("SLUGUNIQ", f"{s!r} ×{len(cks)} cluster_keys: {sorted(cks)[:4]}")

    # URLDUP — una misma URL (top-level o sources[].url) repartida en >1 item
    # DISTINTO: el mismo producto partido en dos filas. DUPCL no lo ve (saltea
    # el tier url:) y DUPSYN sólo cubre synthetic de listadomanga.
    for u, owners in url_owner.items():
        if len(owners) > 1:
            flag("URLDUP", f"{u[-70:]!r} ×{len(owners)} items: {sorted(owners)[:3]}")

    # LANG_ENUM — el TOP de valores no-canónicos (más útil que N ejemplos
    # repetidos del mismo valor). counts["LANG_ENUM"] ya se acumuló en el loop.
    for val, cnt in lang_bad_counter.most_common(args.examples):
        V["LANG_ENUM"].append(f"{val!r} ×{cnt}")

    # Reporte
    print(f"=== VALIDACIÓN DE CORPUS ({N} items) ===\n")
    order = ["SLUG", "CLKEY", "DUPCL", "DUPSYN", "LMCKIND", "TITLE", "ONECOLE", "DUPVOL",
             "COLED", "PAIS", "PAISKEY", "EDSLUG", "SPECIALREG", "SERIESDUP", "PUBMIX", "EKPREFIX", "ISBNDUP", "STOLENIMG",
             "DATEISO", "PTYPE_ENUM", "LANG_ENUM", "VOLRANGE", "EKMALFORMED",
             "SLUGUNIQ", "SLUGFMT", "STDKEYS", "MIRRORREF", "SRCURL", "SRCFMT",
             "URLDUP", "IMGTOP", "COVER0", "APPROVED", "TSISO"]
    NOTES = {"MIRRORREF": f"(de {mirror_checked} refs con local revisadas)"}
    hard_fail = 0
    for k in order:
        n = counts[k]
        tag = "DURA" if k in HARD else "warn"
        mark = "✗" if (n and k in HARD) else ("⚠" if n else "✓")
        note = f"  {NOTES[k]}" if k in NOTES else ""
        print(f"  {mark} [{tag}] {k:8} violaciones: {n}{note}")
        for ex in V[k]:
            print(f"        - {ex}")
        if n and k in HARD:
            hard_fail += n
    print()
    if hard_fail:
        print(f"RESULTADO: ✗ {hard_fail} violaciones DURAS — el corpus NO es válido.")
        return 2  # 2 = violaciones DURAS (gate pre-build); 1 queda para errores del validador
    print("RESULTADO: ✓ corpus VÁLIDO (0 violaciones duras).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
