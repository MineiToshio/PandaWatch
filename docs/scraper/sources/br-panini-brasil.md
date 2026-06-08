# Fuente: Panini Brasil (Planet Manga)

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
