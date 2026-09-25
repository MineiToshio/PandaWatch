# Fuente: MangaLine España

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-08-23. **DESHABILITADA en `sources.yml` desde
> 2026-08-23** (host caído, ver §8/§9) — la editorial sigue activa.

> Es una fuente **simple** del YAML (entrada en `sources.yml`, extractor genérico).
> Sólo lleva §1, §2, §5 (básico), §8/§9 si aplica y §10.

> **Nota — sitio distinto de MangaLine México.** `mangaline.es` (esta ficha,
> España) y `mangaline.com.mx` (México) comparten el MISMO theme WooCommerce
> custom, pero son **sitios, países y editoriales distintos**. No los mezcles:
> son dos entradas separadas en `sources.yml`. La de México se documenta aparte.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | MangaLine España |
| **URL base** | `https://mangaline.es` |
| **Índice / punto de entrada** | `https://mangaline.es/shop/` |
| **Tipo de fuente** | Editorial / tienda oficial (`source_class: official`) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | España (`es`) — fuente mono-país |
| **Idioma** | Español |
| **Cobertura** | Catálogo propio de MangaLine España: preventas y ediciones integrales con extras |
| **Aporte al corpus** | ~4 items (al último conteo) |
| **Parser / módulo** | Entrada en `sources.yml` (extractor genérico, sin parser propio) |

