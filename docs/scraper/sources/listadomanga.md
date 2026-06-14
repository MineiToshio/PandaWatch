# Fuente: ListadoManga

> Catálogo de fuentes de PandaWatch. Esta es la ficha de **ListadoManga** — la fuente
> más importante y delicada del proyecto. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-14.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | ListadoManga |
| **URL base** | `https://www.listadomanga.es` |
| **Índice del catálogo (scrape general)** | `https://www.listadomanga.es/lista.php` |
| **Página de una edición** | `https://www.listadomanga.es/coleccion.php?id=N` |
| **País** | España (`es`) — fuente mono-país |
| **Idioma** | Español |
| **Tipo de fuente** | Catálogo comunitario / base de datos (no es tienda) |
| **Cobertura** | Manga publicado en España: ~6500 colecciones totales, ~3436 activas |
| **Aporte al corpus** | ~1900-2000 items |

**Editoriales que abarca** (todas las editoriales de manga de España; entre paréntesis,
volumen aproximado de items en el corpus):

Norma Editorial (≈530) · Planeta Cómic (≈440) · Panini Manga (≈210) · Milky Way
Ediciones (≈150) · Editorial Ivrea (≈110) · EDT / Ediciones Glénat (≈90) · Editorial
Salvat (≈70) · Arechi Manga (≈70) · ECC Ediciones (≈60) · Ediciones Tomodomo · MangaLine
Ediciones · Ponent Mon · Distrito Manga (Penguin Random House) · Ediciones B · Ooso
Comics · Héroes de Papel · Kitsune Manga · Bruguera · LetraBlanka · Nowevolution · Odaiba
· Devir Manga · Fandogamia, entre otras.

**Por qué importa**: es la fuente principal de **ediciones especiales, cofres, portadas
alternativas, packs, kanzenban, deluxe, artbooks y extras de 1ª edición** del mercado
español. Es la que más bugs ha dado: si algo se rompe en el catálogo, casi siempre es de
acá. Todo cambio en su ingestión debe terminar con el corpus VÁLIDO (ver §7).

---

## 2. Descripción técnica de la fuente

- **`lista.php`** — índice alfabético de TODAS las ediciones activas (~3436). Cada fila
  enlaza a una `coleccion.php?id=N`. Es el punto de entrada del scrape general.
- **`coleccion.php?id=N`** — UNA edición concreta de una obra (ej. una serie de Norma, o
  la "Edición Grimorio" de otra). Contiene todos sus tomos, extras, ediciones especiales y
  portadas variantes. El `id=N` NO sigue el orden alfabético.
