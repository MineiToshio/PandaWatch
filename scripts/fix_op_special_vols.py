#!/usr/bin/env python3
"""Fix & extend One Piece special volumes.

Changes:
  1. Vol 333 (Tokyo One Piece Tower 3rd Anniversary):
     Reclassify from 'theater-giveaway' → 'event' edition.

  2. Add Vol 794 (One Piece × Kyoto, Oct 2017):
     Event volume distributed with WSJ #45 / Oct 2017 collaboration.

  3. Add 6 Saikyo Jump appendix volumes (2017–2021):
     Bundled with specific Saikyo Jump magazine issues.

Idempotent. Atomic write (tmp + rename) with backup.
"""
import json
import sys
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests
from manga_watch import backup_and_rotate, append_jsonl, write_items_atomic
import image_store
from image_store import download_image
from op_series_guard import is_one_piece_title

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.jsonl"
IMAGES_DIR = ROOT / "data" / "images"
TMP = ITEMS.with_suffix(".tmp")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "manga-watch-personal/0.2"})

NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()

# ---------------------------------------------------------------------------
# Data for new / fixed items
# ---------------------------------------------------------------------------

# Vol 333 fix — just new metadata values, no new item
VOL_333_FIX = {
    "edition_key":     "one-piece-shueisha-event",
    "edition_display": "Event Volumes (Shueisha)",
    "cluster_key":     "edition:one-piece-shueisha-event|333",
    "slug":            "one-piece-shueisha-event-333",
    "description":     (
        "Event volume distributed free to visitors of Tokyo One Piece Tower "
        "(theme park inside Tokyo Tower) during its 3rd anniversary "
        "(March 9, 2018). Contains Oda × GReeeeN interview, park history, "
        "character designs, and One Piece Live Attraction info. 777 pages."
    ),
}

