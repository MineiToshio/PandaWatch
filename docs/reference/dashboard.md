# Dashboard — curación humana (feedback / edición / aprobación)

> Documento de referencia de PandaWatch, cargado **bajo demanda** desde
> [CLAUDE.md](../../CLAUDE.md). Leelo cuando vayas a trabajar en este tema.

## Curación humana desde el dashboard

El footer del detalle (`view==='volume'` en `web/index.html`) tiene 3 flujos:
👍 aprobar, ✏️ editar info, 👎 feedback/curación. Al modificar cualquiera,
actualizá el handler en `serve.py` Y el método en `web/index.html` juntos.

### 👎 Feedback / curación → `data/feedback.jsonl` (gi, append-only)

Panel unificado: reportar un problema (item NO se elimina) o 3 acciones
operativas inmediatas. El campo `action` distingue el tipo:

| `action` | Efecto en items.jsonl | Endpoint | Campos extra |
|---|---|---|---|
| `feedback` | ninguno | `POST /api/feedback` | (url, reason) |
| `move` | cambia edition_key/cluster_key/series_key + consolida | `POST /api/curation/move` | from_edition, to_edition |
| `merge` | fusiona 2 items (merge_cluster, no borra el peor) | `POST /api/curation/merge` | duplicate_of, kept_url, dropped_url |
| `remove` | edition_key="" + cluster standalone | `POST /api/curation/remove` | from_edition |

`GET /api/editions/search?q=` = autocomplete de ediciones. Schema de feedback.jsonl:
url + action + reason + submitted_at + spread del item. Sin auth, POST capado 100 kB.
Lo procesa el skill `/watch-review-feedback`.

### ✏️ Edición inline de la metadata → `POST /api/item/update {url, fields}`

Modo edición in-situ: la metadata se vuelve un form dinámico (`buildEditSchema`
infiere el control por tipo: text/textarea/number/list/json). Se edita CUALQUIER
atributo MENOS dos grupos (modelo denylist — "editar todo menos imágenes"):
- `_PROTECTED_ITEM_FIELDS` (imágenes: image_url, image_local, images,
  images_backfilled_at) — se ignoran si llegan; tienen su propio gestor.
- `_ROW_LOCAL_FIELDS` (url, slug, cluster_key, content_hash, source_url, sources)
  — editables pero SÓLO en la fila abierta (per-fila, no del producto).

Los campos de PRODUCTO se propagan a TODAS las filas del cluster (`_apply_item_update`),
así no reaparecen desde una hermana al re-mergear. El frontend manda sólo el diff (el
log registra el cambio real). NO recomputa cluster_key (eso es `/api/curation/move`).
Descripción: se editan `description_es` (override ES, lo que se muestra) y `description`
(original, lo que usa detect_signals) por separado. `@_serialized` (gotcha #34), body
200 kB. Auditoría → `data/edits.jsonl` (gi, sin replay script: re-editar o aprobar si se
reconstruye el catálogo). Durabilidad: items con `standardized_at` preservan curados vía
`_CURATED_FIELDS`; los no-curados persisten hasta el próximo re-scrape de esa URL.

### 👍 Aprobación humana (golden records) — `approved_at`

Patrón golden record / human-in-the-loop: un item aprobado queda **congelado** y sirve
de referencia. Equivalente humano de `standardized_at`. Schema (sticky, en
`_CURATED_FIELDS`): `approved_at` (presencia = aprobado) + `approved_by="owner"`.
Granularidad = por cluster (marca todas las filas del cluster_key).

Congelado (`is_approved()` en manga_watch.py): `append_jsonl` congela toda la metadata
descriptiva y sólo refresca `_VOLATILE_FIELDS` (stock_type, sources, detected_at).
Retrofits saltean aprobados por defecto (`--include-approved` para forzar; los filtros
SIEMPRE los conservan). Skills los excluyen del set a modificar (pueden leerlos como
referencia, nunca sobreescribirlos).

Endpoints: `POST /api/approve {url, approved, reason?}` (todo el cluster) y
`POST /api/approve-edition {edition_key, approved, reason?}` (toda la edición, 1 write
atómico). UI: botón 👍/✓ + toggle candado al hover + badge ✓ + filtro sidebar "Estado de
revisión". Durabilidad: log append-only `data/approvals.jsonl` (cluster_key, url, action,
approved_at/by, reason, submitted_at + snapshot) → `apply_approvals.py` re-materializa
tras reconstruir el catálogo (match cluster_key, fallback url; idempotente).

