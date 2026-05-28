# PRD — Scraper de Ediciones Especiales (PandaWatch)

> Catálogo histórico y continuo de ediciones especiales de manga: ediciones limitadas,
> deluxe, box sets, variant covers, artbooks, kanzenban y extras de primera edición.
> Scraping de ~76 fuentes activas en 10 países y 6 idiomas.

---

## Estado del proyecto

| Fase | Estado | Descripción |
|---|---|---|
| Fase 1 — Búsquedas dirigidas multi-keyword | ✅ Completo | `search_template + keywords` en sources.yml; N fuentes virtuales por editorial |
| Fase 2 — Wikis comunitarias | ✅ Completo | 17 wikis implementados (ver lista abajo) |
| Fase 3 — Sitemap mining | ✅ Completo | Mangavariant (~2700 entries), listadomanga lista.php (~3432 colecciones) |
| Fase 4 — LLM enrichment | ✅ Completo | Skills `/standardize-catalog` + `/enrich-series-aliases` |

---

## Corpus actual

| Métrica | Valor |
|---|---|
| Items totales | **10.103** |
| Fuentes habilitadas | **76 / 138** (45 deshabilitadas: cero yield o duplicadas por wikis) |
| Wikis disponibles | **17** |
| Países representados | **13** (JP, IT, FR, ES, DE, US, VN, MX, BR, TH, AR, TW, LatAm) |
| Top países | Japón 3.758, Italia 2.182, Francia 1.295, España 1.279, Alemania 841 |
| Cobertura ISBN | ~48% |
| Cobertura precio | ~51% |
| Cobertura imagen local | ~99.8% |
| `series_aliases.yml` | 2.844 canonicals |
| `standardized_at` | ~99.6% |

---

## Objetivo del producto

Mantener un **dataset histórico continuo** de ediciones especiales de manga a nivel global,
con calidad suficiente para ser consultadas, filtradas y curadas desde el dashboard.

**No es** una tienda ni un tracker de precios. Es un catálogo de *qué existe en el mundo*,
independientemente de si está disponible hoy para comprar. Las URLs de referencia
(wikis, bases comunitarias) son tan válidas como las de retailers.

---

## Fuentes y wikis activos

### Wikis (17)
| Wiki | Mercado | Qué cubre |
|---|---|---|
| listadomanga | ES | Calendario mensual de novedades |
| listadomanga-collections | ES | ~3432 colecciones vía `lista.php` (Fases 1+2+3) |
| listadomanga-blog | ES | Archivo histórico WordPress 2009-actual (manual) |
| manga-sanctuary | FR | Catálogo histórico FR |
| otaku-calendar | EN | Releases mensuales EN |
| manga-mexico | MX | Catálogo alfabético por editorial |
| mangavariant | Global | Base curada de ~2700 variantes en 13 países |
| socialanime | IT | MangaStore IT: variants (466) + cofanetti (440) |
| blogbbm | BR | Guías curadas de capas variantes + volumes especiais + box sets |
| booksprivilege | JP | 店舗特典 (extras por tienda: Animate, Gamers, Toranoana…) |
| sumikko | JP | 限定版/特装版 curadas (~3178 entries) |
| listadomanga-collections | ES | Parser por colección `coleccion.php?id=N` |
| mangapassion | DE | API REST: Sonderausgaben + Variant-Covers |
| animeclick | IT | Calendario semanal edizioni speciali |
| prhcomics | US/CA | Hardcovers + box sets EN (PRH) |
| kinokuniya | US | Exclusivos Kinokuniya USA |
| yenpress | US | Calendario mensual Yen Press collector's + deluxe |
| whakoom | ES/LatAm | Spider 3-nivel (opt-in, Cloudflare-throttled) |

### Fuentes directas
76 fuentes habilitadas en `sources.yml` cubriendo retailers oficiales, tiendas,
y bases de datos comunitarias. Ver `docs/scraper/SOURCES.md` para la guía completa.

---

## Pipeline de scraping

```
scrape_delta.sh   (diario/semanal, ~30-60 min)
  → listadomanga calendario (últimos 3 meses)
  → resto de fuentes y wikis

scrape_full.sh    (mensual/trimestral, ~2-4 horas)
  → listadomanga lista.php (~3432 colecciones)
  → mangavariant sitemap completo
  → wikis históricos completos
```

Ambos terminan con cleanup retrofits:
`rescore → filter_non_manga → filter_collectible → clean_titles → backfill_metadata`

Ver `docs/scraper/ARCHITECTURE.md` para el detalle técnico completo del pipeline.

---

## Calidad de datos

### Filtros activos (en orden de aplicación)
1. **`is_likely_manga()`** — 4 reglas en cascada: figuras/merch → manga fuerte → manga con extras → soft non-manga
2. **`is_pure_novel()`** — Rechaza light novels puras (URL hints + palabras indicadoras)
3. **`is_comic_not_manga()`** — Blacklist Marvel/DC/franquicias occidentales (bypass si title contiene "manga")
4. **`is_collectible_edition()`** — Segundo gate: solo pasan ediciones especiales, no tomos regulares

### Estandarización (doble pasada)
- **Pasada 1 (scraper)**: heurístico rápido asigna `series_key/edition_key/volume` rough
- **Pasada 2 (skill `/standardize-catalog`)**: LLM verifica y corrige, marca `standardized_at`

### Aliases multilingüe
`data/series_aliases.yml` colapsa variantes de nombre por idioma/mercado
(Demon Slayer = Kimetsu no Yaiba = Guardianes de la Noche = 鬼滅の刃).
Mantenido vía skill `/enrich-series-aliases`.

---

## Roadmap futuro

| Item | Estado | Prioridad |
|---|---|---|
| **Migrate a SQLite** | Pendiente — trigger: deploy multi-usuario | Media |
| **Image storage Fase 2** — subir espejo local a Cloudflare R2 | Pendiente — trigger: deploy | Media |
| **Enrichment pass para items de referencia** — buscar URL de tienda para items Mangavariant/wiki sin precio | Pendiente | Baja |
| **Full backfill booksprivilege** 2020–2026 (~30-40 min) | Pendiente | Baja |
| **Translation layer** — `description_es` vía Google Translate + DeepL opcional | Implementado en `translate_descriptions.py`, no integrado al pipeline canónico aún | — |

---

## No-goals (permanentes)

- Predicción de lanzamientos futuros
- Tracking de precios históricos (solo capturamos el último visto)
- Inventario / stock real-time
- Notificaciones push
- Multi-usuario / auth en el scraper

---

## Riesgos y mitigaciones vigentes

| Riesgo | Mitigación |
|---|---|
| Rate limiting | `--per-host-limit 2`; sleeps por wiki; timeouts portables en shell scripts |
| Sites cambian estructura HTML | Tests de smoke + `source_health.py`; alerta si yield < threshold |
| Wikis cambian estructura | Parser versionado por wiki; `UNKNOWN_H2_LOG` en listadomanga-collections |
| Storage crece | JSONL con upsert-by-URL (no append); GC mark-and-sweep en `mirror_images.py` |
| Playwright no thread-safe | Dedicated worker thread + queue (gotcha #12 en CLAUDE.md) |
| Anti-bot / Cloudflare | UA headers; Accept-Encoding sin `br`; Playwright opt-in para JS sites |
