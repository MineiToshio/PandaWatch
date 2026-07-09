# PRD — Web HTML (Dashboard personal)

> Herramienta personal de exploración y curación del catálogo de ediciones especiales.
> Única audiencia: el dueño del proyecto. Foco en velocidad de uso y control directo
> sobre los datos — no en presentación pública.

---

## Propósito

El dashboard HTML es la **interfaz personal de operación** del catálogo. Su rol es
distinto al del app Next.js (que es público y de presentación):

| | Web HTML (`web/`) | App Next.js (`web-next/`) |
|---|---|---|
| Audiencia | Solo el dueño | Público general |
| Foco | Explorar, curar, dar feedback | Descubrir, navegar, guardar |
| Velocidad de cambio | Rápida (HTML + Alpine.js) | Más deliberada |
| Deploy | Local en `localhost:8000` | Público (Vercel/Cloudflare Pages) |

---

## Usuarios

Un único usuario: el dueño del proyecto (sergiomineiro).

---

## Features actuales

### Exploración del catálogo

- **Grilla de items** con foto, título, país, editorial, tipo de producto
- **Búsqueda** por título (substring, case-insensitive, indexa `title` + `title_original` + `series_display` + aliases multilingües de la serie). **Por botón "Buscar" o Enter — NO en vivo** (con ~13k items, filtrar en cada tecla trababa la UI; perf en gotcha #100). La "×" / "limpiar" resetean.
- **Filtros combinados (AND)**: país, editorial, idioma, tipo de producto, clase de fuente, rareza, estado de revisión (Todos / Aprobados / Sin revisar), solo stock limitado, signal types (multi-select chips)
- **Ordenamiento**: por fecha de detección (default), o título A-Z

> **Removido (2026-06-01):** el score se eliminó de la UI — del grid, del filtro
> "score mínimo", del ordenamiento y de los badges de las cards. El scoring interno
> del pipeline (gate de coleccionables) se mantiene, pero no es user-facing.
- **Paginación** con contador de items que matchean los filtros
- **Página de detalle**: imagen en carrusel (cuando hay múltiples), todos los campos, lista de fuentes, descripción en español (`description_es` con fallback a `description` si no hay traducción)
- **Lightbox**: clic en la imagen del detalle la abre en grande (overlay full-screen, navegación ‹ ›, dots, contador "N / total", etiqueta Portada/Galería/Extra, teclado ←/→/Esc) — mismo comportamiento que el `ImageCarousel` de la app Next.js
- **Navegación entre tomos de la edición**: flechas laterales ‹ › fijas a los lados de la página de detalle (y teclado ←/→) para saltar al tomo anterior/siguiente de la misma edición sin volver a la grilla. Se ocultan en items sin hermanos (ediciones de 1 tomo / standalone). Esc vuelve a la edición/catálogo.
- **Multi-source view**: un producto con N fuentes se muestra como 1 card consolidada; el modal lista todas las fuentes con sus URLs

### Aprobación humana (golden records)

El owner marca cards como **correctas y definitivas** desde el dashboard. Patrón *golden record / human-in-the-loop*: un item aprobado queda congelado frente a los pases automáticos y sirve de referencia de "dato bien hecho". Es el equivalente humano de `standardized_at`.

- **Botón 👍/✓ (modal)** + **toggle rápido (candado al hover en la card)**: marca/desmarca la card. Aplica a todas las filas del `cluster_key`. Endpoint `POST /api/approve {url, approved}`.
- **Aprobar toda la edición**: en la vista de edición, un botón "✓ Aprobar toda la edición" marca todos los tomos de una sola vez (toggle: desaprueba todo si ya estaban todos). Endpoint `POST /api/approve-edition {edition_key, approved}` — una sola reescritura atómica.
- **Badge ✓ verde** en cards aprobadas + **filtro "Estado de revisión"** (Todos / Aprobados / Sin revisar).
- **Schema**: `approved_at` (ISO UTC) + `approved_by` (`owner`) en items.jsonl, sticky. Log durable `data/approvals.jsonl`.
- **Congelado**: re-scrapes congelan la metadata descriptiva y sólo refrescan precio/stock; retrofits y skills saltean items aprobados por defecto. Restauración tras reconstrucción: `scripts/retrofit/apply_approvals.py`.

### Curación de datos

Dos paneles en el footer del modal de detalle, unificados en `data/feedback.jsonl`:

- **Botón 👎 (feedback)**: registra feedback sobre un item (datos erróneos, clasificación equivocada, etc.)
  - El item **NO se elimina** del catálogo — sigue visible
  - Appendea la entrada con `action: "feedback"`, `url`, `title`, `reason`, `submitted_at`
  - Sirve como cola de revisión para corregir datos incorrectos, no para eliminar items

- **Botón lápiz (curación)**: acciones operativas sobre items, con efecto inmediato + log
  - **Mover a otra edición** (`action: "move"`): buscador autocomplete de ediciones existentes por nombre de serie. Cambia `edition_key`, `cluster_key`, `series_key` del item. Log incluye `from_edition` y `to_edition`.
  - **Duplicado / merge** (`action: "merge"`): pegar URL del item duplicado. Fusiona los dos items (gana el más completo — ISBN > imagen > precio, antes era "mejor score"; campos faltantes se completan, imágenes se combinan, el duplicado se elimina de items.jsonl). Log incluye `kept_url` y `dropped_url`.
  - **No va aquí / remover** (`action: "remove"`): separa el item de su edición actual, queda standalone (`edition_key=""`, `cluster_key="url:..."`). Log incluye `from_edition`.
  - Las 3 acciones se loguean en `data/feedback.jsonl` (misma fuente de verdad que el 👎) con campo `action` para que el skill `/watch-review-feedback` las procese
  - Endpoint de búsqueda: `GET /api/editions/search?q=<query>` retorna ediciones matching por nombre
  - Endpoints de escritura: `POST /api/curation/{move,merge,remove}`

### Edición inline de la metadata (botón ✏️ Editar info)

Botón **✏️ Editar info** en el footer de la página de detalle (`view==='volume'`).
Flipea el detalle a un **modo edición in-situ**: la metadata del item se convierte
en un **formulario dinámico** con una barra de acciones **💾 Guardar cambios /
Cancelar**. Es el flujo "edito lo que veo y lo grabo" — corregir cualquier dato del
item desde el mismo detalle, sin herramientas externas.

- **Se edita CUALQUIER atributo del item, EXCEPTO**:
  - **Imágenes** (`image_url`, `image_local`, `images`, `images_backfilled_at`) —
    tienen su propio gestor (`image-manager.html`). Set `_PROTECTED_ITEM_FIELDS` en
    `serve.py`; se ignoran si llegan en el payload.
  - **Identidad de fila** (`url`, `slug`, `cluster_key`, `content_hash`, `source_url`,
    `sources`) — son editables, pero se aplican **solo a la fila abierta**, no a las
    hermanas del cluster (set `_ROW_LOCAL_FIELDS`).
  - Todo lo demás (≈37 campos: title, author, publisher, price, isbn, volume,
    description, description_es, rarity, stock_type, tags, signal_types, signals,
    extras, score, series_key, edition_key, status, fechas, …) es editable.
- **Formulario dinámico** (`buildEditSchema` en `web/index.html`): arma el schema
  desde las keys reales del item, infiriendo el control por tipo — texto / textarea
  (descripciones) / número (score) / lista separada por comas (signal_types, signals,
  tags) / JSON (sources, extras). Split en "Principales" (orden fijo, siempre visibles)
  + "Avanzado / técnico" (colapsable, con warning sobre editar keys estructurales). El
  server **preserva el tipo** de cada valor; el frontend manda **solo lo que cambió**.
- **Descripción**: dos campos — `description_es` (override en español, lo que se
  muestra) y `description` (original de la fuente). Editar `description_es` no toca el
  original que usa `detect_signals` para `signal_types`. Convención i18n estándar.
- **Opera a nivel CLUSTER para los campos de producto**: como el gestor de imágenes,
  el cambio se propaga a **todas las filas del cluster** (mismo `cluster_key`) — así no
  reaparece desde una fila hermana al re-mergear. Clusters `url:` standalone tocan solo
  su fila. Card y detalle se actualizan en memoria sin recargar; si cambió algo
  estructural (keys/grouping), recarga el dataset para re-agrupar al volver.
- **NO recomputa `cluster_key`** automáticamente: la reagrupación estructural por
  arrastre tiene su propio flujo (botón 👎 → "Mover a otra edición"). El owner puede
  editar las keys a mano desde el editor avanzado, a propósito.
- **Durabilidad**: los items con `standardized_at` (≈99.6% del corpus) preservan los
  campos curados (`title`, `series_display`, `edition_display`, `volume`,
  `description_es`, …) frente a re-scrapes vía `_CURATED_FIELDS` de `append_jsonl`. Los
  campos no-curados (autor, editorial, precio, país, idioma, ISBN, product_type)
  persisten hasta que un re-scrape de esa misma URL los refresque. Para congelar TODO,
  el owner aprueba la card (golden record).
- **Auditoría**: cada edición se appendea a `data/edits.jsonl` (gitignored, append-only)
  con `url`, `cluster_key`, `rows_updated`, `fields`, `submitted_at`.
- Endpoint: `POST /api/item/update {url, fields}` (`_apply_item_update`, serializado
  con `@_serialized` — read-modify-write atómico, ver gotcha #34).
- Teclado: `Escape` cancela la edición (no vuelve de vista); abrir otro tomo o el
  catálogo descarta el modo edición.

### Gestor de imagenes (`/image-manager.html`)

Herramienta dedicada para gestionar las portadas e imagenes de galería del catálogo.
Accesible desde el header del dashboard (botón "Gestor de imagenes") o
directamente en `/image-manager.html`. Dark theme, Alpine.js, sin Tailwind.

**Opera a nivel CLUSTER (2026-06-02).** Un producto puede tener varias filas en
`items.jsonl` (una por fuente). El gestor carga la **union** de `images[]` de
todas las filas del cluster — exactamente lo que muestra el carrusel del detalle —
con la portada de la fila abierta primera. Al guardar, el set editado se
**propaga a todas las filas del cluster** (el endpoint resuelve los hermanos por
`cluster_key`). Así detalle y gestor muestran siempre lo mismo, y borrar/agregar
una foto no reaparece desde una fila hermana. (Antes el gestor editaba una sola
fila → discrepaba con el detalle, que ya hacía union.)

#### Acceso rápido por item (deep-link + round-trip)

Desde el dashboard hay un botón **🖼️ Editar imágenes** en el footer de la página
de detalle de un item **y** un ícono 🖼️ al hover en las cards (ediciones de 1 tomo
+ grilla de tomos). Ambos navegan a
`image-manager.html?item=<url>&return=<url-de-vuelta>`:
- `?item=<url>` → el gestor abre directo el editor de galería de ese item
  (`_handleDeepLink()` busca por `url` y llama `selectItem`).
- `?return=<url>` → habilita el botón **"← Volver al detalle"** (barra superior +
  header del editor) que regresa a la página exacta de donde se vino.
- Como el dashboard recarga `items.jsonl` al volver, el detalle muestra las
  **imágenes nuevas** inmediatamente. Misma pestaña (round-trip), no popup.

#### Vista principal (grid)

- **Grid de items** con indicadores de calidad visual (dot verde/amarillo/rojo/gris),
  tamaño del archivo de la portada en KB/MB, y badge de cantidad de imágenes
- **Filtros por calidad** (chips): Todas, Sin imagen, Baja calidad (<50 KB),
  Calidad media (50-200 KB), Escaladas PNG, 1 sola foto
- **Búsqueda** por título, title_original, series_key, series_display
- **Paginación** (60 items por página) con controles de navegación
- **Ordenamiento automático**: worst quality first (sin imagen > baja > media > buena)

#### Vista de detalle (overlay full-screen)

Se abre al hacer clic en un item del grid. Muestra:

- **Header** con título, contador de imágenes, botón "Fuente" (abre URL
  del item en nueva pestaña), y botón "Guardar cambios" con dirty tracking
- **Navegación entre items**: botones Prev/Next en el header para saltar al
  item anterior/siguiente del grid filtrado sin volver a la grilla. Confirma
  si hay cambios sin guardar
- **Imagen grande** (preview) con:
  - Badge informativo: kind (Portada/Galeria/Extra/Variante/Contra) +
    posición (1/3) + dimensiones reales en píxeles (776x1000px) + tamaño (63 KB)
  - Flechas de navegación izquierda/derecha sobre la imagen
  - **Click = lightbox**: abre la imagen a pantalla completa (92vw x 90vh)
    con fondo oscuro, botón X, flechas, y badge inferior
- **Panel de acciones** (sidebar derecha en desktop, debajo en mobile):
  - Agregar por URL / Importar desde página web
  - Reemplazar por URL (imagen seleccionada)
  - **Usar como portada**: mueve la imagen a posición 0 y cambia su kind a "cover"
  - **Mover a la izquierda / derecha**: reordena imágenes en el array
  - Eliminar imagen / Eliminar todas excepto portada
- **Filmstrip** (tira de thumbnails):
  - Cada thumbnail muestra kind label (Portada/Galeria/etc.) y número de posición
  - Click = seleccionar para preview
  - Hover = botones de acción (usar como portada, reemplazar, eliminar)
  - **Drag & drop**: arrastrar thumbnails para reordenar (HTML5 Drag API).
    Visual feedback: el item arrastrado se vuelve semitransparente, el target
    muestra borde azul punteado. Hint "Arrastra para reordenar" visible
  - Botón "+" al final para agregar nueva imagen
- **Barra de edición** (bajo el filmstrip):
  - **Dropdown de tipo**: cambia el kind de la imagen seleccionada
    (`gallery` o `extra`). La portada se determina por posición (images[0]),
    no por kind
  - **Input de descripción**: editar inline la descripción de cada imagen
    (ej: "Contraportada", "Postal de regalo", "Tomo 3 interior")
- **Panel de información del item** (bajo la barra de edición):
  Grid de 3 columnas (desktop) / 2 columnas (mobile) con TODOS los campos
  del item: título, título original, serie, edición, volumen, publisher,
  país, idioma, ISBN, precio, fecha de lanzamiento, autor, rareza,
  tipo de producto, stock, fuente, fecha de detección, signal types (como
  chips), y descripción completa (description_es con fallback a description).
  Permite al usuario saber exactamente qué item está editando y qué buscar
  como reemplazo (por ISBN, título original, etc.)

#### Teclado

| Tecla | Acción |
|---|---|
| `←` `→` | Navegar entre imágenes del filmstrip |
| `Escape` | Cerrar lightbox, o cerrar detalle (con confirmación si hay cambios) |

Los atajos se desactivan cuando el foco está en un input/textarea/select.

#### Agregar imágenes

Cuatro mecanismos:

1. **🔍 Buscar portada en Google**: abre **Google Imágenes** en una pestaña nueva
   con `title_original + publisher` del item. Lo más simple y sin fricción: sin
   API, sin keys, sin límites — buscás/iterás en Google libre y traés la foto con
   "Agregar por URL" o arrastrándola. *(No se puede embeber Google en un iframe
   ni inyectarle botones: X-Frame-Options/CSP bloquean el framing y la Same-Origin
   Policy impide tocar el DOM de un iframe cross-origin. Para un "botón en cada
   foto" mientras navegás, la vía real sería un userscript/extensión, no una web.)*
   *(Parado, no borrado: existe un modal de búsqueda por API — Tavily + ISBN vía
   `POST /api/image-search` — que quedó sin usar tras decisión del owner.)*
2. **Por URL** (modal): pegar una URL directa de imagen. Se descarga al espejo
   local (`data/images/`) automáticamente vía `POST /api/image-manager/download`
3. **Multi-URL** (textarea en el mismo modal): pegar varias URLs, una por línea.
   Se descargan secuencialmente con **barra de progreso** ("3/10 descargadas")
4. **Importar desde página web** (modal de scrape): ingresar la URL de una página
   (pre-llenada con la URL del item para conveniencia). El servidor fetchea el HTML,
   extrae todas las `<img>` URLs, y las muestra en un grid de selección con
   checkboxes. Botones "Seleccionar todas" / "Deseleccionar". Las imágenes
   seleccionadas se descargan al espejo con barra de progreso

#### Persistencia

- **Dirty tracking**: el botón "Guardar cambios" solo se activa cuando hay
  modificaciones pendientes. Si el usuario intenta cerrar o navegar a otro item
  con cambios sin guardar, se muestra confirmación
- **Escritura atómica**: `POST /api/image-manager/save` reescribe la fila del
  item en `items.jsonl` vía tmp + rename. Sincroniza `image_url` / `image_local`
  con la primera imagen del array (la portada)
- **Sync en memoria**: tras guardar, el item en la grilla se actualiza
  inmediatamente (sin recargar toda la página)

#### API endpoints (`scripts/serve.py`)

| Endpoint | Método | Descripción |
|---|---|---|
| `/api/image-file-sizes` | GET | `{filename: size_bytes}` de todos los archivos en `data/images/` |
| `/api/image-manager/save` | POST | Guarda `images[]` modificado de un item (body: `{item_url, images}`) |
| `/api/image-manager/download` | POST | Descarga imagen por URL al espejo local (body: `{image_url}`) |
| `/api/image-manager/scrape` | POST | Extrae `<img>` URLs de una página web (body: `{page_url}`) |

### Selección múltiple y acciones batch

Botón **☑️ Selección múltiple** en la barra de orden (catálogo y vista de edición). Activa checkboxes en cada card; clic en la card (o el checkbox) la marca. Cuando hay ≥1 seleccionada aparece una **barra flotante** abajo con:

- **✓ Aprobar / Desaprobar** — golden record en lote.
- **↪ Mover a edición…** — autocomplete de ediciones destino (reusa `/api/editions/search`).
- **⚐ Reportar** — feedback en lote (pide motivo).
- **Limpiar / Seleccionar visibles**.

La selección unifica ediciones e items: una card de catálogo selecciona la **edición entera** (`e:<edition_key>`), una card de la vista de edición selecciona el **tomo** (`i:<url>`); las ediciones de 1 tomo (`__solo__`) se resuelven al item. Endpoints: `POST /api/batch/approve {urls, edition_keys, approved}` y `POST /api/batch/move {urls, to_edition}` — ambos hacen **una sola lectura+escritura atómica** de `items.jsonl` (`@_serialized`, no N reescrituras).

### Modo curación rápida (teclado)

Botón **⚡ Curación rápida (N)** → overlay full-screen que recorre la **cola filtrada** (los filtros del sidebar definen la cola: ej. "Sin revisar" + un país) de a un item, con portada grande + metadata clave + atajos:

| Tecla | Acción |
|---|---|
| **A** | Aprobar (+ siguiente) |
| **U** | Desaprobar |
| **R** | Reportar (input inline + Enter) |
| **E** | Editar (sale al detalle y abre el editor inline) |
| **S** | Saltar |
| **J / →** | Siguiente |
| **K / ←** | Anterior |
| **Esc** | Salir |

Auto-avanza al actuar. La cola se snapshotea al entrar para que aprobar/reportar no la reordene. Convierte el "scroll-clic-volver-a-la-grilla" en un flujo de teclado continuo.

### Panel de Calidad de datos (`/quality.html`)

Página dedicada (link 🩺 en el header) que consume `data/quality_report.json` (lo genera `scripts/audit/data_quality.py`) y lo muestra como **worklists clickeables** agrupadas:

- **🧰 Preparación del dato — "qué falta correr"** (panel arriba de todo). Surfacea los pasos del [ciclo de vida del dato](../scraper/PIPELINE-WALKTHROUGH.md) que son post-scrape (manuales/semi-manuales): estandarización, aliases, slugs, traducción, rareza, consolidación, imágenes card≠carrusel, feedback, portadas por aprobar. Por cada paso muestra **`pending`** (items que aún no pasaron) y **`stale`/desincronizados** (el paso ya corrió pero quedó viejo — p. ej. el `slug` se generó bien y luego cambió la edición, así que ya no coincide con el recalculado; se detecta reusando `generate_slugs._derive_base_slug`). Tres tipos de acción según el paso:
  - **▶ Arreglar** — pasos con **script mecánico** del registry (`generate_slugs`, `translate_descriptions`, `set_rarity`, `consolidate_sources`, `sync_cover_images`): corren ahí mismo vía `POST /api/run` con loading en vivo y, al terminar, **re-auditan** (`data_quality`) y recargan el reporte.
  - **🧠 copiar** — pasos que son **skills LLM de Claude** (`/watch-standardize-catalog`, `/watch-enrich-series-aliases`, `/watch-validate-rarity`, `/watch-review-feedback`): NO se pueden disparar desde un botón HTML, así que el panel muestra el conteo y copia el nombre del skill para que lo corras en Claude.
  - **Revisar →** — pasos de **aprobación manual** (portadas → `cover-preview.html`).
  Los pasos sin trabajo se muestran al final en verde ("al día"), con el botón deshabilitado. El cómputo vive en `_compute_readiness()` de `data_quality.py` (sección `readiness` del JSON).
- **Resumen por grupo** (estructura / procedencia / imágenes) con conteo de alertas.
- **Categorías colapsables** (14): estructura — productos partidos en varias fichas, **posibles productos duplicados** (mismo ISBN o misma serie+edición+volumen en cluster_keys distintos), procesados sin serie/edición, sin slug; procedencia — sin tienda, tienda sin enlace; imágenes — sin foto, portada-basura, foto rota, imagen diminuta, foto reusada en muchas obras, pixelada, card≠carrusel, **foto repetida en el carrusel** (mismo archivo/url dos veces en `images[]`). Cada categoría trae:
  - **Título en cristiano + descripción `desc`** (qué significa, para alguien que nunca vio la app — el JSON la trae por categoría).
  - **Worklist clickeable**: cada item linkea al **gestor de imágenes** (alertas de imagen — misma pestaña, con **"← Volver al reporte"**) o al **detalle** (estructura/metadata — pestaña nueva).
  - **🛠️ Cómo arreglarlo** — toda categoría tiene una acción (campo `fix` en el JSON, definido en `CATEGORY_META`): **▶ Arreglar todo** (script mecánico del registry, p. ej. `consolidate_sources`/`generate_slugs`/`sync_cover_images`/`fetch_better_covers` — corre vía `/api/run` y re-audita), **🧠 skill** (copia el comando para correr en Claude, p. ej. `/watch-standardize-catalog`, `/watch-search-covers`), o **📋 Copiar prompt para Claude** (un prompt self-contained para los casos que necesitan juicio — source rota, ref de imagen rota). Así **ningún error queda sin forma de solucionarse**.
- **Revisor de duplicados (categoría `dup_product`).** No se renderiza como worklist plana sino **agrupada**: cada bloque son las fichas que parecen el MISMO producto. Dos criterios de match (campo `match`): **`isbn`** (mismo ISBN — header verde 🟢 "muy probablemente el mismo") o **`triple`** (misma serie+edición+volumen sin ISBN — header ámbar 🟡 "revisar"). Hoy en la práctica casi todos son `isbn`. Por grupo se muestran los miembros **lado a lado** (portada + título + tienda + editorial + país + edición + volumen + precio + ISBN + link "ver detalle"); el **ISBN se colorea** verde si coincide con el común del grupo, rojo si difiere. Nota de datos: con el mismo ISBN la **editorial puede diferir** porque algunas tiendas (Sanyodo, Rakuten Books) se cargan a sí mismas como `publisher` en vez de la editorial real — es inconsistencia de extracción, no productos distintos.
  - **Selector "¿con cuál info nos quedamos?"**: al unir, las **fotos y tiendas se juntan siempre**; los campos de **identidad** (`title`, `title_original`, `series_key`, `series_display`, `edition_key`, `edition_display`, `volume`, `publisher` — ver `_DUP_IDENTITY_FIELDS` en serve.py) se toman de **una** ficha. Cada miembro tiene un radio **"✓ Conservar esta info"**; el default (`suggested_keep`) es la ficha más completa (misma métrica `_cluster_completeness` que usa `merge_cluster` como canónica). El usuario puede cambiarlo. Si el `edition_key` elegido difiere, el `slug` se limpia para que `generate_slugs` lo regenere.
  - **Acciones**: **"✓ Son el mismo → unir"** (`POST /api/dup/merge` con `keep_url` → `merge_cluster` + override de identidad, backup automático) y **"✗ Son distintos"** (`POST /api/dup/decide`). Ambas decisiones se persisten en `data/dup_decisions.jsonl` (append-only, por `signature` = dup_key + hash de las URLs del grupo); `data_quality.py` lee ese log y **NO vuelve a mostrar** los grupos ya decididos en sesiones futuras (si cambia la membresía del grupo, la signature cambia y re-aparece). El grupo se quita de la lista en el acto (optimista).
- **Cobertura de campos** (isbn, price, author, volume, …) con barras.
- Botón **Regenerar** que lanza el audit vía `POST /api/run` + polling de `/api/jobs/<id>` y recarga el JSON.
- **Live-update (sin regenerar):** al arreglar un ítem (en el gestor de imágenes o el detalle) el panel lo **saca de la worklist automáticamente**. Tres mecanismos: (a) re-verificación **por ítem** vía `POST /api/quality/check` (no re-audita todo el corpus); (b) **sync entre pestañas** por `BroadcastChannel` — al guardar en el gestor/detalle se avisa la URL y el panel la re-chequea al instante; (c) **recheck al recuperar foco** de los ítems que fuiste a arreglar (cola persistida en `localStorage`, cubre el flujo same-tab). Los **collapses se recuerdan** (regenerar/recargar no los cierra).

Cierra el loop **detectar → ir → arreglar → (se actualiza solo)** (antes las fotos malas se descubrían scrolleando a ciegas y el reporte quedaba viejo hasta regenerar todo).

### Revisión de portadas (`/cover-preview.html`)

Página dedicada para revisar y aprobar las portadas que `fetch_better_covers.py` encontró con **baja confianza** (la imagen original era demasiado chica para verificar por hash, así que no se auto-aplican). Consume `data/cover_preview.json` y persiste vía `POST /api/save-cover-preview`.

**Botón de volver origen-consciente.** Igual que el gestor de imágenes, lee `?return=<url>` de la URL: si se entró desde el Panel de Calidad (paso "Portadas candidatas por aprobar"), el botón superior dice **"← Volver al reporte"** y vuelve a `quality.html`; si se entró directo, dice **"← Catálogo"** y va a `index.html`. El Panel de Calidad arma el link con `?return=` codificado (mismo patrón que `image-manager.html`).

**Multi-candidato + galería completa (2026-06-05).** Cada producto puede tener **N candidatas** (varias pasadas de búsqueda acumulan candidatas para el mismo item). Arriba de cada card se muestra la **galería ACTUAL completa** del item (portada + galería + extras) como filmstrip — así el owner ve todo lo que ya tiene y puede decidir con contexto. Debajo, un **sub-card por candidata**, cada uno con:

- Miniatura + conteo de píxeles + factor de mejora (×N) frente a la portada actual.
- **Dropdown de acción** por candidata, dinámico según la galería: *Reemplazar portada (descarta la actual)* / *Reemplazar portada (la actual pasa a extra)* — la nueva queda de portada y la vieja se conserva en la galería / *Reemplazar imagen N (galería/extra)* — una opción por cada imagen actual más allá de la portada / *Agregar a galería* / *Agregar como extra*. Así el owner puede decir "esta candidata reemplaza **esta imagen específica** de la galería".
- Botones **✓ aprobar / ✕ rechazar** individuales + badge de estado (pendiente / aprobada / rechazada).
- Clic en cualquier miniatura (galería actual o candidata) → zoom / comparación grande.

**Modal de comparación navegable (2026-06-06).** Clic en una miniatura de candidata abre el modal grande "anterior vs nueva". El modal **no es estático**: navega entre **todas** las candidatas del producto sin cerrarse — una barra centrada en una sola línea **◀  N / M  ▶** y **flechas ← → del teclado** (sin dots: se quitaron por ruido visual). El borde de la imagen nueva refleja el estado (amarillo pendiente / verde aprobada / rojo rechazada). Abajo del todo, los **mismos controles** que el sub-card: el `<select>` de acción + botones **✓ Aprobar / ✕ Rechazar**, para decidir desde el propio modal mientras se compara cuál es la mejor foto. La navegación comparte el estado `candIdx`, así el carrusel de la card y el modal quedan sincronizados.

El modal es un **flex column**: header, barra de navegación y footer de controles quedan **fijos** (`flex:0 0 auto`) y **solo el área de imágenes scrollea** (`flex:1 1 auto; overflow-y:auto`). Así las flechas (arriba) y los botones aprobar/rechazar (abajo) están **siempre visibles** sin scroll, aunque la portada sea muy alta. Las flechas usan la clase `.nav-arrow` con hit area amplia (antes eran `.card-toggle` chicas y costaba clickearlas).

Controles globales: **Aprobar / Rechazar todas pendientes** (respeta la acción elegida por candidata). Un producto se **colapsa** (header gris) cuando todas sus candidatas están decididas.

**Feedback desde el cover review (2026-06-21).** En el header de cada producto, además de la galería/candidatas, hay dos acciones de curación que escriben a `data/feedback.jsonl`: **Excluir** (`flagIrrelevant` — motivo fijo "irrelevante" y **saca** el item de la cola de portadas) y **👎 Reportar** (`toggleReport`/`submitReport` — la MISMA funcionalidad que el dislike del catálogo: abre un **editor de motivo inline** —input con Enviar/Cancelar, no `prompt()`— y reporta el item **sin** sacarlo de la cola). Sirve para cuando, revisando portadas, el owner detecta incongruencias o cosas que no son manga y quiere dar feedback ahí mismo. El estado "reportado" persiste entre recargas (se levanta de `feedback.jsonl` por `slug`) → el botón pasa a **"✓ Reportado"** deshabilitado hasta que `/watch-review-feedback` procese y trunque la cola. Backend idempotente por URL (no duplica ante doble-click). Detalle en [dashboard.md](../reference/dashboard.md) y gotchas #105, #106.

**Aprobar ≠ aplicar — botón "Aplicar aprobadas".** Aprobar/rechazar solo **registra la decisión** en `cover_preview.json`; el catálogo (`items.jsonl`) NO cambia hasta aplicar. El botón **"✓ Aplicar aprobadas (N)"** en la barra de acciones lo hace desde la propia página: `POST /api/apply-cover-preview` corre `apply_preview` in-proc (`@_serialized`), aplica las aprobadas a `items.jsonl` y **quita del JSON las decididas** (aprobadas **y** rechazadas), dejando solo las pendientes; la página recarga sola. (También sigue disponible por CLI `fetch_better_covers.py --apply-preview` y en el Panel de Control.) Es seguro por diseño: nada se auto-aplica sin tu OK. Tras aplicar, refrescá el image-manager para ver las portadas nuevas.

Al aplicar, cada acción se materializa: *replace_cover* reemplaza `image_url`/`image_local`/`images[0]` y descarta la vieja; *replace_cover_demote* pone la nueva de portada y **conserva la portada actual en la galería como extra** (no la descarta); *replace_image* reemplaza la imagen de `images[]` cuya url coincide con el `target` elegido (preservando su `kind`; si es la portada, sincroniza los campos de portada; si la galería cambió y el target ya no está, cae a *add_gallery*); *add_gallery*/*add_extra* agregan a `images[]` sin tocar la portada. El rechazo revierte (portada vieja o quita la URL de galería) y borra el archivo nuevo —y el de la imagen reemplazada— si quedan huérfanos.

Backwards-compat: las entries del schema viejo (campos planos `new_image`/`new_url`/…) se normalizan a 1 candidata `action=replace_cover`, con `current_images` sintetizado desde la portada.

### Presentación

- Paleta: fondo claro `#fafaf7`, acento rosa `#d63384`
- Cards con imagen aspect-ratio 3:4, badge ⚠️ para stock limitado (los badges de score se removieron 2026-06-01)
- Sidebar de filtros sticky a 256px en desktop, full-width en mobile
- Carrusel multi-imagen en modal con flechas + dots + descripción del extra
- **Favicon** (todas las páginas): el panda logo sobre un cuadrado redondeado del
  acento rosa `#d63384`. La app pública (Next.js) usa el mismo panda pero sobre
  fondo transparente — el fondo rosa diferencia la app HTML local en la barra de
  pestañas. Assets en `web/favicon.ico` (multi-size 16/32/48/64) +
  `web/apple-touch-icon.png` (180×180), generados por `scripts/gen_html_favicon.py`
  desde `web-next/app/icon.png` (fuente única del logo). `serve.py` los sirve también
  en la raíz (`/favicon.ico`, `/apple-touch-icon.png`) porque las páginas viven en
  URLs de raíz.

---

## Features planificadas

Estas son las funcionalidades que queremos agregar al dashboard HTML (el orden no implica prioridad fija):

### Curación avanzada

- ✅ ~~**Edición inline de campos**~~ — **IMPLEMENTADO** (ver "Edición inline de la metadata" en Features actuales): botón ✏️ Editar info en el detalle, formulario editable + guardar, escritura a nivel cluster vía `POST /api/item/update`.
- ✅ ~~**Merge manual de cards**~~ — **IMPLEMENTADO (parcial)**: "Duplicado / merge" pegando la URL del duplicado en la curación 👎. *(Pendiente: merge multi-select visual sin pegar URL.)*
- **Asignar series_key/edition_key estructural desde el editor**: hoy el editor inline cambia los *display* (`series_display`/`edition_display`) pero no reasigna los keys ni re-clusteriza; eso sigue siendo dominio del flujo "Mover a otra edición" (ahora también en lote vía selección múltiple).
- **Asignar series_key desde el modal**: dropdown con canonicals de `series_aliases.yml` + opción de crear nuevo canonical

### Operaciones de datos

- **Re-run de retrofit desde la UI**: disparar `rescore.py` / `filter_collectible.py` / `backfill_metadata.py` sin tocar el terminal (complementa el Panel de Control admin, pero más contextual). *(Parcial: el Panel de Calidad ya lanza `data_quality.py` desde la UI vía `/api/run`.)*
- **Vista de items sin `standardized_at`**: filtro rápido para ver qué items nuevos están pendientes de curación. *(El filtro "Estado de revisión" + la cola de curación rápida cubren el caso de aprobación; falta un filtro específico de `standardized_at`.)*

### UX

- ✅ ~~**Keyboard shortcuts**~~ — **IMPLEMENTADO**: navegación ←/→ entre tomos, Esc para volver, y el **modo curación rápida** con atajos A/U/R/E/S/J/K (ver Features actuales).
- ✅ ~~**Modo "curación rápida"**~~ — **IMPLEMENTADO** (ver "Modo curación rápida" en Features actuales): overlay de un item a la vez sobre la cola filtrada, con atajos de teclado y auto-avance.
- ✅ ~~**Acciones en lote**~~ — **IMPLEMENTADO** (ver "Selección múltiple y acciones batch").
- ✅ ~~**Surfacear la auditoría de calidad en la UI**~~ — **IMPLEMENTADO** (ver "Panel de Calidad de datos").

---

## Out of scope (permanente)

- Auth / múltiples usuarios (es herramienta personal)
- Export a CSV/JSON (el JSONL ya es el export)
- Notificaciones push
- Tracking de precios históricos (solo se ve el último precio)
- Predicción de lanzamientos

---

## Convención de idioma en descripción

El modal muestra siempre el texto más útil para el dueño (español):

```js
// Patrón aplicado en dos lugares del modal:
description_es || description        // descripción principal del item
ex.description_es || ex.description  // descripción de cada extra
```

- `description_es` — traducción al español generada por `translate_descriptions.py`
  (Google Translate, idempotente, guardado en items.jsonl).
- Si `description_es` es vacío (descripción original ya era español) o el campo no
  existe, se muestra `description` directamente.
- Los campos originales (`description`, `extras[].description`) nunca se modifican —
  los usa `detect_signals()` internamente.

---

## Stack técnico

HTML estático + Alpine.js (CDN) + Tailwind CSS (CDN). Sin npm, sin build step.
Para detalles de implementación ver `docs/scraper/ARCHITECTURE.md` sección "Web layer"
y los comentarios inline en `web/index.html`.

Corre con `scripts/serve.py` (servidor público en `0.0.0.0:8000`) o con
`scripts/run_local.sh` (lanza serve.py + admin_serve.py en paralelo).
