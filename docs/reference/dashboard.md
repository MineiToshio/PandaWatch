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
Lo procesa el skill `/review-feedback`.

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
descriptiva y sólo refresca `_VOLATILE_FIELDS` (price, stock_type, sources, detected_at).
Retrofits saltean aprobados por defecto (`--include-approved` para forzar; los filtros
SIEMPRE los conservan). Skills los excluyen del set a modificar (pueden leerlos como
referencia, nunca sobreescribirlos).

Endpoints: `POST /api/approve {url, approved, reason?}` (todo el cluster) y
`POST /api/approve-edition {edition_key, approved, reason?}` (toda la edición, 1 write
atómico). UI: botón 👍/✓ + toggle candado al hover + badge ✓ + filtro sidebar "Estado de
revisión". Durabilidad: log append-only `data/approvals.jsonl` (cluster_key, url, action,
approved_at/by, reason, submitted_at + snapshot) → `apply_approvals.py` re-materializa
tras reconstruir el catálogo (match cluster_key, fallback url; idempotente).

