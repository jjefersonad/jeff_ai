# Layout library

Common marketing-asset layouts as ready-to-fill JSX snippets. All copy is
**generic placeholder text** ("A short, bold headline", "Feature one") with no
brand-specific wording, so each is a clean starting skeleton. Paste a file into
[og-playground.vercel.app](https://og-playground.vercel.app/) or use it as the
root element of a Vercel OG / Satori `ImageResponse`. Rendered previews live in
[`/images/layouts`](../../../../images/layouts).

Default canvas is 1200×630 (OG/social card size). Each layout was rendered
through Satori to confirm it composes cleanly.

## How to use

1. Pick a layout and copy its outer `<div>`.
2. Replace placeholder copy, numbers, avatars, and accent colors.
3. Swap grey skeleton blocks / window bodies for real screenshots or logos
   (see the `brand-logos` skill for vector logos).

## Satori reminders (apply to all layouts)

- Every element with **two or more children needs `display: flex`** and a
  `flexDirection` — Satori throws otherwise. The snippets already follow this.
- Layout is **flexbox only** — no CSS grid, float, or `position` tricks beyond
  `absolute`/`relative`.
- `backgroundClip: 'text'` (gradient text) works; `conic-gradient` does not.
- Inline `<svg>` works for icons (checks, stars). Pair it with a background
  from `../backgrounds/` for a textured canvas.

## Catalog

| File | Use |
| --- | --- |
| `hero-centered` | Centered launch hero: headline, subhead, two buttons |
| `hero-split` | Copy left, product/visual card right |
| `feature-trio` | Three feature cards with icon + title + description |
| `stat-trio` | Three big metrics on a dark band |
| `big-number` | One dominant hero stat with label and context |
| `quote-testimonial` | Large pull-quote with avatar + name/role |
| `social-proof-bar` | Star rating, score, avatar stack, count |
| `logo-cloud` | "Trusted by" strip of logo placeholders |
| `announcement-banner` | Release / changelog card: title + one detail line |
| `blog-header` | Editorial header: title, author + date |
| `pricing-card` | Single highlighted plan with price + checklist |
| `cta-banner` | Full-bleed gradient call-to-action with button |
| `checklist-feature` | Headline left, vertical checklist of capabilities right |
| `steps-howitworks` | Three numbered steps in a row |
| `comparison-two-col` | Muted "old way" vs highlighted "new way" columns |
| `product-showcase` | Browser-window mockup floating on a tinted backdrop |
| `terminal-window` | Terminal / CLI window mockup for dev tools |
| `event-webinar` | Date block + title + speaker row for live sessions |
