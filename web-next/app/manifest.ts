import type { MetadataRoute } from 'next'

/**
 * Web app manifest (FRD-008 FR-4). Minimal PWA surface — installability + mobile signals.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'PandaWatch — Ediciones especiales de manga',
    short_name: 'PandaWatch',
    description:
      'Descubrí ediciones especiales de manga: deluxe, box sets, limited editions, artbooks y más.',
    start_url: '/',
    display: 'standalone',
    // #F5F1EB = --ink-50, mismo criterio que viewport.themeColor en layout.tsx
    // (auditoría #17 — el sitio es light-only, un splash oscuro desentonaba).
    background_color: '#F5F1EB',
    theme_color: '#F5F1EB',
    icons: [
      { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
  }
}
