---
name: standardize-catalog
description: Standardize new manga items in data/items.jsonl that haven't been processed yet (missing standardized_at field). Uses a 3-tier approach — Tier 1 items are auto-standardized deterministically (no LLM), Tier 2 get lightweight LLM validation, and only Tier 3 (unknown series, CJK) get full LLM derivation. Delegates Tier 2/3 to parallel subagents in small batches (~20 items). Skips items already standardized (incremental). Trigger manually after each scrape or weekly.
---

# Standardize catalog

You are processing manga items in `data/items.jsonl` that haven't been standardized yet. The **scraper** (`scripts/manga_watch.py`) does a heuristic assignment when items are first saved — including `confidence_tier` (1/2/3) that indicates how much LLM help is needed. Items are **not yet marked** with `standardized_at`. This skill is the **verification + correction pass**.

## Preferred method: Workflow script

For batches of **30+ items**, use the saved workflow instead of manual steps:

```
Workflow({ name: 'standardize-catalog' })
```

The workflow at `.claude/workflows/standardize-catalog.js` automates the entire
pipeline: audit → Tier 1 auto-standardize → Tier 2 haiku validation → Tier 3
sonnet derivation → merge + dedup + slugs + translation. Schema-validated output
eliminates truncated URLs and session-limit data loss.

For **< 30 items**, process inline using the manual steps below.

## Architecture: 3-tier processing

The scraper's `derive_series_metadata()` now assigns a `confidence_tier`:

- **Tier 1** (~30%): Series resolved in `series_aliases.yml`, publisher known, edition unambiguous. **Auto-standardized deterministically — no LLM needed.**
- **Tier 2** (~9%): Series resolved but edition ambiguous (lore/special/regular) or publisher unknown. **Lightweight LLM validation** (~100 tokens/item).
- **Tier 3** (~37%): Series NOT in aliases (CJK titles, new series). **Full LLM derivation** (~1200 tokens/item).
- **Empty** (~24%): Heuristic punted entirely (too short, all digits). Treated as Tier 3.

This saves ~38% of tokens compared to sending everything through full LLM.

## Incremental — process only what's pending

Each standardized item carries a `standardized_at` ISO timestamp. The skill **only processes items missing this field** (or, with `--force-all`, every item).

## Step 1 — Audit + tier distribution

```bash
.venv/bin/python << 'PY'
import json, sys
sys.path.insert(0, 'scripts')
from manga_watch import derive_series_metadata, Candidate

items = [json.loads(l) for l in open('data/items.jsonl')]
# Golden records: items aprobados manualmente desde el dashboard (approved_at)
# NUNCA se re-procesan — son fuente de verdad. Pueden usarse como ejemplos de
# referencia de "dato bien hecho", pero jamás se sobreescriben.
pending = [it for it in items
           if not it.get('standardized_at') and not it.get('approved_at')]
approved = [it for it in items if it.get('approved_at')]
print(f'Total items: {len(items)}')
print(f'Pendientes (sin standardized_at): {len(pending)}')
print(f'Aprobados (golden records, no se tocan): {len(approved)}')

if not pending:
    print('\nNothing to standardize.')
    exit()

# Re-derive metadata to get confidence_tier for routing
tiers = {1: [], 2: [], 3: []}
for it in pending:
    c = Candidate(
        title=it.get('title_original') or it.get('title',''),
        url=it.get('url',''), source=it.get('source',''),
        source_url=it.get('source_url',''), country=it.get('country',''),
        language=it.get('language',''), publisher=it.get('publisher',''),
        source_class=it.get('source_class',''), tags=it.get('tags',[]),
        description=it.get('description',''),
        signal_types=it.get('signal_types',[]),
    )
    md = derive_series_metadata(c)
    tier = md.get('confidence_tier', 3) if md else 3
    tiers[tier].append((it, md or {}))

print(f'\nTier 1 (auto-standardize): {len(tiers[1])}')
print(f'Tier 2 (LLM validation):   {len(tiers[2])}')
print(f'Tier 3 (full LLM):         {len(tiers[3])}')

# Save tier assignments for later steps
import pickle
from pathlib import Path
base = Path('/tmp/manga-standardize-run')
base.mkdir(parents=True, exist_ok=True)
with open(base / 'tiers.pkl', 'wb') as f:
    pickle.dump(tiers, f)
print(f'\nTier data saved to {base / "tiers.pkl"}')
PY
```

