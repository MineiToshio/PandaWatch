# PRD — Manga Watch Browser

> Página web local para explorar el catálogo de items detectados por `manga_watch.py`.

---

## 1. Resumen ejecutivo

Una página web estática que lee el archivo `data/items.jsonl` (generado por el scraper) y
permite explorar todos los items detectados con búsqueda, filtros y ordenamiento.
Sin backend, sin DB, sin auth — solo abre y mira.

## 2. Problema actual

Hoy la data se consume de dos formas:

1. **Reporte Markdown diario** (`reports/YYYY-MM-DD.md`): solo muestra los items
   `new`/`changed` del día. No permite explorar el catálogo histórico.
2. **JSONL crudo** (`data/items.jsonl`): tiene todos los items detectados pero es
   ilegible sin herramientas.

No hay forma de hacer preguntas como:
- "Mostrame todos los artbooks de Japón con stock limitado"
- "Buscame todos los items donde el título mencione 'Berserk'"
- "Cuáles son los items más caros que detectó el script?"

## 3. Usuarios

Un único usuario: el dueño del proyecto.

## 4. User stories

### Must have

- Como usuario, quiero ver una grilla de items con su foto, título y tags principales.
- Como usuario, quiero buscar por título usando un input de texto (substring match).
- Como usuario, quiero filtrar por: **país, editorial, idioma, tipo de producto**.
- Como usuario, quiero filtrar por **score mínimo** con un slider.
- Como usuario, quiero ordenar la lista por **score**, **fecha de detección** o **título**.
- Como usuario, quiero hacer click en un item y ver TODOS sus datos en un panel de detalle.
- Como usuario, quiero ver un contador de cuántos items matchean los filtros actuales.

### Should have

- Filtro adicional por **clase de fuente** (official / retailer / trusted_media / social).
- Filtro adicional para mostrar solo items con **stock limitado**.
- Indicador visual claro de items `limited` (badge ⚠️).
- Paginación (60 items por página, navegación con teclado).
- Estadísticas en header: total de items, países cubiertos, última detección.

### Won't have (out of scope para esta versión)

- Edición de items.
- Auth.
- Backend / DB.
- Múltiples usuarios.
- Notificaciones.
- Export a CSV/JSON.

## 5. Decisión técnica

**Stack elegido: HTML estático + Tailwind CSS (CDN) + Alpine.js (CDN).**

### Justificación

| Criterio | Decisión |
|---|---|
| **Cero dependencias npm** | No queremos `node_modules` (200MB) para una vista personal. |
| **Un solo archivo HTML** | `web/index.html` autocontenido. |
| **Servir local** | `python -m http.server` que ya tenemos. |
| **Migración futura** | Alpine tiene sintaxis similar a Vue/React; trivial migrar a Next.js. |

### Por qué NO Next.js ahora

- Overkill para visualización local.
- Setup más pesado (npm, build step, dev server).
- El usuario explícitamente dijo "por ahora basta con HTML".

### Por qué Alpine.js y no vanilla JS

Filtros reactivos + paginación + estado UI = mucho boilerplate en vanilla.
Alpine resuelve eso en ~100 líneas en lugar de ~500.

## 6. Arquitectura

```
                                    ┌──────────────┐
                                    │  Browser      │
                                    │ ┌──────────┐ │
data/items.jsonl   ──── fetch ──►   │ │ Alpine.js │ │
(append-only history)               │ │ + Tailwind│ │
                                    │ └──────────┘ │
                                    └──────────────┘
```

- **No hay backend.** La página fetchea `../data/items.jsonl` cuando carga.
- **Deduplicación cliente-side.** El JSONL es append-only — la misma URL puede aparecer
  varias veces (porque el item cambió). Tomamos la entrada con `detected_at` más reciente.
- **Filtros y orden en memoria.** Para <10k items, performance es instantáneo.

## 7. Páginas / vistas

