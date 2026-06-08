# Fuente: Norma Editorial

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Norma Editorial |
| **URL base** | `https://www.normaeditorial.com` |
| **Índice / punto de entrada** | `https://www.normaeditorial.com/novedades/manga` (catálogo) + `?s={query}` (búsqueda) |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | España (`es`) — fuente mono-país |
| **Idioma(s)** | ES (también publica en catalán en su línea manga) |
| **Cobertura** | Catálogo de manga de Norma Editorial publicado en España |
| **Aporte al corpus** | 5 items (todos España / Norma Editorial) |
| **Parser / módulo** | Sin parser propio — 2 entradas en `sources.yml`, extractor genérico |

Es una **editorial** española: el `publisher` es siempre Norma Editorial y el país
de la edición es España (#46). No es una tienda.

**Por qué importa / qué aporta de único**: capta las ediciones especiales de Norma
(coleccionista, limitadas, deluxe, cofres, integrales, kanzenban, tapa dura) desde la
fuente oficial. Complementa lo que ya entra por ListadoManga, llegando directo a la
editorial cuando una novedad aún no está reflejada en el catálogo comunitario.

> Nota: Norma tiene además dos cuentas de Bluesky en el YAML (`SOCIAL - Norma Editorial
> Bluesky` y `SOCIAL - Norma Editorial Manga Bluesky`). Son fuentes sociales aparte, no
> cubiertas por esta ficha.

---

## 2. Descripción técnica de la fuente

Esta editorial entra al corpus por **dos entradas YAML** del mismo sitio
(`normaeditorial.com`), con dos caminos distintos:

- **Catálogo / novedades** — `ES - Norma Editorial Manga`. HTML de
  `https://www.normaeditorial.com/novedades/manga`, paginado hasta `max_pages: 15`.
  Listado de novedades de manga; cada producto del listado es un candidato.
- **Búsqueda dirigida** — `ES - Norma (search)`. Plantilla `?s={query}` con
  `purity: "mixed"`. Captura ediciones premium que pueden no estar en la portada de
  novedades, lanzando una búsqueda por cada keyword de coleccionable.

- **Estructura del HTML/feed**: layout HTML estándar, procesado por el extractor
  genérico de listados (`extract_listing_candidates`); no hay selectores a medida.
- **Identificador de producto**: URL canónica del producto en normaeditorial.com.
- **Anti-bot / quirks**: la búsqueda devuelve resultados **no-manga** (episodios de
  podcast, posts del blog) → por eso `purity: "mixed"` (ver §5 y §8).
- **Calidad de imágenes**: {{pendiente: no verificado en esta ficha}}.

---

## 5. Proceso de ingestión — técnico

Sin parser propio: ambas entradas viven en `sources.yml` y las procesa el extractor
genérico de listados en la **FASE 1** de `scrape_full.sh` / `scrape_delta.sh`
(`manga_watch.py --workers 8`, source loop del YAML).

- **`ES - Norma Editorial Manga`** (líneas ~468-478 de `sources.yml`): `kind: html`,
  `url` de novedades, `max_pages: 15`. Se recorre el listado paginado y cada producto
  pasa por `is_likely_manga()`.

- **`ES - Norma (search)`** (líneas ~1526-1543): `search_template:
  "https://www.normaeditorial.com/?s={query}"` con 7 `keywords` (`edicion
  coleccionista`, `edicion limitada`, `deluxe`, `cofre`, `integral`, `kanzenban`,
  `tapa dura`). En el arranque, `_expand_search_template()` la expande en **N
  "fuentes virtuales"**, una por keyword (`ES - Norma (search) [search: <keyword>]`),
  sustituyendo `{query}` URL-encoded. El `source_purity` se **propaga a cada hijo**
  (#7). Receta general: `docs/scraper/SOURCES.md` → "Recipe: add a search-template entry".

- **`purity: "mixed"` (decisión #3)**: como la búsqueda devuelve también podcast/blog,
  la decisión por defecto se invierte a "descartar" — sólo pasa lo que tiene un STRONG
  manga hint (manga / vol N / kanzenban / deluxe / etc.). Un pack-extra solo (ej.
  "edición coleccionista" sin señal de manga) NO rescata al item.

Ambas entradas comparten `publisher: "Norma Editorial"`, `country: España`,
`source_class: official`. El merge multi-fuente y el resto del pipeline (filtros,
imágenes, build) son los canónicos; no hay retrofits dedicados a esta fuente.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#3 (purity mixed)**: la búsqueda `?s=` devuelve episodios de podcast y posts del
  blog además de mangas → se marcó `purity: "mixed"` para exigir STRONG manga hint y
  evitar falsos positivos. ✅
- **#7 (propagación de purity)**: el `mixed` se hereda a cada fuente virtual generada
  por `_expand_search_template()`; no hay que marcarlo por keyword. ✅

---

## 9. Pendientes / limitaciones conocidas

- **Aporte bajo (5 items)**: solapa con ListadoManga. {{pendiente: confirmar si el
  bajo conteo es esperado o si el catálogo/búsqueda está sub-capturando}}.
- **Calidad de imágenes**: {{pendiente: no evaluada en esta ficha}}.
- Diferencias FULL vs DELTA por-fuente: ambas entradas se scrapean igual en los dos
  scripts (la única fuente con discovery diferenciado es ListadoManga).

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo el catálogo de novedades de Norma:
.venv/bin/python scripts/manga_watch.py --only-source "ES - Norma Editorial Manga"

# Scrape sólo la búsqueda dirigida (se expande por keyword):
.venv/bin/python scripts/manga_watch.py --only-source "ES - Norma (search)"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "normaeditorial"
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

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0
duras) → tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful,
actualiza esta ficha.
