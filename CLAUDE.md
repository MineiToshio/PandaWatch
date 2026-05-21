# CLAUDE.md — Context for AI assistants working on PandaWatch

> Read this file first if you are an LLM agent (Claude, GPT, etc.) about
> to make changes to this repo. It captures the design intent, the
> conventions, and the gotchas that are not obvious from the code.
> The goal is that a new conversation can resume work with full context.

## ⚠️ Documentation policy — READ BEFORE TOUCHING CODE

**Every meaningful change to this repo MUST update the relevant docs in
the same turn.** This is not optional. The owner (sergiomineiro) has
flagged repeatedly that docs were getting out of sync — do not let that
happen again.

**What counts as "meaningful"** (i.e. requires a doc update):
- New scraper feature, new pipeline stage, new CLI flag, new endpoint
  in `serve.py`.
- Change to filters (`is_likely_manga`, `clean_title`, scoring) that
  shifts behavior or adds a new rule family.
- New source added/removed, or a source's `purity` / `kind` /
  `selectors` changed in a non-trivial way.
- New wiki parser under `scripts/wikis/`.
- Schema change to `items.jsonl`, `state.json`, `feedback.jsonl`, or
  any new data file.
- New retrofit script under `scripts/retrofit/`.
- New gotcha discovered (parser quirk, mojibake variant, source drift).
- Anything that changes the corpus numbers in the "Current corpus
  state" table by >2 percentage points.
- New environment variable, new dependency, new external service.

**What does NOT need a doc update:**
- Bug fixes that restore documented behavior.
- Test additions for already-documented rules.
- Pure refactors with no behavioral change.
- Typo fixes.

**Where to write it** (pick the right file — don't dump everything in
CLAUDE.md):

| Change type | File to update |
|---|---|
| Design intent, conventions, gotchas, corpus state | `CLAUDE.md` (this file) |
| Pipeline internals, data flow, module responsibilities | `docs/ARCHITECTURE.md` |
| How to add/maintain a source, selector recipes | `docs/SOURCES.md` |
| New env var, new dependency | `.env.example` + the file above that fits |
| Retrofit utility behavior | `scripts/retrofit/README.md` |
| Product scope / vision change | `docs/PRD.md` or `docs/PRD-catalog.md` |

**How to apply it during a task:**
1. Before declaring a task done, ask: "did I change behavior, schema,
   sources, or discover a gotcha?" If yes → update docs in the same
   commit, not a follow-up.
2. If the "Current corpus state" table is now wrong, update the
   numbers (run a quick script over `items.jsonl` to get fresh values).
3. If you added a new source or wiki parser, add it to the relevant
   list in CLAUDE.md (mixed-purity sources, wiki parsers list, etc.).
4. If you added a gotcha, append it to the "known gotchas" section and
   renumber if needed.
5. Bump the "Last updated" line at the bottom of CLAUDE.md when you
   edit it.

**If the user pushes back that docs are stale, that's a regression on
this policy — treat it as a bug to fix immediately, not a feature
request.**

## What this project is

**PandaWatch** (repo: `MineiToshio/PandaWatch`, also known internally as
`manga-watch`) is a **personal tracker** that scrapes ~106 enabled sources
(of 120 defined in `sources.yml`) across 9 countries and 5 languages
(ES, EN, FR, IT, JP) looking for
**physical manga special editions**: limited editions, deluxe hardcovers,
box sets, slipcase editions, artbooks, kanzenban, light novels with
bonuses, etc.

**Single user.** No login, no multi-tenant. The owner (sergiomineiro)
runs the scraper periodically and browses results through a static
web UI served locally.

