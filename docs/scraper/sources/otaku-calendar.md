# Fuente: Otaku Calendar

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Otaku Calendar |
| **URL base** | `https://otakucalendar.com` |
| **Índice / punto de entrada** | `https://otakucalendar.com/Calendar?month=YYYY-M` (un mes por página) |
| **Tipo de fuente** | Catálogo comunitario / calendario de lanzamientos (no es tienda) |
| **`kind` en sources.yml** | `html` (fila puntero) — la ingestión real es vía wiki |
| **`source_class`** | `trusted_media` |
| **País(es)** | Estados Unidos (`us`) — filtra a releases con sufijo de país `US` por defecto |
| **Idioma(s)** | Inglés (EN) |
| **Cobertura** | Calendario de releases del mercado manga/light novel en inglés (US), por fecha de salida |
| **Aporte al corpus** | 6 items (al último corpus) |
| **Parser / módulo** | [`scripts/wikis/otaku_calendar.py`](../../../scripts/wikis/otaku_calendar.py) |

**La fila YAML y el wiki son la MISMA fuente.** En `sources.yml` existe la entrada
`EN - Otaku Calendar` (país=Estados Unidos, idioma=Inglés, `source_class=trusted_media`),
pero es sólo un **puntero documental**: el scraper genérico del YAML no la procesa. La
ingestión ocurre exclusivamente vía `--bootstrap-wiki otaku-calendar`, que usa el módulo
`otaku_calendar.py` con una `Source` sintética interna (`_virtual_source()`) idéntica a la
fila YAML. No hay doble conteo: las dos referencias apuntan al mismo origen.

**Editoriales** (del corpus real): el calendario no expone la editorial por release, así
que los items entran como `Varias editoriales` (1 item con publisher seteado; el resto sin
publisher). Todos son de Estados Unidos.

**Por qué importa / qué aporta de único**: cubre el calendario de lanzamientos del mercado
manga/LN en inglés (US) por fecha — una señal de novedades que las fuentes ES/FR/JP no dan.
Aporte de corpus pequeño porque sólo entran releases que pasan `is_likely_manga` y el
umbral de score; es una fuente de descubrimiento, no de catálogo masivo.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs**: una página por mes, `Calendar?month=YYYY-M` (mes sin cero a la
  izquierda). El módulo arma esa URL en `fetch_calendar_month()`.
- **Estructura del HTML**: cada mes trae varios `<div class="dateListingContainer">`, uno
  por día. El contenedor empieza con un encabezado de fecha en texto (`"Tuesday 5 May
  2026"`) y dentro lleva un `<a href="/Release/<id>/<slug>">` por cada release. El texto de
  cada link es de la forma `Título (Manga|Light Novel) Volume N (Manga|Light Novel) US`.
- **Identificador de producto**: la URL canónica del release, `/Release/<id>/<slug>`
  (resuelta con `urljoin` sobre la URL base). No hay URL sintética.
- **Fecha de release**: se deriva del encabezado del contenedor del día (`release_date`,
  ISO `YYYY-MM-DD`) y se propaga a `published_at`.
- **Formato y país**: el sufijo del título (`(Manga) US`, `(Light Novel) AU`) se separa en
  `(clean_title, format_label, country_code)`. Por defecto sólo se conservan releases con
  país `US` (`DEFAULT_COUNTRIES = ("US",)`).
