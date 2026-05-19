# PRD — Expansión del Catálogo de Ediciones Especiales

> Plan multi-fase para pasar de "detección incremental de novedades" a
> "catálogo histórico completo y curado" de ediciones especiales de manga.

---

## 1. Resumen ejecutivo

El scraper actual está optimizado para detectar **lo nuevo de hoy** en 76 fuentes.
Lo que no puede hacer hoy es construir un **catálogo histórico completo** porque
las páginas que visita (homes, "novedades", categorías) solo muestran los últimos
~30 productos por sitio.

Este PRD describe 3 fases (+ 1 bonus) para expandir el catálogo:

- **Fase 1** — Búsquedas dirigidas multi-keyword: usa el scraper actual con queries
  específicas para encontrar el catálogo histórico de cada editorial.
- **Fase 2** — Scraping de wikis comunitarias (ListadoManga, Manga-Sanctuary, etc.):
  data curada por humanos con tags semánticos.
- **Fase 3** — Sitemap mining: discovery automático para editoriales con SEO bien hecho.
- **Bonus (Fase 4)** — LLM enrichment: clasificación, deduplicación semántica,
  completado de metadata faltante.

Cada fase apunta a un eje distinto (cantidad vs calidad) y se pueden ejecutar
de forma independiente o combinada.

## 2. Estado actual

```
data/items.jsonl  → 283 items detectados tras 1 run completo
- 32 fuentes con candidatos OK
- 6 países representados
- 26 editoriales identificadas
- Cobertura: la "punta del iceberg" del universo real
```

**Limitaciones identificadas:**

1. Las landing pages solo muestran los últimos 30-50 productos.
2. Ediciones que salieron antes de hoy y no están en novedades NO se ven.
3. Categorías profundas no se navegan (ej. "Boxsets 2019-2022").
4. Algunas editoriales no tienen catálogo navegable (Norma sin sitemap).

**Universo real estimado** (catálogo histórico):
- Norma España: ~200-300 ediciones especiales históricas.
- Panini España + México: ~500+ entre ambas.
- Glénat Francia: ~500-1000 entre manga + artbooks.
- Editoriales JP: miles de 限定版.
- Total estimado: **5,000-15,000 ediciones especiales** identificables.

## 3. Objetivo

Construir y mantener un **dataset histórico** de al menos **3,000-5,000 ediciones
especiales identificadas** distribuidas en los 5 países objetivo, con calidad
suficiente para ser consultadas en el browser web.

## 4. Las 3 fases (visión)

### Fase 1: Búsquedas dirigidas multi-keyword

**Mecánica**: en lugar de visitar solo `homepage` o `/novedades`, agregar URLs
de búsqueda interna con keywords coleccionistas como "fuentes virtuales".

**Ejemplo concreto**:
```yaml
# Antes (1 fuente)
- name: "MX - Panini Manga México"
  url: "https://tiendapanini.com.mx/coleccionables/item-3"

# Después (1 template + N queries)
- name: "MX - Panini México"
  search_template: "https://tiendapanini.com.mx/catalogsearch/result/?q={query}"
  keywords:
    - "edicion limitada"
    - "edicion especial"
    - "edicion coleccionista"
    - "deluxe"
    - "cofre"
    - "kanzenban"
    - "variante"
    - "hardcover"
    - "tapa dura"
    - "gran formato"
  # → genera 10 fuentes virtuales con sus URLs respectivas
```

**Ganancia esperada**: 283 → ~3,000-5,000 items tras el primer run.

**Costo**: 1 HTTP extra por query x ~15 queries x ~10 editoriales = 150 requests
extra por run (~3-5 min adicionales).

**Por qué primero**: ROI altísimo, cero código nuevo, low risk.

### Fase 2: Wikis comunitarias

Scraping de wikis curadas por humanos. Cada wiki requiere un parser custom
porque la estructura es propia, pero la data resultante es la **mejor calidad
disponible** (curada, con tags semánticos, fechas exactas).

