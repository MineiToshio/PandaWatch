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
    background_color: '#0d0d0f',
    theme_color: '#0d0d0f',
    icons: [
      { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
      { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
  }
}
