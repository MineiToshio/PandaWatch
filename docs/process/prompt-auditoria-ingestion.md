# Prompt — Auditoría y mejora exhaustiva del proceso de ingestión (Fable 5 orquestador)

> Pegar este prompt en una sesión con **Fable 5** como modelo principal.
> Fable 5 NO ejecuta ni investiga directamente: sólo orquesta, planifica,
> consolida y revisa. Todo lo demás va a subagentes Opus/Sonnet.

---

## ROL Y REGLA DE DELEGACIÓN (dura, no negociable)

Eres el **orquestador, planificador y revisor principal** de esta tarea. Tu trabajo es
descomponer, delegar, consolidar, red-teamear, decidir y verificar. **NO** hagas tú
mismo lectura extensa de código, research web, visitas a fuentes, ni edición de archivos.

- **Todo trabajo de ejecución e investigación se delega vía la tool `Agent`**, y en CADA
  llamada debes fijar `model` explícitamente en `"opus"` o `"sonnet"` — **NUNCA `"fable"`**.
  Tú (Fable) sólo lees los resultados que devuelven los subagentes y razonas sobre ellos.
- Criterio de modelo por subagente:
  - `"opus"` → razonamiento denso, cambios de parser/filtros/dedup/scoring, red team,
    decisiones de arquitectura, síntesis crítica.
  - `"sonnet"` → barridos read-only, mapeo de archivos, research web amplio, fetch de
    fuentes, escritura de docs, verificaciones mecánicas.
- Cuando lances varios subagentes independientes, lánzalos **en paralelo** (varias tool
  calls en un mismo mensaje).
- **Economía de tokens**: no pidas a los subagentes que devuelvan dumps de archivos;
  pídeles conclusiones estructuradas (hallazgos, evidencia con `path:línea`, propuesta).

## CONTEXTO Y POLICIES DEL REPO (respetar siempre)

- Lee/haz leer `CLAUDE.md` y los docs de `docs/reference/` y `docs/scraper/` **bajo demanda**.
- **Comunicación**: al owner, español neutro LatAm; cierres a nivel producto (qué/para qué/
  por qué), no paso a paso salvo que lo pida.
- **Docs en el MISMO turn**: todo cambio meaningful actualiza su doc. Cada hallazgo/cambio
  de una fuente actualiza su ficha `docs/scraper/sources/<fuente>.md` (crear desde
  `_TEMPLATE.md` si no existe). Cambios de flujo/DB → `docs/scraper/PIPELINE-WALKTHROUGH.md`.
- **NO autoejecutar** `watch-standardize-catalog` ni `watch-enrich-series-aliases` (queman
  tokens; sólo con OK explícito del owner). Sí puedes usar como análisis read-only las skills
  `watch-evaluate-sources` y `listadomanga-audit`, y el script `source_health.py`.
- **Gate humano**: antes de correr scrapes reales grandes, migraciones de datos, o cualquier
  operación irreversible sobre `items.jsonl`, PARA y pide confirmación al owner. La
  implementación de código/tests sí procede sin gate; los datos y los runs costosos, no.

## OBJETIVO

Revisión **exhaustiva** de toda la estrategia de ingestión de datos (la espina dorsal del
producto): encontrar puntos débiles, cosas que fallan, y mejorarlas — para **ingestión full
Y delta** — con foco en que lo que se ingiere sean **mangas de EDICIÓN ESPECIAL** físicos
(limited/deluxe/box set/slipcase/artbook/kanzenban/coleccionista/etc.). El resultado debe
ser: encontrar los mangas que realmente corresponden y deberíamos agregar, sin ruido.

Áreas obligatorias a cubrir (no te limites a esto — busca todo):

1. **Cobertura full vs delta**: ¿el delta captura la misma riqueza que el full para
   ediciones especiales? ¿hay huecos de discovery? ¿fuentes que sólo corren en uno?
2. **ListadoManga** (la fuente más compleja y crítica): revísala a fondo —
   parser de colecciones, ediciones especiales/cofres/variantes, gaps sitio-real vs parser.
   Usa el preview / navegación a la página si hace falta (delegado a subagente).
3. **Anti-bot**: ¿tenemos sistema para sobreponernos a bloqueos (rate-limit, WAF, JS-gates,
   captchas, geoblock)? ¿qué fuentes nos están bloqueando hoy? ¿qué estrategia por fuente
   (headers/proxies/backoff/Playwright opt-in/cookies)? Propón un mecanismo, no parches.
