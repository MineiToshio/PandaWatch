# Fuente: Mangavariant

> Catálogo de fuentes de PandaWatch. Esta es la ficha de **Mangavariant** — base
> de datos global comunitaria de variantes/ediciones especiales. Léela ANTES de
> tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-07-07 (delta INCREMENTAL implementado — mangavariant ya no es full-only).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Mangavariant (`Global - Mangavariant` en `sources.yml`) |
| **URL base** | `https://mangavariant.com` |
| **Índice / punto de entrada** | 3 sitemaps: `variant-sitemap.xml`, `variant-sitemap2.xml`, `variant-sitemap3.xml` (~2700 URLs) · home incremental: `https://mangavariant.com/variant/` |
| **Página de una variante** | `https://mangavariant.com/variant/<manga-slug>/<variant-slug>/` |
| **Tipo de fuente** | Catálogo comunitario / base de datos (NO es tienda — no expone precio ni botón de compra) |
| **`kind` en sources.yml** | `html` (incremental) · módulo wiki `mangavariant` (bulk) |
| **`source_class`** | `trusted_media` |
| **Países** | Global (multi-país): el país real va por item al `edition_key` (ver §1, abajo) |
| **Idioma(s)** | Multi-idioma (el idioma se deriva del país de cada variante; EN como idioma nominal del sitio) |
| **Cobertura** | ~2700 variantes/ediciones especiales catalogadas en 13 países |
| **Aporte al corpus** | ~1580 items |
| **Parser / módulo** | [`scripts/wikis/mangavariant.py`](../../../scripts/wikis/mangavariant.py) + fila YAML `Global - Mangavariant` |

**Países que abarca** (de `COUNTRY_MAP` en el módulo; entre paréntesis, volumen
real en el corpus): Japón (≈692) · Francia (≈312) · Italia (≈242) · Vietnam
(≈137) · Estados Unidos (≈64) · Tailandia (≈54) · Alemania (≈48) · Argentina
(≈10) · Brasil (≈7) · Taiwán (≈7) · España (≈6) · México (≈1). Cada país mapea a
su idioma (`jp`→Japonés, `fr`→Francés, etc.). Nota: el slug de México es `mexico`,
NO `mx` (Yoast usa el nombre largo).

