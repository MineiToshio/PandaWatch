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

### `/standardize-catalog`

**Propósito**: pasada 2 de la estandarización de schema. Procesa items
de `data/items.jsonl` que NO tienen el campo `standardized_at` —
típicamente items recién scrapeados que llegaron con asignación
heurística cruda (o sin asignación) del pipeline.

**Cómo funciona**:
1. Audita pendientes (filtra items sin `standardized_at`).
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

### `/enrich-series-aliases`

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
4. Corre backfill snippet para consolidar `items.jsonl`.
5. Trunca la queue (`data/unmapped_series.jsonl`).

**Cuándo invocarlo**:
- Después de `/standardize-catalog` cuando aparecieron series_keys
  nuevas.
- Semanal junto con el otro skill.
- Cuando ves la misma obra con nombres diferentes en el dashboard.

### `/evaluate-sources`

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

### `/review-rejected`

**Propósito**: revisar items que el usuario rechazó via el botón 👎 del
dashboard (`data/user_rejected.jsonl`), categorizar la causa raíz de
cada rechazo, y proponer mejoras concretas a los filtros del scraper.

**Cómo funciona**:
1. Carga y muestra la cola de rechazos (dedupando por `cluster_key`).
2. Clasifica cada item usando una taxonomía de 10 categorías (A–J):
   merchandising, trading cards, noticias/blogs, tomos regulares,
   source ruidosa, western comics, light novels, preferencia personal,
   falsa señal, selectores demasiado amplios.
3. Presenta propuestas numeradas al usuario — **espera confirmación**
   antes de aplicar.
4. Para cambios aprobados: edita `manga_watch.py` / `comics_blacklist.yml` /
   `sources.yml` + agrega tests en `tests/test_extraction.py`.
5. Corre pytest (debe quedar verde) y los retrofits correspondientes
   (`filter_non_manga.py`, `filter_collectible.py`, `rescore.py`).
6. Trunca `data/user_rejected.jsonl` (solo después de aplicar todos los
   cambios aprobados).
7. Actualiza CLAUDE.md "Last updated".

**Cuándo invocarlo**:
- Cuando `data/user_rejected.jsonl` tiene entradas (el usuario ha
  clickeado 👎 en el dashboard).
- Explícitamente al decir "revisar rechazados" o "mejorar los filtros".
- Periódicamente después de scrapes grandes (antes de commitear).

## Workflow post-scrape recomendado

```
manga_watch.py scrape
       ↓ items.jsonl con series_key rough + sin standardized_at
/standardize-catalog
       ↓ subagentes verifican/corrigen, marcan timestamp,
         loguean series desconocidas a unmapped_series.jsonl
/enrich-series-aliases
       ↓ consolida nuevas series multilingües
build_web.py  (opcional)
       ↓ refresh del dashboard
```

Ambos skills son **idempotentes** y **incrementales**. Re-ejecutarlos
sin cambios en el corpus no rompe nada.

## Cómo agregar un skill nuevo

1. Crear el directorio `.claude/skills/<nombre>/` y dentro un archivo
   `SKILL.md` con frontmatter:
   ```yaml
   ---
   name: <nombre>
   description: Una descripción CLARA de cuándo y por qué invocarlo.
                Claude Code usa esta descripción para decidir activación.
   ---
   ```
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
