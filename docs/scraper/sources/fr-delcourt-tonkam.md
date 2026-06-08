# Fuente: Delcourt / Tonkam

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | FR - Delcourt / Tonkam Mangas |
| **URL base** | `https://www.editions-delcourt.fr/mangas` |
| **Índice / punto de entrada** | `https://www.editions-delcourt.fr/mangas` (paginado, `max_pages: 15`) |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | Francia (el país de la edición va al `edition_key`) |
| **Idioma(s)** | Francés |
| **Cobertura** | Catálogo de manga de la editorial francesa Delcourt / Tonkam |
| **Aporte al corpus** | 4 items (todos `country=Francia`, `publisher=Delcourt / Tonkam`) |
| **Parser / módulo** | Entrada en `sources.yml` (extractor genérico, sin parser propio) |

**Por qué importa / qué aporta de único**: editorial oficial francesa con ediciones
prestige (`tags` incluye `"prestige"`); aporta ediciones especiales del mercado FR que
no necesariamente cubren las tiendas/catálogos comunitarios.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: listado paginado bajo `editions-delcourt.fr/mangas`,
  recorrido hasta `max_pages: 15`. Página de producto por título.
- **Estructura del HTML/feed**: la entrada del YAML **no define `selectors`** → se usa la
  **auto-detección** del extractor genérico (sin recetas de selectores propias).
- **Identificador de producto**: {{pendiente: SKU / ISBN / URL canónica — no confirmado}}.
- **Anti-bot / quirks**: posible **mojibake FR (#1)** — editoriales/portales franceses
  suelen devolver UTF-8 decodificado como cp1252; `clean_title()::_fix_mojibake()` lo
  repara primero. Otros quirks {{pendiente: no confirmados}}.
- **Calidad de imágenes**: {{pendiente: no confirmada}}.

---

## 5. Proceso de ingestión — técnico

- **Entrada**: `sources.yml` → `"FR - Delcourt / Tonkam Mangas"` (`kind: html`,
  `enabled: true`, `max_pages: 15`, `tags: ["manga", "official", "prestige"]`).
- **Captura**: se scrapea en la **FASE 1** del pipeline (`manga_watch.py --workers 8`),
  vía el **extractor genérico** de fuentes HTML. **No tiene parser propio** ni `selectors`
  definidos → auto-detección de label/value.
- **Filtros**: pasa por las reglas estándar del pipeline (`is_likely_manga`, pureza,
  filtros de coleccionable) como cualquier fuente del YAML; sin reglas dedicadas.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#1 (mojibake FR)** — fuentes francesas pueden devolver acentos corruptos; lo repara
  `_fix_mojibake()` en `clean_title()`. No metas regex-cleaning antes de esa reparación.

---

## 9. Pendientes / limitaciones conocidas

- **Aporte bajo (4 items)**: con `max_pages: 15` y auto-detección, la cobertura real es
  pequeña. {{pendiente: confirmar si es problema de selectores/auto-detección o catálogo
  acotado}}.
- **Sin `selectors` propios**: depende por completo de la auto-detección genérica; si el
  layout del sitio cambia, la captura puede degradarse silenciosamente.
- **`notes` en el YAML**: la entrada **no tiene** campo `notes`.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "FR - Delcourt / Tonkam Mangas"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver items reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "editions-delcourt"
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
→ tests (`pytest tests/test_extraction.py`) → build.
