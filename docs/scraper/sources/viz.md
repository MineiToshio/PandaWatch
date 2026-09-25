# Fuente: VIZ Media

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-12 (fix search URL + selectores, añadidos keywords VIZBIG/3-in-1/complete edition).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | VIZ Media |
| **URL base** | `https://www.viz.com/` |
| **Índice / punto de entrada** | Wiki de artbooks: `https://www.viz.com/calendar/{YYYY}/{M}` (calendario mensual). Búsqueda: `https://www.viz.com/search?search={query}` (search-template) |
| **Tipo de fuente** | Editorial oficial (editor en inglés de Shueisha/Shonen Jump + licencias propias) |
| **`kind` en sources.yml** | Wiki de artbooks: `wiki` (módulo propio). Búsqueda: `html` (entrada `US - VIZ Media (search)`) |
| **`source_class`** | Wiki: `trusted_catalog`. Búsqueda: `official` |
| **País** | Estados Unidos (`Estados Unidos`) — fuente mono-país |
| **Idioma** | Inglés |
| **Cobertura** | Ediciones especiales físicas EN: box sets, deluxe / definitive / legendary editions, hardcovers, collector's / anniversary editions, artbooks (Color Walk Compendium), companion / fan books |
| **Aporte al corpus** | ~25 items |
| **Parser / módulo** | Wiki: `scripts/wikis/viz_artbooks.py`. Búsqueda: entrada `US - VIZ Media (search)` en `sources.yml` (~línea 1584) |

**Editoriales / países reales en el corpus** (snippet de §10):

- **Items**: 25
- **Países**: Estados Unidos (25)
- **Editoriales**: VIZ Media (25)

Todo el aporte es VIZ Media en Estados Unidos, en inglés. `publisher` = VIZ Media,
nunca la tienda (#44 — aplicado, aunque acá editorial y origen coinciden).

**Por qué importa / qué aporta de único**: VIZ es el **editor oficial en inglés del
catálogo de Shueisha** (One Piece, Naruto, Bleach, Jujutsu Kaisen, Chainsaw Man…)
más sus propias licencias. Es la fuente principal de **ediciones especiales en inglés
del mercado de Estados Unidos**: box sets, deluxe / definitive editions, hardcovers,
collector's / anniversary editions y, en especial, los **artbooks** (Color Walk
Compendium) y companion books que ninguna otra fuente cubre con esta profundidad para
el mercado US.

---

## 2. Descripción técnica de la fuente

VIZ se ingiere por **dos caminos** distintos de la misma editorial (ver §5):

**A. Wiki de artbooks / ediciones especiales — calendario mensual** (`viz_artbooks.py`):

- **`calendar/{YYYY}/{M}`** — listado server-rendered (sin JS) de TODOS los lanzamientos
  de un mes. Cada mes se fetchea por separado (`fetch_calendar_month`).
- **URL de producto**: `/manga-books/{manga|art-book}/{slug}/product/{id}[/{format}]`
  (regex `_PRODUCT_RE`). La **edición va codificada en el slug** y el **formato en el
  sufijo del path** (`/hardcover`). Ejemplos:
  - `/manga-books/manga/vagabond-definitive-edition-volume-5-0/product/8681/hardcover`
  - `/manga-books/art-book/one-piece-color-walk-compendium-.../product/.../hardcover`
  - `/manga-books/manga/one-piece-box-set-.../product/...`
- **Pre-filtro por URL** (`special_signals_from_url`): se queda SOLO con ediciones
  especiales sin hitear el detail page. Califica si el path es `/art-book/`, o el sufijo
  es `/hardcover`, o el slug contiene un keyword de edición especial (`box-set`,
  `complete-box`, `deluxe`, `definitive-edition`, `legendary-edition`, `collector`,
  `N-anniversary`, `color-walk`, `compendium`, `illustration`, `art-of`/`artbook`,
  `fanbook`/`cookbook`/`recipes`). Los tomos paperback regulares se descartan ahí mismo.
- **Detail page** (`parse_product_page`): de ahí salen título (de `og:title`, quitando el
  prefijo `VIZ: See `), ISBN-13 (regex `97[89]\d{10}` sobre el texto), precio (`$N.NN`),
  formato (Hardcover / Paperback / Box set), portada y descripción.
