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

- **Grilla de items** con foto, título, score, país, editorial, tipo de producto
- **Búsqueda** por título (substring, case-insensitive, indexa `title` + `title_original` + `series_display`)
- **Filtros combinados (AND)**: país, editorial, idioma, tipo de producto, clase de fuente, score mínimo, solo stock limitado, signal types (multi-select chips)
- **Ordenamiento**: por score, fecha de detección, o título A-Z
- **Paginación** con contador de items que matchean los filtros
- **Modal de detalle**: imagen en carrusel (cuando hay múltiples), todos los campos, lista de fuentes con precio por fuente, descripción original e idioma
- **Multi-source view**: un producto con N fuentes se muestra como 1 card consolidada; el modal lista todas las fuentes con sus precios y URLs

### Curación de datos

- **Botón 👎 en el modal**: marca un item como "no debería estar aquí" con motivo libre
  - Elimina el item del catálogo (`items.jsonl`) inmediatamente
  - Mueve el item a `data/user_rejected.jsonl` con `rejection_reason` + timestamp
  - Si el item tiene varios fuentes (mismo `cluster_key`), elimina todas las filas del cluster
  - La card desaparece del dashboard sin recargar la página

### Presentación

- Paleta: fondo claro `#fafaf7`, acento rosa `#d63384`
- Cards con imagen aspect-ratio 3:4, badges de score (rojo/amarillo/gris), badge ⚠️ para stock limitado
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

## Stack técnico

HTML estático + Alpine.js (CDN) + Tailwind CSS (CDN). Sin npm, sin build step.
Para detalles de implementación ver `docs/scraper/ARCHITECTURE.md` sección "Web layer"
y los comentarios inline en `web/index.html`.

Corre con `scripts/serve.py` (servidor público en `0.0.0.0:8000`) o con
`scripts/run_local.sh` (lanza serve.py + admin_serve.py en paralelo).
