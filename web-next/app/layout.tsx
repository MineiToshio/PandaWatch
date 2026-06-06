import type { Metadata, Viewport } from 'next'
import './globals.css'
import { Header } from '@/components/modules/Header'
import { JsonLd } from '@/components/seo/JsonLd'
import { siteUrl } from '@/lib/seo'
import { websiteJsonLd, organizationJsonLd } from '@/lib/jsonld'

const DEFAULT_DESCRIPTION =
  'Descubrí ediciones especiales de manga de todo el mundo: deluxe, box sets, limited editions, artbooks, kanzenban y más.'

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl()),
  title: {
    default: 'PandaWatch — Ediciones especiales de manga',
    template: '%s · PandaWatch',
  },
  description: DEFAULT_DESCRIPTION,
  applicationName: 'PandaWatch',
  alternates: { canonical: '/' },
  openGraph: {
    type: 'website',
    siteName: 'PandaWatch',
    locale: 'es_ES',
    title: 'PandaWatch — Ediciones especiales de manga',
    description: DEFAULT_DESCRIPTION,
    images: [{ url: '/og-default.png', width: 1200, height: 630, alt: 'PandaWatch' }],
  },
  twitter: {
    card: 'summary_large_image',
    images: ['/og-default.png'],
  },
}

export const viewport: Viewport = {
  themeColor: '#0d0d0f',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;1,9..40,400&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <JsonLd data={[websiteJsonLd(), organizationJsonLd()]} />
        <Header />
        {children}
      </body>
    </html>
  )
}
