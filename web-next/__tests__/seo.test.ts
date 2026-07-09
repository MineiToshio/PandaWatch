import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  siteUrl,
  absoluteUrl,
  localImageUrl,
  ogImage,
  seriesPath,
  editionPath,
  itemPath,
  decodeRouteParam,
} from '@/lib/seo'

// seo.ts resuelve origin/imágenes desde env vars — se aíslan por test para que
// el fallback (localhost / symlink) sea determinista.
const ENV_KEYS = [
  'NEXT_PUBLIC_SITE_URL',
  'VERCEL_PROJECT_PRODUCTION_URL',
  'VERCEL_URL',
  'NEXT_PUBLIC_IMAGE_BASE_URL',
] as const

let saved: Record<string, string | undefined>

beforeEach(() => {
  saved = {}
  for (const k of ENV_KEYS) {
    saved[k] = process.env[k]
    delete process.env[k]
  }
})
afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k]
    else process.env[k] = saved[k]
  }
})

describe('siteUrl / absoluteUrl', () => {
  it('cae a localhost cuando no hay env de origin', () => {
    expect(siteUrl()).toBe('http://localhost:3000')
  })

  it('usa NEXT_PUBLIC_SITE_URL y le quita la barra final', () => {
    process.env.NEXT_PUBLIC_SITE_URL = 'https://watch.pandatrack.app/'
    expect(siteUrl()).toBe('https://watch.pandatrack.app')
    expect(absoluteUrl('/item/x')).toBe('https://watch.pandatrack.app/item/x')
  })

  it('se autocanonicaliza contra la URL inyectada por Vercel', () => {
    process.env.VERCEL_URL = 'preview-abc.vercel.app'
    expect(siteUrl()).toBe('https://preview-abc.vercel.app')
  })

  it('absoluteUrl agrega la barra inicial si falta', () => {
    expect(absoluteUrl('images/x.avif')).toBe('http://localhost:3000/images/x.avif')
  })
})

describe('localImageUrl (auditoría #4)', () => {
  it('sin IMAGE_BASE → symlink local en el origin', () => {
    expect(localImageUrl('cover.avif')).toBe('http://localhost:3000/images/cover.avif')
  })

  it('con NEXT_PUBLIC_IMAGE_BASE_URL → bucket (barra final normalizada)', () => {
    process.env.NEXT_PUBLIC_IMAGE_BASE_URL = 'https://cdn.example.com/img/'
    expect(localImageUrl('cover.avif')).toBe('https://cdn.example.com/img/cover.avif')
  })
})

describe('ogImage', () => {
  it('devuelve [] cuando no hay valor', () => {
    expect(ogImage(undefined)).toEqual([])
    expect(ogImage(null)).toEqual([])
  })

  it('usa una URL http(s) tal cual', () => {
    expect(ogImage('https://x.com/a.jpg', 'alt')).toEqual([
      { url: 'https://x.com/a.jpg', alt: 'alt' },
    ])
  })

  it('resuelve un path absoluto contra el origin', () => {
    expect(ogImage('/og-default.png')[0].url).toBe('http://localhost:3000/og-default.png')
  })

  it('un nombre de archivo pelado va al espejo local (localImageUrl)', () => {
    expect(ogImage('cover.avif')[0].url).toBe('http://localhost:3000/images/cover.avif')
  })

  it('el nombre pelado respeta IMAGE_BASE_URL (mismo criterio que JSON-LD)', () => {
    process.env.NEXT_PUBLIC_IMAGE_BASE_URL = 'https://cdn.example.com'
    expect(ogImage('cover.avif')[0].url).toBe('https://cdn.example.com/cover.avif')
  })

  it('alt por defecto = PandaWatch', () => {
    expect(ogImage('https://x.com/a.jpg')[0].alt).toBe('PandaWatch')
  })
})

describe('path builders — percent-encoding de claves no-ASCII', () => {
  it('encodea las claves CJK y hace round-trip con decodeRouteParam', () => {
    const key = '鬼滅の刃'
    const p = seriesPath(key)
    expect(p).toBe(`/series/${encodeURIComponent(key)}`)
    expect(p).not.toContain(key) // el carácter crudo no viaja en la ruta
    const segment = p.split('/')[2]
    expect(decodeRouteParam(segment)).toBe(key)
  })

  it('editionPath / itemPath también encodean', () => {
    expect(editionPath('a b')).toBe('/edition/a%20b')
    expect(itemPath('x/y')).toBe('/item/x%2Fy')
  })

  it('decodeRouteParam devuelve el valor tal cual si no es decodificable', () => {
    expect(decodeRouteParam('%E0%A4%A')).toBe('%E0%A4%A') // secuencia inválida
  })
})
