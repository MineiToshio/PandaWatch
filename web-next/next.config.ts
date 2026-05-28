import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      { hostname: 'images.penguinrandomhouse.com' },
      { hostname: 'covers.openlibrary.org' },
      { hostname: 'images-na.ssl-images-amazon.com' },
      { hostname: 'm.media-amazon.com' },
      { hostname: 'thumbnail.image.rakuten.co.jp' },
      { hostname: 'tbooks.object.ecstatics.com' },
      { hostname: 'www.manga-sanctuary.com' },
      { hostname: 'www.mangapassion.de' },
    ],
  },
}

export default nextConfig
