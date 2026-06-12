#!/usr/bin/env python3
"""generate_slugs.py — genera el campo `slug` en items.jsonl para la ruta /item/[slug].

Prioridad de derivación (por cluster):
  1. cluster_key = "isbn:{isbn13}"  →  "isbn-{isbn13}"
  2. edition_key + volume           →  "{edition_key}-{vol}"
  3. edition_key solo (sin volumen) →  "{edition_key}"
  4. sin edition_key + isbn field   →  "isbn-{isbn}"
  5. fallback                       →  "item-{sha1(url)[:12]}"

Colisiones entre clusters distintos se resuelven con sufijos -b/-c (el más
antiguo, por detected_at, conserva el slug limpio).

Idempotente: si el slug ya está asignado y edition_key/volume no cambiaron,
el item se saltea. Solo actualiza cuando slug está vacío o cuando el slug
derivado difiere del almacenado.

Uso:
    python scripts/retrofit/generate_slugs.py              # asigna/actualiza todo
    python scripts/retrofit/generate_slugs.py --dry-run    # preview sin escribir
    python scripts/retrofit/generate_slugs.py --only-missing   # solo items sin slug
    python scripts/retrofit/generate_slugs.py --verbose    # log de cada asignación
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from manga_watch import FULLWIDTH_DIGITS_TABLE, backup_and_rotate  # type: ignore


_SLUG_VALID_RE = re.compile(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$')

# Strips leading volume markers (Vol., Tome, #, 第, etc.)
_VOL_PREFIX_RE = re.compile(
    r'^(?:vol\.?\s*|tome\s*|tomo\s*|第\s*|#\s*|n[o°]\.?\s*|巻?\s*)',
    re.IGNORECASE,
)
# Strips trailing JP volume markers
_VOL_SUFFIX_RE = re.compile(r'[巻冊号]$')
# Full-width digits → ASCII: tabla única importada de manga_watch (gotcha #82)
_FULLWIDTH_TABLE = FULLWIDTH_DIGITS_TABLE
# JP parentheses / brackets
_JP_BRACKETS_RE = re.compile(r'[（）【】「」『』]')


def _format_volume(vol: str) -> str:
    """Converts a volume string to a slug-safe suffix.

    Examples:
        "42"      → "42"
        "42.0"    → "42"
        "1.5"     → "1-5"
        "10-12"   → "10-12"
        "第42巻"   → "42"
        "Vol. 42" → "42"
    """
    v = (vol or "").strip()
    if not v:
        return ""
    v = v.translate(_FULLWIDTH_TABLE)
    v = _JP_BRACKETS_RE.sub("", v)
    v = _VOL_SUFFIX_RE.sub("", v)
    v = _VOL_PREFIX_RE.sub("", v).strip()
    if not v:
        return ""
    # Try numeric: strip trailing ".0", replace "." with "-" for decimals
    try:
        f = float(v)
        if f == int(f):
            return str(int(f))
        return str(f).replace(".", "-")
    except ValueError:
        pass
    # Already slug-safe (e.g. "10-12") — just lowercase + replace non-alnum
    safe = re.sub(r"[^a-z0-9]+", "-", v.lower()).strip("-")
    return safe or ""


def _sha1_short(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _sanitize(s: str) -> str:
    """Ensures a string is a valid slug (lowercase, alnum + hyphens, no edges)."""
    s = re.sub(r"[^a-z0-9-]", "-", s.lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _derive_base_slug(item: dict) -> str:
    """Derives the candidate slug for a cluster representative (before collision resolution)."""
    cluster_key = (item.get("cluster_key") or "").strip()
    edition_key = (item.get("edition_key") or "").strip()
    volume = (item.get("volume") or "").strip()
    isbn = (item.get("isbn") or "").strip()
    url = (item.get("url") or "").strip()

    # Rule 1: isbn cluster key → "isbn-{isbn13}"
    # Lowercase handles ISBN-10 check digit 'X'. Strip non-alnum handles edge cases
    # like full-width colons in cluster keys (e.g. isbn:： 9784847037412).
    if cluster_key.startswith("isbn:"):
        isbn13 = re.sub(r"[^a-z0-9]", "", cluster_key[5:].strip().lower())
        if isbn13:
            return f"isbn-{isbn13}"

    # Rule 2: edition_key + volume → "{edition_key}-{vol}"
    if edition_key and volume:
        vol_fmt = _format_volume(volume)
        if vol_fmt:
            candidate = f"{edition_key}-{vol_fmt}"
            if _SLUG_VALID_RE.match(candidate):
                return candidate
            # Sanitize just in case
            sanitized = _sanitize(candidate)
            if sanitized and _SLUG_VALID_RE.match(sanitized):
                return sanitized

    # Rule 3: edition_key alone
    if edition_key:
        if _SLUG_VALID_RE.match(edition_key):
            return edition_key
        sanitized = _sanitize(edition_key)
        if sanitized and _SLUG_VALID_RE.match(sanitized):
            return sanitized

    # Rule 4: no edition_key but has isbn field
    if isbn:
        isbn_clean = re.sub(r"[^0-9x]", "", isbn.lower())
        if isbn_clean and len(isbn_clean) >= 2:
            return f"isbn-{isbn_clean}"

    # Rule 5: fallback hash
    if url:
        return f"item-{_sha1_short(url)}"

    return f"item-{_sha1_short(json.dumps(item, sort_keys=True))}"


def _best_representative(cluster_items: list[dict]) -> dict:
    """Returns the most 'canonical' item from a cluster for slug derivation."""
    def _rank(it: dict) -> tuple:
        return (
            bool(it.get("edition_key")),
            bool(it.get("volume")),
            bool(it.get("isbn")),
            it.get("score") or 0,
        )
    return max(cluster_items, key=_rank)


def _oldest_detected_at(cluster_items: list[dict]) -> str:
    dates = [(it.get("detected_at") or "9999-99-99") for it in cluster_items]
    return min(dates)


# Collision suffix alphabet: a→b→c… (skip 'a' so clean slug is implied)
_COLLISION_SUFFIXES = list("bcdefghijklmnopqrstuvwxyz") + [f"{i}" for i in range(2, 50)]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", default="data/items.jsonl")
    p.add_argument("--output", default="data/items.jsonl")
    p.add_argument("--dry-run", action="store_true",
                   help="Imprime cambios sin escribir a items.jsonl.")
    p.add_argument("--only-missing", action="store_true",
                   help="Solo procesa items sin slug (modo incremental rápido).")
    p.add_argument("--verbose", action="store_true",
                   help="Imprime cada asignación de slug.")
    args = p.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"[ERROR] no existe {src}", file=sys.stderr)
        return 1

    # ------------------------------------------------------------------ #
    # 1. Read items                                                        #
    # ------------------------------------------------------------------ #
    raw_lines: list[str] = []
    items: list[dict | None] = []
    for raw in src.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        raw_lines.append(raw)
        try:
            items.append(json.loads(raw))
        except json.JSONDecodeError:
            items.append(None)

    # ------------------------------------------------------------------ #
    # 2. Group by cluster_key                                             #
    # ------------------------------------------------------------------ #
    clusters: dict[str, list[int]] = defaultdict(list)
    for i, item in enumerate(items):
        if item is None:
            continue
        ck = item.get("cluster_key") or f"__no_cluster_{i}"
        clusters[ck].append(i)

    # ------------------------------------------------------------------ #
    # 3. Compute base slug + metadata per cluster                         #
    # ------------------------------------------------------------------ #
    cluster_base: dict[str, str] = {}
    cluster_oldest: dict[str, str] = {}
    cluster_existing_slug: dict[str, str] = {}

    for ck, indices in clusters.items():
        cluster_items = [items[i] for i in indices if items[i] is not None]
        if not cluster_items:
            continue
        rep = _best_representative(cluster_items)
        cluster_base[ck] = _derive_base_slug(rep)
        cluster_oldest[ck] = _oldest_detected_at(cluster_items)

        # existing slug: use the one already stored (all rows in cluster should
        # agree; take the first non-empty)
        for it in cluster_items:
            s = (it.get("slug") or "").strip()
            if s:
                cluster_existing_slug[ck] = s
                break

    # ------------------------------------------------------------------ #
    # 4. Separate clusters: "already slugged" vs "to assign"             #
    # ------------------------------------------------------------------ #
    if args.only_missing:
        to_assign = {ck for ck in clusters if ck not in cluster_existing_slug}
        reserved_slugs = set(cluster_existing_slug.values())
    else:
        # Default: recompute all — existing slug vs derived slug comparison
        # happens later per cluster.
        to_assign = set(clusters.keys())
        reserved_slugs: set[str] = set()

    # ------------------------------------------------------------------ #
    # 5. Resolve collisions among "to_assign" clusters                   #
    # ------------------------------------------------------------------ #
    # Group clusters by their base slug
    base_to_clusters: dict[str, list[str]] = defaultdict(list)
    for ck in to_assign:
        base = cluster_base.get(ck)
        if base:
            base_to_clusters[base].append(ck)

    cluster_final_slug: dict[str, str] = dict(cluster_existing_slug)  # start from preserved

    collision_count = 0
    for base_slug, ck_list in base_to_clusters.items():
        # Sort by detected_at ascending: oldest gets the clean slug
        ck_list_sorted = sorted(
            ck_list, key=lambda ck: cluster_oldest.get(ck, "9999-99-99")
        )

        # Find a non-colliding slug for each cluster in the group
        used_in_group: set[str] = set()
        for ck in ck_list_sorted:
            # Try clean slug first
            candidate = base_slug
            if candidate not in reserved_slugs and candidate not in used_in_group:
                cluster_final_slug[ck] = candidate
                used_in_group.add(candidate)
                continue
            # Try suffixes -b, -c, …
            assigned = False
            for suffix in _COLLISION_SUFFIXES:
                candidate = f"{base_slug}-{suffix}"
                if candidate not in reserved_slugs and candidate not in used_in_group:
                    cluster_final_slug[ck] = candidate
                    used_in_group.add(candidate)
                    assigned = True
                    break
            if not assigned:
                # Very unlikely: fallback to hash
                cluster_final_slug[ck] = f"item-{_sha1_short(ck)}"

        if len(ck_list) > 1:
            collision_count += len(ck_list)
            print(
                f"[WARN] Colisión en slug '{base_slug}' — "
                f"{len(ck_list)} clusters: "
                + ", ".join(repr(ck) for ck in ck_list_sorted[:3])
                + ("…" if len(ck_list) > 3 else "")
            )

    # ------------------------------------------------------------------ #
    # 6. Assign final slugs to items                                      #
    # ------------------------------------------------------------------ #
    updates = 0
    skipped_unchanged = 0
    skipped_only_missing = 0
    new_items: list[dict | None] = []

    for i, item in enumerate(items):
        if item is None:
            new_items.append(item)
            continue

        ck = item.get("cluster_key") or f"__no_cluster_{i}"
        new_slug = cluster_final_slug.get(ck)
        existing = (item.get("slug") or "").strip()

        # Item is outside any cluster we computed (edge case)
        if new_slug is None:
            new_items.append(item)
            skipped_unchanged += 1
            continue

        # --only-missing: skip clusters we decided to preserve
        if args.only_missing and ck not in to_assign:
            new_items.append(item)
            skipped_only_missing += 1
            continue

        # No change needed
        if existing == new_slug:
            new_items.append(item)
            skipped_unchanged += 1
            continue

        # Update
        updated = dict(item)
        updated["slug"] = new_slug
        new_items.append(updated)
        updates += 1

        if args.verbose:
            old_label = existing or "(vacío)"
            print(f"  {new_slug:50s}  ← {item.get('title', '')[:55]}  [{old_label}]")

    # ------------------------------------------------------------------ #
    # 7. Summary + write                                                  #
    # ------------------------------------------------------------------ #
    total = len(new_items)
    print(f"[INFO] {total} items procesados")
    print(f"[INFO] Slugs asignados/actualizados: {updates}")
    if args.only_missing:
        print(f"[INFO] Saltados (ya tenían slug):    {skipped_only_missing}")
    print(f"[INFO] Sin cambios:                  {skipped_unchanged}")
    if collision_count:
        print(f"[WARN] Colisiones resueltas:         {collision_count} clusters afectados")

    if args.dry_run:
        print("\n[DRY-RUN] No se escribió ningún archivo.")
        return 0

    if updates == 0:
        print("\n[OK] Nada que actualizar. items.jsonl ya está al día.")
        return 0

    dst = Path(args.output)
    if dst.exists() and dst == src:
        backup = backup_and_rotate(dst, "generate-slugs")
        print(f"\n[OK] Backup en {backup}")

    out_lines = [
        json.dumps(it, ensure_ascii=False) if it is not None else raw_lines[i]
        for i, it in enumerate(new_items)
    ]
    dst.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"[OK] Escribí {dst} con {updates} slugs actualizados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
