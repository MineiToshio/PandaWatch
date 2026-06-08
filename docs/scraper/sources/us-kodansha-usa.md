# Fuente: Kodansha USA (search)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | US - Kodansha USA (search) |
| **URL base** | `https://kodansha.us` |
| **Índice / punto de entrada** | Búsqueda dirigida: `https://kodansha.us/?s={query}` |
| **Tipo de fuente** | Editorial (official) — búsqueda en el sitio oficial |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | Estados Unidos (`us`) |
| **Idioma** | Inglés (EN) |
| **Cobertura** | Catálogo en inglés de Kodansha USA, acotado a las ediciones que matchean las keywords coleccionables |
| **Aporte al corpus** | 0 items hoy |
| **Parser / módulo** | Entrada en `sources.yml` (`search_template`); sin parser propio |

**Por qué importa / qué aporta de único**: trae las **ediciones especiales en inglés de
Kodansha USA** (deluxe, hardcover, box sets, omnibus, collector). Es búsqueda dirigida:
sólo se piden las ediciones que matchean las keywords coleccionables, no el catálogo entero.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs**: una sola plantilla de búsqueda, `https://kodansha.us/?s={query}`,
  donde `{query}` se reemplaza por cada keyword coleccionable.
- **Identificador de producto**: la URL canónica del producto que devuelve la búsqueda.
- **Keywords** (verbatim del YAML): `deluxe`, `limited edition`, `hardcover`, `boxset`,
  `collector`, `omnibus`.

---

## 5. Proceso de ingestión — técnico

- Es una fuente del YAML, procesada en **FASE 1** del pipeline (`manga_watch.py`).
- La `search_template` se **expande en fuentes virtuales por keyword** (tag `expansion`):
  una búsqueda por cada keyword listada. No tiene parser propio; usa los extractores
  genéricos del scraper.
- Las URLs de resultado entran al merge estándar (`merge_cluster` / `consolidate_by_cluster`).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#18 — `omnibus` no califica solo**: un omnibus pelado NO cuenta como coleccionable.
  La keyword `omnibus` sirve para descubrir productos, pero un omnibus sin otro qualifier
  premium (hardcover/deluxe/box set) será filtrado aguas abajo.

---

## 9. Pendientes / limitaciones conocidas

- **0 items en el corpus hoy**: la búsqueda no ha producido filas coleccionables que
  sobrevivan a los filtros, o aún no se ha corrido contra esta fuente. Pendiente verificar
  cobertura real.
- Existe además **`US - Kodansha USA News`** (`https://kodansha.us/news/`, `purity: mixed`),
  un blog de noticias que está **`enabled: false`** (auditoría: 0 items). No forma parte
  del pipeline; se menciona sólo para no confundirla con esta fuente de búsqueda.

---

## 10. Runbook / comandos útiles

```bash
# Ver items reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "kodansha.us"
def hit(it):
    blobs=[it.get('url','') or '']+[ (s.get('url','') or '') for s in it.get('sources',[]) ]
    return any(NEEDLE in b for b in blobs)
items=[json.loads(l) for l in open("data/items.jsonl") if l.strip()]
sel=[it for it in items if hit(it)]
print("items:", len(sel))
print("países:", Counter((it.get('country') or '') for it in sel if it.get('country')))
print("editoriales:", Counter((it.get('publisher') or '') for it in sel if it.get('publisher')).most_common(20))
PY

# Validar:
.venv/bin/python scripts/validate_corpus.py
```

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0 duras)
→ tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza
esta ficha.
