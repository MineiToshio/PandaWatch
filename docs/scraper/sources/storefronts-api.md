# Fuente(s): Storefronts API — Jade Dynasty HK · Sharp Point TW · Kim Đồng VN · IPM VN · yaakz TH

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-12 (alta de las 5 fuentes).

Ficha agrupada: las 5 fuentes comparten el módulo
[`scripts/wikis/storefront_json.py`](../../../scripts/wikis/storefront_json.py) —
un módulo, N **perfiles declarativos** (cada perfil = cómo listar su API JSON +
cómo mapear producto→Candidate + filtro de título). Evaluadas con
/watch-evaluate-sources (6 auditores, 2026-06-12); 0% overlap de ISBN con el corpus.

---

## 1. Los 5 perfiles

| Perfil | Fuente virtual | País | API | Items netos | ISBN | Fecha |
|---|---|---|---|---|---|---|
| `jd-intl` | HK - Jade Dynasty (ediciones premium) | Hong Kong | WooCommerce Store API `/wp-json/wc/store/v1/products` (13 págs × 100) | ~341 | ~45% (regex sobre short_description, 978-988) | no (proxy: upload path) |
| `spp-tw` | TW - Sharp Point 尖端 (especiales) | Taiwán | 91APP `/webapi/SearchV2/GetShopSalePageBySearch` (startIndex server-side, 4 keywords) | ~342-719 | barcode en detalle (no se fetchea hoy) | en detalle |
| `kimdong` | VN - NXB Kim Đồng (bản đặc biệt) | Vietnam | Sapo/Bizweb `/collections/all/products.json` (74 págs × 100) | ~119 | parcial (solo ficha SSR, no en JSON) | no |
| `ipm` | VN - IPM (bản sưu tầm / boxset) | Vietnam | Haravan `/collections/all/products.json` (26 págs × 50 — capea limit) | ~110 | EAN-893 en `variants[].barcode` | `published_at` ✓ |
| `yaakz` | TH - Siam Inter / yaakz (box sets) | Tailandia | Laravel `/api/products?filter[parent_category_id]=1098` | ~47 | no | no |

Todas `purity: manga_only`, `source_class: official` (tiendas de la propia editorial).

**Por qué importan**: abren Hong Kong (0→~340) y dan la PRIMERA fuente directa de
Taiwán, Vietnam y Tailandia (antes solo el agregador Mangavariant, desactualizado:
su One Piece VN más nuevo era el 103 vs 110 en venta).

---

## 2. Detalles por perfil

### jd-intl (Hong Kong)
- Catálogo completo 1246 → filtro `_JD_SPECIAL_RE` (珍藏版|愛藏版|完全版|盒裝|豪華|限定|彩色版)
  → ~341. **新裝版 queda FUERA** (re-edición regular ≈ "Nueva Edición").
- El manhua HK propio de Tony Wong (風雲, 龍虎門) NO está en esta tienda — solo
  manga japonés licenciado en HK (帶子雄狼 = Lone Wolf and Cub, 淚眼煞星 = Crying
  Freeman) → los aliases CJK necesitan trabajo (nombres HK no literales).
