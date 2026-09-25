# Fuente: Sumikko (限定版・特装版)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Es una fuente **wiki** (módulo propio, sin entrada en `sources.yml`).
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-02 (44/47 portadas pendientes son SKUs de Amazon muertos — ver
> abajo).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Sumikko (`comic.sumikko.info` — コミック新刊チェック) |
| **URL base** | `https://comic.sumikko.info` |
| **Índice / punto de entrada** | `https://comic.sumikko.info/limited-item/?p=N` (paginado, ~90 items/página) |
| **Tipo de fuente** | Catálogo comunitario / base de datos especializada (NO es tienda, aunque es multi-editorial) |
| **`kind`** | `wiki` (virtual; no está en `sources.yml`) |
| **`source_class`** | `trusted_media` |
| **País** | Japón (`Japón`) — fuente mono-país |
| **Idioma** | Japonés (JP) |
| **Cobertura** | Catálogo japonés de **ediciones limitadas y especiales** de manga (限定版 / 特装版 / 完全版 / 同梱版 / BOX, con extras tipo アクリルスタンド, 小冊子, ブロマイド…). El sitio declara ~3178 items en la home. |
| **Aporte al corpus** | ~2694 items |
| **Parser / módulo** | [`scripts/wikis/sumikko.py`](../../../scripts/wikis/sumikko.py) |

