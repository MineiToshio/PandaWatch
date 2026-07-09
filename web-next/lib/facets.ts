import type { Cluster, FacetOption } from './types'

/**
 * Facet de `product_type` (auditoría #21 — filtro fantasma: `FilterParams` y
 * `filterClusters` ya lo soportan pero no había UI, así que `hasActiveFilters`
 * tampoco lo veía si llegaba por URL). Computado ACÁ, fuera de
 * `buildFacets()` (lib/data.ts, archivo protegido en el paquete
 * H2-webnext-ui), para no tocar su lógica — mismo criterio de conteo
 * (values planos → Map → orden desc) sobre TODOS los clusters (global, igual
 * que el resto de los facets, no filtrado por el query actual).
 */
export function productTypeFacet(clusters: Cluster[]): FacetOption[] {
  const map = new Map<string, number>()
  for (const c of clusters) {
    for (const item of c.items) {
      if (!item.product_type) continue
      map.set(item.product_type, (map.get(item.product_type) || 0) + 1)
    }
  }
  return Array.from(map.entries())
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => b.count - a.count)
}
