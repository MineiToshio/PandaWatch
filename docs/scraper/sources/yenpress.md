# Fuente: Yen Press (calendario)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Yen Press (calendario) |
| **URL base** | `https://www.yenpress.com/` |
| **Índice / punto de entrada** | `https://www.yenpress.com/calendar?year=YYYY&month=M` (calendario mensual de lanzamientos) |
| **Página de un producto** | `https://www.yenpress.com/titles/{isbn13}-{slug}` |
| **Tipo de fuente** | Editorial (calendario oficial de lanzamientos), no es tienda con precio/checkout |
| **`kind` en sources.yml** | `wiki` (módulo propio; ver §5) |
| **`source_class`** | `trusted_catalog` |
| **País** | Estados Unidos (`Estados Unidos`) — fuente mono-país |
| **Idioma** | Inglés |
| **Cobertura** | Calendario mensual de lanzamientos de Yen Press (US), filtrado a ediciones especiales de manga y comics |
| **Aporte al corpus** | ~33 items |
| **Parser / módulo** | `scripts/wikis/yenpress_calendar.py` |

**Editorial que abarca**: una sola — **Yen Press** (33/33 items en el corpus). Es el
sello oficial; el calendario lista únicamente su propio catálogo.

**Por qué importa / qué aporta de único**: es la fuente de **ediciones especiales de
Yen Press en inglés (mercado US)** — collector's editions, deluxe, box sets,
hardcovers, limited editions, artbooks. El calendario mensual permite descubrir estos
lanzamientos premium directo de la editorial, en un idioma y mercado que pocas fuentes
del catálogo cubren con este foco. Trae fecha de lanzamiento, ISBN-13 e imagen de
portada determinística (no trae precio — ver §2).

---

## 2. Descripción técnica de la fuente

- **`calendar?year=YYYY&month=M`** — listado de lanzamientos de UN mes. El parser itera
  mes por mes en el rango pedido (como `manga_sanctuary.py`), NO es un listing único.
- **Estructura del HTML del calendario** (verificada 2026-05-27): cada producto es un
  `<a href="/titles/{isbn13}-{slug}">` que actúa como card raíz. Dentro:
  - **Categoría**: `span.white-label` con clase de categoría (`manga`, `comics`,
    `light-novels`, `audio`). Sólo se aceptan **manga** y **comics** (`_INCLUDE_CATS`);
    light novels y audio se descartan.
  - **Fecha**: `p.label-date` con día numérico + `span.month` (mes abreviado EN, ej.
    `17Jun`). El año se infiere del parámetro de la página (`_parse_date_from_card`).
  - **Título**: `h3.heading.small-h1` dentro de `div.genre-col-txt` (sin `<a>` interior).
  - **Imagen**: la `<img>` de la página usa una URL con parámetros de resize del
    servidor; el parser NO la usa: genera la cover URL determinística con
    `COVER_URL_TPL` a partir del ISBN.
- **Identificador de producto**: el **ISBN-13**, que está en el path del href de la `<a>`
  exterior (`/titles/(\d{13})-`), no en un enlace anidado. Se valida que empiece con
  `978`/`979`. La URL canónica del producto se arma como `{PRODUCT_BASE}{href}`.
- **Pre-filtro de keywords**: sólo pasan los títulos que mencionan un qualifier premium
  (`_SPECIAL_KWS_RE`): `collector's`, `deluxe`, `box set`, `limited/special edition`,
  `complete box/collection`, `numbered`, `slipcase`, `artbook`, `hardcover`, `omnibus`.
  Yen Press publica ~50-80 títulos/mes; este filtro deja ~2-5. Un paperback regular sin
  keyword no entra.
- **Anti-bot / quirks**:
  - **NO hay precio**: la página del calendario no expone `p.label-price`; `_parse_price`
    siempre devuelve `""`. Los items de esta fuente quedan **sin precio** (es referencia,
    no compra).
  - **Cover determinística**: `https://images.yenpress.com/imgs/{isbn13}.jpg?w=285&h=422&type=books`.
    Se deriva del ISBN, no se scrapea el `src` de la card.
  - **Carryover de meses**: Yen Press a veces lista pre-orders del mes siguiente; el
    parser acepta la fecha del `span.month` aunque no coincida con el mes del parámetro
    URL (ajusta año en bordes diciembre/enero).
