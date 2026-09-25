# Fuente: Ivrea Argentina (Editorial Ivrea Argentina)

> ⚠️ **PODA 2026-06-12 (poda de fuentes muertas)** — `AR - Ivreality`: Ivreality (el blog de noticias) se deshabilitó por 0 items netos históricos; la fuente de catálogo AR - Ivrea Argentina SIGUE activa.
> Registro completo: [descartadas/README.md](descartadas/README.md).

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

Cubre las **dos** entradas de `sources.yml` para la editorial Ivrea Argentina:
la web de la editorial (`ivrea.com.ar`) y su portal de novedades (`ivreality.com.ar`).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | `AR - Ivrea Argentina` y `AR - Ivreality` |
| **URL base** | `https://www.ivrea.com.ar/` · `https://www.ivreality.com.ar/` |
| **Índice / punto de entrada** | La home de cada dominio (no hay sitemap declarado en el YAML) |
| **Tipo de fuente** | editorial (official) |
| **`kind` en sources.yml** | `html` (ambas) |
| **`source_class`** | `official` (ambas) |
| **País(es)** | Argentina (`Argentina`) — va al edition_key |
| **Idioma(s)** | ES |
| **Cobertura** | Catálogo y novedades de Editorial Ivrea Argentina (manga en español, edición argentina) |
| **Aporte al corpus** | 8 items (todos vía `ivrea.com.ar`); `ivreality.com.ar` aporta 0 hoy |
| **Parser / módulo** | Entradas en `sources.yml` (extractor genérico por selectores, sin módulo propio) |

