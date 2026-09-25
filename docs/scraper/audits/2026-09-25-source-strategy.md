# Auditoría estratégica de ingestión y fuentes — 25 de septiembre de 2026

## Objetivo y alcance

Catálogo de ediciones físicas especiales, limitadas y premium de manga, manhwa y manhua, incluidos box sets y artbooks. Por confirmación expresa del propietario se conservan también novelas ligeras y danmei premium. Se excluyen cómics occidentales, merchandising independiente, ebooks y tomos ordinarios sin valor coleccionable demostrado. No se abordó la mejora de imágenes ni se ejecutó estandarización/enriquecimiento LLM.

Se revisaron el registro completo de fuentes, módulos wiki, wrappers full/delta, rutina diaria de Claude Code, contribución observada del corpus, tres ejecuciones diarias y los mecanismos de identidad y persistencia. Se hicieron nuevas recorridas históricas de cuatro fuentes modificadas. Esto complementa la [auditoría técnica anterior](2026-09-24-ingestion.md); no representa una prueba nueva de red de cada endpoint ni certifica cobertura mundial completa.

## Resultado en datos

Base de integración: **18.479 productos**. La rutina diaria independiente actualizó la base inicial de 18.542 mientras corría esta auditoría; se volvió a leer su resultado y se preservaron sus cambios.

Resultado validado: **19.378 productos**, incremento neto de **899 filas**. No todas equivalen a títulos nuevos: hay **842 productos sin ninguna URL previamente asociada**; otros reaparecen al separar identidades antes fusionadas. Se apartaron **37 registros fuera de alcance** y se corrigieron **11 clasificaciones**. Los excluidos se archivan con motivo y se conserva respaldo completo; retirar una fuente no borra su histórico.

| Recorrido aislado | Resultado comprobado | Admitidos para integrar |
|---|---|---:|
| PRH Comics: Manga + Seven Seas | 1.374 tarjetas, 105 candidatos, 104 productos; delta posterior 0 nuevos/cambiados | 104 |
| Kingstone: catálogo de la editorial SPP | 498 páginas, 9.943 candidatos; recuperación de 693 SKUs físicos tras excluir ebooks | 690 |
| Delcourt/Tonkam | 150 páginas, 2.878 candidatos, 125 admitidos antes de revisión final | 96 |
| Manga-Sanctuary | 204 meses, enero 2010–diciembre 2026; 2.168 candidatos, 2.129 filas consolidadas | 2.129 |

Estos números son por fuente y **no se suman como altas netas**, pues incluyen productos existentes e intersecciones. Kingstone se exploró antes de completar el filtro digital: los ebooks permanecieron en el entorno aislado y nunca se publicaron en el corpus activo. Se reconstruyeron siete SKUs físicos indebidamente absorbidos por otros productos, usando el estado original y páginas de detalle.

## Decisiones sobre las fuentes

Inventario final: **152 entradas YAML, 55 activas y 139 endpoints expandidos**; **27 parsers wiki, 21 activos**. Se mantienen los mercados principales actuales; no se añadió un país sin una fuente implementada y verificada.

