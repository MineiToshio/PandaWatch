# Fuente: Funside Variant

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-23 (70% de los crudos y 10 de los 14 `standardize_exhausted`,
> pero también 45% de los items nuevos del día — el blacklist por franquicia sigue siendo la vía).
> (2026-08-29: recurrencia del flag no-manga, ver #155; los items flageados quedan
> congelados; `purity` queda `manga_only` por decisión del owner, no re-proponer).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Funside Variant |
| **URL base** | `https://funside.it` |
| **Índice / punto de entrada** | `https://funside.it/collections/a-caccia-di-variant` |
| **Tipo de fuente** | Tienda (retailer) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `retailer` |
| **País(es)** | Italia (`it`) — fuente mono-país |
| **Idioma(s)** | IT (italiano) |
| **Cobertura** | Catálogo ~49 productos de variant covers de manga ("a caccia di variant") |
| **Aporte al corpus** | ~52 items |
| **Parser / módulo** | entrada en `sources.yml` (extractor genérico de HTML) |

**Editoriales que abarca** (del corpus real): Funside (≈49) · JPOP (2) · Star Comics (1).
Nota: `publisher` = editorial real, NO la tienda (#44). La mayoría sale rotulada con la
propia tienda como editorial; las pocas excepciones (JPOP, Star Comics) las captura el
extractor cuando el dato está en el producto.

**Por qué importa / qué aporta de único**: tienda Shopify italiana enfocada en **variant
covers** de manga, un nicho de coleccionismo que otras fuentes IT no concentran.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: Shopify estándar. Índice en
  `/collections/a-caccia-di-variant` (paginado, `max_pages: 5`); cada producto en
  `/products/<handle>`. Los slugs terminan en `-variant`.
- **Estructura del HTML**: selectores Shopify — `item_selector: .product-card`,
  `title_selector: .product-card__title a` (fix 2026-08-24, ver §8 — antes
  `a[href*='/products/']`, gotcha #148). Títulos tipo:
  - "A Tutto Gas vol 2 Variant"
  - "Ai Tempi di Bocchan Perfect Edition vol 3 Variant"
  - "Vita da Slime - A Spasso per Tempest Vol 5 Variant"
- **Identificador de producto**: URL canónica `/products/<handle>`.
- **Anti-bot / quirks**: Shopify HTML plano, sin JS-render. **429 real el
  2026-07-07** (gotcha #114) — no es anti-bot propio de esta tienda, es el borde
  Shopify compartido `23.227.38.0/24` (mismo edge que Dark Horse Direct, Manga
  Dreams y Milky Way) saturado por la concurrencia agregada de las 4 tiendas. Ver
  §8.

---

## 5. Proceso de ingestión — técnico

- **Entrada**: definida en `sources.yml` como `IT - Funside Variant`. Se scrapea en la
  **FASE 1** del pipeline (scrape de sources del YAML vía `manga_watch.py`) con el
  **extractor genérico de HTML**; NO tiene parser propio.
- **Layout Shopify**: los selectores `.product-card` + `.product-card__title a` siguen la
  receta **"Recipe: add a new HTML retailer"** (variante Shopify) de
  [docs/scraper/SOURCES.md](../SOURCES.md). Cada producto del listado = un item.
- **Flujo end-to-end**: entra en la FASE 1 de `scrape_delta.sh` / `scrape_full.sh` junto
  al resto de fuentes del YAML; luego pasa por los retrofits de cleanup comunes.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Antes**: su `/collections/` se tomaba como un **único item** (el índice). **Ahora** se
  scrapea directo el listado → ~49 productos individuales. Descubierto vía
  `search_discovery`.
- **#16 (Shopify variants multi-tomo) NO aplica**: Funside modela 1 producto = 1 tomo (no
  un `<select>` de tomos). El helper de `shopify_variants.py` está restringido a dominios
  conocidos (hoy `darkhorsedirect.com`).
- **El selector de título capturaba la tarjeta entera con el bloque de precio**
  (gotcha #94, 2026-06-13): `title` quedaba como "{título} - VARIANT Prezzo normale
  €X Prezzo di vendita €X … Aggiungi al carrello" o con prefijo "Aggiungi al carrello
  [Confrontare] …" + sufijo de tienda "GAMES ACADEMY FUNSIDE / POPSTORE" (~58 items).
  Fix: `clean_title` corta desde "Prezzo normale/di vendita/unitario", el prefijo del
  botón y el sufijo "FUNSIDE". **RESUELTO 2026-08-24**: `title_selector` cambiado a
  `.product-card__title a` (ver gotcha #148 y la entrada de más abajo).
- **Junk del botón de carrito rompía la traducción de la `description` cuando aparecía
  al PRINCIPIO en vez de al final (2026-07-07, gotcha #119)**: la `description` de
  Funside a veces viene como "Sconto Aggiungi al carrello Confrontare {título} Prezzo…"
  — el botón "Aggiungi al Carrello" pegado al INICIO, no al final como asumía el regex
  de `translate_descriptions.py::_clean_description_for_translation`. El regex viejo
  (ancla `$` + `.*` greedy) borraba desde el primer match hasta el final del texto SIN
  chequear si el match estaba temprano — se comía la description entera y
  `description_es` quedaba como "Descuento". Fix (en `translate_descriptions.py`, no en
  el parser de esta fuente): `_strip_it_cart_suffix()` sólo trata el match como "cola
  removible" si arranca dentro de los últimos 150 caracteres del texto Y queda cuerpo
  sustancial (≥40 chars) antes — si el botón aparece temprano (como acá), se deja
  intacto. Nota: distinto del fix de gotcha #115 (el badge "Sconto" pelado en el
  `title`, más abajo) — éste es sobre la `description`, no el `title`.
- **HTTP 429 en el primer delta real post-mejoras (2026-07-07, gotcha #114)**:
  `HTTP error 429 Client Error: Too Many Requests` al scrapear
  `/collections/a-caccia-di-variant`. Causa: `funside.it` resuelve al mismo borde
  Shopify `23.227.38.0/24` que Dark Horse Direct, Manga Dreams y Milky Way —
  `--per-host-limit` agrupa por hostname y no ve el rate-limit del borde compartido.
  Fix: `throttle_group: "shopify"` en `sources.yml` — semáforo compartido (limit 1)
  + delay mínimo 2s entre requests del grupo (`--throttle-group-delay`). Monitorear
  el próximo run.
- **Curación LLM non-manga 2026-08-23 (gotcha #148) — EL CASO GRAVE**: 98 de sus
  195 items del corpus fueron marcados `is_manga=false` por el skill
  `/watch-standardize-catalog`, el peor caso de toda la curación de 265 items. Se
  expulsaron 93, se conservó 1 (IL RICHIAMO DI CTHULHU — es el manga de Gou Tanabe)
  y 4 quedaron INCIERTOS en `data/unmapped_series.jsonl` (NINE STONES 3, DARK SOULS
  COFANETTO, JAGUA TALES VOL.2 ×2 — sus hermanos ya están estandarizados como manga
  en el corpus, expulsar sólo uno fragmentaría la serie). Dos causas confirmadas:
  (a) `title_selector: a[href*='/products/']` toma el primer link de la card, que en
  cards con badge de preventa/promo es el texto "USCITA: dd/mm/yy" o "Sconto" en vez
  del título real — **50 items del corpus tienen la fecha/badge como `title`** (12
  ya estandarizados); el título real vive en el slug de la URL y en la `description`
  ("… Vai alla pagina Confrontare TÍTULO Prezzo …"); (b) la colección
  `a-caccia-di-variant` es **~50% cómic occidental** (Bonelli: Zagor/Dragonero/
  Senzanima; Disney IT: Topolino/Paperino; Marvel/DC de Panini IT; Image/IDW;
  webcómic Scottecs) y la fuente NO declara `purity` (default = `manga_only`), así
  que ningún gate determinista la filtraba. ~~**PENDIENTE para el owner**: arreglar
  el `title_selector` y/o declarar `purity: mixed`.~~ **(a) RESUELTO 2026-08-24**:
  `title_selector` → `.product-card__title a` (verificado 45/45 títulos en vivo);
  retrofit `scripts/retrofit/fix_funside_frozen_titles_20260824.py` corrigió los 19
  items ya congelados (`standardized_at`) leyendo el título real de la `description`
  (patrón "Confrontare TÍTULO Prezzo normale"). **(b) `purity` queda `manga_only`
  por decisión del owner** (ver sección de más abajo) — NO se declara `mixed`.

---

## 9. Pendientes / limitaciones conocidas

- `publisher` queda mayormente como "Funside" (la tienda) en vez de la editorial real
  (#44). Los productos no siempre exponen la editorial original; quedan ≈49 items así.
- **INVESTIGADO 2026-08-24, sin fix aplicado (no es cambio de esta fuente): 142 items
  del corpus con `author` == "Batman ELDEN RING ARTBOOK"**. NO es un problema de la
  ficha de Funside en sí — es un bug del fallback genérico de extracción de autor en
  `manga_watch.py` (`fetch_metadata_from_detail`, línea ~2944 en adelante) que afecta a
  cualquier fuente que caiga a su último recurso. Causa raíz: cuando ni JSON-LD ni
  metatags ni links `/autor/` traen autor, el fallback toma
  `soup.body.get_text(" ", strip=True)[:3000]` (los primeros 3000 caracteres de TODO el
  texto visible de la página, sin excluir header/nav) y le corre `AUTHOR_BY_PATTERN`
  (`(?:^|\s)(?:by|par|di|du)\s+...`). En las páginas de producto de Funside, ese primer
  tramo de texto es el **mega-menú/nav site-wide** con dos tarjetas promo adyacentes:
  "Scopri i Comics di **Batman**" (categoría) y "**ELDEN RING ARTBOOK** - (VOL.1-2)"
  (producto destacado). El italiano "di" (== "of/by") matchea como si fuera un prefijo
  de autoría, y como no hay separador que corte antes del guión de "ARTBOOK - (VOL...",
  el regex captura "Batman ELDEN RING ARTBOOK" completo como si fuera un nombre de
  autor válido (pasa `_validate_author_candidate` porque empieza con mayúscula latina y
  "Batman" no está en `AUTHOR_FIRST_WORD_BLACKLIST`). Fix propuesto (para quien lo
  aplique — **NO tocar `manga_watch.py` sin decisión del owner**): acotar el fallback a
  un contenedor de contenido real (`soup.find("main")`, `.product__info-container` o
  equivalente) en vez de `soup.body` completo, y/o sacar "di"/"du" de
  `AUTHOR_BY_PATTERN` (son preposiciones genéricas en IT/FR, mucho más propensas a falso
  positivo que "by"/"par"). Este bug probablemente afecta a OTRAS fuentes con el mismo
  fallback y nav site-wide — no es exclusivo de Funside, aunque acá es donde se detectó.
- **RESUELTO (2026-07-07): 7 items con `title` literalmente "Sconto"** (sin
  porcentaje) — `tensura-tempest-tour-funside-variant-it-5/8`,
  `tokyo-duel-funside-variant-it-8`, `mf-ghost-funside-variant-it-2/3`,
  `kumichou-musume-to-sewagakari-funside-variant-it-1/5`. Es el MISMO mecanismo que
  el badge de Dynit (gotcha #115, "Sconto N%") pero SIN el número/porcentaje: el
  regex `_is_sale_badge()` exigía un `\d{1,3}` junto a "sconto", así que un badge
  "Sconto" pelado no matcheaba y `_first_non_badge_title()` no lo salteaba. **Fix**:
  `_SALE_BADGE_RE` extendido con la alternativa de palabra "desnuda"
  (`sconto`/`sale`/`offerta`/`descuento`/`rebaja`/`réduction` como texto COMPLETO,
  vía `fullmatch`, sin sobre-matchear títulos que la contengan en contexto tipo
  "Garage Sale Vol 1"). Regresión en `tests/test_ingestion_fixes.py`
  (`test_is_sale_badge_detecta_badges_desnudos` y vecinos). Los 7 títulos "Sconto"
  del corpus se auto-curan en el próximo scrape vía upsert (sin retrofit manual).

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "IT - Funside Variant"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "funside"
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
→ tests (`pytest tests/test_extraction.py`) → build.

---

## 2026-08-24 — el `purity` sin declarar volvió a costar: 45 de 48 items nuevos eran cómic occidental

Delta diario (`logs/scrape-delta-2026-08-24-183301/`). La fuente fue la **#1 en items
nuevos de toda la corrida** (48 de 78 detectados), pero al estandarizar,
`/watch-standardize-catalog` marcó `is_manga=false` en **45 de esos 48**: 37
`western_comic`, 3 `western_comic_dc`, 3 `western_comic_marvel`, 1 `western_comic_idw`
+ Disney/videojuegos en el resto de la cola. Es exactamente la causa (b) ya documentada
en §8 (la colección `a-caccia-di-variant` es ~50% cómic occidental y la fuente NO
declara `purity`, default `manga_only`, así que ningún gate determinista la filtra).

Novedad respecto a 2026-08-23: **no es un rezago histórico que se curó una vez** — la
fuente sigue inyectando cómic occidental en cada delta, y cada corrida se lo come el
LLM (tokens) y termina en la cola de curación manual del owner. Los 45 items quedaron
PENDIENTES (sin `standardized_at`) y registrados en `data/unmapped_series.jsonl` con
reason `llm_non_manga` — no se borran solos (gate determinista, no el veredicto LLM).

**PENDIENTE para el owner** (sin aplicar por la rutina diaria — es cambio de
configuración): declarar `purity: mixed` para esta fuente en `sources.yml`. Con eso el
gate exige STRONG manga hint y el cómic occidental se filtra upstream, antes de gastar
LLM y antes de llegar a la cola manual. Es el mismo PENDIENTE de §8, ahora con costo
medido por corrida.

## 2026-08-24 — DECISIÓN DEL OWNER: `purity` queda `manga_only` (NO re-proponer)

El owner evaluó el pendiente de arriba (declarar `purity: mixed`) y decidió **dejar la
fuente como está** (`purity` sin declarar = `manga_only`): las ~42 variants de manga
reales que aporta valen más que el ruido de cómic occidental, y ese ruido ya se mitiga
con el `title_selector` arreglado (ver entrada de sources.yml, 2026-08-24 — ya no
inyecta títulos-fecha basura) + el filtro determinista de la curación (comics
blacklist + expulsión manual del `llm_non_manga`). Cambiar a `purity: mixed` sigue
siendo técnicamente viable si en el futuro el ruido crece o el costo LLM se vuelve
un problema real, pero **no se re-implementa por defecto** — es una decisión de
producto tomada, no un pendiente abierto. Si se re-evalúa, partir de la medición de
§ "el `purity` sin declarar volvió a costar" (45/48 items nuevos de una corrida eran
cómic occidental) como baseline de costo.

## 2026-08-25 — la fuente inyecta cómic americano: corre como `manga_only` sin serlo

Delta diario (`logs/scrape-delta-2026-08-25-110223/`). Funside fue **la fuente más
productiva del run — 15 de los 31 items nuevos (48%)** — y la mayoría de esos 15 **no
son manga**:

- GODZILLA – Hic Sunt Dracones III (variant con cofanetto)
- STRAY DOGS – Giorni da cani / Cani randagi (×4 variants: Alien, Squid Game, Bram
  Stoker's Dracula, The Blair Witch Project, La Cosa) — de Tony Fleecs, cómic US
- FANTASTICI QUATTRO 1 / 470 – variant di Mike McKone (Marvel)
- ESPATRIATI X-MEN vol. 1 – variant di Rickie Yagawa (Marvel)
- STREET FIGHTER LEGENDS: Chun-Li – cover variant D
- DIABLO – L'alba dell'odio, UNDISCOVERED COUNTRY 3, AMERICAN CAPER vol. 1,
  CHECK, PLEASE! #Hockey vol. 1, ULTIMATE IMPACT: Reborn

Sobre el corpus acumulado: **128 items de Funside, de los cuales ≥17 son cómic US
identificable por marca** (Marvel/Image/Street Fighter/Godzilla/Stray Dogs); el número
real es mayor porque la heurística por marca no cubre los títulos indie.

**Causa raíz (estructural, no del parser).** La entrada en `sources.yml` **no declara
`purity`**, así que toma el default `manga_only` (`manga_watch.py:457`):

```yaml
- name: IT - Funside Variant
  url: https://funside.it/collections/a-caccia-di-variant
  kind: html
  enabled: true
  # ← sin purity: hereda manga_only
```

Con `manga_only` el gate NO exige STRONG manga hint (decisión #3), así que todo lo que
la colección "A caccia di variant" liste entra al catálogo. Pero Funside **no es una
editorial de manga**: publica variant covers de cómic americano y manga indistintamente,
que es exactamente la definición de un catálogo `mixed`. La purity declarada contradice
lo que la fuente realmente es.

Efecto colateral visible: estos títulos llegan además a `data/unmapped_series.jsonl`
(135 entradas de Funside en el audit de esta corrida, la fuente #1 de la cola), donde
consumen curación manual para series que no deberían estar en el catálogo.

**Para el owner (no aplicado — tocar `sources.yml` es decisión suya):** declarar
`purity: mixed` en esta entrada. Con eso el gate pasa a exigir STRONG manga hint y los
variants de Marvel/Image quedan afuera, mientras los variants de manga que Funside sí
publica siguen entrando. El retorno es doble: deja de contaminarse el catálogo y se
descarga la cola de aliases de su mayor emisor de ruido. Requiere una pasada de
`filter_non_manga.py` para limpiar los ya ingresados.

## 2026-08-26 — CICLO DIARIO: los mismos ~15 items se expulsan y se re-ingestan cada corrida

Delta diario (`logs/scrape-delta-2026-08-26-110228/`). Esta entrada NO re-propone
`purity: mixed` (decisión del owner del 2026-08-24, cerrada). Documenta un patrón
**distinto y nuevo**: los items de esta fuente no se estabilizan nunca en el corpus —
**rotan en un ciclo diario** que consume LLM de Tier 3 (el caro) en cada corrida.

**La evidencia.** Conteo de items de Funside en el corpus por fecha de detección:

```
2026-05-23:  8      2026-08-22: 39
2026-05-24: 47      2026-08-24:  1
2026-06-12: 18      2026-08-26: 15
TOTAL: 128
```

Hay **cero items con fecha 2026-08-25**, pese a que la entrada del 08-25 de esta misma
ficha documenta que ese día Funside aportó **15 de los 31 items nuevos** — y hoy vuelve a
aportar exactamente 15. El total se mantiene clavado en 128 desde el 08-25. No son items
nuevos: **son los mismos 15, re-ingestados con un `detected_at` fresco**. Los títulos
coinciden uno a uno con los listados en la entrada del 08-25 (Stray Dogs ×5, Godzilla ×2,
Espatriati X-Men, Fantastici Quattro, Street Fighter, Diablo, Undiscovered Country,
American Caper, Check Please, Ultimate Impact).

**El mecanismo (las dos mitades encajan).** Es un bucle estable entre el gate LLM y el
gate determinista, y ninguna de las dos mitades está mal por separado:

1. Fase 1 scrapea Funside; los variants de cómic US entran (la fuente corre `manga_only`,
   así que el gate no exige STRONG manga hint — decisión #3).
2. La estandarización los marca `is_manga=false`. Desde la política del 2026-07-07 ese
   veredicto **ya no expulsa**: el item queda PENDIENTE (sin `standardized_at`) y se
   registra en `unmapped_series.jsonl` con reason `llm_non_manga` — hoy, **13 de las 25
   entradas `llm_non_manga` de la corrida son de Funside**.
3. En la corrida SIGUIENTE, `filter_non_manga` (el gate determinista, que sí expulsa) ya
   tiene el item enriquecido por la estandarización y lo rechaza por `comic_franchise`
   — hoy 172 de los 262 rechazos fueron por ese motivo.
4. Pero la Fase 1 de esa misma corrida **ya lo volvió a listar** desde la colección "A
   caccia di variant", que no cambió. Vuelve al paso 1.

El ciclo se cierra porque la fuente re-lista el mismo catálogo cada día y la expulsión
ocurre **después** del scrape, nunca antes. Cada vuelta paga estandarización Tier 3 sobre
los mismos ~15 títulos.

**Costo real.** No es corrupción de datos (el corpus queda consistente y `validate_corpus`
da 0 duras), es **costo recurrente y ruido de curación**: ~15 items/día de LLM caro que
nunca converge, +13 entradas/día a la cola `llm_non_manga` que el owner tiene que revisar
a mano, y un `detected_at` que miente (marca como "hallazgo de hoy" algo visto hace días
— contamina el reporte matinal, que es justamente la salida de más valor de la rutina).

**Para el owner (no aplicado — es decisión suya).** El punto a atacar es el paso 4: que la
expulsión sea *estable* en vez de repetirse. Tres vías, de menos a más invasiva:

- **(a) Blacklist al ingreso.** Sumar las marcas que ya se repiten todos los días
  (Stray Dogs/Tony Fleecs, Godzilla, Undiscovered Country, American Caper, Check Please,
  Ultimate Impact, Diablo) a `data/comics_blacklist.yml`. Corta el ciclo en el paso 1, es
  local a datos (no toca código ni config de fuentes) y no depende de la purity. Es la de
  mejor relación costo/beneficio y no colisiona con la decisión del 08-24.
- **(b) Memoria de expulsión.** Que un item expulsado por `comic_franchise` quede
  registrado para que el ingest no lo vuelva a levantar. Es la solución de fondo del
  patrón (aplicaría a cualquier fuente, no sólo a esta), pero es cambio de pipeline.
- **(c) Reconsiderar `purity: mixed`.** Sigue vetada por la decisión del 08-24 y **no se
  propone acá**; se menciona sólo para dejar constancia de que este ciclo es un dato nuevo
  que no existía cuando esa decisión se tomó, por si el owner quiere re-evaluarla con
  esta evidencia.

## 2026-08-26 — ✅ RESUELTO: el ciclo se cortó con la comics blacklist (vía (a))

El owner aprobó la **vía (a)** de la entrada anterior el mismo día. Aplicado:

**Qué se hizo.** Se agregaron 11 términos a `franchise_keywords` en
`data/comics_blacklist.yml`, bajo la sección "Curación 2026-08-26". La blacklist
**se evalúa siempre**, no sólo en fuentes `mixed` (`manga_watch.py::is_likely_manga`,
paso 0a-bis — decisión #3), así que corta el ingreso aunque Funside siga en
`manga_only`. **No se tocó `sources.yml`**: la decisión del owner del 2026-08-24
(`purity` queda `manga_only`) sigue intacta.

**Verificación previa a agregar cada término** (el paso que evitó el desastre): se
matcheó cada candidato contra el corpus completo antes de escribirlo.

- ❌ **"Stray Dogs" pelado habría borrado 12 items de "Bungo Stray Dogs"**, que SÍ es
  manga (Manga-Sanctuary, Mangavariant, ListadoManga, Manga Dreams, AnimeClick). Se
  usaron en su lugar los títulos italianos del cómic de Tony Fleecs: `Cani Randagi` y
  `Giorni da Cani`.
- ❌ **"Diablo" pelado habría matado "Jiraishin Diablo Artbook"**. Se usó su subtítulo
  italiano: `L'Alba dell'Odio`.
- ⚠️ `Street Fighter` se acotó a `Street Fighter Legends` (cabecera de UDON) porque
  Street Fighter tiene adaptaciones manga reales. `Godzilla` va pelado (los dos títulos
  de Funside no comparten subtítulo): hoy 0 colisiones, pero si entra un Godzilla manga
  legítimo va a `title_exceptions`, NO se quita de la blacklist.
- Marvel: se agregaron `XMEN` (sin guion — la keyword `X-Men` existente no lo matcheaba)
  y `Fantastici Quattro` (título italiano; existía `Fantastic Four` y el pt-BR).

**Resultado.** `filter_non_manga --dry-run` capturó **exactamente 15 items, todos de
Funside/Star Comics, 0 colaterales**. Aplicado: corpus **14 274 → 14 259**. Gates en
verde: `pytest tests/test_extraction.py` 712 passed, `validate_corpus.py` exit 0
(0 violaciones duras), build OK (3537 series).

**Efecto esperado.** El ciclo se corta en el paso 1 (ingreso), así que estos títulos ya
no vuelven a entrar ni a consumir estandarización Tier 3. Quedan ~2 items/día de ruido
residual de Star Comics (`300 Variant Edition`, `Faith n.1`) que **no se blacklistearon
a propósito**: "300" y "Faith" son demasiado genéricos y el riesgo de falso positivo
supera el beneficio. Se curan a mano si molestan.

El patrón general (LLM que no expulsa + gate que expulsa después del scrape = bucle)
quedó documentado como **gotcha #154**, porque puede reaparecer en cualquier fuente que
re-liste su catálogo cada corrida.

## 2026-08-28 — el corte del ciclo AGUANTÓ: de ~15 items diarios a 1

Delta diario (`logs/scrape-delta-2026-08-28-160959/`). Verificación del fix del 08-26
(términos nuevos en `data/comics_blacklist.yml`): **funcionó**. Donde antes se
re-ingestaban ~15 items de cómic occidental por corrida, hoy quedó **1 solo**:

- `IMPERIAL VOL.1 - VARIANT INTERLOCKING JAVIER GARRÓN 1 DI 4` — cómic americano
  (Marvel), no cubierto por los términos actuales de la blacklist. Quedó pendiente en
  `data/unmapped_series.jsonl` (reason `llm_non_manga`).

O sea: la vía (a) —blacklist determinista— sigue siendo la correcta, pero es
**incremental por título**: cada serie occidental nueva que Funside publique va a
filtrarse una vez hasta que se agregue su término. Es el costo conocido de mantener
`purity: manga_only` (decisión del owner del 08-24, no re-proponer).

**Para el owner (no aplicado):** agregar `"IMPERIAL"` (o el patrón de la serie) a
`data/comics_blacklist.yml`. Retorno: cierra el último residual del ciclo.

## 2026-08-29 — vuelve a flaggearse, y esta vez el flag se PERDIÓ (gotcha #155)

Delta diario (`logs/scrape-delta-2026-08-29-110244/`). `IMPERIAL VOL.1 - VARIANT INTERLOCKING JAVIER GARRÓN 1 DI 4` (variant de Marvel) volvió a entrar y a ser flageado por el LLM como no-manga — el término no está cubierto por los 11 que se agregaron a `data/comics_blacklist.yml` el 2026-08-26.

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

## 2026-08-30 — 3er día seguido con IMPERIAL, y 131 series suyas en la cola de aliases

Delta diario (`logs/scrape-delta-2026-08-30-111729/`). Dos datos nuevos:

1. **`IMPERIAL VOL.1 - VARIANT INTERLOCKING JAVIER GARRÓN 1 DI 4` entró por 3ª corrida
   consecutiva** (08-28 → 08-29 → 08-30), otra vez flageado `llm_non_manga` y otra vez
   no expulsado por los gates deterministas. Sigue en el corpus como `product_type:
   manga`, `series_display: Imperial Variant Interlocking Javier Garrón Di 4`.
   **Esta vez el flag SOBREVIVIÓ**: la corrida no ejecutó
   `/watch-enrich-series-aliases`, así que la fila sigue viva en
   `data/unmapped_series.jsonl` en vez de perderse el mismo día por gotcha #155.

2. **Dimensionamiento nuevo — la fuente es la principal contaminadora de la cola de
   aliases**: de las 486 filas de la cola de series sin canónica de este run, **131 (27%)
   son de Funside**, y una muestra de 35 da ~10% manga contra ~90% cómic occidental
   (Batman, Spider-Man, Marvel Miniserie, DC Crossover, The Walking Dead, Zagor,
   Topolino, Sin City, Undiscovered Country, Diablo, Dark Souls…). De esas 131, **90 son
   huérfanas**: su `sample_url` ya no existe en `items.jsonl` porque los gates de la
   FASE 3 sí las expulsaron después de que la fila se escribiera en la FASE 1.

   O sea: el ciclo tiene un segundo costo además del corpus — cada corrida deja ~131
   series basura en la cola que después consume `/watch-enrich-series-aliases`, con
   riesgo de acuñar canónicas de cómic occidental en `data/series_aliases.yml`.

`purity` sigue en `manga_only` por decisión cerrada del owner (08-24) y **no se
re-propone**. Se deja constancia del volumen porque es información nueva: hasta ahora el
costo medido era "~1-15 items de corpus por corrida", y el costo real sobre la cola de
curación es un orden de magnitud mayor.

## 2026-08-31 — 4º día seguido; 3 títulos NUEVOS de cómic occidental y 259 filas en la cola

Delta diario (`logs/scrape-delta-2026-08-31-110202/`). El patrón no se movió, pero
cambió la composición:

1. **IMPERIAL entró por 4ª corrida consecutiva** (08-28 → 08-29 → 08-30 → 08-31),
   otra vez `llm_non_manga`, otra vez no expulsado por los gates deterministas, otra
   vez vivo en el corpus como `product_type: manga`.

2. **Nuevo: 3 títulos que NO se habían visto antes**, los tres cómic occidental y los
   tres flageados `western_comic` por el LLM en esta misma corrida:
   - `TOTALLY TWISTED TALES - VARIANT`
   - `LA MALEDIZIONE DEL DRAGO D'ORO - VARIANT`
   - `HOLLYWOOD HORROR STORIES - GIOCHI PERICOLOSI - VARIANT`

   Esto matiza el "el corte del ciclo aguantó" del 08-28: la comics blacklist corta los
   términos YA vistos, pero la fuente publica títulos nuevos de cómic occidental de
   forma continua, así que la blacklist por términos es un parche que envejece — cada
   título nuevo entra hasta que alguien lo agrega. De los 20 items nuevos del corpus de
   hoy, **5 son de Funside y los 5 son cómic occidental** (25% del ingreso diario total
   del pipeline sale de esta sola fuente y es todo fuera de alcance).

3. **La contaminación de la cola de aliases subió de 131 a 259 filas** (172 huérfanas +
   87 vivas). Sigue siendo la fuente #1 de la cola, ahora con el 26% de sus 987 filas.

`purity` sigue en `manga_only` por decisión cerrada del owner (08-24) y **no se
re-propone**. Se deja constancia de que la vía elegida entonces —blacklist por
términos— tiene mantenimiento recurrente por diseño, dato que en 08-26 todavía no se
podía observar.

## 2026-09-01 — denylist del placeholder "Immagine non disponibile" (logo MD)

Ola 3 de depuración de imágenes (ver `docs/reference/images.md` § "OLA 3"). Dos
productos de esta fuente (`outlaw-tamer-epic-rise-funside-variant-it-1`,
`campfire-cooking-in-another-world-funside-variant-it-1`) tenían como ÚNICA foto
el placeholder genérico "MD — Immagine non disponibile" que Funside sirve cuando
no tiene la portada real, en una variante de tamaño (500×500) que NO coincidía
con las 2 firmas ya registradas (500×541 y 500×500 de otro re-encode, ambas de
2026-06-13) — mismo diseño, sha1 distinto. Confirmado visualmente (conversión
AVIF→PNG + lectura) y agregado a `data/placeholder_signatures.json`
(sha1 `51b45316ed9f6d8de41558d52e4eae5ec6b23b86`). Purgado con
`purge_placeholder_images.py --only-reasons signature` (gotcha #161): las 2 filas
quedaron sin ninguna foto (pasan al bucket de búsqueda web / 📚 en la UI). No
cambia nada del parser/selectores/purity de la fuente — es limpieza de imagen,
no de ingestión.

## 2026-09-01 (bis) — el bucle de re-ingesta sigue: 8 de los 56 items nuevos del delta

Delta diario (`logs/scrape-delta-2026-09-01-110203/`). De los **56 items nuevos** que
entraron al corpus en esta corrida, **8 son de esta fuente** — la 2ª que más aportó,
detrás de Manga-Sanctuary (14). Los 8 quedaron **sin estandarizar**, con veredicto LLM
`is_manga=false` registrado en `data/unmapped_series.jsonl` (reason `llm_non_manga`):

```
IMPERIAL VOL.1 - VARIANT INTERLOCKING JAVIER GARRÓN 1 DI 4
TAKAMINE, RIMETTITI LE MUTANDINE! VOL.5 - VARIANT
KAMIYAMA-SAN: COSA C'E' NEL SACCHETTO? (SENSEI) VOL.3 - VARIANT
TRANSFORMERS VOL.4 - VARIANT
GOKUSEN VOL.1 - VARIANT
TOTALLY TWISTED TALES - VARIANT
LA MALEDIZIONE DEL DRAGO D'ORO - VARIANT
HOLLYWOOD HORROR STORIES - GIOCHI PERICOLOSI - VARIANT
```

Es **exactamente el patrón de gotcha #154** que la nota del 08-26 dejó documentado
como "mantenimiento recurrente por diseño": el veredicto del LLM no expulsa (correcto,
2026-07-07), el gate determinista expulsará en la próxima corrida a los que matcheen
la blacklist, y los que no matcheen vuelven a entrar mañana. La corrección del 08-26
(11 términos nuevos en `data/comics_blacklist.yml`) no cubre estos títulos: `IMPERIAL`,
`TRANSFORMERS`, `TOTALLY TWISTED TALES`, `LA MALEDIZIONE DEL DRAGO D'ORO` y
`HOLLYWOOD HORROR STORIES` son cómic occidental / licencias no-manga que no comparten
término con lo ya blacklisteado.

Matiz importante: **no todos son fuera de alcance**. `GOKUSEN`, `TAKAMINE, RIMETTITI LE
MUTANDINE!` y `KAMIYAMA-SAN` SÍ son manga japonés — el LLM los marcó `is_manga=false`
probablemente por el título italiano en mayúsculas sin contexto de serie. O sea la cola
`llm_non_manga` de esta fuente es MIXTA y no se puede purgar en bloque; necesita la
curación a mano del playbook (`docs/reference/conventions.md`).

**Nada aplicado**: no se tocó `purity` (decisión cerrada del owner 08-24, no se
re-propone), ni la blacklist, ni se borró ninguna fila de la cola.

## 2026-09-02 — otro placeholder MQ "IMMAGINE NON DISPONIBILE" (`cover_*.jpg`, tercera firma)

`calledia-club-funside-variant-it-1` tenía como única foto el mismo placeholder genérico
"MQ · IMMAGINE NON DISPONIBILE" ya documentado el 2026-09-01 (arriba), pero en una URL con
patrón distinto (`/cdn/shop/files/cover_<uuid>.jpg?v=...&width=500` en vez de
`/products/<slug>.jpg`) y sha1 distinto de las 3 firmas previas. Detectado en la Etapa 1
de triage de imágenes (`docs/reference/images.md` § "Etapa 1 — resultados"). Agregado a
`data/placeholder_signatures.json` (sha1 `f5bbb15ab451b1cadf34781d0a8b78e3e4f2bea5`, dims
500×541) y purgado con `purge_placeholder_images.py --only-reasons known,signature`
(gotcha #176): el item quedó sin ninguna foto. Cuarta firma sha1 de este mismo
placeholder registrada en total — confirma que Funside re-encodea/regenera el mismo
gráfico de "sin imagen" con hashes distintos según el path/CDN por el que lo sirve, así
que la denylist por sha1 sigue necesitando una entrada nueva cada vez que aparece una
variante, no hay un fragmento de URL estable que las cubra todas sin arriesgar portadas
reales (`/cdn/shop/files/` también sirve portadas legítimas).

## 2026-09-02 — 4 cómics occidentales nuevos pese a la blacklist del 08-26

Delta diario (`logs/scrape-delta-2026-09-02-110142/`). Entraron como items nuevos
`IMPERIAL VOL.1 - VARIANT INTERLOCKING JAVIER GARRÓN 1 DI 4`, `TOTALLY TWISTED TALES -
VARIANT`, `LA MALEDIZIONE DEL DRAGO D'ORO - VARIANT` y `HOLLYWOOD HORROR STORIES -
GIOCHI PERICOLOSI - VARIANT` — los cuatro re-flageados `llm_non_manga`
(`western_comic` / `non_manga_comic`) y los cuatro vivos en el corpus.

Lectura para el owner: los 11 términos agregados a `data/comics_blacklist.yml` el
2026-08-26 cortaron ESAS licencias, no el mecanismo. La fuente publica variantes de
cómic occidental continuamente, así que la blacklist por término es una carrera que se
pierde de a una licencia por vez. Es la misma conclusión que en `it-star-comics.md`
(recurrencia nº6 el mismo día): el arreglo estructural es acotar qué barre el search de
la fuente, no seguir enumerando títulos.

Nada aplicado: `purity` no se re-propone (decisión cerrada del owner 08-24) y la
blacklist no se tocó.

### RESUELTO el mismo día (2026-09-02) — el owner pidió arreglar las fuentes

Los 4 cómics occidentales quedaron EXPULSADOS vía `data/comics_blacklist.yml`:
`"Transformers"`, `"Imperial"` (evento Marvel 2025), `"Totally Twisted Tales"`,
`"Hollywood Horror Stories"` y `"Maledizione del Drago"`. Cada keyword se midió contra
el corpus COMPLETO antes de agregarla: todas matchean sólo los items fuera de alcance,
0 manga real.

**`purity` sigue sin tocarse, y ahora hay dato duro que respalda esa decisión del owner
(08-24)**: la fuente tiene 122 items y son ~96% manga real (My Dress-Up Darling, Komi,
One-Punch Man, Rent-a-Girlfriend, Vita da Slime, Nagatoro, Nina the Starry Bride…). Poner
`purity: mixed` exigiría STRONG manga hint, y los títulos italianos de Funside no lo
tienen más allá de "vol N" — habría destruido más de 100 manga legítimos para ganar 4.

Esto **corrige la recomendación del reporte matinal del 09-02** ("el arreglo estructural
es acotar qué barre el search, no seguir enumerando títulos"): con 96% de acierto, la
enumeración por franquicia es la herramienta correcta, no un parche. La lección real es
medir la composición de la fuente antes de proponer cambios estructurales.

---

## 2026-09-03 — el campo `author` es basura en TODA la fuente: 117 entries con el mismo texto de promo

**Hallazgo del delta diario.** El log de scrape mostró 174 líneas de esta fuente con
`autor: Batman ELDEN RING ARTBOOK`. No es un caso raro: es **el mismo string para todos
los productos que la fuente devuelve con autor**.

Medido contra el corpus:

```
items con author no vacío:            7040
autor #1 del corpus entero:  102 items — "Batman ELDEN RING ARTBOOK"
                              88 items — Kentaro Miura
                              71 items — Rumiko Takahashi
```

Es decir: **el "autor" más frecuente de PandaWatch no es un autor** — supera a Miura,
Takahashi, Isayama y Toriyama. Desglose por fuente de las 102 filas afectadas:

| Fuente | entries |
|---|---|
| IT - Funside Variant | 117 |
| IT - SocialAnime Variant | 1 |
| IT - AnimeClick (edizioni speciali) | 1 |
| IT - Star Comics (search) [variant] | 1 |

(117 > 102 porque un item consolidado puede tener varias `sources[]` de Funside.)

Ejemplos de items contaminados — todos manga legítimo, sólo el autor está mal:

- `SPECIALE VENT'ANNI COFANETTO CELEBRATIVO - CONTIENE 20 VARIANT CO…`
- `SOFFIO PERFECT EDITION - VARIANT`
- `SE INSISTI 2 - VARIANT DELUXE CON BOOKLET`
- `TALES OF AN IMAGINARY DEADMAN (BOX 4 VOLUMI) - EDIZIONE VARIANT`
- `NON TORMENTARMI, NAGATORO! 1 - VARIANT`

### Diagnóstico

El string mezcla dos franquicias sin relación entre sí (**Batman** + **Elden Ring
Artbook**) y no cambia entre productos → **no sale de la ficha del producto**. Es un
elemento **global de la página** (banner de promo, carrusel de "in evidenza" o menú de
categorías destacadas) que el selector de autor está levantando porque en la ficha real
no hay campo de autor y el selector cae al primer match del documento.

Es el **mismo patrón de la gotcha #187** (una lista CSS separada por comas NO es una
lista de prioridad: matchea por orden en el DOCUMENTO, no por orden en la lista), que en
esta misma tanda hizo que Dynit capturara "Sconto 10%" como título. Acá el síntoma es
`author` en vez de `title`, pero la causa es la misma clase de defecto.

### Impacto

**Bajo pero real y creciente.** El `author` no participa de `cluster_key`, `edition_key`
ni de los gates de filtrado, así que **no corrompe la agrupación ni expulsa nada**. Pero:

- se muestra en la UI (ficha de detalle) → 102 items le atribuyen a Batman/Elden Ring
  obras de autores japoneses;
- envenena cualquier agregación por autor (un futuro "ver todo de este autor");
- crece ~4-8 items por delta mientras el selector siga como está.

### Recomendación (NO aplicada — decisión del owner)

**No tocar el selector a ciegas.** Dos vías, en orden de preferencia:

1. **Acotar el selector de autor al contenedor de la ficha** (no al `document`), igual
   que se hizo con Dynit en la gotcha #187. Es el fix de MECANISMO y arregla también los
   casos sueltos de SocialAnime/AnimeClick/Star Comics.
2. **Si la ficha de Funside no expone autor**, borrar el selector para esta fuente:
   `author` vacío es estrictamente mejor que `author` falso.

Y en cualquiera de las dos, un **retrofit de limpieza** para las 102 filas ya en el
corpus (blanquear el `author` donde el valor sea el string de promo). Sin retrofit el
fix sólo frena el sangrado, no cura lo ya ingerido.

**Nada de esto se aplicó en esta corrida**: la rutina diaria documenta y recomienda, no
cambia selectores.

---

## 2026-09-04 — FALSO POSITIVO del gate non-manga: un patrón de fútbol se come Blue Lock

**Delta diario del 2026-09-04.** De los 263 items que `filter_non_manga` expulsó en la
FASE 3, **uno es manga legítimo de esta fuente** y se pierde por un patrón pensado para
cromos de fútbol:

```
[non_manga_hard:\b(?:LIGA\s+ESTE|WORLD\s+CUP|FIFA…|UEFA|Champions\s+League|…)\b]
  BLUE LOCK 34 VARIANT COVER WORLD CUP CELEBRATION
  ← IT - Funside Variant
  https://funside.it/products/blue-lock-34-variant-cover-world-cup-celebration
```

### Diagnóstico

**Blue Lock es un manga de fútbol** (Kanehsiro/Nomura, Kodansha; en Italia por Planet
Manga). Su línea de portadas variantes usa nombres temáticos de fútbol — acá *"World Cup
Celebration"* es el **nombre de la variante**, no el producto.

El patrón vive en `_NON_MANGA_HARD` (`scripts/manga_watch.py:3582`), en el bloque
"Deportes / cromos de fútbol". Como es una regla **HARD**, corre en la primera rama de
la cascada de `is_likely_manga()` — **antes** del guard de `purity` y antes de que
cualquier señal STRONG de manga pueda rescatarlo. Un título no tiene forma de sobrevivir
al match, por más manga que sea.

Es exactamente la **deuda estructural ya anotada en CLAUDE.md** (los hints de manga y los
patrones duros no distinguen el MEDIO), vista desde el otro lado: acá el término de
dominio (`World Cup`) no distingue **cromo de fútbol** de **manga sobre fútbol**.

### Impacto

**Acotado hoy, pero permanente y cíclico.**

- **1 item** perdido en esta corrida; **0 items vivos** en el corpus matchean el patrón
  (verificado sobre los 14 377) → no hay daño retroactivo que limpiar.
- Es un **bucle de re-ingesta** del tipo de la gotcha #154: Funside seguirá publicando
  la variante, el scraper la seguirá levantando y el gate determinista la seguirá
  expulsando **en cada delta**, para siempre.
- **Radio de explosión mayor al de hoy**: cualquier manga deportivo con nombre de torneo
  cae igual — Blue Lock (arco del Mundial), Captain Tsubasa, Aoashi, Giant Killing. El
  riesgo crece justo cuando esas líneas sacan ediciones conmemorativas.

### Recomendación (NO aplicada — decisión del owner)

El fix de MECANISMO es **acotar el patrón al producto, no al tema**. En orden:

1. **Exceptuar series de manga deportivo conocidas** antes de la regla dura — el mismo
   mecanismo de `title_exceptions` que se usó para `gangan-joker` en la gotcha #189
   (**y con la misma advertencia**: evaluar la excepción contra el MISMO blob que ve la
   regla, o se destruyen manga por la URL).
2. **Exigir co-ocurrencia de cromo** en el patrón (`álbum`, `sobres`, `cards`, `sticker`,
   `Panini Liga`) en vez de que el nombre del torneo baste solo. Un cromo de fútbol casi
   nunca viene sin una de esas palabras; un manga variante casi nunca las trae.

La vía 2 es la más barata y la que no hay que mantener a mano serie por serie.

**Nada de esto se aplicó**: la rutina diaria documenta y recomienda; tocar los patrones
de filtrado cambia el corpus y es del owner (vía `/watch-review-feedback`).

---

## 2026-09-07 — El campo `author` de esta fuente es el MENÚ del sitio (102 items afectados)

**Hallazgo nuevo, verificado en vivo. Gotcha #193.**

### Síntoma

En el log del delta de hoy, las **174 fichas** que Funside fetcheó devolvieron el mismo
autor, palabra por palabra:

```
[95/1118]  IT - Funside Variant → autor: Batman ELDEN RING ARTBOOK, imgs: 4, isbn: 9788834940709
[101/1118] IT - Funside Variant → autor: Batman ELDEN RING ARTBOOK, imgs: 5, isbn: 9791221950311
...  (174/174 idénticos)
```

Un autor constante entre fichas distintas nunca es un autor: es un elemento global de la
plantilla.

### Causa raíz (reproducida)

Reproducción directa sobre una ficha real
(`funside.it/products/non-tormentarmi-nagatoro-1-variant-games-academy-funside`):

| Extractor | Resultado |
|---|---|
| Schema.org / JSON-LD (`author`/`creator`) | `''` — el LD de Funside sólo trae `brand: J-POP` |
| Pares LABEL/VALUE (ficha técnica) | vacío — la plantilla no expone ficha |
| `<meta name="author">` / `book:author` | ausente |
| Links `/autore/` | ninguno |
| **Fallback `extract_author(body_text[:3000])`** | **`'Batman ELDEN RING ARTBOOK'`** |

La ficha de producto de Funside **no publica autor en ninguna forma estructurada**, así
que el extractor siempre llega al último recurso, que mira los primeros 3000 caracteres
del `<body>`. En esta plantilla Shopify esos 3000 caracteres son **el mega-menú**:

```
… Editori Panini Comics Edizioni Star Comics J-Pop Manga Saldapress Sergio Bonelli
Editore A caccia di Variant! LIBRI & FUMETTI Comics DC Pocket Marvel Must Have
Comics di Batman  Comics degli X-Men …
```

El patrón `di <Nombre>` de `extract_author()` engancha en `Comics **di Batman**` y sigue
hasta el siguiente bloque promocional (`div.mega-menu__promotions`, que en el momento de
la corrida promocionaba `ELDEN RING ARTBOOK - (VOL.1-2)`), produciendo la cadena
`Batman ELDEN RING ARTBOOK`.

No es un quirk de Funside: es un defecto del **mecanismo genérico** que Funside destapa
por tener la navegación más pesada del corpus. La ventana de 3000 caracteres no está
acotada a la región del producto.

### Impacto — real pero acotado a presentación

- **102 de los 122** items de Funside en el corpus llevan hoy `author = "Batman ELDEN
  RING ARTBOOK"`. Los 20 restantes tienen autor correcto (`Junji Ito`, `Tomohito Oda`,
  `Shinichi Fukuda`…) o vacío — son los que sí traían dato estructurado.
- Verificado que `author` es campo **de presentación**: no entra en el scoring, ni en
  `is_likely_manga()`, ni en la blacklist de cómics, ni en la derivación de
  `cluster_key`/`edition_key`. **El corpus no está corrompido** — lo que está mal es lo
  que la UI muestra en 102 fichas.
- Se **re-escribe en cada corrida**: mientras el mecanismo no cambie, cualquier retrofit
  que limpie el campo lo vuelve a llenar con basura en el próximo delta.

### Recomendaciones (NO aplicadas — decisión del owner)

1. **Fix de mecanismo (preferido)**: acotar el fallback a la región del producto antes de
   recortar a 3000 caracteres — `main`, `[role="main"]`, `.product`, `article` — y sólo
   caer al `body` entero si ninguno existe. Cierra la clase entera de fallos (no sólo
   Funside) sin listas por sitio.
2. **Guard barato y complementario**: si el mismo valor de `author` se repite en N fichas
   distintas de una misma fuente dentro de una corrida, descartarlo. Convierte el modo de
   fallo silencioso de hoy en una señal visible.
3. **Limpieza retroactiva**: recién DESPUÉS de (1) — vaciar el campo en los 102 items.
   Hacerlo antes es trabajo que la próxima corrida deshace.

Documentado, no aplicado: tocar el extractor cambia datos del corpus y es decisión del
owner.

### 2026-09-07 (mismo día) — RESUELTO

**Aplicado**, fix de mecanismo + limpieza:

1. `fetch_metadata_from_detail()` ya no lee el `<body>` entero. El último recurso
   ahora corre en **dos pasos separados**: (a) selectores estructurados sobre el
   documento —inequívocos, se aceptan tal cual, incluido el `Autori: Tsutomu Nihei`
   de Panini IT que llega con el label pegado—, y (b) el regex sobre texto plano,
   que lee sólo la **región del producto** (`main`/`article`/`.product`) **con el
   cromo de navegación decompuesto** (`nav`, `header`, `footer`, breadcrumbs,
   mega-menús) y exige que el candidato **tenga forma de nombre propio** y no sea
   un trozo del propio título.
2. `scripts/retrofit/fix_chrome_authors_20260907.py` vació los **102** autores
   basura (denylist explícita `(host, valor)` verificada en vivo — NO heurística:
   una regla de "valor repetido" marcaba como cromo autores reales multi-firma
   como "Buronson / Shō Fumimura" y ni siquiera atrapaba el caso objetivo).

**Verificado en vivo, 8/8 fichas de Funside** devuelven ahora autor vacío (que es
lo correcto: la ficha no publica autor), y **los 24 autores reales que la rama
`di|du` recupera de las fichas italianas siguen intactos** — medidos antes de
tocar nada, justamente para no romperlos. Tests nuevos:
`test_product_region_text_skips_mega_menu_and_breadcrumb`,
`test_looks_like_person_name_accepts_real_authors_rejects_prose`,
`test_author_is_title_fragment_detects_title_echo`.

Nota de paso (no corregido, sin impacto en el corpus): Amazon.it devuelve
`"Segui l'autore"` por el mismo tipo de captura de cromo, pero vía selector
estructurado. Ningún item del corpus lleva ese valor, así que no había nada que
limpiar.

## 2026-09-13 — 5 cómics occidentales viven como crudos en la cola de curación

Al cierre del delta diario quedan 9 items crudos en todo el corpus, y **5 son de esta
fuente**, todos marcados por el LLM de standardize como fuera de alcance (cola
`llm_non_manga`):

| Título | Nota del LLM | `standardize_attempts` |
|---|---|---:|
| STREET SHARKS VOL.1 - SPILLATO - VARIANT BLANK COVER | `western_comic` | 2 |
| DAVID MURPHY 911 - SEASON TWO 6 - VARIANT COVER B | `western_comic` | 2 |
| MORGAN LOST NIGHT NOVELS 1 - VARIANT LUCCA 2019 | `pure_novel` | 2 |
| BUFFY L'AMMAZZAVAMPIRI - STAGIONE 10 VOL.2 - VARIANT COVER | `western_comic` | 1 |
| THE MASK OMNIBUS VOL.1 - VARIANT | `western_comic` | 1 |

Ninguna de las cinco franquicias está en `data/comics_blacklist.yml`, así que el gate
determinista no las expulsa y dependen sólo del veredicto del LLM. Buffy y The Mask
volvieron a detectarse hoy (ya estaban en el corpus), así que pagan Tier 3 en cada
corrida en la que la fuente las re-lista. Es el mismo bucle que el 2026-08-26 se cortó
con 11 términos en la blacklist (#154), y el contador de intentos no alcanza a
escalarlas porque el re-scrape lo borra (#202).

Es consistente con el volumen diario del filtro: `filter_non_manga` expulsa ~237-273
items por corrida, la mayoría `comic_franchise` de esta fuente y de Star Comics
`variant`.

**Para el owner (no aplicado):** agregar `STREET SHARKS`, `DAVID MURPHY 911`,
`MORGAN LOST`, `BUFFY` y `THE MASK` a `data/comics_blacklist.yml` y leer el dry-run
completo de `filter_non_manga.py` antes de aplicar (`THE MASK` es corto: verificar que
no roce títulos de manga reales). `purity` de la fuente sin cambios, según la decisión
del owner del 08-24.

## 2026-09-15 — 13 cómics occidentales NUEVOS entran y quedan crudos en la cola

El delta trajo 16 items de esta fuente sin URL previa en el corpus, y **los 16 son cómic
occidental**. La estandarización marcó 11 como `llm_non_manga` (quedan crudos,
`standardize_attempts` = 1), a los que se suman `BUFFY` y `THE MASK`, que ya venían del
09-13 (13 crudos de la fuente en total):

`AGENTE ALLEN`, `MANIFEST DESTINY`, `KABUKI OMNIBUS`, `COVER VOL.1`, `FIRE POWER` (×3:
vols. 2, 4, 5), `NOCTERRA`, `CROSSOVER 2 - MALEDETTI FUMETTI`, `MARJORIE FINNEGAN`,
`PARINI - NAUFRAGO DELLE STELLE`.

Los otros **5 pasaron la estandarización como manga** (falsos negativos del LLM),
verificado en el corpus: `VOLT STAGIONE 2 - 5`, `THE MOON IS FOLLOWING US VOL.2`,
`NAPALM LULLABY` vols. 1 y 2 y `ULTRAMEGA 4`, todos con `product_type = manga` y
`edition_key` `…-funside-variant-it`. `napalm-lullaby` apareció además como candidata
de aliases y se saltó a propósito, para no acuñar una canónica de cómic occidental.

Los otros 3 de la tabla del 09-13 (`STREET SHARKS`, `DAVID MURPHY 911`, `MORGAN LOST`)
llegaron a `standardize_attempts` = 3: la próxima auditoría los excluye y los escala a
`standardize_exhausted`. O sea que el tope de intentos SÍ corta el bucle cuando la
fuente no re-lista el producto (#202 sólo aplica si lo re-lista).

Ninguna de las franquicias nuevas está en `data/comics_blacklist.yml`. Son sellos de
Image/Saldapress/Bao (`FIRE POWER`, `NOCTERRA`, `ULTRAMEGA`, `NAPALM LULLABY`,
`MANIFEST DESTINY`, `KABUKI`, `CROSSOVER`, `MARJORIE FINNEGAN`, `THE MOON IS FOLLOWING
US`) y fumetto italiano (`AGENTE ALLEN`, `PARINI`, `VOLT`). `ULTRAMEGA`, `NAPALM
LULLABY`, `VOLT` y `THE MOON IS FOLLOWING US` pasaron además la estandarización como
manga y hoy viven estandarizados en el corpus (falsos negativos del LLM, a curar).

**Para el owner (no aplicado):** sumar esas franquicias a `data/comics_blacklist.yml`
leyendo el dry-run COMPLETO de `filter_non_manga.py`; ojo con los términos cortos o
genéricos (`COVER`, `CROSSOVER`, `VOLT`, `KABUKI`) — conviene anclarlos al título
completo (`COVER VOL.`, `CROSSOVER 2 - MALEDETTI`, `VOLT STAGIONE`, `KABUKI OMNIBUS`)
para no rozar manga reales.

## 2026-09-16 — Funside es el 42% de la cola de curación (cómic occidental recurrente)

Medido al cierre del delta del 2026-09-16:

| Métrica | Valor |
|---|--:|
| Items del corpus con fuente Funside | 144 |
| …de esos, todavía CRUDOS (sin `standardized_at`) | 16 |
| Filas de Funside en `data/unmapped_series.jsonl` | **26 de 62 (42%)** |
| — `llm_non_manga` | 23 |
| — `standardize_exhausted` | 3 |

De los **21 items que quedaron pendientes** tras estandarizar hoy, **17 son de
Funside** y **todos son cómic occidental**, no manga:

```
STREET SHARKS VOL.1 - SPILLATO - VARIANT BLANK COVER
MORGAN LOST NIGHT NOVELS 1 - VARIANT LUCCA 2019
BUFFY L'AMMAZZAVAMPIRI - STAGIONE 10 VOL.2 - VARIANT COVER
DAVID MURPHY 911 - SEASON TWO 6 - VARIANT COVER B
MANIFEST DESTINY 1 / FIRE POWER 2·4·5 / NOCTERRA 2 / CROSSOVER 2
THE MASK OMNIBUS VOL.1 / KABUKI OMNIBUS VOL.1 / COVER VOL.1
MARJORIE FINNEGAN - LADRA TEMPORALE / PARINI - NAUFRAGO DELLE STELLE
AGENTE ALLEN - VARIANT COVER ESCLUSIVA FUMETTERIE
```

Son Image Comics, Bonelli, Dark Horse y Boom! — catálogo occidental de una
fumetteria que también vende manga.

**Es el bucle de gotcha #154, ahora medido.** El LLM dice `is_manga=false` (correcto),
pero ese veredicto YA NO expulsa (2026-07-07), así que el item queda crudo; el gate
determinista tampoco lo expulsa porque **ninguna de esas franquicias está en
`data/comics_blacklist.yml`** (287 términos; de los 10 verificados sólo `crossover`
está). Resultado: los mismos títulos vuelven a gastar Tier 3 —la ruta más cara— corrida
tras corrida hasta agotar `standardize_attempts` y escalar a curación manual. El fix de
gotcha #191 (que el contador suba también en la rama `is_manga=false`) está funcionando
—hoy hay items en attempt 1, 2 y 3, y 3 ya escalaron— pero eso **acota el costo, no lo
elimina**: cada título nuevo paga 3 corridas de Tier 3 antes de salir del bucle.

**Recomendaciones (decisión del owner, nada aplicado):**

1. **La herramienta proporcionada sigue siendo el blacklist por franquicia**, no tocar
   `purity` (medido 2026-09-02: Funside es 96% manga en el corpus; acotar sus searches
   destruiría manga real). Agregar los ~14 títulos de arriba a
   `data/comics_blacklist.yml` corta el bucle sin costo colateral.
2. **Mecanismo, más durable**: hoy un `llm_non_manga` de una fuente que RE-LISTA el
   producto todos los días sólo se frena tras 3 corridas de Tier 3. Un veredicto
   `is_manga=false` repetido podría alimentar automáticamente una denylist por URL
   (no por título), que es idempotente y no depende de acertar el término.
3. El 42% de la cola de curación viniendo de una sola fuente hace que la cola sea poco
   útil para lo que fue pensada (series ambiguas). Vaciar la parte de Funside con el
   blacklist devolvería la señal.

### El contador de reintentos se resetea en cada corrida (ampliación de gotcha #202)

Verificado el 2026-09-16 comparando contra el snapshot de slugs pre-run: **10 items de
Funside que YA estaban en el corpus volvieron con `detected_at` de hoy y
`standardize_attempts = 1`** (contador zerado). La URL es idéntica en los 10
(`funside.it/products/<slug>` es un slug estable de Shopify), así que acá **no
interviene el cambio de URL de gotcha #192**: alcanza con que la fuente re-liste el
producto para que el upsert reemplace la fila cruda y pierda el contador.

Efecto perverso: el escape a curación de gotcha #191 sólo se dispara para los items
que Funside **dejó** de listar — justo los que ya no cuestan nada. Los que siguen en
catálogo quedan exentos del límite indefinidamente. Eso explica por qué los 3
`standardize_exhausted` son pocos frente a los 23 `llm_non_manga` que reaparecen.

## 2026-09-18 — mismo patrón, 12 cómics occidentales re-listados

Delta diario: 12 de los 18 veredictos `is_manga=false` del día vuelven a ser cómic
occidental italiano de Funside (Fire Power, Nocterra, Crossover, The Mask Omnibus, Kabuki
Omnibus, Lyndon, Marjorie Finnegan, Parini, Cover, Agente Allen, La Strada).
11 de ellos YA estaban en el corpus (URL idéntica) y volvieron con
`standardize_attempts` en 1 — gotcha #202 confirmada otra vez. 6 items de Funside ya
alcanzaron el tope y salieron a `standardize_exhausted`. La recomendación vigente
(blacklist por franquicia en `comics_blacklist.yml` + preservar `standardize_attempts` en
el merge) sigue sin aplicar.

## Seguimiento 2026-09-23 — sigue siendo la fuente #1 de ruido, y ahora también de señal

Delta del 2026-09-23. Dos lecturas opuestas que conviene tener juntas:

**Ruido**: de los **27 items crudos** que quedaron pendientes al cerrar la corrida,
**19 son de Funside** (70 %), y **10 de los 14 que agotaron sus 3 intentos**
(`standardize_exhausted`, escape hatch de #191) son cómic occidental italiano de esta
fuente: *Street Sharks*, *David Murphy 911*, *Morgan Lost*, *Buffy l'Ammazzavampiri*,
*Manifest Destiny*, *Fire Power* (×2), *La Strada*. Ninguno está en
`data/comics_blacklist.yml`, así que vuelven a entrar en cada corrida, gastan Tier 3 —
la ruta más cara del LLM — tres veces, y recién entonces escalan a curación manual.

**Señal**: al mismo tiempo Funside aportó **5 de los 11 items realmente nuevos del día**
(45 %) y todos son manga legítimo y del tipo que este proyecto busca: *Chainsaw Man 1
Christmas Variant*, *Naruto 1 Christmas Variant*, *Yapoo il Bestiame Umano vol. 2
Variant*, *Shinobi Undercover 1 Variant con maxi toppa*, más la *Dark Souls Mater
Luttuosa Collection* (esta última, cómic occidental).

Esto **refuerza la decisión del owner de 2026-09-02** de no tocar el `purity` ni acotar
las searches: la composición medida entonces (96 % manga) se sostiene, y el ruido se
ataca con el blacklist por franquicia, que es la herramienta proporcionada. Las 8
franquicias occidentales de arriba son candidatas directas de ese blacklist.

**Nada aplicado (decisión del owner).**

---

## 2026-09-24 — Sigue siendo la fuente #1 de cómic occidental en la cola de curación

La corrida de hoy vuelve a mostrar el mismo patrón ya documentado (#202 / blacklist por
franquicia), sin novedades de mecanismo pero con números frescos:

- De las **8 candidatas** que el audit de aliases levantó con ≥2 items, **2 son cómic
  occidental de Funside**: `dark-souls-mater-luttuosa` (Dark Souls, Titan Comics) y
  `napalm-lullaby` (Image Comics, Rick Remender). Ninguna de las dos está en
  `data/comics_blacklist.yml`.
- Un tercer item nuevo del día, `PICTURES THAT TICK - STORIE BREVI VOLUME 1 - LIMITED
  VARIANT` (Dave McKean, cómic británico), entró y **quedó crudo** — el LLM lo rechazó y
  fue a curación como `llm_non_manga`.
- De los **13 items** que hoy llegaron a `standardize_attempts=3` y escalaron solos a
  curación (`standardize_exhausted`, escape hatch de #191), **8 son de Funside**: STREET
  SHARKS, DAVID MURPHY 911, MORGAN LOST, BUFFY, MANIFEST DESTINY, FIRE POWER ×2, LA
  STRADA.

O sea: la fuente aporta items nuevos reales (1 de los 9 del día) pero es la principal
consumidora de Tier 3 desperdiciado y la que más llena la cola de curación. El escape
hatch de #191 está conteniendo bien el coste (los 8 dejaron de gastar LLM), pero el
ciclo se reabre cada vez que la tienda re-lista un producto (#202).

**Recomendación (NO aplicada — decisión del owner)**: seguir ampliando
`data/comics_blacklist.yml` por FRANQUICIA con los términos que vuelven a aparecer
(`dark souls`, `napalm lullaby`, `pictures that tick`, `street sharks`, `manifest
destiny`, `fire power`, `morgan lost`, `david murphy`). Sigue siendo la herramienta
proporcionada: la medición del 2026-09-02 mostró que la fuente es **96 % manga**, así que
acotar su `purity` o sus searches destruiría más de lo que gana.


## Revisión de ingestión — 2026-09-24

El upsert conserva detected_at y standardize_attempts en filas crudas; la reingesta ya no reinicia el límite de revisión. Respeta la lista de rechazos explícitos aun si cambia el hash.

Evidencia y alcance: [auditoría integral](../audits/2026-09-24-ingestion.md).

### Auditoría full — 2026-09-24

Se recorrieron 15 páginas (643 candidatos previos a filtros). KAGO'S ARCHIVE
VARIANT B estaba enlazada a las filas VARIANT A y C: se elimina esa asociación
incorrecta y se conserva B como producto independiente. Las variantes crudas
no se consolidan solo por serie/edición inferida/volumen.

### Reparación de referencias históricas — 2026-09-24

Se quitó 1 referencia de `funside.it` asociada a otra fila con ISBN
válido diferente del producto cuya URL primaria es esa misma referencia. Se
conservan ambos productos y su URL primaria; no se fusionan por ISBN. Evidencia
por URL/ISBN en `reports/ingestion-audit-2026-09-24/closure/publication-2-manifest.json`.

## Auditoría estratégica — 2026-09-25

La colección contiene cómic occidental además de manga (Dylan Dog, Wayne Family Adventures). Se agregan exclusiones inequívocas al gate común, preservando manga/exclusivas; no se cambia a mixed sin verificar la pérdida de títulos legítimos sin hints. No retirar por intersección: las variantes exclusivas aportan productos únicos.

Publisher vacío desde 2026-09-25: Funside es tienda, no sello editorial. No se
reescriben ciegamente los campos históricos curados; se impide generar nuevos
edition_keys con la tienda como editorial desde esta configuración.

### Caché de imágenes — auditoría 2026-09-25

El inventario detectó referencias locales con nombres derivados de una normalización
legacy que descartaba parámetros de URL. Se desactivó esa reutilización ambigua;
se preservan parámetros de identidad/versión. Esto es un riesgo del caché local,
no prueba de un producto incorrecto en esta fuente. La revisión por URL y el
resultado de las re-descargas están en `reports/image-audit-2026-09-25/`. Ante
contenido cambiado o descarga fallida se conserva la imagen anterior.
