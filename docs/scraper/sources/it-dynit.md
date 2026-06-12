# Fuente: Dynit

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Dynit |
| **URL base** | `https://www.dynit.it/` |
| **Índice / punto de entrada** | `https://www.dynit.it/` |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | Italia |
| **Idioma(s)** | Italiano |
| **Cobertura** | Manga de Dynit Manga (catálogo italiano) |
| **Aporte al corpus** | 1 item |
| **Parser / módulo** | Entrada `"IT - Dynit"` en `sources.yml` (extractor genérico, sin parser propio) |

Editorial real en el corpus: **Dynit Manga** (1 item, país Italia). `publisher` = editorial
real, NO la tienda (#44).

**Por qué importa / qué aporta de único**: editorial oficial italiana; cubre el mercado IT
junto con las otras fuentes de Italia. Aporte actual muy bajo (1 item).

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda **WooCommerce** servida desde la home
  `https://www.dynit.it/`.
- **Estructura del HTML**: el extractor genérico recorre los productos del listado con los
  selectores declarados en `sources.yml`:
  - `item_selector`: `div.sc_extended_products_content`
  - `title_selector`: `.woocommerce-loop-product__title, h2, h3, a`
- **Identificador de producto**: URL del producto (sin parser propio que derive SKU/ISBN).
- **Anti-bot / quirks**: {{pendiente: no verificado para esta fuente}}.
- **Calidad de imágenes**: {{pendiente: no verificado para esta fuente}}.

---

## 5. Proceso de ingestión — técnico

- Fuente **simple del YAML**: entrada `"IT - Dynit"` en `sources.yml`, capturada en
  **FASE 1** del pipeline (`manga_watch.py` con `--workers 8`) vía el **extractor genérico**
  con los selectores de arriba. **No tiene parser propio** ni helper específico.
- Como cualquier fuente del YAML, los filtros y retrofits de cleanup (FASE 3) aplican igual.

---

## 9. Pendientes / limitaciones conocidas

- **Fechas DD/MM/YYYY crudas en `release_date`** — la ficha técnica del sitio entrega la fecha día-primero y los extractores la guardaban sin normalizar; desde 2026-06-12 `normalize_release_date()` la convierte a ISO en la ingestión y el corpus legacy se reparó con `normalize_release_dates.py` (gotcha #80). ✅
- **Aporte mínimo** (1 item). {{pendiente: confirmar si los selectores capturan todo el
  catálogo o sólo una fracción de la home — posible cobertura incompleta}}.
- **Anti-bot y calidad de imágenes** sin verificar para esta fuente.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "IT - Dynit"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "dynit.it"
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
