# Fuente: KADOKAWA (Japón)

> ⚠️ **PODA 2026-06-12 (poda de fuentes muertas)** — `JP - KADOKAWA Comics`: El catálogo Comics se deshabilitó (1 item compartido, 0 únicos); KADOKAWA Store y Store Artbooks/Fanbooks siguen activas.
> Registro completo: [descartadas/README.md](descartadas/README.md).

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | KADOKAWA (3 entradas en `sources.yml`) |
| **URL base** | `https://www.kadokawa.co.jp` · `https://store.kadokawa.co.jp` |
| **Tipo de fuente** | Editorial oficial (`source_class: official`) + su tienda oficial |
| **`kind` en sources.yml** | `html` (las 3) |
| **País** | Japón (`jp`) — fuente mono-país |
| **Idioma** | Japonés (CJK) |
| **`publisher`** | KADOKAWA (las 3) |
| **Aporte al corpus** | ~85 items (todos `country=Japón`, `publisher=KADOKAWA`) |
| **Parser / módulo** | Entradas en `sources.yml` — extractor genérico, sin parser propio |

Las **tres entradas** que cubre esta ficha (todas `official`, `html`, Japón, KADOKAWA):

| Nombre en `sources.yml` | URL | tags | Qué aporta |
|---|---|---|---|
| `JP - KADOKAWA Comics` | `https://www.kadokawa.co.jp/category/comic/` | manga, official, japan | Catálogo editorial de cómics/manga |
| `JP - KADOKAWA Store Artbooks Fanbooks` | `https://store.kadokawa.co.jp/shop/c/c109050/` | artbook, fanbook, official, japan | Tienda oficial, categoría de artbooks y fanbooks |
| `JP - KADOKAWA Store` | `https://store.kadokawa.co.jp/shop/` | store, bonus, official, japan | Tienda oficial general (ediciones con bonus de tienda) |

**Por qué importa / qué aporta de único**: es la **fuente oficial japonesa** de KADOKAWA.
Captura ediciones del mercado de origen (japonés) que no aparecen en fuentes occidentales:
artbooks y fanbooks (categoría dedicada en la tienda) y ediciones con **bonus de tienda
oficial**, además del catálogo editorial de manga.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**:
  - `kadokawa.co.jp/category/comic/` — listado editorial de la categoría cómic/manga.
  - `store.kadokawa.co.jp/shop/` — tienda oficial; `c/c109050/` es la categoría de
    artbooks/fanbooks dentro de la tienda.
- **Selectores**: ninguno definido en `sources.yml` para las 3 entradas → la captura va por
  **auto-detección del extractor genérico** (detección de producto/imagen por
  heurística, no por selectores propios).
- **Identificador de producto**: URL canónica de la página de producto de la tienda/catálogo.
- **Idioma / encoding**: contenido japonés (CJK). Si aparece mojibake mixto en JP, decodificar
  con `errors='replace'` (#28). Para signals sobre texto CJK, el matching es por substring,
  no por word-boundary ASCII (#9).

---

## 5. Proceso de ingestión — técnico

- **Fase**: las 3 entradas se scrapean en **FASE 1** del pipeline canónico
  (`manga_watch.py --workers 8`, dentro de `scrape_full.sh` / `scrape_delta.sh`), igual que
  cualquier fuente del YAML.
- **Sin parser propio**: usan el **extractor genérico** del pipeline (label/value +
  auto-detección). NO hay módulo dedicado en `scripts/wikis/` ni retrofit específico.
- **Sin selectores en el YAML** → la extracción de título/imagen es por heurística del
  extractor genérico.
- **Filtros estándar**: pasan por la cascada `is_likely_manga()` y los filtros del pipeline
  (`filter_non_manga`, `filter_collectible`) como toda fuente. Al ser `official` japonesa, el
  STRONG manga hint suele venir del contexto editorial KADOKAWA.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#28 (JP mojibake mixto)**: en fuentes japonesas el body puede traer bytes crudos que rompen
  `decode('utf-8', strict)`; el patrón es decodificar con `errors='replace'`. Aplica de forma
  preventiva si aparece texto roto desde KADOKAWA.
- **#9 (signals sobre CJK)**: los detectores de signals usan substring para CJK (no
  word-boundary ASCII). Tenerlo presente si se agrega cualquier detector que toque títulos
  japoneses.

---

## 9. Pendientes / limitaciones conocidas

- **Sin selectores propios**: la captura depende del extractor genérico; si KADOKAWA cambia su
  layout, la auto-detección puede degradarse sin aviso. No hay auditoría de red dedicada para
  esta fuente.
- **{{pendiente: anti-bot / JS-rendered}}** — no verificado si la tienda
  (`store.kadokawa.co.jp`) requiere JS (`--enable-js`, #12) o tiene anti-bot. Si el conteo de
  items cae a 0, revisar primero esto.
- **{{pendiente: calidad de imágenes}}** — no determinada (alta/baja resolución, de dónde sale
  la portada).

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo estas fuentes (ajustar el nombre exacto del YAML):
.venv/bin/python scripts/manga_watch.py --only-source "JP - KADOKAWA Comics"
.venv/bin/python scripts/manga_watch.py --only-source "JP - KADOKAWA Store Artbooks Fanbooks"
.venv/bin/python scripts/manga_watch.py --only-source "JP - KADOKAWA Store"

# Validar (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver items reales de KADOKAWA en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "kadokawa"
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

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0 duras) →
tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza esta
ficha.
