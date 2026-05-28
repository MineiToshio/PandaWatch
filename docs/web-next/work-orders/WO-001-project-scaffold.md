# WO-001: Project Scaffold

**Phase:** 0  
**Effort:** S  
**Status:** Pending  
**Related:** [BP-001](../blueprints/BP-001-architecture.md)  
**Prerequisites:** None

---

## Objective

Create the `web-next/` Next.js 16 project with the correct configuration,
folder structure, and toolchain. No feature code — just the skeleton.

---

## Tasks

### Task 1: Initialize Next.js project

```bash
cd /Users/Shared/Proyectos/manga-watch
npx create-next-app@latest web-next \
  --typescript \
  --tailwind \
  --app \
  --no-src-dir \
  --import-alias "@/*"
```

Select when prompted:
- TypeScript: Yes
- ESLint: Yes
- Tailwind CSS: Yes
- App Router: Yes
- src/ directory: No
- Import alias: `@/*`

Verify installed versions:
- Next.js ≥ 16
- React ≥ 19
- Tailwind ≥ 4

### Task 2: Install additional dependencies

```bash
cd web-next
npm install class-variance-authority clsx tailwind-merge lucide-react
npm install -D @types/node
```

### Task 3: Configure `next.config.ts`

```typescript
// web-next/next.config.ts
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // Images from external sources (remote fallbacks)
  images: {
    remotePatterns: [
      { hostname: '*.prhcomics.com' },
      { hostname: '*.amazon.com' },
      { hostname: '*.amazon.co.jp' },
      { hostname: '*.kinokuniya.com' },
      { hostname: 'images.penguinrandomhouse.com' },
      { hostname: 'covers.openlibrary.org' },
    ],
    // Local images served from public/images/ (symlink)
    // No special config needed — they're in public/
  },
}

export default nextConfig
```

### Task 4: Create folder structure

```bash
mkdir -p web-next/components/{core,modules,catalog,edition,item}
mkdir -p web-next/lib
mkdir -p web-next/app/edition/\[editionKey\]
mkdir -p web-next/app/item/\[slug\]
```

Create placeholder files to establish the structure:
```bash
touch web-next/lib/{data,types,slugs,filters,styles}.ts
touch web-next/components/core/.gitkeep
touch web-next/components/modules/.gitkeep
```

### Task 5: Create images symlink

```bash
ln -s ../../data/images web-next/public/images
```

Verify it works:
```bash
ls web-next/public/images | head -5
# Should show image files from data/images/
```

Add to `.gitignore` note: the symlink itself should be committed (it's a pointer,
not the data). Confirm `data/images/` is in root `.gitignore` (it already is).

### Task 6: Create root `tsconfig.json` paths

Verify `web-next/tsconfig.json` has:
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./*"]
    },
    "strict": true
  }
}
```

### Task 7: Stub page files

Create minimal stubs so `next dev` runs without errors:

```tsx
// web-next/app/page.tsx
export default function CatalogPage() {
  return <main>Catalog — coming soon</main>
}
```

```tsx
// web-next/app/layout.tsx
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  )
}
```

```tsx
// web-next/app/edition/[editionKey]/page.tsx
export default function EditionPage({ params }: { params: { editionKey: string } }) {
  return <main>Edition: {params.editionKey}</main>
}
```

```tsx
// web-next/app/item/[slug]/page.tsx
export default function ItemPage({ params }: { params: { slug: string } }) {
  return <main>Item: {params.slug}</main>
}
```

### Task 8: Verify dev server starts

```bash
cd web-next
npm run dev
# Visit http://localhost:3000 — should show "Catalog — coming soon"
# Visit http://localhost:3000/images/<any-filename>.jpg — should serve an image
```

---

## Files Created/Modified

- `web-next/` — entire directory (new)
- `web-next/public/images` — symlink to `../../data/images/`
- `web-next/next.config.ts`
- `web-next/tsconfig.json`
- `web-next/lib/data.ts` (stub)
- `web-next/lib/types.ts` (stub)
- `web-next/lib/filters.ts` (stub)
- `web-next/lib/slugs.ts` (stub)
- `web-next/lib/styles.ts` (stub)
- `web-next/app/layout.tsx` (stub)
- `web-next/app/page.tsx` (stub)
- `web-next/app/edition/[editionKey]/page.tsx` (stub)
- `web-next/app/item/[slug]/page.tsx` (stub)

---

## Acceptance Criteria

- [ ] `npm run dev` starts without errors
- [ ] `http://localhost:3000` shows the catalog stub
- [ ] `http://localhost:3000/images/<filename>.jpg` serves an image from `data/images/`
- [ ] TypeScript strict mode enabled
- [ ] All dependency versions correct (Next.js ≥ 16, React ≥ 19, Tailwind ≥ 4)
- [ ] Folder structure matches BP-001

---

## Notes

- Do NOT create an `src/` directory. Files live directly in `web-next/`.
- The `web-next/` directory coexists with `web/` (Alpine.js app). Both can run
  simultaneously on different ports during development.
- `npm run dev` runs on port 3000; the Python `serve.py` runs on port 8000.
  They don't conflict.
