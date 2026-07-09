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

**Guard anti-doble-dislike (2026-06-21).** Un item ya reportado NO se puede volver a
reportar hasta que el feedback se procese (la cola se trunca → vuelve a habilitarse).
Dos capas: **(1) backend autoritativo** — `_handle_feedback` consulta `_url_in_feedback(url)`
y, si la URL ya está en `feedback.jsonl`, responde `{"ok":true,"already_reported":true}`
**sin escribir** (idempotente, a prueba de doble-click/retry — antes hacía append ciego).
**(2) frontend UX** — `loadReportedUrls()` levanta las URLs reportadas al cargar; con el
item reportado, `canSubmitCuration()` devuelve `false` (botón "Aplicar" deshabilitado) y el
panel de "Mala elección" muestra un aviso ámbar "Ya reportado — pendiente de procesar". El
badge "⚠ Reportado" ya existía en card/detalle. (El guard cubre la acción `feedback`; move/
merge/remove son operaciones estructurales distintas.) Ver gotcha #105.

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

## Lock de scrape — 423 en endpoints de escritura (2026-07-07)

Un scrape en curso (`data/.scrape.lock`, mismo formato que `acquire_lock()` en
`scrape_delta.sh`/`scrape_full.sh`: mkdir atómico + PID en un archivo `pid`) re-escribe
`data/items.jsonl` al final de cada retrofit (`append_jsonl`/`_atomic_write`). Si un
endpoint de curación del dashboard escribe AL MISMO TIEMPO, el que termine último gana
y el otro desaparece silenciosamente (lost update) — `_ITEMS_LOCK` sólo serializa
requests DENTRO del proceso de `serve.py`, no protege contra el proceso *separado* del
scrape.

**Fix**: `_reject_if_scrape_locked()` chequea `data/.scrape.lock` ANTES de escribir y
responde **423** (`{"error": "scrape en curso, reintentá al terminar", "pid": N}`) en
vez de arriesgar la pérdida — NUNCA espera/bloquea (colgaría la UI hasta que un scrape
de horas termine); el owner reintenta después. Un lock STALE (el PID que lo creó ya no
existe, `os.kill(pid, 0)` → `ProcessLookupError`) se trata como "sin lock" (no lo toca,
igual que el fallback de `acquire_lock()` en los `.sh`, que se re-adquiere solo).
Aplica a los **11 endpoints** que escriben `items.jsonl`: `/api/curation/{move,merge,
remove}`, `/api/item/update`, `/api/approve`, `/api/approve-edition`, `/api/batch/
{approve,move}`, `/api/dup-merge`, `/api/save-cover-preview` (cuando aplica sync),
`/api/image-manager/save`.

**Caso hermano — dos mutadores del Panel de Control pisándose entre sí (S10,
2026-07-08)**: el 423 de arriba cubre dashboard-vs-scrape (proceso externo);
los retrofits lanzados desde `web/panel.html` (`POST /api/run`) NO tienen ese
lock de archivo entre sí, así que lanzar dos a la vez (ej. `filter_non_manga`
+ `clean_titles`) también pisaba el último write. Fix paralelo: cada entrada
de `scripts/script_registry.py` declara `mutates_items: bool`; `/api/run`
responde **409** si ya hay un job `"running"` con `mutates_items: true` —
check + registro del job nuevo son atómicos (mismo lock que
`JobManager.start()`). Detalle completo en `docs/admin/README.md`.

## Cover-preview — endpoint puntual por slug

`GET /api/item?slug=<slug>` devuelve la fila de `items.jsonl` con ese slug (404 si no existe).
Con `?cluster=1` incluye `cluster_rows` (todas las filas del mismo `cluster_key`) para que la lógica
de `_clusterImagesFor` funcione sin descargar `items.jsonl` completo (~25 MB). La UI cachea las
filas en `itemsBySlug` — las llamadas repetidas no hacen fetch.