- **Identificador de producto**: ISBN-13 (clave de dedup cross-month). Si no aparece en el
  texto, se reconstruye desde el nombre de la portada CloudFront (`/products/{isbn10}.ext`
  → `_isbn10_to_13`). Si no hay ISBN, el producto se descarta (`return None`).
- **Anti-bot / quirks**: páginas server-rendered, sin JS ni Cloudflare conocido. La **fecha
  de lanzamiento NO está en el detail page** — se setea desde el mes del calendario
  (`{YYYY}-{MM}-01`). El calendario **no tiene datos antes de ~2013**: `_MIN_YEAR=2013`
  clampea la iteración para no malgastar requests vacíos.
- **Calidad de imágenes**: la portada real sale de CloudFront
  (`dw9to29mmj727.cloudfront.net/products/{isbn10}.{jpg|png}`); se saltean placeholders del
  CDN (#6).

**B. Búsqueda de ediciones especiales — search-template** (`sources.yml`):

- Entrada `US - VIZ Media (search)` con `search_template:
  "https://www.viz.com/search?search={query}&category=Manga"` (fix 2026-06-12:
  añadido `&category=Manga` — sin este param devuelve "series list" en vez de
  productos) y `keywords: [box set, VIZBIG, omnibus, deluxe, collector, hardcover,
  definitive, 3-in-1, complete edition]`.
- Selectores YAML (2026-06-12): `item_selector: "article.g-3"`,
  `title_selector/link_selector: "a.color-off-black.hover-red"`. Cada query
  devuelve hasta 32 artículos de producto.
- `purity: manga_only` — la búsqueda opera sobre la sección Manga del sitio.
- `_expand_search_template()` (manga_watch.py) expande la entrada en N entradas
  virtuales, una por keyword, cada una con la URL de búsqueda ya formateada.
- **Antes del fix (hasta 2026-06-12)**: devolvía 0 candidatos porque la URL sin
  `category=Manga` muestra una vista de "series" sin elementos de producto.

---

## 3. Proceso de ingestión — vista de producto

> Camino A (wiki de artbooks): VIZ es un calendario de lanzamientos mes a mes con la
> edición codificada en la URL. La lógica de captura es directa.

1. **Tomar un mes del calendario** (`calendar/{YYYY}/{M}`): la lista de lanzamientos de VIZ
   de ese mes.
2. **Pre-filtrar por URL** cada producto: sólo siguen los que la URL marca como edición
   especial (art-book, hardcover, box-set, deluxe, definitive, collector, anniversary,
   artbook, fanbook). Los tomos regulares se descartan sin abrir el detail page.
3. **Por cada producto que pasó**, abrir su detail page y armar el item: título, ISBN,
   precio, formato, portada, descripción. Sin ISBN no entra. Se deduplica por ISBN entre
   meses.
4. **Repetir** con el siguiente mes hasta cubrir todo el rango (desde ~2013).

**Reglas de producto que nunca se rompen:**
- El país de la edición es Estados Unidos (es el de la editorial/idioma; #46).
- `publisher` = VIZ Media (#44).
- Un **omnibus / 3-in-1 "pelado"** NO califica solo (#18): sólo entra si además es
  hardcover o tiene otro qualifier premium. El gate `is_collectible_edition` aguas abajo
  termina de filtrar.

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

VIZ se ingiere por dos caminos, con distinto comportamiento full/delta:

**A. Wiki de artbooks** (`--bootstrap-wiki viz`):

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script / paso | `scrape_full.sh` (paso **2p**) | `scrape_delta.sh` (paso **2o**) |
| Invocación | `--bootstrap-wiki viz --wiki-from 2000-01 --sleep-seconds 1.0 --min-score 20` | `--bootstrap-wiki viz --wiki-from "$LISTADO_CAL_FROM" --sleep-seconds 1.0 --min-score 20` |
| Discovery | calendario mes a mes desde `2000-01` (clampeado a `_MIN_YEAR=2013`) hasta el mes actual → catálogo histórico completo | calendario desde `LISTADO_CAL_FROM` (~mes actual − 2) hasta el mes actual → sólo novedades recientes |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Cuándo | refresh completo del catálogo | novedades recientes |

- En full, `--wiki-from 2000-01` se clampea a 2013 dentro de `iter_year_months` (no se
  pierden requests). El catálogo de VIZ es chico, por eso el timeout del paso es 300s en
  ambos scripts.

**B. Búsqueda (search-template)**: corre como parte de la **fase 1 (scrape de fuentes del
YAML)** de AMBOS scripts, idéntica en full y en delta (la entrada `US - VIZ Media (search)`
no tiene discovery distinto por modo). Se ejecuta junto con las demás entradas del YAML,
antes de los wikis.

---

## 5. Proceso de ingestión — técnico

### 5.1 Modelo de datos / claves

- **Wiki de artbooks**: el módulo emite `Candidate`s vía su `_virtual_source()` con
  `name="US - VIZ Media Special Editions"`, `country="Estados Unidos"`,
  `language="English"`, `publisher="VIZ Media"`, `source_class="trusted_catalog"`,
  `kind="wiki"`, `purity="manga_only"`. País = edición (#46): Estados Unidos.
- Identidad del producto = **ISBN-13** (dedup cross-month en `bootstrap` vía `seen_isbns`);
  el dedup global por URL/ISBN lo hace `process_state` aguas abajo.
- No tiene reglas de agrupación propias (no es como ListadoManga).

### 5.2 Qué captura el parser (mapea el §3 al código)

- `fetch_calendar_month(y, m, session)` recorre el mes y aplica `special_signals_from_url`
  a cada URL de producto → devuelve sólo los paths que pre-califican (deduplicados).
- `special_signals_from_url(href)` → `(qualifies, signals, product_type)`. Mapeo
  slug/sufijo → señal (`_SLUG_SIGNALS`):
  - `box-set` / `complete-box` → `box_set` (product_type `boxset`)
  - `deluxe` / `definitive-edition` / `legendary-edition` → `deluxe` (`special`)
  - `collector` → `collector` (`special`); `N-anniversary` → `lore_edition` (`special`)
  - `color-walk` / `compendium` / `illustration` / `art-of` / `artbook` / sección
    `art-book` → `artbook` (`artbook`)
  - `fanbook` / `recipes` / `cookbook` → `fanbook` (`fanbook`)
  - sufijo `/hardcover` → `hardcover` (`special` si no había otro)
- `fetch_product` + `parse_product_page` arman el dict (title, isbn, format,
  cover_url, description); `_meta_to_candidate` lo convierte en `Candidate`, inyectando
  hints en la descripción (`hint_map`: "Box Set.", "Deluxe edition.", "Hardcover."…) para
  que `detect_signals` levante las señales aguas abajo (#10 — las señales salen del item,
  no del nombre de la fuente).
- Gate de entrada: `--min-score 20` (en `bootstrap`, `cand.score < min_score`) **y** el
  gate `is_collectible_edition` del `flush_fn` genérico de manga_watch.py.
- **Búsqueda (search-template)**: `_expand_search_template()` (manga_watch.py ~3539)
  expande `US - VIZ Media (search)` en una entrada virtual por keyword; cada una se recorre
  con el extractor HTML genérico. `source_purity` se propaga a los hijos (#7).

### 5.3 Flujo end-to-end

- **Wiki**: corre como **paso 2p** de `scrape_full.sh` y **paso 2o** de `scrape_delta.sh`,
  después del scrape de fuentes del YAML (fase 1) y junto con los demás wikis. Escribe a
  `data/items.jsonl` incrementalmente vía `flush_fn` (por mes).
- **Búsqueda**: corre dentro de la **fase 1** (scrape de fuentes del YAML) de ambos
  scripts, como una entrada HTML más.
- Luego ambos caminos pasan por las fases comunes (cleanup retrofits → build → validate).
  No hay retrofits dedicados a VIZ.
- Tras el scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr
  `/watch-standardize-catalog` automáticamente.

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural del pipeline (aplica a TODO el corpus,
  sin red). Es la verificación principal para esta fuente.
- No hay auditoría de red dedicada ni enforcer/idempotencia propios: es una fuente plana sin
  reglas de agrupación.
- Sanity manual: re-fetchear un mes del calendario y comparar lo que emite el parser contra
  el corpus (ver runbook §10).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#18 (omnibus pelado)**: un omnibus / 3-in-1 sin otro qualifier NO califica como
  coleccionable. ✅ Por eso `omnibus` NO está en `_SLUG_SIGNALS` del wiki; sólo entra si
  además es hardcover o premium. (Nota: la **búsqueda** sí lleva `omnibus` como keyword,
  pero el gate `is_collectible_edition` aguas abajo lo filtra igual).
- **#6 (placeholders de imagen)**: el CDN sirve placeholders; ✅ el parser los saltea y se
  queda con la portada CloudFront real (o cae a `og:image` no-placeholder).
- **Fecha no está en el detail page**: ✅ se setea desde el mes del calendario
  (`{YYYY}-{MM}-01`), no desde la ficha.
- **Sin ISBN → se descarta**: ✅ el ISBN es la clave de dedup; si no aparece ni se puede
  reconstruir desde la portada CloudFront, el producto no entra.
- **Decisiones (lo que NO se hace)**: no se mergea cross-país (#46); los tomos paperback
  regulares se descartan en el pre-filtro por URL sin abrir el detail page.

---

## 9. Pendientes / limitaciones conocidas

- **Calendario sin datos antes de ~2013**: lanzamientos previos a 2013 no se capturan
  (clamp `_MIN_YEAR`). El catálogo histórico arranca ahí.
- **Aporte chico** (~25 items): el catálogo de ediciones especiales de VIZ es acotado; el
  timeout de los pasos 2o/2p es 300s.
- **Entradas VIZ deshabilitadas en `sources.yml`** (mencionadas de pasada, fuera del
  pipeline canónico):
  - `US - VIZ Blog` (`https://www.viz.com/blog`, `enabled: false` desde 2026-06-01: feed de
    noticias, 0 items coleccionables en corpus).
  - `SOCIAL - VIZ Media Bluesky` (`https://bsky.app/profile/viz.com`, deshabilitada; usar
    el handle `viz.com`, NO `vizmedia.bsky.social` que está stale desde nov-2024).
- {{pendiente: confirmar si las señales de los `--min-score 20` del wiki y el gate de
  búsqueda se solapan o se complementan en la práctica — hoy el corpus muestra 25 items y
  no se distinguió en este pase cuántos vienen del wiki vs de la búsqueda.}}

---

## 10. Runbook / comandos útiles

```bash
# Scrape del WIKI de artbooks (igual que el pipeline, deja raw):
#   FULL: catálogo completo (clampeado a 2013)
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki viz --wiki-from 2000-01 --sleep-seconds 1.0 --min-score 20
#   DELTA: sólo meses recientes
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki viz --wiki-from 2026-04 --sleep-seconds 1.0 --min-score 20

# Debug del módulo directo (sin escribir a items.jsonl): un rango de meses
.venv/bin/python scripts/wikis/viz_artbooks.py --wiki-from 2026-01 --wiki-to 2026-05

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "viz.com"
def hit(it):
    blobs=[it.get('url','') or '']+[ (s.get('url','') or '') for s in it.get('sources',[]) ]
    return any(NEEDLE in b for b in blobs)
items=[json.loads(l) for l in open("data/items.jsonl") if l.strip()]
sel=[it for it in items if hit(it)]
print("items:", len(sel))
print("países:", Counter((it.get('country') or '') for it in sel if it.get('country')))
print("editoriales:", Counter((it.get('publisher') or '') for it in sel if it.get('publisher')).most_common(20))
PY
```

**Antes de cerrar cualquier cambio en VIZ**: validar (`validate_corpus`, 0 duras) → tests
(`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza esta
ficha.

## 2026-09-07 — 429 puntual en el fetch de una ficha (no bloqueante)

En el bootstrap `02o-viz` (artbooks US) apareció **un** rate-limit al pedir la ficha de
producto:

```
[viz] ERROR product https://www.viz.com/manga-books/manga/jojo-s-bizarre-adventure-part-7-steel-ball-run-volume-9-0/product/8984/hardcover: 429 Client Error: Too Many Requests
```

Es un único item de 36 s de corrida; el resto del bootstrap terminó bien y la fase no
falló (rc=0). Se anota como **línea base**: si el mismo 429 vuelve a aparecer en corridas
sucesivas o escala a varias fichas, la fuente necesitaría entrar a un `throttle_group`
(como se hizo con las Shopify en `throttle_group: shopify`). Con una sola ocurrencia
aislada no hay evidencia para pedir cambio de configuración.

### Integridad de ingestión — continuación 2026-09-24

Los fallos de transporte ahora registran `[WIKI-ISSUE]` en la sesión. El dispatcher
conserva los resultados parciales y termina con error; incluye el fallo en el
reporte. Una respuesta fallida no equivale a catálogo vacío. El watermark por
fuente solo avanza después de persistir corpus y estado, sin incidencias ni
límites alcanzados. Tras una interrupción, el calendario amplía su ventana hasta
el último inicio exitoso con siete días de solapamiento. Un import histórico
acotado, un chunk explícito o un dry-run no adelantan ese watermark.

### Auditoría histórica — 2026-09-24

El recorrido 2013-01→2026-09 encontró límites temporales 429 en 33 calendarios
y 19 fichas. Conservó lo recibido y terminó con salida 1; se reintentan esos
huecos por separado y con pausas. Una respuesta de ficha HTTP 200 sin metadata
de libro parseable ahora también registra incidencia, en vez de omitirla como
si el recorrido fuera completo. Los detalles recuperados fuera del calendario
no reciben una fecha inventada: si no existe, queda vacía.

Los 52 grupos fallidos (33 calendarios + 19 detalles) se reintentaron con pausas.
Quedó un 429 en febrero de 2022, resuelto con una última corrida de ese mes (2
candidatos, sin incidencias). El staging de reintento recuperó 48 URLs primarias
ausentes; la corrida inicial con salida 1 sigue registrada como parcial.


## Revalidación de calendarios y catálogos — 2026-09-24

Full y delta incluyen ahora el mes actual +3 mediante LISTADO_CAL_TO.
La prueba 2026-10–12 terminó sin errores con 8 candidatos/reportables. Antes,
el default al mes actual omitía esos anuncios. El timeout full pasa a 1800 s
para permitir el recorrido histórico con pausas y reintentos.

El parser limpia también el prefijo de navegación `VIZ: Read a Free Preview of`
del og:title, sin cambiar el nombre del libro. Un producto enlazado que devuelve
404 se registra como cobertura incompleta y no permite adelantar el checkpoint.

### Reparación de referencias históricas — 2026-09-24

Se quitó 1 referencia de `www.viz.com` asociada a otra fila con ISBN
válido diferente del producto cuya URL primaria es esa misma referencia. Se
conservan ambos productos y su URL primaria; no se fusionan por ISBN. Evidencia
por URL/ISBN en `reports/ingestion-audit-2026-09-24/closure/publication-2-manifest.json`.

Cierre 2026-09-25: se incorporaron 35 referencias adicionales de esta fuente
a productos ya existentes, recuperadas del resultado del upsert en staging.
Cada URL tenía un único propietario propuesto y no existía aún en ninguna
ficha publicada; se conserva el producto canónico. Manifest: `publication-3-manifest.json`.

### Delta 2026-09-25 — 429 puntual + idioma fuera del enum

**(a) Rate-limit 429.** Una sola página de detalle devolvió `429 Too Many Requests`:

```
[viz] ERROR product .../my-hero-academia-box-set-2/product/9072/paperback: 429
```

La corrida siguió normalmente: **16 candidatos** emitidos sobre los 6 meses de
ventana, 16 portadas espejadas, 0 fallidas. El paso salió `rc=1` sólo por la
incidencia registrada. Es degradación parcial de un item, no caída de la fuente;
si se repite, bajar la concurrencia o subir `--sleep-seconds` para VIZ.

**(b) `language` fuera del enum — 148 items.** La fuente emite `"English"` (inglés)
en vez del valor del enum del corpus, `"Inglés"`. Medido en la corrida de hoy,
`validate_corpus` reporta **LANG_ENUM 229** en total y VIZ es el principal
contribuyente:

| Fuente | items con idioma crudo |
|---|--:|
| US - VIZ Media Special Editions | 148 |
| US - Kinokuniya Exclusives | 47 |
| US - PRH Comics | 17 |
| US - Yen Press Calendar | 8 |
| JP - Shueisha Books | 4 |

De los 229, **157 se detectaron el 2026-09-25** (la ingesta ad-hoc de la madrugada),
o sea el defecto está activo y creciendo, no es deuda histórica congelada.

Es `warn`, no violación dura, así que no frena el gate — pero el idioma es un filtro
de la UI y un valor fuera del enum no matchea. **No aplicado**: el fix correcto es
normalizar en el extractor (fuente única), no un retrofit por fuente. Decisión del owner.
