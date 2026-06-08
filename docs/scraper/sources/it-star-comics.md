# Fuente: Star Comics (Italia)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Star Comics |
| **URL base** | `https://www.starcomics.com` |
| **Índice / punto de entrada** | `https://www.starcomics.com/categorie-fumetti/manga` (listado) + `https://www.starcomics.com/ricerca-fumetti?q={query}` (búsqueda por keyword) |
| **Tipo de fuente** | Editorial (`official`) — sitio oficial de Star Comics |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | Italia — fuente mono-país (va al `edition_key`) |
| **Idioma** | Italiano |
| **Cobertura** | Manga publicado por Star Comics en Italia: ediciones especiales, variant cover, celebration/anniversary editions, cofanetti, deluxe, collector, anime comics packs |
| **Aporte al corpus** | ~83 items (82 con publisher `Star Comics`) |
| **Parser / módulo** | Entradas en `sources.yml` (extractor genérico, sin módulo propio) |

**Por qué importa / qué aporta de único**: es el canal **oficial** de las
ediciones especiales italianas de Star Comics — variant cover, celebration y
anniversary editions, tribute variant/cover, cofanetti y collector. La fuente de
búsqueda (`ricerca-fumetti`) es la que más aporta: las variant cover y collector
salen casi todas de ahí.

---

## 2. Descripción técnica de la fuente

Son **dos entradas YAML** del mismo sitio (`starcomics.com`), ambas `enabled`,
publisher `Star Comics`, country Italia, `official`:

- **"IT - Star Comics Manga"** (`html`): listado de catálogo en
  `/categorie-fumetti/manga`, `max_pages: 15`. Usa el extractor genérico (sin
  `selectors` propios). Aporta ~7 items.
- **"IT - Star Comics (search)"** (`html`): `search_template`
  `https://www.starcomics.com/ricerca-fumetti?q={query}`, expandida por keyword
  (ver §5). Selectores:
  - `item_selector: div.fumetto-card`
  - `title_selector: .card-body`

**Detalle clave del selector `.card-body`** (la razón de no usar
`h4.card-title`): en `ricerca-fumetti`, `h4.card-title` trae **solo el nombre de
la serie**, sin la sub-edizione. El `.card-body` captura el bloque completo
`"<SERIE> n. <N>\n<EDIZIONE>\n<DATE>"` — la sub-edizione (Celebration, Variant
Cover, Anniversary, etc.) vive en un `span` hermano dentro del `.card-body`. Sin
esto, todas las variantes de un mismo número quedarían con título idéntico y se
perdería la edición.

- **Estructura de URLs**: producto y listado bajo `starcomics.com`; la búsqueda
  es `ricerca-fumetti?q=<keyword url-encoded>`.
- **Calidad de imágenes**: Star Comics sirve "otros volúmenes" en un
  **subdirectorio del folder de la cover** — relevante para el filtro multi-imagen
  (#31): la comparación de directorio padre es **exacta, no substring**, para no
  arrastrar covers de otros tomos a la galería del producto.

---

## 5. Proceso de ingestión — técnico

Ambas entradas se scrapean en **FASE 1** del pipeline canónico
(`manga_watch.py --workers 8`, dentro de `scrape_delta.sh` / `scrape_full.sh`)
vía el **extractor genérico** del YAML. **No tiene parser propio.**

- **"IT - Star Comics (search)"** lleva `search_template` + `keywords`, así que
  `_expand_search_template()` en `manga_watch.py` la expande en **N fuentes
  virtuales**, una por keyword. Cada hija recibe:
  - `name`: `"IT - Star Comics (search) [search: <keyword>]"`
  - `url`: el template con `q=<keyword url-encoded>`
  - `tags`: los del padre + `["expansion", "search:<keyword>"]`
  - El `source_purity` del padre **se propaga** a las hijas (#7).
- **Keywords activas** (probadas a mano; las que daban 0 resultados —`edizione
  limitata/speciale`, `esclusiva`, `metal edition`, `prima tiratura`, `final
  edition`— se eliminaron): `deluxe`, `cofanetto`, `variant`, `variant cover`,
  `variant cover edition`, `celebration edition`, `anniversary edition`,
  `tribute variant`, `tribute cover`, `tiratura limitata`, `collector`,
  `anime comics pack`.
- Distribución real por keyword en el corpus: `variant cover` (40),
  `collector` (12), `variant` (7), `celebration edition` (6),
  `anniversary edition` (5), `cofanetto` (3), `deluxe` (3); más ~7 del listado
  "IT - Star Comics Manga".
- Después de FASE 1 corren los retrofits de cleanup (rescore → filtros →
  clean_titles → backfill imágenes) como en cualquier fuente del YAML.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#7**: `source_purity` se propaga a las hijas search-template vía
  `_expand_search_template()`. ✅
- **#31**: multi-imagen — Star Comics sirve "otros volúmenes" en un subdirectorio
  del folder de la cover; el filtro descarta gallery por **directorio padre
  EXACTO** (no substring), si no se contaminaría la galería con otros tomos. ✅
- **Selector `.card-body` en vez de `h4.card-title`** — el `h4` solo trae la
  serie; la sub-edizione está en un `span` hermano. Sin `.card-body` se perdían
  las variantes. ✅
- **Keywords con 0 resultados eliminadas** — `edizione limitata/speciale`,
  `esclusiva`, `metal edition`, `prima tiratura`, `final edition`. Re-verificar
  caso por caso si se quieren re-añadir tras nuevos lanzamientos.

---

## 9. Pendientes / limitaciones conocidas

- **"IT - Star Comics Home"** (`https://www.starcomics.com/`,
  `item_selector: div.fumetto-card`, `title_selector: "h3, h4, a, .card-title"`)
  está **`enabled: false`** (audit 2026-05-25: 0 items). Es la home de noticias;
  no aporta productos. Queda en el YAML como referencia, fuera del pipeline.
- Re-validar las keywords periódicamente: `ricerca-fumetti` devuelve 0 para
  varias frases que antes sí daban resultados; la lista activa es la que rinde
  hoy, no una garantía a futuro.

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (deja items.jsonl en raw):
.venv/bin/python scripts/manga_watch.py --only-source "IT - Star Comics Manga"
.venv/bin/python scripts/manga_watch.py --only-source "IT - Star Comics (search)"

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "starcomics.com"
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

**Antes de cerrar cualquier cambio en esta fuente**: validar
(`validate_corpus`, 0 duras) → tests (`pytest tests/test_extraction.py`) → build.
Si tocaste algo meaningful, actualiza esta ficha.
