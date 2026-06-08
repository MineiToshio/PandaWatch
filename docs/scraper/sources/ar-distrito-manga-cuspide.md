# Fuente: AR - Distrito Manga (Cúspide)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

> ⚠️ NO confundir con **"ES - Distrito Manga"** (España, `penguinlibros.com`), que se
> documenta aparte. Esta es la fuente **argentina** servida vía la librería Cúspide.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | AR - Distrito Manga (Cúspide) |
| **URL base** | `https://cuspide.com/editorial/distrito-manga/` |
| **Índice / punto de entrada** | `https://cuspide.com/editorial/distrito-manga/` (paginado, `max_pages: 5`) |
| **Tipo de fuente** | Tienda (retailer) — librería argentina |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `retailer` |
| **País** | Argentina (`Argentina`) |
| **Idioma** | Español |
| **Cobertura** | Catálogo del sello **Distrito Manga** (Penguin Random House) en Argentina, vendido por Cúspide |
| **Aporte al corpus** | 6 items (todos `Distrito Manga Argentina`) |
| **Parser / módulo** | Entrada en `sources.yml` (extractor genérico, sin módulo propio) |

**Por qué importa**: Distrito Manga es el sello de manga de **Penguin Random House**;
Cúspide (librería argentina) tiene el catálogo completo y es la vía de discovery del
mercado **argentino** de ese sello. Aporta cobertura de un país poco representado.

> **Tienda ≠ editorial (#44):** Cúspide es la **tienda**; el `publisher` real es el sello
> **Distrito Manga Argentina**. A diferencia de los retailers multi-editorial de #44 (donde
> el `publisher` NO debe setearse), aquí la fuente apunta a un sello único, así que
> `publisher="Distrito Manga Argentina"` es correcto y específico de la edición.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: índice del sello en Cúspide, paginado (hasta 5 páginas
  por `max_pages`). Cada producto enlaza a una página `/producto/…`.
- **Estructura del HTML**: listado tipo grilla.
  - `item_selector`: `.product`
  - `title_selector`: `a[href*='/producto/']`
- **Identificador de producto**: URL canónica `/producto/…` de Cúspide.
- **Anti-bot / quirks**: {{pendiente: no observado anti-bot/JS-render en esta fuente}}.
- **Calidad de imágenes**: {{pendiente: no verificada}}.

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: `"AR - Distrito Manga (Cúspide)"` (`kind: html`,
  `source_class: retailer`). Se procesa en **FASE 1** del pipeline (scrape de sources del
  YAML, `manga_watch.py --workers 8`) con el **extractor genérico** — NO tiene parser ni
  módulo propio.
- **Selectores**: `item_selector: .product`, `title_selector: a[href*='/producto/']`,
  `max_pages: 5`.
- **Publisher**: `Distrito Manga Argentina` (sello de Penguin Random House). Cúspide es la
  tienda, no la editorial (#44).
- **Notes verbatim (YAML)**: "Distrito Manga es sello de Penguin Random House; Cúspide tiene
  catálogo completo."

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#44 (tienda ≠ editorial)** — Cúspide es la tienda y Distrito Manga el sello. Acá el
  `publisher` apunta al sello correcto (fuente de un único sello), así que no cae en el caso
  problemático de #44 (retailers multi-editorial que contaminan el `publisher`).
- **Decisión**: NO confundir con la fuente homónima de España (`ES - Distrito Manga`,
  `penguinlibros.com`). País distinto = edición distinta (#46); el país (`Argentina`) va en
  el `edition_key`.

---

## 9. Pendientes / limitaciones conocidas

- Aporte chico (6 items). {{pendiente: confirmar si `max_pages: 5` cubre todo el catálogo o
  si se trunca.}}
- {{pendiente: calidad de imágenes y eventuales quirks de layout/anti-bot sin verificar.}}

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "AR - Distrito Manga (Cúspide)"

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver items reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "cuspide"
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
