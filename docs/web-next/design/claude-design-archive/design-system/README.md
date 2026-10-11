# PandaWatch Design System

## Product Overview

**PandaWatch v2** is a collector-grade web platform for manga enthusiasts who want to discover rare, special, and variant manga editions before they disappear. Behind the scenes, a scraper aggregates data from publisher sites, manga databases, and trusted media sources — outputting structured JSON with edition metadata, signals, and rarity scoring.

The target audience is collectors aged 18–25, predominantly but not exclusively male, who are actively hunting for fanbooks, deluxe editions, box sets, limited prints, variant covers, premium bindings, and other editions that distinguish themselves from standard tankōbon releases.

**This is not an e-commerce product.** It's a premium collector database — closer in spirit to Discogs for vinyl than Amazon for books.

---

## Sources

This design system was built from the product brief, JSON data schema, and UX research provided directly. No external Figma or codebase was attached. All design decisions are original, derived from the spec.

Relevant data fields defined in the source JSON:
- `title`, `series_display`, `edition_display`, `product_type`
- `publisher`, `country`, `language`, `isbn`
- `score` (0–100, drives rarity estimation)
- `signal_types` / `signals` (e.g. fanbook, deluxe, box-set, variant-cover)
- `source`, `source_class` (trusted_media, marketplace, publisher)
- `status` (new, changed, etc.)
- `detected_at`, `standardized_at`, `release_date`
- `images[]` with `kind: cover`

---

## Design Principles

1. **Cover first** — the manga image dominates every card. Metadata is subordinate.
2. **Collector archive, not storefront** — price is secondary; rarity and signals are primary.
3. **Scan-first hierarchy** — cover → title → rarity badge → edition type → publisher/country.
4. **Filter excellence** — faceted navigation is the core power feature.
5. **Accessible rarity** — never communicate rarity via color alone; always pair with icon + text.
6. **Responsive by intent** — the mobile layout is independently considered, not a desktop reduction.

---

## Content Fundamentals

**Language:** English (international product). UI copy in English throughout.

**Tone:** Authoritative, concise, slightly mysterious. This is a watchlist system — it discovers things before they're gone. Copy should feel like a knowledgeable collector speaking, not a retailer.

**Casing:**
- Navigation labels: Title Case (`Filter Results`, `Most Rare`)
- Badges & tags: Title Case (`Box Set`, `Very Rare`, `Trusted Source`)
- Body copy & descriptions: Sentence case
- ISBN, codes: UPPERCASE or as-issued

**Microcopy examples:**
- `"Find special manga editions before they disappear"`
- `"Why this was detected"` (not "Why It Was Detected")
- `"Rarity estimated from signals, source, and availability"`
- `"No editions found. Try clearing some filters."`
- `"Collection · 14 items"`
- `"Detected recently"` / `"Updated daily"`
- `"Trusted source"` / `"Marketplace signal"`

**Emoji:** Never used in UI. Icon system only.

**Numbers:** Use locale-appropriate number formats. ISBN displayed with prefix: `ISBN 978-2-82034-270-6`.

---

## Visual Foundations

### Color Philosophy
Warm, editorial, paper-based light theme. Avoids cold whites and neon accents. Evokes a collector's archive, a high-quality art book catalog, or a well-curated library.

**Background:** `#F5F1EB` — warm off-white, like aged paper
**Surface:** `#FFFFFF` — clean white for cards
**Surface elevated:** `#FDFCFB` — near-white for overlays
**Border:** `#E5E0D8` — warm grey, not cold
**Text primary:** `#1C1915` — near-black ink
**Text secondary:** `#6B6460` — warm mid-grey
**Text tertiary:** `#9B9490` — captions, de-emphasized

**Primary — Bamboo Green:** Deep, grounded green. Not loud. Referential to bamboo, nature, Japan.
**Secondary — Vermillion:** Manga red. Used sparingly for "new/changed" status and destructive actions.

### Rarity Color System
Five-level rarity, plus Unknown. Each level has a badge color, background tint, and icon. Never communicated by color alone.

| Level | Score | Color | Hex |
|---|---|---|---|
| Accessible | 0–20 | Slate | `#64748B` |
| Limited | 21–40 | Bamboo Green | `#1A8A5A` |
| Rare | 41–65 | Indigo | `#2D52CC` |
| Very Rare | 66–85 | Violet | `#7C3AED` |
| Ultra Rare | 86–100 | Amber/Gold | `#9E6C00` |
| Unknown | null | Gray | `#9CA3AF` |

### Typography
- **Display / Headings:** Space Grotesk — geometric, modern, slightly editorial. Weights 500, 600, 700.
- **Body / UI:** DM Sans — humanist, highly legible at small sizes. Weights 400, 500.
- **Mono / Codes:** JetBrains Mono — for ISBNs, dates, technical values. Weight 400.

All three available on Google Fonts.

