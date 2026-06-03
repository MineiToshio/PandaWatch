# Panel de Control

Interfaz web para ejecutar los scripts del proyecto sin acordarse de flags.
Todo corre en **un solo servidor** (`scripts/serve.py`, port 8000) — el panel
y el catálogo son partes del mismo proceso.

```
web/panel.html              ← UI Alpine.js + Tailwind (CDN, sin build)
                              Navegación integrada con catálogo y cover-preview.
                              Usa las mismas URLs relativas /api/* que el catálogo.
admin/index.html            ← redirect → http://localhost:8000/web/panel.html
                              (para bookmarks viejos)
scripts/serve.py            ← servidor único: catálogo + panel API + SSE
scripts/script_registry.py  ← fuente única de verdad de qué scripts y qué flags
scripts/run_local.sh        ← wrapper que lanza el servidor unificado
```

---

## Quick start

```bash
./scripts/run_local.sh
```

Lanza el servidor unificado:

- **Catálogo** — `http://localhost:8000/`
- **Panel de control** — `http://localhost:8000/web/panel.html`

`Ctrl+C` lo detiene. O directamente:

```bash
.venv/bin/python scripts/serve.py
```

---

## Arquitectura unificada

`serve.py` combina el catálogo y el panel en un solo proceso. Todos los
endpoints `/api/*` conviven en el mismo servidor:

| Endpoint | Descripción |
|---|---|
| `GET /api/health` | liveness probe |
| `GET /api/scripts` | JSON del registry (panel) |
| `POST /api/run` | lanza un script (panel) |
| `GET /api/jobs` / `GET /api/jobs/<id>` | estado de jobs (panel) |
| `GET /api/jobs/<id>/stream` | SSE stdout/stderr en vivo (panel) |
| `POST /api/jobs/<id>/stop` | detiene un job (panel) |
| `POST /api/feedback` | registra feedback (catálogo) |
| `POST /api/curation/{move,merge,remove}` | curación inmediata de items (catálogo) |
| `POST /api/approve` | aprobar/desaprobar una card — golden record (catálogo) |
| `POST /api/approve-edition` | aprobar/desaprobar todos los tomos de una edición (catálogo) |
| `POST /api/save-cover-preview` | guarda revisiones de portadas (catálogo) |

El servidor usa `ThreadingMixIn` para soportar múltiples conexiones SSE
en paralelo mientras atiende requests HTTP normales concurrentemente.

---

## Anatomía de la UI

Tres zonas:

1. **Izquierda** — Lista de scripts agrupados por categoría
   (Día a día / Mantenimiento / Auditoría), más historial de jobs
   recientes.
2. **Centro** — Detalle del script seleccionado:
   - "¿Qué hace?" y "¿Cuándo usarlo?" en lenguaje natural.
   - **Recetas rápidas (presets)**: un click carga una combinación de
     flags recomendada (ej. "🟢 Normal", "🧪 Prueba (no guarda nada)").
   - **Opciones básicas** siempre visibles + **Opciones avanzadas**
     plegadas detrás de un `details`.
   - Preview del comando equivalente + botón "📋 Copiar comando" +
     botón "▶ Ejecutar".
3. **Derecha** — Consola en vivo (SSE). Líneas coloreadas por nivel
   (`[ERROR]` rojo, `[WARN]` amarillo, `[OK]` verde, `[INFO]` azul,
   meta gris). Auto-scroll toggleable. Botón "⏹ Detener" si el job
   está corriendo.

**Persistencia**: la última selección y los valores de flags se guardan
en `localStorage` por script. Recargar la página no pierde tu setup.

---

## La fuente de verdad: `scripts/script_registry.py`

Toda la metadata que ves en la UI (qué scripts hay, qué flags tienen,
las descripciones para humanos, los presets) vive en
`scripts/script_registry.py`. Es un módulo Python puro que exporta
`SCRIPTS`, una lista de dicts.

`admin_serve.py` lo importa y lo expone tal cual vía `GET /api/scripts`.
La UI lo renderiza. Si querés agregar un script o cambiar un help text,
**solo tocás este archivo** — no hay HTML que actualizar.

### Estructura de cada entrada

```python
{
    "id": "scrape",                 # único, lo usa /api/run
    "category": "Día a día",        # agrupa en la sidebar
    "icon": "🔍",
    "name": "Buscar mangas nuevos (Scraper principal)",
    "tagline": "Una oración corta debajo del nombre.",
    "what": "Párrafo explicando qué hace, para alguien que no programa.",
    "when": "Párrafo explicando cuándo conviene correrlo.",
    "command": [PYTHON, "scripts/manga_watch.py"],
    "presets": [
        {
            "id": "normal",
            "label": "🟢 Normal (recomendado)",
            "desc": "Una línea explicando la receta.",
            "values": {"--fetch-details": True, "--workers": 8},
        },
    ],
    "flags": [
        _flag("--fetch-details", "Buscar portada, autor, ISBN y precio",
              "Help largo en lenguaje natural.",
              type="bool", default=True),
    ],
}
```

