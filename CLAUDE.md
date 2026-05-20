# CLAUDE.md — Context for AI assistants working on PandaWatch

> Read this file first if you are an LLM agent (Claude, GPT, etc.) about
> to make changes to this repo. It captures the design intent, the
> conventions, and the gotchas that are not obvious from the code.
> The goal is that a new conversation can resume work with full context.

## What this project is

**PandaWatch** (repo: `MineiToshio/PandaWatch`, also known internally as
`manga-watch`) is a **personal tracker** that scrapes ~160 sources across
9 countries and 5 languages (ES, EN, FR, IT, JP) looking for
**physical manga special editions**: limited editions, deluxe hardcovers,
box sets, slipcase editions, artbooks, kanzenban, light novels with
bonuses, etc.

**Single user.** No login, no multi-tenant. The owner (sergiomineiro)
runs the scraper periodically and browses results through a static
web UI served locally.

**Stack:**
- Python 3 (scraping pipeline, filters, label/value extraction)
- BeautifulSoup + requests (no Playwright by default; opt-in via
  `--enable-js` for JS-only sites)
- HTML + Alpine.js + Tailwind via CDN (static browser UI — no SPA build)
- Storage: JSONL with **upsert-by-URL semantics** (see "Storage" below)
- Tests: pytest (159 passing as of last commit)

## High-level pipeline

```
sources.yml
    │
    ▼
manga_watch.py (scraper)
  • fetch HTML/RSS/sitemap per source
  • extract_listing_candidates() / extract_rss() / sitemap miner
  • score_candidate() — assigns 0-300 score by signal detection
  • is_likely_manga() — filters out figures/comics/news/etc.
  • clean_title() — strips e-commerce junk, mojibake, news prefixes
  • fetch_metadata_from_detail() — opt-in HTTP per item for cover/
    author/price/ISBN via JSON-LD + label/value pairs
    │
    ▼
data/items.jsonl  ← upsert by URL (1 line per unique URL)
data/state.json   ← cache of seen URLs (for incremental detection)
    │
    ▼
build_web.py  ← reads JSONL, groups by ISBN, embeds in HTML
web/index.html ← Alpine.js dashboard (filters, search, modal)
    │
    ▼
http://localhost:8000/ (via scripts/serve.py)
```

## File map (what lives where)

```
manga_watch.py / scripts/manga_watch.py — main scraper (3500+ lines)
                                          ALL the filtering / scoring
                                          / cleaning lives here.
sources.yml                            — 184 source definitions
                                          (countries, search templates,
                                          purity tier, selectors).
scripts/
  manga_watch.py     — main module (filters, scoring, IO)
  build_web.py       — embeds items.jsonl into web/index.html
  serve.py           — local HTTP server with / → /web/ redirect
  wikis/             — dedicated parsers for community wiki sources
    listadomanga.py     (ES — month calendar)
    manga_sanctuary.py  (FR — Unix timestamp planning)
    otaku_calendar.py   (EN — month-based releases)
    manga_mexico.py     (MX — alphabetic catalog by editorial)
  retrofit/          — utilities to apply changes to historic data
    README.md
    clean_titles.py     — re-clean existing titles
    filter_non_manga.py — re-filter (uses purity from sources.yml)
    backfill_metadata.py — re-fetch missing cover/author/ISBN/price
web/
  index.html         — Alpine.js dashboard
  serve.sh           — convenience wrapper for scripts/serve.py
data/                — gitignored: items.jsonl, state.json, backups
tests/test_extraction.py — pytest suite (159 tests)
docs/
  CLAUDE.md          — THIS FILE
  ARCHITECTURE.md    — deep dive into the pipeline
  SOURCES.md         — how to add/maintain sources
  PRD.md / PRD-catalog.md — original product specs (historical)
```

## Current corpus state

After many filtering and dedup passes:

| Metric | Value |
|---|---|
| Total unique items (line in items.jsonl) | ~3000 |
| Sources enabled | 160 / 184 |
| Sources flagged `purity: mixed` | 46 |
| Countries represented | 9 (FR, JP, ES, IT, US, MX, AR, …) |
| Image coverage | 100.0% |
| Price coverage | 87.4% |
| Author coverage | 82.2% |
| Release date coverage | 75.5% |
| ISBN coverage | 71.5% |

