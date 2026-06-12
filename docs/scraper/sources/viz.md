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
