# Panel de Control (admin)

Interfaz web local para ejecutar los scripts del proyecto sin acordarse
de flags. Vive en una app **separada del catálogo público**, bindeada a
`127.0.0.1`, y **nunca se despliega**.

```
admin/index.html            ← UI Alpine.js + Tailwind (CDN, sin build)
scripts/admin_serve.py      ← server HTTP + API + SSE
scripts/script_registry.py  ← fuente única de verdad de qué scripts y qué flags
scripts/run_local.sh        ← wrapper que lanza catálogo + admin en paralelo
```

---

## Quick start

```bash
./scripts/run_local.sh
```

Lanza ambos servers:

- **Catálogo** (público, deployable) — `http://localhost:8000/`
- **Panel de control** (local, admin) — `http://localhost:8001/`

`Ctrl+C` los baja. O lanzá uno por separado:

```bash
.venv/bin/python scripts/serve.py        # solo catálogo
.venv/bin/python scripts/admin_serve.py  # solo panel admin
```

---

## Por qué dos servers separados

El catálogo está pensado para desplegarse públicamente. El panel ejecuta
subprocesos locales (`subprocess.Popen`) y leería/escribiría datos
arbitrarios — exponerlo en producción sería un agujero de seguridad
crítico (RCE trivial). Separarlo en otro proceso, otro puerto, otro
bind, y otra carpeta es la diferencia entre "olvidarse de deshabilitar
algo en deploy" y "es físicamente imposible que el panel termine en
prod".

| | Server | Bind | Puerto | Carpeta | Despliega |
|---|---|---|---|---|---|
| Catálogo | `scripts/serve.py` | `0.0.0.0` | 8000 | `web/`, `data/` | ✅ |
| Panel | `scripts/admin_serve.py` | `127.0.0.1` | 8001 | `admin/` + registry en `scripts/` | ❌ |

