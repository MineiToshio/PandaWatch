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

### `/watch-standardize-catalog`

**Propósito**: pasada 2 de la estandarización de schema. Procesa items
de `data/items.jsonl` que NO tienen el campo `standardized_at` —
típicamente items recién scrapeados que llegaron con asignación
heurística cruda (o sin asignación) del pipeline.

**Cómo funciona**:
1. Audita pendientes (filtra items sin `standardized_at` **y sin
   `approved_at`** — los golden records aprobados por el owner nunca se
   re-procesan; se pueden leer como referencia pero jamás se sobreescriben).
2. Particiona en chunks de ~150-200.
3. Delega a subagentes paralelos (7 por wave) que re-derivan
   series_key/edition_key/volume/title_standardized desde cero via LLM.
4. Merge: aplica `canonical_series_key()` de `series_aliases.yml`,
   dedupea por `(series_key, edition_key, volume)`, mueve no-manga
   a `data/non_manga_blacklist.jsonl`.
5. Marca cada item con `standardized_at`.

**Cuándo invocarlo**:
- Después de cada `manga_watch.py` scrape (items nuevos vienen sin
  `standardized_at`).
- Antes de publicar un build fresco del dashboard.
- Semanal como pasada de curación.

**Modo `--force-all`**: snippet embebido en el skill que limpia
`standardized_at` de TODOS los items para forzar re-procesamiento
(útil al cambiar reglas de estandarización mayor).

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
  "volume": "1",
  "title_standardized": "Berserk Deluxe 1"
}
```

### `/watch-enrich-series-aliases`

**Propósito**: procesar la queue de series sin canonical
(`data/unmapped_series.jsonl`) y mantener `data/series_aliases.yml`
actualizado con traducciones multilingües.

**Cómo funciona**:
1. Audita la queue (`scripts/audit/unmapped_series.py`).
2. Para cada `series_key` no canónico, decide:
   - **Merge** como alias de un canonical existente (fuzzy match ≥0.8).
   - **Create** nuevo canonical via Anilist API (`graphql.anilist.co`).
     Saca `title.english/romaji/native + synonyms[]`, filtra
     alfabetos no-target (cyrillic, arabic, hebrew, hangul, thai) +
     aliases ambiguos genéricos.
   - **Skip** si confidence baja + item count bajo (esperar más data).
3. Edita `data/series_aliases.yml` in-place.
4. Corre backfill snippet para consolidar `items.jsonl` (**salta items con
   `approved_at`** — no remapea golden records).
5. Trunca la queue (`data/unmapped_series.jsonl`).

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

**Cómo funciona**:
1. Parsea la lista de candidatas del mensaje del usuario.
2. Lanza un subagente por fuente en paralelo. Cada subagente:
   - Fetchea el listing principal y 5 items de detalle.
   - Evalúa: Content Fit (% ediciones especiales reales), campos mínimos
     (serie, tipo de edición, editorial, foto de portada), y — **crítico** —
     si la fuente cubre extras/bonuses, verifica que haya foto del EXTRA en
     sí (no solo la portada del manga).
   - Estima escala y factibilidad técnica.
3. Para fuentes que pasan el filtro básico: cruza muestra con `items.jsonl`
   para calcular % de overlap con el corpus existente.
4. Compila reporte: tabla resumen (✅/⚠️/❌) + detalle solo para viables.

**Output** (no implementación):
- Tabla de viabilidad con veredicto y razón por fuente.
- Para viables: qué aporta, qué falta, acción recomendada
  (`Agregar` / `Reemplaza [X]` / `Complementa [X]`).

**Cuándo invocarlo**:
- Antes de implementar cualquier fuente nueva.
- Al recibir una lista de sitios a evaluar ("evalúa estas páginas").
- Cuando una fuente existente parece redundante con una nueva.

### `/watch-review-feedback`

**Propósito**: revisar el feedback que el usuario dejó via el botón 👎 del
dashboard (`data/feedback.jsonl`). Cada entrada ya contiene todos los campos
del item más el motivo. Categoriza cada feedback (problema de filtro vs.
problema de calidad de datos), propone fixes concretos, aplica los aprobados
y trunca la queue.

**Cómo funciona**:
1. Carga la queue (`data/feedback.jsonl` — ya incluye campos completos del item, sin JOIN).
2. Clasifica cada item con taxonomía de 14 categorías:
   - **A–J** (filtros/catálogo): merchandising, trading cards, noticias, tomos
     regulares, source ruidosa, western comics, light novels, preferencia personal,
     falsa señal, selectores amplios.
   - **K–N** (calidad de datos): portada equivocada, metadata incorrecta,
     series_key/edition_key mal asignado, título con basura del scraper.
3. Para problemas de filtro: escanea el corpus buscando más items afectados
   por el mismo patrón, presenta propuestas numeradas y **espera confirmación**.
4. Aplica cambios aprobados: edita `manga_watch.py` / `comics_blacklist.yml` /
   `sources.yml` / `series_aliases.yml` / o correcciones directas en `items.jsonl`.
   **Golden records guard**: si un fix de calidad de datos (K–N) tocaría un item
   con `approved_at`, NO se auto-edita — se consulta al owner primero.
5. Agrega tests y corre pytest (solo para cambios de filtros).
6. Corre retrofits correspondientes (`filter_non_manga.py`, `filter_collectible.py`,
   `rescore.py`, `backfill_metadata.py`, `clean_titles.py`, etc.).
7. Trunca `data/feedback.jsonl`.
8. Actualiza CLAUDE.md "Last updated".

**Cuándo invocarlo**:
- Cuando `data/feedback.jsonl` tiene entradas (el usuario ha clickeado 👎).
- Al decir "revisar feedback", "mejorar los filtros", "corregir datos".
- Periódicamente después de scrapes grandes.

### `/watch-validate-rarity`

**Propósito**: verificar vía búsqueda web si los **boxsets y artbooks de
publishers grandes** que tienen `rarity="rare"` por default están
actualmente en stock (→ `common`) o no (→ mantener `rare`). Solo procesa
items sin `rarity_verified_at` (incremental). Liviano: agrupa por
`edition_key` (1 búsqueda por edición, no por volumen) y cap de 60
candidatos por corrida.

**Cómo funciona**:
1. Identifica items con `rarity="rare"`, sin `rarity_verified_at`,
   `product_type` en `{boxset, artbook, fanbook, manga}`, y publisher grande.
2. Agrupa por `edition_key` → toma el representativo de mayor score.
3. Busca en el retailer del país (amazon.fr/it/de/es/com, cdjapan.co.jp)
   si está en stock hoy.
4. Actualiza `rarity` a `common` si confirma stock activo; deja `rare` si
   no encontrado o solo segunda mano.
5. Marca `rarity_verified_at` en cada item procesado.

**Cuándo invocarlo**:
- Después de scrapes grandes que trajeron boxsets/artbooks nuevos.
- No para corridas delta diarias (10-20 items nuevos, el default `rare` está bien).
- Nunca integrar en `/watch-standardize-catalog` — separa el costo de tokens.

---

### `/watch-search-covers`

**Propósito**: buscar portadas en alta resolución para items con imagen de baja
calidad (`image_local` < `min-pixels` px) o sin imagen. Usa **Chrome exclusivamente**
(`mcp__Claude_in_Chrome__*`) para navegar **Google Imágenes** (vista `udm=2`), con **fallback
a Bing** si Google muestra un consent wall. Escribe candidatas a `data/cover_preview.json` para
aprobación manual en `cover-preview.html`. **NUNCA modifica `items.jsonl`.**

> **Google vs Bing (verificado 2026-06-06)**: versiones viejas usaban Bing porque el método
> antiguo de Google (patrón `"ou":"..."`) da vacío. Pero en `udm=2` las URLs full-res SÍ están
> en el HTML crudo y se extraen con regex (corta antes de `?` → sin query strings → sin bloqueo
> del MCP). Solo Google **Lens** (reversa por foto) sigue bloqueado. Por eso ahora el default es
> Google (preferencia del owner) y Bing queda de fallback.

**Cómo funciona**:
1. Verifica que Chrome esté disponible (`mcp__Claude_in_Chrome__list_connected_browsers`).
2. Filtra `items.jsonl` para encontrar items cuya imagen sea menor a `min-pixels` (o sin imagen con `--include-no-image`), saltando los que ya tienen candidatas pendientes.
3. Para cada item arma fuentes y las **itera** hasta juntar 3 matches verificados o agotarlas. **Primera fuente: Yandex búsqueda-por-foto** (`yandex.com/images/search?rpt=imageview&url=<image_url>` — la imagen actual como consulta; el mejor motor reverse gratis, sin captcha). **Luego: variantes de texto con contexto** (serie + volumen + tipo de edición + editorial + "portada" en el idioma, vía `fetch_better_covers._COVER_TERM`/`_EDITION_HINT`/`_simplify_publisher`) en Google `udm=2`. En ambas extrae las URLs full-res con regex sobre el `innerHTML` (el regex corta antes de `?` → sin query strings → sin bloqueo). Fallback a Bing (`a.iusc[m].murl`) si Google muestra consent wall; salta Yandex si pide captcha.
4. Valida cada URL con Python: píxeles ≥ 1.5× actual, y **`fetch_better_covers._same_cover()`** — aspect ratio ±25% + aHash Hamming ≤ `MAX_HASH_DIST` (10 base; `_same_cover` relaja +4 para portadas actuales < 30k px). Solo pasa si es **la MISMA portada en mejor resolución** (otro volumen / edición / arte = hash distinto = descartada). Items sin imagen actual (`--include-no-image`) no se pueden verificar → quedan `verified: false`. Esto es lo que elimina las candidatas no relacionadas que antes se colaban (el filtro viejo de "Hamming > 3" hacía justo lo contrario: descartaba la misma portada y dejaba pasar las distintas).
5. Guarda imágenes válidas en `data/images/` y las agrega a `cover_preview.json` con `confidence: "low"`, `status: "pending"`, más `match_dist`/`verified`. Flush **self-healing** después de cada item (acumulador propio + reescritura completa → resiste un save concurrente del dashboard).

> **Motores reverse-image — comparativa probada 2026-06-06**: **Yandex** (`rpt=imageview`) es el mejor gratis: accesible, sin captcha, devuelve portadas del tomo/edición correctos → es la fuente primaria del skill. **Google Lens** es accesible (regex sobre `innerHTML`, NO leer `location.href` que dispara `[BLOCKED]`) pero **inefectivo** con thumbnails de 150×150: cae en matching a nivel franquicia (fan art, wikis, merch, Mercari) → 0 matches. **Bing Visual Search** redirige a búsqueda web de entidad y se bloquea. **Serper Lens** (`fetch_better_covers._search_serper_lens`, `SERPER_API_KEY` de pago, comentada en `.env`) es la reversa server-side de mejor calidad. **Limitación de fondo**: el catálogo son ediciones especiales; texto y reversa suelen traer la edición regular/hermana (arte distinto) → `_same_cover` la rechaza, así que varios items quedan sin candidata (el hi-res del scan especial exacto no está indexado). Esperado, no bug.

**Umbral de calidad**: 90 000 px — mismo valor que `data_quality.py --px` (el panel de
calidad). Si el panel lo marca como "pixelada", este skill lo procesa.

**Args opcionales**:
- `--limit N` (default 20) — máximo de items por sesión
- `--slug SLUG` — procesar solo un item específico
- `--include-no-image` — incluir items sin ninguna imagen
- `--query-extra "texto"` — añadir texto al final de cada query de búsqueda

**Cuándo invocarlo**:
- Cuando quieras mejorar la calidad visual del catálogo (imágenes pequeñas o ausentes).
- Antes de publicar un build fresco si hay items con portadas de baja resolución.
- No integrar en el pipeline canónico automático — requiere decisión consciente.

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
/watch-validate-rarity          (opcional — solo si scrape trajo boxsets/artbooks)
       ↓ 1 búsqueda web por edición, actualiza common/rare
/watch-search-covers            (opcional — si querés mejorar portadas pequeñas)
       ↓ candidatas en cover_preview.json → aprobar en cover-preview.html
build_web.py  (opcional)
       ↓ refresh del dashboard
```

Todos los skills son **idempotentes** y **incrementales**. Re-ejecutarlos
sin cambios en el corpus no rompe nada.

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
4. Listar en `docs/ARCHITECTURE.md` sección "Curation skills" con
   detalles arquitectónicos.
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
