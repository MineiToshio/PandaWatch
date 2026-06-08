# Fuente: Editorial Kamite

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Editorial Kamite (MX - Editorial Kamite) |
| **URL base** | `https://kamite.com.mx` |
| **Índice / punto de entrada** | `https://kamite.com.mx/productos/` |
| **Tipo de fuente** | Editorial (official) — tienda de la propia editorial |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | México (`México`) — fuente mono-país |
| **Idioma** | Español |
| **Cobertura** | Catálogo de manga de Editorial Kamite (México) en `/productos/` |
| **Aporte al corpus** | 1 item (al último corpus) |
| **Parser / módulo** | Entrada en `sources.yml` ("MX - Editorial Kamite"); extractor genérico HTML |

**Editoriales que abarca**: Editorial Kamite (México). `publisher` = editorial real, no la
tienda (#44).

**Por qué importa / qué aporta de único**: cubre el catálogo de manga de Editorial Kamite,
una editorial mexicana, directamente desde su tienda oficial.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: catálogo en `/productos/`, paginado (hasta
  `max_pages: 5`). Cada producto enlaza a una ficha bajo `/productos/`.
- **Plataforma**: Tiendanube. Parece Shopify pero NO lo es (#4, #5): el catálogo vive en
  `/productos/` y los productos se identifican con `[data-product-id]` (mismo patrón que
  Kemuri AR). Shopify usaría `/products/` + `li.grid__item`/`[data-product-card]`.
- **Selectores** (de `sources.yml`, verbatim):
  - `item_selector: "[data-product-id]"`
  - `title_selector: "a[href*='/productos/']"`
- **Identificador de producto**: URL canónica del producto bajo `/productos/`.
- **Anti-bot / quirks**: {{pendiente: no se detectaron quirks específicos documentados}}.
- **Calidad de imágenes**: {{pendiente: no determinado}}.

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: "MX - Editorial Kamite", `kind: html`, `enabled: true`,
  `purity` por defecto (`manga_only`), `tags: ["manga", "official", "store", "new-source"]`.
- **Captura**: fuente simple del YAML, ingesta en **FASE 1** del pipeline canónico
  (`manga_watch.py --workers 8`, dentro de `scrape_delta.sh` / `scrape_full.sh`). Se recorre
  igual en full y delta.
- **Extractor**: genérico de Tiendanube (#4, #5), mismo patrón que Kemuri AR. **No tiene
  parser propio**. Cada producto del listado = un item; el título sale de
  `a[href*='/productos/']` y el item de `[data-product-id]`.
- Tras la captura, los items pasan por los retrofits de cleanup de FASE 3 (rescore,
  filtros, clean_titles, backfill de metadata/imágenes) como el resto de fuentes del YAML.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#4 / #5: plataforma Tiendanube, no Shopify** — Kamite parece Shopify pero su catálogo
  está en `/productos/` con `[data-product-id]`. Usar los selectores Tiendanube, no los de
  Shopify (`/products/`). ✅ resuelto con los selectors del YAML.

---

## 9. Pendientes / limitaciones conocidas

- **Aporte bajo al corpus** (1 item al último corpus). {{pendiente: confirmar si es la
  cobertura real del catálogo de Kamite o si la paginación/selectores dejan productos
  afuera}}.
- Quirks de anti-bot y calidad de imágenes {{pendiente: no determinados}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo de esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "MX - Editorial Kamite"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "kamite"
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
