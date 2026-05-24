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

## 2 scripts canónicos: full vs delta

Hay dos scripts top-level que encadenan todo el pipeline. Operan sobre las
mismas fuentes pero con distinto método de descubrimiento para listadomanga.es
(la fuente más estructural). **El resto de fuentes se comportan igual** entre
los dos por ahora — la única diferencia importante es cómo se descubre
listadomanga (decisión 2026-05-23):

| Script | Listadomanga discovery | Frecuencia | Tiempo | Cuándo |
|---|---|---|---|---|
| `scripts/scrape_delta.sh` | `calendario.php` mes actual + 2 anteriores | diaria / semanal | ~30-60 min | detectar novedades recientes |
| `scripts/scrape_full.sh` | `lista.php` → ~3432 colecciones activas en orden alfabético | mensual / trimestral | ~2-4 horas | refresh completo del catálogo |

Ambos corren las mismas fases:
1. Scrape sources del YAML (`manga_watch.py` con `--workers 8`)
2. Wiki bootstraps (los wikis que aplican según modo)
3. Search discovery (Gemini + DDG)
4. Cleanup retrofits (rescore → filter_non_manga → filter_collectible →
   clean_titles → backfill_metadata)
5. Build web

`scripts/overnight_run.sh` queda como alias deprecated de `scrape_delta.sh`
(retrocompat con cron jobs antiguos).

**`scrape_full` SI hace** lo que `scrape_delta` NO hace:
- listadomanga-collections via `lista.php` (~3432 colecciones × 0.3s ≈ 17 min)
- mangavariant sitemap completo

**Modelo simplificado para listadomanga**: `full = lista.php`,
`delta = calendar`. Sin overlap. El calendar NO está en el full porque
lista.php ya cubre todas las colecciones activas (decisión 2026-05-23,
post-investigación: las "exclusivas" del calendar eran falsos negativos
del parser que se arreglaron con el fix DISCARD→REGULAR para secciones
`(Planeta DeAgostini Cómics)` / `(Planeta Cómic)`).

**`listadomanga-blog` REMOVED del pipeline canónico** (decisión 2026-05-23).
Son posts de noticias (anuncios de licencias, "Novedades de X"), no productos
físicos — `is_collectible_edition` los rechaza al 99%+. 0 items netos al
catálogo. El módulo `wikis/listadomanga_blog.py` sigue disponible para
invocación manual si en el futuro se le da otro uso (ej. input para
`search_discovery`). Mismo razonamiento aplica al RSS feed
`ES - Listado Manga Blog RSS` en `sources.yml` (ahora `enabled: false`).

**El resto de mejoras "full vs delta" por fuente quedan pendientes** —
cuando aparezca la necesidad, cada fuente puede tener su propio modo
incremental específico (ej. SocialAnime delta = solo última página del feed
en vez de paginación completa). Por ahora la simplificación a "una sola
diferencia, listadomanga" es suficiente.

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
  • mirror_candidate_images() — descarga la portada de cada item
    nuevo/cambiado a data/images/ (espejo local, campo image_local).
    On by default; --skip-image-download para saltearlo.
    │
    ▼
data/items.jsonl  ← upsert by URL (1 line per unique URL).
                    Every row carries `cluster_key` for grouping.
