#!/usr/bin/env python3
"""fix_store_publisher.py — saca el NOMBRE DE TIENDA del campo `publisher`.

Bug (gotcha #44): las fuentes retailer JP "JP - Sanyodo Comic Limited Editions"
y "JP - Rakuten Books (search)" seteaban `publisher` = nombre de la tienda
("Sanyodo", "Rakuten Books / 楽天ブックス"). Pero la tienda NO es la editorial:
revenden ediciones estándar de Square Enix, Akita Shoten, Shodensha, Kadokawa,
etc. El publisher errado contamina el `edition_key` (`...-unknown-...` o el slug
de la tienda) y rompe el merge por ISBN con la ficha de la editorial oficial →
"posibles productos duplicados" en el Panel de Calidad.

Qué hace (conservador, no re-deriva a ciegas):

  PASE 1 — colapso de dups por ISBN (mismo producto, distinto cluster_key):
    Para cada grupo de items que comparten ISBN y contiene ≥1 item con
    publisher = nombre de tienda, SI todos comparten el MISMO series_key+volume
    y hay UN ÚNICO publisher real autoritativo (del campo publisher de un
    hermano, o del slug del edition_key; los conflictos se SALTAN), reescribe el
    edition_key de todos a `{series_key}-{slug_autoritativo}-{edition_slug}` y el
    campo publisher al nombre real. Esto es el mismo merge que sugiere el panel
    para "Mismo ISBN", restringido al caso seguro (series_key ya coincide → solo
    se corrige la porción de publisher del edition_key). Las divergencias de
    romanización del series_key NO se tocan (son trabajo del skill).

  PASE 2 — limpieza del campo publisher en el resto:
    Para cualquier item con publisher = nombre de tienda que quede, recupera la
    editorial real desde el slug de su propio edition_key (reverse-map por el
    corpus) o desde un hermano por ISBN; si no se puede, lo deja "" (mejor vacío
    que erróneo — el merge/skill lo completa). NO toca el edition_key.

Respeta aprobados (`is_approved`) — no los modifica.

Uso:
  .venv/bin/python scripts/retrofit/fix_store_publisher.py --dry-run
  .venv/bin/python scripts/retrofit/fix_store_publisher.py
"""
from __future__ import annotations
import json, sys, argparse
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import manga_watch as mw  # noqa: E402

ITEMS = ROOT / "data" / "items.jsonl"

# Nombres de TIENDA (no editoriales) a limpiar. Sanyodo (exacto), cualquier
# variante de "Rakuten Books", y "Kinokuniya …" (librería: la editorial real —
# Viz, Kodansha Comics, Seven Seas, TOKYOPOP… — ya está en el edition_key, ver
# gotcha #44). NO incluye tiendas mono-editorial (Ivrea AR, Distrito) ni labels
# que SÍ son editor de la variante (Funside, Manga Dreams, MangaYo — en el slug
# map a propósito).
_STORE_EXACT = {"sanyodo"}
_STORE_PREFIX = ("rakuten books", "kinokuniya")


def is_store_publisher(pub: str | None) -> bool:
    pl = (pub or "").strip().lower()
    if not pl:
        return False
    if pl in _STORE_EXACT:
        return True
    return any(pl.startswith(p) for p in _STORE_PREFIX)


def ek_pub_slug(it: dict) -> str | None:
    """Extrae la porción publisher-slug del edition_key.

    edition_key = f"{series_key}-{pub_slug}-{edition_slug}". El series_key se
    guarda aparte y el edition_slug es siempre un único token (sin guiones), así
    que: quito el prefijo series_key y hago rsplit por el último guión.
    """
    ek = (it.get("edition_key") or "").strip()
    sk = (it.get("series_key") or "").strip()
    if not ek or not sk or not ek.startswith(sk + "-"):
        return None
    rem = ek[len(sk) + 1:]
    pub_slug = rem.rsplit("-", 1)[0] if "-" in rem else None
    if not pub_slug or pub_slug == "unknown":
        return None
    return pub_slug


def ek_edition_slug(it: dict) -> str:
    ek = (it.get("edition_key") or "").strip()
    sk = (it.get("series_key") or "").strip()
    if ek and sk and ek.startswith(sk + "-"):
        return ek.rsplit("-", 1)[-1]
    return "regular"


def build_slug_to_display(items: list[dict]) -> dict[str, str]:
    """slug canónico → nombre de editorial más común en el corpus (campos reales,
    no tiendas). Sirve para reverse-map cuando solo conocemos el slug."""
    by_slug: dict[str, Counter] = defaultdict(Counter)
    for it in items:
        p = (it.get("publisher") or "").strip()
        if not p or is_store_publisher(p):
            continue
        slug = mw._publisher_slug(p)
        if slug != "unknown":
            by_slug[slug][p] += 1
    return {slug: cnt.most_common(1)[0][0] for slug, cnt in by_slug.items()}


