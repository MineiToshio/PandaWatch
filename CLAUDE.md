# CLAUDE.md — Context for AI assistants working on PandaWatch

> Read this file first if you are an LLM agent (Claude, GPT, etc.) about
> to make changes to this repo. It captures the design intent, the
> conventions, and the gotchas that are not obvious from the code.
> The goal is that a new conversation can resume work with full context.

## ⚠️ Comunicación con el owner — SIEMPRE

- **Habla SIEMPRE en español NEUTRO de Latinoamérica** (tú/formas estándar:
  puedes, haz, muestra, déjame; NADA de voseo ni modismos de España). Nada de
  texto en inglés en las respuestas al owner (el contenido técnico del repo
  —código, docs, commits— sigue su idioma).
- **Cierre puntual y a nivel producto, no exhaustivo.** Al terminar, dar un
  resumen corto y de alto nivel: qué se hizo, para qué sirve y por qué. NO el
  paso a paso ni el detalle técnico, salvo que sea una decisión arquitectónica
  que valga la pena entender, o que el owner pida explicaciones explícitamente.
- Default: breve y entendible a nivel producto. La profundidad técnica es opt-in.

## ⚠️ Skills invocation policy — READ BEFORE RUNNING SKILLS

**NEVER invoke `/watch-standardize-catalog` or `/watch-enrich-series-aliases` automatically.**
These skills consume significant tokens (subagents × chunks × LLM calls) and the
owner (sergiomineiro) wants to decide consciously when to run them. After any
scrape or data ingestion, **leave items.jsonl in raw state** (without `standardized_at`).
Only invoke a skill when the user explicitly types the skill name or asks for
standardization/enrichment by name.

Same rule applies to all skills under `.claude/skills/`: only run them on
explicit request.

---

## ⚠️ Documentation policy — READ BEFORE TOUCHING CODE

**Todo cambio meaningful actualiza los docs relevantes en el mismo turn.** No
es opcional — el owner flageó repetidamente que los docs se desincronizaban.
Si el usuario te dice que un doc está stale, es una regresión de esta policy:
arreglalo en el mismo turn (no es feature request).

**Qué cuenta como "meaningful"** (cualquiera dispara la actualización): feature de
pipeline/filtro/fuente/wiki/retrofit/skill, cambio de schema, fuente agregada/
quitada o con purity/kind/selectors/enabled cambiado, corpus shift >2pp, nueva
dependencia/env var/CLI flag, feature de UI nueva o cambio de UX, endpoint nuevo,
script nuevo en el registry, componente/ruta/data-layer nuevo en web-next, decisión
de arquitectura, o un bug fix que cambia comportamiento documentado.

**Qué NO necesita docs** (estricto): bug fix que restaura comportamiento ya
documentado, tests de reglas ya documentadas, refactor puro sin cambio de
comportamiento (probado por la suite), typos.

**Dónde va cada cambio**:

| Tipo de cambio | Archivo |
|---|---|
| Gotcha nueva (parser quirk, anti-bot, false-positive, dedup edge case) | `docs/reference/gotchas.md` (+ bumpeá el número del heading) |
| Decisión de arquitectura, storage/cluster_key, corpus state | `docs/reference/architecture.md` (+ el gist en CLAUDE.md si cambia) |
| Convención de código nueva (filtros, backup/flush, registry) | `docs/reference/conventions.md` |
| Archivo/módulo/wiki/retrofit nuevo | `docs/reference/file-map.md` |
| Dashboard / serve.py / curación | `docs/reference/dashboard.md` |
| Imágenes (extractor, espejo, carrusel) | `docs/reference/images.md` |
| **Cambio en el FLUJO end-to-end o que impacta la BASE DE DATOS** (nueva etapa/paso del ciclo de vida del dato, nuevo proceso post-scrape, reordenamiento de etapas, campo nuevo en items.jsonl, nueva funcionalidad del workflow) | `docs/scraper/PIPELINE-WALKTHROUGH.md` (runbook completo — **mantener SIEMPRE sincronizado**) |
| Scraper — pipeline internals, data flow (deep dive) | `docs/scraper/ARCHITECTURE.md` |
| Scraper — agregar/mantener fuentes, recetas | `docs/scraper/SOURCES.md` |
| Scraper — roadmap, wikis activos, no-goals | `docs/scraper/PRD.md` |
| Scraper — retrofits / skills | `scripts/retrofit/README.md` / `.claude/skills/README.md` |
| Web HTML — features, UX | `docs/web-html/PRD.md` |
| Admin — Panel de Control | `docs/admin/README.md` |
| Next.js | `docs/web-next/{FRD,blueprints,work-orders}/` |
| Env var / dependencia nueva | `.env.example` + el doc del componente |