# New items to add via append_jsonl
NEW_ITEMS_DATA = [
    # ── Event volumes ──────────────────────────────────────────────────────
    {
        "url":            "https://onepiece.fandom.com/wiki/Volume_794",
        "title":          "One Piece Volume 794",
        "title_original": "ONE PIECE 巻七九四",
        "description":    (
            "Event volume distributed as an appendix with Weekly Shonen Jump "
            "Issue #45 (October 2017), tied to the One Piece 20th Anniversary "
            "× Kyoto collaboration (October 7–22, 2017). A guide/map to the "
            "Kyoto event with wanted posters of the Straw Hats. Road to Wano "
            "Country theme. Volume number 794 = start of the Heian period "
            "(former name of Kyoto: Heian-kyō)."
        ),
        "image_url":      "https://static.wikia.nocookie.net/onepiece/images/e/ea/One_Piece_Volume_794.png/revision/latest?cb=20210222021344",
        "edition_key":    "one-piece-shueisha-event",
        "edition_display":"Event Volumes (Shueisha)",
        "volume":         "794",
        "slug":           "one-piece-shueisha-event-794",
        "release_date":   "2017-10-01",
        "signal_types":   ["limited", "special_edition"],
        "score":          55,
        "rarity":         "super_rare",
    },
    # ── Saikyo Jump appendix volumes ───────────────────────────────────────
    {
        "url":            "https://onepiece.fandom.com/wiki/Volume_Strongest",
        "title":          "One Piece Volume Strongest",
        "title_original": "ONE PIECE 巻最強",
        "description":    (
            "Bundled with Saikyo Jump September 2017 issue. Celebrates "
            "One Piece's 20th anniversary (1997–2017). Features post-timeskip "
            "material with the Straw Hats' reunion at Sabaody."
        ),
        "image_url":      "https://static.wikia.nocookie.net/onepiece/images/a/aa/Volume_Strongest.png/revision/latest?cb=20240413165314",
        "edition_key":    "one-piece-shueisha-saikyo-jump",
        "edition_display":"Saikyo Jump Appendix (Shueisha)",
        "volume":         "1",
        "slug":           "one-piece-shueisha-saikyo-jump-1",
        "release_date":   "2017-08-04",
        "signal_types":   ["limited", "special_edition", "bonus"],
        "score":          60,
        "rarity":         "super_rare",
    },
    {
        "url":            "https://onepiece.fandom.com/wiki/Volume_Zoro",
        "title":          "One Piece Volume Zoro",
        "title_original": "ONE PIECE 巻ゾロ",
        "description":    (
            "Bundled with Saikyo Jump May 2018 issue. Two-page Roronoa Zoro "
            "character profile and two-page recap of Zoro's role in the story. "
            "Included a merchandise raffle (11 winners, notified June 2018)."
        ),
        "image_url":      "https://static.wikia.nocookie.net/onepiece/images/b/b3/Volume_Zoro.png/revision/latest?cb=20240127125227",
        "edition_key":    "one-piece-shueisha-saikyo-jump",
        "edition_display":"Saikyo Jump Appendix (Shueisha)",
        "volume":         "2",
        "slug":           "one-piece-shueisha-saikyo-jump-2",
        "release_date":   "2018-04-04",
        "signal_types":   ["limited", "special_edition", "bonus"],
        "score":          60,
        "rarity":         "super_rare",
    },
    {
        "url":            "https://onepiece.fandom.com/wiki/Volume_Spin-Off",
        "title":          "One Piece Volume Spin-Off",
        "title_original": "ONE PIECE 巻スピンオフ",
        "description":    (
            "Bundled with Saikyo Jump November 2018 issue. Contains: "
            "Fischer's × One Piece crossover, Kobiyama crossover, One Piece "
            "in Love, One Piece Party contributions, and Chin Piece Extra "
            "Edition. The only special volume to introduce content later "
            "compiled into official tankōbon volumes."
        ),
        "image_url":      "https://static.wikia.nocookie.net/onepiece/images/c/cd/Volume_Spin-Off.png/revision/latest?cb=20240927015758",
        "edition_key":    "one-piece-shueisha-saikyo-jump",
        "edition_display":"Saikyo Jump Appendix (Shueisha)",
        "volume":         "3",
        "slug":           "one-piece-shueisha-saikyo-jump-3",
        "release_date":   "2018-10-04",
        "signal_types":   ["limited", "special_edition", "bonus"],
        "score":          60,
        "rarity":         "super_rare",
    },
    {
        "url":            "https://onepiece.fandom.com/wiki/Volume_Wano_Country",
        "title":          "One Piece Volume Wano Country",
        "title_original": "ONE PIECE 巻ワノ国",
        "description":    (
            "Bundled with Saikyo Jump July 2019 issue. Celebrates the beginning "
            "of the Wano Country Arc. Contains Chapters 910, 911, and 912 in "
            "full color: Luffy arrives at Wano, meets Tama, reunites with Zoro, "
            "and faces Hawkins."
        ),
        "image_url":      "https://static.wikia.nocookie.net/onepiece/images/e/ed/Volume_Wano_Country.png/revision/latest?cb=20240127125518",
        "edition_key":    "one-piece-shueisha-saikyo-jump",
        "edition_display":"Saikyo Jump Appendix (Shueisha)",
        "volume":         "4",
        "slug":           "one-piece-shueisha-saikyo-jump-4",
        "release_date":   "2019-06-04",
        "signal_types":   ["limited", "special_edition", "bonus"],
        "score":          60,
        "rarity":         "super_rare",
    },
    {
        "url":            "https://onepiece.fandom.com/wiki/Volume_Stampede",
        "title":          "One Piece Volume Stampede",
        "title_original": "ONE PIECE 巻スタンピード",
        "description":    (
            "Bundled with Saikyo Jump September 2019 issue. Character profiles "
            "for One Piece: Stampede movie characters: Douglas Bullet, Buena "
            "Festa, Donald Moderate, and Ann. Tie-in with the theatrical "
            "release of One Piece: Stampede (August 9, 2019)."
        ),
        "image_url":      "https://static.wikia.nocookie.net/onepiece/images/c/c7/Volume_Stampede.png/revision/latest?cb=20240210083516",
        "edition_key":    "one-piece-shueisha-saikyo-jump",
        "edition_display":"Saikyo Jump Appendix (Shueisha)",
        "volume":         "5",
        "slug":           "one-piece-shueisha-saikyo-jump-5",
        "release_date":   "2019-08-04",
        "signal_types":   ["limited", "special_edition", "bonus"],
        "score":          60,
        "rarity":         "super_rare",
    },
    {
        "url":            "https://onepiece.fandom.com/wiki/Volume_Chopper",
        "title":          "One Piece Volume Chopper",
        "title_original": "ONE PIECE 巻チョッパー",
        "description":    (
            "Bundled with Saikyo Jump October 2021 issue. Contains Chapters "
            "151, 152, and 153 printed in full color — covering Tony Tony "
            "Chopper joining the Straw Hat Pirates."
        ),
        "image_url":      "https://static.wikia.nocookie.net/onepiece/images/e/eb/Volume_Chopper.png/revision/latest?cb=20220829085933",
        "edition_key":    "one-piece-shueisha-saikyo-jump",
        "edition_display":"Saikyo Jump Appendix (Shueisha)",
        "volume":         "6",
        "slug":           "one-piece-shueisha-saikyo-jump-6",
        "release_date":   "2021-09-04",
        "signal_types":   ["limited", "special_edition", "bonus"],
        "score":          60,
        "rarity":         "super_rare",
    },
]

