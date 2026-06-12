import type { MetadataRoute } from 'next'
import { absoluteUrl } from '@/lib/seo'

/**
 * robots.txt (FRD-008 FR-2, FR-7).
 *
 * - Public detail pages are fully crawlable.
 * - Faceted/query catalog URLs are disallowed to avoid duplicate-content + crawl
 *   budget waste (the home `/` is force-dynamic over searchParams).
 * - AI / answer-engine crawlers are an INTENDED discovery channel — explicitly allowed.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/*?'],
      },
      {
        userAgent: [
          'GPTBot',
          'OAI-SearchBot',
          'ChatGPT-User',
          'ClaudeBot',
          'Claude-Web',
          'anthropic-ai',
          'PerplexityBot',
          'Google-Extended',
          'CCBot',
          'cohere-ai',
        ],
        allow: '/',
      },
    ],
    sitemap: absoluteUrl('/sitemap.xml'),
    // Sin `host`: la directiva (sólo Yandex, deprecada) espera hostname sin
    // esquema y emitíamos la URL completa.
  }
}
