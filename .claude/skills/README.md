# .claude/skills/

Project-level **skills** (LLM-driven curation routines) versionados con el
repositorio. Cada skill es un **directorio** `<nombre>/` con un archivo
`SKILL.md` adentro; Claude Code lo descubre y lo invoca via `/<nombre>`.
La descripción frontmatter del `SKILL.md` decide cuándo el modelo lo
activa.

> **Importante (formato)**: Claude Code descubre skills como
> **directorios** (`<nombre>/SKILL.md`), NO como archivos sueltos
> `<nombre>.md` en `.claude/skills/`. Si crearas un `.md` plano, no
> aparecería en el autocompletado de `/`.

Estos skills viven en el proyecto (no en `~/.claude/skills/`) para que
viajen con git. Cualquier máquina que clone el repo los tiene
inmediatamente disponibles.

## Skills disponibles

Dos familias: **proceso de desarrollo** (cómo implementamos código con IA —
ver [docs/process/AI-WORKFLOW.md](../../docs/process/AI-WORKFLOW.md)) y
**curación de datos** (el corpus). Todos son manuales: solo a pedido
explícito del owner.

### `/feature-spec` (proceso)

**Propósito**: arrancar una épica (Vía C del AI-WORKFLOW). Entrevista al
owner (AskUserQuestion), explora el código con un subagente y escribe un
spec autocontenido en `docs/specs/SPEC-<slug>.md` (o FRD de web-next si
aplica) con unidades de trabajo y criterios de verificación ejecutables.
**No implementa** — el spec se ejecuta en una sesión fresca.

**Modelo del subagente**: el subagente `Explore` corre con **`sonnet`** — es
mapeo/recuperación de contexto, no razonamiento fuerte (la entrevista y la
escritura del spec pasan en el hilo principal). Sonnet es más rápido y barato
y alcanza de sobra.

**Cuándo invocarlo**: feature grande, área nueva, o decisiones de producto
abiertas. Para fixes y features acotadas NO (vía directa / plan mode).

### `/ship-check` (proceso)

**Propósito**: gate determinístico pre-commit. Detecta áreas tocadas en el
diff, corre los checks correspondientes (pytest, dry-runs de retrofits,
vitest + build de web-next, validate_corpus si aplica) y audita que los
docs exigidos por la policy de CLAUDE.md estén en el mismo diff (fichas de
fuente, PIPELINE-WALKTHROUGH, registry…). Reporta checklist PASS/FAIL con
evidencia.

**Cuándo invocarlo**: antes de CADA commit meaningful. Costo casi nulo
(comandos + exit codes, casi sin LLM).

### `/product-pulse` (proceso, post-lanzamiento)

**Propósito**: loop de iteración por tracción. Lee PostHog (tráfico,
contenido top, eventos, errores) + `data/feedback.jsonl` y produce un
backlog priorizado de 3–5 oportunidades (impacto × esfuerzo) con la vía
recomendada para cada una. Guarda el reporte en `data/diagnostics/`.
**No implementa.**

**Cuándo invocarlo**: semanal/quincenal después del lanzamiento público.
Antes del lanzamiento solo reporta el gap de instrumentación.

---

### `/watch-standardize-catalog`

**Propósito**: pasada 2 de la estandarización de schema. Procesa items
de `data/items.jsonl` que NO tienen el campo `standardized_at` —
típicamente items recién scrapeados que llegaron con asignación
heurística cruda (o sin asignación) del pipeline.

