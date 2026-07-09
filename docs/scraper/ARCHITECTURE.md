# Architecture

Deep dive into how PandaWatch's pipeline works end-to-end.
Read `CLAUDE.md` first for the high-level orientation.

## Components

```
┌──────────────────────────────────────────────────────────────┐
│                       sources.yml                            │
│  138 entries (76 enabled) × {country, language, kind,         │
│  selectors, search_template?, keywords?, tags, purity}       │
│  kinds: html | rss | js | bluesky                            │
└──────────────────────────┬───────────────────────────────────┘
                           │
        ┌──────────────────┼───────────────────┐
        │                  │                   │
        ▼                  ▼                   ▼
┌───────────────────┐ ┌──────────────────┐ ┌─────────────────────┐
│  Source loop      │ │  Wiki bootstrap  │ │ Search discovery    │
│  manga_watch.py   │ │  (--bootstrap-   │ │ (retrofit/search_   │
│  ThreadPoolExec.  │ │   wiki <name>)   │ │  discovery.py)      │
│  --workers N      │ │                  │ │                     │
│  --per-host-limit │ │  scripts/wikis/  │ │  Gemini grounding   │
│                   │ │   listadomanga   │ │  → Tavily fallback  │
│  • extract_listing│ │   listadomanga_  │ │  → DuckDuckGo HTML  │
│  • extract_rss    │ │     blog (hist.) │ │  (priorities live   │
│  • extract_bluesky│ │   manga_sanctuary│ │   in data/search_   │
│  • sitemap miner  │ │   otaku_calendar │ │   queries.yml)      │
│  (kind:js → Play- │ │   manga_mexico   │ │                     │
│  wright via dedic.│ │   whakoom (opt-  │ │                     │
│  worker+queue)    │ │     in spider)   │ │                     │
└─────────┬─────────┘ └─────────┬────────┘ └─────────┬───────────┘
          │                     │                    │
          └──────────────┬──────┴────────────────────┘
                         ▼
       ╔════════════════════════════════════════════╗
       ║  Filtering & scoring layer (manga_watch)   ║
       ║                                            ║
       ║  clean_title() ─ junk, suffixes, mojibake  ║
       ║  detect_signals() ─ 0-300, word-boundary   ║
       ║                     regex (NOT substring)  ║
       ║  is_likely_manga() ─ 4-rule cascade        ║
       ║  is_pure_novel() ─ URL+word indicators     ║
       ║  is_comic_not_manga() ─ comics blacklist   ║
       ║                         (manga bypass)     ║
       ║  is_collectible_edition() ─ 2nd gate       ║
       ║                         (regular tomos     ║
       ║                          rejected)         ║
       ║  fetch_metadata_from_detail() ─ opt-in     ║
       ║                                 per-item   ║
       ║                                 HTTP (also ║
       ║                                 parallel)  ║
       ║  derive_cluster_key() ─ isbn / fuzzy /    ║
       ║                         url, persisted     ║
       ║                         on each row        ║
       ╚════════════════════╤═══════════════════════╝
                            │
                            ▼
       ┌──────────────────────────────────────────┐
       │  process_state(): diff vs state.json     │
       │  • new       → write to items.jsonl      │
       │  • changed   → upsert in items.jsonl     │
       │  • seen      → skip                      │
       └──────────────────┬───────────────────────┘
                          │
                          ▼
       ┌──────────────────────────────────────────┐
       │  mirror_candidate_images() ─ Fase 1      │
       │  download cover → data/images/, set      │
       │  image_local (image_store.py).           │
       │  Skipped by --skip-image-download.       │
       └──────────────────┬───────────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
      ┌───────────────┐       ┌──────────────────────┐
      │ state.json    │       │  items.jsonl         │
      │ (cache, ~7MB) │       │  (1 fila/producto,   │
      │ url → snapshot│       │   sources[] + cluster_key)│
      └───────────────┘       └────────┬─────────────┘
                                       │
                                       ▼
                         ┌────────────────────────────┐
                         │   build_web.py             │
                         │   • normalize URLs         │
                         │   • group by cluster_key   │
                         │     (isbn / fuzzy / url)   │
                         │   • build sources[]        │
                         │   • embed in index.html    │
                         │     (or leave [])          │
                         └─────────────┬──────────────┘
                                       │
                                       ▼
                         ┌────────────────────────────┐
                         │  web/index.html            │
                         │  + scripts/serve.py        │  ← PUBLIC,
                         │                            │    bind 0.0.0.0
                         │  http://localhost:8000     │    DEPLOYABLE
                         │  + POST /api/feedback      │
                         └────────────────────────────┘

Operación / panel admin (separado, no deployable):
                         ┌────────────────────────────┐
                         │  admin/index.html          │
                         │  + scripts/admin_serve.py  │  ← LOCAL,
                         │  + scripts/script_registry │    bind 127.0.0.1
                         │                            │    NEVER DEPLOY
                         │  http://localhost:8001     │
                         │  GET /api/scripts          │
                         │  POST /api/run             │
                         │  GET /api/jobs/<id>/stream │
                         │       (Server-Sent Events) │
                         └────────────────────────────┘
                         (scripts/run_local.sh lanza ambos en paralelo)

Orchestration (canonical pipelines):
  scripts/scrape_delta.sh  — incremental (diaria/semanal, ~30-60 min).
    listadomanga via calendario.php (últimos 3 meses) + resto de wikis
    → cleanup retrofits → build_web.
  scripts/scrape_full.sh   — refresh completo (mensual/trimestral, ~2-4 h).
    listadomanga via lista.php (~3432 colecciones) + mangavariant sitemap
    → cleanup retrofits → build_web.
  scripts/overnight_run.sh — DEPRECATED, alias de scrape_delta.sh.
  Per-phase logs land in logs/overnight-<ts>/ (o scrape-<ts>/).

Observability: scripts/audit/source_health.py parses N recent run
  logs and classifies sources (broken_http / broken_skip /
  selector_dead / low_yield / declining / healthy / unseen) —
  markdown or JSON output.
```

## Data flow per scrape

The main loop in `manga_watch.py` dispatches each enabled source to
`_scrape_one(index, source)`, run either serially (`--workers 1`,
default) or concurrently in a `ThreadPoolExecutor` (`--workers N`).
A per-host `threading.Semaphore` (default size 2 via
`--per-host-limit`) wraps the HTTP calls so the same domain never
receives more than N concurrent requests. `kind: js` sources are
dispatched via a dedicated **Playwright worker thread + queue**
(`_PLAYWRIGHT_WORKER` / `_PLAYWRIGHT_QUEUE`) because
`playwright.sync_api` greenlets are bound to the thread that called
`sync_playwright().start()` and cannot switch threads safely. Workers
call `fetch_with_playwright(url, ...)` which puts a job on the queue
and blocks until the worker thread returns the result. See CLAUDE.md
gotcha #12 for the full story.

All `requests` traffic (main scrape, wiki bootstraps, `--fetch-details`,
image mirror) goes through the shared session from `make_session()`, which
mounts an `HTTPAdapter` with automatic **retries for transient failures**
(2026-06-10): `Retry(total=3, connect=2, read=2, backoff_factor=1.5)` on
GET/HEAD for status 429/500/502/503/504, honoring `Retry-After`. Before
this, a single TCP reset or 5xx blip silently dropped the whole source
(or a whole listadomanga collection) from the run. Retries happen inside
the adapter while the per-host semaphore is held, so the per-host
concurrency limit still applies during retries. Non-retryable statuses
(404, 403 anti-bot) fail immediately as before — `raise_on_status=False`
keeps the `raise_for_status()` semantics of every caller intact. The
adapter also raises the connection pool to 32/32 (default 10) to avoid
"connection pool is full" discards under `--workers 8`.

Per-source pipeline:

1. **Fetch.**
   - `kind: html` → `requests.get(url)` via `fetch_with_metadata`.
     Follows pagination if a "next" link is detected (heuristic in
     `find_next_page_url`).
   - `kind: rss` → `feedparser.parse(url)`.
   - `kind: bluesky` → derives the handle from a `bsky.app/profile/X`
     URL via `bluesky_handle_from_url`, calls the public XRPC endpoint
     `public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed`
     (`bluesky_api_url`), and parses posts via
     `extract_bluesky_posts`. No auth required.
   - `kind: js` → Playwright (requires `--enable-js` flag at CLI;
     dispatched via `_PLAYWRIGHT_QUEUE` to the dedicated worker thread).
   - `kind: wiki` → not in this loop; activated via `--bootstrap-wiki`.

2. **Parse candidates.**
   - `extract_listing_candidates(soup, source)` walks cards using
     `item_selector` from source.selectors (or auto-detected).
     Returns `Candidate` objects with title, url, description, image_url.
   - `extract_rss(source, feed_text)` walks RSS entries.
   - `extract_bluesky_posts(source, json_text)` walks `feed[].post`.

