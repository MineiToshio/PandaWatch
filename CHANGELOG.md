# Changelog

Todos los cambios notables a `manga-watch` se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/) de forma laxa.

## [Unreleased] — Paginación automática

### Added

- **`find_next_page_url()`**: detecta link "siguiente página" usando 4
  estrategias en orden de confiabilidad:
  1. `<link rel="next">` en `<head>` (estándar SEO)
  2. Selectores comunes: `.next`, `.pagination__next`, `[aria-label*=Next]`,
     `li.next a`, etc.
  3. Texto del link: "Siguiente", "Next", "›", "»", "→", "Suivant",
     "Successivo", "次へ"
  4. Si la URL actual tiene `?page=N` (o `?p=N`, `?paged=N`) y existe un
     anchor en la página con `page=N+1`, devolver esa URL.
- **Loop de paginación en el scraper**: tras extraer una página, intenta
  buscar la siguiente y la procesa, hasta `--max-pages` o no-link.
- **CLI `--max-pages N`** (default 3): cap global de páginas por fuente.
- **YAML `max_pages: N`** por fuente: override del default (ej. catálogos
  grandes podrían usar 10).
- **Diagnostic** registra `pages_visited` por fuente.
- 10 tests nuevos para detección de paginación (rel=next, class, aria,
  texto, loops, cross-origin).

### Anti-features

- RSS feeds NO se paginan (siempre 1 página).
- Guardia anti-loop: URLs ya visitadas se ignoran.
- Cross-origin guard: el "next" debe ser del mismo dominio.
- Si una URL `?page=N+1` no aparece literalmente en algún anchor de la
  página, no se inventa.

### Real-world smoke test

| Fuente | Antes | Con paginación (3 págs) |
|---|---:|---:|
| MX - Panini México Boxsets | 12 candidatos | **29** (2.4×) |

Estimación para el próximo run completo: dataset 493 → **1500-2500** items.

### Performance

Cada fuente puede hacer hasta `max_pages` HTTP requests en serie.
- 150 fuentes × ~2 págs promedio = ~300 fetches extra.
- Sleep entre páginas: `min(args.sleep_seconds, 1.0)`.
- Estimación: run completo 20 min → ~30-40 min con --max-pages 3.

## [Unreleased] — Fase 1: Expansión de catálogo vía búsquedas dirigidas

Primer paso del plan de 3 fases documentado en `docs/PRD-catalog.md`.

### Added

- **`search_template + keywords` en sources.yml**: una entry con estos
  dos campos se expande automáticamente en N fuentes virtuales (1 por
  keyword). Ejemplo:
  ```yaml
  - name: "MX - Panini México (search)"
    search_template: "https://tiendapanini.com.mx/catalogsearch/result/?q={query}"
    keywords: ["edicion limitada", "deluxe", "cofre", ...]
  ```
  Genera 10 fuentes virtuales con nombres como
  `"MX - Panini México (search) [search: deluxe]"` y URLs con la query
  URL-encoded.
- **Tag automático `expansion`** en todas las fuentes virtuales para
  poder filtrarlas en runs específicos.
- **CLI flags nuevos**:
  - `--include-tags csv`: solo fuentes con al menos uno de esos tags.
  - `--exclude-tags csv`: ignora fuentes con esos tags.
  - `--only-tags csv`: alias estricto (mismo comportamiento que include).
- **10 entries de búsqueda** agregadas a `sources.yml` para editoriales
  prioritarias:
  - Panini MX, Panini ES (Magento search)
  - Norma Editorial ES (WordPress search)
  - Glénat FR, Pika FR, Ki-oon FR
  - Dark Horse Direct US, Yen Press US
  - Star Comics IT, Edizioni BD IT
  → Total: 66 fuentes virtuales adicionales.
- **9 tests nuevos** (67/67 total) para expansion + filtros por tags.

### Smoke test (Panini MX)

Solo de las 10 queries de búsqueda de Panini MX (vs 1 catálogo único antes):
- Candidatos con señales: 32 (vs ~12 antes)
- Reportables: 30
- 3x mejora con la misma editorial.

### Comandos sugeridos

```bash
# Bootstrap inicial del catálogo (solo búsquedas)
.venv/bin/python manga_watch.py --enable-js --only-tags expansion

# Run normal sin búsquedas (rápido, solo novedades)
.venv/bin/python manga_watch.py --enable-js --exclude-tags expansion

# Todo combinado
.venv/bin/python manga_watch.py --enable-js --fuzzy-keywords
```

## [Unreleased] — Detail-fetching para mejorar cobertura de autor

### Added

- **`fetch_author_from_detail()`** opt-in: tras detectar items, hace
  1 HTTP extra a la página individual del producto para extraer autor.
  Investigación de 4 sitios reales mostró que ninguno usa JSON-LD ni
  meta tags estándar — todos exponen autor mediante links del tipo
  `<a href="/autor/..."> / /auteur/ / /author/ / /mangaka/`.
  El extractor prueba 4 estrategias en orden de confiabilidad:
    1. JSON-LD (`<script type="application/ld+json">` con
       `author`/`creator`/`illustrator`/`writer`)
    2. meta tags (`name="author"`, `property="book:author"`,
       `og:book:author`, `twitter:creator`)
    3. Links a páginas de autor (`/autor/`, `/auteur/`, `/author/`,
       `/mangaka/`, `/kreator/`, `/verfasser/`, `/autore/`)
    4. Fallback: regex + selectores class-based sobre el body
