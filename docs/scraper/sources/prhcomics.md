# Fuente: PRH Comics (Penguin Random House Comics)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | PRH Comics (Penguin Random House Comics) |
| **URL base** | `https://prhcomics.com/` |
| **Índice / punto de entrada** | `https://prhcomics.com/manga/` (una sola página HTML estática, sin paginación) |
| **Página de una edición** | `https://prhcomics.com/book/?isbn=<isbn13>` (URL canónica determinística) |
| **Tipo de fuente** | Editorial / distribuidor (portal oficial de PRH para sus divisiones de cómic y manga), no es tienda |
| **`kind`** | `wiki` (módulo propio; ver §5 — wiki virtual, NO tiene entrada en `sources.yml`) |
| **`source_class`** | `trusted_catalog` |
| **País** | Estados Unidos (`Estados Unidos`) — fuente mono-país (ver §9) |
| **Idioma** | Inglés (`English`) |
| **Cobertura** | Catálogo activo de ediciones especiales de manga en inglés de las divisiones que PRH distribuye |
| **Aporte al corpus** | ~97 items |
| **Parser / módulo** | `scripts/wikis/prhcomics.py` |

**Editoriales que abarca** (divisiones distribuidas por PRH; entre paréntesis, volumen
aproximado de items en el corpus):

Kodansha Comics (≈22) · Square Enix Manga (≈20) · Dark Horse Manga (≈19) · Dark Horse (≈9) ·
Disney Manga (≈8) · Vertical Comics (≈6) · Seven Seas (≈5) · Square Enix Books (≈2) ·
LoveLove (≈2) · TOKYOPOP (≈1) · Titan Manga (≈1), entre otras (también aparecen sueltos
DC Comics y VIZ Media; ver §8).

El módulo documenta como divisiones objetivo: Dark Horse Manga, Kodansha Comics, Seven Seas
Entertainment, Square Enix Manga, TOKYOPOP, Titan Comics, Vertical Comics e Inklore.
**No cubre VIZ Media ni Yen Press** (tienen distribución propia).