# Common fields shared by all new items
COMMON = {
    "isbn":           "",
    "series_key":     "one-piece",
    "series_display": "One Piece",
    "publisher":      "Shueisha",
    "country":        "Japón",
    "language":       "ja",
    "product_type":   "manga",
    "extras":         [],
    "description_es": "",
    "source":         "Research import (One Piece special volumes)",
    "source_class":   "curated",
    "detected_at":    NOW,
    "standardized_at":NOW,
}


def build_item(d: dict) -> dict:
    item = {**COMMON, **d}
    # `image_url` en los datos seed es solo el insumo para la portada, no un campo
    # top-level del item. La portada es images[0] (única fuente de verdad).
    image_url = item.pop("image_url", "")
    # Download image
    local = download_image(image_url, IMAGES_DIR, SESSION)
    item["images"] = [{
        "url":         image_url,
        "local":       local or "",
        "kind":        "gallery",
        "description": "",
    }]
    item["cluster_key"] = f"edition:{item['edition_key']}|{item['volume']}"
    item["sources"] = [{
        "name":        item["source"],
        "url":         item["url"],
        "country":     item["country"],
        "language":    item["language"],
        "publisher":   item["publisher"],
        "image_url":   image_url,
        "image_local": local or "",
        "release_date":item.get("release_date", ""),
        "score":       item.get("score", 50),
        "source_class":item["source_class"],
        "stock_type":  "",
        "detected_at": NOW,
    }]
    return item


def fix_vol_333(items: list[dict]) -> bool:
    """Reclassify Vol 333 from theater-giveaway to event in-place."""
    for it in items:
        if (it.get("edition_key") == "one-piece-shueisha-theater-giveaway"
                and it.get("volume") == "333"):
            it.update(VOL_333_FIX)
            # Also patch standardized_at so the change sticks
            it["standardized_at"] = NOW
            # Update sources[] edition fields if stored there
            for src in it.get("sources", []):
                src.setdefault("edition_key", it["edition_key"])
            print("  ✓ Vol 333 reclassified → one-piece-shueisha-event")
            return True
    print("  ⚠ Vol 333 not found or already fixed")
    return False


def main(dry_run: bool = False):
    print("=== One Piece special volumes fix & extend ===\n")

    if not dry_run:
        backup_and_rotate(ITEMS, "fix-op-special-vols")
        print("✓ Backup created\n")

    # Load corpus
    items = [json.loads(l) for l in open(ITEMS)]
    before = len(items)

    # 1. Fix Vol 333 in-place
    print("--- Step 1: Fix Vol 333 classification ---")
    fix_vol_333(items)

    if not dry_run:
        write_items_atomic(ITEMS, items)
        print("  ✓ Written to disk\n")

    # 2. Build and ingest new items
    print("--- Step 2: Add Vol 794 (Event) + 6 Saikyo Jump vols ---")
    new_items = []
    for d in NEW_ITEMS_DATA:
        item = build_item(d)
        local = image_store.cover_local(item)
        # Guarda anti-contaminación (WO-2 GRUPO 3, 2026-07-07): rechaza
        # cualquier item cuyo título no matchee la serie objetivo antes de
        # escribirlo (ver op_series_guard.py — mismo bug de fondo que coló
        # 地獄楽/RURIDRAGON/etc. a través de import_op_remix.py).
        if not is_one_piece_title(item.get("title", ""), item.get("title_original", "")):
            print(f"  ⚠ REJECTED (no matchea serie One Piece): {item['title']!r}")
            continue
        print(f"  {item['title']:50s} | img={'✓ ' + local if local else '❌'}")
        new_items.append(item)

    if not dry_run:
        append_jsonl(ITEMS, new_items)
        after = sum(1 for _ in open(ITEMS))
        print(f"\n✓ Corpus: {before} → {after} rows (+{after - before} new)")
    else:
        print(f"\n[DRY RUN] Would add {len(new_items)} items.")

    print("Done.")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
