#!/usr/bin/env python3
"""fix_listadomanga_editions.py — re-deriva edition_key DETERMINÍSTICAMENTE para
items de listadomanga-collections, enforzando la regla del owner (2026-06-06):

    "Cada página /coleccion?id=N es UNA edición. La MISMA obra en distintos
     /coleccion son ediciones DISTINTAS — nunca en el mismo grupo de edición."

El standardize (LLM) violaba esto: agrupaba colecciones distintas bajo el mismo
edition_key (ej. FMA cole=50 tomos-con-cofre + cole=524 artbook → ambos
'fullmetal-alchemist-norma-special'). Acá derivamos el edition_slug de forma
determinística desde campos confiables (product_type, tag edition:KIND, y el
título de colección embebido en description), e imponemos que colecciones
distintas tengan edition_keys distintos.

Uso:
  .venv/bin/python scripts/retrofit/fix_listadomanga_editions.py --dry-run
  .venv/bin/python scripts/retrofit/fix_listadomanga_editions.py        # aplica
"""
from __future__ import annotations
import json, re, sys, argparse, shutil
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "wikis"))
import listadomanga_collections as lmc  # noqa: E402
from manga_watch import derive_cluster_key, consolidate_by_cluster  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"

# product_type intrínsecamente = su propio slug de edición.
PTYPE_SLUG = {"artbook": "artbook", "fanbook": "fanbook", "guidebook": "guidebook",
              "magazine": "magazine", "boxset": "boxset"}
# tag edition:KIND → slug (para secciones especiales explícitas).
KIND_SLUG = {"especial": "special", "limitada": "limited", "alternativa": "variant",
             "pack": "boxset", "box": "boxset"}
# signal del título de colección → slug (para regular premium: Kanzenban, etc.).
TITLE_SIGNAL_SLUG = [  # orden de prioridad
    ("artbook", "artbook"), ("fanbook", "fanbook"), ("guidebook", "guidebook"),
    ("kanzenban", "kanzenban"), ("omnibus", "integral"), ("deluxe", "deluxe"),
    ("special_edition", "special"), ("variant_cover", "variant"),
]
# slug → sufijo de display para el título.
SLUG_DISPLAY = {"regular": "", "artbook": "Artbook", "fanbook": "Fanbook",
                "guidebook": "Guidebook", "magazine": "Magazine", "boxset": "Box Set",
                "kanzenban": "Kanzenban", "integral": "Edición Integral",
                "deluxe": "Deluxe", "special": "Edición Especial", "limited": "Edición Limitada",
                "variant": "Variant", "collector": "Coleccionista"}


def coleccion_id(it: dict) -> str | None:
    m = re.search(r"coleccion\.php\?id=(\d+)", it.get("url", "") or "")
    return m.group(1) if m else None


def edition_kind_tag(it: dict) -> str:
    for t in it.get("tags") or []:
        if t.startswith("edition:"):
            return t.split(":", 1)[1]
    return "regular"


def collection_title(it: dict) -> str:
    return (it.get("description", "") or "").split(" · ")[0].strip()


# Detección AMPLIA de "el título de colección es un artbook/illustration book".
ARTBOOK_TITLE_RE = re.compile(
    r"\b(?:artbook|art\s*book|art\s*works?|illustrations?|ilustraciones|"
    r"libro\s+de\s+ilustraciones|the\s+art\s+of|画集|イラスト集)\b",
    re.IGNORECASE | re.UNICODE,
)
# Slugs premium-ish que son INCORRECTOS para un tomo regular con extras de 1ª ed.
WRONG_FOR_COFRE = {"special", "limited", "collector", "integral", "deluxe", "variant"}


def propose_slug(it: dict, old_slug: str) -> str:
    """Conservador: SOLO corrige los dos patrones que el owner reportó como
    mal etiquetados. Todo lo demás conserva su slug (no re-derivamos a ciegas
    — product_type y títulos son ruidosos).

    a) Tomo regular con extras de 1ª edición (`from_extras`, tag edition:regular)
       mal slugueado como special/limited/etc → es un tomo REGULAR con bonus.
    b) Colección cuyo TÍTULO es un artbook/illustration book, mal slugueada como
       special/limited/etc → `artbook`.
    """
    tags = it.get("tags") or []
    kind = edition_kind_tag(it)
    ct = collection_title(it)
    # (a) cofre/extras de 1ª edición = tomo regular
    if kind == "regular" and "from_extras" in tags and old_slug in WRONG_FOR_COFRE:
        return "regular"
    # (b) artbook por título
    if old_slug in (WRONG_FOR_COFRE | {"regular"}) and ARTBOOK_TITLE_RE.search(ct):
        return "artbook"
    return old_slug