> **Política de títulos (2026-06-12, gotcha #92)**: el skill NO toca el `title`
> — es el nombre OFICIAL scrapeado; no se traduce, no se renombra a la serie
> canónica, no se le inyecta tipo de edición. `title_standardized` quedó
> RETIRADO del schema (el LLM ya no lo emite y el apply lo ignora).

**Cómo funciona** — el audit y el merge son scripts **COMPARTIDOS** con el
workflow (`scripts/standardize_audit.py` / `scripts/standardize_apply.py`,
fuente única anti-drift, 2026-06-11): el skill los invoca, nunca embebe
copias de la lógica. Las reglas de negocio del prompt LLM (edition_key,
publisher/país/tipo de edición, 画集付き, coleccion=edición, allowlists) son
OTRA fuente única — `.claude/skills/watch-standardize-catalog/prompt-rules.md`
— que este SKILL.md y el workflow leen, ninguno la copia (auditoría
2026-07-08, hallazgo F7: antes la regla 画集付き vivía SOLO en este SKILL.md
y 0 veces en el workflow, drift confirmado).

> **Run dir persistente (2026-07-08, hallazgo F3)**: `data/standardize-run/`
> (gitignored) — antes `/tmp/manga-standardize-run`, volátil ante reboot.
> `standardize_audit.py` escribe ahí `tier{1,2,3}.json` + `summary.json` (el
> contrato de conteos `{total,pending,tier1,tier2,tier3,exhausted}` —
> hallazgo F6, reemplaza el parseo por regex del reporte de un subagente).
> El checkpoint `data/standardize-progress.json` quedó MÍNIMO: solo
> `tier1_done` — nunca los resultados LLM completos. Tier 2/3 se resumen
> solos detectando qué `result_t{2,3}_NN.jsonl` ya existen en el run dir.

1. **Audit** (`standardize_audit.py`, flags `--limit`/`--force-all`/`--base`): filtra
   items sin `standardized_at` **y sin `approved_at`** (los golden records
   aprobados por el owner nunca se re-procesan; se pueden leer como
   referencia pero jamás se sobreescriben), asigna `confidence_tier` y
   escribe las proyecciones `tier{1,2,3}.json` con `proposed_*`,
   `existing_edition_key` (el LLM no re-agrupa items con edición asignada) y
   `known_edition_keys` (keys ya existentes en el corpus para esa serie —
   el LLM las REUSA en vez de acuñar variantes special/limited, gotcha #69).
2. **Tier 1** (`standardize_apply.py tier1`): aplica la propuesta
   determinística (0 tokens LLM) y marca `standardized_at`.
3. **Tier 2/3**: subagentes paralelos en chunks chicos validan (T2) o
   derivan desde cero (T3) series_key/edition_key/volume
   via LLM (nunca títulos); cada chunk escribe su propio `result_*.jsonl` y
   devuelve solo un resumen chico (`{count, urls_ok, urls_failed}` — el merge
   siempre lee del JSONL en disco, nunca del structured output). **Modelos del
   workflow**: los agentes mecánicos (audit, tier1, chunkers, checkpoint,
   merge, cleanup) y la validación Tier 2 usan `haiku`; SOLO la derivación
   Tier 3 usa `sonnet`. Costo fijo ~200k tokens/corrida → conviene lotes
   de ≥100 items.
4. **Merge** (`standardize_apply.py merge`): PRESERVA el `edition_key`
   existente, fallback a la propuesta heurística si el LLM devolvió keys
   vacías (sin keys usables → el item queda PENDIENTE), aplica
   `canonical_series_key()` de `series_aliases.yml`. **El LLM NO expulsa**
   (WO-C, gotcha #122, 2026-07-07): `is_manga=false` YA NO manda el item a
   `data/non_manga_blacklist.jsonl` — queda PENDIENTE y se registra en
   `data/unmapped_series.jsonl` (reason `llm_non_manga`); la expulsión real
   la deciden los gates deterministas (`filter_non_manga`/
   `filter_collectible`) en la próxima corrida del scrape. Además detecta
   outliers de serie por /coleccion, consolida duplicados y reporta INTEGRITY.
5. **Enforcer** (`scripts/retrofit/enforce_listadomanga_rules.py`, Step 6b):
   re-aplica determinísticamente las reglas duras de agrupación — el LLM NO
   es autoridad. Incluye los pasos 3c1/3c2/3c3/3c4/3c5 (slug de tipo de
   edición #69, series duplicadas #70, publisher por edición, prefijo de
   serie del edition_key #71, palabra de edición duplicada/"Regular" en
   títulos #72) para TODAS las fuentes, y el paso 4b re-corre los fixers de
   título DESPUÉS de consolidate (converge en una sola pasada).
6. **Gate bloqueante** (Step 7b): tras el merge/enforcer corre
   `scripts/validate_corpus.py` sobre TODO el corpus. Si reporta violaciones
   duras, la corrida NO se da por cerrada (el workflow lo propaga como
   `status: completed_with_violations`) — hay que investigar antes de
   anunciar éxito.
7. **Verificación de integridad con reintento** (Step 5): antes del merge se
   valida que cada `result_*.jsonl` tenga exactamente los mismos items que su
   `chunk_*.jsonl` (parchea URLs truncadas por prefijo, reintenta lo faltante
   inline o con un subagente extra).

**Manual vs workflow guardado**: hay un único umbral de pendientes (una sola
constante, ver el Step 1 del [`SKILL.md`](watch-standardize-catalog/SKILL.md) —
no la dupliques acá) que decide si conviene procesar inline o invocar
`.claude/workflows/watch-standardize-catalog.js` (ver sección "Workflows" más
abajo). El chunker (manual o del workflow) agrupa siempre por `group_key`
(mismo `/coleccion` o misma URL base) para que los hermanos de una edición
nunca queden separados en distintos chunks.

**Cuándo invocarlo**:
- Después de cada `manga_watch.py` scrape (items nuevos vienen sin
  `standardized_at`).
- Antes de publicar un build fresco del dashboard.
- Semanal como pasada de curación.

**Modo `--force-all`**: flag de `standardize_audit.py` que trata TODOS los
items como pendientes para forzar re-procesamiento (útil al cambiar reglas
de estandarización mayor).

**Output esperado por subagente** (per item):
```json
{
  "url": "...",
  "is_manga": true,
  "non_manga_reason": "",
  "series_key": "berserk",
  "series_display": "Berserk",
  "edition_key": "berserk-darkhorse-deluxe",
  "edition_display": "Deluxe (Dark Horse)",
  "volume": "1"
}
```

### `/watch-enrich-series-aliases`

**Propósito**: procesar la queue de series sin canonical
(`data/unmapped_series.jsonl`) y mantener `data/series_aliases.yml`
actualizado con traducciones multilingües. `argument-hint` real:
`[--max-suggestions N] [--min-count N]` — ver
[`SKILL.md`](watch-enrich-series-aliases/SKILL.md) para el detalle completo.

**Cómo funciona** (resumen — el detalle paso a paso vive en el `SKILL.md`):
1. Audita la queue (`scripts/audit/unmapped_series.py`).
2. Para cada `series_key` no canónico, decide: **Merge** como alias de un
   canonical existente (un fuzzy match alto es un hint, NO un veredicto —
   confianza media exige evidencia estructural explícita antes de mergear,
   un falso merge es irreversible), **Create** nuevo canonical vía Anilist
   API, o **Skip** (confianza/volumen bajos).
3. Antes de la primera edición: backup timestamped del YAML
   (`backup_and_rotate(..., timestamped=True)`) y una **snapshot baseline de
   colisiones** (`scripts/audit/lint_series_aliases.py --snapshot`) — las
   colisiones de normalización PRE-EXISTENTES en el YAML no bloquean; solo
   las NUEVAS que esta corrida introduzca.
4. Edita `data/series_aliases.yml` in-place; **lint anti-dup-keys contra ese
   baseline** después de cada tanda de ediciones (`lint_series_aliases.py --baseline`) —
   atrapa claves canónicas duplicadas (fatal siempre) y colisiones nuevas
   (fatal solo si no estaban en el baseline).
5. Corre `scripts/retrofit/backfill_series_aliases.py --only-keys <keys tocadas>`
   (fuente única, backup timestamped propio) para remapear + consolidar
   `items.jsonl` (**salta items con `approved_at`**; `--only-keys` REQUERIDO —
   scope acotado a la corrida, regla anti-colapso).
6. Trunca la queue (`data/unmapped_series.jsonl`) — solo si el backfill salió
   exit 0.
7. **Cierre (gates, todos bloqueantes)**: lint contra baseline + `validate_corpus.py`
   + prueba de idempotencia (re-correr el backfill con los mismos `--only-keys`
   debe dar 0 cambios) + tests. Al final exporta el índice de búsqueda en vivo
   (`scripts/export_series_aliases.py`) para que web-next lo refleje sin build
   completo.

**Cuándo invocarlo**:
- Después de `/watch-standardize-catalog` cuando aparecieron series_keys
  nuevas.
- Semanal junto con el otro skill.
- Cuando ves la misma obra con nombres diferentes en el dashboard.

### `/watch-evaluate-sources`

**Propósito**: auditar fuentes candidatas ANTES de implementarlas. Evitar
incorporar fuentes que no aportan valor real al catálogo (lección: BooksPrivilege
— 11k items de tomos regulares con postal de regalo, sin foto del extra).

**Input**: lista de URLs o nombres en cualquier formato — una por línea, con
contexto adicional o sin él.

**Cómo funciona** (resumen — detalle completo en el
[`SKILL.md`](watch-evaluate-sources/SKILL.md)):
0. Carga las fuentes `enabled` de `sources.yml` **en vivo**, agrupadas por
   país (`load_active_sources_by_country()` de `scripts/audit/source_overlap.py`)
   — ya NO hay una tabla hardcodeada acá ni en el skill; `sources.yml` cambia
   seguido y una tabla fija driftea (hallazgo ES-2, auditoría Fable 2026-07-11).
1. Parsea la lista de candidatas del mensaje del usuario.
2. Lanza un subagente `general-purpose` con **`sonnet`** por fuente en
   paralelo. Cada subagente hace un triage chico para Content Fit y, si pasa,
   amplía la muestra para el resto de la rúbrica (C1-C5, ver `SKILL.md` para
   los tamaños exactos); evalúa campos mínimos, foto del EXTRA si la fuente
   cubre bonuses, `catalog_scope` (`manga_only`/`mixed` — alimenta la decisión
   de `purity` al dar de alta la fuente), y factibilidad técnica (incluye
   distinguir "sitio muerto" de "requiere `kind: js`" cuando WebFetch trae un
   esqueleto vacío con señales de hidratación client-side). Escribe su JSON a
   `data/diagnostics/source-eval-<id>.json`.
3. **Overlap mecánico, no estimado por el LLM**: `scripts/audit/source_overlap.py`
   cruza el `isbn`/`series_key_guess` de la muestra contra `data/items.jsonl`
   con las MISMAS funciones de normalización del pipeline
   (`normalize_isbn`, `_slugify_kebab`) y devuelve `nuevo`/`parcial`/`redundante`
   (o `sin_datos` si la muestra no trajo ISBN — nunca un % inventado).
4. Compila reporte: tabla resumen (✅/⚠️/❌) + detalle solo para viables.

**Output** (no implementación):
- Tabla de viabilidad con veredicto y razón por fuente. Veredictos incluyen
  `Agregar`, `Viable — requiere kind: js` (JS-rendered, no muerto),
  `Reemplaza [X]`, `Complementa [X]`, y varios `No — <razón>` (ver `SKILL.md`).
- Para viables: qué aporta, qué falta, acción recomendada.

**Cuándo invocarlo**:
- Antes de implementar cualquier fuente nueva.
- Al recibir una lista de sitios a evaluar ("evalúa estas páginas").
- Cuando una fuente existente parece redundante con una nueva.

### `/watch-review-feedback`

**Propósito**: revisar el feedback que el usuario dejó via el botón 👎 del
dashboard (`data/feedback.jsonl`). Cada entrada ya contiene todos los campos
del item más el motivo. Categoriza cada feedback (problema de filtro vs.
problema de calidad de datos), propone fixes concretos, aplica los aprobados
y cierra la queue. **Trigger 100% manual** — invocar SOLO cuando el usuario lo
pide explícitamente; nunca correrlo de oficio solo porque el archivo tiene
entradas.

**Cómo funciona** (resumen — detalle completo en el
[`SKILL.md`](watch-review-feedback/SKILL.md)):
1. Carga la queue. `feedback.jsonl` es un **log MIXTO**: filas `action="feedback"`
   (o sin `action`, legacy) son el feedback real a procesar; pero `serve.py`
   también apenda ahí sus operaciones de curación ya aplicadas (`move`/`merge`/
   `remove`/`batch-move`) — el skill filtra por `action` y solo procesa las
   primeras; las de curación se cuentan aparte, informativo.
2. Dedup por cluster: si el mismo item recibió 👎 más de una vez, **conserva
   TODOS los reasons** (no solo el más reciente) para no perder contexto al
   categorizar.
3. Clasifica cada item con taxonomía de 14 categorías: **A–J** (filtros/catálogo:
   merchandising, trading cards, noticias, tomos regulares, source ruidosa,
   western comics, light novels, preferencia personal, falsa señal, selectores
   amplios) y **K–N** (calidad de datos: portada equivocada, metadata incorrecta,
   series_key/edition_key mal asignado, título con basura del scraper).
4. Para problemas de filtro: escanea el corpus buscando más items afectados
   por el mismo patrón, presenta propuestas numeradas y **espera confirmación**.
5. Aplica cambios aprobados: edita `manga_watch.py` / `comics_blacklist.yml` /
   `sources.yml` / `series_aliases.yml` / o correcciones puntuales vía
   `scripts/retrofit/fix_item_fields.py` (allowlist de campos + `title`
   BLOQUEADO salvo `--allow-title` explícito, política de títulos gotcha #92).
   **Golden records guard**: un fix K–N que tocaría un item con `approved_at`
   NO se auto-edita — se consulta al owner primero.
6. Agrega tests y corre pytest (solo para cambios de filtros). **Advertencia
   gotcha #61**: sobre un item YA estandarizado, `rescore.py`/`filter_collectible.py`
   son no-op para las categorías D/I — el corpus está ~98.9% estandarizado, así
   que el fix real para ESE item puntual es `fix_item_fields.py` o
   re-estandarizarlo, no confiar en que el retrofit masivo lo saque.
7. **Cierre no-ciego**: el backup timestamped se toma primero (retiene el
   rastro completo, feedback + curación), pero la reescritura de
   `feedback.jsonl` ya NO es un truncado ciego (`: > archivo`) — conserva las
   filas que esta corrida no vio (por `submitted_at`), así una fila nueva
   escrita por `serve.py` o un 👎 del dashboard mientras el skill corría no se
   pierde.
8. Actualiza CLAUDE.md "Last updated" + el doc de referencia que corresponda.

**Cuándo invocarlo**:
- Cuando el usuario pide explícitamente "revisar feedback", "mejorar los
  filtros", "corregir datos" — nunca de forma automática.
- Periódicamente después de scrapes grandes, a pedido del owner.

### `/watch-validate-rarity`

**Propósito**: verificar vía web los items cuya `rarity="rare"` viene de
**incertidumbre** (fallback de fuente de referencia — Mangavariant/Sumikko —
o `retailer_exclusive` sin stock verificado), NO los que tienen evidencia
estructural (keyword de no-reimpresión, print run). Escribe el veredicto como
evidencia (`stock_status` + `stock_checked_at`) y **re-deriva la rareza con
`derive_rarity_tier()`** — nunca asigna tiers a mano. Solo procesa items sin
`rarity_verified_at` (incremental). Agrupa por `edition_key` (1 verificación
por edición) con cap de 40 por corrida (`--limit N`).

**Cómo funciona** — Steps 0/1 y 3 compilados a script (auditoría Fable
2026-07-08, hallazgo F5; antes el tracer de incertidumbre vivía DUPLICADO dos
veces en el SKILL.md — ahora `scripts/audit/rarity_candidates.py` es la ÚNICA
implementación, fijada por un test de coherencia por-rama contra
`derive_rarity_tier()` en `tests/test_rarity_candidates.py`):
1. `scripts/audit/rarity_candidates.py` selecciona rares por incertidumbre
   (`rarity_uncertainty_reason()`), excluye aprobados y ya verificados, agrupa
   por `edition_key` y prioriza retailer_exclusive (posible promoción a
   super_rare) + mercados occidentales. Escribe
   `data/diagnostics/rarity_validation_candidates.json` — el `group_id` de ahí
   es el identificador que indexa los veredictos en el Step 2/3 y aparece en
   el output humano priorizado.
2. Verifica con escalera de métodos (interactivo, LLM + Chrome — la única
   parte no compilable): URL del item si es retailer → tienda del publisher
   (mejor ground truth; panini.it solo vía Chrome por queue-it) → Amazon vía
   Chrome con selectores JS (WebFetch da 500) → WebSearch solo para descubrir
   la ficha. Guarda los veredictos en
   `data/diagnostics/rarity_validation_results.json` (keyed por `group_id`).
3. Veredictos: `in_stock` → common (salvo evidencia estructural extra),
   `out_of_stock` → rare confirmado o **super_rare** si retailer_exclusive,
   `not_found` → rare confirmado, `inconclusive` → no toca nada (se reintenta).
4. `scripts/retrofit/apply_rarity_verdicts.py` aplica: **valida la estructura
   de `results.json`** (lista de objetos con `group_id` no vacío y `verdict`
   válido; corta con error controlado ante JSON malformado o `group_id`
   duplicado con veredictos distintos), marca `rarity_verified_at` (ground
   truth: `set_rarity --force` lo respeta), loguea a
   `data/diagnostics/rarity_validation_log.jsonl` e imprime **"Veredictos sin
   match: N"** con los `group_id` huérfanos (que no matchearon ningún item
   candidato — típico de un typo o un candidato que dejó de serlo) para que
   se revisen antes de cerrar.

**Cuándo invocarlo**:
- Después de scrapes grandes con items nuevos de fuentes de referencia.
- No para corridas delta diarias (10-20 items nuevos, el default está bien).
- Nunca integrar en `/watch-standardize-catalog` — separa el costo de tokens.

**Tier de modelo (hallazgo F10)**: hilo principal; Steps 0/1/3 son 100%
mecánicos (scripts, cero LLM), el Step 2 (verificación web) sí razona —
`sonnet` alcanza, no requiere `opus`.

---

### `/watch-search-covers`

**Propósito**: buscar portadas en alta resolución para items con imagen de baja
calidad (la portada `images[0]` o una foto de galería por debajo del umbral de
píxeles) o sin imagen. Usa **Chrome exclusivamente** (`mcp__claude-in-chrome__*`)
y combina, por cada imagen objetivo, **Yandex búsqueda-por-foto** (reverse
image, usando la imagen actual como consulta) como fuente **primaria** — sin
captcha, devuelve portadas del tomo/edición correctos — más **variantes de
texto con contexto** en **Google Imágenes** (`udm=2`), con fallback a Bing si
Google muestra consent wall. Escribe candidatas a `data/cover_preview.json`
para aprobación manual en `cover-preview.html`. **NUNCA modifica `items.jsonl`.**
Por defecto solo procesa portadas (`img_idx 0`).

> **Corrección (auditoría Fable 2026-07-11, hallazgo SC-1)**: esta ficha decía
> "Google Imágenes con fallback a Bing" sin mencionar Yandex como motor
> primario, y traía 4 datos desactualizados (umbral de hash con un "relax" que
> ya no existe, default de `--limit`, estado de `SERPER_API_KEY`, y le
> faltaban 4 flags). Regla PR-7: de acá en más esta ficha no reproduce
> constantes/umbrales/flags que puedan driftear del código — cita el símbolo y
> remite al [`SKILL.md`](watch-search-covers/SKILL.md), fuente única.

**Cómo funciona** (detalle completo en el propio `SKILL.md` — acá el resumen):
0. Verifica que Chrome esté disponible.
1. Plan de queries determinístico, compilado a `scripts/retrofit/sc_plan.py`
   (0 tokens LLM). Salta targets ya adjudicados por el skill (campo
   `match_dist` en cualquier estado — pending/approved/rejected) y los que
   fallaron hace menos de 30 días (salvo `--retry-failed`).
2. Por cada target, itera variantes (Yandex reverse primero, texto en Google
   después) hasta juntar varias candidatas verificadas o agotarlas.
3. Valida cada URL con `scripts/retrofit/sc_validate.py` (script permanente,
   fuente única con producción): exige identidad — `fetch_better_covers._same_cover()`,
   un AND-gate cuyo umbral real es la constante `fetch_better_covers.DEFAULT_MAX_HASH_DIST`
   (sin relax, a diferencia de lo que decía una versión anterior de esta
   ficha) — más ausencia de conflicto de metadata (otro volumen/ISBN) y
   calidad de display (`_is_soft_image()`, gotcha #98: descarta escaneos
   chicos y blandos). Solo pasa la MISMA portada en mejor resolución y buena
   calidad.
4. Guarda imágenes válidas en `data/images/` y las agrega a `cover_preview.json`
   con `confidence: "low"`, `status: "pending"`. Flush self-healing
   (`scripts/retrofit/sc_flush.py`) después de cada item.
5. (Opcional, `--serper-fallback`) invoca el motor de producción
   (`fetch_better_covers.py`, con `SERPER_API_KEY` **activa** en `.env` — no
   comentada) para reverse-image vía Serper Lens en los targets que quedaron
   en 0 matches. De pago; solo si el owner lo pide explícitamente.

**Umbral de calidad**: mismo valor que `scripts/audit/data_quality.py --px`
(el panel de calidad) — constante compartida
(`fetch_better_covers.LOW_QUALITY_PX`), no la dupliques acá.

**Args**: 8 flags, ninguno obligatorio — ver el `argument-hint` del
[`SKILL.md`](watch-search-covers/SKILL.md) para la lista completa
(`--limit`, `--slug`, `--include-no-image`, `--gallery-only`,
`--include-gallery`, `--retry-failed`, `--query-extra`, `--serper-fallback`).
Ojo: **sin `--limit` se procesan TODAS** las imágenes pendientes de la
corrida — no hay un default acotado (la ficha anterior decía "default 20",
error corregido en SC-1).

**Cuándo invocarlo**:
- Cuando quieras mejorar la calidad visual del catálogo (imágenes pequeñas o ausentes).
- Antes de publicar un build fresco si hay items con portadas de baja resolución.
- No integrar en el pipeline canónico automático — requiere decisión consciente.

**Tier de modelo (hallazgo F10)**: hilo principal; el loop es mecánico
(navegar + regex + subprocess) y el criterio vive en scripts —
`sonnet` alcanza de sobra, nunca hace falta `opus`.

---

## Workflow post-scrape recomendado

```
manga_watch.py scrape
       ↓ items.jsonl con series_key rough + sin standardized_at
/watch-standardize-catalog
       ↓ subagentes verifican/corrigen, marcan timestamp,
         loguean series desconocidas a unmapped_series.jsonl
/watch-enrich-series-aliases    (si aparecieron series_keys nuevas)
       ↓ consolida nuevas series multilingües
/watch-validate-rarity          (opcional — si hay rares por incertidumbre nuevos)
       ↓ 1 verificación web por edición → stock_status + re-derivación
/watch-search-covers            (opcional — si querés mejorar portadas pequeñas)
       ↓ candidatas en cover_preview.json → aprobar en cover-preview.html
build_web.py  (opcional)
       ↓ refresh del dashboard
```

Todos los skills son **idempotentes** y **incrementales**. Re-ejecutarlos
sin cambios en el corpus no rompe nada.

## Workflows (`.claude/workflows/`)

Un **workflow** NO es un skill: es un script JS que orquesta el mismo trabajo
que un skill haría manualmente, pero corriendo el fan-out de subagentes,
schemas de salida estructurada, checkpoints de progreso y gates de
verificación como CÓDIGO en vez de instrucciones en markdown para el modelo
principal. Se usa cuando el volumen justifica automatizar la orquestación
(muchos subagentes en waves, necesidad de resumir tras una interrupción). El
skill correspondiente sigue siendo la puerta de entrada — es el skill el que
decide, según el volumen, si conviene invocar el workflow o procesar inline.

Hay 2 workflows activos:

| Workflow | Invoca desde | Args | Qué hace |
|---|---|---|---|
| `watch-standardize-catalog.js` | `/watch-standardize-catalog` (Steps 3-10 son su fallback manual) | `{ limit?, force_all?, resume_progress? }` | Audit → Tier 1 determinístico → Tier 2/3 vía subagentes en chunks (agrupados por `group_key`, nunca separa hermanos de una misma coleccion/página) → merge + enforcer + validate_corpus (bloqueante) + slugs + traducción. |
| `listadomanga-audit.js` | `/listadomanga-audit` | `{ chrome_model?, resume?, apply? }` (`apply` default `false`) | Analiza parser/enforcer/validador, navega el sitio real con Chrome, sintetiza gaps priorizados. Sin `apply`, termina en `status: plan_ready` **sin tocar código** — el owner revisa el plan y relanza con `{apply:true, resume:true}` para que ejecute la Fase 5 (implementación), acotada a una allowlist dura de 3 archivos y protegida por una red de seguridad git (revert automático si algo falla). |

**Cuándo usar el skill vs el workflow — regla del umbral (`watch-standardize-catalog`)**:
el propio `SKILL.md` fija un único umbral de pendientes (ver su Step 1 — no lo
dupliques acá, cítalo) que decide: por debajo, procesar inline sin subagentes;
por encima, el workflow guardado es el camino preferido (el fallback manual con
subagentes hace lo mismo a mano si el tool `Workflow` no está disponible).

## Cómo agregar un skill nuevo

1. Crear el directorio `.claude/skills/<nombre>/` y dentro un archivo
   `SKILL.md` con frontmatter:
   ```yaml
   ---
   name: <nombre>
   description: Una descripción CLARA de cuándo y por qué invocarlo.
                Claude Code usa esta descripción para decidir activación.
   argument-hint: "[--flag-a VALUE] [--flag-b]"
   ---
   ```
   **`argument-hint` es obligatorio** si el skill acepta argumentos. Es la
   única pista que aparece en el tooltip de autocompletado de `/` — sin él
   el usuario no sabe qué puede pasarle. Usa corchetes para opcionales y
   ángulos para requeridos: `<fuente>`, `[--limit N]`, `[--dry-run]`.

   **NO** crear el skill como `.claude/skills/<nombre>.md` (archivo
   suelto) — ese formato no lo descubre Claude Code y el skill no
   aparecerá en el autocompletado de `/`.
2. Cuerpo en markdown con instrucciones paso-a-paso. Incluye snippets
   de bash/python que el skill debe ejecutar literalmente.
3. Listar el skill acá en este README + en CLAUDE.md (file map).
4. Mencionar en `docs/scraper/ARCHITECTURE.md` sección "Curation skills"
   (puntero corto — el detalle vive acá, no ahí).
5. Si el skill puede automatizarse via cron: mencionar el patrón
   `/schedule` o `/loop` apropiado.

## Anti-patterns

- ❌ Skills que duplican lo que un retrofit ya hace de forma mecánica.
  Si una regex resuelve el problema, retrofit; LLM es overkill.
- ❌ Skills que modifican datos sin trazabilidad (sin timestamp, sin
  log, sin backup). Cada cambio destructivo debe ser reversible.
- ❌ Skills que NO documentan cuándo invocarlos. La `description`
  frontmatter es crítica para que Claude active el skill correcto.
- ❌ Skills hardcoded a una corrida única (e.g. "procesa los 100
  primeros"). Deben ser incrementales — solo tocan lo pendiente.
