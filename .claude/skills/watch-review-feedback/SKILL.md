---
name: watch-review-feedback
description: Analyze items in data/feedback.jsonl that the user flagged via the 👎 dashboard button. Each entry already contains the full item data plus the user's reason. Categorize each feedback (filter issue vs. data quality issue), propose concrete fixes, apply approved changes with tests, run the relevant retrofit scripts, and finally truncate data/feedback.jsonl. Invoke whenever data/feedback.jsonl has entries, or when the user says they want to review feedback or improve the scraper/data.
argument-hint: "[--dry-run]"
---

# Review feedback and improve catalog quality

You are reviewing items the user flagged via the 👎 button. Each row in `data/feedback.jsonl` is a full item record (all fields from `items.jsonl`) plus `reason` and `submitted_at`. The item was **not removed** from the catalog — it is still visible. Your job: understand what's wrong, categorize it, propose a fix, apply approved changes, and close the loop by truncating the queue.

## Step 0 — Bail early if the queue is empty

```python
import json
rows = []
try:
    with open('data/feedback.jsonl', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
except FileNotFoundError:
    pass
print(f"{len(rows)} feedback items to review")
```

If 0 items → report "no feedback in queue" and stop.

## Step 1 — Load and display the feedback queue

`feedback.jsonl` already contains all item fields — no JOIN needed.

```python
import json
from collections import defaultdict

with open('data/feedback.jsonl', encoding='utf-8') as f:
    rows = [json.loads(l) for l in f if l.strip()]

# Dedupe: if the same cluster has multiple feedback entries, pick the latest
seen_clusters = {}
for r in rows:
    ck = r.get('cluster_key') or r.get('url')
    # Keep latest by submitted_at
    if ck not in seen_clusters or r.get('submitted_at','') > seen_clusters[ck].get('submitted_at',''):
        seen_clusters[ck] = r

items = list(seen_clusters.values())

for i, it in enumerate(items, 1):
    print(f"\n[{i}] {it.get('title','?')}")
    print(f"    source        : {it.get('source','?')}")
    print(f"    url           : {it.get('url','?')[:80]}")
    print(f"    score         : {it.get('score','?')}")
    print(f"    signal_types  : {it.get('signal_types','?')}")
    print(f"    product_type  : {it.get('product_type','?')}")
    print(f"    publisher     : {it.get('publisher','?')}")
    print(f"    country       : {it.get('country','?')}")
    print(f"    series_key    : {it.get('series_key','?')}")
    print(f"    edition_key   : {it.get('edition_key','?')}")
    print(f"    cover         : {((it.get('images') or [{}])[0].get('url') or '?')[:80]}")
    print(f"    reason        : {it.get('reason','?')}")
    print(f"    submitted_at  : {it.get('submitted_at','?')}")
```

## Step 2 — Categorize each item

For each deduplicated item, classify the feedback using the taxonomy below. Read `reason` first — it often tells you exactly what's wrong. Then look at `signal_types`, `source`, `publisher`, the cover (`images[0]`), and `url` to confirm.

### Taxonomy

#### Filter / catalog issues (fix target: scraper code or sources.yml)

| Category | Description | Fix target |
|---|---|---|
| **A: non_manga_merch** | Merchandise, figures, bookends, prints, statues, DVDs, games, t-shirts | `_NON_MANGA_HARD` in `manga_watch.py` |
| **B: trading_cards** | Sticker albums, trading cards, panini figuritas | `_NON_MANGA_HARD` |
| **C: news_blog_post** | News article, blog post, announcement, "X reveals", listicle | `_NON_MANGA_HARD` news-family patterns |
| **D: regular_edition** | Regular tomo, not a special/limited/variant — false signal made it pass | Fix `is_collectible_edition` or remove false signal |
| **E: source_noise** | The entire source is too noisy (most items from it are wrong) | `purity: mixed` in `sources.yml`, or disable source |
| **F: western_comic** | Marvel, DC, Euro BD, superhero comics — not manga | `data/comics_blacklist.yml` |
| **G: light_novel** | Pure light novel without manga content | `is_pure_novel` in `manga_watch.py` |
| **H: user_preference** | Technically valid special edition, but user doesn't want it in their catalog | No code change — document and skip |
| **I: false_signal** | A signal fired incorrectly (e.g., `lore_edition` from a generic word) | Fix `KEYWORD_RULES` or `_GENERIC_X_EDITION_PATTERN` exclusions |
| **J: wrong_source_config** | Item was fetched because selectors are too broad | Tighten selectors in `sources.yml` |

#### Data quality issues (fix target: data fields, not scraper logic)

