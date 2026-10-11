---
name: pandawatch-design
description: Use this skill to generate well-branded interfaces and assets for PandaWatch — a premium manga collector database. Contains essential design guidelines, colors, type, fonts, assets, and a full UI kit for the catalog prototype.
user-invocable: true
---

Read the README.md file within this skill, and explore the other available files.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out of assets/ and reference colors_and_type.css for all design tokens. Create static HTML files for the user to view.

If working on production code, read colors_and_type.css for tokens and README.md for full visual foundations (typography, color, spacing, motion, iconography).

The UI kit is in ui_kits/pandawatch/index.html — it is a fully interactive React prototype with three views: Catalog, Collection detail, and Manga detail. Use it as a reference for building real screens.

Key design decisions:
- Background: #F5F1EB (warm paper, not cold white)
- Primary: #1A8A5A (bamboo green)
- Secondary: #D93D1A (vermillion — used sparingly for status only)
- Type: Space Grotesk (headings) + DM Sans (body) + JetBrains Mono (codes/ISBNs)
- Cards: 10px radius, shadow-sm at rest, shadow-md on hover, transform translateY(-3px)
- Rarity: 6 levels (Accessible → Ultra Rare + Unknown), each with color + icon + tooltip
- Cover ratio: 2:3 or 3:4, image-dominant cards
- Price is always secondary, never the hero
- Collection cards use a CSS stack/fan effect (2–3 offset layers behind main card)
- Lucide icons, 16–20px, 1.5px stroke

If the user invokes this skill without guidance, ask what they want to build or design, ask clarifying questions about the surface (web, mobile, component), and act as an expert designer who outputs HTML artifacts or production code depending on the need.
