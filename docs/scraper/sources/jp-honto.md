# Fuente: Honto

> ⚠️ **PODA 2026-06-12 (poda de fuentes muertas)** — `JP - Honto (search)`: Deshabilitada: 9 búsquedas/run → 0 netos (resultados dominados por ebooks); Rakuten Books (search) cubre JP retail con 179 items.
> Registro completo: [descartadas/README.md](descartadas/README.md).

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Honto (`JP - Honto (search)`) |
| **URL base** | `https://honto.jp` |
| **Índice / punto de entrada** | búsqueda dirigida: `https://honto.jp/netstore/search.html?cidGnrNm=comic&srchTrm={query}` |
| **Tipo de fuente** | Tienda (retailer) — librería japonesa multi-editorial (Maruzen / Junkudo, 丸善ジュンク堂) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `retailer` |
| **País(es)** | Japón (`Japón`) — el país va al edition_key |
| **Idioma(s)** | Japonés (CJK) |
| **Cobertura** | Cómic japonés (`cidGnrNm=comic`) acotado a ediciones especiales por keyword |
| **Aporte al corpus** | 0 items hoy (snippet §10) |
| **Parser / módulo** | entrada en `sources.yml` (`JP - Honto (search)`); sin parser propio |

Honto es una **tienda multi-editorial**: el campo `publisher` NO es el editor real
del producto. El editor real lo completa el merge por ISBN o el skill de standardize
(#44).

**Por qué importa / qué aporta de único**: cubre el mercado japonés de ediciones
especiales físicas (限定版 / 特装版 / 初回限定 / box, artbooks 画集), buscando por
keywords japonesas en lugar de recorrer un catálogo completo. Aporta descubrimiento
de novedades premium JP que otras fuentes ES/EN no ven.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: búsqueda por query string
  `search.html?cidGnrNm=comic&srchTrm={query}`. `cidGnrNm=comic` fija el género cómic;
  `srchTrm` es la keyword (japonesa) url-encodeada.
- **Estructura del HTML**: lista de resultados; cada producto está en
  `div.stContents`. Título y link en `h2.stHeading a.dyTitle`. Datos/descripción en
  `ul.stData`.
  - `item_selector`: `div.stContents`
  - `title_selector`: `h2.stHeading a.dyTitle`
  - `link_selector`: `h2.stHeading a.dyTitle`
  - `description_selector`: `ul.stData`
- **Identificador de producto**: URL del producto (link en `a.dyTitle`). {{pendiente: confirmar si la URL trae un id/ISBN estable.}}
- **Anti-bot / quirks**: contenido japonés (CJK) — los signals usan substring CJK, no
  word-boundary ASCII (#9). {{pendiente: confirmar Cloudflare / JS-render / mojibake.}}
- **Calidad de imágenes**: {{pendiente: no determinado.}}

---

## 5. Proceso de ingestión — técnico

- Es una **fuente del YAML** que se scrapea en la **FASE 1** del pipeline
  (`manga_watch.py`, source loop), no en una fase de wiki. **No tiene parser propio**;
  la extracción la hacen los selectores de la entrada (`extract_*` genérico).
- La `search_template` + `keywords` se **expanden en fuentes virtuales**: una búsqueda
  por cada keyword japonesa (`_expand_search_template` en `manga_watch.py`). Cada
  expansión hereda los tags base + `expansion` + `search:<keyword>`, y su `url` es la
  plantilla con la keyword url-encodeada.
- **Keywords (verbatim)**: 限定版 · 特装版 · 初回限定 · 数量限定 · 完全受注生産 ·
  特典付き · グッズ付き · 画集 · イラスト集.
- Idioma japonés (CJK): el matcheo de signals usa substring para CJK (#9); el editor
  real lo resuelve el merge por ISBN / standardize, no el campo `publisher` de la
  tienda (#44).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#44: tienda multi-editorial con `publisher` seteado** — la entrada trae
  `publisher: "Honto / 丸善ジュンク堂"`, que es la tienda, no el editor real. Por #44
  las fuentes retailer multi-editorial NO deberían llevar `publisher` (mejor `""`: el
  merge por ISBN o el skill completan el editor real). {{pendiente: evaluar si remover
  el `publisher` de esta entrada, como se hizo con Rakuten Books / Kinokuniya / Sanyodo.}}

---

## 9. Pendientes / limitaciones conocidas

- **Aporte 0 al corpus hoy**: el snippet de §10 no encuentra items de `honto.jp`. Puede
  ser que la búsqueda no devuelva resultados que pasen los filtros, que los selectores
  estén desactualizados, o que no se haya scrapeado recientemente. {{pendiente:
  verificar con un scrape dirigido si la fuente realmente captura algo.}}
- **`publisher` de tienda** seteado contra la convención #44 (ver §8). {{pendiente.}}
- Quirks técnicos (anti-bot, calidad de imagen, id de producto) **sin confirmar**
  (ver §2).

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente (todas sus expansiones por keyword):
.venv/bin/python scripts/manga_watch.py --only-source "JP - Honto (search)"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver items/editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "honto.jp"
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
