# Fuente: Star Comics (Italia)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-08-29 (recurrencia del flag no-manga; ver gotcha #155).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Star Comics |
| **URL base** | `https://www.starcomics.com` |
| **Índice / punto de entrada** | `https://www.starcomics.com/categorie-fumetti/manga` (listado) + `https://www.starcomics.com/ricerca-fumetti?q={query}` (búsqueda por keyword) |
| **Tipo de fuente** | Editorial (`official`) — sitio oficial de Star Comics |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | Italia — fuente mono-país (va al `edition_key`) |
| **Idioma** | Italiano |
| **Cobertura** | Manga publicado por Star Comics en Italia: ediciones especiales, variant cover, celebration/anniversary editions, cofanetti, deluxe, collector, anime comics packs |
| **Aporte al corpus** | ~83 items (82 con publisher `Star Comics`) |
| **Parser / módulo** | Entradas en `sources.yml` (extractor genérico, sin módulo propio) |

**Por qué importa / qué aporta de único**: es el canal **oficial** de las
ediciones especiales italianas de Star Comics — variant cover, celebration y
anniversary editions, tribute variant/cover, cofanetti y collector. La fuente de
búsqueda (`ricerca-fumetti`) es la que más aporta: las variant cover y collector
salen casi todas de ahí.

---

## 2. Descripción técnica de la fuente

Son **dos entradas YAML** del mismo sitio (`starcomics.com`), ambas `enabled`,
publisher `Star Comics`, country Italia, `official`:

- **"IT - Star Comics Manga"** (`html`): listado de catálogo en
  `/categorie-fumetti/manga`, `max_pages: 15`. Usa el extractor genérico (sin
  `selectors` propios). Aporta ~7 items.
- **"IT - Star Comics (search)"** (`html`): `search_template`
  `https://www.starcomics.com/ricerca-fumetti?q={query}`, expandida por keyword
  (ver §5). Selectores:
  - `item_selector: div.fumetto-card`
  - `title_selector: .card-body`

**Detalle clave del selector `.card-body`** (la razón de no usar
`h4.card-title`): en `ricerca-fumetti`, `h4.card-title` trae **solo el nombre de
la serie**, sin la sub-edizione. El `.card-body` captura el bloque completo
`"<SERIE> n. <N>\n<EDIZIONE>\n<DATE>"` — la sub-edizione (Celebration, Variant
Cover, Anniversary, etc.) vive en un `span` hermano dentro del `.card-body`. Sin
esto, todas las variantes de un mismo número quedarían con título idéntico y se
perdería la edición.

- **Estructura de URLs**: producto y listado bajo `starcomics.com`; la búsqueda
  es `ricerca-fumetti?q=<keyword url-encoded>`.