El badge de verificación en la card y en el modal ahora es **tri-estado**: verde `✓ verificada` si
`verified === true`; amarillo `⚠ sin verificar` si `verified === false` **o si `match_dist == null`**
(criterio extendido 2026-07-08 — `isUnverified(c)` en Alpine; la cola tiene ~339 candidatas sin
`match_dist`, exactamente las que nunca pasaron verificación de identidad, y antes no mostraban el
aviso si `verified` tampoco estaba seteado); **sin badge** solo cuando `verified === true` explícito
(manda siempre, aunque `match_dist` sea null).

La barra `.actions` es `position: sticky; top: 0` con fondo sólido y z-index 50 — "Aplicar aprobadas"
siempre visible. Cuando `pendingCount() === 0 && approvedCount() > 0` aparece un callout verde con
el botón de aplicar. Los botones de acción se deshabilitan (`isSaving`) mientras hay un POST en vuelo.

## Cover-preview — carga con sincronización automática

Al cargar la cola, el frontend llama `GET /api/cover-preview` (un solo request): el servidor
carga `cover_preview.json`, sincroniza contra `items.jsonl` vía `sync_preview()` de
`scripts/retrofit/sync_cover_preview.py`, persiste los cambios atómicamente si los hubo, y
responde `{"entries": [...], "mtime": "<st_mtime_ns como string>", "synced": {stats},
"approved_unapplied": <int>}`. Si el endpoint no
está disponible (servidor viejo), el frontend cae al fetch estático `cover_preview.json` +
`GET /api/cover-preview-meta` (y recalcula `approved_unapplied` del lado cliente vía
`approvedCount()`). Si `synced` incluye cambios (> 0), se muestra un toast.