**Editoriales que abarca** (de campo `Published by`, top del corpus): Shueisha
(≈193) · Square Enix (≈109) · Kodansha (≈92) · Kim Dong (≈90) · Kana (≈82) ·
J-Pop (≈79) · Kadokawa Shoten (≈66) · Pika Edition (≈60) · Akita Shoten (≈54) ·
Planet Manga (≈54) · Shogakukan (≈39) · IPM (≈37) · Kurokawa (≈35) · ASCII Media
Works (≈33) · VIZ Media (≈25) · Kazè/Crunchyroll (≈25) · Luckpim (≈25) · Ki-oon
(≈23) · Hakusensha (≈20) · Goen (≈20), entre otras. El `publisher` es la editorial
real del campo `Published by`, NO una tienda (#44).

**Por qué importa / qué aporta de único**: es la **única fuente global** del
proyecto enfocada exclusivamente en variantes y ediciones especiales. Cataloga
qué variantes EXISTEN en el mundo (Crunchyroll variant, ediciones de Natsucomi /
Comiket, steelbox, aniversarios), incluyendo mercados poco cubiertos por las
demás fuentes (Vietnam, Tailandia, Taiwán, Japón). Es 100% curada: cada entrada
ES un variant por definición, así que no pasa por `is_likely_manga` ni
`is_collectible_edition` — el scorer general la puntúa por las señales del título
y las notas. Es fuente de **descubrimiento**, no de compra (ver §8).

---

## 2. Descripción técnica de la fuente

- **Stack del sitio**: WordPress + Yoast SEO, hosteado en SiteGround. Desde
  ~2026-06 TODO el sitio (sitemaps incluidos) está detrás de un **challenge JS
  sgcaptcha** (ver sección 2026-06-12 abajo): el módulo lo resuelve UNA vez con
  Playwright y después sigue con `requests` normal sobre HTML estático.
- **Estructura de URLs**: `/variant/<manga-slug>/<variant-slug>/`. Los 3
  `variant-sitemap*.xml` (de `sitemap_index.xml`) listan las ~2700 URLs. El
  filtro de discovery sólo acepta URLs con dos segmentos bajo `/variant/`
  (descarta la home `/variant/`).
- **Estructura del HTML** (detail page): bloque
  `<div class="variant_info_block">` con campos `<strong>label:</strong>`:
  - `Published by:` → editorial (texto plano).
  - `Country:` → `/variant?country=<slug>` (de ahí sale país + idioma vía `COUNTRY_MAP`).
  - `Manga:` → `/manga/<series-slug>` — la **serie real**.
  - `Where:` → `/where/<slug>` (Comiket, Steelbox, Natsucomi…).
  - `Release:` → **sólo año** (4 dígitos); no hay día/mes.
  - `Tags:` → tags de la variante (`/variant?tags=<slug>`).
  - `<a class="v_rarity_icon" href="…rarity=<tier>">` → rareza.
  - `<div class="vInfo notes">` → descripción libre.
  - **Título visible** (`og:title`, sin el sufijo ` - mangavariant.com`) = sólo el
    nombre de la edición (p.ej. "Vol.34 - Crunchyroll variant"). El parser
    concatena `<Serie> — <Edición>` para que el `title` tenga la serie y los
    filtros / `cluster_key` / búsqueda del dashboard funcionen como con cualquier
    otra fuente.
- **Identificador de producto**: la URL canónica `/variant/<manga>/<variant>/`.
- **Calidad de imágenes**: la portada principal sale de `og:image`. Si la detail
  page trae mini-galería en `.entry-content img`, se usa el extractor común
  (`_extract_images_from_detail_soup`) y se guardan todas. Placeholders/lazy se
  manejan con la lógica estándar (#6).

---

## 3. Proceso de ingestión — vista de producto

> Mangavariant es 100% curada: cada página de variante ES, por definición, una
> edición especial. No hay decisión de "¿esto es coleccionable?" — entra todo lo
> que sea una variant page válida con serie identificada.

1. **Reunir las URLs de variantes** (de los 3 sitemaps, en el bulk; o de la home
   `/variant/`, en el incremental).
2. **Abrir cada página de variante** y leer su bloque de información.
3. **Quedarse con la variante** si tiene serie identificada (campo `Manga`). El
   `title` queda como `<Serie> — <Edición>`; el país, idioma y editorial se toman
   de la propia página.
4. **Descartar** si no parece una variant page válida (404, redirect a home,
   página de `/manga/` en vez de `/variant/`, o sin serie).
5. **Repetir** hasta agotar la lista de URLs.

**Reglas de producto que nunca se rompen:**
- **País = edición** (#46): el país de cada variante es el de su edición
  (editorial/idioma), no el de una tienda; va al `edition_key`.
- Sin serie identificada → la variante NO entra (no tiene utilidad downstream).
- El nombre de la edición NO se traduce; sólo se concatena con la serie.

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

Mangavariant se recorre **en AMBOS modos**, con distinto discovery (dos modos del
MISMO módulo `wikis/mangavariant.py`; el delta ya no es full-only desde 2026-07-07):

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script | `scripts/scrape_full.sh` (paso 2e) | `scripts/scrape_delta.sh` (paso 2t) |
| Mecanismo | `--bootstrap-wiki mangavariant` | `--bootstrap-wiki mangavariant` + `MANGAVARIANT_INCREMENTAL=1` |
| Discovery | lee los **3 variant-sitemaps** (~2700 URLs) y parsea **todas** | lee los mismos sitemaps y parsea **sólo las URLs que NO están ya en `items.jsonl`** (diff contra el corpus), ordenadas por `lastmod` desc, con tope `MANGAVARIANT_MAX_NEW` (default 400) |
| Costo | ~2700 detail pages | fijo (sitemaps + 1 challenge) + hasta `max_new` detail pages |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Cuándo | refresh completo del catálogo de variantes | detectar variantes recién publicadas |

- En **FULL**, el paso 2e corre el bulk del sitemap completo (`--min-score 20`,
  timeout 1800s). El bootstrap se hace una vez (carga histórica) y luego se repite
  en cada full para re-sincronizar.
- En **DELTA**, el paso 2t corre el **modo incremental** (`MANGAVARIANT_INCREMENTAL=1`,
  timeout 1200s): baja los sitemaps (costo fijo) y hace `nuevas = urls_sitemap −
  urls_ya_en_corpus`. Fetchea el detalle SÓLO de esas nuevas, priorizadas por
  `lastmod` desc (las recién publicadas primero) y acotadas por `max_new`. Esto
  captura las ediciones variantes nuevas sin bajar el catálogo entero.
- El rango año/mes que recibe `bootstrap()` se **ignora**: mangavariant no
  particiona por fecha, los sitemaps cubren todo (`iter_year_months` devuelve un
  único batch sólo por compat con el dispatcher).

**Cómo funciona el diff (implementación 2026-07-07).** `fetch_variant_url_entries`
baja los sitemaps y devuelve `(loc, lastmod)` por variante. `load_seen_variant_urls`
lee `items.jsonl` una vez y arma el set de claves canónicas ya vistas
(`_norm_variant_url` = `/variant/<manga>/<variant>` en minúsculas, ignora
esquema/host/query/slash final; cubre `url` top-level y `sources[].url`).
`_select_incremental_urls` se queda con las URLs cuya clave NO está en el corpus,
ordena por `lastmod` desc y aplica `max_new` (si se topa, LOGuea explícito — nada
de truncar en silencio). Como `manga_watch.py` no expone flags para esto (el
dispatcher pasa un set fijo de kwargs), el modo se selecciona con **variables de
entorno** (`MANGAVARIANT_INCREMENTAL`, `MANGAVARIANT_MAX_NEW`, `MANGAVARIANT_SINCE`,
`MANGAVARIANT_ITEMS_PATH`), sin tocar el dispatcher.

**Por qué el orden por `lastmod` importa.** El corpus tiene ~1604 variantes
canónicas pero el sitemap lista ~2700 URLs: la brecha (~1100) son mayormente URLs
que el parser RECHAZA (sin serie) y que NUNCA entran al corpus, así que SIEMPRE
parecen "nuevas". Ordenando por `lastmod` descendente, el presupuesto `max_new` se
gasta en las variantes **recién publicadas** (lastmod fresco), no re-fetcheando los
viejos rechazos en cada corrida. Si el `lastmod` viniera vacío/basura, la corrección
se mantiene (solo-nuevas): sólo cambia el orden dentro del tope.

**Veredicto sobre `lastmod` (Yoast).** Es **por-entrada** (modified_time del post de
cada variante; la fixture `sitemap_sample.xml` muestra timestamps variados por URL) —
por eso es útil como sort key de recencia y, opcionalmente, como filtro de
"actualizadas" vía `MANGAVARIANT_SINCE` (re-fetch de URLs YA vistas con `lastmod >
since`). Se deja **opt-in** (default off) porque `lastmod` también se mueve ante
ediciones menores (typo, cambio de imagen), así que como filtro de novedad es ruidoso;
el diff-contra-corpus es la señal robusta y siempre-activa. El sitemap sigue detrás
del challenge sgcaptcha, así que el diff/filtrado ocurre DESPUÉS de resolverlo (el
módulo ya lo maneja). **Trade-off cerrado**: antes las novedades tardaban hasta ~3
meses (entre dos fulls); ahora entran en el delta diario/semanal.

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/mangavariant.py`](../../../scripts/wikis/mangavariant.py).

### 5.1 Modelo de datos / claves

- **Source sintética** (`_virtual_source`): `name="Global - Mangavariant"`,
  `source_class="trusted_media"`, `kind="wiki"`, `purity="manga_only"`. Los campos
  `country` / `language` / `publisher` se **sobreescriben por item** (vienen de la
  propia página de la variante), no son fijos de la fuente.
- **País / idioma** se derivan del slug `Country:` vía `COUNTRY_MAP` (13 países).
  País distinto = edición distinta (#46): el país entra al `edition_key`.
- **Identidad del producto** = URL canónica `/variant/<manga>/<variant>/`.
- **Tags discriminantes** que el parser agrega al candidate: `country:<slug>`,
  `rarity:<tier>`, `where:<slug>`, `mv-series:<series-slug>`, `mv-tag:<tag>`.

### 5.2 Qué captura el parser (mapea el §3 al código)

- `fetch_variant_urls()` → baja los 3 sitemaps, devuelve URLs `/variant/x/y/` únicas.
- `fetch_variant_url_entries()` → igual pero devuelve `(loc, lastmod)` por variante
  (para el diff incremental / sort por recencia).
- `load_seen_variant_urls(items_path)` → set de claves canónicas ya en el corpus.
- `_select_incremental_urls(entries, seen, since, max_new)` → decide qué fetchear en
  el delta (solo-nuevas + opcional updated-since, ordenadas por lastmod, cap).
- `parse_variant_detail(html, url)` → un `Candidate` por variant page:
  - `og:title` (sin sufijo Yoast) = nombre de edición; `Manga` = serie;
    `title = "<Serie> — <Edición>"`.
  - `Published by` → `publisher`; `Country` → país/idioma; `Release` → año
    (`release_date`); `Where` / `Tags` / `notes` → `description` (para que
    `detect_signals` y el scorer tengan contexto).
  - Rechaza si no es variant page válida (HTML < 1000 chars, falta
    `variant_info_block`, `og:type` no article/website, o **sin serie**).
  - **No** pasa por `is_likely_manga` ni `is_collectible_edition` (es 100%
    curada); sólo `score_candidate()`.
- `bootstrap(...)` → orquesta el bulk con `ThreadPoolExecutor` (`--workers`),
  `flush_fn` cada 100 candidates.

### 5.3 Flujo end-to-end

- **FULL**: `scrape_full.sh` paso **2e** corre `--bootstrap-wiki mangavariant`
  (sitemap completo). Cae en la fase 2 (wiki bootstraps) junto con el resto.
- **DELTA**: `scrape_delta.sh` paso **2t** corre el MISMO bootstrap con
  `MANGAVARIANT_INCREMENTAL=1 MANGAVARIANT_MAX_NEW=400` (diff contra el corpus,
  timeout 1200s). También en la fase 2.
- Luego pasa por los cleanup retrofits y el build como cualquier otra fuente.
- ⚠️ Tras un scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr
  el skill `/watch-standardize-catalog` automáticamente.

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural, aplica a TODO el corpus
  (no hay auditoría dedicada de mangavariant). Verificá `PAIS` (todo
  `edition_key` con país conocido) y `SLUG`.
- Como prueba de cordura del parser, correr el módulo directo con `--max-items`
  (ver §10) y confirmar que emite candidates con país/serie correctos.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **URL como referencia (decisión, no bug)**: mangavariant NO es retailer — sus
  páginas no tienen precio ni botón de compra. Igual es una fuente **válida y de
  primera clase**: el objetivo de PandaWatch es **descubrimiento**, no siempre
  compra (ver "URL como referencia" en CLAUDE.md). Un paso de enrichment futuro
  (`enrich_references.py`, diferido) buscaría la URL de tienda y la agregaría a
  `sources[]`; NO es filtro upstream.
- **Slug de país largo**: el slug de México es `mexico`, no `mx` (Yoast usa el
  nombre largo). ✅ contemplado en `COUNTRY_MAP`. Si aparece un país nuevo en el
  sitio sin entrada en el map, su variante entra sin país/idioma → revisar el map.
- **Serie obligatoria**: variantes sin campo `Manga` se descartan (sin serie no
  hay título útil ni cluster). ✅ por diseño.
- **Sólo año en `Release`**: mangavariant no expone día/mes; `release_date` lleva
  sólo el año. No se intenta inferir más.

---

## 9. Pendientes / limitaciones conocidas

- **Delta incremental (IMPLEMENTADO 2026-07-07, ver §4)**: el delta ya trae
  novedades vía diff-contra-corpus (solo-nuevas, orden por `lastmod`, tope
  `max_new`). El filtro por `lastmod > since` queda **opt-in** (`MANGAVARIANT_SINCE`)
  porque como señal de novedad es ruidoso. Limitación residual: las URLs que el
  parser rechaza (sin serie) nunca entran al corpus y re-aparecen como "nuevas" cada
  corrida — mitigado por el orden por recencia (se fetchean las frescas primero) y el
  tope, pero pueden consumir parte del presupuesto si no hay muchas novedades reales.
- **Sin precio ni URL de tienda**: por naturaleza de la fuente. Queda para el
  enrichment pass diferido (ver §8 y CLAUDE.md "URL como referencia").
- **País nuevo no mapeado**: si el sitio agrega un país fuera de `COUNTRY_MAP`,
  sus variantes entran sin país/idioma. No hay alerta automática; revisar al
  agregar.
- **Imágenes**: dependen de `og:image` / mini-galería; algunas variantes pueden
  traer portadas de baja resolución (mismo flujo de baja calidad que el resto).
- **Playwright ahora es requisito de AMBOS modos**: tanto el bulk del FULL como el
  incremental del DELTA bajan los sitemaps detrás del challenge sgcaptcha. Sin
  `playwright` + Chromium instalados el bootstrap degrada con WARN e importa 0 (el
  challenge no se puede resolver). El módulo lo resuelve UNA vez y reusa las cookies.

---

## 10. Runbook / comandos útiles

```bash
# Bulk completo (sitemap, ~2700 — el que corre scrape_full paso 2e).
# Requiere Playwright instalado (resuelve el challenge sgcaptcha una vez):
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki mangavariant \
    --sleep-seconds 0.3 --min-score 20

# Incremental (delta paso 2t): solo variantes nuevas vs el corpus, tope 400.
# Selección por env vars (manga_watch.py no expone flags para esto):
MANGAVARIANT_INCREMENTAL=1 MANGAVARIANT_MAX_NEW=400 \
    .venv/bin/python scripts/manga_watch.py --bootstrap-wiki mangavariant \
    --sleep-seconds 0.3 --min-score 20
# (opcional) re-fetch de variantes actualizadas desde una fecha:
#   MANGAVARIANT_SINCE=2026-06-01T00:00:00+00:00

# Prueba local del modo incremental sin tocar el corpus (parser standalone):
.venv/bin/python scripts/wikis/mangavariant.py --incremental --max-new 20 --workers 4

# Prueba local del parser (sin tocar el corpus):
.venv/bin/python scripts/wikis/mangavariant.py --max-items 20 --workers 4

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "mangavariant"
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

**Antes de cerrar cualquier cambio en Mangavariant**: validar
(`validate_corpus`, 0 duras) → tests (`pytest tests/test_extraction.py`) → build.
Si tocaste algo meaningful, actualiza esta ficha.

## 2026-06-12 — sgcaptcha (SiteGround): challenge JS en TODO el sitio — ✅ resuelto en el bootstrap

El sitio entero (incluyendo `sitemap.xml`) devuelve **202** con un meta-refresh a
`/.well-known/sgcaptcha/` ante requests/UA de bot — challenge JS de SiteGround
(apareció ~2026-06; antes el sitio era requests-friendly). **Playwright SÍ lo pasa**
(headless Chromium, ~4-8 s la primera página; la cookie del challenge se reutiliza) —
verificado primero con `scripts/retrofit/recover_lost_jp_titles.py`.

**Solución implementada en `wikis/mangavariant.py`** (mismo día): resolver el
challenge **UNA vez** con Playwright y exportar las cookies del contexto **+ el
User-Agent real del browser** (la cookie va atada al UA) a la `requests.Session` —
el fetch concurrente con `ThreadPoolExecutor` queda intacto. Detalles:

- `_looks_like_challenge(resp)`: detecta 202 **o** el marker
  `/.well-known/sgcaptcha/` en el body (cubre el caso 200 + meta-refresh). Test:
  `test_mangavariant_detects_sgcaptcha_challenge`.
- `_solve_challenge_into_session(session)`: lanza Chromium headless, espera a que
  `page.title()` deje de ser "Loading…"/captcha (loop 15×2 s), exporta cookies + UA.
  Si Playwright no está instalado: WARN y degrada (el run importará 0, no crashea).
- `_resolve_challenge(session, seen_generation)`: re-solve bajo lock con contador de
  generación — si la cookie expira a mitad del run, UN worker re-resuelve y los demás
  reusan; el snapshot de generación se toma ANTES del request para no re-resolver de más.
- Tanto `fetch_variant_urls` (sitemaps) como `_fetch_one` (detail pages) detectan el
  challenge y hacen un retry tras el solve.
- **Gotcha #12 no aplica**: Playwright se lanza y se cierra COMPLETO dentro del thread
  que lo invoca (one-shot autocontenido); el worker dedicado de manga_watch.py es para
  fetches Playwright repetidos, no para esto.
- Verificado en vivo (2026-06-12): 1 solve (5 cookies) → 2679 URLs de sitemap →
  12/12 detail pages parseadas con requests concurrente, sin re-solve.

✅ **Actualización 2026-07-07**: el DELTA ya no depende de la home `/variant/` ni de
la fila YAML genérica. Ahora corre el MISMO módulo `wikis/mangavariant.py` en modo
incremental (paso 2t de `scrape_delta.sh`, `MANGAVARIANT_INCREMENTAL=1`), que reusa
el manejo de challenge del bulk (resuelve una vez, cachea cookies) y baja los mismos
sitemaps — así que ya NO trae 0 por el challenge. Sólo fetchea el detalle de las URLs
nuevas (diff contra `items.jsonl`). Ver §4.

Además: hay items viejos en el corpus con la URL de mangavariant TRUNCADA (~80 chars,
bug de sesiones LLM tempranas, ej. `…/vol-10-spec`) — esas fichas dan 404 y no van a
re-mergear con el item del sitemap (URL distinta); el dedup por cluster_key los cubre
si la serie/edición coincide.

Además: hay items viejos en el corpus con la URL de mangavariant TRUNCADA (~80 chars,
bug de sesiones LLM tempranas, ej. `…/vol-10-spec`) — esas fichas dan 404 y no van a
re-mergear con el item del sitemap (URL distinta); el dedup por cluster_key los cubre
si la serie/edición coincide.
