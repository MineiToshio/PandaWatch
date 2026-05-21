# Architecture

Deep dive into how PandaWatch's pipeline works end-to-end.
Read `CLAUDE.md` first for the high-level orientation.

## Components

```
┌──────────────────────────────────────────────────────────────┐
│                       sources.yml                            │
│  184 entries × {country, language, kind, selectors,          │
│  search_template?, keywords?, tags, purity}                  │
└──────────────────────────┬───────────────────────────────────┘
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
        ▼                                     ▼
┌───────────────────┐               ┌───────────────────┐
│  HTML/RSS scraper │               │   Wiki bootstrap  │
│  manga_watch.py   │               │   (--bootstrap-   │
│                   │               │     wiki <name>)  │
│  • extract_listing│               │                   │
│  • extract_rss    │               │  scripts/wikis/   │
│  • sitemap miner  │               │   listadomanga    │
│                   │               │   manga_sanctuary │
│                   │               │   otaku_calendar  │
│                   │               │   manga_mexico    │
└─────────┬─────────┘               └─────────┬─────────┘
          │                                   │
          ▼                                   ▼
       ╔══════════════════════════════════════════╗
       ║  Filtering & scoring layer (manga_watch) ║
       ║                                          ║
       ║  clean_title() ─ strip junk prefixes,    ║
       ║                  suffixes, mojibake       ║
       ║  detect_signals() ─ score 0-300 by        ║
       ║                     keyword density       ║
       ║  is_likely_manga() ─ 4-rule cascade       ║
       ║                      (see CLAUDE.md)      ║
       ║  fetch_metadata_from_detail() ─ opt-in    ║
       ║                                  per-item ║
       ║                                  HTTP     ║
       ║                                  enrich   ║
       ╚════════════════════╤═════════════════════╝
                            │
                            ▼
       ┌──────────────────────────────────────────┐
       │  process_state(): diff vs state.json     │
       │  • new       → write to items.jsonl      │
       │  • changed   → upsert in items.jsonl     │
       │  • seen      → skip                      │
       └──────────────────┬───────────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
      ┌───────────────┐       ┌──────────────────┐
      │ state.json    │       │  items.jsonl     │
      │ (cache, ~7MB) │       │  (upsert by URL) │
      │ url → snapshot│       │  (1 line per URL)│
      └───────────────┘       └────────┬─────────┘
                                       │
                                       ▼
                         ┌─────────────────────────┐
                         │   build_web.py          │
                         │   • normalize URLs      │
                         │   • group by ISBN       │
                         │   • build sources[]     │
                         │   • embed in index.html │
                         │     (or leave [])       │
                         └─────────────┬───────────┘
                                       │
                                       ▼
                         ┌─────────────────────────┐
                         │  web/index.html         │
                         │  + scripts/serve.py     │
                         │                         │
                         │  http://localhost:8000  │
                         └─────────────────────────┘
```

## Data flow per scrape

For each enabled source in `sources.yml`:

1. **Fetch.**
   - `kind: html` → `requests.get(url)`. Follows pagination if a "next"
     link is detected (heuristic in `find_next_page_url`).
   - `kind: rss` → `feedparser.parse(url)`.
   - `kind: js` → Playwright (requires `--enable-js` flag at CLI).
   - `kind: wiki` → not in this loop; activated via `--bootstrap-wiki`.

2. **Parse candidates.**
   - `extract_listing_candidates(soup, source)` walks cards using
     `item_selector` from source.selectors (or auto-detected).
     Returns `Candidate` objects with title, url, description, image_url.
   - `extract_rss(source, feed_text)` walks RSS entries.

3. **Filter and score.**
   - `clean_title(title)` strips junk prefixes/suffixes/mojibake.
   - `is_likely_manga(title, description, tags, source_purity)`. If
     False, skip. Counted as `cards_skipped_non_manga`.
   - `score_candidate(candidate)`:
     - `detect_signals(blob)` scans for keywords like "kanzenban",
       "deluxe edition", "exclusive variant", "limited", etc.
     - Adds bonus by source_class (official +5, retailer +4, social -5).
     - Clamps to [0, 300].
     - Populates `candidate.signals`, `signal_types`, `product_type`,
       `stock_type`.

