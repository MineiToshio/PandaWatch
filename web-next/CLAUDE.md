@AGENTS.md

# web-next — contexto para agentes

App pública de PandaWatch (catálogo de ediciones especiales de manga).
Next.js 16 + TypeScript + Tailwind v4, App Router, Server Components.

## Reglas clave

- **Datos**: se leen LIVE de `../data/items.jsonl` SOLO a través de
  `lib/data.ts` (cache por mtime + índices). Nunca leer el JSONL desde
  componentes ni agregar otra puerta de lectura.
- **Sin API routes** — todo es SSG/Server Components. Detalle de item =
  SSG puro con `dynamicParams=false`.
- **Imágenes**: espejo local vía symlink `public/images → ../../data/images/`.
- **Sin precios**: decisión del owner (2026-06-11), no reintroducir captura
  ni UI de precios.
- Next.js 16 tiene breaking changes vs. training data: ante dudas, leer
  `node_modules/next/dist/docs/` (ver AGENTS.md).

## Comandos

```bash
npm run dev        # dev server (puerto 3001)
npx vitest run     # tests
npm run build      # build de producción (check obligatorio pre-commit)
```

## Docs

Specs y diseño en `docs/web-next/` (README + FRD-00X + blueprints + work
orders). Feature nueva o cambio de UX → actualizar el FRD que corresponda
en el mismo turn. Flujo de implementación: `docs/process/AI-WORKFLOW.md`.
