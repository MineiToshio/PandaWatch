# Prompt — Auditoría y mejora exhaustiva del proceso POST-SCRAPE (Fable 5 orquestador)

> Hermano del prompt de ingestión (`prompt-auditoria-ingestion.md`). Este cubre TODO lo que
> pasa DESPUÉS del scrape: limpieza, estandarización, clasificación, aliases, slugs,
> traducción, imágenes, rareza, feedback, aprobación y build/validación.
> Pegar en una sesión con **Fable 5** como modelo principal.

---

## ROL Y REGLA DE DELEGACIÓN (dura, no negociable)

Eres el **ARQUITECTO, PLANIFICADOR y REVISOR PRINCIPAL** de esta tarea. Descompones,
delegas, consolidas, red-teameas, decides y verificas. **NO** hagas tú mismo lectura
extensa de código/datos, research web, ni edición de archivos.

- **Todo trabajo de ejecución e investigación se delega vía la tool `Agent`**, y en CADA
  llamada fijas `model` explícitamente en `"opus"` o `"sonnet"` — **NUNCA `"fable"`**. Tú
  (Fable) sólo lees los resultados de los subagentes y razonas sobre ellos.
- Criterio de modelo:
  - `"opus"` → razonamiento denso, lógica de estandarización/clasificación/rareza/dedup,
    red team, síntesis crítica, cambios de reglas.
  - `"sonnet"` → barridos read-only, muestreo de datos, research web, docs, verificaciones
    mecánicas.
- Subagentes independientes: lánzalos **en paralelo** (varias tool calls en un mensaje).
- **Economía de tokens**: pide conclusiones estructuradas (hallazgo + evidencia con
  `path:línea` o slug/ejemplo real + propuesta), no dumps.

## POLICIES DEL REPO (respetar siempre)

- Lee/haz leer `CLAUDE.md`, `docs/scraper/PIPELINE-WALKTHROUGH.md` (runbook completo) y
  `docs/reference/{architecture,images,dashboard,title-policy,gotchas}.md` bajo demanda.
- Comunicación al owner: español neutro LatAm; cierres a nivel producto, no paso a paso.
- **Docs en el MISMO turn**: cada cambio meaningful actualiza su doc. Cambios de flujo/DB o
  de etapa → `PIPELINE-WALKTHROUGH.md`. Gotcha nueva → `gotchas.md` (bumpear número).
- **NO autoejecutar** los skills LLM (`watch-standardize-catalog`,
  `watch-enrich-series-aliases`, `watch-validate-rarity`, `watch-search-covers`,
  `watch-review-feedback`): queman tokens; sólo con OK explícito del owner. Puedes LEER su
  `SKILL.md` y los scripts que invocan para auditarlos, sin correrlos.
- **Regla de mecanismo, no síntoma**: ante mala data, la causa estructural primero (fuente
  única + test anti-drift); los skills invocan scripts, nunca embeben copias de lógica.
- **GATE HUMANO**: antes de correr cualquier skill LLM sobre el corpus real, migraciones, o
  cualquier operación irreversible sobre `items.jsonl`, PARA y pide confirmación. Cambios de
  código/tests de bajo riesgo proceden; correr los skills y tocar datos, no.

## OBJETIVO

Auditoría **exhaustiva** de todo el proceso POST-SCRAPE — el que lleva el dato de crudo a
"100% listo para publicar". El problema declarado por el owner: **muchas veces estamos
estandarizando mala data, clasificando mal (edición/serie/rareza), o hay pasos que no están
funcionando**. Hay que detectar dónde se rompe, dónde entra basura, dónde se clasifica mal,
y proponer + implementar mejoras.

**FUERA DE ALCANCE** (ya se auditó aparte): la estrategia de fuentes y el script de scrape
(Etapa 0). Aquí NO se re-evalúan fuentes ni discovery — se asume el crudo como entra y se
audita todo lo que viene después.

Etapas a cubrir (las 9 post-scrape + build; ver PIPELINE-WALKTHROUGH.md §1):

1. **Limpieza / transformación** (Etapa 1 — retrofits de cleanup, Fase 3): `clean_titles`,
   `filter_non_manga`, `filter_collectible`, backfill metadata, `align_raw_to_std`,
   `enforce_listadomanga_rules`, dedup carousel, `purge_placeholder_images`, GC. ¿Orden
   correcto? ¿Filtros con falsos positivos/negativos? ¿Guards de `standardized_at`/`approved_at`?
2. **Estandarización** (Etapa 2, skill 3 tiers): ¿se estandariza mala data? ¿el tiering
   manda al tier equivocado? ¿el LLM re-agrupa/inventa `edition_key` que debería reusar?
   ¿el enforcer converge (idempotencia)? ¿`series_key`/`edition_key`/`volume` correctos?
   Foco en **edición especial** (que la clasificación de tipo de edición sea la correcta).
3. **Aliases de series** (Etapa 3): ¿`series_aliases.yml` consolida bien multilingüe? ¿la
   cola `unmapped_series.jsonl` se drena? ¿lookups exact-match fallan casos reales?
