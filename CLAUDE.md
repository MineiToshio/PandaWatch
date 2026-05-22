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

### MANDATORY pre-flight checklist (run this BEFORE saying "done")

Before declaring ANY task complete, walk through this checklist out loud
(in your response or thinking):

1. **Schema?** Did `items.jsonl`, `state.json`, `feedback.jsonl`,
   `unmapped_series.jsonl`, `non_manga_blacklist.jsonl`, or a new YAML/JSON
   file change shape? → Update CLAUDE.md schema docs + ARCHITECTURE.md
   data-flow section.
2. **Sources?** Did `sources.yml` gain/lose entries, or a source's
   `purity`/`kind`/`selectors`/`enabled` change? → Update CLAUDE.md
   counters (corpus state table, sources count) + docs/SOURCES.md.
3. **Filters / signals / scoring?** Changes to `is_likely_manga`,
   `is_collectible_edition`, `is_comic_not_manga`, `is_pure_novel`,
   `detect_signals`, `COLLECTIBLE_EDITION_SIGNAL_TYPES`,
   `_GENERIC_X_EDITION_PATTERN`? → Update CLAUDE.md design decisions +
   gotcha if relevant.
4. **New module under `scripts/`?** Wiki parser, retrofit, audit,
   skill helper? → Add to CLAUDE.md "File map" + appropriate doc
   (scripts/retrofit/README.md for retrofits, docs/SOURCES.md for wikis,
   etc.).
5. **New skill under `.claude/skills/`?** → Add entry to file map +
   `.claude/skills/README.md` (skills index).
6. **New gotcha?** Mojibake variant, parser quirk, anti-bot bypass,
   filter false-positive, dedup edge case? → Append to "known gotchas"
   section + bump the count in heading.
7. **Corpus numbers changed >2pp?** → Re-run the stats snippet and
   update the "Current corpus state" table.
8. **New CLI flag, env var, dependency, external service?** → CLAUDE.md
   + `.env.example` if applicable + the doc that owns it.
9. **Did a multi-turn task accumulate? Bump "Last updated"** with a
   one-paragraph summary of what changed across the turns — even if
   each turn updated docs incrementally. The summary helps future
   readers understand the WHY.

**What counts as "meaningful"** (any one of these triggers the checklist):
- New scraper feature, pipeline stage, CLI flag, endpoint in serve.py.
- Change to filters / scoring that shifts behavior.
- Source added/removed/reconfigured.
- New wiki/retrofit/audit script, new skill, new pipeline helper.
- Schema change to any data file in `data/`.
- New gotcha discovered.
- Corpus numbers shift >2 percentage points.
- New env var, new dependency, new external service (Anilist, Wikidata, etc.).

**What does NOT need docs** (only these — be strict):
- Bug fixes that restore documented behavior (the doc was already right).
- Test additions for already-documented rules.
- Pure refactors with zero behavioral change (test suite must prove it).
- Typo fixes.

**Where each kind of change goes**:

| Change type | File to update |
|---|---|
| Design intent, conventions, gotchas, corpus state, schema reference | `CLAUDE.md` (this file) |
| Pipeline internals, data flow, module responsibilities, ASCII diagrams | `docs/ARCHITECTURE.md` |
| How to add/maintain a source, selector recipes, source-specific quirks | `docs/SOURCES.md` |
| Retrofit utility behavior (one-shot scripts under `scripts/retrofit/`) | `scripts/retrofit/README.md` |
| Skills (`.claude/skills/*.md`) — what they do, when to invoke | `.claude/skills/README.md` |
| New env var, new dependency | `.env.example` + the file above that fits |
| Product scope / vision change | `docs/PRD.md` or `docs/PRD-catalog.md` |
| Control Panel features | `docs/CONTROL-PANEL.md` |

**Anti-patterns** (these violate the policy):

- ❌ "Lo documento después en otro commit". No — same turn, same commit.
- ❌ "Solo agregué un retrofit chiquito". Same rule — `scripts/retrofit/README.md`
  needs the entry.
- ❌ Updating only the "Last updated" line without filling in details.
- ❌ Bumping gotcha count but forgetting to update the heading.
- ❌ Adding a new field to items.jsonl without documenting it in CLAUDE.md
  + ARCHITECTURE.md.
- ❌ Creating a new file (skill, doc, script) without referencing it from
  the file map in CLAUDE.md.

**If the user pushes back that docs are stale, that's a regression on
this policy — treat it as a bug to fix immediately, not a feature
request.** Apologize briefly, fix the docs in the same turn, and run
the pre-flight checklist for the past changes that slipped through.

## What this project is

**PandaWatch** (repo: `MineiToshio/PandaWatch`, also known internally as
`manga-watch`) is a **personal tracker** that scrapes ~118 enabled sources
(of 134 defined in `sources.yml`) across 10 countries and 6 languages
(ES, EN, FR, IT, JP, PT-BR) looking for
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
    mangavariant.py                  (Global — base curada de variants
                                       en 13 países, ~2700 entries.
                                       URLs son páginas-referencia, sin
                                       precio. Yoast sitemap → detail
                                       parser. Ver "URL como referencia"
                                       más abajo.)
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
    expand_whakoom_ediciones.py      — convierte filas con URL
                                       /ediciones/<id>/<slug> en N filas
                                       /comics/<X>/<slug>/<vol> (una por
                                       tomo). Whakoom usa /ediciones/ como
                                       índice de la colección; el catálogo
                                       es por tomo. Soporta one-shots vía
                                       /login?ReturnUrl=/comics/... fallback.
                                       Ver gotcha #14.
    expand_index_pages.py            — limpia páginas-índice guardadas como
                                       productos: Whakoom /publisher/
                                       (expande a /ediciones/ → tomos),
                                       Shopify multi-tomo variants (Dark
                                       Horse Direct usa <select> Volume 1/2/3
                                       para una serie entera), /blogs/news/
                                       (elimina), /collections/X sin /products/
                                       (elimina). Ver gotchas #14, #16, #17.
  audit/
    source_health.py                 — parses N recent overnight logs
                                       and classifies sources as
                                       broken_http / broken_skip /
                                       selector_dead / low_yield /
                                       declining / healthy / unseen.
                                       Markdown or JSON output.
    unmapped_series.py               — lista series_keys de items.jsonl
                                       que NO están en series_aliases.yml,
                                       agrupadas + fuzzy-matched contra
                                       canonicals existentes. Lo consume
                                       el skill enrich-series-aliases.
  series_aliases.py                  — `canonical_series_key()` resolver
                                       + `log_unmapped_series()` (escribe
                                       a data/unmapped_series.jsonl
                                       cuando una nueva series_key no
                                       está en aliases.yml). Ver gotcha #20.