- **Secciones del HTML** de una página de edición (no siempre aparecen todas):
  - Nombre del manga / edición (título de la colección).
  - **Números editados** (tomos numerados de la edición).
  - **Números editados (Ediciones Especiales)**.
  - **Números editados (Portadas alternativas)**.
  - **Números editados (Packs)** / **Números en preparación (Packs)** (packs
    anunciados, aún sin editar — capturados como `pack` + `status:upcoming`; #73).
  - **Cofres de regalo con las primeras ediciones de {obra}**.
  - **Números no editados** / **en preparación** (sin precio, se descartan).
  - **Sinopsis de {obra}**.
  - **Extras de {obra}** (materiales adicionales, regalos).
  - **Otras ediciones de {obra}** (links a otras `coleccion.php` — se descartan: cada una
    es otra edición que se visita por su cuenta).
- **Formato** (`Formato: …`): indica si la edición es premium (kanzenban, cartoné/tapa
  dura, A5, tomo doble, libro de ilustraciones) o normal.
- **URL sintética por tomo**: cada tomo/extra que entra al corpus recibe una URL estable
  `coleccion.php?id=N&item=<kind>-<vol>[-<hash>]` — es su identificador de producto.
- **Calidad de imágenes**: las portadas de listadomanga son de baja resolución
  (thumbnails ~96×150). Es la causa principal de portadas malas en el catálogo (ver §8).

---

## 3. Proceso de ingestión — vista de producto

> Cómo se decide QUÉ entra al catálogo, sin detalle técnico. La lógica clave: de una
> edición **premium** entran todos los tomos; de una edición **normal** sólo entra lo
> coleccionable (especiales, variantes, packs, cofres, box sets).

1. **Ir al índice** `https://www.listadomanga.es/lista.php` — la lista de todas las
   ediciones de manga publicadas en España.
2. **Tomar el primer item** de la lista.
3. **Abrir su página de edición** (`coleccion.php?id=N`): tiene todos los tomos, extras,
   ediciones especiales y portadas variantes de ESA edición.
4. **Mirar las secciones** que trae la página (ver §2; no siempre están todas).
5. **Determinar si la edición es premium** (deluxe, kanzenban, o de alta calidad):
   - **SÍ es premium** → entran **TODOS** los tomos de "Números editados" (toda la edición
     es coleccionable). Además:
     1. Si un tomo trae edición especial / extras de 1ª edición / cofre → la **foto del
        extra/cofre va en la galería del tomo correspondiente**.
     2. Un **pack, edición especial o portada alternativa** se agrega como un **registro
        aparte de esa misma edición**.
     3. Un **box set** se agrega como una **edición aparte**.
   - **NO es premium** (edición normal, no cumple lo anterior) → los tomos regulares NO
     entran (un tomo normal sin nada especial no es coleccionable). Sólo entra:
     1. **Packs, tomos de edición especial o portadas alternativas** → registro aparte de
        esa misma edición.
     2. **Box set** → edición aparte.
     3. **Tomos con extras / cofre / material adicional** → se agrega el tomo regular
        correspondiente (de "Números editados") y a ese registro se le pega la **foto del
        extra** + se **documenta el extra** en la descripción del tomo.
6. **Repetir desde el paso 2** con el siguiente item de la lista, hasta terminar toda la
   lista.

**Reglas de producto que nunca se rompen:**
- Una página de edición = UNA edición. La misma obra en páginas distintas = ediciones
  distintas (nunca se mezclan).
- El cofre de 1ª edición de un tomo normal es un extra de ESE tomo (kind regular), no una
  edición aparte.
- El país de la edición es España (es el de la editorial/idioma, no el de una tienda).

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

Ambos usan el MISMO parser; sólo cambia CÓMO descubren qué colecciones visitar:

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script | `scripts/scrape_full.sh` | `scripts/scrape_delta.sh` |
| Discovery | `lista.php` → ~3436 colecciones, orden alfabético | `calendario.php` → ids con actividad reciente (mes actual + 2 anteriores), ~500-600 |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Tiempo | ~2-4 h | ~30-60 min |
| Cuándo | refresh completo del catálogo | novedades recientes |

- **El FULL recorre `https://www.listadomanga.es/lista.php` item por item**, en orden
  alfabético, parseando cada colección completa.
- Hay **paridad** delta/full: el delta captura la misma riqueza (especiales/cofres/
  variantes), acotada a lo reciente.
- El **calendario plano** (`--bootstrap-wiki listadomanga`) quedó FUERA del pipeline
  (NO parsea especiales/cofres). `listadomanga-blog` también REMOVIDO (0 items netos).
- Driver de ingesta resumible por chunks: `scripts/ingest_listadomanga_full.py`.

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/listadomanga_collections.py`](../../../scripts/wikis/listadomanga_collections.py).

### 5.1 Modelo de datos (REGLAS DURAS)

- **Una `/coleccion?id=N` = UNA edición** (#42/#48): todos sus tomos comparten
  `edition_key`. Obra en colecciones distintas = ediciones distintas, nunca el mismo
  `edition_key` (#57).
- **País = edición** (#46): el país va de sufijo en el `edition_key` (`…-es`).
- **URL sintética** (#27): `coleccion.php?id=N&item=<kind>-<vol>[-<hash>]`; `item` NO está
  en `TRACKING_PARAMS` → sobrevive la normalización.
- **`cluster_key` tier-0 `lmc`** (#48/#52): `lmc:{cole}:{kind}:{vol}`, evaluado ANTES del
  `edition:` (tier-1). El kind se canonicaliza (`especial`→`special`, `alternativa`→
  `variant`, `limitada`→`limited`). Distingue variantes del mismo volumen.
- **`edition_key`** = `{serie}-{publisher}-{edition_slug}-{país}` (+ `-c{cole}` si hubo
  colisión entre colecciones, #57).

### 5.2 Qué captura el parser (mapea el §3 al código)

- **Layout A** (`<table class="ventana_id1">`): items numerados.
  - `Números editados` → SÓLO si el `Formato:` es premium (kanzenban/cartoné/A5/tomo
    doble/libro de ilustraciones). Edición normal → no se capturan los tomos regulares,
    SALVO cofres listados inline ("Cofre de 2 tomos") que se emiten como `box` (#75). Si
    el cofre inline trae ADEMÁS un marcador de edición ("Edición Especial/Limitada",
    "Portada/Sobrecubierta Alternativa"), se clasifica por ESA edición (no como box) —
    así no se inventa un box-set fantasma ni se duplica el especial del mismo vol que
    "Regalos/Cofres" (Layout B) emite (`_match_inline_edition`, #102; caso orange nº7).
  - El volumen del tomo se extrae tras quitar el prefijo del nombre de la colección —
    series con número en el nombre ("Kaiju Nº8") no contaminan el vol (#74).
  - `Ediciones Especiales` → kind `especial`; `Portadas alternativas` → `alternativa`;
    `Packs` → sólo si la línea trae keywords de extras (aplica igual a la variante
    "en preparación (Packs)", que además marca `status:upcoming`; #73).
  - **Número GRATUITO descartado**: si la línea de precio es "Número Gratuito" (folleto
    promocional regalado: preview del 1er cap, mini-artbook, avance bundleado) el item se
    descarta (`FREE_PRICE_PATTERN` → `_parse_item_table` devuelve `None`). No es comprable
    aunque listadomanga lo titule "(Especial)". Por ítem: conserva números de pago (#103).
- **Layout B** (`<table width="920">`): Cofres / Regalos / Extras. Vincula el extra a su
  tomo. Cofre de 1ª edición de "tomos X a Y" → marca esos tomos `regular` (#53).
- Kanzenban se detecta por el literal en título/formato, NO por tamaño A5 (#51). "doble
  sobrecubierta" es cosmético, NO es kanzenban (#51).
- Gate `is_collectible_edition`: score≥30 + señal coleccionable; las URLs sintéticas
  cuentan como proof-of-product (#50).

### 5.3 Flujo end-to-end

```
scrape_full/delta.sh
  └─ FASE 1: scrape sources del YAML (manga_watch.py --workers 8)
  └─ FASE 2: [2a] listadomanga-collections (lista | calendar)
  └─ FASE 3: cleanup retrofits (rescore → filters → clean_titles → backfill imágenes →
             [full] mirror → align/unify → consolidate → dedup_carousel)
  └─ FASE 4: build_web.py
  └─ FASE 5: validate_corpus.py  ← gate de salud (§7)
```

> ⚠️ Tras un scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr el skill
> `/watch-standardize-catalog` automáticamente (consume tokens; lo decide el owner). El
> skill asigna `edition_key`/series vía LLM PERO **NO es autoridad de agrupación**: las
> reglas duras se re-aplican con el **enforcer** (§6), que es su Step 6b.

---

## 6. El ENFORCER — autoridad determinista de agrupación

`scripts/retrofit/enforce_listadomanga_rules.py`. Corre SIEMPRE después de standardize y
re-aplica EN ORDEN todas las reglas duras, sobreescribiendo al LLM. **Es idempotente**
(2× → items.jsonl byte-idéntico, se verifica en §7). Orden actual:

| Paso | Script | Qué hace |
|---|---|---|
| 1 | (interno) | `edition_display` = nombre oficial de la /coleccion (desde `description`, sin red) (#49) |
| 2 | `fix_edition_country` | sufija país en `edition_key` (#46) |
| 2b | `fix_edition_key_anomalies` | `panini-es`→`panini`; `xx`→país si la editorial es mono-país |
| 3 | `unify_coleccion_edition` | una /coleccion = un `edition_key` (incl. fichas de tienda cross-source) (#48) |
| 3-0 | `disambiguate_coleccion_editions` | si un `edition_key` abarca >1 cole → `-c{cole}` (#57) |
| 3-1 | `collapse_baseurl_tomos` | fusiona fila base-url phantom en su tomo sintético (#56) |
| 3-2 | `merge_crosssource_into_lmc` | fusiona ficha de tienda en su tomo lmc por edition_key+vol+título (#56) |
| 3a | `fix_lmc_display_titles` | quita "nº", des-contamina título, aplica marcador de kind (#52/#54/#56) |
| 3a2 | `fix_especial_title_order` | `{serie} {vol} Edición Especial` |
| 3b | `fix_listadomanga_title_collisions` | desambigua títulos que colisionan |
| 3b2 | `backfill_cluster_key` | **re-deriva TODOS los cluster_key** (#55 — sin esto consolidate no fusiona) |
| 3c | `dedup_synthetic_source` | fusiona filas que comparten fuente sintética; de-bundle de fichas multi-kind (#54) |
| 4 | `consolidate_sources` | 1 fila por producto con `sources[]` |
| 5 | `dedup_carousel_images --all` | quita la misma portada repetida en baja resolución |
| 6 | `generate_slugs` | slug por item |

**El orden importa.** Si lo cambias, vuelve a verificar idempotencia + validador.

---

## 7. Validación (CÓMO saber que está bien — objetivo, no "creeme")

1. **`scripts/validate_corpus.py`** (sin red, gate del pipeline). Invariantes DURAS:
   `SLUG` · `CLKEY` (`cluster_key == derive_cluster_key`, #55) · `DUPCL` · `DUPSYN` (#54) ·
   `LMCKIND` · `TITLE` (#52/#54/#56) · `ONECOLE` · `DUPVOL` (ningún volumen duplicado en
   un edition_key, #56/#57). Warnings: `COLED`, `PAIS` (`edition_key` sin país conocido).
2. **Idempotencia**: enforcer 2× → items.jsonl byte-idéntico (hash canónico). Si cambia,
   hay bug de orden/estabilidad.
3. **Auditoría de red** (`scripts/audit_lista_full_bidir.py`): re-fetchea las 3436
   colecciones y compara (kind,vol) parser vs DB → **FALTANTES** + **SOBRANTES**. Objetivo
   0/0. Limpieza de sobrantes: `reconcile_lista_stale.py`.
4. **Errores de red durante el bootstrap** (2026-06-10): `fetch_collection` ya NO traga
   los fallos de red en silencio. La sesión reintenta sola los transitorios (retry adapter
   en `make_session`, 429/5xx/reset con backoff); si aun así falla, la colección se loguea
   (`[WARN] coleccion N: error de red`), se acumula en `NETWORK_ERROR_LOG` y al final del
   bootstrap se vuelca un resumen `[NETWORK-ERROR]` + `logs/listadomanga_network_errors.txt`
   (un id por línea, re-procesable directo con `--coleccion-ids-file`). Antes un blip de
   red era indistinguible de "colección vacía" y el id se perdía del run sin rastro.

**Regla de proceso**: cuando el owner reporta una CLASE de error que el validador no veía,
se AGREGA como invariante nueva (no sólo se parchea el caso). Antes de "arreglar" lo que
reporta el validador, **medir la composición** (ej. PAIS marcaba 226 pero 203 eran países
válidos que faltaban en el allowlist — el bug era del validador).

---

## 8. Problemas encontrados — qué funcionó y qué NO

Resumen de gotchas #43-#60, #73-#75 y #95 (detalle en gotchas.md). Casi todas afectan a TODO el catálogo;
recuperar requiere re-scrape + enforcer.

**Captura / parser:**
- #43-45, #50: capturar premium por título, "en preparación (Ediciones X)", extras
  huérfanos, kanzenban score floor. ✅
- #51: "doble sobrecubierta" NO es kanzenban (capturaba tomos regulares enteros, Zetman). ✅
- #53: **cofre de 1ª edición común no se capturaba** (kind destino vacío) — afectaba TODO
  el catálogo (Medaka Box, Aoha Ride, Cells at Work…). ✅ (default a `regular` si hay
  descriptor de cofre/extra; un marker de edición DESCONOCIDO NO defaultea — no inventamos).
- #74: **número embebido en el nombre de la serie contaminaba el volumen** ("Kaiju Nº8
  nº16" → vol 8; el pack heredaba vol 8 fantasma). ✅ `_strip_series_prefix` antes de
  buscar el nº + reparación de las 2 keys stale del corpus + backfill_cluster_key.
- #75: **cofres inline en "Números editados" no-premium se perdían** ("Cofre de 2 tomos",
  Boichi cole 6240 — solo lo había capturado el calendario legacy). ✅ excepción al gate:
  emite SOLO los items con `\bcofres?\b` en el desc_extra como kind `box`.
- #102: **edición especial CON cofre inline se clasificaba como `box`** → box-set fantasma +
  duplicado del especial del mismo vol que Layout B emite ("orange nº7 Edición Especial +
  Cofre", id=1970). ✅ `_match_inline_edition`: si el cofre inline trae marcador de edición,
  va por esa edición (el merge fusiona el cofre de Layout B como extra). 0 fantasmas en el
  corpus (era preventivo: orange se scrapeó antes de #75).
- #103: **folleto promocional GRATUITO titulado "(Especial)" se colaba como edición especial**
  (Edens Zero id=3112, owner 2026-06-14). El preview del 1er capítulo / mini-artbook de regalo /
  avance bundleado con un videojuego que la editorial REGALA muestra "Número Gratuito" en la línea
  de precio (vs "9,98 €"); el título "(Especial)" disparaba `special_edition`. Señal universal:
  verificada contra TODA la categoría editorial "Previews" (`coleccion_editorial.php?id=332`) +
  promos sueltas = 25 colecciones, todas con esa línea. ✅ `FREE_PRICE_PATTERN` en
  `_parse_item_table` → devuelve `None` (descarta POR ITEM; conserva números de pago de la misma
  colección). Limpieza: `remove_free_preview_editions.py` (13 borrados, regla A description +
  regla B legacy calendario verificado por fetch).

**Agrupación / dedup (la raíz de casi todos los duplicados):**
- #46 país=edición, #48 coleccion=edición, #49 edition_display oficial, #52 cluster_key
  tier-0 lmc. ✅
- #54: dups por fuente sintética compartida + el **hash del `item=` NO es único entre
  colecciones** (sale del filename de portada placeholder → `regular-1-08a0…` se repite en
  obras distintas). Regla: la identidad sintética SIEMPRE se cualifica por cole. ✅
- #55: **`cluster_key` STALE = la raíz de "la auditoría siempre encuentra algo"** —
  standardize renombraba `edition_key` pero el cluster quedaba viejo → 741 items. ✅
  `backfill_cluster_key` en el enforcer.
- #56: **"el tomo aparece dos veces" (4 raíces)**: base-url phantom, dup cross-source
  tier-0/tier-1, título contaminado, falta de marcador de kind. ✅ invariante DUPVOL + 4
  retrofits.
- #57: **colisión de `edition_key` entre colecciones distintas** (Biomega Ultimate vs
  Master, Magic Knight Rayearth vs Rayearth 2). ✅ desambiguación `-c{cole}`.
- #58: **box set = edición APARTE** (no parte de la edición de los tomos). unify
  colapsaba box + tomos a un solo `edition_key`. ✅ unify separa: tomos → base,
  box sets → su propia edición (slug `boxset`). COLED no dispara por el box.
- #59: **extra de "Edición Especial" en Layout B mal clasificado como tomo regular**
  cuando el nombre de serie se parte en 2 líneas (el `nº` cae en la línea 2 →
  fallback Grimorio → regular). Creaba un tomo regular FANTASMA que duplicaba al
  especial real (reportado en Promised Neverland 13). ✅ si la celda dice "Edición
  Especial/Limitada", el kind es `especial` (no un cofre regular). El cofre legítimo
  ("(1ª Edición) Cofre para tomos X a Y") sí va al tomo regular (#53).
- #60: **`volume` vacío en ediciones especiales/limitadas/variantes** — el parser extraía
  el volumen correctamente del `alt` ("nº13") pero NO lo propagaba al `Candidate.volume`;
  `_extract_volume` sólo capturaba trailing numbers y fallaba en "Title 13 Edición
  Especial" (número antes del calificador). Fix: (a) `cand.volume = parsed["volume"]` en
  `listadomanga_collections.py`; (b) nuevo patrón en `_extract_volume` para números
  antes de calificadores; (c) retrofit `backfill_volume_from_cluster.py` para los 9
  items ya existentes. Afectaba: Promised Neverland 13, Berserk 21/41/42, Seven
  Deadly Sins 41, Twilight Outfocus 1/2, A Miyoshi 1/2. ✅

- #73: **"Números en preparación (Packs)" no reconocido** — SECTION_RULES cubría las
  variantes "en preparación" de Especiales/Limitadas/Alternativas + el base, pero NO
  `(Packs)` → el h2 caía a unknown (id=5584 en `logs/listadomanga_unknown_h2.txt`) y los
  packs anunciados se perdían en silencio. ✅ regla nueva ANTES del entry base, mismo
  tratamiento que editados: kind `pack` + filtro de keywords de extras (pack pelado tipo
  "Pack tomos 4 y 5" se sigue descartando) + `status:upcoming` por prefijo.

- #95: **título con la edición DUPLICADA en dos idiomas + volumen perdido** ("Pájaro que
  trina no vuela no Special Edition Edición Especial", reportado por el owner). NO es un bug
  del parser: el skill VIEJO de standardize tradujo la edición a inglés y destruyó el "nº9"
  (→ "no"); ese título mangleado quedó como `title_original` y `restore_official_titles` lo
  propagó a `title`; después `normalize_display_title` re-apendaba "Edición Especial" sin
  remover el "Special Edition" inglés → duplicación. ✅ (a) mecanismo: `_ESP_ANY_RE` ahora
  matchea también "Special Edition" (EN) + `_KIND_MARKER` completado con `collector`; (b)
  datos legacy: `fix_corrupted_lm_special_titles.py` reconstruye el título desde el
  `description` — **el `description` preserva el `collection_title` scrapeado intacto** (con
  `nº{vol}` y la edición en español), así que es la fuente CONFIABLE cuando `title_original`
  quedó corrupto. Cuando el `description` también quedó contaminado por un merge cross-source
  (metadata de tienda, caso "Fruits Basket Collector's Edition" con paginación de fnac), el
  fallback toma el STEM de un tomo hermano limpio de la misma colección + el volumen propio.
  18 items en total (16 desde description + 2 vía fallback).

- #99: **edición especial FANTASMA + foto del bonus de OTRO tomo** (reportado por el owner,
  caso "Edens Zero Especial 23"). El módulo plano del calendario (`scripts/wikis/listadomanga.py`)
  sólo conoce el texto del enlace del día (era literal "Edens Zero nº23") y deja la imagen
  vacía en páginas multi-tomo (#28); pero al pasar esos items legacy por la estandarización
  (LLM) algunos se "derivaron" como Edición Especial/Artbook que NO existe en la página real, y
  se les pegó la foto de un extra (cofre/posavasos/miniartbook) de otro volumen. El parser de
  colecciones es la AUTORIDAD: si ahí no hay tal especial, era fantasma. ⚠️ El cruce
  calendario-vs-colecciones NO basta para borrar (falsos positivos en ambos sentidos — ver §9):
  cada candidato se VERIFICÓ a mano contra la página viva. ✅ limpieza
  `remove_phantom_calendar_editions.py` (5 fantasmas borrados + 2 fotos robadas quitadas, 2026-06-14)
  + guarda durable invariante **STOLENIMG** en `validate_corpus.py` (warning si la portada de un
  tomo NORMAL es el `extra`/`bonus` de otra fila).

**Decisiones (lo que NO se hace):** omnibus pelado no califica (#18); no se mergea
cross-país (#46); el LLM no decide agrupación (lo hace el enforcer).

---

## 9. Pendientes / limitaciones conocidas (NO resuelto)

- **Imágenes de baja calidad**: la mayoría de portadas malas vienen de listadomanga
  (thumbnails). Hay flag de baja calidad + dedup de carrusel que prefiere hi-res de otra
  fuente, pero NO hay forma confirmada de sacar hi-res desde la misma página. Pendiente.
- **Portadas censuradas (adult content)**: algunos tomos muestran un modal "aceptar
  contenido adulto"; el scraper ve el placeholder. Requeriría Playwright o cookie
  injection. Diferido.
- **Hash de `item=` no único entre colecciones** (#54): bug latente del generador. Se
  mitiga cualificando por cole en todo dedup; NO se arregló (cambiarlo rompe idempotencia
  con el corpus). Si se regenera todo desde cero, incluir el cole id en el hash.
- **Drift entre sesiones**: si alguien corre standardize entre tareas, el corpus puede
  desincronizarse; el validador + enforcer lo detectan y auto-corrigen (por eso el gate [5]).
- **~~El parser de colecciones se PIERDE ediciones especiales reales~~ → FALSA ALARMA de medición,
  RESUELTO (2026-06-14, gotcha #101).** Al verificar los fantasmas de #99 se creyó que el parser
  "sólo emitía `regular`" para orange nº7 (id=1970), "El chico que me gusta no es un chico" nº3
  (id=5641) y Hosaka nº1/2 (id=5050). **No es así**: el parser SÍ los emite (reproducir con el debug
  de §10 — id=5050→`especial-1`+`especial-2` en `ventana_id9`; id=5641→`especial-3` en `ventana_id14`;
  id=1970→`especial-7` vía Layout B), y los tres YA ESTÁN en el corpus con DOS fuentes
  `['ListadoManga (calendario)', 'ListadoManga (colecciones)']` — el especial del parser se FUSIONÓ
  con el item del calendario (mismo producto, correcto). El error de medición: el item fusionado
  conserva los **tags del calendario** (`category:Manga`), NO `edition:especial`/`coleccion:N`, y su
  URL primaria es la del calendario (el synthetic `item=especial-N` vive en `sources[]`) → una consulta
  por tag/url-primaria "no lo ve". Para auditar captura por colección hay que escanear `sources[]`,
  como hace `audit_lista_full_bidir.py` (autoridad de faltantes globales). No hubo bug de parser ni se
  necesitó retrofit; los mecanismos que SÍ causarían under-capture (#41 leer cualquier `ventana_id<N>`,
  #60 propagar el volumen) están corregidos y lockeados con tests (`test_lmc_especial_in_non_id1_ventana_is_captured`,
  `test_lmc_two_especiales_same_section_get_distinct_clusters`).
- **Casos ambiguos que se SALTAN**: `dedup_synthetic_source` loguea (no auto-fusiona)
  componentes multi-hash sospechosos (packs especial+variant). Revisar a mano si aparecen.
- **Label `Edición original:` no aprovechado** (auditoría Chrome 2026-06-11): la cabecera
  trae `<b>Edición original:</b> Kanzenban (完全版)` / `Wideban (ワイド版)` — es la señal
  ESTRUCTURADA de la edición japonesa de origen. En las kanzenban españolas inspeccionadas
  (id=4753, id=2661) el `Formato:` NO contiene "kanzenban" (dice "Tomo A5 … rústica con
  sobrecubierta"); hoy la detección depende del título "(Kanzenban)" (P0-A), que en esos
  casos alcanza. NO se agregó como heurístico premium a propósito: describe la edición
  JAPONESA, no la española, y el historial de sobre-marcado premium (heurístico A5
  eliminado, gotcha #41/#51) pide evidencia de misses en corpus antes de sumarlo. Candidato
  si aparecen kanzenban sin "(Kanzenban)" en el título.
- **`Nota:` con señales premium en prosa** ("incluye las páginas a color originales",
  id=2661): texto libre, no extraído. Mismo criterio: no sumar heurístico sin evidencia.
- **`Color:` es crédito de COLORISTA** (persona, ej. "Color: Yoko Kamio" id=2661), NO
  atributo "a todo color". Si alguna vez se agrega heurístico de full-color, NO matchear
  este label (falso positivo garantizado). Hoy no hay heurístico que lo mire (verificado).
- **`Títulos de <colección>`** (H2, visto en tomo doble id=3000): mapeo `nºN - Incluye
  <serie> X-Y JAP`. Hoy se DESCARTA (correcto, no son items); oportunidad futura: extraer
  el mapeo tomo-doble → tomos japoneses como metadato.

---

## 10. Runbook / comandos útiles

```bash
# Scrape (deja raw, sin standardize):
scripts/scrape_delta.sh          # novedades recientes (calendar)
scripts/scrape_full.sh           # catálogo completo (lista.php)

# Re-aplicar reglas duras (idempotente, sin red):
.venv/bin/python scripts/retrofit/enforce_listadomanga_rules.py

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Auditoría de red (re-fetchea 3436 colecciones, ~3-5 min):
.venv/bin/python scripts/audit_lista_full_bidir.py
.venv/bin/python scripts/retrofit/reconcile_lista_stale.py --dry-run

# Ingesta puntual de colecciones por id:
echo "1606 2857" > /tmp/ids.txt
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki listadomanga-collections \
    --coleccion-ids-file /tmp/ids.txt --workers 6

# Re-procesar colecciones perdidas por error de red en el último bootstrap:
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki listadomanga-collections \
    --coleccion-ids-file logs/listadomanga_network_errors.txt --workers 6

# Ver qué emite el parser para una coleccion (debug):
.venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); import requests, wikis.listadomanga_collections as L; \
  s=requests.Session(); s.headers['User-Agent']='mw/0.2'; \
  [print(c.url[-40:], c.title) for c in L.fetch_collection(2857, s)]"
```

**Antes de cerrar cualquier cambio en ListadoManga**: enforcer → `validate_corpus`
(0 duras) → idempotencia (2× idéntico) → tests (`pytest tests/test_extraction.py`) →
auditoría de red (0/0) → build. Si tocaste algo meaningful, actualiza este doc.
