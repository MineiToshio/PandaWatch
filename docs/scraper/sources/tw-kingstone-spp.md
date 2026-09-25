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
