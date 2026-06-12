# Fuente: Aladin (Corea del Sur)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-12 (alta de la fuente).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | KR - Aladin (만화 한정판) |
| **URL base** | `https://www.aladin.co.kr` |
| **Punto de entrada** | `/search/wsearchresult.aspx?SearchTarget=Book&SearchWord=만화+한정판&page=1` (~428 resultados, 18 págs) |
| **Tipo de fuente** | Librería online multi-editorial (retailer) |
| **`kind`** | `html` |
| **`source_class`** | `retailer` |
| **País / idioma** | Corea del Sur / Coreano |
| **`publisher`** | **VACÍO** (gotcha #44) — el real (학산문화사/Haksan, 대원씨아이/Daewon, 디앤씨웹툰비즈/D&C…) sale de la ficha |
| **Cobertura** | 한정판 (ediciones limitadas) de manga japonés licenciado + webtoons coreanos en print |
| **Aporte al corpus** | ~390 reportables (primera fuente de Corea; el país estaba en 0) |
| **Parser** | Entrada en `sources.yml` con selector `div.ss_book_box` |

**Por qué importa**: abre Corea de 0. Las 한정판 coreanas son **ediciones limitadas
DE FÁBRICA** con ISBN y precio propios (2-3× el tomo regular) — estructuralmente
distintas del patrón BooksPrivilege (tomo regular + regalo de tienda), por eso la
fuente pasó la evaluación aunque no haya foto del extra. Cubre además ediciones
print de webtoons coreanos (Solo Leveling/나 혼자만 레벨업, 화산귀환) que NO existen
en ninguna otra fuente del corpus.

---

## 2. Descripción técnica

- HTML server-rendered (~296KB por página), sin anti-bot, paginación `&page=N`.
- **La paginación del sitio es JS** (`Javascript:Page_Set('2')`) — el paginador
  genérico la sigue gracias a: (1) `&page=1` explícito en la URL fuente y
  (2) la extensión 2026-06-12 de `find_next_page_url` estrategia 4 que acepta
  evidencia de página siguiente en llamadas JS de paginación.
- Detalle (`/shop/wproduct.aspx?ItemId=N`): ISBN-13 coreano (979-11-…), fecha
  exacta, editorial, precio KRW.
- Señales en coreano (alta 2026-06-12 en `KEYWORD_RULES`): 한정판 (limited, 50),
  특별판/특장판 (special), 박스 세트 (box), 아트웍스/화집 (artbook), 포토카드/아크릴 (bonus).

## 5. Proceso de ingestión

- FASE 1 (fuente YAML). `max_pages: 18`. Dry-run de alta: 428 candidatos / 389
  reportables.

## 8. Problemas conocidos

- **Sin foto del extra** (solo portada del tomo; los extras se listan como texto).
- **Títulos en coreano**: la serie requiere aliases KO en `series_aliases.yml`
  (장송의 프리렌 → frieren, 스파이 패밀리 → spy-x-family…). Hasta correr
  `/watch-enrich-series-aliases`, muchos items quedarán en unmapped_series.

## 9. Pendientes

- **Aladin OpenAPI (TTB key gratuita)** como upgrade futuro: más estable que
  HTML, devuelve ISBN/portada en JSON. Evaluar si la fuente escala.
- Poblar aliases KO (queue en `data/unmapped_series.jsonl` tras la primera ingesta).

## 10. Runbook

```bash
.venv/bin/python scripts/manga_watch.py --only-source "KR - Aladin (만화 한정판)" --dry-run
```
