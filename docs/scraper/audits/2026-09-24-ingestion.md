# Auditoría de ingestión — 2026-09-24

## Cierre de la continuación — 2026-09-25

**Catálogo local: 18 542 productos.** Esta continuación publicó **2453 altas**
(16 089 → 18 542), reparó **113 referencias incorrectas**, incorporó **343
referencias nuevas** y unió otras **12 referencias** a fichas existentes en lugar
de duplicarlas. Cuatro títulos VIZ perdieron únicamente su prefijo de navegación.
Desde el inicio de la auditoría: **14 608 → 18 542 (+3934 productos)**.
Todas las URLs primarias anteriores se conservaron; las nuevas filas siguen crudas.

**Validación final: cero violaciones duras; 2711 pruebas aprobadas.** Web reconstruida.
No hay spool ni conflictos de ingestión pendientes en producción ni en los
recorridos terminados. Backups, hashes, cambios por URL y logs en
`reports/ingestion-audit-2026-09-24/closure/`; cada publicación tiene su manifest.

Terminaron PRH Comics, BlogBBM, Manga México, Sumikko, Shueisha, Kinokuniya,
Kim Đồng, IPM, Yaakz, AnimeClick (614 semanas), VIZ (con recuperación explícita
de fallos 429), Yen Press, Manga Sanctuary, Otaku Calendar, Manga-Passion y
ListadoManga (3469 colecciones). Panini también terminó: 246 páginas únicas del
catálogo italiano y 119 del español, más todas las búsquedas configuradas y las
categorías italianas especializadas (8 +12 páginas). La reanudación Panini cerró
con cero errores; el proceso previo interrumpido no se presenta como un run verde.

Correcciones adicionales: conflictos sin spool reintentables; fronteras y topes
semanales de AnimeClick; Shueisha y VIZ exponen enlaces/esquemas rotos; ISBN
válidos diferentes impiden absorber otra edición (checksum validado también
antes de convertir ISBN-10); cada página HTML queda guardada antes de continuar.
Panini reutiliza sesión pública del navegador, incluye productos fuera del filtro
de disponibilidad y acepta títulos simples en categorías oficiales especializadas.
Calendarios incluyen tres meses futuros; un import solo futuro no adelanta
checkpoint. Otaku y Manga Sanctuary full inician en 2010 tras verificar archivo
histórico. Kaiju No. 8 no confunde el número de serie con el tomo; los productos
creados desde extras de ListadoManga aplican la misma normalización de títulos.

### Límites que permanecen

- **SocialAnime, Seven Seas y SPP:** feeds automatizados sin recuperación
  verificada. Las páginas HTML de los dos primeros cargan en navegador normal,
  lo cual no demuestra que el job automatizado funcione.
- **Metadatos ausentes:** autor en 11 342 filas, ISBN en 10 684, fecha en 4076 e
  imágenes en 813. No se inventaron valores ni se ejecutó estandarización LLM.
- **88 URLs compartidas entre fichas:** no se asumió que toda coincidencia fuera
  un error. Los casos demostrables por ISBN/volumen se repararon; los restantes
  conservan sus datos y la ingestión difiere las entradas ambiguas.
- **Cache histórico:** 5400 URLs con score ≥20 no están en el corpus ni en la
  blacklist consultada por el auditor. Esto no equivale a 5400 productos perdidos
  (incluye descartes y referencias históricas); la reconciliación evita tratarlas
  automáticamente como productos ya guardados. No se importaron ciegamente.


---

## Resultado de la segunda pasada «arregla todo»

**Catálogo local: 16,089 productos.** Esta continuación incorporó
**1,334 productos adicionales**, todos crudos, y reparó
**176 asociaciones incorrectas** entre fuentes y productos. Sumada a la primera
pasada: **14 608 → 16,089 (+1,481)**, conservando las URLs
primarias previas. Se generaron slugs y se reconstruyó la web. El gate final
reporta **cero violaciones duras** y la suite completa **2 682 pruebas aprobadas**.

### Correcciones adicionales

