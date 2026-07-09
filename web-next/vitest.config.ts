import { defineConfig } from 'vitest/config'
import path from 'path'

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
  test: {
    // jsdom para toda la suite (vitest 4 no trae ya environmentMatchGlobs
    // per-glob ni el docblock @vitest-environment de v3 — ver
    // docs/web-next/README.md). jsdom sigue siendo Node.js completo por
    // debajo (fs, etc. intactos) más document/window — los tests de lib/
    // puros no se ven afectados; los de __tests__/components/** (auditoría
    // #20 — antes 0 tests de componentes) lo necesitan para
    // @testing-library/react.
    environment: 'jsdom',
    setupFiles: ['./__tests__/setup.ts'],
  },
})
