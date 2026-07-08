import { describe, it, expect } from 'vitest'
import { imageKey } from '@/lib/images'

// WO-G (auditoría post-scrape) — paridad de la clave de dedup de imágenes.
// Tabla de fixtures COMPARTIDA con tests/test_audit_wo_g.py (misma lista URL
// -> clave esperada). Si agregás un caso acá, agregalo también allá. La
// referencia canónica es `manga_watch._img_stem` (Python); ver
// docs/reference/images.md:47-52 (invariante: manga_watch._img_stem /
// web/index.html `imgKey` / web-next `imageKey` deben coincidir).
const IMAGE_KEY_FIXTURES: Array<[url: string, expected: string, note: string]> = [
  [
    'https://cdn.shop.com/files/cover_600x600.jpg',
    'cdn.shop.com/files/cover.jpg',
    'Shopify thumb NxN (guion bajo) — dedupea contra la full',
  ],
  [
    'https://cdn.shop.com/files/cover.jpg',
    'cdn.shop.com/files/cover.jpg',
    'Shopify full (sin sufijo) — misma clave que el thumb de arriba',
  ],
  [
    'https://cdn.shop.com/files/cover_grande.jpg',
    'cdn.shop.com/files/cover.jpg',
    'Shopify sufijo con nombre (_grande) — también se stripea',
  ],
  [
    'https://example.com/wp-content/uploads/cover-800x600.jpg',
    'example.com/wp-content/uploads/cover-800x600.jpg',
    'WordPress -NxN (guion medio) — NO se stripea (gap conocido de la referencia Python)',
  ],
  [
    'https://example.com/wp-content/uploads/cover.jpg',
    'example.com/wp-content/uploads/cover.jpg',
    'WordPress full — clave DISTINTA a la de -800x600.jpg de arriba',
  ],
  [
    'https://example.com/img.jpg?v=12345&utm_source=x',
    'example.com/img.jpg',
    'query params se descartan por completo',
  ],
  [
    'https://example.com/img.jpg?v=1#main',
    'example.com/img.jpg',
    'fragment pegado a un query param — coincide en las 3 implementaciones',
  ],
  ['http://example.com/img.jpg', 'example.com/img.jpg', 'scheme http se stripea'],
  [
    'https://example.com/img.jpg',
    'example.com/img.jpg',
    'scheme https se stripea — misma clave que http de arriba',
  ],
  [
    'https://example.com/plain-cover.png',
    'example.com/plain-cover.png',
    'URL sin nada que strippear',
  ],
  [
    'https://EXAMPLE.com/IMG.JPG',
    'example.com/img.jpg',
    'case-insensitive (host + path se lowercasean)',
  ],
  [
    'https://cdn.shop.com/files/cover_100x100.jpg?v=99',
    'cdn.shop.com/files/cover.jpg',
    'sufijo Shopify + query combinados',
  ],
]

describe('imageKey — paridad con manga_watch._img_stem (WO-G)', () => {
  it.each(IMAGE_KEY_FIXTURES)('%s -> %s (%s)', (url, expected) => {
    expect(imageKey(url)).toBe(expected)
  })

  it('strips a bare "#fragment" explicitly (unlike raw Python _img_stem)', () => {
    // A diferencia de mw._img_stem (que sólo pierde el fragment como
    // side-effect cuando está pegado a un query param descartado — ver
    // tests/test_audit_wo_g.py::test_img_stem_bare_fragment_without_query_is_a_python_only_quirk),
    // imageKey SÍ stripea un "#fragment" standalone por robustez. Esto no
    // rompe la paridad real: canonicalize_url() en Python (urldefrag) ya
    // elimina cualquier fragment ANTES de persistir la URL en images[], así
    // que ninguna URL real llega acá con un "#" bare.
    expect(imageKey('https://example.com/img.jpg#main')).toBe('example.com/img.jpg')
  })
})
