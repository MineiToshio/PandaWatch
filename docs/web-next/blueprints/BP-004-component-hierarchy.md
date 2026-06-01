# BP-004: Component Hierarchy

**Version:** 1.0  
**Status:** Draft  
**Author:** Architecture session 2026-05-27  
**Related FRDs:** FRD-002, FRD-003, FRD-004, FRD-005

---

## Purpose

Define all components, their location, their Server/Client boundary, their props
interface, and how they compose into pages.

---

## Server vs Client boundary

```
SERVER (no "use client")       CLIENT ("use client" required)
─────────────────────────      ─────────────────────────────
app/layout.tsx                 SidebarFilters.tsx
app/page.tsx                   ImageCarousel.tsx
app/edition/[k]/page.tsx       ThemeToggle.tsx
app/item/[slug]/page.tsx       MobileDrawer.tsx
                               Pagination.tsx (maybe — uses router)
All components/core/*
Most components/modules/*
EditionCard.tsx
ItemCard.tsx
EditionHeader.tsx
ItemHero.tsx (wraps Carousel)
MetaTable.tsx
SourcesList.tsx
```

---

## Component Tree by Page

### Root Layout

```
app/layout.tsx
└── <html data-theme="light">
    └── <body>
        ├── <Header />                          [Server]
        │   ├── <Logo />                        [Server]
        │   ├── <SearchBar />                   [Server — form submit]
        │   └── <ThemeToggle />                 [Client — localStorage]
        └── {children}
```

### Catalog Page (`/`)

```
app/page.tsx                                    [Server]
├── <SidebarFilters facets={...} />             [Client]
│   ├── <SearchInput />                         [Client — debounce]
│   ├── <FilterSection title="País">
│   │   └── <CheckboxList options={facets.countries} />
│   ├── <FilterSection title="Idioma">
│   ├── <FilterSection title="Editorial">
│   ├── <FilterSection title="Tipo">
│   ├── <SignalTypeFilterChips options={facets.signalTypes} />
│   ├── <ScoreRangeSlider min={0} max={300} />
│   └── <ToggleSwitch label="Solo limitadas" />
└── <main>
    ├── <SortBar total={N} sort={...} />        [Client — select onChange]
    ├── <CatalogGrid clusters={[...]} />        [Server]
    │   └── <EditionCard cluster={...} /> × N  [Server]
    │       ├── <CoverImage />                  [Server]
    │       ├── <StackEffect leaves={1|2|3} />  [Server — CSS only]
    │       ├── <Typography />
    │       ├── <Badge />
    │       └── <SignalChip /> × N
    └── <Pagination pages={N} current={N} />   [Client — router.replace]
```

### Edition Detail Page (`/edition/[editionKey]`)

```
app/edition/[editionKey]/page.tsx              [Server]
├── <BackLink href="/" />                       [Server]
├── <EditionHeader cluster={firstCluster} />   [Server]
│   ├── <Heading />
│   ├── <CountryFlag />
│   ├── <SignalChip /> × N
│   └── <Badge />
└── <VolumeGrid clusters={[...]} />            [Server]
    └── <ItemCard cluster={...} /> × N         [Server]
        ├── <CoverImage />
        ├── <VolumeBadge />
        ├── <Typography />
        ├── <ScoreBadge />
        └── <SignalChip /> × N
```

### Item Detail Page (`/item/[slug]`)

```
app/item/[slug]/page.tsx                       [Server]
├── <BackLink href={from} />                   [Server]
└── <article>
    ├── <ItemHero cluster={...} />             [Server]
    │   ├── <ImageCarousel images={...} />     [Client — useState]
    │   │   ├── <img /> (current image)
    │   │   ├── <KindBadge />                  [Server — static label]
    │   │   ├── <CarouselArrows />             [Client — click handlers]
    │   │   └── <CarouselDots />               [Client — active state]
    │   └── <HeroMeta item={...} />            [Server]
    │       ├── <Heading />
    │       ├── <ScoreBadge />
    │       └── <SignalChip /> × N
    ├── <MetaTable item={...} />               [Server]
    ├── <ExtrasSection extras={...} />         [Server — conditional]
    └── <SourcesList items={...} />            [Server — conditional]
```

---

## Component Specifications

### `components/core/`

#### `Button`
```tsx
type ButtonProps = {
  variant: 'primary' | 'secondary' | 'ghost' | 'outline' | 'link' | 'tonal'
  size?: 'sm' | 'md' | 'lg'
  className?: string
  children: React.ReactNode
} & React.ButtonHTMLAttributes<HTMLButtonElement>
```

#### `Chip`
```tsx
type ChipProps = {
  variant: 'accent' | 'neutral' | 'info' | 'success' | 'warning' | 'destructive'
  size?: 'sm' | 'md'
  dismissible?: boolean
  onDismiss?: () => void
  className?: string
  children: React.ReactNode
}
```

#### `Badge` (variant chip)

> ⚠️ **Actualizado 2026-06-01:** `ScoreBadge` se eliminó (archivo borrado) junto
> con todo el score de la UI. `Badge` quedó como chip genérico por `variant`
> (sin derivación por score). Las referencias a `<ScoreBadge />` en los árboles
> de componentes de este doc son históricas.

