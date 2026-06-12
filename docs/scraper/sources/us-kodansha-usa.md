# Fuente: Kodansha USA

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-12 (migración search → wiki).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre (wiki)** | US - Kodansha USA (ediciones especiales) |
| **Nombre (search, deshabilitada)** | US - Kodansha USA (search) |
| **URL base** | `https://kodansha.us` |
| **Punto de entrada** | API propia: `/wp-json/kodansha/v1/search-series?q={keyword}` |
| **`kind`** | `wiki` (fuente sintética vía `--bootstrap-wiki kodansha-us`) |
| **`source_class`** | `official` |
| **País / idioma** | Estados Unidos / Inglés |
| **purity** | `manga_only` |
| **Cobertura** | Deluxe hardcovers, omnibus, box sets, collector's editions, hardcovers |
| **Aporte estimado** | ~61 series, ~200-300 volúmenes (catálogo completo) |
| **Parser / módulo** | [`scripts/wikis/kodansha_us.py`](../../../scripts/wikis/kodansha_us.py) |

**Por qué importa**: Kodansha USA publica algunas de las ediciones deluxe más icónicas del
manga en inglés (Vinland Saga Deluxe, Battle Angel Alita Deluxe, Ghost in the Shell Deluxe,
Attack on Titan Omnibus, AoT Box Set, Cardcaptor Sakura Collector's…). La fuente de búsqueda
anterior devolvía artículos de blog, no páginas de producto → 0 candidatos. El wiki usa la
API real del sitio y extrae ISBN/fecha/portada desde el JSON-LD de cada volumen.

---

## 2. Descripción técnica

### API de series (discovery)

```
GET https://kodansha.us/wp-json/kodansha/v1/search-series?q={keyword}&per_page=100&page={N}
```

Respuesta JSON:
```json
{
  "success": true,
  "data": [{"uuid": "...", "slug": "vinland-saga-deluxe", "name": "Vinland Saga Deluxe", "image": {...}}],
  "count": 5,
  "total_count": 5
}
```

La API devuelve hasta ~25 ítems por página (el param `per_page` no tiene efecto más allá de 25).
El wiki itera `page` hasta que `count >= total_count` o hasta que el batch venga vacío.

Keywords usadas: `deluxe`, `omnibus`, `collector`, `hardcover`, `box set`, `boxset`, `definitive`, `complete`.

### Series page (volúmenes)

```
GET https://kodansha.us/series/{slug}/
```

Scrape de `div.volume-card a[href]` → lista de URLs de volumen.

### Volume page (datos)

```
GET https://kodansha.us/series/{slug}/volume-N/
```

JSON-LD `@type=Book` con:
- `name` → título
- `image` → URL portada (azuki.co CDN: `production.image.azuki.co/{uuid}/800.webp`)
- `author.name` → autor
- `workExample[0]` (Paperback) → `isbn`, `datePublished`, `offers.price`

Filtro delta: en modo delta, solo se emiten volúmenes con `datePublished >= from_date`.

---

## 3. Cómo se compara con la fuente search anterior

| Aspecto | Search (deshabilitada) | Wiki (activa) |
|---|---|---|
| URL de búsqueda | `kodansha.us/?s=deluxe` | API `/wp-json/kodansha/v1/search-series` |
| Qué devuelve | Artículos de blog (noticias) | Series del catálogo |
| Candidatos en el último run | 0 | ~61 series, ~18 candidatos delta |
| ISBN disponible | No | Sí (JSON-LD) |
| Portada | No | Sí (azuki.co CDN) |
| Fecha de publicación | No | Sí (JSON-LD) |

La fuente `US - Kodansha USA (search)` está **`enabled: false`** desde 2026-06-12.

---

## 4. Proceso de ingestión

- **FASE 2** del pipeline (wikis), después de Seven Seas.
- **Delta** (`scrape_delta.sh`, paso `[2r]`): `--wiki-from LISTADO_CAL_FROM` — solo
  volúmenes con `datePublished` en los últimos ~3 meses.
- **Full** (`scrape_full.sh`, paso `[2y]`): `--wiki-from 2000-01` — catálogo completo.
- Timeout: 600s (delta) / 900s (full).
- Sleep: 0.5s entre requests (3 requests por volumen: series page + volume page × N).

### Wiring

```bash
# Delta (últimos 3 meses)
python scripts/manga_watch.py --bootstrap-wiki kodansha-us \
    --wiki-from 2026-04 --sleep-seconds 0.5 --min-score 20

# Full (catálogo completo)
python scripts/manga_watch.py --bootstrap-wiki kodansha-us \
    --wiki-from 2000-01 --sleep-seconds 0.5 --min-score 20
```

---

## 5. Problemas y quirks

- **Paginación API no-estándar**: `per_page` aceptado pero máx ~25 resultados por
  página. El wiki pagina correctamente hasta `count >= total_count`.
- **"box set" (con espacio) devuelve 0 series** vía la API de búsqueda — las series tipo
  "Box Set" se descubren por la keyword `box` o `complete`. Las series con "Box Set" en el
  nombre sí calificadas por `is_special_series()` al tener el regex `box\s*set`.
- **Imágenes**: provienen del CDN azuki.co (`production.image.azuki.co/{uuid}/800.webp`).
  El campo `image` del API es un dict `{uuid, aspect_ratio_decimal, ...}` — no una URL directa.
- **No es tienda**: Kodansha USA no vende directamente. Las URLs son páginas de publisher,
  no de compra. El campo `source_class: "official"` es correcto (no `retailer`).
- **Filtro manga_only**: el catálogo es manga 100% — `purity: manga_only` es correcto.
- **#18 — omnibus**: omnibus a secas es válido en Kodansha (Noragami Omnibus, AoT Omnibus
  son formatos gruesos, no tomos regulares). A diferencia de Seven Seas, los omnibus de
  Kodansha suelen ser hardcovers caros ($49-$69) que sí califican como coleccionables.

---

## 6. Runbook / comandos útiles

```bash
# Test rápido (dry-run, últimos 6 meses)
python scripts/manga_watch.py --bootstrap-wiki kodansha-us \
    --wiki-from 2026-01 --sleep-seconds 0.3 --min-score 20 --dry-run

# Ver items de Kodansha en el corpus
python - <<'PY'
import json
from collections import Counter
items = [json.loads(l) for l in open("data/items.jsonl") if l.strip()]
kd = [it for it in items if any("kodansha.us" in (s.get("url","") or "") for s in it.get("sources",[]))]
print(f"Items: {len(kd)}")
for it in kd[:10]:
    print(f"  {it.get('title','?')[:60]} | {it.get('country','?')}")
PY

# Tests
python -m pytest tests/test_kodansha_us.py -v

# Validar corpus después de ingestión
python scripts/validate_corpus.py
```
