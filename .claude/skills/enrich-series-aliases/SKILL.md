---
name: enrich-series-aliases
description: Process queue of unmapped manga series (data/unmapped_series.jsonl), group them under existing canonicals or create new entries in data/series_aliases.yml via Anilist API and web search. Trigger manually whenever new items appear without a known series canonical (e.g., after each scrape). Updates the YAML, runs the backfill on items.jsonl, and reports what was done.
---

# Enrich series aliases

You are processing the queue of manga series that the scraper discovered but couldn't map to a canonical entry in `data/series_aliases.yml`. Your job: review each candidate, decide whether it's an alias of an existing canonical or a new series, update the YAML, and apply the backfill so `items.jsonl` reflects the new mappings.

## Step 1 — Audit the queue

Run the audit script first. It reads `data/items.jsonl` + `data/unmapped_series.jsonl`, aggregates by `series_key`, and proposes fuzzy matches against existing canonicals.

```bash
.venv/bin/python scripts/audit/unmapped_series.py --min-count 1 --max-suggestions 50
```

The output is markdown with one section per candidate, ordered by `item_count` DESC. For each candidate you see:

- `series_key` (current, non-canonical) and `primary_display`
- Best fuzzy guess of an existing canonical (🟢 confidence ≥ 0.8 / 🟡 0.6–0.8 / 🔴 < 0.6)
- Languages, publishers, sample titles, sample URL

If the file is empty / no candidates: report "no unmapped series" and stop.

## Step 2 — Classify each candidate

For each entry in the audit output, choose ONE of three actions:

### Action A: merge into existing canonical (alias)

When the candidate is clearly a translation, romanization, or spelling variant of a series already in `series_aliases.yml`:

- "🟢 best guess = `witch-hat-atelier` (confidence 0.85)" + candidate is `atelier-des-sorciers` → it's the French title.
- "🟢 best guess = `apothecary-diaries` (confidence 0.92)" + candidate is `apothicaire` → FR title.

Add the candidate's `series_key` and `primary_display` (and any extra synonyms you know) to the `aliases` list of the existing canonical entry in the YAML.

### Action B: create a new canonical entry

When the candidate is a real new series not yet in the YAML (e.g., a recent release, a niche manga, a spin-off). Steps:

1. Query Anilist GraphQL to get the canonical international name + multilingual synonyms:

   ```bash
   curl -s -X POST https://graphql.anilist.co \
     -H "Content-Type: application/json" \
     -H "User-Agent: PandaWatch/1.0 (sminei10@gmail.com)" \
     -d '{"query":"query($s:String){Media(search:$s,type:MANGA){id title{romaji english native} synonyms}}","variables":{"s":"<SERIES_DISPLAY>"}}'
   ```

2. If Anilist returns a match:
   - Choose canonical key = slug of `title.english` (preferred) or `title.romaji`. Avoid subtitles ("Frieren: Beyond Journey's End" → just "frieren").
   - Display = `title.english` cleaned, or romaji if no english.
   - Aliases = romaji, native, and synonyms — **filter out** synonyms in non-target alphabets (cyrillic, arabic, hebrew, hangul, thai) and single-word generic aliases that could collide ("Monster", "Real", "Blue Period" when those refer to other series).

3. If Anilist returns nothing (rare — doujinshi, very recent, or obscure):
   - Try a quick web search for the title to find its English/international name.
   - If still nothing: use the JP romaji (transliterate the title if needed) as canonical. Display = romaji form.

4. For Spanish (especially Latin American), French (Glénat/Pika), Italian (Star Comics/Panini) translations — check the publishers in the candidate's metadata and add the local title as an alias if it differs from canonical. The audit output lists languages and publishers you can use as hints.

### Action C: skip (low confidence, low priority, or wrong data)

Reasons to skip:
- `item_count` == 1 AND title looks like garbage (truncated, weird encoding).
- The candidate is actually a one-shot or doujinshi that won't get more items.
- The data is ambiguous and you'd rather wait for more items to accumulate before deciding.

For skips: just leave the entry unmapped. The audit will surface it again next time you run the skill.

## Step 3 — Update the YAML

For each Action A or B, edit `data/series_aliases.yml` directly. Add entries in the same shape as existing ones:

```yaml
witch-hat-atelier:
  display: Witch Hat Atelier
  aliases:
    - Atelier of Witch Hat
    - L'Atelier des Sorciers
    - Tongari Boushi no Atelier
    - とんがり帽子のアトリエ
    # ← add new alias here
    - atelier-of-witch-hat
```

