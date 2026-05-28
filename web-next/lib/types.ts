// Full types — implemented in WO-004
export type Item = {
  url: string
  title: string
  title_original?: string
  description?: string
  description_es?: string
  image_url?: string
  image_local?: string
  images?: ItemImage[]
  extras?: ItemExtra[]
  price?: string
  release_date?: string
  author?: string
  isbn?: string
  volume?: string
  publisher?: string
  country?: string
  language?: string
  score?: number
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
  minPrice?: string
}

export type FacetOption = {
  value: string
  count: number
}

export type Facets = {
  countries: FacetOption[]
  languages: FacetOption[]
  publishers: FacetOption[]
  productTypes: FacetOption[]
  sourceClasses: FacetOption[]
  signalTypes: FacetOption[]
  scoreRange: { min: number; max: number }
}

export type SortKey =
  | 'score_desc'
  | 'score_asc'
  | 'date_desc'
  | 'date_asc'
  | 'title_asc'
  | 'title_desc'

export type FilterParams = {
  q?: string
  country?: string[]
  language?: string[]
  publisher?: string[]
  product_type?: string[]
  source_class?: string[]
  signal_types?: string[]
  min_score?: number
  only_limited?: boolean
  sort: SortKey
  page: number
}