- Entrada de raíz: corregido el import que fallaba al guardar el primer candidato.
- Identidad: números chinos, polacos, alemanes y coreanos; rangos preservados;
  ediciones inferidas sin volumen y variantes crudas conservadas por URL.
  Un conflicto de volumen o cubierta precede al ISBN al resolver referencias.
- Paginación: SPP no corta por overlap entre búsquedas; límites de catálogo y
  esquemas inesperados ya se reportan. Kodansha no interpreta un total ausente
  como cero. Sanyodo no recorre «siguiente noticia» como catálogo.
- Delta: Seven Seas usa modificación del post; checkpoints por wiki confirmados
  solo después de ambos sinks, con replay de la interrupción y solapamiento.
- Errores: otros 14 parsers registran fallos de red; HTML de challenge no pasa
  como catálogo vacío exitoso. Los conflictos de identidad se guardan en cola
  durable, se reintentan y no bloquean los demás productos ni avanzan checkpoint.
- Sitemaps: evitar doble descompresión del transporte gzip.
- Calidad: tres cajas de cartas descartadas antes de publicar; los tomos con
  booster como bonus siguen admitidos. No se borraron productos del catálogo.
- Panini: Queue-it activa Chromium con `--enable-js`; recuperación verificada
  de 27 productos de las dos categorías italianas y la búsqueda española deluxe.

### Evidencia viva y límites

Se recorrieron las **140 entradas expandidas** del YAML en staging. Se corrigió
y repitió Sanyodo; Kadokawa Taiwán reanudó desde la página 54 y completó otras
31 páginas sin error tras bajar la concurrencia. KADOKAWA artbooks recorrió
184 páginas; altraverse 84; Manga Dreams 40; Funside 15; Aladin 18. Se importaron
catálogos API de Jade Dynasty (293 candidatos) y Kodansha US (243 candidatos).
La corrida principal se interrumpió al diagnosticar la navegación errónea de
Sanyodo: los **4 094 registros del spool** se conservaron y reprocesaron con las
reglas corregidas. No se presenta ese proceso interrumpido como un run verde.

Panini IT variantes completó 4 páginas/81 candidatos y cofanetti 9/209; Panini ES
deluxe 1/12. Sus 179 reportables finalizaron sin errores. El resto de búsquedas
españolas tendrá el fallback en su próxima corrida; no se ha probado un full de
todas ellas con navegador. Tampoco se recorrió todo el histórico de los 27 wikis.

**Bloqueos externos restantes:** SocialAnime, Seven Seas y SPP devuelven 403
mediante requests, Chromium y la prueba de transporte con fingerprint Chrome.
No se añadió esa dependencia de prueba al proyecto. Estas fuentes conservan su
histórico, siguen habilitadas y reportan fallo; no se declara que funcionen.

La auditoría posterior registra **127 URLs compartidas**
(frente a 185 iniciales), **0 filas de spool** y
**0 conflictos de ingestión pendientes**.
Una URL histórica compartida no demuestra por sí sola un duplicado; no se
fusionaron productos ni se inventó metadata para borrar esa advertencia.
Autor, ISBN y fechas aún pueden estar ausentes cuando la fuente no los entrega.

Backups exactos de ambas publicaciones:
- `/Users/Shared/Proyectos/manga-watch/data/backups/items.jsonl/items.jsonl.20260925-032939.pre-ingestion-followup-bak`
- `/Users/Shared/Proyectos/manga-watch/data/backups/items.jsonl/items.jsonl.20260925-033558.pre-ingestion-followup-bak`

Evidencia y productos recuperados: `reports/ingestion-audit-2026-09-24/followup/`.
Los manifiestos incluyen hashes previos/finales, URLs incorporadas y cambios de
proveniencia. La publicación comprobó el hash previo bajo lock exclusivo.

---

## Primera pasada (registro histórico)

Estado del código y los datos locales, incluidos los cambios previos sin commit. El
catálogo inicial tenía **14 608 productos**, 25 338 entradas de caché, 1 555 URLs
secundarias y ningún spool pendiente. Validación inicial: cero violaciones duras.

## Alcance y evidencia

- Revisión de los dos orquestadores, cache/dedup, upsert, spool, filtros, hashing,
  paginación, parsers wiki, señales de error, retrofits y modelo del catálogo.
