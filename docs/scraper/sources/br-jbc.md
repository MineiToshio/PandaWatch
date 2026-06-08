# Fuente: Editora JBC

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Editora JBC |
| **URL base** | `https://editorajbc.com.br` |
| **Índice / punto de entrada** | Dos entradas en `sources.yml`: checklist mensual (`/checklist/atual/`) y catálogo completo (`/titulos/`) |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | Brasil (`Brasil`) — fuente mono-país |
| **Idioma(s)** | Portugués (PT-BR) |
| **Cobertura** | Catálogo de manga de Editora JBC: checklist mensual (~184 items/mes) + catálogo completo (~565 títulos) |
| **Aporte al corpus** | 5 items (al último corpus; ver §10) |
| **Parser / módulo** | Dos entradas en `sources.yml` (extractor genérico, sin módulo propio) |

**Editoriales que abarca** (del corpus real): Editora JBC (5 items, todos `Brasil`).

**Por qué importa / qué aporta de único**: cubre el catálogo oficial de Editora JBC,
una de las editoriales de manga de Brasil. Aporta presencia del mercado brasileño (PT-BR)
desde la propia editorial.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: sitio WordPress.
  - `/checklist/atual/` — checklist del mes (lanzamientos físicos, digitales,
    reimpresiones), página única.
  - `/titulos/` — catálogo completo, paginado (`max_pages: 5`).
  - URL de producto: `/mangas/colecao/<serie>/vol/<vol>/`.
- **Estructura del HTML**: cada producto es un card `div.card.item-mangas`. El título
  se toma del `<strong>` directo del card.
- **Identificador de producto**: la URL canónica del producto (`/mangas/colecao/<serie>/vol/<vol>/`).
- **Anti-bot / quirks**: ver el quirk del título en §5 y §8.

---

## 5. Proceso de ingestión — técnico

Ambas entradas se scrapean en **FASE 1** del pipeline (sources del YAML vía
`manga_watch.py`), usando el **extractor genérico** con los selectores declarados.
**No hay parser/módulo propio.**

- **`BR - Editora JBC Checklist`** (`/checklist/atual/`): checklist mensual,
  ~184 items/mes. Sin paginación.
- **`BR - Editora JBC Títulos`** (`/titulos/`): catálogo completo, ~565 títulos,
  con `max_pages: 5`.

Ambas comparten selectores:

```yaml
selectors:
  item_selector: "div.card.item-mangas"
  title_selector: "strong"
```

**Quirk del título en `<strong>`** (saca selectors/notes verbatim): el título se
extrae del `<strong>` directo **a propósito**. El anchor del card
(`a.post-selo-catalog-volume`) contiene un `<span>` con el texto "mais detalhes",
que **contaminaría** el título si se usara el anchor como `title_selector`. Por eso
se apunta al `<strong>` directo en lugar del anchor.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Título contaminado por "mais detalhes"** — el anchor `a.post-selo-catalog-volume`
  del card incluye un `<span>` "mais detalhes"; usarlo como `title_selector` ensuciaría
  el título. → ✅ Se usa el `<strong>` directo del card.

---

## 9. Pendientes / limitaciones conocidas

- **Aporte bajo al corpus** (5 items): {{pendiente: confirmar si es esperado por el
  filtro de coleccionables o si hay sub-captura — la editorial publica ~565 títulos}}.
- {{pendiente: comportamiento full vs delta — ambas entradas se scrapean igual siempre;
  no hay distinción full/delta documentada para esta fuente}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente (ajustar al nombre exacto de la entrada):
.venv/bin/python scripts/manga_watch.py --only-source "BR - Editora JBC Checklist"
.venv/bin/python scripts/manga_watch.py --only-source "BR - Editora JBC Títulos"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "editorajbc"
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
