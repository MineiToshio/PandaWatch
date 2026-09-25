# Fuente: KADOKAWA (Japón)

> ⚠️ **PODA 2026-06-12 (poda de fuentes muertas)** — `JP - KADOKAWA Comics`: El catálogo Comics se deshabilitó (1 item compartido, 0 únicos); KADOKAWA Store y Store Artbooks/Fanbooks siguen activas.
> Registro completo: [descartadas/README.md](descartadas/README.md).

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-07-07.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | KADOKAWA (3 entradas en `sources.yml`) |
| **URL base** | `https://www.kadokawa.co.jp` · `https://store.kadokawa.co.jp` |
| **Tipo de fuente** | Editorial oficial (`source_class: official`) + su tienda oficial |
| **`kind` en sources.yml** | `html` (las 3) |
| **País** | Japón (`jp`) — fuente mono-país |
| **Idioma** | Japonés (CJK) |
| **`publisher`** | KADOKAWA (las 3) |
| **Aporte al corpus** | ~85 items (todos `country=Japón`, `publisher=KADOKAWA`) |
| **Parser / módulo** | Entradas en `sources.yml` — extractor genérico, sin parser propio |

Las **tres entradas** que cubre esta ficha (todas `official`, `html`, Japón, KADOKAWA):

| Nombre en `sources.yml` | URL | tags | Qué aporta |
|---|---|---|---|
| `JP - KADOKAWA Comics` | `https://www.kadokawa.co.jp/category/comic/` | manga, official, japan | Catálogo editorial de cómics/manga |
| `JP - KADOKAWA Store Artbooks Fanbooks` | `https://store.kadokawa.co.jp/shop/c/c109050/` | artbook, fanbook, official, japan | Tienda oficial, categoría de artbooks y fanbooks |
| `JP - KADOKAWA Store` | `https://store.kadokawa.co.jp/shop/` | store, bonus, official, japan | Tienda oficial general (ediciones con bonus de tienda) |

**Por qué importa / qué aporta de único**: es la **fuente oficial japonesa** de KADOKAWA.
Captura ediciones del mercado de origen (japonés) que no aparecen en fuentes occidentales:
artbooks y fanbooks (categoría dedicada en la tienda) y ediciones con **bonus de tienda
oficial**, además del catálogo editorial de manga.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**:
  - `kadokawa.co.jp/category/comic/` — listado editorial de la categoría cómic/manga.
  - `store.kadokawa.co.jp/shop/` — tienda oficial; `c/c109050/` es la categoría de
    artbooks/fanbooks dentro de la tienda.
- **Selectores**: ninguno definido en `sources.yml` para las 3 entradas → la captura va por
  **auto-detección del extractor genérico** (detección de producto/imagen por
  heurística, no por selectores propios).
