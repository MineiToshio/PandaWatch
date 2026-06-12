# Fuente: Meian

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-12.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Meian |
| **URL base** | `https://www.meian-editions.fr` |
| **Índice / punto de entrada** | `https://www.meian-editions.fr/meian/accueil-meian` |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `js` (requiere render con Playwright) |
| **`source_class`** | `official` |
| **País(es)** | Francia (`Francia`) — el país va al edition_key |
| **Idioma(s)** | FR (francés) |
| **Cobertura** | Catálogo de la editorial francesa Meian (manga publicado en Francia) |
| **Aporte al corpus** | ~16 items, todos `publisher=Meian` / `country=Francia` |
| **Parser / módulo** | Entrada en `sources.yml` (`FR - Meian`); sin parser propio |

**Por qué importa / qué aporta de único**: cubre el catálogo oficial de **Meian**, una
editorial francesa de manga, aportando ediciones del mercado francés (FR) que no
aparecen en las fuentes españolas/japonesas.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: índice en `meian-editions.fr/meian/accueil-meian`;
  páginas de producto del sitio de la editorial.
- **Identificador de producto**: URL canónica del producto en el dominio
  `meian-editions.fr`.
- **Anti-bot / quirks**: sitio **JS-rendered** (`kind: js`) → se renderiza con Playwright
  (#12). Posible **mojibake FR** (#1) por la codificación del HTML francés.
- **Calidad de imágenes**: {{pendiente: resolución real de las portadas de Meian}}.

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: bloque `FR - Meian` (`kind: js`, `source_class: official`,
  `country: Francia`, `publisher: Meian`). Se scrapea como una fuente simple del YAML.
- **FASE 1 del pipeline** (`scrape_full.sh` / `scrape_delta.sh`): la fuente entra en el
  paso de scrape de sources del YAML (`manga_watch.py --workers 8`). **No tiene parser
  propio** ni discovery dedicado.
- **Render JS (#12)**: por ser `kind: js`, las páginas se rinden con Playwright. Playwright
  sync NO es thread-safe → el render se serializa en el único thread `playwright-worker`
  vía `_PLAYWRIGHT_QUEUE`; los workers HTTP despachan a esa cola con
  `fetch_with_playwright()`. Requiere `--enable-js` (Playwright es opt-in).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#12 (JS/Playwright)**: el sitio es JS-rendered; el scrape exige `--enable-js` y el
  render se serializa en el worker dedicado. Sin Playwright la página no entrega productos.
- **#1 (mojibake FR)**: riesgo de codificación cp1252 sobre UTF-8 en HTML francés;
  `clean_title()::_fix_mojibake()` lo repara primero (no meter regex-cleaning antes).

---

## 9. Pendientes / limitaciones conocidas

- **Costo de Playwright**: al ser `kind: js`, cada fetch pasa por el worker serializado de
  Playwright (más lento y caro que HTML plano).
- **`FR - Meian Plus Boutique`** (`meian-plus.fr`, mismo `publisher: Meian`) está
  **`enabled: false`** (deshabilitada 2026-06-01: 0 items en corpus, fuente JS cara, sin
  yield). Queda fuera del pipeline; reactivar sólo si justifica el costo de Playwright.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente (requiere Playwright por ser kind: js):
.venv/bin/python scripts/manga_watch.py --only-source "FR - Meian" --enable-js

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "meian-editions"
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

### Verificación 2026-06-12 — falsa alarma del run de mayo

- El "0 candidatos / error" del run 2026-05-24 fue el fallo transitorio de greenlet
  (`Cannot switch to a different thread`) del worker Playwright compartido (gotcha #12)
  — NO un cambio del sitio. Verificado en vivo: 14 cards, 9 candidatos (coffrets
  intégrale: Madoka Magica, Lodoss, Higurashi Gô…), 5 tomos regulares bien skippeados.
  Regla: si Meian da 0 en un run full con muchas fuentes js, sospechar del worker
  Playwright antes que del sitio.
- **Hallazgo técnico**: el sitio es una SPA Angular que consume la API JSON
  `https://www.anime-store.fr/api-meian/v5/` (exige header `Referer:
  https://www.meian-editions.fr/`, si no → 403). Endpoints útiles:
  `/v5/produits/news/` (los ~14 recientes), `/v5/licences/?cat=0&q=` (catálogo
  completo, 161 series), `/v5/planning/` (lanzamientos futuros). Hoy Playwright
  resuelve todo; si algún día se quiere bajar el costo de JS o ampliar cobertura
  (la homepage solo muestra ~14 recientes), migrar a la API con ese Referer es el
  camino — sin Playwright.
- Selectores confirmados del DOM renderizado (no necesarios hoy, el método clusters
  funciona): item `div.swiper-news`, title `h3`, link `a[href*='/produit/']`.