**Rules for editing the YAML:**
- Keep entries alphabetized by canonical key (the file is sorted that way).
- Within `aliases`, sorted alphabetically too (helps diff readability).
- One entry per line in the aliases array (YAML list).
- Preserve diacritics in display names ("Frieren", "L'Apothicaire") — the resolver normalizes them at match time.
- For JP-only manga that has no English title, use romaji as display (e.g., "Yawara!").
- Never add an alias that's a single short generic word ("Monster", "Real") — those collide with other series.
- If you're merging two existing canonicals into one (e.g., `detective-conan` + `case-closed`), pick the more globally-recognized one as canonical, move all aliases of the loser into the winner, then DELETE the loser entry from the YAML.

## Step 4 — Apply the backfill

After saving the YAML, run this Python snippet to apply the new mappings to `data/items.jsonl`:

```bash
.venv/bin/python -c "
import json, sys
sys.path.insert(0, 'scripts')
import series_aliases, importlib
importlib.reload(series_aliases)
from series_aliases import canonical_series_key, _build_lookup
_build_lookup.cache_clear()
from pathlib import Path

ITEMS = Path('data/items.jsonl')
items = [json.loads(l) for l in open(ITEMS)]
remapped = 0
for it in items:
    old_sk = it.get('series_key','')
    old_sd = it.get('series_display','')
    new_sk, new_sd = canonical_series_key(it.get('title',''), old_sk, old_sd)
    if new_sk != old_sk:
        it['series_key'] = new_sk
        it['series_display'] = new_sd
        old_ek = it.get('edition_key','')
        if old_ek.startswith(old_sk + '-'):
            it['edition_key'] = new_sk + old_ek[len(old_sk):]
        remapped += 1
    elif new_sd != old_sd:
        it['series_display'] = new_sd

# Dedup por (series_key, edition_key, volume)
def comp(it):
    return (100 if it.get('isbn') else 0) + (10 if it.get('image_url') else 0) + (5 if it.get('price') else 0)
seen = {}
for it in items:
    sk = it.get('series_key',''); ek = it.get('edition_key',''); v = it.get('volume','')
    if not (sk and ek): continue
    k = (sk, ek, v)
    if k not in seen or comp(it) > comp(seen[k]):
        seen[k] = it
final = []
seen_keys = set()
for it in items:
    sk = it.get('series_key',''); ek = it.get('edition_key',''); v = it.get('volume','')
    if not (sk and ek):
        final.append(it); continue
    k = (sk, ek, v)
    if k in seen_keys: continue
    seen_keys.add(k)
    final.append(seen[k])

tmp = ITEMS.with_suffix(ITEMS.suffix + '.tmp')
with tmp.open('w', encoding='utf-8') as fh:
    for it in final:
        fh.write(json.dumps(it, ensure_ascii=False) + '\n')
tmp.replace(ITEMS)
print(f'Items remapped: {remapped} / {len(items)}')
print(f'After dedup: {len(final)} items')
"
```

## Step 5 — Truncate the unmapped queue

Once you've processed the queue, clear it so the next run starts fresh:

```bash
# Backup + truncate (usa backup_and_rotate para respetar la rotación max-3)
.venv/bin/python -c "from scripts.manga_watch import backup_and_rotate; from pathlib import Path; backup_and_rotate(Path('data/unmapped_series.jsonl'), 'enrich')"
: > data/unmapped_series.jsonl
```

(The pipeline will repopulate it on the next scrape if any series remains unmapped.)

## Step 6 — Run tests + report

```bash
.venv/bin/python -m pytest tests/test_extraction.py -q
```

Then write a brief report to the user:
- Total candidates processed.
- New canonicals added (with display name).
- Aliases merged into existing canonicals.
- Items remapped via backfill.
- Anything you skipped + why.

## Anti-patterns to avoid

- **Don't add single-letter or 2-3 char aliases.** They cause substring collisions (the resolver is exact-match, but humans editing the YAML may make mistakes later).
- **Don't add an alias whose normalization equals an existing canonical key for a different series.** Check the YAML before adding.
- **Don't bulk-merge without inspecting the data.** A confidence of 0.7 is a hint, not a verdict — check the sample titles to confirm.
- **Don't include the original Anilist `synonyms` blindly.** They contain transliterations to alphabets we don't target (cyrillic, hebrew, arabic, korean, thai) plus single-word generic aliases (BNHA, MHA, AoT, SnK) that pollute the namespace. Drop them.
- **Don't delete the unmapped_series.jsonl mid-run.** Truncate at the END, after the backfill applied cleanly.

## When to invoke this skill

- After each `manga_watch.py` scrape if new series were discovered.
- Once a week as a regular curation pass.
- Before generating a fresh build of the dashboard (so the filter-by-obra dropdown is consistent).
- When user reports "I see this series twice with different names in the dashboard".
