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
- **Búsqueda** por título (substring, case-insensitive, indexa `title` + `title_original` + `series_display`)
- **Filtros combinados (AND)**: país, editorial, idioma, tipo de producto, clase de fuente, rareza, estado de revisión (Todos / Aprobados / Sin revisar), solo stock limitado, signal types (multi-select chips)
- **Ordenamiento**: por fecha de detección (default), o título A-Z

> **Removido (2026-06-01):** el score se eliminó de la UI — del grid, del filtro
> "score mínimo", del ordenamiento y de los badges de las cards. El scoring interno
> del pipeline (gate de coleccionables) se mantiene, pero no es user-facing.
- **Paginación** con contador de items que matchean los filtros
- **Página de detalle**: imagen en carrusel (cuando hay múltiples), todos los campos, lista de fuentes con precio por fuente, descripción en español (`description_es` con fallback a `description` si no hay traducción)
- **Lightbox**: clic en la imagen del detalle la abre en grande (overlay full-screen, navegación ‹ ›, dots, contador "N / total", etiqueta Portada/Galería/Extra, teclado ←/→/Esc) — mismo comportamiento que el `ImageCarousel` de la app Next.js
- **Navegación entre tomos de la edición**: flechas laterales ‹ › fijas a los lados de la página de detalle (y teclado ←/→) para saltar al tomo anterior/siguiente de la misma edición sin volver a la grilla. Se ocultan en items sin hermanos (ediciones de 1 tomo / standalone). Esc vuelve a la edición/catálogo.
- **Multi-source view**: un producto con N fuentes se muestra como 1 card consolidada; el modal lista todas las fuentes con sus precios y URLs

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
  - Las 3 acciones se loguean en `data/feedback.jsonl` (misma fuente de verdad que el 👎) con campo `action` para que el skill `/review-feedback` las procese
  - Endpoint de búsqueda: `GET /api/editions/search?q=<query>` retorna ediciones matching por nombre
  - Endpoints de escritura: `POST /api/curation/{move,merge,remove}`

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

Tres mecanismos:

1. **Por URL** (modal): pegar una URL directa de imagen. Se descarga al espejo
   local (`data/images/`) automáticamente vía `POST /api/image-manager/download`
2. **Multi-URL** (textarea en el mismo modal): pegar varias URLs, una por línea.
   Se descargan secuencialmente con **barra de progreso** ("3/10 descargadas")
3. **Importar desde página web** (modal de scrape): ingresar la URL de una página
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

### Presentación

- Paleta: fondo claro `#fafaf7`, acento rosa `#d63384`
- Cards con imagen aspect-ratio 3:4, badge ⚠️ para stock limitado (los badges de score se removieron 2026-06-01)
- Sidebar de filtros sticky a 256px en desktop, full-width en mobile
- Carrusel multi-imagen en modal con flechas + dots + descripción del extra

---

## Features planificadas

Estas son las funcionalidades que queremos agregar al dashboard HTML (el orden no implica prioridad fija):

### Curación avanzada

- **Edición inline de campos**: modificar `title`, `series_key`, `edition_key`, `publisher`, `volume` de un item directamente desde el modal sin tocar el JSONL a mano
- **Merge manual de cards**: seleccionar 2+ cards y combinarlas en una sola (para casos donde el dedup automático por `cluster_key` no detectó que son el mismo producto)
- **Asignar series_key desde el modal**: dropdown con canonicals de `series_aliases.yml` + opción de crear nuevo canonical

### Operaciones de datos

- **Re-run de retrofit desde la UI**: disparar `rescore.py` / `filter_collectible.py` / `backfill_metadata.py` sin tocar el terminal (complementa el Panel de Control admin, pero más contextual)
- **Vista de items sin `standardized_at`**: filtro rápido para ver qué items nuevos están pendientes de curación

### UX

- **Keyboard shortcuts** para navegar entre cards y cerrar modal
- **Modo "curación rápida"**: vista simplificada con solo 👍 / 👎 por item para pasadas de review masivo

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
