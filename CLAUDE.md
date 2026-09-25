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

**ÚNICA excepción (autorizada por el owner 2026-08-24)**: la tarea programada
`pandawatch-delta-diario` (rutina diaria de Claude Code, 11:00 AM; vive en
`~/.claude/scheduled-tasks/pandawatch-delta-diario/SKILL.md`) SÍ invoca
`/watch-standardize-catalog` y `/watch-enrich-series-aliases` como parte de su
corrida, con **freno de seguridad**: si hay >300 items crudos pendientes NO
estandariza y flaggea al owner. Fuera de esa rutina, la política de arriba
sigue intacta. Detalle en PIPELINE-WALKTHROUGH → "Delta diario (programación)".

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

**Regla de FUENTES (dura)**: cada vez que se modifica o se descubre algo de CUALQUIER
fuente (un bug, un quirk, un cambio de parser/selectores, un problema, un fix, un
cambio de cobertura), se actualiza su ficha `docs/scraper/sources/<fuente>.md` en el
MISMO turn. Si la fuente aún no tiene ficha, se crea desde `_TEMPLATE.md`. No es opcional.

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
| **Cualquier cambio o hallazgo en una FUENTE específica** (parser/selectores/quirk/problema/fix/comportamiento/cobertura/anti-bot de esa fuente) | `docs/scraper/sources/<fuente>.md` — la ficha de ESA fuente, **SIEMPRE en el mismo turn** (si no existe, créala desde `_TEMPLATE.md`). Regla dura. |
| Scraper — roadmap, wikis activos, no-goals | `docs/scraper/PRD.md` |
| Scraper — retrofits / skills | `scripts/retrofit/README.md` / `.claude/skills/README.md` |
| Web HTML — features, UX | `docs/web-html/PRD.md` |
| Admin — Panel de Control | `docs/admin/README.md` |
| Next.js | `docs/web-next/{FRD,blueprints,work-orders}/` |
| Env var / dependencia nueva | `.env.example` + el doc del componente |
| Cambio al proceso de implementación con IA (vías, verificación, skills de proceso) | `docs/process/AI-WORKFLOW.md` |

`CLAUDE.md` (este archivo) sólo lleva el núcleo: policies, orientación, el índice de
referencias y los gists de las 7 decisiones. Si tocás un gist, sincronizá el detalle
en `docs/reference/architecture.md` (y viceversa). El detalle nuevo va al doc de referencia,
NO a CLAUDE.md — mantenelo chico.

## What this project is

**PandaWatch** (repo: `MineiToshio/PandaWatch`, internamente `manga-watch`) es
un **tracker personal** que scrapea **55 fuentes habilitadas** (de 152 en
`sources.yml`; 16 podadas 2026-06-12 por 0 items netos + 2 deshabilitadas
2026-08-23 por host caído — ES/MX MangaLine + 1 deshabilitada 2026-09-02 por
redundante: la entrada YAML de Mangavariant, cuya ingesta real es el módulo
wiki + 1 deshabilitada 2026-09-07 por el mismo motivo: la entrada HTML de Meian,
que pasó a ingesta por API — gotcha #197) + 27 módulos wiki (21 activos mediante `ingestion_policy.yml`), en 20 países y
14 idiomas (ES, EN, FR, IT, JP, PT-BR, DE, PL, KO, ZH, VI, TH, TR, CS) buscando
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
- Tests: pytest (~1028 al último commit)

## Integridad de ingestión — revisión 2026-09-24

Cache/corpus reconciliados antes del delta; upsert reconoce URLs secundarias;
lectura estricta evita pérdida por JSONL corrupto. Full sigue páginas descubiertas
con `--full-catalog`; Meian API corre en ambos modos; Mangavariant delta revisa
modificaciones de siete días. Fallos/limitaciones ya no salen con éxito silencioso.
Informe y límites actuales: [auditoría de ingestión](docs/scraper/audits/2026-09-24-ingestion.md).

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
netos; módulo disponible para invocación manual). Desde 2026-09-24, full además sigue las páginas de listados con
`--full-catalog` (delta conserva límites), y Mangavariant delta revisa URLs nuevas
y modificadas en siete días. Meian API corre en ambos modos. Ver la auditoría de
ingestión para límites y fuentes bloqueadas.

## 📚 Documentos de referencia — cargar bajo demanda

CLAUDE.md es el núcleo (siempre inyectado). El detalle vive en `docs/reference/` y
se lee **sólo cuando vas a trabajar en ese tema** — así el contexto se mantiene
chico. ANTES de tocar código de un área, leé su doc:

| Vas a… | Leé primero |
|---|---|
| **Implementar cualquier feature o fix** (elegir vía A/B/C, plan mode, verificación, eficiencia de tokens; skills de proceso `/feature-spec`, `/ship-check`, `/product-pulse`) | [docs/process/AI-WORKFLOW.md](docs/process/AI-WORKFLOW.md) |
| **Escribir, transformar, filtrar o mostrar el `title` de un item** (parser, skill, retrofit de títulos, filtro non-manga, tarjeta/detalle de UI) | [docs/reference/title-policy.md](docs/reference/title-policy.md) — **léelo ANTES**; el title es el nombre OFICIAL, no se traduce/renombra |
| Tocar un parser / filtro / extractor / scoring / dedup | [docs/reference/gotchas.md](docs/reference/gotchas.md) (las 223 gotchas) |
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
   en manga_watch.py — nunca reimplementar en otro lado. Escritura vía
   `append_jsonl`/`write_items_atomic` (tmp+fsync+`os.replace`); el scraper flushea
   por-fuente a un spool append-only que el `append_jsonl` final absorbe en una sola
   pasada (2026-07-08).
2. **`is_likely_manga()` = cascada de 4 reglas en orden** (HARD → STRONG → extras →
   SOFT → default). El orden importa.
3. **Source purity `manga_only` vs `mixed`**: en mixed, sólo pasa lo que tiene STRONG
   manga hint (la comics blacklist aplica siempre).
4. **Agrupación multi-fuente por `cluster_key`** (tier-based: `lmc:` > `edition:` >
   `fuzzy:` > `url:`; `isbn:` ELIMINADO 2026-07-07 — el ISBN pelado repite entre
   ediciones/series distintas en manga, fusionarlo era destructivo). Si cambiás la
   derivación → `backfill_cluster_key.py`.
5. **Live-fetch, no data embebida**: el dashboard hace `fetch()` de items.jsonl;
   correr siempre `serve.py` (no `file://`).