If `Pendientes = 0` → report "nothing to standardize" and stop.

If `Pendientes < 15` → process ALL tiers inline (no subagents needed).

If `Pendientes >= 15` → use the tiered workflow below.

## Step 2 — Auto-standardize Tier 1 (deterministic, no LLM)

Tier 1 items have high-confidence heuristic assignments. Apply them directly:

```bash
.venv/bin/python << 'PY'
import json, pickle, datetime as dt, sys
sys.path.insert(0, 'scripts')
from series_aliases import canonical_series_key
from pathlib import Path

BASE = Path('/tmp/manga-standardize-run')
ITEMS = Path('data/items.jsonl')

with open(BASE / 'tiers.pkl', 'rb') as f:
    tiers = pickle.load(f)

items = [json.loads(l) for l in open(ITEMS)]
url_to_md = {it['url']: md for it, md in tiers[1]}
now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
applied = 0

for it in items:
    if it.get('standardized_at'):
        continue
    md = url_to_md.get(it.get('url',''))
    if not md:
        continue
    # Apply deterministic standardization
    if not it.get('title_original'):
        it['title_original'] = it.get('title', '')
    it['series_key'] = md['series_key']
    it['series_display'] = md['series_display']
    it['edition_key'] = md['edition_key']
    it['edition_display'] = md['edition_display']
    it['volume'] = md['volume']
    if md.get('title_standardized'):
        it['title'] = md['title_standardized']
    it['standardized_at'] = now_iso
    applied += 1

# Write back
tmp = ITEMS.with_suffix(ITEMS.suffix + '.tmp')
with tmp.open('w', encoding='utf-8') as fh:
    for it in items:
        fh.write(json.dumps(it, ensure_ascii=False) + '\n')
tmp.replace(ITEMS)

print(f'Tier 1 auto-standardized: {applied} items (0 tokens used)')
print(f'Remaining for LLM: {len(tiers[2]) + len(tiers[3])} items')
PY
```

## Step 3 — Partition Tier 2 + 3 into chunks

**CRITICAL** — items that share coleccion/page-id MUST go in the SAME chunk.

Tier 2 and Tier 3 items get different prompt templates but can share chunks
if they're siblings. Chunk size: **20-30 items** (smaller than before to avoid
session limits — the #1 reliability problem in past runs).

```bash
.venv/bin/python << 'PY'
import json, re, pickle
from pathlib import Path
from collections import defaultdict

BASE = Path('/tmp/manga-standardize-run')
with open(BASE / 'tiers.pkl', 'rb') as f:
    tiers = pickle.load(f)

CHUNK_SIZE = 25

# Combine Tier 2 + Tier 3 items
remaining = [(it, md, 2) for it, md in tiers[2]] + [(it, md, 3) for it, md in tiers[3]]

def project(it, md, tier):
    return {
        'url': it.get('url',''),
        'title': it.get('title',''),
        'title_original': it.get('title_original',''),
        'source': it.get('source',''),
        'publisher': it.get('publisher',''),
        'country': it.get('country',''),
        'language': it.get('language',''),
        'isbn': it.get('isbn',''),
        'signal_types': it.get('signal_types', []),
        'description_excerpt': (it.get('description','') or '')[:200],
        'tier': tier,
        # Tier 2: include heuristic proposal for validation
        'proposed_series_key': md.get('series_key', ''),
        'proposed_edition_key': md.get('edition_key', ''),
        'proposed_volume': md.get('volume', ''),
        'proposed_title': md.get('title_standardized', ''),
    }

def group_key(it):
    url = it.get('url','')
    m = re.search(r'listadomanga\.es/coleccion\.php\?id=(\d+)', url)
    if m: return f'lmc:{m.group(1)}'
    m = re.match(r'^(https?://[^?#]+)', url)
    return f'url:{m.group(1) if m else url}'

groups = defaultdict(list)
for it, md, tier in remaining:
    groups[group_key(it)].append((it, md, tier))

# Pack into chunks respecting groups
for old in BASE.glob('chunk_*.jsonl'): old.unlink()
for old in BASE.glob('result_*.jsonl'): old.unlink()

chunks = []
current = []
for group in sorted(groups.values(), key=len, reverse=True):
    if len(group) > CHUNK_SIZE:
        if current: chunks.append(current); current = []
        chunks.append(group)
        continue
    if len(current) + len(group) > CHUNK_SIZE and current:
        chunks.append(current); current = []
    current.extend(group)
if current: chunks.append(current)

for idx, chunk in enumerate(chunks):
    p = BASE / f'chunk_{idx:02d}.jsonl'
    p.write_text('\n'.join(
        json.dumps(project(it, md, tier), ensure_ascii=False)
        for it, md, tier in chunk
    ))

print(f'Chunks: {len(chunks)}, sizes: {sorted([len(c) for c in chunks], reverse=True)[:5]}...')
print(f'Total items for LLM: {sum(len(c) for c in chunks)}')
PY
```

