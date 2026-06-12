# Fuente(s): Editoriales alemanas directas (altraverse · Egmont · TOKYOPOP · Carlsen)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-12 (alta de las 6 fuentes).

Ficha agrupada: las 4 editoriales comparten el mismo racional y proceso. Antes de
2026-06-12 TODO el corpus alemán (~856 items) venía de un único wiki comunitario
(Manga-Passion Sonderausgaben). Estas fuentes first-party agregan: **ISBN** (0/162
items altraverse tenían ISBN), fecha exacta, fotos de extras, señal de stock y
resiliencia si el wiki muere. Evaluadas con /watch-evaluate-sources (0% overlap
de ISBN — el wiki no los tiene).

---

## 1. Las 6 entradas

| Entrada | URL | Items | Selectores | Nota |
|---|---|---|---|---|
| DE - altraverse Collectors Edition | `altraverse.de/manga/?f=135` | ~70 | genéricos (clusters) | Shopware 5, filtro de categoría puro |
| DE - altraverse Manga mit Box | `altraverse.de/manga/?f=64` | ~13 | genéricos | GACHIAKUTA Schuber, FMA Metal Box |
| DE - Egmont Luxusausgaben | `egmont-shop.de/manga/luxusausgaben/` | ~12 | `li.o-grid__cell` + `a.c-product-card` | línea Luxury (HC kanzenban) — 0% overlap con Manga-Passion (que solo cubre la línea Limited de Egmont) |
| DE - TOKYOPOP Jubiläumseditionen | `tokyopop.de/buecher/jubilaeumseditionen/` | ~11 | `div.product-box` + `.product-name` | HC aniversario "streng limitiert" |
| DE - TOKYOPOP (search limited) | `tokyopop.de/search?search=limited` | ~66 | ídem | overlap alto con Manga-Passion (84 LEs TOKYOPOP ya en corpus) — valor = enriquecimiento |
| DE - Carlsen Manga Novedades | `carlsen.de/manga/monatsuebersicht` | ~15-20/mes (~1-2 especiales) | `a.pondus-product__link` + `.field--name-title` | delta mensual mixto: el gate filtra los regulares; ISBN viene en la URL del producto |

Todas `country: Alemania`, `source_class: official`, `purity: manga_only` (default),
`publisher` = la editorial real.

---

## 2. Quirks técnicos

- **Egmont manda >100 headers HTTP** (decenas de Set-Cookie) → `http.client`
  abortaba con "got more than 100 headers". Fix global 2026-06-12 en
  manga_watch.py: `http.client._MAXHEADERS = 200`.
- **Señales en alemán** (alta 2026-06-12 en `KEYWORD_RULES`): limitierte Auflage /
  streng limitiert / limitiert (limited), Sammelschuber / Schuber / Sammelbox /
  mit Box (box_set), Luxusausgabe / Luxury Edition (premium_format),
  Jubiläumsedition (collector), Erstauflage (bonus).
- **Carlsen**: el ISBN viene en la URL del producto (`/{formato}/{slug}/{isbn}`)
  SALVO legacy items con ID numérico interno. Como catálogo completo NO es viable
  (>90% tomos regulares); solo el listado mensual.
- **NO usar** `altraverse.de/manga/?f=491` (Leerschuber = estuches VACÍOS sin
  tomos, merchandise).
- **Kazé/Crunchyroll Manga DE**: en watchlist — HarperCollins relanza la marca
  Kazé en abril 2026; hoy no hay catálogo de consumidor scrapeable.
- **Panini DE**: técnicamente viable (Magento) pero con waiting-room Queue-it
  (necesita cookie jar persistente) — diferida.

## 5. Proceso de ingestión

- FASE 1 (fuentes YAML estándar). Dry-runs de alta: altraverse 25+12, Egmont 12,
  TOKYOPOP 11+40, Carlsen 15→2 tras gate (regulares filtrados — correcto).

## 9. Pendientes

- Si los items duplican a Manga-Passion sin fusionarse (el wiki no tiene ISBN →
  el match cae a fuzzy por título DE), vigilar duplicados en validate_corpus y
  considerar un merge asistido por título normalizado alemán.

## 10. Runbook

```bash
for s in "DE - altraverse Collectors Edition" "DE - altraverse Manga mit Box" \
         "DE - Egmont Luxusausgaben" "DE - TOKYOPOP Jubiläumseditionen" \
         "DE - TOKYOPOP (search limited)" "DE - Carlsen Manga Novedades"; do
  .venv/bin/python scripts/manga_watch.py --only-source "$s" --dry-run
done
```