`CLAUDE.md` (este archivo) sólo lleva el núcleo: policies, orientación, el índice de
referencias y los gists de las 7 decisiones. Si tocás un gist, sincronizá el detalle
en `docs/reference/architecture.md` (y viceversa). El detalle nuevo va al doc de referencia,
NO a CLAUDE.md — mantenelo chico.

## What this project is

**PandaWatch** (repo: `MineiToshio/PandaWatch`, internamente `manga-watch`) es
un **tracker personal** que scrapea ~67 fuentes habilitadas (de 138 en
`sources.yml`) en 13 países y 6 idiomas (ES, EN, FR, IT, JP, PT-BR) buscando
**ediciones especiales físicas de manga**: limited editions, deluxe hardcovers,
box sets, slipcase, artbooks, kanzenban, light novels con bonus, etc.

**Single user.** Sin login ni multi-tenant. El owner (sergiomineiro) corre el
scraper periódicamente y navega resultados en una UI web local.

**Stack:**
- Python 3 (pipeline de scraping, filtros, extracción label/value)
- BeautifulSoup + requests + ThreadPoolExecutor (`--workers N`; sin Playwright por
  defecto — opt-in `--enable-js`, serializado por el worker thread; gotcha #12)
- HTML + Alpine.js + Tailwind CDN (UI estática) + app Next.js nueva en `web-next/`
- Storage: JSONL, 1 fila por producto con `sources[]` (decisión #1)
- Tests: pytest (~538 al último commit)

## 2 scripts canónicos: full vs delta

Hay dos scripts top-level que encadenan todo el pipeline. Operan sobre las
mismas fuentes y **ambos usan el MISMO parser de colecciones de listadomanga**
(`listadomanga_collections.py`); la única diferencia es el **discovery** de qué
colecciones parsear (decisión 2026-05-23, paridad delta/full 2026-06-06):

| Script | Listadomanga discovery | Frecuencia | Tiempo | Cuándo |
|---|---|---|---|---|
| `scripts/scrape_delta.sh` | `--coleccion-mode calendar`: ids con actividad en `calendario.php` (mes actual + 2 anteriores) → parsea esas colecciones completas (~500-600) | diaria / semanal | ~30-60 min | detectar novedades recientes |
| `scripts/scrape_full.sh` | `--coleccion-mode lista`: `lista.php` → ~3432 colecciones activas en orden alfabético | mensual / trimestral | ~2-4 horas | refresh completo del catálogo |

Ambos corren las mismas fases:
1. Scrape sources del YAML (`manga_watch.py` con `--workers 8`)
2. Wiki bootstraps (los wikis que aplican según modo)
3. Cleanup retrofits (rescore → filter_non_manga → filter_collectible →
   clean_titles → backfill_metadata)
4. Build web

`scripts/overnight_run.sh` queda como alias deprecated de `scrape_delta.sh`.

**Modelo simplificado para listadomanga**: ambos modos corren el parser de
colecciones (`listadomanga-collections`); `full = lista.php` (~3432), `delta =
calendar` (ids con actividad reciente, ~500-600). Antes el delta usaba el
calendario plano (`--bootstrap-wiki listadomanga`) que NO parseaba ediciones
especiales/cofres/variantes — ahora hay **paridad**: el delta captura la misma
riqueza que el full, acotado a lo reciente (P1, 2026-06-06). El módulo de
calendario plano (`wikis/listadomanga.py`) sigue disponible pero fuera del
pipeline canónico. `scrape_full` además hace mangavariant sitemap completo.
`listadomanga-blog` REMOVIDO del pipeline canónico (posts de noticias, 0 items
netos; módulo disponible para invocación manual). El resto de mejoras "full vs
delta" por-fuente quedan pendientes (por ahora la única diferencia es listadomanga).

## 📚 Documentos de referencia — cargar bajo demanda

CLAUDE.md es el núcleo (siempre inyectado). El detalle vive en `docs/reference/` y
se lee **sólo cuando vas a trabajar en ese tema** — así el contexto se mantiene
chico. ANTES de tocar código de un área, leé su doc:

| Vas a… | Leé primero |
|---|---|
| Tocar un parser / filtro / extractor / scoring / dedup | [docs/reference/gotchas.md](docs/reference/gotchas.md) (las 53 gotchas) |
| Cambiar storage, cluster_key, el pipeline, o entender el modelo de datos | [docs/reference/architecture.md](docs/reference/architecture.md) (pipeline + corpus state + las 7 decisiones) |
| Escribir/modificar un retrofit, fuente, wiki, o script del registry | [docs/reference/conventions.md](docs/reference/conventions.md) (filtros, backup/flush/nohup, registry, playbooks) |
| Ubicar un archivo o entender qué hace cada módulo | [docs/reference/file-map.md](docs/reference/file-map.md) |
| Tocar el dashboard HTML / serve.py / curación (feedback, edición, aprobación) | [docs/reference/dashboard.md](docs/reference/dashboard.md) |
| Tocar imágenes (extractor, espejo local, carrusel, portadas) | [docs/reference/images.md](docs/reference/images.md) |
| Entender / ejecutar el **proceso completo** para dejar el dato 100% listo (scrape → standardize → aliases → imágenes → rareza → traducción → slugs → feedback → aprobación → build), con runbooks por etapa | [docs/scraper/PIPELINE-WALKTHROUGH.md](docs/scraper/PIPELINE-WALKTHROUGH.md) |
| Tocar la ingestión de una **fuente específica** (proceso full/delta, problemas, runbook) | `docs/scraper/sources/<fuente>.md` — TODAS las fuentes activas tienen ficha; el índice está en [SOURCES.md](docs/scraper/SOURCES.md#índice-de-fichas-por-fuente). La más importante: [listadomanga.md](docs/scraper/sources/listadomanga.md). Para una fuente nueva, copiá [_TEMPLATE.md](docs/scraper/sources/_TEMPLATE.md) |

Las gotchas se referencian por número (#N) a lo largo del repo — ese número es
estable y vive en `docs/reference/gotchas.md`.

## Las 7 decisiones de diseño (gist) — detalle en architecture.md

Resumen de una línea; el **detalle completo + casos + invariantes** está en
[docs/reference/architecture.md](docs/reference/architecture.md). Antes de cualquier
cambio estructural, leé esa doc.

1. **Storage = JSONL, 1 fila por PRODUCTO con `sources[]`** (no por URL). El merge
   tiene una FUENTE ÚNICA: `merge_cluster()`/`consolidate_by_cluster()`/`source_entry()`
   en manga_watch.py — nunca reimplementar en otro lado.
2. **`is_likely_manga()` = cascada de 4 reglas en orden** (HARD → STRONG → extras →
   SOFT → default). El orden importa.
3. **Source purity `manga_only` vs `mixed`**: en mixed, sólo pasa lo que tiene STRONG
   manga hint (la comics blacklist aplica siempre).
4. **Agrupación multi-fuente por `cluster_key`** (tier-based: `edition:` > `isbn:` >
   `fuzzy:` > `url:`). Si cambiás la derivación → `backfill_cluster_key.py`.
5. **Live-fetch, no data embebida**: el dashboard hace `fetch()` de items.jsonl;
   correr siempre `serve.py` (no `file://`).
6. **Concurrencia con ThreadPoolExecutor, NO asyncio** (`--workers` + `--per-host-limit`
   + Playwright worker thread dedicado, gotcha #12).
7. **Pipeline canónico + observabilidad**: scrape_delta/full encadenan todo; no comandos
   ad-hoc. `source_health.py` clasifica fuentes desde los logs.

## Quick sanity check before committing

```bash
.venv/bin/python -m pytest tests/test_extraction.py -q          # debe quedar verde
.venv/bin/python scripts/retrofit/filter_non_manga.py --dry-run # 0 rechazos si los patterns son estables
# Según lo que tocaste:
#   filtros        → filter_non_manga.py [+ filter_collectible.py si is_collectible_edition]
#   signals/score  → rescore.py
#   clean_title    → clean_titles.py --dry-run
#   extractores    → backfill_metadata.py --dry-run
#   derive_cluster_key → backfill_cluster_key.py --dry-run
```

## Next things on the radar (not committed to)

Diferidos explícitamente:

- **SQLite migration** — pospuesto hasta multi-user/deploy (triggers + plan en ARCHITECTURE.md).
- **Censored cover modals** (ListadoManga "accept adult content") — el scraper ve el
  placeholder; requeriría Playwright o cookie injection per-source.
- **Price history** — el upsert pisa el precio viejo. Para histórico haría falta un
  `events.jsonl` separado o SQLite.
- **async/httpx migration** — ThreadPoolExecutor + GIL alcanza al scale actual; sólo
  revisitar con ~500+ fuentes o si se necesita cancelación per-request.
- **Enrichment pass para items de referencia** — items de Mangavariant/wikis tienen
  serie/volumen/publisher/país pero no precio ni URL de tienda. Script aparte
  (`enrich_references.py`) que busque la URL de tienda y la agregue a `sources[]`. NO es
  filtro upstream (los de referencia son válidos igual). Ver "URL como referencia".
- **Image storage Fase 2** — subir el espejo local a un bucket Cloudflare R2 propio al
  desplegar. Ver sección "Image storage".

## Claude-in-Chrome MCP — Context Rules

These rules apply whenever any `mcp__claude-in-chrome__*` tool is used.
The Chrome extension MCP tools can return very large DOM/HTML payloads
that fill the context window in a single call. Follow these constraints
strictly to prevent autocompact thrashing.

### Before calling any Claude-in-Chrome tool
- Check current context usage. If it is above 40%, run /compact first
  with the instruction: "keep only the current task goal and last tool
  result, drop everything else."

### Tab and page discovery
- Use `tabs_context_mcp` only to get a tab ID. Do not read or process
  its full output beyond the numeric ID and URL.
- Never request full page state unless the user explicitly asks for it.

### Content extraction
- When reading page content, always target a specific CSS selector or
  element ID. Never extract the full <main>, <body>, or root DOM.
- If you need page text, prefer get_page_text over DOM snapshots.
- Limit any single tool response to what fits in ~5,000 tokens. If more
  is needed, read in chunks across multiple turns.

### Screenshots
- Take a screenshot only when the user asks to see the page visually.
  Do not take screenshots as a default verification step.

### Cookie banners and popups
- Dismiss cookie notices and popups in a single find + javascript_tool
  call. Do not use screenshot-scroll sequences for this.

### On thrashing error
- If the error "Autocompact is thrashing" appears, stop immediately.
  Do not retry the same tool call.
  Run: /compact keep only the current task goal, drop all tool outputs
  Then resume with a more targeted approach (smaller selector, chunk
  reading, or a subagent).

---

Last updated: 2026-06-05. CLAUDE.md se compactó de ~5700 a ~190 líneas: el changelog
histórico narrativo se removió (vive en `git log -- CLAUDE.md`) y el detalle de
referencia (file map, las 7 decisiones, las 53 gotchas, convenciones, dashboard,
imágenes) se movió a `docs/reference/`, cargado bajo demanda vía el índice de arriba.
Al cerrar una tarea meaningful: actualizá el doc de referencia que corresponda (NO
metas detalle nuevo en CLAUDE.md — mantenelo chico), sincronizá el gist si aplica,
y bumpeá esta fecha. Nada de changelog narrativo acá.