4. **Overlap y poda de fuentes**: identifica solapamientos. Si una fuente cubre ~100% de un
   país (p. ej. España), las fuentes mono-editorial de ese país sobran. Decide con datos con
   cuál quedarse y cuál descartar. Evalúa si fuentes **de comunidad / no oficiales** aportan
   señal única o sólo ruido/duplicados. Entrega recomendación por fuente: mantener / podar /
   degradar a referencia.
5. **Calidad de la señal**: filtros (non-manga, collectible), scoring, dedup/cluster_key,
   false positives/negatives respecto a "edición especial". ¿Se nos escapan ediciones? ¿Entra
   basura?
6. Cualquier otro punto débil del pipeline end-to-end que detectes.

## FASES (tú orquestas; los subagentes ejecutan)

**Fase 0 — Encuadre (tú, Fable).** Lee CLAUDE.md y el índice de docs. Define el plan de
subagentes de auditoría y repártelo. No investigues tú.

**Fase 1 — Auditoría interna (subagentes en paralelo, read-only, `opus`/`sonnet`).**
Mapea el estado actual: `sources.yml` (fuentes, purity/kind/enabled/país/idioma), los 2
scripts canónicos (`scrape_full.sh`/`scrape_delta.sh`), parsers/wikis, `listadomanga_collections.py`,
filtros, scoring, dedup, anti-bot (gotcha #12 y afines), logs/`source_health.py`. Cada subagente
devuelve hallazgos con evidencia `path:línea` y severidad.

**Fase 2 — Research externo (subagentes con WebSearch/WebFetch/preview, `sonnet`; `opus` si
requiere juicio).** Para las fuentes clave y candidatas: cobertura real por país/editorial,
solapamientos, señales anti-bot del sitio, y posibles fuentes faltantes de ediciones especiales.
Usa `watch-evaluate-sources` para candidatas y `listadomanga-audit` para ListadoManga.

**Fase 3 — Síntesis y propuestas (tú, Fable).** Consolida todo en un set de propuestas
concretas y priorizadas (impacto/esfuerzo/riesgo), cada una con evidencia y con la decisión
que implica (agregar/podar/degradar/arreglar).

**Fase 4 — Red team (subagente `opus`, adversarial).** Pásale TODAS tus propuestas con la
consigna de refutarlas: cuestionar supuestos, buscar contraejemplos, riesgos de podar una
fuente (¿de verdad hay 100% de cobertura?), falsos ahorros, regresiones. Devuelve veredicto
por propuesta: sobrevive / se cae / se modifica.

**Fase 5 — Plan final (tú, Fable).** Integra el red team. Entrega al owner un plan de mejora
sólido y priorizado. **Presenta el plan y espera OK** antes de implementar cambios grandes o
tocar datos (gate humano). Cambios de código de bajo riesgo con tests pueden proceder.

**Fase 6 — Implementación (subagentes `opus`/`sonnet`; los subagentes hacen los cambios).**
Delega cada work-order a un subagente: cambios de código + tests (TDD donde aplique). Aísla en
worktree si hay edición concurrente. Tú no editas archivos.

**Fase 7 — Revisión (tú, Fable).** Cuando terminen, revisa lo que hicieron: corre/haz correr
la suite (`pytest`), los retrofits en `--dry-run` según lo tocado, y verifica que cada cambio
haga lo que dice. Si algo falla, devuélvelo al subagente correspondiente.

**Fase 8 — Documentación (subagentes `sonnet`; tú verificas alineación).** Actualiza TODA la
doc afectada en línea con las policies: fichas de fuentes tocadas, PIPELINE-WALKTHROUGH,
gotchas nuevas, architecture/conventions/file-map, SOURCES.md, PRD si aplica. Tú revisas que
quede todo alineado y sin drift.

## ENTREGABLES

1. Informe de auditoría (hallazgos priorizados con evidencia).
2. Plan de mejora final (post red team), con decisiones por fuente (mantener/podar/degradar).
3. Los cambios implementados y verificados (código + tests verdes).
4. Docs actualizadas y alineadas.
5. Cierre al owner en español, a nivel producto: qué se mejoró, para qué sirve, y qué decisiones
   quedan pendientes de su OK.

Empieza por la Fase 0 y luego lanza los subagentes de la Fase 1 en paralelo.
