import type { NextConfig } from 'next'

// Sin images.remotePatterns: next/image sólo sirve el espejo local
// (/images/...); toda imagen remota va por <img> plano a propósito —
// mantener un allowlist de ~270 hosts de tiendas no escala (ver CoverImage).
//
// Tuning del optimizer (auditoría #15): el espejo local YA está normalizado
// (AVIF Q60 ≤1600px, pipeline Python) — next/image por default igual
// re-transcodifica por cada breakpoint solicitado y cachea poco tiempo.
//   - formats: sólo AVIF (el espejo ya es AVIF; no generar variantes WebP
//     redundantes del mismo archivo).
//   - minimumCacheTTL: 31 días — los covers son inmutables por filename
//     (un cambio de imagen es un archivo nuevo, no un overwrite).
//   - deviceSizes/imageSizes: recortados a los anchos reales que layout usa
//     (sizes declara 20vw/33vw/50vw/64px/160px/280px — ver EditionCard,
//     ItemCard, SeriesCard, EditionHeader, SeriesHeader, ImageCarousel).
const nextConfig: NextConfig = {
  images: {
    formats: ['image/avif'],
    minimumCacheTTL: 2678400, // 31 días
    deviceSizes: [280, 384, 480, 640, 828, 1080, 1600],
    imageSizes: [64, 96, 160, 200, 280],
  },
}

export default nextConfig