**Editoriales que abarca** (multi-editorial; el `publisher` se rellena por item desde el
HTML, NO con el nombre del sitio — #44). Top del corpus (volumen aproximado):

Kodansha (≈752) · Ichijinsha (≈384) · Shogakukan (≈250) · Kadokawa (≈223) · Hakusensha
(≈173) · Square Enix (≈116) · Shueisha (≈93) · Akita Shoten (≈62) · Mag Garden (≈47) ·
Futabasha (≈28) · Takeshobo (≈22) · Libre (≈16) · Frontier Works (≈13), entre otras.
Algunas editoriales menos frecuentes quedan con su nombre japonés literal (コアマガジン,
マイクロマガジン社, キルタイムコミュニケーション…) hasta que el skill las canonicaliza.

**Por qué importa / qué aporta de único**: cubre la dimensión **"qué EDICIÓN es"** del
mercado japonés —ediciones limitadas / special package con bonus— que las fuentes JP
regulares (Rakuten, Kadokawa Store, Sanyodo) no marcan explícitamente. Es complementaria
a `wikis/booksprivilege.py` (que cubre 店舗特典 / extras de tienda).

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: índice paginado `/limited-item/?p=N` con ~90 items por
  página; ~32 páginas reales cubren el catálogo completo. La metadata viene completa en el
  listing, así que **NO se hitean las detail pages** (`/item-select/<isbn>`).
- **Estructura del HTML**: cada item es un bloque `<a href="/item-select/<isbn>">` con:
  - `div.name` → título (suele incluir volumen y "特装版"/"限定版").
  - `div.sab[0]` → `[fecha de release, autor]` (fecha JP "26年10月23日(金)").
  - `div.sab[1]` → `[imprint, editorial]`.
  - `img[data-src]` → portada (CDN de Amazon, `images-na.ssl-images-amazon.com`).
  - `span.type.type-tag` → describe el **tipo del EXTRA** (CD等, カセット等, 単行本…),
    **NO** si el producto es manga (ver §8). Por eso no se filtra por tipo.
- **Identificador de producto**: ISBN (10 o 13 dígitos) extraído de la URL. La URL canónica
  que se guarda es el detail page `/item-select/<isbn>` (referencia estable aunque el
  listing reordene).
- **Anti-bot / quirks**: ninguno notable. Servidor LiteSpeed, HTML UTF-8 limpio (sin
  mojibake #1). Imágenes lazy: se prefiere `data-src` sobre `src`; se descartan
  placeholders (`reload200_299`, `/loading/`, `no_image200_299_BL.png` = cover R18 blur).
- **Calidad de imágenes**: portadas del CDN de Amazon (resolución decente, mejor que los
  thumbnails de listadomanga).

---

## 4. Discovery: scrape general (FULL) vs incremental (DELTA)

El sitio **no expone filtro por fecha** → siempre recorre el catálogo completo (ordenado
por release_date desc). Por eso FULL y DELTA corren **idéntico**; el upsert por URL deja
sólo lo nuevo en cada pasada.

| | FULL (general) | DELTA (incremental) |
|---|---|---|
| Script / paso | `scripts/scrape_full.sh` — paso **2i** | `scripts/scrape_delta.sh` — paso **2h** |
| Comando | `--bootstrap-wiki sumikko --sleep-seconds 0.3 --min-score 20` | idéntico |
| Discovery | `/limited-item/?p=1..N` con early-stop (3 páginas vacías consecutivas), `max_pages=40` (cubre las ~32 reales) | idéntico |
| Frecuencia | mensual / trimestral | diaria / semanal |
| Tiempo | ~30s (~30 páginas con sleep 0.3) | ~30s |
| Cuándo | refresh completo | novedades recientes (las captura igual: el catálogo va ordenado por fecha y el upsert filtra) |

---

## 5. Proceso de ingestión — técnico

Parser: [`scripts/wikis/sumikko.py`](../../../scripts/wikis/sumikko.py).

### 5.1 Modelo de datos / claves

- **País = Japón** (#46): mono-país; el país va al `edition_key`.
- **Publisher por item** (#44): se toma de `sab[1]` del HTML y se canonicaliza con
  `_PUBLISHER_MAP` (KADOKAWA→Kadokawa, 講談社→Kodansha…). Los no mapeados quedan literales
  en japonés y los resuelve el skill `/watch-standardize-catalog`. **Nunca** se setea el
  publisher al nombre del sitio.
- **ISBN** como identificador; **URL canónica** = `/item-select/<isbn>` (referencia estable).
- **Volumen**: se extrae del título por heurística (`第N巻`, `(N)`, `vol. N`, `N` antes de
  un keyword 限定版/特装版/BOX…) y se anexa como tag `sk-vol:<N>`.

### 5.2 Qué captura el parser

- `parse_listing_page()` → un `Candidate` por bloque `<a href="/item-select/...">`.
- `_virtual_source()`: `kind="wiki"`, `source_class="trusted_media"`, `purity="manga_only"`
  (el sitio cura sólo limited/special editions de manga).
- **`description` inyectada**: cada item arranca con
  `"限定版・特装版 / limited edition / special edition / bonus edition."` para garantizar
  que `detect_signals` levante el signal de edición especial aun cuando el título sólo diga
  "BOX" o "完全版".
- **NO se filtra por `type-tag`** (`accept_types=frozenset()` por default): la etiqueta
  describe el extra, no el producto (#8).

### 5.3 Flujo end-to-end

- Entra en la **FASE 2** (wiki bootstraps) de ambos scripts canónicos: `scrape_full.sh`
  paso **2i** y `scrape_delta.sh` paso **2h**, con el mismo comando.
- Luego pasa por los cleanup retrofits comunes (rescore → filtros → clean_titles →
  backfill imágenes/metadata → consolidate) y el build.

> ⚠️ Tras un scrape, items.jsonl queda **raw** (sin `standardized_at`). NO correr el skill
> `/watch-standardize-catalog` automáticamente (lo decide el owner). El skill es quien
> canonicaliza los publishers japoneses literales que no estaban en `_PUBLISHER_MAP`.

---

## 7. Validación

- **`scripts/validate_corpus.py`** — gate estructural, aplica a TODO el corpus (sin red).
- Snippet read-only de §10 para chequear conteo, país (debe ser 100% Japón) y editoriales.
- Demo rápida del parser: correr el módulo directo (`__main__`) trae 2 páginas para
  smoke-test sin tocar el corpus.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **`type-tag` NO indica si es manga** — la etiqueta `<span class="type type-tag">`
  describe el **extra** de la edición (CD等, カセット等, 単行本…), no el producto.
  Verificado contra fixtures reales (2026-05): items con `カセット、ＣＤ等` incluyen manga
  puro (薬屋のひとりごと vol 22). ✅ Por default no se filtra por tipo; la curación del
  sitio ya garantiza que `/limited-item/` son ediciones especiales de manga.
- **#44 — tienda multi-editorial ≠ editorial** — el sitio agrupa muchas editoriales; el
  `publisher` se rellena por item desde el HTML, NO con "Sumikko". El publisher real lo
  refina el merge por ISBN o el skill. ✅
- **Imágenes lazy / placeholders** — se prefiere `data-src`; se descartan spinners de carga
  y la portada R18 borrosa (`no_image200_299_BL.png`). ✅
- **Fecha JP de 2 dígitos** (`26年…`) — se asume siglo 20XX; el sitio no tiene items
  pre-2000, sin riesgo de colisión. ✅
- **Sin calendario** — el sitio no filtra por fecha; `iter_year_months` devuelve batch
  único y `bootstrap` ignora los argumentos de año/mes. El catálogo completo se recorre
  siempre (igual en full y delta).
- **Falsos positivos por boilerplate de description (audit 2026-06-10)** — el parser
  inyecta `"限定版・特装版 / limited edition / special edition / bonus edition."` en la
  description de TODOS los items, así que títulos donde el 限定 sólo aparece DENTRO de
  los corchetes de obra 『』「」 (es parte del nombre del manga, p.ej.
  サツジンゲーム『配神限定』) se volvían falsos positivos; también pasaban títulos junk
  tipo `>>>>>>&`. ✅ Fix: gate `_has_edition_marker_outside_brackets()` en `sumikko.py`
  — se strippean los spans 『…』/「…」 y se exige un marcador de edición
  (特装版|限定版|完全版|愛蔵版|豪華版|同梱|付き|付録|BOX|ＢＯＸ|セット|画集|特典) en lo que
  queda; sin marcador → el item NO se emite. Además se descartan títulos con <3
  caracteres alfanuméricos/CJK. Auditado contra los 2671 items sumikko existentes: el
  gate sólo excluye los 2 falsos positivos confirmados (cero riesgo de falso negativo).
  Tests en `tests/test_wiki_parser_fixes.py` (`test_sk_*`).
- **Churn de slug ISBN-10 ↔ ISBN-13 resuelto (2026-07-07)**: Sumikko identifica sus
  productos por ISBN (§5.1) y su `cluster_key` cae en la cascada fuzzy/url (no tiene
  `edition_key` propio hasta que el skill lo asigna) — el slug generado
  (`generate_slugs.py`) podía oscilar entre `isbn-{10}` e `isbn-{13}` según qué fila
  del cluster fuera el representante en cada corrida (churn medido: 71 items en TODO
  el corpus, buena parte de origen Sumikko por su volumen). Fix (no específico de esta
  fuente, aplica a `generate_slugs.py` en general): el slug ISBN ahora se deriva
  SIEMPRE del ISBN-13 normalizado vía `manga_watch.isbn13()`, idempotente sin importar
  qué variante de ISBN traiga la fila. Ver `docs/web-next/FRD-006-slug-generation.md`.
- **Curación LLM non-manga 2026-08-23 (gotcha #147)**: 60 items flageados por el
  skill `/watch-standardize-catalog`, de los cuales **52 eran light novels
  legítimas** (限定版/特装版 con drama CD, booklet, tarjetas de ilustración) y se
  conservaron — es el caso testigo de la gotcha #147 (el `prompt-rules.md` del
  skill decía "Light novels → false", contradiciendo CLAUDE.md). Se expulsaron 8:
  making-of del anime de Girls und Panzer, un escape-game book de SCRAP, 化物語
  Premium Item BOX (merch: Nendoroid + pósters), guía visual de historia china,
  revista infantil de trenes, manual del software Hatsune Miku V3, pouch de One
  Piece y clear file de Go-Toubun no Hanayome.

---

## 9. Pendientes / limitaciones conocidas

- **Publishers japoneses literales**: las editoriales fuera de `_PUBLISHER_MAP` quedan con
  su nombre en japonés hasta que corre el skill de standardize. No es un bug, pero hasta
  esa pasada conviven canónicos (Kodansha) con literales (コアマガジン).
- **Sin precio ni URL de tienda**: como toda fuente de referencia, los items traen
  serie/volumen/editorial/edición pero no precio. Candidato a `enrich_references.py` (ver
  CLAUDE.md, "Enrichment pass para items de referencia").
- **Endpoints alternativos no usados** (`/month-list/`, `/weekly-list/`, `/rss.xml`): más
  caros y con menos cobertura de limited editions; no se aprovechan por ahora.
- **{{pendiente: verificar el conteo exacto de páginas reales (~32) y si `max_pages=40`
  sigue cubriendo todo cuando el catálogo crezca}}**.

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (idéntico en full y delta; deja raw, sin standardize):
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki sumikko \
    --sleep-seconds 0.3 --min-score 20

# Smoke-test del parser (2 páginas, NO toca el corpus):
.venv/bin/python scripts/wikis/sumikko.py

# Validar (gate de salud, sin red):
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "sumikko"
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

## 2026-06-12 — títulos oficiales re-exponen keywords de bonus (gotcha #92)

Con la política de títulos (title = nombre oficial JP), los items de Sumikko vuelven a
nombrar el bonus de la edición en el título ("夏目友人帳 ニャンコ先生フィギュアストラップ付き特装版",
"テラフォーマーズ(21)特装版 DVD LIMITED EDITION", "限定版プレミアムBOX", "図鑑未掲載!…").
Los patterns HARD de figura/DVD/プレミアムBOX/図鑑 los mataban como merchandise. Fix
genérico en `is_likely_manga`: tier `_NON_MANGA_HARD_UNLESS_BONUS` + marcador de
inclusión POSICIONAL (付/同梱 pegado al match, 特装版 en cualquier parte — NO 限定版 a
secas). Tests: `test_is_likely_manga_bonus_context_*`. Verificado: 0 rechazos del
corpus Sumikko tras el fix.

## 2026-06-12 — store_bonus separado del título (gotcha #93)

Sumikko (y Rakuten Books JP) traen el 店舗特典 pegado al título oficial:
"数学ゴールデン 2(描き下ろしイラストカード)【楽天ブックス限定特典】". Eso es el perk de compra
de Rakuten, no el nombre del producto. El scraper (`candidate_to_json` →
`mw.split_store_bonus`) lo separa al campo `store_bonus` (visible solo en el detalle,
no en el grid del catálogo). 221 items afectados en el corpus, casi todos de Sumikko.
La edición real (特装版/限定版 con figura/booklet) SÍ queda en el título — solo se quita
el bracket 【…特典…】 del retailer. Ver docs/reference/title-policy.md.

## 2026-08-25 — `[ISBN_ANOMALY]`: los códigos de Sumikko son JAN/EAN-13, no ISBN

Delta diario (`logs/scrape-delta-2026-08-25-110223/04e-backfill-images.log`). El paso
`backfill_metadata --only image_url` emitió 9 markers `[ISBN_ANOMALY]`, **todos** de
Sumikko, con códigos del tipo `4538806044790`, `4580142062228`, `4560219324343`.

**No es un bug — es cómo funciona la fuente.** La URL canónica de Sumikko es
`/item-select/<código>` (§5.1) y para las ediciones especiales con bonus físico ese
código NO es un ISBN sino un **JAN** (EAN-13 japonés, prefijos `45…`/`49…`), porque el
producto está registrado como artículo de comercio y no como libro. Un ISBN-13 real
empieza siempre con `978`/`979`; el validador lo nota y lo reporta.

Comportamiento actual, y es el correcto: el pipeline **conserva** el código
(`kept='4538806044790'`) porque sigue siendo el identificador estable de esa página. No
hay pérdida de dato ni de agrupación — el `cluster_key` no usa ISBN pelado desde que se
eliminó el tier `isbn:` (decisión #4, 2026-07-07), así que un JAN en ese campo no puede
fusionar ediciones distintas.

**Para el owner (no aplicado — decisión suya):** si el ruido molesta en los logs, la
opción limpia es que `normalize_isbn()` reconozca el prefijo JAN y clasifique el código
como `product_code` en vez de emitir la anomalía. Es cosmético: no cambia el corpus.

## 2026-08-28 — la fuente inyectó un juego de mesa (`Overlord Imagine Stories`)

Delta diario (`logs/scrape-delta-2026-08-28-160959/`). Durante la curación de la cola de
series sin canónica (`/watch-enrich-series-aliases`) apareció la candidata
`overlord-imagine-stories`, que **no es manga ni material impreso**: es un *juego de mesa
narrativo* de Kadokawa ambientado en la franquicia Overlord. Entró por esta fuente y pasó
los gates deterministas del pipeline.

Se dejó **sin catalogar como serie** (Action C del skill de aliases) para no acuñar una
canónica de una obra fuera de alcance. El item sigue en el corpus: el skill de aliases no
expulsa nada.

Causa probable: el listado 限定版・特装版 de Sumikko incluye productos de franquicia que no
son libros, y el término de edición limitada alcanza para pasar el scorer. Es el mismo
patrón que ya afecta a otras fuentes por-término (gotcha #154): el gate determinista no lo
matchea, así que se re-ingesta en cada corrida.

**Para el owner (no aplicado):** evaluar un patrón de exclusión por formato para esta
fuente (`ボードゲーム` / juego de mesa y similares), o sumar el título a
`data/comics_blacklist.yml`. Retorno: evita que productos de franquicia no impresos sigan
entrando por el listado de ediciones limitadas.

## 2026-09-02 — 44/47 portadas pendientes del delta de hoy son SKUs de Amazon muertos (1×1)

Backfill post-delta de imágenes (`mirror_images.py`, balance de cierre del delta diario
`logs/scrape-delta-2026-09-02-110142/`). De las 47 portadas nuevas de Sumikko sin espejo
local, **44 (94%) descargan un placeholder estructural `tiny:1x1`** — un JPEG de 43 bytes,
1×1 px — desde `images-na.ssl-images-amazon.com/images/P/<código>.09._SCLZZZZZZZ_.jpg`
(más 1 entry de galería con el mismo patrón, y el mismo código de este item aparece
también documentado arriba por una anomalía distinta de `normalize_isbn`, sin relación).
`mirror_images.py` los detectó correctamente vía `image_store.placeholder_reason()`
(capacidad #3 de OLA 1, gotcha #158) y NO les asignó `local` — el `url` remoto queda de
fallback, comportamiento correcto, nada que reparar en el mecanismo.

**Causa confirmada, no es un bug de `normalize_image_url`**: se probaron 5 variantes de la
misma URL (la capturada tal cual, con `_SY180_`/`_SY500_` insertado, sin ningún sufijo de
tamaño, y sin el segmento `.09`) contra un SKU muerto real
(`4538806044790`, item `amakano-2-unknown-fanbook-jp`) — **las 5 devuelven el mismo
JPEG de 43 bytes / 1×1 px**, sin importar la forma de la URL. El SKU de Amazon
simplemente no tiene imagen subida (o fue retirada) — Amazon no devuelve 404, devuelve
sirve ese placeholder fijo con HTTP 200, por eso `_classify_failure` (que sólo mira el
status code) no lo distingue de un éxito; sólo el chequeo estructural post-descarga lo
atrapa. Mismo patrón que el 404 persistente de Manga-Sanctuary "(planning)" (ver
`docs/scraper/sources/manga-sanctuary.md` § 2026-09-01): la URL capturada en el scrape
apunta a un recurso que dejó de existir del lado de la fuente/CDN, no es recuperable
reintentando la descarga.

Contraejemplo real (para no generalizar de más): el mismo patrón de URL con un SKU VIVO
(`4099432416`, no de esta fuente) sí sirve una imagen real de 353×500 cuando se le quita
el sufijo de tamaño `_SY180_` — el bug es específico del SKU, no del formato de URL.

**Para el owner (no aplicado)**: no hay URL alternativa a reintentar — Sumikko sólo
expone el link de Amazon en su HTML. Si se quiere portada real para estos 44 items,
hace falta una fuente de imagen distinta (búsqueda por texto/whakoom no aplica, son
ediciones JP). Bajo impacto relativo: quedan con 📚 (sin foto) en la UI, mismo estado
que tenían antes del delta de hoy — el backfill no empeoró nada, sólo confirmó que la
URL capturada no tiene remedio.

---

## 2026-09-04 — el early-stop cortó la cosecha a la MITAD y el run reportó éxito

`source_health` flaggeó **1153 candidatos vs mediana 2775 (42%)**. No es variación de la
fuente: es el **heurístico de early-stop cortando por un hueco transitorio**, y el run
terminó diciendo "terminado" sin ninguna señal de error.

### La evidencia — la última página llena es el tell

| Corrida | Última página CON items | Total |
|---|---|---|
| 2026-09-01 | `p=33: 38 items` ← **parcial** | 2813 |
| 2026-09-02 | `p=33: 40 items` ← **parcial** | 2638 |
| 2026-09-03 | `p=33: 41 items` ← **parcial** | 2740 |
| **2026-09-04** | **`p=13: 96 items` ← LLENA** | **1153** |

El catálogo real termina en **p=33 con una página parcial** (~38-41 de 96) — la firma
normal de un fin de paginación. Hoy la última página fue **p=13 y venía LLENA (96)**, y
las tres siguientes devolvieron 0:

```
[sumikko] p=13: 96 items, 96 nuevos (total 1153)
[sumikko] p=14: 0 items (streak 1/3)
[sumikko] p=15: 0 items (streak 2/3)
[sumikko] p=16: 0 items (streak 3/3)
[sumikko] terminado: 1153 candidates con score>=20
```

**Una página llena seguida de cero no es un fin de catálogo.** Es un hueco: rate-limit,
respuesta vacía o hipo del servidor en p=14-16. El log **no registró ningún error, 429 ni
challenge** — por eso el corte fue invisible.

### Por qué no lo detectó nada

El early-stop trata "3 páginas vacías seguidas" como fin de catálogo, sin mirar **si la
última página con datos venía llena**. Cuando el sitio devuelve vacío por un motivo
transitorio, el scraper concluye que terminó, escribe `terminado: N candidates` y el run
sale con rc=0. `source_health` es lo único que lo nota — y lo reporta como "yield
regression", que se lee como problema de la fuente y no como corte del scraper.

### Impacto

**Hoy, cero pérdida real**: los reportables fueron 0 (las 13 páginas cosechadas ya eran
todas conocidas), porque la fuente pagina de más reciente a más antiguo y lo nuevo entra
por las primeras páginas.

**El riesgo es el caso no observado**: si el hueco cae en p=2 o p=3, el mismo mecanismo
descarta el 90% del catálogo **y también reporta éxito**. La pérdida sería de items
recientes — justo los que el delta existe para capturar. Ya pasó una vez en modo benigno;
no hay nada que impida la versión cara.

### Recomendación (NO aplicada — decisión del owner)

1. **Distinguir "fin de catálogo" de "hueco"**: sólo aceptar el early-stop si la última
   página con datos vino **parcial** (< tamaño de página). Si venía llena, reintentar esas
   páginas antes de cortar. Es el fix de MECANISMO y sirve para todos los wikis paginados,
   no sólo Sumikko.
2. **Que el corte sospechoso sea ruidoso**: si se corta después de una página llena,
   emitir WARN y que el step salga con rc≠0 — hoy un corte del 58% del catálogo es
   indistinguible de una corrida sana en el resumen del delta.

**Nada de esto se aplicó**: la rutina diaria documenta y recomienda; tocar el heurístico
de paginación es un cambio de mecanismo del scraper y es del owner.

### Integridad de ingestión — continuación 2026-09-24

Los fallos de transporte ahora registran `[WIKI-ISSUE]` en la sesión. El dispatcher
conserva los resultados parciales y termina con error; incluye el fallo en el
reporte. Una respuesta fallida no equivale a catálogo vacío. El watermark por
fuente solo avanza después de persistir corpus y estado, sin incidencias ni
límites alcanzados. Tras una interrupción, el calendario amplía su ventana hasta
el último inicio exitoso con siete días de solapamiento. Un import histórico
acotado, un chunk explícito o un dry-run no adelantan ese watermark.

### Continuación de auditoría — 2026-09-24

Tope defensivo aumentado a 1000 páginas; alcanzarlo reporta cobertura incompleta. El final normal sigue siendo tres páginas consecutivas sin candidatos.

### Comprobación viva adicional — 2026-09-24

Reingesta completa del listado en staging: 2653 candidatos, 2652 reportables y
39 URLs primarias adicionales. Se conservan las alertas de códigos de producto
que no validan como ISBN: no se inventan ni corrigen automáticamente sus dígitos.

La corrida detectó siete referencias ambiguas heredadas; no confirmó checkpoint.
Cinco se resolvieron al excluir propietarios con ISBN válidos distintos. Las
otras dos corresponden a extras distintos de `僕とロボコ 11` (llaveros Roboco y
Roboco Quiz), antes ligados a las fichas Bondo y Motsuo: se separaron tras revisar
los títulos y códigos de producto de la misma fuente. Un código de tienda que
no valida como ISBN no sirve para desambiguar automáticamente varias tiendas.
La recuperación pendiente de publicación asciende a 45 filas de Sumikko.

### Reparación de referencias históricas — 2026-09-24

Se quitaron 28 referencias de `comic.sumikko.info` asociadas a otra fila con ISBN
válido diferente del producto cuya URL primaria es esa misma referencia. Se
conservan ambos productos y su URL primaria; no se fusionan por ISBN. Evidencia
por URL/ISBN en `reports/ingestion-audit-2026-09-24/closure/publication-2-manifest.json`.
