# Fuente: Akata

> ⚠️ **PODA 2026-06-12 (poda de fuentes muertas)** — `FR - Akata`: Deshabilitada: 0 items netos históricos; FR cubierta por Manga-Sanctuary + Pika/Glénat/Kurokawa/Meian.
> Registro completo: [descartadas/README.md](descartadas/README.md).

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Akata |
| **URL base** | `https://www.akata.fr/` |
| **Índice / punto de entrada** | `https://www.akata.fr/` |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | Francia (`fr`) — fuente mono-país |
| **Idioma(s)** | Francés (FR) |
| **Cobertura** | Catálogo de la editorial francesa Akata (manga y obras relacionadas) |
| **Aporte al corpus** | 0 items hoy (snapshot 2026-06-08; ver §9) |
| **Parser / módulo** | Entrada en `sources.yml` (`FR - Akata`), extractor genérico HTML |

**Editoriales que abarca**: Akata (editorial; `publisher: "Akata"` fijado en el YAML).
El `publisher` es la editorial real, no una tienda (#44).

**Por qué importa / qué aporta de único**: editorial francesa con catálogo propio;
aporta ediciones del mercado francés (idioma FR) directamente desde la fuente oficial.

---

## 2. Descripción técnica de la fuente

- **Estructura del sitio**: sitio Drupal (módulo *Views*). El listado de productos se
  renderiza como vistas de Drupal; cada producto cae en un bloque
  `div.views-field-view-comment`.
- **Selectores (verbatim del YAML)**:
  - `item_selector: "div.views-field-view-comment"`
  - `title_selector: "a"`
- **Identificador de producto**: URL del producto (link `<a>` dentro del item).
  {{pendiente: confirmar si hay SKU/ISBN expuesto en la página de producto}}
- **Anti-bot / quirks**: posible **mojibake FR** (#1) — sitios FR suelen devolver UTF-8
  decodificado como cp1252; `clean_title()::_fix_mojibake()` lo repara primero.
- **Calidad de imágenes**: {{pendiente: no determinado}}.

---

## 5. Proceso de ingestión — técnico

- Fuente **SIMPLE** del YAML: se scrapea en **FASE 1** del pipeline
  (`manga_watch.py --workers 8`) vía el **extractor genérico HTML**, NO tiene parser
  propio.
- Entrada en `sources.yml`: `FR - Akata` (`kind: html`, `enabled: true`).
- Captura: por cada `div.views-field-view-comment` (item), el título sale del `<a>`
  interno (`title_selector: "a"`) y la URL del producto del `href` de ese link.
- Luego pasa por los retrofits de cleanup de FASE 3 como cualquier item del catálogo
  (rescore → filtros → clean_titles → backfill de metadata/imágenes).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#1 (mojibake FR)**: aplica potencialmente por ser fuente francesa; el fix está
  centralizado en `clean_title()` — no agregues limpieza de regex antes de eso.

---

## 9. Pendientes / limitaciones conocidas

- **0 items en el corpus hoy** (snapshot 2026-06-08): la fuente está `enabled: true`
  pero no aportó filas al último corpus. {{pendiente: confirmar si los selectores
  Drupal/Views siguen vigentes o si el listado cambió de estructura}}.
- {{pendiente: verificar paginación del listado y si el extractor genérico la sigue}}.
- {{pendiente: identificador de producto (SKU/ISBN) y calidad de imágenes}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "FR - Akata"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver items de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "akata.fr"
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
