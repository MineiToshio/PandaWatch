# Fuente: Pipoca & Nanquim

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Pipoca & Nanquim |
| **URL base** | `https://pipocaenanquim.com.br/` |
| **Índice / punto de entrada** | Listado del storefront Magento (paginado, `max_pages: 5`) |
| **Tipo de fuente** | Editorial (official) — tienda propia |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | Brasil (`Brasil`) — fuente mono-país |
| **Idioma(s)** | Portugués (PT-BR) |
| **Cobertura** | Catálogo mixto: manga premium (Junji Ito, omnibus de Tezuka, City Hunter Omnibus) junto con BD europea (Thorgal) |
| **Aporte al corpus** | 1 item (snapshot 2026-06-08) |
| **Parser / módulo** | Entrada en `sources.yml` (extractor genérico, sin parser propio) |

**Por qué importa / qué aporta de único**: editorial brasileña que publica manga
premium en PT-BR (Junji Ito, omnibus de Tezuka, City Hunter Omnibus). Es una de las
pocas fuentes del mercado brasileño con ediciones de autor / premium.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: storefront **Magento** (Mageshop), listado paginado
  acotado a `max_pages: 5`. Producto en `*.html`.
- **Estructura del HTML**: selectores del YAML (verbatim) —
  - `item_selector`: `li.product-item, .item.product`
  - `title_selector`: `a.product-item-link, a[href$='.html']`
- **Identificador de producto**: URL canónica del producto (`*.html`).
- **Catálogo mixto**: mezcla manga con BD europea (Thorgal). La comics blacklist filtra
  Thorgal; `purity: mixed` exige STRONG hint para el resto (ver §5).

---

## 5. Proceso de ingestión — técnico

- **FASE 1** del pipeline: se scrapea con el resto de fuentes del YAML
  (`manga_watch.py --workers 8`) vía el **extractor genérico** de Magento. **No tiene
  parser propio.**
- **`purity: mixed`** (decisión #3): en una fuente mixed sólo pasa lo que trae **STRONG
  manga hint**; un producto sin esa señal no entra al catálogo.
- **Comics blacklist** (#11): filtra la BD europea (Thorgal) antes de la regla de purity.
  La blacklist aplica siempre.
- Entrada en `sources.yml` bajo `"BR - Pipoca & Nanquim"` (`enabled: true`).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Catálogo mixto manga / BD europea** — Thorgal y similares conviven con manga premium.
  La comics blacklist (#11) los filtra; `purity: mixed` (decisión #3) exige STRONG hint
  para el resto. ✅

---

## 9. Pendientes / limitaciones conocidas

- **Aporte real bajo**: 1 item en el corpus (snapshot 2026-06-08). {{pendiente: confirmar
  si es cobertura esperada o si el STRONG-hint gate está filtrando manga válido del
  catálogo PT-BR}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "BR - Pipoca & Nanquim"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "pipocaenanquim"
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
