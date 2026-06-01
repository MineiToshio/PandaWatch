# FRD-002: Design System

**Version:** 2.0  
**Status:** Active  
**Author:** 2026-05-27 (updated from Claude Design handoff bundle)  
**Related:** [BP-001](blueprints/BP-001-architecture.md), [WO-002](work-orders/WO-002-design-system.md)

---

## Overview

Implement the **PandaWatch Design System** as the visual foundation for the Next.js app.
The design system was created with Claude Design and is documented in the handoff bundle
at `/tmp/design_bundle/pandawatch-design-system/`. The canonical token source is
`project/colors_and_type.css` in that bundle.

This is **not** a port of PandaTrack. The PandaWatch design system has its own
identity: warm editorial paper aesthetic, Bamboo Green primary, Vermillion secondary,
Space Grotesk + DM Sans typography, light theme only.

---

## Design Identity

**Personality:** Premium collector archive. Closer to Discogs (vinyl database) than
Amazon (storefront). Authoritative, concise, slightly mysterious.

**Visual mood:** Warm paper/editorial. Aged off-white background. Deep green accent.
Manga red for status. Not cold, not neon, not gacha.

**Audience:** Manga collectors 18–25 hunting special editions, variants, deluxe prints.

---

## Functional Requirements

### FR-1: Color Tokens

Implement the full token set from `colors_and_type.css` in `app/globals.css`.
All values are hex — **no OKLCH**. **No dark mode** in this version (light theme only).

**Core palette:**

```css
/* Bamboo (Primary Green) */
--bamboo-500: #1A8A5A;   /* primary action */
--bamboo-600: #147047;   /* hover */
--bamboo-700: #0F5637;   /* active */
--bamboo-50:  #EDFAF3;   /* subtle tint */
--bamboo-100: #D4F0E3;   /* tint */

/* Vermillion (Secondary / Status) */
--vermillion-500: #D93D1A;   /* secondary action, "new" status */
--vermillion-600: #B53215;   /* hover */
--vermillion-50:  #FEF3EF;   /* subtle tint */

/* Ink (Neutrals) */
--ink-900: #1C1915;   /* primary text / ink black */
--ink-800: #3B3632;   /* emphasis text */
--ink-700: #554D49;   /* body text */
--ink-600: #706560;   /* medium text */
--ink-500: #8C8178;   /* secondary text */
--ink-400: #A89E93;   /* tertiary text */
--ink-300: #C6BEB4;   /* placeholder, disabled */
--ink-200: #DDD8CF;   /* borders */
--ink-100: #EDE9E2;   /* subtle dividers */
--ink-50:  #F5F1EB;   /* page background */

/* Semantic aliases */
--color-bg:      var(--ink-50);    /* #F5F1EB warm paper */
--color-surface: #FFFFFF;          /* card/panel surface */
--color-border:  var(--ink-200);   /* #DDD8CF default border */
--color-primary: var(--bamboo-500);
--color-secondary: var(--vermillion-500);

/* Text hierarchy */
--color-text-primary:   var(--ink-900);
--color-text-secondary: var(--ink-500);
--color-text-tertiary:  var(--ink-400);
--color-text-disabled:  var(--ink-300);
--color-text-inverse:   #FFFFFF;
```

### FR-2: Typography

Google Fonts loaded in `<head>` of `layout.tsx`. Three typefaces:

| Role | Font | Weights |
|---|---|---|
| `--font-display` | Space Grotesk | 400, 500, 600, 700 |
| `--font-body` | DM Sans | 400, 500 (also italic 400) |
| `--font-mono` | JetBrains Mono | 400, 500 |

Body default: `DM Sans`, 16px base, 1.5 line-height.
Heading default: `Space Grotesk`, tracking tight.
Mono usage: ISBNs, dates, technical codes.

**Type classes (semantic):**

