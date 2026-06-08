# Fuente: Ivrea Argentina (Editorial Ivrea Argentina)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

Cubre las **dos** entradas de `sources.yml` para la editorial Ivrea Argentina:
la web de la editorial (`ivrea.com.ar`) y su portal de novedades (`ivreality.com.ar`).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | `AR - Ivrea Argentina` y `AR - Ivreality` |
| **URL base** | `https://www.ivrea.com.ar/` · `https://www.ivreality.com.ar/` |
| **Índice / punto de entrada** | La home de cada dominio (no hay sitemap declarado en el YAML) |
| **Tipo de fuente** | editorial (official) |
| **`kind` en sources.yml** | `html` (ambas) |
| **`source_class`** | `official` (ambas) |
| **País(es)** | Argentina (`Argentina`) — va al edition_key |
| **Idioma(s)** | ES |
| **Cobertura** | Catálogo y novedades de Editorial Ivrea Argentina (manga en español, edición argentina) |
| **Aporte al corpus** | 8 items (todos vía `ivrea.com.ar`); `ivreality.com.ar` aporta 0 hoy |
| **Parser / módulo** | Entradas en `sources.yml` (extractor genérico por selectores, sin módulo propio) |

Editoriales reales en el corpus (de §10): **Editorial Ivrea Argentina** (8/8).
País: Argentina (8/8). Recuerda: `publisher` = editorial real, NO la tienda (#44).

**Por qué importa / qué aporta de único**: cubre la edición **argentina** de Ivrea,
distinta de la edición española (`ES - Ivrea España Noticias`). País distinto =
edición distinta (#46), así que estos items nunca se mergean con los de Ivrea España.

---

## 2. Descripción técnica de la fuente

- **`ivrea.com.ar`** — web de la editorial armada con **WPBakery** (page builder de
  WordPress). Los productos se listan como columnas del grid; el `item_selector`
  apunta a esas columnas (`div.vc_col-sm-2.vc_column_container.wpb_column`). No se
  definen `title_selector`/`link_selector`, así que el extractor genérico cae a sus
  heurísticas por defecto dentro de cada card.
- **`ivreality.com.ar`** — portal de **noticias/novedades** con tema **Newspaper
  (tagDiv)**. Cada nota es un módulo `div.td_module_flex`; el título/enlace salen del
  `<h3 class="entry-title">` (o `.td-module-title`). Es un feed de posts de novedades,
  no un catálogo de producto con precio.
- **Identificador de producto**: URL de la card/post (sin SKU/ISBN expuesto en el listado).
- **Anti-bot / quirks**: ninguno documentado por ahora. `ivreality.com.ar` aporta 0
  items netos (ver §8).
- **Calidad de imágenes**: {{pendiente: no verificado}}.

---

## 5. Proceso de ingestión — técnico

Ambas entradas se scrapean en **Fase 1** del pipeline (scrape de sources del YAML vía
`manga_watch.py`), con el **extractor genérico por selectores** —
`extract_with_selectors()` en `scripts/manga_watch.py` (~línea 4503). **No hay parser
propio.**

Selectores (verbatim del YAML):

- **`AR - Ivrea Argentina`** (`ivrea.com.ar/`):
  - `item_selector: "div.vc_col-sm-2.vc_column_container.wpb_column"`
- **`AR - Ivreality`** (`ivreality.com.ar/`):
  - `item_selector: "div.td_module_flex"`
  - `title_selector: "h3.entry-title a, .td-module-title a"`
  - `link_selector: "h3.entry-title a, .td-module-title a"`

El extractor recorre cada card del `item_selector`, saca título/enlace (con los
selectores declarados o las heurísticas por defecto cuando faltan) y emite candidatos
que luego pasan por los filtros y el merge canónico (1 fila por producto, decisión #1).
Tras el scrape, los retrofits de cleanup corren igual que para el resto de fuentes del
YAML (rescore → filter_non_manga → filter_collectible → clean_titles → backfill_metadata).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **`ivreality.com.ar` aporta 0 items netos**: hoy el corpus no tiene ningún item de
  este dominio. Puede ser que sea un feed de noticias (no de producto) y que sus posts
  no pasen el filtro de "edición especial física", o que los selectores `td_module_flex`
  no estén matcheando el layout actual. {{pendiente: confirmar causa — feed de noticias
  filtrado vs. selectores stale}}.
- **`ivrea.com.ar` sí aporta** (8 items), todos `Editorial Ivrea Argentina` / Argentina.
- **Decisión**: no mergear cross-país con Ivrea España (#46) — la edición argentina es
  edición propia.

---

## 9. Pendientes / limitaciones conocidas

- `ivreality.com.ar` en 0 items: decidir si vale la pena mantenerlo enabled o ajustar
  selectores / filtros. {{pendiente}}.
- Aporte real chico (8 items) vía `ivrea.com.ar`. {{pendiente: si se espera más cobertura,
  revisar paginación/índice — el YAML sólo declara la home como punto de entrada}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo estas fuentes (ajustar al caso):
.venv/bin/python scripts/manga_watch.py --only-source "AR - Ivrea Argentina"
.venv/bin/python scripts/manga_watch.py --only-source "AR - Ivreality"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de ambos dominios en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
for NEEDLE in ["ivrea.com.ar", "ivreality"]:
    def hit(it):
        blobs=[it.get('url','') or '']+[ (s.get('url','') or '') for s in it.get('sources',[]) ]
        return any(NEEDLE in b for b in blobs)
    items=[json.loads(l) for l in open("data/items.jsonl") if l.strip()]
    sel=[it for it in items if hit(it)]
    print("== NEEDLE", NEEDLE, "==")
    print("items:", len(sel))
    print("países:", Counter((it.get('country') or '') for it in sel if it.get('country')))
    print("editoriales:", Counter((it.get('publisher') or '') for it in sel if it.get('publisher')).most_common(20))
PY
```

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0 duras)
→ tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza
esta ficha.
