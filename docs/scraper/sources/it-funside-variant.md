# Fuente: Funside Variant

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Funside Variant |
| **URL base** | `https://funside.it` |
| **Índice / punto de entrada** | `https://funside.it/collections/a-caccia-di-variant` |
| **Tipo de fuente** | Tienda (retailer) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `retailer` |
| **País(es)** | Italia (`it`) — fuente mono-país |
| **Idioma(s)** | IT (italiano) |
| **Cobertura** | Catálogo ~49 productos de variant covers de manga ("a caccia di variant") |
| **Aporte al corpus** | ~52 items |
| **Parser / módulo** | entrada en `sources.yml` (extractor genérico de HTML) |

**Editoriales que abarca** (del corpus real): Funside (≈49) · JPOP (2) · Star Comics (1).
Nota: `publisher` = editorial real, NO la tienda (#44). La mayoría sale rotulada con la
propia tienda como editorial; las pocas excepciones (JPOP, Star Comics) las captura el
extractor cuando el dato está en el producto.

**Por qué importa / qué aporta de único**: tienda Shopify italiana enfocada en **variant
covers** de manga, un nicho de coleccionismo que otras fuentes IT no concentran.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: Shopify estándar. Índice en
  `/collections/a-caccia-di-variant` (paginado, `max_pages: 5`); cada producto en
  `/products/<handle>`. Los slugs terminan en `-variant`.
- **Estructura del HTML**: selectores Shopify — `item_selector: .product-card`,
  `title_selector: a[href*='/products/']` (#4). Títulos tipo:
  - "A Tutto Gas vol 2 Variant"
  - "Ai Tempi di Bocchan Perfect Edition vol 3 Variant"
  - "Vita da Slime - A Spasso per Tempest Vol 5 Variant"
- **Identificador de producto**: URL canónica `/products/<handle>`.
- **Anti-bot / quirks**: ninguno conocido; Shopify HTML plano, sin JS-render.

---

## 5. Proceso de ingestión — técnico

- **Entrada**: definida en `sources.yml` como `IT - Funside Variant`. Se scrapea en la
  **FASE 1** del pipeline (scrape de sources del YAML vía `manga_watch.py`) con el
  **extractor genérico de HTML**; NO tiene parser propio.
- **Layout Shopify**: los selectores `.product-card` + `a[href*='/products/']` siguen la
  receta **"Recipe: add a new HTML retailer"** (variante Shopify) de
  [docs/scraper/SOURCES.md](../SOURCES.md). Cada producto del listado = un item.
- **Flujo end-to-end**: entra en la FASE 1 de `scrape_delta.sh` / `scrape_full.sh` junto
  al resto de fuentes del YAML; luego pasa por los retrofits de cleanup comunes.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Antes**: su `/collections/` se tomaba como un **único item** (el índice). **Ahora** se
  scrapea directo el listado → ~49 productos individuales. Descubierto vía
  `search_discovery`.
- **#16 (Shopify variants multi-tomo) NO aplica**: Funside modela 1 producto = 1 tomo (no
  un `<select>` de tomos). El helper de `shopify_variants.py` está restringido a dominios
  conocidos (hoy `darkhorsedirect.com`).
- **El selector de título capturaba la tarjeta entera con el bloque de precio**
  (gotcha #94, 2026-06-13): `title` quedaba como "{título} - VARIANT Prezzo normale
  €X Prezzo di vendita €X … Aggiungi al carrello" o con prefijo "Aggiungi al carrello
  [Confrontare] …" + sufijo de tienda "GAMES ACADEMY FUNSIDE / POPSTORE" (~58 items).
  Fix: `clean_title` corta desde "Prezzo normale/di vendita/unitario", el prefijo del
  botón y el sufijo "FUNSIDE". **Pendiente**: afinar `title_selector` (hoy
  `a[href*='/products/']` arrastra toda la tarjeta en algunos productos).

---

## 9. Pendientes / limitaciones conocidas

- `publisher` queda mayormente como "Funside" (la tienda) en vez de la editorial real
  (#44). Los productos no siempre exponen la editorial original; quedan ≈49 items así.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "IT - Funside Variant"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "funside"
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
→ tests (`pytest tests/test_extraction.py`) → build.
