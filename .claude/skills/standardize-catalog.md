---
name: standardize-catalog
description: Standardize new manga items in data/items.jsonl that haven't been processed yet (missing standardized_at field). Delegates to parallel subagents in batches of ~150-200 to assign canonical series_key/edition_key, rewrite titles to the standard format ("Berserk Deluxe 1"), extract volume numbers, identify non-manga items (move to data/non_manga_blacklist.jsonl), and dedup by (series_key, edition_key, volume). Skips items already standardized (incremental). Trigger manually after each scrape or weekly.
---

# Standardize catalog

You are processing manga items in `data/items.jsonl` that haven't been standardized yet. The **scraper** (`scripts/manga_watch.py`) does a rough heuristic assignment when items are first saved — but those items are **not yet marked** with `standardized_at`. This skill is the **verification + correction pass**: it re-derives the schema fields from scratch via LLM, fixes whatever the scraper got wrong, and marks each item with `standardized_at`.

**TRUST NOTHING the scraper assigned.** The scraper uses regex-based heuristics that may produce wrong `series_key` (e.g. "atomic-robo-5" when the "5" is the volume), wrong publisher slug, or wrong edition slug. Your job is to re-derive everything correctly. The user explicitly said: "no importa si por ahí hay algún error, ya después cuando pasa este skill ahí podemos mejorarlo."

## Incremental — process only what's pending

Each standardized item carries a `standardized_at` ISO timestamp. The skill **only processes items missing this field** (or, with `--force-all`, every item).

## Step 1 — Audit what's pending

```bash
.venv/bin/python -c "
import json
items = [json.loads(l) for l in open('data/items.jsonl')]
pending = [it for it in items if not it.get('standardized_at')]
print(f'Total items: {len(items)}')
print(f'Pendientes (sin standardized_at): {len(pending)}')
if pending:
    print(f'\nMuestra de 5 pendientes:')
    for it in pending[:5]:
        print(f'  - {it.get(\"title\",\"\")[:60]}  ← {it.get(\"source\",\"\")[:30]}')
"
```

If `Pendientes = 0` → report "nothing to standardize" and stop.

If `Pendientes < 30` → process them inline (no need for subagents, you can do them yourself in this conversation).

If `Pendientes >= 30` → use the parallel subagent workflow below.

## Step 2 — Partition into chunks

```bash
.venv/bin/python << 'PY'
import json, os
from pathlib import Path

items = [json.loads(l) for l in open('data/items.jsonl')]
pending = [it for it in items if not it.get('standardized_at')]

CHUNK_SIZE = 150  # 150-200 per chunk works well; subagent context fits comfortably

def project(it):
    return {
        'url': it.get('url',''),
        'title': it.get('title',''),
        'source': it.get('source',''),
        'publisher': it.get('publisher',''),
        'country': it.get('country',''),
        'language': it.get('language',''),
        'isbn': it.get('isbn',''),
        'signal_types': it.get('signal_types', []),
    }

base = Path('/tmp/manga-standardize-run')
base.mkdir(parents=True, exist_ok=True)
# Wipe any previous chunk_/result_ files
for old in base.glob('chunk_*.jsonl'): old.unlink()
for old in base.glob('result_*.jsonl'): old.unlink()

chunks = [pending[i:i+CHUNK_SIZE] for i in range(0, len(pending), CHUNK_SIZE)]
for idx, chunk in enumerate(chunks):
    p = base / f'chunk_{idx:02d}.jsonl'
    p.write_text('\n'.join(json.dumps(project(it), ensure_ascii=False) for it in chunk))

print(f'Chunks creados: {len(chunks)} de {CHUNK_SIZE} items c/u (total {len(pending)})')
PY
```

## Step 3 — Spawn subagents in parallel waves

For each chunk, spawn a `general-purpose` subagent **in the background** (`run_in_background: true`). Wave size: 7 subagents in parallel max (to avoid overwhelming the system). If you have >7 chunks, launch the first 7 and the rest will go in subsequent waves as the first ones complete.

Each subagent gets this prompt template (substitute `<NN>` with the chunk number):

