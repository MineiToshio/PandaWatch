---
name: watch-enrich-series-aliases
description: Process queue of unmapped manga series (data/unmapped_series.jsonl), group them under existing canonicals or create new entries in data/series_aliases.yml via Anilist API and web search. Trigger manually whenever new items appear without a known series canonical (e.g., after each scrape). Updates the YAML, runs the backfill on items.jsonl, and reports what was done.
argument-hint: "[--limit N]"
---

# Enrich series aliases

> **Model tier (F10):** the per-candidate decision (Steps 1–3 — Anilist lookup +
> A/B/C classification) is bounded reasoning, not heavy synthesis. **Run this skill
> in `sonnet`** (or fix `model: 'sonnet'` on the decision phase if this is ever
> compiled to a workflow). Steps 1, 4, 5 are mechanical (scripts). Never opus.

You are processing the queue of manga series that the scraper discovered but couldn't map to a canonical entry in `data/series_aliases.yml`. Your job: review each candidate, decide whether it's an alias of an existing canonical or a new series, update the YAML, and apply the backfill so `items.jsonl` reflects the new mappings.

**Keep a list of every `series_key` you touch in Steps 2–3** (each candidate's
current, non-canonical `series_key`). You pass that exact list to the backfill in
Step 4 via `--only-keys` — the backfill is deliberately scoped to just those keys.

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
   - The canonical key MUST be pure ASCII kebab-case (`[a-z0-9-]` only) — never raw CJK
     and never Cyrillic/Greek homoglyphs copied from a source ("taihо-to-stamp" with
     Cyrillic о, "maku-ga-oriru-to-bokura-wa-番" — real bugs, gotcha #81). Transliterate
     to romaji instead. The pipeline now sanitizes keys with `sanitize_key_ascii()`, so a
     non-ASCII key will silently diverge from what items actually get — don't coin one.
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

After saving the YAML, run the backfill retrofit **scoped to the exact `series_key`s
you processed** in Steps 2–3 (comma-separated, no spaces):

```bash
# Dry-run first to preview what changes (no write):
.venv/bin/python scripts/retrofit/backfill_series_aliases.py \
  --dry-run --only-keys key1,key2,key3

# Then apply:
.venv/bin/python scripts/retrofit/backfill_series_aliases.py \
  --only-keys key1,key2,key3
```

The script (FUENTE ÚNICA — no embedded logic here anymore):
- Remaps `series_key`/`series_display` of the in-scope items via
  `series_aliases.canonical_series_key` (the single alias resolver), re-aligns the
  `edition_key` prefix, and re-derives `cluster_key` with
  `manga_watch.derive_cluster_key`.
- **Delegates consolidation** to `manga_watch.consolidate_by_cluster` (the single
  merge primitive that ingest uses) — it never re-implements dedup.
- **Backs up `data/items.jsonl`** via `backup_and_rotate` before writing (this is the
  file actually at risk — see Step 5).
- Skips `approved_at` golden records (guard homogéneo). Idempotent.

**⚠️ `--only-keys` is REQUIRED.** Do NOT run this over the whole corpus. Passing every
key you touched is the whole point: a new alias applied blanket-style can collapse
unrelated series across the entire base (regla dura, auditoría post-scrape
2026-07-07: *"backfill de aliases NUNCA sobre todo el corpus"*). The script aborts
without `--only-keys`; `--all --yes-i-know-collateral` exists only for the rare
deliberate full pass.

## Step 5 — Truncate the unmapped queue

Once you've processed the queue, clear it so the next run starts fresh:

```bash
# Backup + truncate (usa backup_and_rotate para respetar la rotación max-3)
.venv/bin/python -c "from scripts.manga_watch import backup_and_rotate; from pathlib import Path; backup_and_rotate(Path('data/unmapped_series.jsonl'), 'enrich')"
: > data/unmapped_series.jsonl
```

(The pipeline will repopulate it on the next scrape if any series remains unmapped.)

> **Note on backups:** the queue (`unmapped_series.jsonl`) is cheap and regenerable —
> the next scrape rebuilds it. The file actually at risk is `data/items.jsonl`, which
> Step 4's retrofit already backs up (`backup_and_rotate` label `series-aliases`)
> before its destructive rewrite. So the critical restore point lives with items.jsonl,
> not the queue; this queue backup is just a convenience.

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
