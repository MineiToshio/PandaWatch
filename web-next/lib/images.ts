import type { ItemImage } from './types'

// Sufijos de tamaño de CDN a stripear ANTES de la extensión, para que un
// thumb (`img_600x600.jpg`, `img_grande.jpg`) dedupee contra la imagen full
// (`img.jpg`). Sólo cubre sufijos con GUION BAJO estilo Shopify — los de
// WordPress con GUION MEDIO (`img-800x600.jpg`) NO se stripean: es una
// limitación conocida de la referencia canónica en Python
// (scripts/manga_watch.py `_gallery_url_normalize` / `_img_stem`; su
// docstring menciona "WP -NxM" pero la regex nunca lo implementó). Ver
// __tests__/images.test.ts / tests/test_audit_wo_g.py (WO-G).
const IMG_KEY_SUFFIX_RE =
  /_(?:\d+x\d+|small|medium|grande|large|master|compact|original|x\d+|pico|icon|thumb|mini|crop_center)(?=\.(?:jpe?g|png|webp|gif|avif)(?:\?|$))/gi

/**
 * Clave normalizada de una imagen: sin sufijo de tamaño de CDN conocido, sin
 * esquema, sin query/hash, lowercase. Dos URLs que sólo difieren en
 * http/https, en params de tracking, o en el sufijo de miniatura Shopify son
 * la misma imagen.
 *
 * MISMA semántica que `manga_watch._img_stem` (Python, fuente canónica) y
 * `web/index.html` `imgKey` — si tocás una, tocá las tres
 * (docs/reference/images.md#carrusel-cluster). Única definición acá — ItemHero
 * y el carrusel deben dedupear con el mismo criterio o la portada puede
 * duplicarse en la galería.
 */
export function imageKey(url?: string): string {
  return (url ?? '')
    .replace(IMG_KEY_SUFFIX_RE, '')
    .split(/[?#]/)[0]
    .replace(/^https?:\/\//, '')
    .toLowerCase()
}

/**
 * Dedup por URL normalizada conservando el orden de entrada. Si una entrada
 * duplicada trae `local` y la conservada no, se lo presta (la galería a veces
 * tiene el archivo espejado aunque la entrada de portada no).
 */
export function dedupeImages(images: ItemImage[]): ItemImage[] {
  const seen = new Map<string, number>()
  const out: ItemImage[] = []
  for (const img of images) {
    if (!img?.url) continue
    const key = imageKey(img.url)
    if (!key) continue
    const idx = seen.get(key)
    if (idx === undefined) {
      seen.set(key, out.length)
      out.push(img)
    } else if (!out[idx].local && img.local) {
      out[idx] = { ...out[idx], local: img.local }
    }
  }
  return out
}