```
Standardize manga catalog entries. Read `/tmp/manga-standardize-run/chunk_<NN>.jsonl` and write `/tmp/manga-standardize-run/result_<NN>.jsonl` with one JSON per input item, SAME ORDER.

## OUTPUT FIELDS:
```json
{"url":"","is_manga":true,"non_manga_reason":"","series_key":"","series_display":"","edition_key":"","edition_display":"","volume":"","title_standardized":""}
```

## RULES

### is_manga
- ALL `Global - Mangavariant` items → ALWAYS true. NEVER false.
- Slipcases/box sets/coffrets/cofanetti/steelbox/variant covers (even w/o volume)/artbooks/fanbooks/magazines → valid.
- Marvel/DC/IDW/Image comics → false unless "manga" in title or known adaptation.
- Figures/statues/plushies/t-shirts/mugs/trading cards/news posts → false.
- Light novels (roman/light-novel/LN URLs) → false (non_manga_reason="light_novel").
- **When in doubt → true.**

### series_key
Lowercase, kebab-case, no diacritics. Cap ~35 chars. Use globally-recognized name (EN typically, JP romanji if canonical). Examples: "berserk", "demon-slayer", "spy-x-family", "attack-on-titan", "naruto", "boruto", "jujutsu-kaisen", "one-piece", "fullmetal-alchemist", "20th-century-boys".

### edition_key — `{series}-{publisher_slug}-{edition_slug}`
publisher_slug: "darkhorse", "glenat", "viz", "panini", "norma", "planeta", "ivrea", "ivrea-ar", "kana", "pika", "kaze", "kioon", "star", "kodansha", "kodansha-us", "shueisha", "squareenix", "kadokawa", "meian", "ecc", "arechi", "delcourt", "tokyopop", "jbc", "devir", "newpop", "pipoca-nanquim", "kamite", "mangaline", "mangadreams", "funside", "milkyway", "dokidoki", "nobinobi", "tomodomo", "fandogamia". Unknown → "unknown".

edition_slug (most distinctive): "deluxe", "kanzenban", "perfect", "coffret", "boxset", "cofanetto", "variant", "limited", "collector", "anniversary", "celebration", "color", "maximum", "ultimate", "master", "library", "integral", "artbook", "fanbook", "guidebook", "magazine", "steelbox", "slipcase", "prestige", "regular", "special". Compound OK (e.g. "ultra-collector").

### edition_display
"{Edition Name} ({Publisher})". Omit parens if unknown publisher.

### volume
String. Digits only. "1", "100", "1-3" for multi-vol sets, "" if absent (artbooks, one-shots, cover-only).

### title_standardized
`{Series Display} {Edition Suffix} {Volume}`. Short, clean. NO year, NO retailer, NO "(Reedición)".

## EXECUTION
1. Read input file with Read tool.
2. Process EVERY item.
3. Output line count MUST equal input line count.
4. Report: total, distinct series_keys, distinct edition_keys, is_manga=false count.

CRITICAL: Same series/publisher → same keys consistently across the file.
```

Spawn pattern (you can launch 7 at once in a single message):

```python
# Pseudocode — in actual skill execution, use the Agent tool 7x in parallel
for chunk_num in chunks_to_process:
    Agent(
        subagent_type='general-purpose',
        description=f'Standardize chunk {chunk_num:02d}',
        prompt=<template above with chunk_num substituted>,
        run_in_background=True,
    )
```

Wait for completion notifications, then process the next wave.

## Step 4 — Merge results + apply

After all subagent results are written to `result_NN.jsonl`, merge:

```bash
.venv/bin/python << 'PY'
import json, sys
sys.path.insert(0, 'scripts')
import series_aliases, importlib
importlib.reload(series_aliases)
from series_aliases import canonical_series_key, _build_lookup
_build_lookup.cache_clear()
from pathlib import Path
import datetime as dt

BASE = Path('/tmp/manga-standardize-run')
ITEMS = Path('data/items.jsonl')
BLACKLIST = Path('data/non_manga_blacklist.jsonl')

# Load all results
results = {}
for p in sorted(BASE.glob('result_*.jsonl')):
    for line in open(p):
        r = json.loads(line)
        results[r['url']] = r

items = [json.loads(l) for l in open(ITEMS)]
now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

non_manga = []
final = []
for it in items:
    if it.get('standardized_at'):
        # Already standardized, keep as-is
        final.append(it)
        continue
    r = results.get(it.get('url',''))
    if not r:
        # Didn't get a result for this item — skip (will retry next run)
        final.append(it)
        continue
    if not r.get('is_manga', True):
        non_manga.append({
            'url': it.get('url',''),
            'title': it.get('title',''),
            'source': it.get('source',''),
            'publisher': it.get('publisher',''),
            'reason': r.get('non_manga_reason','flagged_by_review'),
            'reviewed_at': now_iso,
        })
        continue
    # Apply standardization
    it['series_key'] = r.get('series_key','')
    it['series_display'] = r.get('series_display','')
    it['edition_key'] = r.get('edition_key','')
    it['edition_display'] = r.get('edition_display','')
    it['volume'] = r.get('volume','')
    new_title = r.get('title_standardized','').strip()
    if new_title:
        # Preservar el título scrapeado original antes de sobrescribir.
        # Esto permite que el search del dashboard encuentre items tipeando
        # el título en JP/ES/FR original aunque el display sea EN canonical.
        # Ver gotcha #22.
        if not it.get('title_original'):
            it['title_original'] = it.get('title','')
        it['title'] = new_title
    # Apply canonical resolution (aliases.yml)
    new_sk, new_sd = canonical_series_key(it['title'], it['series_key'], it['series_display'])
    if new_sk != it['series_key']:
        old_sk = it['series_key']
        it['series_key'] = new_sk
        it['series_display'] = new_sd
        if it['edition_key'].startswith(old_sk + '-'):
            it['edition_key'] = new_sk + it['edition_key'][len(old_sk):]
    elif new_sd != it['series_display']:
        it['series_display'] = new_sd
    # Mark as standardized
    it['standardized_at'] = now_iso
    final.append(it)

# Dedup by (series_key, edition_key, volume) across the entire corpus
def comp(it):
    return (100 if it.get('isbn') else 0) + (10 if it.get('image_url') else 0) + (5 if it.get('price') else 0)
winners = {}
for it in final:
    sk = it.get('series_key',''); ek = it.get('edition_key',''); v = it.get('volume','')
    if not (sk and ek): continue
    k = (sk, ek, v)
    if k not in winners or comp(it) > comp(winners[k]):
        winners[k] = it
deduped = []
seen = set()
dedup_removed = 0
for it in final:
    sk = it.get('series_key',''); ek = it.get('edition_key',''); v = it.get('volume','')
    if not (sk and ek):
        deduped.append(it); continue
    k = (sk, ek, v)
    if k in seen:
        dedup_removed += 1
        continue
    seen.add(k)
    deduped.append(winners[k])

# Write items.jsonl
tmp = ITEMS.with_suffix(ITEMS.suffix + '.tmp')
with tmp.open('w', encoding='utf-8') as fh:
    for it in deduped:
        fh.write(json.dumps(it, ensure_ascii=False) + '\n')
tmp.replace(ITEMS)

# Append non_manga to blacklist (idempotent: check existing URLs first)
existing_bl = set()
if BLACKLIST.exists():
    for line in open(BLACKLIST):
        try:
            existing_bl.add(json.loads(line).get('url',''))
        except: pass
new_bl = [nm for nm in non_manga if nm['url'] not in existing_bl]
with BLACKLIST.open('a', encoding='utf-8') as fh:
    for nm in new_bl:
        fh.write(json.dumps(nm, ensure_ascii=False) + '\n')

print(f'Items totales: {len(items)} → {len(deduped)}')
print(f'Standardized: {sum(1 for it in deduped if it.get("standardized_at"))}')
print(f'Non-manga movidos a blacklist: {len(new_bl)}')
print(f'Deduped: {dedup_removed}')
PY
```

## Step 5 — Run tests

```bash
.venv/bin/python -m pytest tests/test_extraction.py -q
```

## Step 6 — Cleanup + report

```bash
rm -rf /tmp/manga-standardize-run
```

Then report to the user:
- Total items standardized this run.
- Distinct new series_keys discovered (might want to alias them via `/enrich-series-aliases`).
- Distinct edition_keys.
- Non-manga removed (with sample reasons).
- Items deduplicated.
- Suggest running `/enrich-series-aliases` if new series_keys appeared.

## Anti-patterns

- **Don't process items that already have `standardized_at`** unless the user explicitly asked for `--force-all`. Wastes API calls.
- **Don't lower the chunk size below 100** unless the corpus is tiny. Subagent setup overhead is non-trivial; bigger chunks amortize it.
- **Don't skip the `canonical_series_key` step in merge** — that's where Demon Slayer's various names collapse to one. Without it, the standardization output is partial.
- **Don't forget to set `standardized_at`** on each processed item — that's what makes future runs incremental.
- **Don't truncate `/tmp/manga-standardize-run/` until you've confirmed the merge wrote items.jsonl successfully.** If the merge fails, you want the raw subagent outputs preserved for debugging.

## Force-rerun the whole catalog

If standardization rules changed significantly and you want to re-process EVERYTHING:

```bash
# Backup first!
cp data/items.jsonl /tmp/items.jsonl.bak-$(date +%Y%m%d)
.venv/bin/python -c "
import json
items = [json.loads(l) for l in open('data/items.jsonl')]
for it in items: it.pop('standardized_at', None)
with open('data/items.jsonl','w',encoding='utf-8') as fh:
    for it in items: fh.write(json.dumps(it, ensure_ascii=False) + '\n')
print(f'Cleared standardized_at on {len(items)} items')
"
```

Then re-run the skill normally.

## When to invoke

- After each `manga_watch.py` scrape (new items will have empty `standardized_at`).
- Before publishing a fresh build of the dashboard.
- Weekly as part of overnight maintenance.
- When you notice messy titles, missing series_keys, or non-manga items in the dashboard.
