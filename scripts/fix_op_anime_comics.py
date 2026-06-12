#!/usr/bin/env python3
"""One-shot corrección de los anime comics de One Piece (tanda research import).

Arregla 3 problemas detectados:
  1. Ediciones marcadas "tomo 1" que en realidad son TOMO ÚNICO.
  2. Ediciones cuyo anime comic NO existe (solo hay novela) -> convertir a novela.
  3. ISBNs corruptos/barajados en la tanda Shueisha 'special volumes' +
     tomo 2 faltante de Cursed Holy Sword.

Verificado vía openBD + ja.wikipedia + Glénat/PlaneteBD (junio 2026).
Idempotente sobre (edition_key, volume). Atómico (tmp + rename) con backup.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import requests
from manga_watch import backup_and_rotate
import image_store
from image_store import download_image

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.jsonl"
IMAGES_DIR = ROOT / "data" / "images"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "manga-watch-personal/0.2"})


def isbn13_to_isbn10(isbn13: str) -> str:
    core = isbn13[3:12]  # drop 978, take 9 digits
    s = sum((10 - i) * int(d) for i, d in enumerate(core))
    check = (11 - (s % 11)) % 11
    return core + ("X" if check == 10 else str(check))


def amazon_cover(isbn13: str) -> str:
    return f"https://images-na.ssl-images-amazon.com/images/P/{isbn13_to_isbn10(isbn13)}.01.LZZZZZZZ.jpg"


def shueisha_url(isbn13: str) -> str:
    d = isbn13
    dashed = f"{d[:3]}-{d[3]}-{d[4:6]}-{d[6:12]}-{d[12]}"
    return f"https://www.shueisha.co.jp/books/items/contents.html?isbn={dashed}"


# ---- target specs keyed by (edition_key, volume_as_str) -------------------
# action: 'single' | 'fix' | 'novel' | 'delete'
SPECS = {
    # ----- Group 1: Glénat single tomes (sólo volumen -> único) -----
    ("one-piece-glenat-animecomics-alabasta", "1"): {"action": "single"},
    ("one-piece-glenat-animecomics-episode-chopper", "1"): {"action": "single"},
    ("one-piece-glenat-animecomics-karakuri", "1"): {"action": "single"},

    # ----- Group 1: Shueisha single anime comics (volumen -> único, ISBN ok) -----
    ("one-piece-shueisha-animecomics-movie-7", "1"): {
        "action": "single", "isbn": "9784088741727",
        "release_date": "2006-11-02", "price": "¥ 1190",
        "title_original": "ONE PIECE THE MOVIE カラクリ城のメカ巨兵 アニメコミックス",
    },
    ("one-piece-shueisha-animecomics-movie-8", "1"): {
        "action": "single", "isbn": "9784088742366",
        "release_date": "2008-03-04", "price": "¥ 1190",
        "title_original": "劇場版 ONE PIECE エピソードオブアラバスタ 砂漠の王女と海賊たち アニメコミックス",
    },

    # ----- Group 2: genuine 2-vol anime comics (fix ISBN/URL/cover/price) -----
    ("one-piece-shueisha-animecomics-movie-4", "1"): {
        "action": "fix", "isbn": "9784088735474",
        "release_date": "2003-10-03", "price": "¥ 714",
        "title_original": "劇場版 ONE PIECE デッドエンドの冒険 アニメコミックス 上",
    },
    ("one-piece-shueisha-animecomics-movie-4", "2"): {
        "action": "fix", "isbn": "9784088735481",
        "release_date": "2003-10-03", "price": "¥ 714",
        "title_original": "劇場版 ONE PIECE デッドエンドの冒険 アニメコミックス 下",
    },
    ("one-piece-shueisha-animecomics-movie-5", "1"): {
        "action": "fix", "isbn": "9784088737072",
        "release_date": "2004-07-02", "price": "¥ 714",
        "title_original": "劇場版 ONE PIECE 呪われた聖剣 アニメコミックス 上",
    },

    # ----- Group 3: fabricated anime comics -> novelas (info real) -----
    ("one-piece-shueisha-animecomics-movie-2", "1"): {
        "action": "novel",
        "new_edition_key": "one-piece-shueisha-novel-clockwork-island",
        "edition_display": "Novela Clockwork Island (Shueisha, JUMP j BOOKS)",
        "title": "One Piece Clockwork Island (Novela)",
        "title_original": "ONE PIECE ねじまき島の冒険 (JUMP j BOOKS)",
        "isbn": "9784087031027", "release_date": "2001-03-19", "price": "¥ 743",
        "description": "Novelización (JUMP j BOOKS) de la película One Piece: La aventura de la isla mecánica (Clockwork Island). El anime comic de esta película nunca se publicó.",
    },
    ("one-piece-shueisha-animecomics-movie-3", "1"): {
        "action": "novel",
        "new_edition_key": "one-piece-shueisha-novel-chopper-kingdom",
        "edition_display": "Novela Chopper's Kingdom (Shueisha, JUMP j BOOKS)",
        "title": "One Piece Chopper's Kingdom (Novela)",
        "title_original": "ONE PIECE 珍獣島のチョッパー王国 (JUMP j BOOKS)",
        "isbn": "9784087031102", "release_date": "2002-03-19", "price": "¥ 743",
        "description": "Novelización (JUMP j BOOKS) de la película One Piece: El reino de Chopper en la isla de los animales extraños. El anime comic de esta película nunca se publicó.",
    },
    ("one-piece-shueisha-animecomics-movie-6", "1"): {
        "action": "novel",
        "new_edition_key": "one-piece-shueisha-novel-baron-omatsuri",
        "edition_display": "Novela Baron Omatsuri (Shueisha, JUMP j BOOKS)",
        "title": "One Piece Baron Omatsuri (Novela)",
        "title_original": "ONE PIECE THE MOVIE オマツリ男爵と秘密の島 (JUMP j BOOKS)",
        "isbn": "9784087031539", "release_date": "2005-03-19", "price": "¥ 743",
        "description": "Novelización (JUMP j BOOKS) de la película One Piece: El barón Omatsuri y la isla secreta. El anime comic de esta película nunca se publicó.",
    },

    # ----- delete the fabricated movie-2 tomo 2 (no existe 2do volumen) -----
    ("one-piece-shueisha-animecomics-movie-2", "2"): {"action": "delete"},
}

# New item to add: Cursed Holy Sword tomo 2 (下)
NEW_MOVIE5_VOL2 = {
    "_clone_from": ("one-piece-shueisha-animecomics-movie-5", "1"),
    "isbn": "9784088737089", "volume": "2",
    "title": "One Piece Cursed Holy Sword Anime Comics 2",
    "title_original": "劇場版 ONE PIECE 呪われた聖剣 アニメコミックス 下",
    "release_date": "2004-07-02", "price": "¥ 714",
}


def set_cover(item, isbn13):
    """Descarga la portada Amazon por ISBN y la fija como images[0] (la portada)."""
    url = amazon_cover(isbn13)
    local = download_image(url, IMAGES_DIR, session=SESSION)
    item["images"] = [{"kind": "cover", "url": url, "local": local}]
    return bool(local)


def sync_sources(item):
    """Re-sincroniza sources[0] (la única) con la portada (images[0]) + campos top-level.

    Los campos `image_url`/`image_local` de sources[] son per-fuente (otro layer):
    se rellenan desde la portada del item (images[0]).
    """
    if item.get("sources"):
        s = item["sources"][0]
        s["image_url"] = image_store.cover_url(item)
        s["image_local"] = image_store.cover_local(item)
        for f in ("price", "release_date", "publisher", "country", "language"):
            if f in item:
                s[f] = item[f]
        s["url"] = item["url"]


def apply_single(item, spec):
    vol = item.get("volume")
    # strip trailing " N" from title
    title = item.get("title", "")
    if vol and title.rstrip().endswith(" " + str(vol)):
        item["title"] = title.rstrip()[: -(len(str(vol)) + 1)].rstrip()
    item["volume"] = ""
    ek = item["edition_key"]
    item["cluster_key"] = f"edition:{ek}|"
    item["slug"] = ek
    if "isbn" in spec:
        item["isbn"] = spec["isbn"]
        item["url"] = shueisha_url(spec["isbn"])
        set_cover(item, spec["isbn"])
    for f in ("release_date", "price", "title_original"):
        if f in spec:
            item[f] = spec[f]
    sync_sources(item)


def apply_fix(item, spec):
    item["isbn"] = spec["isbn"]
    item["url"] = shueisha_url(spec["isbn"])
    for f in ("release_date", "price", "title_original"):
        if f in spec:
            item[f] = spec[f]
    set_cover(item, spec["isbn"])
    sync_sources(item)


def apply_novel(item, spec):
    new_ek = spec["new_edition_key"]
    item["edition_key"] = new_ek
    item["edition_display"] = spec["edition_display"]
    item["title"] = spec["title"]
    item["title_original"] = spec["title_original"]
    item["volume"] = ""
    item["isbn"] = spec["isbn"]
    item["url"] = shueisha_url(spec["isbn"])
    item["release_date"] = spec["release_date"]
    item["price"] = spec["price"]
    item["description"] = spec["description"]
    item["description_es"] = spec["description"]
    item["product_type"] = "novel"
    item["author"] = "浜崎 達也 / 尾田 栄一郎"
    item["signal_types"] = []
    tags = item.get("tags") or []
    if "novela" not in tags:
        tags = tags + ["novela"]
    item["tags"] = tags
    item["cluster_key"] = f"edition:{new_ek}|"
    item["slug"] = new_ek
    set_cover(item, spec["isbn"])
    sync_sources(item)


def main():
    backup_and_rotate(ITEMS, "fix-op-anime-comics")
    rows = [json.loads(l) for l in ITEMS.read_text(encoding="utf-8").splitlines() if l.strip()]

    out = []
    touched = {"single": 0, "fix": 0, "novel": 0, "delete": 0}
    clone_src = None

    for it in rows:
        key = (it.get("edition_key"), str(it.get("volume")))
        spec = SPECS.get(key)
        if spec is None:
            out.append(it)
            continue
        act = spec["action"]
        if act == "delete":
            touched["delete"] += 1
            print(f"  DELETE  {key[0]} vol{key[1]}  ({it.get('title')})")
            continue
        if act == "single":
            apply_single(it, spec)
        elif act == "fix":
            apply_fix(it, spec)
        elif act == "novel":
            apply_novel(it, spec)
        touched[act] += 1
        print(f"  {act.upper():6} {it['edition_key']} -> vol={it.get('volume')!r} isbn={it.get('isbn')} cover={'ok' if image_store.cover_local(it) else 'NO'}")
        if NEW_MOVIE5_VOL2["_clone_from"] == key:
            clone_src = it
        out.append(it)

    # Add Cursed Holy Sword tomo 2 (clone movie-5 vol1, override)
    already_v2 = any(
        i.get("edition_key") == "one-piece-shueisha-animecomics-movie-5"
        and str(i.get("volume")) == "2" for i in out
    )
    if clone_src and not already_v2:
        nv = json.loads(json.dumps(clone_src))  # deep copy
        sp = NEW_MOVIE5_VOL2
        nv["isbn"] = sp["isbn"]
        nv["volume"] = sp["volume"]
        nv["title"] = sp["title"]
        nv["title_original"] = sp["title_original"]
        nv["release_date"] = sp["release_date"]
        nv["price"] = sp["price"]
        nv["url"] = shueisha_url(sp["isbn"])
        ek = nv["edition_key"]
        nv["cluster_key"] = f"edition:{ek}|2"
        nv["slug"] = f"{ek}-2"
        set_cover(nv, sp["isbn"])
        sync_sources(nv)
        out.append(nv)
        print(f"  ADD    {ek} vol2 isbn={nv['isbn']} cover={'ok' if image_store.cover_local(nv) else 'NO'}")

    tmp = ITEMS.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for it in out:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(ITEMS)
    print(f"\nDone. {touched}  added_movie5_v2={bool(clone_src and not already_v2)}  total_rows={len(out)}")


if __name__ == "__main__":
    main()
