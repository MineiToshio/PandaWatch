#!/usr/bin/env python3
"""
One-off dedup for known ISBN duplicate cases:
 1. Soul Eater Perfect Edition US: zero-padded volumes (|01, |02…) duplicated as (|1, |2…)
 2. Fire Force Box Set 2: kodansha-us-boxset-us|7-11 duplicated as kodansha-boxset-us|2
 3. Hitorijime My Hero Box Set 2: kodansha-us-boxset-us|7-12 duplicated as kodansha-boxset-us|2

Strategy:
 - Soul Eater: remove zero-padded duplicates (keep |1, |2, … — simpler canonical form)
 - Fire Force / Hitorijime: remove the |vol-range version, keep the |box-number version
   (consistent with Box Set 1 which was already merged under kodansha-boxset-us|1)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ITEMS = ROOT / "data" / "items.jsonl"

# cluster_keys to DROP (duplicates)
KEYS_TO_REMOVE = {
    # Soul Eater zero-padded
    "edition:soul-eater-squareenix-perfect-us|01",
    "edition:soul-eater-squareenix-perfect-us|02",
    "edition:soul-eater-squareenix-perfect-us|03",
    "edition:soul-eater-squareenix-perfect-us|04",
    "edition:soul-eater-squareenix-perfect-us|05",
    "edition:soul-eater-squareenix-perfect-us|06",
    # Fire Force Box Set 2 (vol-range variant)
    "edition:fire-force-kodansha-us-boxset-us|7-11",
    # Hitorijime Box Set 2 (vol-range variant)
    "edition:hitorijime-my-hero-kodansha-us-boxset-us|7-12",
}

dry_run = "--dry-run" in sys.argv

items = [json.loads(l) for l in ITEMS.open() if l.strip()]

kept, removed = [], []
for it in items:
    ck = it.get("cluster_key", "")
    if ck in KEYS_TO_REMOVE:
        removed.append(it)
    else:
        kept.append(it)

print(f"Items total: {len(items)}")
print(f"To remove:   {len(removed)}")
print(f"To keep:     {len(kept)}")
print()
for it in removed:
    print(f"  REMOVE  {it['cluster_key']}  isbn={it.get('isbn','')}  title={it.get('title','')[:50]}")

if dry_run:
    print("\n[dry-run] No changes written.")
    sys.exit(0)

import sys as _sys
_sys.path.insert(0, str(ROOT))
try:
    from manga_watch import backup_and_rotate, write_items_atomic  # noqa: E402
except ImportError:
    from scripts.manga_watch import backup_and_rotate, write_items_atomic  # noqa: E402
backup_and_rotate(ITEMS, "dedup-isbn")

write_items_atomic(ITEMS, kept)
print(f"\n✅ Wrote {len(kept)} items (removed {len(removed)}).")