def split_series_publisher(edition_key: str, series_key: str) -> tuple[str, str] | None:
    """edition_key = {series_key}-{publisher_slug}-{slug}. El slug es un token
    sin guiones (allowlist), así que rsplit('-',1) separa publisher (que puede
    tener guiones: panini-es) del slug. Devuelve (series_key, publisher_slug, old_slug)."""
    if not edition_key or not series_key:
        return None
    if not edition_key.startswith(series_key + "-"):
        return None
    remainder = edition_key[len(series_key) + 1:]
    if "-" not in remainder:
        return None
    publisher_slug, old_slug = remainder.rsplit("-", 1)
    return series_key, publisher_slug, old_slug


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    items = [json.loads(l) for l in ITEMS.open() if l.strip()]

    # 1) Proponer slug + (series, publisher) para cada item lmc estandarizado.
    proposals: dict[int, dict] = {}  # idx -> {ek_base, slug, cid, series, pub}
    for i, it in enumerate(items):
        if "coleccion.php" not in (it.get("url", "") or ""):
            continue
        sk = it.get("series_key", "")
        ek = it.get("edition_key", "")
        sp = split_series_publisher(ek, sk)
        if not sp:
            continue  # raw (sin edition_key) o no parseable → lo arregla standardize
        series, pub, old_slug = sp
        cid = coleccion_id(it)
        if not cid:
            continue
        slug = propose_slug(it, old_slug)
        proposals[i] = {"slug": slug, "old_slug": old_slug, "cid": cid,
                        "series": series, "pub": pub, "ek_base": f"{series}-{pub}-{slug}"}

    # 2) Enforzar coleccion = edición: si un ek_base abarca >1 coleccion id,
    #    desambiguar por coleccion (append -cN) para que NUNCA se fusionen.
    ek_to_cids: dict[str, set] = defaultdict(set)
    for p in proposals.values():
        ek_to_cids[p["ek_base"]].add(p["cid"])
    collide = {ek for ek, cids in ek_to_cids.items() if len(cids) > 1}

    # 3) Aplicar.
    changed = 0
    diffs = []
    for i, p in proposals.items():
        it = items[i]
        new_ek = p["ek_base"]
        if new_ek in collide:
            new_ek = f"{new_ek}-c{p['cid']}"
        old_ek = it.get("edition_key", "")
        if new_ek == old_ek:
            continue
        # SOLO reescribimos display/título cuando el SLUG cambió por la corrección
        # (special→regular / →artbook). En splits por colisión (slug igual, solo
        # sufijo -cN) NO tocamos el título — sino perderíamos nombres de edición
        # sin display mapeado (ej. "Death Note Black Edition" → "Death Note").
        slug_changed = p["slug"] != p["old_slug"]
        new_title = it.get("title", "")
        if slug_changed:
            suffix = SLUG_DISPLAY.get(p["slug"], "")
            sd = it.get("series_display") or ""
            vol = it.get("volume") or ""
            new_title = " ".join(x for x in [sd, suffix, vol] if x).strip()
        if len(diffs) < 60:
            diffs.append((it.get("url", "")[-40:], old_ek, new_ek,
                          it.get("title", ""), new_title))
        if not args.dry_run:
            it["edition_key"] = new_ek
            if slug_changed:
                it["edition_display"] = SLUG_DISPLAY.get(p["slug"], "")
                if it.get("series_display"):
                    it["title"] = new_title
        changed += 1

    # Reporte
    print(f"[lmc-editions] items lmc estandarizados: {len(proposals)}")
    print(f"[lmc-editions] edition_keys con colisión multi-coleccion: {len(collide)}")
    for ek in sorted(collide)[:15]:
        print(f"    COLISIÓN {ek!r} → colecciones {sorted(ek_to_cids[ek])}")
    print(f"[lmc-editions] items con edition_key cambiado: {changed}")
    print("\n  ejemplos (url | old_ek → new_ek | old_title → new_title):")
    for url, oek, nek, ot, nt in diffs[:30]:
        print(f"    …{url}\n        {oek}  →  {nek}\n        {ot!r} → {nt!r}")

    if args.dry_run:
        print("\n[DRY-RUN] no se escribió nada.")
        return 0

    # 4) Recomputar cluster_key + consolidar (misma primitiva que el ingest).
    for it in items:
        it["cluster_key"] = derive_cluster_key(it)
    before = len(items)
    items = consolidate_by_cluster(items)
    print(f"[lmc-editions] consolidate: {before} → {len(items)} ({before - len(items)} fusionados)")

    bak = ITEMS.with_suffix(".jsonl.pre-fix-editions-bak")
    shutil.copy(ITEMS, bak)
    tmp = ITEMS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(ITEMS)
    print(f"[lmc-editions] escrito {ITEMS} ({changed} items corregidos). Backup: {bak}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
