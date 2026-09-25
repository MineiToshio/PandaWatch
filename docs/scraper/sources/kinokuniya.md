# Fuente: Kinokuniya USA Exclusives

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Kinokuniya USA Exclusives |
| **URL base** | `https://usa.kinokuniya.com/kinokuniya-exclusives` |
| **Índice / punto de entrada** | `https://usa.kinokuniya.com/kinokuniya-exclusives` (página única, sin paginación) |
| **Página de un producto** | `https://united-states.kinokuniya.com/bw/{isbn13}` (devuelve 403; no se fetchea) |
| **Tipo de fuente** | Tienda (retailer) — librería japonesa con sucursales en EE. UU. |
| **`kind` en sources.yml** | `wiki` (módulo propio; la fila YAML `html` quedó deshabilitada, ver §8) |
| **`source_class`** | `retailer` |
| **País** | Estados Unidos (`Estados Unidos`) — fuente mono-país por diseño |
| **Idioma** | Inglés |
| **Cobertura** | Catálogo activo de exclusivos de Kinokuniya USA: variant covers, dust jackets, shikishi, ID cards, sticker packs, limited editions con bonus |
| **Aporte al corpus** | ~58 items |
| **Parser / módulo** | `scripts/wikis/kinokuniya.py` |

**Editoriales que abarca** (la editorial real la completa el merge por ISBN / el skill, NO
la tienda — #44; entre paréntesis, volumen aproximado de items en el corpus):

Seven Seas Entertainment (≈13) · Viz Media / VIZ Media (≈11) · Kodansha Comics (≈6) ·
Kodansha USA (≈4) · TOKYOPOP (≈4) · Yen Press (≈3) · Titan Comics (≈2) · Square Enix (≈1) ·
Hakusensha (≈1) · Shueisha (≈1) · Akita Shoten (≈1) · Ichijinsha (≈1) · Coamix (≈1) ·
Tokuma Shoten (≈1) · Denpa (≈1) · Crunchyroll (≈1) · Dark Horse Comics (≈1), entre otras.

> Nota de corpus: aunque la fuente es 100% Estados Unidos por diseño (`country="Estados
> Unidos"` en la `_virtual_source`), el snippet de §10 reporta ~9 items con `country="Japón"`.
> Eso es esperado: cuando el mismo ISBN llega también desde una fuente japonesa, el merge por
> ISBN une las fichas y el `country` del producto consolidado puede quedar con el de la otra
> fuente. La edición exclusiva de Kinokuniya es siempre US.

**Por qué importa / qué aporta de único**: es la fuente principal de **ediciones exclusivas
de tienda del mercado estadounidense en inglés** (variant covers, dust jackets, shikishi, ID
cards, sticker packs) — un tipo de exclusividad de retailer que ninguna otra fuente del
catálogo cubre. Trae el ISBN-13 de cada exclusivo, lo que permite que el merge por ISBN una
la variante con la edición oficial de la editorial real.

---

## 2. Descripción técnica de la fuente

- **Estructura del sitio**: el listing es **una sola página** (`/kinokuniya-exclusives`) que
  muestra el catálogo activo completo de exclusivos. No tiene paginación ni histórico por
  fecha.
- **Squarespace (quirk central)**: el sitio corre sobre **Squarespace** y los nombres de
  clase CSS son **dinámicos** — cambian con cada redeploy. Por eso un selector estático del
  YAML no es estable (fue lo que motivó migrar a wiki parser; ver §8). El **único anclaje
  estable es el patrón de URL de producto**: `/bw/{isbn13}`.
- **Identificador de producto**: el **ISBN-13** embebido en el path del link
  (`/bw/{isbn13}`). Es la URL canónica del item y la key de dedup dentro del run. Solo se
  aceptan ISBNs que empiezan con `978`/`979` (los `0810…` son UPCs/EANs de productos de
  regalo, se descartan).
- **Dónde está el título**: Squarespace renderiza cada producto como bloque imagen-link, así
  que el título sale del atributo `alt` de la `<img>` (NO del texto del anchor). Los `*` al
  inicio/final del alt son marcadores de estado de Squarespace (p. ej. "próximamente") y se
  eliminan.
- **Anti-bot / quirks**: las **páginas de detalle devuelven 403**, así que todos los
  metadatos se extraen del listing; no hay fetch por producto.
- **Calidad de imágenes**: la portada se construye desde el CDN de Penguin Random House
  (`images.penguinrandomhouse.com/cover/{isbn13}`). La mayoría de los publishers EN que
  Kinokuniya usa para exclusivos (Kodansha, Seven Seas, Square Enix, Yen Press, VIZ,
  TOKYOPOP…) tienen cover en ese CDN; los que no, quedan para el backfill / espejo local.

---

## 3. Proceso de ingestión — vista de producto

> Kinokuniya es una página plana de exclusivos: la lógica de captura es directa, sin las
> jerarquías de edición de ListadoManga.

1. **Descargar la página de exclusivos** (`/kinokuniya-exclusives`): una sola request,
   sin paginación ni rango de fechas.
2. **Recorrer cada link de producto** que matchee el patrón `/bw/{isbn13}`, en orden de
   aparición; cada ISBN-13 único genera un candidato.
3. **Por cada producto**, decidir si entra:
   - Se descarta el link si el ISBN no es válido (no empieza con `978`/`979`) o si el título
     (del `img alt`) es vacío o demasiado corto.
   - De los que pasan, sólo se conservan los que superan el umbral de score (`--min-score
     20`); la descripción inyecta `"Kinokuniya Exclusive"` para que `detect_signals` levante
     el signal `retailer_exclusive` aunque el título no lo mencione.
4. **Terminar** — no hay siguiente página.

**Reglas de producto que nunca se rompen:**
- El país de la edición es Estados Unidos (#46): es una exclusiva de tienda US.
- `publisher` = editorial real (Viz, Kodansha, Seven Seas, TOKYOPOP…), **NUNCA**
  "Kinokuniya" (#44). La tienda no es la editorial.
- Sólo entran exclusivos de Kinokuniya (la página entera lo es); la exclusividad la captura
  el signal `retailer_exclusive`, no el campo `publisher`.

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

Kinokuniya se invoca **idéntico en FULL y en DELTA**: mismo módulo, mismos flags. No hay
diferencia de discovery — la página siempre muestra el catálogo activo completo, así que una
única request basta en ambos modos.

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script / paso | `scripts/scrape_full.sh` (paso 2m) | `scripts/scrape_delta.sh` (paso 2l) |
| Invocación | `--bootstrap-wiki kinokuniya --min-score 20` | idéntica |
| Discovery | una sola request al listing completo (sin paginación) | idéntico |
| Timeout | corto (120s) — una sola request | idéntico (120s) |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Cuándo | refresh completo | novedades recientes |

- El filtro de fechas (`year_from`…`month_to`) se ignora: `iter_year_months` devuelve un
  único batch y `bootstrap` no aplica filtro temporal (la página no tiene histórico).

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/kinokuniya.py`](../../../scripts/wikis/kinokuniya.py). Se activa con
`--bootstrap-wiki kinokuniya` (bypassea el loop de fuentes del YAML, #8).

### 5.1 Modelo de datos / claves
- No tiene reglas de agrupación propias. Emite `Candidate`s desde la `_virtual_source()`:
  `country="Estados Unidos"`, `language="English"`, `source_class="retailer"`, `kind="wiki"`,
  `purity="manga_only"`.
- `publisher` se emite **vacío** a propósito (#44): la editorial real la deriva el merge por
  ISBN o `/watch-standardize-catalog` en el `edition_key`. El `edition_key` ya suele traer la
  editorial real (ej. `vagabond-viz-deluxe`, `attack-on-titan-kodansha-us-deluxe`).
- Identidad del producto = ISBN-13 (de `/bw/{isbn13}`); es la URL canónica
  (`united-states.kinokuniya.com/bw/{isbn13}`) y el `cand.isbn`. El dedup por URL/ISBN lo
  hace `process_state` aguas abajo.

### 5.2 Qué captura el parser (mapea el §3 al código)
- `fetch_listing()` baja el HTML del listing (una request).
- `parse_listing()` itera todos los `<a href>`, extrae el ISBN-13 con `_ISBN_URL_RE`
  (`/bw/(\d{13})`), filtra `978`/`979`, dedup por ISBN dentro del run, y arma un `Candidate`
  por cada uno (título del `img alt` saneado con `clean_text`, portada del CDN de PRH,
  descripción que inyecta `"Kinokuniya Exclusive"` para el signal `retailer_exclusive`).
- `bootstrap()` orquesta: fetch → parse → filtro `min_score` → `flush_fn`.
- `signal_types`/`product_type` se derivan aguas abajo (`score_candidate`, `detect_signals`):
  `"kinokuniya exclusive"` está en `KEYWORD_RULES` (score=45, type=`retailer_exclusive`).
- Gate de entrada (en el `flush_fn` genérico de `manga_watch.py`): `score ≥ --min-score`
  (20). Por debajo de eso no entra.

### 5.3 Flujo end-to-end
- Corre como **paso 2m** de `scrape_full.sh` y **paso 2l** de `scrape_delta.sh`, entre los
  demás retailers de variantes/exclusivos en inglés. Comando:
  ```
  manga_watch.py --bootstrap-wiki kinokuniya --min-score 20
  ```
  (timeout corto de 120s vía `_run_timed`, una sola request).
- Escribe a `data/items.jsonl` incrementalmente vía `flush_fn`. Luego pasa por las fases
  comunes del pipeline (cleanup retrofits → build → validate). No tiene retrofits dedicados;
  el `publisher` correcto lo aporta el merge por ISBN o el retrofit transversal
  `scripts/retrofit/fix_store_publisher.py` (#44).
- Tras el scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr
  `/watch-standardize-catalog` automáticamente.

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural del pipeline (aplica a TODO el corpus,
  sin red). Es la verificación principal para esta fuente.
- No hay auditoría de red dedicada ni enforcer/idempotencia propios: es una fuente plana sin
  reglas de agrupación.
- Sanity manual: correr el módulo directamente (`python scripts/wikis/kinokuniya.py`) y
  comparar los ISBNs/títulos que emite contra el corpus (ver runbook §10).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Squarespace con class names dinámicos → migración a wiki parser**: originalmente
  Kinokuniya era una fila `kind: html` en `sources.yml` (`US - Kinokuniya Exclusives`,
  `selectors.item_selector: "div.margin-wrapper"`). Como Squarespace cambia los nombres de
  clase CSS en cada redeploy, ese selector se rompía. ✅ Se reemplazó por
  `scripts/wikis/kinokuniya.py`, que extrae los ISBNs directamente del patrón estable de URL
  de producto (`/bw/{isbn13}`). La fila YAML quedó con **`enabled: false`** y una nota que
  apunta al wiki parser; se conserva como rastro histórico (no borrar sin actualizar esta
  ficha).
- **#44 (la tienda no es la editorial)**: la `_virtual_source` antes hardcodeaba
  `publisher="Kinokuniya USA"`, lo que metía la tienda en el `edition_key`/`publisher` y
  separaba el mismo ISBN en otro `cluster_key` (falsos "duplicados" en el Panel de Calidad).
  ✅ Se removió el publisher (queda `""`); la editorial real la completa el merge por ISBN o
  el skill. Kinokuniya **NO es excepción** a la regla retailer (decisión 2026-06-07): es una
  librería multi-editorial.
- **Detail pages 403**: las páginas `/bw/{isbn13}` devuelven 403 → todo se extrae del
  listing. `fetch_details` queda en `False` por diseño.
- **Decisiones (lo que NO se hace)**: no se pone la tienda como publisher (#44); no se
  fetchean páginas de detalle; no se aceptan códigos que no sean ISBN-13 `978`/`979`.

---

## 9. Pendientes / limitaciones conocidas

- **Sin precio en el listing**: el precio no se extrae (PandaWatch no captura precios).
- **Cobertura = snapshot del catálogo activo**: la página sólo muestra los exclusivos
  vigentes hoy; los exclusivos descontinuados desaparecen del listing (no hay histórico). Lo
  que ya entró al corpus persiste, pero no se descubren exclusivos pasados.
- **Portada dependiente del CDN de PRH**: los ISBNs cuya portada no esté en
  `images.penguinrandomhouse.com` quedan sin imagen hasta que el backfill / espejo local la
  resuelva.

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (igual que en el pipeline, deja raw):
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki kinokuniya --min-score 20

# Debug: ver qué emite el parser (sin escribir a items.jsonl):
.venv/bin/python scripts/wikis/kinokuniya.py

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "kinokuniya"
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

**Antes de cerrar cualquier cambio en Kinokuniya**: validar (`validate_corpus`, 0 duras) →
tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza esta
ficha.

---

## 2026-09-24 — El parser sólo emite título + ISBN: 96 % de los items sin editorial (gotcha #215)

**Corrida**: delta diario. La fuente rindió **47 candidatos, 5 reportables**, sin errores
ni skips — o sea es una fuente **sana en disponibilidad** y el problema es de **riqueza
del dato**, no de acceso. 4 de los 9 items realmente nuevos del día salieron de acá.

**Medición sobre los 47 items de la fuente en el corpus**:

| Campo | Faltante | % |
|---|---|---|
| `publisher` | 45 | 96 % |
| `release_date` | 47 | 100 % |
| `volume` | 39 | 83 % |
| `edition_key` con `-unknown-` | 11 | 23 % |
| rareza `rare` (por `retailer_exclusive`, sin stock verificado) | 6 | 13 % |

El `description` que emite el parser es literalmente `"Kinokuniya Exclusive. ISBN:
<isbn>."`. La causa es el discovery: el módulo lee la grilla de
`usa.kinokuniya.com/kinokuniya-exclusives` (portada + título + ISBN) y **no visita la
ficha por producto** `united-states.kinokuniya.com/bw/<isbn>`, que sí trae editorial,
fecha y tomo.

**Por qué esto no es cosmético**: `publisher` es un componente del `edition_key`. Con la
editorial vacía el item acuña `…-unknown-variant-us`, y si el mismo producto entra
después por una fuente que sí la trae, nacen **dos ediciones para un solo producto** —
el mecanismo de **#210**. Los 4 items nuevos de hoy entraron los 4 así:

```
servant-beasts-unknown-variant-us
it-s-strictly-business-unknown-variant-us
omniscient-reader-s-viewpoint-novel-unknown-variant-us
can-you-kiss-me-first-unknown-variant-us
```

Dicho de otro modo: **Kinokuniya no sufre #210, lo produce.**

**Contexto de alcance medido el mismo día**: el corpus tiene **1672 items** con
`-unknown-` en el `edition_key` y **204 grupos partidos** (misma serie + volumen + tipo
+ país repartidos en ≥2 `edition_key`, uno `-unknown-`). El 2026-09-17 eran **110**
grupos sobre 1662 items: el pool está estable pero la fragmentación **casi se duplicó en
una semana**.

**Recomendación (NO aplicada — decisión del owner)**: agregar fetch-details de
`/bw/<isbn>` en `scripts/wikis/kinokuniya.py`. Es **1 request por item sobre ~47 items**
(costo trivial, la fuente ya responde bien) y cierra el agujero en el origen: recupera
editorial, fecha y tomo de una sola vez, lo que además convierte 6 rarezas
"rare-por-incertidumbre" en rarezas con evidencia. Retorno alto, riesgo bajo: no cambia
slugs de items existentes salvo los 11 que hoy tienen `-unknown-`.

### Integridad de ingestión — continuación 2026-09-24

Los fallos de transporte ahora registran `[WIKI-ISSUE]` en la sesión. El dispatcher
conserva los resultados parciales y termina con error; incluye el fallo en el
reporte. Una respuesta fallida no equivale a catálogo vacío. El watermark por
fuente solo avanza después de persistir corpus y estado, sin incidencias ni
límites alcanzados. Tras una interrupción, el calendario amplía su ventana hasta
el último inicio exitoso con siete días de solapamiento. Un import histórico
acotado, un chunk explícito o un dry-run no adelantan ese watermark.

### Comprobación viva adicional — 2026-09-24

Catálogo de exclusivas reingerido en staging: 47 candidatos/reportables, salida
0. El rango de fechas no convierte el índice de exclusivas actual en histórico.

### Reparación de referencias históricas — 2026-09-24

Se quitaron 2 referencias de `united-states.kinokuniya.com` asociadas a otra fila con ISBN
válido diferente del producto cuya URL primaria es esa misma referencia. Se
conservan ambos productos y su URL primaria; no se fusionan por ISBN. Evidencia
por URL/ISBN en `reports/ingestion-audit-2026-09-24/closure/publication-2-manifest.json`.

### Delta 2026-09-25 — `language` fuera del enum (47 items)

La fuente emite `"English"` en vez del valor del enum del corpus (`"Inglés"`): **47
de sus items** caen en el warn `LANG_ENUM` de `validate_corpus`. Es el segundo mayor
contribuyente después de VIZ (148). Detalle y tabla completa en
[viz.md](viz.md#delta-2026-09-25--429-puntual--idioma-fuera-del-enum).

Se suma a #215 (el módulo emite sólo título + ISBN): Kinokuniya es una fuente
estructuralmente pobre en metadata. **Nada aplicado**; el fix correcto es normalizar
el idioma en el extractor compartido, no por fuente.
