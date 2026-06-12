# AI-WORKFLOW — Flujo de implementación con IA

> **Cuándo leer esto**: antes de empezar cualquier feature, fix o épica.
> Define CÓMO trabajamos con Claude Code: qué vía tomar según el tamaño de
> la tarea, cómo verificar, y cómo gastar la menor cantidad de tokens
> posible sin sacrificar calidad. Complementa CLAUDE.md (políticas) y
> PIPELINE-WALKTHROUGH.md (ciclo de vida del DATO — esto es el ciclo de
> vida del CÓDIGO).

Última actualización: 2026-06-12.

## Por qué este flujo (resumen de la investigación)

Comparamos tres enfoques de desarrollo con IA (2026):

| Enfoque | Fortaleza | Debilidad | Costo tokens |
|---|---|---|---|
| **Vibe coding** (prompt directo, sin plan) | Velocidad en tareas chicas y prototipos | Resuelve el problema equivocado en tareas multi-archivo | Bajo por intento, alto si hay que rehacer |
| **Spec-driven** (Kiro / GitHub spec-kit: Spec → Plan → Tasks → Implement) | Fiabilidad en features grandes; el spec es contrato verificable | Burocracia para fixes chicos | +20–40% por feature, compensado por menos ciclos desperdiciados |
| **Híbrido por tamaño** (recomendación oficial de Claude Code: explore → plan → code → commit, con plan mode solo cuando hay incertidumbre) | Ajusta el overhead al riesgo real de la tarea | Requiere clasificar la tarea al inicio | Óptimo |

**Adoptamos el híbrido**: tres vías según tamaño. Ya teníamos la pieza
spec-driven (sistema FRD → Blueprint → Work Order de `docs/web-next/`);
este flujo la generaliza y le agrega la disciplina de verificación y de
contexto. La restricción que gobierna todo: **el contexto es el recurso
escaso** — el rendimiento del modelo degrada a medida que se llena, y los
tokens cuestan. Cada regla de abajo existe para proteger eso.

## Las 3 vías — elegir al inicio de cada tarea

Regla de decisión (en orden):

1. ¿Puedes describir el diff en una frase? → **Vía A**.
2. ¿Multi-archivo pero el alcance está claro y no hay decisiones de producto? → **Vía B**.
3. ¿Área nueva, decisiones de producto/arquitectura, o >1 sesión de trabajo? → **Vía C**.

### Vía A — Fix rápido (typo, log, rename, bug puntual ya diagnosticado)

