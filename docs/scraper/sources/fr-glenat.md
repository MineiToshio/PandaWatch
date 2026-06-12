# Fuente: Glénat Manga (Francia)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Glénat Manga (Francia) |
| **URL base** | `https://www.glenat.com` |
| **Índice / punto de entrada** | Dos listados: `/manga/nouveautes/` (novedades) y `/livres-keywords-art-book/` (art books) |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | Francia (`Francia`) — el país va al edition_key |
| **Idioma(s)** | Francés (FR) |
| **Cobertura** | Catálogo de la editorial francesa Glénat: novedades de su línea manga + art books |
| **Aporte al corpus** | 2 items (al último corpus) |
| **Parser / módulo** | Dos entradas en `sources.yml` (extractor genérico HTML; sin parser propio) |

Esta fuente cubre **dos entradas del YAML** del mismo sitio (`glenat.com`), ambas
`publisher: Glénat Manga`, `country: Francia`, `source_class: official`, `kind: html`:

- **"FR - Glénat Manga Nouveautés"** → `https://www.glenat.com/manga/nouveautes/`,
  `max_pages: 15`, tags `["manga", "official", "france"]`.
- **"FR - Glénat Art Books"** → `https://www.glenat.com/livres-keywords-art-book/`,
  tags `["artbook", "official", "france"]`.

**Por qué importa / qué aporta de único**: es la voz **oficial de la editorial** para el
mercado **francés** (FR), uno de los mercados clave de ediciones premium de manga. Aporta
novedades de la línea manga y, por separado, **art books** — formato premium que otras
fuentes no siempre capturan.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: dos listados independientes. Nouveautés pagina (hasta
  `max_pages: 15`); art books es un listado por keyword. Cada producto enlaza a su ficha en
  `glenat.com`.
- **Estructura del HTML/feed**: listado HTML estático servido por la editorial; el
  extractor genérico saca título / imagen / URL de cada ficha del listado.
  {{pendiente: selectores específicos — las entradas del YAML no declaran `selectors`,
  los maneja el extractor genérico}}.
- **Identificador de producto**: URL canónica de la ficha en `glenat.com`.
- **Anti-bot / quirks**: **mojibake FR (#1)** — Glénat sirve UTF-8 decodificado como
  cp1252; `clean_title()::_fix_mojibake()` lo repara PRIMERO (no metas regex-cleaning
  antes). La **búsqueda del sitio es JS-only** (ver §9). Otros quirks: {{pendiente: no
  confirmados}}.
- **Calidad de imágenes**: {{pendiente: no determinada}}.

---

## 5. Proceso de ingestión — técnico

Fuente del YAML, **sin parser propio**: la procesa el **extractor genérico HTML** del
pipeline.

- **Entrada en `sources.yml`**: las dos entradas enabled (Nouveautés y Art Books) descritas
  en §1.
- **Flujo end-to-end**: ambas entran en la **FASE 1** de `scrape_full.sh` / `scrape_delta.sh`
  (scrape de las sources del YAML vía `manga_watch.py --workers 8`). Luego pasan por los
  retrofits de cleanup comunes (rescore → filtros → clean_titles → backfill de metadata/
  imágenes) como cualquier fuente del YAML. No tiene discovery especial ni enforcer
  dedicado.

---

## 9. Pendientes / limitaciones conocidas

- **"FR - Glénat (search)" está DESHABILITADA** (`enabled: false`): el endpoint
  `?keys={query}` devuelve la **home**, no resultados — la búsqueda del sitio es **JS-only**.
  Se usa la canónica `/manga/nouveautes/` en su lugar. (También existe
  `SOCIAL - Glénat Manga Bluesky`, otra entrada/fuente, fuera del alcance de esta ficha.)
- **Aporte bajo al corpus** (2 items): {{pendiente: confirmar si es esperado o si el
  listado/paginación no se está recorriendo completo}}.
- **Selectores y calidad de imagen**: {{pendiente: no determinados en esta revisión}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo estas fuentes (ajustar el nombre exacto del YAML):
.venv/bin/python scripts/manga_watch.py --only-source "FR - Glénat Manga Nouveautés"
.venv/bin/python scripts/manga_watch.py --only-source "FR - Glénat Art Books"

# Validar (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver items reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "glenat.com"
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
