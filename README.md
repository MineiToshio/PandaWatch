# PandaWatch

> Personal tracker for **physical manga special editions** — limited
> editions, deluxe hardcovers, box sets, slipcases, artbooks, kanzenban,
> light novels with bonuses — scraped from ~160 sources across 9
> countries and 5 languages (ES, EN, FR, IT, JP).

Single-user. Runs locally. Browses results through a static dashboard.

## Documentación

Si vas a trabajar en el código (humano o asistente IA), empezá por:

- **[`CLAUDE.md`](CLAUDE.md)** — Resumen ejecutivo + decisiones de diseño
  + gotchas + convenciones. Léelo primero si querés contexto rápido para
  modificar algo.
- **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** — Pipeline completo,
  componentes, storage, filtros, performance baselines. Profundidad
  técnica.
- **[`docs/CONTROL-PANEL.md`](docs/CONTROL-PANEL.md)** — Panel web local
  para correr scripts sin acordarte de flags. Cómo se usa, cómo se
  extiende vía `scripts/script_registry.py`, API, modelo de seguridad,
  qué llevarse/dejar en deploy.
- **[`docs/SOURCES.md`](docs/SOURCES.md)** — Cómo agregar/mantener
  sources y wikis, cuándo usar `purity: "mixed"`, recetas paso a paso.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

En Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Uso

### Atajo: Panel de Control web

Si no querés acordarte de flags, hay una interfaz web local:

```bash
./scripts/run_local.sh
```

Lanza dos servers en paralelo:

- **Catálogo público** — http://localhost:8000/ (lo que un día se despliega)
- **Panel de Control (LOCAL)** — http://localhost:8001/ (bindea solo
  127.0.0.1, nunca se despliega)

Desde el panel elegís un script ("Scraper principal", "Filtrar lo que
NO es manga", "Backfill metadata", "Auditoría de fuentes"…), aplicás
una receta pre-armada o ajustás flags con toggles, ▶ Ejecutar, y mirás
los logs en vivo. Ver **[`docs/CONTROL-PANEL.md`](docs/CONTROL-PANEL.md)**
para detalles, API y cómo agregar tus propios scripts al panel.

Si preferís la línea de comandos, todo lo que sigue funciona igual.

### Scrapeo

```bash
# Scrape completo (todas las fuentes habilitadas)
python scripts/manga_watch.py

# Solo oficiales y retailers (más precisos)
python scripts/manga_watch.py --source-classes official,retailer --min-score 30

# Filtrar por países
python scripts/manga_watch.py --countries Francia,Italia,Japón

# Sólo una fuente nueva (etiquetada con "new-source")
python scripts/manga_watch.py --only-tags new-source

# Wikis comunitarias (calendarios por mes)
python scripts/manga_watch.py --bootstrap-wiki listadomanga    --wiki-from 2026-01 --wiki-to 2026-12
python scripts/manga_watch.py --bootstrap-wiki manga-sanctuary --wiki-from 2026-01 --wiki-to 2026-12
python scripts/manga_watch.py --bootstrap-wiki otaku-calendar  # solo expone mes actual
python scripts/manga_watch.py --bootstrap-wiki manga-mexico    # catálogo completo (sin fechas)

# Listar fuentes habilitadas
python scripts/manga_watch.py --list-sources
```

Después del scrape vas a tener:

- `data/items.jsonl` — base de datos con todos los items detectados
  (1 línea por URL única, upsert).
- `data/state.json` — cache para detectar cambios en próximos scrapes.
- `reports/YYYY-MM-DD.md` — reporte diario del último scrape.

### Browser web (dashboard)

```bash
./web/serve.sh
```

Esto arranca `http://localhost:8000/` y abre el browser. El dashboard
lee `data/items.jsonl` en vivo, así que cualquier scrape posterior se
refleja con un simple refresh.

**Importante:** no abras `web/index.html` con doble-click — el browser
bloquea `fetch()` a archivos locales por seguridad CORS. Usá siempre
el server.

Si necesitás un HTML auto-contenido (para abrir desde el FS o enviar
por mail), embebé la data primero:

```bash
python scripts/build_web.py            # embebe data en el HTML
python scripts/build_web.py --clear    # vuelve a modo fetch dinámico
```

### Retrofit (cuando cambiás reglas)

Los scripts en `scripts/retrofit/` reaplican cambios de código a los
items ya guardados. Cada uno hace una sola cosa:

```bash
python scripts/retrofit/clean_titles.py        # re-aplica clean_title()
python scripts/retrofit/filter_non_manga.py    # re-aplica is_likely_manga()
python scripts/retrofit/backfill_metadata.py   # re-fetch metadata faltante
```

Detalles en `scripts/retrofit/README.md`.

## Estructura del repo

```
sources.yml                 # 184 fuentes (de qué scrapear)
scripts/
  manga_watch.py            # scraper + filtros + IO
  build_web.py              # embebe data en index.html (opcional)
  serve.py                  # HTTP server con / → /web/ redirect
  wikis/                    # parsers de wikis comunitarias
  retrofit/                 # utilitarios de mantenimiento
tests/test_extraction.py    # 159 tests (correr con pytest)
web/index.html              # dashboard Alpine.js + Tailwind
data/                       # items.jsonl, state.json (gitignored)
docs/                       # arquitectura, sources, PRDs históricos
```

## Tests

```bash
.venv/bin/python -m pytest tests/test_extraction.py -q
```

Debería terminar en <1s con 159+ tests pasando.

## Stack

- **Backend**: Python 3 + requests + BeautifulSoup. Playwright opcional
  (`--enable-js`).
- **Frontend**: HTML estático + Alpine.js + Tailwind CSS via CDN
  (sin build step).
- **Storage**: JSONL con upsert por URL. Migrar a SQLite es lo que
  viene cuando despleguemos para multi-user
  (ver `docs/ARCHITECTURE.md`).
- **Hosting actual**: local (`scripts/serve.py`).
