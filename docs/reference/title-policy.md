# Política de títulos — cómo PandaWatch maneja los nombres

> Documento de referencia, cargado **bajo demanda** desde [CLAUDE.md](../../CLAUDE.md).
> **Léelo ANTES de tocar cualquier cosa que escriba, transforme, filtre o muestre
> el `title` de un item** (parser, skill standardize, retrofit de títulos, filtro
> non-manga, tarjeta o detalle de una UI). Es la fuente de verdad de toda la
> regla; los gotchas #92/#93 y architecture.md → "Política de títulos" apuntan acá.

Decisión del owner, 2026-06-12. Reemplaza el comportamiento viejo (el skill
`/watch-standardize-catalog` traducía/renombraba los títulos).

---

## 1. La regla (qué es el `title`)

**`title` = el nombre OFICIAL con que la editorial/fuente publica ESE producto.
Es un DATO, no una etiqueta editable.** Cuatro prohibiciones duras:

1. **NO se traduce.** "Guardianes de la Noche 8" (Norma) se queda así; un título
   japonés se queda en japonés ("鬼滅の刃 23 特装版").
2. **NO se renombra a la serie canónica.** "Guardianes de la Noche 8" NUNCA se
   convierte en "Demon Slayer 8".
3. **NO se le inyecta el tipo de edición.** No se le agrega "Kanzenban"/"Deluxe"/
   "Edición especial" salvo que ya sea parte del nombre oficial (ej. "Berserk
   Maximum", que Panini publica literalmente así).
4. **NO se le pega el bonus de UNA tienda.** El perk de compra de un retailer
   (店舗特典 japonés: "(…ポストカード)【楽天ブックス限定特典】") no es el nombre del
   producto → va al campo `store_bonus` (gotcha #93).

Lo único que SÍ se le hace al título: **limpieza cosmética** que no cambia idioma
ni nombre de la obra — quitar basura de e-commerce (`clean_title`), el marcador
"nº", reordenar "{serie} {vol} Edición Especial", desambiguar colisiones. Eso es
todo.

## 2. El porqué (para no revertirlo por error)

El owner detectó dos daños del renombre:

- **Confianza**: un usuario que conoce la obra ve un nombre inventado y piensa
  "¿por qué le cambiaron el nombre?" → pierde confianza en la app.
- **Búsqueda externa rota**: si el usuario quiere comprar ese tomo, busca en
  Google/la tienda el nombre que ve en PandaWatch; si se lo inventamos, no lo
  encuentra.

El nombre reconocible de la obra NO se pierde: vive en `series_display` (canónico,
lo que las UIs muestran ENCIMA del título) y la **búsqueda** lo resuelve vía
aliases. Desacoplar "cómo se llama" (title, dato oficial) de "cómo se encuentra"
(búsqueda + series_display) es el principio que sostiene toda la política.

## 3. Los campos (dónde vive cada cosa)

| Campo | Contenido | Quién lo escribe |
|---|---|---|
| `title` | Nombre OFICIAL, limpio, en su idioma. Lo que se muestra en el grid. | Scraper (`candidate_to_json` → `clean_title` + `split_store_bonus`). NUNCA el skill ni un renombrador. |
| `title_original` | Nombre oficial COMPLETO tal como vino de la fuente (incl. el store_bonus). Red de seguridad. | Scraper; preservado por todos los pasos. |
| `series_display` | Nombre canónico/reconocible de la OBRA ("Demon Slayer"). Se muestra encima del título. | Skill standardize + `canonical_series_key` (resuelve aliases). |
| `series_key` | Slug canónico kebab ("demon-slayer"). Une todas las ediciones de la obra. | Idem. |
| `edition_key` | `{serie}-{pub}-{tipo}-{país}`. El slug de TIPO se muestra como **badge** (no en el título). | Scraper + enforcer (determinístico). |
| `store_bonus` | Perk de compra de UN retailer (店舗特典), separado del título oficial. Se muestra solo en el DETALLE. | `mw.split_store_bonus` (scraper + retrofit `extract_store_bonus.py`). |

## 4. El mecanismo (cómo se garantiza, capa por capa)

1. **Scraper** (`candidate_to_json`): `title` = `clean_title(title_original)`, y
   `split_store_bonus` separa el 店舗特典 a `store_bonus`. El título NUNCA se
   re-escribe después.
2. **Skill `/watch-standardize-catalog`**: deriva serie/edición/volumen + detecta
   non-manga, pero **NO emite ningún campo de título**. El schema del workflow y
   `standardize_apply.py` ya no tienen `title_standardized` (campo RETIRADO). Ver
   [SKILL.md](../../.claude/skills/watch-standardize-catalog/SKILL.md).
3. **Enforcer** (`enforce_listadomanga_rules.py`): sólo normalizaciones cosméticas
   del nombre oficial (nº, orden Edición Especial, colisiones, palabra de edición
   duplicada). Nunca idioma ni nombre de obra.
4. **Búsqueda (ambas UIs)**: matchea `title` + `title_original` + `series_display`
   + **aliases del `series_key`** (`data/series_aliases.json`, exportado por
   `export_series_aliases.py` en cada `build_web`). Así "demon slayer", "kimetsu no
   yaiba" y "guardianes de la noche" devuelven lo mismo. Ver
   [dashboard.md](dashboard.md) y FRD-003.
5. **UIs**: el grid muestra `series_display` (arriba) + `title` (oficial) + **badge
   de tipo de edición** (`EditionTypeChip` / `editionTypeLabel`). El detalle muestra
   además `title_original` (si difiere) y `store_bonus` ("🎁 Bonus de tienda").

## 5. Migración y mantenimiento (estado actual + qué correr)

Migración one-shot ya ejecutada sobre todo el corpus (2026-06-12):

| Script | Qué hizo | Re-correr cuándo |
|---|---|---|
| `restore_official_titles.py` | `title` = nombre oficial (desde `title_original`); retiró `title_standardized`. Marca `title_restored_at`. | Sólo si se restauran items viejos de un backup. |
| `recover_lost_jp_titles.py` | Recuperó nombres oficiales de items JP cuyo `title_original` había sido pisado por corridas viejas del skill (openBD por ISBN + re-fetch Playwright de mangavariant). | Si reaparecen títulos "generados" JP. |
| `extract_store_bonus.py` | Separó el 店舗特典 a `store_bonus` (221 items). | Sólo si cambia el helper (el scraper ya lo aplica a items nuevos). |

**Para items NUEVOS no hay que correr nada**: el scraper ya aplica `clean_title` +
`split_store_bonus`, y el skill no toca el título. La política se auto-mantiene.

**Limitación conocida**: algunos `title_original` viejos fueron pisados por
retrofits históricos (`fix_listadomanga_titles.py` escribía title_original); esos
items conservan el mejor título disponible, no necesariamente el oficial exacto.
`recover_lost_jp_titles.py` cubrió el grueso del mercado JP.

## 6. Si vas a tocar títulos — checklist

- **¿Vas a renombrar/traducir un título "para que se vea mejor"?** → NO. Revisá si
  lo que querés es mejorar la BÚSQUEDA (aliases) o el `series_display`.
- **¿Un filtro non-manga rechaza un título oficial que nombra su bonus**
  ("…フィギュア付特装版", "…w/ DVD")**?** → es gotcha #92: el bonus es parte del nombre
  oficial; usá el tier `_NON_MANGA_HARD_UNLESS_BONUS` / marcador de inclusión, no
  borres el item.
- **¿Aparece basura de tienda en el título** ("【楽天…特典】", "Prezzo normale")**?** →
  si es 店舗特典 japonés, es gotcha #93 (`split_store_bonus`); si es otro junk,
  extendé `clean_title` (`TITLE_JUNK_*`).
- **¿Agregaste un retrofit que escribe `title`?** → que NUNCA traduzca ni renombre;
  reusá `clean_title`/`split_store_bonus`; respetá `approved_at`; re-derivá
  cluster_key y consolidá; probá idempotencia.

## Referencias

- [architecture.md](architecture.md) → "Política de títulos" (gist + decisión).
- [gotchas.md](gotchas.md) #92 (filtros vs bonus en nombre oficial), #93 (store_bonus).
- [SKILL.md](../../.claude/skills/watch-standardize-catalog/SKILL.md) (el skill no toca title).
- [dashboard.md](dashboard.md) (búsqueda con aliases + badge de edición).
- [PIPELINE-WALKTHROUGH.md](../scraper/PIPELINE-WALKTHROUGH.md) (ETAPA 2 + build).