def real_pub_slug(it: dict) -> str | None:
    """Slug autoritativo de un item: del campo publisher (si es real), si no del
    edition_key."""
    p = (it.get("publisher") or "").strip()
    if p and not is_store_publisher(p):
        s = mw._publisher_slug(p)
        if s != "unknown":
            return s
    return ek_pub_slug(it)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    items = [json.loads(l) for l in ITEMS.open() if l.strip()]
    slug_to_display = build_slug_to_display(items)

    def display_for(slug: str) -> str:
        return slug_to_display.get(slug) or slug.replace("-", " ").title()

    # ---- PASE 1: colapso de dups por ISBN -------------------------------------
    isbn_groups: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        isbn = (it.get("isbn") or "").strip()
        if isbn:
            isbn_groups[isbn].append(it)

    p1_changed, p1_groups = 0, 0
    p1_diffs: list[str] = []
    for isbn, grp in isbn_groups.items():
        if len(grp) < 2:
            continue
        if not any(is_store_publisher(m.get("publisher")) for m in grp):
            continue
        if any(mw.is_approved(m) for m in grp):
            continue
        # mismo producto físico ⇒ mismo series_key y volume; si no coinciden es
        # romanización divergente (trabajo del skill) → saltar.
        sks = {(m.get("series_key") or "") for m in grp}
        vols = {(m.get("volume") or "") for m in grp}
        if len(sks) != 1 or len(vols) != 1 or not next(iter(sks)):
            continue
        # publisher autoritativo: único slug real entre los miembros.
        slugs = {s for s in (real_pub_slug(m) for m in grp) if s}
        if len(slugs) != 1:
            continue  # conflicto (kadokawa vs bushiroad…) o sin info → saltar
        auth = next(iter(slugs))
        sk = next(iter(sks))
        # edition_slug: el más común entre los miembros (deberían coincidir).
        ed = Counter(ek_edition_slug(m) for m in grp).most_common(1)[0][0]
        new_ek = f"{sk}-{auth}-{ed}"
        display = display_for(auth)
        # display de edición: tomar el de un miembro con el slug correcto.
        templ = next((m for m in grp if ek_pub_slug(m) == auth), grp[0])
        new_ed_display = templ.get("edition_display") or ""
        group_touched = False
        for m in grp:
            new_pub = m.get("publisher")
            if is_store_publisher(new_pub):
                new_pub = display
            if m.get("edition_key") == new_ek and m.get("publisher") == new_pub:
                continue
            if len(p1_diffs) < 40:
                p1_diffs.append(
                    f"    ISBN {isbn}: ek {m.get('edition_key')!r} → {new_ek!r} | "
                    f"pub {m.get('publisher')!r} → {new_pub!r}")
            if not args.dry_run:
                m["edition_key"] = new_ek
                if new_ed_display:
                    m["edition_display"] = new_ed_display
                m["publisher"] = new_pub
                m["cluster_key"] = mw.derive_cluster_key(m)
            p1_changed += 1
            group_touched = True
        if group_touched:
            p1_groups += 1

    # ---- PASE 2: limpieza del campo publisher restante ------------------------
    isbn_real_pub: dict[str, str] = {}
    for it in items:
        p = (it.get("publisher") or "").strip()
        if p and not is_store_publisher(p):
            isbn = (it.get("isbn") or "").strip()
            if isbn:
                isbn_real_pub.setdefault(isbn, p)

    p2_blanked, p2_recovered = 0, 0
    p2_diffs: list[str] = []
    for it in items:
        if not is_store_publisher(it.get("publisher")):
            continue
        if mw.is_approved(it):
            continue
        slug = ek_pub_slug(it)
        if slug:
            new_pub = display_for(slug)
            p2_recovered += 1
        else:
            new_pub = isbn_real_pub.get((it.get("isbn") or "").strip(), "")
            if new_pub:
                p2_recovered += 1
            else:
                p2_blanked += 1
        if len(p2_diffs) < 40:
            p2_diffs.append(f"    pub {it.get('publisher')!r} → {new_pub!r}  ({it.get('title')!r})")
        if not args.dry_run:
            it["publisher"] = new_pub

    # ---- PASE 3: limpiar el nombre de tienda dentro de sources[] -------------
    # Cada entry de sources[] congela el publisher con que se scrapeó esa fuente.
    # Lo alineamos al publisher (ya corregido) del item, o "" si no hay.
    p3_changed = 0
    for it in items:
        if mw.is_approved(it):
            continue
        for s in it.get("sources") or []:
            if is_store_publisher(s.get("publisher")):
                if not args.dry_run:
                    s["publisher"] = it.get("publisher") or ""
                p3_changed += 1

    print(f"[store-pub] PASE 1 (dups ISBN): {p1_changed} filas en {p1_groups} grupos alineadas")
    for d in p1_diffs[:30]:
        print(d)
    print(f"[store-pub] PASE 2 (campo publisher): {p2_recovered} recuperadas, {p2_blanked} a \"\"")
    for d in p2_diffs[:20]:
        print(d)
    print(f"[store-pub] PASE 3 (sources[].publisher): {p3_changed} entradas limpiadas")

    if args.dry_run:
        print("[DRY-RUN] no se escribió nada.")
        return 0

    before = len(items)
    items = mw.consolidate_by_cluster(items)
    print(f"[store-pub] consolidate: {before} → {len(items)} ({before - len(items)} fusionados)")

    mw.backup_and_rotate(ITEMS, "storepub")
    mw.write_items_atomic(ITEMS, items)
    print(f"[store-pub] escrito {ITEMS}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
