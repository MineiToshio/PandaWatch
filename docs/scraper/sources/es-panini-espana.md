# Fuente: Panini Manga España

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

Fuente **SIMPLE** (entradas en `sources.yml`, sin parser propio). Cubre **dos
entradas** del mismo sitio (`panini.es`): el catálogo de novedades y el buscador
expandido por keywords.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Panini Manga España |
| **URL base** | `https://www.panini.es/shp_esp_es/` |
| **Índice / punto de entrada** | `novedades-panini-comics-marvel-manga` (catálogo) · `catalogsearch/result/?q={query}` (buscador) |
| **Tipo de fuente** | Editorial oficial (tienda Magento de Panini España) |
| **`kind` en sources.yml** | `html` (ambas entradas) |
| **`source_class`** | `official` |
| **País** | España (`es`) — fuente mono-país |
| **Idioma** | Español (ES) |
| **Cobertura** | Manga publicado por Panini en España: novedades + ediciones especiales/limitadas/deluxe que aparecen en el buscador |
| **Aporte al corpus** | ~14 items (al último conteo) |
| **Parser / módulo** | Sin parser propio: 2 entradas en `sources.yml` vía extractor genérico Magento |

**Editoriales que abarca** (del corpus real): Panini Manga España (14/14 items).

**Por qué importa / qué aporta de único**: es la voz **oficial** de Panini para el
mercado español — capta novedades y ediciones premium (Master/Ultimate Edition,
deluxe, cofres, tapa dura, variantes) directo de la editorial, sin pasar por
intermediarios.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda **Magento**. El catálogo de novedades
  pagina (`max_pages: 15`). El buscador usa `catalogsearch/result/?q={query}`,
  que en el pipeline se expande en fuentes virtuales (una por keyword).
- **Estructura del HTML**: layout Magento estándar. Selectores de la entrada
  (search): `item_selector: "li.product-item"`, `title_selector:
  "a.product-item-link"`. El catálogo de novedades usa el extractor genérico
  (sin selectores explícitos en el YAML).
- **Identificador de producto**: URL canónica del producto Magento.
- **Anti-bot / quirks**: catálogo **mixto** — el buscador devuelve también cromos
  (LIGA ESTE, Eurocopa), corbatas y otros no-manga; por eso la entrada (search)
  declara `purity: "mixed"` (ver §8).
- **Calidad de imágenes**: {{pendiente: no verificada en esta revisión}}.

---

## 5. Proceso de ingestión — técnico

Sin parser dedicado. Las dos entradas se ingieren en **FASE 1** (`manga_watch.py`,
scrape de las fuentes del YAML) vía el **extractor genérico** de Magento.

- **`ES - Panini Manga España`** (`sources.yml:479`): entrada `html` con
  `url` al catálogo de novedades y `max_pages: 15`. Tags `["manga", "official"]`.
  El extractor genérico recorre la paginación y toma cada producto del listado.

- **`ES - Panini España (search)`** (`sources.yml:1493`): entrada `html` con
  `search_template`. En el pipeline, `_expand_search_template()` la **expande en
  fuentes virtuales por keyword** (una query por cada keyword del bloque
  `keywords`) — tag de procesamiento "expansion". Cada query se ejecuta contra
  `catalogsearch/result/?q={query}` y se parsea con los `selectors` declarados
  (`li.product-item` / `a.product-item-link`). `purity: "mixed"` se **propaga a
  todas las fuentes hijas** generadas por la expansión (#7). Tags
  `["manga", "official", "store"]`.

  Keywords (verbatim del YAML): `edicion limitada`, `edicion especial`,
  `edicion coleccionista`, `deluxe`, `cofre`, `kanzenban`, `tapa dura`,
  `variante`, `portada variante`, `master edition` (rescata Berserk Master
  Edition; "Beherit" cae aquí), `ultimate edition`, `tarot`, `celebration`,
  `anniversary`, `tribute`, `aniversario`.

  Nota del YAML: keywords validadas a mano; se eliminaron `gran formato`,
  `perfect edition` y `beherit` (esta última sólo aparece en la descripción, no
  en el título, así que el buscador no la indexa).

**Flujo end-to-end**: ambas entran en **FASE 1** del pipeline canónico
(`scrape_full.sh` / `scrape_delta.sh`). No tienen discovery especial: se scrapean
igual en full y en delta. Luego pasan por los cleanup retrofits genéricos de la
FASE 3 (rescore → `filter_non_manga` → `filter_collectible` → clean_titles →
backfill_metadata).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **`purity: mixed` (decisión #3)**: el buscador de Panini ES devuelve cromos
  (LIGA ESTE, Eurocopa), corbatas y merch no-manga. En `mixed`, sólo pasa lo que
  trae un **STRONG manga hint** (la comics blacklist aplica siempre). Por eso la
  entrada (search) está marcada `mixed` y NO `manga_only`.
- **#7: `source_purity` se propaga a las fuentes hijas** de la expansión del
  `search_template`. El `mixed` de la entrada padre cubre automáticamente cada
  query-por-keyword; no hay que marcarlo por hijo.
- **Tienda ≠ editorial (#44)**: NO aplica como contaminación acá — Panini España
  **es** la editorial real, así que `publisher: "Panini Manga España"` es
  correcto (la entrada es `source_class: official`, no un retailer multi-editorial).

---

## 9. Pendientes / limitaciones conocidas

- **Aporte chico** (~14 items): la cobertura depende de que las ediciones traigan
  alguna de las keywords en el **título** indexado por el buscador (las que sólo
  aparecen en descripción no se capturan — caso "beherit"). Ampliar keywords
  podría subir recall, pero sube también el ruido (catálogo mixto).
- **Calidad de imágenes**: {{pendiente: no verificada}}.
- **Diferencia full vs delta**: hoy ninguna — ambas entradas se scrapean igual en
  los dos modos.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo estas fuentes (ajustar al nombre exacto del YAML):
.venv/bin/python scripts/manga_watch.py --only-source "ES - Panini Manga España"
.venv/bin/python scripts/manga_watch.py --only-source "ES - Panini España (search)"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "panini.es"
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

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`,
0 duras) → tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo
meaningful, actualiza esta ficha.