## Step 4 — Spawn subagents in parallel

For each chunk, spawn a `general-purpose` subagent **in the background**.
Wave size: 7 subagents max. Chunks are smaller (20-30) so more waves but
each agent finishes faster and never hits session limits.

Each subagent gets this prompt template:

```
Standardize manga catalog entries. Read `/tmp/manga-standardize-run/chunk_<NN>.jsonl` and write `/tmp/manga-standardize-run/result_<NN>.jsonl` with one JSON per input item, SAME ORDER.

## OUTPUT FIELDS:
```json
{"url":"","is_manga":true,"non_manga_reason":"","series_key":"","series_display":"","edition_key":"","edition_display":"","volume":"","title_standardized":""}
```

## TIER-SPECIFIC INSTRUCTIONS

Each input item has a `tier` field (2 or 3).

**Tier 2 items** come with `proposed_*` fields (heuristic assignment). The heuristic
already resolved the series via aliases.yml and assigned a publisher slug. Your job is
to VALIDATE and optionally CORRECT:
- Check if proposed_series_key looks right for this title.
- Check if the edition_slug is the best match (the heuristic might have assigned
  "special" when "collector" or "limited" is more specific).
- If the proposed values look correct, USE THEM (don't re-derive from scratch).
- If something is wrong, fix it using the same rules as Tier 3.

**Tier 3 items** have NO reliable heuristic — derive everything from scratch.

## RULES

### is_manga
- ALL `Global - Mangavariant` items → ALWAYS true. NEVER false.
- Slipcases/box sets/coffrets/cofanetti/steelbox/variant covers/artbooks/fanbooks/magazines → valid.
- Marvel/DC/IDW/Image comics → false unless "manga" in title or known adaptation.
- Figures/statues/plushies/t-shirts/mugs/trading cards/news posts → false.
- Light novels (roman/light-novel/LN URLs) → false (non_manga_reason="light_novel").
- **When in doubt → true.**

### series_key
Lowercase, kebab-case, no diacritics. Cap ~35 chars. Use globally-recognized name.

### edition_key — `{series}-{publisher_slug}-{edition_slug}`
publisher_slug (allowlist — use literal slug from this list):
"darkhorse", "glenat", "viz", "panini", "norma", "planeta", "ivrea", "ivrea-ar",
"kana", "pika", "kaze", "kioon", "star", "kodansha", "kodansha-us", "shueisha",
"squareenix", "kadokawa", "meian", "ecc", "arechi", "delcourt", "tokyopop", "jbc",
"devir", "newpop", "kamite", "mangaline", "mangadreams", "funside", "milkyway",
"dokidoki", "nobinobi", "tomodomo", "fandogamia", "kurokawa", "akita", "hakusensha",
"ichijinsha", "futabasha", "takeshobo", "tokuma", "asciimw", "frontier", "yenpress",
"carlsen", "noeve", "distrito", "001edizioni", "goen", "gpmanga", "jpop", "dynit",
"edizionibd", "magicpress", "coconino", "tora", "dokusho", "tokyomangasha", "kbooks",
"luckpim", "ipm", "isan", "nxb", "mpeg", "sevenseas", "titan", "inklore", "vertical",
"udon", "shogakukan", "gentosha", "maggarden", "egmont", "dokico", "papertoons",
"crosscult", "mangacult", "loewe", "reprodukt", "altraverse", "universe",
"pipoca-nanquim", "kim-dong", "panini-mx", "panini-es", "panini-ar", "panini-br",
"crunchyroll", "rakuten".

edition_slug (pick ONE — NEVER compound two together):
"deluxe", "kanzenban", "perfect", "coffret", "boxset", "cofanetto", "variant",
"limited", "collector", "anniversary", "celebration", "color", "maximum", "ultimate",
"master", "library", "integral", "artbook", "fanbook", "guidebook", "magazine",
"steelbox", "slipcase", "prestige", "grimorio", "grimoire", "special", "regular".

**ANTI-COMPOUND RULE**: Choose ONE slug. Never "deluxe-box", "ultimate-variant", etc.
When format-slug (boxset/hardcover/coffret) conflicts with edition-name
(collector/ultimate/limited), choose the edition-name.

**ARTBOOK vs SPECIAL**: If the item has a volume number → `special` (never `artbook`).
Only standalone illustration books without volume → `artbook`.

### volume
String. Digits only. "1", "100", "1-3" for sets, "" if absent.

### title_standardized
`{Series Display} {Edition Suffix} {Volume}`. Short, clean.

## EXECUTION
1. Read input. 2. Process EVERY item. 3. Output line count MUST equal input. 4. Report totals.
CRITICAL: Same series/publisher → same keys consistently.
```