- Revisión histórica de cinco corridas y del inventario completo de fuentes.
- Sondeo HTTP real de **140 entradas expandidas** del YAML: una página por entrada,
  sin escritura de catálogo ni descarga de imágenes. No prueba páginas posteriores;
  Glénat Art Books requiere JS y no fue renderizada en este sondeo.
- Reingesta de Mangavariant incremental y catálogo API completo de Meian en copia
  aislada; validación de corpus y asignación de slugs a las nuevas filas.
- Comprobación HTTP directa de SocialAnime, Seven Seas y SPP: las tres devolvieron
  403. Las dos primeras sirven Cloudflare; SPP devuelve un cuerpo de CloudFront.
- Auditorías de calidad, overlap y contraste cache/corpus; evidencia durable en
  `reports/ingestion-audit-2026-09-24/`. Las ausencias de autor/ISBN/fecha son
  incompletitud de metadata, no prueba de pérdida de productos.

## Fallos corregidos

| Prioridad | Fallo | Corrección y prueba |
|---|---|---|
| P1 | Cleanup expulsaba variantes curadas recién ingresadas | Compartir bypass de fuentes curadas después de gates duros; dry-run real pasa de 134 rechazados a 147/147 conservados. |
| P1 | Un `seen` ausente del catálogo no podía reingresar | Reconciliar caché con TODAS las URLs del corpus/spool antes de decidir; conservar rechazos explícitos. Recuperación real de 149 candidatos Mangavariant. |
| P1 | URL secundaria generaba otro producto crudo | Índice de fuentes secundarias que actualiza la fila canónica. Una URL ambigua aborta la escritura sin borrar datos: requiere revisión. |
| P1 | JSONL/spool malformado se omitía al reescribir | Lectura estricta con archivo y línea; conservar originales y spool ante error. |
| P1 | Bloqueo en página siguiente descartaba páginas ya adquiridas | Guardar los candidatos parciales antes de abandonar la fuente. |
| P1 | Full usaba límites de páginas de delta | `--full-catalog`: seguir siguiente página hasta agotarla, tope de seguridad 1000 visible; full usa hasta 10 000 cards por página. No crea histórico ausente del sitio. |
| P1 | Meian API registrada pero fuera de ambas rutinas | Paso explícito en full y delta, con timeout y registro de resultado. |
| P1 | Fallos de wiki y corridas parciales terminaban exitosos | Reporte común de incidencias en módulos corregidos, errores/tracebacks/ausencia de resumen en salud, exit no cero del scraper y orquestadores. |
| P1 | Variantes PT-BR eran expulsadas por falta de vocabulario | `capa variante` y `capa alternativa` son `variant_cover`; pruebas con títulos reales. |
| P2 | Metadata vacía borraba ISBN/autor/fecha de estandarizados | Preservar valores existentes cuando la entrada no tiene valor. |
| P2 | Reingesta borraba fecha original y contador de revisión | Preservar `detected_at` y `standardize_attempts` también en productos crudos. |
| P2 | Cambios solo de portadas/extras no disparaban delta | Incluir imágenes remotas y extras en hash; excluir rutas locales. |
| P2 | Mangavariant delta no refrescaba productos conocidos | Ventana de `lastmod` de siete días y orden global por recencia para nuevas y actualizadas; límite visible. |
| P2 | Queue-it era diagnosticado como página vacía/JS | Clasificar por host de redirección como challenge; no confundir con fuente sin novedades. |
| P2 | `search: término` rompía el nombre en SKIP | Preservar nombre completo; evitar fuentes fantasma. |
| P2 | `--include-seen` reportaba pero no escribía | El sink también persiste las filas vistas cuando se solicita expresamente. |
| P2 | Fechas italianas abreviadas no entraban | Reconocer `Fumetti dd/mm/yy`, validar calendario y convertir a ISO; no interpretar fechas ambiguas sin contexto. |
| P2 | Fallo de backup permitía mutaciones sin respaldo | Abortar la rutina antes de tocar datos si falla el backup inicial. |
| P2 | `--data-dir` alternativo escribía cola en datos reales | Dirigir también `unmapped_series` al directorio elegido. |

## Cobertura real de full y delta

