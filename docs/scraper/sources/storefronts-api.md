# Fuente(s): Storefronts API — Jade Dynasty HK · Sharp Point TW · Kim Đồng VN · IPM VN · yaakz TH

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-09-15 (yaakz: probable duplicado HAPPINESS 10 con publisher IPM equivocado; §2).

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
- **Curación LLM non-manga 2026-08-23**: 1 item expulsado — guía de juegos de
  Roblox; no se pudo blacklistear por keyword porque el título embebe "ROBLOX"
  entre caracteres CJK y `\b` no hace frontera contra CJK, así que se curó por URL.

### kimdong / ipm (Vietnam)
- Ambas plataformas clonan el `/products.json` de Shopify → `_shopify_like_list`
  compartido. Filtro `_VN_SPECIAL_RE` (bản đặc biệt/giới hạn/sưu tầm/boxset/có box)
  + exclusiones de ruido `_VN_FALSE_POSITIVE_RE` ("Pokémon Đặc Biệt" es nombre de
  serie, no edición; ídem "Đội quân Doraemon đặc biệt", "Tuyển tập đặc biệt" de Conan).
- IPM es la API más rica: EAN + `published_at` + tags estructurados. Kim Đồng no
  expone ISBN en JSON (vive en la ficha SSR; ~1/3 ni ahí lo tiene).
- products.json solo lista productos PUBLICADOS — especiales viejos despublicados
  se pierden → **Mangavariant sigue siendo complementario para el histórico VN**.
