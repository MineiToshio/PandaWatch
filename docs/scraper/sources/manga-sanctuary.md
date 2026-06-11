# Fuente: Manga-Sanctuary

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-10.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Manga-Sanctuary |
| **URL base** | `https://www.manga-sanctuary.com/` |
| **Índice / punto de entrada** | `https://www.manga-sanctuary.com/planning/?&deb=<unix_timestamp>` (planning mensual) |
| **Página de una edición** | `https://www.manga-sanctuary.com/<slug>.html` (ficha de producto) |
| **Tipo de fuente** | Catálogo comunitario / base de datos (calendario de salidas), no es tienda |
| **`kind` en sources.yml** | `html` (módulo wiki propio; ver §5) |
| **`source_class`** | `trusted_media` |
| **País** | Francia (`Francia`) — fuente mono-país |
| **Idioma** | Francés |
| **Cobertura** | Calendario histórico de salidas de manga en Francia, mes a mes |
| **Aporte al corpus** | ~1099 items (re-ingest histórico 2026-06-10: 901 → 1099 con el fix de labels bare) |
| **Parser / módulo** | `scripts/wikis/manga_sanctuary.py` |

**Editoriales que abarca** (todas las editoriales de manga francesas; entre paréntesis,
volumen aproximado de items en el corpus):

Kana (≈105) · Panini Manga (≈100) · Glénat Manga (≈83) · Pika (≈69) · Meian (≈61) ·
Ki-oon (≈57) · Doki-Doki (≈55) · Kurokawa (≈49) · Kazé Manga (≈27) · Delcourt / Tonkam
(≈27) · Crunchyroll (≈26) · Custom Publishing France (≈21) · Noeve (≈16) · Black Box
(≈16) · Akata (≈15) · Panini Comics (≈15) · Ankama Manga (≈12) · Nobi Nobi! (≈12) ·
Soleil Manga (≈11) · Vega-Dupuis (≈11), entre otras.

**Por qué importa / qué aporta de único**: es la fuente principal de **ediciones
especiales y coleccionables del mercado francés** (coffret / collector / édition limitée /
édition deluxe), un mercado y un idioma que ninguna otra fuente del catálogo cubre con esta
profundidad. El planning es un calendario de salidas: trae fecha de publicación, editorial,
tipo de edición, precio en euros, EAN (ISBN-13) e imagen de portada.

---

## 2. Descripción técnica de la fuente

- **`planning/?&deb=<unix_timestamp>`** — listado de salidas de UN mes. El parámetro `deb`
  es el timestamp Unix del 1er día del mes a 00:00 UTC (`month_to_deb_param`). Cada mes se
  fetchea por separado.
- **Estructura del HTML del planning**:
  - Los encabezados de fecha van en `<div class="sortie-date …">` con texto en francés
    (`"mercredi 6 mai 2026"`). Se parsea a ISO `2026-05-06` (`_parse_date_header`, con el
    diccionario `FRENCH_MONTHS`).
  - Cada producto es un `<div class="post sortie …">`:
    - Título: `.post-title a`.
    - Editorial: `.sortie-editeur`.
    - Tipo de edición: el texto que sigue al `" / "` en `.sortie-edition` (ej. `"simple"`,
      `"coffret collector"`) → se guarda como tag `edition:<texto>`.
    - Categoría: `.badge_sm` (`Manga`, `Light novel`, `Magazine`…) → tag `type:<texto>`.
    - EAN/ISBN-13: atributo `ean` del `.affiliation` (se valida que tenga 13 dígitos).
    - Precio: regex `\d+[,.]\d{2}\s*€` sobre el texto del post → `€ N,NN`.
    - Imagen: `.post-thumbnail img` (`src`/`data-src`/`data-original`).
- **Página de detalle** (`<slug>.html`): se usa SÓLO si `fetch_details=True` (no en el
  pipeline canónico). De ahí sale el autor (links a `/bdd/personnalites/` o labels
  `Scénariste`/`Dessinateur`/`Auteur`) y, si existe, una galería multi-imagen.