El bind a `127.0.0.1` significa que **ni siquiera otros equipos en tu
Wi-Fi pueden alcanzar el panel** — solo procesos locales tuyos. Si
necesitás cambiar el bind (no recomendado), usá la env var
`ADMIN_BIND=0.0.0.0` o el flag `--bind` y entendé que cualquiera en la
red puede ejecutar tus scripts.

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
        # …
    ],
    "flags": [
        _flag("--fetch-details", "Buscar portada, autor, ISBN y precio",
              "Help largo en lenguaje natural.",
              type="bool", default=True),
        # …
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

**Convención de defaults**:
- `bool default=True` → el toggle viene prendido por defecto.
- `int/float default=N` → el input arranca con N pre-cargado.
- `str default=""` → vacío significa "no agregar el flag al comando".

### Marcar un flag como avanzado

```python
_flag("--connect-timeout", "Timeout HTTP", "…", type="int",
      default=10, advanced=True)
```

Los avanzados van detrás del `▸ Mostrar opciones avanzadas`. Pensá:
**básico** = lo que el dueño usa todos los días. **Avanzado** = lo que
ajustás una vez por año.

### Cómo agregar un script nuevo

1. Asegurate que tu script tenga un argparse decente.
2. Editá `scripts/script_registry.py` y agregá una entrada a `SCRIPTS`.
3. Reiniciá el admin server (`Ctrl+C` y `./scripts/run_local.sh` o
   `python scripts/admin_serve.py`).
4. Refrescá `http://localhost:8001/` — aparece solo.

No hay step extra: la UI itera sobre el JSON que devuelve la API.

### Cómo modificar un flag existente

- Cambió la descripción → editá el `help=...` de `_flag(...)`.
- Cambió el default → editá `default=...`.
- Lo querés esconder en avanzados → `advanced=True`.
- Lo querés sacar completamente → eliminá la línea. El usuario ya no lo
  ve y `admin_serve.py` rechazará cualquier payload que lo incluya
  (`flag desconocido para <script>: --foo`).

---

## API HTTP

Toda la API vive bajo `/api/*`. Origen mismo del HTML por default
(CORS abierto para flexibilidad de dev).

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

**Validación:** `admin_serve.py` solo acepta `script_id` que estén en
el registry y `flags` cuyo nombre esté en la lista del script. Tipos se
validan (un int es int, un choice está dentro de `choices`). Si algo no
encaja, devuelve `400 {"error": "…"}`.

**Respuesta:**
```json
{
  "job_id": "89bbfe6b616e",
  "label": "Auditoría de salud de fuentes  ·  --last-n=3 --output=md",
  "command": [".venv/bin/python", "scripts/audit/source_health.py", ...]
}
```

El job arranca en un thread del server con `subprocess.Popen`,
`stderr=STDOUT`, `bufsize=1`, `PYTHONUNBUFFERED=1` (para que las líneas
lleguen vivas). Stdout se lee línea por línea y se publica al condition
variable del job.

### `GET /api/jobs`

Lista todos los jobs en memoria (corriendo + recientes). Sin las líneas
de log.

### `GET /api/jobs/<id>`

Detalle de un job. **Incluye** todas las líneas bufferizadas hasta el
límite (`MAX_BUFFERED_LINES = 5000`).

### `GET /api/jobs/<id>/stream`

Server-Sent Events. **Reenvía desde el principio** las líneas
bufferizadas y sigue pusheando las nuevas en vivo. Cierra con un evento
`end` cuando el job termina.

```
data: {"line": "[admin_serve] PID 96904 — …"}

data: {"line": "# Source Health Audit"}

…

event: end
data: {"status": "exited", "exit_code": 0, "ended_at": "2026-05-21T17:50:00Z"}
```

Keepalive cada ~15s (comment SSE) por si hay un proxy intermedio.

**Nota:** como el stream entrega desde el principio, la UI **no debe**
pre-cargar las líneas con `GET /api/jobs/<id>` antes de abrir el SSE —
duplicaría todo el output. La UI solo lee metadata vía el GET y deja al
SSE poblar la consola.

### `POST /api/jobs/<id>/stop`

Manda `SIGTERM` al proceso. Si en 3s no salió, manda `SIGKILL`. El
estado del job pasa a `error` (exit code negativo) o queda en `running`
si el handler ya estaba terminando.

---

## El job manager

`admin_serve.py` mantiene un `JobManager` global con un diccionario de
jobs activos + un deque ordenado por inserción. Cap blando de 30 jobs
terminados en memoria (`MAX_FINISHED_JOBS`); el más viejo se descarta
cuando se supera. Los jobs vivos nunca se descartan.

Cada `Job` tiene:
- `id` (uuid corto), `script_id`, `label`, `command`
- `status`: `running` | `exited` | `error` | `killed`
- `started_at`, `ended_at`, `exit_code`
- `lines: deque(maxlen=5000)` con stdout combinado (stderr redirigido)
- `cv: threading.Condition` para que SSE se despierte cuando hay líneas
  nuevas o el job termina.

El server es `ThreadingTCPServer` (un thread por request) para soportar
múltiples SSE en paralelo + GETs/POSTs concurrentes.

---

## Modelo de seguridad

| Vector | Mitigación |
|---|---|
| Atacante remoto en internet | Server bindea solo `127.0.0.1`. No es ruteable. |
| Otro equipo en la misma LAN | Idem. Probar con `curl http://<tu-ip-LAN>:8001/` → "Couldn't connect". |
| Otra app en tu propio equipo (proceso local malicioso) | Cualquier proceso puede hacer requests a `127.0.0.1:8001` y disparar scripts. Si confiás cosas raras en tu máquina, no corras el admin. |
| `script_id` arbitrario | Allowlist. Solo IDs que existen en `script_registry.py` se aceptan. |
| Flags inyectados arbitrarios | Allowlist por script. Solo flags listadas en el registry se permiten. Valores se castean al tipo declarado (int/float). |
| Shell injection en flags string | No hay shell. `subprocess.Popen` se llama con `list[str]`, no con un string ni `shell=True`. El usuario puede meter `;rm -rf /` en un input — llegaría al script como un argumento literal, no se ejecuta. |
| Despliegue accidental del panel | El admin vive en `admin/`, `scripts/admin_serve.py` y `scripts/script_registry.py`. No incluir esos en el build de prod. Aunque se cuelen, sin el server admin corriendo no se sirven. |

---

## Deploy: qué llevarse y qué dejar

**Catálogo (público) — incluir:**
- `web/`
- `data/items.jsonl` (o el SQLite que migres)
- `scripts/serve.py` (o reemplazarlo por nginx / Vercel / Fly / etc.)

**Panel (local) — DEJAR FUERA:**
- `admin/`
- `scripts/admin_serve.py`
- `scripts/script_registry.py`
- `scripts/run_local.sh`

Si usás un `.dockerignore` o similar, agregalos explícitamente. Si
hacés `git archive` o builds parciales, asegurate de que esos paths
no entren.

---

## Troubleshooting

**"No se pudo cargar la lista de scripts"** en la UI
→ El admin server no está corriendo, o estás abriendo `admin/index.html`
con `file://` en vez de via `http://localhost:8001/`. Lanzá
`./scripts/run_local.sh` (o solo `python scripts/admin_serve.py`).

**"flag desconocido para <script>: --foo"** al ejecutar
→ El registry tiene un flag que el `argparse` real del script no tiene
(o viceversa). Sincronizá `scripts/script_registry.py` con el argparse
del script.

**La consola se queda en blanco aunque el script imprime**
→ El script bufferea stdout. `admin_serve.py` exporta
`PYTHONUNBUFFERED=1` al subprocess, pero si el script tiene su propio
buffering (ej. `print(..., flush=False)` en loops o subprocess shell)
podés necesitar `python -u` o flush manual.

**Las líneas aparecen duplicadas**
→ Bug ya arreglado: la UI ya no precarga líneas del GET antes del SSE.
Si lo ves de nuevo, revisá `attachToJob()` en `admin/index.html`.

**El job no termina aunque le di stop**
→ El proceso ignoró SIGTERM. A los 3s `admin_serve.py` manda SIGKILL.
Si tampoco salió, es un zombie del kernel; matalo a mano (`ps`, `kill -9`).

**El admin escucha en 0.0.0.0 sin querer**
→ Revisá la env var `ADMIN_BIND` y el flag `--bind`. Default debería
ser `127.0.0.1`. `lsof -nP -iTCP -sTCP:LISTEN | grep 8001` te dice qué
interface está usando.

---

## Cosas que NO hace (a propósito)

- **No tiene auth.** No la necesita: bind a `127.0.0.1` + allowlist de
  scripts es suficiente para single-user-local. Si algún día querés
  exponerlo en una red privada, agregás un token simple en
  `admin_serve.py` antes de abrir el bind.
- **No encadena scripts.** Cada job es un script. Si querés correr
  "scrape → cleanup → build" usá `scripts/overnight_run.sh`.
- **No persiste jobs entre reinicios del server.** El historial vive en
  memoria. Si querés histórico permanente, mirá los logs que cada
  script ya escribe en `logs/`.
- **No edita archivos.** Solo lanza scripts. Cualquier mutación pasa
  por el script.

---

## Roadmap (no comprometido)

- Notificación del navegador al terminar un job largo.
- Botón "ver logs anteriores" leyendo `logs/overnight-*/`.
- Cadenas declarativas en el registry (`pipeline: [filter_non_manga,
  filter_collectible, rescore]`) para reproducir overnight desde la UI.
- Modo dark.

Si te interesa alguno, abrí un issue o tirá un PR.
