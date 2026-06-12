# Fuente: Panini Manga México

> ⚠️ **PODA 2026-06-12 (poda de fuentes muertas)** — `MX - Panini Manga México`: El catálogo base se deshabilitó (2 candidatos/run → 0 netos); Boxsets + búsquedas siguen activas (67+ items).
> Registro completo: [descartadas/README.md](descartadas/README.md).

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Panini Manga México (4 entradas del mismo sitio) |
| **URL base** | `https://tiendapanini.com.mx` |
| **Índice / punto de entrada** | `coleccionables/item-3` · `coleccionables/item-3/boxsets` · `catalogsearch/result/?q=…` |
| **Tipo de fuente** | Tienda (retailer) — tienda oficial de la editorial |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | México (`mx`) — el país va al edition_key (#46) |
| **Idioma(s)** | ES |
| **Cobertura** | Coleccionables y ediciones especiales de Panini Manga México (Magento) |
| **Aporte al corpus** | ~64 items (Panini Manga México) |
| **Parser / módulo** | entradas en `sources.yml` (extractor genérico, sin parser propio) |

**Editoriales que abarca** (del corpus real, ver §10): Panini Manga México (~64 items).
`publisher` = editorial real, NO la tienda (#44).

**Por qué importa / qué aporta de único**: es la tienda oficial de Panini en México;
aporta ediciones especiales, deluxe, cofres, kanzenban, box sets y portadas variantes del
mercado mexicano (idioma ES, país `mx`) que otras fuentes no cubren.

---

## 2. Descripción técnica de la fuente

- **Plataforma**: Magento. Listados de categoría (`coleccionables/item-3`,
  `…/boxsets`) y búsqueda (`catalogsearch/result/?q=…`).
- **Estructura del HTML**: items en `li.product-item`; título en `a.product-item-link`
  (selectores declarados en la entrada `(search)`; las demás usan el extractor genérico).
- **Cuatro entradas YAML del mismo sitio**:
  1. **MX - Panini Manga México** — `url: coleccionables/item-3`, `purity: mixed`
     (la categoría `/coleccionables` incluye cromos, no solo manga), `max_pages: 15`.
  2. **MX - Panini México Boxsets** — `url: coleccionables/item-3/boxsets`,
     `tags: [manga, boxset, official]`.
  3. **MX - Panini México búsqueda edición especial** — `url:
     catalogsearch/result/?q=edicion%20especial`, `purity: mixed` (trae CONMEBOL
     Libertadores, Hot Wheels, Dragon Ball Cards, etc.).
  4. **MX - Panini México (search)** — `search_template:
     catalogsearch/result/?q={query}`, `purity: mixed` (catálogo trae trading cards
     FIFA/WC, Hot Wheels, Lady Bug, etc.), selectors `li.product-item` /
     `a.product-item-link`, keywords: `edicion limitada`, `edicion especial`,
     `edicion coleccionista`, `deluxe`, `cofre`, `kanzenban`, `tapa dura`, `variante`,
     `portada variante`, `gran formato`, `boxset`, `tarot`, `celebration`, `anniversary`,
     `tribute`, `aniversario`. (Se eliminaron `master edition` / `ultimate edition`: el
     catálogo MX no las indexa hoy.)
- **Anti-bot / quirks**: {{pendiente: no determinado en esta revisión}}.
- **Calidad de imágenes**: {{pendiente: no determinado en esta revisión}}.

---

## 5. Proceso de ingestión — técnico

- **Sin parser propio**: las 4 entradas se ingieren en **FASE 1** (scrape de sources del
  YAML, `manga_watch.py --workers 8`) vía el **extractor genérico** de Magento.
- **Search-template → fuentes virtuales**: la entrada `(search)` se expande en una fuente
  por keyword (tag `expansion`) vía `_expand_search_template()`. El `source_purity` se
  **propaga** a esos hijos (#7).
- **`purity: mixed` → requiere STRONG manga hint** (decisión #3): hay mucho ruido de
  cromos/trading cards/coleccionables no-manga (CONMEBOL, Hot Wheels, Dragon Ball Cards,
  FIFA/WC, Lady Bug). Solo pasan los items con señal fuerte de manga. La comics blacklist
  se aplica SIEMPRE, no solo en mixed.
- **País = edición** (#46): el país de estas 4 fuentes es México (`mx`) — el de la
  editorial/idioma, no el de la tienda.

---

## 9. Pendientes / limitaciones conocidas

- Anti-bot / quirks y calidad de imágenes del sitio: **{{pendiente: no determinado en esta
  revisión}}**.
- El corpus muestra 1 item con `publisher: Panini Manga ARG` que también referencia
  `tiendapanini`; verificar que no haya cruce de país (debe ser `mx`, #46).

---

## 10. Runbook / comandos útiles

```bash
# Scrape de estas fuentes (FASE 1, junto al resto del YAML):
.venv/bin/python scripts/manga_watch.py --only-source "MX - Panini Manga México"
.venv/bin/python scripts/manga_watch.py --only-source "MX - Panini México (search)"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "tiendapanini"
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