**Targets prioritarios:**

1. **ListadoManga.es** (España) — Calendario histórico mes-por-mes desde 2003.
   URL pattern: `?mes=N&ano=YYYY`. Hierarchy: editorial → fecha → categoría.
   Algunos entries marcan explícitamente "Edición Especial" / "Sobrecubierta Reversible".
2. **Manga-Sanctuary.com** (Francia) — Catálogo histórico equivalente para FR.
3. **comicnatalie.com / ja.wikipedia** (Japón) — Catálogo japonés histórico.
4. **AnimeNewsNetwork Encyclopedia** (US/global) — Para cross-validation.

**Ganancia esperada**: 5,000-15,000 items curados.

**Costo**: 1-2 días de implementación por wiki. Cada parser es ~200-400 líneas.

### Fase 3: Sitemap mining

Algunas editoriales exponen `/sitemap.xml` con TODAS sus URLs de producto.
Implementar un detector que:

1. Intenta `/sitemap.xml`, `/sitemap_index.xml`, `/robots.txt → Sitemap:`.
2. Parsea XML, filtra URLs con patrones de producto (`/product/`, `/manga/`, etc.).
3. Encola cada URL como item a procesar por el scraper actual.

**Ganancia variable**: muy buena para editoriales con SEO bien hecho;
inútil para sitios sin sitemap (como Norma, según validamos).

**Costo**: 1-2 días de implementación, generalizable a múltiples sitios.

### Bonus — Fase 4: LLM enrichment

Una vez que tenemos un dataset grande pero ruidoso, usar LLM para:

- **Clasificación**: "¿este item es realmente edición especial o tomo regular?"
- **Dedup semántico**: "Berserk Deluxe Vol 14" y "Berserk Edición Coleccionista Tomo 14"
  son el mismo producto en distinto idioma/editorial.
- **Metadata completion**: extraer autor, año original, signals adicionales
  desde la descripción.
- **Validación**: filtrar items que el scraper detectó como "limited" pero
  en realidad no lo son.

**Costo estimado**: $5-30 USD en API por barrido completo del dataset.

**Por qué NO usarlo como source**: LLMs alucinan ediciones que no existen.
Solo lo usamos para enriquecer datos ya scrappeados.

## 4.5. Bootstrap inicial (modo one-shot)

Antes/en paralelo a Fase 2-3, hay una herramienta tipo "primer crawleo
exhaustivo" para construir el dataset inicial:

```bash
./scripts/bootstrap.sh
```

Hace scraping profundo con:
- `--max-pages 50` (vs 5 incremental)
- `--sleep-seconds 1.5` (anti-rate-limit)
- Todos los modos activados: JS, fuzzy, fetch-details, diagnostic
- Snapshot del `items.jsonl` previo (rollback fácil)

Tiempo: 1-2 horas. Pensado para correr una vez (o cada 6-12 meses).

Es **complementario** a Fase 2/3, no las reemplaza:
- Para **ES/FR** (editoriales grandes): Fase 2 (wikis) sigue siendo mejor para el histórico.
- Para **MX/AR/JP** (sin wiki ni sitemap claro): bootstrap es la única forma de cubrir profundo.
- Para **catálogos con sitemap accesible**: Fase 3 sigue siendo más eficiente.

Después del bootstrap, runs incrementales con `./scripts/full_run.sh`.

## 5. Roadmap propuesto

