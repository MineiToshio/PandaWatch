# Reglas de prompt — /watch-standardize-catalog (fuente única)

> **FUENTE ÚNICA** de las reglas de negocio que el LLM debe aplicar al asignar
> `series_key` / `edition_key` / `edition_display` / `volume` / `is_manga` en
> el skill `/watch-standardize-catalog`. Tanto `SKILL.md` (camino manual,
> < 30 items) como el workflow `.claude/workflows/watch-standardize-catalog.js`
> (camino preferido, ≥ 15/30 items) **leen ESTE archivo antes de procesar
> cualquier item** — no copiar su contenido en ninguno de los dos.
>
> Auditoría 2026-07-08 (hallazgo F7): la regla 画集付き vivía SOLO en
> `SKILL.md` (6 menciones) y 0 veces en el workflow — drift confirmado que
> hacía que el camino "preferido" (workflow) tuviera peor calidad que el
> manual para justo ese caso. Con este archivo como fuente única, un cambio
> acá aplica automáticamente a los dos caminos — no hay nada más que
> sincronizar.

## Política de títulos (dura, 2026-06-12, gotcha #92)

El `title` de cada item es el nombre OFICIAL con que la fuente/editorial
publica el producto. NUNCA se traduce, NUNCA se renombra a la serie
canónica, NUNCA se le inyecta el tipo de edición. No emitas ningún campo de
título — el nombre reconocible va en `series_display` (canónico) y la
búsqueda resuelve aliases multilingües (`series_aliases.yml`).

## is_manga

- `Global - Mangavariant` (cualquier item con `source`/`sources` conteniendo
  "mangavariant") → SIEMPRE `true`. Nunca `false`.
- Slipcases / box sets / coffrets / cofanetti / steelbox / portadas
  variante / artbooks / fanbooks / magazines → manga válido.
- Marvel/DC/IDW/Image comics → `false`, salvo que "manga" esté en el título
  o sea una adaptación conocida.
- Figuras/estatuas/peluches/remeras/tazas/trading cards/posts de noticias →
  `false`.
- Light novels (roman/light-novel/URLs LN) → `false`
  (`non_manga_reason="light_novel"`).
- **Ante la duda → `true`.**

## series_key