**Degradación a solo-lectura (2026-07-08, hallazgo #1, ALTA)**: antes de sincronizar, el
servidor corre `sync_cover_preview.catalog_is_sane(preview, items_by_slug,
malformed_lines)`. Si `items.jsonl` no cargó bien (ausente, truncado, o con líneas que no
parsean como JSON) — o si >20% de los slugs de la cola no matchean ningún item del
catálogo — el GET NO sincroniza ni persiste nada: devuelve la cola TAL CUAL está en disco
(`synced: {"degraded": true, "reason": "<motivo>"}`) y el servidor loguea `[serve][WARN]`
a stderr. Antes de este guard, un `items.jsonl` corrupto en el momento equivocado hacía
que este mismo GET vaciara la cola de aprobación entera (cada slug se veía como "item
borrado"). El frontend no necesita tratar `synced.degraded` de forma especial — `entries`
sigue siendo la cola completa, sólo que sin refrescar contra el catálogo en ese request.

**Orden best-first de la cola (2026-07-08)**: `sortBestFirst()` en Alpine reordena `entries`
tras cada carga (ambas rutas: `GET /api/cover-preview` y el fallback estático). Prioridad:
(1) entries con alguna candidata **pendiente** con `match_dist` numérico, ascendente por el
mínimo — las más seguras primero; (2) entries con candidatas pendientes de `match_dist == null`
(sin verificar); (3) entries sin pendientes, al final. Estable (desempata por posición original)
para no reordenar sin motivo real entre recargas. La navegación `N`/`P` del modal sigue el mismo
orden ya materializado en `entries` — no hay divergencia entre el orden visible y el de salto.

**`approved_unapplied` (P24, 2026-07-07)** — contador AUTORITATIVO (server-side) de
candidatas con `status=approved` que TODAVÍA no se aplicaron a `items.jsonl`
(`_count_approved_unapplied()`, cuenta ambos schemas: multi-candidato
`candidates[].status` y el legado plano `status` a nivel de entry). Existe porque
"aprobar" (👍, guarda `status=approved` en `cover_preview.json`) y "aplicar" (POST
`/api/apply-cover-preview`, escribe `items.jsonl`) son pasos DESACOPLADOS — una
candidata puede quedar aprobada-pero-invisible si el owner cierra la pestaña antes de
aplicar. Cuando `approved_unapplied > 0`, `cover-preview.html` muestra un banner verde
prominente apenas carga, con el conteo y un botón **"✓ Aplicar ahora"** (llama
`applyApproved()` directo, sin scroll a la barra sticky de abajo).

## Cover-preview — guard de concurrencia optimista

`loadedMtime` viene en la respuesta de `GET /api/cover-preview` (el mtime post-sync) y es un
**token STRING opaco** (`st_mtime_ns` serializado como string — un Number de JS redondearía
todo entero > 2^53 y daría 409 espurio en cada save, gotcha #79; helpers `_mtime_token()` /
`_mtime_matches()` en serve.py). Cada POST de save incluye `expected_mtime: loadedMtime`; si
el token no coincide con el del archivo en disco, el servidor responde **409
`{"error":"stale","mtime":"<token>"}`** sin escribir. El frontend muestra un aviso y recarga
la cola — nunca reintenta el save stale. Clientes sin `expected_mtime` (scripts/legado)
siguen con el comportamiento anterior; si un cliente viejo manda un Number, el servidor
compara en espacio double para no rechazarlo de más.

`POST /api/apply-cover-preview` acepta el mismo guard opcional (body
`{"expected_mtime": "<token>"}`): si la cola en disco no es la que el owner estaba viendo,
responde 409 sin aplicar nada. El frontend lo manda siempre y, antes del apply, espera los
guardados en vuelo (el apply lee la cola del DISCO).

En el frontend todos los guardados pasan por una ruta única (`save()` → `_doSave()`): una
**cola en serie** garantiza que dos acciones rápidas (p. ej. atajos A/R, que no pasan por
botones deshabilitados) salgan cada una con el token que dejó la anterior, en vez de
competir y generar 409 entre sí. Si un save falla (no-409), la UI recarga la cola para no
mostrar como guardado algo que no se persistió. `deleteGalleryImage` y `flagIrrelevant`
usan esta misma ruta (antes duplicaban el fetch del save inline).

**👎 Reportar desde el cover review (2026-06-21).** Cada entry tiene, además de
"Excluir", un botón **👎 Reportar** con la MISMA funcionalidad que el dislike del
dashboard. `toggleReport(entry)` abre un **editor de motivo inline** (un `<input>` con
Enviar/Cancelar, Enter envía / Esc cierra) — NO usa `prompt()`, que algunos navegadores
suprimen (gotcha #106). `submitReport(entry)` resuelve la URL del item (`/api/item?slug=`)
y hace `POST /api/feedback` con `{title, url, reason}`. A diferencia de "Excluir"
(`flagIrrelevant`, motivo fijo "irrelevante" + saca de la cola), el 👎 **NO elimina** la
entry — solo la reporta, igual que en el catálogo. El estado "reportado" se levanta de
`feedback.jsonl` al cargar (`loadReportedSlugs()`, indexado por `slug` —cada fila de
feedback es el item completo + reason) y el botón pasa a "✓ Reportado" deshabilitado; se
rehabilita cuando la cola se procesa y trunca. El backend dedup-ea por URL
(`already_reported`), así que el guard anti-doble-dislike vale acá también. Ver gotchas #105, #106.

## Cover-preview (`web/cover-preview.html`) — atajos de teclado

El modal de comparación de portadas (`compareEntry` en el state Alpine) tiene atajos
**sólo cuando el modal está abierto y ningún `<input>`/`<textarea>`/`<select>` tiene
focus** (guard `document.activeElement.tagName`):

| Tecla | Acción |
|---|---|
| `A` | Aprobar la candidata visible (equivale a "✓ Aprobar") |
| `R` | Rechazar la candidata visible (equivale a "✕ Rechazar") |
| `1`-`5` | Rechazar con motivo en un solo paso (ver abajo) — o cambiar el motivo si ya estaba rechazada |
| `N` | Saltar al siguiente producto con candidatas pendientes |
| `P` | Saltar al producto anterior con candidatas pendientes |
| `←` / `→` | Navegar entre candidatas del mismo producto |
| `Esc` | Cerrar el modal |

Un hint `A aprobar · R rechazar · 1-5 motivo · N/P producto` aparece en el footer del modal
(alineado a la derecha, muted). `jumpToNextEntry(dir)` en Alpine navega a la primera candidata
pendiente del entry siguiente/anterior (sin wrap si no hay).

## Cover-preview — chips de motivo de rechazo (2026-07-08, sin fricción)

**Restricción dura**: el rechazo sigue siendo 1 tecla/1 clic (`R` o `✕`) y el motivo es
**100% opcional** — se persiste inmediatamente al rechazar, ANTES de elegir motivo. Los
chips nunca bloquean ni agregan un paso al flujo de rechazo pelado.

Tras rechazar una candidata (card compacta o modal), aparece una fila `.reject-chips` con
6 chips de 1 clic: `otro_tomo`, `otra_edicion`, `arte_sin_logo`, `no_es_la_obra`,
`mala_calidad`, `otros…`. Clickear un chip (no-"otros") setea `cand.reject_reason = "<motivo>"`
y guarda ya (`pickReason()` en Alpine). El chip activo se resalta (`rejectReasonKey(c)` compara
contra `cand.reject_reason`), incluyendo al recargar la página — el chip actúa como badge de
motivo ya elegido, no solo como control.

**"Otros…"** abre un `<input>` de texto libre inline (`x-show`, NO `x-model` sobre un
`<template x-if>` — ver gotcha de implementación abajo). El foco automático SOLO ocurre si el
chip se clickeó (nunca al abrirse desde las teclas 1-5, que mapean únicamente a los otros 5
motivos). El texto se confirma con Enter o blur (`confirmOtros()`) y se guarda como
`reject_reason: "otros:<texto>"`.

**Teclas 1-5 en el modal** (`handleReasonKey($event)`, mismo guard de foco que A/R/N/P):
si la candidata visible está `pending`, la tecla rechaza + setea el motivo N-ésimo + avanza
automático en un solo paso (mismo comportamiento que `R`, vía `setStatus(...,'rejected')` con
`reject_reason` ya seteado antes del save). Si ya está `rejected`, la tecla solo cambia el
motivo (sin avanzar, sin cerrar el modal).

**Persistencia**: `reject_reason` viaja en el objeto candidata por `wrap()` →
`cleanPayload()` → `POST /api/save-cover-preview` → `cover_preview.json` (el backend no
filtra campos, escribe el payload completo tal cual). `sync_preview()` en
`scripts/retrofit/sync_cover_preview.py` preserva el campo intacto para candidatas no-pending
(nunca las toca) y en el `{**cand, ...}` de recompute de píxeles para las pendientes. Los
campos UI-only `_otrosOpen`/`_otrosText` (estado transitorio del input) NUNCA viajan al
servidor.

**Gotcha de implementación**: el input de "otros" usa `x-show`, no `<template x-if>`. Cerrar
el input DESDE su propio handler (`@blur`/`@keydown.enter` → `confirmOtros()` → 
`_otrosOpen = false`) mientras el nodo está enfocado y esa asignación dispara la REMOCIÓN del
nodo del DOM (lo que pasa con `x-if`) hace que el navegador dispare un `blur` extra sobre un
nodo a medio desmontar — Alpine tira `"Cannot set properties of undefined (setting
'textContent')"`. `x-show` sólo alterna `display`, nunca remueve el nodo, así que el handler
termina su ciclo de vida normalmente antes de ocultarse.

## Carga de datos del catálogo — vivo primero, embed VACÍO por default (2026-06-14)

`loadItems()` en `web/index.html` prioriza **items.jsonl EN VIVO** (decisión #5):
servido vía `serve.py`, el dashboard refleja siempre el estado actual tras cualquier
retrofit/curación sin re-correr `build_web.py`. La copia embebida
(`<script id="manga-data">`) es SOLO fallback: `file://` (doble-click) o fetch fallido.

**Optimización 2026-06-14 (peso de carga)**: `build_web.py` **ya NO embebe el catálogo
por defecto** — deja el embed vacío (`[]`). Antes lo poblaba con los ~13k items (~30 MB
en una sola línea) que el navegador descargaba y parseaba en cada carga **además** del
fetch en vivo → trabajo doble. Ahora `index.html` pesa **~139 KB** (era ~30 MB). El embed
sólo se llena con `python scripts/build_web.py --embed` (para el fallback `file://`); el
default exporta `series_aliases.json` y vacía el embed. Como el owner siempre usa `serve.py`,
no se pierde nada en la práctica. Ver gotcha #100.

**Servido gzip (`serve.py`, 2026-06-14)**: el fallthrough estático comprime al vuelo los
estáticos de TEXTO grandes (`.jsonl`/`.json`/`.html`/`.js`/`.css`/… > 1 KB) cuando el cliente
manda `Accept-Encoding: gzip`. `items.jsonl` baja de ~31 MB a **~4 MB** de transferencia
(7.8×). Cache por `mtime_ns` (`_gzip_file()`) para no re-comprimir en cada carga. La allowlist
de seguridad sigue siendo el gate (`_resolve_static` reusa la misma normalización; `/.env` →
403). En localhost el ahorro de transferencia es chico (el cuello es el parseo del JSON, igual
con o sin gzip); el valor real aparece al servir remoto.

## Búsqueda y badge de tipo de edición (2026-06-12)

**Búsqueda por BOTÓN/Enter (NO en vivo, 2026-06-14)**: con ~13k items, filtrar en cada
tecla trababa la UI (recomputaba todo el pipeline por pulsación). Ahora el input edita
`searchInput` y sólo `applySearch()` (botón "Buscar" o Enter) commitea a `filters.search`,
que es lo que el pipeline observa. La "×" / "limpiar" resetean. Detalle de rendimiento
(haystack precomputado + memoización del pipeline + contrato `_dataVersion`): gotcha #100.

**Búsqueda con aliases**: el buscador del grid matchea `title` + `title_original` +
`series_display` + los **aliases del `series_key`** — precomputados en `i._search`
(`_indexSearch()`) desde `this.aliasIndex`, cargado en `init()` vía
`../data/series_aliases.json` (lo regenera `export_series_aliases.py` en cada
`build_web.py`, con o sin `--embed`). Razón: política de títulos 2026-06-12 — el `title`
es el nombre OFICIAL de cada edición y no se renombra/traduce, así que "demon slayer",
"kimetsu no yaiba" y "guardianes de la noche" tienen que devolver lo mismo vía alias.
En modo `file://` (embebido, sólo con `--embed`) el JSON no se puede fetchear: la
búsqueda funciona igual pero sin aliases.

**Badge de tipo de edición**: la tarjeta muestra un chip púrpura con el tipo derivado
del slug del `edition_key` (`editionTypeLabel(item)`; omitido para `regular`). El
title oficial ya no lleva "Kanzenban"/"Deluxe" inyectado — el chip lo comunica.
Mantener `_editionTypeLabels`/`_editionCountries` en sync con
`web-next/lib/format.ts` (`EDITION_TYPE_LABELS`) y `_VALID_COUNTRY`
(fix_lmc_display_titles.py).

## Seguridad del server local (2026-06-13)

`serve.py` corre `os.chdir(ROOT)` y servía estáticos con `SimpleHTTPRequestHandler`
sin restricción: `/.env` (con las 5 API keys), `/.git/config`, `/scripts/`, `/.venv/`
resolvían a archivos reales, y `/api/run` ejecuta scripts del registry. Antes el
`--bind` por defecto era `0.0.0.0` → todo eso accesible desde CUALQUIER dispositivo
de la red. Endurecido:

- **`--bind` default = `127.0.0.1`** (solo loopback; antes `0.0.0.0`). Override con
  `--bind 0.0.0.0` o `BIND=0.0.0.0` **sólo en red de confianza** — imprime un warning
  explícito al arrancar. `admin_serve.py` ya bindeaba a loopback; ahora hay paridad.
- **Allowlist del fallthrough estático** (`_static_path_allowed`): sólo se sirven
  rutas bajo `web/`, `data/`, `reports/`. Todo lo demás (dotfiles/dotdirs `.env`/
  `.git`, `scripts/`, `.venv/`, traversal `..`) devuelve **403**, incluso sobre
  loopback (defensa en profundidad por si `--bind` se abre). Las páginas HTML de la
  raíz siguen vía `_HTML_ALIASES`. Test: `test_serve_static_allowlist_blocks_secrets`.

Si agregás un directorio nuevo que el dashboard deba fetchear como estático, sumalo a
`MangaWatchHandler._STATIC_ALLOW_TOP`.

## Favicon (2026-06-14)

Todas las páginas HTML (`index`, `panel`, `quality`, `cover-preview`, `image-manager`)
declaran `<link rel="icon" href="/favicon.ico">` + `<link rel="apple-touch-icon">`.
Como las páginas se sirven en URLs de raíz (`/`, `/panel.html`) y el navegador pide
`/favicon.ico` por defecto, **tanto `do_GET` como `do_HEAD`** resuelven `/favicon.ico` y
`/apple-touch-icon.png` (set `_ROOT_ASSETS`) hacia `web/<archivo>` — fuera del allowlist
estático, que sólo cubre `/web/...`. `do_HEAD` es necesario porque el heredado de
`SimpleHTTPRequestHandler` traduce contra `ROOT/` y devolvía **404** en HEAD (varios
navegadores sondean el favicon con HEAD antes del GET). Los `<link>` usan `?v=N` como
cache-bust: el favicon se cachea por origen de forma muy agresiva y un refresh normal no
lo vuelve a pedir; bumpeá `v` si cambia el ícono. Los assets se generan con
`scripts/gen_html_favicon.py` (panda sobre fondo rosa de acento para diferenciar de la app
pública Next.js).

## Panel de Calidad — "archivo_tiny" por píxeles + live-update respeta duplicados decididos (2026-07-08)

`scripts/audit/data_quality.py` (lo lee `web/quality.html` vía `data/quality_report.json`
+ `check_urls()` para el live-update tras arreglar un item) tenía dos bugs de criterio:

- **"Imagen diminuta" juzgaba por BYTES (<6KB), no por píxeles.** El espejo local es
  100% AVIF Q60 y comprime tan bien que una portada real de ~600×900 pesa <6KB — sobre
  el corpus real eso daba ~1060 falsos positivos "archivo_tiny" (portadas de 642×600,
  520×604… marcadas como "ícono"). Ahora usa `image_store.placeholder_reason()` (fuente
  única, la misma que usan los retrofits de imágenes): detecta placeholders reales
  (`broken`/`tiny:WxH`/`solid:STD`/`signature:LABEL`) sin importar cuánto pese el
  archivo. Sin Pillow o con `--no-measure`, cae al umbral de bytes viejo (heurística
  imperfecta pero mejor que nada). Mismo fix en `check_urls` (live-update).
- **El live-update (`check_urls`, llamado tras editar/aprobar un item desde el panel)
  ignoraba `data/dup_decisions.jsonl`.** El owner marcaba un grupo "productos distintos"
  desde el panel, tocaba otra cosa del mismo item, y `check_urls` volvía a flaggearlo
  como `dup_product` (sólo `audit_items`, la auditoría completa periódica, respetaba el
  archivo). Ahora `check_urls` recomputa la MISMA firma de grupo
  (`display_key + sha1(urls ordenadas)`) que `audit_items`/`_emit_dup_group` y saltea
  las decididas — paridad completa entre el audit completo y el live-update.

Ninguno de los dos cambia qué se persiste en `items.jsonl` — `data_quality.py` sigue
siendo 100% de solo lectura; sólo cambia qué reporta el panel.
