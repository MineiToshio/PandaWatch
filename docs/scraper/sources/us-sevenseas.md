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
- **Curación LLM non-manga 2026-08-23 (gotcha #147)**: 1 item flageado y
  conservado (Case File Compendium novela vol.10 Special Edition, danmei).


## Revisión de ingestión — 2026-09-24

Endpoint WP books devuelve 403 Cloudflare en verificación viva. Fallos agotados se reportan WIKI-ISSUE, no como catálogo vacío exitoso. Un HTTP 400 solo es fin de paginación si code=rest_post_invalid_page_number. Bloqueo externo vigente.

Evidencia y alcance: [auditoría integral](../audits/2026-09-24-ingestion.md).

### Continuación de auditoría — 2026-09-24

El delta consulta `modified_after` y ordena por `modified`, para incluir cambios en entradas antiguas. Llegar al límite de páginas produce incidencia. El endpoint continúa bajo challenge 403 en requests y Chromium, también mediante rest_route; la integración remota de modified_after queda pendiente de acceso. El contrato local de paginación está probado.

Contrato `modified_after` confirmado en la [referencia oficial WordPress](https://developer.wordpress.org/rest-api/reference/posts/).

### Verificación con navegador normal — 2026-09-24

El navegador integrado carga `/series/` tras la comprobación automática del
sitio. La navegación directa al endpoint JSON fue rechazada por el cliente;
el scraper automatizado continúa bloqueado. El índice HTML accesible confirma
que el sitio sigue activo, pero no demuestra recuperación de la ingestión API.

### Delta 2026-09-25 — bloqueo Cloudflare confirmado (2º día)

El endpoint `/wp-json/wp/v2/books` volvió a responder challenge de Cloudflare en
los **3 intentos** (`[WIKI-ISSUE] challenge=cloudflare`), con `partial books=0` y
**0 candidatos**. Es la continuación directa del bloqueo anotado el 2026-09-24,
ya no un incidente aislado: dos corridas consecutivas con el mismo modo de fallo.

Novedad operativa: gracias al mecanismo `wikis/health.report_issue` +
`return 1 if session._ingestion_issues else 0` (`scripts/manga_watch.py:9886`),
el paso ahora sale **rc=1** en vez de reportar un catálogo vacío como éxito. El
fallo es RUIDOSO, que es el comportamiento deseado — pero implica que el conteo
de "pasos en error" del run diario ya NO es comparable con los runs previos al
2026-09-24.

**Sin acción aplicada.** El bloqueo es externo; recuperarlo exige una vía distinta
(navegador con challenge resuelto, o un endpoint alternativo). Decisión del owner.

## Auditoría estratégica — 2026-09-25

Parser directo retirado de full/delta administrados mediante ingestion_policy.yml tras repetir 403 en /series/ y API pública. PRH /seven-seas/ añade descubrimiento oficial viable; no garantiza recuperar todo el histórico. Se conservan productos y referencias existentes. Ejecución manual del parser sigue disponible para diagnóstico.
