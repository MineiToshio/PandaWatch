# Fuente: Shueisha Books

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Shueisha Books |
| **URL base** | `https://www.shueisha.co.jp/books/` |
| **Índice / punto de entrada** | N/A — NO hay índice crawleable; el discovery parte de ISBNs seed hardcodeados (ver §2) |
| **Página de un libro** | `https://www.shueisha.co.jp/books/items/contents.html?isbn=<isbn-con-guiones>` |
| **Tipo de fuente** | Catálogo editorial oficial (editorial) — no es tienda |
| **`kind` en sources.yml** | `wiki` (módulo propio; el virtual source lo define el módulo, ver §4/§5) |
| **`source_class`** | `trusted_catalog` |
| **País** | Japón (`Japón`) — fuente mono-país |
| **Idioma** | Japonés (JP-native) |
| **Cobertura** | Publicaciones especiales de Shueisha asociadas a series de Shonen Jump: artbooks (Color Walk, All Faces, Doors!), magazines (One Piece Magazine), databooks (RED/BLUE/YELLOW/GREEN/BLUE DEEP) y libros companion. Hoy todos de **One Piece** |
| **Aporte al corpus** | ~130 items |
| **Parser / módulo** | `scripts/wikis/shueisha_books.py` |

**Editoriales que abarca**: una sola — **Shueisha** (≈130 items, todos `country=Japón`).
El `publisher` siempre es Shueisha (#44).

**Por qué importa / qué aporta de único**: es la fuente principal de **artbooks,
magazines y databooks JP-native** (画集 / ムック / 公式データブック) de franquicias de
Shueisha que NO entran por otras vías en su forma original japonesa. Las franquicias de
Shueisha ya entran al corpus en inglés vía el parser VIZ (`viz_artbooks.py`, editor
oficial EN de Shueisha) y en sus ediciones limitadas JP vía sumikko (限定版/特装版) y
booksprivilege (店舗特典); este parser queda como **suplemento JP-native específico de
One Piece** (artbooks Color Walk, One Piece Magazine, databooks).

---

## 2. Descripción técnica de la fuente

- **Página de libro** (`contents.html?isbn=<isbn-con-guiones>`) — **server-rendered**
  (HTML directo, sin JS). Una página por libro, con ISBN, precio, fecha, formato, portada
  CloudFront y navegación prev/next entre volúmenes de la misma serie. El parser le añade
  los guiones al ISBN-13 para la query (`_isbn_to_dashes`).
- **NO hay índice / buscador crawleable**: el listado de shueisha.co.jp inyecta los
  productos por **JavaScript** y NO expone filtro de ediciones especiales (限定版/特装版/
  画集). No hay forma programática (sin Playwright + reverse-engineering de XHR) de
  **descubrir** qué series/ediciones existen. Por eso el discovery NO es un crawler de
  catálogo: parte de **ISBNs seed hardcodeados** en el módulo (`SERIES` + `STANDALONE_ISBNS`),
  hoy todos de One Piece. Para sumar otra serie hay que agregar su seed ISBN al módulo.
- **Estructura del HTML** (selectores estables):
  - Título: `h1.bktitle cite b` (fallback `h1.bktitle`).
  - Autor: del `<title>` (`TÍTULO／AUTOR | 集英社`), partido por `／`.
  - Sección de edición en papel: `li.current-kamidigi section p` — de ahí salen, por
    regex sobre el texto japonés: fecha (`YYYY年M月D日`), precio (`N円` → `¥N`), formato +
    páginas (`…判／Nページ`) e ISBN (`ISBN: …`).
  - Portada: `figure.slide-item a[href]`; si no, se arma la URL CloudFront a 1200px
    (`COVER_CDN/<isbn>/1200/<isbn>.jpg`).
  - Navegación entre volúmenes: `nav.item-btn-zenkan a` — se sigue el link cuyo texto es
    `次巻` (siguiente) para encadenar la serie.
- **Identificador de producto**: el ISBN-13 (también va al dedup por ISBN). La URL
  canónica es `contents.html?isbn=<isbn-con-guiones>`.
- **Anti-bot / quirks**:
  - Texto japonés: toda la metadata (fecha/precio/formato/ISBN) se extrae por regex sobre
    kanji (`年月日`, `円`, `判`, `ページ`). Frágil si Shueisha cambia el wording.
  - Sin Cloudflare ni paginación: la página es HTML plano server-rendered.
- **Calidad de imágenes**: buena — la portada CloudFront se pide a **1200px**.

---

## 3. Proceso de ingestión — vista de producto

> Shueisha Books no descubre catálogo: recorre series **predefinidas** por sus ISBNs seed
> y, además, una lista fija de libros sueltos (databooks y misceláneos).

1. **Por cada serie predefinida** (`SERIES`: One Piece Magazine, Color Walk, All Faces,
   Doors!), arrancar desde su **ISBN seed** (primer volumen).
2. **Caminar la cadena**: abrir la página del volumen, extraer su metadata, y seguir el
   link `次巻` (siguiente volumen) hasta que no haya más (o se llegue a `max_vols=100`).
3. **Por cada libro suelto** (`STANDALONE_ISBNS`: databooks RED/BLUE/YELLOW/GREEN/BLUE
   DEEP, PIRATE RECIPES, artbooks de films, Animation Logbook), abrir su página directa
   (no tiene navegación prev/next).
4. **Cada libro** se convierte en un item con su `signals` y `product_type` predefinidos
   (artbook / fanbook-databook / magazine). Entra al corpus si supera el gate (`score ≥
   --min-score`, ver §5).

**Reglas de producto que nunca se rompen:**
- El país de la edición es Japón (es el de la editorial/idioma; #46).
- `publisher` = Shueisha, nunca una tienda (#44).
- No se inventa catálogo: sólo se ingiere lo alcanzable desde los seeds hardcodeados.

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

El parser tiene un **modo delta interno**: se activa cuando `year_from >= 2020`
(`delta = year_from >= 2020`). El modo lo decide el `--wiki-from` que pasa cada script.

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script / flag | `scripts/scrape_full.sh` (paso **2o**): `--wiki-from 2000-01` | `scripts/scrape_delta.sh` (paso **2n**): `--wiki-from $LISTADO_CAL_FROM` (mes actual − 2) |
| Modo interno | `year_from < 2020` → full: camina cada serie desde el vol 1 + **incluye los standalone** | `year_from >= 2020` → delta: sólo trae volúmenes con `release_date >= cutoff` (descubre nuevos issues de Magazine, nuevos Color Walk…); **NO trae los standalone** (databooks no cambian) |
| Discovery | mismas series chains + standalone (ISBNs seed hardcodeados) | mismas series chains; camina igual pero saltea volúmenes anteriores al cutoff |
| Invocación | `--bootstrap-wiki shueisha --wiki-from 2000-01 --sleep-seconds 0.5 --min-score 20` | `--bootstrap-wiki shueisha --wiki-from <YYYY-MM reciente> --sleep-seconds 0.5 --min-score 20` |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Cuándo | refresh completo del catálogo conocido | novedades recientes |

- En delta, el cutoff es `{year_from}-{month_from}-01`: la cadena se camina igual, pero los
  volúmenes con fecha anterior se saltean (siguiendo el `次巻` sin emitirlos).
- En delta, los **standalone NO se fetchean** (databooks/misceláneos no cambian; sólo en full).

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/shueisha_books.py`](../../../scripts/wikis/shueisha_books.py).
Se activa con `--bootstrap-wiki shueisha` (bypassea el loop de fuentes del YAML, #8).

### 5.1 Modelo de datos / claves
- No tiene reglas de agrupación propias (no es como ListadoManga). El módulo define su
  `_virtual_source()`: `country="Japón"`, `language="Japanese"`, `publisher="Shueisha"`,
  `source_class="trusted_catalog"`, `kind="wiki"`, `purity="manga_only"`, tags `["wiki",
  "shueisha", "japan", "japanese", "artbook", "magazine"]`.
- País = edición (#46): Japón, aportado por el virtual source.
- Identidad del producto = ISBN-13 + URL canónica (`contents.html?isbn=…`); el dedup por
  URL/ISBN lo hace `process_state` aguas abajo.

### 5.2 Qué captura el parser (mapea el §3 al código)
- `walk_series(seed_isbn, …)` camina una cadena siguiendo `次巻` (`parse_book_page` extrae
  `next_isbn` de `nav.item-btn-zenkan`); aplica el `date_cutoff` del modo delta.
- `fetch_standalone(isbn, …)` trae cada libro suelto (sin navegación).
- `parse_book_page(html, isbn)` arma el dict de metadata (título, autor, ISBN, fecha,
  formato, páginas, portada, next_isbn, imprint).
- `_meta_to_candidate()` construye el `Candidate`: inyecta hints en la descripción según
  `signals` (`artbook` → "Artbook."; `fanbook` → "Fanbook / Databook.") para que
  `score_candidate`/`detect_signals` deriven los `signal_types` aguas abajo, y setea
  `image_url`, `release_date`, `author`, `isbn`.
- `signal_types`/`product_type` predefinidos por entrada de `SERIES`/`STANDALONE_ISBNS`:
  `artbook`, `fanbook` (databook), `magazine`, `special_edition`.
- Gate de entrada: `score ≥ --min-score` (20) en el `flush_fn` genérico de `manga_watch.py`.
  En el corpus, los `product_type` resultantes se reparten en special/manga/magazine/
  artbook/fanbook/novel.

### 5.3 Flujo end-to-end
- Corre como **paso 2o** de `scrape_full.sh` (`--wiki-from 2000-01`, timeout 1800s) y como
  **paso 2n** de `scrape_delta.sh` (`--wiki-from $LISTADO_CAL_FROM`, timeout 600s), después
  del scrape de fuentes del YAML (fase 1) y junto a los demás wikis JP/US.
- Escribe a `data/items.jsonl` incrementalmente vía `flush_fn` (por serie / tras los
  standalone). Luego pasa por las fases comunes (cleanup retrofits → build → validate). No
  tiene retrofits dedicados.
- Tras el scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr
  `/watch-standardize-catalog` automáticamente.

> Nota: el módulo se llama `shueisha_books.py` pero se invoca como `--bootstrap-wiki
> shueisha` (el dispatch usa el alias corto).

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural del pipeline (aplica a TODO el
  corpus, sin red). Es la verificación principal para esta fuente.
- No hay auditoría de red dedicada ni enforcer/idempotencia propios (a diferencia de
  ListadoManga): es una fuente plana, sin reglas de agrupación.
- Sanity manual: caminar una serie y comparar lo que emite el parser contra el corpus (ver
  runbook §10).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Sin índice crawleable (auditoría 2026-06-01)**: el listado/buscador inyecta productos
  por JS y no expone filtro de especiales → imposible **descubrir** series sin Playwright +
  reverse-engineering de XHR. ✅ Decisión: NO ser crawler de catálogo; caminar desde ISBNs
  seed hardcodeados. Las franquicias de Shueisha ya entran en EN vía VIZ y en JP-limited
  vía sumikko/booksprivilege; este parser queda como suplemento JP-native de One Piece.
- **El DETAIL page sí funciona** (server-rendered): metadata estable por selectores. ✅
- **Decisiones (lo que NO se hace)**: no se inventa catálogo (sólo lo alcanzable desde los
  seeds); no se mergea cross-país (#46); los databooks (standalone) sólo se fetchean en
  full (no cambian).

---

## 9. Pendientes / limitaciones conocidas

- **Cobertura acotada a One Piece**: todos los seeds de `SERIES`/`STANDALONE_ISBNS` son de
  One Piece. Otras franquicias de Shueisha no entran por este parser (sí por VIZ/sumikko/
  booksprivilege). Para sumar una serie hay que agregar manualmente su seed ISBN al módulo.
- **No hay discovery automático**: si Shueisha publica una serie/edición nueva sin link
  `次巻` desde un seed conocido, este parser no la verá hasta que se agregue el ISBN a mano.
- **Metadata por regex sobre japonés**: fecha/precio/formato/ISBN se extraen por regex
  sobre kanji; un cambio de wording en el sitio puede romper la extracción en silencio.
- {{pendiente: confirmar el desglose exacto entre artbooks/magazines/databooks. En el
  corpus actual los `product_type` resultantes se reparten en special (≈37), manga (≈35),
  magazine (≈21), artbook (≈19), fanbook (≈9) y novel (≈9) — el mapeo final lo decide el
  scoring aguas abajo, no siempre coincide 1:1 con el `product_type` predefinido del seed.}}

---

## 10. Runbook / comandos útiles

```bash
# Scrape FULL de esta fuente (catálogo completo: series chains + standalone, deja raw):
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki shueisha --wiki-from 2000-01 --sleep-seconds 0.5 --min-score 20

# Scrape DELTA (sólo volúmenes nuevos; year_from >= 2020 activa el modo delta interno):
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki shueisha --wiki-from 2026-04 --sleep-seconds 0.5 --min-score 20

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Debug: parsear una página de libro por ISBN (sin escribir a items.jsonl):
.venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); import requests, \
  wikis.shueisha_books as S; s=requests.Session(); \
  html=S.fetch_book_page('9784088592176', s); \
  import json; print(json.dumps(S.parse_book_page(html,'9784088592176'), ensure_ascii=False, indent=2))"

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "shueisha"
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

**Antes de cerrar cualquier cambio en Shueisha Books**: validar (`validate_corpus`, 0
duras) → tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful,
actualiza esta ficha.