| Sprint | Trabajo | Resultado esperado |
|---|---|---|
| **Sprint 0.5** (1 hora) | `bootstrap.sh` one-shot con paginación 50 | Dataset: 493 → 2,000-4,000 items |
| **Sprint 1** (1-2 días) | Fase 1: `search_template + keywords` en YAML, agregar entries para 8-10 editoriales | Dataset: 283 → 2,000-5,000 items |
| **Sprint 2** (3-5 días) | Fase 2.1: parser de ListadoManga (calendario histórico ES) | +3,000-5,000 items curados ES |
| **Sprint 3** (3-5 días) | Fase 2.2: parser de Manga-Sanctuary (FR) | +2,000-4,000 items FR |
| **Sprint 4** (2-3 días) | Fase 2.3: parser de wiki JP (manga-comic-database o similar) | +5,000-10,000 items JP |
| **Sprint 5** (1-2 días) | Fase 3: detector universal de sitemaps | Cobertura adicional variable |
| **Sprint 6** (3-5 días, opcional) | Fase 4: LLM enrichment + dedup | Calidad +30% |

Tras Sprints 1-3, el dataset debería rondar **10,000-20,000 items** con cobertura
sólida de ES + FR + algo de US/MX. La web browser ya está lista para mostrar todo.

## 6. Métricas de éxito

| Métrica | Hoy | Post Sprint 1 | Post Sprint 3 |
|---|---:|---:|---:|
| Items totales | 283 | 2,000-5,000 | 10,000-20,000 |
| Fuentes OK | 32 | 50-70 | 100+ |
| Países cubiertos | 6 | 6 | 6 (más profundo) |
| % items con autor | 2% | 5% | 30% (wikis tienen autor) |
| % items con precio | 53% | 50% | 50% |
| % items con foto | 67% | 70% | 80% (wikis tienen covers) |
| % items con fecha real de venta | 17% | 30% | 70% (wikis tienen fechas) |

## 7. Diseño Fase 1 (detalle)

### Cambios en `sources.yml`

Nuevo formato opcional: una fuente puede tener `search_template + keywords`
en lugar de `url` directa. El loader expande esto en N fuentes virtuales.

```yaml
- name: "MX - Panini México (search)"
  country: "México"
  language: "Español"
  publisher: "Panini Manga México"
  source_class: "official"
  kind: "html"
  search_template: "https://tiendapanini.com.mx/catalogsearch/result/?q={query}"
  keywords:
    - "edicion limitada"
    - "edicion especial"
    - "deluxe"
    - "cofre"
    - "kanzenban"
    - "variante"
    - "hardcover"
    - "tapa dura"
  tags: ["manga", "official", "expansion", "search"]
```

### Cambios en `scripts/manga_watch.py`

- `load_sources()` detecta `search_template`. Si está, genera 1 `Source` por keyword.
- El nombre se expande: `"MX - Panini México (search: 'cofre')"`.
- La URL se expande: `template.format(query=quote_plus(keyword))`.
- Los tags incluyen automáticamente `"expansion"` y `"search:<keyword>"`.

### Nuevo flag CLI

- `--exclude-tags expansion`: ignora todas las fuentes expandidas en runs rápidos.
- `--include-tags-only expansion`: corre SOLO las fuentes expandidas (útil para
  bootstrap inicial sin re-tocar las fuentes normales).

### Tests

- Parser correcto del template (verifica encoding de espacios).
- 1 entrada con keywords genera N Sources con nombre/URL/tags coherentes.
- Una fuente sin `search_template` se carga normal.

### Editoriales objetivo para Sprint 1

| Editorial | Search endpoint | Validación |
|---|---|---|
| Panini MX | `tiendapanini.com.mx/catalogsearch/result/?q=` | ✅ ya validado |
| Panini ES | `panini.es/shp_esp_es/catalogsearch/result/?q=` | a validar (mismo Magento) |
| Norma | `normaeditorial.com/?s=` | a validar (WP) |
| Glénat | `glenat.com/?keys=` | a validar |
| Pika FR | `pika.fr/?s=` | a validar |
| Ki-oon | `ki-oon.com/recherche?q=` | a validar |
| Dark Horse Direct | `darkhorsedirect.com/search?q=` | Shopify estándar |
| Yen Press | `yenpress.com/search?q=` | a validar |
| Star Comics IT | `starcomics.com/search?q=` | a validar |
| Edizioni BD | Magento search | a validar |

