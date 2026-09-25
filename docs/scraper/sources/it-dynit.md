# Fuente: Dynit

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-08-29 (recurrencia del flag no-manga; ver gotcha #155).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Dynit |
| **URL base** | `https://www.dynit.it/` |
| **Índice / punto de entrada** | `https://www.dynit.it/` |
| **Tipo de fuente** | Editorial (official) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | Italia |
| **Idioma(s)** | Italiano |
| **Cobertura** | Manga de Dynit Manga (catálogo italiano) |
| **Aporte al corpus** | 1 item |
| **Parser / módulo** | Entrada `"IT - Dynit"` en `sources.yml` (extractor genérico, sin parser propio) |

Editorial real en el corpus: **Dynit Manga** (1 item, país Italia). `publisher` = editorial
real, NO la tienda (#44).

**Por qué importa / qué aporta de único**: editorial oficial italiana; cubre el mercado IT
junto con las otras fuentes de Italia. Aporte actual muy bajo (1 item).

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda **WooCommerce** servida desde la home
  `https://www.dynit.it/`.
- **Estructura del HTML**: el extractor genérico recorre los productos del listado con los
  selectores declarados en `sources.yml`:
  - `item_selector`: `div.sc_extended_products_content`
  - `title_selector`: `.woocommerce-loop-product__title, h2, h3, a`
- **Identificador de producto**: URL del producto (sin parser propio que derive SKU/ISBN).
- **Anti-bot / quirks**: el sitio está detrás de **Cloudflare** para fetch plano
  (verificado 2026-07-07: headers `server: cloudflare` + `cf-mitigated: challenge` en
  algunos requests). El fetch del scraper funcionó normal en el run de hoy (13
  candidatos), pero es sensible a las heurísticas del WAF — si empieza a devolver
  0 items/challenge sin razón aparente, sospechar primero de Cloudflare antes que
  de un cambio de selectores.
- **Calidad de imágenes**: {{pendiente: no verificado para esta fuente}}.

---

## 5. Proceso de ingestión — técnico

- Fuente **simple del YAML**: entrada `"IT - Dynit"` en `sources.yml`, capturada en
  **FASE 1** del pipeline (`manga_watch.py` con `--workers 8`) vía el **extractor genérico**
  con los selectores de arriba. **No tiene parser propio** ni helper específico.
- Como cualquier fuente del YAML, los filtros y retrofits de cleanup (FASE 3) aplican igual.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Curación LLM non-manga 2026-08-23**: 2 items expulsados — el box de DVD de
  Madoka Magica (que además había entrado con el título "Sconto 10%", mismo
  síndrome de card corrupta que Funside Variant, ver `it-funside-variant.md`) y
  Harmagedon Limited Edition (Blu-Ray+DVD+booklet). Dynit es distribuidora de home
  video: su catálogo mezcla ediciones físicas de anime con libros.

---

## 9. Pendientes / limitaciones conocidas

- **Fechas DD/MM/YYYY crudas en `release_date`** — la ficha técnica del sitio entrega la fecha día-primero y los extractores la guardaban sin normalizar; desde 2026-06-12 `normalize_release_date()` la convierte a ISO en la ingestión y el corpus legacy se reparó con `normalize_release_dates.py` (gotcha #80). ✅
- **Aporte mínimo** (1 item). {{pendiente: confirmar si los selectores capturan todo el
  catálogo o sólo una fracción de la home — posible cobertura incompleta}}.
- **Cola "Disponibile dal: DD/MM/YYYY Dynit" pegada al título** (gotcha #94,
  2026-06-13): `title` quedaba "Isekai Editor (The) #03 Disponibile dal: 05/06/2026
  Dynit". Fix: `clean_title` corta desde "Disponibile dal:". 2 items.
- **Badge de descuento capturado como título (2026-07-07, gotcha #115)**: el
  `title_selector` genérico (`.woocommerce-loop-product__title, h2, h3, a`) tomaba
  el PRIMER match dentro de la card — cuando el theme insertaba un badge de oferta
  ("Sconto 10%", "Sconto 5%") ANTES del título real, ese badge quedaba como `title`
  en 3 items. Fix: `_first_non_badge_title()` en `manga_watch.py` itera los matches
  y salta los que son badges de descuento (`_is_sale_badge()`). Los 3 items malos se
  auto-curan en el próximo scrape vía upsert (no hizo falta retrofit dedicado).
- **Cloudflare confirmado** (antes decía "sin verificar"): ver §2.
- **Calidad de imágenes** sin verificar para esta fuente.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "IT - Dynit"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "dynit.it"
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

## 2026-08-28 — la fuente trae home video (Blu-Ray/DVD), no material impreso

Delta diario (`logs/scrape-delta-2026-08-28-160959/`). Dos items marcados
`is_manga=false` por el LLM del skill de estandarización, pendientes en
`data/unmapped_series.jsonl` (reason `llm_non_manga`):

- `Manie Manie (Box Set Limited Edition) (Blu-Ray+Dvd+Booklet+Settei Book)`
- `Harmagedon Limited Edition (Blu-Ray+Dvd+Booklet+Settei Book)`

Causa: Dynit es distribuidora de **anime en home video**; sus "limited edition" son
box sets de Blu-Ray/DVD que incluyen un booklet o settei book como bonus. El término
de edición dispara el scorer, pero el producto no es una edición especial de manga
impreso — el libro es un extra dentro de un box de video.

**Para el owner (no aplicado):** evaluar un patrón de exclusión por formato
(`Blu-Ray`, `DVD`, `Box Set … Blu-Ray`) para esta fuente. Retorno: corta la re-ingesta
diaria de los box de video, que es el grueso de lo que Dynit aporta fuera de alcance.

## 2026-08-29 — vuelve a flaggearse, y esta vez el flag se PERDIÓ (gotcha #155)

Delta diario (`logs/scrape-delta-2026-08-29-110244/`). Los 2 items ya documentados en la entrada del 2026-08-28 (`Manie Manie (Box Set Limited Edition)` y `Harmagedon Limited Edition`, ambos box sets de Blu-Ray/DVD con booklet) volvieron a ser flageados por el LLM como no-manga.

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

## 2026-09-02 — dos defectos encontrados y cerrados (revisión de fuentes pedida por el owner)

La fuente tenía 6 items en el corpus y **3 de los 6 estaban mal**. Los dos mecanismos:

### 1. El `title_selector` capturaba el badge de descuento, no el título (gotcha #187)

Valor anterior: `".woocommerce-loop-product__title, h2, h3, a"`. La intención era una
cadena de fallbacks, pero **una lista CSS separada por comas matchea por orden en el
DOCUMENTO, no por el orden de la lista**: el `<span class="onsale">Sconto 10%</span>` vive
dentro de un `<a>` que precede al `<h2>`, así que la alternativa `a` ganaba siempre.
Verificado en vivo: las cards devolvían `"Sconto 10%"` / `"Sconto 5%"` / `None`.

Es el MISMO bug que Funside el 2026-08-24 — o sea reincidente en el repo.

- Fix: `title_selector: ".woocommerce-loop-product__title"` (selector único, verificado en
  vivo: devuelve `Harmagedon Limited Edition…`, `Yuka Kitagawa – Without Love…`, etc.).
- Item ya congelado reparado con `scripts/retrofit/fix_dynit_badge_titles_20260902.py`:
  `your-name-dynit-artbook-it` tenía `title: "Sconto 5%"` y su URL es
  `/prodotto/makoto-shinkai-your-name-artbook-libri/` — **es un artbook REAL de *Your
  Name***, así que se reparó el título (`Makoto Shinkai – Your Name – Artbook`), no se
  expulsó el item. Ojo con esto: un título basura no implica un item basura.

### 2. Dos box sets de home video pasaban el filtro (gotcha #188)

`Manie Manie (Box Set Limited Edition) (Blu-Ray+Dvd+Booklet+Settei Book)` y
`Harmagedon Limited Edition (Blu-Ray+Dvd+Booklet+Settei Book)` estaban vivos en el
corpus como si fueran manga. El título dice literalmente "soy un Blu-ray" y el filtro lo
leía como "soy un manga con un Blu-ray de regalo": el rescate `_bonus_context_near`
tomaba el `+` que sigue a `Blu-Ray` como marcador de bonus, cuando en realidad esa lista
`Blu-Ray+Dvd+Booklet+…` es el CONTENIDO de la caja y su primer elemento ES el producto.
Fix de mecanismo en `manga_watch.py` (`_BONUS_ROMANCE_AFTER_RE`), con tests. Los 2 items
quedaron expulsados.

**La fuente NO se deshabilitó ni se le cambió `purity`**: los otros 3 items son manga real
(*Isekai Editor* #03, *Torikae Baya* #03, *Honey Lemon Soda* #03) y Dynit publica manga
además de home video de anime. Con el selector corregido y el filtro de home video
arreglado, la fuente queda sana. **A vigilar**: la home mezcla catálogo de anime y manga
(las `<li>` traen clases `product_cat-anime` / `product_cat-blu-ray` que hoy no se leen);
si vuelve a colar home video por otra vía, esa taxonomía del propio sitio es el
discriminador natural.
