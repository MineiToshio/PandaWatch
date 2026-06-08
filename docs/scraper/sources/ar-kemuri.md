# Fuente: Kemuri Ediciones

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Kemuri Ediciones |
| **URL base** | `https://www.kemuriediciones.com.ar/` |
| **Índice / punto de entrada** | Catálogo de la tienda (`/productos/`) |
| **Tipo de fuente** | Editorial (official) — tienda propia sobre Tiendanube |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | Argentina (`Argentina`) — fuente mono-país |
| **Idioma(s)** | ES |
| **Cobertura** | Manga publicado por Kemuri Ediciones en Argentina |
| **Aporte al corpus** | ~2 items (Kemuri Ediciones, Argentina) |
| **Parser / módulo** | entrada en `sources.yml` ("AR - Kemuri Ediciones"), extractor genérico |

**Por qué importa / qué aporta de único**: editorial argentina con tienda propia;
suma catálogo de Kemuri en el mercado AR, complementando otras fuentes del país.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda Tiendanube; las fichas de producto cuelgan
  de `/productos/`. Paginación acotada a `max_pages: 5`.
- **Estructura del HTML**: cada producto se identifica con el atributo
  `[data-product-id]` (selector de item) y el título sale del enlace
  `a[href*='/productos/']` (selector de título).
- **Identificador de producto**: URL canónica `/productos/…`.
- **Calidad de imágenes**: {{pendiente: confirmar resolución de portadas}}.

---

## 5. Proceso de ingestión — técnico

- Fuente del **YAML** que se scrapea en **FASE 1** del pipeline canónico
  (`manga_watch.py --workers 8`, vía `scrape_full.sh` / `scrape_delta.sh`), con el
  **extractor genérico** de HTML. **No tiene parser propio**.
- Entrada en `sources.yml`: `"AR - Kemuri Ediciones"` (`enabled: true`,
  `kind: html`, `source_class: official`, `max_pages: 5`). Selectores verbatim:
  - `item_selector: "[data-product-id]"`
  - `title_selector: "a[href*='/productos/']"`
- El patrón `[data-product-id]` + `/productos/` es el **típico de Tiendanube** (#4),
  compartido con otras tiendas LatAm (p. ej. Kamite MX, que parece Shopify pero es
  Tiendanube, #5).

---

## 9. Pendientes / limitaciones conocidas

- Aporte chico al corpus (~2 items); {{pendiente: confirmar si refleja catálogo real
  o si la paginación / los selectores dejan productos afuera}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "AR - Kemuri Ediciones"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "kemuri"
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