## Step 5 — Verify integrity

```bash
.venv/bin/python << 'PY'
import json
from pathlib import Path
base = Path('/tmp/manga-standardize-run')
missing_items = []
for cf in sorted(base.glob('chunk_*.jsonl')):
    n = cf.stem.replace('chunk_', '')
    rf = base / f'result_{n}.jsonl'
    chunk_urls = {}
    for line in open(cf):
        line = line.strip()
        if not line: continue
        try:
            it = json.loads(line)
            chunk_urls[it['url']] = it
        except: pass

    if not rf.exists():
        for url, it in chunk_urls.items():
            missing_items.append((n, it))
        continue

    result_urls = set()
    prefix_map = {url[:80]: url for url in chunk_urls}
    out_lines = []
    patched = 0
    for line in open(rf):
        line = line.strip()
        if not line: continue
        try: r = json.loads(line)
        except: continue
        if r.get('url') not in chunk_urls:
            match = prefix_map.get(r.get('url','')[:80])
            if match:
                r['url'] = match; patched += 1
            else: continue
        result_urls.add(r['url'])
        out_lines.append(json.dumps(r, ensure_ascii=False))

    if patched > 0:
        rf.write_text('\n'.join(out_lines) + '\n')
        print(f"chunk {n}: patched {patched} truncated URLs")

    for url in set(chunk_urls) - result_urls:
        missing_items.append((n, chunk_urls[url]))

print(f"\nMissing items: {len(missing_items)}")
if missing_items:
    with open(base / 'inline_retry.jsonl', 'w') as fh:
        for n, it in missing_items:
            fh.write(json.dumps({'chunk': n, 'item': it}, ensure_ascii=False) + '\n')
    print(f"Saved to inline_retry.jsonl — process inline before merge.")
PY
```

If missing > 0, process inline (≤10) or spawn a retry subagent (>10).

## Step 6 — Merge results + apply

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
        final.append(it); continue
    r = results.get(it.get('url',''))
    if not r:
        final.append(it); continue
    if not r.get('is_manga', True):
        non_manga.append({
            'url': it.get('url',''), 'title': it.get('title',''),
            'source': it.get('source',''), 'publisher': it.get('publisher',''),
            'reason': r.get('non_manga_reason','flagged_by_review'),
            'reviewed_at': now_iso,
        })
        continue
    it['series_key'] = r.get('series_key','')
    it['series_display'] = r.get('series_display','')
    it['edition_key'] = r.get('edition_key','')
    it['edition_display'] = r.get('edition_display','')
    it['volume'] = r.get('volume','')
    new_title = r.get('title_standardized','').strip()
    if new_title:
        if not it.get('title_original'):
            it['title_original'] = it.get('title','')
        it['title'] = new_title
    new_sk, new_sd = canonical_series_key(it['title'], it['series_key'], it['series_display'])
    if new_sk != it['series_key']:
        old_sk = it['series_key']
        it['series_key'] = new_sk
        it['series_display'] = new_sd
        if it['edition_key'].startswith(old_sk + '-'):
            it['edition_key'] = new_sk + it['edition_key'][len(old_sk):]
    elif new_sd != it['series_display']:
        it['series_display'] = new_sd
    it['standardized_at'] = now_iso
    final.append(it)

# Consistency check for listadomanga collection groups
import re as _re
from collections import defaultdict as _dd, Counter as _cnt
_groups = _dd(list)
for it in final:
    if not it.get('standardized_at'): continue
    url = it.get('url','') or ''
    m = _re.search(r'listadomanga\.es/coleccion\.php\?id=(\d+)', url)
    if m: _groups[f'lmc:{m.group(1)}'].append(it)

