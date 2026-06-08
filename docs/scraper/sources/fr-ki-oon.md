# Fuente: Ki-oon

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Ki-oon |
| **URL base** | `https://www.ki-oon.com/` |
| **Índice / punto de entrada** | `https://www.ki-oon.com/` |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | Francia (`fr`) — fuente mono-país |
| **Idioma(s)** | Francés |
| **Cobertura** | Novedades del sitio oficial de la editorial francesa Ki-oon |
| **Aporte al corpus** | 0 items al último snapshot (ver §9) |
| **Parser / módulo** | Entrada en `sources.yml` ("FR - Ki-oon"); extractor genérico |

**Por qué importa / qué aporta de único**: editorial oficial francesa con foco en
ediciones de colección (`tags` incluye `collector`). Aporta novedades del mercado FR
directo de la fuente editorial, no de una tienda.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: home en `https://www.ki-oon.com/` como punto de
  entrada; el extractor genérico recorre los items del listado de la página.
- **Estructura del HTML**: `item_selector: article.new`; título vía
  `title_selector: h2, h3, a` (verbatim del YAML).
- **Identificador de producto**: URL del item (sin parser propio que derive SKU/ISBN).
- **Anti-bot / quirks**: al ser fuente francesa, puede aplicar **#1 (mojibake FR)** —
  UTF-8 decodificado como cp1252; `clean_title()::_fix_mojibake()` lo repara primero.
  {{pendiente: confirmar si Ki-oon en particular sirve mojibake — no observado, 0 items}}.
- **Calidad de imágenes**: {{pendiente: no observado en el corpus actual (0 items)}}.

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: bloque `FR - Ki-oon` (`kind: html`, `enabled: true`).
- **Selectores** (verbatim del YAML):

  ```yaml
  selectors:
    item_selector: "article.new"
    title_selector: "h2, h3, a"
  ```

- **Cómo se scrapea**: en FASE 1 del pipeline canónico (`manga_watch.py` desde el YAML),
  con el **extractor genérico HTML** usando esos selectores. NO tiene parser propio ni
  módulo en `scripts/wikis/`.
- **Flujo end-to-end**: entra en FASE 1 (scrape de sources del YAML) de
  `scrape_full.sh` / `scrape_delta.sh`; luego pasa por los retrofits de cleanup (FASE 3)
  y el build (FASE 4) como cualquier fuente del YAML.

---

## 9. Pendientes / limitaciones conocidas

- **0 items en el corpus** al último snapshot (`data/items.jsonl`). La fuente está
  `enabled: true` pero no aporta items netos hoy. {{pendiente: investigar por qué no
  rinde — selector `article.new` desactualizado, contenido JS-rendered (#12), o
  filtrado downstream}}.
- **Mojibake FR (#1)**: aplica a fuentes francesas en general; no confirmado para
  Ki-oon por falta de items observados.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo de esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "FR - Ki-oon"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "ki-oon"
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