| Class | Font | Size | Weight |
|---|---|---|---|
| `.pw-h1` | Space Grotesk | 2.25rem | 700 |
| `.pw-h2` | Space Grotesk | 1.875rem | 600 |
| `.pw-h3` | Space Grotesk | 1.5rem | 600 |
| `.pw-h4` | Space Grotesk | 1.125rem | 500 |
| `.pw-body-lg` | DM Sans | 1.125rem | 400 |
| `.pw-body` | DM Sans | 1rem | 400 |
| `.pw-body-sm` | DM Sans | 0.875rem | 400 |
| `.pw-caption` | DM Sans | 0.75rem | 400 |
| `.pw-label` | DM Sans | 0.75rem | 500, uppercase, tracking wide |
| `.pw-mono` | JetBrains Mono | 0.875rem | 400 |

### FR-3: Rarity System

The rarity badge is the most important UI component. It appears on every manga card.

Five levels plus Unknown. Score ranges map to rarity. **Each badge must show icon + text,
never color alone.**

| Level | Score | Foreground | Background | Border | Lucide Icon | (Bundle SVG hint) |
|---|---|---|---|---|---|---|
| Accessible | 0–20 | `#64748B` | `#F1F5F9` | `#CBD5E1` | `Circle` | circle |
| Limited | 21–40 | `#1A8A5A` | `#EDFAF3` | `#A6DFCA` | `Star` | star |
| Rare | 41–65 | `#2D52CC` | `#EEF2FF` | `#C7D2FE` | `Sparkles` | star2 |
| Super Rare | 66–85 | `#7C3AED` | `#F5F3FF` | `#DDD6FE` | `Gem` | sparkle |
| Ultra Rare | 86–100 | `#9E6C00` | `#FFFBEB` | `#FDE68A` | `Diamond` | diamond |
| Unknown | null | `#9CA3AF` | `#F9FAFB` | `#E5E7EB` | `HelpCircle` | help |

Token names in CSS: `--rarity-<level>-fg`, `--rarity-<level>-bg`, `--rarity-<level>-border`.

**Note:** The 4th level is **Super Rare** (not "Very Rare") — confirmed in the design session
(chat3.md). The icon mapping above uses Lucide equivalents; the original bundle drew custom
SVGs which roughly correspond to (Circle / 5-pt-star / 5-pt-star-outline / 4-pt-sparkle /
filled-diamond / question-circle). Lucide's `Sparkles` is the closest match to the "star2"
outline-star used for Rare; `Gem` evokes the same "collectible jewel" feel as the bundle's
"sparkle" for Super Rare.

**Shape & sizing — sourced from the authoritative `preview/components-rarity-badges.html`
card in the bundle (NOT from MangaCard.jsx, which uses a tighter compact variant for inside
a card grid):**

| Size | Radius | Padding | Font size | Icon size | Gap | Icon stroke |
|---|---|---|---|---|---|---|
| `sm` | 4px | `3px 7px`  | 10px | 10px | 4px | 2.5 |
| `md` | 6px | `5px 10px` | 12px | 13px | 6px | 2   |
| `lg` | 8px | `7px 14px` | 13px | 15px | 7px | 2   |

The badge is a **rounded rectangle**, NOT a pill. Font family is Space Grotesk
(`--font-display`), weight 600.

`Unknown` rarity uses `border-style: dashed` in both modes (to make "no data yet"
visually distinct from a confirmed-but-low rarity).

The badge has two display modes:
- **Light** (default): uses bg/border/fg token set — for use in info sections, list rows,
  metadata tables.
