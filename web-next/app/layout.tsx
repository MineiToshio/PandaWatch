import type { Metadata, Viewport } from 'next'
import { Suspense } from 'react'
import { Space_Grotesk, DM_Sans, JetBrains_Mono } from 'next/font/google'
import './globals.css'
import { Header } from '@/components/modules/Header'
import { NavigationTracker } from '@/components/modules/NavigationTracker'
import { JsonLd } from '@/components/seo/JsonLd'
import { siteUrl } from '@/lib/seo'
import { websiteJsonLd, organizationJsonLd } from '@/lib/jsonld'

// Self-hosted vía next/font (antes: <link> a Google Fonts — FOUT + warning de
// lint). globals.css consume estas variables en --font-display/body/mono.
const spaceGrotesk = Space_Grotesk({ subsets: ['latin'], variable: '--font-space-grotesk' })
const dmSans = DM_Sans({ subsets: ['latin'], style: ['normal', 'italic'], variable: '--font-dm-sans' })
const jetbrainsMono = JetBrains_Mono({ subsets: ['latin'], variable: '--font-jetbrains-mono' })

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
    <html
      lang="es"
      suppressHydrationWarning
      className={`${spaceGrotesk.variable} ${dmSans.variable} ${jetbrainsMono.variable}`}
    >
      <body>
        <JsonLd data={[websiteJsonLd(), organizationJsonLd()]} />
        {/* useSearchParams → Suspense para no des-estatizar las páginas de detalle */}
        <Suspense fallback={null}>
          <NavigationTracker />
        </Suspense>
        <Header />
        {children}
      </body>
    </html>
  )
}