### Spacing
4px base grid. Main scale: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96.

### Border Radius
- `2px` — tags, inline chips
- `6px` — inputs, small components
- `10px` — cards
- `16px` — modals, bottom sheets
- `999px` — full pills (status indicators)

### Shadows / Elevation
Three levels:
- **sm:** `0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)` — card resting state
- **md:** `0 4px 12px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04)` — card hover, dropdowns
- **lg:** `0 12px 32px rgba(0,0,0,0.10), 0 4px 8px rgba(0,0,0,0.06)` — modals, bottom sheets

### Animation
- Default easing: `cubic-bezier(0.22, 1, 0.36, 1)` — fast-out, slow ease
- Card hover lift: `transform translateY(-3px)` + shadow upgrade, 180ms
- Badge tooltips: fade in 120ms
- Bottom sheet: slide-up 280ms with ease
- No bounces. No dramatic transitions. Collected, controlled motion.

### Hover States
Cards: slight elevation increase + shadow upgrade + cursor pointer. No color change on card background.
Buttons: darken 8–10% on hover, 6% on press.
Links/chips: background tint on hover (5% opacity fill).

### Cards
White background, 10px border radius, `shadow-sm` at rest, `shadow-md` on hover. Subtle `1px border: #E5E0D8`. Cover image fills top 65–70% of card. Info section below with comfortable padding.

### Imagery
Cover images are the primary visual element. They should be shown at 2:3 or 3:4 aspect ratio, cropped to fill. No filters applied over images. Placeholder covers use brand-themed gradient fills.

### Breakpoints
- Mobile: `< 640px`
- Tablet: `640px – 1024px`
- Desktop: `≥ 1025px`
- Wide: `≥ 1280px`
- Max content width: `1440px`

---

## Iconography

No external icon library is used — this design system recommends **Lucide Icons** (CDN, stroke-based, 1.5px stroke weight, 24px default). Clean, modern, accessible. Lucide aligns with the editorial aesthetic.

Usage notes:
- Always use `width: 16` or `width: 20` in UI contexts (not 24, which is too large for dense catalog UI)
- Stroke color inherits from `currentColor`
- Never use emoji as icons
- Rarity badges use a curated set: Diamond (Ultra Rare), Gem (Very Rare), Sparkles (Rare), Star (Limited), Circle (Accessible), HelpCircle (Unknown)

Key icons in use:
- `Search`, `Filter`, `X` (clear), `ChevronDown`, `ChevronRight`
- `Diamond`, `Gem`, `Sparkle`, `Star`, `Circle`, `HelpCircle` (rarity)
- `BookOpen`, `Box`, `Package`, `Layers` (edition types)
- `Globe`, `Calendar`, `Hash`, `ExternalLink`
- `AlertCircle` (status changed/new)

Logo: custom panda mark (see `assets/logo-mark.svg`). Combined with wordmark in HTML.

---

## File Index

```
/
├── README.md                   ← This file
├── SKILL.md                    ← Agent skill manifest
├── colors_and_type.css         ← CSS custom properties (full token system)
├── assets/
│   ├── logo-mark.svg           ← Panda icon mark (standalone)
│   └── logo.svg                ← Full logo (mark + wordmark)
├── preview/                    ← Design System tab cards
│   ├── brand-logo.html
│   ├── colors-primary.html
│   ├── colors-secondary.html
│   ├── colors-neutrals.html
│   ├── colors-rarity.html
│   ├── colors-semantic.html
│   ├── type-display.html
│   ├── type-body.html
│   ├── type-context.html
│   ├── spacing-tokens.html
│   ├── spacing-radius-shadow.html
│   ├── components-rarity-badges.html
│   ├── components-edition-badges.html
│   ├── components-manga-card.html
│   ├── components-collection-card.html
│   ├── components-header.html
│   ├── components-filter-chips.html
│   └── components-states.html
└── ui_kits/
    └── pandawatch/
        ├── README.md           ← UI kit notes
        ├── index.html          ← Interactive prototype (main entry)
        ├── data.js             ← Mock data + rarity utilities
        ├── Header.jsx          ← Header + search bar
        ├── MangaCard.jsx       ← Single + collection card components
        ├── FilterSidebar.jsx   ← Desktop sidebar + mobile bottom sheet
        ├── CatalogView.jsx     ← Main catalog grid view
        ├── CollectionView.jsx  ← Collection detail view
        └── DetailView.jsx      ← Manga detail view
```

---

## UI Kits

### PandaWatch Web App (`ui_kits/pandawatch/index.html`)
Full interactive prototype of the catalog experience. Three views:
1. **Catalog** — filterable/searchable grid of all tracked editions
2. **Collection** — drill-in view for grouped editions (e.g. Berserk Deluxe 14-volume set)
3. **Detail** — individual manga page with full metadata, signals, data confidence

Design width: 1440px desktop, fully responsive to 375px mobile.