### 7.1 Vista principal — listado (`/`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Manga Watch                              123 items · 5 países  │
├──────────────┬──────────────────────────────────────────────────┤
│              │  🔍 [buscar título...]    Sort: [score ▼]         │
│   FILTROS    ├──────────────────────────────────────────────────┤
│              │                                                   │
│ País         │  ┌────┐ ┌────┐ ┌────┐ ┌────┐                     │
│ [todos ▼]    │  │card│ │card│ │card│ │card│                     │
│              │  └────┘ └────┘ └────┘ └────┘                     │
│ Editorial    │  ┌────┐ ┌────┐ ┌────┐ ┌────┐                     │
│ [todas ▼]    │  │card│ │card│ │card│ │card│                     │
│              │  └────┘ └────┘ └────┘ └────┘                     │
│ Idioma       │                                                   │
│ [todos ▼]    │  ────────  página 1 de 4  ────────              │
│              │                                                   │
│ Tipo         │                                                   │
│ [todos ▼]    │                                                   │
│              │                                                   │
│ Score ≥ [30] │                                                   │
│              │                                                   │
│ ☐ Solo lim.  │                                                   │
└──────────────┴──────────────────────────────────────────────────┘
```

### 7.2 Vista detalle — modal

Se abre al hacer click en una card. Muestra:

- Imagen grande (si hay)
- Título + score + estado (new/changed/seen)
- Todos los campos del item:
  - Tipo de producto
  - Autor (si está)
  - Editorial
  - País + idioma
  - Precio (si está)
  - Fecha de lanzamiento (si está)
  - Stock (limited / regular)
  - Señales detectadas (lista de keywords)
  - Fragmento de descripción
- Botón "Ver en sitio original" (link a `url`)
- Botón "Cerrar"

## 8. Filtros

Cada filtro reduce la lista; combinaciones se aplican con AND.

| Filtro | Tipo | Default | Valores |
|---|---|---|---|
| Búsqueda título | Text input (substring case-insensitive) | "" | Cualquier string |
| País | Single-select | "todos" | Países únicos del dataset |
| Editorial | Single-select | "todas" | Publishers únicos |
| Idioma | Single-select | "todos" | Languages únicos |
| Tipo de producto | Single-select | "todos" | manga / artbook / boxset / fanbook / guidebook / novel |
| Clase de fuente | Single-select | "todas" | official / retailer / trusted_media / social |
| Score mínimo | Range slider (0-100) | 30 | Number |
| Solo stock limitado | Checkbox | off | bool |

## 9. Ordenamiento

| Opción | Default | Notas |
|---|---|---|
| Score (más alto primero) | ✅ | |
| Score (más bajo primero) | | |
| Fecha de detección (más reciente) | | Por `detected_at` |
| Fecha de detección (más antigua) | | |
| Título A→Z | | |
| Título Z→A | | |

## 10. Diseño visual

- **Paleta**: fondo claro `#fafaf7`, acento rosa `#d63384` (consistente con `docs/index.html`).
- **Tipografía**: -apple-system, SF Pro, Segoe UI.
- **Cards**:
  - aspect-ratio 3:4 para la imagen
  - sombra suave, border-radius 12px
  - hover: elevación + cursor pointer
  - badge de score arriba a la derecha (color según rango: rojo ≥70, amarillo 35-69, gris <35)
  - footer con tags: 🌍 país · 🏢 editorial · 📚 tipo
  - badge ⚠️ "limitado" si `stock_type === "limited"`
- **Modal**: overlay semi-transparente, content centered, scroll vertical.
- **Sidebar**: sticky a 256px en desktop, full-width arriba en mobile.

## 11. Estructura del proyecto

```
manga-watch/
├── web/
│   ├── index.html       ← La página
│   └── serve.sh         ← Script para servir
├── data/
│   └── items.jsonl      ← Source of truth
└── ...
```

## 12. Cómo se usa

Hay **dos modos**, elegí el que te guste:

### Modo A — Single-file (recomendado, doble-click)

```bash
# Embebe data/items.jsonl dentro de web/index.html
.venv/bin/python scripts/build_web.py

# Abre con doble-click (file://)
open web/index.html
```

El HTML queda autocontenido. Lo podés mover de carpeta, mandar por mail, etc.
Hay que volver a correr `build_web.py` cuando hay nuevos items.

### Modo B — Server local (más vivo)

```bash
./web/serve.sh
# o: python -m http.server 8000 desde la raíz
open http://localhost:8000/web/
```

No requiere build step. Cada refresh re-fetcha `data/items.jsonl`.

## 13. Performance esperada

- Carga inicial: ~200ms para parsear 1000 items.
- Filtrado en memoria: <50ms para 1000 items.
- Hasta ~10k items sin lag perceptible.
- Para >10k items, podrías necesitar virtual scrolling — out of scope ahora.

## 14. Plan de migración futura a Next.js

Cuando quieras deployear, los pasos:

1. `npx create-next-app@latest manga-watch-web`
2. Copiar el HTML como `app/page.tsx`, convertir Alpine `x-data` → `useState`.
3. Server Component lee `items.jsonl` con `fs.readFile` (build-time).
4. SSG con `output: 'export'` para Cloudflare Pages / Vercel.
5. Cron diario que regenera el JSONL y rebuildea.

Tiempo estimado: 1 día. El layout HTML ya estará probado y solo cambia el binding.

## 15. Tests

Esta versión es manual (visual). Si se complica, se puede añadir Playwright pero
para una vista personal local no se justifica.

## 16. Criterios de aceptación

- ✅ Abro `http://localhost:8000/web/` y veo el grid cargado.
- ✅ Cuento de items totales en header coincide con `wc -l data/items.jsonl` (deduplicado).
- ✅ Buscar "Berserk" en el input filtra a items con "Berserk" en el título.
- ✅ Cada filtro reduce la lista correctamente.
- ✅ Combinación de filtros (país=Japón + tipo=artbook) funciona.
- ✅ Cambiar el sort reordena la grilla.
- ✅ Click en card abre el modal con todos los datos.
- ✅ Click en "Ver en sitio" abre el `url` en nueva pestaña.
- ✅ Cards con stock limited muestran badge ⚠️.
- ✅ Cards sin imagen muestran un placeholder.
- ✅ Funciona si `items.jsonl` está vacío (mensaje "sin items aún").