| Fuente o grupo | Decisión y fundamento |
|---|---|
| Kingstone / SPP Taiwán | Nueva fuente comercial verificable, restringida al catálogo de la editorial SPP; excluye ebooks. Cubre parte del hueco del sitio editorial bloqueado. |
| PRH Comics | Ampliado al catálogo seleccionado de Seven Seas, además de Manga. Distribuidor oficial; cobertura parcial, no todo el fondo histórico de Seven Seas. |
| Delcourt/Tonkam | Reparada la URL de listado y los selectores; el HTML anterior respondía 200 pero no rendía productos. Se excluyen recomendaciones de BD fuera del catálogo de mangas. |
| Manga-Sanctuary | Conservada como catálogo estructurado y recorrida histórica repetida; reparadas etiquetas françaises `spéciale` y `unlimited double`. |
| Seven Seas directo, SPP directo y SocialAnime | Retirados de ejecución administrada por bloqueo persistente 403. Se conserva histórico y documentación. PRH/Kingstone son alternativas parciales; no se declara equivalencia total. |
| ES Pika / Hablamos de Libros | Deshabilitada entrada de noticias erróneamente etiquetada como oficial. No confundir con la editorial francesa Pika, que sigue activa. |
| Manga México HTML genérico | Deshabilitado el recorrido de homepage redundante; se mantiene el parser de listas estructuradas confirmadas. |
| Listadomanga calendario antiguo/blog y Whakoom | Excluidos del registro administrado: rutas sustituidas, noticias o automatización no fiable. El catálogo Listadomanga Collections continúa activo. |
| Kana, Pika, VIZ, Kodansha, Kinokuniya y catálogos oficiales complementarios | Se conservan. Una intersección elevada de las filas observadas no prueba que otra fuente cubra todo su universo ni sus próximas exclusivas. |
| Funside | Sigue como retailer; se elimina el nombre de la tienda del campo editorial. |

La herramienta de overlap ahora informa `overlap_alto`, no recomienda baja automática con un umbral del 70%, y declara que **no hay evidencia suficiente para retirar**. Las muestras de Kana (3) y Pika (10) compartidas con Manga-Sanctuary son demasiado pequeñas para demostrar cobertura total. Tampoco se supone que Listadomanga cubra todas las exclusivas españolas.

Alternativas exploradas no activadas: Books.com.tw seguía bloqueado; TongLi corresponde a otra editorial y no sustituye SPP; una selección adicional de hardcovers de PRH no expuso las tarjetas estáticas que necesita el parser. No se añadieron fuentes de relleno sin una ingestión funcional.

## Correcciones de full y delta

- Política central `ingestion_policy.yml`: el estado de una entrada YAML ya no es la única referencia; los parsers wiki tienen habilitación y motivo de retirada explícitos.
- Recibos durables por fuente/configuración y umbral de score. Un delta sin full compatible ejecuta primero el histórico configurado. Si cambia la configuración relevante o el umbral, exige nueva verificación completa.
- El recibo requiere escritura persistida, recorrido terminado y ausencia de errores de la fuente. No se certifican ejecuciones secas, parciales o truncadas. Un endpoint vacío no demuestra cobertura.
- Los listados HTML administrados recorren su paginación también en delta y comparan contenido. Evita perder altas insertadas en páginas antiguas. Existen límites de seguridad y tiempo; alcanzarlos no debe parecer éxito completo.
- Los módulos con calendario usan checkpoints y ventana de repetición; PRH ya no descarta un producto recién incorporado por tener una fecha de publicación antigua.
- El wrapper diario amplía el presupuesto temporal cuando necesita el full inicial. La rutina de Claude Code conoce el nuevo comportamiento y conserva sus límites de estandarización LLM.

Se trasladan únicamente los recibos de los cuatro recorridos comprobados. **Las demás fuentes sin recibo compatible deberán verificar su full en su siguiente ejecución administrada.** Por eso el primer ciclo posterior puede durar bastante más que un delta habitual. Un recibo acredita el endpoint/rango configurado, no todo lo publicado históricamente por una editorial.

## Identidad, intersecciones y filtros

La coincidencia aproximada de serie/tomo no puede prevalecer sobre ISBN válidos distintos, mercados distintos, variantes de portada explícitas, box set frente a tomo, partes chinas diferentes o SKUs diferentes de Kingstone. Las URLs secundarias se actualizan sin absorber una edición contradictoria. Se conserva procedencia y URL canónica, y se recalcula correctamente la clave de identidad protegida.

Se recuperaron versiones separadas de Gundam Origin y Vinland Saga que tenían ISBN distintos. En Taiwán, la última entrega de una serie podía confundirse con una caja completa; también se fusionaban tomos del mismo número de partes distintas. Ahora se preservan. **210 registros llevan marca `identity_review_required`**: es una señal explícita de que una agrupación anterior tenía evidencia contradictoria; no se borran para hacer desaparecer la advertencia. La armonización editorial de sus nombres/ediciones continúa en el proceso de curación existente.