4. **Detail enrichment** (opt-in via `--fetch-details`):
   - `fetch_metadata_from_detail(url, session, timeout)`:
     - GET the URL.
     - Extract `name`, `author`, `image_url`, `isbn`, `price`,
       `release_date`, `publisher`, `description` via:
       1. JSON-LD `<script type="application/ld+json">`
       2. OpenGraph / Twitter meta tags
       3. `_extract_label_value_pairs(soup)` — recognizes
          `<li><span>label</span>value</li>`, `<dt>/<dd>`, `<tr>` with
          multilingual labels (FR/ES/EN/IT/JP). This is the workhorse
          for sites like Manga-Sanctuary, Pika, Glénat, Sanyodo.
       4. Body text fallback (regex).

5. **State diff.**
   - `process_state(candidates, state, min_score, include_seen)`:
     - Compute `content_hash` per candidate (sha256 of key fields).
     - Compare to `state.json[url].content_hash`:
       - URL not in state → status `"new"`.
       - URL in state, hash differs → status `"changed"`.
       - URL in state, hash same → status `"seen"` (skip unless
         `--include-seen`).
     - Update state[url] with new snapshot.

6. **Persist.**
   - `append_jsonl(items_path, new_or_changed)`:
     - Read existing items.jsonl into a dict keyed by
       `normalize_url_for_dedup(url)`.
     - Upsert each row (last-wins by detected_at).
     - Atomic write via `.tmp` + `rename`.
   - `save_state(state_path, state)`.
   - `write_markdown_report(report_path, ...)`.

## Filter / scoring internals

### `clean_title()`

Applies in order, iterating until stable (max 5 passes):

1. **Mojibake repair.** Round-trip cp1252/latin-1 → UTF-8 if hints
   present (`Ã©`, `Ã¨`, etc.). Fallback to known-pair substitution
   if strict round-trip fails (`Ã ` standalone, double-encoded text).

2. **`TITLE_JUNK_PREFIXES`** — removes "New Product Announcement -",
   "Panini: Fumetti_", "Nouveauté Glénat Manga", "Próximamente", etc.

3. **`TITLE_JUNK_PATTERNS`** — strips trailing junk: Shopify "Sale price:",
   "Add to cart", currency-only tails, retailer-exclusive parens (Dark
   Horse Direct, Kinokuniya, Barnes & Noble), Norma's "Con sobrecubierta…
   MÁS INFO" descriptive tail, trailing dates, news headlines
   ("Reveals…", "Gives X a Y", "Contest: Win…"), podcast prefixes
   (`^Episodio N |`), trading cards / sticker albums, JP magazines
   (N月号), JP encyclopedias (図鑑), etc.

### `is_likely_manga()`

4-rule cascade. See CLAUDE.md for the full ordering. Source code in
`scripts/manga_watch.py`. Three pattern groups:

- `_NON_MANGA_HARD`: products that are NEVER bonuses in a manga pack
  (DVD, Blu-ray, Funko, vinyl figure, Q Posket, Banpresto, action
  figure, model kit, art prints, bookends, statues by spec, sports
  collectibles, podcasts, news patterns, jewelry/clothing, conventions,
  JP magazines, idol BOX sets).
- `_STRONG_MANGA_PATTERNS`: confirm the item IS a book. Includes
  multilingual "manga", "vol/tome/tomo N", "kanzenban", "artbook",
  "Deluxe Hardcover", "Library Edition", "Omnibus", "Compendium",
  "Box Set", "Frame Art", "The Art of", JP terms (画集, 漫画, etc.).
- `_NON_MANGA_SOFT`: can be a manga bonus extra (statue, plush, puzzle,
  mug, "Figure" standalone at end of title). Only blocks if no strong
  rescue.