Minúscula, kebab-case, sin diacríticos. Tope ~35 caracteres. Usá el nombre
globalmente reconocido (inglés preferido, romaji JP si es canónico). Solo
ASCII (`[a-z0-9-]`) — nunca CJK crudo ni homoglifos cirílicos/griegos
copiados de la fuente (gotcha #81); transliterá a romaji. El pipeline
re-sanitiza con `sanitize_key_ascii()` de todas formas.

## edition_key — `{series}-{publisher_slug}-{edition_slug}-{country_slug}`

**NO RE-DERIVES la edición si el item YA tiene `edition_key` asignado**
(llega como `existing_edition_key` en el input). El scraper ya aplicó las
reglas duras de agrupación (coleccion=edición, país, nombre oficial) — está
bien. Para esos items tu trabajo es SOLO: serie canónica + detectar
non-manga. El apply del skill conserva `edition_key`/`edition_display`
existentes (y el `title` SIEMPRE). Derivá la edición desde cero SOLO para
items SIN `edition_key` (p.ej. fuentes que no son listadomanga). Las reglas
de abajo aplican a esos casos.

**REUSO DE KEYS EXISTENTES (gotcha #69)**: si el item trae
`known_edition_keys` (edition_keys YA existentes en el corpus para esa
serie) y una matchea el publisher+tipo+país de este item, USÁ ESA KEY
EXACTA. NUNCA acuñes una key nueva que difiera de una existente solo en el
slug de tipo (special/limited/collector/deluxe) — eso parte la misma
edición en dos páginas.

**TABLA DE TÉRMINOS DE TIPO (DURA, gotcha #69)** — el término del título
manda y se mapea SIEMPRE igual (un post-paso determinístico,
`canonicalize_edition_slugs.py`, re-aplica esta tabla; no la contradigas):
- 限定版 → `limited` · 特装版 / 同梱版 → `special` · 愛蔵版 → `deluxe` ·
  完全版 → `kanzenban`
- "edición limitada" / "edizione limitata" / "édition limitée" /
  "limited edition" → `limited`
- "coleccionista" / "collector" → `collector` · "edición de lujo" /
  "deluxe" → `deluxe`
- Ediciones NOMBRADAS (Maximum, Perfect, Ultimate, Master, Grimorio…) ganan
  sobre el término de tipo: "One Piece Maximum 限定版" → `maximum`.
- **GUARD de nombre de serie**: si la palabra "de edición" es parte del
  NOMBRE de la serie ("Trigun Maximum", "Ultimate Muscle"), NO es tipo de
  edición — usá la evidencia real de edición (o `regular`) para el slug. El
  título no se toca ("Trigun Maximum Maximum 2" es incorrecto → "Trigun
  Maximum 2").
- Ediciones regulares: el título NO lleva palabra de edición ("Noragami 27",
  nunca "Noragami Regular 27").

**REGLA DE NEGOCIO DURA (gotcha #46): país distinto = edición distinta,
SIEMPRE.** El `edition_key` TERMINA con el código de país de la EDICIÓN
(derivado de editorial/idioma del item, NO de la tienda). Dos mercados
NUNCA comparten `edition_key` aunque coincidan series+publisher+edición
(Panini IT vs Panini ES/MX/BR, Kazé FR vs DE, etc.).
`country_slug` (allowlist): "jp", "it", "es", "fr", "de", "us", "vn", "mx",
"br", "th", "ar", "tw", "gb", "pt", "pe", "cl", "kr", "eslatam". Desconocido
→ "xx".
Ejemplo: Hunter x Hunter variante Panini España =
`hunter-x-hunter-panini-variant-es`; la de Panini Italia =
`hunter-x-hunter-panini-variant-it` (NUNCA la misma).
NOTA: como el país ya va en el sufijo, NO uses slugs de publisher con país
embebido (usá "panini", NO "panini-es"; "ivrea", NO "ivrea-ar" salvo que
sean editoriales legalmente distintas).

`publisher_slug` (allowlist — usá el slug literal de esta lista):
"darkhorse", "glenat", "viz", "panini", "norma", "planeta", "ivrea", "ivrea-ar",
"kana", "pika", "kaze", "kioon", "star", "kodansha", "kodansha-us", "shueisha",
"squareenix", "kadokawa", "meian", "ecc", "arechi", "delcourt", "tokyopop", "jbc",
"devir", "newpop", "kamite", "mangaline", "mangadreams", "funside", "milkyway",
"dokidoki", "nobinobi", "tomodomo", "fandogamia", "kurokawa", "akita", "hakusensha",
"ichijinsha", "futabasha", "takeshobo", "tokuma", "asciimw", "frontier", "yenpress",
"carlsen", "noeve", "distrito", "001edizioni", "goen", "gpmanga", "jpop", "dynit",
"edizionibd", "magicpress", "coconino", "tora", "dokusho", "tokyomangasha", "kbooks",
"luckpim", "ipm", "isan", "nxb", "mpeg", "sevenseas", "titan", "inklore", "vertical",
"udon", "shogakukan", "gentosha", "maggarden", "egmont", "dokico", "papertoons",
"crosscult", "mangacult", "loewe", "reprodukt", "altraverse", "universe",
"pipoca-nanquim", "kim-dong", "panini-mx", "panini-es", "panini-ar", "panini-br",
"crunchyroll", "rakuten".

`edition_slug` (elegí UNO — NUNCA compuesto):
"deluxe", "kanzenban", "perfect", "coffret", "boxset", "cofanetto", "variant",
"limited", "collector", "anniversary", "celebration", "color", "maximum", "ultimate",
"master", "library", "integral", "artbook", "fanbook", "guidebook", "magazine",
"steelbox", "slipcase", "prestige", "grimorio", "grimoire", "special", "regular".

**REGLA ANTI-COMPUESTO**: elegí UN slug. Nunca "deluxe-box",
"ultimate-variant". Si el slug de formato (boxset/hardcover/coffret) choca
con el nombre de edición (collector/ultimate/limited), elegí el nombre de
edición.

**ARTBOOK vs SPECIAL**: si el item tiene número de volumen → `special`/
`limited` (nunca `artbook`). Solo libros de ilustraciones AUTÓNOMOS sin
volumen → `artbook`. EXCEPCIÓN: si la COLECCIÓN ENTERA es un libro de
ilustraciones (su título dice "Libro de Ilustraciones" / "Illustrations" /
"Art Works" / "The Art of" / 画集), entonces TODOS sus tomos son `artbook`
aunque estén numerados (es una serie de artbooks, no tomos especiales). Ej.
FMA cole=524 "Libro de Ilustraciones 1/2".

**CRITICAL — "画集付き" / "イラスト集付き" = artbook INCLUIDO COMO BONUS, no
es el producto.** Un título japonés como "宇宙兄弟(39) 画集付き特装版" /
"暁のヨナ イラスト集付き特装版 47" es un TOMO regular (notá el número) que
viene CON un mini-libro de arte de regalo. NO es un artbook. Regla:
- 画集/イラスト集/アートワーク seguido inmediatamente de 付き/付/つき/同梱
  (= "con/incluido") → el artbook es un BONUS → edición = `special`
  (特装版/同梱版) o `limited` (限定版), `product_type` = `manga`.
  Ej. "宇宙兄弟(39) 画集付き特装版" → `edition_key`
  `space-brothers-kodansha-special` (el `title` queda tal cual, en
  japonés).
- 画集/イラスト集 como producto autónomo, SIN 付き (ej. "笠井あゆみ画集
  麗人") → `artbook` real. Misma lógica para "ファンブック付き" (fanbook
  bonus) vs un "Visual Fanbook" autónomo.

**listadomanga — REGLA DURA: cada `/coleccion?id=N` es UNA edición = UNA
página.** La MISMA obra en `/coleccion` distintos = ediciones DISTINTAS →
NUNCA el mismo `edition_key`. Y al revés (gotcha #48): TODOS los tomos de
una MISMA `/coleccion` (regulares, especiales, cofres, variantes) comparten
el MISMO `edition_key` — el de la edición BASE de la coleccion (la
`regular` si existe; si no, la predominante, ej. Berserk Maximum). NO
separes el tomo 34 "Edición Especial" en `…-special` aparte de los
regulares de su coleccion: va en la misma página, con el mismo
`edition_key`. Lo que distingue al especial-34 del regular-34 es el
`cluster_key` (tier-0 `lmc:{coleccion}:{kind}:{vol}`), NO el `edition_key`.
Los tomos REGULARES con cofre/extras de 1ª edición (description con
"regalos / brindes" o tag `from_extras`) son edición `regular`, el cofre es
un bonus.

**`edition_display` = NOMBRE OFICIAL de la edición, SIN traducir
(gotcha #49).** NO un slug genérico traducido ("Special (Norma Editorial)",
"Regular"). Nada se traduce: ni el nombre de la EDICIÓN ni el `title` del
tomo. Para items de listadomanga, el item YA trae el `edition_display`
correcto (= título de la coleccion, ej. "Ataque a los Titanes", "Guardianes
de la Noche (Kimetsu no Yaiba)", "Berserk (Maximum) (Castellano)"):
**CONSERVALO, no lo regeneres ni lo traduzcas.** Para otras fuentes, usá el
nombre oficial de la edición (no inventes un slug traducido).

## volume

String. Solo dígitos. "1", "100", "1-3" para sets, "" si no hay.

## Reglas específicas por tier

**Tier 2** (el item trae `proposed_*`): validá la propuesta heurística contra
las reglas de arriba. Si la propuesta es correcta, copiá los `proposed_*`
**verbatim** a los campos de salida (`proposed_series_key` → `series_key`,
`proposed_edition_key` → `edition_key`, `proposed_volume` → `volume`, etc.).
Si algo está mal, corregí ese campo con las mismas reglas. **No existe ningún
campo `accept_proposal`** — el contrato de salida son solo los 8 campos de la
sección OUTPUT FIELDS; para aceptar una propuesta simplemente copiás sus
valores. En particular, si el volumen propuesto es correcto, emití ese número
en `volume` (nunca lo dejes vacío esperando que "se acepte" implícitamente).

**Tier 3** (sin heurística confiable): derivá todo desde cero con las
reglas de arriba. Misma serie/publisher → mismas keys consistentemente
entre items del batch.

## Ejecución

Procesá TODOS los items del batch. La cantidad de líneas de salida DEBE
igualar la cantidad de líneas de entrada.
