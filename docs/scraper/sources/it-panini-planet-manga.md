# Fuente: Panini / Planet Manga (Italia)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Panini / Planet Manga (Italia) |
| **URL base** | `https://www.panini.it/shp_ita_it/` |
| **Tipo de fuente** | Editorial oficial (Planet Manga es el sello de manga de Panini Italia) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | Italia — código que va al edition_key |
| **Idioma** | Italiano (IT) |
| **`publisher`** | `Panini / Planet Manga` (editorial real, no una tienda — #44 no aplica) |
| **Cobertura** | Catálogo de manga italiano de Planet Manga, con dos categorías de coleccionables directas |
| **Aporte al corpus** | ~128 items (todos `country=Italia`; 127 con publisher `Panini / Planet Manga`, 1 `Panini Comics`) |
| **Parser / módulo** | Entrada(s) en `sources.yml` (sin parser propio) |

Son **tres entradas YAML del mismo sitio** (`panini.it`):

| `name` | URL |
|---|---|
| `IT - Panini Planet Manga` | `…/shp_ita_it/planet-manga.html` |
| `IT - Panini Variant ed Esclusive` | `…/planet-manga/tipologia/variant-ed-esclusive.html` |
| `IT - Panini Edizioni da Collezione e Cofanetti` | `…/planet-manga/tipologia/edizioni-da-collezione-e-cofanetti.html` |

**Por qué importa / qué aporta de único**: cubre el mercado italiano (IT) desde la
editorial oficial. Las dos últimas entradas apuntan directo a categorías de
**coleccionables**: *variant ed esclusive* (variantes y exclusivas) y *edizioni da
collezione e cofanetti* (ediciones de colección y cofres/box sets). Son justo el tipo
de producto que busca PandaWatch, sin tener que filtrar el catálogo general.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda Magento. La entrada principal es la landing
  de Planet Manga; las otras dos son categorías filtradas por *tipologia* (variant/
  esclusive y edizioni da collezione/cofanetti). Cada listado enlaza a las páginas de
  producto del catálogo.
- **Selectores**: las tres entradas **no declaran selectores** en `sources.yml` → se
  apoyan en la **auto-detección genérica del extractor** (layout Magento estándar:
  título, precio, imagen de producto).
- **Identificador de producto**: URL canónica del producto Magento.
- **`publisher` = Panini / Planet Manga** es editorial real; #44 (tienda≠editorial) no
  aplica.
- **Idioma italiano**: los títulos traen acentos (è, à…). No se confirmó mojibake en
  esta fuente; #1 (mojibake) está documentado sólo para FR (Glénat/Pika), no para
  panini.it. {{pendiente: confirmar si panini.it necesita el fix de encoding}}

---

## 5. Proceso de ingestión — técnico

- **Entradas en `sources.yml`**: las tres listadas en §1 (`kind: html`,
  `source_class: official`, `enabled: true`).
- **Fase del pipeline**: se scrapean en **FASE 1** (sources del YAML vía
  `manga_watch.py --workers 8`), junto al resto de fuentes simples. **NO tiene parser
  propio** ni paso de bootstrap-wiki: usa el **extractor genérico** de productos.
- Luego pasan por los retrofits de cleanup estándar (FASE 3: rescore → filtros →
  clean_titles → backfill de metadata/imágenes) como cualquier fuente del YAML.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- Sin parser propio: el comportamiento depende del extractor genérico Magento. Cualquier
  problema de captura es del extractor compartido, no de un módulo de esta fuente.
- {{pendiente: no se registró ningún problema específico de panini.it (mojibake,
  anti-bot, lazy-loading de imágenes) en esta revisión.}}

---

## 9. Pendientes / limitaciones conocidas

- Las tres entradas dependen de la **auto-detección genérica**; si Panini cambia el
  layout Magento, hay que revisar la extracción (no hay selectores fijos que ajustar).
- {{pendiente: encoding/mojibake IT sin confirmar (ver §2).}}
- {{pendiente: cobertura full vs delta sin diferenciar — hoy se scrapea igual siempre
  (es una fuente simple del YAML).}}

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo estas entradas (ajustar el name exacto):
.venv/bin/python scripts/manga_watch.py --only-source "IT - Panini Planet Manga"
.venv/bin/python scripts/manga_watch.py --only-source "IT - Panini Variant ed Esclusive"
.venv/bin/python scripts/manga_watch.py --only-source "IT - Panini Edizioni da Collezione e Cofanetti"

# Validar (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "panini.it"
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
