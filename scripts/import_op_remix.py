#!/usr/bin/env python3
"""Import One Piece Shueisha Jump Remix series (2 editions).

Edition 1 — One Piece Remix (集英社ジャンプリミックス)
  24 volumes, arc-based compilations, convenience store format.
  Released biweekly Sep 2021 – Aug 2022. ~¥550/vol.
  Image source: Amazon CDN (LZZZZZZZ).

Edition 2 — One Piece Jump Character Remix (JUMPキャラクターREMIX)
  11 volumes, character-focused anthologies.
  Released Jul 2024 – Mar 2025. ¥880/vol.
  Each copy included bonus stickers + double-sided mini-poster.
  Image source: Shueisha CDN (dosbg3xlm0x1t.cloudfront.net).

ISBNs verified via check-digit calculation; Vol 16 Remix corrected
(agent error: 9784081150583 → 9784081150588).
Idempotent on (edition_key, volume). Atomic write with backup.
"""
import json
import sys
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests
from manga_watch import backup_and_rotate, append_jsonl
from image_store import download_image

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.jsonl"
IMAGES_DIR = ROOT / "data" / "images"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "manga-watch-personal/0.2"})


def isbn13_to_isbn10(isbn13: str) -> str:
    core = isbn13[3:12]
    s = sum((10 - i) * int(d) for i, d in enumerate(core))
    check = (11 - (s % 11)) % 11
    return core + ("X" if check == 10 else str(check))


def shueisha_url(isbn13: str) -> str:
    d = isbn13
    dashed = f"{d[:3]}-{d[3]}-{d[4:6]}-{d[6:12]}-{d[12]}"
    return f"https://www.shueisha.co.jp/books/items/contents.html?isbn={dashed}"


def amazon_cover_large(isbn13: str) -> str:
    isbn10 = isbn13_to_isbn10(isbn13)
    return f"https://images-na.ssl-images-amazon.com/images/P/{isbn10}.01.LZZZZZZZ.jpg"


def shueisha_cover(isbn13: str) -> str:
    return f"https://dosbg3xlm0x1t.cloudfront.net/images/items/{isbn13}/1200/{isbn13}.jpg"


NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()

# ---------------------------------------------------------------------------
# Volume data
# ---------------------------------------------------------------------------

REMIX_VOLS = [
    # (vol, isbn13, release_date, subtitle_jp, subtitle_en)
    (1,  "9784081150434", "2021-09-03", "東の海編 VS.道化のバギー",           "East Blue — VS. Buggy the Clown"),
    (2,  "9784081150441", "2021-09-17", "東の海編 VS.百計のクロ",             "East Blue — VS. Captain Kuro"),
    (3,  "9784081150458", "2021-10-01", "東の海編 VS.首領・クリーク",         "East Blue — VS. Don Krieg"),
    (4,  "9784081150465", "2021-10-15", "東の海編 VS.魚人アーロン",           "East Blue — VS. Arlong"),
    (5,  "9784081150472", "2021-10-29", "アラバスタ編 VS.バロックワークス 1", "Alabasta — VS. Baroque Works 1"),
    (6,  "9784081150489", "2021-11-12", "アラバスタ編 VS.ブリキング海賊団",   "Alabasta — VS. Tin Tyrant Pirates"),
    (7,  "9784081150496", "2021-11-26", "アラバスタ編 VS.バロックワークス 2", "Alabasta — VS. Baroque Works 2"),
    (8,  "9784081150502", "2021-12-10", "アラバスタ編 VS.バロックワークス 3", "Alabasta — VS. Baroque Works 3"),
    (9,  "9784081150519", "2021-12-24", "アラバスタ編 VS.サー・クロコダイル", "Alabasta — VS. Sir Crocodile"),
    (10, "9784081150526", "2022-01-14", "空島編 VS.ベラミー海賊団",           "Skypiea — VS. Bellamy Pirates"),
    (11, "9784081150533", "2022-01-28", "空島編 VS.神の四神官",               "Skypiea — VS. God's Four Priests"),
    (12, "9784081150540", "2022-02-10", "空島編 VS.神・エネル",               "Skypiea — VS. God Enel"),
    (13, "9784081150557", "2022-02-25", "ウォーターセブン編 VS.フォクシー海賊団", "Water Seven — VS. Foxy Pirates"),
    (14, "9784081150564", "2022-03-11", "ウォーターセブン編 VS.フランキー一家", "Water Seven — VS. Franky Family"),
    (15, "9784081150571", "2022-03-25", "ウォーターセブン編 VS.CP9",          "Water Seven — VS. CP9"),
    (16, "9784081150588", "2022-04-08", "ウォーターセブン編 VS.CP9（2）",     "Water Seven — VS. CP9 (2)"),
    (17, "9784081150595", "2022-04-22", "ウォーターセブン編 VS.CP9（3）",     "Water Seven — VS. CP9 (3)"),
    (18, "9784081150601", "2022-05-13", "ウォーターセブン編 VS.ロブ・ルッチ", "Water Seven — VS. Rob Lucci"),
    (19, "9784081150618", "2022-05-27", "スリラーバーク編 VS.スリラーバーク海賊団", "Thriller Bark — VS. Thriller Bark Pirates"),
    (20, "9784081150625", "2022-06-10", "スリラーバーク編 VS.ゲッコー・モリア", "Thriller Bark — VS. Gecko Moria"),
    (21, "9784081150632", "2022-06-24", "頂上戦争 VS.海軍",                   "Marineford — VS. Marines"),
    (22, "9784081150649", "2022-07-08", "頂上戦争編 VS.監獄署長マゼラン",     "Marineford — VS. Chief Warden Magellan"),
    (23, "9784081150656", "2022-07-22", "頂上戦争編 VS.海軍・王下七武海 1",   "Marineford — VS. Marines & Warlords 1"),
    (24, "9784081150663", "2022-08-05", "頂上戦争編 VS.海軍・王下七武海 2",   "Marineford — VS. Marines & Warlords 2"),
]

