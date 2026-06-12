---
name: feature-spec
description: Planifica una feature grande (Vía C del AI-WORKFLOW) entrevistando al owner y explorando el código, y produce un spec autocontenido en docs/specs/ listo para implementar en una sesión fresca. Usar al inicio de una épica o de una feature con decisiones de producto abiertas. No implementa nada.
argument-hint: "<descripción breve de la feature>"
disable-model-invocation: true
---

# feature-spec — entrevista → spec autocontenido

Produce un spec que una sesión SIN contexto pueda implementar de punta a
punta. **Este skill NO implementa nada** — su único output es el archivo de
spec (y, si aplica, su registro en docs).

## Paso 0 — Clasificar la vía

Evalúa la feature pedida contra la regla de decisión de
[docs/process/AI-WORKFLOW.md](../../../docs/process/AI-WORKFLOW.md):

- Si es **Vía A** (diff en una frase) o **Vía B clara** (multi-archivo pero
  sin decisiones abiertas): dilo y recomienda ir directo (plan mode para B).
  NO generes spec — sería burocracia. Termina aquí salvo que el owner
  insista.
- Si es **Vía C** (área nueva / decisiones de producto / >1 sesión): continúa.

## Paso 1 — Explorar (subagente, contexto principal limpio)

Lanza UN subagente Explore con la pregunta concreta: qué módulos/rutas/
docs toca la feature, qué patrones existentes hay que seguir, qué gotchas
(#N) y decisiones de diseño aplican. Pide de vuelta: lista de archivos
relevantes con 1 línea c/u + restricciones detectadas. NO leas módulos
grandes en el hilo principal.

## Paso 2 — Entrevistar al owner

Usa AskUserQuestion en 2–3 rondas máximo. NO preguntes lo obvio; ataca lo
difícil que el owner quizá no consideró:

- Alcance mínimo lanzable vs. nice-to-have (¿qué queda explícitamente fuera?)
- Edge cases del dominio (multi-país, multi-idioma, items sin imagen/fecha…)
- UX: ¿dónde vive en la UI? ¿qué pasa en estados vacíos/error?
- Trade-offs técnicos detectados en el Paso 1 (elige una recomendación y
  preséntala como opción primera)
- ¿Cómo sabremos que funciona? (esto alimenta los criterios de verificación)

## Paso 3 — Escribir el spec

Archivo: `docs/specs/SPEC-<slug-corto>.md` (crea el directorio si no
existe). Si la feature es de **web-next** y tiene entidad de producto,
usa en su lugar el sistema existente: FRD en `docs/web-next/` (+ WOs si
hay varias unidades), siguiendo el formato de los FRD-00X existentes.

Plantilla del spec:

```markdown
# SPEC-<slug> — <título>
Estado: pendiente | Fecha: <hoy> | Vía: C

## Objetivo (1-2 frases, a nivel producto)
## Alcance
## Fuera de alcance (explícito)
## Contexto técnico
- Archivos involucrados (ruta + qué cambia en cada uno)
- Patrones a seguir (referencia a código existente)
- Gotchas y decisiones que aplican (#N, decisión #N)
## Unidades de trabajo
1. <unidad> — criterio de verificación EJECUTABLE (comando + resultado esperado)
2. …
## Verificación end-to-end
<comando(s)/flujo observable que prueba la feature completa>
## Docs a actualizar al cerrar (según tabla de CLAUDE.md)
```

Cada unidad debe ser completable en una sesión y verificable por sí sola.

## Paso 4 — Cierre

Reporta al owner (breve, a nivel producto): qué quedó en el spec, qué quedó
fuera, y el siguiente paso literal:

> `/clear` y luego: «implementa @docs/specs/SPEC-<slug>.md, unidad 1»

No empieces a implementar en esta sesión.
