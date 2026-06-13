# Fuente: Sumikko (限定版・特装版)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Es una fuente **wiki** (módulo propio, sin entrada en `sources.yml`).
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

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
