# Fuente: Square Enix Manga & Books (US)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-12.
>
> ⚠️ NO confundir con **JP - Square Enix Comics** (Japón, `magazine.jp.square-enix.com`),
> que se documenta aparte. Esta ficha es la fuente de **Estados Unidos**.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | US - Square Enix Manga Coming Soon |
| **URL base** | `https://squareenixmangaandbooks.square-enix-games.com` |
| **Índice / punto de entrada** | `https://squareenixmangaandbooks.square-enix-games.com/en-us/release-calendar` |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | Estados Unidos |
| **Idioma** | Inglés (EN) |
| **Cobertura** | Calendario de próximos lanzamientos (coming soon) de Square Enix Manga & Books en EE. UU. |
| **Aporte al corpus** | 0 items históricos; el extractor RSC nuevo (2026-06-12) ve ~488 productos (~32-36 especiales: Perfect Editions, artbooks FF, Material Ultimania, picture books) |
| **Parser / módulo** | `extract_squareenix_rsc` en `manga_watch.py` (extractor DEDICADO, registrado en `_SITE_EXTRACTORS` por dominio) |

**Editoriales que abarca**: Square Enix Manga & Books (sello propio de Square Enix en EE. UU.).

**Por qué importa / qué aporta de único**: cubre el pipeline editorial oficial de
Square Enix en EE. UU. — el adelanto de próximos lanzamientos en inglés, antes de
que aparezcan en tiendas. Complementa la cobertura de la edición japonesa (JP -
Square Enix Comics) con el mercado norteamericano.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: una sola página de calendario de lanzamientos
  (`/en-us/release-calendar`). {{pendiente: estructura de paginación o secciones internas —
  no verificado en vivo}}.
- **Estructura del HTML**: sin `selectors` en `sources.yml` → la fuente la procesa el
  **extractor genérico de HTML** (auto-detección de título/precio/imagen). {{pendiente:
  selectores reales del listado de productos — no verificado en vivo}}.
- **Identificador de producto**: {{pendiente: SKU/ISBN/URL canónica — no verificado en vivo}}.
- **Anti-bot / quirks**: {{pendiente: no verificado en vivo}}. El `kind` es `html` (no `js`),
  así que el pipeline NO renderiza JavaScript para esta fuente (no aplica #12).
- **Calidad de imágenes**: {{pendiente: no verificado en vivo}}.

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: `US - Square Enix Manga Coming Soon` (`kind: html`,
  `source_class: official`, `enabled: true`, `tags: [manga, official, coming-soon]`).
  Sin bloque `selectors` → la procesa el **extractor genérico** de `manga_watch.py`
  (auto-detección de campos), NO un parser dedicado.
- **`purity`**: no declarada → default `manga_only` (todos los productos del listado
  se consideran manga; la comics blacklist aplica siempre, decisión #3).
- **Flujo end-to-end**: se scrapea en la **FASE 1** de `scrape_full.sh` / `scrape_delta.sh`
  (`manga_watch.py --workers 8`), junto al resto de fuentes del YAML. Sin discovery especial
  ni retrofits propios.

---

## 9. Pendientes / limitaciones conocidas

- **0 items en el corpus** (al 2026-06-08): la fuente está `enabled: true` pero todavía
  no aportó items. {{pendiente: confirmar si el extractor genérico capta el calendario o
  si hace falta `selectors` / parser propio — no verificado en vivo}}.
- Sin `selectors`: si el extractor genérico no rinde, habría que agregar selectores
  específicos o un wiki parser dedicado (como se hizo con Kinokuniya).

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "US - Square Enix Manga Coming Soon"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver items reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "square-enix-games"
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

## 8. Problemas encontrados — qué funcionó y qué NO

- **0 candidatos con el extractor genérico (detectado 2026-06-12)**: la página es una
  app **Next.js App Router (RSC)**. El DOM solo renderiza ~10 items del mes visible;
  el catálogo COMPLETO (~488 productos, todos los meses) viene embebido en el payload
  `__next_f` (React Server Components wire format) dentro de `<script>` sin `type` —
  exactamente lo que `extract_generic_html` descarta al decomponer scripts. Ni
  `selectors:` ni `kind: js` sirven (Playwright también vería solo el mes visible).
- **FIX (2026-06-12)**: extractor dedicado `extract_squareenix_rsc` — concatena los
  `self.__next_f.push([1,"…"])`, localiza el array `"products":`, y emite candidatos
  con title/url (`/en-us/product/<slug>` — el slug ES el ISBN-13)/cover (CDN
  `fyre.cdn.sewest.net`)/release_date ("July 2026" → `2026-07-01`). SIN Playwright.
  Falla silenciosa a `[]` si Square Enix cambia el build (cae al flujo genérico).
  Registrado en `_SITE_EXTRACTORS` (hook por dominio en `extract_generic_html`).
  Test: `test_extract_squareenix_rsc_payload`. `purity: manga_only` agregado (sello
  100% manga/artbooks — los artbooks sin la palabra "manga" pasan igual).
- **Riesgos**: estructura del payload puede cambiar con un rebuild de Next.js
  (mitigado: 0 items + extraction_method `sqex-rsc-no-products` en el diagnóstico);
  CDN de portadas puede cambiar (solo rompería imágenes, no títulos/URLs).