3. **Filter and score.**
   - `clean_title(title)` strips junk prefixes/suffixes/mojibake.
   - `is_likely_manga(title, description, tags, source_purity)` —
     4-rule cascade. If False, skip.
   - `is_pure_novel(title, description, url)` — rejects pure light
     novels via URL hints + indicator words (`light novel`, `ノベル`,
     etc.); bypassed if the title matches a manga-adaptation pattern
     or signals an artbook.
   - `is_comic_not_manga(title, publisher)` — comics blacklist
     (`data/comics_blacklist.yml`: Marvel/DC publishers + franchise/
     format keywords). Applied ALWAYS, regardless of source purity;
     bypassed when title literally contains "manga" (Batmanga survives).
   - `score_candidate(candidate)`:
     - `detect_signals(blob)` scans for keywords ("kanzenban",
       "deluxe edition", "exclusive variant", "limited", …) via
       cached word-boundary regex (`_phrase_pattern`).
     - Adds bonus by source_class (official +5, retailer +4, social -5).
     - Clamps to [0, 300].
     - Populates `candidate.signals`, `signal_types`, `product_type`,
       `stock_type`.

4. **Detail enrichment** (opt-in via `--fetch-details`):
   - For each eligible candidate (`new`/`changed`, score >= threshold,
     missing author or image, official/retailer source),
     `fetch_metadata_from_detail(url, session, timeout)` does another
     HTTP call. Under `--workers > 1` these calls also run in a
     `ThreadPoolExecutor` with the same per-host semaphore; metadata
     application back to the candidates is serialized after the pool
     drains so state mutations stay race-free.
   - Extracts `name`, `author`, `image_url`, `isbn`,
     `release_date`, `publisher`, `description` via:
       1. JSON-LD `<script type="application/ld+json">`
       2. OpenGraph / Twitter meta tags
       3. `_extract_label_value_pairs(soup)` — recognizes
          `<li><span>label</span>value</li>`, `<dt>/<dd>`, `<tr>` with
          multilingual labels (FR/ES/EN/IT/JP). This is the workhorse
          for sites like Manga-Sanctuary, Pika, Glénat, Sanyodo.
       4. OG/title fallback chain for sites without JSON-LD (Whakoom).
       5. Body text fallback (regex).

5. **Collectible-edition gate** (`is_collectible_edition`):
   - Project scope is **only** special editions, variants, deluxe,
     limited, box sets, artbooks, fanbooks, magazines. Regular tomos
     are dropped here.
   - Logged as `[GATE] N/M candidatos descartados por no ser edición
     coleccionable`.

6. **State diff.**
   - `process_state(candidates, state, min_score, include_seen)`:
     - Compute `content_hash` per candidate (sha256 of key fields).
     - Compare to `state.json[url].content_hash`:
       - URL not in state → status `"new"`.
       - URL in state, hash differs → status `"changed"`.
       - URL in state, hash same → status `"seen"` (skip unless
         `--include-seen`).
     - Update state[url] with new snapshot.

7. **Incremental flush** (resilience, added 2026-05-26):
   - `flush_source_candidates(candidates, state, items_path, min_score)`
     is called immediately after EACH source finishes (both in serial
     mode and inside `as_completed()` in the parallel pool). It applies
     the same `is_collectible_edition` gate as `process_state()` and
     writes passing candidates to `items.jsonl` via `append_jsonl`.
   - Does NOT update `state` — that still happens in step 6 at the end
     of the full run. If the process is killed mid-run, every source
     completed so far is already persisted; the next run re-processes
     only the remaining sources.
   - The final `append_jsonl` call in step 8 is idempotent — it upserts
     the enriched fields (from detail-fetch) over what the flush wrote.
   - See gotcha #32 in CLAUDE.md for details and tests.

8. **Image mirror** (Image storage Fase 1, on by default,
   `--skip-image-download` to opt out):
   - `mirror_candidate_images(reportable, data_dir, session, ...)`
     downloads EACH image of every `new`/`changed` candidate to
     `data/images/<sha256(url)[:16]>.<ext>` and sets the entry's `local`
     in `images[]` (`images[0]` = cover). The remote `url` stays as
     provenance + fallback. (`candidate.image_url`/`image_local` are
     runtime-only inputs; `candidate_to_json` folds them into `images[0]`.)
   - Parallelized with `ThreadPoolExecutor` (same `--workers`).
     Idempotent: a file already on disk is reused without a request.
     Magic-byte validation rejects non-image responses (anti-bot HTML).
   - Pure download primitives live in `scripts/image_store.py`.
   - See "Image storage" in CLAUDE.md for the full design + Fase 2 (R2).

8. **Persist.**
   - `candidate_to_json(candidate)` builds the row and stamps
     `cluster_key = derive_cluster_key(row)` on every write — so the
     dashboard's grouping logic works without re-parsing titles in JS.
   - `append_jsonl(items_path, new_or_changed)`:
     - Read existing items.jsonl into a dict keyed by
       `normalize_url_for_dedup(url)`.
     - Upsert each row (last-wins by detected_at). The cover's `local`
       (`images[0].local`) is sticky via the `images[]` union-merge — a
       re-scrape that did not download keeps the old mirror.
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
- Semantics (cambio 2026-06-02): **una fila por PRODUCTO** (cluster), no por
  URL. `append_jsonl` hace upsert por URL normalizada, luego **consolida por
  `cluster_key`** (`consolidate_by_cluster`) → cada producto queda en UNA fila
  con un array **`sources[]`** (todas las fuentes donde se encontró: name, url,
  price, country, stock_type, image_url…). Un producto re-encontrado en otra
  fuente NO agrega fila: suma su entrada a `sources[]` (sticky+merge, preserva
  hermanas). El merge vive en `manga_watch.merge_cluster` / `source_entry`
  (fuente única de verdad; también lo usan build_web y `consolidate_sources.py`).
  `cluster_key` no es estable hasta `/watch-standardize-catalog` (asigna edition_key),
  por eso `consolidate_sources.py` re-consolida como paso `[4g]` del pipeline.
- Sort: by `detected_at` ascending (oldest first); rows without URL go
  at the end.
- Atomic write via `.tmp` + `rename`. Safe under crash.
- **Every row carries `cluster_key`** (string) computed by
  `derive_cluster_key(row)` inside `candidate_to_json`. Used by
  `build_web.py` and `web/index.html` to consolidate multi-source
  cards. See "Cluster key" section above.
- Backup files: created by `backup_and_rotate(path, label, max_keep=3)`
  in `manga_watch.py`. Stored under `data/backups/<filename>/` (e.g.
  `data/backups/items.jsonl/`). Rotates automatically to keep the last 3
  backups per family; the oldest is deleted when the limit is exceeded.
  All gitignored via `data/backups/` in `.gitignore`.

Row schema (the fields written by `candidate_to_json`):

