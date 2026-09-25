# Fuente(s): Editoriales alemanas directas (altraverse · Egmont · TOKYOPOP · Carlsen)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-08-24 (causa real del 429 de Carlsen: ban de IP del host
> completo, no rate-limit — hipótesis original refutada; gotcha #150).

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
| DE - TOKYOPOP (search limited) | `tokyopop.de/search?search=limited` | ~66 | ídem | **DEGRADADA a fallback 2026-07-07** — 77.5% overlap por cluster con Manga-Passion; se mantiene por el 23% único (ver §9) |
| DE - Carlsen Manga Novedades | `carlsen.de/manga/monatsuebersicht` | ~15-20/mes (~1-2 especiales) | `a.pondus-product__link` + `.field--name-title` | **DESHABILITADA 2026-08-24** (ban de IP del host, § 8) — delta mensual mixto: el gate filtra los regulares; ISBN viene en la URL del producto |

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

## 8. Problemas encontrados — qué funcionó y qué NO

- **Carlsen 429 en el delta 2026-08-22** (`logs/scrape-delta-2026-08-22-174458/`):
  `carlsen.de/manga/monatsuebersicht` devolvió `429 Too Many Requests` durante el
  diagnóstico. Verificado con curl (mismo user-agent del scraper) minutos después:
  seguía en 429. Se esperó >120s y se reintentó una vez: **persiste el 429**. No se
  insistió más (regla del runbook: un solo reintento tras esperar).
  ~~Hipótesis original: rate-limit real del lado de Carlsen, probablemente por el
  resto de fuentes DE (altraverse/Egmont/TOKYOPOP) o el propio diagnóstico pegándole
  seguido a `carlsen.de` en la misma ventana; se esperaba que un `sleep-seconds` más
  alto o correrlo aparte del resto de fuentes DE lo despejara.~~ **REFUTADA
  2026-08-24** — ver causa real abajo (post "Carlsen 429 SE REPITIÓ").

## 9. Pendientes

- Si los items duplican a Manga-Passion sin fusionarse (el wiki no tiene ISBN →
  el match cae a fuzzy por título DE), vigilar duplicados en validate_corpus y
  considerar un merge asistido por título normalizado alemán.
- **DE - TOKYOPOP (search limited): degradada a `tags: [..., "fallback"]` en
  `sources.yml` (2026-07-07)**, tras medir en la auditoría de ingestión que el
  77.5% de sus items solapan por `cluster_key` con Manga-Passion (que ya cubre
  esas 84 LEs TOKYOPOP). Se mantiene habilitada (no se poda) por el **23% único**
  que sigue aportando, pero pasa a prioridad de fallback frente a Manga-Passion.
  **Candidata a poda** si una futura auditoría mide que el overlap sigue subiendo
  (más cerca del 100%, es decir, cero aporte neto).

## 10. Runbook

```bash
for s in "DE - altraverse Collectors Edition" "DE - altraverse Manga mit Box" \
         "DE - Egmont Luxusausgaben" "DE - TOKYOPOP Jubiläumseditionen" \
         "DE - TOKYOPOP (search limited)" "DE - Carlsen Manga Novedades"; do
  .venv/bin/python scripts/manga_watch.py --only-source "$s" --dry-run
done
```

- **Carlsen 429 SE REPITIÓ en el delta 2026-08-24** (`logs/scrape-delta-2026-08-24-183301/`):
  mismo `429 Too Many Requests` sobre `carlsen.de/manga/monatsuebersicht`, 0 candidatas.
  Es la **segunda corrida consecutiva** con el mismo síntoma (la anterior fue el
  2026-08-22).

  **CAUSA REAL (diagnosticada 2026-08-24, gotcha #150)**: NO es rate-limit por
  volumen de pedidos — es un **ban de IP a nivel de host completo**. Evidencia:
  - `carlsen.de/` (home) y `carlsen.de/robots.txt` devuelven **429 igual que
    `/manga/monatsuebersicht`**, con curl directo, fuera del scraper y con
    User-Agents distintos entre sí (Chrome UA y `curl/8.0`). Un rate-limit por
    endpoint/UA no explica que el `robots.txt` — que no cuenta contra ninguna
    cuota real de ningún sitio — también caiga.
  - Ninguna respuesta trae header `Retry-After` (verificado con `curl -D -`):
    un 429 de rate-limit "cortés" casi siempre lo incluye; su ausencia total,
    en cualquier endpoint, es consistente con un bloqueo perimetral (WAF/CDN)
    por IP de origen, no con una cola de rate-limiting de la app.
  - `--sleep-seconds` es **no-op** cuando `--workers` > 1 (el throttling
    secuencial no aplica en modo concurrente) — así que la hipótesis original
    de "bajar la velocidad de pedidos" no tenía forma de surtir efecto aunque
    fuera la causa correcta.

  **Test diagnóstico reusable** para distinguir rate-limit real de ban de IP en
  cualquier fuente que devuelva 429 de forma persistente:
  ```bash
  curl -s -o /dev/null -D - -A "<UA real del scraper>" "https://<host>/" | grep -i "^http/\|retry-after"
  curl -s -o /dev/null -D - -A "curl/8.0" "https://<host>/robots.txt" | grep -i "^http/\|retry-after"
  ```
  Si **ambos** devuelven 429 (home Y robots.txt, con UAs distintos, sin
  `Retry-After`) → es ban de IP del host entero, NO lo arregla bajar la
  velocidad ni cambiar `sleep-seconds`/UA/headers del scraper. La única
  mitigación real es esperar (el ban suele ser temporal) o rotar de IP/salida
  de red — ninguna de las dos es un cambio de código en este repo.

  **DECISIÓN DEL OWNER (2026-08-24): deshabilitada TEMPORALMENTE.**
  `enabled: false` en `sources.yml` (mismo formato que MangaLine ES/MX) —
  motivo: ban de IP del host + la cobertura DE de ediciones especiales ya la
  aporta Manga-Passion Sonderausgaben (wiki) + altraverse/Egmont/TOKYOPOP, así
  que no hay urgencia de forzar el desbloqueo. Registrada en la watchlist de
  `docs/scraper/sources/descartadas/README.md` § 3. **Condición de
  reactivación**: `curl -sI https://www.carlsen.de/robots.txt` deja de
  devolver 429 (chequeo simple, sin necesidad de credenciales ni proxy).

### Auditoría full — 2026-09-24

Se reconocen `Band 08` y rangos `Band 01-05` como identidades `8` y `1-5`.
El rango evita colapsar cajas de tramos diferentes. altraverse Collectors Edition
recorrió 84 páginas y produjo 143 candidatos antes de los filtros finales.