.claude/skills/
  enrich-series-aliases.md           — Skill manual: procesa unmapped
                                       series del queue, consulta Anilist,
                                       agrega entries a series_aliases.yml,
                                       corre backfill. Ver gotcha #20.
  standardize-catalog.md             — Skill manual incremental: para items
                                       sin `standardized_at`, delega
                                       subagentes en paralelo (chunks ~150)
                                       que asignan series_key/edition_key,
                                       estandarizan título, mueven non-manga
                                       a blacklist, deduplican. Solo procesa
                                       items nuevos — los antiguos llevan
                                       timestamp y se saltean. Ver gotcha #21.
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
| Total unique items (line in items.jsonl) | 4436 (post variant signal + mangadreams variants-europeas, 2026-05-22) |
| Items aportados por Mangavariant bootstrap | 2625 (de 2679 URLs en sitemap, 54 reasignados) |
| Items movidos a `data/non_manga_blacklist.jsonl` | 94 (cómics occidentales, light novels, posters, figuras, etc.) |
| Items deduplicados por (series_key, edition_key, volume) | 690 (+6 más al re-merger 38 items mangadreams contra Kurokawa/Pika/Star Comics existentes) |
| Distinct `series_key` (filtro por obra) | 1428 |
| Distinct `edition_key` (filtro por edición+editorial) | 2918 |
| `data/series_aliases.yml` entries | 106 canonical works (Anilist + manual) |
| Sources in YAML | 137 |
| Sources enabled | 121 / 137 |
| Sources flagged `purity: mixed` | 17 |
| Bluesky sources (`kind: bluesky`) | 15 |
| Countries represented | 15 (Japón, Francia, Italia, España, Estados Unidos, Vietnam, México, Alemania, Tailandia, Brasil, Argentina, España/LatAm, Taiwán, Reino Unido + Global). |
| Image coverage | 100.0% |
| `series_key` coverage | 100.0% (todos los items tienen serie canónica) |
| `edition_key` coverage | 100.0% |
| `volume` coverage | 78.9% (vacío para artbooks, cover-only, one-shots) |
| Release date coverage | 86.3% |
| ISBN coverage | 30.5% |
| Price coverage | 39.9% |
| Author coverage | 30.3% |
| `cluster_key` populated | 100% (precomputed by candidate_to_json) |

