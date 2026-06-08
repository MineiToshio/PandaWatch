# Fuente: Edizioni BD

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Edizioni BD (sello manga: J-Pop Manga) |
| **URL base** | `https://www.edizionibd.it` |
| **Índice / punto de entrada** | Búsqueda: `https://www.edizionibd.it/catalogsearch/result/?q={query}` |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` (con `search_template`) |
| **`source_class`** | `official` |
| **País(es)** | Italia (`it`) |
| **Idioma(s)** | Italiano (IT) |
| **Cobertura** | Catálogo de Edizioni BD / J-Pop Manga; vía búsqueda por keywords de ediciones especiales |
| **Aporte al corpus** | 0 items netos atribuibles al sitio de Edizioni BD (ver §8 y §9) |
| **Parser / módulo** | Entrada en `sources.yml` (sin módulo propio) |

**Por qué importa / qué aporta de único**: editorial italiana cuyo sello de manga es
**J-Pop Manga**. Cubre ediciones limitadas, deluxe y cofanetti del mercado italiano. En la
práctica la presencia de Edizioni BD / J-Pop en el corpus llega hoy por OTRAS fuentes
(catálogo comunitario animeclick.it), no por el scraping directo del sitio (§8).

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda Magento. La entrada activa NO es el storefront
  sino la **búsqueda** (`catalogsearch/result/?q={query}`), que se expande en una consulta
  por cada keyword (ver §5).
- **Estructura del HTML**: items en `li.product-item`; título en `a.product-item-link`.
  (La entrada storefront deshabilitada usa `div.product.product-item` /
  `.product-item-link, .product-item-name a`.)
- **Identificador de producto**: URL canónica de la ficha de producto Magento.
- **Anti-bot / quirks**: tienda Magento; la búsqueda devolvió 0 productos netos para las
  keywords configuradas (ver §8).

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: `IT - Edizioni BD (search)` (`enabled: true`), con
  `publisher: Edizioni BD`, `country: Italia`, `source_class: official`, `kind: html`.
- **Fase del pipeline**: se scrapea en la **FASE 1** (`manga_watch.py`, sources del YAML).
  **No tiene parser propio.**
- **Expansión por keyword**: la `search_template` se expande en fuentes virtuales —una por
  keyword— vía `_expand_search_template()` (tag `expansion`). Keywords configuradas:
  `edizione limitata`, `edizione speciale`, `deluxe`, `cofanetto`, `variant`.
- **`source_purity`** se propaga a esas fuentes hijas (#7).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **0 items netos del sitio de Edizioni BD**: la búsqueda Magento con las keywords
  configuradas no aportó productos al corpus. Los 162 items que aparecen con
  `publisher = "Edizioni BD"` provienen en realidad de **animeclick.it** (catálogo
  comunitario italiano), no del scraping de `edizionibd.it`. La atribución del aporte real
  de esta fuente es 0.
- **#7 (search_template)**: la fuente usa el mecanismo de `search_template` + keywords; la
  `source_purity` se propaga a las fuentes virtuales por keyword.

---

## 9. Pendientes / limitaciones conocidas

- La entrada **storefront** `IT - Edizioni BD` (`url: https://www.edizionibd.it/`) está
  **`enabled: false`** (auditoría 2026-05-25: 0 items). La cobertura, de existir, llega por
  la entrada de **búsqueda** (`(search)`), que hoy también rinde 0 items netos.
- {{pendiente: confirmar si la búsqueda Magento requiere otros selectors/keywords o está
  bloqueada — la cobertura real de J-Pop Manga llega por animeclick.it, no por este sitio}}.
- {{pendiente: decidir si conviene mantener la fuente habilitada dado el aporte 0, o
  re-evaluar selectors/keywords}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente (FASE 1, sin standardize):
.venv/bin/python scripts/manga_watch.py --only-source "IT - Edizioni BD (search)"

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales atribuidos a Edizioni BD en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
items=[json.loads(l) for l in open("data/items.jsonl") if l.strip()]
sel=[it for it in items if 'edizioni bd' in (it.get('publisher','') or '').lower()]
print("items:", len(sel))
print("países:", Counter((it.get('country') or '') for it in sel if it.get('country')))
print("editoriales:", Counter((it.get('publisher') or '') for it in sel).most_common(10))
PY
```

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0 duras)
→ tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza
esta ficha.
