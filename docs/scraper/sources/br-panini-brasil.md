# Fuente: Panini Brasil (Planet Manga)

> ⚠️ **PODA 2026-06-12 (poda de fuentes muertas)** — `BR - Panini Brasil Planet Manga`: El catálogo se deshabilitó (39 candidatos/run → 0 netos); las búsquedas Panini BR (search) siguen activas (21 items).
> Registro completo: [descartadas/README.md](descartadas/README.md).

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Panini Brasil (Planet Manga) |
| **URL base** | `https://panini.com.br` |
| **Índice / punto de entrada** | `https://panini.com.br/planet-manga` (catálogo curado) + `https://panini.com.br/catalogsearch/result/?q={query}` (búsqueda) |
| **Tipo de fuente** | Editorial (official) — tienda Magento de Panini Brasil |
| **`kind` en sources.yml** | `html` (las dos entradas) |
| **`source_class`** | `official` |
| **País** | Brasil (`Brasil`) — fuente mono-país |
| **Idioma** | Portugués (PT-BR) |
| **Cobertura** | Manga publicado por Panini Brasil bajo el sello **Planet Manga** (One Piece, Demon Slayer, JJK, Naruto, Dragon Ball, etc.) y, vía búsqueda, ediciones especiales/limitadas/definitivas, box sets, kits y variantes |
| **Aporte al corpus** | ~20 items (todos `country=Brasil`, `publisher=Panini Brasil`) |
| **Parser / módulo** | Dos entradas en `sources.yml` (sin módulo propio): `BR - Panini Brasil Planet Manga` (HTML) + `BR - Panini Brasil (search)` (search_template) |

**Por qué importa / qué aporta de único**: cubre el catálogo de **ediciones especiales
físicas de manga del mercado brasileño** (Planet Manga), un país/idioma que pocas otras
fuentes alcanzan. La entrada de búsqueda apunta a los formatos coleccionables: edições
especiais/limitadas/definitivas, box sets, "Kit", deluxe, capa dura, variantes y
kanzenban.

---

## 2. Descripción técnica de la fuente

- **Plataforma**: tienda **Magento**. Dos puntos de entrada al mismo sitio:
  - `/planet-manga` — catálogo de manga **curado** por Panini (paginado, `max_pages: 10`).
  - `/catalogsearch/result/?q={query}` — buscador del sitio (se expande por keyword).
- **Estructura del HTML** (igual en ambas entradas): listado de productos Magento.
  - `item_selector: "li.product-item"`
  - `title_selector: "a.product-item-link"`