These numbers help future agents sanity-check their changes — a
retrofit that suddenly drops author coverage from 82% to 30% means
something broke.

## The 5 design decisions you MUST understand

### 1. Storage = JSONL with upsert-by-URL semantics

`data/items.jsonl` is NOT append-only anymore. It's an upsert table:
**one line per unique URL** (normalized via `normalize_url_for_dedup`).
`append_jsonl()` does read-modify-write, ~50ms for 3000 items.

History is NOT preserved (we used to be append-only, with 2.5x bloat).
If we need price history later, that's a separate event log.

We're **not migrating to SQLite yet**. The user explicitly chose to
stay on JSONL while we still iterate on filters and patterns. SQLite
will come when we add multi-user / deploy. See ARCHITECTURE.md for the
trigger conditions.

### 2. `is_likely_manga()` is a 4-rule cascade, in order

```
0. _NON_MANGA_HARD       → False (vinyl figure, DVD, Funko, statue, art print, ...)
1. _STRONG_MANGA_PATTERNS → True  (manga, kanzenban, vol N, "Deluxe Hardcover", ...)
2. _MANGA_WITH_EXTRAS    → True  (edición especial + figura, cofanetto, ...)
                          EXCEPT when source_purity='mixed' — then we
                          require a STRONG hint, not just a pack-extras.
3. _NON_MANGA_SOFT       → False (statue, plush, puzzle, mug, ...)
4. Default               → True if purity='manga_only', False if 'mixed'
```