### Keywords por idioma

- **ES**: edicion limitada, edicion especial, edicion coleccionista, deluxe, cofre, coleccionista, numerada, kanzenban, integral, tapa dura, variante, gran formato
- **EN**: limited edition, special edition, collector edition, deluxe, hardcover, boxset, slipcase, omnibus, variant cover, signed, exclusive
- **FR**: edition collector, edition limitee, tirage limite, coffret, prestige, deluxe, integrale, jaquette
- **IT**: edizione limitata, edizione speciale, deluxe, cofanetto, variant, esclusiva, prestige
- **JA**: 限定版, 特装版, 初回限定, 数量限定, 完全版, 愛蔵版, BOX

## 8. Diseño Fase 2 (preview)

Parser de wiki sigue este patrón:

```python
def parse_listado_manga(year: int, month: int) -> list[Candidate]:
    """Parser custom para listadomanga.es/calendario.php?mes=N&ano=YYYY."""
    url = f"https://www.listadomanga.es/calendario.php?mes={month}&ano={year}"
    soup = fetch_html(url)
    # Cada entry tiene editorial + fecha + título + opcionalmente tags
    for entry in soup.select("table.calendario tr"):
        ...
```

Nuevo CLI: `--bootstrap-wiki listado-manga --from 2018-01 --to 2026-12`.

## 9. Diseño Fase 3 (preview)

```python
def discover_via_sitemap(base_url: str) -> list[str]:
    """Intenta /sitemap.xml, parsea, devuelve URLs de producto."""
    for path in ("/sitemap.xml", "/sitemap_index.xml"):
        ...
    # Filtra URLs que matchean patrones de producto
```

Nuevo CLI: `--discover-sitemaps`.

## 10. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Rate limiting al hacer 100+ queries | Sleep mayor entre queries (1-2s); flag para correr en chunks |
| Sites cambian estructura de búsqueda | Tests de smoke para cada editorial; CI mensual |
| Wikis cambian estructura de HTML | Parser por wiki versionado; alerta si N items < threshold |
| Búsquedas devuelven false positives | El sistema de signals/score ya filtra; min-score 30 cubre la mayoría |
| Storage del JSONL crece a 50MB+ | Compactación periódica via dedup; rotación a JSONL anual |
| LLM alucinaciones | NO usar como source; solo para enrichment de items existentes |

## 11. No-goals (out of scope)

- Edición/curación manual del dataset desde la web.
- Predicción de futuros lanzamientos.
- Tracking de precios históricos (solo capturamos el último visto).
- Inventario / stock real-time.
- Notificaciones de re-stock.

## 12. Criterios de aceptación por Fase

### Fase 1
- ✅ Una fuente con `search_template + keywords` se expande en N Sources.
- ✅ `--list-sources` muestra las fuentes expandidas correctamente.
- ✅ Un run con `--include-tags-only expansion` ejecuta solo las queries.
- ✅ Tras un run completo, items totales suben de 283 a >1000.
- ✅ No hay regresión en las fuentes existentes.

### Fase 2
- ✅ Un comando como `python manga_watch.py --bootstrap-wiki listado-manga --from 2024-01`
  popula el JSONL con items de calendario histórico.
- ✅ Items wiki incluyen autor en ~70% de los casos.

### Fase 3
- ✅ Comando `--discover-sitemaps` agrega URLs auto-discovered al run.

## 13. Resumen visual

```
HOY:       283 items, 6 países, scraper diario
            ▼
SPRINT 1:  2,000-5,000 items via búsquedas dirigidas (Fase 1)
            ▼
SPRINT 2-4: 10,000-20,000 items via wikis comunitarias (Fase 2)
            ▼
SPRINT 5:  Cobertura adicional via sitemaps (Fase 3)
            ▼
SPRINT 6:  Calidad de metadata +30% via LLM (Fase 4 opcional)
```