**Stack:**
- Python 3 (scraping pipeline, filters, label/value extraction)
- BeautifulSoup + requests + ThreadPoolExecutor (parallel scrape via
  `--workers N`; no Playwright by default — opt-in via `--enable-js`
  for JS-only sites, which are serialized internally because
  `playwright.sync_api` isn't thread-safe)
- HTML + Alpine.js + Tailwind via CDN (static browser UI — no SPA build)
- Storage: JSONL with **upsert-by-URL semantics** (see "Storage" below)
- Tests: pytest (227 passing as of last commit)

## High-level pipeline

```
sources.yml  (120 entries, 106 enabled)
    │
    ▼
manga_watch.py (scraper)  ←─── ThreadPoolExecutor(--workers N)
  • fetch HTML / RSS / Bluesky API / sitemap per source
  • extract_listing_candidates() / extract_rss() /
    extract_bluesky_posts() / sitemap miner
  • score_candidate() — assigns 0-300 score by signal detection
  • is_likely_manga() — 4-rule cascade (figures, comics, news, etc.)
  • is_pure_novel() — rejects pure light novels (URL hints + words)
  • is_comic_not_manga() — comics blacklist with "manga" bypass
  • clean_title() — strips e-commerce junk, mojibake, news prefixes
  • fetch_metadata_from_detail() — opt-in HTTP per item for cover/
    author/price/ISBN via JSON-LD + label/value pairs (also
    parallelized in the --fetch-details stage)
    │
    ▼
data/items.jsonl  ← upsert by URL (1 line per unique URL).
                    Every row carries `cluster_key` for grouping.
data/state.json   ← cache of seen URLs (for incremental detection)
    │
    ▼
build_web.py  ← reads JSONL, groups by cluster_key (ISBN or fuzzy
                lang+series+vol+variants+publisher), embeds in HTML
web/index.html ← Alpine.js dashboard (filters incl. signal_types
                 chip filter, search, multi-source modal)
    │
    ▼
http://localhost:8000/ (via scripts/serve.py — PUBLIC, deployable)
                       + POST /api/feedback for "this shouldn't be here"

Operación: scripts/admin_serve.py (127.0.0.1:8001, LOCAL, no deployable)
  + admin/index.html → Panel de Control web. Lee scripts/script_registry.py
  y permite ejecutar cualquier script del repo desde una UI con
  toggles + presets + logs en vivo (SSE). Detalle en docs/CONTROL-PANEL.md.

Orchestration: scripts/overnight_run.sh chains
  scrape (parallel) → wiki bootstraps → search discovery →
  cleanup retrofits (rescore, filter_non_manga, filter_collectible,
  clean_titles, backfill_metadata, [wayback_recover]) →
  build_web.

Observability: scripts/audit/source_health.py parses N recent overnight
  logs and classifies sources (broken_http / selector_dead / declining
  / healthy / unseen).
```

## File map (what lives where)

```
sources.yml                          — 120 source definitions (106
                                       enabled), 15 with kind:bluesky,
                                       13 with purity:mixed, the rest
                                       html/rss/js.
data/
  comics_blacklist.yml               — Marvel/DC publishers + franchise
                                       keywords (Spider-Man, Batman,
                                       Sin City, Asterix, …) +
                                       format keywords (graphic novel,
                                       facsímil). Applied always
                                       (not just in mixed sources);
                                       bypassed when title contains
                                       "manga" (Batmanga survives).
  search_queries.yml                 — queries for multi-engine search
                                       discovery, with engine priority
                                       per query (gemini/tavily/ddg).
  items.jsonl                        — gitignored. Upsert table; every
                                       row carries cluster_key.
  state.json, feedback.jsonl         — gitignored.
scripts/
  manga_watch.py                     — main module (4400+ lines):
                                       filters, scoring, IO, the
                                       parallel scrape loop, the
                                       Bluesky/Playwright/HTTP
                                       dispatchers, derive_cluster_key.
  build_web.py                       — reads items.jsonl, groups by
                                       cluster_key (not ISBN), embeds
                                       in web/index.html (or leaves []
                                       so the dashboard fetches live).
  serve.py                           — PUBLIC HTTP server. Sirve web/
                                       + data/ + redirige / → /web/ +
                                       POST /api/feedback → feedback.jsonl.
                                       Bindea 0.0.0.0:8000. ES lo que se
                                       despliega.
  admin_serve.py                     — ADMIN HTTP server del Panel de
                                       Control. Sirve admin/ + /api/scripts
                                       + /api/run + /api/jobs/*/stream (SSE)
                                       + /api/jobs/*/stop. Bindea
                                       127.0.0.1:8001. NO desplegar.
  script_registry.py                 — fuente única de verdad para el
                                       Panel de Control. Lista SCRIPTS con
                                       icon/name/what/when/flags/presets
                                       para cada script ejecutable. Lo
                                       lee admin_serve.py vía /api/scripts.
                                       Agregás un script acá, aparece solo
                                       en la UI.
  run_local.sh                       — wrapper que lanza serve.py +
                                       admin_serve.py en paralelo
                                       (Ctrl+C baja ambos).
  overnight_run.sh                   — chained 5-phase pipeline:
                                       scrape (parallel) → wikis →
                                       search → cleanup → build. Opt-in
                                       knobs: INCLUDE_WHAKOOM_SPIDER,
                                       INCLUDE_WAYBACK_RECOVERY,
                                       SCRAPE_WORKERS, PER_HOST_LIMIT,
                                       GEMINI_SLEEP, LISTADO_BLOG_FROM/TO.
  retry_failed.sh                    — re-runs only sources that errored
                                       in the latest overnight log.
  wikis/                             — dedicated parsers for wikis.
    listadomanga.py                  (ES — month calendar)
    listadomanga_blog.py             (ES — historical WordPress blog
                                       archive, 2009-11 → current)
    manga_sanctuary.py               (FR — Unix timestamp planning)
    otaku_calendar.py                (EN — current-month releases)
    manga_mexico.py                  (MX — alphabetic catalog per editorial)
    whakoom.py                       (ES/LatAm — Cloudflare-throttled
                                       3-level spider, opt-in only)
  retrofit/                          — utilities to apply changes to
                                       historic data.
    README.md
    rescore.py                       — refresh score + signal_types +
                                       product_type over items.jsonl
                                       (run after detector changes).
    clean_titles.py                  — re-clean existing titles.
    filter_non_manga.py              — re-filter (uses purity from
                                       sources.yml + comics blacklist).
    filter_collectible.py            — second gate: drop regular tomos,
                                       keep only special/variant editions.
    backfill_metadata.py             — re-fetch cover/author/ISBN/price
                                       per item via fetch_metadata_from_detail.
    backfill_cluster_key.py          — add cluster_key to legacy rows.
                                       Reports the consolidation impact.
    search_discovery.py              — multi-engine discovery (Gemini
                                       grounding + Tavily + DDG HTML).
    wayback_recover.py               — for items returning 404/410, query
                                       archive.org Availability API and
                                       rebuild metadata from snapshots.
                                       Distinguishes 404/410 (real death)
                                       from 403/429 (anti-bot blocks).
  audit/
    source_health.py                 — parses N recent overnight logs
                                       and classifies sources as
                                       broken_http / broken_skip /
                                       selector_dead / low_yield /
                                       declining / healthy / unseen.
                                       Markdown or JSON output.
web/
  index.html                         — Alpine.js dashboard (PÚBLICO,
                                       deployable). Consume data/items.jsonl
                                       y POST /api/feedback.
  serve.sh                           — convenience wrapper for serve.py.
admin/
  index.html                         — Panel de Control Alpine.js (LOCAL,
                                       no deployable). Consume /api/scripts,
                                       /api/run, /api/jobs/*/stream del
                                       admin_serve.py.
tests/test_extraction.py             — pytest suite (227 tests, <1s).
docs/
  CLAUDE.md                          — THIS FILE
  ARCHITECTURE.md                    — deep dive into the pipeline
  CONTROL-PANEL.md                   — panel admin: UI, API, registry,
                                       seguridad, deploy, troubleshooting
  SOURCES.md                         — how to add/maintain sources
  PRD.md / PRD-catalog.md            — original product specs (historical)
```

## Current corpus state

After the filtering, dedup, collectible-gate, and clustering passes:

| Metric | Value |
|---|---|
| Total unique items (line in items.jsonl) | 2706 |
| Items after cluster_key grouping (dashboard cards) | 2576 (89 multi-source groups, 130 cards consolidated) |
| Sources in YAML | 120 |
| Sources enabled | 106 / 120 |
| Sources flagged `purity: mixed` | 13 |
| Bluesky sources (`kind: bluesky`) | 15 |
| Countries represented | 9 (FR, JP, ES, IT, US, MX, AR, …) |
| Image coverage | 99.4% |
| Release date coverage | 74.5% |
| ISBN coverage | 61.5% (the rest cluster via fuzzy key when possible) |
| Price coverage | 81.0% |
| Author coverage | 62.9% |
| `cluster_key` populated | 100% (precomputed by candidate_to_json) |

The drop in ISBN/author coverage vs older numbers is **expected and
healthy**: the collectible filter (`is_collectible_edition`) trimmed
~10% of the corpus (mostly regular tomos with ISBN+author), shifting
the ratio toward special editions which are JP-heavy and metadata-sparse.

These numbers help future agents sanity-check their changes — a
retrofit that suddenly drops image coverage from 99% to 60% means
something broke.

## The 7 design decisions you MUST understand

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

### 4. Multi-source grouping by `cluster_key` (ISBN OR fuzzy fallback)

`items.jsonl` keeps one line per unique URL. **Multi-source aggregation
is done at presentation by `cluster_key`**, computed once per row by
`derive_cluster_key(item)` in `manga_watch.py` and stored in the
JSONL via `candidate_to_json`. The same key is consumed by
`build_web.py` (`_group_by_cluster_key`) and the JS `dedupByUrl()`
in `web/index.html`.

Three cluster-key shapes, in priority order:
1. **`isbn:<X>`** — authoritative, ISBN is unique per edition/market.
2. **`fuzzy:<lang>|<series>|<vol>|<variant_sig>|<publisher>`** — for
   items without ISBN. All five components must be present and
   meaningful (series ≥ 3 chars, language non-empty, volume detected);
   otherwise the row falls through to standalone.
3. **`url:<url>`** — standalone, never groups with anything else.
   Triggered when a fuzzy match would be unsafe (no volume, short
   series name, no language). Better to show one card per source than
   to merge unrelated products.

When two items share a cluster_key:
- The higher-scored item is the canonical.
- Missing fields on canonical are completed from the rest (best-of merge).
- All items go into `sources[]` array preserving per-source price, URL,
  country, stock_type, etc.

**If you change the cluster_key derivation, run
`scripts/retrofit/backfill_cluster_key.py`** to update items.jsonl
in-place. The dashboard then picks up the new grouping on next load.

`_extract_volume` supports vol/tomo/tome/n./#/巻 and parenthesized
numbers including JP full-width `（15）`. `_normalize_series_name`
strips variant keywords + volume markers + bracketed retailer noise
but **preserves kanji/kana/accents** — they're discriminants for
non-Latin scripts.

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

### 6. Concurrency via ThreadPoolExecutor, NOT asyncio

The scrape loop in `manga_watch.py` uses `ThreadPoolExecutor` with
`--workers N` (default 1 for backward compat, recommended 8 for
overnight runs). Two safety rails:

- **`--per-host-limit N`** (default 2) — a per-host
  `threading.Semaphore` bounds concurrent requests to the same
  domain. Protects retailers from being hammered by search-template
  expansions of the same source family (e.g. several Panini
  search-keyword children).
- **`_js_lock`** — `playwright.sync_api` is **not** thread-safe.
  All `kind: js` sources go through one global lock and run
  one-at-a-time, while HTTP sources keep parallelizing in the same
  pool.

**`DiagnosticRecorder` is thread-safe**: every `record_*` method
accepts an explicit `entry` arg so each worker mutates its own dict
instead of racing on `self.current`. `self.entries.append` is
protected by `_entries_lock`. The shim of "implicit `self.current`"
is preserved for sequential callers (wiki bootstraps).

Why not asyncio: switching `requests`/`feedparser`/Playwright to
async would touch hundreds of call sites and rewrite three wiki
parsers. Threads buy ~6-8× speedup with ~250 LOC of change and the
existing fetch helpers untouched. The cost is GIL, but the workload
is I/O-bound — we're network-waiting, not CPU-burning.

Measured: España subset 35.7s → 6.4s (5.6×), full overnight Phase 1
projected ~26min → ~5min.

### 7. Overnight pipeline + observability over ad-hoc commands

`scripts/overnight_run.sh` is the canonical end-to-end run. 5 phases,
each in its own log file under `logs/overnight-<timestamp>/`. Skips
via `SKIP_*` env vars, opt-ins via `INCLUDE_*`. The phases:

1. **scrape** — main parallel scrape of all enabled sources
   (`--workers` + `--per-host-limit`).
2. **wikis** — `listadomanga` (calendar + blog historical),
   `manga-sanctuary`, `otaku-calendar`, `manga-mexico`. Optional:
   `whakoom` (Cloudflare-risk, opt-in).
3. **search** — `scripts/retrofit/search_discovery.py` runs Gemini +
   Tavily + DDG queries from `data/search_queries.yml`.
4. **cleanup retrofits** — `rescore` → `filter_non_manga` →
   `filter_collectible` → `clean_titles` → `backfill_metadata`
   (`--only image_url`). Optional: `wayback_recover` for 404 items
   (opt-in, ~30-60 min, run weekly).
5. **build_web** — embed final items.jsonl into the dashboard.

`scripts/audit/source_health.py` parses the last N overnight log
directories and reports source-by-source classification
(broken_http / broken_skip / selector_dead / low_yield / declining
/ healthy / unseen) as Markdown or JSON. Run after each overnight
to spot rotting selectors before they accumulate.

`scripts/retry_failed.sh` extracts source names that errored or were
skipped in the latest log and re-runs only those — fast triage
without re-scraping everything.

## Feedback de "mala elección" desde el modal

El dashboard tiene un botón **👎** en el footer del modal de detalle.
Al clickearlo se abre un textarea pidiendo el motivo por el que el item
NO debería estar en el catálogo. Al enviar:

1. JS hace `POST /api/feedback` con `{title, url, reason}`.
2. `scripts/serve.py.do_POST()` valida el body y hace append a
   `data/feedback.jsonl` con la línea:

   ```json
   {"title": "...", "url": "...", "reason": "...", "submitted_at": "<ISO 8601 UTC>"}
   ```

**Propósito.** Este archivo es la entrada para una pasada de revisión
con IA: el dueño marca items que se colaron pese a los filtros, escribe
por qué, y luego se le pasa el JSONL al asistente para que sugiera qué
patrón añadir (`_NON_MANGA_HARD` / `_NON_MANGA_SOFT` / `purity: mixed`
del source / regla nueva en `is_collectible_edition`, etc.).

**Diseño.**
- **No incluye ISBN** intencionalmente — muchos items JP no lo tienen
  y el ID práctico es la URL (ya es única en `items.jsonl`).
- **Sin auth ni rate-limit.** Single-user, server local. El POST está
  capado a 100 kB de body y exige los 3 campos no vacíos.
- **JSONL append-only** (a diferencia de `items.jsonl` que es upsert).
  Cada 👎 es un evento histórico — si el mismo item se marca dos veces
  con motivos distintos, ambas líneas se conservan.
- El archivo es gitignored junto con el resto de `data/`.

**No modificar el formato** sin actualizar el handler en `serve.py` y
el `submitFeedback()` en `web/index.html` a la vez. La IA que lee el
archivo asume las 4 claves de arriba.

## Conventions for code changes

### When you add or modify a filter pattern

There are now **four filter families**, applied in this order:
1. `is_likely_manga` — 4-rule cascade (figures, news, statues).
2. `is_pure_novel` — rejects light novels via URL hints + indicator
   words (`light novel`, `ノベル`, `light novels`); bypassed for manga
   adaptations and artbooks.
3. `is_comic_not_manga` — comics blacklist (Marvel/DC publishers,
   franchise keywords, format keywords). Applied ALWAYS (not just
   in mixed sources), bypassed when title literally contains "manga"
   (so Batmanga survives).
4. `is_collectible_edition` — second gate: keep only special editions,
   variants, deluxe, limited, box sets, artbooks, fanbooks, magazines.
   Rejects regular tomos.

Workflow when changing any of them:
1. **Find a real example** in `data/items.jsonl` (use `grep -i "..."
   data/items.jsonl | head` or a small Python script).
2. **Add a unit test** in `tests/test_extraction.py` with the exact
   user-reported string. Tests group by feature
   (`test_is_likely_manga_rejects_*`, `test_is_pure_novel_*`,
   `test_is_comic_not_manga_*`, `test_is_collectible_edition_*`).
3. **Run `pytest tests/test_extraction.py -q`** — must stay green
   (currently 227 tests).
4. **Retrofit the corpus** with the right script:
   - `is_likely_manga` / `is_comic_not_manga` change → `filter_non_manga.py`
   - `is_pure_novel` change → `filter_non_manga.py` (covers novels too)
   - `is_collectible_edition` change → `filter_collectible.py`
   - `detect_signals` / `signal_types` / `score` change → `rescore.py`
   - `clean_title` change → `clean_titles.py`
   - field extractors change → `backfill_metadata.py [--only X]`
   - `derive_cluster_key` change → `backfill_cluster_key.py`
5. **Verify the specific user examples are gone** with a quick Python
   snippet over items.jsonl.

### When you add a new source

See `docs/SOURCES.md` for the complete recipe. Quick version:
- `kind: "html"` for normal sites, `"rss"` for feeds, `"bluesky"` for
  publisher Bluesky profiles (no auth, uses public.api.bsky.app),
  `"js"` for JS-only pages (rare, requires Playwright via
  `--enable-js`).
- `selectors:` with `item_selector` and `title_selector` if the auto-
  detection misses (Tiendanube uses `[data-product-id]`, Shopify uses
  `[data-product-id]` or `li.grid__item`, etc.).
- `purity: "mixed"` if the catalog is NOT manga-only. **Note**:
  comics blacklist (`data/comics_blacklist.yml`) is applied regardless
  of purity; purity only affects `is_likely_manga`'s pack-extras rescue
  and default.
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

### When you add un script nuevo (o flag nuevo a uno existente)

El Panel de Control (`admin/index.html` + `scripts/admin_serve.py`) lee
los scripts disponibles desde **`scripts/script_registry.py`** — es la
única fuente de verdad de qué se puede ejecutar desde la UI.

1. Asegurate que tu script tenga un argparse decente.
2. Editá `scripts/script_registry.py`:
   - Si es un script nuevo, agregá un dict a `SCRIPTS` con
     `id/category/icon/name/tagline/what/when/command/presets/flags`.
   - Si es un flag nuevo en un script existente, agregá un `_flag(...)`
     a su lista `flags`.
3. Para cada flag, el `type` debe coincidir con el del argparse:
   `bool` para `action="store_true"`, `int`/`float`/`str` para
   `type=`, `choice` para `choices=`. Los `default` también deben
   coincidir.
4. Si el flag no se usa día a día, pasale `advanced=True` para que vaya
   detrás de "Mostrar opciones avanzadas" en la UI.
5. Pensá un help en español plano para alguien que no programa — los
   tooltips de la UI vienen de ahí.
6. Reiniciá `admin_serve.py` (`Ctrl+C` + `./scripts/run_local.sh`) y
   refrescá `http://localhost:8001/` — debería aparecer solo.

`admin_serve.py` valida cada request contra el registry (allowlist de
script_id + allowlist de flags por script + cast de tipos). Si el
registry y el argparse divergen, el panel devuelve errores 400
("flag desconocido para X: --foo") en lugar de ejecutar comandos
inválidos.

Ver **`docs/CONTROL-PANEL.md`** para la API completa, el modelo de
seguridad (bind 127.0.0.1, no shell, allowlist), qué incluir/excluir
del deploy, y troubleshooting.

## The 13 known gotchas

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
   `--bootstrap-wiki <name>` (listadomanga, listadomanga-blog,
   manga-sanctuary, otaku-calendar, manga-mexico, whakoom). They do
   their own filtering by calling `is_likely_manga()` inside the parser.
   Don't expect them to pick up `sources.yml` config.

9. **Word-boundary regex for signals, not substring.** Both
   `detect_signals` and `derive_product_type` route through
   `_phrase_pattern()` which builds `(?<![a-z0-9])phrase(?![a-z0-9])`
   for ASCII and plain substring for CJK. Required because
   "poster" was matching inside "posters", "artbook" inside "artbooks",
   "cofanetto" inside source name "Cofanetti". Use `_phrase_pattern`
   for any new keyword detector.

10. **`signal_types` come from THE ITEM only.** `detect_signals` runs
    on `title + description` exclusively. NEVER feed source name,
    publisher, tags, or search-template keywords into it — source
    "IT - Panini Edizioni da Collezione e **Cofanetti**" once
    contaminated every item with `box_set`. The source-class boost
    is applied separately by `score_candidate`.

11. **Comics blacklist uses word boundaries with "manga" bypass.**
    `is_comic_not_manga` checks publisher equality (Marvel/DC) plus
    franchise/format keywords with `(?<![\w])kw(?![\w])` — so
    "Batman" doesn't kill "Batmanga" (the Jiro Kuwata manga). If the
    title contains the word "manga" the entire blacklist is bypassed.
    Edit `data/comics_blacklist.yml` to extend; don't add publishers
    that also publish manga (Panini, Norma, Planeta).

12. **Playwright sync is not thread-safe.** Under `--workers > 1` all
    `kind: js` sources are serialized through a global `_js_lock` —
    they coexist in the same pool but never run concurrently with
    each other. HTTP sources keep parallelizing. If you ever add
    async-Playwright, lift the lock.

13. **Wayback recovery treats 403/429 as alive, not dead.**
    `wayback_recover.py` only tries to recover items returning
    **404 or 410**. 403/429/5xx are anti-bot blocks (Kadokawa,
    Bookoff…) where the page is alive but won't serve our UA —
    queueing those to Wayback would burn API quota for nothing.
    Don't relax this filter without seeing the real status
    distribution first (`--check` mode).

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
13. `is_collectible_edition` second gate + `is_pure_novel` detector +
    comics blacklist with `manga` bypass + `kind: bluesky` support +
    15 Bluesky publisher sources + 2 new wikis
    (`listadomanga_blog` historical, `whakoom` 3-level spider).
14. Multi-engine search discovery: Gemini API with Grounding (free
    500 RPD) + Tavily (1k/mo) + DDG HTML, priority-routed via
    `data/search_queries.yml`.
15. `scripts/overnight_run.sh` — chained 5-phase end-to-end pipeline
    with per-phase logs and skip/include env vars.
16. `scripts/audit/source_health.py` — classifies sources from recent
    overnight logs as broken / declining / healthy / unseen.
17. `scripts/retrofit/wayback_recover.py` — recovers 404 items via
    archive.org Availability API + clean snapshot extraction.
18. `signal_types` UI filter (chip multi-select in dashboard sidebar).
19. Parallelization via `--workers` / `--per-host-limit` with
    thread-safe DiagnosticRecorder and JS-source lock. 5-8× speedup.
20. `derive_cluster_key` for grouping beyond ISBN (fuzzy
    lang+series+vol+variants+publisher) — consolidates ~7% more
    multi-source cards in the dashboard.

## Quick sanity check before committing

```bash
.venv/bin/python -m pytest tests/test_extraction.py -q    # must be green (227)
.venv/bin/python scripts/retrofit/filter_non_manga.py --dry-run   # expect 0 rejections if patterns are stable
# If you touched filters:
.venv/bin/python scripts/retrofit/filter_non_manga.py
.venv/bin/python scripts/retrofit/filter_collectible.py   # if is_collectible_edition changed
# If you touched signals / scoring:
.venv/bin/python scripts/retrofit/rescore.py
# If you touched clean_title:
.venv/bin/python scripts/retrofit/clean_titles.py --dry-run
# If you touched extractors, optionally:
.venv/bin/python scripts/retrofit/backfill_metadata.py --dry-run
# If you touched derive_cluster_key:
.venv/bin/python scripts/retrofit/backfill_cluster_key.py --dry-run
```

## Next things on the radar (not committed to)

These came up in conversation but were explicitly deferred:

- **SQLite migration.** Postponed until multi-user / deploy. See
  ARCHITECTURE.md for the trigger conditions and the migration plan.
- **Censored cover modals** (e.g. Listado Manga has an "accept adult
  content" modal). Currently scraper sees the placeholder. Would
  require Playwright or per-source cookie injection.
- **Price history per item.** Once an item changes price, the new value
  overwrites the old in upsert. If we want a price history we need a
  separate `events.jsonl` or, again, SQLite.
- **async/httpx migration.** ThreadPoolExecutor + GIL is fine at
  current scale; a true async rewrite would buy marginal gains over
  the existing parallel implementation and would touch every fetch
  helper. Only revisit if we hit ~500+ sources or need per-request
  cancellation semantics.

---

Last updated: 2026-05-21 — sweep update after Sprints 1 / 2.4 / 2.5
/ 2.6 / 3.8: collectible/novel/comics filters, multi-engine search,
overnight pipeline + source-health audit, Wayback recovery, scrape
parallelization, cluster_key grouping. **+ Panel de Control web local
(admin/, scripts/admin_serve.py, scripts/script_registry.py,
scripts/run_local.sh) — server admin separado del público, bind a
127.0.0.1, no deployable. Ver `docs/CONTROL-PANEL.md`.** If you find
this file stale relative to the code, update it (per the Documentation
policy at the top of this file).
