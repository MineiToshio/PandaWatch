# Documentación — PandaWatch

Índice de toda la documentación del proyecto. Cuatro componentes, cuatro carpetas.

---

## Componentes

| Componente | Código | Docs |
|---|---|---|
| Scraper Python | `scripts/` | [`docs/scraper/`](#scraper) |
| Dashboard HTML personal | `web/` | [`docs/web-html/`](#web-html) |
| Panel de Control admin | `admin/` | [`docs/admin/`](#admin) |
| App Next.js (público) | `web-next/` | [`docs/web-next/`](#web-next) |

---

## Scraper

Pipeline de scraping de ~76 fuentes en 10 países. Detección de ediciones especiales,
wikis comunitarios, filtros, scoring, estandarización con LLM.

| Doc | Qué cubre |
|---|---|
| [`scraper/PRD.md`](scraper/PRD.md) | Qué es, corpus actual, wikis activos, roadmap, no-goals |
| [`scraper/ARCHITECTURE.md`](scraper/ARCHITECTURE.md) | Pipeline interno, filtros, cluster_key, concurrencia, schema de datos |
| [`scraper/SOURCES.md`](scraper/SOURCES.md) | Cómo agregar/mantener fuentes, recetas por tipo, gotchas por fuente |

Scripts de retrofit en [`scripts/retrofit/README.md`](../scripts/retrofit/README.md).
Skills de curación en [`.claude/skills/README.md`](../.claude/skills/README.md).

---

## Web HTML

Dashboard personal para explorar y curar el catálogo. Solo el dueño. Alpine.js + Tailwind.

| Doc | Qué cubre |
|---|---|
| [`web-html/PRD.md`](web-html/PRD.md) | Features actuales, features planificadas, propósito vs Next.js |

---

## Admin

Panel de Control web local para ejecutar scripts sin tocar el terminal.
Corre en `localhost:8001`, solo accesible localmente.

| Doc | Qué cubre |
|---|---|
| [`admin/README.md`](admin/README.md) | Quick start, API HTTP, modelo de seguridad, script_registry.py, troubleshooting |

---

## Web Next

App Next.js 16 + Tailwind v4 para el público. Server Components, SSG, diseño PandaTrack.

| Doc | Qué cubre |
|---|---|
| [`web-next/README.md`](web-next/README.md) | Tech stack, constraints, folder structure |
| [`web-next/FRD-001`](web-next/FRD-001-data-layer.md) … [`FRD-006`](web-next/FRD-006-slug-generation.md) | Feature requirements por área |
| [`web-next/blueprints/`](web-next/blueprints/) | ADRs de arquitectura, URL routing, data flow, component hierarchy |
| [`web-next/work-orders/`](web-next/work-orders/) | Tareas de implementación concretas por área |

---

## Contexto para AI

[`CLAUDE.md`](../CLAUDE.md) en la raíz del proyecto — contexto completo para agentes AI:
convenciones, gotchas, schema de datos, decisiones de diseño, corpus state.
Es el documento más completo del proyecto y la fuente de verdad operativa.