data/images/      ← espejo local de portadas (image_local apunta acá)
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
  images/                            — gitignored. Espejo local de
                                       portadas (Image storage Fase 1):
                                       1 archivo por imagen, nombre
                                       <sha256(image_url)[:16]>.<ext>.
                                       Lo llena el scrape; el JSONL
                                       referencia el filename en el
                                       campo `image_local`.
  unmapped_series.jsonl              — **FUENTE ÚNICA DE VERDAD para cualquier
                                       registro de items.jsonl que no estemos
                                       seguros cómo clasificar** (serie,
                                       edición, agrupación, publisher, lo que
                                       sea). Antes había también
                                       `data/uncertain_groupings.jsonl` para
                                       casos de agrupación; se unificó acá
                                       (2026-05-23, por feedback del owner:
                                       "asegurémonos que tener solamente un
                                       archivo y siempre usamos ese").
                                       NUNCA crear archivos paralelos de
                                       "uncertain_X.jsonl" / "review_X.jsonl"
                                       / etc — todo el flagging va acá.

                                       Schema (append-only, una línea por flag):
                                       - `series_key` (REQ): slug actual del item.
                                       - `series_display`: display actual.
                                       - `sample_title`, `sample_url`, `source`:
                                         contexto del item.
                                       - `detected_at`: ISO timestamp.
                                       - `flagged_by`: origen del flag —
                                         `"pipeline"` si lo logueó
                                         `log_unmapped_series()` automáticamente,
                                         o `"audit:<nombre-pasada>"` /
                                         `"human"` para casos manuales.
                                       - Opcionales (auditoría manual):
                                         `reason`, `notes`,
                                         `proposed_canonical_key`,
                                         `proposed_canonical_display`,
                                         `current_edition_key`, etc.
                                         Cualquier campo extra está OK;
                                         el lector (skill enrich-series-aliases
                                         + audit/unmapped_series.py) ignora
                                         lo que no conoce.

                                       Vaciado al final de cada corrida del
                                       skill `/enrich-series-aliases`; el
                                       pipeline lo repopula en el próximo
                                       scrape. No lo consume ningún script
                                       en runtime, sólo skills/auditorías.
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
  scrape_delta.sh                    — ⭐ CANÓNICO INCREMENTAL. Encadena
                                       todas las fases en modo delta
                                       (listadomanga via calendario.php
                                       últimos 3 meses, no recorre el
                                       catálogo entero). ~30-60 min.
                                       Frecuencia: diaria/semanal.
                                       Opt-in: INCLUDE_WHAKOOM_SPIDER,
                                       INCLUDE_WAYBACK_RECOVERY,
                                       SKIP_SCRAPE/SKIP_WIKIS/...
  scrape_full.sh                     — ⭐ CANÓNICO FULL. Recorre las
                                       ~3432 colecciones de listadomanga
                                       via lista.php + blog histórico
                                       completo + mangavariant sitemap
                                       completo. ~2-4 horas.
                                       Frecuencia: mensual/trimestral.
  overnight_run.sh                   — DEPRECATED. Alias de scrape_delta.sh
                                       por retrocompat con cron jobs.
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
    socialanime.py                   (IT — MangaStore de socialanime.it,
                                       JSON feed paginado, ~840 items.
                                       Cubre variant/limited/special editions
                                       (type=variant, 466) + cofanetti
                                       (type=box, 440). Las URLs van a
                                       Amazon Italia con afiliados, se
                                       canonicalizan al /dp/<ASIN>. ASIN
                                       de libros italianos = ISBN-10
                                       (prefijo 88…), 95% cobertura ISBN.
                                       Cubre publishers que las sources
                                       directas no agarran: Edizioni BD,
                                       001 Edizioni, Goen, Magic Press,
                                       Dynit, Coconino, Tora.)
    blogbbm.py                       (BR — Biblioteca Brasileira de Mangás,
                                       parser de 2 posts curados
                                       continuamente actualizados:
                                       /2020/10/09/capas_variantes/ y
                                       /2024/05/15/guia-volumes-especiais-
                                       de-mangas-com-itens-especiais/.
                                       Heurística title-driven que soporta
                                       dos layouts (gallery `<div>` antes
                                       del título en capas_variantes /
                                       title con `(MM/YYYY)` parens +
                                       `<figure>` después en volumes-especiais).
                                       URLs sintéticas con query param
                                       `?bbm-entry=vol-N-<stem>` para
                                       unicidad por entry — ver gotcha #27.)
    listadomanga_collections.py      (ES — parser por colección individual,
                                       coleccion.php?id=N. Complementa el
                                       calendario mensual (listadomanga.py)
                                       capturando ediciones especiales /
                                       portadas alternativas / cofres /
                                       extras de primera edición / formato
                                       premium (kanzenban A5, cartoné tapa
                                       dura, doble sobrecubierta, artbook).
                                       Iteración secuencial id=1..~6500.
                                       Fase 1 (actual): Layout A — tomos
                                       de "Números editados (Ediciones
                                       Especiales)" + "(Portadas alternativas)"
                                       + Packs con extras + Formato premium
                                       page-wide. Fase 2 (planeada): Layout B
                                       — Cofres/Regalos/Extras con
                                       vinculación extra→tomo + carrusel
                                       de imágenes (campo `images[]`).
                                       Fase 3 (planeada): iteración masiva
                                       de todos los ids del catálogo
                                       (~6500 colecciones).
                                       URLs sintéticas con query param
                                       `?item=<edition_slug>-<vol>` para
                                       unicidad por tomo — ver gotcha #27.)
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
    mirror_images.py                 — espejo local de portadas (Image
                                       storage Fase 1): backfill (descarga
                                       a data/images/ las portadas de items
                                       sin image_local) + GC mark-and-sweep
                                       (saca los archivos huérfanos a una
                                       cuarentena, o --gc-delete). Ver
                                       sección "Image storage".
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
  image_store.py                     — primitivas del espejo local de
                                       portadas (Image storage Fase 1):
                                       nombre de archivo determinístico
                                       por hash, descarga con validación
                                       por magic bytes, idempotencia. Lo
                                       orquesta mirror_candidate_images()
                                       en manga_watch.py. Ver sección
                                       "Image storage".
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
| Total unique items (line in items.jsonl) | **5532** (post primera corrida scrape_full + standardize --force-all + cleanup compound slugs, 2026-05-24) |
| Items movidos a `data/non_manga_blacklist.jsonl` (acumulado) | 285 (+191 en esta corrida — cómics occidentales Funside, light novels, novelas, news/video, art_supplies, photobooks, etc.) |
| Items deduplicados por (series_key, edition_key, volume) en esta corrida | 918 (915 en el merge + 3 al cleanup compound slugs) |
| Distinct `series_key` (filtro por obra) | 1564 |
| Distinct `edition_key` (filtro por edición+editorial) | 3062 |
| `data/series_aliases.yml` entries | 261 canonical works (Anilist + manual + auditoría 2026-05-23) |
| Sources in YAML | 138 |
| Sources enabled | 121 / 138 (Listado Manga Blog RSS deshabilitado 2026-05-23) |
| Sources flagged `purity: mixed` | 17 |
| Bluesky sources (`kind: bluesky`) | 15 |
| Wikis disponibles (`--bootstrap-wiki`) | 10 (listadomanga, listadomanga-blog, manga-sanctuary, otaku-calendar, manga-mexico, mangavariant, whakoom opt-in, socialanime, blogbbm, **listadomanga-collections** *Fase 1+2+3 completas*) |
| Top sources | Mangavariant 1744, ListadoManga colecciones 1002, Manga-Sanctuary 947, SocialAnime Cofanetti 333, ListadoManga calendario 237, SocialAnime Variant 190, KADOKAWA Store 86, Sanyodo 84, Panini IT EdC 83, Manga Dreams 74 |
| Image coverage | 99.7% (5517/5532) |
| `image_local` coverage | 96.7% (5352/5532) |
| `series_key` / `edition_key` / `standardized_at` coverage | 100% (5532/5532 — force-all reprocesó todo el corpus) |
| `volume` coverage | 83.2% (4602/5532) |
| Release date coverage | 86.6% (4792/5532) |
| ISBN coverage | 35.7% (1976/5532) |
| Price coverage | 59.3% (3282/5532) |
| Author coverage | 51.8% (2865/5532) |
| `cluster_key` populated | 100% (precomputed + backfilled post-cleanup) |
| Items con `images[]` populated | 5384 (~97%) |
| Items con carrusel real (`images.length > 1`) | 132 |
| Items con al menos 1 image `kind=extra` | 133 |
| Items con `extras[]` descriptivo | 133 |
| Countries represented | 15 (Japón, Francia, Italia, España, EUA, Vietnam, México, Alemania, Tailandia, Brasil, Argentina, España/LatAm, Taiwán, Reino Unido + Global) |

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

### When you flag a record as "uncertain" / "needs review"

**Append it a `data/unmapped_series.jsonl` — siempre.** Ese archivo es la
única fuente de verdad para cualquier registro de la base que no estés
seguro cómo clasificar (a nivel de serie, edición, publisher,
agrupación, lo que sea).

**NUNCA crear archivos paralelos** tipo `uncertain_groupings.jsonl`,
`review_X.jsonl`, `audit_X.jsonl`, etc. Esto fue un problema real (el
owner pidió consolidación el 2026-05-23 porque algunas auditorías
escribían en `uncertain_groupings.jsonl` y otras en `unmapped_series.jsonl`).
Si necesitás agregar contexto al flag (motivo, propuesta, audit-id),
usá los campos opcionales del schema (`flagged_by`, `reason`, `notes`,
`proposed_canonical_*`, `current_edition_key`, etc.) — ver schema completo
en el file map arriba.

Ejemplo mínimo para flagging desde una auditoría manual:

```python
import json, datetime as dt
with open('data/unmapped_series.jsonl', 'a') as f:
    f.write(json.dumps({
        'series_key': item['series_key'],
        'series_display': item.get('series_display', ''),
        'sample_title': item.get('title', ''),
        'sample_url': item.get('url', ''),
        'source': item.get('source', ''),
        'detected_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'flagged_by': 'audit:my-audit-name',
        'reason': '...',
        'notes': '...',
    }, ensure_ascii=False) + '\n')
```

Para flags automáticos desde el pipeline, ya existe `log_unmapped_series()`
en `scripts/series_aliases.py` — usalo en vez de escribir el archivo a mano.

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

## Image storage — espejo local de portadas (Fase 1 + Fase 2)

**Problema.** Hasta la Fase 1, `items.jsonl` guardaba sólo `image_url`
apuntando al sitio fuente (retailer/wiki) y el dashboard hotlinkeaba
esa imagen. Para desplegar PandaWatch como servicio multi-usuario hay
que **ser dueños de los bytes**: si la fuente muere, cambia sus URLs o
agrega protección anti-hotlink, las cards se rompen para todos los
usuarios.

La estrategia separa dos cosas: **ser dueño de los bytes** (una copia
propia de cada portada) y **dónde se sirven** (carpeta local vs
Cloudflare R2). La Fase 1 resuelve lo primero; la Fase 2 mueve el
serving a R2 al desplegar.

### Fase 1 — espejo local `data/images/` (IMPLEMENTADA)

- El scrape descarga la portada de cada item nuevo/cambiado a
  `data/images/<sha256(image_url)[:16]>.<ext>` y guarda el **filename**
  (no la URL completa) en el campo `image_local`.
- `image_url` queda intacto como **provenance + fallback**: si el
  espejo local no existe o falla al cargar, el dashboard cae al
  `image_url` remoto, y si ese también falla muestra el placeholder 📚.
- Pasa por defecto en TODO scrape (source loop, wiki bootstrap, sitemap
  mining). Se desactiva con `--skip-image-download`.
- Módulo `scripts/image_store.py` — primitivas puras de descarga.
  `mirror_candidate_images()` en `manga_watch.py` orquesta el filtro
  (sólo new/changed con `image_url`) + descarga paralela (`--workers`).
- **Idempotente**: el nombre es determinístico, así que re-scrapear la
  misma imagen reusa el archivo en disco (glob `<stem>.*`, sin red).
- **Validación por magic bytes**: si el body descargado no empieza con
  una firma de imagen conocida (típico: una página HTML de error /
  anti-bot servida en vez de la imagen), se descarta y `image_local`
  queda vacío. La extensión sale de los magic bytes, no de la URL.
- **`image_local` es sticky** en `append_jsonl` — ver gotcha #25.
- `data/images/` está gitignored (entrada propia en `.gitignore` —
  ojo: `data/` NO está ignorado en bloque, sólo archivos puntuales).
- **Esquema deploy-agnóstico**: como el JSONL guarda sólo el filename,
  la misma fila sirve local o desde R2 — sólo cambia la base de la URL
  (`../data/images/` en el dashboard hoy; un dominio R2 en Fase 2).

**Backfill + GC del corpus existente** — retrofit
`scripts/retrofit/mirror_images.py`:
- **Backfill**: recorre `items.jsonl`, descarga la portada de cada item
  con `image_url` y sin `image_local`, setea el campo. Idempotente.
  El scrape ya hace esto para items nuevos; el retrofit cubre el corpus
  histórico (los items previos a la Fase 1).
- **GC mark-and-sweep**: saca de `data/images/` los archivos que ningún
  item referencia (orphans, de items quitados del corpus). Por defecto
  los manda a una cuarentena `data/images/_orphans/` (reversible);
  `--gc-delete` los borra. La carpeta nunca acumula basura. La misma
  lógica servirá para el bucket R2 en la Fase 2.
- Flags: `--dry-run`, `--no-gc`, `--gc-only`, `--gc-delete`,
  `--workers`, `--limit`. Disponible también en el Panel de Control.

### Fase 2 — subir el espejo a Cloudflare R2 (PLANEADA, no implementada)

Al desplegar PandaWatch, el espejo local se sincroniza a object storage
S3-compatible (Cloudflare R2). El proyecto hermano **PandaTrack**
(`/Users/Shared/Proyectos/pandatrack`) ya usa R2 vía `@aws-sdk/client-s3`
(ver `src/lib/user/avatarStorage.ts`, `src/lib/store/logoStorage.ts`)
con las env vars `ASSETS_STORAGE_BUCKET/ENDPOINT/REGION/ACCESS_KEY_ID/
SECRET_ACCESS_KEY` + `ASSETS_PUBLIC_BASE_URL`. PandaWatch reutilizará
el patrón (en Python sería `boto3`, también S3-compatible).

**Decisión: bucket R2 propio, NO un prefijo dentro del bucket de
PandaTrack.** Misma cuenta de Cloudflare, bucket separado. Razones:
- **Blast radius**: credenciales separadas — una key de PandaWatch
  filtrada no toca los avatares de usuarios de PandaTrack.
- **GC seguro**: el mark-and-sweep ("borrá lo no referenciado") es
  peligroso en un bucket compartido — un filtro de prefijo mal hecho
  podría borrar assets de PandaTrack.
- Crear buckets en R2 es gratis (se paga storage + operaciones, no
  por bucket).
- Cuando los dos proyectos se fusionen (estimado ~1 año), mantener dos
  buckets o unirlos es trivial; des-unir un bucket compartido no.

Serving en Fase 2: dominio propio (como el `ASSETS_PUBLIC_BASE_URL` de
PandaTrack), **no** el URL `r2.dev` (está rate-limited, es sólo para
dev). La sync es `data/images/ → R2`; el GC borra orphans también en R2.

## The 27 known gotchas

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
   `placeholder_*`, data:image lazy-load placeholders, theme/UI assets
   under `/assets/images/common/` and any `.svg` — un SVG nunca es
   portada, es ícono de UI; ej. Sanyodo servía `icn_close.svg` como
   `image_url` —, URLs ending in `/` with no filename). The extractor
   returns `""` if all candidates are placeholders, which lets backfill
   re-fetch later.

   **Lazy-loaded `<img>`: el `src` es un placeholder, la portada real
   vive en `data-src`/`data-lazy-src`.** `_img_to_url` prueba los
   atributos en orden (`src` primero) y **saltea valores `data:` URI**
   — sin ese skip devolvía el data-URI placeholder (típico:
   `data:image/svg+xml;base64,…` en MangaLine MX) en vez de caer al
   `data-src` con la URL real. Un `data:` URI no es descargable y rompe
   el espejo local. Si agregás un atributo lazy nuevo, mantené el skip.

   **`IMAGE_URL_GOOD_PATTERNS` puede llevar hosts, no sólo paths.**
   `e-hon.ne.jp` está en la lista: es el CDN de portadas que linkea
   Sanyodo (`/content/images/m_*.jpg` y `/images/syoseki/*.jpg`). Sin
   ese boost, una portada e-hon con `alt` corto quedaba en score 4 —
   bajo el umbral 5 del ranking fallback — y no se extraía.

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

24. **`_GENERIC_X_EDITION_PATTERN` debe excluir genéricos en ES/IT/FR, no
    solo en inglés.**

    El regex `_GENERIC_X_EDITION_PATTERN` matchea `<Word> Edition` para
    capturar ediciones lore-específicas ("Tarot Edition", "Gold Edition",
    "Beherit Edition"). Cuando dispara, `score_candidate` agrega el signal
    `lore_edition` — que ESTÁ en `COLLECTIBLE_EDITION_SIGNAL_TYPES`, así que
    rescata el item por `is_collectible_edition`.

    El patrón también matchea `Edición / Edizione / Édition` (ES/IT/FR), pero
    su lista de exclusión de palabras genéricas (First, New, Print, Standard,
    Regular, Original…) era **solo inglesa**. Resultado: **"Nueva Edición"**
    (= "New Edition", una simple reimpresión) disparaba `lore_edition` y
    colaba tomos/omnibus normales por el gate. Caso real (2026-05-22): los
    omnibus Planeta "One Piece (Nueva Edición 3 en 1)", "Naruto (Nueva
    Edición 3 en 1)", etc. + ~21 reimpresiones "Nueva Edición" sueltas
    (Nausicaä, Yu-Gi-Oh!, Detective Conan…). En paralelo, los One Piece
    "Omnibus Edition" de VIZ arrastraban un `lore_edition` viejo de cuando
    "Omnibus" todavía no estaba excluido (gotcha #18).

    Fix: la lista de exclusión ahora incluye los equivalentes ES/IT/FR de
    las mismas categorías (new / ordinales / standard / regular / original /
    digital / idioma): `Nueva|Nuova|Nouvelle|Primera|Prima|Première|...`.
    Si agregás un idioma nuevo con su propia palabra "Edition", revisá que
    sus genéricos también estén excluidos. 33 items omnibus/reimpresión
    limpiados retroactivamente. Tests:
    `test_is_collectible_edition_x_edition_stoplist_multilingual` +
    `test_nueva_edicion_omnibus_does_not_slip_through`.

    **Nota de mantenimiento**: `signal_types` (incluido `lore_edition`) se
    deriva de `title_original` + `description`, NO del `title`
    estandarizado. Como `title_original` se preserva intacto (gotcha #22),
    `signal_types` NO se vuelve caduco cuando el skill `/standardize-catalog`
    reescribe el `title` — es una propiedad del texto scrapeado, que es
    estable. La única forma de que `signal_types` quede desactualizado es
    que cambie el *código* de detectores (p.ej. esta corrección del patrón)
    — y para eso está `rescore.py`, que el pipeline nocturno corre en su
    fase de cleanup. No hay que refrescar `signal_types` en cada curación.

25. **`image_local` es sticky en `append_jsonl` — un re-scrape sin
    descarga no borra el espejo.**

    `image_local` (espejo local de portadas, Image storage Fase 1) NO
    está en `_CURATED_FIELDS` — es un campo scrapeado, se refresca con
    cada upsert. Pero un re-scrape corrido con `--skip-image-download`,
    o con un fallo de red puntual al descargar la portada, produce una
    row nueva con `image_local` vacío. Sin protección, el upsert
    borraría el puntero al espejo que ya teníamos en disco.

    Por eso `append_jsonl` trata `image_local` como **sticky**: si la
    row nueva no trae `image_local` pero la fila existente sí, conserva
    el de la existente. Aplica a TODO upsert (no sólo a items
    standardized, a diferencia de `_CURATED_FIELDS`). El archivo en
    `data/images/` sigue en disco; lo único que se perdería sin esto es
    la referencia desde el JSONL. Ver sección "Image storage".

    Tests: `test_append_jsonl_image_local_is_sticky`.

26. **Amazon affiliate URL canonicalization** (extiende gotcha #19).

    Las URLs Amazon que llegan vía afiliados (SocialAnime, futuras fuentes)
    pueden traer hasta dos capas de tracking:
    - **Query params**: `tag` (affiliate id), `linkCode` (tipo de enlace),
      `th` (variant select), `psc` (product context), `ascsubtag`/`smid`
      (sub-affiliate / seller), `pf_rd_*`/`pd_rd_*` (surface tracking),
      `content-id`. Todos en `TRACKING_PARAMS` — `parse_qsl` los strippea.
    - **Path token `/ref=...`**: Amazon le pega un segmento opaco al path
      (`/dp/<ASIN>/ref=cm_sw_r_apa_glt_fabc_xyz`) que cambia por sesión /
      widget. Como NO es query, no lo agarra `parse_qsl`. `normalize_url_for_dedup`
      lo strippea sólo cuando el host es `amazon.<tld>` (no aplica a otros
      retailers porque `/ref=` es semánticamente Amazon).

    Sin esto, dos URLs del mismo ASIN con afiliados distintos (p.ej. SocialAnime
    `?tag=socianim0c-21` vs un share manual con `?tag=otro&ref_=...`)
    generaban rows duplicadas. Caso real: si en el futuro la misma SKU
    aparece desde dos affiliates, el upsert por URL ya las colapsa.

    Tests: `test_normalize_url_strips_amazon_affiliate_params`.

27. **`normalize_url_for_dedup` strippea fragments — usar query param para
    URLs sintéticas por-entry.**

    Para fuentes wiki que enumeran muchos entries desde UNA misma URL base
    (BBM `/manga/<slug>/` ficha cubre múltiples volúmenes + variants),
    necesitamos URLs únicas por entry para que el upsert por URL (gotcha
    de upsert + `candidate_key`) no los colapse en una sola fila.

    El primer intento fue usar fragment: `<ficha>#vol-N-<image-stem>`.
    No funcionó: `normalize_url_for_dedup` siempre devuelve fragment vacío
    (línea final `urlunparse((..., new_query, ""))`), así que 35 entries
    BBM colapsaban a ~21 ficha URLs distintas. El parser perdía data
    silenciosamente porque process_state hacía el dedup por la URL
    normalizada, no por la `candidate.url` original.

    Fix: usar **query param** `?bbm-entry=vol-N-<image-stem>`. El param
    NO está en `TRACKING_PARAMS` → sobrevive la normalización. BBM ignora
    el query desconocido y muestra la ficha al clickear. Cualquier
    futuro parser que necesite URLs sintéticas por entry sobre una base
    común debe seguir el mismo patrón: query param custom, NO fragment.

    Tests: `test_blogbbm_parses_layout_a_capas_variantes` verifica que
    35 candidates → 35 distinct `candidate_key`.

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
- **Image storage Fase 2 — subir el espejo a Cloudflare R2.** La
  Fase 1 está completa (espejo local en el scrape + retrofit
  `mirror_images.py` para backfill y GC). Falta sólo la Fase 2: al
  desplegar, sincronizar `data/images/` a un bucket Cloudflare R2
  propio. Ver la sección "Image storage" más arriba para la decisión
  de diseño (bucket separado del de PandaTrack).
- **listadomanga.es per-collection parser — TERMINADO** (Fases 1+2+3
  completas en 2026-05-23, ver `scripts/wikis/listadomanga_collections.py`
  y entradas "Last updated" arriba). Quedan abiertos sólo:
  - 2 edge cases de h2 desconocido sin cubrir (`Tomos de Manga Hentai
    incluidos en la revista Hentype`, `Portadas de Roboco y Yo`) —
    descartables, no aportan items relevantes.
  - Re-corrida periódica (mensual o trimestral) cuando el catálogo
    crezca; el `UNKNOWN_H2_LOG` reportará nuevos patrones automáticamente
    si aparecen.

  Detalle histórico del plan (preservado por referencia):
  Plan acordado con el owner 2026-05-23:

  **Discovery**: iteración secuencial por `coleccion.php?id=N` desde
  id=1 hasta el máximo conocido (~6500). No navegamos el grafo "Otras
  ediciones de X" — la iteración secuencial cubre todas las ediciones
  igual. Discovery por enumeración, descartando ids que devuelvan 404
  o que sean páginas vacías.

  **Fase 1 — parser base, Layout A** (en progreso):
  parser detecta secciones por `<h2>` (con HTML entities decoded y
  whitespace trim — algunas son `<h2><strong>`, otras `<h2>` puro):
  - `Números editados` — tomos regulares, **descartados por
    `is_collectible_edition`** salvo que la página entera sea formato
    premium (ver más abajo).
  - `Números editados (Ediciones Especiales)` — tomos con signal
    `special_edition`, pasan el gate.
  - `Números editados (Portadas alternativas)` — signal `variant_cover`,
    pasan.
  - `Números editados (Packs)` — **solo si traen extra/variant/special**
    (signal en la línea descriptiva del pack); packs "tomos 1+2 sin
    extra" se descartan.
  - `Números editados (Edición Revisada)` — descartado (re-impresión,
    no coleccionable).
  - `Números en preparación` / `Números no editados` — opcionalmente
    incluibles como preventa, sin precio.
  Items dentro de las secciones se parsean del `<table class="ventana_id1">`:
  `<img class="portada">` con `alt` = título, líneas `<br/>`-separadas
  con `XX páginas`, `Y,YY €`, `[día] <a>Mes Año</a>`.

  **Detección "página entera = edición premium"**: lee
  `<b>Formato:</b> <valor>` (NO `<strong>`) y matchea tokens
  `cartoné`, `tapa dura`, `A5` (148x210 / 150x210), `Tomo doble`,
  `doble sobrecubierta`, `Libro de ilustraciones`, `Kanzenban`.
  Cuando matchea, TODOS los items de "Números editados" reciben el
  signal correspondiente automáticamente (`kanzenban`, `hardcover`,
  `omnibus`, `artbook` según el caso). Cubre id=6242 (Edición Grimorio),
  id=1741 (FMA Kanzenban), id=342 (Slam Dunk Kanzenban), id=4027
  (Ilustraciones Gotouge). **Kanzenban INCLUIDA** (decisión del owner
  2026-05-23): el corpus ya tiene kanzenbans desde otras fuentes,
  sería inconsistente descartar selectivamente; el filtro por signal
  type en el dashboard permite ocultarlas cuando se quiere navegar
  solo cofres/extras.

  **URL sintética por item** (gotcha #27 generalizada): cada item
  genera `coleccion.php?id=<N>&item=<edition_slug>-<vol>` donde
  `edition_slug ∈ {regular, especial, alternativa, pack, grimorio, ...}`
  y `vol` es el número de tomo. Determinístico (mismo input → mismo URL)
  para que `append_jsonl` haga upsert correcto en re-scrapes.

  **Fase 2 — schema `images[]` + Layout B extras**:
  - **Schema change aditivo**: nuevo campo `images: [{url, local, kind}]`
    donde `kind ∈ {cover, extra, variant_cover, back_cover, gallery}`.
    `image_url` / `image_local` se mantienen como alias del primer
    elemento (`kind=cover`) — no breaking change para consumidores
    existentes. Frontend modal: render carrusel cuando `images.length > 1`.
  - **Layout B parser**: secciones `Cofres de regalo con las primeras
    ediciones de X`, `Regalos con las primeras ediciones de X`,
    `Regalo con la primera edición de X`, `Regalos de X`, `Extras de X`.
    Cada item en `<table width="920">` `<td width="150">` con `<br/>`-
    separated lines.
  - **Vinculación extra→tomo**: el texto descriptivo de cada extra es
    estructurado, NO prosa: `<Serie> nº<N>` línea 1, `(1ª Edición)` /
    `Edición Especial Limitada` / `Portada Alternativa` línea 2,
    descripción del extra, fecha. Algoritmo:
    1. Parsear primero Layout A → dict `{(edition_kind, vol_n): item}`.
    2. Para cada extra Layout B, identificar target via marker:
       `(1ª Edición)` → target en "Números editados" (regular).
       `Edición Especial Limitada` → target en "(Ediciones Especiales)".
       `Portada Alternativa` → target en "(Portadas alternativas)".
       `Edición Grimorio nº<N>` (sin paréntesis) → la página entera ES
       la edición premium.
    3. Si el target EXISTE en el dict → upsert con imagen appendeada al
       `images[]` y descripción del extra en `extras[]`.
    4. Si el target NO EXISTE (extra de tomo regular que no se listó por
       ser tomo normal sin qualifier) → CREAR el tomo con la imagen del
       extra como `kind=extra` + signal `bonus`, ahora pasa el gate. Esto
       es lo que "abre la puerta" a tomos regulares de 1ª edición que
       trajeron marcapáginas/postales/cofres.
  - **Dedup cross-source**: cada item generado tiene URL sintética única
    (no se pisa con otras en items.jsonl). Cluster_key (series_key +
    edition_key + volume) agrupa a presentación con items del mismo
    tomo desde Norma/Mangavariant/calendario. **El `image_local`
    sticky** (gotcha #25) protege el espejo cuando se re-scrape.

  **Fase 3 — iteración masiva**: corrida full sobre ~6500 ids. Antes
  pensar paginación más agresiva en el dashboard, o filtrar
  agresivamente en Fase 1 (descartar páginas que son solo "Números
  editados" sin formato premium y sin secciones extras — solo escribir
  items cuando hay al menos una sección premium o un extra que vincular).
  Cron semanal vía Panel de Control.

  Status: Fase 1 en implementación. Tras validación piloto sobre 5
  colecciones conocidas (ids 1606, 3020, 6090, 6242, 2688) + dry-run
  comparado contra items.jsonl actual, se decide si avanzar Fase 2
  inmediatamente o esperar feedback del corpus.

---

Last updated: 2026-05-24 (primera corrida scrape_full completa + standardize
--force-all + audit exhaustivo del catálogo) — Ejecución end-to-end del nuevo
modelo "2 scripts canónicos" sobre el catálogo entero, primera vez que
`lista.php` se recorre completo (3432 colecciones) post-refactor.

**Cifras del corpus (snapshot 2026-05-24)**:
- Total items: **5532** (5763 → 6669 tras scrape, → 5535 tras standardize+dedup,
  → 5532 tras cleanup de compound edition_slugs).
- 100% `standardized_at` (forzado todo el corpus).
- 1564 distinct series_keys, 3062 distinct edition_keys.
- Cobertura: image_url 99.7%, image_local 96.7%, volume 83.2%, release_date
  86.6%, price 59.3%, author 51.8%, isbn 35.7%.
- Top sources nuevos: Mangavariant 1744 (sitemap completo), ListadoManga
  colecciones 1002 (lista.php discovery), Manga-Sanctuary 947, SocialAnime
  Cofanetti 333, ListadoManga calendario 237.

**Pipeline corrido**: `scripts/scrape_full.sh` ~1h 16m (5763 → 6669 items,
+906 netos pre-standardize) seguido de `/standardize-catalog --force-all`
(45 chunks ~150 items c/u, 7 waves paralelas de subagentes,
6669 procesados → 5535 final con 915 dedups por (series, edition, vol)
+ 191 non-manga movidos a blacklist + 1 outlier auto-corregido).

**Issues descubiertos en el audit (y arreglados retroactivamente)**:

1. **Compound edition_slugs (50 items)**: a pesar de la regla anti-compound
   en el skill, los subagentes generaron edition_keys terminadas con dos
   slugs (ej. `tokyo-ghoul-edizionibd-deluxe-box`, `blame-panini-ultimate-deluxe`).
   Cleanup determinístico aplicado en items.jsonl:
   - `collection-box` → `boxset` (20 items)
   - `collector-box` → `collector` (11)
   - `ultimate-deluxe` → `ultimate` (8)
   - `taniguchi-deluxe` → `taniguchi` (5)
   - `deluxe-box` → `boxset` (4)
   - `regular-box` → `boxset` (1)
   - `ultimate-variant` → `variant` (1)
   - `edition-box` → `boxset` (1)

   3 items mergearon contra existentes después del cleanup (5535 → 5532).

2. **Publisher slug duplicates**: `kimdong` (10 items) → consolidado a
   `kim-dong` (publisher multi-token canonical); `001` (4) → `001edizioni`.
   Backfill cluster_key corrido tras el cambio.

3. **Publishers nuevos legítimos no en allowlist del skill**: `edizionibd`
   (137 items), `kurokawa` (62), `dynit` (35), `shogakukan` (34),
   `distrito` (30), `jpop` (29), `ichijinsha` (23), `akita` (21),
   `hakusensha` (20), `noeve` (11), `asciimw` (11), `luckpim` (7),
   `crunchyroll` (5), `001edizioni` (4), `takeshobo` (4), `goen` (4),
   `kbooks` (4), `tokuma` (3), `futabasha` (3), `nxb` (3), `yenpress` (3),
   `gpmanga` (3), `mpeg` (3), `carlsen` (3), `tokyomangasha` (5), `ipm` (5).
   Todos son publishers reales y consistentes; el skill prompt podría
   eventualmente agregarlos al allowlist explícito, pero los subagentes
   ya los usaron coherentemente (no se contaminó con basura).

4. **Funside parser bug**: 42 items Funside con prefix
   `"Aggiungi al carrello Confrontare "` en `title_original` (capturaba
   el botón del listing como inicio del title). El `title` ya estaba clean
   (skill lo sobrescribió), pero futuras corridas iban a volver a meter
   el prefix. Fix en `scripts/manga_watch.py:443`: agregadas 2 regex
   anchoradas al INICIO del title (`^Aggiungi\s+al\s+carrello\s+Confrontare\s+`
   y `^Confrontare\s+`). Tests de regresión:
   `test_clean_title_strips_funside_cart_prefix`. Total tests: 331/331 verde.

5. **Chunk 10 — bug del subagente**: el LLM truncó 28 URLs Panini IT en
   `~96` chars (cortando `.html` final). Detectado por mismatch URL en
   merge. Fix programático: matchear URLs por prefix de 80 chars contra
   chunk_10.jsonl y restaurar la URL completa. 100% recuperado, no se
   perdió ningún item.

6. **3 chunks (29, 31, 34) y wave 6+7 (35-44)**: los subagentes 29, 31, 34
   en wave 5 hit session limit y solo procesaron 149/150 items cada uno
   antes del cutoff. Wave 6 re-procesó los 7 chunks faltantes (35-41) y
   wave 7 hizo el retry de 29/31/34 + chunks 42-44. Los 5 items
   genuinamente missing tras todas las waves se procesaron INLINE
   (Blue Lock Collector 14, Burn the Witch Limited 1, D.Gray-man Variant,
   Vanitas Variant 1, Prison School Variant 21).

**Consistency check post-merge**: 1 outlier auto-corregido
(`our-wild-youth-milkyway-regular` vol 8 → `our-wild-youth-milkyway-limited`
para alinearse con los hermanos del coleccion_id). Después del merge,
**0 coleccion_ids con múltiples series_keys** (consistency total).

**Errores conocidos del scrape (no críticos, no afectan datos finales)**:
- 4 `kind: js` sources hit `greenlet.error: Cannot switch to a different
  thread` (Crunchyroll Noticias, Kibook Novedades, Seven Seas Box Sets,
  Meian). El `_js_lock` debería serializar las JS sources pero algo se
  pisó. No bloqueante — sólo perdieron esas 4 fuentes esa noche; el
  próximo `scrape_delta` las re-procesará. **Pendiente para investigación**:
  ver si Playwright async-thread-safety se rompió con los nuevos workers.
- 1 unknown h2 en listadomanga-collections: "Portadas de Roboco y Yo"
  (id=4778) — ya documentado como edge case descartable, no aporta items
  relevantes.

**Backups disponibles** (gitignored, en data/):
- `items.jsonl.pre-fullrun-bak` — antes del scrape full
- `items.jsonl.pre-standardize-bak` — después scrape, antes /standardize-catalog
- `items.jsonl.pre-audit-cleanup-bak` — antes del cleanup compound slugs
- `items.jsonl.pre-funside-fix-bak` — antes del Funside fix
- `items.jsonl.pre-cluster-bak` — antes del último backfill_cluster_key

**Mejoras futuras detectadas (no implementadas)**:
- Skill prompt update: agregar publishers reales (`kurokawa`, `edizionibd`,
  `dynit`, `shogakukan`, `distrito`, `jpop`, etc.) al allowlist explícito
  para reducir uso de `unknown`. Hoy los subagentes ya los usan
  coherentemente, pero un allowlist explícito daría mejor garantía.
- Skill prompt update: reforzar regla ANTI-COMPOUND con ejemplos
  específicos de las trampas observadas (`-deluxe-box` no es boxset
  doble, es `boxset` solo; `-ultimate-deluxe` es `ultimate`, etc.).
- Robustness del subagente: chunks que hit session limit producen
  output truncado; agregar verificación de URL count y/o
  retry-individual-items dentro del skill.
- Investigación Playwright thread-safety: revisar por qué `_js_lock` no
  está serializando bien `kind: js` sources bajo workers=8.

---

Last updated previo: 2026-05-23 (2 scripts canónicos: scrape_full + scrape_delta;
listadomanga-collections discovery via lista.php) — Reorganización
top-level para clarificar el modelo operativo:

- **`scripts/scrape_delta.sh`** (NUEVO, refactor de overnight_run.sh):
  scraping incremental. Listadomanga via `calendario.php` últimos 3 meses.
  ~30-60 min. Frecuencia: diaria/semanal. El `overnight_run.sh` original
  queda como alias deprecated.
- **`scripts/scrape_full.sh`** (NUEVO): scraping completo. Listadomanga
  via `lista.php` → recorre las ~3432 colecciones activas en orden
  alfabético, buscando en cada una ediciones especiales / portadas
  alternativas / cofres / extras de primera edición. ~2-4 horas.
  Frecuencia: mensual/trimestral.
- **Discovery via `lista.php` en `wikis/listadomanga_collections.py`**:
  nueva función `_discover_via_lista()` + flag `--coleccion-mode {lista|range}`
  default `lista`. Reemplaza la iteración numérica 1..6500 (que procesaba
  muchos ids huérfanos) por el índice oficial alfabético (3432 colecciones
  activas, incluye ids hasta 6624+ que el rango numérico no cubría).
- **`script_registry.py`**: nuevos presets canónicos arriba del Panel de
  Control ("⭐ Canónicos" categoría) — `scrape_delta` y `scrape_full`
  con 2 variantes cada uno (estándar / con opt-ins).
- **CLAUDE.md**: nueva sección "2 scripts canónicos: full vs delta" al
  inicio que explica el modelo + tabla comparativa.

**Modelo conceptual aclarado con el owner**: por ahora **una sola
diferencia entre full y delta es importante** — el discovery de
listadomanga (lista vs calendario). El resto de fuentes corren igual.
En el futuro cada fuente podría tener su propio modo full vs delta
fino, pero hoy se simplifica para no fragmentar la mantenibilidad.

Sin re-correr el catálogo todavía. Próximo paso recomendado: una
corrida real de `scripts/scrape_full.sh` para re-ingerir las 3432
colecciones via `lista.php` (vs los 6500 ids numéricos que se usaron
en Fase 3 inicial — el cambio descubrirá colecciones recientes con
ids > 6500 que no se procesaron antes).

**Update mismo día (post-revisión owner)**: `listadomanga-blog` removido
del pipeline canónico. El owner pidió investigar si era necesario y la
investigación confirmó que aporta 0 items reales al catálogo (los posts
del blog son noticias, no productos — el gate los rechaza). Ver bloque
"`listadomanga-blog` REMOVED" en la sección "2 scripts canónicos". El
RSS feed correspondiente también deshabilitado en sources.yml. Ahorro:
~30-60 min por corrida full.

**Update mismo día #2**: `listadomanga calendario` ALSO removido del
scrape_full. La investigación mostró que las 222 "colecciones exclusivas"
del calendar eran FALSOS NEGATIVOS del parser de collections — el parser
descartaba secciones `Números editados (Planeta DeAgostini Cómics)` y
`(Planeta Cómic)` por error, perdiendo colecciones premium como
"Dragon Ball Box Set Edición de Lujo" (id=1832). Fix aplicado: esas
secciones ahora se procesan como `regular` (con gate de premium-format
de la página, como las demás). Verificado en piloto: id=1832 ahora
extrae 4 items premium (antes 0). El calendar queda SOLO en scrape_delta.
Modelo final: **full = lista.php exclusivamente, delta = calendar
exclusivamente, sin overlap**. Test de regresión:
`test_lmc_planeta_section_processed_as_regular_with_premium_format`.

Last updated previo: 2026-05-23 (Fase 3 cerrada — corrida masiva del catálogo
listadomanga `coleccion.php?id=1..6457`) — Ejecución completa de la
Fase 3 con +1017 items netos y carrusel real activo. Cierre incluye:

- **Corrida masiva en 2 pasadas** (split por edge case técnico):
  - Pasada 1 ids 1-854 cortó por `skip_404_streak=50` demasiado bajo
    (gaps largos del catálogo). +78 items.
  - Pasada 2 ids 855-6457 con `skip_404_streak=500` (subido como
    default permanente) llegó al final del catálogo. +929 items.
  - Re-procesado focalizado de 67 ids con UNKNOWN h2 → +10 items.
  - **Total Fase 3: 1017 items nuevos** (items.jsonl 4840 → 5857).
- **Headers desconocidos descubiertos y cubiertos**: 42 únicos
  detectados, 40 ahora cubiertos por patterns ampliados:
  - **Layout B nuevos**: `Pack especial en cofre de X` (singular),
    `Regalo[s] con X` (sin "primeras ediciones"), `Extras con X`,
    `Cartas/Lámina de regalo con X`, `Regalos exclusivos de la tienda`,
    `Cofre de X (sin "de regalo")`.
  - **SECTION_RULES nuevo**: `Números editados (Ediciones Limitadas)`
    → `limitada` edition_kind con signals `[limited, special_edition]`.
  - **DISCARD nuevos**: `(Planeta DeAgostini Cómics)` / `(Planeta Cómic)`
    (re-ediciones de misma editorial, no premium), `(Novela Gráfica)` /
    `(Manga Bara)` (subtipos editoriales), `Ilustración de portadas/lomos`
    (galerías), `Ediciones de X en Japón y España` (comparativa).
  - Edge cases restantes: 2 (`Tomos de Manga Hentai incluidos en la
    revista Hentype`, `Portadas de Roboco y Yo`) — descartables manualmente.
- **Carrusel real activado** en 36 items con multi-imagen, 153 items
  con al menos un `kind=extra`. Verificado en browser sobre "Mujina into
  the deep nº1" (Inio Asano, Norma): cover + 4 postales + back cover =
  6 imágenes navegables con flechas + dots + descripción del extra.
- **Top series aportadas por Fase 3**: Rurouni Kenshin 43, Bleach 37,
  Berserk 28, Ranma½ 28, Fénix 24, FullMetal Alchemist 18, Ataque a los
  Titanes 16, Tokyo Revengers 16, Beck 16, Hajime no Ippo 15.
- **Cobertura items LMC (1357 filas totales)**: image_url 100%,
  image_local 100%, images[] 100%, price 75.2%, release_date 97.4%,
  author 97.2%, publisher 100%.
- **Top publishers Fase 3**: Norma 348, Planeta Cómic 221, Panini Manga
  173, EDT/Glénat 66, Distrito Manga 40, Milky Way 27.
- **`UNKNOWN_H2_LOG` persistente**: el bootstrap escribe el log de h2
  desconocidos a `logs/listadomanga_unknown_h2.txt` al final de la
  corrida. Para futuras adiciones del catálogo, basta inspeccionar ese
  archivo y agregar patterns.
- Backups: `data/items.jsonl.pre-lmc-fase3-bak` (4840 filas).
- **Re-merge focalizado final**: tras descubrir los UNKNOWN h2 y agregar
  los patterns, los items Layout A ya ingeridos (status=seen) no se
  re-escribían vía `process_state` porque el `content_hash` no incluye
  `images`/`extras`. Solución: snippet python que re-parsea los 67 ids
  con UNKNOWN h2 y hace **MERGE union manual** de images[]/extras[]
  bypaseando `process_state`. Resultado: 48 items nuevos creados desde
  Layout B (tomos de 1ª edición con cofres/regalos) + 3 items existentes
  enriquecidos con extras adicionales. **Total final: 5905 items** en
  items.jsonl. 55/75 imágenes extras descargadas al espejo local (20
  fallos por hotlinks bloqueados, items mantienen image_url como
  fallback).

**Conclusión del proyecto listadomanga_collections**: las 3 fases
completas + re-merge final suman ~1065 items nuevos al corpus de los
~6457 ids del catálogo (~16% de las colecciones aportan al menos 1
item coleccionable; el resto son tomos regulares sin formato premium
ni extras). El carrusel modal + extras[] descriptivos eleva
sustancialmente la calidad de los items existentes (cofres,
marcapáginas, postales, pósters, baraja de tarot, etc. visibles en el
modal).

Last updated previo: 2026-05-23 (Fase 2 cerrada — schema `images[]` aditivo +
Layout B parser + merge extra→tomo + frontend carrusel) — Implementación
completa de Fase 2 del parser `scripts/wikis/listadomanga_collections.py`.
Cierre incluye:

- **Schema aditivo en `items.jsonl`**: nuevos campos
  - `images: [{url, local, kind, description}]` — carrusel. `kind ∈ {cover,
    extra, variant_cover, back_cover, gallery}`. Primer elemento siempre
    `kind=cover`, sincroniza con `image_url`/`image_local` legacy (no
    breaking). Cuando length > 1 el modal renderiza carrusel.
  - `extras: [{description, release_date, source_section}]` — descripciones
    de items extra vinculados al tomo (cofres / postales / marcapáginas).
- **Layout B parser** en `listadomanga_collections.py`: `<table width="920">`
  con `<td width="150">` y texto `<br/>`-separated. Detecta marker en línea
  2 (`(1ª Edición)` / `Edición Especial Limitada` / `Portada Alternativa` /
  `Edición Grimorio nº N`). Headers reconocidos: `Cofres de regalo con
  las primeras ediciones de X`, `Regalos con las primeras ediciones de X`,
  `Regalo con la primera edición de X`, `Regalos de X`, `Extras de X`.
- **Algoritmo merge extra→tomo** (`_merge_extras_into_items`): para cada
  extra Layout B, identifica target `(edition_kind, volume)` y:
  - si target ∈ Layout A → mutación in-place del Candidate (append imagen
    a `images[]` con `kind=extra`, append entry a `extras[]`).
  - si target NO existe Y `target_edition_kind=regular` → CREA Candidate
    nuevo con imagen del extra + signal `bonus` + tag `from_extras`. Esto
    abre la puerta a tomos regulares de 1ª edición que el gate
    `is_collectible_edition` no aprobaría sin el extra como justificación.
- **Log de h2 desconocidos** (`UNKNOWN_H2_LOG`) — registra headers que no
  matchean ningún SECTION_RULES ni LAYOUT_B_SECTION_PATTERNS para detectar
  patrones nuevos durante la corrida masiva. En los 5 fixtures piloto +
  ids 1-100: **0 unknown**.
- **`append_jsonl` con union-merge** para `images[]` y `extras[]`: dedup por
  `(kind, url)` y `(description, release_date)` respectivamente. Garantiza
  que un re-scrape que sólo trae la cover NO borre los extras agregados en
  una pasada previa con Layout B, y viceversa.
- **`mirror_candidate_images` extendido** para descargar TODAS las imágenes
  del `images[]` (no sólo la cover de `image_url`). Cada extra recibe su
  espejo local en `data/images/` con el mismo nombre determinístico.
- **Frontend carrusel** en `web/index.html` + `scripts/build_web.py`:
  - Modal renderiza carrusel cuando `images.length > 1` con flechas + dots
    indicator + descripción del extra. Si length ≤ 1, fallback a single
    image legacy (no breaking para items pre-Fase 2).
  - Estado Alpine `modalImageIdx` que resetea a 0 al abrir item nuevo.
  - `dedupByUrl` y `_merged_canonical` en build_web propagan `images[]` y
    `extras[]` con union dedup cross-source.
  - Lista visible de "Incluye / extras de primera edición" debajo de los
    datos del modal, con descripción + fecha.
- **Backfill aplicado**: 4818 items existentes con `image_url` recibieron
  `images=[{kind:cover}]` para que el carrusel los reconozca cuando un
  re-scrape posterior agregue extras. Aditivo, sin tocar otros campos.
- **Tests**: 6 nuevos en `tests/test_extraction.py` (cobertura merge, creación
  desde extras, marker desconocido = skip, Grimorio pattern, flag
  `enable_layout_b=False`, union-merge en append_jsonl). Total: **324
  verde** (304 previos + 20 LMC = Fase 1 14 + Fase 2 6).
- **Validación local sobre fixtures**: 36 items vs 18 en Fase 1 (+18
  creados desde extras), 57 imágenes totales, 39 extras descritos, 0 h2
  desconocidos. Re-corrida ids 1-100 con `--include-seen`: 9 candidates (4
  nuevos por Layout B + 5 seen) — Kobato vol 6, FullMetal Alchemist vols
  1/20/27 son tomos de 1ª edición creados desde cofres que no estaban en
  el catálogo. items.jsonl 4836 → 4840 (+4).

**Estrategia recordada con el owner**: Fase 3 (iteración masiva ids
1-6500) se hace al final en UNA sola corrida, después de tener Fases 1+2
estables. Total HTTP ~6700 reqs en vez de ~19500 si corriéramos full
entre fases.

Last updated previo: 2026-05-23 (Fase 1 cerrada — parser por colección de
listadomanga.es; piloto ids 1-100 ingerido) — Implementación completa
de Fase 1 del parser `scripts/wikis/listadomanga_collections.py` para
`coleccion.php?id=N`. Cierre incluye:

- **Parser Layout A** (`Números editados [+variants]`, packs con extras,
  formato premium desde `<b>Formato:</b>`). Detección por `<h2>` con
  HTML entities decodificadas. URLs sintéticas con `?item=<edition_slug>-
  <vol>-<image_id>` (gotcha #27 generalizada; image_id como disambiguator
  primario garantiza unicidad cuando un mismo (vol, edition_kind) tiene
  múltiples productos físicos distintos — caso real Zelda packs 1-5 vs 6-10
  + Berserk vol 42 con 2 ediciones limitadas distintas).
- **Dispatcher wiring**: `--bootstrap-wiki listadomanga-collections` +
  flags `--coleccion-from / --coleccion-to`. Panel de Control con 2
  presets (piloto 1-100 + full 1-6500). Entrada en sources.yml con
  `kind: wiki`.
- **Tests**: 14 nuevos en `tests/test_extraction.py` (12 cobertura
  inicial + 2 regresiones de bugs encontrados en el piloto). Suite
  total: **318 verde** (304 previos + 14 LMC).
- **Piloto ids 1-100** corrido en real: 5 items nuevos (2 artbooks
  Tsubasa Norma, 1 artbook Uzumaki Glénat, 2 packs Zelda "tomos 1-5 / 6-10
  + cofre"). Score≥30 todos, gate pasa todos. Items en items.jsonl
  4831 → 4836. Portadas espejadas 5/5. Backup
  `data/items.jsonl.pre-lmc-piloto-bak`.
- **Bugs encontrados y arreglados durante el piloto** (con tests de
  regresión nuevos):
  1. *Colisión URL en packs Zelda*: disambiguator de description_extra
     truncado a 20 chars colapsaba "pack-especial-tomos-1-a-5" y
     "pack-especial-tomos-6-a-10" al mismo slug. Fix: usar image_id del
     CDN (hash único + estable) como disambiguator primario.
  2. *Gate `is_collectible_edition` rechazaba packs*: title
     "The Legend of Zelda" sin número/URL canónica no cumplía las
     pruebas de "producto físico" pese a signal `box_set`. Fix: para
     `edition_kind=pack` enriquezco el title con `description_extra`
     ("The Legend of Zelda — Pack especial tomos 1 a 5 + cofre de
     regalo"), aprueba.

**Fase 2 y 3 pendientes** (ver "Next things on the radar"):
- Fase 2: schema `images[]` aditivo (carrusel cover+extras), Layout B
  parser (Cofres / Regalos / Extras de X), vinculación extra→tomo —
  crea tomos regulares de 1ª edición con marcapáginas/postales que hoy
  no entran al catálogo.
- Fase 3: iteración masiva ids 1-6500 + paginación dashboard + cron
  semanal.

**Decisión estratégica con el owner**: implementar Fase 2 + Fase 3
sin corrida completa intermedia (validamos contra los 5 fixtures locales
en `/tmp/lmc_fixtures/` + un piloto chico ids 1-100 post-Fase 2 para
detectar edge cases), después UNA corrida completa final. Total ~6700
HTTP requests vs ~19500 si corriéramos full entre fases. Mitigación de
bugs ocultos: log estructurado de `<h2>` desconocidos durante la
corrida completa para detectar patrones nuevos no cubiertos por los
fixtures (lo agrego como parte de Fase 2).

Last updated previo: 2026-05-23 (plan + Fase 1 del parser por colección de
listadomanga.es — `scripts/wikis/listadomanga_collections.py`) —
Análisis de patrones sobre 15+ páginas `coleccion.php?id=N`
confirmó dos layouts HTML mutuamente excluyentes y un texto de extras
muy estructurado (no prosa libre). Plan acordado con el owner en 3
fases. Sin cambios todavía a items.jsonl (el piloto se hizo en la
sesión siguiente — entrada de arriba).

Last updated previo: 2026-05-23 (consolidación: `unmapped_series.jsonl` es la
única fuente de verdad para "uncertain records"; eliminado
`uncertain_groupings.jsonl`) — Por feedback del owner: a veces algunas
auditorías escribían flags en `data/uncertain_groupings.jsonl` y otras en
`data/unmapped_series.jsonl`. Decisión: **único bucket**. Cambios:

1. **Schema extendido** en `unmapped_series.jsonl` para aceptar entries de
   auditoría manual: campos opcionales `flagged_by` (`pipeline` /
   `audit:<nombre>` / `human`), `reason`, `notes`, `proposed_canonical_key`,
   `proposed_canonical_display`, `current_edition_key`. El pipeline
   (`log_unmapped_series` en `scripts/series_aliases.py`) sigue escribiendo
   sus 6 campos básicos; los readers (skill `/enrich-series-aliases` +
   `scripts/audit/unmapped_series.py`) ignoran cualquier campo extra que
   no entiendan.
2. **Migración**: las 2 entradas activas de `data/uncertain_groupings.jsonl`
   (studio-ghibli, tsukasa-hojo) appendeadas a `unmapped_series.jsonl`
   con sus `reason`/`notes` preservados via los campos opcionales.
3. **Borrado**: `data/uncertain_groupings.jsonl` +
   `data/uncertain_groupings.jsonl.pre-web-audit-bak` eliminados. Ambos
   estaban untracked (no en git).
4. **Convención documentada** en el file map (entry `unmapped_series.jsonl`)
   + nueva sección "When you flag a record as 'uncertain' / 'needs review'"
   en CLAUDE.md. NUNCA crear archivos paralelos tipo
   `uncertain_groupings.jsonl` / `review_X.jsonl` / `audit_X.jsonl` —
   todo flag va a `unmapped_series.jsonl` con `flagged_by` discriminando
   el origen.

Sin cambios de código ni de items.jsonl. La memoria persistente del agente
también se actualizó con esta convención (feedback memory) para que sesiones
futuras no creen archivos paralelos sin pedir confirmación.

Last updated previo: 2026-05-23 (auditoría de `unmapped_series.jsonl` — limpieza
completa de la cola de series sin alias) — Pasada de mantenimiento sobre
`data/unmapped_series.jsonl` (la cola append-only que el scraper alimenta
cuando encuentra una `series_key` no presente en `series_aliases.yml`).
Estado inicial: **1786 entradas** (1739 únicas). Workflow:

1. **Prune de stale entries**: 1143 entradas correspondían a `series_key`
   ya remapeadas por `/standardize-catalog` previos y no existen más en
   `items.jsonl`. Pruneadas (backup en `.pre-prune-bak`). Live: 596.

2. **Carrera con `/standardize-catalog`**: durante mi prune, otra invocación
   del skill `/standardize-catalog` corrió en paralelo (probablemente del
   usuario) y remapeó 422 entradas más de la cola live. Al re-correr el
   prune contra el snapshot actual de items.jsonl: live=174. *Lección
   operativa*: si `unmapped_series.jsonl` y `items.jsonl` se editan en
   paralelo, conviene re-snapshot antes de aplicar.

3. **Heurística local** (sin LLM, `/tmp/unmapped_audit/heuristic_cleanup.py`)
   sobre las 174 vivas:
   - 84 fuzzy-match ratio=1.0 contra sí mismas (keys ya canónicas en items.jsonl
     pero ausentes de aliases.yml).
   - 1 fuzzy-match real: `kaguya-sama-love-is-war` → `kaguya-sama` (ratio 0.98).
   - 0 stripped-exact-match en este paso (el otro skill ya había barrido los
     casos con qualifiers obvios).
   - 89 a investigar.

4. **Investigación**: dividí 90 entradas (89 + uncertain margin) en 3 chunks
   de 30 a subagentes paralelos con WebSearch/WebFetch + acceso al
   `canonical_catalog.json` (535 series canónicas del corpus) y a
   `series_aliases.yml`. Cada subagente decidió por cada fila:
   `merge-to-existing` / `new-canonical` (con aliases multilingüe) /
   `uncertain`.

5. **Veredictos** (todos los 90):
   - **17 merge-to-existing**: variants retailer-exclusivos (Blue Lock
     Fnac/Momie/Panini → `blue-lock`; Dandadan Canal BD → `dandadan`;
     Boruto Two Blue Vortex Fnac → `boruto-two-blue-vortex`),
     traducciones (Ataque a los Titanes Inside → `attack-on-titan`;
     Carnets de l'Apothicaire → `apothecary-diaries`; Gen di Hiroshima →
     `gen-of-hiroshima`; Mushoku Tensei Reencarnación → `mushoku-tensei`),
     boxsets MX (Lone Wolf → `lone-wolf-and-cub`), spin-offs Gundam
     (Crossbone, Origin → `mobile-suit-gundam-series-and-spin`), un caso
     de scraper-artifact (`prochainement` → `slam-dunk`, Kana metió
     "Prochainement"/banner como series), y artbooks (Promised Neverland
     World → `the-promised-neverland`, Visões Grotescas → `junji-ito`).
   - **71 new-canonical**: agregados a `series_aliases.yml` con aliases
     multilingüe. Incluyen series genuinamente nuevas en el catálogo
     (Aposimz, Black Bird, Bloom Into You, Btooom!, Chiisakobe, Captain
     Harlock: Dimensional Voyage, Heaven Official's Blessing, Kyoukai
     no Rinne, Orb: On the Movements of the Earth, Steam Reverie in
     Amber, Times of Botchan, Pygmalion, Sweet Paprika, The Box Man,
     Tokyo Alien Bros, Tsubaki-chou Lonely Planet, Yuuna and the
     Haunted Hot Springs, Zone-00, etc.) + artbooks/ilustración
     (Fuzichoco Gashu Saigenkyou/Shukusai Junrei, Beasts Art Book,
     Kasai Ayumi Reijin 1993-2025, Dragon Quest Illustrations, Mihara
     Jun Special Box, Visões Grotescas como artbook). De los 71, 21
     llevaron canonical_key distinto del slug logueado (e.g., `1993-2025`
     → `kasai-ayumi-reijin-1993-2025`; `box` → `mihara-jun-special-box`;
     `katekyo-hitman-reborn-i-ii` → `katekyo-hitman-reborn`), así que
     items.jsonl también se remapeó.
   - **2 uncertain**: `studio-ghibli` (Coffret es un libro de cinema-ref,
     no manga) y `tsukasa-hojo` (series_key es nombre de autor, no de
     obra). Guardados en `data/uncertain_groupings.jsonl`.

6. **Aplicación**:
   - **items.jsonl**: 38 filas remapeadas (17 merge + 21 new-canonical con
     key distinta). Backup `.pre-unmapped-web-bak`.
   - **series_aliases.yml**: 106 → **261** entradas (+71 new-canonical
     +84 self-canonicals para evitar re-logueo). Backup
     `.pre-unmapped-web-bak`. Fix encontrado por el camino:
     `yaml.safe_dump` no representa `OrderedDict` (raise `RepresenterError`
     → archivo trunco a 0 bytes); restauración desde backup + re-escritura
     con `dict` plano (Python 3.7+ preserva orden de inserción).
   - **uncertain_groupings.jsonl**: +2 casos para revisión manual.
   - **unmapped_series.jsonl**: 174 → **0**. Cola limpia.
   - **cluster_key**: refrescado tras los remaps (`backfill_cluster_key.py`).

7. **Decisión técnica registrada**: el "fix correcto" para entries que el
   resolver no agarra es **remap directo en items.jsonl + entry en
   `series_aliases.yml`**, no agregar más aliases en blanco. Las 84
   self-canonicals se agregaron al YAML con `aliases: []` puramente para
   evitar re-aparecer en el log futuro — no porque la display tenga
   variants conocidas (los aliases reales se irán enriqueciendo con
   `/enrich-series-aliases`).

Corpus: items.jsonl está en **4841** filas (bajó de 5136 entre el inicio
de la sesión y ahora; `/standardize-catalog` corrido en paralelo movió
non-manga a blacklist + dedupeó por `(series, edition, vol)`). Tests
304/304 verde. CLAUDE.md actualizado.

Last updated previo: 2026-05-23 (auditoría de agrupaciones — fase 2, resolución por
web research) — Continuación de la pasada de auditoría del día anterior:
los 5 casos que quedaron en `data/uncertain_groupings.jsonl` se resolvieron
investigándolos en internet. Workflow:

1. **5 subagentes en paralelo**, uno por caso, con WebFetch + WebSearch
   para verificar el producto real. Tres pegaron contra el session limit
   antes de terminar (NieR Art, Tokyo Ghoul Zakki:re, Yomi no Tsugai), así
   que los investigué desde el hilo principal con WebFetch directo.
2. **Veredictos**:
   - **Blue Lock × Liverpool FC** (Manga Dreams IT) → **confirm-fix**.
     Es un collab one-time de Kodansha JP (oct 2024) que reagrupa los
     vols 1-5 con tapas Liverpool FC para el anime S2. NO es un variant
     line de mangadreams.it, es producto Kodansha. Movido a
     `blue-lock-kodansha-liverpool-collab`.
   - **Gannibal box set (Vol. 2)** (Amazon IT, 001 Edizioni) →
     **confirm-fix**. ISBN 8871822900 es el **2º box de la línea
     "Collection box" de 001 Edizioni**, contiene vols 4-6 (el "(Vol. 2)"
     refiere al número de caja, no al volumen del manga). Movido al
     series_key `gannibal-collection-box` para hermanarse con
     "Collection box (Vol. 1-3)" y "Collection box (Vol. 4)".
   - **NieR Art** (Kurokawa FR) → **leave-as-is**. Artbook standalone
     de 160 páginas por Kazuma Koda (concept artist) que cubre TODA
     la franquicia (Replicant + Automata + Reincarnation + Yorha stage).
     La sibling `nier-automata-kurokawa-artbook` es la "World Guide"
     Automata-específica → ambos correctamente distintos.
   - **Tokyo Ghoul Zakki:re** (Norma ES) → **leave-as-is**. Artbook
     oficial de 288 páginas que expande el universo entero post-:re.
     La versión Glénat FR ya está bajo `tokyo-ghoul-glenat-artbook`,
     consistente. Mantener ambas bajo `tokyo-ghoul` (franquicia-raíz).
   - **Yomi no Tsugai** (Mangavariant) → **confirm-fix + remap masivo**.
     `data/series_aliases.yml` ya tiene `yomi-no-tsugai` como canonical
     con "Daemons of the Shadow Realm" como alias, pero 11 items en
     items.jsonl quedaron con el `series_key=yomi-no-tsugai-daemons-of-the-shado`
     (artefacto de truncado del slugify a 33 chars que `canonical_series_key`
     nunca resolvió). Remap aplicado: `series_key` → `yomi-no-tsugai`,
     `series_display` → `Yomi no Tsugai`, `edition_key` prefix-replace
     (`-unknown-collector` con publisher Kurokawa → `-kurokawa-collector`,
     etc.).
3. **Aplicado**: 2 confirm-fix individuales (Blue Lock, Gannibal) + 11
   filas remapeadas (Yomi). Total **13 items modificados**.
4. **Cluster_key refresh**: corrí `backfill_cluster_key.py` porque cambié
   `series_display` en 13 filas.
5. **`data/uncertain_groupings.jsonl` vaciado** — los 5 casos quedaron
   todos resueltos. Backup en `.pre-web-audit-bak` por si se necesita
   revisar la cola original.

Tests: 304/304 verde. Backups `data/items.jsonl.pre-web-audit-bak`
preservado. Decisión de diseño confirmada: items que sobreviven la
auditoría como **leave-as-is** valen igual que los corregidos — son
casos donde la agrupación actual ya era buena y la heurística los flagueó
de más; mantenerlos sin tocar es la respuesta correcta.

Patrón aprendido para futuras auditorías: cuando un alias YA existe en
`series_aliases.yml` pero `canonical_series_key()` no lo resolvió, el
problema es que la `series_key` derivada en el scrape no matchea ningún
alias normalizado (el resolver compara contra display y key normalizados,
no contra cualquier substring). El fix correcto es remap directo en
items.jsonl, no agregar más aliases.

Last updated previo: 2026-05-23 (nueva fuente BR — Biblioteca Brasileira de Mangás) —
Segunda fuente nueva en cadena tras SocialAnime: **blogbbm.com**, un blog
comunitario brasileño que mantiene **dos posts-guía curados continuamente
actualizados** (la última entrada agregada es de mayo 2026, el primer
post arrancó en 2020). Cubre publishers BR con clasificación explícita
de variant/special/bonus que el scrape directo de Panini BR / JBC /
NewPOP / Pipoca & Nanquim / MPEG no marca por sí solo.

Trabajo entregado en esta pasada:

1. **Parser `scripts/wikis/blogbbm.py`** (~370 líneas) — heurística
   **title-driven** que soporta dos layouts distintos del mismo blog:
   - **Layout A** (`/2020/10/09/capas_variantes/`): gallery `<div>`
     ANTES del título, prose después. Cada entry separado por `<hr>`,
     pero algunos chunks tardíos agrupan varios entries sin `<hr>` entre
     ellos. Las imágenes siempre van a un buffer `pending_imgs` y se
     atan al siguiente título — esto resuelve el alineamiento aunque
     haya N entries dentro de un mismo chunk.
   - **Layout B** (`/2024/05/15/guia-volumes-especiais-...`): título
     con `(MM/YYYY)` parens al final, `<figure>` después. `<figure>`
     adentro del current entry (post-título).

   Distinción: `<div>` siempre va al buffer (entre entries), `<figure>`
   va al entry actual.

   Detección de título: parens-date `(MM/YYYY)` al final OR ficha link
   `/manga/<slug>/` cubre ≥80%. Modo lenient (cuando pending_imgs está
   cargado sin asignar) acepta volume marker `#NN` solo o `<strong>`
   envolviendo. Cubre entries Layout A sin ficha (Re:Zero, NGNL).
   Reject prefijos narrativos largos para no agarrar prose ("Em janeiro",
   "No Brasil", "A editora", "O volume #") — cuidado con prefijos cortos
   ambiguos como "no " (chocaría con "No Game No Life").

2. **URL sintética por-entry con query param** (gotcha #27 nueva).
   Primer intento usaba fragment `<ficha>#vol-N-<stem>`, pero
   `normalize_url_for_dedup` strippea fragments siempre → 35 candidates
   colapsaban a 21 ficha-URLs distintas, perdiendo 14 entries
   silenciosamente. Fix: query param custom `?bbm-entry=vol-N-<image-stem>`
   que NO está en `TRACKING_PARAMS` y sobrevive la normalización.
   Patrón replicable para futuros wikis con muchos entries derivados de
   una URL ficha común.

3. **Dispatcher + UI**: `--bootstrap-wiki blogbbm` en argparse choices;
   preset 🇧🇷 BBM en `script_registry.py`; fase `02g` en
   `overnight_run.sh` (whakoom opt-in ahora es 02h).

4. **Tests**: 5 nuevos — parse layout A / parse layout B / rejects
   narrativos / image proxy stripping (i0.wp.com → blogbbm.com) /
   iter_year_months. **304/304 verde**.

5. **Ingesta**:
   - 35 candidates (25 Capas + 10 Volumes), 1 dropped por gate
     `is_collectible_edition` → **34 reportables**.
   - Backup `data/items.jsonl.pre-blogbbm-bak`.
   - **Corpus: 5102 → 5136** (+34).
   - **Brasil: 40 → 74** (+85%) — sale del último puesto y se acerca a
     Argentina. Antes BR estaba subrepresentado pese a tener 6 sources
     directas porque ninguna marcaba "capa variante" en title; ahora 34
     items con `variant_cover` + `special_edition`/`bonus` signals
     explícitos.
   - Cobertura BBM: image 100%, release_date 100%, publisher 85% (29/34),
     price 73% (25/34). ISBN 0% (BBM no expone — esperado, son items
     de referencia).
   - 34/34 portadas espejadas a `data/images/`. URLs de imagen usan
     proxy `i0.wp.com` que el parser convierte a `blogbbm.com` directo
     para que el espejo descargue del origen.
   - `standardized_at` NO setado — los 34 quedan pendientes para
     `/standardize-catalog`.

Quedan integrados los dos posts conocidos. Si BBM saca un nuevo
post-guía con otro shape, basta con agregar el meta al `BBM_POSTS`
del parser — la lógica de detección es genérica para layouts WordPress
similares.

Last updated previo: 2026-05-22 (auditoría de agrupaciones con descripción + URL) —
Pasada manual de re-revisión sobre items.jsonl buscando agrupaciones mal
asignadas que se nos colaron porque `/standardize-catalog` solo miró el
title (caso semilla: vol 2 de "One Piece Doors Fanbook" estaba en
`one-piece-glenat-fanbook` porque Manga-Sanctuary scrapeó el título sin
"Doors" — la descripción y el URL slug sí decían "Doors"). Workflow:

1. **Heurísticas de candidatos** (`/tmp/regroup_audit/build_candidates.py`,
   no quedó en repo — utility one-shot):
   - **H1 superset**: items donde la descripción menciona una serie conocida
     más específica que su `series_display` actual (e.g., propio="One Piece"
     + desc menciona "One Piece Doors").
   - **H2 orphan-con-hermana-extendida**: edition_keys de tamaño 1 cuyo
     prefijo coincide con otra edition_key de serie más larga
     (e.g., `one-piece-glenat-fanbook` vs `one-piece-doors-glenat-fanbook`).
   - Output: 113 candidatos (27 H1 + 86 H2 + 3 ambos).
2. **4 subagentes en paralelo** (chunks de ~28 c/u) revisaron cada
   candidato leyendo `title` + `title_original` + `description` + URL
   slug + ediciones hermanas. Veredictos:
   - **confirm-fix**: 34 — agrupación corregida en items.jsonl
     (campos `series_key`, `series_display`, `edition_key`,
     `edition_display`, `title`; `title_original` preservado).
   - **leave-as-is**: 74 — falsos positivos. Patrón principal: el "sibling"
     que la heurística sugería es en realidad una edición con `series_key`
     malformado por qualifiers italianos ("Ediz. variant", "Ediz. limitata")
     o tokens de volumen filtrados en el slug — el candidato estaba bien;
     el hermano es el que necesita limpieza (queda para futura pasada).
   - **uncertain**: 5 — guardados en **`data/uncertain_groupings.jsonl`**
     (archivo nuevo, append-only) para revisión manual.
3. **Fixes aplicados notables**:
   - **Dragon Ball le super livre** (3 fanbooks, vols 1-3) — title scrapeado
     decía "Dragon Ball Fanbook N" pero desc + URL: "Dragon Ball le super
     livre". Mismo patrón que One Piece Doors.
   - **Pokémon Or et Argent / Espada y Escudo / Noir et Blanc** — cada
     generación de Pokémon es su propia sub-serie. Estaban bajo `pokemon`
     genérico; ahora cada gen tiene su `series_key`.
   - **My Hero Academia Ultra Analysis Fanbook** — sub-línea distinta de
     `my-hero-academia` (no es la serie principal, es el fanbook "Ultra
     Analysis"). Antes orphan en `my-hero-academia-kioon-fanbook`.
   - **Kaiju No. 8** vols Collector y Celebration — Star Comics y
     Manga-Sanctuary dropearon el "8" al derivar series_key, quedando
     `kaiju-no`. Movidos a `kaiju-no-8`.
   - **The Legend of Zelda: Breath of the Wild Artbook** — estaba bajo
     `legend-of-zelda` genérico; reasignado al sub-key `zelda-breath-wild`.
   - **Cyberpunk: Edgerunners Madness** — sub-serie distinta, ahora bajo
     `cyberpunk-edgerunners-madness` (el principal sigue en
     `cyberpunk-edgerunners`).
   - **Genshin Impact Artbook officiel vol 1** — los vols 2 y 3 estaban
     en `genshin-impact-officiel`, el 1 en `genshin-impact` genérico.
     Mergeado.
   - **Animal Crossing New Horizons — Le Journal de l'île** — sub-serie
     dedicada, no la genérica.
   - **Killing Stalking Season 1 / Season 3** — el "Box" se había
     embebido en el series_key (`killing-stalking-season-box`); limpiado.
   - **Slam Dunk Takehiko Inoue Illustrations** — artbook dedicado, no la
     línea genérica de Slam Dunk.
   - **Cyberpunk Edgerunners Madness, Negima Boxset, NieR:Automata
     Artbook**, etc. — varios casos similares.
4. **Backfill cluster_key**: corrí `scripts/retrofit/backfill_cluster_key.py`
   porque los fixes cambiaron `series_display` (componente de la fuzzy key).
   1857 cluster_keys refrescadas; 50 items en 25 grupos consolidados
   (-25 cards en el dashboard).

Corpus: distinct series_key **1863 → 1855** (-8), distinct edition_key
**3128 → 3115** (-13). Total items: 5102 (sin cambios). Backups
`data/items.jsonl.pre-regroup-audit-bak` y `data/items.jsonl.pre-cluster-bak`
preservados.

**Casos uncertain en `data/uncertain_groupings.jsonl`** (para revisar
manual o web-check después):
- *Blue Lock x Liverpool FC* — ¿variant retailer-exclusivo merece su propio
  edition_key vs la línea genérica de variantes mangadreams?
- *Gannibal box set (Vol. 2)* — ¿es 2º box numerado o el box del vol 2 solo?
- *NieR Art Vol 1* (Kurokawa) — ¿artbook genérico de NieR o solo de
  NieR:Automata? Hay sibling para Automata.
- *Tokyo Ghoul Zakki:re* — artbook combinado de Tokyo Ghoul + :re, no claro
  bajo qué key debe colgarse.
- *Yomi no Tsugai / Daemons of the Shadow Realm* — caso de
  series_aliases (un solo manga con dos nombres), no de regrouping —
  hay que consolidar las dos keys en `series_aliases.yml`.

**Patrón meta detectado por los subagentes** (no corregido en esta pasada,
candidato para futura): muchos `series_key` malformados con qualifiers
italianos/japoneses filtrados (`-ediz-variant`, `-ediz-limitata`,
volúmenes pegados, "box" embebido en el slug). Un retrofit nuevo que
detecte y limpie esos `series_key` por reglas (tokens prohibidos en
slugs) ahorraría una pasada de subagentes en el futuro.

Tests: 299/299 verde. Nueva entrada en file map para
`data/uncertain_groupings.jsonl`. No hay schema change a items.jsonl —
los campos modificados ya existían.

Last updated previo: 2026-05-22 (nueva fuente IT — SocialAnime variant + cofanetti) —
Nueva wiki `socialanime` que importa el MangaStore italiano de
**socialanime.it** vía un JSON feed paginado (descubierto inspeccionando
`store.js`; el endpoint `flow_mangafeed.php?type={variant|box}&group_no=N&macro_filter=best_of_all`
devuelve 25 items por página con title/link/img/precio/editore/autore/trama/
PublicationDate/extra_class). Cubre 466 variant + 440 cofanetti del mercado
italiano de publishers que las sources directas (Panini IT search, Star
Comics search, Manga Dreams) no capturaban: **Edizioni BD, 001 Edizioni,
Goen, Magic Press, Dynit, Coconino, Tora, Dokusho**.

Trabajo entregado en esta pasada:

1. **Parser `scripts/wikis/socialanime.py`** (~300 líneas) — paginación
   automática hasta página vacía sobre tipos `variant` + `box`, inyecta
   hint "Cofanetto / box set." en la descripción para items de type=box
   sin keyword explícito (sin esto `detect_signals` no levantaría `box_set`
   y caerían fuera del gate). ASIN Amazon → ISBN-10 cuando el ASIN parece
   ISBN legacy italiano (prefijo 88, no `B0…` que son Kindle). Skip items
   sin link Amazon (~10% del feed son entries delisteadas sin URL canónica).

2. **Canonicalización Amazon en `normalize_url_for_dedup`** (gotcha #26
   nueva, extiende #19): añadidos a `TRACKING_PARAMS` los affiliate
   params Amazon (`linkCode`, `th`, `psc`, `ascsubtag`, `smid`, `pf_rd_*`,
   `pd_rd_*`, `content-id`) + path-token stripping `/ref=...` que NO es
   query y por eso parse_qsl no lo agarra. Sólo aplica a host amazon.*.
   Cualquier futura fuente con Amazon affiliates ya cae al mismo canónico
   `/dp/<ASIN>` o `/gp/product/<ASIN>`.

3. **Dispatcher + UI**: `--bootstrap-wiki socialanime` en argparse
   choices; entrada en `script_registry.py` con preset 🇮🇹 SocialAnime
   para que aparezca en el Panel de Control; fase `02f` agregada al
   `overnight_run.sh` (el whakoom opt-in pasa a `02g`).

4. **Tests**: 8 nuevos (parse variant item / box hint / box-no-duplica /
   skip sin link / skip sin título / ASIN Kindle no es ISBN /
   iter_year_months / Amazon URL canonicalization). 299/299 verde.

5. **Ingesta**:
   - 906 items raw del feed → 640 candidates score>=20 → **638 reportables**
     (1 dropped por gate is_collectible_edition, 1 colision dedup local).
   - Backup `data/items.jsonl.pre-socialanime-bak` preservado.
   - **Corpus: 4464 → 5102** (+638, +14%). **Italia: 789 → 1427 (+81%)** —
     pasa de 4º país a empatar con Francia.
   - Cobertura SocialAnime items: **ISBN 95.3%, image_local 97.5%,
     price 100%, release_date 99%**. ISBN viene del ASIN Amazon
     (libros italianos legacy con prefijo 88 son ISBN-10 válido).
   - 622/638 portadas espejadas a `data/images/` en la ingesta (los 16
     fallidos son URLs de imagen Amazon con anti-hotlink, quedan con
     `image_url` como fallback).
   - **`standardized_at` NO setado** — los 638 quedan pendientes para
     `/standardize-catalog` (flujo de doble pasada, gotcha #21). Hay
     que correr el skill después para asignarles series_key/edition_key
     canónicos (algunos ya tienen los del heurístico del scraper, otros
     necesitan revisión LLM porque los títulos italianos con prefijo
     "Ediz." + variante son ambiguos).

Próximos pasos sugeridos por el dueño (en orden):
- Fuente 2: **Biblioteca Brasileira de Mangás** (`/2020/10/09/capas_variantes/`)
  — post-guía consolidado actualizado continuamente con secciones por
  título + dos imágenes (normal vs variant) + editorial BR.
- Fuente 3: **BBM `/guia-volumes-especiais-de-mangas-com-itens-especiais/`**
  — post-guía con volúmenes que traen brindes/postales/marcapáginas/cards.

Last updated previo: 2026-05-22 (ingesta de lista curada usuario — 63 items
nuevos de variantes/ediciones especiales MX/AR/ES). El usuario pasó una
lista de ~75 portadas alternativas / ediciones especiales / sobrecubiertas
reversibles publicadas por Panini México, MangaLine México, Editorial
Ivrea (Argentina), Panini Argentina, OVNI Press, Panini España, Norma
Editorial, Planeta Cómic, Distrito Manga, Milky Way Ediciones, MangaLine
Ediciones (España) y ECC Ediciones. Workflow ejecutado:

1. **Cruce automatizado contra items.jsonl** vía script ad-hoc
   (`/tmp/curated-list/`): 30 entradas ya cubiertas en el corpus desde
   agregadores (Mangavariant / ListadoManga / Whakoom) — confirmadas
   como duplicados por presencia. 41 entradas genuinamente faltantes.
   4 dudosas resueltas por research adicional.
2. **Política multi-source confirmada con el usuario**: para variantes
   donde el corpus ya tenía una entrada vía agregador pero NO la URL
   editorial oficial, agregar la URL oficial igual — el dashboard
   agrupa múltiples filas en una sola card vía `cluster_key`. Por
   eso el alcance final fueron 64 entradas a investigar (no solo
   las 41 missing).
3. **Investigación paralela en 8 subagentes** (uno por familia editorial,
   batches de 4-15 entradas). Cada subagente buscó URL canónica
   (preferencia: tienda oficial → Whakoom → ListadoManga → casadellibro
   → otras), imagen de portada, ISBN, fecha, precio, autor, descripción
   de extras. Resultado: 57/64 con tienda oficial, 7/64 fallback Whakoom
   (`/ediciones/` para items descontinuados Panini MX/Ivrea AR).
4. **Construcción de filas** vía script (`build_rows.py`): para cada
   resultado, derivar `series_key` canónico (vía `series_aliases.py`),
   `edition_key` `{series}-{publisher_slug}-{edition_slug}` con
   publisher_slug market-suffixed (`panini-mx` vs `panini-es` vs
   `panini-ar` para distinguir mercados), `volume` del input,
   `cluster_key` ISBN-based si hay ISBN si no fuzzy, `signal_types`
   del subagente, `standardized_at=NOW` para no re-procesar con
   `/standardize-catalog`. Source field `<MARKET> - <publisher> (lista
   curada)`, source_class=`official` o `curated`.
5. **Descarga de imágenes** vía `image_store.download_image()`
   paralelizada (workers=6). 53/64 OK al primer intento; 7 Whakoom
   re-intentadas explícitamente con `Accept-Encoding: gzip, deflate`
   (NO brotli, ver gotcha #15) — todas funcionaron. 3 imágenes Norma
   con URLs CDN stale, re-fetched og:image desde la página del producto.
   **Cobertura final: 64/64**.
6. **Append vía `append_jsonl`**: 64 filas → +63 netos (H×H pack
   castellano #1+#37 son 2 entradas que comparten URL única del pack).
7. **Tests**: 291 passing.

Notas:
- **Cluster merging**: solo 1 fila nueva (MHA Cofre 42 castellano)
  mergea con una existente vía ISBN. Las otras 62 quedan como cards
  separadas de los registros agregador-only correspondientes, porque
  el `publisher` field difiere entre Mangavariant ("Panini Manga"),
  ListadoManga ("Panini Manga") y mis nuevas filas ("Panini Manga
  España"). Solución futura: correr `/standardize-catalog` con
  `--force-all` para re-unificar series_key/edition_key/volume en todo
  el corpus y dedupear (la skill colapsa las mismas (series, edition,
  vol) en 1 fila aunque vinieran de fuentes distintas).
- **Países**: México 91→108 (+17), Argentina 27→40 (+13), España 385→418
  (+33). Argentina antes era el tercer país con menos cobertura tras
  Reino Unido y Taiwán; ahora está en el rango medio.
- **Backup**: `data/items.jsonl.pre-curated-list-bak` preservado por si
  hay que rollback.
- **Subagentes**: ~720k tokens totales + 340 tool uses en ~7 min
  cumulativos. La estrategia de 1 subagente por familia editorial
  funcionó bien porque cada familia tiene patrones de búsqueda comunes
  (mismo dominio, mismas SKUs, mismo schema de ficha).

Last updated previo: 2026-05-22 (fix extracción de portadas — Sanyodo theme
assets + MangaLine data-URI) — El extractor de imágenes guardaba junk
como `image_url` en dos fuentes: **Sanyodo** (~33 items) capturaba el
ícono de tema `icn_close.svg`, y **MangaLine MX** (~8 items) guardaba
un placeholder `data:image/svg+xml;base64,…` en vez de la portada
lazy-loaded. Cambios (ver gotcha #6 ampliada):
- `IMAGE_URL_BAD_PATTERNS` += `/assets/images/common/` (theme assets de
  WP) y `.svg` (un SVG nunca es portada). Rechaza los íconos de Sanyodo.
- `_img_to_url` ahora saltea valores `data:` URI — así una imagen
  lazy-loaded cae al `data-src`/`data-lazy-src` con la URL real en vez
  de devolver el placeholder data-URI. Aplica al listing extractor y al
  detail extractor (steps 4-5).
- `IMAGE_URL_GOOD_PATTERNS` += `e-hon.ne.jp` — CDN de portadas que
  linkea Sanyodo; sin el boost una cover e-hon con `alt` corto quedaba
  bajo el umbral 5 del ranking.
- Retrofit: limpié el `image_url` junk de los 41 items, corrí
  `backfill_metadata.py --only image_url` (38 recuperaron portada real
  vía detail-fetch; 3 Sanyodo quedaron sin portada porque su búsqueda
  `?s=ISBN` ya no devuelve resultados — el libro salió del catálogo) y
  `mirror_images.py` (38 portadas nuevas en el espejo local). MangaLine
  8/8 recuperados; Sanyodo 30/33.
- Tests: 291 passing (+6 — data-URI skip, theme/SVG reject, e-hon host).

Last updated previo: 2026-05-22 (Image storage Fase 1 — espejo local de
portadas) — Nueva estrategia para ser dueños de las imágenes de portada
en vez de hotlinkearlas (necesario para desplegar PandaWatch como
servicio multi-usuario). Cambios:
- Campo nuevo `image_local` en items.jsonl: filename del espejo local
  en `data/images/`. `image_url` queda como provenance + fallback.
- Módulo nuevo `scripts/image_store.py` — primitivas de descarga:
  nombre de archivo determinístico por hash del URL, validación por
  magic bytes (rechaza HTML de error), idempotencia (no re-descarga).
- `mirror_candidate_images()` en manga_watch.py orquesta la descarga
  paralela; conectada en las 3 rutas de escritura (source loop, wiki
  bootstrap, sitemap mining). On by default; flag nueva
  `--skip-image-download` para saltearla.
- `append_jsonl`: `image_local` es sticky (gotcha #25 nueva) — un
  re-scrape sin descarga no borra el espejo ya existente.
- Frontend (`web/index.html`): `coverSrc()` (local primero, image_url
  fallback) + `onCoverError()` (fallback en cascada → placeholder 📚).
  `build_web.py` y el dedup JS propagan `image_local`.
- Retrofit nuevo `scripts/retrofit/mirror_images.py` — completa la
  Fase 1: backfill del corpus histórico (descarga las portadas de los
  items previos a la Fase 1) + GC mark-and-sweep (saca de
  `data/images/` los archivos huérfanos a una cuarentena, o
  `--gc-delete`). Idempotente. Agregado al Panel de Control.
- Panel de Control: flags `--skip-image-download` (scrape) +
  script `mirror_images` agregados al registry.
- Nueva sección "Image storage" documenta Fase 1 (completa: scrape +
  retrofit) y Fase 2 (subir el espejo a un bucket Cloudflare R2 propio
  — planeada, reusando el patrón de PandaTrack pero con bucket separado).
- Tests: 285 passing (+6 — image_store + sticky append_jsonl).
- Backfill corrido sobre el corpus existente: **4342/4403 items
  (98.6%)** con espejo local en `data/images/` (4284 archivos — varios
  items comparten portada). El catálogo (items, series, ediciones) no
  cambió. Los 61 sin espejo NO son re-descargables (no son fallos
  transitorios): `image_url` mal extraída por el scraper —
  `data:` URI placeholder (MangaLine MX), ícono SVG de UI en vez de
  portada (Sanyodo) — o imágenes 404 muertas (Manga-Sanctuary). Quedan
  con `image_url` como fallback; arreglarlos requiere mejorar el
  extractor de imágenes, no es problema del espejo.
- Fix: race condition en `image_store.download_image` — dos threads
  bajando el MISMO `image_url` compartían el path `.tmp` (el segundo
  encontraba el tmp ya renombrado → FileNotFoundError). Ahora el tmp
  lleva un token uuid único por descarga. El retrofit además dedupea
  los targets por `image_url` (baja cada portada una sola vez).
- Fix: el retrofit usaba un User-Agent propio (`manga-watch-mirror/1.0`)
  que algunas fuentes (Manga-Sanctuary) responden con 404. Ahora usa el
  MISMO UA que el scraper (`manga-watch-personal/0.2`) — el corpus se
  scrapeó con él, así que las imágenes hay que pedirlas con el mismo.

Last updated previo: 2026-05-22 (noche, limpieza omnibus/Nueva-Edición) — El owner
reportó que los tomos "One Piece Omnibus Edition" de VIZ se habían colado al
catálogo pese a la regla (gotcha #18) de que un omnibus pelado no califica.
Causa raíz: `_GENERIC_X_EDITION_PATTERN` tenía su lista de exclusión de
palabras genéricas **solo en inglés**, pero el patrón matchea
`Edición/Edizione/Édition`. Resultado: **"Nueva Edición"** (= "New Edition",
reimpresión) disparaba el signal `lore_edition` y rescataba tomos/omnibus
normales por `is_collectible_edition`. Cambios:
- **Fix de raíz**: la exclusión ahora cubre los genéricos ES/IT/FR
  (`Nueva|Nuova|Nouvelle|Primera|Prima|Première|Última|Estándar|...`) — las
  mismas categorías que ya tenía la lista inglesa. Ver gotcha #24 nueva.
- **35 items eliminados** de `items.jsonl` (4436 → 4401) vía snippets
  quirúrgicos (backups `data/items.jsonl.pre-omnibus-cleanup-bak` +
  `.pre-generic-edition-bak`): 4 One Piece Omnibus VIZ + Ghost in the Shell
  + 6 omnibus Planeta "Nueva Edición 3 en 1" + Solanin Integral + 21
  reimpresiones "Nueva Edición" sueltas (primer barrido, 33) + 1 "Segunda
  Edición" + 1 título-junk "Pika Édition" (segundo barrido tras extender la
  exclusión a los otros genéricos, 2).
  NO se corrió `filter_collectible.py` completo a propósito: rechazaba 191
  items, incluyendo legítimos mal clasificados (ediciones "Colossal",
  "Limitada" cuyo qualifier se perdió al estandarizar el título). La
  eliminación usó `signal_types` GUARDADO como autoridad de "tiene qualifier
  premium" — así "17 Años Integral" (limited), "Death Note Integral"
  (box_set) y "Tokko Integral" (variant_cover) sobrevivieron correctamente.
- Tests: +2 (stoplist multilingüe + omnibus "Nueva Edición").
- Aclaración importante: NO hay un problema de `signal_types` caduco. Una
  medición inicial sugería ~200 filas con `lore_edition` "stale", pero fue
  un artefacto: se comparó `signal_types` contra el `title` estandarizado
  cuando en realidad se deriva de `title_original` (estable). La mayoría de
  esas filas son ediciones lore reales (Attack on Titan "Colossal Edition",
  Fullmetal Alchemist "Fullmetal Edition", Witch Hat Atelier "Grimoire
  Edition"). `signal_types` solo se desactualiza si cambia el código de
  detectores — y para eso está `rescore.py` en el pipeline nocturno. Ver la
  "Nota de mantenimiento" en gotcha #24.

Last updated previo: 2026-05-22 (noche, variant signal + preservación de campos
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
