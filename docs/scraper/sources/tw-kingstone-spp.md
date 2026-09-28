# Fuente: Kingstone — SPP Manga (Taiwán)

## Alcance y evidencia — 2026-09-25

[Catálogo público del editor SPP Manga](https://www.kingstone.com.tw/bookpublish/publist/14395/?classname=new&dis=pic&format=0&page=1&sort=sa_desc&subkind=all),
retailer verificable con libros físicos y ebooks; 498 páginas observadas, 20 fichas por página.
No noticias ni rumores. Alternativa para descubrimiento cuando SPP directo responde 403.
No garantiza todo el fondo descatalogado de la editorial.

## Parser y ciclo completo/delta

Entrada `TW - Kingstone (SPP Manga)` en sources.yml. Tarjetas `.mod_prod_card`,
título/enlace `h3.pdnamebox a`; siguiente `li.pageNext a`. URL de producto `/basic/`.
Los títulos 【電子書】 son ebooks y se rechazan, aunque digan 完全版 o 典藏版.
No confundir el código interno 201… con ISBN. Publisher 尖端; país Taiwán;
idioma Chino tradicional. Descripción de tarjeta conserva señales de extras/edición.
Los gates comunes excluyen tomos regulares, cómics y mercancía; se conservan manga,
manhwa/manhua y novelas asiáticas premium según el alcance confirmado.

Full inicial obligatorio con recibo durable. Sin timestamp de modificación fiable,
se recorre el catálogo en delta y el estado persistido identifica cambios. Límite
1000 páginas; alcanzar el límite con página siguiente es fallo de cobertura.
Los productos de páginas ya leídas sobreviven a error/interrupción.

Ensayo aislado y resultados: `reports/source-strategy-2026-09-25/`.

La ficha real declara canonical `/basic/<id>/`; `lid` y `actid` son tracking de
listado y se ignoran al deduplicar solo en ese host/ruta. No confundir GTIN
4717702301606 rotulado "ISBN" por la tienda con ISBN editorial 978/979.

Recorrido completo confirmado: 498 páginas, 9.943 candidatos de catálogo. Se
identificaron 693 SKU físicos candidatos a premium antes del filtro semántico final.
La corrida exploratoria detectó y permitió corregir cruces de ebooks, cajas con
último tomo y partes 第1部/第2部. Se reconstruyeron las 7 fichas físicas fusionadas
erróneamente y se conservaron todas las identidades; fuentes electrónicas excluidas.
Los SKU diferentes de Kingstone no se colapsan solo por una clave aproximada.
漫畫集/漫画集 significa recopilación de manga, no un artbook; se corrige la señal
por substring. 畫冊 sí es un álbum de ilustración y 套書 un conjunto de libros.

## Primera cosecha completa y el falso `artbook` — 2026-09-26

Baseline inicial de la fuente repartida en dos tramos: ~689 items en la ingesta del
2026-09-25 (19:00-20:00) y **701 items netos más** en el delta del 2026-09-26. Es la
fuente que domina los hallazgos del run y por amplio margen.

Composición de esos 701: **604 manga, 55 box sets, 37 "artbook", 5 fanbooks**;
12 `rare`. El fondo es exactamente lo que se buscaba al incorporarla: la línea
典藏版 (deluxe/coleccionista) de 尖端 en formato 盒裝套書 (caja) — *Orange Road* (全10冊),
*帶子狼* (Lone Wolf and Cub, encuadernación 精裝), *橫濱購物紀行*, *銀河鐵道999*,
*蒼天之拳*, *水滸傳*, *夏子的酒* en dos acabados (櫻花款 / 楓葉款), más 首刷限定版
(limitadas de primera tirada) y 完結限定版 (limitadas de cierre de serie).

### Defecto medido: `畫冊等級` se lee como "es un artbook"

De los 37 items clasificados `artbook`, **28 están mal** (76%). El disparador no es
el título sino la descripción, que en las ediciones premium presume el papel:

```
內文用紙皆採用畫冊等級的高階美術紙120g雪白畫刊
```

`畫冊` ahí significa "de grado artbook" (papel), no "esto es un artbook". Filtrando
por la construcción de grado (`畫冊等級`/`畫冊級`) el resultado es **21 de 21 falsos
positivos, 0 legítimos**: los 18 tomos numerados de *鋼之鍊金術師完全版* más sus 3 box
sets. Detalle, blast radius y el guard propuesto en **gotcha #229**. No aplicado
(toca `product_type` → `edition_key` → slugs).

Corolario de lectura: **un `artbook` de esta fuente no es de fiar sin mirar el
título.** Los artbooks reales sí se distinguen — llevan 畫冊/畫集/作品集/ILLUSTRATIONS
en el nombre (*INOUE TAKEHIKO ILLUSTRATIONS*, los tres 畫冊 de *Gochiusa*,
*東京喰種【ZAKKI:re】*).

### Otra cosa a tener en cuenta

Los títulos traen el tomo entre paréntesis a la tailandesa/taiwanesa (`(03)`,
`(18)完`, `(01~09冊)`) y `完` marca cierre de serie, no un tipo de edición. El
`series_key` de la mayoría de estos items quedó vacío (`None`) porque entraron crudos:
no juzgar la agrupación de esta fuente antes de estandarizar.

### Resolución operativa — 2026-09-27

Corregido el falso artbook por `畫冊等級`/`畫冊級`. Se repararon 21 filas sin cambiar URLs ni slugs: 18 mangas premium y 3 box sets. `Chino tradicional` se publica como idioma canónico `Chino`, conservando `language_variant: tradicional`; así aparece en el filtro de idioma sin perder la variante.