Also: **tag-level filter** (`_NON_MANGA_TAG_PREFIXES`). Manga-Sanctuary
ships items with `type:série tv animée`, `type:film`, `type:OAV`,
`type:produit dérivé` — these are rejected upfront before title
inspection.

### `detect_signals()`

Looks for ~70 keywords in title + description. Each match adds points.
Different weights for "limited", "deluxe", "exclusive", "boxset",
"kanzenban", "variant_cover", "premium_format", "shikishi",
"made_to_order", "omnibus", "compendium", "library edition", etc.

Outputs a numeric score (clamped [0, 300]), a list of human-readable
"signals" strings, and a set of `signal_types` (`limited`, `deluxe`,
`box_set`, `artbook`, `fanbook`, `variant_cover`, `made_to_order`, etc.)
used by other functions (e.g. `derive_product_type`, `derive_stock_type`,
`is_collectible_edition`).

### `is_collectible_edition()`

Second gate after `is_likely_manga`. The project's product is **only**
special editions / variants / collector / first-edition extras /
artbooks / fanbooks / guidebooks / series-magazines. A regular tomo
without anything special is rejected.

Rules (any match → accepted):
1. Title signal_types intersect `COLLECTIBLE_EDITION_SIGNAL_TYPES`
   (limited, collector, deluxe, variant_cover, box_set, retailer_exclusive,
   omnibus, hardcover, etc.).
2. Title signal_types intersect `FIRST_EDITION_EXTRAS_SIGNAL_TYPES`
   (bonus, finish) — for "tomo regular con marcapáginas exclusivo".
3. product_type in `COLLECTIBLE_PRODUCT_TYPES` (artbook, fanbook,
   guidebook, magazine, boxset).
4. Title matches `<Word> Edition/Edizione/Édition/Edición` with a
   non-stoplist proper noun — rescues lore-specific words
   (Beherit Edition, Tarot Edition, Celebration Edition, Anniversary
   Edition, Colossal Edition, Grimoire Edition, etc.) without
   maintaining a series catalog.

Pre-filter: `_UMBRELLA_JP_MAGAZINE_PATTERN` blocks Shōnen Jump,
Young Jump, Big Comic Spirits, etc. (multi-series anthologies).
Series-specific magazines like "One Piece Magazine" pass.

**Critical: signals are recomputed from title only** inside the gate,
even if `signal_types` are passed in. This guards against news/social
posts whose description happens to mention "limited" or "póster" but
whose title is clearly not a product.

### Filter / scoring INVARIANTS

Recurring bugs in this codebase originated from breaking one of these.
Keep them in mind when extending:

**Invariant 1: signal_types describe THE ITEM, not the source.**
`detect_signals` runs ONLY on `title + description`. NEVER include
source name, publisher, tags, or search-template keywords in its input.
Source-class score boost is applied SEPARATELY in `score_candidate`.

Why: source name "IT - Panini Edizioni da Collezione e **Cofanetti**"
once contaminated every item from that source with `box_set` signal.
Tag `edition:coffret collector` from Manga-Sanctuary did the same.
Search-template `[search: boxset]` also.

**Invariant 2: keyword matching uses WORD BOUNDARIES, not substrings.**
Both `detect_signals` and `derive_product_type` go through
`_phrase_pattern()` which builds `(?<![a-z0-9])phrase(?![a-z0-9])` for
ASCII phrases and plain substring for CJK phrases.

Why: "poster" was matching inside "posters" (Bluesky junk). "artbook"
was matching inside "artbooks" (Planeta description). "cofanetto" was
matching inside "Cofanetti" (Panini source name — see invariant 1).

**Invariant 3: tag comparison is case-insensitive.**
`is_likely_manga` lowercases both sides before comparing against
`_NON_MANGA_TAG_PREFIXES`. External feeds normalize tags differently
than internal expectations.

Why: Manga-Sanctuary ships `type:oav` lowercase; our blacklist had
`type:OAV` mixed-case. 700+ OAV/anime items leaked into the catalog.