### Tipos de flag soportados

| `type` | UI render | CLI emit | Notas |
|---|---|---|---|
| `bool` | toggle switch | agrega `--flag` si True; si False no aparece | Para `action="store_true"` |
| `int` | input numérico | `--flag N` si no está vacío | |
| `float` | input numérico con step 0.1 | `--flag X` si no está vacío | |
| `str` | input texto | `--flag VAL` si no está vacío | |
| `csv` | input texto con placeholder de coma | igual que `str`, semántica de "lista CSV" | Solo cambia el placeholder |
| `choice` | select desplegable | `--flag opt` si no es vacío | requiere `choices=[...]` |

### Cómo agregar un script nuevo

1. Asegurate que tu script tenga un argparse decente.
2. Editá `scripts/script_registry.py` y agregá una entrada a `SCRIPTS`.
3. Reiniciá el admin server (`Ctrl+C` y `./scripts/run_local.sh`).
4. Refrescá `http://localhost:8000/web/panel.html` — aparece solo.

---

## API HTTP

La API vive bajo `http://localhost:8001/api/*` (puerto 8001, solo localhost).
`web/panel.html` la llama con `ADMIN_API = "http://localhost:8001"` prefijado
en todas las llamadas fetch/EventSource. CORS abierto para dev.

### `GET /api/health`

Liveness probe.

```json
{"ok": true, "ts": "2026-05-21T17:44:08.373799+00:00"}
```

### `GET /api/scripts`

Devuelve el registry tal cual.

```json
{ "scripts": [ { "id": "scrape", "category": "...", "flags": [...] }, ... ] }
```

### `POST /api/run`

Lanza un script.

**Body:**
```json
{
  "script_id": "source_health",
  "flags": { "--last-n": 3, "--output": "md" }
}
```

**Validación:** solo `script_id` en el registry + flags listados por script.
Tipos se castean. `400 {"error": "…"}` si algo no encaja.

**Respuesta:**
```json
{
  "job_id": "89bbfe6b616e",
  "label": "Auditoría de salud de fuentes  ·  --last-n=3 --output=md",
  "command": [".venv/bin/python", "scripts/audit/source_health.py", ...]
}
```

### `GET /api/jobs` / `GET /api/jobs/<id>` / `GET /api/jobs/<id>/stream` / `POST /api/jobs/<id>/stop`

Ver descripción completa de cada endpoint en el README anterior o directamente
en el código de `scripts/admin_serve.py`.

---

## Modelo de seguridad

| Vector | Mitigación |
|---|---|
| Atacante remoto en internet | API bindea solo `127.0.0.1`. No es ruteable. |
| Otro equipo en la misma LAN | Idem. |
| `script_id` arbitrario | Allowlist. Solo IDs que existen en `script_registry.py`. |
| Flags inyectados arbitrarios | Allowlist por script + cast de tipos. |
| Shell injection | No hay shell. `subprocess.Popen` usa `list[str]`, no `shell=True`. |
| Panel UI accesible desde internet | La UI es solo HTML — no puede ejecutar procesos. La API está en otro puerto, solo localhost. |

---

## Deploy: qué llevarse y qué dejar

**Catálogo (público) — incluir:**
- `web/` (incluyendo `panel.html` — es solo HTML, no ejecuta nada sin la API)
- `data/items.jsonl`
- `scripts/serve.py`

**Admin API (local) — DEJAR FUERA:**
- `scripts/admin_serve.py`
- `scripts/script_registry.py`
- `scripts/run_local.sh`
- `admin/` (solo contiene el redirect HTML, irrelevante en prod)

---

## Troubleshooting

**"No se pudo cargar la lista de scripts"** en la UI
→ El admin server no está corriendo. Lanzá `./scripts/run_local.sh`
(o solo `python scripts/admin_serve.py`). La UI en `web/panel.html`
llama a `http://localhost:8001/api/scripts` — si port 8001 no responde,
muestra ese error.

**"flag desconocido para <script>: --foo"** al ejecutar
→ El registry tiene un flag que el `argparse` real del script no tiene
(o viceversa). Sincronizá `scripts/script_registry.py` con el argparse.

**La consola se queda en blanco aunque el script imprime**
→ `admin_serve.py` exporta `PYTHONUNBUFFERED=1` al subprocess. Si el
script tiene su propio buffering, usá `python -u` o flush manual.

**Las líneas aparecen duplicadas**
→ La UI no debe precargar líneas del GET antes del SSE. Revisá
`attachToJob()` en `web/panel.html`.

**El job no termina aunque le di stop**
→ El proceso ignoró SIGTERM. A los 3s `admin_serve.py` manda SIGKILL.
Si tampoco salió, matalo a mano (`ps aux | grep python`, `kill -9 <pid>`).
