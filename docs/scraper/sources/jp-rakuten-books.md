# Fuente: Rakuten Books (búsqueda dirigida)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-02 (upgrade determinista del downsize + expulsión non-manga; ver gotcha #180).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | JP - Rakuten Books (search) |
| **URL base** | `https://books.rakuten.co.jp` |
| **Índice / punto de entrada** | `https://books.rakuten.co.jp/search?sitem={query}&g=001` (búsqueda dirigida; `g=001` = sección libros) |
| **Tipo de fuente** | Tienda (retailer) — marketplace multi-editorial |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `retailer` |
| **País** | Japón (`Japón`) — el país va al edition_key |
| **Idioma** | Japonés (CJK) |
| **Cobertura** | Ediciones especiales de manga vendidas en Rakuten Books, de muchas editoriales japonesas (no de una sola) |
| **Aporte al corpus** | ~107 items |
| **Parser / módulo** | Entrada `search_template` en `sources.yml` (sin parser propio) |

**Editoriales que abarca** (sacadas del corpus real — Rakuten es marketplace, así que el
`publisher` viene del producto, NO de la tienda; #44): Kodansha (≈14) · Kadokawa (≈11) ·
Shueisha (≈9) · Ichijinsha · Square Enix · Akita Shoten · Mag Garden · Wanibooks ·
Hakusensha · Bushiroad · Shogakukan, entre otras.

> **SIN `publisher` a propósito.** Rakuten Books es un marketplace multi-editorial, no
> una editorial. Citando el comentario del YAML verbatim:
>
> ```yaml
> # SIN publisher: Rakuten Books es un marketplace multi-editorial, no una
> # editorial. El nombre de la tienda NO es el publisher — dejarlo vacío evita
> # contaminar el edition_key y generar dups. Ver gotcha #44.
> ```
>
> Dejar `publisher` vacío evita que la tienda contamine el `edition_key` y genere
> duplicados (#44). El publisher real lo aporta cada producto.

**Por qué importa / qué aporta de único**: captura **ediciones especiales japonesas**
(限定版 / 特装版 / 特典付き / 画集, etc.) del mercado JP, de múltiples editoriales que
otras fuentes mono-editorial no cubren.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: búsqueda por query expandida desde
  `https://books.rakuten.co.jp/search?sitem={query}&g=001`. `{query}` se reemplaza por
  cada keyword japonesa de la lista (ver §5); cada keyword genera una fuente virtual.
- **Estructura del HTML**: lista de resultados con estos selectores (verbatim del YAML):
  - `item_selector`: `div.rbcomp__item-list__item`
  - `title_selector`: `.rbcomp__item-list__item__details__lead a`
- **Idioma japonés (CJK)**: tanto las queries como los títulos vienen en japonés.
- **`purity: mixed`** — la búsqueda trae no-manga (ver §8). Citando el YAML verbatim:
  `# search trae enciclopedias 図鑑, revistas 月号, idol boxes プレミアムBOX.`

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: bloque `"JP - Rakuten Books (search)"`. Es una fuente
  **SIMPLE** del YAML, sin parser propio. Se ingiere en **FASE 1** del pipeline
  (`manga_watch.py` con las fuentes del YAML), igual que el resto de fuentes search.
- **Fuentes virtuales por keyword**: la `search_template` se **expande** en una fuente
  virtual por cada keyword (tag `expansion`). Keywords (verbatim del YAML):
  限定版 · 特装版 · 初回限定 · 数量限定 · 特典付き · グッズ付き · 画集.
- **`purity: mixed` → STRONG manga hint (decisión #3)**: como la fuente es mixta, sólo
  pasan los items con una señal STRONG de manga; así se descartan enciclopedias (図鑑),
  revistas (月号) e idol boxes (プレミアムBOX) que la búsqueda arrastra. La comics
  blacklist aplica siempre.
- **País = Japón** (va al `edition_key`); **`publisher` vacío** (lo aporta el producto, #44).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Veredicto de auditoría de ingestión (2026-07-07): las queries `画集` y `限定版` se
  MANTIENEN**, tras verificar overlap por ISBN contra Sumikko (la otra fuente JP grande
  de ediciones limitadas):
  - **`画集` (artbooks)**: **0% overlap** con Sumikko — Sumikko casi no indexa artbooks
    (11/2751 items de Sumikko). Esta keyword es **100% aporte neto**.
  - **`限定版` (edición limitada)**: **15.2% único** — el resto solapa con Sumikko, pero
    ese 15.2% son ediciones con bundle de DVD/CD que Sumikko no siempre lista. Se
    mantiene por ese aporte neto.
- **Nota de calidad de datos (misma auditoría): ISBN con prefijo basura fullwidth**.
  ~30-40% de los ISBN capturados de fuentes JP (Rakuten Books incluida) traían un
  prefijo `"： "` (colon fullwidth + espacio) delante del ISBN real (ej. `"： 9784799777046"`).
  Causa: el split por label de "ISBN：" no strippeaba el colon fullwidth. Ya se
  **normaliza en la extracción** (`normalize_isbn()` en `manga_watch.py`, aplicado en
  `candidate_to_json` y en los parsers que setean `candidate.isbn`). Para el corpus
  legacy existe el retrofit `scripts/retrofit/normalize_isbn.py` — **109 filas
  pendientes de la corrida real** (verificado con `--dry-run`: "12870 líneas totales,
  109 ISBN cambiarían"); sólo se corrió en dry-run, falta aplicarlo.
- **#44: la tienda no es la editorial** — Rakuten Books es marketplace multi-editorial;
  poner el nombre de la tienda como `publisher` contaminaría el `edition_key` y generaría
  duplicados. ✅ Solución: el bloque NO define `publisher` (queda vacío a propósito); el
  publisher real lo aporta cada producto (corpus real: Kodansha, Kadokawa, Shueisha…).
- **Decisión #3 (purity `mixed` → STRONG manga hint)**: la búsqueda trae no-manga
  (enciclopedias 図鑑, revistas 月号, idol boxes プレミアムBOX). ✅ `purity: mixed`
  exige una señal STRONG de manga para que un item pase.
- **Curación LLM non-manga 2026-08-23**: 8 items flageados, 5 light novels
  conservadas (特装版/グッズ付き) y 3 expulsadas por ser libros generales sin vínculo
  manga/anime: コーヒーが冷めないうちに (novela literaria), しらふ (ensayo de Yuriko
  Yoshitaka) y ゲッターズ飯田の五星三心占い (libro de adivinación).

---

## 9. Pendientes / limitaciones conocidas

- {{pendiente: anti-bot / rate-limiting de Rakuten — no determinado en esta revisión}}.
- {{pendiente: calidad/origen de las imágenes de portada — no determinado}}.
- {{pendiente: diferencia full vs delta para esta fuente — por ahora se scrapea igual en
  ambos modos (la única diferencia full/delta documentada es listadomanga)}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "JP - Rakuten Books (search)"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "rakuten"
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

## 2026-08-25 — `series_key` derivada del prefijo/sufijo de edición (mismo patrón que Sanyodo)

Delta diario (`logs/scrape-delta-2026-08-25-110223/`), detectado al curar la cola de
aliases. Dos casos en esta corrida:

- `cd-division-rap-battle-side-d-h-b` ← *"CD付き ヒプノシスマイク -Division Rap Battle-
  side D．H ＆ B．A．T＋（1）限定版"*. La key arranca con el `CD` del **prefijo** `CD付き`
  y pierde el nombre de la obra (Hypnosis Mic). Mapeado a mano a
  `hypnosismic-division-rap-battle-side-dh-bat`.
- `au-artbook` ← *"AU画集"*. Quedó sin destino verificable y se salteó.

Es la misma falla documentada con más volumen en
[`jp-sanyodo.md`](jp-sanyodo.md) — el derivador toma el fragmento latino del
prefijo/sufijo de edición en vez del segmento CJK con el nombre de la serie. En Rakuten
aparece sobre todo con el prefijo `CD付き`/`特典付き`, mientras que en Sanyodo domina el
sufijo `…付き特装版`. La recomendación de fix (cortar los sufijos/prefijos de edición
antes de derivar la serie) está desarrollada en la ficha de Sanyodo y aplica igual acá,
ya que ambas comparten el derivador.

Aparte, sin relación con lo anterior: el ítem *"【楽天ブックス限定カバー：サイン付き（数量
限定）】ゲッターズ飯田の五星三心占い2021完全版"* entró como manga y es un **libro de
horóscopos** (五星三心占い) con cubierta firmada — material fuera de alcance que el gate
no frenó porque el título carga `数量限定`/`限定カバー`, señales fuertes de edición
limitada. Un solo caso en esta corrida; se anota por si el patrón se repite (libros de
no-ficción con cubierta limitada de Rakuten).

## 2026-08-28 — las búsquedas `初回限定` / `数量限定` traen libros generales, no manga

Delta diario (`logs/scrape-delta-2026-08-28-160959/`). Tres items marcados
`is_manga=false` por el LLM del skill de estandarización, pendientes en
`data/unmapped_series.jsonl` (reason `llm_non_manga`):

- `吉高由里子 『 しらふ 』【初回限定版】(…イラスト＆メッセージプリント入り栞)` — `[search: 初回限定]`
  (libro/ensayo de una actriz, edición de 1ª tirada con marcapáginas)
- `ゲッターズ飯田の五星三心占い2026完全版(限定カバー：サイン入り（数量限定）)` — `[search: 数量限定]`
- `【楽天ブックス限定カバー：サイン付き（数量限定）】ゲッターズ飯田の五星三心占い2021完全版` — `[search: 数量限定]`
  (ambos: almanaques de adivinación, portada limitada firmada, exclusiva Rakuten)

Causa: `初回限定` ("edición de primera tirada") y `数量限定` ("cantidad limitada") son
términos de **marketing editorial japonés genéricos**, no específicos de manga. Rakuten
Books es librería generalista, así que las queries traen cualquier libro con tirada
especial. El patrón de edición es exactamente el que el proyecto busca; lo que falla es
el medio de la obra.

Nota: las 2 entradas de 五星三心占い son el **mismo almanaque en años distintos**
(2021 y 2026), o sea que el ruido de esta query es recurrente año a año.

**Para el owner (no aplicado):** sumar los patrones de serie (`五星三心占い`, y en general
autores/obras no-manga que reincidan) a `data/comics_blacklist.yml`, o acotar las queries
con un término de medio (`コミック`, `漫画`). Retorno: corta la re-ingesta diaria y baja el
gasto de LLM, que hoy re-evalúa estos mismos títulos en cada corrida (gotcha #154).

## 2026-08-29 — vuelve a flaggearse, y esta vez el flag se PERDIÓ (gotcha #155)

Delta diario (`logs/scrape-delta-2026-08-29-110244/`). Los 3 items ya documentados en la entrada del 2026-08-28 volvieron a entrar como `product_type=manga` y a ser flageados por el LLM: `吉高由里子 『しらふ』【初回限定版】` (ensayo de una actriz, search `初回限定`) y las dos ediciones de `ゲッターズ飯田の五星三心占い` (libro de adivinación, search `数量限定`).

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

## 2026-08-30 — el search `数量限定` trae libros que no son manga (2 items)

Delta diario (`logs/scrape-delta-2026-08-30-111729/`). El search `[search: 数量限定]`
(“cantidad limitada”) inyectó **2 libros de adivinación** de la serie
ゲッターズ飯田の五星三心占い (Getters Iida, horóscopo/五星三心占い), ediciones 2021 y 2026
con cubierta limitada firmada:

- `ゲッターズ飯田の五星三心占い2026完全版(限定カバー：サイン入り（数量限定）)` — 2025-11-03
- `【楽天ブックス限定カバー：サイン付き（数量限定）】ゲッターズ飯田の五星三心占い2021完全版` — 2020-11-11

Ambos flageados `llm_non_manga` por `/watch-standardize-catalog` y **no expulsados** por
los gates deterministas (gotcha #154). Peor: el modelo de rareza les asignó **`rare`**,
así que aparecen destacados en la UI como si fueran hallazgos valiosos. Quedaron sin
`series_display`, sin `edition_display` y sin `publisher`.

Causa: `数量限定` es vocabulario de **tirada limitada** genérico del retail japonés, no
específico de manga — matchea cualquier libro con edición limitada firmada. La fuente no
declara `purity`, así que el default `manga_only` no exige STRONG manga hint.

Contraste útil dentro de la misma fuente: el search `[search: 特装版]` de la misma corrida
trajo un hallazgo **correcto** — `逆転バリバリバース 1 金のバリバコイン2枚つき特装版`
(Shogakukan, ColoCoro Comics, con 2 monedas doradas, 2026-07-28). O sea que el problema
no es la fuente sino el término: `特装版` implica manga, `数量限定` no.

**Para el owner (no aplicado — cambio de configuración):** el fix más directo es
restringir el search `数量限定` (o quitarlo y quedarse con `特装版`/`初回限定`, que son
específicos de manga). Retorno: elimina una vía de entrada recurrente de libros generales
japoneses que además contaminan el ranking de rareza.

## 2026-08-31 — recurrencia nº5: el mismo libro de horóscopos entra por 2º día seguido

Delta diario (`logs/scrape-delta-2026-08-31-110202/`). Dos filas nuevas `llm_non_manga`
con `note: pure_novel`, ambas de searches de FORMATO de edición:

- `僕が1人のファンになる時（2）初回限定版B` — search `初回限定`
- `ゲッターズ飯田の五星三心占い2026完全版(限定カバー：サイン入り（数量限定）)` — search `数量限定`

El segundo es **el mismo item que ya se había flageado el 08-30** (libro de horóscopos
de Getters Iida, no manga): entró de nuevo porque el veredicto del LLM no expulsa y los
gates deterministas tampoco lo agarran. Es el bucle de la gotcha #154 aplicado a esta
fuente. La cola ya acumula 3 filas de la misma familia (`五星三心占い` 2021 y 2026).

Ambos items siguen VIVOS en el corpus, contados como `product_type: manga` y con
`rarity: rare`, así que aparecen en el dashboard como hallazgos legítimos.

Nada aplicado: acotar los searches de formato (`初回限定`/`数量限定`) o agregar los
términos a la blacklist es decisión del owner.

## 2026-09-02 — cierre: `ゲッターズ飯田` y `博物画集` a `_NON_MANGA_HARD` (gotcha #176)

Cierra el bucle documentado arriba. La Etapa 1 de triage de imágenes (visión sobre
portadas, no sobre texto) detectó de paso 3 non-manga de esta fuente que el filtro de
texto nunca había atrapado: las 2 filas de `五星三心占い` (2021 y 2026, ya documentadas
arriba) y un tercero nuevo, `ゲランのフランス博物画集` (`[search: 画集]`, artbook de
láminas de historia natural francesa, no relacionado a manga). Verificados los 3 contra
`items.jsonl` (título/descripción/publisher) antes de tocar nada — el 五星三心占い incluso
trae `占い本特集` ("especial de libros de adivinación") literal en su propia descripción de
Rakuten.

Se agregaron 2 patrones a `_NON_MANGA_HARD` en `manga_watch.py` (no a
`data/comics_blacklist.yml`, que es específico de franquicias de cómic occidental):
`ゲッターズ飯田` (nombre del adivino, nunca aparece en manga) y `博物画集` (género de
artbook de historia natural, distinto de `画集` a secas que sí es formato habitual de
artbook de manga/mangaka — verificado que no colisiona con los 90 items `画集` del
corpus). `filter_non_manga.py --dry-run` confirmó exactamente estos 3 items expulsados
de esta fuente (7 en total contando las otras 2 fuentes del mismo hallazgo, JP - Sumikko
y ListadoManga — ver gotcha #176). El search `数量限定` sigue sin acotar: la restricción
de searches queda como pendiente del owner, sin cambios en esta pasada — el blacklist de
título es el mecanismo que efectivamente cortó el bucle esta vez.

## 2026-09-01 — denylist del placeholder "sin portada" de Rakuten (título superpuesto)

Ola 3 de depuración de imágenes (ver `docs/reference/images.md` § "OLA 3"). Dos
items de esta fuente (`oshiete-kudasai-fujishima-san-unknown-limited-jp-3`,
`oshiete-fujine-san-bright-limited-jp-3`, ambas ediciones de 教えてください、藤縞さ
ん！) tenían como ÚNICA foto una plantilla genérica de `thumbnail.image.rakuten.
co.jp` que Rakuten sirve cuando no tiene la carátula real: fondo gris claro con el
propio título del libro renderizado como texto plano (no es un scan de portada) —
confirmado visualmente (conversión AVIF→PNG + lectura). **No es un problema de
selectores**: el parser capturó bien la imagen que el sitio sirve; el sitio mismo
no tiene la carátula para este ISBN y genera esta card de "sin portada" en su
lugar. Ambas filas eran byte-idénticas (mismo sha1 del espejo AVIF pese a URLs
distintas — el "título superpuesto" no cambia el hash porque Rakuten sirve el
MISMO archivo genérico para ambas ediciones de este libro, no una plantilla
renderizada por-título). Agregado a `data/placeholder_signatures.json`
(sha1 `b10109774a879c1d8f484177fea3bafd6ffa46bf`, dims 1004×1172). Purgado con
`purge_placeholder_images.py --only-reasons signature` (gotcha #161): las 2 filas
quedaron sin ninguna foto (pasan al bucket de búsqueda web / 📚 en la UI). **No
se generalizó a un fragmento de URL** (`KNOWN_PLACEHOLDER_URL_FRAGMENTS`): el path
`thumbnail.image.rakuten.co.jp/@0_mall/book/cabinet/...` es el MISMO que usan las
portadas reales de esta fuente, así que un fragmento habría sido demasiado amplio
y purgado covers legítimos — la denylist queda acotada a la firma sha1 exacta.

## 2026-09-02 — la "tarjeta de título" SÍ tiene patrón de URL: la extensión `.gif`

Corrige el párrafo anterior. Es cierto que el **path** (`/book/cabinet/<n>/<ISBN>`) es el
mismo para portadas reales y para placeholders, pero la **extensión no**: Rakuten Books
sirve la tarjeta de título generada (título + autor en rojo + banda オリジナル特典付き sobre
fondo blanco) como **`.gif`**, y las portadas reales como **`.jpg`**. Medido sobre todo el
corpus en la Etapa 1 de triage de imágenes (`docs/reference/images.md` § "Etapa 1 —
resultados"):

- **50 portadas `.gif`** en `tshop.r10s.jp` / `thumbnail.image.rakuten.co.jp` /
  `shop.r10s.jp` → **49 son tarjeta de título** y 1 es un mockup con marca de agua `SAMPLE`
  (`the-heroic-legend-of-arslan-kobunsha-boxset-jp-1-16`). **50/50 no son portada usable.**
- **295 portadas `.jpg`** de los mismos hosts → **0 placeholders** en el subconjunto juzgado
  a ojo (52 ítems).

La denylist por `sha1` no escala en esta fuente: el título va **quemado en el pixel**, así
que cada archivo tiene hash distinto (49 placeholders = 49 hashes; sólo repite el par
`bang-dream-mygo-*-jp-4`, que es el mismo libro cargado dos veces). Ver gotcha #171.
Cuidado al implementar: el sufijo de transformación va después de la extensión
(`?downsize=130:*`, `?fitin=560:400&composite-to=*`) — hay que mirar `url.split('?')[0]`.

**Aplicado (2026-09-02, cierre de la Etapa 1, gotcha #176)**: la regla se implementó en
`image_store.known_placeholder_url_reason()` — host de la familia Rakuten Y
`urlparse(url).path` (sin query) termina en `.gif`. Antes de purgar se cruzaron los 50
`.gif` de `images[0]` contra `etapa1-triage.json`: **50/50 confirmados NO-portada** (49
`placeholder` + 1 `imagen_equivocada`), 0 falsos positivos. `purge_placeholder_images.py
--only-reasons known,signature` quitó **53 entries `known:rakuten:title-card-gif`**
(más que 49 porque la regla corre en CUALQUIER posición del array `images[]`, no sólo
portada — atrapó 4 tarjetas coladas como foto de "galería" además de las 49 portadas; 3
más quedaron protegidas porque el propio item las lista como `kind: extra` de su propia
colección, ver gotcha #176). Test unitario en `tests/test_purge_placeholder_images.py`
(`test_rakuten_gif_is_known_placeholder` + `test_purge_rakuten_gif_placeholder_cover`):
positivo `.gif` con/sin sufijo de transformación en los 3 hosts, negativo `.jpg` del
mismo host, negativo `.gif` de otro host. La tabla de decisión original (49 slugs,
`sha1`/`sha256`) sigue en `data/diagnostics/etapa1-triage.json` →
`_meta.denylist_candidata_por_host` como referencia histórica.

Efecto colateral del `?downsize=130:*`: las portadas reales de esta fuente entran al espejo
a **130 px de ancho**, que en una card de 300 px es un reescalado de 2.3×. Son 20 de los 33
`se_ve_mal` del lote A — la fuente es la principal aportante de portadas blandas del corpus.

## 2026-09-02 — upgrade determinista del `?downsize=` (gotcha #180) + expulsión de un non-manga

**Upgrade de resolución.** El efecto colateral de arriba (portadas blandas por
`?downsize=130:*`) tiene fix determinista: la familia `tshop.r10s.jp`/`shop.r10s.jp`
sirve la imagen NATIVA con sólo quitar la query entera (no hace falta pedir un
`downsize=N` grande — verificado en vivo: `downsize=130:*` → 130×184, sin query →
844×1200, misma imagen, mismo mecanismo que el host `thumbnail.image.rakuten.co.jp`
que ya tenía este fix con `?_ex=`). Agregado como patrón #11 de
`scripts/retrofit/upgrade_image_resolution.py::derive_original_url()`, con guard
anti-`.gif` (nunca "mejora" la tarjeta de título placeholder de gotcha #171/#176).
Corrida real acotada (`--host r10s.jp`): **176 candidatas → 145 mejoradas** (ganancia
mediana ×5.34, hasta ×85), **22 sin mejora** — todas por espejo local ya mejor que la
nativa de Rakuten (upgrade previo vía `watch-search-covers`), no por límite del CDN.
Detalle técnico completo en gotcha #180.

**Non-manga expulsado.** El item `吉高由里子『しらふ』【初回限定版】` (slug
`item-75cd876218b5`, `[search: 初回限定]`) — fotolibro/ensayo de la actriz Yuriko
Yoshitaka, documentado como recurrente desde 2026-08-28 (ver entradas arriba) — se
agregó a `_NON_MANGA_HARD` en `manga_watch.py` (patrón `吉高由里子`, único item con ese
nombre en el corpus, sin riesgo de colisión) y se expulsó con `filter_non_manga.py`
(`--dry-run` confirmó exactamente 1 descarte antes de aplicar). Corpus 14346→14345.
El item tenía una candidata `approved` pendiente en `data/cover_preview.json` (portada
mejorada por `watch-search-covers`) que quedó huérfana — `sync_cover_preview.py
--dry-run` la detecta como "slug no existe" (1 entry a podar en la próxima corrida real
de ese script; no se tocó en esta tarea).

## 2026-09-05 — el search `限定版` trae fotolibros de ídolos (写真集)

El término de búsqueda `限定版` ("edición limitada") devolvió, entre otros, este item que
quedó crudo y flageado non-manga por el LLM:

- `books.rakuten.co.jp/rb/18800122/` — **特別限定版 中務裕太ファースト写真集『 1000% 』**
  (salida 2026-10-21)

Es el **primer fotolibro (写真集) de un ídolo**, no un producto de manga. Entra porque
`限定版` es un término de FORMATO de edición, no de medio: cualquier libro japonés con
tirada limitada lo lleva. Es exactamente la deuda estructural anotada el 2026-09-02 en
CLAUDE.md — *"los STRONG manga hints incluyen términos de FORMATO que no distinguen el
medio"* — vista ahora desde el lado de los términos de búsqueda.

En la misma corrida el mismo search sí trajo material legítimo
(`キスで溶かしたそのあとに 限定版`, gateau コミックス), así que **el término no está roto**:
su precisión simplemente no es 1.0. No corresponde acotar el search — el precedente de las
gotchas #187-#190 (Funside/Star Comics) es explícito: recortar un search de alto volumen
para expulsar unos pocos falsos positivos destruye mucho más manga del que salva.

Como el item quedó pendiente y no estandarizado, **no llegó a publicarse en la UI**. Pero
sí cae en el bucle de la gotcha #191: mientras no se arregle el contador de intentos, va a
volver a gastar Tier 3 en cada corrida.

**Nada aplicado.** Recomendación: si el ruido de 写真集 se vuelve recurrente, la
herramienta proporcionada es una señal non-manga por token de título (`写真集` acompañado
de `ファースト`/nombre propio), **no** tocar el término de búsqueda.

## 2026-09-06 — el `l-id` de la URL es POSICIONAL: pisa `detected_at` y finge novedades (gotcha #192)

Al reconstruir el ciclo del fotolibro del 2026-09-05 apareció un mecanismo que no estaba
documentado y que **no es específico de ese item**.

El item de ayer y el de hoy son el MISMO producto:

| Corrida | URL guardada | `detected_at` |
|---|---|---|
| 2026-09-05 | `books.rakuten.co.jp/rb/18800122/?l-id=search-c-item-img-**20**` | `2026-09-05T20:13:23` |
| 2026-09-06 | `books.rakuten.co.jp/rb/18800122/?l-id=search-c-item-img-**23**` | `2026-09-06T23:47:45` |

El sufijo `NN` de `l-id=search-c-item-img-NN` es **el puesto que ocupó el producto en la
página de resultados esa corrida**, no un identificador del producto. Cuando el ranking se
mueve, la misma ficha vuelve con una URL literalmente distinta.

**Qué NO se rompe**: el dedup por `cluster_key` funciona — el corpus tiene UNA sola fila
para el producto, no una por posición. La URL vieja tampoco queda huérfana.

**Qué SÍ se rompe**: el merge refresca `detected_at` con la fecha de hoy, así que un item
que lleva días en el corpus aparece como novedad. Medido en esta corrida: de 10 items con
`detected_at` de hoy, **3 ya estaban** en el backup `pre-scrape-delta` (Rakuten fotolibro,
Io Sakisaka Variant Bundle de Panini/AnimeClick, Mujirushi Lux de Manga México) — las
novedades reales eran 7. Contar por `detected_at` sobre-cuenta ~30% en un delta chico.

La forma correcta de contar novedades es comparar la URL **normalizada** (sin query ni
fragmento) contra el backup `pre-scrape-delta` del propio run:

```bash
.venv/bin/python - << 'PY'
import json, re
RS = '2026-09-06T23:10:34'   # marca de inicio del run
BAK = 'data/backups/items.jsonl/items.jsonl.20260906-181051.pre-scrape-delta-bak'
norm = lambda u: re.sub(r'[?#].*$', '', u or '').rstrip('/')
before = set()
for l in open(BAK):
    if not l.strip(): continue
    it = json.loads(l)
    before |= {norm(s.get('url')) for s in (it.get('sources') or []) if s.get('url')}
    if it.get('url'): before.add(norm(it['url']))
for l in open('data/items.jsonl'):
    if not l.strip(): continue
    it = json.loads(l)
    if (it.get('detected_at') or '')[:19] < RS: continue
    us = [norm(s.get('url')) for s in (it.get('sources') or []) if s.get('url')]
    print('YA ESTABA' if any(u in before for u in us) else 'NUEVO', '|', (it.get('title') or '')[:50])
PY
```

**Nada aplicado.** Dos opciones, ninguna urgente (el corpus está sano; lo que engaña es el
conteo):

1. **Normalizar la URL al ingresar** — quitar `l-id` (y equivalentes de tracking) antes de
   guardarla en `sources[].url`. Es el fix de mecanismo, pero toca la identidad de URL de
   toda la fuente: cambia `content_hash`/URLs guardadas de ~180 items de Rakuten y hay que
   medir el impacto en `URLDUP` antes de tocarlo. **Decisión del owner.**
2. **No confiar en `detected_at` para contar novedades** — es lo que hace ya el snippet de
   arriba; barato y sin riesgo.

### Segunda ocurrencia del fotolibro de ídolo (写真集)

`特別限定版 中務裕太ファースト写真集『 1000% 』` volvió a mandarse a un subagente Tier 3
hoy, como se predijo el 2026-09-05. Confirma la gotcha #191 desde esta fuente: el item
sigue con `standardize_attempts` sin incrementar, así que el escape hatch
`standardize_exhausted` nunca se dispara. Es el **día 2** de este item en el bucle; los 2
items de KADOKAWA Store llevan **4**. La recomendación del 2026-09-05 (señal non-manga por
token `写真集`, NO tocar el término de búsqueda) sigue en pie sin cambios.

## 2026-09-07 — 2ª confirmación del `l-id` posicional: 7 de 21 "novedades" eran falsas

Segundo día consecutivo midiendo el efecto de la gotcha #192, ahora con la muestra entera
atribuible a esta fuente:

| Métrica del delta 2026-09-07 | Valor |
|---|---|
| Items con `detected_at >= RUN_START` | **21** |
| De esos, con TODAS sus URLs ya presentes en el corpus previo | **7** (100 % `books.rakuten.co.jp`) |
| **Novedades reales** | **14** |

Ayer fueron 3 de 10 (30 %); hoy, 7 de 21 (33 %) — la proporción se sostiene y el origen es
**exclusivamente Rakuten**. Los 7 son ediciones especiales japonesas que ya estaban en el
catálogo (`君と夏のなか(2)` y `(3)` 限定版, `ブラック・ラグーン 11` 限定版,
`花燭の白 12巻` 特装版, `アルスラーン戦記(25)` 特装版, `ちいかわ(7)` 特装版,
`ともしびワークデイズ 1` 特装版) y volvieron con un `?l-id=search-c-item-img-NN` distinto
por haber cambiado de puesto en los resultados de búsqueda.

El corpus está bien: una sola fila por producto, el dedup por `cluster_key` funciona. Lo
que falla es leer `detected_at` como "esto es nuevo".

**Método correcto, ya en uso por la rutina diaria** (comparar la URL normalizada contra el
corpus previo, tomando el snapshot ANTES de lanzar el scrape):

```python
from urllib.parse import urlsplit, parse_qsl, urlunsplit, urlencode
DROP = ('l-id', 'utm_', 'ref', '_', 'gclid', 'fbclid', 'scid', 'sc_')

def norm(u):
    p = urlsplit(u)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not any(k.startswith(d) or k == d for d in DROP)]
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip('/'), urlencode(sorted(q)), ''))

# novedad real  ⇔  todas las URLs normalizadas del item son nuevas
```

**Atención a la zona horaria** (aprendido hoy): filtrar por el PREFIJO de fecha
(`detected_at.startswith('2026-09-07')`) mete items que no son del run — el scrape corre
11:01 hora local = 16:01 UTC, así que todo lo detectado entre las 00:00 UTC y esa hora
comparte fecha sin pertenecer a la corrida (hoy: 2 fichas de AnimeClick con
`detected_at = 2026-09-07T00:00:41Z`). Hay que comparar contra el **timestamp UTC completo**
del inicio del run, no contra la fecha.

**Recomendación (NO aplicada — decisión del owner)**: normalizar la URL al guardarla en
`sources[]`, quitando los parámetros de tracking. Elimina la causa en vez de compensarla en
cada consumidor, y de paso reduce las 160 violaciones `URLDUP` (warn) que el validador
reporta. Cambiar cómo se persisten las URLs toca el corpus entero: es del owner.

## 2026-09-11 — los dos "pendientes que iban a escalar solos" nunca escalan (gotcha #202)

El 09-07 se anotó que el fotolibro `特別限定版 中務裕太ファースト写真集『1000%』` y
`コーヒーが冷めないうちに(特装版/特製しおり1種)` "ahora acumulan intentos y escalarán solos a
curación". **No pasa.** Rastreo en los backups `pre-scrape-delta`: el café llegó a
`standardize_attempts = 2` y el scrape del 09-09 lo devolvió a `None`; el fotolibro nunca
pasó de 1. Hoy los dos siguen crudos con 1 intento y volvieron a gastar Tier 3.

Causa (gotcha #202): el upsert del scraper sólo preserva campos curados en filas que ya
tienen `standardized_at`; una fila cruda que la búsqueda vuelve a listar se reemplaza entera
y pierde el contador. Esta fuente es el peor caso: sus búsquedas re-listan los mismos
productos a diario y además cambian la URL por el `l-id` posicional (#192), así que ambos
items figuran también como "detectados hoy" sin serlo. Mientras no se preserve el contador,
todo falso negativo del LLM que venga de Rakuten queda en bucle indefinido.

## 2026-09-16 — el `l-id` posicional también CAMBIA LA IDENTIDAD de un item crudo

Ampliación medida de la gotcha #192 (hasta ahora documentada como "pisa
`detected_at`"). En el delta del 2026-09-16, el item

```
コーヒーが冷めないうちに(特装版/特製しおり1種)
```

pasó de `https://books.rakuten.co.jp/rb/18761453/?l-id=search-c-item-img-11`
(puesto 11 en el run anterior) a `…?l-id=search-c-item-img-06` (puesto 6 hoy)
**sin cambiar de producto**, y con eso **cambió de slug**:

```
PRE  item-695cdcb6a9b4   (el slug viejo YA NO EXISTE en items.jsonl)
POST item-3da162c72e9e
```

**Por qué le pasa sólo a los crudos:** un item estandarizado tiene `cluster_key` y su
slug se deriva de serie/edición, así que la URL rotatoria no lo mueve. Un item **sin
`standardized_at`** no tiene esa ancla: su slug se deriva de la URL, y la URL cambia en
cada corrida. Medido sobre las 211 URLs de Rakuten presentes antes y después del run,
**4 cambiaron de slug: 3 por estandarización legítima y 1 por esto**.

Consecuencias prácticas:

1. Contar "novedades del día" por **slug nuevo** también sobre-cuenta, no sólo por
   `detected_at` (hoy: 1 de 7 supuestos items nuevos era este). La forma correcta sigue
   siendo comparar la **URL normalizada** (sin query) contra el backup
   `pre-scrape-delta` del propio run.
2. Cualquier referencia externa al slug de un item crudo (una aprobación del dashboard,
   un enlace guardado) se rompe en la corrida siguiente.
3. Es la otra cara de gotcha #202: la fila se reescribe entera, así que además pierde
   `standardize_attempts` y nunca alcanza el escape a curación.

**Recomendación (decisión del owner, nada aplicado):** normalizar la URL de Rakuten
—quitar el parámetro `l-id` antes de derivar slug/identidad— resolvería los tres
síntomas de una sola vez y es un cambio acotado a esta fuente.

## 2026-09-17 — El culpable NO era el `l-id`: el índice de upsert ignora `sources[]` (gotcha #209)

Corrida `logs/scrape-delta-2026-09-17-110139`. De los 45 items crudos pendientes, **10
eran de Rakuten y 9 ya existían en el corpus** como filas estandarizadas que llevaban el
MISMO `rb/<id>` en su `sources[]`:

| Fila cruda nueva | `rb/<id>` | Fila estandarizada que ya existía |
|---|---|---|
| `item-f59619f43575` | 18791905 | `detective-conan-shogakukan-special-jp-109` |
| `item-9f9c2b11354d` | 18035391 | `chiikawa-kodansha-special-jp-7` |
| `item-8c8d8ebde97a` | 16733166 | `tensura-kodansha-limited-jp-18` |
| `item-0e96557a7933` | 15668414 | `black-lagoon-shogakukan-limited-jp-11` |
| `item-084c12a0721d` | 18238578 | `kimi-to-natsu-no-naka-ichijinsha-limited-jp-3` |
| `item-81e728e40d42` | 17158652 | `kimi-to-natsu-no-naka-ichijinsha-limited-jp-2` |
| `item-e3371c1991c0` | 18601636 | `hajimemashite-ore-no-shinyuu-ichijinsha-limited-jp-2` |
| `item-6bb106312596` | 18695103 | `welcome-to-demon-school-iruma-kun-akita-special-jp-50` |
| `item-677a1b14cbdd` | 18816089 | `haimiya-senpai-wa-kowakute-kawaii-squareenix-special-jp-4` |

### Qué se creía (y era falso)

Las notas del 09-06 y del 09-16 atribuían esto al `?l-id=search-c-item-img-NN` posicional.
**Refutado midiéndolo:** `l-id` está en `TRACKING_PARAMS` desde 2026-05-22 y
`normalize_url_for_dedup` lo strippea bien. Las tres URLs de prueba, con el puesto cambiado
entre corridas, normalizan todas al mismo producto:

```
rb/18791905  puesto 01 (corpus) → 08 (hoy)   →  books.rakuten.co.jp/rb/18791905
rb/18035391  puesto 03 (corpus) → 09 (hoy)   →  books.rakuten.co.jp/rb/18035391
rb/16733166  puesto 18 (corpus) → 24 (hoy)   →  books.rakuten.co.jp/rb/16733166
```

El `l-id` es sólo la razón por la que el producto vuelve a aparecer en el listado. No es la
causa del duplicado.

### La causa real

Las 9 filas estandarizadas **no nacieron de Rakuten**: su `url` top-level apunta a Sumikko
(`comic.sumikko.info/item-select/…`) o Sanyodo, y la de Rakuten vive sólo en `sources[]`.
El índice del upsert (`manga_watch.py` ~5917) sólo mapea la URL top-level:

```
URLs top-level indexadas:                          14 539
URLs en sources[] que el upsert NO indexa:          1 545
rb/18791905 → en_url_toplevel=False  en_sources=True
```

Por eso el lookup falla y nace una fila nueva. **Afecta a cualquier producto multi-fuente,
no sólo a Rakuten**: son 1545 duplicados latentes en todo el corpus.

### Por qué importa (y por qué no se ve en el conteo)

El duplicado nace **crudo**, sin `cluster_key`, así que se va a **Tier 3 del LLM** —la ruta
más cara— y recién después se fusiona con la fila buena por `edition_key`. No corrompe el
corpus de forma permanente: **desperdicia LLM**. En este run, 9 de las ~37 llamadas Tier 3
fueron para re-derivar metadata que el corpus ya tenía.

Es invisible en el conteo de items: el delta neto del día fue **+24 líneas**, pero las URLs
realmente nuevas fueron **13**.

**Recomendación (no aplicada, decisión del owner):** ver el fix de mecanismo y su trampa de
implementación en gotcha #209.

### Confirmación end-to-end en la misma corrida

Tras la estandarización, las filas crudas duplicadas **desaparecieron fusionadas** en su
fila estandarizada, y el corpus bajó de 14 563 a 14 552 (−11):

```
item-f59619f43575                          → FUSIONADO
detective-conan-shogakukan-special-jp-109  → EXISTE (absorbió al duplicado)
item-9f9c2b11354d                          → FUSIONADO
chiikawa-kodansha-special-jp-7             → EXISTE (absorbió al duplicado)
```

Esto cierra el ciclo descrito arriba y confirma que **el daño es de costo, no de
integridad**: el duplicado vive exactamente lo que tarda en consumir su llamada Tier 3, y
después se disuelve. Sin el fix, el gasto se repite cada vez que Rakuten (o cualquier
fuente secundaria) re-lista uno de los 1545 productos afectados.

## 2026-09-21 — Prefijo `【バーゲン本】` sin limpiar + slug fosilizado (gotcha #213)

Dos items nuevos de la corrida delta destaparon un quirk y confirmaron un mecanismo:

**1) `【バーゲン本】` es un marcador de la TIENDA, no del producto.** El item
`【バーゲン本】特装版 マンガ戦国自衛隊ーNFTデジタル特典付き` llega con ese prefijo pegado
al título. `バーゲン本` = "libro de saldo/remate": es una etiqueta comercial de Rakuten
sobre el estado del stock, no parte del nombre oficial con que la editorial publicó el
producto. Por la política de títulos (el `title` es el nombre OFICIAL), el prefijo debería
caer en `clean_titles.py` como ya caen otros corchetes promocionales. Hoy NO está en la
lista. Detectable de forma determinista: `【バーゲン本】` siempre al inicio, entre corchetes
CJK, con lectura fija.

**2) El slug quedó fosilizado en un fragmento espurio.** Los 2 items JP nuevos del día
(este y `『男一匹ガキ大将 全8巻』 特典付きBOXセット…`) terminaron con slugs
`nft-unknown-special-jp` y `box-001-008-unknown-boxset-jp-8` mientras sus `edition_key`
post-estandarización son los correctos (`sengoku-jieitai-unknown-special-jp`,
`otoko-ippiki-gaki-daishou-unknown-boxset-jp`). La derivación cruda tomó
`NFTデジタル特典付き` → `nft` y `BOXセット … 001〜008` → `box-001-008` como si fueran la
serie. Mecanismo completo, medición sobre el corpus y fix propuesto en la gotcha **#213**.

Ambos items son manga real y de interés (un 特装版 con bonus y un BOX SET de 8 tomos con
特典, este último con salida 2026-11-19 — preorden accionable), así que el defecto es
cosmético/de identidad, no de filtrado.

**Nada aplicado (decisión del owner).**

---

## 2026-09-24 — Instancia fresca de #210: el MISMO artbook partido en dos ediciones por la editorial vacía

Caso del día, verificable en el corpus con una línea:

```
the-art-of-pragmata-lunar-echoes-kadokawa-artbook-jp  ← store.kadokawa.co.jp
the-art-of-pragmata-lunar-echoes-unknown-artbook-jp   ← books.rakuten.co.jp
```

Mismo `series_key`, mismo `product_type`, mismo país, **título byte-idéntico**
(`The Art of PRAGMATA プラグマタ 公式設定画集 -Lunar Echoes-`) — y sin embargo son **dos
filas con dos `edition_key` distintos**, porque la ficha de Rakuten no expone la
editorial y la de KADOKAWA Store sí. Es exactamente el mecanismo de **#210** (`publisher`
vacío → sufijo `-unknown-`), esta vez capturado en un producto que entró hoy, con las dos
fuentes en la misma corrida.

**Cómo se manifestó aguas arriba**: las 2 filas llegaron juntas a la cola de aliases como
la candidata `the-art-of-pragmata-lunar-echoes` con `item_count: 2`, y el audit las
reporta como si fueran dos items distintos de una serie sin canónica. No lo son: es un
producto duplicado. **Crear una canónica no habría arreglado nada** — el `series_key` ya
es correcto e idéntico en ambas filas; lo que difiere es el `publisher` del
`edition_key`. Por eso la candidata se saltó.

**Lección operativa para la cola de aliases**: una candidata con `item_count: 2` cuyos
dos sample titles son idénticos es sospechosa de ser #210, no una serie nueva.
Verificar los `edition_key` antes de decidir.

**Nada aplicado (decisión del owner).** El fix de mecanismo es el de #210 (rellenar
`publisher` en el origen o normalizar `-unknown-` contra la edición hermana); el retrofit
cambia `edition_key` y por lo tanto slugs.


## Revisión de ingestión — 2026-09-24

Corregido el upsert compartido: también indexa sources[]. Una relectura de Rakuten actualiza el producto canónico curado en vez de generar una fila cruda. URLs secundarias reclamadas por varios productos se rechazan por ambigüedad, sin fusionar destructivamente.

Evidencia y alcance: [auditoría integral](../audits/2026-09-24-ingestion.md).

### Caché de imágenes — auditoría 2026-09-25

El inventario detectó referencias locales con nombres derivados de una normalización
legacy que descartaba parámetros de URL. Se desactivó esa reutilización ambigua;
se preservan parámetros de identidad/versión. Esto es un riesgo del caché local,
no prueba de un producto incorrecto en esta fuente. La revisión por URL y el
resultado de las re-descargas están en `reports/image-audit-2026-09-25/`. Ante
contenido cambiado o descarga fallida se conserva la imagen anterior.
