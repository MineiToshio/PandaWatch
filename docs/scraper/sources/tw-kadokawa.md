# Fuente: Kadokawa Taiwan

> Ficha del catálogo de fuentes de PandaWatch. Última revisión: 2026-06-12 (alta).

| Campo | Valor |
|---|---|
| **Nombre** | TW - Kadokawa Taiwan (特裝/限定) |
| **Entrada** | `search_template: kadokawa.com.tw/products?query={query}&page=1` · keywords 特裝/限定/典藏 |
| **kind / class** | `html` / `official` · País Taiwán · purity manga_only |
| **Aporte** | ~118-250 especiales (overlap alto entre queries) |

- SHOPLINE server-rendered; selectores `product-item` + `div.title` + `a[href*='/products/']`.
- El slug de la URL de producto ES el barcode (EAN 4711… bundles / ISBN 978… libros).
- JSON-LD Product en ficha (precio TWD, availability); fotos de extras verificadas
  (ej. 狼與辛香料 完全版 典藏Box con foto de postal + standee).
- ~35-40% del listing es merch propio (複製原畫, 加購特典 acrílicos, 燈光畫) — lo
  filtran non-manga + gate; si crece el ruido, excluir por keyword en título.
- Evaluación 2026-06-12: viable (auditoría con muestras verificadas visualmente).
- Dry-run de alta: 120 candidatos / 118 reportables (query 特裝).

```bash
.venv/bin/python scripts/manga_watch.py --only-source "TW - Kadokawa Taiwan (特裝/限定) [search: 特裝]" --dry-run
```
