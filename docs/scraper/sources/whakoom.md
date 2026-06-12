# Fuente: Whakoom

> ⚠️ **PODA 2026-06-12 (poda de fuentes muertas)** — `ES/LatAm - Whakoom Novedades`: Novedades deshabilitada (kind js/Playwright → 1 item neto histórico). El spider whakoom opt-in sigue disponible (INCLUDE_WHAKOOM_SPIDER=1).
> Registro completo: [descartadas/README.md](descartadas/README.md).

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Whakoom |
| **URL base** | `https://www.whakoom.com` |
| **Índice / punto de entrada** | `https://www.whakoom.com/newtitles` (~415 novedades editoriales recientes) |
| **Página de un tomo** | `https://www.whakoom.com/comics/{shortcode}/{slug}/{vol}` |
| **Página de una edición** | `https://www.whakoom.com/ediciones/{id}/{slug}` (colección, NO un tomo — #14) |
| **Tipo de fuente** | Catálogo comunitario / tracker de coleccionistas (no es tienda) |
| **`kind` en sources.yml** | `html` (la fila /newtitles); el spider profundo es un módulo wiki (`--bootstrap-wiki`) |
| **`source_class`** | `trusted_media` |
| **País(es)** | España / LatAm — Argentina, México, España; el spider también captura ediciones en otros países (ver §1 corpus) |
| **Idioma(s)** | Español (principal); el spider detecta también Inglés, Italiano, etc. del HTML de la edición |
| **Cobertura** | Indexa exhaustivamente cómics y manga publicados en España y LatAm; expone novedades + variantes/portadas alternativas sin login |
| **Aporte al corpus** | ~26 items |
| **Parser / módulo** | Fila YAML `ES/LatAm - Whakoom Novedades` + spider `scripts/wikis/whakoom.py` |

**Editoriales / países que abarca** (del corpus real, ver snippet en §10):

- **Editoriales** (con volumen aprox. en el corpus): Seven Seas Entertainment (≈9) ·
  Editorial Ivrea (≈6) · Varias editoriales (≈5, items del spider sin publisher resuelto) ·
  Viz Media (≈2) · Panini Manga México (≈1).
- **Países**: Estados Unidos (≈11) · Argentina (≈6) · España / LatAm (≈5, el default de la
  fuente) · México (≈1).

Recuerda: `publisher` = editorial real (Ivrea, Seven Seas…), nunca "Whakoom" (#44).

**Por qué importa / qué aporta de único**: Whakoom es el mejor catálogo del **mercado
español y latinoamericano de manga** (Argentina, México, España), un mercado que pocas
fuentes del catálogo cubren. Su diferencial frente a otras fuentes es que expone
**variantes y portadas alternativas** (ej. "Spy x Family #1 Portada Alternativa, Ivrea
Argentina") que no aparecen en un listado plano de novedades: cada tomo lista sus
ediciones específicas, y desde una edición se descubren sus hermanas (deluxe, cofre,
portada alternativa). El acceso es sin login.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**:
  - `/newtitles` → ~415 últimas novedades editoriales públicas (el radar). Cada novedad es
    un `<a href="/comics/{shortcode}/...">` al volumen.
  - `/comics/{shortcode}/{slug}/{vol}` → página de un tomo individual; lista las
    `/ediciones/N` específicas de ese volumen.
  - `/ediciones/{id}/{slug}` → metadata completa de UNA edición (OG tags) + lista de tomos
    + lista de ediciones hermanas (variantes). **Una `/ediciones/` es una colección, no un
    tomo** (#14): se expande a N tomos `/comics/...`, nunca se guarda como un solo item.
  - `/publisher/{id}/{slug}` → índice puro de ediciones de un editor (no productos;
    `is_whakoom_publisher_url`).
  - `/autores/{id}/{slug}` → discovery por autor (accesible sin login; mencionado en las
    notas del YAML, no recorrido por el spider canónico).
- **Estructura del HTML / selectores clave**:
  - `/newtitles`: `a[href^='/comics/']` (selector de la fila YAML, e
    `extract_comics_urls_from_newtitles` en el spider).
  - Página de edición: OG tags (`og:title`, `og:description`, `og:image`, `og:url`); el
    publisher sale del paréntesis final del `og:title` (`"… (Ivrea Argentina)"`) o de
    `.publisher`; idioma/país de `ul.info-summary > li .value.flag` + `.title`
    (`_detect_language_from_edition_html`); autores de `h3.autores + p`; tipo de edición de
    `p.edition-type`.
  - Tomos dentro de una edición: `li[id^='comic'] a[href^='/comics/']`
    (`parse_volume_links`). Whakoom muestra sólo ~11 tomos en la página principal; el resto
    está en `<edition_url>/todos` (`edition_todos_url`).
  - One-shots: la URL `/comics/` canónica viene enmascarada en `/login?ReturnUrl=…`
    (`_extract_oneshot_comic_url`).
- **Identificador de producto**: la URL canónica del tomo (`/comics/{shortcode}/…/{vol}`).
  La `/ediciones/N` se usa sólo como agrupador/origen, nunca como identidad del item (#14).
- **Anti-bot / quirks**:
  - **Cloudflare agresivo** (#15): es la razón por la que el spider profundo es **opt-in**.
    El spider usa headers "browser-like" completos (no sólo User-Agent) para reducir
    challenges/429, detecta la página de challenge (`WhakoomBlocked`) y **aborta el batch
    entero** si la IP entra en cuarentena. Markers reales: `cf-chl-bypass`,
    `__cf_chl_rt_tk`, `/cdn-cgi/challenge-platform/h/` (NO el script JSD legítimo).
  - **Brotli** (#15): el header **NO** debe pedir `br` — `requests` no lo decodifica nativo
    y `response.text` quedaría binario (parser ve 0 tomos en silencio). Se usa
    `Accept-Encoding: gzip, deflate`. Si re-agregás `br`, agregá `brotli` a requirements.
  - **429 / rate-limit**: backoff exponencial (10s → 20s → 40s) en `fetch_url`. Si ves
    muchos `[WHAKOOM] 429`, subí `--sleep-seconds` a 3.0.
  - **Throttle local**: lockfile en `~/.cache/manga-watch/whakoom_lastrun` impide correr el
    bootstrap completo más de 1× cada 6h (protege la IP). `--ignore-throttle` lo salta.
- **Calidad de imágenes**: las portadas salen del `og:image` de la edición y del cover del
  tomo individual (`img` dentro del `<a>`); puede venir thumbnail (`small/`).

---

## 3. Proceso de ingestión — vista de producto

> Whakoom tiene dos caminos: la fila /newtitles (ligera, default) y el spider profundo
> (opt-in). Lo que sigue describe el spider, que es donde está la lógica de captura.

1. **Tomar el radar** (`/newtitles`): la lista de ~415 novedades recientes → URLs de
   volúmenes (`/comics/{X}`).
2. **Por cada volumen**, abrir su página y listar las **ediciones** (`/ediciones/N`) que lo
   publican (regular, deluxe, cofre, portada alternativa…).
3. **Por cada edición**, expandirla: una edición es una **colección de tomos** (#14), así
   que se produce **un item por tomo** (`/comics/.../{vol}`), heredando de la edición su
   publisher, autor, idioma, país, tipo de edición y descripción. Las ediciones hermanas
   descubiertas en esa página se agregan a la cola (BFS) para capturar variantes que el
   listado plano no expone.
4. **Decidir qué entra**: de cada tomo expandido sólo se conserva el que parece manga
   (`is_likely_manga` con `source_purity="mixed"`) y supera el umbral de score.
5. **Repetir** hasta agotar la cola o tocar el cap de ediciones (`max_editions=1500`).

**Reglas de producto que nunca se rompen:**
- Una `/ediciones/N` NUNCA se guarda como item; siempre se expande a tomos `/comics/…`
  (#14).
- El país de la edición es el de la edición (editorial/idioma), no el de la tienda (#46);
  el spider lo infiere por publisher/flag (Argentina, México, España, etc.).
- `publisher` = editorial real, nunca "Whakoom" (#44).
- En una fuente `mixed` sólo pasa lo que tiene hint fuerte de manga; la comics blacklist
  (Marvel/DC/Astérix/etc.) aplica siempre (#11, decisión de diseño #3).

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

Whakoom tiene **dos caminos** que se comportan distinto en el pipeline:

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| **Fila /newtitles** (default, kind:html) | corre en la **fase 1** (scrape de fuentes del YAML) | idéntica — corre en la **fase 1** |
| **Spider profundo** (opt-in) | paso **2q**, sólo si `INCLUDE_WHAKOOM_SPIDER=1` | paso **2p**, sólo si `INCLUDE_WHAKOOM_SPIDER=1` |
| Invocación spider | `--bootstrap-wiki whakoom --sleep-seconds 2.0 --min-score 20` | idéntica |
| Discovery | `/newtitles` → BFS de 3 niveles (comics → ediciones → tomos + hermanas) | idéntico (Whakoom no indexa por mes) |
| Default | **OFF** (riesgo Cloudflare) | **OFF** |

- **Camino default (sin spider)**: la fila `ES/LatAm - Whakoom Novedades` lee sólo
  `/newtitles` (`max_pages: 1`, ~415 novedades) usando el selector `a[href^='/comics/']`.
  Es ligera, sin riesgo de ban, y corre en cada scrape (full y delta) sin intervención.
  Captura el delta diario al **nivel 1** (novedad → volumen), sin variantes.
- **Camino opt-in (spider)**: `--bootstrap-wiki whakoom` corre el BFS completo de 3
  niveles, que descubre **todas las variantes y portadas alternativas** relacionadas a las
  novedades. Pesado (~1500 ediciones, ~60-70 min con `sleep=2.0`) y con riesgo de Cloudflare
  ban — por eso está detrás de `INCLUDE_WHAKOOM_SPIDER=1` (default OFF en ambos scripts).
- El módulo ignora `year_from`/`month_to` (Whakoom no es por mes); los mantiene por
  compatibilidad con la interfaz de wikis.
- **Nota del propio módulo**: para discovery regular se recomienda
  `scripts/retrofit/search_discovery.py` (Gemini + Grounding) en lugar del spider — cubre
  histórico, sin riesgo de ban y más rápido. El spider queda para bootstrap inicial de
  volumen o recovery forense puntual.

---

## 5. Proceso de ingestión — técnico

Parser/spider: [`scripts/wikis/whakoom.py`](../../../scripts/wikis/whakoom.py).
La fila /newtitles es una entrada estándar de `sources.yml` (`kind: html`) que recorre el
loop genérico de fuentes; el spider se activa con `--bootstrap-wiki whakoom`, que bypassea
ese loop (#8).

### 5.1 Modelo de datos / claves
- País de la edición (#46): el spider lo infiere por publisher conocido (`"argentina"` →
  Argentina, `"méxico"`/`"mexico"` → México, `"ivrea españa"`/`"planeta"`/`"norma"`/
  `"panini españa"` → España) y por el flag/`.title` de `ul.info-summary`
  (`_detect_language_from_edition_html`, que también mapea Estados Unidos, Italia, etc.).
  El default de la `_virtual_source()` es país="España / LatAm", idioma="Español".
- Identidad del producto = URL del tomo `/comics/…`. La `/ediciones/N` es un agrupador
  (#14): se expande, nunca se persiste como item.
- `source_class="trusted_media"`, `kind="html"`, `purity="mixed"` (tanto en la fila YAML
  como en la `_virtual_source()` del spider).

### 5.2 Qué captura el parser (mapea el §3 al código)
- `extract_comics_urls_from_newtitles()` — nivel 1: `/newtitles` → URLs `/comics/{X}`.
- `extract_ediciones_urls_from_html()` — nivel 2: `/comics/{X}` → pares `(id, /ediciones/N)`,
  deduplicados por id.
- `expand_whakoom_edition()` — nivel 3: expande una `/ediciones/N` en N `Candidate`s (uno
  por tomo). Lee la página principal (`parse_edition_metadata` + `parse_volume_links`) y,
  si hay >~11 tomos, `<url>/todos`. Merge por URL (`_merge_volume_dicts`). Fallback
  one-shot vía `_extract_oneshot_comic_url` cuando la edición no lista tomos.
- `expand_whakoom_publisher_url()` — expande una `/publisher/` a sus ediciones (no en el
  flujo BFS canónico).
- **Gate de entrada**: por cada tomo, `is_likely_manga(..., source_purity="mixed",
  publisher=…)` (#11/#3) y luego `score_candidate`; al final se conservan los de
  `score ≥ --min-score` (20 en el pipeline).
- `signal_types`/`product_type` se derivan aguas abajo del `title + description` (#10), no
  los setea el spider.

### 5.3 Flujo end-to-end
- **Fila /newtitles**: fase 1 de `scrape_full.sh` y `scrape_delta.sh` (scrape de fuentes del
  YAML), sin flags especiales.
- **Spider**: paso **2q** en `scrape_full.sh` y paso **2p** en `scrape_delta.sh`, sólo si
  `INCLUDE_WHAKOOM_SPIDER=1`. Comando:
  ```
  manga_watch.py --bootstrap-wiki whakoom --sleep-seconds 2.0 --min-score 20
  ```
- Escribe a `data/items.jsonl` incrementalmente vía `flush_fn` (por edición). Luego pasa por
  las fases comunes (cleanup retrofits → build → validate). No tiene retrofits dedicados.
- Tras el scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr
  `/watch-standardize-catalog` automáticamente.

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural del pipeline (aplica a TODO el corpus,
  sin red). Es la verificación principal para esta fuente.
- No hay auditoría de red dedicada ni enforcer/idempotencia propios (a diferencia de
  ListadoManga).
- Sanity manual: verificar que NO existan items cuya URL sea una `/ediciones/N` (deberían
  ser todas `/comics/…`; #14).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#14 (`/ediciones/` = colección, no tomo)**: una `/ediciones/N` lista varios tomos; si se
  guardara como un solo item, una serie entera quedaría como un registro. ✅ Se expande a un
  `Candidate` por tomo (`expand_whakoom_edition`); la `/ediciones/` sólo sirve de agrupador
  y para descubrir hermanas.
- **#15 (Brotli + Cloudflare challenge)**: pedir `br` en `Accept-Encoding` deja
  `response.text` binario → 0 tomos en silencio; y Cloudflare puede challengear la IP entera.
  ✅ Header sin `br`; detección de challenge (`WhakoomBlocked`) aborta el batch; throttle
  local de 6h. El spider llegó a **quemar la IP** una vez — por eso es opt-in.
- **#11 / #3 (purity mixed + comics blacklist)**: Whakoom mezcla manga + cómic occidental +
  BD. ✅ Sólo entra lo que pasa `is_likely_manga` con hint fuerte de manga; Marvel/DC/
  Astérix/etc. los filtra la comics blacklist (que aplica siempre).
- **#6 (placeholders de imagen)**: covers pueden venir como thumbnail/placeholder; el
  backfill aguas abajo re-fetchea cuando aplica.
- **Decisiones (lo que NO se hace)**: no se guarda ninguna `/ediciones/` ni `/publisher/`
  como producto (son índices/colecciones); no se mergea cross-país (#46); para discovery
  regular se prefiere `search_discovery.py` (Gemini) sobre el spider.

---

## 9. Pendientes / limitaciones conocidas

- **Spider opt-in por riesgo de ban**: el camino que captura variantes/portadas alternativas
  NO corre por default. Sin `INCLUDE_WHAKOOM_SPIDER=1`, sólo se captura el nivel 1 de
  /newtitles (novedad → volumen), sin variantes.
- **Cobertura sesgada a lo reciente**: tanto /newtitles como el spider parten del radar de
  novedades; los items históricos no se cubren por esta vía (de ahí la recomendación de usar
  `search_discovery.py`).
- **País/idioma heurísticos**: el país se infiere por publisher/flag; ediciones con publisher
  no mapeado caen al default "España / LatAm" (de ahí los ≈5 items con publisher "Varias
  editoriales" / país genérico en el corpus).
- **`/autores/{id}/{slug}`**: mencionado como vía de discovery por autor en las notas del
  YAML, pero el spider canónico NO lo recorre. {{pendiente: confirmar si existe un camino de
  discovery por autor implementado o si es sólo una nota.}}
- {{pendiente: confirmar el número de gotcha exacto del placeholder de imagen citado como #6
  arriba (verificado contra el heading de gotchas.md, pero conviene revalidarlo si se
  renumeran).}}

---

## 10. Runbook / comandos útiles

```bash
# Camino default (ligero, /newtitles): corre solo en fase 1 del scrape, vía la fila YAML.
# No requiere comando dedicado; es parte de scrape_full.sh / scrape_delta.sh.

# Spider profundo (OPT-IN, riesgo Cloudflare — deja items raw):
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki whakoom --sleep-seconds 2.0 --min-score 20

# En el pipeline, activar el spider (default OFF):
INCLUDE_WHAKOOM_SPIDER=1 scripts/scrape_delta.sh   # paso 2p
INCLUDE_WHAKOOM_SPIDER=1 scripts/scrape_full.sh    # paso 2q

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "whakoom"
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

**Antes de cerrar cualquier cambio en Whakoom**: validar (`validate_corpus`, 0 duras) →
tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza
esta ficha.
