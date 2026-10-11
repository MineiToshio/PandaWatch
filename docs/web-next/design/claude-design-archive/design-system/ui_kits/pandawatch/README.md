# PandaWatch UI Kit

## Overview
Full interactive prototype of the PandaWatch manga collector catalog. Three views, real filtering, search, and navigation.

## Design Width
- **Desktop:** 1440px max-width, sidebar + grid layout
- **Mobile:** 375px, bottom sheet filters, 2-column grid

## Views
1. **Catalog** (`CatalogView.jsx`) — filterable/searchable grid with hero stats, filter sidebar, sort toolbar, applied filter chips, and manga/collection cards
2. **Collection** (`CollectionView.jsx`) — stacked-cover header, breadcrumb, volume grid with inner filters
3. **Detail** (`DetailView.jsx`) — two-column layout (cover + metadata), signals section, collector notes placeholder, data confidence panel

## Files
| File | Purpose |
|---|---|
| `index.html` | App shell, React root, loads all components |
| `data.js` | Mock data, rarity utils, filter/sort functions |
| `Header.jsx` | Sticky header with logo + search + filter toggle |
| `MangaCard.jsx` | Single card, collection card, rarity badge, cover placeholder |
| `FilterSidebar.jsx` | Desktop sidebar + mobile bottom sheet |
| `CatalogView.jsx` | Home catalog view with hero + grid |
| `CollectionView.jsx` | Collection detail with volume grid |
| `DetailView.jsx` | Manga detail with full metadata |

## Mock Data
6 items across all rarity levels:
- The Promised Neverland Fanbook — **Limited** — France
- Berserk Deluxe Edition — **Rare** — Collection (14 vols)
- One Piece Vol. 100 Variant — **Ultra Rare** — Japan
- Chainsaw Man Box Set — **Limited** — Collection (11 vols)
- Akira 35th Anniversary Box Set — **Very Rare** — Collection (6 vols)
- Naruto Exhibition Fanbook — **Rare** — Japan

## Notes
- Cover images are CSS gradient placeholders (no external image dependency)
- All filtering, sorting, and navigation is fully interactive
- Responsive: detects viewport width and adjusts layout at 768px
- Focus states implemented for keyboard navigation