```jsonc
{
  "detected_at":   "ISO-8601 UTC timestamp",
  "status":        "new | changed",
  "score":         0-300,
  "signals":       ["human readable, e.g. 'limited edition'", ...],
  "signal_types":  ["limited", "deluxe", "box_set", ...],
  "title":         "display canonical (international, standardized)",
  "title_original":"original scraped title (cleaned, pre-standardization)",
  "url":           "absolute URL",
  "source":        "source name from sources.yml",
  "source_url":    "source listing page",
  "source_class":  "official | retailer | trusted_media | social",
  "publisher":     "publisher name",
  "country":       "country in Spanish",
  "language":      "language in Spanish",
  "tags":          ["from sources.yml + search:KEYWORD if expanded"],
  "published_at":  "ISO timestamp from RSS or empty",
  "description":   "extracted description (original, never modified — detect_signals reads this)",
  "description_es":"Spanish translation of description (set by translate_descriptions.py retrofit)",
                   // empty string when description is already ES or translation failed.
                   // Frontend shows description_es when non-empty, falls back to description.
  "content_hash":  "sha256 for state-diff",
  // Portada = images[0] (única fuente de verdad, 2026-06-09). NO hay campos
  // top-level image_url/image_local en el item. Cada entry de images[] lleva
  // url (remota, provenance+fallback) + local (filename en data/images/).
  "images":        "[{url, local, kind:gallery|extra, description}] — images[0] = portada",
  "release_date":  "ISO date or empty",
  "product_type":  "manga | artbook | fanbook | magazine | boxset | ...",
  "author":        "extracted author or empty",
  "stock_type":    "regular | limited | exclusive | preorder | ...",
  "isbn":          "ISBN-13 if extracted",
  "cluster_key":   "isbn:<X> | edition:<edition_key>|<volume> | fuzzy:lang|series|vol|tier|publisher | url:<X>",
                   // Four tiers (priority order): isbn beats edition beats fuzzy beats url.
                   // edition: tier added 2026-05-24 for box sets with same edition_key but no ISBN.

  // --- Series/edition schema (added 2026-05-22, see CLAUDE.md gotcha #21) ---
  "series_key":    "canonical work id (e.g. 'demon-slayer', 'one-piece')",
  "series_display":"display name of the work (e.g. 'Demon Slayer')",
  "edition_key":   "{series}-{publisher}-{edition_slug}, e.g. 'berserk-darkhorse-deluxe'",
  "edition_display":"display name e.g. 'Deluxe Edition (Dark Horse)'",
  "volume":        "string '1' | '100' | '1-3' for sets | '' for one-shots",
  "standardized_at":"ISO-8601 UTC, set ONLY by /watch-standardize-catalog skill",

  // --- Human approval / golden records (added 2026-06-01, see CLAUDE.md "Aprobación humana") ---
  "approved_at":   "ISO-8601 UTC. Presence = the owner approved this card as
                    correct from the dashboard. Empty/absent = unreviewed.
                    Sticky (part of _CURATED_FIELDS). When set, append_jsonl
                    FREEZES all descriptive metadata on re-scrape and only
                    refreshes _VOLATILE_FIELDS (stock_type/sources/
                    detected_at). Retrofits + skills skip approved items by
                    default. Set per-CLUSTER by POST /api/approve and per-EDITION
                    by POST /api/approve-edition. Also logged to approvals.jsonl
                    for durable replay (apply_approvals.py).",
  "approved_by":   "'owner' when approved, '' when cleared.",

  // --- URL slug for Next.js app (added 2026-05-27, see docs/web-next/FRD-006-slug-generation.md) ---
  "slug":          "URL-safe unique key for /item/[slug] route in web-next.
                    Generated by scripts/retrofit/generate_slugs.py.
                    Priority: isbn cluster_key → edition_key+volume →
                    edition_key only → isbn field → item-{sha1(url)[:12]}.
                    Collision-safe (oldest keeps clean slug, newer gets -b/-c).
                    Set ONLY by generate_slugs.py (not by scraper or skill).
                    Sticky in append_jsonl for ALL rows: a re-scrape never
                    leaves slug=None (gotcha #65).",

  // --- Multi-image carousel (added 2026-05-26, Image storage Fase 1+2) ---
  "images": [
    {
      "url":         "absolute remote URL",
      "local":       "filename in data/images/ or empty",
      "kind":        "cover | gallery | extra | variant_cover | back_cover",
      "description": "short label e.g. 'Tomo 3' or '' for cover"
    }
  ],

  // --- Extras/bonuses linked to the item (added 2026-05-23, LMC Fase 2) ---
  "extras": [
    {
      "description":    "original text, language of the source",
      "description_es": "Spanish translation (set by translate_descriptions.py)",
                        // empty string when already ES or translation failed.
      "release_date":   "ISO date or empty",
      "source_section": "h2 section label from the wiki source"
    }
  ],

}
```

After `wayback_recover.py`, recovered rows also carry:
`recovered_from_wayback: true`, `wayback_snapshot_url`, `wayback_timestamp`.

#### Two-pass standardization (gotcha #21)

The schema fields `series_key`, `edition_key`, `volume`, `title_standardized`
get populated in **two passes**:

1. **Pass 1 — scraper rough assignment** (`candidate_to_json` →
   `derive_series_metadata`): regex-based heuristic over title +
   publisher + signal_types. Uses `_extract_volume`,
   `_normalize_series_name`, `_variant_tier`, `_publisher_slug`.
   Defensive: returns empty dict for obviously-garbage cases
   (series_key < 3 chars, all digits, trailing-number pattern).
   **Does NOT set `standardized_at`** — items remain marked "pending".

2. **Pass 2 — `/watch-standardize-catalog` skill** (manual, parallel
   subagents): processes items WITHOUT `standardized_at`. Subagents
   re-derive everything from scratch via LLM, fix scraper errors,
   apply `canonical_series_key()` for multilingual consolidation,
   move non-manga to `data/non_manga_blacklist.jsonl`, dedup by
   `(series_key, edition_key, volume)`, mark with `standardized_at`.

`title_original` is preserved by both passes: pass 1 writes it equal
to the cleaned scraped title; pass 2 backs up `title` to `title_original`
(if empty) before overwriting `title` with the standardized form.

### data/images/ — local cover mirror (Image storage Fase 1)

- Directory under `data/`, gitignored via its own `data/images/`
  entry in `.gitignore` (`data/` is not ignored wholesale).
- One file per unique image: `<sha256(url)[:16]>.<ext>`.
  Deterministic — a re-scrape of the same image reuses the file.
- Extension comes from the downloaded bytes' magic signature, not the
  URL. A non-image response (anti-bot HTML page) is rejected and the
  entry's `local` stays empty.
- Written by `mirror_candidate_images()` (orchestration in
  `manga_watch.py`) using the primitives in `scripts/image_store.py`.
- The JSONL stores only the **filename** in each `images[].local` — the base
  path is environment config (`../data/images/` locally; a Cloudflare
  R2 public URL in Fase 2). The row stays deploy-agnostic.
- Backfilling the historic corpus and a mark-and-sweep GC for orphaned
  files are handled by the retrofit `scripts/retrofit/mirror_images.py`
  (backfill downloads covers for pre-Fase-1 items; GC quarantines or
  deletes files no item references). See CLAUDE.md "Image storage".

### Translation layer — `description_es` / `extras[].description_es`

**Status: IMPLEMENTED** — `scripts/retrofit/translate_descriptions.py`

#### Problem

The corpus spans 13 countries and 8 languages. Descriptions scraped from
source pages arrive in the native language of the source: Japanese for
Sumikko/BooksPrivilege/Rakuten, German for Manga-Passion, French for
Manga-Sanctuary/Glénat/Ki-oon, Italian for AnimeClick/SocialAnime,
Vietnamese for Vietnamese sources, Thai for Thai sources, English for
US/UK sources. Only the owner (ES speaker) reads the dashboard; most of
these descriptions are unreadable without translation.

#### Fields added to items.jsonl

| Field | Scope | Description |
|---|---|---|
| `description_es` | top-level | Spanish translation of `description`. Empty string when `description` is already ES, when translation failed, or when `description` is empty. |
| `extras[].description_es` | per-extra | Spanish translation of `extras[].description`. Same empty-string semantics. |

`description` (original) is **never modified** — `detect_signals` runs on
it and modifying it would invalidate stored `signal_types`. Same rule for
`extras[].description`.

#### Naming convention — `description_{lang_code}`

The suffix uses **ISO 639-1** language codes. Today only `_es` is
generated. Adding `_en`, `_fr`, etc. in the future follows the same
pattern without schema changes — just new fields. This makes the design
multi-language-ready at zero extra cost.

#### Translation services

| Priority | Languages | Service | Rationale |
|---|---|---|---|
| PRIMARY | All languages | **Google Translate** via `deep-translator` | Free unofficial endpoint, no API key required, no usage limits. Works for every language in the corpus including VI and TH. |
| UPGRADE (optional) | DE, FR, IT, JP, EN, PT, ZH, KO and more | **DeepL Free API** | If `DEEPL_API_KEY` is present in `.env`, DeepL is tried first for supported languages (better quality). Falls back to Google if DeepL fails or has no credits. |

**Important**: DeepL's free plan provides a **one-time credit of 1M characters**
(not a monthly renewal). Once exhausted, the script continues working via
Google Translate without any code change or configuration update.

Language routing:
```python
def translate_to_es(text, deepl_translator):
    lang = langdetect.detect(text)          # detect source language
    if lang == 'es':
        return ""                            # already Spanish, skip

    # Upgrade path: DeepL (if available and lang supported)
    if deepl_translator is not None and lang in _DEEPL_SOURCE_LANGS:
        result = deepl_client.translate_text(text, target_lang="ES").text
        if result:
            return result
        # DeepL failed → fall through to Google

    # Guaranteed path: Google Translate (always works, no key)
    return GoogleTranslator(source='auto', target='es').translate(text)
```

#### Dependencies

```
# Required:
deep-translator   # pip install deep-translator  (Google Translate wrapper)
langdetect        # pip install langdetect        (language detection)

# Optional (quality upgrade):
deepl             # pip install deepl             (official DeepL SDK)
                  # + DEEPL_API_KEY in .env
```

`deep-translator` and `langdetect` are the only required packages.
`deepl` is strictly optional — the script runs without it.

#### Retrofit script: `translate_descriptions.py`

Lives at `scripts/retrofit/translate_descriptions.py`. Behavior:
- Iterates all items in `items.jsonl`.
- For each item, translates `description` → `description_es` if
  `description_es` is missing or empty AND `description` is non-empty.
- For each `extras[]` entry, translates `description` → `description_es`
  under the same condition.
- Skips items where `description` is already Spanish (detected via
  `langdetect` — threshold `lang == 'es'`).
- Writes back in-place (per-row update, only the translated fields change;
  el modelo 1-fila-por-producto con sources[] no se altera).
