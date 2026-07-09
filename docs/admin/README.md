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
| `POST /api/batch/approve` | aprobar/desaprobar N cards/ediciones a la vez (catálogo) |
| `POST /api/batch/move` | mover N items a una edición a la vez (catálogo) |
| `POST /api/quality/check` | re-evalúa N items — live-update del Panel de Calidad (solo lectura) |
| `POST /api/image-search` | busca portadas candidatas por ISBN + Tavily (gestor de imágenes, solo lectura) |
| `POST /api/save-cover-preview` | guarda revisiones de portadas (catálogo) |

El catálogo (`web/index.html`) además expone **selección múltiple** (acciones
batch sobre los endpoints `/api/batch/*`) y un **modo curación rápida** por
teclado. El **Panel de Calidad** (`web/quality.html`) lanza
`data_quality.py` vía `POST /api/run` y consume `data/quality_report.json`.
Ver `docs/web-html/PRD.md`.

El servidor usa `ThreadingMixIn` para soportar múltiples conexiones SSE
en paralelo mientras atiende requests HTTP normales concurrentemente.

---

## Anatomía de la UI

Tres zonas:

1. **Izquierda** — Lista de scripts agrupados por categoría
   (⭐ Canónicos / Día a día / Mantenimiento / Retrofit / Auditoría /
   🔍 Calidad), más historial de jobs
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

`serve.py` (el servidor unificado, ver "Arquitectura unificada" arriba)
lo importa y lo expone tal cual vía `GET /api/scripts`; el legacy
`admin_serve.py` hace lo mismo si lo corrés standalone (ver más abajo).
La UI lo renderiza. Si querés agregar un script o cambiar un help text,
**solo tocás este archivo** — no hay HTML que actualizar.

**`script_registry.py` también es la fuente única de `build_command()` /
`resolve_preset_env()` / `mutates_items()`** (2026-07-08) — antes estaban
duplicadas byte-a-byte en `serve.py` y `admin_serve.py` (ya habían divergido:
sólo una copia sabía validar `choice`). Ambos servers las importan de acá.
`tests/test_script_registry.py` compara cada flag del registry, por AST,
contra el argparse REAL del script — corré ese test tras tocar el registry
o un argparse.

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
    "mutates_items": True,          # ¿puede escribir data/items.jsonl? (409 de S10)
    "presets": [
        {
            "id": "normal",
            "label": "🟢 Normal (recomendado)",
            "desc": "Una línea explicando la receta.",
            "values": {"--fetch-details": True, "--workers": 8},
        },
        {
            "id": "with_whakoom",
            "label": "🟡 + Whakoom spider",
            "desc": "Agrega spider profundo de Whakoom.",
            "env": {"INCLUDE_WHAKOOM_SPIDER": "1"},  # sólo INCLUDE_*/SKIP_*
            "values": {},
        },
    ],
    "flags": [
        _flag("--fetch-details", "Buscar portada, autor, ISBN y precio",
              "Help largo en lenguaje natural.",
              type="bool", default=True),
    ],
}
```

Todas las claves de un preset son **obligatorias**: `id`, `label`, `desc`,
`values` (dict) — el schema viejo con `flags` en vez de `values` es el bug
1.1 de la auditoría 2026-07-08 (el panel lo ignoraba en silencio: presets
"Dry-run" corrían sin `--dry-run`). `script_registry.py` valida esto con
`assert`s al importar; `tests/test_script_registry.py` lo prueba explícito.

`mutates_items` es obligatorio (bool) en toda entrada — lo usa el 409 de
`/api/run` (ver abajo) para no dejar correr dos mutadores de `items.jsonl`
al mismo tiempo desde el Panel (no tienen lock de archivo entre sí, a
diferencia de scrape-vs-scrape que sí usa `.scrape.lock`).

### Tipos de flag soportados

| `type` | UI render | CLI emit | Notas |
|---|---|---|---|
| `bool` | toggle switch | agrega `--flag` si True; si False no aparece | Para `action="store_true"` |
| `int` | input numérico | `--flag N` si no está vacío | soporta `choices=[...]` (ints) |
| `float` | input numérico con step 0.1 | `--flag X` si no está vacío | |
| `str` | input texto | `--flag VAL` si no está vacío | |
| `csv` | input texto con placeholder de coma | `--flag "a,b,c"` (UNA toma) | el script splitea comas internamente |
| `csv_multi` | igual que `csv` en la UI | `--flag a --flag b --flag c` (una toma por valor) | para `action="append"` sin split interno |
| `choice` | select desplegable | `--flag opt` si no es vacío | requiere `choices=[...]` |

### Cómo agregar un script nuevo

1. Asegurate que tu script tenga un argparse decente.
2. Editá `scripts/script_registry.py` y agregá una entrada a `SCRIPTS`
   (con `mutates_items`).
3. Corré `.venv/bin/python -m pytest tests/test_script_registry.py -q` —
   el test AST te dice si algún flag/default/choices no matchea el argparse real.
4. Reiniciá el server (`Ctrl+C` y `./scripts/run_local.sh`).
5. Refrescá `http://localhost:8000/web/panel.html` — aparece solo.