**Por qué importa / qué aporta de único**: es la fuente principal de **ediciones especiales
de manga en inglés del mercado norteamericano** (collector's editions, deluxe hardcovers,
box sets, slipcase, complete editions, artbooks). Concentra en una sola página el catálogo
de varias editoriales que de otro modo habría que scrapear por separado, y es la vía por la
que entran los box sets de Seven Seas (la fuente directa de Seven Seas quedó deshabilitada
por costo de JS — ver `sources.yml`, `enabled: false`). `publisher` = la división real
(Kodansha, Square Enix…), nunca "PRH" (#44).

---

## 2. Descripción técnica de la fuente

- **`/manga/`** — una **única página HTML estática** con todo el catálogo. Sin paginación,
  sin JS, sin autenticación. Todos los metadatos del listing están en el HTML directamente;
  no hace falta hitear páginas de detalle.
- **Estructura del HTML**: cada producto es un `<li class="toast-anchor">` con un bloque
  `div[data-component="carousel-meta"]`. Selectores clave (todos `data-component`):
  - Título: `carousel-meta-title a`.
  - Autor: `carousel-meta-author a`.
  - ISBN-13: `carousel-meta-isbn` (se le quitan guiones; **requerido**).
  - Precio: `carousel-meta-price span.price-usa` (USD).
  - Formato del binding: `carousel-meta-format` (`Hardcover`, `Boxed Set`, …).
  - División/editorial: `carousel-meta-division`.
  - Fecha de salida: `carousel-meta-on-sale-date` (`"On sale May 19, 2026"`).
- **Identificador de producto**: el **ISBN-13**. De él se derivan de forma determinística:
  - URL canónica: `https://prhcomics.com/book/?isbn={isbn13}`.
  - Portada: `https://images.penguinrandomhouse.com/cover/{isbn13}`.
- **Anti-bot / quirks**: ninguno relevante — HTML estático plano, sin Cloudflare ni JS. El
  mismo tomo puede aparecer en varios carruseles de la página; el módulo deduplica por ISBN
  dentro del mismo run (`seen_isbns`).
- **Calidad de imágenes**: la portada viene del CDN de Penguin Random House
  (`images.penguinrandomhouse.com/cover/{isbn}`), que sirve la imagen sin límite explícito
  de ancho en la URL determinística (el HTML linkea miniaturas `?width=180`, pero el módulo
  guarda la URL base sin el parámetro).

---

## 3. Proceso de ingestión — vista de producto

> PRH Comics es un catálogo plano de una sola página: la lógica de captura es directa, sin
> las jerarquías de edición de ListadoManga.

1. **Descargar `/manga/`** y recolectar todos los `<li class="toast-anchor">`.
2. **Por cada producto**, decidir si entra:
   - Se descarta si le falta **título o ISBN** (campos mínimos).
   - Se descarta si **no parece edición especial**: el gate `_is_collectible()` exige que el
     formato del binding sea coleccionable (`hardcover`, `boxed set`, `box set`, `slipcase`)
     **o** que el título traiga una keyword especial (`collector`, `deluxe`, `artbook`,
     `limited edition`, `complete edition`, `omnibus hardcover`, `premium`, `kanzenban`,
     `anniversary`, `special edition`…). Un paperback regular sin señal especial **no entra**.
   - Se descarta si la división **no es de manga** (`_NON_MANGA_PUBLISHERS`: DK Children, DK,
     Golden Books, Random House Books for Young Readers, Prestel, Pantheon — aparecen bajo
     `/manga/` por licencias de franquicia, no son manga).
3. **Deduplicar por ISBN** dentro del run (un tomo puede repetirse en varios carruseles).
4. **Filtro de fecha opcional** (modo delta): si la fecha de salida es anterior al cutoff
   `--wiki-from`, se descarta. Si `--wiki-from` es < 2010, no se filtra por fecha.
5. **Umbral de score**: sólo entran los que superan `--min-score` (20 en el pipeline).

**Reglas de producto que nunca se rompen:**
- El país de la edición es Estados Unidos (es el de la editorial/idioma; #46).
- `publisher` = división real (Kodansha, Square Enix…), nunca "PRH" (#44).
- Una división que no es de manga se descarta aunque aparezca bajo `/manga/`.

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

PRH Comics se invoca con el **mismo módulo** en ambos modos; la única diferencia es el cutoff
de fecha que se pasa por `--wiki-from`. Como la página es una sola y trae el catálogo
activo completo, no hay un discovery distinto: el "delta" sólo recorta por fecha de salida.

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script / paso | `scripts/scrape_full.sh` (paso **2l**) | `scripts/scrape_delta.sh` (paso **2k**) |
| Invocación | `--bootstrap-wiki prhcomics --wiki-from 2010-01 --min-score 20` | `--bootstrap-wiki prhcomics --wiki-from "$LISTADO_CAL_FROM" --min-score 20` |
| Cutoff de fecha | `2010-01` (efectivamente sin filtro: trae todo el catálogo activo) | `LISTADO_CAL_FROM` = mes actual − 2 meses (sólo salidas recientes) |
| Request HTTP | una sola, `timeout` corto (`_run_timed 120`) | idéntica |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Cuándo | refresh completo del catálogo | novedades recientes |

- El filtro de fecha aplica sobre `release_date` (la "On sale date" parseada). Items sin
  fecha parseable **no se filtran** (pasan el cutoff).
- `fetch_details` no se usa: todo el metadato está en el listing, no hay HTTP por ficha.

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/prhcomics.py`](../../../scripts/wikis/prhcomics.py). Se activa con
`--bootstrap-wiki prhcomics`, que **bypassea el loop de fuentes del YAML** y corre su propio
`is_likely_manga()`/scoring (#8). No lee config de `sources.yml` (es wiki virtual).

### 5.1 Modelo de datos / claves
- No tiene reglas de agrupación propias. Emite `Candidate`s desde `_virtual_source()` con
  `country="Estados Unidos"`, `language="English"`, `source_class="trusted_catalog"`,
  `kind="wiki"`, `purity="manga_only"`, `tags=["wiki","prhcomics","usa","canada","english"]`.
- País = edición (#46): Estados Unidos. Lo aporta `_virtual_source()`.
- Identidad del producto = **ISBN-13** (→ URL canónica `book/?isbn=` + cover determinística).
  El dedup global por URL/ISBN lo hace `process_state` aguas abajo; el módulo además
  deduplica por ISBN dentro del run.

### 5.2 Qué captura el parser (mapea el §3 al código)
- `fetch_manga_page()` descarga `/manga/` y devuelve los `<li class="toast-anchor">`.
- `parse_item()` arma cada `Candidate`: título, autor, ISBN, precio (USD), formato, división
  (publisher), fecha de salida (`_parse_release_date`), URL e imagen determinísticas.
- `_is_collectible(title, fmt)` es el gate de edición especial (formato coleccionable o
  keyword en el título). `_NON_MANGA_PUBLISHERS` rechaza divisiones no-manga.
- `_format_signal_hints(fmt)` inyecta palabras (`"Hardcover"`, `"Box Set"`) en la
  `description` para que `detect_signals` levante las señales correctas desde el binding
  (las `signal_types` salen sólo de `title + description`, #10). `score_candidate(cand)` corre
  dentro de `parse_item`.
- `bootstrap()` recorre todos los `<li>`, deduplica por ISBN, aplica el filtro de fecha
  opcional y el `--min-score`, y hace `flush_fn` con los candidates resultantes.

### 5.3 Flujo end-to-end
- Corre como **paso 2l** de `scrape_full.sh` y **paso 2k** de `scrape_delta.sh`, en el bloque
  de wikis de fuentes en inglés (junto a kinokuniya US, yenpress US). Comando base:
  ```
  manga_watch.py --bootstrap-wiki prhcomics --wiki-from <cutoff> --min-score 20
  ```
  envuelto en `_run_timed 120` (timeout corto: una sola request).
- Escribe a `data/items.jsonl` vía `flush_fn`. Luego pasa por las fases comunes del pipeline
  (cleanup retrofits → build → validate). No tiene retrofits dedicados.
- Tras el scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr
  `/watch-standardize-catalog` automáticamente.

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural del pipeline (aplica a TODO el corpus,
  sin red). Es la verificación principal para esta fuente.
- No hay auditoría de red dedicada ni enforcer/idempotencia propios (es una fuente plana sin
  reglas de agrupación).
- Sanity manual: correr el módulo directamente (`python scripts/wikis/prhcomics.py`, ver §10)
  y comparar lo que emite el parser contra el corpus.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Divisiones no-manga bajo `/manga/`**: PRH agrupa bajo `/manga/` licencias de franquicia
  que no son manga (DK readers de Pokémon, guías DK, Golden Books…). ✅ Se filtran por
  publisher con `_NON_MANGA_PUBLISHERS`.
- **Editoriales fuera del scope objetivo en el corpus**: aparecen sueltos items con publisher
  `DC Comics` y `VIZ Media`, pese a que el módulo declara que no cubre VIZ. Llegan porque el
  gate es por formato/keyword + filtro de publishers no-manga, no por allowlist de divisiones;
  si la división no está en `_NON_MANGA_PUBLISHERS` y el formato es coleccionable, entra.
  {{pendiente: confirmar si conviene endurecer el filtro a una allowlist de divisiones manga,
  o si estos sueltos son aceptables como ediciones especiales válidas.}}
- **Dedup por ISBN dentro del run**: el mismo tomo aparece en varios carruseles de la página.
  ✅ `seen_isbns` evita duplicados en una misma corrida (el dedup global por URL/ISBN aguas
  abajo lo cubre entre corridas).
- **Decisiones (lo que NO se hace)**: no se hitean páginas de detalle (todo el metadato está
  en el listing); no se mergea cross-país (#46); un paperback regular sin señal coleccionable
  no entra.

---

## 9. Pendientes / limitaciones conocidas

- **País = Estados Unidos, no Canadá**: aunque la fuente se describe como "US/CA" en los
  scripts y los tags incluyen `"canada"`, `_virtual_source()` fija `country="Estados Unidos"`
  para todos los items (en el corpus, los 97 son `Estados Unidos`). No se distingue la edición
  canadiense.
- **Catálogo activo, no histórico**: `/manga/` muestra el catálogo vigente; los títulos que
  salen de catálogo dejan de aparecer. No hay forma de recuperar salidas históricas que ya no
  estén listadas (el `--wiki-from 2010-01` del full no trae histórico, sólo desactiva el
  filtro de fecha sobre el catálogo actual).
- **Precio sólo en USD**: se captura `span.price-usa`; no se guarda el precio canadiense aunque
  exista en el HTML.
- **Gate por formato/keyword, no por allowlist**: ver §8 — pueden colarse divisiones fuera del
  scope objetivo (DC, VIZ) si el formato es coleccionable.

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (igual que en el pipeline FULL, deja raw):
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki prhcomics --wiki-from 2010-01 --min-score 20

# Modo delta (sólo salidas recientes):
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki prhcomics --wiki-from 2026-04 --min-score 20

# Debug: correr el módulo directo (no escribe a items.jsonl, imprime candidates):
.venv/bin/python scripts/wikis/prhcomics.py --wiki-from 2010-01

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "prhcomics"
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

**Antes de cerrar cualquier cambio en PRH Comics**: validar (`validate_corpus`, 0 duras) →
tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza esta
ficha.