- Flags: `--dry-run`, `--limit N`, `--workers N` (parallel calls, default 4),
  `--force` (re-translate even if `description_es` already set),
  `--sleep` (pause between API calls, default 0.15s).
- New items from the scraper will NOT have `description_es` — re-run the
  retrofit periodically (or after large scrapes).

#### `append_jsonl` stickiness

`description_es` is in `_CURATED_FIELDS` in `append_jsonl` — a re-scrape
of a standardized item will not wipe translations written by the retrofit.
For non-standardized items, `description_es` also has sticky behavior:
if the incoming row has no `description_es` but the existing row does,
the existing value is preserved.

Since gotcha #65 (2026-06-10) `_CURATED_FIELDS` also includes `slug`,
`detected_at`, `score`, `signals` and `signal_types`: a re-scrape must not
degrade a standardized row (post-standardization truth lives in the derived
edition label, not in the raw text — gotcha #61). The standardized merge
re-derives `cluster_key` AFTER restoring the curated fields, so the row
stays at the `edition:` tier and the CLKEY invariant
(`stored == derive_cluster_key(item)`) holds without manual repair.
`slug` is additionally sticky for ALL rows (like `description_es`): the
scraper never produces slugs, only `generate_slugs.py` does.

#### Frontend behavior

`web/index.html` modal: display `description_es` when non-empty, else
fall back to `description`. No UI changes needed beyond the field
selection — the template already handles the conditional.

### unmapped_series.jsonl

Append-only log written by `series_aliases.log_unmapped_series()` (called
from `candidate_to_json`) every time a candidate produces a `series_key`
that is NOT a canonical entry in `data/series_aliases.yml`. The
`/watch-enrich-series-aliases` skill consumes this queue.

Schema (one record per line):
```jsonc
{
  "series_key":     "non-canonical key (e.g. 'apothicaire')",
  "series_display": "display name as detected",
  "sample_title":   "title from the first item that triggered the log",
  "sample_url":     "url from the first item",
  "source":         "scrape source",
  "detected_at":    "ISO-8601 UTC"
}
```

Dedup-by-key within a single scrape run (in-memory set
`_UNMAPPED_LOGGED_THIS_RUN`). Across runs, duplicates accumulate —
the `/watch-enrich-series-aliases` skill aggregates by `series_key` when
processing.

### non_manga_blacklist.jsonl

Items that the `/watch-standardize-catalog` skill identified as NOT manga
get moved here (instead of staying in items.jsonl). Append-only. The
skill is idempotent: checks existing URLs before appending.

Schema:
```jsonc
{
  "url":         "the original URL",
  "title":       "original title at time of removal",
  "source":      "scrape source",
  "publisher":   "publisher name",
  "reason":      "human-readable: 'Western indie comic', 'light_novel', ...",
  "reviewed_at": "ISO-8601 UTC of skill run"
}
```

Mangavariant items are NEVER moved to blacklist (owner policy: all
Mangavariant entries are valid manga regardless of detected signals).

### series_aliases.yml

YAML mapping canonical series_keys to their display name + all known
aliases (multilingual). Source of truth for `canonical_series_key()`.

```yaml
demon-slayer:
  display: Demon Slayer
  aliases:
    - kimetsu no yaiba
    - 鬼滅の刃
    - guardianes de la noche
    - demon slayer: kimetsu no yaiba
```

- Lookup is **exact-match-only** on `series_key` and `series_display`
  normalized (lowercase, no diacritics, slug form). NO substring match
  on titles — avoids false positives like "Monster Musume → Monster".
- The aliases list contains: canonical display, all known
  romanizations, native JP characters, FR/ES/IT publisher-specific
  titles.
- Initially populated via Anilist API (~106 entries). Maintained
  incrementally via `/watch-enrich-series-aliases` skill processing the
  unmapped queue.

### state.json

- Format: single JSON object, dict-shaped: `{url: snapshot}`.
- Snapshot includes `content_hash`, `first_seen_at`, `last_seen_at`,
  plus a cached copy of title/url/score/source/etc.
- Used ONLY for incremental detection (deciding `new` vs `changed` vs
  `seen`). The web does not read state.json.
- Size: ~7 MB for 3000 items (cache, can be regenerated by re-scraping).

### feedback.jsonl

Feedback that the owner left via the 👎 button in the dashboard modal.
The item is **not removed** from `items.jsonl` — feedback is informational.
When 👎 is submitted:

1. JS posts `{title, url, reason}` to `POST /api/feedback` in `scripts/serve.py`.
2. `_log_feedback(url, reason)` looks up the full item in `items.jsonl` by URL,
   then appends the complete item record + `reason` + `submitted_at` to
   `data/feedback.jsonl`.
3. Returns `{"ok": true}`.
4. JS shows a brief confirmation and closes the feedback panel. Item stays visible.

Schema: all fields of the original `items.jsonl` row, plus:
```jsonc
{
  "reason":       "free-text from the user",
  "submitted_at": "ISO-8601 UTC"
}
```

- **Append-only** — one line per feedback submission.
- **Reader**: the `/watch-review-feedback` skill — reads the queue, categorizes
  root causes (A–J filter issues + K–N data quality), proposes fixes,
  applies approved changes, and truncates the queue.
- Gitignored.

### approvals.jsonl

Durable, append-only log of the cards the owner **approved** (golden records)
from the dashboard. Complements the `approved_at`/`approved_by` fields written
into `items.jsonl`: those live in the regenerable catalog, this log survives a
from-scratch rebuild.

- Written by `POST /api/approve` (one entry per cluster) and
  `POST /api/approve-edition` (one entry per affected cluster) in `serve.py`.
- One line per approve/unapprove action. Schema:
  ```jsonc
  {
    "cluster_key":  "edition:<key>|<vol> | isbn:<X> | url:<X>",
    "url":          "canonical item URL",
    "action":       "approve | unapprove",
    "approved_at":  "ISO-8601 UTC (empty when unapprove)",
    "approved_by":  "owner | ''",
    "reason":       "free-text / 'bulk edition: <key>'",
    "submitted_at": "ISO-8601 UTC",
    "series_key": "...", "edition_key": "...", "title": "...", "volume": "..."
  }
  ```
- **Reader / replay**: `scripts/retrofit/apply_approvals.py` reduces the log to
  the final state per cluster_key (last-wins) and re-applies `approved_at` to a
  freshly rebuilt `items.jsonl` (match by cluster_key, fallback url). Idempotent.
- Gitignored.

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

In both cases, **`dedupByUrl()` in JS does the cluster_key grouping**
(building `sources[]`). It reads `item.cluster_key` directly (precomputed
in the JSONL) — for legacy rows without the field it falls back to ISBN
or `url:<url>`. The Python `build_web.py:_group_by_cluster_key` does the
same on the embed path — the JS check `if (item.sources)` respects
existing groupings to avoid double-work. Both code paths share the same
key semantics: ISBN authoritative, then fuzzy
`lang|series|vol|variants|publisher`, then standalone `url:`.

### Two-server architecture (público + admin)

Hay **dos** procesos HTTP separados a propósito:

|  | Server | Bind | Puerto | Sirve | Deploy |
|---|---|---|---|---|---|
| Público | `scripts/serve.py` | `0.0.0.0` | 8000 | `web/`, `data/`, `POST /api/feedback` | ✅ |
| Admin (panel) | `scripts/admin_serve.py` | `127.0.0.1` | 8001 | `admin/index.html`, `/api/scripts`, `/api/run`, `/api/jobs/*` (SSE), `/api/jobs/*/stop` | ❌ |

El público está pensado para deploy (estático + endpoint de feedback).
El admin ejecuta subprocesos arbitrarios (`subprocess.Popen` de los
scripts del registry) — exponerlo sería RCE. La separación física
(otro proceso, otro puerto, otro bind, otro directorio) lo blinda
contra "olvidé deshabilitar algo".

`scripts/run_local.sh` lanza ambos en paralelo para uso diario.

Detalle completo del panel admin (API, job manager, registry, modelo
de seguridad, troubleshooting): **[`docs/admin/README.md`](../admin/README.md)**.

### Server público (`scripts/serve.py`)

Custom Python http.server subclass. Serves the project root so
`/data/items.jsonl` is reachable. Redirects `/` and `/index.html` to
`/web/` so the user doesn't type the path.

Also exposes **`POST /api/feedback`** (the only mutating endpoint):

- Body: JSON `{title, url, reason}`. All three required, non-empty.
- Validates length (≤100 kB) and JSON shape; returns `400` otherwise.
- Calls `_log_feedback(url, reason)`:
  - Looks up the full item in `items.jsonl` by URL.
  - Appends the complete item record + `{reason, submitted_at}` to
    `data/feedback.jsonl`. Does NOT modify `items.jsonl`.
- Response: `200 {"ok": true}`.

No auth, no rate limit — single-user local. El endpoint es
intencionalmente angosto (un path, un método, schema fijo) así no se
convierte en una API general.

### Server admin (`scripts/admin_serve.py`)

`ThreadingTCPServer` (un thread por request → soporta múltiples SSE +
GET/POST en paralelo). Sirve `admin/index.html` como root y expone:

- `GET /api/scripts` — devuelve el contenido de
  `scripts/script_registry.py` tal cual.
- `POST /api/run` — valida `{script_id, flags}` contra el registry y
  lanza `subprocess.Popen(cmd, cwd=ROOT, stdout=PIPE, stderr=STDOUT,
  PYTHONUNBUFFERED=1)`. Devuelve `job_id`.
- `GET /api/jobs` y `/api/jobs/<id>` — listado y detalle (con líneas
  de log bufferizadas).
- `GET /api/jobs/<id>/stream` — Server-Sent Events: reenvía las líneas
  bufferizadas y sigue pusheando las nuevas. Cierra con un evento
  `end` cuando el job termina.
- `POST /api/jobs/<id>/stop` — SIGTERM, luego SIGKILL a los 3s.

**Allowlist por construcción**: solo se aceptan `script_id` y flags
que estén en `script_registry.py`. No hay `shell=True` en ningún lado;
los argumentos se pasan como `list[str]` a `Popen`, así que aunque el
usuario meta `;rm -rf /` en un input, llega como argumento literal.

**Job manager**: dict global de `Job` (uuid corto). Cada `Job` tiene
`status`, `lines: deque(maxlen=5000)`, y una `threading.Condition` para
que el handler SSE se duerma hasta que aparezca una línea nueva o
termine el proceso. Cap blando de 30 jobs terminados en memoria
(`MAX_FINISHED_JOBS`). Los jobs vivos nunca se descartan.

**Registry**: `scripts/script_registry.py` es un módulo Python con una
lista `SCRIPTS` de dicts. Cada entrada describe un script con sus
flags tipados (bool/int/float/str/csv/choice), descripciones para
humanos, recetas (presets), y la flag `advanced` para esconder cosas
detrás de un `<details>` en la UI. Es la **fuente única de verdad** —
agregar/modificar un script desde la UI es solo editar este archivo.

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
own country/stock).