| Category | Description | Fix target |
|---|---|---|
| **K: wrong_image** | Cover is wrong item, wrong edition, low quality, or still a placeholder | `backfill_metadata.py --only image_url`, `fetch_better_covers.py`, or manual fix |
| **L: wrong_metadata** | Author, price, ISBN, or description is incorrect or missing | `backfill_metadata.py --only <field>` or manual fix |
| **M: wrong_classification** | `series_key`, `edition_key`, or `volume` is misassigned | Manual edit of item + possibly `series_aliases.yml` + `generate_slugs.py` |
| **N: bad_title** | Title contains scraping garbage (button text, prefix noise, truncation) | `clean_titles.py` or manual fix |

For each item, state:
- Category (A–N)
- Root cause explanation (1-2 sentences)
- Confidence: HIGH / MEDIUM / LOW
- Proposed fix (specific — quote the exact pattern, field, or value)

If the reason is ambiguous, look at `signal_types` + `source` + `url` to infer the most likely category.

## Step 3 — Scan corpus and consolidate proposals

### 3a — For filter issues (A–J, I): find more items matching each bad pattern

Before presenting proposals, **search `data/items.jsonl` for other items that already match the same bad pattern** — items the user hasn't flagged yet but that would be caught by the same fix.

```python
import json, re
from pathlib import Path

with open("data/items.jsonl", encoding="utf-8") as f:
    corpus = [json.loads(l) for l in f if l.strip()]

# A/B/C — keyword pattern
def corpus_keyword_hits(pattern_re, corpus):
    hits = []
    for item in corpus:
        text = " ".join(filter(None, [
            item.get("title", ""), item.get("title_original", ""),
            item.get("description", ""),
        ]))
        if pattern_re.search(text):
            hits.append(item)
    return hits

# D — regular_edition: items with no premium signals from the same source/publisher
def corpus_regular_edition_hits(source_name, publisher, corpus):
    PREMIUM = {"limited","deluxe","box_set","artbook","kanzenban",
                "lore_edition","variant_cover","hardcover","collector",
                "special_edition","bonus"}
    return [i for i in corpus
            if (i.get("source") == source_name or i.get("publisher") == publisher)
            and not (set(i.get("signal_types") or []) & PREMIUM)]

# E — source noise: all items from the noisy source
def corpus_source_hits(source_name, corpus):
    return [i for i in corpus if i.get("source") == source_name]

# F — western_comic: items from the same publisher
def corpus_publisher_hits(publisher, corpus):
    return [i for i in corpus if i.get("publisher","").lower() == publisher.lower()]

# I — false signal: items that have the specific signal type
def corpus_signal_hits(signal_name, corpus):
    return [i for i in corpus if signal_name in (i.get("signal_types") or [])]

# Print summary per proposal — adapt to actual proposals
# hits = corpus_keyword_hits(re.compile(r"\bbandana\b", re.I), corpus)
# print(f"'bandana' → {len(hits)} hits:")
# for h in hits[:5]: print(f"  - {h.get('title','?')} ({h.get('source','?')})")
```

### 3b — For data quality issues (K–N): show affected items directly

For K/L/M/N, show the specific item(s) from feedback and whether similar items in the corpus are likely affected by the same issue.

```python
# K — wrong_image: check corpus for items from same source whose cover (images[0])
# matches a bad URL pattern. La portada es images[0] (única fuente de verdad).
import sys; sys.path.insert(0, "scripts")
import image_store
def corpus_image_issue_hits(source_name, bad_image_pattern_re, corpus):
    return [i for i in corpus
            if i.get("source") == source_name
            and bad_image_pattern_re.search(image_store.cover_url(i))]

# M — wrong_classification: find siblings with same series_key that may also be wrong
def corpus_series_siblings(series_key, corpus):
    return [i for i in corpus if i.get("series_key") == series_key]
```

### 3c — Present consolidated proposals to the user

Group all HIGH/MEDIUM confidence fixes by type:

```
PROPUESTAS DE MEJORA (N total):

[1] [A: non_manga_merch] Agregar "bandana" a _NON_MANGA_HARD
    Motivo: item "Naruto Bandana Set" pasó como special_edition.
    Riesgo: BAJO — "bandana" no aparece en títulos manga legítimos.
    Retrofit: filter_non_manga.py

    ⚠️  TAMBIÉN EN EL CORPUS ACTUAL: 4 items más matchean este patrón
        - "Bleach Bandana Edición Limitada" (Animate JP)
        - ... (3 más)
        → Si aprobás esta propuesta, el retrofit los elimina también.

[2] [K: wrong_image] Portada equivocada en "Berserk Deluxe 12"
    Motivo: la portada (images[0]) apunta a la del vol.11 (Norma CDN).
    Fix: backfill_metadata.py --only image_url --limit N (no existe flag --url; para un item puntual usar image_store.set_cover() manual)
    (o corrección manual de images[0] en items.jsonl vía image_store.set_cover)

[3] [M: wrong_classification] series_key "berserk-41" → debería ser "berserk"
    Motivo: el heurístico del scraper interpretó el número como parte del slug.
    Fix: editar el item + agregar alias en series_aliases.yml si hay variantes.
    Hermanos en corpus: 0 (case único).

[4] [H: user_preference] "Nausicaä regular tomo" — sin cambio de código
    Preferencia personal. Se documenta pero no se cambia ningún filtro.

¿Aprobás las propuestas [1], [2], [3]?
```