- **Anti-bot / quirks**: sin Cloudflare ni JS conocido. El módulo fuerza encoding (cae a
  `apparent_encoding`/`utf-8` si el server no lo declara). No envía `Accept-Encoding: br`,
  evitando el problema de Brotli binario (#15).
- **Calidad de imágenes**: la página de release **no expone portada, precio ni ISBN** — el
  único dato útil está en el listing (título, formato, país, fecha). Por eso `fetch_details`
  es no-op para esta fuente.

---

## 3. Proceso de ingestión — vista de producto

1. **Ir al calendario** de un mes (`Calendar?month=YYYY-M`).
2. **Recorrer cada día** (`dateListingContainer`): leer la fecha del encabezado y tomar
   cada release link (`/Release/…`).
3. **Limpiar el título**: separar formato (`Manga` / `Light Novel`) y país del sufijo.
4. **Filtrar por país**: sólo entran releases `US` (configurable; default `US`).
5. **Filtrar non-manga**: cada release pasa por `is_likely_manga()` (#2). Lo que no califica
   se descarta.
6. **Puntuar** (`score_candidate`) y conservar sólo lo que supera el umbral de score.
7. **Repetir** mes a mes en el rango pedido.

**Reglas de producto que nunca se rompen:** el país de la edición es Estados Unidos (`us`),
y va al `edition_key` (#46) — es el país del release (mercado/idioma), no el de una tienda.
Un release que no califica como manga (`is_likely_manga`) no entra.

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

Otaku Calendar se ingiere **igual en FULL y en DELTA**: misma invocación, mismo rango por
defecto. No tiene discovery diferenciado.

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script / flag | `scrape_full.sh` paso 2c · `--bootstrap-wiki otaku-calendar` | `scrape_delta.sh` paso 2c · `--bootstrap-wiki otaku-calendar` |
| Discovery | rango de meses por defecto (`--wiki-from` 2024-01 → mes actual) | idéntico |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Cuándo | refresh completo | novedades recientes |

Ninguno de los dos scripts pasa `--wiki-from`/`--wiki-to`, así que ambos usan el rango por
defecto de `manga_watch.py` (desde 2024-01 hasta el mes actual). El parámetro es el mismo en
los dos modos: `--sleep-seconds 0.5 --min-score 20`.

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/otaku_calendar.py`](../../../scripts/wikis/otaku_calendar.py).
API pública paralela al resto de wikis: `parse_calendar_page`, `fetch_calendar_month`,
`iter_year_months`, `bootstrap`.

### 5.1 Modelo de datos / claves
- **Identidad** = URL canónica del release (`/Release/<id>/<slug>`). No hay URL sintética.
- **País = edición** (#46): `us` (filtro `DEFAULT_COUNTRIES`), va al `edition_key`.
- `release_date` / `published_at` = fecha ISO del día del calendario.
- `tags`: hereda los de la `Source` virtual (`wiki`, `otakucalendar`, `english`, `calendar`)
  y agrega `format:<manga|light_novel>` y `country:<cc>` cuando se detectan.

### 5.2 Qué captura el parser (mapea el §3 al código)
- `parse_calendar_page()` → itera `div.dateListingContainer`; por cada `<a>` con `/Release/`
  arma un `Candidate` vía `candidate_from_source` con la `Source` virtual.
- `_strip_format_and_country()` → separa `(formato, país)` del sufijo del título.
- Gates: filtro de país → `is_likely_manga()` (#2) → `score_candidate()` → umbral
  `min_score` en `bootstrap()`.
- `fetch_details` está aceptado en la firma pero es **no-op** (la página de release no trae
  cover/precio/ISBN).

### 5.3 Flujo end-to-end
- **FULL** (`scrape_full.sh`, paso 2c) y **DELTA** (`scrape_delta.sh`, paso 2c) corren la
  misma fase de wiki bootstraps, con timeout de 300s y log en `02c-otaku-calendar.log`.
- Luego pasa por los cleanup retrofits comunes (rescore → filtros → clean_titles →
  backfill metadata → build) como cualquier otra fuente.

> ⚠️ Tras el scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr
> `/watch-standardize-catalog` automáticamente (lo decide el owner).

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural, aplica a TODO el corpus (sin red).
- Esta fuente no tiene enforcer ni retrofits dedicados, así que no hay prueba de
  idempotencia propia.
- Verificación puntual: re-correr `bootstrap` para un mes y comparar el conteo de releases
  `US` con los items en la DB (ver runbook §10).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Aporte bajo (6 items)**: esperado. Es un calendario de novedades, no un catálogo; sólo
  entra lo que pasa `is_likely_manga` (#2) y supera el score. No es un bug.
- **Sin portada/precio/ISBN en la página de release** — la página individual no expone esos
  datos, por eso `fetch_details` es no-op y el dato útil se toma del listing.
- **Encoding** — el server a veces no declara charset; el módulo cae a `apparent_encoding`
  para evitar mojibake. No se envía `Accept-Encoding: br` (evita el Brotli binario, #15).
- **Decisiones (lo que NO se hace)**: no se mergea cross-país (#46); por defecto sólo entra
  `US` (otros países como `AU` se filtran salvo que se configure `allowed_countries`).

---

## 9. Pendientes / limitaciones conocidas

- **Publisher ausente**: el calendario no expone editorial, así que los items quedan sin
  `publisher` (o como `Varias editoriales`). Enriquecerlo requeriría cruzar con otra fuente.
- **Sin imágenes**: no hay portada disponible desde esta fuente; los items dependen de que
  otra fuente aporte la cover en el merge, o quedan sin imagen.
- **Sólo país US por defecto**: releases de otros mercados del calendario (`AU`, etc.) se
  descartan; ampliarlo es un cambio de configuración (`allowed_countries`), no del parser.

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (igual en full y delta; deja raw):
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki otaku-calendar \
    --sleep-seconds 0.5 --min-score 20

# Acotar a un rango de meses (default: 2024-01 → mes actual):
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki otaku-calendar \
    --wiki-from 2026-04 --wiki-to 2026-06 --min-score 20

# Debug directo del módulo (un rango, score bajo, sin tocar items.jsonl):
.venv/bin/python scripts/wikis/otaku_calendar.py --from 2026-04 --to 2026-06 --country US

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "otakucalendar"
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