**Feedback de "mala elección" (botón 👎).** El footer del modal expone
un botón pulgar-abajo que despliega un textarea + "Enviar"/"Cancelar".
`submitFeedback()` (Alpine) hace `fetch("/api/feedback", { method: "POST",
... })` con `{title, url, reason}`. El estado del flujo vive en cinco
propiedades reactivas: `feedbackOpen`, `feedbackReason`, `feedbackSending`,
`feedbackSent`, `feedbackError`. `_resetFeedback()` se llama al abrir/
cerrar el modal para no arrastrar estado entre items.

El handler en el servidor (ver "Server" arriba) llama a
`_log_feedback(url, reason)` que: busca el item en `items.jsonl` por URL
y appendea el registro completo + `{reason, submitted_at}` a
`data/feedback.jsonl` sin tocar `items.jsonl`. El item sigue visible en
el catálogo. El JS muestra confirmación breve y cierra el panel.
Ver también CLAUDE.md → "Feedback desde el modal" para el propósito
(input para el skill `/watch-review-feedback`).

## Wiki parsers

Wikis are sources that need custom parsing logic, not just generic
`extract_listing_candidates`. They live in `scripts/wikis/` and are
invoked via `--bootstrap-wiki <name>`.

All 17 parsers share the same public API:

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
  cover.
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
- **mangavariant.py** (Global — base curada de variants, 13 países).
  URL: `https://mangavariant.com/variant/<manga-slug>/<variant-slug>/`.
  No usa rango año/mes (no hay calendario): lee los 3 Yoast sitemaps
  (`variant-sitemap.xml`, `variant-sitemap2.xml`, `variant-sitemap3.xml`)
  para enumerar todas las URLs (~2700) y procesa cada detail en paralelo
  (`ThreadPoolExecutor(workers=4)`). Estructura del detail page: bloque
  `<div class="variant_info_block">` con campos `<div class="vInfo">
  <strong>Label:</strong><ul><li>value</li></ul></div>` para Published
  by / Country / Manga / Where / Release / Tags + un `<a class=
  "v_rarity_icon" href="/variant?rarity=<tier>">`. El **título visible**
  es solo la edición (p.ej. "Vol.34 - Crunchyroll variant"); la serie va
  en el tag Manga y el parser concatena `f"{serie} — {edicion}"` para
  que el dashboard y `cluster_key` funcionen. Country slug → nombre /
  idioma vía `COUNTRY_MAP` (incluye 5 países nuevos para el corpus:
  Alemania, Taiwán, Tailandia, Reino Unido, Vietnam). NO pasa por
  `is_likely_manga` / `is_collectible_edition` — la fuente es 100%
  curada de variants por diseño. URLs son referencia, no de tienda
  (ver "URL como referencia" en CLAUDE.md).
