# Fuente: Manga México

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Manga México |
| **URL base** | `https://mangamexico.blogspot.com` |
| **Índice / punto de entrada** | Páginas de catálogo por editorial (ver §2): `/2015/10/mangas-de-panini-comics.html`, `/2015/10/mangas-de-editorial-kamite.html`, `/2015/10/mangas-de-editorial-vid.html` |
| **Tipo de fuente** | Catálogo comunitario (wiki en Blogger), no es tienda |
| **`kind` en sources.yml** | `html` (la fila es puntero; la ingestión real es `wiki` — ver abajo) |
| **`source_class`** | `trusted_media` |
| **País(es)** | México (`México`) — fuente mono-país |
| **Idioma(s)** | ES (español) |
| **Cobertura** | Manga publicado en México por Panini México, Editorial Kamite y Editorial Vid; un `<li>` por obra con volúmenes, estado y periodicidad |
| **Aporte al corpus** | ~17 items |
| **Parser / módulo** | `scripts/wikis/manga_mexico.py` (entrada puntero en `sources.yml`) |

**Editoriales que abarca** (del corpus real; `publisher` = editorial, no la tienda, #44):

Panini México (≈16) · "Varias editoriales" (1).

> El parser cubre tres editoriales (Panini México, Editorial Kamite, Editorial
> Vid), pero por defecto el pipeline corre sólo `panini` y `kamite` (ver §4); el
> aporte neto al corpus hoy es casi todo Panini México. {{pendiente: confirmar
> por qué Kamite/Vid aportan ~0 items netos — posible solape con otras fuentes o
> score bajo el umbral.}}

**Por qué importa / qué aporta de único**: es una de las pocas fuentes de
**catálogo del mercado mexicano** con metadata estructurada por obra (volúmenes
editados vs. abiertos en JP, estado, periodicidad). Aporta
descubrimiento de obras publicadas en México que no aparecen en fuentes ES/EU.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: el catálogo NO es por fecha (no hay
  calendario como listadomanga). Son **páginas estáticas de Blogger**, una por
  editorial, con URLs canónicas fijas (las 3 de arriba, en `CATALOG_URLS`).
- **Estructura del HTML**: dentro de `<div class="post-body">` (fallback a
  `<article>` o al documento) hay una `<ul>` con un `<li>` por obra. Cada `<li>`
  es **texto plano con metadata embebida**, ej.:
  `Akatsuki no Yona (3 en 1) - Volúmenes: 8/15+ ( Publicándose ) | Bimestral (Próx. en julio) | Precio actual: 349 MXN`.
  El parser separa título y metadata por ` - ` / ` – ` / ` — ` (`_split_title`) y
  extrae por regex: volúmenes (`Volúmenes: X/Y[+]`, donde `+` = sigue abierta en
  JP), tomo único, estado (`Publicándose`/`Finalizado`/`Anunciado`/`Pausado`/
  `Licenciado`), periodicidad, `Próx. en <mes>` y `Precio actual: X MXN`.
- **Identificador de producto**: si el `<li>` trae `<a href>`, se usa esa URL;
  si no (caso normal), se **fabrica una URL sintética por query param**
  `…?manga=<editorial>-<slug-del-título>` (#27). Es deliberado: usar fragment
  colapsaría todo el catálogo a un solo item porque `normalize_url_for_dedup`
  descarta fragments.
- **Anti-bot / quirks**: Blogger sirve HTML estático, sin Cloudflare ni
  JS-render conocido. La encoding se fuerza a `apparent_encoding`/utf-8 en
  `fetch_catalog`. La wiki a veces **repite títulos** dentro de la misma página →
  el parser dedupea por título lower-case (`seen_titles`).
- **Calidad de imágenes**: no aplica — los `<li>` no traen portada; estos items
  son de **referencia/descubrimiento** (sin imagen de tienda ni URL de compra).

---

## 3. Proceso de ingestión — vista de producto

1. Para cada editorial habilitada, **abrir su página de catálogo** (Panini,
   Kamite, Vid).
2. **Tomar cada `<li>`** de la lista de obras.
3. Separar **título** y **metadata**; extraer volúmenes, estado, periodicidad.
   Saltar líneas vacías, demasiado cortas (`< 4` chars) o con título
   fuera de rango (`< 2` o `> 200` chars), y duplicados dentro de la página.
4. Pasar el candidate por `is_likely_manga()` (rescata art books / packs,
   descarta merch); puntuar con `score_candidate()`.
5. Conservar sólo los que superan `--min-score` (20 en el pipeline).
6. **Repetir** con la siguiente editorial.

**Reglas de producto que nunca se rompen:** país = México (es el de la
editorial, no de una tienda, #46). Estos
items son de **referencia** (sin URL de compra) y eso es válido — el objetivo es
descubrimiento, no siempre compra.

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

FULL y DELTA corren **igual** (la fuente no tiene noción de "reciente"): el
catálogo es estático y se reparsea completo cada vez.

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script / flag | `scrape_full.sh` paso `[2d]` · `--bootstrap-wiki manga-mexico --sleep-seconds 0.5 --min-score 20` | `scrape_delta.sh` paso `[2d]` · idénticos flags |
| Discovery | reparsea las páginas de catálogo de las editoriales habilitadas | igual |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Cuándo | refresh completo | novedades recientes |

- Editoriales recorridas por defecto en `bootstrap()`: `("panini", "kamite")`.
  Editorial Vid existe en `CATALOG_URLS` pero NO está en el default.
- `iter_year_months()` devuelve una lista trivial (1 entrada por editorial); sólo
  existe para conformar la interfaz del dispatcher `_run_wiki_bootstrap` (la
  fuente no tiene semántica de mes/año).

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/manga_mexico.py`](../../../scripts/wikis/manga_mexico.py).

### 5.1 Entrada en sources.yml vs. ingestión real (MISMA fuente)

- La fila `MX - Manga México (catálogo wiki)` en `sources.yml` (`kind: html`,
  `publisher: "Varias editoriales"`, `source_class: trusted_media`) es un
  **puntero documental**. El scraper genérico de YAML NO la procesa de forma
  útil: la ingestión real pasa por **`--bootstrap-wiki manga-mexico`**, que
  invoca este módulo.
- El módulo construye un `Source` **sintético por editorial** (`_virtual_source`)
  con `kind: "wiki"`, `publisher` específico (Panini México / Editorial Kamite /
  Editorial Vid) y tags `["wiki","manga-mexico","mexico-<slug>","catalog"]`. Por
  eso el `publisher` que llega al corpus es la editorial concreta, no "Varias
  editoriales".

### 5.2 Qué captura el parser

- `parse_catalog_page(html_text, source_url, publisher_slug)` → un `Candidate`
  por `<li>` que pase los filtros. Le setea `publisher` y `tags`
  (`status:…`, `volumes:…`, `periodicity:…`, `next_month:…`); la `description` es
  el texto completo del `<li>` (también alimenta el scoring por señales).
- `fetch_catalog(slug, session)` baja una página de editorial y delega en
  `parse_catalog_page`.
- `bootstrap(...)` recorre las editoriales (default `panini`+`kamite`), filtra
  por `min_score`, hace `flush_fn` por lote y respeta `sleep_seconds`.

### 5.3 Flujo end-to-end

- Entra en la **FASE 2 (wiki bootstraps)** de ambos scripts canónicos, paso
  `[2d] manga-mexico`, con timeout de 300 s. Después le aplican los retrofits de
  cleanup de la FASE 3 (rescore → filtros → clean_titles → backfill metadata)
  como a cualquier item.

> ⚠️ Tras un scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr
> `/watch-standardize-catalog` automáticamente — lo decide el owner.

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural, aplica a TODO el corpus
  (sin red).
- **Smoke test del parser** (sin tocar items.jsonl): correr el módulo
  directamente (ver §10) y revisar que emita los `<li>` con título y metadata.
- No tiene enforcer ni retrofits dedicados (a diferencia de listadomanga), así
  que no hay prueba de idempotencia propia.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#27 (URLs sintéticas por query param, no fragment)**: la wiki no da URL por
  obra; el parser fabrica `?manga=<editorial>-<slug>`. Usar fragment colapsaría
  todo el catálogo a un solo item. ✅ resuelto por diseño.
- **Títulos repetidos en la misma página**: la wiki a veces duplica filas → dedup
  por título lower-case (`seen_titles`). ✅
- **Encoding**: se fuerza `apparent_encoding`/utf-8 en `fetch_catalog` para evitar
  texto mal decodificado. ✅
- **Decisiones (lo que NO se hace)**: estos items son de **referencia** (sin URL
  de compra ni portada) y se aceptan igual — no son filtrados upstream por no ser
  e-commerce.

---

## 9. Pendientes / limitaciones conocidas

- **Aporte bajo / solape**: el corpus tiene sólo ~17 items y casi todos Panini
  México; Kamite/Vid aportan ~0 netos. {{pendiente: confirmar si es solape con
  otras fuentes MX, score bajo el umbral, o cambio de estructura de la página.}}
- **Editorial Vid fuera del default**: existe en `CATALOG_URLS` pero `bootstrap()`
  sólo corre `panini`+`kamite`. {{pendiente: decidir si vale habilitar Vid.}}
- **Sin imágenes**: los items no traen portada (catálogo de texto). Quedan
  marcados como de baja calidad de imagen / sin imagen.
- **Páginas con fecha fija en la URL** (`/2015/10/…`): si la wiki migra esas URLs
  canónicas, el parser deja de traer items en silencio (devuelve `[]` ante
  cualquier excepción de red). {{pendiente: añadir alerta si una editorial
  devuelve 0 items.}}

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (deja raw, sin standardize):
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki manga-mexico \
    --sleep-seconds 0.5 --min-score 20

# Smoke test del parser (una editorial, sin tocar items.jsonl):
.venv/bin/python scripts/wikis/manga_mexico.py --publisher panini --min-score 10

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "mangamexico"
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

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`,
0 duras) → tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo
meaningful, actualiza esta ficha.