Editoriales reales en el corpus (de §10): **Editorial Ivrea Argentina** (8/8).
País: Argentina (8/8). Recuerda: `publisher` = editorial real, NO la tienda (#44).

**Por qué importa / qué aporta de único**: cubre la edición **argentina** de Ivrea,
distinta de la edición española (`ES - Ivrea España Noticias`). País distinto =
edición distinta (#46), así que estos items nunca se mergean con los de Ivrea España.

---

## 2. Descripción técnica de la fuente

- **`ivrea.com.ar`** — web de la editorial armada con **WPBakery** (page builder de
  WordPress). Los productos se listan como columnas del grid; el `item_selector`
  apunta a esas columnas (`div.vc_col-sm-2.vc_column_container.wpb_column`). No se
  definen `title_selector`/`link_selector`, así que el extractor genérico cae a sus
  heurísticas por defecto dentro de cada card.
- **`ivreality.com.ar`** — portal de **noticias/novedades** con tema **Newspaper
  (tagDiv)**. Cada nota es un módulo `div.td_module_flex`; el título/enlace salen del
  `<h3 class="entry-title">` (o `.td-module-title`). Es un feed de posts de novedades,
  no un catálogo de producto con precio.
- **Identificador de producto**: URL de la card/post (sin SKU/ISBN expuesto en el listado).
- **Anti-bot / quirks**: ninguno documentado por ahora. `ivreality.com.ar` aporta 0
  items netos (ver §8).
- **Calidad de imágenes**: {{pendiente: no verificado}}.

---

## 5. Proceso de ingestión — técnico

Ambas entradas se scrapean en **Fase 1** del pipeline (scrape de sources del YAML vía
`manga_watch.py`), con el **extractor genérico por selectores** —
`extract_with_selectors()` en `scripts/manga_watch.py` (~línea 4503). **No hay parser
propio.**

Selectores (verbatim del YAML):

- **`AR - Ivrea Argentina`** (`ivrea.com.ar/`):
  - `item_selector: "div.vc_col-sm-2.vc_column_container.wpb_column"`
- **`AR - Ivreality`** (`ivreality.com.ar/`):
  - `item_selector: "div.td_module_flex"`
  - `title_selector: "h3.entry-title a, .td-module-title a"`
  - `link_selector: "h3.entry-title a, .td-module-title a"`

El extractor recorre cada card del `item_selector`, saca título/enlace (con los
selectores declarados o las heurísticas por defecto cuando faltan) y emite candidatos
que luego pasan por los filtros y el merge canónico (1 fila por producto, decisión #1).
Tras el scrape, los retrofits de cleanup corren igual que para el resto de fuentes del
YAML (rescore → filter_non_manga → filter_collectible → clean_titles → backfill_metadata).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **`ivreality.com.ar` aporta 0 items netos**: hoy el corpus no tiene ningún item de
  este dominio. Puede ser que sea un feed de noticias (no de producto) y que sus posts
  no pasen el filtro de "edición especial física", o que los selectores `td_module_flex`
  no estén matcheando el layout actual. {{pendiente: confirmar causa — feed de noticias
  filtrado vs. selectores stale}}.
- **`ivrea.com.ar` sí aporta** (8 items), todos `Editorial Ivrea Argentina` / Argentina.
- **Decisión**: no mergear cross-país con Ivrea España (#46) — la edición argentina es
  edición propia.

---

## 9. Pendientes / limitaciones conocidas

- `ivreality.com.ar` en 0 items: decidir si vale la pena mantenerlo enabled o ajustar
  selectores / filtros. {{pendiente}}.
- Aporte real chico (8 items) vía `ivrea.com.ar`. {{pendiente: si se espera más cobertura,
  revisar paginación/índice — el YAML sólo declara la home como punto de entrada}}.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo estas fuentes (ajustar al caso):
.venv/bin/python scripts/manga_watch.py --only-source "AR - Ivrea Argentina"
.venv/bin/python scripts/manga_watch.py --only-source "AR - Ivreality"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de ambos dominios en el corpus (para §1):
.venv/bin/python - <<'PY'
import json
from collections import Counter
for NEEDLE in ["ivrea.com.ar", "ivreality"]:
    def hit(it):
        blobs=[it.get('url','') or '']+[ (s.get('url','') or '') for s in it.get('sources',[]) ]
        return any(NEEDLE in b for b in blobs)
    items=[json.loads(l) for l in open("data/items.jsonl") if l.strip()]
    sel=[it for it in items if hit(it)]
    print("== NEEDLE", NEEDLE, "==")
    print("items:", len(sel))
    print("países:", Counter((it.get('country') or '') for it in sel if it.get('country')))
    print("editoriales:", Counter((it.get('publisher') or '') for it in sel if it.get('publisher')).most_common(20))
PY
```

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0 duras)
→ tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza
esta ficha.

## 2026-09-07 — La URL del producto es un JPG: 19 de 20 enlaces de la fuente no llevan a ninguna página

**Hallazgo nuevo, verificado en vivo. Es la ÚNICA fuente del corpus con este problema.**

### Síntoma

Los 5 items que esta fuente aportó al delta de hoy (Baki Kanzenban 16, Dragon Ball
Kanzenban 1/7/8, Inuyasha 22) tienen como URL de producto un archivo de imagen:

```
https://www.ivrea.com.ar/wp-content/uploads/2026/06/inuyasha22.jpg
```

### Alcance medido sobre el corpus

| Métrica | Valor |
|---|---|
| Entradas de `sources[]` que apuntan a `ivrea.com.ar` | 20 |
| De esas, que apuntan a un archivo de imagen | **19 (95 %)** |
| Entradas-imagen en TODO el resto del corpus (las otras ~56 fuentes) | **0** |

O sea: el problema está **aislado en esta fuente**, y dentro de ella es prácticamente
total. Ejemplos: `DNAngel09.jpg`, `dandadan22.jpg`, `grandblue10.jpg`,
`bakithegrappler14.jpg`.

### Causa raíz (verificada en vivo)

La home de `ivrea.com.ar` publica las novedades como miniaturas envueltas en un enlace a la
imagen a tamaño completo (patrón lightbox de WordPress):

```html
<a href="https://www.ivrea.com.ar/wp-content/uploads/2026/08/dbkanzen07.jpg"> <img …> </a>
```

El seguidor de enlaces genérico toma ese `href` como la URL del producto. No es un fallo de
la fuente: es la plantilla del sitio enlazando su propio JPG.

**La página real existe y responde**: el sitio tiene fichas por serie bajo `/titulo/<slug>/`
—verificado en vivo, `HTTP 200`, `<h1>` con el nombre de la serie— y la home ya las enlaza
(13 anclas `/titulo/` en el mismo documento):

```
https://www.ivrea.com.ar/titulo/dragon-ball/          → 200, h1 "Dragon Ball"
https://www.ivrea.com.ar/titulo/inuyasha/
https://www.ivrea.com.ar/titulo/baki-the-grappler-edicion-kanzenban/
```

Son fichas **por serie**, no por tomo, así que no dan el volumen exacto — pero es un
destino navegable, que es exactamente lo que hoy falta.

### Impacto

- **19 items del catálogo tienen un enlace que no lleva a ninguna parte útil**: al hacer
  clic, el owner ve un JPG suelto en vez de la ficha del producto. Para un tracker cuyo
  objetivo es el descubrimiento, es el enlace lo que da valor al hallazgo.
- Ninguna de las páginas reales se está fetcheando, así que la fuente tampoco puede aportar
  ISBN, precio ni fecha de salida (los 5 items de hoy entraron con `release_date` vacía).
- Efecto colateral en la calidad del dato: sin ficha que leer, la derivación se apoya sólo
  en el nombre del archivo/el texto suelto. Se ve hoy en `INUYASHA #22`, que quedó con
  `edition_display = "Artbook (Editorial Ivrea Argentina)"` cuando su propia descripción
  dice "Con sobrecubierta y páginas a color, formato B6, 400 págs." — un tomo regular en
  edición con sobrecubierta, no un artbook.

### Recomendación (NO aplicada — decisión del owner)

1. **Preferir el ancla `/titulo/` sobre el ancla a imagen** al resolver la URL del item en
   esta fuente. Barato y verificado: ambos enlaces conviven en el mismo bloque de la home.
   Complemento defensivo y general: un enlace cuyo `href` termina en una extensión de
   imagen nunca debería quedar como URL de producto — hoy los 19 casos del corpus son todos
   de esta fuente, así que la regla no tiene costo en ninguna otra.
2. **Después** de (1), re-fetchear los 19 items para recuperar ficha real (y de paso
   corregir la edición mal derivada de `INUYASHA #22`).

Cambiar selectores/config de la fuente es decisión del owner.

### 2026-09-07 (mismo día) — RESUELTO

**Aplicado**, fix de mecanismo + reparación:

1. `_product_anchor()` (nuevo, en `manga_watch.py`) elige el primer `<a>` de la
   card cuyo `href` NO sea un archivo de imagen. Es una regla general y segura
   —una URL de producto nunca es un JPG— y si todas las anclas fueran imágenes se
   conserva la primera para no perder el item.
2. `scripts/retrofit/fix_ivrea_image_urls_20260907.py` repuntó las **19** entradas
   ya ingresadas a su ficha `/titulo/<slug>/`. El slug NO se inventa: se resuelve
   contra el índice real del catálogo del sitio (517 slugs leídos de
   `/catalogo/`, `/shonen/`, `/seinen/`, `/shojo/`) y **cada URL se verifica con
   una petición en vivo antes de escribirla**.

19/19 resueltas. Hizo falta un detalle: WordPress se come los apóstrofes al
generar el slug (`JoJo's Bizarre Adventure` → `jojos-bizarre-adventure`), así que
el normalizador los elimina en vez de convertirlos en separador — sin eso, los 2
items de JoJolion quedaban sin resolver.

**Corrección sobre la primera versión de este retrofit**: reparaba sólo
`sources[].url`, pero el item lleva **además** una `url` de nivel superior (la
primaria — es la que leen las proyecciones de `standardize_audit.py` y varios
retrofits), que quedó apuntando al JPG en los 19. Se detectó porque las
proyecciones Tier 2 de la corrida siguiente seguían mostrando el `.jpg`. El
retrofit ahora repara los dos campos.

Verificación final: **0 en los DOS campos** — `url` primaria y `sources[].url` —
en todo el corpus (antes 19 y 19, todas de esta fuente). Idempotente — segunda
pasada: 0 cambios.

Colateral tratado: los 5 items de la fuente que habían quedado con
`edition_display = "Artbook"` siendo tomos regulares (Inuyasha #22, JoJolion
#17/#18, Bocchi the Rock! #8, Dai Dark #6) se marcaron para re-derivación.

#### Colateral cerrado: 4 `edition_key` decían `artbook` siendo tomos numerados

Consecuencia directa del bug de la URL: sin ficha que leer, la derivación etiquetó
como `artbook` a tomos regulares numerados (JoJolion #18, Bocchi the Rock! #8,
Dai Dark #6, Inuyasha #22). Es una **contradicción interna del propio item** —
`product_type = manga` + `volume` presente + `edition_key` terminado en
`-artbook-ar`—, y la regla del repo es explícita: un item con número de volumen
nunca es `artbook`.

El paso de estandarización no podía arreglarlo (preserva el `edition_key`
existente por regla dura), así que se hizo con
`scripts/retrofit/fix_ivrea_artbook_keys_20260907.py`, con guard: sólo toca lo que
es demostrablemente un tomo (`product_type == manga` **y** `volume` no vacío).

**Verificado en vivo** contra la ficha `/titulo/<slug>/` de cada uno: el único
término de formato que aparece es "sobrecubierta"; no hay kanzenban, deluxe, wide
ni artbook. Es la línea estándar de Ivrea (B6 con sobrecubierta, páginas a color,
~400 págs), que en el corpus ya se codifica como `-regular-ar` para esta misma
fuente.

**Matiz anotado, no resuelto**: la ficha de Inuyasha dice "ESTADO EN JAPÓN:
COMPLETA – 30 TOMOS", o sea que la obra base es la **Wide Edition** japonesa, no
el tankōbon de 56. Se codifica igual como `regular` porque es la única edición que
Ivrea publica y es el patrón establecido de la fuente. Si alguna vez conviven dos
líneas de la misma serie habrá que distinguirlas.
