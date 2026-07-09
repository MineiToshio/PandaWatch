// Full types — implemented in WO-004
export type Item = {
  url: string
  title: string
  title_original?: string
  // Bonus de compra de UN retailer (店舗特典) separado del título oficial
  // (gotcha #93). Va en el detalle, NO en el grid.
  store_bonus?: string
  description?: string
  description_es?: string
  // Portada = images[0] (única fuente de verdad, 2026-06-09). Los campos
  // top-level image_url/image_local fueron eliminados del item. (SourceEntry
  // SÍ conserva los suyos per-fuente — es otro layer.)
  images?: ItemImage[]
  extras?: ItemExtra[]
  release_date?: string
  author?: string
  isbn?: string
  volume?: string
  publisher?: string
  country?: string
  language?: string
  signal_types?: string[]
  product_type?: string
  source_class?: string
  source?: string
  cluster_key: string
  slug?: string
  series_key?: string
  series_display?: string
  edition_key?: string
  edition_display?: string
  standardized_at?: string
  detected_at?: string
  stock_type?: string
  rarity?: 'common' | 'rare' | 'super_rare' | 'ultra_rare'
  // Modelo 1-fila-por-producto: cada fila lleva todas las fuentes donde se
  // encontró el producto (name/url/country/stock_type…). Lo escribe
  // append_jsonl al ingestar; ver CLAUDE.md decisión #1.
  sources?: SourceEntry[]
}

export type SourceEntry = {
  name?: string
  source_class?: string
  country?: string
  publisher?: string
  language?: string
  url: string
  image_url?: string
  image_local?: string
  stock_type?: string
  detected_at?: string
  release_date?: string
}

export type ItemImage = {
  url: string
  local?: string
  kind: 'cover' | 'gallery' | 'extra' | 'variant_cover' | 'back_cover'
  description?: string
}

export type ItemExtra = {
  description: string
  description_es?: string
  release_date?: string
  source_section?: string
}

export type Cluster = {
  clusterKey: string
  slug: string
  canonical: Item
  items: Item[]
  editionKey?: string
  editionDisplay?: string
  seriesDisplay?: string
  volume?: string
  volumeCount: number
  signalTypes: string[]
  countries: string[]
  publishers: string[]
  languages: string[]
  // Índice de búsqueda normalizado (title/title_original/series/publishers/isbn),
  // precomputado una vez por cluster en el data layer. NO afecta el display del
  // título (política de títulos). Opcional: clusters de fixtures pueden omitirlo.
  searchText?: string
}

export type FacetOption = {
  value: string
  count: number
}

export type Facets = {
  countries: FacetOption[]
  languages: FacetOption[]
  publishers: FacetOption[]
  signalTypes: FacetOption[]
}

export type SortKey =
  | 'date_desc'
  | 'date_asc'
  | 'title_asc'
  | 'title_desc'

export type Series = {
  seriesKey: string
  seriesDisplay: string
  cover: { imageLocal?: string; imageUrl?: string }
  editionCount: number
  itemCount: number
  countries: string[]
  publishers: string[]
  signalTypes: string[]
  topRarity?: Item['rarity']
}

export type FilterParams = {
  q?: string
  country?: string[]
  language?: string[]
  publisher?: string[]
  product_type?: string[]
  source_class?: string[]
  signal_types?: string[]
  rarity?: string[]
  only_limited?: boolean
  sort: SortKey
  page: number
}
