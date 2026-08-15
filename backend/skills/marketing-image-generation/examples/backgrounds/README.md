# Background library

Drop-in page backgrounds for marketing images, OG cards, and hero sections.
Each `.html` file is a single JSX snippet you can paste straight into
[og-playground.vercel.app](https://og-playground.vercel.app/) or use as the
outer container in a Vercel OG / Satori `ImageResponse`. Rendered previews live
in [`/images/backgrounds`](../../../../images/backgrounds).

## How to use

1. Pick a background and copy its `<div>`.
2. Make it the outermost element of your image.
3. Put your content (headline, logo, screenshot, card) inside it.

Most are pure CSS backgrounds with no child elements, so they compose with any
foreground.

## Satori / og-playground constraints (verified while building these)

These patterns were each rendered through Satori (the engine og-playground and
Vercel OG use) to confirm they render flawlessly. Things to know:

- **No `conic-gradient`.** Satori does not support it — it throws. Sunbursts and
  color wheels are not possible; use `linear-gradient` / `radial-gradient` mixes.
- **Dotted patterns need percentage color stops, not px.**
  `radial-gradient(circle, #fff 2px, transparent 2px)` renders blank.
  Use `radial-gradient(circle at center, #fff 0%, #fff 14%, transparent 15%)`
  with a `backgroundSize` tile instead.
- **Per-layer `backgroundSize` works.** Comma-separate sizes to pair a full-bleed
  glow (`100% 100%`) with a tiled grid (`44px 44px`). Layers paint top-to-bottom.
- **No `mask` / `background-clip` fades.** Fake a fade-out grid by layering a
  radial gradient of the background color on top (see `light-grid-fade`).
- Grid lines (`linear-gradient` pairs) and `repeating-linear-gradient` stripes
  tile reliably.

## Catalog

### Dark
| File | Look |
| --- | --- |
| `dark-dot-grid` | Indigo dot grid on near-black |
| `dark-line-grid` | Graph-paper grid on dark |
| `dark-grid-glow` | Grid with a soft center glow (signature dev-tool look) |
| `dark-mesh-aurora` | Indigo / pink / cyan aurora blobs |
| `dark-diagonal-stripes` | Quiet 45° texture |
| `dark-spotlight` | Top-center spotlight fading to black |
| `dark-crosshatch` | Fine woven crosshatch |
| `dark-dots-vignette` | Dot grid bright in center, fading at edges |
| `dark-dual-gradient` | Deep violet into black |
| `dark-glow-corners` | Twin amber + indigo corner glows |

### Light
| File | Look |
| --- | --- |
| `light-dot-grid` | Soft grey dots on off-white |
| `light-line-grid` | Pale slate graph grid on white |
| `light-blueprint` | Blue major/minor grid on blue |
| `light-grid-fade` | Grid dissolving into a clean white center |
| `light-pastel-mesh` | Peach / sky / lilac pastel blobs |
| `light-warm-gradient` | Cream into coral sunrise wash |
| `light-cool-gradient` | Mint into sky diagonal wash |

### Vibrant
| File | Look |
| --- | --- |
| `vibrant-sunset` | Violet → magenta → amber diagonal |
| `vibrant-ocean` | Indigo → blue → teal diagonal |
| `vibrant-mesh` | Saturated electric blobs on black |
| `vibrant-vertical-stripes` | Candy violet vertical bands |
| `gradient-grid-combo` | White grid over a vivid gradient |