CHAR_REMIX_VOLS = [
    # (vol, isbn13, release_date, character_jp, character_en)
    (1,  "9784081152230", "2024-07-04", "モンキー・D・ルフィ 1",     "Monkey D. Luffy 1"),
    (2,  "9784081152247", "2024-07-04", "モンキー・D・ルフィ 2",     "Monkey D. Luffy 2"),
    (3,  "9784081152254", "2024-08-02", "ロロノア・ゾロ",             "Roronoa Zoro"),
    (4,  "9784081152261", "2024-08-02", "ナミ",                       "Nami"),
    (5,  "9784081152278", "2024-09-04", "ウソップ",                   "Usopp"),
    (6,  "9784081152285", "2024-09-04", "サンジ",                     "Sanji"),
    (7,  "9784081152292", "2024-10-04", "トニートニー・チョッパー",   "Tony Tony Chopper"),
    (8,  "9784081152308", "2024-10-04", "ニコ・ロビン",               "Nico Robin"),
    (9,  "9784081152315", "2024-11-01", "フランキー",                 "Franky"),
    (10, "9784081152322", "2024-11-01", "ブルック",                   "Brook"),
    (11, "9784081152544", "2025-03-04", "ポートガス・D・エース",     "Portgas D. Ace"),
]


def build_remix_item(vol, isbn13, release_date, subtitle_jp, subtitle_en):
    edition_key = "one-piece-shueisha-remix"
    slug = f"{edition_key}-{vol}"
    url = shueisha_url(isbn13)
    image_url = amazon_cover_large(isbn13)

    # Download image
    local_name = download_image(image_url, IMAGES_DIR, SESSION)
    if not local_name:
        print(f"  ⚠ Vol {vol}: image download failed, continuing without local")

    title = f"One Piece Remix {vol}"
    title_original = f"ONE PIECE {subtitle_jp}（集英社ジャンプリミックス）"
    description = (
        f"Shueisha Jump Remix arc compilation. "
        f"{subtitle_en}. "
        f"B6 format, sold at convenience stores (2021–2022)."
    )

    item = {
        "url": url,
        "title": title,
        "title_original": title_original,
        "description": description,
        "description_es": "",
        "isbn": isbn13,
        "series_key": "one-piece",
        "series_display": "One Piece",
        "edition_key": edition_key,
        "edition_display": "Remix (Shueisha)",
        "volume": str(vol),
        "publisher": "Shueisha",
        "country": "Japón",
        "language": "ja",
        "price": "¥ 550",
        "release_date": release_date,
        "signal_types": ["special_edition"],
        "score": 45,
        "product_type": "manga",
        "rarity": "rare",
        "source": "Research import (One Piece Jump Remix)",
        "source_class": "curated",
        "image_url": image_url,
        "image_local": local_name or "",
        "images": [{
            "url": image_url,
            "local": local_name or "",
            "kind": "gallery",
            "description": "",
        }],
        "extras": [],
        "cluster_key": f"edition:{edition_key}|{vol}",
        "slug": slug,
        "detected_at": NOW,
        "standardized_at": NOW,
        "sources": [{
            "name": "Research import (One Piece Jump Remix)",
            "url": url,
            "price": "¥ 550",
            "country": "Japón",
            "language": "ja",
            "publisher": "Shueisha",
            "image_url": image_url,
            "image_local": local_name or "",
            "release_date": release_date,
            "score": 45,
            "source_class": "curated",
            "stock_type": "",
            "detected_at": NOW,
        }],
    }
    return item


