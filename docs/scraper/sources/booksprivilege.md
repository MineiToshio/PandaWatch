# Fuente: BooksPrivilege

## Información general

Catálogo japonés de beneficios de tienda para libros físicos. Entrada:
`https://booksprivilege.com/?cal_ym=YYYY-M`; páginas por día con `?date=YYYY-MM-DD`
y fichas con `?id=N`. Parser: `scripts/wikis/booksprivilege.py`.

## Ingestión y límites

Recorre meses, días publicados y fichas; extrae los bonus de retailers japoneses.
La fecha de calendario controla el discovery. Las reglas de pertinencia y score
se aplican antes de publicar. No confundir un bonus de tienda con una edición
editorial diferente. No se verificó una corrida histórica completa en esta revisión.

## Verificación

Las pruebas de fallo de transporte están en `tests/test_ingestion_integrity.py`.

### Integridad de ingestión — continuación 2026-09-24

Los fallos de transporte ahora registran `[WIKI-ISSUE]` en la sesión. El dispatcher
conserva los resultados parciales y termina con error; incluye el fallo en el
reporte. Una respuesta fallida no equivale a catálogo vacío. El watermark por
fuente solo avanza después de persistir corpus y estado, sin incidencias ni
límites alcanzados. Tras una interrupción, el calendario amplía su ventana hasta
el último inicio exitoso con siete días de solapamiento. Un import histórico
acotado, un chunk explícito o un dry-run no adelantan ese watermark.