Las bajadas de ISBN/Price/Author **NO son regresiones** — son el efecto
esperado de añadir 2679 filas curadas que por diseño no tienen esos
campos (la fuente cataloga "qué variant existe", no "dónde comprarlo
con qué ISBN"). Ver "URL como referencia" más arriba. El enrichment
script futuro va a poblar precios/ISBN para filas mangavariant que
matcheen un retailer real.

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
- ES - ECC Manga (publica manga + DC superhéroes)
- ES - Planeta Cómic
- US - Anime News Network News RSS
- US - ComicBook.com Anime
- US - Kodansha USA News
- JP - Rakuten Books (search) variants
- BR - Panini Brasil (search) (álbumes Copa, figurinhas)
- BR - Pipoca & Nanquim (manga + BD europea)
- BR - Devir Brasil (RPG + literatura + manga minoritario)

### 4. Multi-source grouping by `cluster_key` (ISBN OR fuzzy fallback) — tier-based variant discriminant

`items.jsonl` keeps one line per unique URL. **Multi-source aggregation
is done at presentation by `cluster_key`**, computed once per row by
`derive_cluster_key(item)` in `manga_watch.py` and stored in the
JSONL via `candidate_to_json`. The same key is consumed by
`build_web.py` (`_group_by_cluster_key`) and the JS `dedupByUrl()`
in `web/index.html`.

Three cluster-key shapes, in priority order:
1. **`isbn:<X>`** — authoritative, ISBN is unique per edition/market.
2. **`fuzzy:<lang>|<series>|<vol>|<variant_tier>|<publisher>`** — for
   items without ISBN. All five components must be present and
   meaningful (series ≥ 3 chars, language non-empty, volume detected);
   otherwise the row falls through to standalone. `variant_tier` is
   the **most specific** entry from `_VARIANT_TIER_RULES` matching the
   item's signal_types, NOT the full set. See "variant tier" below.
3. **`url:<url>`** — standalone, never groups with anything else.
   Triggered when a fuzzy match would be unsafe (no volume, short
   series name, no language). Better to show one card per source than
   to merge unrelated products.

**Variant tier (replaces the old comma-joined `variant_sig`):**

Distintas fuentes detectan signal_types ligeramente distintos para el
**mismo producto físico** porque sus descripciones son distintas (un
retailer dice "Edición coleccionista" → ["collector"]; mangavariant
agrega "Tags: bonus, special_edition" → ["bonus", "special_edition",
"collector", "lore_edition"]). Si usáramos el set completo como
discriminante, nunca mergearían. Por eso `_variant_tier(signal_types)`
elige el **primer tier que matchee** en este orden (de más específico a
menos):

```
artbook  > omnibus  > box_set      > kanzenban      >
lore_edition (X-Anniversary, Celebration…)  >
variant_cover (cover variants / retailer-exclusives)  >
deluxe (deluxe/hardcover/oversized)  > limited  >
special (special_edition/collector/bonus/finish)  >  "" (tomo regular)
```

Two items in the SAME tier merge. Two items in different tiers don't
(OP100 Deluxe ≠ OP100 Celebration, aunque ambos tengan ~vol 100~).

Caso real que motivó este diseño: **One Piece Vol.98 Celebration
Edition** aparecía dos veces en el dashboard porque Star Comics search
detectaba `[collector, lore_edition]` mientras Mangavariant detectaba
`[bonus, special_edition, collector, lore_edition]`. Ambos colapsan a
`tier=lore_edition` → mergean en una sola card. Tests en
`tests/test_extraction.py::test_cluster_key_one_piece_98_celebration_merges_across_sources`.

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

## URL como referencia (no de tienda) — política

**PandaWatch acepta items cuya `url` NO lleva a una tienda.** Wikis,
bases comunitarias y directorios son fuentes de primera clase: la meta
del proyecto es **descubrir qué variantes / ediciones especiales
existen en el mundo**, no solo "dónde están a la venta hoy".

Ejemplos concretos:
- `Global - Mangavariant` (`https://mangavariant.com/variant/<manga>/<edicion>/`)
  es página de referencia: tiene serie, país, publisher, año, rarity,
  tags, cover image — **pero no precio ni botón de compra**.
- ListadoManga (`/zonas/preventa/...`) y el blog histórico son
  anuncios editoriales, no listings de tienda.
- Manga-Sanctuary (`/planning_sortie/...`) es catálogo comunitario FR.
- Whakoom (`/comics/<X>/<slug>/<vol>`) es catálogo de coleccionistas.

**Reglas que se derivan de esto:**
- **No filtrar** items por falta de `price` / `stock_type`. Una card
  sin precio es válida — el dashboard la muestra igual.
- **No eliminar** wikis/bases referencia para "limpiar" el corpus.
  Cuando un item de referencia matchea cluster_key con uno de retailer,
  se consolidan; el de referencia suele quedar como card canónica y los
  retailers aparecen como "dónde comprar".
- **Enrichment**, si llega, es una pasada **separada** que toma items
  de referencia y busca su URL de tienda (no filtro upstream que los
  descarte).
- Documentado y guardado en memoria persistente (`feedback_url_as_reference.md`)
  porque el owner lo flageó varias veces.

## The 23 known gotchas

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

14. **Whakoom `/ediciones/` no es un tomo, es una colección.**
    `https://whakoom.com/ediciones/<id>/<slug>` indexa la edición entera
    (p.ej. "Berserk Deluxe Edition" = 14 tomos). El catálogo es por tomo,
    así que NUNCA hay que guardar una `/ediciones/` URL como item.
    Siempre se expande vía `wikis.whakoom.expand_whakoom_edition()` →
    N candidates, uno por cada `/comics/<shortcode>/<slug>/<vol>`. Casos:
    - **Multi-vol**: la página principal lista los primeros ~11 tomos en
      `<li id="comic*">`; el resto vive en `<edition_url>/todos` (una
      request HTTP extra). El helper carga ambas y mergea por URL.
    - **One-shot (1 tomo)**: la `/comics/` URL solo aparece dentro de
      `/login?ReturnUrl=/comics/<X>/<slug>`. Hay fallback que la extrae.
    Tres puntos de ingesta protegidos: `search_discovery.py` (intercepta
    URLs `/ediciones/` Y `/publisher/` antes de guardarlas), `wikis/whakoom.py`
    (Fase 3 del spider expande cada edición), `Whakoom Novedades` (la fuente
    regular ya emite `/comics/` por su selector `a[href^='/comics/']`,
    no necesita interceptación). Retrofit: `expand_whakoom_ediciones.py`
    para limpiar `/ediciones/` legacy + `expand_index_pages.py` cubre
    también `/publisher/`.

    También se aplica a **Whakoom `/publisher/<id>/<slug>`**: es la página
    del editor que lista sus `/ediciones/`. `expand_whakoom_publisher_url`
    extrae las ediciones del HTML y llama a `expand_whakoom_edition` por
    cada una — dos niveles de expansión.

15. **Whakoom requiere `Accept-Encoding: gzip, deflate` SIN `br`.**
    El servidor sirve Brotli cuando se lo pide. `requests` no decodifica
    Brotli nativamente (sin la lib `brotli` instalada) y entonces
    `response.text` es bytes binarios — el parser ve "0 tomos", "0
    metadata", silenciosamente. Hubo un bug por esto: el spider devolvía
    HTML basura sin error. El UA-session de `wikis/whakoom.py` EXCLUYE
    `br` del Accept-Encoding por esto. Si alguien lo re-agrega, agregar
    también `brotli` a `requirements.txt`.

    **Falso positivo previo en CF challenge detector**: el marker
    `challenge-platform` matcheaba el script JSD legítimo
    (`/cdn-cgi/challenge-platform/scripts/jsd/main.js`) que Cloudflare
    inyecta en TODAS las páginas que protege. Los markers reales de
    challenge son específicos: `cf-chl-bypass`, `__cf_chl_rt_tk`, o el
    path `/cdn-cgi/challenge-platform/h/` (UI del challenge, no
    `/scripts/`). Si volvés a tocar `_CLOUDFLARE_CHALLENGE_MARKERS`,
    asegurate de que un fixture válido de Whakoom NO matchee.

16. **Shopify variants multi-tomo: 1 producto = N SKUs.** Sitios Shopify
    como Dark Horse Direct modelan series ("Berserk Deluxe Hardcover
    Volumes") como UN solo `og:type=product` con un `<select>` que
    expone N variants (Volume 1 / 2 / 3 / ...). Cada variant tiene su
    propio `variant_id`, `sku`, `price` y deep-link vía `?variant=<id>`.
    Estructuralmente es lo mismo que Whakoom `/ediciones/`: el catálogo
    es por tomo, así que estos productos hay que expandirlos.
    Helpers en `scripts/shopify_variants.py`:
    - `extract_shopify_variants(html)` — saca los variants del JSON
      embebido (patrón `"variants":[...]`) o del `<select data-variant-id>`.
    - `is_volume_variants(variants)` — heurística que requiere al menos
      un variant con keyword de volumen ("Volume N", "Tome N", "#N",
      "第N巻", etc.) para evitar expandir productos con variants de color
      o talle. Single-variant ("Default Title") también devuelve False.
    - `build_variant_url(parent, id)` — construye `?variant=<id>` y
      limpia tracking de Shopify (`_pos`, `_sid`, `_ss`).
    Retrofit `expand_index_pages.py` aplica esta lógica a Dark Horse
    Direct + cualquier futuro Shopify multi-tomo. **Importante**: la
    detección se restringe a dominios donde sabemos que esto pasa (hoy
    solo `darkhorsedirect.com`). Otros Shopify (mangadreams.it,
    milkyway, etc.) no usan variants para volúmenes y NO se chequean.

17. **`url_is_useful` (search_discovery) bloquea índices conocidos.**
    El blacklist en `search_discovery.py` rechaza URLs que NUNCA son
    productos: `/lists/`, `/profile/`, `/blogs/news/`, `/collections/X`
    (sin `/products/Y`), `whakoom.com/(autores|tag)/`, social media
    posts, YouTube, Reddit, etc. Si Gemini/Tavily devuelven una de
    estas, las descartamos antes de gastar HTTP en detail-fetch.
    Whakoom `/publisher/` queda FUERA del blacklist porque sí se
    expande (a sus /ediciones/ → tomos). Si agregás un patrón nuevo
    al blacklist, verificá que no esté en el set de URLs que el
    overnight pipeline necesita procesar.

18. **Omnibus / "X en X" / "X-in-X" NO califican solos como coleccionables.**
    Decisión del owner (2026-05-22): "ediciones ómnibus o 2 en 1 o 3 en 1
    a menos que sean hardcover o ediciones premium, con portada alternativa
    o con algún extra — sino son prácticamente ediciones normales con más
    páginas". Por eso:
    - `omnibus` se quitó de `COLLECTIBLE_EDITION_SIGNAL_TYPES`. Como
      otros qualifiers premium (hardcover, deluxe, limited, variant_cover,
      box_set, bundle, etc.) SÍ están en el set, un omnibus premium
      sigue pasando vía ellos. Solo el omnibus "pelado" se rechaza.
    - `_GENERIC_X_EDITION_PATTERN` excluye específicamente "Omnibus" para
      que "Omnibus Edition" NO dispare `lore_edition` por puerta trasera.
      "Tarot Edition", "Gold Edition", etc. siguen activos.
    Casos rechazados (ejemplos del corpus): "Bestiarius Omnibus", "One Piece
    (3 En 1) N.1", "Akatsuki no Yona (3 en 1)", "ALL YOU NEED IS KILL
    INTEGRAL", "EL CASTILLO DE LOS ANIMALES. INTEGRAL 2".
    Casos aceptados (premium qualifier): "Lone Wolf & Cub Omnibus –
    Cofanetto 3" (box_set), "Berserk Tarot Edition" (lore_edition desde
    "Tarot"), "Utena Edición Integral - Cofre de 2 tomos"
    (hardcover+box_set), "17 Años (Edición Integral) - (1ª Edición Limitada)"
    (limited). 91 items omnibus-only fueron limpiados retroactivamente
    el 2026-05-22.

19. **Rakuten Books usa `?l-id=search-c-item-img-NN` como tracking de slot.**
    Cada listing en Rakuten genera un `l-id` distinto para la MISMA URL de
    producto (`/rb/<id>/`). Si scrapeás 5 búsquedas distintas que devuelven
    la misma SKU, terminan 5 filas duplicadas en items.jsonl porque la URL
    completa cambia. `l-id` y `l_id` están agregados a `TRACKING_PARAMS` en
    `normalize_url_for_dedup` (manga_watch.py) — el upsert por URL ya los
    colapsa. 182 clones eliminados retroactivamente el 2026-05-22. Si añadís
    un tracking param nuevo encontrado en otra fuente, agregalo a ese
    frozenset para que el upsert lo ignore.

20. **Una obra tiene N nombres según mercado/idioma.** Por ejemplo Demon
    Slayer = Kimetsu no Yaiba (JP romaji) = 鬼滅の刃 (JP native) =
    Guardianes de la Noche (ES México). Para que el filtro por obra
    funcione, todos esos series_keys deben colapsar al canónico
    (`demon-slayer`). La fuente de verdad es **`data/series_aliases.yml`**:

    ```yaml
    demon-slayer:
      display: Demon Slayer
      aliases:
        - kimetsu no yaiba
        - 鬼滅の刃
        - guardianes de la noche
    ```

    La resolución la hace `scripts/series_aliases.py::canonical_series_key()`,
    integrada en `candidate_to_json` para que CADA item nuevo del scraper
    pase por el normalizador automáticamente. Reglas de matching:
    - **Match exacto only**: compara `current_series_key` y `current_display`
      (normalizados: lowercase, sin diacríticos, slug) contra el índice
      del YAML. NO hace substring-match en el title — eso generaba
      false-positives tipo "Monster Musume → Monster (Urasawa)".
    - **Sin match → input intacto**: si la serie no está en el YAML,
      devuelve el series_key actual sin tocar. Mantenimiento incremental:
      cuando aparece una variante nueva, se agrega al YAML.

    El YAML inicial (~108 series, 2026-05-22) se armó con:
    - Anilist API GraphQL (`https://graphql.anilist.co`) — devuelve
      `title.english`, `title.romaji`, `title.native`, `synonyms[]`
      multilingües por cada serie buscada.
    - Override manuales para casos donde Anilist tira false matches
      (ej. Anilist devuelve "Knights of the Zodiac" como english de Saint
      Seiya → override manual a "Saint Seiya" canónico).
    - Fragmentaciones detectadas en el corpus existente (apothicaire/
      apothecary-diaries, atelier-des-sorciers/witch-hat-atelier, etc.).

    **Mantenimiento via queue + skill** (2026-05-23):
    - Cuando un scrape encuentra un item con `series_key` NO listado en
      `series_aliases.yml`, el hook en `candidate_to_json` lo appendea
      a `data/unmapped_series.jsonl` (append-only, dedupe por key
      dentro del mismo run vía `_UNMAPPED_LOGGED_THIS_RUN`).
    - El usuario invoca el skill `enrich-series-aliases` cuando quiere
      curar el backlog. El skill vive en
      `.claude/skills/enrich-series-aliases.md` y orquesta:
      1. `scripts/audit/unmapped_series.py` → tabla agrupada por
         series_key con fuzzy-match contra canonicals existentes.
      2. Para cada candidata: decidir alias-de-existente / new-canonical /
         skip. Consultar Anilist API si necesita traducciones.
      3. Editar `data/series_aliases.yml`.
      4. Backfill sobre `items.jsonl` aplicando las nuevas reglas
         (Python snippet incluido en el skill).
      5. Truncar `unmapped_series.jsonl` y reportar.
    - Futuro: el skill podría engancharse a un cron (vía `/schedule`)
      para correr semanal. Por ahora es manual.

    Cuando agregues una serie nueva al YAML manualmente:
    1. Buscar en Anilist por título conocido para obtener titles+synonyms.
    2. Curar aliases — quitar transliteraciones a alfabetos no-target
       (cyrillic, arabic, hebrew, hangul, thai) y synonyms ambiguos
       (palabras genéricas como "Monster", "Real", "Blue Period" si ya
       designan otras series).
    3. Después de editar el YAML, correr el backfill manual sobre
       items.jsonl si querés consolidar legacy rows (no hay retrofit
       formal — un Python snippet usando `canonical_series_key()`
       basta).

    220 items remapped en la corrida inicial. Sin retrofit script,
    porque el hook en `candidate_to_json` ya cubre el caso del scraper
    futuro.

21. **Flujo de doble pasada: scraper hace asignación cruda, skill la corrige.**

    - **Pasada 1 (scraper, automática)**: `manga_watch.py::candidate_to_json`
      llama `derive_series_metadata()` que aplica un heurístico rápido
      basado en regex sobre el title + publisher + signal_types.
      Devuelve series_key/edition_key/volume/title_standardized.
      Pasa por `canonical_series_key()` (aliases.yml) para consolidar
      traducciones. **Items quedan SIN `standardized_at`** — esa marca
      la setea solo el skill.

      Casos donde el heurístico devuelve EMPTY (mejor que wrong):
      * series_key < 3 caracteres tras slug.
      * series_key todo dígitos (probable volumen mal capturado).
      * series_key termina con `-N` y volumen no detectado
        (ej. "atomic-robo-5", "berserk-41" sin marker "vol/tome/巻").

      En esos casos el item se guarda sin series_key/edition_key. El
      skill lo procesa después con LLM para asignar correctamente.

    - **Pasada 2 (skill `/standardize-catalog`, manual incremental)**:
      Lee items sin `standardized_at`, delega chunks de ~150 a subagentes
      LLM en paralelo, RE-DERIVA todo desde cero (no confía en lo que
      el scraper puso), aplica canonical_series_key, mueve no-manga a
      blacklist, dedupea, marca con `standardized_at`. El skill VERIFICA
      y corrige la asignación rough del scraper.

    `standardized_at` (ISO timestamp UTC) indica cuándo pasó el item
    por la pasada 2. Sirve como flag de "this item has been LLM-verified".

    - **Items sin `standardized_at`** son los que el skill procesa: lo
      típico es items recién scrapeados que llegaron a items.jsonl
      directamente desde manga_watch.py sin pasar por la pasada de
      curación.
    - **Items con `standardized_at`** se saltean. No se re-procesan
      (ahorro de costo de LLM/subagentes).
    - **`--force-all` re-procesa todo**: el skill incluye un snippet
      para limpiar `standardized_at` de todos los items y forzar un
      re-run completo (cuando cambias las reglas de estandarización
      sustancialmente, ej. nuevo set de edition_slugs).

    El pipeline NO setea `standardized_at` por sí mismo — solo el skill
    lo escribe al final del merge. Items nuevos del scraper aparecen
    SIN el flag, listo para que el skill los procese en la próxima
    invocación.

    Reglas operativas:
    1. Después de cada `manga_watch.py` scrape grande, correr
       `/standardize-catalog`. Procesa solo lo nuevo.
    2. Luego correr `/enrich-series-aliases` si aparecieron series_keys
       nuevas que no están en `series_aliases.yml` (el skill anterior
       las loguea en `data/unmapped_series.jsonl`).
    3. Los dos skills se complementan: `standardize-catalog` asigna los
       campos schema-level; `enrich-series-aliases` consolida nombres
       multilingües.

22. **`title` es international canonical, `title_original` preserva el scrape.**

    Cada item lleva DOS campos de título:

    - **`title`** — display canonical estandarizado al formato
      `{Series} {Edition} {Volume}` en inglés/internacional. Es lo que
      se ve en las cards del dashboard. Ejemplo: `"Demon Slayer Limited 23"`.
    - **`title_original`** — el título tal como vino de la fuente, después
      de `clean_title()` (mojibake fixed, junk removido) pero ANTES de
      la estandarización. Preserva el lenguaje y estilo del scrape.
      Ejemplos: `"鬼滅の刃 23 特装版"` (Rakuten JP),
      `"Guardianes de la Noche Vol 23"` (Panini México), `"Les Carnets
      de l'Apothicaire Coffret 5"` (Ki-oon FR).

    **Por qué los DOS:**

    - **UX**: audiencia ES/EN ve el canonical internacional, scanneable y
      consistente. Si un mismo manga aparece desde 5 fuentes en 5 idiomas,
      la card NO es esquizofrénica — un solo display.
    - **Búsqueda**: el dashboard indexa AMBOS campos en `filtered()`. Tipear
      "Demon Slayer" / "鬼滅の刃" / "Guardianes de la Noche" /
      "Kimetsu no Yaiba" encuentra el mismo item. Cero pérdida de
      flexibilidad.
    - **Audit/exportación**: si alguna vez querés data al estilo MyAnimeList
      con multilingüe completo, ya tenés el original.

    **Cuándo se popula cada uno:**

    - **`title_original`** se setea EN EL SCRAPER (`candidate_to_json`)
      copiando `candidate.title` (que ya pasó por `clean_title`). Siempre
      se escribe — items nuevos garantizan tener el original.
    - **`title`** lo escribe la pasada 1 del scraper igual a `title_original`.
      Después la pasada 2 (skill `/standardize-catalog`) lo sobrescribe con
      `title_standardized` ("Demon Slayer Limited 23"). El skill detecta
      si `title_original` ya está set; si no, hace backup antes de
      sobrescribir.

    **Frontend** (`web/index.html`):

    - Card: solo muestra `title` (clean, scaneable).
    - Modal: muestra `title` prominente arriba. Si `title_original`
      difiere, muestra una segunda línea en gris itálico con el prefijo
      `原題:` (etiqueta JP de "título original").
    - Search: el `filtered()` indexa `title + title_original +
      series_display`. Una sola búsqueda matchea cualquier idioma.

    **Dedup**:

    - **Pipeline dedup** sigue siendo por `(series_key, edition_key, volume)`
      — keys canónicas, no por texto. Más robusto que comparar títulos.
    - **Search del usuario** SÍ matchea por título text-based contra ambos
      campos. Eso es UX, no dedup — la decisión de "esto es duplicado"
      se hace por keys.

    Items históricos backfilled tienen `title_original = title` (perdimos
    el original porque el skill previo sobrescribió antes de existir este
    campo). Items futuros del scraper tienen el original real preservado.

23. **`append_jsonl` preserva los campos seteados por `/standardize-catalog`
    al re-scrapear.**

    El upsert por URL (`append_jsonl` en `manga_watch.py`) por defecto
    reemplazaba la fila completa, BORRANDO `standardized_at` + título
    canónico + `series_key`/`edition_key`/`volume` cada vez que el
    scraper veía la URL otra vez. Resultado: un `--include-seen` sobre
    una fuente ya ingerida revertía todo el trabajo del skill.

    El fix (2026-05-22): cuando la fila existente tiene `standardized_at`,
    `append_jsonl` hace MERGE en vez de replace — preserva los campos
    curados por el skill y refresca solo los scrapeados (price, image_url,
    isbn, author, signal_types, score, detected_at, stock_type). Lista
    completa de campos preservados en la constante `_CURATED_FIELDS`
    dentro de la función.

    **Implicación**: si cambiás reglas de estandarización
    (`_PUBLISHER_SLUG_MAP`, edition_slugs, lógica de `derive_series_metadata`,
    etc.) y querés que los items existentes se re-procesen, NO basta con
    re-scrapear — hay que correr el snippet `--force-all` del skill que
    limpia `standardized_at` de todo el corpus. Ver el final de
    `.claude/skills/standardize-catalog.md`.

    Tests: `test_append_jsonl_preserves_curated_fields_on_standardized_items`
    + `test_append_jsonl_does_not_preserve_when_no_standardized_at` cubren
    ambos paths.

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
- **Enrichment pass para items de referencia.** Items que llegaron
  de Mangavariant / wikis tienen serie + volumen + publisher + país
  pero no precio ni URL de tienda. La idea (acordada con el owner
  2026-05-22) es un script aparte (e.g. `scripts/retrofit/enrich_references.py`)
  que para cada item de referencia haga una búsqueda dirigida (Tavily /
  Gemini grounding / search en retailers por publisher) y agregue las
  URLs de tienda encontradas al array `sources[]` del cluster. NO es
  un filtro upstream — los items de referencia siguen siendo válidos
  aunque no encuentren retailer. Diferido hasta haber probado el corpus
  con los datos de Mangavariant cargados.

---

Last updated: 2026-05-22 (noche, variant signal + preservación de campos
curados) — Dos cambios encadenados:

1. **Signal `"variant"` solo (sin "cover")** agregado a `KEYWORD_RULES`
   con score 30 / type `variant_cover`. En retail manga IT/FR/EN/ES la
   palabra "Variant" suelta casi siempre denota una variant cover
   (ej. "One Piece 108 Variant Metal alla prima tiratura", "Demon Slayer
   23 Variant Limited Francese", "Hunter X Hunter 37 Variant"). Sin esta
   regla, 13/43 productos de la colección variants-europeas de Manga
   Dreams quedaban fuera del gate `is_collectible_edition`. Word-boundary
   evita "covariant", "invariant" y "variante" (italiano/español, vocal
   final extra). 3 tests nuevos cubren detección + integración con el
   gate + non-matches.

2. **`append_jsonl` ahora preserva campos curados** cuando re-scrapeás
   un item ya estandarizado (gotcha #23 nueva). Antes, un
   `--include-seen` sobre una fuente ya ingerida sobrescribía
   `standardized_at`, `title` canónico, `series_key`/`edition_key`,
   `volume`, `title_original` con los valores rough del scraper. Ahora
   el upsert merge-ea: campos LLM-verified se mantienen; price, image,
   isbn, author, stock_type, signal_types, score, detected_at refrescan.
   Lista en `_CURATED_FIELDS`. 2 tests nuevos.

Corpus: 4426 → 4436 items (+10 netos = 13 nuevos por signal variant - 3
deduplicados contra Star Comics existentes). Mangadreams.it: 78 → 91
items. Distinct edition_keys 2914 → 2918. Tests 272 → 277.

Last updated previo: 2026-05-22 (noche, mangadreams variants europeas) —
Nueva fuente `IT - Manga Dreams (variants europeas)` apuntando a
`mangadreams.it/collections/edizioni-europee-manga-variant-limited`
(sub-colección Shopify dedicada a variants/limited europeas: Momie,
Alfa BD, Comptoir du Rêve, Canal BD, Fnac, ediciones tedescas y
españolas). 43 productos detectados en 3 páginas, 29 pasaron
`is_collectible_edition`, 23 ingresaron netos a items.jsonl, 6 se
consolidaron contra Kurokawa/Pika Collector existentes (Spy×Family
Collector 8, AoT Collector 34, etc.) vía dedup por
(series_key, edition_key, volume). Skill `/standardize-catalog`
corrió inline (<30 items, no requiere subagentes) asignando keys
canónicos por mercado (kurokawa/kazé/pika/ki-oon/glénat para FR,
star para IT, carlsen para DE, norma para ES). Corpus: 4409 → 4426
(+17 netos). Sources YAML 136 → 137; enabled 120 → 121.
14 productos quedaron fuera por falsos negativos en
`is_collectible_edition` (ej. "One Piece 108 Variant Metal alla prima
tiratura" debería pasar — variant cover + first-print) — separate
follow-up para tunear el detector si el owner quiere.

Last updated previo: 2026-05-22 — pasada documental panorámica + refuerzo de
política (ver sección al inicio de este archivo). Documentación
sincronizada con todo el trabajo de Sprint 4.z + 5.a:
- **Reforzada la política de docs** con checklist pre-flight obligatorio
  y lista de anti-patterns. Si la política se viola, fixarlo es una
  prioridad inmediata.
- **`docs/ARCHITECTURE.md`** ampliado con:
  - Schema completo de `items.jsonl` (campos nuevos series_key,
    edition_key, volume, standardized_at, title_original).
  - Schemas de `unmapped_series.jsonl`, `non_manga_blacklist.jsonl`,
    `series_aliases.yml`.
  - Sección nueva "Two-pass standardization" (gotcha #21).
  - Sección nueva "Curation skills" al final, describiendo
    `/standardize-catalog` y `/enrich-series-aliases`.
- **`docs/SOURCES.md`** ampliado con:
  - Whakoom URL types (`/comics/` vs `/ediciones/` vs `/publisher/`).
  - Whakoom Brotli/CF detection gotchas.
  - Shopify variants multi-tomo (Dark Horse pattern).
  - "Source de referencia" pattern (Mangavariant) con sus reglas
    (Mangavariant SIEMPRE manga, no filtrar por falta de price/isbn).
- **`scripts/retrofit/README.md`** reescrito con:
  - Cuadro completo de retrofits (incluye `filter_collectible`,
    `expand_whakoom_ediciones`, `expand_index_pages`).
  - Sección "Retrofits vs Skills" para decidir qué herramienta usar.
- **`.claude/skills/README.md`** nuevo: índice de los 2 skills
  project-level + recipe para agregar skills nuevos.

Sin cambios de código en esta pasada — solo docs. Tests 272/272 verde.

Last updated previo: 2026-05-24 — preservación de título original (`title_original`):
- Nuevo campo `title_original` en cada item. Pipeline (`candidate_to_json`)
  lo escribe siempre con el title scrapeado (cleaned-but-not-standardized).
- Skill `/standardize-catalog` actualizado: cuando sobrescribe `title`
  con el standardized form, hace backup a `title_original` si no estaba.
- Frontend: modal muestra `title` prominente + `title_original` en gris
  con prefijo `原題:` solo cuando difiere. Search ahora indexa AMBOS +
  `series_display` → tipear JP/ES/EN/FR/IT encuentra el mismo item.
- Dedup pipeline-level sigue siendo por `(series_key, edition_key, volume)`,
  no por texto. Decisión consciente: keys canónicas más robustas.
- Backfill aplicado: 4409 items históricos con `title_original = title`
  (perdimos el original; nuevos scrapes lo preservan correcto).
- Tests: 272 passing (+1 del title_original).
- Ver gotcha #22.

Last updated previo: 2026-05-23 (noche) — heurístico del scraper (doble pasada):
- Nueva función `derive_series_metadata(candidate)` en manga_watch.py
  que asigna series_key/edition_key/volume desde regex sobre title +
  publisher + signal_types. Llamada automáticamente desde
  `candidate_to_json` para items que no traen esos campos.
- Tabla `_PUBLISHER_SLUG_MAP` con ~35 publishers conocidos
  (Dark Horse, Glénat, Panini, Norma, Planeta, Kodansha, Shueisha,
  Kadokawa, Star Comics, etc.) → slug canónico.
- Guards defensivos: heurístico devuelve EMPTY cuando el resultado es
  obvio garbage (series_key < 3 chars, todo dígitos, termina con -N
  sin volumen). El skill /standardize-catalog procesa esos casos.
- El heurístico tampoco setea `standardized_at` — solo el skill lo
  hace. Items del scraper aparecen sin el flag, listos para verificación
  con LLM.
- Tests: 271 passing (+4 del heurístico).
- Ver gotcha #21 actualizada con el flujo doble pasada.

Last updated previo: 2026-05-23 (tarde) — skill incremental de estandarización:
- Nuevo campo `standardized_at` (ISO timestamp UTC) en cada item.
  Backfill seteó 4409 items existentes con timestamp = "2026-05-22"
  (la fecha en que pasaron por la primera estandarización masiva).
- Nuevo skill `.claude/skills/standardize-catalog.md`. Procesa SOLO
  items SIN `standardized_at` (los recién scrapeados). Delega a
  subagentes paralelos en chunks de 150, asigna series_key/edition_key/
  title estandarizado, mueve non-manga a blacklist, deduplica, aplica
  canonical_series_key, marca con `standardized_at`. Incremental por
  diseño — no cuesta re-procesar items ya curados.
- Doble skill complementario: `/standardize-catalog` corre primero
  (schema fields), `/enrich-series-aliases` corre después (consolida
  nombres multilingües). Workflow normal post-scrape: ambos en
  secuencia.
- `--force-all` snippet (en el skill) limpia los timestamps cuando se
  quiere re-procesar todo el corpus (ej. al cambiar reglas).
- Ver gotcha #21.

Last updated previo: 2026-05-23 — queue de unmapped series + skill de enrichment:
- Pipeline hook: `candidate_to_json` ahora llama
  `log_unmapped_series()` para appendear a `data/unmapped_series.jsonl`
  cada vez que un item llega con un `series_key` que NO está en
  `series_aliases.yml`. Dedupea por key dentro del mismo run.
- Audit: `scripts/audit/unmapped_series.py` agrupa el log + scan de
  items.jsonl, con fuzzy-match (difflib) contra canonicals existentes
  para sugerir merges obvios (ej. `umamusume-cinderella-gray` 🟢 0.98
  contra `uma-musume-cinderella-gray`).
- Skill: `.claude/skills/enrich-series-aliases.md`. Invocación manual
  cuando el usuario quiera curar el backlog. Orquesta audit → decide
  alias-de-X / new-canonical / skip por candidate → consulta Anilist
  cuando hace falta → edita YAML → corre backfill → reporta.
- Futuro: el skill puede engancharse a un cron via `/schedule`.
- Tests: 267 passing (+2 del logger).

Last updated previo: 2026-05-22 (tarde, multilingual series alias resolver):
- Nueva fuente de verdad `data/series_aliases.yml` con 106 series canónicas
  + traducciones JP/EN/ES/FR/IT/PT-BR. Inicial generado via Anilist API
  (`graphql.anilist.co` — `title.english/romaji/native + synonyms[]`) +
  overrides manuales (Saint Seiya, Detective Conan, Tensura, Blue Period
  y otros casos donde Anilist tira false matches).
- Nuevo `scripts/series_aliases.py::canonical_series_key()` con matching
  ESTRICTO (solo exact-match en `series_key` y `series_display`
  normalizados, NO substring en title — evita false positives tipo
  "Monster Musume → Monster (Urasawa)").
- Hook en `candidate_to_json` (manga_watch.py): items futuros del
  scraper se normalizan automáticamente.
- Backfill aplicado: 220 items remapped (Demon Slayer absorbiendo
  "kimetsu-no-yaiba" + JP nativo + "Guardianes de la Noche"; Attack on
  Titan absorbiendo "L'Attaque des Titans" + "L'Attacco dei Giganti" +
  "Ataque a los Titanes"; Apothecary Diaries absorbiendo "Les Carnets de
  l'Apothicaire"; Witch Hat Atelier absorbiendo "Atelier of Witch Hat" +
  "L'Atelier des Sorciers"; etc.).
- Corpus: 4420 → 4409 (Δ -11 dedups tras consolidación). series_keys
  distintos: 1456 → 1431. Ver gotcha #20.
- Tests: 265/265 passing (+4 tests del resolver).

Last updated previo: 2026-05-22 (mediodía, standardization de nombres + agrupación
por obra+edición — manual via subagentes, sin retrofit script):
- Schema nuevo agregado a items.jsonl: `series_key` (id canónico de la obra,
  ej. "berserk", "one-piece"), `series_display`, `edition_key` (id de
  edición+publisher, ej. "berserk-darkhorse-deluxe"), `edition_display`,
  `volume`. Permite filtrar por obra y por edición en el dashboard.
- Títulos estandarizados al formato `{Series} {Edition Suffix} {Volume}`
  ej. "Berserk Deluxe 1", "One Piece Celebration 100".
- 5192 items procesados en 26 chunks de ~200 via subagentes paralelos.
  Reconciliación posterior: 86 series_keys remapeados a versión canónica
  (ej. "hells-paradise" prevaleciendo sobre "hell-s-paradise"/"hells-paradise-jigokuraku";
  "boruto" sobre "boruto-naruto-next-generations"; "demon-slayer" sobre
  "kimetsu-no-yaiba"; etc.). 370 items remapped.
- 94 items movidos a nuevo `data/non_manga_blacklist.jsonl`: cómics
  occidentales (Marvel/DC/IDW/Image), light novels, posters, figuras,
  DVDs/Blu-rays, videojuegos. Mangavariant SIEMPRE marcado is_manga=true
  (regla del usuario: "todo lo que venga de mangavariant tomalo como
  válido siempre").
- Dedup por (series_key, edition_key, volume): 678 duplicados eliminados.
  Conserva el más completo (priorizando ISBN > image > price > author).
- 37 items Rakuten con título "Unknown X" reparados via descripción JP
  (un mini-subagente extrajo serie/edición/volumen del título japonés).
- Corpus final: **5192 → 4420 items** (Δ -772 = -94 non-manga -678 dups).
  1456 series_keys distintos, 2915 edition_keys distintos.
  Coverage: 100% series_key, 100% edition_key, 100% image, 78.9% volume.
- Próximo paso natural: agregar UI de filtro por obra/edición en el
  dashboard usando series_key/edition_key como agrupadores.

Last updated previo: 2026-05-22 (madrugada, manual review):
- 9 índices residuales eliminados (Dark Horse Direct Volumes/Hardcovers que
  re-aparecieron tras el scrape + Mangavariant "Loveless — Vol.1~12 - Limited
  editions" que era un rango de tomos).
- 182 clones Rakuten l-id deduplicados + fix preventivo en TRACKING_PARAMS
  (`l-id`, `l_id`). Ver gotcha #19.
- 589 títulos Manga-Sanctuary enriquecidos: títulos pelados como "Demon slayer
  1" ahora muestran su qualifier ("Demon slayer 1 (Coffret Collector 2025)").
  Resolvió 184 de 229 grupos duplicados; los 41 restantes son ediciones
  legítimas con ISBN distinto (reimpresiones Panini, etc.) en distintos
  formatos.
- 7 items sin imagen completados a mano vía web (3 ListadoManga + 4 Fnac).
  4 ISBNs nuevos extraídos: 9788411616218 (Cofre 5º Aniversario Planeta
  Manga Ana C. Sánchez), 9788498474503 (Rg Veda 2 Ed. Coleccionista),
  9788467928150 (Fruits Basket 1 Ed. Coleccionista), 9788467929287 (Fruits
  Basket 3 Ed. Coleccionista). Image coverage 99.9% → 100.0%.
- 4 títulos Fnac limpiados del "-5% en libros" / "- Fnac" trailing junk.
- Corpus: 5383 → 5192 (Δ -191).

Last updated previo: 2026-05-22 (noche, post-omnibus-cleanup) — Decisión del owner:
omnibus / "X en X" / "X-in-X" NO califican como coleccionables solos. Solo
se aceptan si vienen con qualifier premium (hardcover, deluxe, limited,
variant_cover, box_set, bundle, extras). Cambios:
- `omnibus` removido de `COLLECTIBLE_EDITION_SIGNAL_TYPES` (manga_watch.py).
- `"Omnibus"` agregado a la exclusión de `_GENERIC_X_EDITION_PATTERN` (evita
  que "Omnibus Edition" dispare `lore_edition` falsamente).
- 91 items omnibus-only limpiados retroactivamente de items.jsonl
  (5474 → 5383). NO se aplicó filter_collectible completo (habría
  removido ~739 items Mangavariant válidos por otra razón — issue
  separado en radar).
- Tests: 261 passing (+8). Ver gotcha #18.

Last updated previo: 2026-05-22 (noche, post-mangavariant) — Sprint 4.y.1:
cluster_key tier-based. Cuando se ingestó Mangavariant, el caso "One
Piece Vol.98 Celebration Edition" aparecía dos veces (Star Comics +
Mangavariant) porque sus signal_types divergían y `variant_sig` (set
completo) era demasiado discriminante. Reemplazado por
`_variant_tier()` que elige el tier **más específico** del item
(`artbook > omnibus > box_set > kanzenban > lore_edition >
variant_cover > deluxe > limited > special > ""`). Bug colateral:
`_normalize_series_name` dejaba un `.` residual en títulos tipo
"One Piece — Vol.98 - ..." → fix con trim de edges. Tests: +5
(variant_tier hierarchy, OP98 cross-source merge, tolerance a extra
low-priority signals, deluxe≠lore, series trim). Retrofit aplicado a
5474 items.jsonl: 2398 keys refrescadas, 137 cards consolidadas (5474
→ 5337 cards en dashboard). 258/258 verde. Documentado en design
decision #4 ("variant tier").

Last updated previo: 2026-05-22 (noche) — Sprint 4.z: limpieza de páginas-índice.
Auditoría descubrió 13 items que eran índices/catálogos guardados como
productos: 1 Whakoom `/publisher/`, 7 Shopify variants multi-tomo en
Dark Horse Direct, 3 blog/news posts, 1 colección funside.it. Nuevos
módulos: `scripts/shopify_variants.py` (parser genérico de variants
con detección heurística por keyword de volumen) y
`scripts/wikis/whakoom.py::expand_whakoom_publisher_url`. Nuevo retrofit
`scripts/retrofit/expand_index_pages.py` que maneja los 4 casos
(eliminar / expandir). Nueva fuente `IT - Funside Variant` en sources.yml
(reemplaza el item-índice eliminado). `search_discovery.py` ahora
intercepta `/publisher/` (expand) + `/blogs/news/` + `/collections/X`
(blacklist). +32 filas netas en items.jsonl (45 tomos nuevos − 13
índices eliminados). Ver gotchas #14 (extendida), #16 (Shopify variants),
#17 (url_is_useful blacklist).

Last updated previo: 2026-05-22 (tarde) — Sprint 4.y: integración Mangavariant.
Nueva fuente global `Global - Mangavariant` (sources.yml, incremental con
max_pages=1) + wiki parser `scripts/wikis/mangavariant.py` (sitemap-driven
bulk importer, ~2700 entries de 13 países). Cubre el caso central del
proyecto: descubrir variants/ediciones especiales con serie + año +
publisher + país + cover, aunque sin precio ni URL de tienda. **Nueva
sección "URL como referencia (no de tienda)"** en CLAUDE.md que
formaliza el principio: las URLs no-shop son válidas, el enrichment de
precios es una pasada aparte (próximo sprint). 8 tests nuevos, 246/246
verde. Países nuevos que ahora aparecen en items.jsonl: Alemania,
Taiwán, Tailandia, Reino Unido, Vietnam.

Last updated previo: 2026-05-22 — Sprint 4.x: Whakoom `/ediciones/` expansion.
Items con URL `/ediciones/<id>/<slug>` se expanden a N filas `/comics/...`
(una por tomo) en los tres puntos de ingesta (spider, search discovery,
retrofit). One-shots se resuelven vía `/login?ReturnUrl=/comics/...`.
Bug fixes laterales: Whakoom session ya no anuncia Brotli (no soportado
por `requests` sin lib extra → respuestas eran bytes binarios silenciosos)
y se tightenearon los markers de CF challenge (`challenge-platform`
matcheaba el script JSD legítimo, generando falsos positivos). +40 filas
en items.jsonl tras el retrofit (17 `/ediciones/` reemplazadas por 57
tomos `/comics/`, descontando 14 duplicados cross-subdominio
en./www.whakoom.com). Ver gotchas #14 y #15.

Last updated previo: 2026-05-21 — sweep update after Sprints 1 / 2.4 / 2.5
/ 2.6 / 3.8: collectible/novel/comics filters, multi-engine search,
overnight pipeline + source-health audit, Wayback recovery, scrape
parallelization, cluster_key grouping. **+ Panel de Control web local
(admin/, scripts/admin_serve.py, scripts/script_registry.py,
scripts/run_local.sh) — server admin separado del público, bind a
127.0.0.1, no deployable. Ver `docs/CONTROL-PANEL.md`.** **+ Expansión
de fuentes a Brasil (Panini BR Planet Manga, Editora JBC, NewPOP,
Pipoca & Nanquim, Devir + Panini BR search) y nuevas fuentes con
variantes/alternativas en MX (MangaLine México) y ES (ECC Manga
[deshabilitado: Cloudflare], MangaLine España). +1 país (Brasil),
+6º idioma (PT-BR), +11 fuentes (120→131, 106→115 habilitadas — ECC
y NewPOP Catálogo quedaron disabled). Tres nuevas mixed: ECC,
Pipoca & Nanquim, Devir.** If you find this file stale relative to
the code, update it (per the Documentation policy at the top of this
file).
