# Fuente: Seven Seas Entertainment (US)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-12 (alta de la fuente).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | US - Seven Seas (ediciones especiales) |
| **URL base** | `https://sevenseasentertainment.com` |
| **Punto de entrada** | API WordPress: `/wp-json/wp/v2/books` (CPT `books`, ~6150 items) |
| **`kind`** | `wiki` (fuente sintética vía `--bootstrap-wiki sevenseas`; sin fila en sources.yml) |
| **`source_class`** | `official` |
| **País / idioma** | Estados Unidos / Inglés |
| **purity** | `manga_only` (manga, manhwa, light novels — todo japonés/asiático) |
| **Cobertura** | Deluxe hardcovers, box sets, collector's/special editions, artbooks, danmei deluxe |
| **Aporte estimado** | ~150-250 especiales (evaluación 2026-06-12); el mayor gap de EEUU (corpus US ≈ 340) |
| **Parser / módulo** | [`scripts/wikis/sevenseas.py`](../../../scripts/wikis/sevenseas.py) |

**Por qué importa**: editorial US top-3 con el catálogo más denso de deluxe/box sets
que NINGUNA fuente cubría sistemáticamente. PRH Comics solo lista su carrusel activo
distribuido por PRH (~14 items SS en el corpus antes de esta fuente); Otaku Calendar
captura releases sueltos.

---

## 2. Descripción técnica

- **Listing**: `GET /wp-json/wp/v2/books?per_page=100&page=N[&after=ISO8601]`.
  `X-WP-TotalPages` da la paginación (~62 páginas). El JSON trae `title.rendered`,
  `link`, `date`, `content.rendered` (descripción rica). NO trae ISBN/portada.
- **Detalle (2 requests por especial)**:
  - `GET /wp-json/wp/v2/media?parent=<id>` → portada (mayor resolución; preferencia
    por archivos `*coverFRONT*`). Algunos libros no tienen media → img vacía
    (la rellena backfill_metadata después).
  - `GET <link>` (HTML) → `<b>ISBN:</b>` / `<b>Release Date:</b>` ("February 17,
    2026" → ISO). El precio NO se captura (decisión 2026-06-11).
- **Anti-bot**: 403 a clients sin pinta de browser; con User-Agent de Chrome
  (`_HEADERS` del módulo) responde 200 estable. Sin Cloudflare challenge.
- **Filtro de especiales** (`is_special_title`): deluxe / box set / collector /
  special edition / hardcover / artbook / anniversary en el TÍTULO. Exclusiones:
  - `omnibus` a secas NO califica (gotcha #18 — 2-en-1 rústica; los omnibus
    premium entran por deluxe/hardcover).
  - `[Mature Hardcover]` sin otro qualifier = variante sin censura del tomo
    regular, NO coleccionable (hallazgo de la evaluación).

---

## 4. Discovery: FULL vs DELTA

| | FULL | DELTA |
|---|---|---|
| Script | `scrape_full.sh` paso **2x** | `scrape_delta.sh` paso **2p** |
| Invocación | `--bootstrap-wiki sevenseas --wiki-from 2000-01` (⚠️ OBLIGATORIO: sin `--wiki-from` el dispatcher defaultea a 2024-01 → solo ~2245 de 6153 books) | `--wiki-from $LISTADO_CAL_FROM` (3 meses) |
| Mecanismo | catálogo completo (~62 páginas API) | `after=` del API (posts nuevos = anuncios nuevos) |
| Costo | ~62 reqs listing + 2×N detalle (~10-15 min) | 2-3 págs + pocos detalles (~1 min) |

⚠️ El dispatcher **fuerza `fetch_details=True`** para esta wiki (como animeclick):
sin el enrich, los items quedan sin ISBN (el valor de dedup de la fuente).

---

## 7. Validación

```bash
.venv/bin/python scripts/wikis/sevenseas.py --wiki-from 2026-04   # standalone, sin escribir
.venv/bin/python -m pytest tests/test_sevenseas.py -q              # 5 tests del parser
# tras un bootstrap real: repair estándar + validate_corpus (0 duras)
```

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **403 de WebFetch/bots simples**: es solo por headers — User-Agent de Chrome lo
  resuelve; sin challenge. ✅
- **El API no expone ISBN/portada** (ACF vacío, featured_media=0): se resuelve con
  `media?parent` + regex sobre el HTML del libro (`<b>ISBN:</b>` estructurado). ✅
- **Primer run llegó sin ISBN/fecha**: el dispatcher pasaba `fetch_details=False`
  (flag de CLI pensado para el source loop). Fix: el dispatcher fuerza
  `fetch_details=True` para sevenseas. ✅
- **"(Omnibus)" a secas contaminaba** (score 45, el gate los expulsa después):
  se removió del filtro de título — ahorra ~50% de fetches de detalle. ✅
- **"Catálogo completo" devolvía siempre 2245 books**: NO era la paginación — el
  dispatcher de `--bootstrap-wiki` defaultea `wiki_from` a **2024-01** cuando no se
  pasa el flag → `after=2024-01-01` filtraba a los posts desde 2024. El modo full
  DEBE invocarse con `--wiki-from 2000-01` (igual que los presets full de PRH/VIZ).
  De paso, `fetch_books` ganó reintentos con backoff (3×) y header TotalPages
  sticky — robustez real ante WAF/caché. ✅
- **Autor casi siempre vacío**: el staff del detail usa markup variado (links,
  strong con/sin dos puntos); el regex captura solo el formato `<strong>Story…`
  — mejorable, no bloqueante (author es opcional en el corpus).
- **Decisión**: items "Mature Hardcover" se excluyen DE ENTRADA (no son
  coleccionables); las light novels deluxe (Mo Dao Zu Shi, Little Mushroom) SÍ
  entran (LN con formato premium es producto del proyecto).
