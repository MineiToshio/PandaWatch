#!/usr/bin/env python3
"""we_resolve.py — resolución determinista (0 tokens LLM) del skill
`/watch-whakoom-covers`, Step 2.

Recibe el JSON COMPACTO que el agente extrajo del navegador (Chrome pane) al
abrir hasta 3 páginas `/ediciones/<id>/<slug>` candidatas de Whakoom (las que
devolvió la búsqueda Bing `site:whakoom.com "<serie>" <editorial>` armada por
`we_plan.py`) y decide, de forma 100% determinista, si alguna de esas
ediciones ES la edición española del item.

Una edición sólo se acepta si TODAS estas condiciones se cumplen:
  1. idioma == "Spanish (Spain)" (normalizado: contiene "spanish"/"espanol"/
     "castellano" Y "spain"/"espana" — `is_spanish_spain`).
  2. editorial coincide con `item.publisher` por CONJUNTO de tokens
     normalizados (sin acentos, sin stopwords editoriales genéricas), no por
     substring — tolera un imprint co-editado con el orden de tokens
     invertido (`publisher_matches`, endurecido tanda 3 2026-09-02, cierra
     `task_07e139d6`).
  3. `total_tomos` de la edición coincide con `listado.total_tomos`
     (preferentemente REMOTO — fetch real de `listadomanga.es/coleccion.php`
     vía `listadomanga_meta.py`, ver `we_plan.py`; cae a heurística LOCAL si
     no hay caché remoto). Si `listado.ongoing` o `cand.ongoing` es true
     (serie en curso en cualquiera de los dos lados), se acepta
     `cand.total_tomos >= listado.total_tomos` en vez de igualdad estricta
     — endurecimiento tanda 3, ver `_edition_total_tomos_ok`. Si
     `listado.total_tomos` es desconocido (None/0), se exige en cambio que
     `other_editions` NO tenga otra edición en Español de España del MISMO
     publisher (si la hay, no hay forma de desambiguar sin el dato → no se
     resuelve).
  4. Guard de reedición (`_reedition_guard_ok`, tanda 3): si la edición es
     oneshot (`total_tomos == 1`) o tiene una hermana ES del mismo publisher,
     el formato+páginas embebidos en el SLUG de whakoom
     (`"<título>-rustica_240_pp"`) deben ser consistentes con
     `listado.formato`/`listado.paginas` (remoto) — evita confundir
     reediciones del mismo sello con mismo `total_tomos` pero formato
     distinto (caso real curación tanda 1: `sensor-ecc-deluxe-es`).

Si más de una de las ediciones candidatas pasa las cuatro condiciones →
AMBIGUO, no se resuelve (nunca se adivina entre dos ediciones plausibles).

Si NINGUNA candidata resuelve por `language_mismatch`, el resultado incluye
`sibling_urls`: URLs de ediciones ES-España del mismo publisher listadas en
`other_editions[]` de las candidatas abiertas (típicamente el hub de una
edición LatAm que Bing indexó mejor) — el skill puede abrirlas como una
pasada adicional del Step 3 sin repetir la búsqueda Bing (endurecimiento
tanda 3, hallazgo tanda 2: 33 `language_mismatch`).

Al resolver una edición, ubica el tomo pedido (`item.volume`) en
`edition.volumes` (o el único tomo si el item es oneshot sin volumen) y
emite `candidate_urls` en el MISMO formato que consume `sc_validate.py`
(`{url, page_title, domain, query}`) — la validación de identidad/calidad
(descarga real + `_same_cover` + `_is_soft_image` + denylist) NO se
reimplementa acá, es 100% de `sc_validate.py` (fuente única, igual que
`/watch-search-covers`).

SIEMPRE persiste una fila en el caché append-only `data/whakoom_edition_map.jsonl`
(resuelto o no) — así `we_plan.py` no vuelve a plantear la misma búsqueda Bing
en corridas futuras. `--no-cache-write` la omite (tests).

Uso:
    we_resolve.py <input.json> [--cache PATH] [--no-cache-write]

FORMATO DE INPUT
-----------------
{
  "item": {... item completo de items.jsonl ...},
  "listado": {"coleccion_id": 1832, "total_tomos": 25, "formato": "", "paginas": "",
              "editorial": "", "ongoing": false, "source": "listadomanga_remota"},
  "candidates": [
    {
      "edition_id": 589084,
      "edition_url": "https://www.whakoom.com/ediciones/589084/dragon-ball-rustica_240_pp",
      "title": "Dragon Ball",
      "publisher": "Planeta Cómic",
      "language": "Spanish (Spain)",
      "formato": "Rústica con sobrecubierta",
      "total_tomos": 25,
      "ongoing": false,
      "other_editions": [{"language": "...", "publisher": "...", "formato": "...",
                          "total_tomos": N, "edition_url": "https://www.whakoom.com/ediciones/..."}],
      "volumes": [{"n": "1", "img_url": "https://i1.whakoom.com/small/.../x.jpg"}, ...]
    }
  ]
}

STDOUT
-------
{"resolved": bool, "reason": str, "edition_id": int|None, "edition_url": str,
 "candidate_urls": [...], "sibling_urls": [...]}
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

_SCRIPTS_RETROFIT = Path(__file__).resolve().parent
if str(_SCRIPTS_RETROFIT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_RETROFIT))


def _default_data_path(name: str) -> Path:
    data_dir = os.environ.get("MANGA_WATCH_DATA_DIR")
    base = Path(data_dir) if data_dir else _SCRIPTS_RETROFIT.parent.parent / "data"
    return base / name


# ── Normalización de editorial ──────────────────────────────────────────────
_PUBLISHER_STOPWORDS = frozenset({
    "ediciones", "edicion", "editorial", "edition", "editions", "sa", "sl",
    "comics", "comic", "manga", "books", "publishing", "group", "grupo",
    "españa", "espana", "spain",
})


def normalize_publisher_tokens(raw: str) -> frozenset[str]:
    """Conjunto de tokens normalizados (sin acentos, sin stopwords
    editoriales genéricas) — 'Editorial Ivrea España' → {'ivrea'}."""
    s = (raw or "").lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return frozenset(t for t in s.split() if t and t not in _PUBLISHER_STOPWORDS)


def normalize_publisher(raw: str) -> str:
    """'Editorial Ivrea España' → 'ivrea'. Sin acentos, sin stopwords
    genéricas. Se mantiene por compat (otros consumidores/tests esperan un
    string) — el match real (`publisher_matches`) NO usa esta forma string,
    compara CONJUNTOS (ver esa función)."""
    return " ".join(sorted(normalize_publisher_tokens(raw)))


def publisher_matches(a: str, b: str) -> bool:
    """Conjunto de tokens normalizados, orden libre — tolera un imprint
    co-editado con el orden de tokens invertido (hallazgo tanda 2, 2026-09-02:
    item local `"EDT Editores de Tebeos / Ediciones Glénat"` vs whakoom
    `"Glénat España - Editores de Tebeos"` — mismos tokens, orden distinto;
    la contención de substring vieja no matcheaba, 4 targets de Trigun Maximum
    rechazados por `publisher_mismatch` sin motivo real. Ver
    docs/scraper/sources/whakoom.md § 6, tarea `task_07e139d6`).

    Match si el conjunto de tokens de uno de los dos publishers está
    CONTENIDO en el del otro (en cualquier sentido) y comparten al menos un
    token — como ambos ya vienen sin stopwords genéricas, cualquier token
    compartido es "distintivo" por construcción (nunca "manga"/"comics"/
    "ediciones"/etc., ya filtrados)."""
    ta, tb = normalize_publisher_tokens(a), normalize_publisher_tokens(b)
    if not ta or not tb:
        return False
    if ta <= tb or tb <= ta:
        return bool(ta & tb)
    return False


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


# Términos de idioma/país español según el locale de la UI de Whakoom —
# verificado en vivo (piloto real, 2026-09-02): `www.whakoom.com` (sin
# subdominio) muestra el idioma en ESPAÑOL ("Español (España)"), no en inglés
# ("Spanish (Spain)") como se había asumido inicialmente del reconocimiento
# (que aparentemente vio `en.whakoom.com` o una sesión con Accept-Language
# distinto). `is_spanish_spain()` NO puede depender de un único idioma de UI —
# el skill navega a `www.whakoom.com` por defecto. Cubre inglés y español
# (los dos verificados en vivo); términos de otros locales quedan como
# extensión futura si aparecen en la práctica.
_SPANISH_LANG_TERMS = frozenset({"spanish", "espanol", "castellano"})
_SPAIN_COUNTRY_TERMS = frozenset({"spain", "espana"})


def is_spanish_spain(language: str) -> bool:
    l = _strip_accents((language or "").lower())
    return any(t in l for t in _SPANISH_LANG_TERMS) and any(t in l for t in _SPAIN_COUNTRY_TERMS)


def _norm_vol(v: Any) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    stripped = s.lstrip("0")
    return stripped if stripped else "0"


def find_volume_image(volumes: list[dict[str, Any]], target_volume: str) -> dict[str, Any] | None:
    """Ubica el tomo pedido en la lista de volúmenes de la edición.

    Sin `target_volume` (oneshot): sólo resuelve si hay EXACTAMENTE un tomo
    listado (si hay varios, no hay forma de saber cuál sin volumen declarado)."""
    tv = _norm_vol(target_volume)
    if not tv:
        return volumes[0] if len(volumes) == 1 else None
    for v in volumes:
        if _norm_vol(v.get("n", "")) == tv:
            return v
    return None


def _same_publisher_es_siblings(cand: dict[str, Any]) -> list[dict[str, Any]]:
    """Ediciones hermanas (`other_editions[]`) que son Español-España del
    MISMO publisher que `cand` — señal de posible ambigüedad/reedición."""
    others = cand.get("other_editions") or []
    return [
        o for o in others
        if is_spanish_spain(o.get("language", "")) and publisher_matches(o.get("publisher", ""), cand.get("publisher", ""))
    ]


def _edition_total_tomos_ok(cand: dict[str, Any], listado_total: Any, *, ongoing: bool = False) -> tuple[bool, str]:
    """Endurecimiento #1 (tanda 3, 2026-09-02): `listado_total` ahora viene
    preferentemente de `listadomanga_meta.py` (fetch REAL de
    `listadomanga.es/coleccion.php`), no sólo del heurístico local — ver
    docstring de `we_plan.py`.

    `ongoing`: True si CUALQUIERA de los dos lados (la colección de
    listadomanga vía `listado.ongoing`, o la propia edición whakoom vía
    `cand.ongoing`) está en curso — en ese caso se acepta `cand_total >=
    listado_total` en vez de igualdad estricta, porque:
      (a) listadomanga puede no haber editado aún tomos que whakoom ya
          cuenta (o viceversa), y
      (b) whakoom mismo puede llevar su contador de "N cómics" desactualizado
          en ediciones "Ongoing" (hallazgo tanda 1, ver whakoom.md § 6 —
          "Berserk Master Edition" mostraba 1 cómic con 2 tomos ya listados)."""
    cand_total = cand.get("total_tomos")
    if listado_total:
        if cand_total is None:
            return False, "total_tomos_unknown"
        try:
            cand_total_i = int(cand_total)
            listado_total_i = int(listado_total)
        except (TypeError, ValueError):
            return False, "total_tomos_unknown"
        if ongoing:
            return cand_total_i >= listado_total_i, "total_tomos_mismatch"
        return cand_total_i == listado_total_i, "total_tomos_mismatch"
    # Sin dato de referencia (ni remoto ni local): exigir que no haya otra
    # edición ES del mismo publisher entre las hermanas (si la hay, no se
    # puede desambiguar).
    if _same_publisher_es_siblings(cand):
        return False, "ambiguous_no_total_tomos"
    return True, ""


# ── Endurecimiento #2 (tanda 3): guard de reedición para oneshots ──────────
# Whakoom embebe formato+páginas en el SLUG de la edición: "sensor-rustica_
# 240_pp", "sunny-cartone_1282_pp", "frankenstein-flexibook_192_pp" —
# "<título>-<formato>_<NNN>_pp". Lo usamos para distinguir reediciones del
# MISMO sello con el MISMO total_tomos pero formato/páginas distintos (caso
# real, curación tanda 1: `sensor-ecc-deluxe-es` — único error de la tanda,
# una reedición del mismo sello con mismos tomos y páginas que casi se
# confunde con la edición rústica original).
_SLUG_FORMAT_PAGES_RE = re.compile(r"-([a-z]+)_(\d+)_pp\b", re.IGNORECASE)
_LISTADO_PAGES_RE = re.compile(r"(\d+)")
_FORMAT_SYNONYMS: dict[str, re.Pattern[str]] = {
    "rustica": re.compile(r"r[uú]stica|tapa\s*blanda", re.IGNORECASE),
    "cartone": re.compile(r"cart[oó]n[ée]|tapa\s*dura", re.IGNORECASE),
    "tapadura": re.compile(r"tapa\s*dura|cart[oó]n[ée]", re.IGNORECASE),
    "flexibook": re.compile(r"flexibook", re.IGNORECASE),
}


def _slug_format_pages(edition_url: str) -> tuple[str, int | None]:
    """'.../ediciones/1234/sensor-rustica_240_pp' → ('rustica', 240).
    Best-effort: si el slug no trae el patrón `-<formato>_<NNN>_pp`, devuelve
    ('', None) — el guard no bloquea sin datos (ver `_reedition_guard_ok`)."""
    slug = (edition_url or "").rstrip("/").rsplit("/", 1)[-1].lower()
    m = _SLUG_FORMAT_PAGES_RE.search(slug)
    if not m:
        return "", None
    return m.group(1), int(m.group(2))


def _reedition_guard_ok(cand: dict[str, Any], listado: dict[str, Any] | None) -> tuple[bool, str]:
    """Sólo aplica cuando `total_tomos` NO alcanza para descartar una
    reedición: la edición es oneshot (`total_tomos == 1`, el caso degenerado
    donde casi cualquier hermana también declara 1 tomo) O tiene una hermana
    ES del MISMO publisher que declara el MISMO `total_tomos` (si la hermana
    tiene un `total_tomos` distinto, el check de la condición 3 ya la
    hubiera descartado sola — no hace falta este guard, caso real
    "Berserk Deluxe" 13 tomos vs hermana regular 42 tomos, ver
    `test_fixture_berserk_deluxe_resolves_when_total_tomos_matches`). En
    cualquier otro caso no bloquea (`True, ""`).

    Si el slug de whakoom trae formato+páginas Y `listado.formato`/
    `listado.paginas` (de `listadomanga_meta.py` remoto) están disponibles,
    exige que sean consistentes. Sin datos suficientes para comparar: sólo
    bloquea si además hay una hermana con el mismo total_tomos (ambigüedad
    real, `ambiguous_sibling_same_publisher`) — sin ella, no hay nada que
    desambiguar y no bloquea."""
    listado = listado or {}
    cand_total = cand.get("total_tomos")
    siblings = _same_publisher_es_siblings(cand)
    same_total_siblings = [s for s in siblings if s.get("total_tomos") == cand_total]
    applies = (cand_total == 1) or bool(same_total_siblings)
    if not applies:
        return True, ""

    slug_fmt, slug_pages = _slug_format_pages(cand.get("edition_url", ""))
    listado_formato = listado.get("formato", "") or ""
    listado_paginas_raw = listado.get("paginas", "") or ""
    pm = _LISTADO_PAGES_RE.search(listado_paginas_raw)
    listado_pages_num = int(pm.group(1)) if pm else None

    if not slug_fmt or not listado_formato:
        if same_total_siblings:
            return False, "ambiguous_sibling_same_publisher"
        return True, ""

    pattern = _FORMAT_SYNONYMS.get(slug_fmt)
    fmt_ok = bool(pattern and pattern.search(listado_formato))
    pages_ok = True
    if slug_pages is not None and listado_pages_num is not None:
        pages_ok = slug_pages == listado_pages_num

    if fmt_ok and pages_ok:
        return True, ""
    if same_total_siblings:
        return False, "ambiguous_sibling_same_publisher"
    return False, "reedition_format_mismatch"


# ── Endurecimiento #4 (tanda 3): sugerir hermana ES desde "Other Editions" ──
def _collect_sibling_urls(item_publisher: str, edition_candidates: list[dict[str, Any]]) -> list[str]:
    """Cuando NINGUNA candidata abierta resuelve por idioma, busca en
    `other_editions[]` de esas mismas candidatas una hermana ES-España del
    publisher del ITEM con `edition_url` propia — hallazgo tanda 2 (33
    `language_mismatch`): Bing suele indexar mejor la edición LatAm que la
    de España para la MISMA obra+editorial (Yu Yu Hakusho, Baki, Fushigi
    Yûgi, Spy x Family, D.N.Angel, Black Jack); el hub de esa edición LatAm
    normalmente LISTA la hermana ES bajo "Otras ediciones" sin necesidad de
    una segunda búsqueda Bing. No abre ni resuelve nada acá — sólo devuelve
    URLs candidatas para que el skill las abra como Step 3 de una sola
    pasada adicional (ver SKILL.md)."""
    urls: list[str] = []
    seen: set[str] = set()
    for cand in edition_candidates:
        for sib in cand.get("other_editions") or []:
            url = (sib.get("edition_url") or "").strip()
            if not url or url in seen:
                continue
            if is_spanish_spain(sib.get("language", "")) and publisher_matches(sib.get("publisher", ""), item_publisher):
                seen.add(url)
                urls.append(url)
    return urls


def resolve_candidates(
    item: dict[str, Any],
    listado: dict[str, Any] | None,
    edition_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Decide cuál (si alguna) de las ediciones candidatas es la edición ES
    del item, y arma `candidate_urls` en formato `sc_validate.py`."""
    listado = listado or {}
    item_publisher = item.get("publisher", "")
    item_volume = str(item.get("volume") or "")
    listado_total = listado.get("total_tomos")
    listado_ongoing = bool(listado.get("ongoing"))

    passing: list[dict[str, Any]] = []
    reasons: list[str] = []
    for cand in edition_candidates:
        if not is_spanish_spain(cand.get("language", "")):
            reasons.append("language_mismatch")
            continue
        if not publisher_matches(cand.get("publisher", ""), item_publisher):
            reasons.append("publisher_mismatch")
            continue
        cand_ongoing = bool(cand.get("ongoing"))
        ok, why = _edition_total_tomos_ok(cand, listado_total, ongoing=listado_ongoing or cand_ongoing)
        if not ok:
            reasons.append(why)
            continue
        ok2, why2 = _reedition_guard_ok(cand, listado)
        if not ok2:
            reasons.append(why2)
            continue
        passing.append(cand)

    if not passing:
        reason = reasons[0] if reasons else "not_found"
        sibling_urls = _collect_sibling_urls(item_publisher, edition_candidates) if reason == "language_mismatch" else []
        return {"resolved": False, "reason": reason, "edition_id": None,
                "edition_url": "", "candidate_urls": [], "sibling_urls": sibling_urls}

    if len(passing) > 1:
        return {"resolved": False, "reason": "ambiguous_multiple_editions",
                "edition_id": None, "edition_url": "", "candidate_urls": [], "sibling_urls": []}

    cand = passing[0]
    vol_img = find_volume_image(cand.get("volumes") or [], item_volume)
    if vol_img is None:
        return {"resolved": False, "reason": "volume_not_listed",
                "edition_id": cand.get("edition_id"), "edition_url": cand.get("edition_url", ""),
                "candidate_urls": [], "sibling_urls": []}

    img_url = (vol_img.get("img_url") or "").strip()
    if not img_url:
        return {"resolved": False, "reason": "volume_no_image",
                "edition_id": cand.get("edition_id"), "edition_url": cand.get("edition_url", ""),
                "candidate_urls": [], "sibling_urls": []}

    series_title = item.get("series_display") or item.get("title") or ""
    vol_label = item_volume or "1"
    page_title = f"{series_title} #{vol_label}".strip()
    candidate_urls = [{
        "url": img_url,
        "page_title": page_title,
        "domain": "whakoom.com",
        "query": f"whakoom_edicion:{cand.get('edition_url', '')}",
    }]
    return {"resolved": True, "reason": "", "edition_id": cand.get("edition_id"),
            "edition_url": cand.get("edition_url", ""), "candidate_urls": candidate_urls,
            "sibling_urls": []}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def append_cache_row(
    cache_path: Path, *, item: dict[str, Any], listado: dict[str, Any] | None,
    result: dict[str, Any],
) -> None:
    listado = listado or {}
    method = "whakoom_edicion_page" if result.get("resolved") else (result.get("reason") or "not_found")
    row = {
        "series_key": item.get("series_key", ""),
        "series_display": item.get("series_display", ""),
        "publisher": item.get("publisher", ""),
        "country": item.get("country", ""),
        "listado_coleccion_id": listado.get("coleccion_id"),
        "total_tomos": listado.get("total_tomos"),
        "formato": listado.get("formato", ""),
        "whakoom_edition_id": result.get("edition_id"),
        "whakoom_edition_url": result.get("edition_url", ""),
        "resolved_at": _now_iso(),
        "method": method,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", help="Ruta al JSON con item/listado/candidates.")
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--no-cache-write", action="store_true")
    args = ap.parse_args(argv)

    if args.input:
        inp = Path(args.input)
    else:
        tmp_inputs = sorted(Path(".").glob(".tmp_we_input_*.json"))
        if not tmp_inputs:
            print(json.dumps({"resolved": False, "reason": "no input file found",
                              "edition_id": None, "edition_url": "", "candidate_urls": [],
                              "sibling_urls": []}))
            return 0
        inp = tmp_inputs[0]

    if not inp.exists():
        print(json.dumps({"resolved": False, "reason": f"input not found: {inp}",
                          "edition_id": None, "edition_url": "", "candidate_urls": [],
                          "sibling_urls": []}))
        return 0

    data = json.loads(inp.read_text(encoding="utf-8"))
    item = data.get("item", {}) or {}
    listado = data.get("listado", {}) or {}
    edition_candidates = data.get("candidates", []) or []

    result = resolve_candidates(item, listado, edition_candidates)

    if not args.no_cache_write:
        cache_path = args.cache if args.cache is not None else _default_data_path("whakoom_edition_map.jsonl")
        append_cache_row(cache_path, item=item, listado=listado, result=result)

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