def build_char_remix_item(vol, isbn13, release_date, char_jp, char_en):
    edition_key = "one-piece-shueisha-character-remix"
    slug = f"{edition_key}-{vol}"
    url = shueisha_url(isbn13)
    image_url = shueisha_cover(isbn13)

    # Download image
    local_name = download_image(image_url, IMAGES_DIR, SESSION)
    if not local_name:
        print(f"  ⚠ Vol {vol} ({char_en}): image download failed")

    title = f"One Piece Character Remix {vol} — {char_en}"
    title_original = f"ONE PIECE JUMPキャラクターREMIX {char_jp}"
    description = (
        f"Character-focused manga anthology: {char_en}. "
        f"Includes bonus stickers and double-sided mini-poster. "
        f"Part of the JUMPキャラクターREMIX series (2024–2025)."
    )

    item = {
        "url": url,
        "title": title,
        "title_original": title_original,
        "description": description,
        "description_es": "",
        "isbn": isbn13,
        "series_key": "one-piece",
        "series_display": "One Piece",
        "edition_key": edition_key,
        "edition_display": "Jump Character Remix (Shueisha)",
        "volume": str(vol),
        "publisher": "Shueisha",
        "country": "Japón",
        "language": "ja",
        "price": "¥ 880",
        "release_date": release_date,
        "signal_types": ["special_edition", "bonus"],
        "score": 65,
        "product_type": "manga",
        "rarity": "rare",
        "source": "Research import (One Piece Jump Remix)",
        "source_class": "curated",
        "image_url": image_url,
        "image_local": local_name or "",
        "images": [{
            "url": image_url,
            "local": local_name or "",
            "kind": "gallery",
            "description": "",
        }],
        "extras": [],
        "cluster_key": f"edition:{edition_key}|{vol}",
        "slug": slug,
        "detected_at": NOW,
        "standardized_at": NOW,
        "sources": [{
            "name": "Research import (One Piece Jump Remix)",
            "url": url,
            "price": "¥ 880",
            "country": "Japón",
            "language": "ja",
            "publisher": "Shueisha",
            "image_url": image_url,
            "image_local": local_name or "",
            "release_date": release_date,
            "score": 65,
            "source_class": "curated",
            "stock_type": "",
            "detected_at": NOW,
        }],
    }
    return item


def main(dry_run: bool = False):
    print("=== One Piece Jump Remix import ===\n")

    # Backup first
    if not dry_run:
        backup_and_rotate(ITEMS, "import-op-remix")
        print("✓ Backup created\n")

    new_items = []

    print("--- One Piece Remix (24 vols) ---")
    for vol, isbn13, release_date, subtitle_jp, subtitle_en in REMIX_VOLS:
        item = build_remix_item(vol, isbn13, release_date, subtitle_jp, subtitle_en)
        local = item["image_local"]
        print(f"  Vol {vol:2d}: {isbn13} | img={local or '❌'}")
        new_items.append(item)

    print(f"\n--- One Piece Jump Character Remix (11 vols) ---")
    for vol, isbn13, release_date, char_jp, char_en in CHAR_REMIX_VOLS:
        item = build_char_remix_item(vol, isbn13, release_date, char_jp, char_en)
        local = item["image_local"]
        print(f"  Vol {vol:2d} ({char_en}): {isbn13} | img={local or '❌'}")
        new_items.append(item)

    print(f"\nTotal: {len(new_items)} items to ingest")

    if dry_run:
        print("\n[DRY RUN] Skipping write.")
        return

    # Ingest using append_jsonl
    before = sum(1 for _ in open(ITEMS)) if ITEMS.exists() else 0
    append_jsonl(ITEMS, new_items)
    after = sum(1 for _ in open(ITEMS)) if ITEMS.exists() else 0
    print(f"\n✓ Ingested: {len(new_items)} items → corpus {before} → {after} rows (+{after - before})")
    print("Done.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
