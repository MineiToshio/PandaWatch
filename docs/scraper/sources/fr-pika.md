# Fuente: Pika Édition (Francia)

> ⚠️ **PODA 2026-06-12 (poda de fuentes muertas)** — `FR - Pika Planning`: Planning deshabilitada (2 items, 0 únicos). Pika Édition y Pika Livres/Artbooks siguen activas.
> Registro completo: [descartadas/README.md](descartadas/README.md).

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

> ⚠️ **No confundir**: esta es **Pika Édition** (Francia, `pika.fr`), el editor francés
> de manga. Es DISTINTA de **Pika Ediciones** (España, `hablamosdelibros.es`), que es
> otra fuente y otra ficha.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Pika Édition (Francia) |
| **URL base** | `https://www.pika.fr/` |
| **Índice / punto de entrada** | Tres entradas del YAML sobre el mismo sitio: home (`/`), planning de salidas (`/planning-sorties/`) y libros/artbooks (`/livres-pika/`) |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | Francia (`Francia`) — fuente mono-país |
| **Idioma** | Francés |
| **Cobertura** | Catálogo del editor francés de manga Pika Édition (novedades, planning de salidas, libros y artbooks) |
| **Aporte al corpus** | ~8 items (todos `country=Francia`, `publisher=Pika Édition`) |
| **Parser / módulo** | Sin módulo propio — tres entradas en `sources.yml`, extractor genérico HTML |

**Por qué importa**: aporta el catálogo oficial de un editor francés relevante de manga,
con su planning de salidas y su sección de libros/artbooks. Cubre el mercado francés (FR)
desde la fuente de primera mano.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs**: tres páginas de listado sobre `pika.fr` que se scrapean tal cual
  (home, `/planning-sorties/`, `/livres-pika/`). No hay paginación ni sitemap propio
  configurado; cada entrada del YAML scrapea su URL como índice.
- **Selectores**: **ninguno** en las entradas del YAML → se usa **auto-detección** del
  extractor genérico HTML (sin selectores propios).
- **Identificador de producto**: URL del producto / URL sintética del extractor genérico.
- **Anti-bot / quirks**: **#1 mojibake FR** — Pika (igual que Glénat) devuelve UTF-8
  decodificado como cp1252; lo repara `clean_title()::_fix_mojibake()` PRIMERO (no metas
  regex-cleaning antes).
- **Calidad de imágenes**: {{pendiente: no verificada — el corpus actual es pequeño (8 items)}}.

---

## 5. Proceso de ingestión — técnico

- **Entradas en `sources.yml`** (tres, mismo sitio `pika.fr`, todas `enabled: true`):
  `FR - Pika Édition` (`/`), `FR - Pika Planning` (`/planning-sorties/`) y
  `FR - Pika Livres / Artbooks` (`/livres-pika/`).
- Se scrapean en la **FASE 1** del pipeline (sources del YAML vía `manga_watch.py`), con el
  **extractor genérico HTML** (sin parser propio ni selectores → auto-detección).
- Luego pasan por los retrofits de cleanup estándar de la FASE 3 (rescore, filtros,
  clean_titles —donde se repara el mojibake #1—, etc.). No hay reglas de agrupación
  dedicadas para esta fuente.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Fechas DD/MM/YYYY crudas en `release_date`** — la ficha técnica del sitio entrega la fecha día-primero y los extractores la guardaban sin normalizar; desde 2026-06-12 `normalize_release_date()` la convierte a ISO en la ingestión y el corpus legacy se reparó con `normalize_release_dates.py` (gotcha #80). ✅
- **#1 mojibake FR** — Pika devuelve UTF-8 leído como cp1252 (acentos rotos). ✅ Reparado
  por `_fix_mojibake()` en `clean_title()` (corre PRIMERO; no anteponer otro regex).

---

## 9. Pendientes / limitaciones conocidas

- **`FR - Pika (search)` está deshabilitada** (`enabled: false`): el endpoint `?s={query}`
  devuelve la home en vez de resultados (búsqueda **JS-only**). Por eso se usan las páginas
  canónicas Livres/Artbooks/Planning en su lugar. Verbatim del YAML:
  *"?s= devuelve la home, no resultados. Búsqueda JS-only. Usar canónicas Livres/Artbooks."*
- **Aporte chico** (~8 items): {{pendiente: confirmar si las tres páginas de listado
  cubren bien el catálogo o si gran parte queda detrás de la búsqueda JS-only}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (una de las tres entradas del YAML):
.venv/bin/python scripts/manga_watch.py --only-source "FR - Pika Édition"
.venv/bin/python scripts/manga_watch.py --only-source "FR - Pika Planning"
.venv/bin/python scripts/manga_watch.py --only-source "FR - Pika Livres / Artbooks"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "pika.fr"
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
