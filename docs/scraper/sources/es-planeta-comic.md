# Fuente: Planeta Cómic

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | ES - Planeta Cómic |
| **URL base** | `https://www.planetadelibros.com` |
| **Índice / punto de entrada** | `https://www.planetadelibros.com/editorial/planeta-comic/54` |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | España (`es`) — fuente mono-país |
| **Idioma(s)** | ES |
| **Cobertura** | Catálogo de la editorial Planeta Cómic en la web de Planeta de Libros: manga + cómic occidental + literatura clásica integral (publica mixto). |
| **Aporte al corpus** | 3 items (Planeta Cómic, España). |
| **Parser / módulo** | Entrada en `sources.yml` (`ES - Planeta Cómic`), sin módulo propio — extractor genérico. |

`purity: mixed`, `tags: ["manga", "official"]`. La editorial publica manga junto con
cómic occidental (Madman, etc.) y literatura clásica (p. ej. *La guerra de los mundos*
integral), por eso es mixed: sólo entra lo que tiene STRONG manga hint (decisión #3) y la
comics blacklist (#11) descarta lo occidental.

**Por qué importa / qué aporta de único**: cobertura oficial del catálogo de Planeta
Cómic, una de las grandes editoriales de manga en España. Complementa a ListadoManga con
la ficha de origen de la editorial. Aporte numérico hoy bajo (3 items): la mayor parte del
catálogo español de Planeta llega vía ListadoManga.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: índice de editorial en `planetadelibros.com` con
  listado de productos paginado; cada producto tiene su página de detalle. El scrape
  recorre hasta `--max-pages 5` desde la URL de entrada.
- **Estructura del HTML/feed**: sin selectores explícitos en `sources.yml` → el extractor
  genérico usa **auto-detección de cards** (título / imagen / enlace de producto).
  Layout concreto: {{pendiente: confirmar selectores reales de card y de detalle}}.
- **Identificador de producto**: URL canónica del producto en `planetadelibros.com`
  ({{pendiente: confirmar si expone ISBN/SKU en el detalle}}).
- **Anti-bot / quirks**: se scrapea con `--enable-js` (JS-rendered, gotcha #12 — la fase 1
  lo corre con Playwright serializado por el worker thread). Posible mojibake ES/cp1252
  (#1) — lo repara `clean_title()` si aparece. {{pendiente: confirmar si hay Cloudflare /
  lazy-images / placeholders}}.
- **Calidad de imágenes**: {{pendiente: confirmar resolución de las portadas que sirve
  planetadelibros.com}}.

---

## 5. Proceso de ingestión — técnico

Es una fuente **simple del YAML**, sin parser ni bootstrap-wiki propios.

- **Entrada**: bloque `ES - Planeta Cómic` en `sources.yml`
  (`url: …/editorial/planeta-comic/54`, `kind: html`, `purity: mixed`).
- **Quién la procesa**: el extractor genérico de `manga_watch.py`. Al no traer selectores,
  usa **auto-detección de cards**; si en el futuro el layout lo exige, se agregan
  selectores explícitos en el YAML (no hay módulo dedicado).
- **Purity mixed (decisión #3)**: en mixed, un item sólo pasa si tiene **STRONG manga
  hint** (manga, kanzenban, vol N, deluxe hardcover, etc.); el default es descartar. La
  **comics blacklist (#11)** se aplica SIEMPRE y filtra lo occidental (Madman, etc.).

### Flujo end-to-end

Entra en la **FASE 1** de `scrape_full.sh` / `scrape_delta.sh` junto con el resto de
fuentes del YAML:

```
scrape_full/delta.sh
  └─ FASE 1: scrape sources del YAML (manga_watch.py --workers 8 --enable-js
             --fetch-details --max-pages 5 …)   ← acá entra Planeta Cómic
  └─ FASE 3: cleanup retrofits (rescore → filter_non_manga → filter_collectible →
             clean_titles → backfill_metadata)
  └─ FASE 4: build_web.py
  └─ FASE 5: validate_corpus.py
```

Se scrapea **igual en full y en delta** (no tiene discovery diferenciado). Tras el scrape,
items.jsonl queda **raw** (sin `standardized_at`); NO correr skills automáticamente.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Decisión de diseño #3 (purity mixed)**: Planeta publica manga + cómic occidental +
  literatura clásica integral, así que está marcada `mixed` → exige STRONG manga hint y
  apoya en la comics blacklist (#11) para no contaminar el catálogo.
- {{pendiente: no hay historial de bugs específicos documentado para esta fuente; el aporte
  bajo (3 items) sugiere que no se ha estresado.}}

---

## 9. Pendientes / limitaciones conocidas

- **Aporte bajo (3 items)**: la mayor parte del catálogo español de Planeta llega vía
  ListadoManga. Sin auditar si la auto-detección de cards está capturando bien el listado
  de `planetadelibros.com` o si conviene agregar selectores explícitos. {{pendiente:
  confirmar si el bajo aporte es por filtro mixed correcto o por extracción incompleta.}}
- **Selectores / detalle**: layout de card y página de producto sin documentar
  ({{pendiente}}).

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente (deja raw, sin standardize):
.venv/bin/python scripts/manga_watch.py --only-source "ES - Planeta Cómic" \
    --enable-js --fetch-details --max-pages 5

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "planetadelibros"
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