**Editoriales que abarca** (del corpus real, ver snippet §10): MangaLine España
y MangaLine Ediciones — es su propio catálogo de editorial. El `publisher` en el
YAML es `MangaLine España` (#44: publisher = editorial real, no la tienda).

**Por qué importa / qué aporta de único**: tienda oficial de la editorial
MangaLine en España. Aporta **preventas** y **ediciones integrales con extras**
de su catálogo propio — series como Grey, Silent Möbius, Dark Angel y UFO Robot
Grendizer (preventa Goldorak) — que no necesariamente aparecen en otras fuentes.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda WooCommerce. Índice en `/shop/` con
  paginación (`max_pages: 10`); cada producto vive en `/product/<slug>/`.
- **Estructura del HTML**: tema WooCommerce **custom** (mismo theme que MangaLine
  México). Los productos del listado son `li.product`; el título está en
  `h3.product-title` — **NO** el `h2` estándar de WooCommerce. Las tarjetas de
  categoría del listado son `li.product.product-category` y se excluyen.
- **Identificador de producto**: URL canónica del producto (`/product/<slug>/`).
- **Pureza**: `manga_only` — es el catálogo propio de la editorial, sin mezcla de
  comics/coleccionables. (La entrada del YAML no declara `purity` explícito; se
  trata como mono-editorial de manga.)

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: `ES - MangaLine España` (`kind: html`,
  `url: https://mangaline.es/shop/`). Se scrapea en **FASE 1** del pipeline junto
  con el resto de fuentes del YAML (`manga_watch.py --workers 8`), vía el
  **extractor genérico** (no hay parser propio).
- **Selectores**:
  - `item_selector: li.product:not(.product-category)` — toma cada producto del
    listado y **excluye las tarjetas de categoría** (`li.product-category`), que
    de otro modo entrarían como falsos productos.
  - `title_selector: h3.product-title` — el título va en `h3`, no en el `h2`
    estándar de WooCommerce (de ahí el selector explícito).
- **Paginación**: `max_pages: 10`.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Título en `h3.product-title`, no `h2`**: el theme custom de MangaLine no usa
  el markup estándar de WooCommerce → se fija `title_selector: h3.product-title`.
- **Tarjetas de categoría como falsos productos**: el listado mezcla `li.product`
  reales con `li.product.product-category` (cards de categoría) → el
  `:not(.product-category)` las descarta.
- **Outage total 2026-07-07** (primer delta real post-mejoras): `mangaline.es`
  respondió `ConnectTimeoutError` (connect timeout=10s) — el mismo síntoma que
  MangaLine México el mismo día. DNS resuelve (`217.76.149.251`), pero el host no
  responde en el puerto 443; el IP pertenece al hosting compartido **Arsys**
  (`arsys.es`, confirmado por whois — `NET-ARSYS-EURO-10`). El sitio SÍ funcionaba
  en el run del 2026-06-12 (88 candidatos, 8 páginas), así que es probable que sea
  un problema **transitorio de hosting**, no un cambio permanente del sitio.
  Monitorear el próximo run: si persiste, escalar a contacto directo con la
  editorial en vez de reintentos automáticos (un timeout de conexión no es un
  429/403 — reintentar no ayuda si el host está caído).
- **Outage SIGUE 2026-08-22** (delta `logs/scrape-delta-2026-08-22-174458/`): mismo
  `ConnectTimeoutError`. Verificado en vivo con curl (mismo user-agent del scraper,
  puerto 80 Y 443, `shop/` y raíz `/`): timeout de conexión en ambos puertos, DNS
  sigue resolviendo (`217.76.149.251`, sin cambios). **Van 2 runs con más de un mes
  de diferencia (2026-07-07 → 2026-08-22) con el host inalcanzable**, igual que
  MangaLine México (mismo hosting Arsys) — ya no es razonable seguir llamándolo
  "transitorio"; escala a **host caído / posible cese del sitio**. No se reintentó
  el scrape (host caído, no recuperable con un retry). Revisar manualmente en
  navegador antes del próximo delta; si sigue caído, evaluar `enabled: false` en
  `sources.yml` para ambas MangaLine (ES + MX) en vez de seguir intentando en vano.
- **DESHABILITADA 2026-08-23**: re-verificado con `curl -sI` (mismo user-agent,
  puertos 80/443, timeout corto) — `mangaline.es` sigue sin responder
  (`ConnectTimeoutError`, exit 28), tercera confirmación tras 2026-07-07 y
  2026-08-22 (~6 semanas de host inalcanzable). Se puso `enabled: false` en
  `sources.yml` con comentario fechado. **La editorial NO cerró**: bajo nueva
  dirección (Rafael, al frente de MangaLine España y Locura MangaLine desde
  inicios de 2026 tras ~3 años en la estructura interna) están relanzando con
  periodicidad fija mensual, retomando reimpresiones de catálogo y anunciando
  licencias nuevas (*Corrector Yui* de Kia Asamiya) — entrevista de julio 2026 en
  Ramen Para Dos. Es decir: el sitio propio está caído por un problema de hosting
  (Arsys) ajeno al estado del negocio, que sigue operando. Ojo: existe un cierre
  **histórico** de "Mangaline Ediciones" en 2011 (deudas, cierre tras completar
  Yugo/Coco/GTO) — es una editorial distinta/reboot, no confundir con el estado
  actual.

---

## 9. Pendientes / limitaciones conocidas

- **Aporte chico al corpus** (~4 items): catálogo pequeño y/o muchas preventas.
  Revisar tras un scrape grande si `max_pages` o los selectores dejan productos
  afuera.
- {{pendiente: confirmar calidad/resolución de las imágenes de portada de esta
  fuente — no verificado en esta ficha}}.
- **Cobertura tras deshabilitar (2026-08-23)**: de los 4 items del corpus con esta
  fuente, 3 quedan SOLO con MangaLine ES como sources[] (se perderían si el item
  se recorta por staleness) — Grey (Edición Integral), Angelic (Artbook), y Losers
  Limited Edition. El resto del catálogo España de MangaLine (Devilman, Silent
  Möbius, Grey variant) YA está cubierto independientemente por **ListadoManga
  (colecciones)**, que es agregador ES y ya trackea esas ediciones sin depender de
  este scrape directo — confirmado en el corpus real (`cluster_key` con fuente
  `ListadoManga (colecciones)` para esos títulos). Reactivar esta fuente si
  `mangaline.es` vuelve a responder; mientras tanto, ListadoManga es la cobertura
  de facto para novedades ES de esta editorial.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "ES - MangaLine España"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver items/editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "mangaline.es"
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
(`validate_corpus.py`, 0 duras) → tests (`pytest tests/test_extraction.py`) →
build. Si tocaste algo meaningful, actualiza esta ficha.
