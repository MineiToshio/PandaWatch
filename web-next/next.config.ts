import type { NextConfig } from 'next'

// Sin images.remotePatterns: next/image sólo sirve el espejo local
// (/images/...); toda imagen remota va por <img> plano a propósito —
// mantener un allowlist de ~270 hosts de tiendas no escala (ver CoverImage).
const nextConfig: NextConfig = {}

export default nextConfig