Ambos comparten parser y reglas. Full explora páginas de listados, no una copia
universal de todo lo alguna vez publicado. RSS/homepages/búsquedas solo permiten
recuperar lo que la fuente expone. ListadoManga full descubre por `lista.php`; delta
por calendario reciente/futuro. Mangavariant full lee sitemaps; delta nuevas URLs y
modificaciones de siete días. Meian recorre el catálogo en ambos. Los demás módulos
conservan sus estrategias específicas (calendarios, APIs, listados y límites).

Un tope, una caída o un bloqueo producen ejecución parcial, no evidencia de que el
catálogo de origen se haya agotado. No se ejecutó una ingestión full mundial de
varias horas en producción; la matriz inferior distingue sondeo actual e histórico.

## Limitaciones y pendientes verificables

1. **Bloqueos externos vigentes:** SocialAnime/Seven Seas/SPP y Queue-it intermitente
   de Panini. El código ahora informa el fallo, pero eso no elimina el bloqueo. No
   se declara restaurada la cobertura de estas fuentes.
2. **Cache divergente no equivale a pérdida confirmada:** 8 521 URLs ausentes sin
   rechazo explícito (6 140 con score histórico >=20). Incluye descartes legítimos
   por reglas posteriores; se reevalúan con reglas vigentes, nunca se importan los
   8 521 registros directamente desde caché.
3. **185 URLs compartidas por varias filas:** algunas son referencias compartidas,
   otras pueden ser duplicados. No se fusionan por ISBN o publisher desconocido sin
   evidencia de identidad. El nuevo índice rechaza matches secundarios ambiguos.
4. **Metadata pendiente inicial:** autor 7 522, ISBN 7 879, fecha 3 013, imágenes 251.
   El arreglo evita perder metadata presente; no inventa lo que la fuente no da.
5. **Ventanas de delta:** una novedad histórica fuera del calendario o una modificación
   de sitemap fuera de siete días necesita full. No existe garantía de captura de
   entradas publicadas y retiradas entre dos corridas.
6. **Wikis no reejecutadas completas:** el histórico y la revisión estática no
   reemplazan un barrido vivo completo. Límites internos y errores de fuentes
   no incluidas en las reingestas siguen sujetos al comportamiento de cada módulo.
7. Delcourt cero no prueba selector roto: su ficha documenta que el rendimiento
   anterior dependía de una coincidencia fuzzy espuria. No se deshabilitó ninguna
   fuente ni se podó cobertura basándose solo en cero candidatos u overlap.

## Recuperación aplicada al catálogo

Con backup fechado y comprobación SHA-256 bajo lock antes de publicar:
**14 608 → 14 755 productos (+147)**. Se incorporaron 143 de Mangavariant,
dos coffrets The One de Meian y dos variantes Wotakoi de Panini Brasil.
**150 fechas faltantes de Panini Italia** se recuperaron de `Fumetti dd/mm/yy`.
Los 147 sobreviven a ambos filtros posteriores, verificado por dry-run real.
No se borró ningún producto previo ni se ejecutó estandarización LLM; las altas
quedan crudas con slug y trazabilidad, listas para el proceso habitual.

La reingesta aislada también sirvió como control de falsos positivos/negativos:
23 productos occidentales de Panini se excluyeron antes de publicar. El gate
non-manga ahora corre antes del spool y del sink, incluidos resultados de
selectores. `bestseller` solo no demuestra que un libro sea novela y dejó de ser
un motivo de expulsión; se conservan señales literarias explícitas y BookTok.
En Mangavariant, la identidad estructural de serie (`mv-series:` + URL de producto
canónica + `variant-catalog`) evita expulsar Akira por el distribuidor Marvel o
variantes crossover por nombrar Avengers/Mickey Mouse. No es un bypass para
retailers ni reemplaza los rechazos explícitos del usuario.

Manifest, backup exacto y verificaciones: `reports/ingestion-audit-2026-09-24/`.
Validación de la publicación: cero violaciones duras. Web reconstruida.
Suite completa final: **2 636 tests passed**. Nueve warnings (siete de buffer
subprocess y dos del HTML mínimo de fixtures); ningún fallo. Bash y compilación
Python también correctos.