- **CLI `--fetch-details`** (off por default).
- **CLI `--fetch-details-min-score N`** (default 70). Solo enriquece
  items urgentes para no agregar HTTP overhead innecesario.
- 10 tests nuevos: JSON-LD (string/object/list/inválido), links de
  autor (es/fr, blacklist, lowercase rejection).

### Filtros aplicados al detail-fetching

Solo enriquece items que cumplen TODOS los criterios:
- Status `new` o `changed` (no re-fetch para `seen`)
- Score ≥ `--fetch-details-min-score`
- `author` ya está vacío después del extract inicial
- `source_class` ∈ {official, retailer} — evita ruido de blogs/news
- URL distinta a la del listing (es page de detalle, no catálogo)

### Performance

- Solo afecta a items reportables high-score (~10-30 items por día)
- Reusa la misma `requests.Session` con sleep entre fetches
- Tras detail-fetch que actualiza autor, se recalcula `content_hash`
  para que aparezca como `changed` en próxima corrida y el state
  refleje el nuevo dato.

### Real-world testing

- Norma Editorial (Berserk/Resident Evil): 2/2 items enriquecidos
  → "Hajime Isayama", "CAPCOM | ZINO"
- Glénat (Dragon Ball): 1/1 enriquecido → "Akira Toriyama"

## [Unreleased] — Autor + stock_type

### Added

- **`author`**: extracción del mangaka/autor.
  - Selectores HTML estructurados (`[itemprop="author"]`,
    `[class*="author"]`, `[class*="byline"]`, `meta[name="author"]`).
  - Regex con prefijos: "Autor:", "Author:", "Auteur:", "Autore:",
    "著者:", "作者:", "原作:", "作画:", "by ", "par ", "di ", "du ".
  - Validación post-match: primer carácter debe ser mayúscula latina
    o CJK; blacklist filtra "la editorial", "sin autor", etc.
  - Vacío si no se encuentra (best-effort).
- **`stock_type`**: indicador de stock limitado.
  - Valor `"limited"` cuando hay señal explícita (signal_types
    `limited` / `made_to_order` / `retailer_exclusive`, o keywords
    "numerada", "while supplies last", "tirage limité", "数量限定",
    "完全受注生産", "受注生産", "予約限定", "初回限定", "limitata 500"…).
  - Valor `""` (vacío) cuando no hay señal — esto **NO afirma "regular
    permanente"**, simplemente no se pudo confirmar.
- 12 tests nuevos: regex multi-idioma, selectores HTML, blacklist,
  validación de mayúscula inicial, derivación desde signal_types.

### Changed

- `Candidate`: agrega `author` y `stock_type` (default `""`).
- `state.json`, `items.jsonl`, reporte Markdown incluyen los 2 campos.
  El reporte muestra `- **Autor:** X` y `- **Stock:** ⚠️ limitado /
  numerado` cuando aplica.
- `content_hash` ahora incluye author + stock_type para detectar
  cambios reales.

## [Unreleased] — Metadata extra por producto

### Added

- **`price`**: extracción multi-moneda con regex (€/$/¥/£/USD/MXN).
  Best-effort; queda vacío si no se encuentra.
- **`image_url`**: primera imagen de la card (src, data-src, srcset,
  data-srcset, data-original, data-lazy-src). Canonicalizada.
- **`release_date`**: fecha de lanzamiento. Patrones soportados:
  ISO 8601, dd/mm/yyyy, japonés (`2026年6月15日`), mes en EN/ES/FR/IT
  ("June 15, 2026", "15 de junio de 2026", "15 juin 2026", etc.).
  Prefiere fechas cerca de palabras-clave ("disponible", "release",
  "発売日", "sortie le", "salida", "preventa", "pre-order").
- **`product_type`**: derivado de título + signal_types. Valores:
  `artbook` / `fanbook` / `guidebook` / `boxset` / `novel` / `manga`.
  Vacío si no hay título ni descripción.
- 18 tests nuevos para los 4 extractores (multi-moneda, multi-idioma,
  word boundary, fallbacks vacíos).

### Changed

- `Candidate` dataclass: 4 campos nuevos (`price`, `image_url`,
  `release_date`, `product_type`), todos default `""`.
- `state.json` agrega los 4 campos (retrocompatible con states
  existentes — los campos faltantes se reciben como vacíos).
- `items.jsonl` agrega los 4 campos en cada línea nueva.
- Reporte Markdown muestra cada uno cuando tiene valor:
  `- **Tipo de producto:** boxset`
  `- **Precio:** € 19.99`
  `- **Fecha de lanzamiento:** 2026-06-15`
  `- **Imagen:** https://...` + preview con `![](url)`
- `content_hash` ahora incluye price + release_date + product_type para
  detectar cambios reales (precio bajó, fecha cambió, etc.).

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
