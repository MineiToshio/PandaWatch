# Fuente: Manga Dreams

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Manga Dreams |
| **URL base** | `https://mangadreams.it` |
| **Índice / punto de entrada** | `https://mangadreams.it/collections/all` (+ sub-colección, ver §5) |
| **Tipo de fuente** | Tienda (retailer) — Shopify |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `retailer` |
| **País** | Italia (`Italia`) |
| **Idioma** | Italiano |
| **Cobertura** | Ediciones especiales italianas de manga (Variant Metal, prima tiratura, variant covers) + variants/limited europeas importadas |
| **Aporte al corpus** | ~111 items (107 con publisher `Manga Dreams`; el resto desambiguado a editorial real: Kurokawa, Crunchyroll, Glénat) |
| **Parser / módulo** | Entrada en `sources.yml` (extractor genérico Shopify; sin parser propio) |

Son **dos entradas YAML del mismo sitio** (`mangadreams.it`, Shopify), ambas con
`publisher: "Manga Dreams"`, `country: "Italia"`, `source_class: retailer`:

- **`IT - Manga Dreams`** → `url: /collections/all`, `max_pages: 10`.
- **`IT - Manga Dreams (variants europeas)`** → `url: /collections/edizioni-europee-manga-variant-limited`, `max_pages: 3`.

**Por qué importa / qué aporta de único**: catálogo concentra **ediciones especiales
italianas** (Variant Metal, prima tiratura, edizione francese con gadget de evento,
variant covers de One Piece / Vinland Saga / My Hero Academia / Berserk) más **variants y
limited europeas importadas** (francesas, alemanas, españolas) que rara vez aparecen en
otras fuentes. El `publisher` real puede ser otra editorial (el corpus muestra Kurokawa,
Glénat, etc.): `Manga Dreams` es la tienda, no siempre la editorial (#44).

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: Shopify estándar. Listado en `/collections/<x>` con
  paginación Shopify; página de producto bajo `/products/<slug>`. URL típica de producto:
  `/products/one-piece-108-variant-metal-limitata-alla-prima-tiratura`.
- **Estructura del HTML**: tarjetas de producto en el listado.
  - `item_selector`: `.card-wrapper.product-card-wrapper`
  - `title_selector`: `a[href*='/products/']`
  - Ambas entradas YAML usan **los mismos selectores**.
- **Identificador de producto**: URL canónica `/products/<slug>`.
- **Anti-bot / quirks**: Shopify estándar, sin anti-bot conocido. La paginación de
  `/collections/all` se queda corta — ver §5 (por qué existe la sub-colección).

---

## 5. Proceso de ingestión — técnico

Fuente del YAML procesada en **FASE 1** del pipeline (scrape de sources del YAML vía
`manga_watch.py`) con el **extractor genérico de Shopify**. **No tiene parser propio**:
las dos entradas se recorren como cualquier fuente `html` del YAML, con su `item_selector`
/ `title_selector` y su `max_pages`.

**Por qué hay dos entradas (la sub-colección)**: la fuente `/collections/all` no llega a
todos los productos por la **paginación de Shopify** — solo capturaba ~6 de los 43
productos de la colección de variants/limited europeas. Por eso se agregó
`/collections/edizioni-europee-manga-variant-limited` como **fuente hermana directa**, con
los mismos selectores. Sigue la nota de `docs/scraper/SOURCES.md`:

> Tip: si `/collections/all` no captura todo, agregá la sub-colección.

El **dedup automático por `(series_key, edition_key, volume)`** evita duplicar lo que sí se
solapa entre ambas entradas.

---

## 9. Pendientes / limitaciones conocidas

- **`publisher` = tienda, no editorial** (#44): 107 de 111 items quedan con `Manga Dreams`
  como publisher; solo unos pocos se desambiguaron a la editorial real (Kurokawa, Glénat,
  Crunchyroll). La normalización de editorial real para el resto queda pendiente.
- **Cobertura por paginación**: `/collections/all` no surfacea todo; la cobertura completa
  depende de mantener las sub-colecciones relevantes como fuentes hermanas. Si aparece otra
  colección temática con productos que `/collections/all` no trae, hay que agregarla igual.

---

## 10. Runbook / comandos útiles

```bash
# Scrape solo de esta fuente (cada entrada por su nombre):
.venv/bin/python scripts/manga_watch.py --only-source "IT - Manga Dreams"
.venv/bin/python scripts/manga_watch.py --only-source "IT - Manga Dreams (variants europeas)"

# Validar (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "mangadreams"
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
