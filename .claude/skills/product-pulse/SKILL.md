---
name: product-pulse
description: Loop de iteración post-lanzamiento. Lee las señales de uso real (PostHog) y el feedback del dashboard (data/feedback.jsonl), y produce un backlog priorizado de 3-5 oportunidades (impacto × esfuerzo) con la vía recomendada (A/B/C) para cada una. No implementa nada. Correr semanal o quincenalmente después del lanzamiento público.
argument-hint: "[--days N]"
disable-model-invocation: true
---

# product-pulse — señales de uso → backlog priorizado

Objetivo del proyecto: lanzar, medir tracción, iterar según uso real. Este
skill convierte las señales en decisiones. **Solo análisis — no implementa.**

Default: últimos 14 días (`--days N` para cambiar).

**Tier de modelo (auditoría Fable 2026-07-08, hallazgo F10, nota opcional)**:
corre en el hilo principal, sin fan-out. Es un análisis corto quincenal
(agregar señales de PostHog + feedback.jsonl y priorizar) — `sonnet` alcanza;
no requiere `opus`.

## Paso 1 — Señales de PostHog

Carga las tools de PostHog vía ToolSearch (query `+posthog trends`) y
consulta, para el período:

1. **Tráfico**: pageviews totales + tendencia (¿crece, plano, cae?).
2. **Contenido top**: top 10 páginas/rutas (¿qué series/ediciones/países
   atraen?). Agrupa por tipo de ruta (`/series/`, `/edition/`, `/item/`).
3. **Acciones clave** (si están instrumentadas): búsquedas, filtros
   aplicados, clicks a tienda. Si NO hay eventos custom todavía, anótalo
   como gap de instrumentación (es en sí un item del backlog).
4. **Errores**: issues de error tracking del período, ordenados por
   ocurrencias.

Si PostHog no responde o no hay datos (pre-lanzamiento): dilo y sigue solo
con el Paso 2.

## Paso 2 — Feedback interno

```bash
wc -l data/feedback.jsonl 2>/dev/null
.venv/bin/python -c "import json,collections; rs=[json.loads(l).get('reason','') for l in open('data/feedback.jsonl')]; print(collections.Counter(r[:60] for r in rs).most_common(15))" 2>/dev/null
```

Si hay volumen significativo de feedback de datos, recuerda que el fix
profundo es `/watch-review-feedback` (no lo invoques tú — sugiérelo).

## Paso 3 — Sintetizar el backlog

Cruza señales y produce **3–5 oportunidades**, ni una más. Para cada una:

| Campo | Contenido |
|---|---|
| Oportunidad | 1 frase a nivel producto |
| Evidencia | el dato concreto que la respalda (número de PostHog / feedback) |
| Impacto | alto/medio/bajo — sobre tracción o retención |
| Esfuerzo | S/M/L |
| Vía | A / B / C según [AI-WORKFLOW](../../../docs/process/AI-WORKFLOW.md) |

Prioriza: (1) errores que bloquean uso, (2) fricción en el flujo más
transitado, (3) demanda visible no servida (búsquedas sin resultados,
contenido top sin profundidad), (4) gaps de instrumentación.

## Paso 4 — Cierre

Guarda el reporte en `data/diagnostics/product-pulse-<YYYYMMDD>.md` (fecha
vía `date +%Y%m%d`) y muestra al owner SOLO la tabla final + una
recomendación: «empezaría por X porque Y». El owner elige; cada item entra
por su vía.
