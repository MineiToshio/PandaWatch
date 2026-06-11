# Fuente: Manga-Passion

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Manga-Passion |
| **URL base** | `https://www.manga-passion.de` |
| **API / punto de entrada** | `https://api.manga-passion.de/volumes` (REST JSON-LD / Hydra, pública, sin auth) |
| **Tipo de fuente** | Catálogo comunitario / base de datos del mercado DACH (no es tienda) |
| **`kind` en sources.yml** | `wiki` (módulo propio; no tiene entrada en `sources.yml`) |
| **`source_class`** | `trusted_catalog` |
| **País** | Alemania (`Alemania`) — fuente mono-país |
| **Idioma** | Alemán (Deutsch) |
| **Cobertura** | Ediciones especiales alemanas: Sonderausgaben (Limited / Collector / Premium / Box) + Variant-Covers de tomos regulares |
| **Aporte al corpus** | ~791 items |
| **Parser / módulo** | `scripts/wikis/mangapassion.py` |

**Editoriales que abarca** (entre paréntesis, volumen aproximado de items en el corpus):

altraverse (≈161) · TOKYOPOP (≈132) · Dokico (≈121) · Carlsen Manga! (≈80) · KAZÉ Manga
(≈76) · Manga Cult (≈37) · Egmont Manga (≈35) · Panini Manga (≈27) · papertoons (≈21) ·
Manlin Verlag (≈19) · Yurico (≈18) · MANGAMOON (≈12) · Yomeru (≈10) · C LINES · dani books
· Hayabusa · B-Love Manga · CROCU · Hornico · Manhwa Cult, entre otras.

