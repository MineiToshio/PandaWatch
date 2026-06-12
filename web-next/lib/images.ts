import type { ItemImage } from './types'

/**
 * Clave normalizada de una imagen: sin esquema, sin query/hash, lowercase.
 * Dos URLs que sólo difieren en http/https o en params de tracking son la
 * misma imagen. Única definición — ItemHero y el carrusel deben dedupear con
 * el mismo criterio o la portada puede duplicarse en la galería.
 */
export function imageKey(url?: string): string {
  return (url ?? '')
    .split('?')[0]
    .split('#')[0]
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