- **Identificador de producto**: URL canónica de la página de producto de la tienda/catálogo.
- **Idioma / encoding**: contenido japonés (CJK). Si aparece mojibake mixto en JP, decodificar
  con `errors='replace'` (#28). Para signals sobre texto CJK, el matching es por substring,
  no por word-boundary ASCII (#9).

---

## 5. Proceso de ingestión — técnico

- **Fase**: las 3 entradas se scrapean en **FASE 1** del pipeline canónico
  (`manga_watch.py --workers 8`, dentro de `scrape_full.sh` / `scrape_delta.sh`), igual que
  cualquier fuente del YAML.
- **Sin parser propio**: usan el **extractor genérico** del pipeline (label/value +
  auto-detección). NO hay módulo dedicado en `scripts/wikis/` ni retrofit específico.
- **Sin selectores en el YAML** → la extracción de título/imagen es por heurística del
  extractor genérico.
- **Filtros estándar**: pasan por la cascada `is_likely_manga()` y los filtros del pipeline
  (`filter_non_manga`, `filter_collectible`) como toda fuente. Al ser `official` japonesa, el
  STRONG manga hint suele venir del contexto editorial KADOKAWA.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **#28 (JP mojibake mixto)**: en fuentes japonesas el body puede traer bytes crudos que rompen
  `decode('utf-8', strict)`; el patrón es decodificar con `errors='replace'`. Aplica de forma
  preventiva si aparece texto roto desde KADOKAWA.
- **#9 (signals sobre CJK)**: los detectores de signals usan substring para CJK (no
  word-boundary ASCII). Tenerlo presente si se agrega cualquier detector que toque títulos
  japoneses.
- **Fechas crudas colándose en `release_date` (2026-07-07, gotcha #123, regresión de #80)**:
  KADOKAWA Store (extractor genérico, sin parser propio) es una de las fuentes que aportó
  filas a las **113 fechas no-ISO** detectadas por la nueva invariante WARN `DATEISO` de
  `validate_corpus.py` — formatos como `"2026年04月08日"` llegaban crudos porque
  `normalize_release_date()` se aplicaba en puntos de asignación específicos pero no como
  guardia UNIVERSAL. Fix (no específico de esta fuente, aplica a TODO el pipeline):
  `candidate_to_json` ahora envuelve incondicionalmente `release_date` en
  `normalize_release_date()` en el sink final de escritura. Idempotente; no requiere backfill
  específico de KADOKAWA (el warning se resuelve solo en el próximo re-scrape de las filas
  afectadas, o corriendo `normalize_release_dates.py --all-formats` sobre el corpus).
- **Curación LLM non-manga 2026-08-23**: 6 items expulsados — 2 bundles de
  videojuego con el marcador ファミ通DXパック (Persona 4 Revival, ANOMALITH PS5,
  agregado como patrón HARD), 1 álbum de música, 2 boxes de merch (アクリルカード /
  きらきら缶バッジコレクション) y 1 libro ilustrado de Winnie the Pooh que había
  entrado por la variante "Artbooks Fanbooks".

---

## 9. Pendientes / limitaciones conocidas

- **Sin selectores propios**: la captura depende del extractor genérico; si KADOKAWA cambia su
  layout, la auto-detección puede degradarse sin aviso. No hay auditoría de red dedicada para
  esta fuente.
- **{{pendiente: anti-bot / JS-rendered}}** — no verificado si la tienda
  (`store.kadokawa.co.jp`) requiere JS (`--enable-js`, #12) o tiene anti-bot. Si el conteo de
  items cae a 0, revisar primero esto.
- **{{pendiente: calidad de imágenes}}** — no determinada (alta/baja resolución, de dónde sale
  la portada).

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo estas fuentes (ajustar el nombre exacto del YAML):
.venv/bin/python scripts/manga_watch.py --only-source "JP - KADOKAWA Comics"
.venv/bin/python scripts/manga_watch.py --only-source "JP - KADOKAWA Store Artbooks Fanbooks"
.venv/bin/python scripts/manga_watch.py --only-source "JP - KADOKAWA Store"

# Validar (gate estructural, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver items reales de KADOKAWA en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "kadokawa"
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

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0 duras) →
tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza esta
ficha.

## 2026-08-28 — artbooks de videojuego: veredicto LLM `is_manga=false` (caso limítrofe)

Delta diario (`logs/scrape-delta-2026-08-28-160959/`). Dos items quedaron pendientes en
`data/unmapped_series.jsonl` (reason `llm_non_manga`):

- `真・女神転生V / V Vengeance 公式設定画集` (artbook oficial de settings del juego)
- `真・女神転生V / V Vengeance 公式設定画集 ebtenDXパック（アトラスDショップ限定特典付き）`
  (mismo artbook, pack DX con bonus exclusivo de tienda)

**Es un caso limítrofe, no un error claro de la fuente.** Son 公式設定画集 (artbooks
oficiales) de un **videojuego**, no de un manga/anime. `product_type=artbook` está dentro
del enum del proyecto, pero la obra de origen no es manga — por eso el LLM los rechaza.
La 2ª entrada además es exactamente el tipo de edición que el proyecto busca (pack
limitado con 特典 de tienda), sólo que sobre una obra fuera de alcance.

**Para el owner (decisión de alcance, no aplicada):** definir si los artbooks de
videojuego entran o no. Si NO entran, conviene un patrón de exclusión; si SÍ entran,
conviene ajustar `prompt-rules.md` para que el LLM no los rechace — hoy se re-ingestan
y se re-evalúan cada corrida sin converger (mismo patrón que gotcha #154).

## 2026-08-31 — regresión de yield: 3 items contra una mediana de 7 (43%)

Delta diario (`logs/scrape-delta-2026-08-31-110202/`). `source_health --baseline-alert`
marcó **JP - KADOKAWA Store** como única regresión de yield del run: 3 items en esta
corrida contra una mediana histórica de 7 sobre 8 corridas (43% de la mediana).

No hubo error, challenge ni skip — la fuente respondió bien; simplemente trajo menos.
Con 8 corridas de historial y una sola por debajo del umbral, es tan compatible con
"semana floja de novedades" como con un cambio de selectores que dejó de ver parte del
listado. **No es accionable todavía**: lo que lo vuelve accionable es que se repita.
Si en la próxima corrida sigue en ~40-50% de la mediana, ahí conviene revisar los
selectores de `store.kadokawa.co.jp/shop/c/c109050/` contra el HTML vivo.

Dato de contexto del mismo run: la fuente aporta 130 URLs rancias de 186 (70%, la más
vieja de 105 días).

## 2026-09-01 — la regresión de yield SE REPITIÓ: 2ª corrida consecutiva en 3 items (43%)

Delta diario (`logs/scrape-delta-2026-09-01-110203/06-source-health.md`). `JP - KADOKAWA
Store` vuelve a aparecer en **YIELD REGRESSIONS**, con exactamente el mismo número que
ayer: **3 candidatos contra una mediana de 7 sobre 9 corridas (43%)**. La línea del log
es `[JP - KADOKAWA Store] candidatos con señales: 3` — respuesta normal, sin error HTTP,
sin challenge, sin skip.

Esto **cumple la condición de accionabilidad que dejó escrita la nota del 08-31**
("lo que lo vuelve accionable es que se repita… si en la próxima corrida sigue en
~40-50% de la mediana, conviene revisar los selectores"). Dos corridas seguidas con el
mismo valor exacto (3) pesa más hacia "el parser dejó de ver parte del listado" que
hacia "semana floja": una semana floja fluctúa, un selector roto devuelve el mismo
subconjunto estable.

Matiz honesto de tamaño de muestra: hablamos de 3 vs 7 items. La diferencia absoluta es
de 4 items, así que también es compatible con ruido de una tienda que rota poco stock
destacado. No es una emergencia.

La entrada hermana `JP - KADOKAWA Store Artbooks Fanbooks` sigue sana en el mismo run
(27 candidatos con señales, 5 páginas) — o sea el problema, si existe, es del listado
general `/shop/`, no de la categoría de artbooks.

**No aplicado**: no se tocaron selectores ni `sources.yml`. Recomendación al owner:
comparar a mano `store.kadokawa.co.jp/shop/` contra los selectores actuales; es la
primera fuente de la cola de mantenimiento de parsers.

## 2026-09-05 — merchandising entrando por el token `BOX`, y atascado en bucle de Tier 3

Dos items de KADOKAWA Store detectados el **2026-09-03** siguen **crudos** (sin
`standardized_at`) después de las corridas del 09-04 y 09-05:

| URL | Título | Qué es realmente |
|---|---|---|
| `store.kadokawa.co.jp/shop/g/g302606000402/` | TVアニメ「ガチアクタ」ポジフィルム風クリアシートコレクション BOX | Caja de láminas transparentes tipo positivo (merchandising de la serie de anime) |
| `store.kadokawa.co.jp/shop/g/g302604002169/` | DIGIMON BEATBREAK キラキラ缶バッジ お祭りVer. Box | Caja de chapas/pins |

**Ninguno de los dos es un producto editorial**: no hay tomo, ni ISBN, ni contenido
impreso — son goods. Entran porque el título termina en `BOX`/`Box`, que el pipeline lee
como señal de *box set* (el tipo de edición que sí buscamos). El LLM del skill de
estandarización los detecta bien y los marca `is_manga=false`, pero ese veredicto **no
expulsa** (por diseño, WO-C): el item queda pendiente esperando que un gate determinista
lo saque. Como ningún patrón de `filter_non_manga`/`filter_collectible` cubre "caja de
chapas", nunca lo sacan.

Consecuencia medida hoy (gotcha **#191**): el veredicto `is_manga=false` es la única rama
de `standardize_apply.py` que deja el item pendiente **sin** incrementar
`standardize_attempts`, así que el escape hatch `standardize_exhausted` no se dispara y
los dos items **volvieron a mandarse a un subagente Tier 3 hoy** (verificado en el journal
del workflow) — la ruta de inferencia más cara, repetida en cada corrida, indefinidamente.

**Nada aplicado.** Dos recomendaciones para el owner, independientes:

1. **Fix de mecanismo (barato, alto retorno)**: incrementar `standardize_attempts` también
   en la rama `is_manga=false` de `scripts/standardize_apply.py`. Con eso, a la 3ª corrida
   el item escala a `standardize_exhausted` y deja de consumir LLM. Cierra el bucle para
   TODOS los items no-manga pendientes, no sólo estos dos.
2. **Evidencia non-manga por título/URL (acotado)**: agregar tokens de merchandising
   japonés —`缶バッジ` (chapas), `クリアシート` / `クリアファイル` (láminas/carpetas),
   `アクリルスタンド`— como señal non-manga. Ojo con el precedente de las gotchas #187-#190:
   **medir la composición real de la fuente antes de tocar nada**; KADOKAWA Store es una
   fuente legítima de artbooks y fanbooks, y un patrón demasiado ancho destruiría material
   válido. `BOX` a secas NO sirve como discriminador: los box sets reales lo usan igual.

## 2026-09-06 — día 4 de los 2 items de merchandising en el bucle de re-inferencia

Los dos items detectados el 2026-09-03 (`TVアニメ「ガチアクタ」ポジフィルム風クリアシート
コレクション BOX` y `DIGIMON BEATBREAK キラキラ缶バッジ お祭りVer. Box` — chapas y hojas
de plástico, no manga) volvieron a mandarse a un subagente Tier 3 por **cuarto día
consecutivo**. Verificado en el corpus: siguen con `standardize_attempts` sin valor y sin
`standardized_at`, exactamente como describe la gotcha #191.

Confirma que el escape hatch `standardize_exhausted` (cap `MAX_STANDARDIZE_ATTEMPTS=3`)
**nunca se dispara para esta rama**: son 4 corridas contra un cap de 3. El costo no es
visible en ningún conteo de items —el corpus no crece— sino en la ruta más cara del skill,
repetida indefinidamente. Hoy el bucle sumó un tercer inquilino desde otra fuente (el
fotolibro de Rakuten, día 2), así que el consumo crece de forma acumulativa.

Sigue sin aplicarse: el fix es de una línea (incrementar el contador también en la rama
`is_manga=false` de `standardize_apply.py`) y es decisión del owner.

## 2026-09-07 — El bucle #191 DUPLICÓ de tamaño + un ítem de merchandising sí entró como manga

### El bucle creció de 3 a 6

Sexta corrida consecutiva con la rama `is_manga=false` sin incrementar
`standardize_attempts`. Los 3 inquilinos conocidos siguen ahí, con `attempts = None`, y hoy
se sumaron 3 más:

| Item | Fuente | Detectado | `standardize_attempts` |
|---|---|---|---|
| ガチアクタ ポジフィルム風クリアシートコレクション BOX | KADOKAWA Store | 2026-09-03 | `None` |
| DIGIMON BEATBREAK キラキラ缶バッジ お祭りVer. Box | KADOKAWA Store | 2026-09-03 | `None` |
| 特別限定版 中務裕太ファースト写真集『1000%』 | Rakuten Books | 2026-09-06 | `None` |
| コーヒーが冷めないうちに(特装版/特製しおり1種) | Rakuten Books | **2026-09-07** | `None` |
| 『週に一度クラスメイトを買う話』Birthday B2タペストリー With Ver. | KADOKAWA Store | **2026-09-07** | `None` |
| 『週に一度クラスメイトを買う話』Birthday B2タペストリー 宮城志緒理 | KADOKAWA Store | **2026-09-07** | `None` |

El bucle **no es estable: crece**. Cada corrida agrega los rechazos nuevos del LLM al pool
permanente de Tier 3 (la ruta más cara) y ninguno sale nunca, porque el cap de
`MAX_STANDARDIZE_ATTEMPTS = 3` se cuenta sobre un contador que esta rama no toca. Seis
corridas contra un cap de 3, y el costo por corrida ahora es el doble que hace cuatro días.

### Hallazgo nuevo: el veredicto es INCONSISTENTE dentro de la misma familia de producto

KADOKAWA Store publicó hoy tres artículos del mismo evento y del mismo tipo (merchandising
de `週に一度クラスメイトを買う話`):

| Producto | Veredicto del LLM | Estado |
|---|---|---|
| B2タペストリー With Ver. (tapiz) | `is_manga=false` | pendiente, en el bucle |
| B2タペストリー 宮城志緒理 (tapiz) | `is_manga=false` | pendiente, en el bucle |
| **描き下ろしアクリルジオラマ (diorama acrílico)** | **`is_manga=true`** | **estandarizado y VIVO en el corpus** |

El tercero quedó con `product_type = manga`, `edition_display = "Variant (KADOKAWA)"` y un
`series_display` que es el título entero en minúsculas — es decir, **un diorama de acrílico
está publicado en el catálogo como si fuera un tomo de manga**. Los tres son el mismo tipo
de producto; la única diferencia es qué le tocó a cada uno en el sorteo del LLM.

Esto muestra que el problema no es sólo de costo: el veredicto por-item de un LLM sobre
merchandising japonés **no es reproducible**, así que apoyarse en él como único guardián
deja pasar items fuera de alcance de a uno. Composición actual de la fuente en el corpus:
59 artbook, 31 fanbook, 5 boxset, **4 "manga"** — de esos 4, al menos 1 es merchandising.

### Recomendaciones (NO aplicadas — decisión del owner)

1. **El fix de una línea de #191** (incrementar `standardize_attempts` también en la rama
   `is_manga=false` de `standardize_apply.py`): corta el bucle y hace que estos items
   escalen a `standardize_exhausted` para curación manual, en vez de gastar Tier 3 para
   siempre. Sigue siendo lo más barato y ya lleva 6 corridas de evidencia.
2. **Gate determinista de merchandising**, para no depender del criterio del LLM: los
   tokens `タペストリー`, `アクリルスタンド`, `アクリルジオラマ`, `缶バッジ`,
   `クリアシート`, `キーホルダー` identifican producto físico que no es libro. Un patrón
   duro los expulsa siempre, igual para los tres hermanos de hoy. Ojo con la advertencia de
   la gotcha #189: los libros que traen esos extras **de regalo** mencionan el mismo token,
   así que la regla tiene que mirar el producto, no la mención (p. ej. exigir que el token
   esté en la CABEZA del título, no después de un `+` o de `付き`).
3. **Curar el diorama ya ingresado** una vez que exista (2) — hoy es 1 item.

### 2026-09-07 (mismo día) — RESUELTO

**Aplicado**, las dos recomendaciones:

**1. El bucle #191 está cortado.** `standardize_apply.py` ahora incrementa
`standardize_attempts` también en la rama `is_manga=false`. Era la única rama que
dejaba el item pendiente sin contar el intento, así que
`MAX_STANDARDIZE_ATTEMPTS` nunca se alcanzaba y el item volvía a gastar Tier 3
indefinidamente. Con el contador, a los 3 intentos el audit lo saca de las
proyecciones y lo manda a curación manual.

**2. Gate determinista de merchandising JP** (`_NON_MANGA_MERCH_JP` +
`_merch_bonus_context_near()` en `manga_watch.py`). Tier propio, separado de
`_NON_MANGA_HARD_UNLESS_BONUS`, porque el rescate por marcador ROMANCE
(con/with/avec…) es ruido en un título japonés: `"B2タペストリー With Ver."` usa
"With" como parte del NOMBRE de la variante, y con el rescate genérico el tapiz
se salvaba por error.

Tokens: `タペストリー`, `アクリル(スタンド|ジオラマ|フィギュア|キーホルダー|チャーム|ブロック|パネル)`,
`缶バッジ`, `クリアシート(コレクション)`, `キーホルダー`, `ラバーストラップ|ラバーマット`.

**La primera versión de la regla iba a destruir 10 manga reales** — exactamente
la trampa de la gotcha #189, detectada sólo por leer el dry-run COMPLETO sobre el
corpus. Dos correcciones salieron de ahí:

- **Los marcadores de inclusión también van en hiragana.** Media docena de
  ediciones reales escriben `つき`, no `付き` ("アクリルキーホルダー2個つき限定版",
  "アクリルスタンドつき限定版"). La ventana posterior al match se amplió a 16
  caracteres para admitir un contador entremedio (`2個つき`).
- **El discriminante fuerte no es el marcador, es que el título nombre un LIBRO.**
  `僕とロボコ 11(アクリルキーホルダー(ガチゴリラ))` no tiene marcador ninguno y es
  un tomo. Se rescata por número de tomo —incluido el número SUELTO tras el
  nombre de la serie— o por cualquier señal STRONG de manga.

Resultado del dry-run final sobre los 14 399 items: **exactamente 5 rechazos, los
5 merchandising real, 0 falsos positivos**. Los 5 se expulsaron (corpus
14 399 → 14 394), incluido el diorama de acrílico que estaba publicado como
`product_type = manga`.

Efecto sobre el bucle: **de 6 items pendientes bajó a 2** (el fotolibro de ídolo
de Rakuten y `コーヒーが冷めないうちに(特装版)`, que es un falso negativo del LLM sobre
una edición especial legítima). Los dos ahora acumulan intentos y escalarán solos
a curación.

Tests: `test_merch_jp_gate_rejects_standalone_merchandising` y
`test_merch_jp_gate_never_kills_a_real_volume` (este último con los 8 casos reales
que el dry-run destapó).

## 2026-09-11 — una caja de cartas acrílicas se escapó del gate (falta `アクリルカード`)

Delta diario (`logs/scrape-delta-2026-09-11-111743/`). Entró y quedó **estandarizado y
vivo en el corpus** `デジモンアドベンチャー オーロラアクリルカード Box`
(`https://store.kadokawa.co.jp/shop/g/g302603000372/`, 6 930 円): una caja de cartas de
acrílico de Digimon Adventure, merchandising puro sin libro. Dos fallas encadenadas:

1. **El gate determinista no lo cubre.** `_NON_MANGA_MERCH_JP` (`manga_watch.py:3941`)
   lista `アクリル(?:スタンド|ジオラマ|フィギュア|キーホルダー|チャーム|ブロック|パネル)` —
   **sin `カード`**. Peor: `アクリルカード` está en la tabla de SEÑALES como bonus de 30
   puntos (`manga_watch.py:292`), así que el scorer lo premió (score 70/115, señales
   `アクリルカード` + `box`).
2. **El LLM de standardize lo aceptó** como `product_type = boxset` y le inventó una serie
   ajena: `series_key = chiikawa`, `edition_key = chiikawa-kadokawa-boxset-jp`. El título
   no menciona Chiikawa en ningún lado — es la misma no-reproducibilidad del veredicto
   sobre merchandising que motivó el gate (#191).

**Recomendación (NO aplicada — decisión del owner)**: agregar `カード` a la alternancia de
`アクリル(...)` en `_NON_MANGA_MERCH_JP`. El rescate existente ya protege las ediciones
reales que la traen de regalo (`アクリルカード付き特装版` tiene marcador `付` y señal de
tomo), pero hay que correr el dry-run de `filter_non_manga.py` completo y leerlo antes
de aplicar, como en el 09-07. La expulsión del item la haría ese mismo filtro en la
próxima corrida; la rutina diaria no lo tocó.

## 2026-09-13 — otro formato acrílico fuera del gate: `アクリルクリップ`

Delta diario (`logs/scrape-delta-2026-09-13-110143/`). Entró
`【カドスト限定特装版】『儒烏風亭らでん、芸術偏愛ことはじめ』ミュージアムノート＆アクリルクリップ付きセット`:
un libro de ensayo sobre arte de una VTuber, en set con cuaderno y clip acrílico. No es
manga ni artbook de una serie.

Esta vez **el LLM de standardize sí lo marcó** (`is_manga=false`, nota `merchandise`) y
quedó en la cola de curación `llm_non_manga`, sin estandarizar. Pero el gate determinista
tampoco lo habría atrapado: `クリップ` no está en la alternancia `アクリル(...)` de
`_NON_MANGA_MERCH_JP`, igual que `カード` el 09-11. Van dos formatos acrílicos en tres
días que dependen sólo del veredicto del LLM, que no es reproducible (#191).

**Recomendación (NO aplicada)**: en vez de ir sumando formatos de a uno (`カード`,
`クリップ`…), evaluar si la regla puede ser `アクリル\S+` **sin** marcador de inclusión
(`付`/`つき`) y **sin** nombre de libro en el título, que es el discriminante que ya
funcionó el 09-07. Aplica lo mismo que para `カード`: leer el dry-run completo de
`filter_non_manga.py` antes de aplicar.

## 2026-09-18 — merchandising de colaboración (`缶バッジ`, `ブロマイド`) fuera del gate

Delta diario (`logs/scrape-delta-2026-09-18-110112/`). Entraron 3 artículos NUEVOS de la
colaboración My Hero Academia × Fuji-Q: `…にいてんごきらきら缶バッジコレクション 富士急コラボver. vol.1 Box`,
`…vol.2 Box` y `…ミニブロマイドコレクション 富士急コラボver. Box`. Son cajas ciegas de
chapas (缶バッジ) y fotos-tarjeta (ブロマイド): merchandising puro, sin libro.

Pasaron `filter_non_manga` en la Fase 3 del scrape: ninguno de los dos términos está en
`_NON_MANGA_MERCH_JP` (la familia `アクリル(...)` no aplica). El LLM de standardize sí los
marcó `is_manga=false` y quedaron crudos en la cola `llm_non_manga`, pero la heurística
del scraper les había acuñado `series_key = ver-box` (resto del título tras cortar en
`ver.`), que apareció como candidata de aliases con 3 items — se saltó.

**Recomendación (NO aplicada — decisión del owner)**: sumar `缶バッジ` y `ブロマイド` al gate
de merchandising JP con la misma condición que ya funciona (sin marcador `付`/`つき` y sin
nombre de libro en el título), y leer el dry-run COMPLETO de `filter_non_manga.py` antes de
aplicar — hay tomos reales que traen `缶バッジ付き特装版`. Es el 4º formato de merchandising en
una semana que depende sólo del veredicto del LLM (`アクリルカード`, `アクリルクリップ`, y ahora
estos dos).

## 2026-09-19 — 503 con sala de espera propia ("ただいまサイトが込み合っております")

Delta `logs/scrape-delta-2026-09-19-110115/`: las DOS entradas (`KADOKAWA Store` y
`KADOKAWA Store Artbooks Fanbooks`) cayeron con `HTTP 503`. Verificado en vivo ~1 h después:
`/shop/` sigue devolviendo **503 con una página de espera de 19 KB** ("el sitio está
congestionado, espere su turno; la página se actualiza sola", con contador de gente en
cola). No es un bloqueo al UA del scraper: es una sala de espera de tráfico del propio
sitio (probable pico por un lanzamiento/evento). Es la primera vez que se ve; se reporta
correctamente como 🔴 Broken (a diferencia de Queue-it de Panini, #208, que se disfraza de
yield parcial). Acción: ninguna; si persiste 3+ corridas, reevaluar.

## 2026-09-20 — 缶バッジ / ブロマイド fuera del gate: 3 items agotaron sus intentos

Los tres artículos de merchandising que el 2026-09-18 se anotaron como fuera del gate de
merchandising JP (#191) llegaron hoy a `standardize_attempts = 3` y **escalaron solos a
curación** (`standardize_exhausted` en `data/unmapped_series.jsonl`):

- `僕のヒーローアカデミア ミニブロマイドコレクション 富士急コラボver. Box`
- `僕のヒーローアカデミア にいてんごきらきら缶バッジコレクション 富士急コラボver. vol.1 Box`
- `僕のヒーローアカデミア にいてんごきらきら缶バッジコレクション 富士急コラボver. vol.2 Box`

Los tres son del mismo evento (colaboración Fuji-Q) y ninguno es un libro:
`ミニブロマイドコレクション` = colección de mini-bromides (fotos), `缶バッジコレクション` =
colección de chapas. El escape hatch de #191 funcionó como se esperaba —dejaron de gastar
Tier 3 y se fueron a curación—, pero **gastaron 3 corridas de LLM antes de salir**, que es
exactamente lo que el gate determinista debería haber evitado en la primera.

Efecto colateral medible: los tres comparten el `series_key` derivado `ver-box` (del
sufijo `ver. Box` del título), que hoy encabezó la cola de aliases con 3 items y un
best-guess 🟡 espurio (`fuse-box`, 0.67) — o sea, el merchandising no sólo cuesta LLM de
standardize, también ensucia la cola de series.

**Recomendación (NO aplicada)**: agregar `ブロマイド` y `缶バッジ` a los marcadores de
merchandising del gate JP. Vale la trampa ya documentada en #189/#191: verificar el
`--dry-run` COMPLETO antes de aplicar, porque los marcadores de INCLUSIÓN de un bonus
(`付き`, `つき`) conviven con estos términos en manga real que regala una chapa, y el
discriminante fuerte es que el título nombre un LIBRO, no el marcador suelto.

### Auditoría full — 2026-09-24

El catálogo de artbooks usa `/shop/c/c109050_p2/` y siguientes; se mantiene este
formato explícito al endurecer la detección de paginación. La corrida aislada
recorrió 184 páginas y obtuvo 389 candidatos antes de filtros finales.