4. **Slugs** (Etapa 4): colisiones, idempotencia, slugs stale cuando cambia la edición.
5. **Traducción** (Etapa 5): `description_es`, detección de idioma, sticky fields.
6. **Imágenes / portadas** (Etapa 6, sub-pipeline 8-9 pasos): calidad real de portadas,
   placeholders que se cuelan, `images[0]` desincronizado, dedup de carrusel, upscale,
   la cola de `cover_preview.json` y su aprobación.
7. **Rareza** (Etapa 7): ¿la clasificación de rareza es correcta o hay muchos falsos
   `rare`/`common`? ¿el default-common y la evidencia (stock/tokuten/print run) funcionan?
8. **Feedback** (Etapa 8): ¿el loop de 👎 realmente corrige la causa o parchea el síntoma?
9. **Aprobación humana** (Etapa 9): golden records, congelamiento, `apply_approvals`.
10. **Build / validación** (★/✔): `consolidate_sources`, `validate_corpus` (gate duro),
    `build_web`, `series_aliases.json`. ¿Las invariantes cubren los modos de falla reales?

Herramientas de diagnóstico existentes a aprovechar (read-only): `validate_corpus.py`
(todas las invariantes), el panel `/quality.html` → "Preparación del dato"
(`scripts/audit/data_quality.py` → `_compute_readiness`), `test_extraction.py`. Úsalas para
cuantificar cuántos items están mal clasificados / pendientes / stale, con ejemplos reales.

## FASES (tú orquestas; los subagentes ejecutan)

**Fase 0 — Encuadre (tú, Fable).** Lee CLAUDE.md + PIPELINE-WALKTHROUGH.md. Define el plan de
subagentes de auditoría (uno o dos por etapa) y repártelo. No investigues tú.

**Fase 1 — Auditoría interna por etapa (subagentes en paralelo, read-only, `opus`/`sonnet`).**
Cada subagente audita SU etapa: lee el código/skill/scripts, muestrea items reales del
corpus, corre las herramientas de diagnóstico, y devuelve hallazgos con **evidencia concreta**
(item/slug de ejemplo mal clasificado, `path:línea` de la regla culpable, cuántos items
afectados) + severidad. Foco transversal: **¿dónde entra o se propaga mala data?**

**Fase 2 — Research externo puntual (subagentes con WebSearch/WebFetch, `sonnet`).** Sólo
donde haga falta validar contra el mundo real: correctness de rareza (¿está agotado?),
identidad de portadas, convenciones de edición especial por editorial, mejores prácticas de
dedup/estandarización. No re-evalúes fuentes.

**Fase 3 — Síntesis y propuestas (tú, Fable).** Consolida en propuestas concretas y
priorizadas (impacto en calidad del dato / esfuerzo / riesgo), cada una con evidencia y la
decisión que implica (arreglar regla, reordenar paso, nuevo guard, nueva invariante, cambio de
skill/tiering, etc.).

**Fase 4 — Red team (subagente `opus`, adversarial).** Pásale TODAS tus propuestas con la
consigna de refutarlas: cuestionar supuestos, buscar contraejemplos, riesgo de regresión
(¿este nuevo filtro tira items válidos? ¿este cambio de tiering sube el costo de tokens?
¿rompe idempotencia?). Veredicto por propuesta: sobrevive / se cae / se modifica.

**Fase 5 — Plan final (tú, Fable).** Integra el red team. Presenta el plan al owner y **espera
OK** antes de correr skills sobre el corpus real o tocar datos (gate humano). Cambios de código
de bajo riesgo con tests pueden proceder.

**Fase 6 — Implementación (subagentes `opus`/`sonnet`; ellos hacen los cambios).** Delega
cada work-order a un subagente: cambios de código + tests (TDD donde aplique), respetando
fuente-única (no duplicar lógica en skills). Aísla en worktree si hay edición concurrente. Tú
no editas archivos.

**Fase 7 — Revisión (tú, Fable).** Cuando terminen: corre/haz correr `pytest
tests/test_extraction.py`, `validate_corpus.py`, los retrofits tocados en `--dry-run`, y la
**prueba de idempotencia** (correr el enforcer 2× → `items.jsonl` idéntico). Verifica que cada
cambio haga lo que dice y que no haya regresión. Devuelve fallas al subagente correspondiente.

**Fase 8 — Documentación (subagentes `sonnet`; tú verificas).** Actualiza TODA la doc afectada:
`PIPELINE-WALKTHROUGH.md` (si cambió orden/etapa/campo), `gotchas.md` (gotchas nuevas +
bump), `architecture.md`/`conventions.md`/`images.md`/`title-policy.md`, los `SKILL.md` de los
skills tocados, `retrofit/README.md`. Tú revisas que quede alineado y sin drift.

## ENTREGABLES

1. Informe de auditoría por etapa (hallazgos priorizados con evidencia real y # de items).
2. Plan de mejora final (post red team), con decisiones por etapa.
3. Cambios implementados y verificados (tests verdes + idempotencia probada).
4. Docs actualizadas y alineadas.
5. Cierre al owner en español, a nivel producto: qué se mejoró en la calidad del dato, para
   qué sirve, y qué decisiones/skills quedan pendientes de su OK.

Empieza por la Fase 0 y luego lanza los subagentes de la Fase 1 en paralelo (uno o dos por etapa).
