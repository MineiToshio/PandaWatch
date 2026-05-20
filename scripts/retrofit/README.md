# scripts/retrofit/

Utilitarios de **retrofit** — herramientas para aplicar mejoras del pipeline
de forma retroactiva sobre `data/items.jsonl` cuando el corpus histórico
no se beneficia automáticamente.

> **Estos scripts NO contienen lógica propia.** Solo importan funciones de
> `scripts/manga_watch.py` y las aplican a items ya guardados. Las mismas
> funciones ya corren automáticamente durante cualquier scrape nuevo
> (`bootstrap.sh`, `full_run.sh`).

## ¿Cuándo necesitás usarlos?

| Escenario | Script |
|---|---|
| Encontraste un patrón basura nuevo en títulos (ej. `"Comprar ahora >>"`) y lo agregaste a `TITLE_JUNK_PATTERNS` en `manga_watch.py`. Querés que los items ya guardados también se limpien. | `clean_titles.py` |
| Identificaste un nuevo tipo de no-manga (ej. `"Plushie XL"`, `"Doll"`) y lo agregaste a `_NON_MANGA_HARD`/`_SOFT` en `is_likely_manga()`. Querés sacar los que ya pasaron el filtro anterior. | `filter_non_manga.py` |
| Mejoraste un extractor (ej. nuevos selectores para Sanyodo, o `_extract_label_value_pairs` con un label nuevo). Querés re-fetchear items con campo vacío para aprovechar el extractor mejorado. | `backfill_metadata.py` |
| Agregaste una fuente nueva y querés rellenar metadata pendiente sin esperar al próximo scrape completo. | `backfill_metadata.py` |

## ¿Cuándo NO los necesitás?

- **Scrape nuevo de una fuente que ya existe**: el pipeline ya aplica todo.
- **Nunca tocaste las reglas**: no hay nada nuevo que aplicar a items viejos.

## Uso

Desde la raíz del proyecto:

```bash
# Re-limpiar títulos
python scripts/retrofit/clean_titles.py --dry-run    # preview
python scripts/retrofit/clean_titles.py              # aplicar

# Re-filtrar non-manga
python scripts/retrofit/filter_non_manga.py --dry-run
python scripts/retrofit/filter_non_manga.py

# Backfill de metadata (HTTP-bound, lento)
python scripts/retrofit/backfill_metadata.py --dry-run
python scripts/retrofit/backfill_metadata.py --sleep 0.2
python scripts/retrofit/backfill_metadata.py --only image_url --limit 50
python scripts/retrofit/backfill_metadata.py --max-per-source 100
```

Cada script crea un backup `.pre-*-bak` antes de sobrescribir
`data/items.jsonl`, así que un mal run es recuperable.

## Estado actual (última corrida)

- Total items: 8435 (después de filtros)
- Cobertura: image_url 99.7%, author 79.6%, isbn 70.6%, price 80.6%, release_date 66.0%

Si la cobertura empeora notablemente después de un scrape grande, es señal
de que conviene correr `backfill_metadata.py` para rellenar los nuevos
campos vacíos.