Recuerda: `publisher` = editorial real (la del campo `edition.publishers` de la API), NO
la tienda (#44).

**Por qué importa / qué aporta de único**: es el catálogo de referencia más completo del
**mercado alemán (DACH)** y la fuente principal de **ediciones especiales alemanas** —
Limited / Collector / Premium Editions, Sammelschuber (estuches/box sets) y Variant-Covers
de muchas editoriales locales (altraverse, Carlsen, Egmont, Manga Cult…) que ninguna otra
fuente del catálogo cubre. Aporta metadata muy limpia: ISBN, precio, fecha de lanzamiento
y portada, todo desde una API pública.

---

## 2. Descripción técnica de la fuente

- **API pública REST JSON-LD (Hydra)** en `api.manga-passion.de`, **sin autenticación, sin
  anti-bot y sin JS**: NO requiere Playwright. El parser pega directo contra el endpoint
  con `requests`.
- **Endpoint base**: `GET /volumes` con estos parámetros:
  - `type[]=3` → **Sonderausgaben** (cualquier edición especial: Limited, Collector,
    Premium, Sammelschuber/estuche).
  - `type[]=0&tags.tag.id=200` → tomos **regulares con Variant-Cover**.
  - `itemsPerPage=50`, `page=N`, `order[year|month|day]=asc`.
  - `date[after]=YYYY-MM-DD` → filtro de fecha (modo delta; ver §4).
- **Paginación Hydra**: cada respuesta trae `hydra:member` (items de la página) y
  `hydra:view.hydra:next` (URL de la siguiente página). El parser pagina hasta que no haya
  `hydra:next` o no haya members. Hay un cap de seguridad `MAX_PAGES=300`.
- **Schema de un volumen** (campos que se usan): `id`, `type`, `specialType`
  (`0`=limited/collector, `1`=Sammelschuber/box), `title` (qualifier de la edición, p. ej.
  "Limited Edition" — NO es el título de la serie), `numberDisplay` (número de tomo),
  `price` (en **centavos** → `1900` = `19.00 €`), `year`/`month`/`day`, `isbn13`/`isbn10`,
  `cover`, `tags[]`, `contributors[]`, y `edition{title, publishers[], sources[]}` con el
  título de la serie y la editorial.
- **Identificador de producto**: URL canónica `https://api.manga-passion.de/volumes/{id}`,
  estable y única por volumen (el `id` es la PK de la base de datos).
- **Calidad de imágenes**: la portada sale del campo `cover`
  (`media.manga-passion.de/volume/cover/…`); resolución decente, mejor que los thumbnails
  de otras fuentes.

---

## 3. Proceso de ingestión — vista de producto

1. **Consultar la API** dos veces (una por cada tipo de query): Sonderausgaben (`type=3`)
   y Variant-Covers (`type=0` + tag `200`).
2. **Paginar** cada query hasta agotar resultados (Hydra `hydra:next`).
3. **Por cada volumen** se arma un item con: título completo (`{serie} Band {n} – {qualifier}`),
   editorial, precio (centavos → euros), fecha, ISBN, portada y autor. Se descarta el
   volumen si no tiene `id` o si no trae título de serie (`edition.title`).
4. Los `id` ya vistos se deduplican entre las dos queries (un volumen no entra dos veces).
5. Se aplica el gate de score (`--min-score 20` en el pipeline): los items por debajo del
   umbral se descartan.

**Reglas de producto que nunca se rompen:**
- El país de la edición es **Alemania** (#46): es el de la editorial/idioma alemán, no el
  de una tienda. Nunca se mergea cross-país.
- El qualifier de edición (`title` de la API: "Limited Edition", "Variant Cover"…) NO es el
  título de la serie; la serie sale de `edition.title`.

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

Ambos corren el mismo parser y las mismas dos queries (Sonderausgaben + Variant-Covers);
sólo cambia el **filtro de fecha** que se le pasa a la API vía `date[after]`:

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script / paso | `scripts/scrape_full.sh` (paso 2j) | `scripts/scrape_delta.sh` (paso 2i) |
| Flag | `--bootstrap-wiki mangapassion --wiki-from 2000-01` | `--bootstrap-wiki mangapassion --wiki-from "$LISTADO_CAL_FROM"` (últimos ~3 meses) |
| Discovery | catálogo histórico **completo**: `year_from=2000 < 2010` → el parser NO aplica `date[after]` y descarga todo | sólo volúmenes con `date[after] = YYYY-MM-01` de los últimos ~3 meses |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Cuándo | refresh completo del catálogo alemán | novedades recientes |

- **Umbral del filtro**: el parser sólo aplica `date[after]` si `year_from >= 2010`. Por eso
  el FULL usa `--wiki-from 2000-01` (cae bajo el umbral → catálogo completo, sin filtro).
- Ambos modos corren con `--sleep-seconds 0.3` y `--min-score 20`.

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/mangapassion.py`](../../../scripts/wikis/mangapassion.py).

### 5.1 Modelo de datos / claves
- **Source sintética por tipo de query** (`_virtual_source`): `DE - Manga-Passion
  Sonderausgaben` o `DE - Manga-Passion Variant-Covers`, ambas `country="Alemania"`,
  `language="Deutsch"`, `source_class="trusted_catalog"`, `kind="wiki"`,
  `purity="manga_only"`, tags `["wiki", "mangapassion", "deutschland"]`.
- **URL canónica** = `api.manga-passion.de/volumes/{id}` (identificador de producto).
- **País = Alemania** (#46): va de la edición, no de la tienda.
- El `edition_key`/`cluster_key` finales los deriva el pipeline general (no hay enforcer
  dedicado para esta fuente; ver §6).

### 5.2 Qué captura el parser (mapea el §3 al código)
- `parse_volume(item, type_label)` → mapea un volumen de la API a un `Candidate`. Compone
  título, precio (centavos→€), fecha, ISBN (prefiere ISBN-13 limpio), portada y autor.
- **Señales (signal_types)** vía `detect_signals`, alimentadas con hints en alemán→inglés:
  - `specialType=1` (Sammelschuber) → inyecta `"Sammelschuber Box Set"` para levantar
    `box_set`.
  - Query de variant → garantiza `"Variant Cover"` en la descripción.
  - Tags físicos del catálogo se traducen a keywords que `detect_signals` entiende
    (`_TAG_ID_TO_HINT`: `261`→Box/Schuber, `228`→DVD/Blu-ray bonus).
- **Publisher slug**: `_publisher_slug_de` complementa el map global con editoriales
  alemanas (carlsen, egmont, dokico, cross cult, manga cult, altraverse, …).
- `score_candidate(cand)` asigna el score; el gate `--min-score 20` del pipeline filtra.

### 5.3 Flujo end-to-end
- Es un **wiki/bootstrap** (#8): bypassa el source loop del YAML; se activa con
  `--bootstrap-wiki mangapassion`. Corre en **FASE 2** de `scrape_full.sh` (paso 2j) y
  `scrape_delta.sh` (paso 2i), después del scrape de fuentes del YAML.
- La firma del módulo es la estándar de los wiki parsers: `bootstrap(...)`,
  `fetch_volumes(...)`, `parse_volume(...)`, `iter_year_months(...)` (devuelve un batch
  único porque la API no particiona por mes).
- Luego pasan los retrofits de cleanup de FASE 3 (rescore → filtros → clean_titles →
  backfill metadata/imágenes → consolidate) como cualquier otra fuente.

> ⚠️ Tras un scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr el skill
> `/watch-standardize-catalog` automáticamente (lo decide el owner).

---

## 7. Validación

- **`scripts/validate_corpus.py`** (gate estructural, aplica a TODO el corpus; sin red).
- Sanity rápido sin red: que los items con `manga-passion` en la URL tengan
  `country="Alemania"` y editorial real (no la tienda). Ver el snippet de §10.
- No hay auditoría de red dedicada ni enforcer propio para esta fuente.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **API pública sin auth ni anti-bot** — a diferencia de la mayoría de fuentes, no hay
  Cloudflare, JS-render (#12) ni mojibake (#1): el JSON viene limpio. ✅
- **Términos en alemán fuera de los patterns de señal** — `Sammelschuber`, tags físicos
  del catálogo, no los entiende `detect_signals`. → ✅ se inyectan hints en inglés
  (`_TAG_ID_TO_HINT`, `specialType=1` → "Box Set", query variant → "Variant Cover").
- **Precio en centavos** — `price` viene como entero de centavos (`1900` = `19.00 €`); se
  divide entre 100. ✅
- **`title` del volumen ≠ título de serie** — el campo `title` es el qualifier de la edición
  ("Limited Edition"); la serie sale de `edition.title`. ✅
- **`day=null` con year/month válidos (audit 2026-06-10)** — la API manda `day: null`
  cuando el día exacto aún no está anunciado; el parser exigía los 3 campos y descartaba
  la fecha entera. ✅ Fix en `parse_volume()`: con year+month (sin day) el `release_date`
  queda como `"YYYY-MM"` en vez de vacío. Tests en `tests/test_wiki_parser_fixes.py`
  (`test_mp_*`).

**Decisiones (lo que NO se hace):** no se mergea cross-país (#46, la edición es alemana);
las dos queries se deduplican por `id` para no duplicar un volumen que matchee ambas.

---

## 9. Pendientes / limitaciones conocidas

- **Sólo dos queries** (`type=3` y `type=0`+tag `200`): captura Sonderausgaben y
  Variant-Covers, pero NO tomos regulares sin variante (por diseño — sólo interesan
  ediciones coleccionables).
- **Sin URL de tienda**: el item de referencia trae serie/volumen/editorial/precio/ISBN
  pero su URL canónica es la de la API, no una tienda donde comprar. Encaja en el pendiente
  global de "enrichment pass para items de referencia".
- {{pendiente: confirmar si los slugs de publishers nuevos/desconocidos —fallback
  `lc.replace(" ", "-")[:24]` en `_publisher_slug_de`— necesitan curación manual a medida
  que aparezcan editoriales no mapeadas.}}

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (deja raw, sin standardize):
# FULL (catálogo histórico completo):
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki mangapassion --wiki-from 2000-01 --min-score 20
# DELTA (últimos ~3 meses, vía date[after]):
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki mangapassion --wiki-from 2025-03 --min-score 20

# Probar el módulo directo (imprime los primeros candidates):
.venv/bin/python scripts/wikis/mangapassion.py --wiki-from 2025-01

# Validar (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "manga-passion"
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
