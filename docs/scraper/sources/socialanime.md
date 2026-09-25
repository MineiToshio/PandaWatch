# Fuente: SocialAnime

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Las gotchas se citan por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-23 (4º día consecutivo en 0 por el Managed Challenge, #211).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | SocialAnime |
| **URL base** | `https://socialanime.it` |
| **Índice / punto de entrada** | `https://socialanime.it/store/backend/flow_mangafeed.php` (endpoint JSON del MangaStore) |
| **Tipo de fuente** | Portal de noticias anime/manga con una sección **MangaStore** curada (no es tienda) |
| **`kind`** | `wiki` (fuente sintética, vía `--bootstrap-wiki socialanime`; sin fila en `sources.yml`) |
| **`source_class`** | `trusted_media` (blog/portal curado, no retailer directo) |
| **País** | Italia (`Italia`) — fuente mono-país |
| **Idioma** | Italiano |
| **Cobertura** | Variants, ediciones limitadas, special editions y cofanetti / box sets del mercado italiano |
| **Aporte al corpus** | ~508 items |
| **Parser / módulo** | `scripts/wikis/socialanime.py` |

**Editoriales que abarca** (entre paréntesis, volumen aproximado de items en el corpus):

Edizioni BD (≈149) · Star Comics (≈116) · Panini Comics (≈114) · Dynit / Dynit Manga
(≈45) · 001 Edizioni (≈25) · Goen (≈15) · Magic Press (≈5) · GP Manga (≈4) · Shockdom
(≈3) · Mangasenpai (≈3) · Coconino Press · Dokusho Edizioni, entre otras.

> Nota: hay variantes de string con coma final (`Edizioni BD,`, `Dynit Manga,`,
> `Star Comics,`) que el standardize todavía no normaliza — son la misma editorial.
> El `publisher` sale del campo `editore` del feed (no de la tienda, #44).

**Por qué importa / qué aporta de único**: cubre publishers italianos chicos y medianos
(Star Comics, Panini IT, Edizioni BD, J-Pop, 001 Edizioni, Goen, Magic Press, Dynit,
Coconino…) que las fuentes directas italianas (Panini IT search, Star Comics search) NO
cubren exhaustivamente. Es la principal fuente de **variant cover / limited / special
edition** y **cofanetti / box sets** italianos.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: la sección pública es `/store/manga/variant` (y
  `/store/manga/box`), **JS-renderizada** — los items se cargan vía AJAX al div
  `#results`. NO se parsea HTML: se llama directo al endpoint JSON que usa `store.js`:

  ```
  GET /store/backend/flow_mangafeed.php
      ?type={variant|box}
      &group_no={0,1,2,…}        # paginación, 25 items por página
      &macro_filter=best_of_all   # best_of_all = todo el histórico
  ```

- **Estructura del feed (JSON puro)**: array de objetos con `id`, `nome` (título),
  `link` (URL Amazon afiliado), `img`, `prezzo`, `editore` (publisher), `autore`,
  `trama` (sinopsis), `PublicationDate` (`"DD MMM YYYY"` en inglés), `extra_class`
  (`variant` / `ristampa` / `volume_unico` / …).
  - `type=variant` cubre las **tres** categorías que el sitio anuncia (Variant, Limited,
    Special Edition) — están en la misma colección, distinguibles por el texto del `nome`.
  - `type=box` cubre **cofanetti / box sets**.
  - Los feeds `popolari` y `novita-piu-interessanti` NO se ingieren (son catálogo general:
    en su mayoría tomos regulares, no special editions).
- **Identificador de producto**: la **URL Amazon afiliado**
  (`amazon.it/dp/<ASIN>?tag=socianim0c-21`). Items sin `link` (~10% del feed, entries
  delisteadas) se descartan: sin URL no se pueden dedupar contra el corpus.
- **Anti-bot / quirks**:
  - El endpoint exige headers `Referer` (`/store/manga/<type>`), `X-Requested-With:
    XMLHttpRequest` y `Accept: application/json` — sin ellos puede no responder JSON.
  - **URLs afiliadas Amazon** (#26): `normalize_url_for_dedup` strippea `tag`/`linkCode`/
    `th`/`psc`/`ref=…` para que dos URLs con afiliados distintos del mismo ASIN colapsen.
  - `PublicationDate` usa el placeholder fijo `"1 Jan 2030"` para "fecha desconocida" →
    se descarta (no se setea fecha).
- **Calidad de imágenes**: portadas Amazon (`m.media-amazon.com`), generalmente de buena
  resolución; mejores que las de catálogos comunitarios con thumbnails.

---

## 3. Proceso de ingestión — vista de producto

1. **Bajar el feed `variant`** del MangaStore (todo el histórico con `best_of_all`),
   página por página (25 items por página) hasta recibir una vacía.
2. **Bajar el feed `box`** (cofanetti / box sets) igual.
3. **Por cada entry**: si tiene título y URL Amazon → se convierte en un item. Sin URL se
   descarta (no se puede dedupar).
4. **Clasificar la señal**: el título + la sinopsis traen las palabras italianas que el
   scorer reconoce. Para `type=box`, si el título no menciona `cofanetto`/`box set`, se
   inyecta el keyword en la descripción para que se levante `box_set` (no se inventan
   señales: sólo se garantiza que la palabra aparezca para que `detect_signals` la matchee).
5. **Dedup local** entre `variant` y `box` (un cofanetto con variant cover puede aparecer
   en ambos feeds): se queda con la primera ocurrencia por URL.

**Reglas de producto que nunca se rompen:**
- País = Italia (es el de la editorial/idioma, no el de la tienda Amazon, #46).
- El `publisher` sale de `editore`, no de "Amazon" ni de "SocialAnime" (#44).
- Sólo se ingieren los feeds curados `variant` y `box`; el catálogo general queda fuera.

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

El feed NO particiona por fecha: el rango año/mes que recibe `bootstrap()` se ignora (se
acepta sólo por compat con el dispatcher). El único control temporal es `macro_filter`
(`best_of_all` = histórico completo; `next_from_now` = upcoming; `""` = últimos 8 meses).

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script / flag | `scrape_full.sh` paso **2f** | `scrape_delta.sh` paso **2e** |
| Invocación | `--bootstrap-wiki socialanime --sleep-seconds 0.3 --min-score 20` | idéntica |
| Discovery | `macro_filter=best_of_all` (default del módulo): baja todo el histórico de `variant`+`box` | igual |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Cuándo | refresh completo | novedades recientes |

> FULL y DELTA corren **la misma invocación**. El feed es chico (variant ≈466 items ≈ 19
> páginas, box ≈375 ≈ 15 páginas) y se relanza periódicamente para captar nuevas entries;
> no hay un modo "delta" más acotado.

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/socialanime.py`](../../../scripts/wikis/socialanime.py).
API paralela a `mangavariant.py` / `otaku_calendar.py`:
`parse_feed_item` · `fetch_feed_pages` · `bootstrap` · `iter_year_months`.

### 5.1 Modelo de datos / claves
- **Fuente sintética por `type`**: `_virtual_source_for_type()` crea un `Source` distinto
  para `variant` (`"IT - SocialAnime Variant"`) y `box` (`"IT - SocialAnime Cofanetti"`),
  para que el `name` en `items.jsonl` indique qué colección lo trajo. `country=Italia`,
  `language=Italiano`, `purity=manga_only`.
- **ISBN oportunista**: si el ASIN Amazon parece ISBN-10 (libros italianos legacy con
  prefijo `88…`) se guarda como `isbn` → mejora el `cluster_key` contra retailers europeos
  que sí publican ISBN. ASINs no-libro (`B0…`) no llevan ISBN.
- **`cluster_key`/`edition_key`**: se derivan con la maquinaria estándar del corpus (no
  hay reglas propias tipo ListadoManga). El país (`Italia`) entra en el edition_key (#46).

### 5.2 Qué captura el parser (mapea el §3 al código)
- `fetch_feed_pages(type)` → itera `group_no` hasta página vacía o parcial.
- `parse_feed_item(item, type_label)` → `Candidate`; mapea `nome`/`link`/`img`/
  `editore`/`autore`/`trama` (`prezzo` NO — precios fuera del pipeline);
  arma la descripción con `trama` + hints de `extra_class`
  (`variant`→"Edizione variant cover", `ristampa`, `volume_unico`) + hint de `box`
  (`"Cofanetto / box set."`). Tags: `wiki`, `socialanime`, `italia`, el `type`, y
  `sa-class:<extra_class>`.
- **signal_types observados** en el corpus: `box_set` (≈338), `variant_cover` (≈171),
  `deluxe` (≈36), `collector` (≈12), `bonus`, `oversized`, `retailer_exclusive`,
  `limited`, `special_edition`, `lore_edition`, `artbook`, `premium_format`. Las señales
  las levanta `score_candidate`/`detect_signals` desde title+description.

### 5.3 Flujo end-to-end
- Entra en **FASE 2** (wiki bootstraps) de ambos pipelines: `scrape_full.sh` paso **2f**,
  `scrape_delta.sh` paso **2e**, con `--sleep-seconds 0.3 --min-score 20`.
- Después la atraviesan los cleanup retrofits de FASE 3 (rescore → filtros → clean_titles
  → backfill imágenes → consolidate → dedup_carousel) como cualquier otra fuente.

---

## 7. Validación

- **`scripts/validate_corpus.py`** (gate estructural, aplica a TODO el corpus, sin red).
- Verificar país=`Italia` y `publisher` poblado desde `editore` (no "Amazon"/"SocialAnime").
- Chequeo manual rápido: que los items con `link` Amazon hayan colapsado por ASIN (#26) y
  que no haya duplicados variant/box del mismo producto.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#26 — URLs afiliadas Amazon**: distintos `tag`/`ref=…` del mismo ASIN producían URLs
  distintas → se normalizan en `normalize_url_for_dedup` para que colapsen. ✅
- **Placeholder de fecha `"1 Jan 2030"`**: socialanime lo usa para "fecha desconocida";
  se descarta en `_parse_pub_date` (no se setea release_date). ✅
- **Entries sin `link` (~10%)**: delisteadas, sin URL no se pueden dedupar → se descartan
  en `parse_feed_item`. ✅ (decisión: precisión sobre recall).
- **Campo `prezzo` del feed NO se captura**: precios eliminados del pipeline
  (decisión 2026-06-11, ver architecture.md — catálogo de descubrimiento, no
  tracker de precios). Guard: `test_sa_parse_feed_item_never_captures_price`. ✅
- **`box_set` sin keyword en el título**: para `type=box` se inyecta `"Cofanetto / box
  set."` en la descripción para que `detect_signals` levante la señal. ✅ (no inventa
  señales: sólo garantiza que la palabra aparezca).
- **Decisiones (lo que NO se hace)**: los feeds `popolari` / `novita-piu-interessanti` NO
  se ingieren (mayormente tomos regulares); sólo `variant` + `box`.
- **Curación LLM non-manga 2026-08-23 (gotcha #147)**: 4 items flageados — 2
  conservados (No Game No Life cofanetto limited = light novel; Death Stranding
  Collection Box = novela de Hitori Nojima, J-POP) y 2 expulsados (Wayne Family
  Adventures variant = webtoon de DC; Box Tutto Attica = fumetto italiano de
  Bonelli).

---

## 9. Pendientes / limitaciones conocidas

- **Variantes de `publisher` con coma final** (`Edizioni BD,`, `Dynit Manga,`,
  `Star Comics,`) sobreviven en el corpus — el standardize todavía no las normaliza contra
  la forma sin coma. Cosmético, pero fragmenta el conteo por editorial.
- **Sin ISBN para ASINs no-libro** (`B0…`): esos items dependen del ASIN/URL para dedupar;
  no tienen ISBN para cruzar contra retailers europeos.
- **Sin paginación incremental real**: FULL y DELTA bajan el mismo histórico completo; no
  hay un modo acotado a lo reciente. El feed es chico, así que no es un problema de costo.
- **{{pendiente: confirmar el conteo real por feed (variant vs box) en una corrida fresca;
  los números de páginas en el módulo (variant ≈466, box ≈375) son del comentario del
  código, no medidos en esta revisión.}}**

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (deja raw, sin standardize):
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki socialanime \
    --sleep-seconds 0.3 --min-score 20

# Probar el módulo directo (sin tocar items.jsonl): imprime los primeros candidates
.venv/bin/python scripts/wikis/socialanime.py --types variant,box --macro-filter best_of_all

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "socialanime"
def hit(it):
    blobs=[it.get('url','') or '']+[ (s.get('url','') or '') for s in it.get('sources',[]) ]
    names=[ (s.get('name','') or '') for s in it.get('sources',[]) ]
    return any(NEEDLE in b for b in blobs) or any('SocialAnime' in n for n in names)
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

## 2026-09-18 — el campo `editore` trae una coma final (`"Edizioni BD,"`)

Detectado en el delta diario: 4 items nuevos de SocialAnime Cofanetti llegaron con
`publisher = "Panini Comics,"` / `"Edizioni BD,"`, y de ahí `edition_display` quedó como
`Cofanetto (Panini Comics,)`. Medido en el corpus: **28 items** afectados, todos de
SocialAnime (19 Cofanetti + 9 Variant), desde la primera ingesta (2026-05-23): `Edizioni BD,`
×15, `Dynit Manga,` ×5, `Panini Comics,` ×5, `Star Comics,` ×3.

Causa: `scripts/wikis/socialanime.py` toma `item["editore"]` con `clean_text()`, que no
quita puntuación final; la fuente separa editoriales con comas. El `edition_key` NO se
parte (usa el slug de editorial normalizado, `PUBMIX` = 0), así que la agrupación está
sana; el daño es cosmético (display y faceta de editorial duplicada en la UI).

**Recomendación (NO aplicada — decisión del owner)**: `.rstrip(" ,;")` sobre `editore` en
el parser + retrofit de `publisher`/`edition_display` en los 28 items existentes.

## 2026-09-20 — Cloudflare Managed Challenge: la fuente pasó de ~641 items a 0 (gotcha #211)

Primera corrida en 0 de esta fuente. El log del delta muestra **403 en la primera
página de los dos tipos**:

```
[socialanime] WARN type=variant group_no=0: 403 Client Error: Forbidden for url:
  https://socialanime.it/store/backend/flow_mangafeed.php?type=variant&group_no=0&macro_filter=best_of_all
[socialanime] WARN type=box group_no=0: 403 Client Error: Forbidden ...
[socialanime] terminado: 0 candidates con score>=20
```

**Verificado en vivo el mismo día** (3 sondas): con el UA del scraper, con el UA + un
`Referer` del propio store, y contra la **home** `https://socialanime.it/store/` — las
tres devuelven 403 con `cf-mitigated: challenge`, `server: cloudflare` y el cuerpo
"Just a moment..." de Turnstile. O sea:

- **No es el User-Agent** (el mismo UA funcionó 25 corridas seguidas hasta ayer).
- **No es el endpoint**: la home del sitio está igual de bloqueada, así que no hay
  ruta alternativa sana que sirva de fallback.
- **No es rate-limit**: falla en la primera request de la corrida, `group_no=0`.

Contraste útil con las otras dos fuentes con anti-bot: el `sgcaptcha` de Mangavariant
es **intermitente** (se cayó solo al día siguiente el 2026-09-06) y la Queue-it de
Panini (#208) es **silenciosa** (yield parcial sin error). Acá el fallo es ruidoso y
total, que es el mejor caso: el reporte de salud lo marcó 🔴 con 0% de la mediana en la
misma corrida.

Ojo con el reporte de salud: `wiki:socialanime` sale a la vez en 🔴 YIELD REGRESSIONS
(0 vs mediana 641) y en 🟢 Healthy con `Zero runs 1` — doble contabilidad de la
familia #199.

**Nada aplicado (decisión del owner).** Antes de intentar cualquier cosa, re-medir con
una sonda de una línea; si el challenge se cayó, la fuente vuelve sola:

```bash
curl -sI -A "Mozilla/5.0" "https://socialanime.it/store/" | grep -i "cf-mitigated\|HTTP/"
# 403 + cf-mitigated: challenge  → sigue bloqueada
# 200 sin cf-mitigated           → se destrabó, la próxima corrida la recupera
```

Opciones si persiste, de menor a mayor costo: (a) esperar (precedente Mangavariant);
(b) `--enable-js` NO alcanza por sí solo — Turnstile hay que resolverlo, no sólo
ejecutar JS; (c) inyectar `cf_clearance` obtenida a mano del navegador, que caduca y
ata la ingesta a una sesión manual.

## 2026-09-21 — Challenge persistente, 2º día (gotcha #211)

Delta `logs/scrape-delta-2026-09-21-110220/02e-socialanime.log`: mismo cuadro exacto que
ayer — `403 Client Error: Forbidden` en `group_no=0` de los dos tipos (`variant` y `box`),
0 items raw, 0 candidates. La fuente lleva **2 corridas seguidas en 0** contra una mediana
histórica de 641 items.

Sonda de la propia ficha re-corrida hoy, el challenge NO se cayó:

```
curl -sI "https://socialanime.it/store/"   →  HTTP/2 403  +  cf-mitigated: challenge
curl .../flow_mangafeed.php?type=variant&group_no=0&macro_filter=best_of_all  →  403
```

O sea: a diferencia del `sgcaptcha` de Mangavariant (intermitente, se cayó solo en 24 h),
el Managed Challenge de Cloudflare acá **se sostiene**. Eso descarta la hipótesis
optimista de "esperar un día" y deja las opciones (b)/(c) de arriba como las únicas vías,
las dos con costo real.

El fallo sigue siendo **ruidoso** (WARN 403 + 0 items + 🔴 en el reporte), que es lo
deseable: no corrompe el baseline con yield parcial como hace la Queue-it de Panini (#208).

**Nada aplicado (decisión del owner).**

### Seguimiento 2026-09-23 — 4º día consecutivo en 0

Delta del 2026-09-23: `wiki:socialanime` volvió a rendir **0 items** contra una mediana
histórica de **641** (27 corridas), duración del paso 1 s. Es el **cuarto día seguido**
desde que se activó el Managed Challenge (#211, detectado 2026-09-20).

Lectura acumulada: ya no es un incidente, es el **estado estable** de la fuente. Cuatro
días descartan definitivamente la analogía con el `sgcaptcha` intermitente de
Mangavariant (que se cayó solo en 24 h) y confirman que la única salida son las vías con
costo real ya listadas arriba. Mientras tanto la fuente aporta 0 y **no ensucia el
corpus** — el fallo sigue siendo ruidoso y honesto (403 → WARN → 🔴), así que no hay
urgencia de dato, sí de cobertura: SocialAnime era la vía IT de variantes y cofanetti,
y hoy esa cobertura depende sólo de Funside y AnimeClick.

**Nada aplicado (decisión del owner).**

---

## 2026-09-24 — 5º día consecutivo en 0 (gotcha #211): estado estable, no incidente

Quinta corrida seguida con la fuente en **0 items** contra una mediana histórica de
**641**. Los dos tipos siguen dando 403 en la primera página:

```
[socialanime] WARN type=variant group_no=0: 403 Client Error: Forbidden
              .../flow_mangafeed.php?type=variant&group_no=0&macro_filter=best_of_all
[socialanime] WARN type=box     group_no=0: 403 Client Error: Forbidden
[socialanime] terminado: 0 candidates con score>=20
```

Con 5 días idénticos queda **descartada** cualquier lectura de fallo transitorio: el
Managed Challenge de Cloudflare es la configuración actual del sitio, no un pico. La
comparación con Mangavariant (que se recuperó sola en 1 día) ya se había cerrado el
09-21; hoy sólo lo confirma.

**Lo bueno sigue siendo que este fallo es RUIDOSO**: WARN 403 explícito, 0 items y 🔴 en
el reporte de salud (`wiki:socialanime | 0 | 641 | 0% | 28 runs`). Es el caso contrario a
la Queue-it de Panini (#208), que degrada en silencio. Nada que arreglar del lado del
reporte.

**Nada aplicado (decisión del owner).** Las opciones siguen siendo las de #211: resolver
Turnstile (fuera de alcance y de política), buscar una ruta alternativa del sitio, o
deshabilitar la entrada para dejar de gastar 2 requests por corrida y sacar el 🔴
permanente del reporte. Mientras la fuente quede habilitada, el coste es despreciable y
el día que el sitio afloje la ingesta se reanuda sola.


## Revisión de ingestión — 2026-09-24

HTTP vivo 403 Cloudflare confirmado. Se conservan candidatos adquiridos antes de fallos y se registra WIKI-ISSUE; la rutina devuelve estado parcial y salud deja de marcar healthy. La causa externa no está resuelta.

Evidencia y alcance: [auditoría integral](../audits/2026-09-24-ingestion.md).

### Continuación de auditoría — 2026-09-24

El feed ya reporta esquema inválido y límite de páginas como fallos de cobertura. requests y Chromium continúan recibiendo challenge 403, también con www. No se eliminaron datos ni se deshabilitó la fuente.

### Verificación con navegador normal — 2026-09-24

El navegador integrado logró cargar `/store/manga/variant` y sus 25 primeras
fichas tras la comprobación automática del sitio. El acceso directo al feed en
ese navegador fue rechazado por el cliente; requests y Chromium del scraper
siguen sin una recuperación verificada. Ver la página manualmente no equivale
a resolver el bloqueo de ingestión ni demostrar cobertura del catálogo completo.

### Reparación de referencias históricas — 2026-09-24

Se quitó 1 referencia de `www.amazon.it` asociada a otra fila con ISBN
válido diferente del producto cuya URL primaria es esa misma referencia. Se
conservan ambos productos y su URL primaria; no se fusionan por ISBN. Evidencia
por URL/ISBN en `reports/ingestion-audit-2026-09-24/closure/publication-2-manifest.json`.

### Delta 2026-09-25 — #211 continúa, ahora con rc=1

Sexto día consecutivo en 0 items. El challenge de Cloudflare golpeó **los dos
tipos** en su primera página:

```
[WIKI-ISSUE] socialanime type=variant page=0: challenge=cloudflare: .../flow_mangafeed.php
[WIKI-ISSUE] socialanime type=box     page=0: challenge=cloudflare: .../flow_mangafeed.php
```

Cambio respecto a los días anteriores: el paso ahora sale **rc=1** (antes rendía 0
items sin marcar el paso como fallido). Lo produce el guard de respuesta nuevo
(`wikis/health.install_response_guard`), que convierte una página de WAF servida
con HTTP 200 en un `HTTPError` — así un challenge deja de avanzar el checkpoint y
de contarse como corrida exitosa.

Con seis corridas idénticas, la lectura de #211 se mantiene: **no es un fallo
transitorio, es la configuración actual del sitio**. Sigue sin haber ruta de
fallback (`--enable-js` no alcanza: Turnstile hay que resolverlo, no sólo ejecutar JS).
Nada aplicado.

## Auditoría estratégica — 2026-09-25

Feed automático retirado de full/delta administrados por 403 persistente. AnimeClick, MangaVariant, Panini y tiendas exclusivas siguen activos; no se afirma equivalencia total. Conservamos históricos. Wayne Family Adventures era cómic DC infiltrado: ahora el gate lo excluye aun si el título omite Batman.