- **Calidad de imágenes**: portadas de resolución media (~285×422 servidas por el CDN de
  Yen Press); el backfill puede re-fetchear mejor resolución aguas abajo (#6).

---

## 3. Proceso de ingestión — vista de producto

> Yen Press es un calendario de lanzamientos: una fuente plana mes-a-mes, sin las
> jerarquías de edición de ListadoManga. La lógica de captura es directa.

1. **Tomar un mes del calendario** (`calendar?year=YYYY&month=M`): la lista de
   lanzamientos de Yen Press de ese mes.
2. **Recorrer cada card** (`<a href="/titles/...">`) del mes, en orden de aparición.
3. **Por cada producto**, decidir si entra:
   - Se descarta si la **categoría** no es manga ni comics (light novels, audio fuera).
   - Se descarta si el **título no menciona una keyword de edición especial** (paperback
     regular fuera).
   - Faltan campos mínimos (título o ISBN válido) → se descarta.
   - De los que pasan, sólo entran al corpus los que superan el umbral de score y el gate
     de coleccionable (ver §5).
4. **Repetir** con el siguiente mes hasta cubrir todo el rango (dedup por ISBN
   intra-página y cross-mes).

**Reglas de producto que nunca se rompen:**
- El país de la edición es Estados Unidos (es el de la editorial/idioma; #46).
- `publisher` = Yen Press (la editorial real; nunca la tienda — #44). Acá coincide con la
  fuente porque Yen Press es el sello oficial.
- Un omnibus pelado sin otra señal coleccionable puede no calificar como coleccionable
  aunque la keyword lo deje pasar el pre-filtro (#18 — ver §8).

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

Mismo módulo y mismos flags en ambos modos; **la única diferencia es el rango de meses**
(`--wiki-from`).

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script / paso | `scripts/scrape_full.sh` (paso **2n**) | `scripts/scrape_delta.sh` (paso **2m**) |
| Invocación | `--bootstrap-wiki yenpress --wiki-from 2013-01 --sleep-seconds 0.5 --min-score 20` | `--bootstrap-wiki yenpress --wiki-from "$LISTADO_CAL_FROM" --sleep-seconds 0.5 --min-score 20` |
| Discovery | **catálogo histórico**: desde `2013-01` (lanzamiento de Yen Press como sello independiente) hasta el mes actual — ~140 meses | **sólo lo reciente**: últimos ~3 meses (`$LISTADO_CAL_FROM`, el mismo rango de calendario que usa el delta de listadomanga) |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Cuándo | refresh completo del histórico | novedades recientes |

- El rango sale de `--wiki-from`/`--wiki-to`. El pipeline sólo pasa `--wiki-from`; cuando
  falta `--wiki-to`, el default de `manga_watch.py` lo extiende hasta el mes actual.
- Timeouts: FULL 600s (~140 meses × 0.5s sleep ≈ 70s de red); DELTA 300s.

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/yenpress_calendar.py`](../../../scripts/wikis/yenpress_calendar.py).
Se activa con `--bootstrap-wiki yenpress` (bypassea el loop de fuentes del YAML, #8).

### 5.1 Modelo de datos / claves
- No tiene reglas de agrupación propias (no es como ListadoManga). Emite `Candidate`s con
  `country="Estados Unidos"`, `language="English"`, `publisher="Yen Press"`,
  `source_class="trusted_catalog"`, `kind="wiki"`, `purity="manga_only"`. Lo aporta la
  `_virtual_source()` del módulo.
- País = edición (#46): Estados Unidos.
- Identidad del producto = **ISBN-13** (del path del href) + URL canónica del título; el
  dedup por ISBN/URL lo hace `process_state` aguas abajo. El módulo además deduplica por
  ISBN dentro de la página y entre meses (`seen_isbns`).

### 5.2 Qué captura el parser (mapea el §3 al código)
- `parse_calendar_page()` busca los `<a href="/titles/{isbn13}-...">` que contienen
  `img.genre-col-img` (fallback: que tengan `span.white-label`); descarta los anchors de
  navegación.
- `_parse_card()` arma cada `Candidate`: valida ISBN (`_ISBN_PATH_RE`), filtra categoría
  (`_category_of_card` ∈ {`manga`, `comics`}), exige keyword premium (`_SPECIAL_KWS_RE`),
  extrae título, fecha (`_parse_date_from_card`) e imagen determinística
  (`COVER_URL_TPL`). El precio siempre queda `""` (no está en la página).
- `score_candidate()` se corre dentro de `_parse_card`; `signal_types`/`product_type` se
  derivan aguas abajo a partir de `title + description`.
- Gate de entrada al corpus (en el `flush_fn` genérico de `manga_watch.py`):
  `score ≥ --min-score` (20) **y** `is_collectible_edition(...)` ⇒ sólo entran ediciones
  coleccionables. El `min_score` del módulo descarta dentro del `bootstrap` además.

### 5.3 Flujo end-to-end
- Corre como **paso 2n** de `scrape_full.sh` y **paso 2m** de `scrape_delta.sh`, dentro de
  la tanda de wikis posterior al scrape de fuentes del YAML. Comando (FULL):
  ```
  manga_watch.py --bootstrap-wiki yenpress --wiki-from 2013-01 --sleep-seconds 0.5 --min-score 20
  ```
- Escribe a `data/items.jsonl` incrementalmente vía `flush_fn` (por mes). Luego pasa por
  las fases comunes del pipeline (cleanup retrofits → build → validate). No tiene
  retrofits dedicados.
- **Relación con las filas de Yen Press en `sources.yml`** (todas `enabled: false`): hay
  una fila `US - Yen Press News` (feed de noticias, deshabilitada 2026-06-01 por 0 items
  coleccionables) y una fila `US - Yen Press (search)` (búsqueda interna que no responde a
  queries vía URL — probable JS/AJAX). La ingestión real de collector's/deluxe/box **NO**
  llega por esas filas, sino por este wiki calendario (`--bootstrap-wiki yenpress`). Las
  filas del YAML quedan documentadas pero inactivas. (También existe `SOCIAL - Yen Press
  Bluesky`, ajena a este pipeline.)
- Tras el scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr
  `/watch-standardize-catalog` automáticamente.

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural del pipeline (aplica a TODO el
  corpus, sin red). Es la verificación principal para esta fuente.
- No hay auditoría de red dedicada ni enforcer/idempotencia propios (a diferencia de
  ListadoManga): es una fuente plana sin reglas de agrupación.
- Sanity manual: correr el módulo en standalone para un mes y comparar lo que emite contra
  el corpus (ver runbook §10).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Sin precio en la página**: el calendario no expone `label-price`; los items quedan sin
  precio (referencia, no compra; ver MEMORY "URL as reference is OK"). ✅ Esperado; no hay
  fix posible desde el calendario.
- **#6 (placeholders / resolución de imagen)**: la portada se deriva del ISBN
  (`images.yenpress.com/imgs/{isbn13}.jpg`) en resolución media; el backfill puede mejorar
  la imagen aguas abajo.
- **#18 (omnibus pelado)**: `omnibus` está en el pre-filtro de keywords del módulo (deja
  pasar la card), pero un omnibus sin otra señal coleccionable puede NO calificar en el
  gate `is_collectible_edition` aguas abajo. El pre-filtro es amplio a propósito; el gate
  final decide.
- **Decisiones (lo que NO se hace)**: no se mergea cross-país (#46); light novels y audio
  se excluyen por categoría; un paperback regular sin keyword premium no entra.

---

## 9. Pendientes / limitaciones conocidas

- **Sin precio ni URL de tienda con stock**: la fuente es de referencia editorial; para
  precio/compra haría falta un enrichment pass (ver "Enrichment pass para items de
  referencia" en CLAUDE.md).
- **Cobertura sesgada a lo reciente/futuro**: el calendario lista lanzamientos próximos;
  títulos descatalogados o muy antiguos pueden no aparecer aunque el rango histórico
  arranque en `2013-01`.
- **Markup dependiente de clases CSS** (`white-label`, `genre-col-img`, `label-date`): si
  Yen Press rediseña el calendario, el parser puede romperse. Hay un fallback de anchors
  por `span.white-label`, pero un cambio mayor exige re-verificar selectores.
- {{pendiente: confirmar el comportamiento exacto del default de `--wiki-to` en
  `manga_watch.py` para este wiki (se asume "mes actual" por paridad con los otros
  calendarios, pero no se verificó en código para yenpress específicamente).}}
- {{pendiente: el aporte de ~33 items es chico; confirmar si refleja el yield real del
  filtro de ediciones especiales o si conviene relajar el pre-filtro de keywords.}}

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente como en el pipeline FULL (histórico, deja raw):
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki yenpress --wiki-from 2013-01 --sleep-seconds 0.5 --min-score 20

# Sólo los últimos meses (como el DELTA):
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki yenpress --wiki-from 2026-03 --sleep-seconds 0.5 --min-score 20

# Debug: ver qué emite el parser para un mes (sin escribir a items.jsonl):
.venv/bin/python scripts/wikis/yenpress_calendar.py --wiki-from 2026-06

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "yenpress"
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

**Antes de cerrar cualquier cambio en Yen Press**: validar (`validate_corpus`, 0 duras) →
tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza
esta ficha.
