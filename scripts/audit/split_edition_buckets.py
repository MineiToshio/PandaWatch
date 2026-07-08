#!/usr/bin/env python3
"""split_edition_buckets.py — detector READ-ONLY de ediciones sospechosas de
estar partidas SOLO por el slug de TIPO (data/items.jsonl).

Contexto (WO-F, auditoría post-scrape 2026-07-07): el auto-merge de ediciones
"parecidas" fue VETADO por el red team (falso positivo real: deluxe/regular NO
son el mismo producto). Este script reemplaza esa idea por un reporte para
revisión HUMANA: agrupa filas NO-lmc (fuera de la regla /coleccion=edición de
listadomanga — ver COLED en validate_corpus.py) por (series_key, país del
edition_key, volume) y, dentro de cada grupo, aísla los casos donde 2+
edition_keys comparten EXACTAMENTE el mismo prefijo serie+publisher y país,
y sólo difieren en el slug de TIPO (special/limited/collector/deluxe/ultimate/
perfect/master/boxset/variant/cofanetto…). Esa es la firma de "probablemente
la MISMA edición con el tipo etiquetado de forma inconsistente" — pero el
script NO decide ni fusiona nada: sólo junta la evidencia (fuentes, ISBN
compartido como señal fuerte de duplicado real, título de muestra) para que
un humano (o un skill con criterio) revise caso por caso.

Formato del edition_key (fuente única del FORMATO: `manga_watch.
rebuild_edition_key_prefix`, gotcha del prefijo): `{series}-{pub}-{slug}-{país}`
(+ sufijo opcional `-cN` de colisión). Este script reimplementa LOCALMENTE el
mismo parseo right-to-left en modo sólo-lectura (no reconstruye la key, sólo la
inspecciona) usando las mismas tablas (`_KNOWN_EDITION_SLUGS`,
`_PUBLISHER_SLUG_MAP`, `_COUNTRY_SLUG_MAP`) importadas de manga_watch.py.

No escribe NADA por default. `--json PATH` es la única forma de persistir algo,
y es explícita/opt-in.

Uso:
  .venv/bin/python scripts/audit/split_edition_buckets.py
  .venv/bin/python scripts/audit/split_edition_buckets.py --json data/diagnostics/split-buckets.json
"""
from __future__ import annotations
import argparse, json, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"

_CN_SUFFIX = re.compile(r"c\d+")


def _parse_edition_key(ek: str, countries: set, known_slugs: frozenset,
                        known_pubs: set) -> tuple[str, str, str, str] | None:
    """Parsea `edition_key` en (series_part, pub, slug, country), o None si no
    matchea el formato `{series}-{pub}-{slug}-{país}` (+ `-cN` opcional,
    descartado). Espejo LOCAL del right-to-left parse de
    `manga_watch.rebuild_edition_key_prefix` — acá sólo se INSPECCIONA, nunca
    se reconstruye ni se escribe. `country`/`slug` deben ser reconocidos
    (allowlists importadas); si no, devuelve None (edition_key ya cubierto por
    PAIS/EKMALFORMED en validate_corpus.py, o formato atípico — no es este
    script quien lo audita)."""
    if not ek:
        return None
    parts = ek.split("-")
    if parts and _CN_SUFFIX.fullmatch(parts[-1]):
        parts = parts[:-1]
    if len(parts) < 4:
        return None
    country, slug = parts[-1], parts[-2]
    if country not in countries or slug not in known_slugs:
        return None
    if len(parts) >= 5 and "-".join(parts[-4:-2]) in known_pubs:
        pub = "-".join(parts[-4:-2])
        series_part = "-".join(parts[:-4])
    elif parts[-3] in known_pubs:
        pub = parts[-3]
        series_part = "-".join(parts[:-3])
    else:
        return None
    if not series_part:
        return None
    return (series_part, pub, slug, country)


def _sources_of(items: list[dict]) -> list[str]:
    names: set[str] = set()
    for it in items:
        for s in (it.get("sources") or []):
            n = (s.get("name") or s.get("source") or "").strip()
            if n:
                names.add(n)
        n = (it.get("source") or "").strip()
        if n:
            names.add(n)
    return sorted(names)


def _isbns_of(items: list[dict]) -> list[str]:
    out = {(it.get("isbn") or "").strip() for it in items}
    out.discard("")
    return sorted(out)


