# Fuente: MangaLine México

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.
>
> Nota: MangaLine México (`mangaline.com.mx`) y MangaLine España (`mangaline.es`)
> comparten el MISMO theme WooCommerce custom, pero son **sitios y países distintos**.
> Esta ficha es la de **México**. La de España se documenta aparte en
> [es-mangaline-espana.md](es-mangaline-espana.md).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | MangaLine México |
| **URL base** | `https://mangaline.com.mx` |
| **Índice / punto de entrada** | `https://mangaline.com.mx/tienda/` |
| **Tipo de fuente** | Editorial / tienda oficial |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | México (`México`) |
| **Idioma** | Español |
| **Cobertura** | Catálogo propio de MangaLine México, concentrado en sobrecubiertas alternativas y ediciones exclusivas |
| **Aporte al corpus** | ~19 items |
| **Parser / módulo** | Entrada en `sources.yml` ("MX - MangaLine México Tienda") — extractor genérico, sin parser propio |

**Editoriales que abarca** (del corpus real): MangaLine México (19 items).

**Por qué importa / qué aporta de único**: aporta el catálogo de **sobrecubiertas
alternativas y ediciones exclusivas** de MangaLine en México (Devilman #1-3,
Q on the Seaside, Tokko, Silent Möbius, Nadesico, Grey, Dark Angel). Es la edición
mexicana — país distinto de la edición española (#46), nunca se mezclan.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda WooCommerce en `tienda/`, paginada
  (`max_pages: 10`). Cada producto es una card del listado.
- **Estructura del HTML**: WooCommerce con **tema custom**. Selectores del YAML:
  - `item_selector`: `li.product:not(.product-category)`
  - `title_selector`: `h3.product-title` (NO el `h2.woocommerce-loop-product__title`
    estándar de WooCommerce — el tema custom usa `h3.product-title`).
- **Quirk del selector**: `li.product` también matchea cards de **"líneas temáticas"**
  (DARK LINE, EPIC LINE…) que son category-cards, no productos. Se filtran con
  `:not(.product-category)`.
- **Pureza**: `manga_only`.

---

## 5. Proceso de ingestión — técnico

Fuente del **YAML**, ingestada en **FASE 1** del pipeline (`manga_watch.py`,
scrape de sources del YAML) vía el **extractor genérico** con los selectores de
arriba. **No tiene parser propio**. Comparte el mismo theme WooCommerce custom que
MangaLine España, por lo que ambos usan los mismos selectores (`h3.product-title`,
`li.product:not(.product-category)`).

---

## 9. Pendientes / limitaciones conocidas

- Catálogo chico (~19 items); no hay ediciones especiales/cofres con lógica propia
  como en ListadoManga, así que entra todo por el extractor genérico.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "MX - MangaLine México Tienda"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "mangaline.com.mx"
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