6. **Concurrencia con ThreadPoolExecutor, NO asyncio** (`--workers` + `--per-host-limit`
   + Playwright worker thread dedicado, gotcha #12) + lock inter-proceso (`flock`) sobre
   `items.jsonl` entre scraper/dashboard/Panel (2026-07-08).
7. **Pipeline canónico + observabilidad**: scrape_delta/full encadenan todo; no comandos
   ad-hoc. `source_health.py` clasifica fuentes desde los logs.

Además, **política de títulos (2026-06-12)**: `title` = nombre OFICIAL con que la
editorial publica el producto — NUNCA se traduce, NUNCA se renombra a la serie canónica,
NUNCA se le inyecta tipo de edición. La serie reconocible va en `series_display`, el tipo
como badge en las UIs, y la búsqueda resuelve aliases (`data/series_aliases.json`).
Detalle en architecture.md → "Política de títulos"; consecuencia en filtros: gotcha #92.

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
- **Image storage Fase 2** — subir el espejo local (ya estandarizado: AVIF Q60 ≤1600px,
  ~1.64 GB) a un bucket Cloudflare R2 propio al desplegar. La pre-optimización ya está hecha
  (entra en el free tier de 10 GB; pre-optimizar es obligatorio porque R2 no transforma). Ver
  `docs/reference/images.md` → "Normalización / estandarización al ingresar".

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

Last updated: 2026-09-25 (delta diario **con dos frenos activados**. Antes de correr nada, la
línea base mostró el corpus en **18 542** items (ayer cerró en 14 608) y **3961 crudos**: una
**ingesta ad-hoc de madrugada** (19:34→00:09 local) metió **3934 items** por invocación directa
de los módulos wiki, **fuera del pipeline canónico** — sin carpeta de log, sin los retrofits de
cleanup y sin estandarizar. Calidad del lote verificada y BUENA (los 850 de Manga-Sanctuary que
parecían tomos sueltos resultaron todos Kanzenban/Coffret/Deluxe/Artbook con señales y score
30-92; *Chainsaw Man 23 Collector* score 92). **PASO 2 disparó el freno**: 3902 crudos contra un
umbral de 300 → **no se estandarizó**, decisión del owner. **PASO 4 (aliases) se saltó por
decisión propia**, documentada: la cola pasó de 222 a **1695 filas / 1650 series únicas**, pero
**84 % de esas keys no corresponde a ningún item vivo** del corpus (#156 a gran escala) y las que
sí son crudas — o sea descriptores de edición y basura (`akira-graphitti-limited`,
`anteprima-396-con-sovracover`, `2-cd`). Correr el skill habría escrito ~1650 canónicas malas y
PERMANENTES en el YAML; la estandarización es justamente lo que arregla el `series_key`, y está
frenada. Delta: 1 h 31 m, corpus 18 542 → **18 479**, gate `validate_corpus` **verde** (0
violaciones duras), `set_rarity` sin cambios y build OK. **23 items realmente nuevos** (medidos
por URL normalizada contra el backup pre-scrape, método de #192; `detected_at` habría dicho 18).
Lo accionable: **2 preórdenes `rare`** — *彼方から* (From Far Away) **小冊子付き愛蔵版 vols. 3 y 4**,
aizōban con folleto de Hakusensha, **salida 2026-11-05**, score 284 — más 3 deluxe hardcover
nuevos de Dark Horse Direct (*Appleseed Companion*, *Oldboy* Book One y Two). Del lote de
madrugada, 26 items `ultra_rare`/`super_rare`, entre ellos los **5 tomos de *Akira* Graphitti
limited** y 10 variantes italianas de tirada corta (600-2500 copias) de Manga Dreams. Hallazgo
principal, gotcha **#223**: desde la auditoría del 09-24, `return 1 if session._ingestion_issues
else 0` (`manga_watch.py:9886`) hace que **`rc=1` en un wiki ya NO signifique "la fuente falló"**
sino "hubo al menos una incidencia" — de los 5 wikis en rojo hoy, **2 ingirieron bien** (`viz` 16
candidatos con un solo 429; `kodansha-us` 3 items con `repeated search page=2`). Es el
comportamiento deseado —cierra la familia de fallos silenciosos tipo #208— pero **el conteo de
"pasos en error" dejó de ser comparable con los runs previos**: pasar de 0 a 7 no es una
regresión. Fuentes: Seven Seas 2º día de challenge Cloudflare (0 books), SocialAnime **6º día en
0** (#211, ahora ruidoso), `storefront:spp-tw` agotó reintentos por primera vez mientras los
otros 3 storefronts del mismo paso corrían bien. Segundo hallazgo transversal: **LANG_ENUM 229**
(`English` en vez de `Inglés`), del que **157 entraron en la ingesta de madrugada** — VIZ 148 y
Kinokuniya 47 son el 85 %; es warn, no frena el gate, pero el idioma es filtro de la UI. Nada
aplicado sobre fuentes ni configuración: todo documentado en las fichas (sevenseas, kodansha-usa,
viz, socialanime, storefronts-api, kinokuniya) y en #223. Sin commit.)
Update previo, 2026-09-24 (delta diario: corpus 14 600 → **14 608**; 36 crudos estandarizados
—0 Tier 1, 0 Tier 2, 36 Tier 3—, 0 perdidos; aliases: 8 candidatas con ≥2 items y **8 skips
justificados, 0 cambios al YAML**; cola podada 507 → 88 conservando las 88 de curación; gate
verde, 726 tests de extracción, build OK, `backfill_metadata --only image_url` completó (1422 s)
y el run cerró con **0 pasos en error** en 1 h 08 m. **9 items realmente nuevos**; lo más
accionable es un **特裝版 de *Hallelujah Baby* vol. 8** (Kadokawa Taiwán, `rare`) y un **box set
de 8 tomos de *Xóm Om Xòm*** (Kim Đồng, Vietnam); ninguno salió super_rare o superior y **ninguno
trae fecha de salida**, así que no hay preórdenes accionables hoy. Hallazgo principal, gotcha
**#215**: el módulo wiki de **Kinokuniya USA emite sólo título + ISBN** — medido sobre sus 47
items del corpus, **96 % sin `publisher`**, **100 % sin `release_date`**, **83 % sin `volume`** —
y como `publisher` es componente del `edition_key`, cada item acuña `…-unknown-…`: **los 4 items
nuevos de hoy entraron así**. O sea **Kinokuniya no sufre #210, lo produce**. Medición transversal
del mismo día: **1672 items** con `-unknown-` en el `edition_key` y **204 grupos partidos** (misma
serie+volumen+tipo+país en ≥2 `edition_key`) contra los **110** anotados el 09-17 — el pool de
items está estable pero **la fragmentación casi se duplicó en una semana**, así que #210 está en
crecimiento activo, no latente. Ningún gate lo ve (`PUBMIX` no dispara porque no hay mezcla
*dentro* de una edición, `EKPREFIX` y `SLUGUNIQ` aprueban): lo que está mal es la PARTICIÓN, el
punto ciego de #210/#213/#214. Fix propuesto y barato: fetch-details de `/bw/<isbn>` (1 request ×
47 items). Instancia fresca de #210 capturada en vivo: el MISMO artbook *The Art of PRAGMATA -
Lunar Echoes*, con **título byte-idéntico**, quedó en dos filas (`-kadokawa-artbook-jp` vs
`-unknown-artbook-jp`) porque Rakuten no expone la editorial — y llegó a la cola de aliases
disfrazado de "serie nueva con 2 items". **#212 ampliada y corregida**: los 2 items de
`xxxHOLiC・戻` volvieron con `series_key` **`xxxholic` en x LATINAS**, o sea el arreglo de
homoglifos **no habría resuelto este caso** — el parser perdió el `・戻`, que es el marcador de la
secuela; y el YAML tiene **dos canónicas para la misma obra** donde la de nombre correcto
(`xxxholic-rei`) **no tiene un solo alias**, así que es una entrada MUERTA e inalcanzable para el
resolver. El lint sale verde porque no colisionan al normalizar. La trampa sigue: el audit propone
🟢 0.80 y aceptarlo fusionaría la serie madre de CLAMP con su secuela. Fuentes: **#208 en su 8º
día y ESCALADO** — el listado principal de Planet Manga pasó de yield parcial (47/75 ayer) a
**SKIP TOTAL** hoy, con los 3 listados IT caídos a la vez en ~2.3 KB; **19 source-runs saltados,
todos de Panini** (3 listados IT + 16 searches ES) y ninguna otra fuente afectada. **#199 lo tapó
por 9º día**: el reporte mostró 4 filas de 19, con las 16 searches colapsadas en una fila
fantasma. **#211 SocialAnime 5º día en 0** (mediana 641, 403 en ambos tipos): con 5 días idénticos
queda descartado el fallo transitorio, es la configuración actual del sitio — pero es un fallo
RUIDOSO (WARN + 🔴), el caso contrario a Panini. **#200 por 5º día**: 7 items bajo
`numeros-en-preparacion-cofre` (5, con TRES editoriales distintas) y `numeros-editados-cofre` (2).
Funside aporta 2 de las 8 candidatas de aliases y **8 de los 13 `standardize_exhausted`** — el
escape hatch de #191 está conteniendo el coste. Nada aplicado sobre fuentes ni configuración:
todo documentado en las fichas. Sin commit.)
Update previo, 2026-09-23 (delta diario: corpus 14 589 → **14 600**; 34 crudos estandarizados
—1 Tier 1, 0 Tier 2, 33 Tier 3—, 0 perdidos; aliases: 8 candidatas con ≥2 items y **8 skips
justificados, 0 cambios al YAML**; cola podada 520 → 86 conservando las 86 de curación; gate
verde, build OK, `backfill_metadata --only image_url` completó (871 s) y el run cerró con **0
pasos en error** en 59 m 54 s. **11 items realmente nuevos** (22 con `detected_at` de hoy — la
brecha de #192/#209 sigue); lo más accionable es un **Trigun Deluxe Edition HC** de Dark Horse,
una **edición limitada con póster** de *Days with My Stepsister* vol. 7 (Kim Đồng, Vietnam), el
tapa dura de *ABARA* (J.P.Fantastica, Polonia) y 3 preórdenes con fecha futura (2 artbooks JP —
*The Art of PRAGMATA* 12-02 y *鍛冶屋ソレイユ画集 日廻* 11-17— más *Hotel Inhumans* #07 variant de
Dynit, 10-20). Ninguno salió `rare` o superior. Hallazgo principal, gotcha **#214**: el **rótulo
de STOCK de Mangarden.pl** (`OSTATNIE` = últimas unidades, `II Gatunek` = segunda calidad) **y el
`tom NN` entran al `edition_key`**, y parten UNA edición en N ediciones de un solo tomo. Medido
en todo el corpus: **130 items** de J.P.Fantastica con `-tom-NN-` en el `edition_key`, **128 de
ellos en una edición de UN SOLO item**; la edición deluxe de *Ranma ½* está partida en **16**
ediciones, *Inuyasha* 15, *Urusei Yatsura* 13, *Yu Yu Hakusho* 12 — **29 familias / 156
`edition_key`** que deberían ser 29. Lo grave no es la fragmentación sino que **el rótulo es
MUTABLE**: describe el inventario de hoy, no el producto, así que cuando la tienda lo cambia el
mismo tomo cambia de `edition_key` → de `slug` → de IDENTIDAD y nace un duplicado (ya pasa dentro
de *Ranma ½*: el tomo 06 quedó en `ii-gatunek` y sus hermanos en `ostatnie`; `ostatnie` aparece en
94 `edition_key`). **Esto da la causa de mecanismo de los 5 duplicados `preorder → ostatnie`
anotados el 09-15**, que se habían registrado como síntoma suelto. Ningún gate lo ve: `EKPREFIX`
pasa (el prefijo sí arranca con el `series_key`), `DUPVOL` no dispara (cada edición tiene un solo
tomo, no hay volumen repetido *dentro* de una edición) y `SLUGUNIQ`/`SLUGFMT` aprueban — cada fila
es válida por separado y lo que está mal es la PARTICIÓN, que ninguna invariante mira: el mismo
punto ciego de #210 y #213. **No aplicado porque cambia slugs.** Fuentes: **#208 en su 7º día** —
**18 source-runs** de Panini saltados por la Queue-it (16 searches ES + 2 listados IT) y, lo más
serio, el **listado principal de Planet Manga rindió 47 en 4 págs contra mediana 75** (79 ayer)
**sin que el reporte lo marcara**: yield parcial silencioso que además baja la mediana y degrada
el propio baseline. **#199 lo volvió a tapar**: el reporte mostró 3 skips de 18, con las 16
searches colapsadas en una fila fantasma y `Runs 0`. **#211 SocialAnime 4º día en 0** (mediana
641), lo que lo consolida como estado estable y no incidente. Funside es el 70% de los crudos (19
de 27) y **10 de los 14 `standardize_exhausted`** (cómic occidental italiano fuera del blacklist),
pero también el 45% de los items nuevos — el blacklist por franquicia sigue siendo la herramienta
proporcionada. Los 3 artículos de merchandising de KADOKAWA (缶バッジ/ブロマイド) volvieron a
agotar sus 3 intentos. Delcourt 0 y Dark Horse `variant` 0 / `limited edition` 6 son mediana
obsoleta ya cerrada. Nada aplicado sobre fuentes ni configuración. Sin commit.)
Update previo, 2026-09-21 (delta diario: corpus 14 582 → **14 589**; 33 crudos estandarizados
—2 Tier 1, 2 Tier 2, 29 Tier 3—, 0 perdidos; aliases: 6 candidatas con ≥2 items y **6 skips
justificados, 0 cambios al YAML**; cola podada 503 → 82 conservando las 82 de curación (el dedup
del fix #198 quitó 0 filas, o sea ya no entran duplicados); gate verde, 726 tests de extracción + **2597 de la suite completa**, build OK,
`backfill_metadata --only image_url` completó (925 s) y el run cerró con **0 pasos en error** en
1 h 01 m. **7 items realmente nuevos** (19 con `detected_at` de hoy — la brecha sigue siendo
#192); el más accionable es un **BOX SET de 8 tomos con 特典 de 男一匹ガキ大将** (Rakuten,
2026-11-19, preorden) y hay 2 `rare` (set limitado coreano de *Merry Marbling* y un 特装版 de
*Sengoku Jieitai* con bonus NFT). Hallazgo principal, gotcha **#213**: el **`slug` de un item
crudo se fosiliza** — la estandarización le asigna el `series_key`/`edition_key` correcto pero
`generate_slugs.py` corre `--only-missing` y nunca lo reescribe. Medido en todo el corpus: sólo
**4 de 14 563 items** tienen slug desalineado del `edition_key`, **y 3 son de hoy**, o sea el
defecto nace en la ingesta y no se corrige jamás (`nft-unknown-special-jp` en vez de
`sengoku-jieitai-unknown-special-jp`; `box-001-008-…`; `isbn-9791141116118`). Pasa desapercibido
porque `SLUGUNIQ`/`SLUGFMT` lo aprueban y `EDSLUG` sólo mira el TIPO de edición, no el prefijo de
serie — y el slug es la IDENTIDAD PÚBLICA del item. Fix propuesto en dos pasos (invariante `SLUGEK`
en warn + regenerar sólo lo que marque), barato hoy justamente porque son 4 items; **no aplicado
porque cambia slugs** (mismo riesgo que el retrofit de ISBN pendiente). Fuentes: **#208 escaló a
los LISTADOS PRINCIPALES** — 19 source-runs perdidos y por primera vez cayeron `manga.html` de
`panini.es` y **los dos sublistados IT de variant/cofanetti** (justo las categorías de las que
este proyecto se alimenta) mientras el listado principal de Planet Manga rindió 79 (> mediana 75);
verificado en vivo 302 → `panini.queue-it.net` con `e=paninies` y `e=paniniitaly` +
`kupver=magento2_1.3.5`, o sea Queue-it configurada a nivel plataforma y `--enable-js` inútil.
**#211 SocialAnime 2º día en 0** con la sonda re-corrida hoy (403 + `cf-mitigated: challenge`),
lo que **descarta la hipótesis de "esperar un día"** que sí había funcionado con Mangavariant.
**#212 ampliada**: el YAML tiene **DOS canónicas para la misma obra** (`bd-holic` y
`xxxholic-rei`) y el lint no las ve porque no colisionan al normalizar. **#200** volvió como las
2 candidatas de MÁS impacto del día (7 items, 5 colecciones, 3 editoriales bajo "Números en
preparación/editados"). Lead de Manga-Sanctuary reforzado: los 2 items FR nuevos son collectors
exclusivos de CADENA (Comptoir du Rêve, Momie) y el discriminante está en el slug de la URL, no
en el título. Delcourt 0 y Dark Horse `variant` 0 / `limited edition` 6 son mediana obsoleta ya
cerrada. Funside sigue siendo el 69% de los crudos (18 de 26). Nada aplicado sobre fuentes ni
configuración. Sin commit.)
Update previo, 2026-09-20 (delta diario: corpus 14 576 → **14 582**; 36 crudos estandarizados
—1 Tier 1, 2 Tier 2, 33 Tier 3—, 0 perdidos; aliases: 7 candidatas con ≥2 items, 1 canónica nueva
(`happiness`, confirmada por Anilist: única de las 6 homónimas con 10 tomos y FINISHED, que casa
con el tailandés "เล่ม 10 (จบ)") y 6 skips justificados; cola podada 498 → 79 conservando las 79
de curación; gate verde, 752 tests, build OK, `backfill_metadata --only image_url` completó
(866 s) y el run cerró con **0 pasos en error**. **5 items realmente nuevos** (medidos por URL
normalizada vs el backup pre-scrape, no por `detected_at` — método de #192); el más accionable
sale en 2 días (*Witch Hat Atelier: Grimoire Edition 2*, Kodansha USA, 2026-09-22). Hallazgo
principal, gotcha **#211**: **SocialAnime activó el Managed Challenge de Cloudflare** y la fuente
cayó de una mediana de 641 items a **0** — 403 en la primera página de los dos tipos, verificado
en vivo con `cf-mitigated: challenge` + "Just a moment..." de Turnstile contra el endpoint, el
endpoint con `Referer` y la **home** del sitio, así que no es el UA ni un rate-limit y no hay ruta
de fallback; `--enable-js` NO alcanza (Turnstile hay que resolverlo, no sólo ejecutar JS). A
diferencia de la Queue-it de Panini (#208), este fallo es **ruidoso**: WARN 403, 0 items y 🔴 en
el reporte de salud — el mejor caso. Segundo hallazgo, **#212**: un alias escrito con `×××`
(U+00D7) NO matchea el título real con `xxx` latinas, así que `xxxHOLiC・戻` de Rakuten/Sumikko no
resuelve contra su canónica —que además vive bajo la key corrupta **`bd-holic`**, invisible para
quien audite el YAML buscando "holic"—; el fix general es un mapa de homoglifos en
`_normalize`, y la trampa a evitar es aliasear `xxxholic` pelado, que fusionaría
irreversiblemente la serie madre de CLAMP con su secuela. Fuentes: Queue-it de Panini 5º día
(#208, las 2 entradas IT + 1 search ES, con el listado principal de Planet Manga sano — sigue
siendo por-request); **#200 medida en la cola de aliases** (`numeros-en-preparacion-cofre` agrupa
5 items de TRES editoriales distintas bajo el texto del `<h2>`); los 3 artículos de merchandising
de KADOKAWA (`缶バッジ`/`ブロマイド`) llegaron a `standardize_attempts=3` y **escalaron solos a
curación**, validando el escape hatch de #191 pero tras gastar 3 corridas de Tier 3. Las otras 3
yield regressions (Delcourt 0/1, Dark Horse `variant` 0/2, `limited edition` 6/15) son mediana
obsoleta ya diagnosticada. Nada aplicado sobre fuentes ni configuración. Sin commit.)
Update previo, 2026-09-19 (delta diario: corpus 14 571 → **14 576**; 38 crudos estandarizados —0 Tier 1, 1 Tier 2, 37 Tier 3—, 0 perdidos; 1 canónica nueva de aliases (`kamen-rider`), 7 skips; cola podada 491 → 77 conservando las 77 de curación; gate verde, 752 tests, build OK; 0 pasos en error. **4 items realmente nuevos** (18 con `detected_at` de hoy). Hallazgos documentados en fichas, nada aplicado: KADOKAWA Store con sala de espera propia (503, ambas entradas), Queue-it de Panini 4º día (#208: ahora trunca `Variant ed Esclusive` y `Collezione e Cofanetti` a 2 págs), Kana sin `title_selector` → título "Prochainement". Sin commit.)
Update previo, 2026-09-18 (delta diario: corpus 14 552 → **14 571**; 48 crudos estandarizados —3 Tier 1, 45 Tier 3—, 0 perdidos; 1 canónica nueva de aliases (`trouble-is-my-business`) y 8 skips justificados; cola podada 517 → 75 conservando las 75 filas de curación; gate verde, 752 tests, build OK; 0 pasos en error. **18 items realmente nuevos** (14 manga estandarizados + 4 non-manga en curación). Hallazgos documentados en fichas, nada aplicado: Queue-it de Panini 3er día (#208), merchandising JP `缶バッジ`/`ブロマイド` fuera del gate (jp-kadokawa), coma final en `editore` de SocialAnime (28 items), Funside re-lista 11 cómics occidentales con `standardize_attempts` reseteado (#202). Sin commit.)
Update previo, 2026-09-17 (delta diario: corpus 14 539 → **14 552**; 38 crudos
estandarizados —0 Tier 1, 1 Tier 2, 37 Tier 3—, 0 perdidos; aliases: sólo 7 candidatas con
≥2 items, 1 canónica nueva (`lingling-zongzong-paibudao`) y 6 skips justificados; cola podada
496 → 69 conservando las 69 filas de curación; gate verde, 752 tests, build OK;
`backfill_metadata --only image_url` COMPLETÓ por 2ª corrida seguida (1019 s) y el run cerró
con **0 pasos en error**. **13 items realmente nuevos** (no 24: el delta neto de líneas no
mide novedades). Dos hallazgos de MECANISMO, ninguno aplicado —decisión del owner—:
**#209** el índice de upsert de `append_jsonl` indexa SÓLO la `url` top-level y **ignora las
1545 URLs de `sources[]`**, así que cuando una fuente secundaria re-lista un producto
multi-fuente nace una fila DUPLICADA que se va a **Tier 3 —la ruta más cara del LLM—** y recién
después se fusiona: 9 de las 37 llamadas Tier 3 del día fueron para re-derivar metadata que el
corpus ya tenía (verificado end-to-end: los duplicados desaparecieron tras el merge, corpus
14 563 → 14 552). **Esto CORRIGE el diagnóstico de #192**: el `l-id` posicional de Rakuten NO
es la causa —está en `TRACKING_PARAMS` desde 2026-05-22 y se strippea bien—, sólo es lo que
hace visible el bug. **#210** un `publisher` vacío parte una edición en dos (`…-unknown-…` vs
`…-<editorial>-…`): el mismo `xxxHOLiC・戻 6 特装版` quedó en dos filas, y hay **110 grupos
partidos** (misma serie+volumen+tipo+país) sobre 1662 items con `-unknown-` en el
`edition_key`; `validate_corpus` no lo ve porque ambas filas son válidas. Fuentes: **gotcha
#208 escalada y medida** — la cola Queue-it de Panini alcanzó el listado principal de Planet
Manga (16 vs mediana 75, **paginación truncada a 2 págs**, 10/10 requests encolados en vivo);
su modo de fallo peligroso es que **no da error ni skip: da yield parcial silencioso** que
corrompe la mediana del baseline. Los 17 skips reales volvieron a colapsarse en 2 filas
fantasma por **#199**. Las otras 4 "yield regressions" son **mediana obsoleta verificada, no
averías**: Dark Horse `limited edition`/`exclusive` (3 y 2, con las 5 páginas recorridas),
`hardcover` (12), Milky Way `deluxe` (6 por 4ª corrida igual) y Delcourt (0 con la página sana
en 314 KB — sus 10 "deluxe" son un banner de 2022 repetido). Dato positivo: la cola de
curación mostró **462 `series_key` únicas de 491 filas (6% de duplicación vs 82% histórico)**,
o sea el fix #157/#198 sigue conteniendo, y los **7 `standardize_exhausted`** confirman que el
escape hatch de #191 dispara (todos cómic occidental italiano de Funside, que sigue siendo la
fuente #1 de ruido: 14 de los 17 veredictos `is_manga=false` del día). Nada aplicado sobre
fuentes ni configuración: todo documentado en las fichas. Sin commit.)
Update previo, 2026-09-16 (delta diario: corpus 14 533 → **14 539**; 36 crudos
estandarizados —0 Tier 1, 1 Tier 2, 35 Tier 3—, 1 canónica nueva de aliases
(`panguan-the-twelfth-gate`), cola de curación conservada (62 filas), gate verde y build
OK; **`backfill_metadata --only image_url` COMPLETÓ** (1313 s, sin rc=124) y el run
cerró con 0 pasos en error. 7 items realmente nuevos. Hallazgo principal, gotcha
**#208**: **Panini activó una sala de espera Queue-it** en `.es` y `.it` — 17 source-runs
se saltaron con *"HTML muy corto… probablemente JS-rendered"*, pero la verificación en
vivo muestra **302 → `panini.queue-it.net`** y que esos 2.3 KB son la página de la cola;
`--enable-js` NO lo arregla (Playwright aterrizaría en la misma cola). La avería es
por-request: en la misma corrida Panini Planet Manga rindió 75 y las 16 searches de
`panini.es` dieron 0. **Gotcha #199 sigue viva y lo tapó**: el reporte de salud colapsó
las 16 searches en una fila FANTASMA y mostró las reales como 🟢 Healthy con `Runs 0`.
Segundo hallazgo: **gotcha #202 medida con su efecto perverso completo** — 10 items de
Funside que YA estaban en el corpus volvieron con `standardize_attempts` zerado **y URL
idéntica**, así que el cambio de URL de #192 no hace falta: basta con que la fuente
re-liste. El escape a curación de #191 sólo se dispara para lo que la fuente DEJÓ de
listar, o sea lo que ya no cuesta. **#192 también quedó ampliada**: el `l-id` posicional
de Rakuten no sólo pisa `detected_at` — a un item CRUDO le cambia el SLUG (su identidad),
porque sin `cluster_key` el slug se deriva de la URL; 1 de los 7 "items nuevos" del día
era en realidad esto. Funside es hoy el **42% de la cola de curación** (26
de 62) y 17 de los 21 pendientes, todo cómic occidental que NO está en
`comics_blacklist.yml`. Tercero: las regresiones de Dark Horse `limited edition`/
`exclusive` (1 vs mediana 15/13) quedaron **cerradas como falso positivo verificado en
vivo** — el buscador devuelve 25 productos pero son estatuas, pins y skate decks; el
filtro hizo su trabajo. Milky Way `deluxe` (6, 3ª vez igual) y Delcourt (0 vs mediana 1)
son mediana obsoleta. Nada aplicado sobre fuentes ni configuración: todo documentado en
las fichas, los fixes son decisión del owner. Sin commit.)
Update previo, 2026-09-15 (delta diario: corpus 14 497 → **14 533**; 62 crudos
estandarizados vía workflow —2 Tier 1, 2 Tier 2, 58 Tier 3—, 0 perdidos; aliases: 4
candidatas con ≥2 items, 4 skips [2 basura de ListadoManga #200, 1 cómic occidental, 1
homónimo ambiguo `happiness`], sin cambios al YAML; gate verde, build OK;
`backfill_metadata --only image_url` otra vez rc=124. De 35 URLs nuevas, 16 son cómic
occidental de Funside Variant [11 quedan crudos como `llm_non_manga`, 5 pasaron como
manga] y 5 son DUPLICADOS de Mangarden [el slug cambia de `preorder` a `ostatnie` y la
fila nueva queda con publisher `unknown`]. Dark Horse `limited edition`/`exclusive`
caen a 5 con paginación completa [probable cambio de ranking]. Todo documentado en las
fichas, nada aplicado. Sin commit.)
Update previo, 2026-09-13 (delta diario: corpus 14 503 → **14 497**; 27 crudos
estandarizados —2 Tier 1, 25 Tier 3—, aliases acotados a las 4 candidatas con ≥2 items
[2 merges, 0 canónicas, 2 skips de ListadoManga #200], gate verde, 752 tests, build OK;
`backfill_metadata --only image_url` completó. 4 novedades reales. Cinco hallazgos de
MECANISMO, ninguno aplicado —decisión del owner—: **#203** la sección PT-BR no tiene
`capa variante`, así que `filter_collectible` descarta todas las portadas variantes de
Panini Brasil [14 corridas seguidas]; **#204** `state.json` y el corpus divergen: 149
variantes de Mangavariant con score ≥20 están bloqueadas desde el 05-21 y se re-fetchean
309 URLs por día; **#205** el wiki API de Meian nunca se cableó a `scrape_delta`/
`scrape_full`, así que la fuente no tiene ingesta automática desde el 09-07; **#206** el
extractor de fechas exige año de 4 dígitos y 150 items de Panini Italia quedan sin
`release_date`; **#207** el backfill de aliases acotado por serie partió la edición MARS
30th. Sin commit.)
Update previo, 2026-09-11 (delta diario: corpus 14 476 → **14 490**; 56 crudos estandarizados
—5 Tier 1, 8 Tier 2, 43 Tier 3— incluidos 30 que la corrida del 09-09 dejó sin estandarizar
[su sesión murió tras lanzar el scrape; la del 09-10 no corrió por límite de sesión]; 3
canónicas nuevas de aliases; gate verde, 752 tests, build OK; `backfill_metadata --only
image_url` otra vez rc=124. Dos hallazgos de MECANISMO, ambos sin aplicar —decisión del
owner—: **#200** ListadoManga movió el nombre de la colección a `<h1>` y el parser lee el
primer `<h2>`, así que 231 items / 113 ediciones muestran "Números editados" como
`edition_display` y la detección premium por nombre está muerta [A/B en memoria: 0 → 38
candidatos en 4 colecciones]; **#201** el traductor persiste la página "Error 500" de
Google como traducción válida [289 items]; **#202** cada re-scrape borra
`standardize_attempts` de un item crudo, lo que deja inefectivo el fix de #191 en fuentes
que re-listan productos. Fuentes: los 3 *yield regressions* verificados como falsos
positivos; KADOKAWA Store coló una caja de cartas acrílicas [`アクリルカード` falta en el gate
de merchandising]. Sin commit.)
Update previo, 2026-09-08 (delta diario: corpus 14 446 → **14 449**, 7 items nuevos netos,
16 crudos estandarizados —2 Tier 1, 14 Tier 3—, gate `validate_corpus` verde, 752 tests verdes
y build OK. **Los dos bloqueos crónicos se destrabaron en esta corrida**: (a) `backfill_metadata
--only image_url` COMPLETÓ por primera vez en 7 corridas (1646 s, sin rc=124); (b)
`/watch-enrich-series-aliases` corrió por primera vez en 9 corridas y **conservó las 33 filas de
curación** — el fix #198 del 09-07 validado en producción. Lote de aliases acotado a las 21
candidatas con ≥2 items (de 813; **792 tienen 1 solo item**): 17 canónicas nuevas, 2 merges, 1
skip, 21 items remapeados, backfill idempotente en 2ª pasada. Gotcha #191 también confirmada
resuelta: el item pendiente ahora sí acumula `standardize_attempts`. Hallazgo principal, gotcha
**#199**: `_SKIP_RE`/`_ERROR_RE_LEGACY` de `source_health.py` capturan el nombre de fuente con
`([^:]+)`, que corta en el primer `:` — y **94 de las 140 fuentes del run se llaman
`<fuente> [search: <keyword>]`**. Consecuencia: Edizioni BD saltó sus 5 searches y el reporte la
mostró en 🟢 Healthy, con los skips atribuidos a una fuente FANTASMA marcada `Enabled ✗`. Misma
familia que los fixes #1/#2/#4 de ese archivo (fuente rota que el reporte da por sana). Las 2
anomalías de fuente del día resultaron **transitorias, verificadas en vivo**: Edizioni BD
responde 200/105 KB con resultados (y con el UA del scraper, así que no es el UA) tras 6
corridas sin un skip; Dark Horse `hardcover` cayó 32→17 por paginación truncada (5 págs → 3),
pero `page=5` sigue devolviendo 24 productos — y NO fue el borde Shopify compartido, porque
`deluxe`, `exclusive`, Funside y Manga Dreams rindieron idéntico en la misma corrida. De las 4
"yield regressions", **3 son mediana obsoleta, no averías**: JBC lleva 8 corridas clavada en 20
contra una mediana de 72.5 que aún arrastra dos 99 viejos (cierra el diagnóstico abierto de
#190), y Milky Way `deluxe` rindió 6 ayer Y hoy — no hay caída. Lead nuevo medido en
Manga-Sanctuary: 31 de 345 items con evidencia `collector` quedaron con `edition_key` `special`
(el item nuevo `Shinjū - Mourir d'amour` es el caso del día); **la hipótesis de que esto
explicaba las URLDUP quedó refutada** —sólo 3 de 112— y por eso no se tocó nada: la mayoría de
las 26 series partidas no comparte URL y pueden ser dos líneas comerciales legítimas. Nada
aplicado sobre fuentes ni configuración: todos los fixes son decisión del owner. Sin commit.)
Update previo, 2026-09-07 (delta diario + **tanda de fixes aplicada a pedido del owner**:
los 6 hallazgos del reporte matinal se cerraron en el mismo día, mecanismo primero y
limpieza después. **(1) Meian, gotcha #197** — la fuente llevaba 4 corridas en 0 y no tenía
arreglo por HTML (Angular sirve 64 KB de shell con 60 caracteres de texto útil, 0 enlaces y
sin sitemap). Se capturó el API JSON con el panel de red del navegador y se escribió
`scripts/wikis/meian.py`: **de 0 a 118 ediciones especiales** (Coffrets Collector) con ISBN,
fecha, autor, portada y contenido de la caja — datos que la fuente NUNCA había entregado. Dos
trampas costaron un 403 cada una: exige el header `Origin` (un `Referer` no alcanza) y la
respuesta lleva prefijo anti-XSSI `)]}',`; además el host es `www.anime-store.fr` CON `www.`
(sin eso parece que el API no existiera, que es por qué la sonda de la mañana lo dio por
indeducible). La entrada HTML quedó `enabled: false`. **(2) Aladin, gotcha #195** — la fuente
no declaraba `title_selector`, así que 130 de sus 438 títulos (30%) llevaban pegado el número
de puesto y el banner de la lista; `title_selector: "a.bo3"` + retrofit. **(3) Ivrea, gotcha
#196** — 19 de 20 URLs apuntaban a un JPG (lightbox de WordPress); `_product_anchor()` ahora
prefiere el ancla no-imagen y el retrofit repuntó las 19 a su ficha `/titulo/`, resolviendo el
slug contra el catálogo REAL del sitio y verificando cada URL en vivo. Hoy quedan **0
entradas-imagen en todo el corpus**. **(4) Funside, gotcha #193** — el fallback de autor leía
el `<body>` entero y devolvía el mega-menú (`"Batman ELDEN RING ARTBOOK"` en las 174 fichas de
la corrida); ahora corre en dos pasos separados, con la región del producto sin cromo y un
guard de forma de nombre propio. **La separación en dos pasos fue esencial**: la primera
versión aplicaba el guard a todo y mataba `"Autori: Tsutomu Nihei"`; y antes de endurecer se
MIDIÓ que la rama `di|du` —la sospechosa obvia— aporta 24 autores reales del corpus, así que
sacarla habría sido peor que el bug. 102 autores basura limpiados. **(5) #191** — el bucle de
re-inferencia se cortó (`standardize_attempts` ahora sube también en la rama `is_manga=false`)
y se agregó un gate determinista de merchandising JP, porque el día lo destapó: de tres
artículos del MISMO evento de KADOKAWA el LLM rechazó dos y aprobó el tercero, un diorama de
acrílico publicado como `product_type = manga`. **La primera versión del gate iba a destruir
10 manga reales** —la trampa exacta de la #189, vista sólo por leer el dry-run COMPLETO—: los
marcadores de inclusión también van en hiragana (`つき`, no sólo `付き`) y el discriminante
fuerte no es el marcador sino que el título nombre un LIBRO. Dry-run final: 5 rechazos, los 5
merchandising real, 0 falsos positivos; el bucle bajó de 6 items a 2. **(6) #194** — el
homónimo `uzumaki` (el terror de Junji Ito + el artbook de NARUTO de Kishimoto) se separó; los
3 artbooks de Kishimoto quedaron juntos bajo `naruto`. **Bonus, #155/#157/#198**: el bloqueo
que tenía la rutina diaria 7 corridas sin correr aliases está cerrado —
`scripts/prune_unmapped_queue.py` conserva la cola de curación en vez de truncar el archivo
entero, y `log_unmapped_series` ahora deduplica ENTRE corridas (la cola pasó de 4528 a 1064
filas, 76% eran duplicados, con las 31 de curación intactas). **Dos errores propios
corregidos sobre la marcha, que vale la pena recordar**: (a) el fix de Ivrea reparaba sólo
`sources[].url` y dejaba intacta la `url` de nivel superior —la que leen las proyecciones de
standardize—, así que el `.jpg` reapareció aguas abajo (gotcha #196 ampliada: todo retrofit
de URLs tiene que cubrir los DOS campos); (b) la primera versión del retrofit de autores
usaba una heurística de "valor repetido" que marcaba autores reales multi-firma y ni siquiera
atrapaba el caso objetivo — se reemplazó por denylist verificada en vivo. **El workflow de
standardize falló 2 veces seguidas** con `subagent completed without calling
StructuredOutput` (reproducible, no casualidad); se cerró por el camino MANUAL del skill —
subagentes que escriben `result_NN.jsonl`—, 79/79 items, 0 perdidos; el modo de fallo y su
recuperación quedaron documentados en el SKILL.md. Los subagentes destaparon además 4
`edition_key` de Ivrea que decían `artbook` siendo tomos numerados (colateral del bug de la
URL), corregidos con guard y verificación en vivo. Corpus 14 386 → **14 446** (+118 de Meian,
−5 merchandising expulsado, −2 novela/fotolibro a curación, resto consolidación), 2 crudos
pendientes (los dos escalan solos a curación con el fix de #191), suite 2592 → **2597 tests
verdes**, `validate_corpus` 0 violaciones duras, `set_rarity` y `build_web` OK, retrofits
idempotentes verificados en 2ª pasada. Fuentes habilitadas 57 → 56, wikis 26 → 27. Sin commit:
el working tree queda para revisión del owner.)
Update previo, 2026-09-06 (delta diario: corpus 14 378 → 14 386, 19 crudos estandarizados
—3 Tier 1, 16 Tier 2/3—, gate `validate_corpus` verde, 721 tests de extracción verdes y build OK.
Hallazgo principal, gotcha **#192**: el parámetro `?l-id=search-c-item-img-NN` de Rakuten es
POSICIONAL (codifica el puesto del producto en los resultados de esa corrida), así que la misma
ficha vuelve con una URL literalmente distinta cuando cambia de ranking y el merge le pisa
`detected_at` con la fecha de hoy. El dedup por `cluster_key` no se rompe —hay una sola fila—
pero **cualquier consumidor que defina "novedades del día" como `detected_at >= inicio del run`
sobre-cuenta**: de los 10 items con `detected_at` de hoy, 3 ya estaban en el corpus previo
(novedades reales: 7). La forma correcta de contar es comparar la URL NORMALIZADA contra el
backup `pre-scrape-delta` del propio run; snippet en `docs/scraper/sources/jp-rakuten-books.md`.
El caso se destapó rastreando el fotolibro de ídolo del 09-05, que pasó del puesto 20 al 23 sin
cambiar de producto. Corrida sin errores de red (0 en el scrape principal, a diferencia de los 3
read timeouts de ayer); el único paso en rojo es `backfill_metadata --only image_url` (rc=124,
6ª corrida seguida, ya documentado). Fuentes: Meian acumula 3 corridas seguidas de SPA sin
hidratar —única avería real de las 5 "yield regressions", las otras 4 son ruido ya
diagnosticado— y Mangavariant se recuperó sola del challenge de ayer, lo que CONFIRMA que es
intermitente y que el backoff propuesto habría salvado la corrida. Panini Italia publicó un
producto real con el número de tomo ausente del nombre (el SKU sí lo lleva), verificado en vivo.
`/watch-enrich-series-aliases` NO se corrió: sigue truncando el archivo entero (`SKILL.md:228`)
y hoy destruiría 28 filas `llm_non_manga` de curación (gotcha #155, 6ª corrida saltada); además
la condición "¿creció la cola?" está rota por #157 —82% de las 4013 filas de series son
`series_key` repetidas (713 únicas)—. Gotcha #191 confirmada por 5º día: 3 items siguen en el
bucle de re-inferencia sin incrementar `standardize_attempts`. Nada aplicado ni commiteado:
todos los fixes son decisión del owner.)
Update previo, 2026-09-05 (delta diario: corpus 14 371 → 14 378, 8 items nuevos netos,
17 crudos estandarizados —todos Tier 3—, gate `validate_corpus` verde y build OK. Hallazgo
principal, gotcha **#191**: el veredicto `is_manga=false` del LLM es la ÚNICA rama de
`standardize_apply.py` que deja el item pendiente SIN incrementar `standardize_attempts`,
así que el escape hatch `standardize_exhausted` nunca se dispara y el item vuelve a gastar
Tier 3 —la ruta más cara— en cada corrida, indefinidamente; verificado con 2 items de
merchandising de KADOKAWA Store detectados el 09-03 que volvieron a mandarse a un subagente
hoy. Es el patrón de #154 una capa más adentro (bucle de re-inferencia, no de re-ingesta),
invisible en el conteo de items. Incidentes del run: Mangavariant cayó por el challenge
sgcaptcha (rc=1, 2ª vez) —primera corrida en que el fallo queda al descubierto tras
deshabilitar la entrada YAML redundante el 09-02, el riesgo asumido funcionando como se
esperaba— y 3 read timeouts simultáneos (Pipoca & Nanquim, Planeta Cómic, Panini Brasil).
De las 5 "yield regressions" del reporte de salud, 4 son ruido ya diagnosticado (JBC 4ª
confirmación —y el dato del día 5 REFUTA que el checklist "se vaya llenando"—, Panini
España = página de novedades, Dark Horse `slipcase` con mediana 1, Panini Brasil = eco de
su propio timeout) y sólo Meian es avería real y reproducible (SPA de Angular sin hidratar,
2ª vez). `/watch-enrich-series-aliases` NO se corrió pese a que la cola creció: sigue
truncando el archivo entero (`SKILL.md:228`) y hoy destruiría 27 filas `llm_non_manga` de
curación (gotcha #155, 4ª corrida saltada). Nada aplicado ni commiteado: todos los fixes
son decisión del owner.)
Update previo, 2026-09-02 (revisión de fuentes pedida por el owner tras el delta diario:
4 defectos de MECANISMO cerrados + 17 items fuera de alcance expulsados, corpus
14 366→14 349, suite 2585→2592, 0 violaciones duras, enforcer byte-idéntico en 2ª pasada.
Gotchas #187-#190: (a) una lista CSS separada por comas NO es lista de prioridad —matchea
por orden en el DOCUMENTO— y hacía que Dynit capturara "Sconto 10%" como título; (b) un
`+` inmediatamente DESPUÉS de un token de home video enumera el CONTENIDO de la caja, no
un bonus, así que "(Blu-Ray+Dvd+Booklet)" se leía como manga-con-Blu-ray-de-regalo; (c)
`is_comic_not_manga()` ahora ve el SLUG de la URL (el sello que el título omite: Valiant),
y las `title_exceptions` DEBEN evaluarse contra el mismo blob —la primera versión iba a
destruir 3 manga por `gangan-joker` en la URL, detectado sólo por leer el dry-run
completo—; (d) `source_health` da falso positivo de yield garantizado a principio de mes
en fuentes con forma de calendario (JBC verificado sano en vivo). También: evidencia
non-manga por URL (`trading-card`) y entrada YAML de Mangavariant deshabilitada.
**Corrige la recomendación del reporte matinal del mismo día**: se midió la composición
real de las fuentes (Funside 96% manga, Star Comics ~98%) y acotar sus searches habría
destruido >100 manga para ganar 4 — el blacklist por franquicia era la herramienta
proporcionada. Deuda estructural anotada, NO abordada: los "STRONG manga hints" incluyen
términos de FORMATO (Deluxe/Library Edition, vol N) que no distinguen el medio, y la
regla 1 corre antes del guard de `purity: mixed`. Detalle en las fichas de fuente y
gotchas #187-#190. Sin commit.)
Update previo, 2026-09-02 (cierre de la vía whakoom: las 18 candidatas de tanda 3
curadas 18/18 aprobadas y aplicadas [167 portadas whakoom en total entre las 3 tandas],
deuda de sync de tanda 2 podada [cola 131→76 entries, 60 pendientes de otras acciones
intactas], corpus 14 366 con 0 violaciones duras y 2585 tests verdes; techo de la vía:
158 items ES con tomo >11 que exigen cuenta Whakoom. Detalle en
`docs/reference/images.md` § "Cierre vía whakoom (2026-09-02)". Sin commit.)
Update previo, 2026-09-02 (whakoom tanda 1 — los 139 items ES sin imagen resolubles
[vol<=11], 137 intentados [2 ya adjudicados de una corrida piloto previa]: 93 candidatas
nuevas encoladas en `cover_preview.json` [`pending`, hit rate 67.9%], 44 no resueltos
[11 `total_tomos_mismatch`, 13 rechazadas por el gate determinista de `sc_validate.py`, 14
`not_found`, 3 `ambiguous_multiple_editions`, 3 `volume_not_listed`]. Optimización clave:
agrupar los 137 targets por `coleccion_id` de listadomanga.es antes de buscar en Bing
colapsó las búsquedas a 61 grupos [reutilizando las candidatas de edición para todos los
volúmenes del grupo] — hasta 11 targets resueltos de una sola búsqueda. 2 hallazgos nuevos
documentados en `whakoom.md` §6: el contador `p.edition-issues` de una edición "Ongoing"
puede ir retrasado respecto a los tomos que ya lista (Berserk Master Edition, resuelto a
mano); ediciones-hermanas casi idénticas sin campo que las distinga (3 casos, correctamente
no resueltos). Caso de la ambigüedad de tipo de producto del piloto [gotcha ya documentada]
confirmado en vivo: el primer target casi resolvía contra un artbook en vez del box set
correcto — detectado a mano antes de pasarlo al resolver. Caché
`whakoom_edition_map.jsonl` 18→147 filas [110 resueltas]. `sync_cover_preview.py --dry-run`
0 cambios [cola sana]. Nada tocado en `items.jsonl`. Detalle completo en
`docs/reference/images.md` § "Whakoom tanda 1", quirks nuevos en
`docs/scraper/sources/whakoom.md` § 6. Sin commit — pendiente del owner: revisión visual de
las 93 candidatas y decisión sobre una tanda 2 para las ~369 "portada chica" [excluidas a
propósito de esta tanda].)
Update previo, 2026-09-02 (implementación de la vía "whakoom por página de edición" para
portadas ES, aprobada por el owner: skill nuevo `/watch-whakoom-covers` +
`scripts/retrofit/we_plan.py`/`we_resolve.py` [deterministas, reusan `sc_validate.py`/
`sc_flush.py` sin cambios]; universo real 670 items ES sin/con portada chica → 508
resolubles [vol<=11, sin login], 162 fuera de alcance. Piloto real vía Browser pane sobre
7 targets: 2 resueltos y encolados en `cover_preview.json` [`pending`, sin auto-aplicar],
5 correctamente rechazados por el gate determinista [total_tomos/idioma/tomo no listado —
0 falsos positivos]. 3 hallazgos reales corregidos en el mismo turno: Bing WEB search
(`bing.com/search`) da captcha con `site:` incluso autenticado → el skill usa Bing
IMÁGENES (no challengeado, mismo endpoint que `sc_plan.py`) + filtro de relevancia
client-side; Whakoom tiene DOS templates de página de edición (manga con tomos vs
libro/artbook oneshot) con selectors CSS distintos; el idioma se muestra en el idioma de
la UI (`www.whakoom.com` = español, no inglés) — `is_spanish_spain()` corregido para
ambos. Limitación documentada (no resuelta): oneshots pueden casar por casualidad
editorial+idioma+total_tomos=1 entre productos de tipo distinto (artbook vs box set) —
mitigado por owner review obligatorio (nunca auto-aplica). Suite 2464→2520 tests, 0
regresiones, `validate_corpus.py` 0 violaciones duras. Detalle en
`docs/scraper/sources/whakoom.md` § 6, `docs/reference/images.md`, gotcha #183. Sin
commit — pendiente del owner: decidir cuenta Whakoom para el pool >11 tomos (implica
evaluar ToS).)
Update previo, 2026-09-02 (cierre Etapas 1-2 de imágenes: cola aplicada —17 portadas
mejoradas, 97 rechazos ledgereados, 1 downgrade real detectado y revertido—, balance
614→548 portadas malas / 12 con `cover_upscale_factor≥1.6`, 542 targets restantes para
tanda 3; hallazgo nuevo sin corregir: 109 items con imagen duplicada en `images[]`, 100%
Aladin. Detalle en `docs/reference/images.md` § "Cierre Etapas 1-2". Sin commit.)
Update previo, 2026-09-02 (gotcha #177 cerrada — Aladin: fix de mecanismo en
`candidate_metadata_conflict`/`_extract_candidate_volumes` [ya no confunde el índice de
foto `_N` de Aladin con el tomo — regla general por ID de catálogo numérico, no un check
de host] + patrón determinista nuevo en `upgrade_image_resolution.py` [`cover<N>/` →
`cover500/`, verificado en vivo que `cover500` es el techo real del CDN]. Corrida real
acotada con `--host aladin.co.kr`: 371 URLs candidatas → 297 mejoradas [mediana ×6.25
píxeles, rango ×1.77–×16], 54 sin mejora real [techo del CDN o portada ya
algoritmo-upscaleada]; 2 de los 4 items con recorte apaisado destruido quedaron resueltos
[`return-of-the-mount-hua-sect-...-kr-21`, `frieren-...-kr-10`], 2 siguen bajo el piso por
falta de detalle real en la fuente. pytest 2432 verde [+11], `validate_corpus` 0
violaciones duras, segunda corrida real 0 mejoradas adicionales [idempotencia],
`sync_cover_preview --dry-run` 0 operaciones [el candidate `approved` externo de
`return-of-the-mount-hua-sect-...-kr-21` queda redundante contra la portada nativa ya
aplicada, pero las candidatas `approved` son intocables por diseño — no se tocó
`cover_preview.json`]. Backup `items.jsonl.pre-aladin-upgrade-bak`. Sin commit.)
Update previo, 2026-09-02 (cierre de la Etapa 1 de triage de imágenes: denylist aplicada +
7 non-manga expulsados, todo verificado contra `etapa1-triage.json` antes de tocar el
corpus, gotcha #176. Regla `.gif` de Rakuten implementada por host+extensión —cruzada
contra los 50 `.gif` de portada del corpus, 50/50 confirmados placeholder/imagen
equivocada, 0 falsos positivos— + 6 firmas sha1 nuevas (AnimeClick/Amazon×4/Funside/
Mangavariant) + 6 `imagen_equivocada` por sha1. `purge_placeholder_images.py
--only-reasons known,signature`: 68 entries quitadas, 56 items sin foto (candidatos a
`/watch-search-covers`); `--dry-run` posterior 0 pendientes. Los 5 sospechosos non-manga
verificados por título/fuente (2 almanaques de adivinación, 1 artbook de historia
natural, 1 guía de viaje, 1 ensayo/tanka de gatos, 1 enciclopedia de videoconsolas) se
agregaron a `_NON_MANGA_HARD`; `filter_non_manga.py` expulsó exactamente 7 items
(14353→14346). 2 falsos positivos del juez de visión (un manhwa real de Daewon C.I. y 2
`dudoso`) NO se tocaron — verificados por búsqueda web antes de descartar. pytest 2421
verde, `validate_corpus` 0 violaciones duras, `sync_cover_preview --dry-run` 0
operaciones. Backup `items.jsonl.pre-etapa1-denylist-bak`. Sin commit.)
Update previo, 2026-09-02 (Etapa 1 de triage de imágenes CERRADA: 15 subagentes de
visión juzgaron los 2 lotes y un JUDGE re-verificó todo lo decisorio →
`data/diagnostics/etapa1-triage.json` (1179 veredictos). Dos conclusiones que cambian
criterios: (1) **el umbral de 90.000 px no sirve para encolar búsqueda web** — el 91% del
lote A se ve bien; la métrica correcta es el reescalado en la card (`min(300/w,420/h) >=
1.6`), lo que baja la cola de 579 a 33 ítems (recomendación para `sc_plan`, sin tocar
código); (2) **la familia dominante de placeholders (Rakuten, 49/58) NO es dedupable por
hash** porque quema el título en el pixel — el discriminador es la extensión `.gif`
(gotcha #171). Además: 45% de los `placeholder` de los agentes baratos eran fotos de
producto físico o portadas minimalistas legítimas (gotcha #172), y el chunk 1 de ambos
lotes se había perdido entero sin que nada lo detectara. Nada purgado ni aplicado: la
tabla de denylist por host es decisión del owner. Sin commit.)
Update previo, 2026-09-01 (cierre final de la tanda de depuración de imágenes:
cola de portadas aplicada de punta a punta —220 reemplazos/391 huérfanas
purgadas, 211 `remove_image`, 8 revertidas, 25 rechazos al ledger—; portadas
malas 1042→614 [<90k 767→579, sin local 275→35], sin imagen 467→439,
`cover_preview.json` 462→58 entries/476→60 pendientes, ledger 210→235 filas;
0 items sin portada, 0 duplicados de galería (gotcha #164), 0 refs de
mangavariant sin espejo local (gotcha #169); pytest 2394 verde antes y
después, validate_corpus 0 violaciones duras. Backups: `items.jsonl.pre-
apply-final-bak` + `cover_preview.json.pre-sync-cover-preview-bak`. Sin
commit.)
Update previo, 2026-09-01 (cierre de la tanda de depuración de imágenes: banner
de meian-editions.fr purgado —7 items—, cola de portadas aplicada —9 aprobadas,
204 rechazadas ledgereadas, 478 pendientes—, bug de duplicado en
`replace_cover_demote` encontrado y parchado ad hoc —gotcha #164, fix de
mecanismo pendiente—; verificación completa en 0 violaciones duras. Sin commit.)
Update previo, 2026-09-01 (OLA 3 de depuración de imágenes — gotcha #160: al
recalcular el criterio C3b (SHA-256 compartido ≥5 items) sobre el corpus post
ola1/ola2 aparecieron 3 grupos nuevos que el red-team nunca validó; 2 resultaron
falsos positivos (portadas reales cross-contaminadas entre tomos hermanos de un
box de Mangarden.pl, no placeholders) y 1 sigue sin validar (banner de
meian-editions.fr en 7 items de 3 series). Los 3 grupos YA validados (Berserk
Deluxe/Dark Horse, logo Mangavariant, banner Square Enix) se purgaron: 27
entries, 0 items quedaron sin imagen. Denylist de 28 candidatas icónicas
(manga-passion.de/livriz.com/funside.it/PRH/Rakuten) clasificada a mano y
reportada — nada purgado, decisión del owner. 40 candidatas de promoción local
(portada mala con alternativa ya local en la propia galería) encoladas en
`cover_preview.json` vía `action="replace_cover_demote"` reusando la
infraestructura existente (cero código nuevo en fetch_better_covers/serve/
dashboard), ordenadas fuertes-primero (7 fuertes / 33 débiles). Detalle en
`docs/reference/images.md` § "OLA 3" y fichas de fuente `pl-mangarden.md`/
`fr-meian.md`. Sin commit.)
Update previo, 2026-08-31 (delta diario: gotcha #157 — `unmapped_series.jsonl` NO
deduplica: cada corrida re-apila las mismas series, así que la cola crece por
duplicación y no por descubrimiento. En esta corrida (+26 items netos) se escribieron
501 filas nuevas de las cuales sólo 8 son de items nuevos; 92% del archivo (908/987
filas) son `series_key` repetidas. Consecuencia directa: la condición "¿creció la
cola?" que usa el PASO 4 de la rutina diaria se dispara siempre. Esta corrida tampoco
ejecutó `/watch-enrich-series-aliases` (3er día), para no destruir las 14 filas
`llm_non_manga` por gotcha #155. Nada aplicado: dedup de la cola, `purity`/searches y
sacar el paso 4e del delta son decisiones del owner).
Update previo, 2026-08-30 (delta diario: gotcha #156 — `unmapped_series.jsonl` se
escribe en la FASE 1, antes de los gates deterministas de la FASE 3, así que el 46%
de sus filas (223/485) apuntan a items que el pipeline ya expulsó; las fuentes de
tipo `search` con términos de FORMATO de edición —deluxe/box/hardcover/slipcase/
数量限定/variant— tienen 100% de filas huérfanas y son la vía de entrada recurrente
de cómic occidental y libros generales. Esta corrida NO ejecutó
`/watch-enrich-series-aliases` justamente para no destruir la cola `llm_non_manga`
por gotcha #155: las 9 filas flageadas siguen vivas para curación. Nada aplicado:
las recomendaciones de `purity`/searches son decisión del owner).
Update previo, 2026-08-29 (delta diario: gotcha #155 — `unmapped_series.jsonl` es
DOS colas en un archivo y el Step 5 de `/watch-enrich-series-aliases` las trunca
ambas, así que correr aliases después de standardize borra la cola de curación
`llm_non_manga` sin revisarla; recuperable del backup pre-enrich, que rota.
También documentado: el paso 4e del delta —`backfill_metadata --only image_url`—
muere por timeout rc=124 hace 5 corridas seguidas, en `docs/reference/images.md`.
Nada aplicado: ambos son decisión del owner).
Update previo, 2026-08-26 (ciclo de re-ingesta diaria cortado en IT - Funside
Variant: 11 términos nuevos en `data/comics_blacklist.yml`, corpus 14274→14259.
El patrón general —veredicto LLM que no expulsa + gate determinista que expulsa
DESPUÉS del scrape = bucle infinito— quedó como gotcha #154; `purity` de la
fuente NO se tocó, sigue vigente la decisión del owner del 08-24).
Update previo, 2026-08-24 (rutina diaria `pandawatch-delta-diario` creada como
tarea programada de Claude Code, 11:00 AM — delta + estandarización con freno
>300; excepción a la skills policy documentada arriba; detalle en
PIPELINE-WALKTHROUGH → "Delta diario (programación)").
Update previo, 2026-08-23 (curación de la cola `llm_non_manga`: 265 items
revisados → 94 KEEP / 171 EXPEL / 7 inciertos; corpus 14386→14215. Causa raíz
del bloque grande: el prompt del skill standardize mandaba a rechazar light
novels — corregido, gotchas #147-#149. Playbook en `docs/reference/conventions.md`).
Mismo día: ES/MX MangaLine deshabilitadas por host caído desde
2026-07-07 — conteo de fuentes habilitadas ~63→~61; detalle en
`docs/scraper/sources/es-mangaline-espana.md` y `mx-mangaline-mexico.md`.
Update previo, 2026-07-08 (implementación de la auditoría Fable 2026-07-08 —
~180 hallazgos en 26 commits sobre `fable-audit-20260708`, gists #1 y #6
ajustados: spool de flush + lock inter-proceso sobre items.jsonl). CLAUDE.md se
compactó de ~5700 a ~190 líneas: el changelog histórico narrativo se removió
(vive en `git log -- CLAUDE.md`) y el detalle de referencia (file map, las 7
decisiones, las 149 gotchas, convenciones, dashboard, imágenes) se movió a
`docs/reference/`, cargado bajo demanda vía el índice de arriba.
Al cerrar una tarea meaningful: actualizá el doc de referencia que corresponda (NO
metas detalle nuevo en CLAUDE.md — mantenelo chico), sincronizá el gist si aplica,
y bumpeá esta fecha. Nada de changelog narrativo acá.
