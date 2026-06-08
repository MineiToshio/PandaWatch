# Fuente: Mangavariant

> Catálogo de fuentes de PandaWatch. Esta es la ficha de **Mangavariant** — base
> de datos global comunitaria de variantes/ediciones especiales. Léela ANTES de
> tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

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

- **Stack del sitio**: WordPress + Yoast SEO. Sin Cloudflare ni JS-rendering: el
  parser usa `requests` normal sobre HTML estático.
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

Mangavariant se recorre **distinto** en full vs delta (dos modos de ingestión):

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script | `scripts/scrape_full.sh` (paso 2e) | `scripts/scrape_delta.sh` (fila YAML, fase 1) |
| Mecanismo | módulo wiki: `--bootstrap-wiki mangavariant` | fila `Global - Mangavariant` en `sources.yml`, `max_pages: 1` |
| Discovery | lee los **3 variant-sitemaps** (~2700 URLs) y parsea todas | recoge sólo las novedades que aparecen en la home `/variant/` |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Cuándo | refresh completo del catálogo de variantes | detectar variantes recién publicadas |

- En **FULL**, el paso 2e corre el bulk del sitemap completo (`--min-score 20`,
  timeout 1800s). El bootstrap se hace una vez (carga histórica) y luego se repite
  en cada full para re-sincronizar.
- En **DELTA**, el bootstrap NO corre; el incremental llega por la fila del YAML
  con `max_pages: 1`, que recoge lo nuevo de la home en la fase 1 (scrape de
  sources del YAML), sin re-recorrer los 2700.
- El rango año/mes que recibe `bootstrap()` se **ignora**: mangavariant no
  particiona por fecha, los sitemaps cubren todo (`iter_year_months` devuelve un
  único batch sólo por compat con el dispatcher).

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
  (sitemap completo, sólo en FULL). Cae en la fase 2 (wiki bootstraps) junto con
  el resto de wikis.
- **DELTA**: `scrape_delta.sh` NO corre el bootstrap; el incremental entra por la
  fila YAML `Global - Mangavariant` en la fase 1 (scrape de sources del YAML).
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

- **Sin precio ni URL de tienda**: por naturaleza de la fuente. Queda para el
  enrichment pass diferido (ver §8 y CLAUDE.md "URL como referencia").
- **País nuevo no mapeado**: si el sitio agrega un país fuera de `COUNTRY_MAP`,
  sus variantes entran sin país/idioma. No hay alerta automática; revisar al
  agregar.
- **Imágenes**: dependen de `og:image` / mini-galería; algunas variantes pueden
  traer portadas de baja resolución (mismo flujo de baja calidad que el resto).

---

## 10. Runbook / comandos útiles

```bash
# Bulk completo (sitemap, ~2700 — el que corre scrape_full paso 2e):
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki mangavariant \
    --sleep-seconds 0.3 --min-score 20

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
