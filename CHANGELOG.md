# Changelog

Todos los cambios notables a `manga-watch` se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/) de forma laxa.

## [Unreleased] — Fuzzy keyword matching

### Added

- **Fuzzy keyword matching opcional** en `detect_signals()`.
  - Activable con `--fuzzy-keywords` (off por default).
  - Cuando una regla compuesta como `"edición especial"` no matchea
    como frase exacta, el script intenta matchear palabras
    individuales fuertes ("especial") con score reducido (default
    score ÷ 3, configurable con `--fuzzy-divisor`).
  - `FUZZY_STOPWORDS` excluye genéricos como "edición/de/la/the/of/
    manga/vol/tomo…" que solos no aportan señal.
  - Solo aplica a phrases con espacios — frases monolíticas (japonés
    `限定版`, etc.) siguen como están.
  - Matches fuzzy se marcan en reporte como `phrase [fuzzy:token]`.
- 7 tests nuevos para el matching fuzzy: comportamiento off/on,
  stopwords, word boundaries, no-double-count, japonés.

## [Unreleased] — Playwright + YAML fixes

### Added

- **Playwright integration** opcional para fuentes JS-rendered.
  - Nuevo `kind: "js"` en YAML marca fuentes que requieren rendering.
  - CLI `--enable-js` activa el flujo (off por default).
  - `fetch_with_playwright()` lanza Chromium headless, hace
    `wait_for_function` esperando anchors con texto, scroll lazy-load,
    y devuelve HTML + metadata.
  - Singleton de browser para reutilizar entre fuentes.
  - `close_playwright()` cleanup al final del run.
  - Si `--enable-js` está y Playwright no instalado, error claro
    (no crash).
- **`requirements-playwright.txt`** opt-in install (`pip install -r`
  + `playwright install chromium`).
- **14 fuentes marcadas con `kind: "js"`** identificadas como JS-heavy
  en runs anteriores (Crunchyroll, Misión Tokyo, La Comiquería, etc.).

### Fixed

- **4 URLs 404** actualizadas en sources.yml:
  - MX - Panini Manga México → `/coleccionables/item-3`
  - US - Square Enix → `/release-calendar`
  - FR - Pika Planning → `/planning-sorties/`
  - JP - Animate Online Books → URL nueva, marcada `enabled: false`
    hasta que se pueda saltar bot detection.

### Changed

- Cuando `source.kind == "js"`, el flujo salta `detect_empty_or_js`
  porque ya renderizamos con browser; el resultado tras Playwright es
  nuestra mejor apuesta.

## [Unreleased] — Modo diagnóstico

### Added

- **`DiagnosticRecorder`** clase que captura por fuente: HTTP status,
  content-type, tiempo de fetch (ms), tamaño HTML, conteo de anchors
  totales y "significativos" (texto ≥10 chars), método de extracción
  usado (`yaml-selectors` / `clusters` / `rss` / `none`), # de cards
  detectados, breakdown de cards descartados (sin anchor, desc <40,
  desc >2000, url duplicada, sin señales), # de candidatos con señales,
  top 5 títulos con score, top 10 señales únicas, y error si lo hubo.
- **CLI `--diagnostic`** activa la grabación. Sin el flag, nada cambia.
- **CLI `--log-dir`** (default `logs/`) destino de los outputs.
- **`logs/diagnostic-<timestamp>.json`** estructurado, machine-readable.
- **`logs/diagnostic-<timestamp>.md`** legible para humanos, agrupado por
  estado: ok / no-candidates / empty / js-shell / no-links / http /
  request / robots / other.
- **`logs/raw/<slug>.html`** dump de los primeros 80 KB del HTML de
  fuentes problemáticas (no-candidates, empty, js-shell, no-links, http,
  request) para inspección posterior.
- **`fetch_with_metadata()`** nuevo helper: devuelve `(text, metadata)`
  con `http_status`, `content_type`, `fetch_ms`, `final_url`.
- **`extract_generic_html()`** acepta `info: dict | None` opcional;
  cuando se pasa, llena el dict con stats de extracción.

### Changed

- `.gitignore` ignora `logs/`.

## [Unreleased] — Fase 1: ruido y JS-rendered

### Added

- **`detect_product_clusters()`** detecta tarjetas de producto repetidas en HTML
  genérico sin selectores YAML. Busca contenedores con la misma firma
  `(tag, classes)` que aparezcan ≥3 veces con `<a href>` único, o selectores
  comunes de e-commerce (`.product-item`, `.product-card`, `[class*="product"]`,
  etc.).
- **`strip_chrome()`** elimina `header`, `footer`, `nav`, `aside` y contenedores
  cuyo `class`/`id`/`role` indique menú/navegación antes de extraer candidatos.
- **`detect_empty_or_js()`** marca fuentes con HTML <5000 chars, SPA shells
  (`<div id="root">`, `#app`, `#__next`, ...) vacíos, o menos de 5 anchors con
  texto significativo. La extracción se omite y la fuente queda registrada
  como problemática.
- **`problems`** estructurado en `run()` (lista de dicts con `source`,
  `category`, `message`). Categorías: `empty`, `js-shell`, `no-links`,
  `http`, `request`, `robots`, `selector`, `other`.
- **Sección "Fuentes problemáticas"** en el reporte Markdown, agrupada por
  categoría, además de la sección "Errores" ya existente.
- **CLI `--list-empty-sources`**: al final del run, imprime las fuentes
  detectadas como vacías o JS-renderizadas.
- **CLI `--only-source "nombre"`**: procesa solo la fuente con ese nombre
  exacto. Útil para debuggear una fuente sin correr las 82.
- **CLI `--max-age-days N`** (default 30, `0` desactiva): en feeds RSS,
  descarta entradas con `published_at` más viejas que N días. Fechas no
  parseables no se descartan.
- **`_parse_feed_date()`** parser best-effort de fechas RSS: RFC 2822 vía
  `email.utils.parsedate_to_datetime` con fallback a ISO 8601.
- **Tests `pytest`** en `tests/test_extraction.py` (13 casos) cubriendo las
  funciones nuevas. Nuevo `requirements-dev.txt`.

### Changed

- **`extract_generic_html()`**: ahora corre `strip_chrome()` y
  `detect_product_clusters()` cuando no hay selectores YAML. Los candidatos
  se filtran por longitud de descripción (40 ≤ len ≤ 2000) para descartar
  menús y bloques contaminados.
- **Reporte Markdown**: nueva sección "Fuentes problemáticas".

### Removed

- **Fallback "página entera con señales → un candidato sintético"** en
  `extract_generic_html`. Causaba ruido diario sobre páginas categoría
  (ej. `/coleccionables/manga` de Panini). Si no se detectan candidatos
  individuales, ahora preferimos silencio.

### Compatibility

- API CLI 100 % compatible: no se renombra ni se quita ningún flag.
- `state.json` schema sin cambios.
- Sin dependencias nuevas en `requirements.txt`. `pytest` queda en
  `requirements-dev.txt` (opcional).

### Cómo probar

```bash
# tests unitarios
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -v

# debug de una sola fuente
python manga_watch.py --only-source "MX - Panini Manga México" --dry-run

# listar fuentes JS/vacías
python manga_watch.py --list-empty-sources --dry-run

# RSS limitado a últimos 7 días
python manga_watch.py --max-age-days 7 --dry-run
```