ORDER MATTERS. HARD must fire before STRONG because some non-manga
titles legitimately contain "manga" or "vol N" in them (e.g. "Kodansha
Reveals New Print Manga Licenses" — news, not a product).

When you add a new pattern, ask yourself: **does this need to override
strong-manga rescue?** If yes → HARD. If only when no rescue → SOFT.

### 3. Source purity ("manga_only" vs "mixed")

Some sources have mixed catalogs. Dark Horse Direct sells manga + comics
+ statues + bookends + art prints in the same listing pages. Panini
catalogsearch returns trading cards, Hot Wheels, and corbatas alongside
manga. Anime News Network is a blog, not a catalog.

**`purity: "mixed"` in sources.yml** flips two behaviors in is_likely_manga:
- Pack-extras rescue is disabled ("Collector's Edition" alone won't
  save a Hellboy statue).
- The default is `False` (discard) instead of `True` (keep).

So in mixed sources, ONLY items with a STRONG manga hint pass through.

Sources currently marked mixed (`purity: mixed`):
- US - Dark Horse Direct (manga page + search expansions)
- MX - Panini Manga México, MX - Panini México (search) variants
- ES - Panini España (search) variants
- ES - Norma (search)
- US - Anime News Network News RSS
- US - ComicBook.com Anime
- US - Kodansha USA News
- JP - Rakuten Books (search) variants

### 4. Multi-source grouping happens at presentation, not storage

`items.jsonl` keeps one line per unique URL. **Multi-source aggregation
by ISBN is done in `build_web.py` and replicated in `web/index.html`'s
`dedupByUrl()` JS function** for the live-fetch mode.

When two items share an ISBN:
- The higher-scored item is the canonical.
- Missing fields on canonical are completed from the rest (best-of merge).
- All items go into `sources[]` array preserving per-source price, URL,
  country, stock_type, etc.

This means the storage stays simple and the web does the smart grouping.
**If you change the schema of items, remember sources[] is added by
the dedup step, not by the scraper.**

### 5. Live-fetch mode, not embedded data

`web/index.html` reads `data/items.jsonl` via `fetch("../data/items.jsonl")`
by default. The `<script id="manga-data" type="application/json">` tag
is empty (`[]`) in the repo.

**Always run `scripts/serve.py` to view the dashboard.** The shortcut
`./web/serve.sh` does that + opens the browser. If you `cd` to the repo
and `open web/index.html` directly (file://), the fetch will fail by
CORS and you'll see an error message.

To embed data for offline / double-click use: `python scripts/build_web.py`.
To revert: `python scripts/build_web.py --clear`.

## Conventions for code changes

### When you add or modify a filter pattern

1. **Find a real example** in `data/items.jsonl` (use `grep -i "..."
   data/items.jsonl | head` or a small Python script).
2. **Add a unit test** in `tests/test_extraction.py` with the exact
   user-reported string. Tests group by feature
   (`test_is_likely_manga_rejects_*` etc.).
3. **Run `pytest tests/test_extraction.py -q`** — keep it green.
4. **Retrofit the corpus**: `python scripts/retrofit/filter_non_manga.py`
   if the change affects `is_likely_manga`, or `clean_titles.py` if
   `clean_title`, or `backfill_metadata.py` if extractors changed.
5. **Verify the specific user examples are gone** with a quick Python
   snippet over items.jsonl.

### When you add a new source

See `docs/SOURCES.md` for the complete recipe. Quick version:
- `kind: "html"` for normal sites, `"rss"` for feeds, `"js"` for JS-only
  pages (rare, requires Playwright via `--enable-js`).
- `selectors:` with `item_selector` and `title_selector` if the auto-
  detection misses (Tiendanube uses `[data-product-id]`, Shopify uses
  `[data-product-id]` or `li.grid__item`, etc.).
- `purity: "mixed"` if the catalog is NOT manga-only.
- Tag with `"new-source"` for selective scraping via
  `--only-tags new-source`.

### When you add a new wiki parser

Dedicated parsers live in `scripts/wikis/`. Follow the public API of
`listadomanga.py`:
```python
def parse_calendar_page(html_text, source_url) -> list[Candidate]
def fetch_calendar_month(year, month, session, timeout) -> list[Candidate]
def iter_year_months(yf, mf, yt, mt) -> list[tuple[int, int]]
def bootstrap(yf, mf, yt, mt, session, ...) -> list[Candidate]
```
Then wire into `scripts/manga_watch.py`'s `_run_wiki_bootstrap()`
dispatcher AND add a `choices=` entry in the argparse.

### When you write JSONL

Don't use `open(items_path, 'a')` directly. Use the
`append_jsonl(path, rows)` helper — it does the upsert + atomic rename.

## The 8 known gotchas

1. **Mojibake in FR sources.** Glénat/Pika sometimes return UTF-8 bytes
   decoded as cp1252. `clean_title()` handles via `_fix_mojibake()` with
   iterative round-trip + fallback pair map. Don't add new
   regex-cleaning before this fix; mojibake must be repaired first or
   patterns won't match.

2. **Manga-Sanctuary URL drift.** Future releases sometimes redirect to
   unrelated products. `wikis/manga_sanctuary.py` validates page content
   against expected title with `_title_matches_page()`. Don't disable
   that check.

3. **Otaku Calendar shows only the current month.** Its `?month=YYYY-M`
   URL parameter is ignored by the site. Bootstrap any month range and
   you'll get duplicates of the current month. This is a known
   limitation; the parser is for monthly checking, not historical
   backfill.

4. **Tiendanube vs Shopify selectors.** Tiendanube uses
   `[data-product-id]` + `a[href*='/productos/']`. Shopify uses
   `li.grid__item` or `[data-product-card]` + `a[href*='/products/']`.
   Same idea, different paths (`productos` vs `products`).

5. **Kamite catalog is at /productos/ not /collections/all.** Despite
   looking like Shopify, it's Tiendanube.

6. **Image placeholders are many.** See `IMAGE_URL_BAD_PATTERNS` for the
   list (Glénat `placeholders/`, Pika `placeholders/`, Manga-Sanctuary
   `visuel_defaut`, Kodansha `kodansha--placeholder`, Panini IT/MX
   `placeholder_*`, data:image lazy-load placeholders, URLs ending in
   `/` with no filename). The extractor returns `""` if all candidates
   are placeholders, which lets backfill re-fetch later.

7. **`source_purity` propagates via search-template expansion.** If you
   mark `"FR - Glénat (search)"` as mixed, all 9 search-keyword children
   (`[search: edition collector]`, etc.) inherit the purity because
   `_expand_search_template()` copies the whole dict.

8. **Wikis bypass the source loop.** They are activated via
   `--bootstrap-wiki <name>` (listadomanga, manga-sanctuary,
   otaku-calendar, manga-mexico). They do their own filtering by
   calling `is_likely_manga()` inside the parser. Don't expect them to
   pick up `sources.yml` config.

## When the user reports "this item shouldn't be here"

1. Look up the item in `data/items.jsonl` to see its actual source,
   URL, signals, and what rule(s) it passed.
2. Categorize:
   - **Non-manga merchandise** (figures, bookends, prints, statues) →
     add to `_NON_MANGA_HARD` or `_NON_MANGA_SOFT`.
   - **Trading cards / sticker albums** (Panini Hot Wheels, FIFA, etc.) →
     HARD pattern.
   - **News / blog post** ("X Reveals", "Gives Y a tribute", "Win this!")
     → HARD pattern in the news family.
   - **Source-level problem** (whole feed is news, or whole search trail
     returns mixed crap) → flag the source `purity: mixed`.
   - **Menu junk** ("BD arrow_forward", "rss", category page) → HARD
     pattern matching the literal title.
3. Add a unit test with the exact title.
4. Run `pytest`, then `filter_non_manga.py`.

## When the user reports "this item is missing X field"

Almost always means the extractor didn't pick it up. Workflow:
1. `curl` the item's URL and inspect the HTML.
2. Look for the field in:
   - JSON-LD `<script type="application/ld+json">`
   - `<meta>` tags (`og:image`, `twitter:image`, `book:author`)
   - Definition lists / tables (`<li><span>label</span>value</li>` is
     the common pattern handled by `_extract_label_value_pairs`)
3. If a new label needs handling, add it to `_FIELD_LABELS` (e.g. JP
   labels like 著者, 価格, 発売日 already covered).
4. Run `backfill_metadata.py` (or `--only image_url` etc.) over the
   corpus.

## Commit history milestones (in order)

Useful to skim with `git log --oneline` if you want full chronology.

1. Initial scraper with sources.yml
2. ListadoManga + Manga-Sanctuary wiki parsers (Fase 2 PRD-catalog)
3. Title cleaning iterations (Norma cola, Panini prefix, mojibake)
4. `is_likely_manga()` introduction + filter non-manga script
5. Backfill metadata with `_extract_label_value_pairs` (huge author
   coverage jump 44% → 80%)
6. Tag-based filter (Manga-Sanctuary `type:série tv animée` etc.)
7. Source purity ("mixed" tier for Dark Horse Direct etc.)
8. EN / AR / MX expansion: otaku_calendar.py, manga_mexico.py wikis +
   AR retail sources
9. items.jsonl converted to upsert (one line per URL)
10. Custom server (scripts/serve.py) with `/` → `/web/` redirect
11. Multi-source grouping by ISBN at the presentation layer
12. Numbered pagination + URL `?page=N` + naming "fuentes" not "tiendas"

## Quick sanity check before committing

```bash
.venv/bin/python -m pytest tests/test_extraction.py -q    # must be green
.venv/bin/python scripts/retrofit/filter_non_manga.py --dry-run   # expect 0 rejections if patterns are stable
# If you touched filters, retrofit:
.venv/bin/python scripts/retrofit/filter_non_manga.py
# If you touched clean_title:
.venv/bin/python scripts/retrofit/clean_titles.py --dry-run
# If you touched extractors, optionally:
.venv/bin/python scripts/retrofit/backfill_metadata.py --dry-run
```

## Next things on the radar (not committed to)

These came up in conversation but were explicitly deferred:

- **Multi-source matching beyond ISBN.** Right now we only group items
  that share an ISBN. Many JP items don't have ISBN, and some retailers
  don't expose it. Possible future: fuzzy title + author + language
  match.
- **SQLite migration.** Postponed until multi-user / deploy. See
  ARCHITECTURE.md for the trigger conditions and the migration plan.
- **Censored cover modals** (e.g. Listado Manga has an "accept adult
  content" modal). Currently scraper sees the placeholder. Would
  require Playwright or per-source cookie injection.
- **Price history per item.** Once an item changes price, the new value
  overwrites the old in upsert. If we want a price history we need a
  separate `events.jsonl` or, again, SQLite.

---

Last updated: by Claude in conversation 2026-05-20. If you find this
file stale relative to the code, update it.