## Cover-preview — endpoint puntual por slug

`GET /api/item?slug=<slug>` devuelve la fila de `items.jsonl` con ese slug (404 si no existe).
Con `?cluster=1` incluye `cluster_rows` (todas las filas del mismo `cluster_key`) para que la lógica
de `_clusterImagesFor` funcione sin descargar `items.jsonl` completo (~25 MB). La UI cachea las
filas en `itemsBySlug` — las llamadas repetidas no hacen fetch.

El badge de verificación en la card y en el modal ahora es **tri-estado**: verde `✓ verificada` si
`verified === true`; amarillo `⚠ sin verificar` si `verified === false`; **sin badge** si el campo
no existe (evita 100% de ruido amarillo con el corpus que no trae el campo).

La barra `.actions` es `position: sticky; top: 0` con fondo sólido y z-index 50 — "Aplicar aprobadas"
siempre visible. Cuando `pendingCount() === 0 && approvedCount() > 0` aparece un callout verde con
el botón de aplicar. Los botones de acción se deshabilitan (`isSaving`) mientras hay un POST en vuelo.

## Cover-preview — carga con sincronización automática

Al cargar la cola, el frontend llama `GET /api/cover-preview` (un solo request): el servidor
carga `cover_preview.json`, sincroniza contra `items.jsonl` vía `sync_preview()` de
`scripts/retrofit/sync_cover_preview.py`, persiste los cambios atómicamente si los hubo, y
responde `{"entries": [...], "mtime": <st_mtime_ns>, "synced": {stats}}`. Si el endpoint no
está disponible (servidor viejo), el frontend cae al fetch estático `cover_preview.json` +
`GET /api/cover-preview-meta`. Si `synced` incluye cambios (> 0), se muestra un toast.

## Cover-preview — guard de concurrencia optimista

`loadedMtime` viene en la respuesta de `GET /api/cover-preview` (el mtime post-sync).
Cada POST de save incluye `expected_mtime: loadedMtime`; si el mtime del archivo en disco
no coincide, el servidor responde **409 `{"error":"stale"}`** sin escribir. El frontend
muestra un aviso y recarga la cola — nunca reintenta el save stale. Clientes sin
`expected_mtime` (scripts/legado) siguen con el comportamiento anterior.

## Cover-preview (`web/cover-preview.html`) — atajos de teclado

El modal de comparación de portadas (`compareEntry` en el state Alpine) tiene atajos
**sólo cuando el modal está abierto y ningún `<input>`/`<textarea>`/`<select>` tiene
focus** (guard `document.activeElement.tagName`):

| Tecla | Acción |
|---|---|
| `A` | Aprobar la candidata visible (equivale a "✓ Aprobar") |
| `R` | Rechazar la candidata visible (equivale a "✕ Rechazar") |
| `N` | Saltar al siguiente producto con candidatas pendientes |
| `P` | Saltar al producto anterior con candidatas pendientes |
| `←` / `→` | Navegar entre candidatas del mismo producto |
| `Esc` | Cerrar el modal |

Un hint `A aprobar · R rechazar · N/P producto` aparece en el footer del modal (alineado
a la derecha, muted). `jumpToNextEntry(dir)` en Alpine navega a la primera candidata
pendiente del entry siguiente/anterior (sin wrap si no hay).

## Carga de datos del catálogo — vivo primero, embebido como fallback

`loadItems()` en `web/index.html` prioriza **items.jsonl EN VIVO** (decisión #5):
servido vía `serve.py`, el dashboard refleja siempre el estado actual tras cualquier
retrofit/curación sin re-correr `build_web.py`. La copia embebida
(`<script id="manga-data">`, generada por build_web) es SOLO fallback: `file://`
(doble-click) o fetch fallido. Antes era al revés (embebido primero) y el dashboard
servido mostraba datos stale hasta el próximo build — corregido 2026-06-12.