- **Identificador de producto**: URL canónica del producto (extractor genérico Magento).
- **Purity**: la entrada `/planet-manga` es un catálogo manga curado (purity por defecto).
  La entrada de búsqueda es **`purity: "mixed"`** porque el catálogo de Panini BR trae
  también álbumes de la Copa, figurinhas y cromos → ahí sólo entra lo que tiene STRONG
  manga hint (decisión #3).

---

## 5. Proceso de ingestión — técnico

Ambas entradas se procesan en **FASE 1** del pipeline (`manga_watch.py`, scrape de sources
del YAML) mediante el **extractor genérico** de listados Magento; **no hay parser propio**.

- **`BR - Panini Brasil Planet Manga`** (HTML, `/planet-manga`): se recorre el catálogo
  curado hasta `max_pages: 10`, tomando cada `li.product-item` y su `a.product-item-link`.
- **`BR - Panini Brasil (search)`** (search_template): `manga_watch.py` la **expande en
  fuentes virtuales por keyword** vía `_expand_search_template()` — una entrada por
  `q={keyword}`, etiquetada con el tag `expansion` (y `search:<keyword>`). Keywords
  configuradas (verbatim): `edicao especial`, `edicao limitada`, `edicao definitiva`,
  `edicao colecionador`, `boxset`, `box`, `kit` (Panini BR usa "Kit \<serie\>" para packs:
  Berserk, Vinland Saga, JJK), `deluxe`, `capa dura`, `encadernado`, `variante`,
  `capa variante`, `kanzenban`, `tarot`, `anniversary`, `tribute`.
- **Purity `mixed` → STRONG manga hint** (decisión #3): en la entrada de búsqueda, por
  traer álbumes/figurinhas/cromos, sólo se acepta el item si hay un STRONG manga hint en
  título o descripción; la comics blacklist aplica siempre. La `purity` se propaga a las
  fuentes virtuales hijas del search-template (#7).
- No participa de sitemap discovery: las fuentes con tag `expansion` se excluyen de esa
  etapa.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Curación LLM non-manga 2026-08-23**: 1 item expulsado — "Tom Strong: Edição
  Definitiva Vol. 2" (ABC/DC), colado por el search "edicao definitiva".

---

## 9. Pendientes / limitaciones conocidas

- **Cobertura acotada**: ~20 items en el corpus. El catálogo `/planet-manga` está limitado
  a `max_pages: 10`; series fuera de ese tope sólo entran si las captura alguna keyword de
  la búsqueda.
- **Ruido de la entrada `mixed`**: depende del STRONG manga hint para filtrar álbumes
  Copa/figurinhas/cromos. Si aparecen falsos positivos/negativos brasileños, ajustar el
  hint, no la fuente.
- {{pendiente: confirmar anti-bot / Cloudflare / Brotli / mojibake u otros quirks de
  Magento en panini.com.br — no verificado en esta revisión}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo el catálogo curado:
.venv/bin/python scripts/manga_watch.py --only-source "BR - Panini Brasil Planet Manga"

# Scrape sólo la búsqueda (se expande por keyword):
.venv/bin/python scripts/manga_watch.py --only-source "BR - Panini Brasil (search)"

# Validar (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver items reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "panini.com.br"
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

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0 duras)
→ tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza
esta ficha.

## 2026-09-05 — read timeout en la búsqueda `edicao colecionador` (+ falso flag de yield)

Delta diario (`logs/scrape-delta-2026-09-05-113236/`). La entrada de búsqueda aparece
**dos veces** en el reporte de salud, y las dos son el mismo hecho:

```
[ERROR] BR - Panini Brasil (search) [search: edicao colecionador]: request error
HTTPSConnectionPool(host='panini.com.br', port=443): Read timed out.
```

- en `🔴 Broken (HTTP errors)` — la causa real;
- en `🚨 YIELD REGRESSIONS` como `12 | mediana 42 | 29%` — que es **consecuencia** del
  timeout, no un hallazgo aparte. El expandido por keyword devolvió menos porque una de
  las peticiones murió a mitad.

Vale anotarlo porque el reporte de salud presenta las dos listas como si fueran problemas
independientes: cuando una fuente aparece en ambas, **la de yield suele ser eco de la de
HTTP** y no merece diagnóstico propio.

Fue uno de los tres timeouts del mismo run (con Pipoca & Nanquim y Planeta Cómic), lo que
sugiere ventana de saturación antes que un bloqueo de `panini.com.br`. **Nada aplicado.**

## 2026-09-13 — `filter_collectible` descarta TODAS las "Capa Variante" (gotcha #203)

Delta diario (`logs/scrape-delta-2026-09-13-110143/04d-filter-collectible.log`). El gate de
coleccionables rechaza como `regular_tomo` los **mismos 3 productos en cada corrida**, al
menos desde el 2026-08-30 (14 deltas seguidos con exactamente 3 descartes "Capa Variante"):

- `Blue Lock Vol. 15 - Capa Variante`
- `Wotakoi: O Amor é Difícil Para Otakus Vol. 10 - Capa Variante`
- `Wotakoi: O Amor é Difícil Para Otakus Vol. 11 - Capa Variante`

El corpus tiene **0** items con "capa variante" en el título.

**Verificado en vivo (2026-09-13)**: las 3 fichas de `panini.com.br` responden 200 y su
`<title>` oficial lleva "Capa Variante". Son productos reales, y una portada variante es
coleccionable por definición del proyecto.

**Causa — mecanismo, no la fuente:**

```
detect_signals("Blue Lock Vol. 15 - Capa Variante")   → (0, [], [])
detect_signals("Blue Lock Vol. 15 - Capa Variant")    → (30, ['variant'], ['variant_cover'])
detect_signals("Blue Lock Vol. 15 - Portada Variante") → (40, ['portada variante'], ['variant_cover'])
```

La sección portuguesa de las frases de señal (`manga_watch.py`, bloque "Portugués (PT-BR)")
sólo trae `edição limitada/especial/de colecionador/definitiva` y `capa dura`; no tiene el
equivalente de `portada variante` (ES) ni de `couverture variante` (FR). El `variant`
suelto de la sección inglesa usa límite de palabra y, a propósito, no matchea "variante".

**Consecuencia**: las keywords `variante` y `capa variante` de la búsqueda rinden **0 netos
por construcción**, porque todo lo que traen muere en el gate. Además es un bucle diario:
se re-fetchea y se re-expulsa en cada corrida (patrón #154).

**Para el owner (no aplicado):** agregar `capa variante` (y probablemente
`capa alternativa`) como `variant_cover` en la sección PT-BR, con test. Es una frase de dos
palabras y específica, así que el riesgo de falso positivo es bajo; además `is_likely_manga`
(purity `mixed` + comics blacklist) corre ANTES y sigue frenando Marvel/DC con portada
variante. Retorno: las 3 variantes de hoy y todas las futuras de Panini Brasil.


## Revisión de ingestión — 2026-09-24

Se agregaron capa variante y capa alternativa como señales variant_cover. Pruebas con Blue Lock 15/Wotakoi; el gate ya no las rechaza por ausencia de vocabulario PT-BR.

Evidencia y alcance: [auditoría integral](../audits/2026-09-24-ingestion.md).


La reingesta aislada encontró además 23 cómics occidentales que pasaban desde selectores sin gate non-manga. Corregido gate común pre-spool/sink; se publicaron solamente Wotakoi 10 y 11 Capa Variante. No se ingresaron los descartes occidentales.
