# Fuente: Milky Way Ediciones

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Milky Way Ediciones |
| **URL base** | `https://www.milkywayediciones.com` |
| **Índice / punto de entrada** | `https://www.milkywayediciones.com/collections/proximamente` (preventas) + `search?q={query}` (búsqueda por keyword) |
| **Tipo de fuente** | Editorial (official) — tienda propia en Shopify |
| **`kind` en sources.yml** | `html` (ambas entradas) |
| **`source_class`** | `official` |
| **País(es)** | España (`es`) — fuente mono-país |
| **Idioma(s)** | Español |
| **Cobertura** | Manga publicado por Milky Way Ediciones en España (ediciones especiales/limitadas, deluxe, tapa dura, kanzenban) + preventas/próximos lanzamientos |
| **Aporte al corpus** | ~16 items |
| **Parser / módulo** | Sin parser propio — dos entradas en `sources.yml` vía extractor genérico |

**Por qué importa / qué aporta de único**: tienda oficial de la editorial Milky Way
Ediciones. Aporta sus **preventas/próximos lanzamientos** (que aún no aparecen en otras
fuentes) y sus **ediciones especiales/deluxe** vía búsqueda por keyword, directo de la
fuente primaria (`publisher = Milky Way Ediciones`, no una tienda revendedora, #44).

---

## 2. Descripción técnica de la fuente

- **Plataforma**: Shopify. Listados en `/collections/...`, fichas de producto en
  `/products/...`; la búsqueda usa `/search?q=...` (#4: Shopify usa
  `li.grid__item`/`[data-product-card]` + `/products/`).
- **Dos puntos de entrada distintos** (dos entradas del YAML, mismo dominio):
  - **`ES - Milky Way Próximamente`** (`html`): listado fijo de la colección
    `collections/proximamente` (preventas / próximos lanzamientos). Sin `selectors`
    custom → extractor genérico de Shopify.
  - **`ES - Milky Way (search)`** (`html`): `search_template`
    `https://www.milkywayediciones.com/search?q={query}`, expandido por keyword
    (ver §5).
- **Identificador de producto**: URL canónica del producto Shopify (`/products/<slug>`).
- **Calidad de imágenes**: portadas de la CDN de Shopify (`cdn.shopify.com`),
  resolución aceptable. {{pendiente: confirmar resolución típica si se vuelve relevante}}.

---

## 5. Proceso de ingestión — técnico

Sin parser propio: ambas entradas se scrapean en la **FASE 1** del pipeline
(`manga_watch.py`, sources del YAML) con el **extractor genérico de Shopify**.

- **`ES - Milky Way Próximamente`**: se recorre como una fuente HTML simple — se visita
  el listado `collections/proximamente` y cada producto del grid entra como un item.
- **`ES - Milky Way (search)`**: el `search_template` se expande a **una fuente virtual
  por keyword** (`edicion limitada`, `edicion especial`, `deluxe`, `tapa dura`,
  `kanzenban`) vía `_expand_search_template()`; cada keyword dispara un `GET`
  `search?q=<keyword>` y los resultados entran como items. El `source_purity` de la
  entrada se propaga a esos hijos search-template (#7).
- Ambas comparten `publisher = Milky Way Ediciones`, `country = España`,
  `source_class = official`. El país va al `edition_key` como `…-es` (#46).
- El merge multi-fuente es el estándar del proyecto (`consolidate_by_cluster()` en
  `manga_watch.py`, decisión #1); esta fuente no tiene reglas de agrupación propias.

---

## 9. Pendientes / limitaciones conocidas

- **Sin `selectors` custom**: ambas entradas dependen del extractor genérico de Shopify.
  Si Milky Way cambia el tema de Shopify y rompe los selectores por defecto (#4), habría
  que agregar `selectors` en el YAML.
- **Variantes Shopify multi-tomo** (#16): no hay evidencia de que esta tienda modele
  packs/box sets como 1 producto = N SKUs. {{pendiente: confirmar si alguna ficha usa
  variantes de volumen; de ser así, evaluar `shopify_variants.py`}}.
- **Cobertura search-template**: limitada a las 5 keywords configuradas; ediciones
  especiales con otra nomenclatura podrían no salir en la búsqueda.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente (preventas):
.venv/bin/python scripts/manga_watch.py --only-source "ES - Milky Way Próximamente"

# Scrape sólo la búsqueda por keyword:
.venv/bin/python scripts/manga_watch.py --only-source "ES - Milky Way (search)"

# Validar (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "milkywayediciones"
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
