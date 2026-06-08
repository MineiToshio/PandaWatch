# Fuente: blogbbm (Biblioteca Brasileira de Mangás)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Biblioteca Brasileira de Mangás (BBM) |
| **URL base** | `https://blogbbm.com` |
| **Índice / punto de entrada** | Conjunto fijo de posts-guía curados (`BBM_POSTS`); no hay listado ni sitemap |
| **Tipo de fuente** | Catálogo comunitario / blog curado (no es tienda) |
| **`kind`** | `wiki` (fuente virtual; no tiene entrada en `sources.yml`) |
| **`source_class`** | `trusted_media` |
| **País** | Brasil (`Brasil`) — fuente mono-país |
| **Idioma** | Portugués (PT-BR) |
| **Cobertura** | Ediciones especiales del mercado brasileño: capas variantes, volúmenes con brindes/itens especiais y box sets |
| **Aporte al corpus** | ~49 items (al último conteo) |
| **Parser / módulo** | [`scripts/wikis/blogbbm.py`](../../../scripts/wikis/blogbbm.py) |

**Editoriales que abarca** (entre paréntesis, volumen aproximado de items en el corpus):

Panini (≈14) · JBC (≈12) · Conrad (≈8) · Nova Sampa (≈5) · MPEG (≈4) · Pipoca & Nanquim
(≈1) · Vida Nova (≈1). El módulo también reconoce NewPOP y Devir en el prose, aunque hoy
no aparezcan con volumen alto en el corpus. El `publisher` se deriva del texto del post
(editorial real, NO la tienda, #44).

**Por qué importa / qué aporta de único**: BBM cubre el mercado brasileño de manera que
el scrape directo de tiendas BR cubre poco — marca explícitamente "esto es variant
cover", "esto trae brinde/itens especiais" y "esto es box set". Es la fuente de descubrimiento
de ediciones especiales de Brasil (capas variantes + volúmenes con extras + cofres),
publishers que de otro modo quedarían sin señal de coleccionable.

---

## 2. Descripción técnica de la fuente

- **No tiene índice ni paginación**: el módulo trae un conjunto FIJO de 3 posts-guía
  (`BBM_POSTS`), cada uno una colección distinta. Son posts **actualizados continuamente**
  (no archivados): el editor agrega cada nuevo lanzamiento notable al mismo post. Por eso
  no hay rango año/mes que respetar (ver §4).
- **Los 3 posts y su layout**:
  - `/2020/10/09/capas_variantes/` → **Capas variantes** (todas las entradas son variant
    cover por curación). Layout **AB**.
  - `/2024/05/15/guia-volumes-especiais-de-mangas-com-itens-especiais/` → **Volúmenes con
    itens especiais** (postais, marcapáginas, stickers, cards): cada entrada es
    `special_edition` + `bonus`. Layout **AB**.
  - `/2024/02/09/guia-box-de-manga-no-brasil/` → **Box de mangá** (box sets / cofres).
    Layout **C** (tablas supsystic).
- **Estructura del HTML** — dentro de `<div class="entry-content">`:
  - **Layout A** (`/capas_variantes/`): el gallery `<div>` con 2 imgs (cover normal +
    variant) aparece ANTES del título; el título es un `<p>` con `<strong>` o un link a
    `/manga/<slug>/`; sigue el prose.
  - **Layout B** (`/volumes-especiais/`): título `<p>` con fecha entre paréntesis
    `(MM/YYYY)`, separado por `<hr>`, seguido de prose y `<figure>` con cada imagen.
  - **Layout C** (`/guia-box-de-manga/`): 2 tablas `<table class="supsystic-table">`. Cada
    `<tr>` data row = un box, con columnas [imagen, título, editora, fecha `YYYY.MM`].
  - El parser de los layouts AB **no divide por `<hr>` ni por gallery divs específicos**:
    escanea todos los `<p>` con "title shape" (texto corto con marker de volumen `#NN` /
    `Vol N` / `Tomo N`, o fecha `(MM/YYYY)`, o link a `/manga/<slug>/`). Cada title abre un
    entry y lo cierra el siguiente title; entre medio acumula imgs y prose.
- **Identificador de producto**: URL sintética por entry (no hay URL de producto real). En
  layouts AB: `?bbm-entry=vol-<NN>-<image-stem>` colgado de la ficha `/manga/<slug>/` (o del
  post si no hay ficha). En layout C: `?bbm-entry=box-<slug-del-título>`. El param
  `bbm-entry` NO está en `TRACKING_PARAMS`, así que sobrevive a la normalización y discrimina
  cada variante aunque compartan ficha (#27, #19).
- **Quirks**:
  - Las imágenes se sirven vía proxy `i0/i1/i2.wp.com`; el módulo lo reescribe a
    `blogbbm.com` directo para que el espejo local descargue de origen.
  - El post de box usa un placeholder `Sem-Imagem.png` para rows pendientes; el módulo lo
    descarta (no es portada real) y el item queda con el placeholder del frontend.
  - Rows de box sin fecha o con "Em breve" → preventa (`release_date=""`).
- **Calidad de imágenes**: imágenes de `wp-content/uploads/` de blogbbm; en layouts AB el
  entry suele traer 2+ imgs (normal + variant) que se preservan en el carrusel del item.

---

## 3. Proceso de ingestión — vista de producto

> Cómo se decide QUÉ entra al catálogo, sin detalle técnico. La curación la hace el
> editor del blog: por estar listado en un post de BBM, el item ya es coleccionable por
> definición.

1. **Abrir cada post-guía** del conjunto fijo (capas variantes, volúmenes especiais, box).
2. **Recorrer cada entrada** del post (un título por volumen/edición).
3. **Cada entrada entra al catálogo como un item**, con el tipo de coleccionable que el
   post implica por curación:
   - post de **capas variantes** → variant cover;
   - post de **volúmenes especiais** → edición especial con brinde (bonus);
   - post de **box de mangá** → box set / cofre.
4. Del texto de la entrada se extrae editorial, precio (R$), volumen y fecha de
   lanzamiento; del bloque de imágenes, la portada (preferentemente la variante) y el
   carrusel.
5. **Repetir** hasta agotar las entradas de los 3 posts.

**Reglas de producto que nunca se rompen:**
- El país de la edición es **Brasil** (es el de la editorial/idioma, no el de una tienda) (#46).
- El `publisher` es la editorial real detectada en el texto (JBC, Panini, NewPOP, etc.),
  no el blog (#44).
- Un item por entry; la URL sintética se cualifica por entry (ficha + volumen + stem de
  imagen, o slug del título en el box) para no fusionar variantes ni obras distintas.

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

**Idéntico en FULL y DELTA**: no hay diferencia. BBM no tiene calendario mensual ni rango
año/mes — el módulo siempre procesa el mismo conjunto fijo de posts (`iter_year_months`
devuelve un único batch, y `bootstrap` ignora el rango año/mes que recibe, sólo lo acepta
por compatibilidad con el dispatcher). Como los posts se actualizan continuamente, cada
corrida re-captura todo el contenido vigente, incluidos los lanzamientos nuevos.

| | FULL (`scrape_full.sh`, paso 2g) | DELTA (`scrape_delta.sh`, paso 2f) |
|---|---|---|
| Invocación | `--bootstrap-wiki blogbbm --sleep-seconds 0.5 --min-score 20` | igual |
| Discovery | conjunto fijo de 3 posts curados | igual |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Cuándo | refresh completo | novedades recientes (mismo costo, los posts traen todo) |

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/blogbbm.py`](../../../scripts/wikis/blogbbm.py).

### 5.1 Modelo de datos / claves

- **Fuente virtual** (`_virtual_source`): no hay entrada en `sources.yml`. El módulo
  construye un `Source` con `kind="wiki"`, `country="Brasil"`, `language="Portugués"`,
  `source_class="trusted_media"`, `purity="manga_only"` (ambos posts son 100% manga curado).
  El nombre se discrimina por post: `BR - Biblioteca Brasileira de Mangás (<suffix>)` con
  suffix `Capas Variantes` / `Volumes Especiais` / `Box de Mangá`.
- **`publisher`** se sobreescribe por item desde el prose (regex `_EDITORA_PATTERNS`) o,
  en el box, desde la columna de editora de la tabla.
- **URL sintética** (#27): identificador estable por entry. AB →
  `<ficha>?bbm-entry=vol-<NN>-<image-stem>`; C → `<post>?bbm-entry=box-<slug>`. El param
  `bbm-entry` no se strippea en la normalización de dedup.
- **`tags`**: siempre `["wiki", "blogbbm", "brasil", <tag-del-post>]`; los items AB suman
  `bbm-vol:<N>` y los de box suman `bbm-box`.

### 5.2 Qué captura el parser (mapea el §3 al código)

- **`_parse_layout_ab`** (posts capas variantes + volúmenes especiais): heurística
  title-driven (`_is_title_p`) con buffer `pending_imgs` para los gallery divs que vienen
  ANTES del título (Layout A). El signal type se garantiza inyectando un texto a la
  descripción (`signal_inject`): "Capa variante / variant cover." o "Edição especial com
  brinde / special edition with bonus." → `detect_signals` levanta el signal correcto.
  `_pick_variant_image` elige la variante como portada y `_build_candidate` preserva el
  resto del gallery como carrusel (`images[]`, normal + variant para comparar en el modal).
- **`_parse_layout_c`** (post box): cada `<tr>` de las tablas supsystic = un box;
  `signal_inject` = "Cofre / box set / boxset.". Descarta el placeholder `Sem-Imagem.png`;
  "Em breve"/sin fecha → preventa.
- **Extractores comunes**: volumen (`_VOL_RE`, del título o prose), precio R$ (`_PRICE_RE`),
  fecha → `YYYY-MM` (`_extract_date`, meses PT-BR largos o `MM/YYYY`).

### 5.3 Flujo end-to-end

- Entra en **FASE 2** de ambos scripts (paso `2g` en `scrape_full.sh`, `2f` en
  `scrape_delta.sh`), después de las demás wikis y antes de los cleanup retrofits.
- Invocación: `--bootstrap-wiki blogbbm --sleep-seconds 0.5 --min-score 20` (timeout 300s).
- Tras la captura, items.jsonl queda **raw** (sin `standardized_at`): NO correr el skill
  `/watch-standardize-catalog` automáticamente (lo decide el owner).

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural que aplica a TODO el corpus (sin red).
- No tiene auditoría de red ni enforcer dedicados (a diferencia de ListadoManga). Los
  items de BBM se reprocesan completos en cada corrida porque los posts se descargan enteros,
  así que el "drift" se resuelve re-scrapeando.
- Debug rápido del parser sobre un post:
  ```bash
  .venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); import requests, wikis.blogbbm as B; \
    s=requests.Session(); s.headers['User-Agent']='mw/0.2'; \
    [print(c.score, c.publisher, c.signal_types, c.title[:50]) for c in B.bootstrap(2024,1,2026,12,session=s,min_score=0)[:15]]"
  ```

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Layouts heterogéneos** (gallery antes del título en A; figures después del título en B):
  resuelto con la heurística title-driven + buffer `pending_imgs` y el modo `lenient` de
  `_is_title_p` (acepta un título sin ficha link / sin fecha cuando hay gallery pendiente).
  ✅
- **Prose que menciona volúmenes** ("Volume #21 veio com…") se colaba como título: el modo
  estricto exige fecha parenthesized o ficha link; el marker `#NN` solo no alcanza. ✅
- **Proxy `i?.wp.com`**: las imágenes venían con proxy de WordPress; se reescriben a
  `blogbbm.com` directo para que el espejo local descargue de origen. ✅
- **Placeholder `Sem-Imagem.png`** en el post de box: se descarta como portada (#6); el item
  se genera igual y cae al placeholder del frontend. ✅
- **URL sintética `?bbm-entry=`**: query param custom que sobrevive a la normalización de
  dedup porque no está en `TRACKING_PARAMS` (#19) y los wikis con URL sintética se SKIPEAN
  en el backfill de imágenes vía `SYNTHETIC_URL_MARKERS` (re-fetchear daría 404). El marker
  `?bbm-entry=` está registrado junto a `?item=` de listadomanga.

**Decisiones (lo que NO se hace):** no se merge cross-país (#46) — Brasil es el país de la
edición; el blog no se usa como `publisher` (la editorial real sale del texto).

---

## 9. Pendientes / limitaciones conocidas

- **Conjunto de posts fijo**: si BBM publica un nuevo post-guía (otra categoría de
  coleccionable), hay que agregarlo a mano a `BBM_POSTS` con su `layout`. No hay discovery
  automático de posts nuevos.
- **Items de referencia, sin precio/URL de tienda confiables**: muchos entries no traen
  precio (sobre todo el box); son válidos para descubrimiento pero no para compra directa
  (ver "URL como referencia" en CLAUDE.md).
- **Detección de editorial por regex**: limitada a las editoras conocidas en
  `_EDITORA_PATTERNS`; una editora no listada queda con `publisher` vacío hasta agregar el
  patrón.

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (igual en full y delta; deja raw, sin standardize):
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki blogbbm --sleep-seconds 0.5 --min-score 20

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "blogbbm"
def hit(it):
    blobs=[it.get('url','') or '']+[ (s.get('url','') or '') for s in it.get('sources',[]) ]
    return any(NEEDLE in b for b in blobs) or 'blogbbm' in (it.get('tags') or [])
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