_outliers_fixed = 0
for gk, grp in _groups.items():
    if len(grp) < 4: continue
    sk_counts = _cnt(it.get('series_key','') for it in grp)
    dom_sk, dom_sk_n = sk_counts.most_common(1)[0]
    if dom_sk_n >= 3:
        for it in grp:
            if it.get('series_key','') and it['series_key'] != dom_sk:
                old_ek = it.get('edition_key','')
                if old_ek.startswith(it['series_key'] + '-'):
                    it['edition_key'] = dom_sk + old_ek[len(it['series_key']):]
                it['series_key'] = dom_sk
                dom_sd = next((x.get('series_display','') for x in grp if x.get('series_key')==dom_sk), '')
                if dom_sd: it['series_display'] = dom_sd
                _outliers_fixed += 1

print(f"[CONSISTENCY] outliers fixed: {_outliers_fixed}")

# Consolidar por producto (modelo 1-fila-por-producto).
# El edition_key/volume cambió al estandarizar, así que recomputamos cluster_key
# y FUSIONAMOS los duplicados con merge_cluster (NO los borramos — borrar
# perdería las fuentes hermanas). consolidate_by_cluster es la MISMA primitiva
# que usa append_jsonl al ingestar (fuente única de verdad del merge): une
# sources[], imágenes (portada canónica primera) y extras.
from manga_watch import derive_cluster_key, consolidate_by_cluster
for it in final:
    it['cluster_key'] = derive_cluster_key(it)
_before_consolidate = len(final)
deduped = consolidate_by_cluster(final)
dedup_removed = _before_consolidate - len(deduped)

tmp = ITEMS.with_suffix(ITEMS.suffix + '.tmp')
with tmp.open('w', encoding='utf-8') as fh:
    for it in deduped:
        fh.write(json.dumps(it, ensure_ascii=False) + '\n')
tmp.replace(ITEMS)

existing_bl = set()
if BLACKLIST.exists():
    for line in open(BLACKLIST):
        try: existing_bl.add(json.loads(line).get('url',''))
        except: pass
new_bl = [nm for nm in non_manga if nm['url'] not in existing_bl]
with BLACKLIST.open('a', encoding='utf-8') as fh:
    for nm in new_bl:
        fh.write(json.dumps(nm, ensure_ascii=False) + '\n')

print(f'Items: {len(items)} → {len(deduped)}')
print(f'Standardized: {sum(1 for it in deduped if it.get("standardized_at"))}')
print(f'Non-manga: {len(new_bl)}')
print(f'Deduped: {dedup_removed}')
PY
```

## Step 7 — Run tests

```bash
.venv/bin/python -m pytest tests/test_extraction.py -q
```

## Step 8 — Generate slugs

```bash
.venv/bin/python scripts/retrofit/generate_slugs.py --only-missing --verbose
```

## Step 9 — Translate new descriptions

```bash
.venv/bin/python scripts/retrofit/translate_descriptions.py --workers 4
```

## Step 10 — Cleanup + report

```bash
rm -rf /tmp/manga-standardize-run
```

Report to the user:
- Tier 1 auto-standardized (0 tokens).
- Tier 2+3 processed by LLM.
- Distinct new series_keys.
- Non-manga removed.
- Items deduplicated.
- Items translated.
- Suggest running `/enrich-series-aliases` if new series_keys appeared.

## Anti-patterns

- **NEVER write to items with `approved_at`** (golden records). The owner
  approved them from the dashboard — they are frozen. Even `--force-all` must
  NOT touch them: they stay out of the pending set. You MAY read them as
  reference examples of correct data, but never overwrite their fields.
- **Don't process items that already have `standardized_at`** unless `--force-all`.
- **Don't skip Step 2 (Tier 1 auto-standardize)** — it saves ~30% of tokens.
- **Don't use chunks larger than 30** — session limits cause data loss with big chunks.
- **Don't skip the `canonical_series_key` step in merge.**
- **Don't skip Step 9 (translation)** for small runs.
- **Don't truncate `/tmp/manga-standardize-run/` until merge is confirmed.**

## Force-rerun the whole catalog

```bash
.venv/bin/python -c "from scripts.manga_watch import backup_and_rotate; from pathlib import Path; backup_and_rotate(Path('data/items.jsonl'), 'standardize-force')"
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