- **blogbbm.py** (BR — Biblioteca Brasileira de Mangás, posts curados).
  URLs: `/2020/10/09/capas_variantes/` (capas variantes) y
  `/2024/05/15/guia-volumes-especiais-de-mangas-com-itens-especiais/`
  (volúmenes con extras/brindes). Ambos posts son **curated guides
  actualizadas continuamente**: el blog agrega nuevos entries cada vez
  que el editor encuentra una variant brasileña notable. El parser
  ignora el rango año/mes — no hay calendario; los posts se relanzan
  periódicamente. Heurística **title-driven** que soporta dos layouts
  HTML del mismo blog: Layout A (`/capas_variantes/`) tiene gallery
  `<div>` antes del título; Layout B (`/volumes-especiais/`) tiene
  título con parens-date `(MM/YYYY)` y `<figure>` adentro del entry.
  Las imágenes en `<div>` siempre van a un buffer pre-título; las
  imágenes en `<figure>` van al entry actual. Detección de título usa
  combinación de markers: parens-date, ficha link `/manga/<slug>/`
  cubriendo ≥80%, o (modo lenient cuando hay imgs en buffer) volume
  marker `#NN` o `<strong>` envolvente. URL por entry usa query param
  `?bbm-entry=vol-N-<image-stem>` (NO fragment — los fragments se
  strippean en `normalize_url_for_dedup`; ver gotcha #27). Cubre los
  publishers BR (Panini, JBC, NewPOP, Pipoca & Nanquim, MPEG, Devir,
  Conrad) con clasificación EXPLÍCITA de variant/special/bonus que el
  scrape directo de esas sources no marca.
- **socialanime.py** (IT — MangaStore variant + cofanetti, JSON feed).
  URL: `https://socialanime.it/store/manga/variant` (página) y endpoint
  `flow_mangafeed.php?type={variant|box}&group_no=N&macro_filter=best_of_all`
  (JSON paginado, 25 items/página). El parser ignora el rango año/mes
  — el feed no particiona por fecha; el control temporal es el
  `macro_filter` (`best_of_all` baja todo, `next_from_now` solo upcoming,
  default = últimos 8 meses). Por cada item del JSON construye un
  Candidate con `editore` → publisher, `autore` → author,
  `PublicationDate` (formato "DD MMM YYYY" en inglés) →
  release_date. **El link es un Amazon affiliate** (`amazon.it/dp/<ASIN>?tag=socianim0c-21`)
  que se canonicaliza vía `normalize_url_for_dedup` (strip `tag/linkCode/
  th/psc/ref=...` — ver gotcha #26). El ASIN de libros italianos legacy
  (prefijo `88…`) es un ISBN-10 válido y se guarda en `isbn`; ASINs
  Kindle (`B0…`) NO son ISBN. Para type=box (cofanetti) se inyecta
  "Cofanetto / box set." en la descripción si el título no lo dice,
  para que `detect_signals` levante el signal `box_set`. Items sin link
  Amazon (~10% del feed) se descartan: sin URL canónica no se puede
  dedupar. Cubre publishers italianos chicos que las sources directas
  no agarran exhaustivamente (Edizioni BD, 001 Edizioni, Goen, Magic
  Press, Dynit, Coconino, Tora, Dokusho).
- **whakoom.py** (ES/LatAm — Cloudflare-throttled spider, opt-in).
  3-level BFS: `/newtitles` → `/comics/{shortcode}` →
  `/ediciones/{id}` (which exposes sibling variants — alt covers,
  retailer-exclusives). 4 protection layers: browser-like headers,
  default 2s sleep, 429 backoff (10s→20s→40s, max 3 retries),
  Cloudflare challenge detection → abort with `WhakoomBlocked` (don't
  keep hammering, you'll get IP-banned across your whole network).
  Throttle lockfile at `~/.cache/manga-watch/whakoom_lastrun` blocks
  runs <6h apart. Activated only via `--bootstrap-wiki whakoom` (NOT
  in regular scrapes — the lightweight diff is the
  `ES/LatAm - Whakoom Novedades` source in sources.yml).
- **booksprivilege.py** (JP — 店舗特典まとめました, extras de tienda JP).
  Discovery: calendar mensual `?cal_ym=YYYY-M` → `td.has-book` marks
  days with releases → daily listing `?date=YYYY-MM-DD` → detail
  `?id=NNNN`. ISBN-10 inferred from Amazon CDN path
  `/P/<isbn>.09_*.jpg`; Kindle ASIN `B0…` discarded. Imprints JP
  mapped to canonical publishers (~30 entries). Description structured
  with per-shop bonuses. Body decoded `utf-8 errors='replace'` because
  ad banner alt-text contains raw cp932 bytes (gotcha #28).
- **sumikko.py** (JP — comic.sumikko.info コミック新刊チェック, ~3178
  限定版/特装版 curated). Listing at `/limited-item/?p=N` (90 items/page,
  ~32 pages). Each `<a href="/item-select/<isbn>">` block contains full
  metadata — NO detail fetch needed. ISBN-10 from URL path. Items
  BL/R18 use `<img class="touch18">` — parser searches any `<img>`
  (not filtered by class). Type-tag describes the EXTRA type, not the
  product type — all items accepted by default (gotcha #30).
- **mangapassion.py** (DE — manga-passion.de via public REST API).
  Two queries against `api.manga-passion.de`: `type[]=3` (Sonderausgaben)
  + `type[]=0&tags.tag.id=200` (Variant-Covers). `specialType=1` →
  Sammelschuber (Schuber/estuche); hint "Box Set" injected so
  `detect_signals` fires `box_set`.
  Delta mode uses `date[after]` filter; full mode downloads complete
  historical catalog.
- **animeclick.py** (IT — calendario semanal edizioni speciali).
  AJAX navigation via `?paging=prev-week&day=DD&month=MM&year=YYYY`
  with `X-Requested-With: XMLHttpRequest` header. Keyword filter
  `_COLLECTOR_RE` on calendar cards before fetching detail pages
  (~20% hit rate). Detail pages use schema.org Book markup
  (`itemprop name/image/description/datePublished`) + `Editore:`
  labels in `<strong>`. No ISBN available. Hints injected
  for IT terms (`Cofanetto` → `box_set`, `Integrale` → omnibus).
  Covers Star Comics, Panini Comics, J-POP, MangaYo!, Crunchyroll IT.
- **prhcomics.py** (US/CA — prhcomics.com/manga/, PRH catalog).
  Single static page, no pagination or JS. Items in
  `<li class="toast-anchor">`. ISBN-13 in HTML → cover URL deterministic
  `images.penguinrandomhouse.com/cover/{isbn13}`. Filter: format
  (`hardcover`, `boxed set`, `slipcase`) or title keywords. Denylist of
  non-manga publishers (DK, Golden Books, Prestel, Pantheon). Covers
  Dark Horse Manga, Kodansha Comics, Seven Seas, Square Enix, TOKYOPOP,
  Titan, Vertical, Inklore. NOT VIZ or Yen Press.
- **kinokuniya.py** (US — usa.kinokuniya.com/kinokuniya-exclusives).
  Squarespace site with dynamic class names; extraction by URL pattern
  `_ISBN_URL_RE = r"/bw/(\d{13})(?:[/?#]|$)"` (stable). Title in
  `<img alt>` (not `anchor.get_text()` — Squarespace renders image-link
  blocks without text nodes). Validates ISBN-13 starts with `978`/`979`
  to filter gift-card UPCs. Cover URL deterministic via PRH CDN.
  Injects "Kinokuniya Exclusive" in description → signal
  `retailer_exclusive`.
- **yenpress_calendar.py** (US — yenpress.com/calendar, monthly
  releases). Card selector `a[href~=_ISBN_PATH_RE]` (not CSS class —
  Squarespace-like dynamic classes). Category from `span.white-label`
  classes; discards light novels (`light-novels` class). Pre-filter by
  premium keywords (collector's, deluxe, box set, hardcover, etc.).
  ISBN-13 from path `/titles/(\d{13})-`. Cover URL deterministic
  `images.yenpress.com/imgs/{isbn13}.jpg`. Iterates monthly
  (`iter_year_months`). Delta: last 3 months; full: from 2013-01.
- **listadomanga_collections.py** (ES — coleccion.php?id=N, per-
  collection parser). Iterates collection IDs; discovery via
  `lista.php` index (~3432 active collections). Layout A: sections
  by `<h2>` (Ediciones Especiales, Portadas alternativas, Packs,
  premium format detection from `<b>Formato:</b>`). Layout B: extra
  items (Cofres/Regalos/Extras) linked back to their tomo. Synthetic
  URL per item via query param `?item=<edition_slug>-<vol>`
  (gotcha #27). En-cofre format emits single box-level item instead
  of individual tomos (gotcha #29). `images[]` populated with all
  cover + extra images. Used exclusively in `scrape_full.sh`
  (too slow for delta).

## Concurrency model

Added in 2026-05-21 (Sprint 2.4). The scrape loop in `manga_watch.py`
processes sources concurrently using `concurrent.futures.ThreadPoolExecutor`.

```
              ┌─────────────────────────────────────────────┐
              │  ThreadPoolExecutor(max_workers=N)          │
              │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ...   │
              │  │ src1 │ │ src2 │ │ src3 │ │ src4 │       │
              │  └───┬──┘ └───┬──┘ └───┬──┘ └───┬──┘       │
              └──────┼────────┼────────┼────────┼──────────┘
                     │        │        │        │
                     └────┬───┴────┬───┴────────┘
                          │        │
                          ▼        ▼
                ┌───────────────┐  ┌────────────────────────┐
                │ per-host      │  │ _PLAYWRIGHT_QUEUE      │
                │ Semaphore     │  │ (jobs dispatched to    │
                │ (size = N)    │  │  playwright-worker     │
                └───────────────┘  │  thread — never cross  │
                                   │  greenlet boundaries)  │
                                   └────────────────────────┘
```

- **`--workers N`** (default 1, recommended 8 for overnight). When 1,
  the path is byte-identical to the historical serial loop (including
  the inter-source `time.sleep(--sleep-seconds)`). When > 1, the inter-
  source sleep is skipped because the per-host semaphore already
  serializes hits to the same domain.
- **`--per-host-limit N`** (default 2). A `defaultdict(lambda:
  threading.Semaphore(N))` keyed by `urlparse(url).hostname` bounds
  concurrent requests to the same host. Protects retailers from being
  hammered by search-template expansions of the same source family
  (e.g. several Panini search-keyword children all targeting
  `panini.es`).
- **`_PLAYWRIGHT_WORKER` + `_PLAYWRIGHT_QUEUE`** — dedicated worker
  thread that owns the entire Playwright lifecycle (browser launch,
  context, navigate, content, close). HTTP workers call
  `fetch_with_playwright(url, ...)` which puts a job on
  `_PLAYWRIGHT_QUEUE` and blocks on a per-job `queue.Queue` for the
  result. The worker thread lazy-launches Chromium on its first job.
  `close_playwright()` sends a sentinel for clean shutdown and is
  idempotent (safe to call multiple times). Required because
  `playwright.sync_api` binds greenlets to the thread that called
  `sync_playwright().start()` — any other thread hitting the browser
  raises `greenlet.error: Cannot switch to a different thread`
  (gotcha #12). The old `_js_lock` approach serialized access but
  did NOT move execution to the owner thread, so it failed the same
  way under concurrent workers.
- **`print_lock`** wraps every `print()` so log lines from concurrent
  workers don't interleave. Output is still per-source-completion
  rather than strictly ordered.
- **`DiagnosticRecorder` thread-safety.** Every `record_*` method
  accepts an explicit `entry: dict | None = None` argument so each
  worker mutates its own pre-allocated entry instead of racing on
  `self.current`. `self.entries.append(entry)` is protected by
  `_entries_lock`. The implicit `self.current` shim is preserved for
  callers that still run sequentially (wiki bootstraps).
- **`--fetch-details` is also parallelized.** Each eligible item is
  submitted to the same pool. Metadata application back to candidates
  runs serially after the pool drains (`as_completed`) so state
  mutations stay race-free.

Measured speedups (5.6-7.5× depending on subset):
- España subset (50 sources): 35.7s serial → 6.4s with `--workers 8`.
- trusted_media subset: 1:12 serial → 9.5s.
- Full Phase 1 (overnight): projected ~26min → ~5min.

Why not asyncio: switching `requests` + `feedparser` + Playwright to
async would touch hundreds of call sites and rewrite the wiki
parsers. Threads buy 6-8× speedup with ~250 LOC of change and the
existing fetch helpers untouched. The cost is GIL, but the workload
is I/O-bound (network-waiting, not CPU-burning).

### Server-side write serialization (`serve.py`) — `@_serialized`

`serve.py` runs on a **threaded** server (`ThreadedTCPServer(ThreadingMixIn,
TCPServer)`) so it can handle concurrent SSE streams and API requests. But the
6 endpoints that mutate `items.jsonl` (`_apply_approve`, `_apply_approve_edition`,
`_apply_move`, `_apply_remove`, `_apply_merge_items`, `_update_item_images`)
do a **read-modify-write of the entire file** (`_load_items()` → mutate →
`_write_items()`). Without serialization, two concurrent requests (fast clicks:
approving several items, or approve + curate) both read the old state and the
last `_write_items` wins, **silently dropping the other's change**.

Fix (2026-06-02, gotcha #34): a module-level `_ITEMS_LOCK = threading.Lock()`
and a `@_serialized` decorator wrapping each of the 6 functions in
`with _ITEMS_LOCK`. The lock must span the whole load→modify→write critical
section (locking only `_write_items` is insufficient — the stale read happens
before the lock). `_log_feedback` is intentionally NOT decorated (it only reads
items.jsonl for a snapshot + appends to feedback.jsonl, and is called from
functions already holding the lock → avoids deadlock since `Lock` is not
reentrant). **Any new endpoint that rewrites `items.jsonl` MUST use
`@_serialized`.** Regression test: `test_serve_concurrent_approvals_do_not_clobber`.

## Cluster key — multi-source grouping beyond ISBN

Added 2026-05-21 (Sprint 3.8). `derive_cluster_key(item) -> str` lives
in `manga_watch.py` and is called by `candidate_to_json` so every row
in `items.jsonl` carries a precomputed `cluster_key`.

Four cluster-key shapes, in priority order:

| Shape | When | Example |
|---|---|---|
| `isbn:<X>` | Item has an ISBN | `isbn:9784099432416` |
| `edition:<edition_key>\|<volume>` | No ISBN but both `edition_key` and `volume` set (or no volume needed for box sets) | `edition:gon-norma-collector\|` |
| `fuzzy:<lang>\|<series>\|<vol>\|<tier>\|<publisher>` | No ISBN/edition_key but lang + series (≥3 chars) + volume all derivable | `fuzzy:japonés\|転生したらスライムだった件\|15\|limited\|講談社` |
| `url:<url>` | Insufficient info to fuzzy-merge safely | `url:https://example.com/x` |

The `edition:` tier (added 2026-05-24) solves box sets and other items
without volume that the fuzzy tier couldn't merge — e.g. Gon Edición
Coleccionista appeared as 2 cards (Whakoom + ListadoManga) because both
had no ISBN, no volume, and different publishers. With `edition:`, items
sharing the same `edition_key` (which encodes publisher+market in its
slug) merge regardless of publisher string. See design decision #4 in
CLAUDE.md for full details including the variant tier hierarchy.

Components of the fuzzy key:
- `language`: `item.language` lowercased.
- `series`: `_normalize_series_name(title, volume)` — strips variant
  keywords (deluxe, kanzenban, celebration edition…), volume markers
  (vol., tomo, tome, n., #, 巻…), and bracketed retailer noise (the
  full-width `（...）` is part of that). Preserves kanji/kana/accents
  because they're discriminants for non-Latin scripts.
- `volume`: `_extract_volume(title)` — first match of vol/tomo/tome/
  n./#/巻 patterns, including JP-style parenthesized numbers
  (`タイトル（15）`). Required for fuzzy mode; without it we fall through
  to `url:` to avoid merging different tomos of the same series.
- `tier`: `_variant_tier(signal_types)` — picks the most specific tier
  from `artbook > omnibus > box_set > kanzenban > lore_edition >
  variant_cover > deluxe > limited > special > ""`. Two items in the
  same tier merge; two in different tiers don't.
- `publisher`: `item.publisher` lowercased.

Grouping consumers:
- **`build_web.py:_group_by_cluster_key`** — groups items by key,
  picks the canonical (highest score, latest detected_at as tiebreak),
  best-of-merges missing fields, and builds `sources[]`.
- **`web/index.html:dedupByUrl`** — mirrors the same logic in JS for
  live-fetch mode. Reads `item.cluster_key`; for legacy rows without
  the field, falls back to ISBN (or `url:` if neither).

Retrofit: `scripts/retrofit/backfill_cluster_key.py` adds/refreshes
`cluster_key` on every row in `items.jsonl`. Reports the consolidation
delta (currently ~7%, 130 cards collapsed into 89 multi-source
groups).

If you change the derivation, re-run the retrofit AND verify in the
browser that the top groups still look right — bad merges are
subtle.

## Wayback recovery (opt-in retrofit)

`scripts/retrofit/wayback_recover.py` recovers metadata for items
whose source URLs returned **404 or 410** by querying the archive.org
Availability API and parsing the cleanest snapshot.

```
items.jsonl URLs ─┬─→ HEAD check ─→ 200/301/302/304 → keep
                  ├─→ HEAD check ─→ 404 / 410 → query Wayback
                  │                                 ↓
                  │                       found → re-extract via
                  │                               fetch_metadata_
                  │                               from_detail on
                  │                               /web/<ts>if_/<url>
                  │                               (clean HTML — no
                  │                                Wayback chrome).
                  │                       not found → leave as-is
                  └─→ HEAD check ─→ 403 / 429 / 5xx / conn fail
                                    → ANTI-BOT BLOCK, skip
                                      (page is alive, just rejecting us;
                                       Wayback recovery would burn quota)
```

Modes:
- `--check` — only HEAD checks. Reports the status distribution.
- `--dry-run` — also queries Wayback but doesn't write.
- `--urls a,b,c` — recovery for explicit URLs (no jsonl scan).
- default — full run, writes back to items.jsonl with backup
  `items.jsonl.pre-wayback-bak` and marks recovered rows with
  `recovered_from_wayback: true`, `wayback_snapshot_url`,
  `wayback_timestamp`.

Wayback URL trick: snapshots come as `web.archive.org/web/<ts>/<orig>`
(includes Wayback chrome banner). We rewrite to
`web.archive.org/web/<ts>if_/<orig>` ("iframe" mode) to get the raw
original HTML — JSON-LD, OG tags, all intact for re-parsing.

In overnight_run.sh, this is opt-in via `INCLUDE_WAYBACK_RECOVERY=1`.
Default OFF because it's slow (~30-60 min) and the corpus dead-rate
is ~0.1% — run it weekly at most.

## Source health audit

`scripts/audit/source_health.py` parses the last N
`logs/overnight-*/01-scrape.log` files and classifies each source as
one of:

| Category | Trigger |
|---|---|
| `broken_http` | error rate ≥ 50% |
| `broken_skip` | skip rate (JS-required, robots) ≥ 50% |
| `selector_dead` | always 0 candidates AND seen in ≥ 2 runs |
| `low_yield` | avg candidates/run < 1 AND seen in ≥ 2 runs |
| `declining` | second half of runs has < 50% candidates of first half |
| `healthy` | none of the above |
| `unseen` | not present in any of the N parsed logs |

Output formats: markdown (default) or JSON. Run after each overnight
to spot rotting selectors before they accumulate. Output land in
stdout by default; use `--output-file` to persist.

## CLI surface

```
python scripts/manga_watch.py
    --source-classes official,retailer,trusted_media
    --countries Francia,España,Japón
    --include-tags <tag>          (only sources with this tag)
    --exclude-tags <tag>
    --only-tags <tag>
    --min-score 30
    --include-seen                (also re-emit unchanged items)
    --fetch-details               (enrich via per-item HTTP)
    --enable-js                   (Playwright for kind:js sources)
    --workers 8                   (default 1 = serial; >1 enables
                                   ThreadPoolExecutor)
    --per-host-limit 2            (concurrent requests per domain
                                   under --workers > 1)
    --max-pages 5
    --connect-timeout 10
    --read-timeout 30
    --sleep-seconds 0.5           (inter-source pause; ignored when
                                   --workers > 1)
    --bootstrap-wiki {listadomanga, listadomanga-blog, manga-sanctuary,
                      otaku-calendar, manga-mexico, mangavariant,
                      socialanime, blogbbm, booksprivilege, sumikko,
                      mangapassion, animeclick, prhcomics, kinokuniya,
                      yenpress, listadomanga-collections, whakoom}
    --wiki-from YYYY-MM
    --wiki-to YYYY-MM
    --sitemap-mining-domain <domain>
    --skip-image-download         (skip the local cover mirror;
                                   default OFF = covers are downloaded
                                   to data/images/, Image storage Fase 1)
    --dry-run

python scripts/build_web.py [--input ...] [--output ...] [--clear]
python scripts/serve.py [--port 8000]

# Retrofits (operate on items.jsonl in-place with backup)
python scripts/retrofit/rescore.py [--dry-run]
python scripts/retrofit/clean_titles.py [--dry-run]
python scripts/retrofit/filter_non_manga.py [--dry-run]
python scripts/retrofit/filter_collectible.py [--dry-run]
python scripts/retrofit/backfill_metadata.py [--only image_url] [--sleep 0.3]
                                              [--max-per-source N] [--limit N]
                                              [--skip-source X] [--skip-domain Y]
python scripts/retrofit/backfill_cluster_key.py [--dry-run]
python scripts/retrofit/search_discovery.py [--engines gemini,tavily,ddg]
                                             [--limit N] [--dry-run]
python scripts/retrofit/wayback_recover.py [--check | --dry-run |
                                            --urls a,b,c]
python scripts/retrofit/mirror_images.py [--dry-run] [--no-gc | --gc-only]
                                          [--gc-delete] [--workers N] [--limit N]
python scripts/retrofit/translate_descriptions.py [--dry-run] [--limit N]
                                                   [--workers N] [--force]
                                                   # Google Translate primary (no key),
                                                   # DeepL optional via DEEPL_API_KEY

# Audit / observability
python scripts/audit/source_health.py [--last-n 10] [--output md|json]
                                      [--output-file PATH]

# Canonical orchestrators
./scripts/scrape_delta.sh                       # incremental — listadomanga
                                                # via calendario.php, ~30-60 min
                                                # Frequency: daily/weekly
INCLUDE_WHAKOOM_SPIDER=1 ./scripts/scrape_delta.sh    # CF-risk opt-in
INCLUDE_WAYBACK_RECOVERY=1 ./scripts/scrape_delta.sh  # weekly cadence
SKIP_SCRAPE=1 ./scripts/scrape_delta.sh               # only wikis + cleanup

./scripts/scrape_full.sh                        # full refresh — listadomanga
                                                # via lista.php (~3432 collections)
                                                # + mangavariant sitemap, ~2-4h
                                                # Frequency: monthly/quarterly

./scripts/overnight_run.sh                      # DEPRECATED alias for scrape_delta.sh
                                                # kept for cron backwards compat

./scripts/retry_failed.sh                       # re-run only sources
                                                # that errored in latest run
```

## Tests

`tests/test_extraction.py` — 425 tests, runtime <2s.

Coverage areas:
- `clean_title()` — every junk pattern has a test with a real example
  from the corpus.
- `is_likely_manga()` — strong/pack/hard/soft cases, source purity
  variants, real titles reported by the user.
- `is_pure_novel()` — URL/word indicators + bypass for manga
  adaptations.
- `is_comic_not_manga()` — publisher equality, franchise/format
  keywords with word-boundary regex, "manga" bypass (Batmanga).
- `is_collectible_edition()` — gates for each
  `COLLECTIBLE_EDITION_SIGNAL_TYPES` family + lore-edition rescue.
- `derive_cluster_key()` / `_extract_volume()` /
  `_normalize_series_name()` — ISBN authority, fuzzy fallbacks for
  ES/IT/FR/JP, JP full-width parenthesized volume, safe degradation
  to `url:` when info is insufficient.
- `_extract_label_value_pairs()` — `<li><span>`, `<dt>/<dd>`, `<tr>`
  structures in 3+ languages incl. JP labels.
- `_fix_mojibake()` — strict round-trip + fallback pair.
- `append_jsonl()` — upsert with and without URL.
- Each wiki parser has happy-path tests with realistic HTML.
- Listing extractor edge cases (next-page, cross-origin, broken anchors).

Run: `.venv/bin/python -m pytest tests/test_extraction.py -q`.

## Performance baselines

| Operation | Time | Notes |
|---|---|---|
| Full scrape serial (`--workers 1`, no detail-fetch) | 15-25 min | depends on enabled sources |
| Full scrape parallel (`--workers 8`, no detail-fetch) | 3-5 min | 5-7× speedup, I/O-bound |
| Full overnight Phase 1 (`--workers 8 --fetch-details`) | ~5 min | was ~26min serial |
| España subset serial (50 sources) | 35.7s | baseline |
| España subset `--workers 8` | 6.4s | 5.6×, identical results |
| trusted_media subset serial | 1:12 | |
| trusted_media subset `--workers 6` | 9.5s | 7.5× |
| `--bootstrap-wiki listadomanga` (12 months) | 3-5 min | |
| `--bootstrap-wiki listadomanga-blog 2009-11 → 2026-05` | 30-60 min | one-shot historical |
| `--bootstrap-wiki mangavariant` (full sitemap) | 10-15 min | ~2700 detail HTTPs, parallel |
| `--bootstrap-wiki socialanime` (variant + box, JSON feed) | 30-60s | 30-40 paginated JSON calls |
| `--bootstrap-wiki blogbbm` (2 posts curados) | 5-10s | 2 HTML fetches + parsing |
| `--bootstrap-wiki whakoom` (3-level spider, opt-in) | 25-40 min | ~1500 HTTP, CF-risk |
| Search discovery (Gemini + Tavily + DDG, 32 queries) | 10-15 min | quota-limited |
| Wayback recovery `--check` (full corpus HEAD) | ~10 min | mostly anti-bot 403s |
| `append_jsonl` upsert (3000 items) | ~50 ms | atomic |
| `filter_non_manga` retroactive | <1 s | in-memory |
| `clean_titles` retroactive | <1 s | in-memory |
| `backfill_metadata` (1000 items) | 5-10 min | network-bound |
| Web initial load | <1 s | 3.6 MB JSONL → parse + dedup → render |
| Web filter/search/page navigation | <50 ms | client-side |

If a number above doubles after a change, something regressed.

## Curation skills (LLM-driven, manual)

Two project-level skills under `.claude/skills/`. They live in the repo
(versioned with git) and are invoked manually by the owner via
`/<skill-name>` from Claude Code. Both are designed to be incremental
and idempotent — safe to re-run.

### `/watch-standardize-catalog`

**File**: `.claude/skills/watch-standardize-catalog/SKILL.md`

**Purpose**: pass 2 of the schema standardization (see `items.jsonl`
section above). Processes items WITHOUT `standardized_at`. Delegates
to parallel subagents (`general-purpose`) in batches of ~150-200,
each one returning per-item: `is_manga`, `series_key`,
`series_display`, `edition_key`, `edition_display`, `volume`,
`title_standardized`.

Workflow:
1. Audit pending count (filter `items.jsonl` by missing `standardized_at`).
2. Partition into chunks of 150, written to `data/standardize-run/`
   (persistent run dir — moved off `/tmp` 2026-07-08 so Tier 2/3 chunk/
   result files survive a reboot and the audit can resume mid-run).
3. Spawn 7 subagents per wave (parallel). Each one reads its chunk and
   writes a result file.
4. Merge results back into items.jsonl via `standardize_apply.py merge`
   (fuente única — ya no lógica embebida en SKILL.md). Apply
   `canonical_series_key()` from `data/series_aliases.yml`. Dedup by
   `(series_key, edition_key, volume)`. **El LLM NO expulsa (WO-C,
   2026-07-07)**: `is_manga=false` NO borra la fila ni la manda a
   `non_manga_blacklist.jsonl` — el item queda PENDIENTE y se registra en
   `data/unmapped_series.jsonl` (reason `llm_non_manga`); la expulsión real
   la hacen los gates deterministas (`filter_non_manga`/`filter_collectible`)
   en la próxima corrida del scrape.
5. Set `standardized_at` on each processed item.
6. Cleanup `data/standardize-run/` (only after the merge is confirmed).

Incremental by default. `--force-all` snippet (embedded in the skill)
clears `standardized_at` from all items to force a full re-run when
standardization rules change substantively.

### `/watch-enrich-series-aliases`

**File**: `.claude/skills/watch-enrich-series-aliases/SKILL.md`

**Purpose**: process the `data/unmapped_series.jsonl` queue, deciding
for each new `series_key` whether it's an alias of an existing
canonical (merge into existing entry) or a new series (create entry).
Queries Anilist GraphQL API for international titles + synonyms when
needed.

Workflow:
1. Run `scripts/audit/unmapped_series.py` to aggregate the queue +
   fuzzy-match candidates against canonicals.
2. For each unmapped series (sorted by item count desc):
   - **Action A**: merge as alias of existing canonical (high
     confidence fuzzy match, ≥0.8).
   - **Action B**: query Anilist, create new canonical entry.
   - **Action C**: skip (low confidence + low item count → wait for
     more data).
3. Edit `data/series_aliases.yml` in place.
4. Run the embedded backfill snippet to consolidate items.jsonl.
5. Truncate `data/unmapped_series.jsonl` (next scrape repopulates).

### Recommended post-scrape workflow

```
1. manga_watch.py runs (scrape) → new items with rough series_key, no standardized_at
2. /watch-standardize-catalog          → subagents verify/correct/timestamp
3. /watch-enrich-series-aliases        → consolidate any new multilingual series
4. build_web.py                  → refresh dashboard
```

Both skills can be triggered via `/loop`/`/schedule` in the future for
fully-automated curation cadence.
