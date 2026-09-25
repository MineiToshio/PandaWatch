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
- Curación LLM non-manga 2026-08-23: 11 items de merchandising expulsados
  (stickers, chapas, mini-cartas, acrílicos, tapices, láminas) — todos con el sello
  【日本進口精品】 ("artículo japonés de importación"), que Kadokawa Taiwan usa SOLO
  para su línea de goods, nunca para 漫畫/輕小說; se agregó como patrón HARD en
  `manga_watch.py`. Se conservaron 2 light novels (Classroom of the Elite 12.5
  全套收納BOX典藏版, 86 Ep.14 限定版).

```bash
.venv/bin/python scripts/manga_watch.py --only-source "TW - Kadokawa Taiwan (特裝/限定) [search: 特裝]" --dry-run
```

### Auditoría full — 2026-09-24

Las búsquedas completas 特裝 y 典藏 recorrieron 47 y 44 páginas; 限定 llegó a la
página 54 y recibió HTTP 429. Se conservaron los candidatos previos. Se añade
`throttle_group: kadokawa-tw`: una petición simultánea y pausa mínima del grupo.
No se afirma cobertura completa del tramo que devolvió 429.

El extractor reconoce `2 【特裝版】` como volumen 2. Dos URLs de BOX estaban
incorrectamente enlazadas a productos de Evangelion/沉月第一部; los listados
observados corresponden a 沉月第二部 y 狼與辛香料. Se separan por URL sin inventar ISBN.