- Bonus de 1ª edición a veces fotografiados en ficha (pasa la lección BooksPrivilege).
- ⚠️ **Quirk país (2026-07-08, gotcha #143):** el scrape hornea `country="Hong Kong"`
  correctamente (fuente de verdad), pero el standardize LLM del 2026-06-12 acuñó
  `edition_key` terminado en `-tw` (Taiwán) para 15 items de Jade Dynasty — el LLM
  confundió el mercado (JD también distribuye en TW) pese a que la edición es HK.
  Violaba la invariante PAISKEY (`-tw` ≠ `_country_slug("Hong Kong")="hk"`). Corregido
  determinísticamente: `fix_edition_country` ahora reemplaza un sufijo país válido pero
  EQUIVOCADO (`-tw`→`-hk`), no sólo apenda el faltante. El fix corre en el pipeline
  (`enforce_listadomanga_rules`), así que un re-standardize que vuelva a acuñar `-tw`
  queda saneado por el enforcement final.

### spp-tw (Taiwán)
- El HTML de búsqueda tiene paginación client-side ROTA (&page=2 = mismo lote);
  el endpoint `webapi/SearchV2` descubierto en la auditoría la resuelve
  (startIndex real, maxCount 150).
- Filtro doble en `_spp_map`: qualifier en título (限定版|特裝版|典藏|盒裝) +
  exclusión 寫真/畫冊典藏/原畫/複製 (photobooks/merch). Queda algo de ruido de
  photobooks K-pop con 典藏版 — el filtro non-manga downstream ayuda; si crece,
  endurecer el exclude.
- Detalle `/SalePage/Index/{id}` tiene barcode/fecha/autor embebidos (HTML
  estático) — enrich futuro si hace falta ISBN.

### kimdong / ipm (Vietnam)
- Ambas plataformas clonan el `/products.json` de Shopify → `_shopify_like_list`
  compartido. Filtro `_VN_SPECIAL_RE` (bản đặc biệt/giới hạn/sưu tầm/boxset/có box)
  + exclusiones de ruido `_VN_FALSE_POSITIVE_RE` ("Pokémon Đặc Biệt" es nombre de
  serie, no edición; ídem "Đội quân Doraemon đặc biệt", "Tuyển tập đặc biệt" de Conan).
- IPM es la API más rica: EAN + `published_at` + tags estructurados. Kim Đồng no
  expone ISBN en JSON (vive en la ficha SSR; ~1/3 ni ahí lo tiene).
- products.json solo lista productos PUBLICADOS — especiales viejos despublicados
  se pierden → **Mangavariant sigue siendo complementario para el histórico VN**.

### yaakz (Tailandia)
- ⚠️ La cifra "~1839 items" del discovery era un FALSO POSITIVO (índice de la
  tabla de referencias del payload Nuxt/devalue, no un conteo). Real: **58** en la
  categoría 1098 (`total: 58, last_page: 3` en la API).
- Exclusiones: prefijo กล่องเปล่า (cajas vacías de reposición) y
  "[Subscription Order]" (bundles duplicados del mismo box).
- Sin ISBN (el `code` tipo LISBX… es SKU interno) → dedup fuzzy.
- 37/58 títulos llevan el nombre de serie en latín (ONE PIECE, HAIKYU!!) →
  mapeo directo; los thai-only vía el campo "ชื่อ eng" de la descripción.

---

## 5. Proceso de ingestión

- FASE 2 (wikis): paso `[2s]` en scrape_delta.sh y `[2z]` en scrape_full.sh —
  los 5 perfiles en loop secuencial (catálogos chicos, upsert idempotente; no
  hay modo delta: siempre catálogo completo).
- Señales de idioma (alta 2026-06-12 en KEYWORD_RULES): chino tradicional
  (首刷限定版, 特裝版, 珍藏版, 愛藏版, 盒裝套書…), vietnamita (bản đặc biệt,
  bản giới hạn, bản sưu tầm, có box), tailandés (ชุดพิเศษ, ฉบับพิเศษ).

## 9. Pendientes

- **SPP enrich**: fetchear `/SalePage/Index/{id}` para barcode/fecha (hoy solo listing).
- **Kim Đồng ISBN**: fetch SSR por item (~119 requests extra) si se quiere dedup ISBN.
- **Aliases CJK/VN/TH**: correr `/watch-enrich-series-aliases` tras la primera ingesta.
- **Tong Li (TW)**: VIABLE en la auditoría (editorial #1, ISBN+fecha por ficha,
  ~300 especiales/año) pero requiere módulo propio con discovery de fichas
  (la tabla Search1.aspx no enlaza; códigos con sufijo `A` = limitada; descubrir
  vía webpagebooks.aspx). **Pendiente para una próxima sesión** — notas completas
  en la auditoría (handoff §10).
- **books.com.tw search**: borderline (listado-only, solo query 漫畫 限定版 usable,
  ~80% de 特裝版 es 18+ con placeholder) — watchlist.

## 10. Runbook

```bash
# Standalone (debug, sin escribir items.jsonl)
.venv/bin/python scripts/wikis/storefront_json.py jd-intl --sleep-seconds 0.3
.venv/bin/python scripts/wikis/storefront_json.py spp-tw

# Ingesta real de un perfil
.venv/bin/python scripts/manga_watch.py --bootstrap-wiki jd-intl --sleep-seconds 0.3 --min-score 20
```