## Matriz de fuentes

`Productos` cuenta procedencias únicas por producto del corpus inicial. `Histórico`
es la clasificación de cinco corridas (heurística, no certificación). `Sondeo`
corresponde a una sola página sin fuzzy ni JS; `—` significa no sondeada, no avería.
Búsquedas expandidas se presentan por separado para hacer visible la cobertura.

| Fuente | Productos | Histórico | Sondeo actual |
|---|---:|---|---|
| AR - Distrito Manga (Cúspide) | 9 | healthy | ok |
| AR - Ivrea Argentina | 14 | healthy | no-candidates |
| AR - Kemuri Ediciones | 2 | healthy | ok |
| BR - Editora JBC Checklist | 17 | healthy | ok |
| BR - NewPOP Lançamentos | 1 | healthy | no-candidates |
| BR - Panini Brasil (search) [search: anniversary] | 0 | healthy | ok |
| BR - Panini Brasil (search) [search: box] | 0 | healthy | ok |
| BR - Panini Brasil (search) [search: boxset] | 0 | healthy | ok |
| BR - Panini Brasil (search) [search: capa dura] | 0 | healthy | ok |
| BR - Panini Brasil (search) [search: capa variante] | 1 | healthy | ok |
| BR - Panini Brasil (search) [search: deluxe] | 12 | healthy | ok |
| BR - Panini Brasil (search) [search: edicao colecionador] | 0 | healthy | ok |
| BR - Panini Brasil (search) [search: edicao definitiva] | 18 | healthy | ok |
| BR - Panini Brasil (search) [search: edicao especial] | 1 | healthy | ok |
| BR - Panini Brasil (search) [search: edicao limitada] | 2 | healthy | ok |
| BR - Panini Brasil (search) [search: encadernado] | 0 | healthy | ok |
| BR - Panini Brasil (search) [search: kanzenban] | 9 | healthy | ok |
| BR - Panini Brasil (search) [search: kit] | 0 | healthy | ok |
| BR - Panini Brasil (search) [search: tarot] | 0 | healthy | ok |
| BR - Panini Brasil (search) [search: tribute] | 0 | healthy | ok |
| BR - Panini Brasil (search) [search: variante] | 1 | healthy | ok |
| BR - Pipoca & Nanquim | 1 | healthy | ok |
| CZ - Crew Manga | 4 | healthy | ok |
| DE - Egmont Luxusausgaben | 12 | healthy | ok |
| DE - TOKYOPOP (search limited) | 40 | healthy | ok |
| DE - TOKYOPOP Jubiläumseditionen | 11 | healthy | ok |
| DE - altraverse Collectors Edition | 28 | healthy | ok |
| DE - altraverse Manga mit Box | 14 | healthy | ok |
| ES - Arechi Manga Próximamente | 0 | healthy | no-candidates |
| ES - Milky Way (search) [search: deluxe] | 2 | healthy | ok |
| ES - Milky Way (search) [search: edicion especial] | 2 | healthy | ok |
| ES - Milky Way (search) [search: edicion limitada] | 12 | healthy | ok |
| ES - Milky Way (search) [search: kanzenban] | 0 | selector_dead | no-candidates |
| ES - Milky Way (search) [search: tapa dura] | 2 | healthy | ok |
| ES - Milky Way Próximamente | 0 | healthy | no-candidates |
| ES - Norma Editorial Manga | 6 | healthy | ok |
| ES - Panini España (search) [search: aniversario] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: anniversary] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: celebration] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: cofre] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: deluxe] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: edicion coleccionista] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: edicion especial] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: edicion limitada] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: kanzenban] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: master edition] | 12 | broken_skip | empty |
| ES - Panini España (search) [search: portada variante] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: tapa dura] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: tarot] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: tribute] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: ultimate edition] | 0 | broken_skip | empty |
| ES - Panini España (search) [search: variante] | 0 | broken_skip | empty |
| ES - Panini Manga España | 1 | healthy | no-candidates |
| ES - Pika Ediciones | 0 | healthy | ok |
| ES - Planeta Cómic | 2 | healthy | ok |
| FR - Delcourt / Tonkam Mangas | 8 | selector_dead | no-candidates |
| FR - Glénat Art Books | 15 | healthy | js-shell |
| FR - Glénat Manga Nouveautés | 7 | healthy | no-candidates |
| FR - Kana | 3 | healthy | ok |
| FR - Pika Livres / Artbooks | 10 | healthy | ok |
| FR - Pika Édition | 3 | healthy | ok |
| IT - Dynit | 5 | healthy | ok |
| IT - Edizioni BD (search) [search: cofanetto] | 1 | healthy | ok |
| IT - Edizioni BD (search) [search: deluxe] | 0 | healthy | ok |
| IT - Edizioni BD (search) [search: edizione limitata] | 0 | healthy | ok |
| IT - Edizioni BD (search) [search: edizione speciale] | 0 | healthy | ok |
| IT - Edizioni BD (search) [search: variant] | 1 | healthy | ok |
| IT - Funside Variant | 153 | healthy | ok |
| IT - Manga Dreams | 97 | healthy | ok |
| IT - Manga Dreams (variants europeas) | 44 | healthy | ok |
| IT - Panini Edizioni da Collezione e Cofanetti | 106 | broken_skip | empty |
| IT - Panini Planet Manga | 58 | healthy | ok |
| IT - Panini Variant ed Esclusive | 22 | broken_skip | ok |
| IT - Star Comics (search) [search: anime comics pack] | 0 | healthy | ok |
| IT - Star Comics (search) [search: anniversary edition] | 7 | healthy | ok |
| IT - Star Comics (search) [search: celebration edition] | 6 | healthy | ok |
| IT - Star Comics (search) [search: cofanetto] | 4 | healthy | ok |
| IT - Star Comics (search) [search: collector] | 13 | healthy | ok |
| IT - Star Comics (search) [search: deluxe] | 6 | healthy | ok |
| IT - Star Comics (search) [search: tiratura limitata] | 2 | healthy | ok |
| IT - Star Comics (search) [search: tribute cover] | 0 | healthy | ok |
| IT - Star Comics (search) [search: tribute variant] | 0 | healthy | ok |
| IT - Star Comics (search) [search: variant cover edition] | 0 | healthy | ok |
| IT - Star Comics (search) [search: variant cover] | 9 | healthy | ok |
| IT - Star Comics (search) [search: variant] | 64 | healthy | ok |
| IT - Star Comics Manga | 19 | healthy | ok |
| JP - KADOKAWA Store | 8 | healthy | ok |
| JP - KADOKAWA Store Artbooks Fanbooks | 92 | healthy | ok |
| JP - Rakuten Books (search) [search: グッズ付き] | 20 | healthy | ok |
| JP - Rakuten Books (search) [search: 初回限定] | 42 | healthy | ok |
| JP - Rakuten Books (search) [search: 数量限定] | 13 | healthy | ok |
| JP - Rakuten Books (search) [search: 特典付き] | 24 | healthy | ok |
| JP - Rakuten Books (search) [search: 特装版] | 100 | healthy | ok |
| JP - Rakuten Books (search) [search: 画集] | 55 | healthy | ok |
| JP - Rakuten Books (search) [search: 限定版] | 56 | healthy | ok |
| JP - Sanyodo Comic Limited Editions | 169 | healthy | ok |
| KR - Aladin (만화 한정판) | 439 | healthy | ok |
| MX - Editorial Kamite | 1 | healthy | ok |
| MX - Manga México (catálogo wiki) | 2 | healthy | ok |
| MX - Panini México (search) [search: aniversario] | 0 | healthy | ok |
| MX - Panini México (search) [search: anniversary] | 0 | healthy | ok |
| MX - Panini México (search) [search: boxset] | 28 | healthy | ok |
| MX - Panini México (search) [search: celebration] | 1 | healthy | ok |
| MX - Panini México (search) [search: cofre] | 0 | healthy | ok |
| MX - Panini México (search) [search: deluxe] | 0 | healthy | ok |
| MX - Panini México (search) [search: edicion coleccionista] | 5 | healthy | ok |
| MX - Panini México (search) [search: edicion especial] | 1 | healthy | ok |
| MX - Panini México (search) [search: edicion limitada] | 2 | healthy | ok |
| MX - Panini México (search) [search: gran formato] | 0 | healthy | ok |
| MX - Panini México (search) [search: kanzenban] | 3 | healthy | ok |
| MX - Panini México (search) [search: portada variante] | 2 | healthy | ok |
| MX - Panini México (search) [search: tapa dura] | 0 | healthy | ok |
| MX - Panini México (search) [search: tarot] | 1 | healthy | ok |
| MX - Panini México (search) [search: tribute] | 0 | healthy | ok |
| MX - Panini México (search) [search: variante] | 2 | healthy | ok |
| MX - Panini México Boxsets | 30 | healthy | ok |
| MX - Panini México búsqueda edición especial | 4 | healthy | ok |
| PL - Mangarden (JPF preorders) | 56 | healthy | ok |
| PL - Mangarden (JPF tapa dura) | 223 | healthy | ok |
| PL - Mangastore (twarda) | 71 | healthy | ok |
| TR - Gerekli Şeyler (varyant) | 8 | healthy | ok |
| TW - Kadokawa Taiwan (特裝/限定) [search: 典藏] | 12 | healthy | ok |
| TW - Kadokawa Taiwan (特裝/限定) [search: 特裝] | 135 | healthy | ok |
| TW - Kadokawa Taiwan (特裝/限定) [search: 限定] | 49 | healthy | ok |
| US - Dark Horse Direct (search) [search: boxset] | 0 | low_yield | no-candidates |
| US - Dark Horse Direct (search) [search: deluxe] | 1 | healthy | ok |
| US - Dark Horse Direct (search) [search: exclusive] | 2 | healthy | no-candidates |
| US - Dark Horse Direct (search) [search: hardcover] | 9 | healthy | ok |
| US - Dark Horse Direct (search) [search: limited edition] | 0 | healthy | ok |
| US - Dark Horse Direct (search) [search: slipcase] | 0 | selector_dead | no-candidates |
| US - Dark Horse Direct (search) [search: variant] | 0 | selector_dead | no-candidates |
| US - Dark Horse Direct Manga | 6 | healthy | ok |
| US - Square Enix Manga Coming Soon | 6 | healthy | ok |
| US - VIZ Media (search) [search: VIZBIG] | 31 | healthy | ok |
| US - VIZ Media (search) [search: box set] | 33 | healthy | ok |
| US - VIZ Media (search) [search: collector] | 24 | healthy | ok |
| US - VIZ Media (search) [search: complete edition] | 0 | healthy | ok |
| US - VIZ Media (search) [search: definitive] | 9 | healthy | ok |
| US - VIZ Media (search) [search: deluxe] | 6 | healthy | ok |
| US - VIZ Media (search) [search: hardcover] | 25 | healthy | ok |
| wiki:animeclick | — | healthy | — |
| wiki:blogbbm | — | healthy | — |
| wiki:booksprivilege | — | unseen | — |
| wiki:ipm | — | healthy | — |
| wiki:jd-intl | — | healthy | — |
| wiki:kimdong | — | healthy | — |
| wiki:kinokuniya | — | healthy | — |
| wiki:kodansha-us | — | healthy | — |
| wiki:listadomanga | — | unseen | — |
| wiki:listadomanga-blog | — | unseen | — |
| wiki:listadomanga-collections | — | healthy | — |
| wiki:manga-mexico | — | healthy | — |
| wiki:manga-sanctuary | — | healthy | — |
| wiki:mangapassion | — | healthy | — |
| wiki:mangavariant | — | healthy | — |
| wiki:meian | — | unseen | — |
| wiki:otaku-calendar | — | healthy | — |
| wiki:prhcomics | — | healthy | — |
| wiki:sevenseas | — | broken_http | — |
| wiki:shueisha | — | healthy | — |
| wiki:socialanime | — | broken_http | — |
| wiki:spp-tw | — | selector_dead | — |
| wiki:sumikko | — | healthy | — |
| wiki:viz | — | healthy | — |
| wiki:whakoom | — | unseen | — |
| wiki:yaakz | — | healthy | — |
| wiki:yenpress | — | healthy | — |
