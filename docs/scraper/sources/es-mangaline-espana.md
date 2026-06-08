# Fuente: MangaLine España

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

> Es una fuente **simple** del YAML (entrada en `sources.yml`, extractor genérico).
> Sólo lleva §1, §2, §5 (básico), §8/§9 si aplica y §10.

> **Nota — sitio distinto de MangaLine México.** `mangaline.es` (esta ficha,
> España) y `mangaline.com.mx` (México) comparten el MISMO theme WooCommerce
> custom, pero son **sitios, países y editoriales distintos**. No los mezcles:
> son dos entradas separadas en `sources.yml`. La de México se documenta aparte.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | MangaLine España |
| **URL base** | `https://mangaline.es` |
| **Índice / punto de entrada** | `https://mangaline.es/shop/` |
| **Tipo de fuente** | Editorial / tienda oficial (`source_class: official`) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | España (`es`) — fuente mono-país |
| **Idioma** | Español |
| **Cobertura** | Catálogo propio de MangaLine España: preventas y ediciones integrales con extras |
| **Aporte al corpus** | ~4 items (al último conteo) |
| **Parser / módulo** | Entrada en `sources.yml` (extractor genérico, sin parser propio) |

**Editoriales que abarca** (del corpus real, ver snippet §10): MangaLine España
y MangaLine Ediciones — es su propio catálogo de editorial. El `publisher` en el
YAML es `MangaLine España` (#44: publisher = editorial real, no la tienda).

**Por qué importa / qué aporta de único**: tienda oficial de la editorial
MangaLine en España. Aporta **preventas** y **ediciones integrales con extras**
de su catálogo propio — series como Grey, Silent Möbius, Dark Angel y UFO Robot
Grendizer (preventa Goldorak) — que no necesariamente aparecen en otras fuentes.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda WooCommerce. Índice en `/shop/` con
  paginación (`max_pages: 10`); cada producto vive en `/product/<slug>/`.
- **Estructura del HTML**: tema WooCommerce **custom** (mismo theme que MangaLine
  México). Los productos del listado son `li.product`; el título está en
  `h3.product-title` — **NO** el `h2` estándar de WooCommerce. Las tarjetas de
  categoría del listado son `li.product.product-category` y se excluyen.
- **Identificador de producto**: URL canónica del producto (`/product/<slug>/`).
- **Pureza**: `manga_only` — es el catálogo propio de la editorial, sin mezcla de
  comics/coleccionables. (La entrada del YAML no declara `purity` explícito; se
  trata como mono-editorial de manga.)

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: `ES - MangaLine España` (`kind: html`,
  `url: https://mangaline.es/shop/`). Se scrapea en **FASE 1** del pipeline junto
  con el resto de fuentes del YAML (`manga_watch.py --workers 8`), vía el
  **extractor genérico** (no hay parser propio).
- **Selectores**:
  - `item_selector: li.product:not(.product-category)` — toma cada producto del
    listado y **excluye las tarjetas de categoría** (`li.product-category`), que
    de otro modo entrarían como falsos productos.
  - `title_selector: h3.product-title` — el título va en `h3`, no en el `h2`
    estándar de WooCommerce (de ahí el selector explícito).
- **Paginación**: `max_pages: 10`.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Título en `h3.product-title`, no `h2`**: el theme custom de MangaLine no usa
  el markup estándar de WooCommerce → se fija `title_selector: h3.product-title`.
- **Tarjetas de categoría como falsos productos**: el listado mezcla `li.product`
  reales con `li.product.product-category` (cards de categoría) → el
  `:not(.product-category)` las descarta.

---

## 9. Pendientes / limitaciones conocidas

- **Aporte chico al corpus** (~4 items): catálogo pequeño y/o muchas preventas.
  Revisar tras un scrape grande si `max_pages` o los selectores dejan productos
  afuera.
- {{pendiente: confirmar calidad/resolución de las imágenes de portada de esta
  fuente — no verificado en esta ficha}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "ES - MangaLine España"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver items/editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "mangaline.es"
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

**Antes de cerrar cualquier cambio en esta fuente**: validar
(`validate_corpus.py`, 0 duras) → tests (`pytest tests/test_extraction.py`) →
build. Si tocaste algo meaningful, actualiza esta ficha.