- **Calidad de imágenes**: Star Comics sirve "otros volúmenes" en un
  **subdirectorio del folder de la cover** — relevante para el filtro multi-imagen
  (#31): la comparación de directorio padre es **exacta, no substring**, para no
  arrastrar covers de otros tomos a la galería del producto. **La página de detalle
  además incrusta DOS carruseles ajenos a la galería del producto**: "Altri volumi
  della serie" (otros tomos de la MISMA serie) y, más abajo, "Se ti è piaciuto prova
  anche:" (recomendación de OTRAS series — verificado en vivo 2026-07-07: 9 cards de
  9 productos distintos en un ejemplo real). Ambos viven dentro del `<main>` del
  producto; cuando la cover propia también vive en `/thumbnail/` (mismo subdir que
  esas cards), el filtro de directorio no las separa — hace falta detección
  estructural (ver §8, gotcha #31 actualizada).

---

## 5. Proceso de ingestión — técnico

Ambas entradas se scrapean en **FASE 1** del pipeline canónico
(`manga_watch.py --workers 8`, dentro de `scrape_delta.sh` / `scrape_full.sh`)
vía el **extractor genérico** del YAML. **No tiene parser propio.**

- **"IT - Star Comics (search)"** lleva `search_template` + `keywords`, así que
  `_expand_search_template()` en `manga_watch.py` la expande en **N fuentes
  virtuales**, una por keyword. Cada hija recibe:
  - `name`: `"IT - Star Comics (search) [search: <keyword>]"`
  - `url`: el template con `q=<keyword url-encoded>`
  - `tags`: los del padre + `["expansion", "search:<keyword>"]`
  - El `source_purity` del padre **se propaga** a las hijas (#7).
- **Keywords activas** (probadas a mano; las que daban 0 resultados —`edizione
  limitata/speciale`, `esclusiva`, `metal edition`, `prima tiratura`, `final
  edition`— se eliminaron): `deluxe`, `cofanetto`, `variant`, `variant cover`,
  `variant cover edition`, `celebration edition`, `anniversary edition`,
  `tribute variant`, `tribute cover`, `tiratura limitata`, `collector`,
  `anime comics pack`.
- Distribución real por keyword en el corpus: `variant cover` (40),
  `collector` (12), `variant` (7), `celebration edition` (6),
  `anniversary edition` (5), `cofanetto` (3), `deluxe` (3); más ~7 del listado
  "IT - Star Comics Manga".
- Después de FASE 1 corren los retrofits de cleanup (rescore → filtros →
  clean_titles → backfill imágenes) como en cualquier fuente del YAML.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Fechas DD/MM/YYYY crudas en `release_date`** — la ficha técnica del sitio entrega la fecha día-primero y los extractores la guardaban sin normalizar; desde 2026-06-12 `normalize_release_date()` la convierte a ISO en la ingestión y el corpus legacy se reparó con `normalize_release_dates.py` (gotcha #80). ✅
- **#7**: `source_purity` se propaga a las hijas search-template vía
  `_expand_search_template()`. ✅
- **#31**: multi-imagen — Star Comics sirve "otros volúmenes" en un subdirectorio
  del folder de la cover; el filtro descarta gallery por **directorio padre
  EXACTO** (no substring), si no se contaminaría la galería con otros tomos. ✅
- **Selector `.card-body` en vez de `h4.card-title`** — el `h4` solo trae la
  serie; la sub-edizione está en un `span` hermano. Sin `.card-body` se perdían
  las variantes. ✅
- **Keywords con 0 resultados eliminadas** — `edizione limitata/speciale`,
  `esclusiva`, `metal edition`, `prima tiratura`, `final edition`. Re-verificar
  caso por caso si se quieren re-añadir tras nuevos lanzamientos.
- **Bug de galería: la grilla "otros volúmenes" contaminaba el carrusel del producto
  (2026-07-07, gotcha #31 actualizada)**: las páginas de detalle incrustan "Altri
  volumi della serie" + "Se ti è piaciuto prova anche:" (recomendaciones de otras
  series) DENTRO del scope del producto. Cuando la cover propia del producto también
  vive en `/files/immagini/fumetti-cover/thumbnail/` (mismo subdirectorio que esas
  cards), el filtro de "directorio padre exacto" (#31 original) no las distinguía —
  ambos viven en el mismo folder, así que no había señal de path que los separara.
  Los thumbnails de esas grillas (covers reales de OTRAS series — Blue Box, Dragon
  Ball, One Piece, etc.) terminaban en la galería del producto scrapeado. Fix
  estructural (no síntoma): `_related_grid_card_ids()` detecta la grilla por FORMA
  (≥3 product-cards que enlazan a ≥3 páginas de producto distintas) y las excluye
  del harvest, sin importar en qué carpeta viva la imagen. El purge de este bug
  limpió **29 entradas contaminadas** del corpus. ✅
- **Curación LLM non-manga 2026-08-23**: 11 items expulsados — variant covers de
  Valiant (X-O Manowar, Bloodshot, Harbinger, Britannia, Faith) coladas por los
  searches `?q=variant` y `?q=collector`, más Rabbids, "300", Barnstormers, La
  Casta dei Meta-Baroni y The Plot Holes. Los searches traen el catálogo NO-manga
  completo de la editorial, sin filtro adicional en la query.

---

## 9. Pendientes / limitaciones conocidas

- **"IT - Star Comics Home"** (`https://www.starcomics.com/`,
  `item_selector: div.fumetto-card`, `title_selector: "h3, h4, a, .card-title"`)
  está **`enabled: false`** (audit 2026-05-25: 0 items). Es la home de noticias;
  no aporta productos. Queda en el YAML como referencia, fuera del pipeline.
- Re-validar las keywords periódicamente: `ricerca-fumetti` devuelve 0 para
  varias frases que antes sí daban resultados; la lista activa es la que rinde
  hoy, no una garantía a futuro.

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (deja items.jsonl en raw):
.venv/bin/python scripts/manga_watch.py --only-source "IT - Star Comics Manga"
.venv/bin/python scripts/manga_watch.py --only-source "IT - Star Comics (search)"

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "starcomics.com"
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
(`validate_corpus`, 0 duras) → tests (`pytest tests/test_extraction.py`) → build.
Si tocaste algo meaningful, actualiza esta ficha.

## 2026-08-28 — la búsqueda `variant` trae cómic occidental (2 items a curación)

Delta diario (`logs/scrape-delta-2026-08-28-160959/`). La query de búsqueda
`[search: variant]` devolvió 2 items que el LLM del skill de estandarización marcó
`is_manga=false` y quedaron pendientes en `data/unmapped_series.jsonl`
(reason `llm_non_manga`):

- `FAITH n. 1 HOLLYWOOD E LA VIGNA - VARIANT COVER` — cómic italiano, no manga.
- `300 VARIANT EDITION` — cómic americano (Frank Miller).

Causa: el término `variant` es agnóstico de medio; Star Comics publica también línea
de cómic occidental y la búsqueda no distingue. Ojo: `data/comics_blacklist.yml` ya
tiene `"300 di Frank Miller"` y `"Frank Miller's 300"`, pero **no** matchean el título
pelado `300 VARIANT EDITION` — es el mismo patrón de gotcha #154 (veredicto LLM que no
expulsa + gate determinista que no matchea = el item vuelve a entrar cada corrida).

**Para el owner (no aplicado):** agregar `"300 VARIANT EDITION"` y `"FAITH"` (o el
patrón de serie correspondiente) a `data/comics_blacklist.yml`. Retorno: corta la
re-ingesta diaria de estos 2 y deja de gastar LLM en ellos cada día.

## 2026-08-29 — vuelve a flaggearse, y esta vez el flag se PERDIÓ (gotcha #155)

Delta diario (`logs/scrape-delta-2026-08-29-110244/`). Los 2 items ya documentados en la entrada del 2026-08-28 (`FAITH n. 1 HOLLYWOOD E LA VIGNA - VARIANT COVER`, de Valiant, y `300 VARIANT EDITION`, de Frank Miller) volvieron a entrar por el search `?q=variant` y volvieron a ser flageados por el LLM como no-manga.

Dos cosas que agrega esta corrida:

1. **La recurrencia está confirmada**: el gate LLM de `/watch-standardize-catalog`
   vuelve a marcar exactamente el mismo material, y los gates deterministas
   (`filter_non_manga`/`filter_collectible`) vuelven a no expulsarlo, así que sigue
   contando como manga en el corpus. El patrón es el de gotcha #154 (veredicto LLM que
   no expulsa + gate determinista que no lo cubre), estable corrida a corrida.
2. **El flag se destruyó el mismo día**: el pase de `/watch-enrich-series-aliases` que
   corrió después trunca `data/unmapped_series.jsonl` entero (gotcha #155), así que las
   filas `llm_non_manga` de esta corrida desaparecieron de la cola de curación sin que
   nadie las revisara. Sobreviven sólo en
   `data/backups/unmapped_series.jsonl/unmapped_series.jsonl.pre-enrich-bak`, que rota.

Consecuencia práctica: mientras las dos etapas corran en ese orden, **este material se
va a re-flaggear y re-perder todos los días**, y la cola nunca acumula la evidencia que
haría falta para justificar un fix. No se tocó ninguna configuración de la fuente.

## 2026-08-30 — recurrencia nº4, pero esta vez el flag SOBREVIVIÓ

Delta diario (`logs/scrape-delta-2026-08-30-111729/`). El search `[search: variant]`
volvió a inyectar cómic occidental al corpus. Dos items nuevos, ambos flageados
`llm_non_manga` por `/watch-standardize-catalog` y ambos **no expulsados** por los gates
deterministas (patrón de gotcha #154):

- `FAITH n. 1 HOLLYWOOD E LA VIGNA - VARIANT COVER` — Valiant (US), 2016-11-16.
  Quedó en el corpus como `product_type: manga`, `edition: Variant (Star Comics)`,
  `series_display: Faith Hollywood E La Vigna`.
- `300 VARIANT EDITION` — Frank Miller / Dark Horse (US), 2023-10-31. Quedó en el corpus
  como `product_type: manga` y **sin `series_display` ni `edition_display`**.

Causa: el término de búsqueda `variant` es vocabulario de **tipo de edición**, no de
manga, así que matchea todo el catálogo de licencias occidentales que Star Comics
distribuye en Italia (Valiant, Dark Horse). La fuente no declara `purity`, así que el
default `manga_only` no exige STRONG manga hint y nada los filtra.

**Diferencia con el 08-29**: esta corrida NO ejecutó `/watch-enrich-series-aliases`
(ver el reporte del run), así que las filas `llm_non_manga` **siguen vivas** en
`data/unmapped_series.jsonl` — por primera vez la cola conserva la evidencia en lugar de
perderla el mismo día por gotcha #155.

**Para el owner (no aplicado — cambio de configuración):** las opciones siguen siendo
(a) agregar los términos de estas licencias a `data/comics_blacklist.yml` — barato pero
incremental, una serie por vez; o (b) acotar el search de esta fuente para que no barra
el catálogo occidental. Retorno: corta la re-ingesta diaria de material fuera de alcance.

## 2026-08-31 — recurrencia nº5: los mismos dos títulos, quinto día

Delta diario (`logs/scrape-delta-2026-08-31-110202/`). Sin filas nuevas, pero
`FAITH n. 1 HOLLYWOOD E LA VIGNA - VARIANT COVER` y `300 VARIANT EDITION` **siguen
vivos en el corpus** desde el 08-28, los dos como `product_type: manga` /
`edition_display: Variant (Star Comics)`. Ambos son cómic occidental (Valiant y el
300 de Frank Miller).

El search `variant` de esta fuente aporta además 26 filas huérfanas y 32 vivas a la
cola de aliases de este run.

Nada aplicado: la vía (acotar el search `variant` o agregar los títulos a la comics
blacklist) es decisión del owner.

## 2026-09-02 — recurrencia nº6: los mismos dos títulos entran otra vez como items NUEVOS

Delta diario (`logs/scrape-delta-2026-09-02-110142/`). Esta vez `FAITH n. 1 HOLLYWOOD E
LA VIGNA - VARIANT COVER` y `300 VARIANT EDITION` no sólo siguen vivos: aparecen con
`detected_at` de ESTE run, o sea vuelven a contarse como descubrimientos del día. Los dos
quedaron re-flageados `llm_non_manga` / `non_manga_comic` por el skill de estandarización.

Confirma el mecanismo de gotcha #154 en su forma más cara: el veredicto del LLM no
expulsa (por diseño, desde 2026-07-07), los gates deterministas de la FASE 3 tampoco los
ven (son `manga_only`, sin STRONG hint exigido), así que cada corrida los re-descubre,
los re-estandariza gastando LLM y los re-apila en la cola. Seis días seguidos.

Nada aplicado: acotar el search `variant` o sumar los términos a `data/comics_blacklist.yml`
sigue siendo decisión del owner.

### RESUELTO el mismo día (2026-09-02) — el owner pidió arreglar las fuentes

Los dos títulos quedaron EXPULSADOS del corpus y el mecanismo cerrado. Detalle:

- `300 VARIANT EDITION` → keyword `"300 Variant Edition"` en `data/comics_blacklist.yml`.
  **Deliberadamente la frase completa, NO "300" pelado**: se midió contra el corpus y
  `300` a secas mataba dos manga reales (*300 jours avec toi*, FR, y *Ich habe 300 Jahre
  lang Schleim getötet*, DE). Hay un test permanente
  (`test_bare_300_is_not_blacklisted`) que frena a quien intente agregarlo pelado.
- `FAITH n. 1 HOLLYWOOD E LA VIGNA` → por vía NUEVA: `is_comic_not_manga()` ahora también
  busca franquicias en el **slug de la URL**. El título no delata nada, pero la URL es
  `/fumetto/valiant-variant-cover-29-faith-1` y Valiant es editorial de cómic
  estadounidense. Se agregó `"Valiant"` al blacklist; matchea 1 item, 0 por título.
  Se evitó agregar `"Faith"` (palabra demasiado común). Ver gotchas #189.

**El search `variant` NO se acotó, y fue una decisión con datos, no por omisión**: la
fuente tiene 129 items en el corpus y son ~98% manga real (Gachiakuta, Kagurabachi, One
Piece, My Hero Academia, Dr. Stone, Kaiju No. 8…). Acotar el search habría costado mucho
más de lo que ahorraba. Con ~2% de contaminación por franquicias occidentales concretas,
el blacklist ES la herramienta proporcionada. Esto **corrige la recomendación del reporte
matinal del 09-02**, que proponía acotar el search antes de medir la composición real.

---

## 2026-09-03 — ruido en `author`: el selector cae a fragmentos del título

**Hallazgo del delta diario** (secundario al caso grave de Funside, ver
`it-funside-variant.md` § 2026-09-03). En esta fuente el `author` **mayormente funciona**
(Mirka Andolfo, Frank Miller, Boichi, Tatsuki Fujimoto, Yukito Ayatsuji… son correctos),
pero un subconjunto sale mal:

| Valor capturado como "autor" | veces | qué es en realidad |
|---|---|---|
| `IT-AL` | 8 | código de región/idioma |
| `STICKER JANKU VARIANT n` | 2 | fragmento del título |
| `KAPPA LIMITED n` | 2 | fragmento del título (nombre de colección) |
| `THEO VALIANT VARIANT COVER n` | 1 | fragmento del título |
| `Rave` | 2 | nombre de la SERIE, no del autor |
| `Tanjiro` | 1 | nombre de un PERSONAJE |
| `TUTTO IL MONDO` | 1 | fragmento del título |

Dos defectos distintos mezclados:

1. **Fallback al documento** — cuando la ficha no tiene autor, el selector agarra lo
   primero que matchea en la página (misma clase de defecto que la gotcha #187 y que
   Funside). Ahí salen `IT-AL` y los fragmentos en mayúsculas.
2. **Confusión serie/personaje ↔ autor** — `Rave`, `Tanjiro`: la fuente pone en ese campo
   la franquicia, no el autor.

### Impacto

**Muy bajo.** ~17 filas sobre una fuente de ~98% manga sano; `author` no entra en
`cluster_key`/`edition_key` ni en los gates. Sólo ensucia la ficha de detalle.

### Recomendación (NO aplicada)

Va junto con el fix de Funside: **acotar el selector de autor al contenedor de la ficha**
en lugar del documento entero. No amerita una intervención propia — si se arregla el
mecanismo para Funside, esta fuente se cura de arrastre. Un `author` vacío es preferible
a uno falso.