**Esperar confirmación del usuario antes de continuar.**

### Important: corpus hits require explicit user approval

- **Nunca borrar items del corpus silenciosamente.** Siempre mostrar count + samples antes.
- Si el corpus tiene > 10 hits para una propuesta, ofrecer mostrar la lista completa.
- Si el usuario aprueba el fix de código, el retrofit limpia el corpus automáticamente (camino preferido).
- Items categoría H (user_preference) o confianza LOW → solo documentar en el resumen final, no cambiar código.

## Step 4 — Apply approved changes

> **Golden records guard.** Before applying any **data-quality** fix that
> rewrites a specific item in `items.jsonl` (categories K–N: wrong image,
> wrong metadata, wrong series/edition key, junk title), check
> `item.get('approved_at')`. If the item is **approved**, do NOT auto-edit it
> — the owner marked it correct. Surface it to the owner and ask before
> touching it. Filter/code fixes (A–J) are about scraper logic, not specific
> rows, so they're fine; but when a retrofit follows, it already skips
> approved items by default (`--include-approved` to override).

### A/B/C: Adding to `_NON_MANGA_HARD`

Read the current `_NON_MANGA_HARD` list in `manga_watch.py`. Add using `_phrase_pattern()` for word-boundary matching:

```python
re.compile(_phrase_pattern(r"bandana"), re.I),
```

### D: Fixing `is_collectible_edition`