- **Glassy** (on cover): `background: rgba(20,17,14,0.82)` + `backdrop-filter: blur(6px)`,
  border `1px solid rgba(255,255,255,0.12)` (or `rgba(255,255,255,0.08)` when dashed).
  The foreground color is NOT the light-mode `fg` — it switches to a brighter on-dark
  variant (the "On card" column in the preview's "Rarity Scale — Token Reference" table):

  | Tier | Light `fg` | Glassy `fg` |
  |---|---|---|
  | Accessible | `#64748B` | `#9CA3AF` |
  | Limited    | `#1A8A5A` | `#4DC99A` |
  | Rare       | `#2D52CC` | `#8BA8F8` |
  | Super Rare | `#7C3AED` | `#C4A8FF` |
  | Ultra Rare | `#9E6C00` | `#FDE68A` |
  | Unknown    | `#9CA3AF` | `rgba(255,255,255,0.4)` |

  Without this fg switch the dark-mode fg would sit illegibly close to the glassy bg.

### FR-3b: Chip / SignalChip / Button — sizing tables

The bundle distinguishes three distinct "chip" shapes that must NOT be conflated:

**`core/Chip` — filter chip (applied filters bar, sidebar selections).**
Spec: `preview/components-filter-chips.html`. Rounded **rectangle**, not pill.

| Size | Radius | Padding | Font size | Gap |
|---|---|---|---|---|
| `md` | 6px | `5px 10px` | 12px | 5px |
| `sm` | 5px | `3px 8px`  | 11px | 4px |

Dismiss button (when `dismissible`): 14×14, radius 3, background
`rgba(<fg>, 0.15)` for colored variants or `rgba(255,255,255,0.18)` for the dark variant.
Internal X-mark SVG is 8×8 stroke-width 3.

Variant colors (bg / border / fg): accent `#EDFAF3 / #A6DFCA / #1A8A5A`,
info `#EEF2FF / #C7D2FE / #2D52CC`, warning `#FFFBEB / #FDE68A / #9E6C00`,
destructive `#FEF3EF / #FABEAD / #D93D1A`, neutral ink-100/ink-200/ink-600,
dark `#1C1915 / transparent / #FFFFFF` (used for free-text filter chips like
"Japan" / "Shueisha" in the preview).

**`modules/SignalChip` — signal/why-detected tag inside cards.**
Spec: `preview/components-edition-badges.html` → "Signal Chips". Pill (`radius: 999`).

| Size | Padding | Font size | Icon size | Gap |
|---|---|---|---|---|
| `md` | `3px 8px` | 11px | 10px | 4px |
| `sm` | `2px 7px` | 10px | 9px  | 3px |

Weight 500, DM Sans. Color = tinted bg + same-hue fg per signal type (e.g. fanbook /
limited → `#EDFAF3 / #1A8A5A`, deluxe → `#EEF2FF / #2D52CC`, variant-cover /
retailer-exclusive → `#FFFBEB / #9E6C00`). Neutral fallback `#EDE9E2 / #706560`.

**`core/Button` — CTA / action button.**
Spec: composite of `preview/components-states.html` (action buttons) +
`preview/components-header.html` (filter button).

| Size | Height | Padding-x | Font size | Notes |
|---|---|---|---|---|
| `sm` | 32px   | 12px | 12px | secondary actions, chip-adjacent |
| `md` | 38px   | 16px | 13px | primary CTA — matches the bundle's "Show 128 results" / "Try again" |
| `lg` | 44px   | 20px | 14px | hero / oversized — rare; used for empty-state primary action |

Font: Space Grotesk weight 600 across all sizes. Radius 8px. Gap 8 between icon and label.
Primary fill `#1A8A5A` → hover `#147047` → active `#0F5637`; secondary surface white with
border `1px solid var(--ink-200)`; ghost variant transparent with border on hover.

**Status badges (`New` / `Changed` / `No stock`)** are NOT `Chip` instances — they are
pill `999px` with `padding: 3px 8px`, font 10px weight 600 uppercase, optional 5×5 colored
dot on the left. Colors: `New` `#FEF3EF / #FABEAD / #D93D1A`,
`Changed` `#FFFBEB / #FDE68A / #9E6C00`, `No stock` `#F9FAFB / #E5E7EB / #9CA3AF`.

### FR-4: Core Component Library

Located in `components/core/`. Server Components by default.

| Component | File | Purpose |
|---|---|---|
| `Button` | `Button/index.tsx` + `buttonVariants.ts` | CTAs with CVA variants |
| `Chip` | `Chip.tsx` | Filter chips, applied filters |
| `Heading` | `Heading.tsx` | Semantic + visual size decoupled |
| `Typography` | `Typography.tsx` | Body/caption/label text |
| `Icon` | `Icon.tsx` | Lucide icons at consistent sizes |
| `RarityBadge` | `RarityBadge.tsx` | **New** — core rarity chip (see FR-3) |

**Button primary = Bamboo Green** (`#1A8A5A`), not pink. Hover: `#147047`.
Focus ring: `rgba(26, 138, 90, 0.45)`.

### FR-5: Module Components

Located in `components/modules/`. App-specific components.

| Component | File | Purpose |
|---|---|---|
| `Header` | `Header.tsx` | Sticky header: panda mark + wordmark + search |
| `SearchBar` | `SearchBar.tsx` | Client Component (focus state) — used by `Header` |
| `SignalChip` | `SignalChip.tsx` | Signal type tags (no emoji — Lucide icons only) |
| ~~`ScoreBadge`~~ | — | **ELIMINADO 2026-06-01** junto con todo el score de la UI (sort + visual). El archivo `ScoreBadge.tsx` se borró; `Badge` quedó como chip genérico por variante (sin derivación por score). |
| `CountryFlag` | `CountryFlag.tsx` | Country + flag |

**SearchBar behaviour (updated 2026-05-30):**

- **Debounce:** 600ms after the last keystroke. Increased from 300ms to give users
  time to finish typing without interruptions.
- **Enter key:** fires the search immediately, cancelling any pending debounce timer.
- **URL→input sync guard:** a `focusedRef` (React ref, not state) tracks whether the
  input is focused. The `useEffect` that syncs `params → query` is guarded by
  `if (!focusedRef.current)`, so a `router.replace()` triggered mid-typing never
  overwrites the user's current input. Without this guard, the prior 300ms debounce
  caused the URL to update, which changed `params`, which called `setQuery()`,
  visibly deleting characters the user had typed after the debounce fired.
- **Immediate clear:** the ✕ button clears both the input and the URL param instantly
  (no debounce).

**Header logo asset:** the panda mark is `public/panda-mark.png` (copied from the design
bundle at `project/assets/panda-mark.png`). Rendered at 32×32 with `object-fit: contain`,
to the left of the "**Panda**Watch" wordmark. Transparent background, so it sits cleanly on
any surface.

### FR-6: `cn()` Utility

```ts
// lib/styles.ts
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)) }
```

### FR-7: Layout

`app/layout.tsx` must:
1. Load Google Fonts (Space Grotesk, DM Sans, JetBrains Mono) via `<link>` in `<head>`.
2. No dark mode toggle — light theme only, no `data-theme` attribute needed.
3. No anti-FODT script (dark mode doesn't exist).
4. Apply `font-body` to `<body>`, `color-bg` as page background.

---

## Non-Functional Requirements

- **No emoji in UI.** Icon system (Lucide) only. `SignalChip` must use Lucide icons.
  **Sole exception:** `CountryFlag` uses Unicode regional-indicator flag emoji (🇯🇵, 🇪🇸, …),
  because there is no equivalent Lucide icon set with per-country flags and emoji flags
  render natively in every browser at any size.
- **No dark mode.** Light theme only. Remove any `data-theme` / `ThemeToggle` logic.
- **Accessibility:** Rarity never communicated by color alone — always icon + text + color.
  Focus rings: `2px solid #1A8A5A` / `outline-offset: 2px`.
- **Performance:** Google Fonts with `display=swap` and `preconnect` hints.
- **Browser support:** Modern evergreen browsers only.

---

## UI Copy Rules

- Navigation labels: Title Case
- Badges & tags: Title Case (`Box Set`, `Super Rare`, `Trusted Source`)
- Body copy: Sentence case
- ISBN / codes: as-issued
- Language: English throughout

---

## Out of Scope

- Dark mode (deferred).
- Animation library (CSS transitions only).
- Complex form components.

---

## Acceptance Criteria

- [ ] Page background is `#F5F1EB` (warm paper), not white, not pink
- [ ] Primary CTA buttons are Bamboo Green (`#1A8A5A`)
- [ ] Header shows "Panda" (bold, `#1C1915`) + "Watch" (regular, `#1A8A5A` green)
- [ ] Google Fonts load: Space Grotesk visible in headings, DM Sans in body
- [ ] `<RarityBadge level="super-rare" />` renders with violet (`#7C3AED`) + Gem icon
- [ ] `<RarityBadge level="ultra-rare" />` renders with amber (`#9E6C00`) + Diamond icon
- [ ] No emoji anywhere in the UI
- [ ] No dark mode toggle / ThemeToggle component visible
- [ ] `npm run build` has no TypeScript errors