def find_buckets(items: list[dict]) -> tuple[list[dict], int]:
    """Devuelve (buckets, n_non_lmc). Cada bucket:
    {series_key, country, volume, prefix, edition_keys: [...], shared_isbn: [...]}
    """
    countries = set(mw._COUNTRY_SLUG_MAP.values())
    known_slugs = mw._KNOWN_EDITION_SLUGS
    known_pubs = set(mw._PUBLISHER_SLUG_MAP.values()) | {"unknown"}

    # non-lmc: fuera de la regla /coleccion=edición de listadomanga (esas ya
    # están gobernadas por COLED en validate_corpus.py — auto-merge ahí sería
    # redundante y potencialmente incorrecto, la /coleccion manda).
    non_lmc = [it for it in items if not (it.get("cluster_key") or "").startswith("lmc:")]

    # (series_key, country, volume, series_part, pub) -> [(edition_key, slug, item)]
    by_prefix: dict[tuple, list[tuple[str, str, dict]]] = defaultdict(list)
    for it in non_lmc:
        ek = (it.get("edition_key") or "").strip()
        if not ek:
            continue
        parsed = _parse_edition_key(ek, countries, known_slugs, known_pubs)
        if not parsed:
            continue
        series_part, pub, slug, country = parsed
        sk = (it.get("series_key") or "").strip() or series_part
        vol = (it.get("volume") or "").strip()
        by_prefix[(sk, country, vol, series_part, pub)].append((ek, slug, it))

    buckets: list[dict] = []
    for (sk, country, vol, series_part, pub), rows in by_prefix.items():
        distinct_eks = {ek for ek, _, _ in rows}
        distinct_slugs = {slug for _, slug, _ in rows}
        # Firma de "difieren SOLO en el slug de tipo": mismo (series_key, país,
        # volumen, series_part, publisher) — eso YA lo garantiza la clave de
        # agrupación — Y 2+ edition_keys Y 2+ slugs distintos entre ellos.
        if len(distinct_eks) < 2 or len(distinct_slugs) < 2:
            continue

        by_ek: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for ek, slug, it in rows:
            by_ek[ek].append((slug, it))

        isbn_owner: dict[str, set[str]] = defaultdict(set)
        ek_entries = []
        for ek, group in sorted(by_ek.items()):
            its = [it for _, it in group]
            slug = group[0][0]
            isbns = _isbns_of(its)
            for isbn in isbns:
                isbn_owner[isbn].add(ek)
            ek_entries.append({
                "edition_key": ek,
                "slug": slug,
                "n_items": len(its),
                "sources": _sources_of(its),
                "isbns": isbns,
                "sample_title": (its[0].get("title") or "")[:120],
            })
        shared_isbn = sorted(isbn for isbn, eks in isbn_owner.items() if len(eks) > 1)

        buckets.append({
            "series_key": sk,
            "country": country,
            "volume": vol,
            "prefix": f"{series_part}-{pub}",
            "edition_keys": ek_entries,
            "shared_isbn": shared_isbn,
        })

    # Buckets con ISBN compartido primero (señal fuerte de dup real), después
    # por cantidad de edition_keys involucrados (impacto).
    buckets.sort(key=lambda b: (not b["shared_isbn"], -len(b["edition_keys"]),
                                 b["series_key"]))
    return buckets, len(non_lmc)


def _print_bucket(b: dict) -> None:
    isbn_tag = f" ISBN COMPARTIDO={b['shared_isbn']}" if b["shared_isbn"] else ""
    print(f"- {b['series_key']} · {b['country']} · vol {b['volume'] or '—'}"
          f"{isbn_tag}")
    print(f"    prefix: {b['prefix']}")
    for e in b["edition_keys"]:
        srcs = ", ".join(e["sources"][:4]) or "(sin sources)"
        isbns = ", ".join(e["isbns"]) or "—"
        print(f"    · {e['edition_key']}  [{e['slug']}]  ×{e['n_items']}  "
              f"fuentes: {srcs}  isbn: {isbns}")
        print(f"        \"{e['sample_title']}\"")
    print()


def _print_human(buckets: list[dict], n_non_lmc: int, n_total: int, examples: int) -> None:
    """Resumen a stdout: SIEMPRE se listan los buckets con ISBN compartido
    (señal fuerte de dup real — pocos, alto valor); el resto (ediciones que
    probablemente SÍ son distintas — artbook vs fanbook vs collector…) se capa
    a `examples` para no inundar la terminal. El detalle completo de los 433+
    buckets vive en --json."""
    with_isbn = [b for b in buckets if b["shared_isbn"]]
    without_isbn = [b for b in buckets if not b["shared_isbn"]]

    print(f"=== SPLIT EDITION BUCKETS ({n_total} items, {n_non_lmc} no-lmc) ===\n")
    print(f"Buckets sospechosos (>1 edition_key que difieren SOLO en el slug de "
          f"tipo): {len(buckets)}")
    print(f"  con ISBN compartido (señal fuerte de dup real): {len(with_isbn)}")
    print(f"  sin ISBN compartido (probablemente ediciones distintas de "
          f"verdad — artbook/fanbook/collector/variant… no son duplicados "
          f"entre sí, revisar igual): {len(without_isbn)}\n")

    if with_isbn:
        print(f"--- Con ISBN compartido ({len(with_isbn)}) ---\n")
        for b in with_isbn:
            _print_bucket(b)

    shown = without_isbn[:examples]
    if shown:
        print(f"--- Sin ISBN compartido — primeros {len(shown)} de "
              f"{len(without_isbn)} ---\n")
        for b in shown:
            _print_bucket(b)
    remaining = len(without_isbn) - len(shown)
    if remaining > 0:
        print(f"… {remaining} bucket(s) más sin mostrar. Usá --json PATH para "
              f"el reporte completo, o --examples N para ver más acá.\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(ITEMS),
                    help="corpus a auditar (default data/items.jsonl)")
    ap.add_argument("--json", default="",
                    help="si se pasa, escribe el reporte estructurado a esta ruta "
                         "(NUNCA se escribe nada sin este flag — script read-only)")
    ap.add_argument("--examples", type=int, default=20,
                    help="cuántos buckets SIN isbn compartido mostrar en stdout "
                         "(los que SÍ comparten ISBN siempre se listan todos)")
    args = ap.parse_args()

    items = [json.loads(l) for l in Path(args.file).open() if l.strip()]
    buckets, n_non_lmc = find_buckets(items)
    _print_human(buckets, n_non_lmc, len(items), args.examples)

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"total": len(items), "non_lmc": n_non_lmc, "buckets": buckets},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[OK] reporte JSON → {out}  ({len(buckets)} buckets)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