- **Identificador de producto**: la URL canónica de la ficha (`<slug>.html`). El EAN se
  guarda aparte como ISBN para el dedup por ISBN.
- **Anti-bot / quirks**:
  - **Mojibake FR** (#1): las editoriales FR (Glénat/Pika y similares) sirven UTF-8
    decodificado como cp1252; el saneo lo hace `clean_title()` aguas abajo.
  - **URL drift de releases futuros** (#2): una URL de un release futuro puede redirigir a
    la ficha de OTRO manga. `_title_matches_page()` valida que la página de detalle
    corresponda al título esperado antes de extraer autor/galería; si no, aborta.
  - **Placeholder de imagen** (#6): el thumbnail por defecto `visuel_defaut` no es una
    portada real; el parser lo descarta (`image_url=""`) para que el dashboard muestre el
    placeholder 📚 y el backfill re-fetchee.
- **Calidad de imágenes**: las portadas salen de `img.sanctuary.fr/objet/300/…` (resolución
  media). Cuando hay galería en el detalle, sólo se captura si tiene más de una imagen.

---

## 3. Proceso de ingestión — vista de producto

> Manga-Sanctuary es un calendario de salidas: una fuente plana mes-a-mes, sin las
> jerarquías de edición de ListadoManga. La lógica de captura es directa.

1. **Tomar un mes del planning** (`planning/?&deb=<timestamp>`): la lista de salidas de
   manga en Francia de ese mes.
2. **Recorrer cada bloque de fecha y cada producto** dentro del mes, en orden de aparición.
3. **Por cada producto**, decidir si entra:
   - Se descarta si NO parece manga (figuras, estatuas, derivados): se aplica
     `is_likely_manga()` sobre título/descripción/tags (#2 de las 7 decisiones).
   - De los que pasan, sólo se conservan los que superan el umbral de score y el gate de
     coleccionable (ver §5): ediciones especiales, coffret collector, édition limitée, etc.
     Un tomo `simple` normal sin señal coleccionable no entra.
4. **Repetir** con el siguiente mes hasta cubrir todo el rango de fechas.

**Reglas de producto que nunca se rompen:**
- El país de la edición es Francia (es el de la editorial/idioma; #46).
- `publisher` = editorial real (Kana, Glénat…), nunca "Manga-Sanctuary" (#44).
- Un release derivado no-manga se descarta aunque aparezca en el planning.

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

Manga-Sanctuary se invoca **idéntico en FULL y en DELTA**: mismo módulo, mismos flags. No
hay diferencia de discovery entre ambos modos (a diferencia de ListadoManga).

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script | `scripts/scrape_full.sh` (paso 2b) | `scripts/scrape_delta.sh` (paso 2b) |
| Invocación | `--bootstrap-wiki manga-sanctuary --sleep-seconds 0.5 --min-score 20` | idéntica |
| Discovery | planning mes a mes en el rango `--wiki-from`→`--wiki-to` | idéntico |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Cuándo | refresh completo | novedades recientes |

- El rango de meses sale de `--wiki-from`/`--wiki-to`. Como ninguno de los dos scripts los
  pasa, aplican los defaults de `manga_watch.py`: **desde `2024-01` hasta el mes actual**
  (`yf,mf = 2024-01`; `yt,mt = today`). Itera mes por mes (`iter_year_months`).
- `fetch_details` queda en **False** en el pipeline (no se hace el HTTP extra por ficha);
  el autor sólo se enriquece si se invoca a mano con `--fetch-details`.

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/manga_sanctuary.py`](../../../scripts/wikis/manga_sanctuary.py).
Se activa con `--bootstrap-wiki manga-sanctuary` (bypassea el loop de fuentes del YAML,
#8); el dispatch está en `manga_watch.py` (~línea 6687).

### 5.1 Modelo de datos / claves
- No tiene reglas de agrupación propias (no es como ListadoManga). Emite `Candidate`s con
  `country="Francia"`, `language="Francés"`, `source_class="trusted_media"`, `kind="html"`.
- País = edición (#46): Francia. Lo aporta la `_virtual_source()` del módulo.
- Identidad del producto = URL canónica de la ficha (`<slug>.html`) + ISBN (EAN) cuando
  existe; el dedup por URL/ISBN lo hace `process_state` aguas abajo.

### 5.2 Qué captura el parser (mapea el §3 al código)
- `parse_planning_page()` recorre los `<div>` del mes: detecta encabezados de fecha
  (`sortie-date`) y posts de producto (`post sortie`).
- `_parse_post()` arma cada `Candidate`: título, publisher, tipo de edición (tag
  `edition:…`), categoría (tag `type:…`), EAN→ISBN, precio (€) e imagen.
- `signal_types`/`product_type` se derivan aguas abajo (`score_candidate`, `detect_signals`)
  a partir de `title + description` (la descripción combina publisher · edición · tipo ·
  título para dar contexto coleccionable). Los tags `type:…`/`edition:…` también alimentan
  los filtros (los reconoce el set taxonómico de fuentes externas en `manga_watch.py`).
- Gate de entrada al corpus (en el `flush_fn` genérico de `manga_watch.py`): `score ≥
  --min-score` (20) **y** `is_collectible_edition(...)` ⇒ sólo entran ediciones
  coleccionables.

### 5.3 Flujo end-to-end
- Corre como **paso 2b** de `scrape_full.sh` y `scrape_delta.sh`, justo después del scrape
  de fuentes del YAML (fase 1) y antes de los demás wikis. Comando:
  ```
  manga_watch.py --bootstrap-wiki manga-sanctuary --sleep-seconds 0.5 --min-score 20
  ```
- Escribe a `data/items.jsonl` incrementalmente vía `flush_fn` (por mes). Luego pasa por las
  fases comunes del pipeline (cleanup retrofits → build → validate). No tiene retrofits
  dedicados.
- Tras el scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr
  `/watch-standardize-catalog` automáticamente.

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural del pipeline (aplica a TODO el corpus,
  sin red). Es la verificación principal para esta fuente.
- No hay auditoría de red dedicada ni enforcer/idempotencia propios (a diferencia de
  ListadoManga): es una fuente plana sin reglas de agrupación.
- Sanity manual: re-fetchear un mes del planning y comparar lo que emite el parser contra el
  corpus (ver runbook §10).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#1 (Mojibake FR)**: editoriales francesas sirven UTF-8 leído como cp1252 → acentos rotos
  en títulos. ✅ Lo repara `clean_title()` aguas abajo; no agregar regex-cleaning antes.
- **#2 (URL drift de releases futuros)**: la URL de detalle de un release futuro puede
  servir la ficha de otro manga. ✅ `_title_matches_page()` valida coincidencia de título
  antes de extraer autor/galería; si no matchea, no enriquece.
- **#6 (placeholder de imagen)**: `visuel_defaut` es un thumbnail "sin imagen". ✅ El parser
  lo descarta para que el backfill re-fetchee una portada real.
- **Labels de edición "bare" sin señal (audit 2026-06-10)**: la planning page expone el
  tipo de edición como label pelado tras el `/` de `.sortie-edition` ("Perfect",
  "Ultimate", "Prestige", "limitée", "unlimited double", "Collector"…) pero
  `detect_signals()` sólo matchea bigramas ("perfect edition", "édition limitée"…), así
  que ~100+ ediciones especiales FR puntuaban 0 y se perdían (verificado:
  `detect_signals('Prestige') == 0`). ✅ Fix: mapeo canónico `_EDITION_LABEL_CANONICAL` +
  `canonical_edition_phrase()` en `manga_sanctuary.py` — la frase canónica se APPENDEA a
  la description (el label original se conserva para display; si el label ya es la frase
  canónica, no se duplica). "Intégrale" se deja sin mapear a propósito (omnibus, fuera de
  scope — gotcha #18); labels desconocidos quedan verbatim. Tests en
  `tests/test_wiki_parser_fixes.py` (`test_ms_*`).
- **Revista ATOM infiltrada como serie astro-boy (2026-06-10, gotcha #62)**: la revista de
  prensa FR "ATOM" (`/magazine-atom-vol-N`) se coló en el planning y quedó mapeada a la
  serie astro-boy — estandarizada como "Astro Boy | Mighty Atom Deluxe N", idéntica al título
  de los tomos deluxe reales de Planeta ES. Un gate por título habría borrado esos 7 legítimos.
  ✅ Fix: gate por URL (`manga-sanctuary.com/magazine-atom-`) vía `_UMBRELLA_MAGAZINE_URL_PATTERN`
  en `is_collectible_edition` paso 0b (paso `umbrella_magazine`); removidas las alternativas
  de título "Atom Hardcover|Mighty Atom (Magazine|Deluxe|Hardcover)". 21 items removidos del
  corpus. REGLA: cuando el título de una revista coincide con el de una obra manga real, el
  discriminante es la URL, no el título.
- **Re-ingest histórico con el fix de labels bare (2026-06-10)**: corrida full 2024-01 →
  2026-06 (30 meses, 591 candidates ≥20). La fuente pasó de 901 a 1099 items; los nuevos
  entran exactamente por los labels mapeados (`edition:perfect` ×14 en los últimos 6 meses,
  `ultimate`, `prestige`, `limitée`, `unlimited double`…). ✅ Fix verificado en producción.
- **Re-scrape sobre corpus estandarizado degrada filas existentes (gotcha #65, 2026-06-10)**:
  el upsert del flush refrescó ~394 filas estandarizadas de esta fuente reseteando
  `slug`/`cluster_key`/`detected_at`/`score`/`signals` → validate_corpus en rojo
  (SLUG/CLKEY/DUPCL). Reparación: `backfill_cluster_key.py` → `generate_slugs.py
  --only-missing` → `consolidate_sources.py` (1272 → 0 violaciones duras). Tener en cuenta
  SIEMPRE que se re-scrapee esta fuente (o cualquiera) sobre items ya estandarizados.
- **Decisiones (lo que NO se hace)**: no se mergea cross-país (#46); un tomo `simple` sin
  señal coleccionable no entra; releases derivados no-manga se descartan vía
  `is_likely_manga()`.

---

## 9. Pendientes / limitaciones conocidas

- **Autor sólo con `fetch_details`**: el planning no trae autor; sólo se obtiene haciendo un
  HTTP extra por ficha (`--fetch-details`), que el pipeline canónico NO activa. La mayoría
  de items quedan sin autor desde esta fuente.
- **Imágenes de resolución media**: las portadas salen de `img.sanctuary.fr/objet/300/…`; no
  hay forma confirmada de obtener hi-res desde el planning.
- **Rango de fechas fijo por default** (`2024-01` → mes actual): salidas anteriores a 2024
  no se capturan salvo que se pase `--wiki-from` manualmente.
- {{pendiente: confirmar si Manga-Sanctuary aparece como entrada propia en `sources.yml`.
  El módulo define su `_virtual_source()` internamente y se invoca vía `--bootstrap-wiki`;
  no se encontró una entrada en `sources.yml` con `manga-sanctuary`/`Manga-Sanctuary`, por
  lo que `kind`/`source_class`/tags de esta ficha salen del módulo, no del YAML.}}

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (igual que en el pipeline, deja raw):
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki manga-sanctuary --sleep-seconds 0.5 --min-score 20

# Rango de meses explícito (por default es 2024-01 → mes actual):
.venv/bin/python scripts/manga_watch.py \
    --bootstrap-wiki manga-sanctuary --wiki-from 2026-01 --wiki-to 2026-05 \
    --sleep-seconds 0.5 --min-score 20

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Debug: ver qué emite el parser para un mes (sin escribir a items.jsonl):
.venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); import requests, \
  wikis.manga_sanctuary as M; s=requests.Session(); \
  s.headers['User-Agent']='manga-watch/0.2'; \
  cs=M.fetch_planning_month(2026,5,s); \
  [print(f'[{c.score:3d}] {c.publisher[:18]:18s} · {c.title[:60]}') for c in cs[:15]]"

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "manga-sanctuary"
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

**Antes de cerrar cualquier cambio en Manga-Sanctuary**: validar (`validate_corpus`, 0
duras) → tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful,
actualiza esta ficha.