**Invariant 4: search-keyword injection is a SCORE boost, not a SIGNAL.**
If `tags` contains `search:X`, `score_candidate` raises the floor to 10
(so the item isn't dropped by `min-score`) but does NOT add `X` to
`signal_types`. The signal belongs to the item, not the search.

Why: items from `[search: boxset]` were inheriting `box_set` signal
even when their title and description had nothing about a boxset.

## Storage layer

### items.jsonl

- Format: JSON Lines (one JSON object per line).
- Semantics: **upsert by URL** (after `normalize_url_for_dedup`).
- Sort: by `detected_at` ascending (oldest first); rows without URL go
  at the end.
- Atomic write via `.tmp` + `rename`. Safe under crash.
- Backup files: `*.pre-compact-bak`, `*.pre-filter-bak`,
  `*.pre-backfill-bak`. All gitignored.

### state.json

- Format: single JSON object, dict-shaped: `{url: snapshot}`.
- Snapshot includes `content_hash`, `first_seen_at`, `last_seen_at`,
  plus a cached copy of title/url/score/source/etc.
- Used ONLY for incremental detection (deciding `new` vs `changed` vs
  `seen`). The web does not read state.json.
- Size: ~7 MB for 3000 items (cache, can be regenerated by re-scraping).

### feedback.jsonl

- Format: JSON Lines, one event per line:
  `{"title": "...", "url": "...", "reason": "...", "submitted_at": "<ISO>"}`.
- Semantics: **append-only**, unlike `items.jsonl`. Each 👎 submission
  is a separate line even if the same URL is flagged twice.
- Writer: `do_POST` in `scripts/serve.py` (the dashboard's 👎 button).
- Reader: a human or an AI assistant that re-evaluates the filter
  rules — no code in the scraper pipeline reads this file. It's a
  one-way feedback channel from the UI back to the maintainer.
- No ISBN field by design (many JP items don't carry one; URL is the
  practical identifier).
- Gitignored along with the rest of `data/`.

### Why JSONL and not SQLite (yet)

Current scale (3000 items, ~3-4 MB) makes SQLite premature. The browser
loads the entire JSONL into memory and filters/sorts in JS in <50ms.

Triggers that would justify the migration (none of these have hit yet):
- Multi-user / deploy → need server-side queries and auth tables.
- ~20k+ items → loading the whole JSONL becomes slow.
- Need price history → append-only events table is natural in SQL.
- Need a notifications worker / cron → shared DB more practical than
  file locking.

The migration would mostly affect `append_jsonl()` (write path), the
`load_items()` in `build_web.py` (read path), and the web's
`loadItems()` (would become HTTP API calls). The 99% of filtering /
scoring / cleaning code lives in Python functions that are independent
of storage.

## Web layer

### How data reaches the dashboard

Two modes, decided at runtime in `loadItems()`:

1. **Inline mode** (after `python scripts/build_web.py`):
   - `<script id="manga-data" type="application/json">[{...}, ...]</script>`
     has the items embedded.
   - Works from `file://` (no server needed).

2. **Fetch mode** (default in repo):
   - `<script id="manga-data" type="application/json">[]</script>` is
     empty.
   - JS falls through to `fetch("../data/items.jsonl")`.
   - Requires `scripts/serve.py` to be running because file:// would
     fail CORS.

In both cases, **`dedupByUrl()` in JS does the ISBN grouping**
(building `sources[]`). The Python `build_web.py` does the same and
sets `sources[]` before embedding — the JS check `if (item.sources)`
respects existing groupings to avoid double-work.

### Server (`scripts/serve.py`)

Custom Python http.server subclass. Serves the project root so
`/data/items.jsonl` is reachable. Redirects `/` and `/index.html` to
`/web/` so the user doesn't type the path.

Also exposes **`POST /api/feedback`** (the only mutating endpoint):

- Body: JSON `{title, url, reason}`. All three required, non-empty.
- Validates length (≤100 kB) and JSON shape; returns `400` otherwise.
- Appends one line to `data/feedback.jsonl` with the payload plus a
  `submitted_at` ISO-8601 UTC timestamp.
- Response: `200 {"ok": true}`.

No auth, no rate limit — this server is local single-user. The endpoint
is intentionally narrow (one path, one method, fixed schema) so it
doesn't grow into a general API.

### Filters, sorting, pagination

All in Alpine.js. Reactive computed properties:
- `unique` — items deduplicated (already done at load).
- `filtered` — applies search box, country, publisher, language,
  productType, sourceClass, minScore, onlyLimited.
- `sorted` — by score_desc / detected_at / title.
- `paginated` — slice of 60 items per page (configurable).
- `visiblePages` — current ± 5, clamped.

URL sync: `_loadPageFromUrl()` on init reads `?page=N`,
`_syncPageToUrl()` on `goToPage()` / `resetFilters()` updates
history without reload.

### Modal

Built from `selectedItem`. Shows cover, badges (multi-source, limited
stock), tag list, signals, fragment of description, and a **`sources[]`
list** if available (each row clickable to the external URL, with its
own price/country/stock).

**Feedback de "mala elección" (botón 👎).** El footer del modal expone
un botón pulgar-abajo que despliega un textarea + "Enviar"/"Cancelar".
`submitFeedback()` (Alpine) hace `fetch("/api/feedback", { method: "POST",
... })` con `{title, url, reason}`. El estado del flujo vive en cinco
propiedades reactivas: `feedbackOpen`, `feedbackReason`, `feedbackSending`,
`feedbackSent`, `feedbackError`. `_resetFeedback()` se llama al abrir/
cerrar el modal para no arrastrar estado entre items.

El handler en el servidor (ver "Server" arriba) hace append a
`data/feedback.jsonl`. Ver también CLAUDE.md → "Feedback de mala
elección" para el propósito (input para revisión con IA de los filtros).

## Wiki parsers

Wikis are sources that need custom parsing logic, not just generic
`extract_listing_candidates`. They live in `scripts/wikis/` and are
invoked via `--bootstrap-wiki <name>`.

All four have the same public API:

```python
def parse_calendar_page(html_text, source_url) -> list[Candidate]:
    """Parse a single page (month, catalog, whatever) into Candidates."""

def fetch_calendar_month(year, month, session, timeout) -> list[Candidate]:
    """Fetch + parse the page for a given (year, month)."""

def iter_year_months(yf, mf, yt, mt) -> list[tuple[int, int]]:
    """Iterate the (year, month) range for bootstrap()."""

def bootstrap(yf, mf, yt, mt, session, sleep_seconds=0.5,
              timeout=(10, 30), min_score=30, fetch_details=False
              ) -> list[Candidate]:
    """Loop over year_months, fetch each, return scored candidates."""
```

`_run_wiki_bootstrap()` in `scripts/manga_watch.py` dispatches to the
right module based on the CLI arg.

### Per-wiki notes

- **listadomanga.py** (ES). URL: `calendario.php?mes=N&ano=YYYY`.
  Structure: `<h2>Editorial</h2>` / `<h2>Date</h2>` / `<table>` of items
  with `<a>title</a> / `<a>author</a>`. Has detail-fetch for
  cover/price.
- **listadomanga_blog.py** (ES — archivo histórico del blog).
  URL: `blog/YYYY/MM/page/N/`. Structure: `div.post.hentry` con
  `<h3><a>title</a></h3>`, `<small>fecha</small>`, `<div class="entry">
  <p>excerpt</p>...</div>`. WordPress estándar, 10 posts/página, archivo
  desde 2009-11.
  **Doble setup** (importante):
  - DIFERENCIAL: source `ES - Listado Manga Blog RSS` (kind:rss) en
    sources.yml — corre en cada scrape regular, trae los ~10 posts
    más recientes vía feed.
  - HISTÓRICO: `--bootstrap-wiki listadomanga-blog --wiki-from 2009-11
    --wiki-to YYYY-MM` — one-shot, recorre todo el archivo. Necesario
    para recuperar items pre-RSS (Hell's Paradise vol 1 Collector FNAC,
    OP100 Celebration que ya está 404 en starcomics, etc.).
- **manga_sanctuary.py** (FR). URL: planning by Unix timestamp range.
  Structure: `<div class="sortie-date">` headers + `<div class="sortie
  post">` post-cards. Has detail-fetch with title-match validation
  (`_title_matches_page`) to guard against URL drift on future
  releases.
- **otaku_calendar.py** (EN/US). URL: `Calendar?month=YYYY-M`
  (note: param IS ignored by the site — only current month available).
  Structure: `<div class="dateListingContainer">` with date text + `<a>`
  items. Filters by country code (US by default).
- **manga_mexico.py** (MX). URL: blog post per publisher (Panini,
  Kamite, Vid). Structure: `<ul><li>title - Volúmenes: X/Y | (Estado)
  | Periodicidad | Precio actual: N MXN</li>`. Generates synthetic URL
  with `?manga=publisher-slug` query so URL-based dedup doesn't collapse
  the whole catalog into one row.

## CLI surface

```
python scripts/manga_watch.py
    --source-classes official,retailer,trusted_media
    --countries Francia,España,Japón
    --include-tags <tag>     (only sources with this tag)
    --exclude-tags <tag>
    --only-tags <tag>
    --min-score 30
    --include-seen           (also re-emit unchanged items)
    --fetch-details          (enrich via per-item HTTP)
    --enable-js              (Playwright for kind:js sources)
    --max-pages 5
    --connect-timeout 10
    --read-timeout 30
    --sleep-seconds 0.5
    --bootstrap-wiki {listadomanga, manga-sanctuary, otaku-calendar, manga-mexico}
    --wiki-from YYYY-MM
    --wiki-to YYYY-MM
    --sitemap-mining-domain <domain>
    --dry-run

python scripts/build_web.py [--input ...] [--output ...] [--clear]
python scripts/serve.py [--port 8000]
python scripts/retrofit/clean_titles.py [--dry-run]
python scripts/retrofit/filter_non_manga.py [--dry-run]
python scripts/retrofit/backfill_metadata.py [--only image_url] [--sleep 0.3]
                                              [--max-per-source N] [--limit N]
                                              [--skip-source X] [--skip-domain Y]
```

## Tests

`tests/test_extraction.py` — 159 tests, runtime <1s.

Coverage areas:
- `clean_title()` — every junk pattern has a test with a real example
  from the corpus.
- `is_likely_manga()` — strong/pack/hard/soft cases, source purity
  variants, real titles reported by the user.
- `_extract_label_value_pairs()` — `<li><span>`, `<dt>/<dd>`, `<tr>`
  structures in 3 languages.
- `_fix_mojibake()` — strict round-trip + fallback pair.
- `append_jsonl()` — upsert with and without URL.
- Each wiki parser has happy-path tests with realistic HTML.
- Listing extractor edge cases (next-page, cross-origin, broken anchors).

Run: `.venv/bin/python -m pytest tests/test_extraction.py -q`.

## Performance baselines

| Operation | Time | Notes |
|---|---|---|
| Full scrape (no detail-fetch) | 5-15 min | depends on enabled sources |
| Full scrape (with `--fetch-details`) | 30-90 min | network-bound |
| `--bootstrap-wiki listadomanga` (12 months) | 3-5 min | |
| `append_jsonl` upsert (3000 items) | ~50 ms | atomic |
| `filter_non_manga` retroactive | <1 s | in-memory |
| `clean_titles` retroactive | <1 s | in-memory |
| `backfill_metadata` (1000 items) | 5-10 min | network-bound |
| Web initial load | <1 s | 3.6 MB JSONL → parse + dedup → render |
| Web filter/search/page navigation | <50 ms | client-side |

If a number above doubles after a change, something regressed.