Read the function in `manga_watch.py`. If a signal fired falsely, add the equivalent to the exclusion list of `_GENERIC_X_EDITION_PATTERN` (see CLAUDE.md gotcha #24) or tighten the relevant condition.

### E: Source purity change

In `sources.yml`, change `purity: "manga_only"` → `purity: "mixed"`. If the source yields 0 real items after, consider `enabled: false`.

### F: Comics blacklist

Edit `data/comics_blacklist.yml` — add publisher to `publishers` or franchise keyword to `franchise_keywords`. Never add publishers that also publish manga (Panini, Norma, Planeta).

### G: Light novel hints

In `manga_watch.py`, find `is_pure_novel()`. Add the publisher or URL hint pattern.

### I: False signal fix

Find the entry in `KEYWORD_RULES` or `_GENERIC_X_EDITION_PATTERN`. Remove the conflicting keyword or add it to the exclusion list (CLAUDE.md gotchas #9, #24).

### K: Wrong image

Option 1 — run backfill for that specific item:
```bash
.venv/bin/python scripts/retrofit/backfill_metadata.py --only image_url --dry-run
# then apply
```

Option 2 — manual fix in items.jsonl (for a single item when the correct URL is known):
```python
import json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
import image_store

items_path = Path("data/items.jsonl")
target_url = "<item_url>"
correct_image_url = "<correct_image_url>"

rows = []
with items_path.open(encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line: continue
        row = json.loads(line)
        if row.get("url") == target_url:
            # La portada es images[0] (única fuente de verdad); set_cover la
            # actualiza con local="" para forzar el re-download de mirror_images.
            image_store.set_cover(row, correct_image_url, "")
        rows.append(row)

tmp = items_path.with_name("items.jsonl.tmp")
with tmp.open("w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
tmp.replace(items_path)
print("Done — run mirror_images.py to download the new cover")
```

Then re-download:
```bash
.venv/bin/python scripts/retrofit/mirror_images.py --no-gc
```

### L: Wrong metadata

```bash
# Example: re-fetch author for a specific source
.venv/bin/python scripts/retrofit/backfill_metadata.py --only author --dry-run
# then apply if it looks right
```

Or for a single item, edit directly in `items.jsonl` using the same pattern as K above.

### M: Wrong classification

1. Fix the item directly in `items.jsonl`:
```python
import json
from pathlib import Path

items_path = Path("data/items.jsonl")
target_url = "<item_url>"

rows = []
with items_path.open(encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line: continue
        row = json.loads(line)
        if row.get("url") == target_url:
            row["series_key"] = "<correct_series_key>"
            row["series_display"] = "<correct_display>"
            row["edition_key"] = "<correct_edition_key>"
            row["edition_display"] = "<correct_display>"
            row["volume"] = "<correct_volume>"
            row["title"] = "<correct_standardized_title>"
        rows.append(row)

tmp = items_path.with_name("items.jsonl.tmp")
with tmp.open("w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
tmp.replace(items_path)
```

2. If the issue is a missing alias (same work under a different name), add to `data/series_aliases.yml`.

3. Refresh cluster_key and slug:
```bash
.venv/bin/python scripts/retrofit/backfill_cluster_key.py
.venv/bin/python scripts/retrofit/generate_slugs.py --only-missing
```

### N: Bad title

If it's a systematic pattern (same prefix on multiple items from same source), fix in `manga_watch.py` and run:
```bash
.venv/bin/python scripts/retrofit/clean_titles.py --dry-run
.venv/bin/python scripts/retrofit/clean_titles.py
```

If it's a one-off, fix the item directly (same pattern as K above, changing the `title` field).

## Step 5 — Add tests (filter changes only)

For every code change to filters (A–J, I), add a unit test in `tests/test_extraction.py` with the exact title string from the feedback. Use the appropriate group:

- `test_is_likely_manga_rejects_*` for `_NON_MANGA_HARD/SOFT` changes
- `test_is_comic_not_manga_*` for comics blacklist
- `test_is_collectible_edition_*` for gate changes
- `test_is_pure_novel_*` for novel filter

Then run the full suite:
```bash
.venv/bin/python -m pytest tests/test_extraction.py -q
```

**If any test fails: fix before continuing.**

Data quality fixes (K–N) do not need new tests unless they reveal a systematic extractor bug worth covering.

## Step 6 — Run retrofit scripts (filter changes only)

| What changed | Retrofits to run |
|---|---|
| `_NON_MANGA_HARD` / `_NON_MANGA_SOFT` / `is_pure_novel` / `is_comic_not_manga` | `filter_non_manga.py` |
| `is_collectible_edition` / `COLLECTIBLE_EDITION_SIGNAL_TYPES` | `filter_collectible.py` |
| `KEYWORD_RULES` / `detect_signals` / `score_candidate` | `rescore.py` then `filter_collectible.py` |
| `sources.yml` purity change | `filter_non_manga.py` |

Always dry-run first:
```bash
.venv/bin/python scripts/retrofit/filter_non_manga.py --dry-run
.venv/bin/python scripts/retrofit/filter_non_manga.py   # apply if looks right
```

## Step 7 — Truncate `feedback.jsonl`

Once all approved changes are applied, back up and clear the queue:

```bash
.venv/bin/python -c "
from scripts.manga_watch import backup_and_rotate
from pathlib import Path
backup_and_rotate(Path('data/feedback.jsonl'), 'review')
"
: > data/feedback.jsonl
```

**Do NOT truncate before all changes are applied.**

## Step 8 — Final report + update CLAUDE.md

```
RESUMEN DE /watch-review-feedback
============================
Items revisados          : N
  → Problemas de filtros : X  (categorías A–J)
  → Calidad de datos     : Y  (categorías K–N)
  → Preferencia personal : Z  (categoría H, sin acción)

Cambios de código        : X
Tests agregados          : Y
Items corpus removidos   : Z (via retrofits)

Cambios aplicados:
  - [1] _NON_MANGA_HARD += "bandana" → filter_non_manga removió 5 items
  - [2] image_url corregida para "Berserk Deluxe 12" + re-download cover
  - [3] series_key "berserk-41" → "berserk" + cluster_key refresh
  ...

feedback.jsonl: truncado (0 items pendientes)
```

Luego actualizá la fecha de la línea `Last updated:` de `CLAUDE.md` (sin agregar prosa — CLAUDE.md ya no lleva changelog) y el doc de referencia que corresponda en `docs/reference/` según la política de documentación.

---

## Referencia rápida: categorías y sus pointers en CLAUDE.md

- `_NON_MANGA_HARD` / `_NON_MANGA_SOFT`: design decision #2, gotcha #9
- Comics blacklist: design decision #3, gotcha #11
- `is_collectible_edition`: conventions "When you add or modify a filter pattern"
- `is_pure_novel`: misma sección
- Source purity: design decision #3, gotchas #7, #10
- False `lore_edition` de palabras genéricas: gotcha #24
- `_phrase_pattern()` para word-boundary: gotcha #9
- `backfill_metadata.py`: file map en CLAUDE.md, sección retrofit
- `clean_titles.py` / `generate_slugs.py`: file map en CLAUDE.md

Ante la duda sobre si un fix es seguro, preferir **no cambiar código** y marcar como categoría H. Mejor dejar un item marginal en el corpus que romper items legítimos con un patrón demasiado amplio.