---

## API HTTP

**Arquitectura actual (2026-07-08): un solo server.** `web/panel.html` usa
`ADMIN_API = ""` (mismo origen) y pega contra `serve.py` en `:8000` — el
mismo proceso que sirve el catálogo (ver "Arquitectura unificada" arriba).
El legacy `admin_serve.py` (puerto 8001, standalone) sigue funcionando si
lo corrés a mano, con los mismos endpoints/validaciones, pero **no es el
flujo normal** — `run_local.sh` sólo lanza `serve.py`. Sin CORS abierto en
ninguno de los dos (el header `Access-Control-Allow-Origin: *` de
`admin_serve.py` se quitó — S7, 2026-07-08: permitía que cualquier página
de otro origen ejecutara scripts vía `/api/run`).

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
  "flags": { "--last-n": 3, "--output": "md" },
  "preset_id": "with_whakoom"
}
```

`preset_id` es **opcional** y sólo hace falta cuando el preset aplicado
tiene `"env"` (ej. "🟡 + Whakoom spider" de scrape_delta/full) — el cliente
**nunca manda env directo**, sería inyección de proceso arbitraria. El
servidor resuelve el `env` server-side desde `script_registry.resolve_preset_env()`,
que busca el preset por id en el registry y filtra sus claves contra la
allowlist `INCLUDE_*`/`SKIP_*` antes de pasarlo al `Popen` (1.2/S5, 2026-07-08).
`web/panel.html` sólo manda `preset_id` cuando el preset recién aplicado
tenía `env` — si el usuario toca un flag a mano después, se resetea a `null`.

**Validación:** solo `script_id` en el registry + flags listados por script.
Tipos se castean. `400 {"error": "…"}` si algo no encaja. También rechaza
con `403` si el header `Origin` no matchea el `Host` local (S7, defensa
CSRF/DNS-rebinding — sólo aplica a requests cross-origin; clientes sin
`Origin`, como curl o el propio panel same-origin, pasan siempre).

**Respuesta 200:**
```json
{
  "job_id": "89bbfe6b616e",
  "label": "Auditoría de salud de fuentes  ·  --last-n=3 --output=md",
  "command": [".venv/bin/python", "scripts/audit/source_health.py", ...]
}
```

**Respuesta 409** (S10, 2026-07-08) — el `script_id` pedido tiene
`mutates_items: true` en el registry y YA hay un job `"running"` que
también muta `items.jsonl` (dos retrofits pisándose en un
read-modify-write, sin lock de archivo entre sí):
```json
{
  "error": "ya hay un job mutador corriendo (clean_titles, job f437ca54884d) — esperá a que termine antes de lanzar otro que escribe items.jsonl",
  "job_id": "f437ca54884d",
  "script_id": "clean_titles"
}
```
El chequeo y el registro del job nuevo son **atómicos** (mismo lock en
`JobManager.start(block_if_mutator=True)`) — dos `POST /api/run`
simultáneos para scripts mutadores no pueden colarse los dos.

### `GET /api/jobs` / `GET /api/jobs/<id>` / `GET /api/jobs/<id>/stream` / `POST /api/jobs/<id>/stop`

Ver descripción completa de cada endpoint en el código de `scripts/serve.py`
(flujo normal) o `scripts/admin_serve.py` (legacy standalone, mismos endpoints).

---

## Modelo de seguridad

| Vector | Mitigación |
|---|---|
| Atacante remoto en internet | API bindea solo `127.0.0.1`. No es ruteable. |
| Otro equipo en la misma LAN | Idem. |
| `script_id` arbitrario | Allowlist. Solo IDs que existen en `script_registry.py`. |
| Flags inyectados arbitrarios | Allowlist por script + cast de tipos. |
| `env` arbitrario inyectado por el cliente | Nunca se acepta env del body — sólo `preset_id`, resuelto server-side contra la allowlist `INCLUDE_*`/`SKIP_*` (1.2/S5). |
| Shell injection | No hay shell. `subprocess.Popen` usa `list[str]`, no `shell=True`. |
| CSRF / DNS-rebinding hacia `/api/run` desde otra pestaña | `Origin` (si está presente) debe matchear `Host` → `403` si no (S7). `admin_serve.py` ya no manda `Access-Control-Allow-Origin: *`. |
| Dos mutadores de `items.jsonl` pisándose desde el Panel | `409` si ya hay un job `"running"` con `mutates_items: true`; check+registro atómicos (S10). |
| Panel UI accesible desde internet | La UI es solo HTML — no puede ejecutar procesos sin la API. |

---

## Deploy: qué llevarse y qué dejar

**Catálogo (público) — incluir:**
- `web/` (incluyendo `panel.html` — es solo HTML, no ejecuta nada sin la API)
- `data/items.jsonl`
- `scripts/serve.py`

⚠️ `serve.py` es el mismo proceso que expone `/api/run` — si desplegás
`serve.py` "tal cual" a un host público, `/api/run` queda accesible ahí
también (mitigado por el bind a loopback y el `Origin` check, pero pensado
para uso LOCAL). Para un deploy público real, la vía es servir sólo los
estáticos + el subconjunto de endpoints de catálogo, sin `/api/run` — fuera
del alcance de este documento (ver `docs/reference/architecture.md`).

**Admin (`script_registry.py`/panel) — pensado para uso LOCAL, no deploy:**
- `scripts/admin_serve.py` (legacy standalone, DEPRECATED — ver file-map.md)
- `scripts/script_registry.py`
- `scripts/run_local.sh`
- `admin/` (solo contiene el redirect HTML, irrelevante en prod)

---

## Troubleshooting

**"No se pudo cargar la lista de scripts"** en la UI
→ El server no está corriendo. Lanzá `./scripts/run_local.sh` (levanta
`serve.py` en `:8000`, catálogo + panel unificados). La UI en
`web/panel.html` usa `ADMIN_API = ""` (mismo origen) — si el server no
responde, muestra ese error. (El legacy `admin_serve.py` standalone en
`:8001` también sirve `/api/scripts` si lo corrés a mano.)

**"flag desconocido para <script>: --foo"** al ejecutar
→ El registry tiene un flag que el `argparse` real del script no tiene
(o viceversa). Sincronizá `scripts/script_registry.py` con el argparse y
corré `.venv/bin/python -m pytest tests/test_script_registry.py -q` para
confirmar — el test AST atrapa exactamente este tipo de deriva.

**"ya hay un job mutador corriendo" (409) al ejecutar**
→ Esperado (S10): otro script que también escribe `items.jsonl` sigue
`"running"`. Esperá a que termine (mirá la consola/`GET /api/jobs`) y
reintentá. Si el job quedó colgado, `POST /api/jobs/<id>/stop`.

**La consola se queda en blanco aunque el script imprime**
→ El server exporta `PYTHONUNBUFFERED=1` al subprocess. Si el script tiene
su propio buffering, usá `python -u` o flush manual.

**Las líneas aparecen duplicadas**
→ La UI no debe precargar líneas del GET antes del SSE. Revisá
`attachToJob()` en `web/panel.html`.

**El job no termina aunque le di stop**
→ El proceso ignoró SIGTERM. A los 3s `admin_serve.py` manda SIGKILL.
Si tampoco salió, matalo a mano (`ps aux | grep python`, `kill -9 <pid>`).