- **Sin plan mode.** Prompt directo con: archivo(s) por nombre (`@ruta`),
  el síntoma exacto (pegar el error), y el comando de verificación en el
  MISMO prompt ("corre `pytest tests/test_extraction.py -k <caso> -q` al
  terminar").
- Si toca un parser/filtro/extractor: leer primero la gotcha relevante
  (`docs/reference/gotchas.md` por número) y la ficha de la fuente.
- Cierre: docs si el cambio es meaningful (tabla de CLAUDE.md) + commit.

### Vía B — Feature acotada (multi-archivo, alcance claro)

1. **Plan mode** (Shift+Tab): explorar con subagentes ("usa un subagente
   para investigar X"), producir plan. Revisar/editar el plan antes de
   aprobar — corregir el plan cuesta 10× menos que corregir el código.
2. **Implementar contra el plan**, con tests escritos/corridos en el camino.
3. **Verificar con evidencia** (ver escalera abajo): pytest dirigido +
   dry-runs según área (pipeline) o vitest + build + preview (web-next).
4. **`/code-review`** (effort low/medium) si tocó lógica delicada
   (merge/cluster_key/filtros/scoring).
5. **`/ship-check`** + docs en el mismo turn + commit.

### Vía C — Épica (área nueva, feature de producto, >1 sesión)

1. **`/feature-spec`** — entrevista al owner, explora el código con
   subagentes y escribe un spec autocontenido en `docs/specs/SPEC-<slug>.md`
   (o FRD/BP/WO si es web-next, siguiendo `docs/web-next/`).
2. **Sesión fresca por unidad de trabajo**: `/clear` (o sesión nueva) y
   prompt mínimo: "implementa @docs/specs/SPEC-x.md, sección N". El spec
   viaja como artefacto; el contexto de planificación NO. Esto es lo que
   hace al spec rentable: la sesión de implementación arranca limpia.
3. Cada unidad termina con su verificación (el spec define el criterio
   ejecutable) antes de pasar a la siguiente.
4. **Cierre de la épica**: `/code-review` (effort high) sobre el diff
   completo + `/verify` end-to-end + `/ship-check`.

## Reglas de eficiencia de tokens (en orden de impacto)

1. **`/clear` entre tareas no relacionadas.** La sesión "cajón de sastre"
   es el anti-patrón #1: reduce el costo por mensaje 30–50% y mejora la
   calidad.
2. **Exploración → subagentes, siempre.** "Usa un subagente para
   investigar X" mantiene el contexto principal limpio; el subagente lee
   20 archivos y devuelve 10 líneas. Nunca pedir "lee todo el módulo Y"
   en el hilo principal.
3. **NUNCA leer `data/items.jsonl` (ni JSONL grandes) al contexto.**
   ~11k líneas de JSON denso. Siempre `python -c`/`jq` para contar,
   muestrear o filtrar. Lo mismo aplica a `manga_watch.py` completo
   (~9k líneas): leer por rangos/símbolos.
4. **Docs bajo demanda** (ya es policy de CLAUDE.md): cargar SOLO el doc
   del área que se toca, vía la tabla de referencias. No "ponte en
   contexto leyendo docs/".
5. **Tests dirigidos durante el desarrollo** (`pytest -k caso` o archivo
   específico); la suite completa solo en `/ship-check` final.
6. **Dos correcciones fallidas → `/clear` + prompt mejor.** Una sesión
   limpia con un prompt que incorpora lo aprendido gana casi siempre a una
   sesión larga llena de intentos fallidos.
7. **Plan en una sesión, implementación en otra** (Vía C). El artefacto
   (spec) reemplaza al contexto acumulado.
8. **Modelos por tarea**: haiku para subagentes mecánicos (ya es el patrón
   de `/watch-standardize-catalog`); el modelo grande solo orquesta y
   decide.
9. **Preguntas laterales → `/btw`** (no entran al historial).
10. **Skills pesados solo a pedido explícito** (policy existente — siguen
    siendo la mayor partida de tokens del repo).

## Escalera de verificación — "si no lo puedes verificar, no lo embarques"

El principio central de las best practices oficiales: darle al agente un
check que pueda CORRER, no confiar en "se ve bien". De menor a mayor costo:

| Nivel | Qué | Cuándo |
|---|---|---|
| 1 | Criterio en el prompt ("estos 3 casos deben pasar") | Siempre, gratis |
| 2 | pytest dirigido / vitest / `npm run build` / dry-runs de retrofits | Toda vía |
| 3 | `/verify` o preview tools (levantar la app, ejercitar el flujo, screenshot) | Cambios de UI/UX en web-next o dashboard |
| 4 | `/code-review` (low→high según riesgo) | Lógica delicada, cierres de épica |
| 5 | Subagente adversarial revisando el diff contra el spec en contexto fresco | Trabajo largo no supervisado (Vía C) |

Pedir siempre **evidencia** (output del test, screenshot), no afirmaciones.
La tabla "Quick sanity check" de CLAUDE.md mapea área tocada → comando;
`/ship-check` la automatiza. Ojo gotcha #61: NO correr `rescore.py` real
sobre corpus estandarizado.

## Skills — cuándo usar cada uno

**De proceso** (nuevos, 2026-06-12 — manuales, no auto-invocables):

| Skill | Cuándo | Costo |
|---|---|---|
| `/feature-spec` | Al iniciar una Vía C (o una Vía B difusa): entrevista → spec autocontenido | Bajo (entrevista + 1 subagente explorador) |
| `/ship-check` | Antes de CADA commit meaningful: detecta áreas tocadas, corre los checks correspondientes y audita docs-sync | Bajo (determinístico, casi sin LLM) |
| `/product-pulse` | Post-lanzamiento, semanal/quincenal: PostHog + feedback → backlog priorizado de iteración | Medio |

**De curación de datos** (existentes — ver detalle en
[.claude/skills/README.md](../../.claude/skills/README.md)): `/watch-standardize-catalog`,
`/watch-enrich-series-aliases`, `/watch-review-feedback`, `/watch-validate-rarity`,
`/watch-search-covers`, `/watch-evaluate-sources`. Todos solo a pedido explícito.

**Built-in de Claude Code** que adoptamos en el flujo: `/verify` (probar la
app de verdad), `/code-review [effort]` (bugs en el diff), `/simplify`
(limpieza post-feature), `/security-review` (antes de exponer algo público),
`/fewer-permission-prompts` (reducir fricción de permisos).

## Post-lanzamiento — loop de iteración por tracción

El objetivo del proyecto: lanzar, conseguir tracción, iterar según uso real.
El loop (semanal o quincenal):

```
señales:  PostHog (uso real) + data/feedback.jsonl (👎 del dashboard)
              ↓
/product-pulse  →  backlog priorizado (impacto × esfuerzo, 3–5 items)
              ↓
owner elige 1–2  →  cada uno entra por su vía (A/B/C)
              ↓
ship  →  (repetir)
```

Prerrequisito al desplegar: instrumentar web-next con PostHog (pageviews +
eventos clave: búsqueda, filtro aplicado, click a tienda, vista de edición).
Sin señal no hay loop. El MCP de PostHog ya está conectado a Claude Code,
así que `/product-pulse` consulta los datos directamente.

## Qué decidimos NO hacer (y cuándo revisitarlo)

- **CI (GitHub Actions)**: por ahora el gate es local (`/ship-check`).
  Revisitar al desplegar públicamente — ahí un `pytest + npm run build` en
  PR protege contra regresiones desde sesiones cloud/web.
- **Hooks automáticos post-edit** (lint/test tras cada edición): la suite
  es pesada (~645 tests); un hook la haría insufrible. Revisitar si se
  agrega un linter rápido (ruff) al repo.
- **Agent teams / sesiones paralelas**: overkill para un solo dev con un
  solo hilo de trabajo. Revisitar si alguna épica tiene 2+ frentes
  independientes (p.ej. pipeline + web-next a la vez → worktrees).

## Fuentes de la investigación

- [Best practices oficiales de Claude Code](https://code.claude.com/docs/en/best-practices)
- [Martin Fowler — Understanding Spec-Driven Development (Kiro, spec-kit, Tessl)](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html)
- [GitHub spec-kit](https://github.com/github/spec-kit) y su [anuncio](https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/)
- [Turing Post — From Vibe Coding to Spec-Driven Development](https://www.turingpost.com/p/sdd)