Se apartaron 10 cómics occidentales, 22 tomos regulares de Medaka-Box y 5 Gurren Lagann Double Edition ordinarios. Se corrigieron 10 Air Gear Unlimited y una edición especial de Medaka-Box. Se añadió rechazo de etiquetas digitales; `漫畫集` no se interpreta como artbook por contener `畫集`. Double/Triple Edition por sí solo no acredita una edición premium; otros atributos comprobados pueden hacerla admisible.

Air Gear Unlimited se conserva por extras, páginas a color y nuevas cubiertas confirmados por [Pika](https://www.pika.fr/actualite/air-gear-unlimited-arrive-dans-la-collection-pika-shonen/), sin inventar tirada limitada. El formato regular de Gurren Lagann Double Edition se comprobó en el [catálogo oficial de Panini A415](https://www.panini.it/media/paniniFiles/A415.pdf).

## Validación y límites

- Recorridos de red aislados y logs por fuente; replay de la integración conserva 19.378 identidades y asociaciones de fuentes sin crecimiento.
- PRH full seguido de delta real sin productos nuevos/cambiados.
- **2.750 pruebas aprobadas**, cero violaciones estructurales duras tras publicar y dashboard HTML reconstruido. Resultados y hashes en el manifest y `reports/source-strategy-2026-09-25/logs/`.
- Publicación con bloqueo de escritura, comparación del hash de la base y backup previo. No se sobrescriben cambios de una rutina concurrente.
- La salud de tres ejecuciones diarias es evidencia histórica: Delcourt estaba vacío antes del arreglo y Kingstone no existía. Algunos términos de búsqueda válidos pueden no tener resultados. Las protecciones anti-bot y errores transitorios de VIZ/Kodansha siguen siendo condiciones externas observables, no se presentan como fuentes perfectas.
- El cruce final de caché detecta **112 URLs históricas sin fila vigente**, algunas pertenecientes a productos descartados por los filtros. No se reinsertan desde el caché como si fueran productos verificados: `reconcile_ingestion_state` ya las invalida en memoria al arrancar la siguiente ingesta para reevaluarlas con la fuente y los gates actuales. El detalle queda en `published-integrity.json`. Hay además **91 URLs de procedencia compartidas**; pueden ser referencias de colección y no justifican fusionar productos distintos.
- No se promete catálogo completo de todos los países, cobertura total de Seven Seas/SPP ni metadata curada de todos los registros. Los nuevos registros crudos y las marcas de identidad se conservan para el circuito de curación ya existente. Las imágenes quedan fuera de esta fase.

## Evidencia reproducible

- [Inventario completo](../../../reports/source-strategy-2026-09-25/source-register.json)
- [Manifest de publicación](../../../reports/source-strategy-2026-09-25/publication-manifest.json)
- [Contribución y overlap observado](../../../reports/source-strategy-2026-09-25/corpus-contribution.json)
- [Salud de las tres rutinas previas](../../../reports/source-strategy-2026-09-25/source-health.json)
- [Registros apartados con motivo](../../../reports/source-strategy-2026-09-25/excluded-existing.jsonl)
- [Correcciones del corpus existente](../../../reports/source-strategy-2026-09-25/corrected-existing.json)
- [Recuperación de productos físicos](../../../reports/source-strategy-2026-09-25/physical-recovery.json)
- [PRH / Seven Seas](https://prhcomics.com/seven-seas/), [Kingstone / SPP](https://www.kingstone.com.tw/bookpublish/publist/14395/?classname=new&dis=pic&format=0&page=1&sort=sa_desc&subkind=all), [Delcourt mangas](https://www.editions-delcourt.fr/mangas/liste-mangas).