- ⚠️ **Quirk series_key/display en IPM (2026-07-11, gotcha #144):** 3 volúmenes de
  "Chàng Băng Giá Và Nàng Lạnh Lùng" (The Ice Guy and His Cool Female Colleague)
  quedaron con `series_key`/`series_display` de una obra japonesa sin relación
  ("Science Fell in Love, So I Tried to Prove It"), mientras otros volúmenes de la
  MISMA obra IPM quedaron en 2 series_key más (`ice-guy-cool-colleague`,
  `chang-bang-gia-va-nang-lanh-lung`) — una sola obra partida en 3 keys, probablemente
  por el standardize LLM asignando series_key por heurística de volumen en vez de por
  título real. Curado vía `/watch-enrich-series-aliases` fusionando los 3 keys bajo
  `ice-guy-cool-colleague`; la causa raíz en el standardize NO se investigó (pendiente,
  fuera de alcance del skill de aliases).
- **Curación LLM non-manga 2026-08-23**: 6 items de Kim Đồng flageados → 1 light
  novel conservada (Chúa tể bóng tối = Kage no Jitsuryokusha, edición limitada),
  3 expulsados (boxset de libros de texto de primaria, Việt Nam sử lược = libro de
  historia, Dế Mèn phiêu lưu ký = literatura infantil vietnamita en prosa) y 2
  INCIERTOS conservados (los kamishibai "Kể chuyện bằng tranh", porque el "Combo
  Kamishibai (8 cuốn)" ya está estandarizado en el corpus).

### yaakz (Tailandia)
- ⚠️ La cifra "~1839 items" del discovery era un FALSO POSITIVO (índice de la
  tabla de referencias del payload Nuxt/devalue, no un conteo). Real: **58** en la
  categoría 1098 (`total: 58, last_page: 3` en la API).
- Exclusiones: prefijo กล่องเปล่า (cajas vacías de reposición) y
  "[Subscription Order]" (bundles duplicados del mismo box).
- Sin ISBN (el `code` tipo LISBX… es SKU interno) → dedup fuzzy.
- 37/58 títulos llevan el nombre de serie en latín (ONE PIECE, HAIKYU!!) →
  mapeo directo; los thai-only vía el campo "ชื่อ eng" de la descripción.
- **Curación LLM non-manga 2026-08-23**: 1 item INCIERTO conservado ("YAAKZ
  Collector Box") — la URL da 404 y no se pudo verificar si es una caja vacía de
  merch o un box set real.
- **2026-09-15 — probable DUPLICADO por cambio de slug + publisher inconsistente**: el
  delta trajo `HAPPINESS เล่ม 10 + (ชุดพิเศษ Boxset)`
  (`/product/happiness-เล่ม-10-ชุดพิเศษ-boxset`), y el corpus ya tenía desde el 06-12
  `HAPPINESS เล่ม 10 (จบ) + (ชุดพิเศษ boxset)` (`/product/happiness-เล่ม-10-จบ-ชุดพิเศษ-boxset`).
  Mismo tomo final 10 con box, misma tienda; la única diferencia del título es `(จบ)`
  ("fin"). Quedaron como 2 filas porque el standardize les dio publishers distintos:
  `happiness-ipm-boxset-th` (IPM, que es editorial VIETNAMITA, no tailandesa, así que
  la fila vieja casi seguro está mal) vs `happiness-siaminter-boxset-th`. No se unió ni
  se tocó (regla: publisher distinto = edición distinta, y la decisión es del owner).
  Además la serie es un homónimo ambiguo: en Anilist hay 3 obras japonesas llamadas
  "Happiness" (Shūzō Oshimi, 10 tomos, que calza con "tomo 10 fin"; Usamaru Furuya;
  Goma Gorilla) más un webtoon coreano. Por eso NO se acuñó una canónica `happiness` en
  `/watch-enrich-series-aliases`. **Recomendación (no aplicada)**: corregir el
  publisher de la fila vieja a Siam Inter y dejar que consolide; si se crea la
  canónica, usar clave desambiguada (`happiness-oshimi`) y NO el alias pelado
  "Happiness".

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


## Revisión de ingestión — 2026-09-24

SPP devolvió 403 CloudFront en prueba viva. El helper JSON notifica fallos tras tres intentos y SPP denuncia esquema desconocido; cero silencioso ya no se confunde con éxito. No se da por reparado el acceso remoto.

Evidencia y alcance: [auditoría integral](../audits/2026-09-24-ingestion.md).

### Continuación de auditoría — 2026-09-24

SPP continúa después de páginas enteramente repetidas entre búsquedas distintas; detecta repeticiones dentro de una búsqueda como error. Se elevan los topes de catálogo de Jade Dynasty, Shopify/Haravan y Yaakz a 1000 páginas, con aviso de ingestión incompleta si se alcanzan. Las respuestas de esquema desconocido de Jade Dynasty y Shopify/Haravan se reportan. SPP sigue devolviendo 403 de CloudFront tanto por requests como Chromium; el dominio sin www falla TLS y no se usa como fallback.

Jade Dynasty: la corrida real recuperó tomos que antes compartían indebidamente
cluster al no reconocer `第N期`. El extractor general ahora reconoce números
arábigos/full-width con 巻, 卷, 期, 冊 o 册. Un volumen distinto impide que una
asociación secundaria antigua absorba el nuevo tomo. Sin volumen ni identidad
explícita, el heurístico mantiene el producto independiente por URL.

### Comprobación viva adicional — 2026-09-24

Tres perfiles recorrieron sus catálogos actuales en staging con salida 0:
Kim Đồng 89 candidatos/88 reportables (17 URLs primarias nuevas), IPM 57/57
(una nueva), Yaakz 45/45 (ninguna nueva). Los códigos comerciales que no son
ISBN se conservan como evidencia con `ISBN_ANOMALY`; no se interpretan como
ISBN válidos para resolver asociaciones entre diferentes tiendas.

SPP también devolvió la página `301 Moved Permanently / CloudFront` en el
navegador normal de la aplicación; no hay recuperación automatizada verificada.

### Reparación de referencias históricas — 2026-09-24

Se quitaron 6 referencias de `nxbkimdong.com.vn` asociadas a otra fila con ISBN
válido diferente del producto cuya URL primaria es esa misma referencia. Se
conservan ambos productos y su URL primaria; no se fusionan por ISBN. Evidencia
por URL/ISBN en `reports/ingestion-audit-2026-09-24/closure/publication-2-manifest.json`.

### Delta 2026-09-25 — `spp-tw` agotó reintentos

El storefront de Taiwán falló su request JSON en los 3 intentos:

```
[WIKI-ISSUE] JSON request failed after 3 attempts:
https://www.spp.com.tw/webapi/SearchV2/GetShopSalePageBySearch
```

Paso `storefront:spp-tw` → **rc=1**, 0 items. Los otros storefronts del mismo paso
(jd-intl HK, kimdong/ipm VN, yaakz TH) corrieron bien en la misma corrida — de hecho
Jade Dynasty aportó 2 de los 23 items nuevos del día, así que **no es una caída del
paso completo ni del borde compartido**: es específico de `spp-tw`.

Primera aparición registrada. **No verificado en vivo** si es rate-limit, cambio de
contrato del endpoint o bloqueo. Si se repite mañana, conviene sonda manual antes de
tocar configuración. Nada aplicado.

## Auditoría estratégica — 2026-09-25

SPP-TW queda retirado del job administrado por 403 persistente también en ficha real (CloudFront). Alternativa incorporada: catálogo SPP Manga de Kingstone; ficha tw-kingstone-spp.md. Books.com.tw respondió 403 y no se habilita. TongLi webpagebooks.aspx sí expone BooksDetail.aspx, pero cubre otro editor y no reemplaza SPP; queda candidato, sin activar un parser incompleto.