```tsx
type BadgeProps = {
  children: React.ReactNode
  variant?: 'auto' | 'green' | 'yellow' | 'orange' | 'red' | 'neutral'
  className?: string
}
// 'auto' derives color from numeric children: ≥200=green, ≥100=yellow, ≥50=orange, else=red
```

#### `Heading`
```tsx
type HeadingProps = {
  as: 'h1' | 'h2' | 'h3' | 'h4'
  size?: 'display' | 'h1' | 'h2' | 'h3' | 'h4'  // decouple visual from semantic
  className?: string
  children: React.ReactNode
}
```

#### `Typography`
```tsx
type TypographyProps = {
  variant: 'body' | 'body-sm' | 'caption' | 'eyebrow'
  as?: 'p' | 'span' | 'div' | 'label'
  className?: string
  children: React.ReactNode
}
```

---

### `components/modules/`

#### `SignalChip`
```tsx
type SignalChipProps = {
  signal: string  // e.g. "box_set", "limited", "variant_cover"
  size?: 'sm' | 'md'
}
// Derives icon and label from a SIGNAL_META map
// Derives variant (Chip color) from a SIGNAL_COLOR map
```

SIGNAL_META map:
```typescript
const SIGNAL_META: Record<string, { icon: string; label: string; chipVariant: ChipVariant }> = {
  limited:           { icon: '🏷️', label: 'Edición Limitada',     chipVariant: 'accent' },
  special_edition:   { icon: '⭐',  label: 'Edición Especial',     chipVariant: 'accent' },
  collector:         { icon: '🏆',  label: 'Coleccionista',        chipVariant: 'accent' },
  box_set:           { icon: '📦',  label: 'Cofre / Box Set',      chipVariant: 'info' },
  variant_cover:     { icon: '🎨',  label: 'Portada Alternativa',  chipVariant: 'neutral' },
  artbook:           { icon: '🖼️', label: 'Artbook',              chipVariant: 'info' },
  deluxe:            { icon: '💎',  label: 'Deluxe',               chipVariant: 'accent' },
  hardcover:         { icon: '📚',  label: 'Tapa Dura',            chipVariant: 'neutral' },
  kanzenban:         { icon: '🗾',  label: 'Kanzenban',            chipVariant: 'info' },
  lore_edition:      { icon: '✨',  label: 'Edición Especial',     chipVariant: 'success' },
  omnibus:           { icon: '📖',  label: 'Ómnibus',              chipVariant: 'neutral' },
  bonus:             { icon: '🎁',  label: 'Con Extra',            chipVariant: 'success' },
  retailer_exclusive:{ icon: '🏪',  label: 'Exclusivo Tienda',     chipVariant: 'warning' },
}
```

#### `ScoreBadge`
```tsx
type ScoreBadgeProps = {
  score: number
  showLabel?: boolean  // "Score: 250" vs just "250"
}
```

#### `CoverImage`
```tsx
type CoverImageProps = {
  imageLocal?: string   // filename in data/images/
  imageUrl?: string     // remote URL fallback
  alt: string
  sizes?: string        // Next.js Image sizes prop
  priority?: boolean    // above-fold images
}
// Renders Next.js <Image> with local path → remote fallback → emoji placeholder
```

#### `CountryFlag`
```tsx
type CountryFlagProps = {
  country: string    // "Japan", "España", "France", etc.
  showLabel?: boolean
}
// Maps country name to emoji flag + optional text label
```

---

### `components/catalog/`

#### `EditionCard`
```tsx
type EditionCardProps = {
  cluster: Cluster
  priority?: boolean  // for above-fold images
}
// Server Component
// Renders as <Link href="/edition/[editionKey]" OR "/item/[slug]">
```

#### `SidebarFilters` (Client Component)
```tsx
type SidebarFiltersProps = {
  facets: Facets
  current: ParsedFilterParams
}
```

#### `SortBar`
```tsx
type SortBarProps = {
  total: number
  sort: SortKey
  page: number
  pages: number
}
```

#### `Pagination`
```tsx
type PaginationProps = {
  total: number    // total pages
  current: number  // current page (1-indexed)
}
// Client Component — router.replace on page click
```

---

### `components/item/`

#### `ImageCarousel` (Client Component)
```tsx
type ImageCarouselProps = {
  images: ItemImage[]
  alt: string
}
```

#### `MetaTable`
```tsx
type MetaTableProps = {
  item: Item
  showAll?: boolean  // show fields even if empty
}
```

#### `SourcesList`
```tsx
type SourcesListProps = {
  items: Item[]   // all items in the cluster
}
// Only renders if items.length > 1
```

---

## CSS Conventions

### Stack effect
```css
/* Set data-leaves="1|2|3" on the card wrapper */
.edition-card { position: relative; }
.edition-card[data-leaves="2"]::before {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: inherit;
  transform: translate(5px, 5px);
  z-index: -1;
}
.edition-card[data-leaves="3"]::before { transform: translate(5px, 5px); z-index: -1; }
.edition-card[data-leaves="3"]::after  { transform: translate(10px, 10px); z-index: -2; }
```

### Cover image aspect ratio
All cover images use `aspect-[2/3]` (standard book cover ratio) with `object-fit: cover`.
