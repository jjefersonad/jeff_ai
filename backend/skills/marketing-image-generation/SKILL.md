---
name: marketing-image-generation
description: Generate high-quality marketing images, ad creatives, launch visuals, social cards, blog headers, product mockups, thumbnails, and campaign assets. Use when the user asks to create, design, iterate on, or prompt an image for marketing, growth, social media, paid ads, landing pages, newsletters, or product launches.
---

# Marketing Image Generation

## Core Workflow

1. Identify the asset type: ad, social post, blog header, hero image, launch graphic, thumbnail, email banner, product mockup, or campaign visual.
2. Gather only missing essentials: goal, audience, channel, dimensions or aspect ratio, required copy, brand constraints, product context, and output count.
3. Check available context before asking: README, `DESIGN.md`, brand files, existing screenshots, product copy, and any user-provided reference images.
4. Draft a concrete visual direction before generating: subject, layout, composition, style, color palette, typography direction, lighting, mood, camera/framing, and constraints.
5. Use the image generation tool only when the user has explicitly asked for an image asset or visual mockup.
6. Review the result against the brief, then iterate with targeted changes instead of rewriting the whole concept.

## Marketing Defaults

- Prefer one strong focal point over collages.
- Make the product, benefit, or audience instantly legible at thumbnail size.
- Use short text in images. If copy is required, preserve it exactly and keep it to a headline or label.
- For product-led assets, show a plausible interface, workflow, or user outcome rather than decorative UI fragments.
- For paid ads, optimize for immediate comprehension, contrast, and a clear emotional hook.
- For editorial/blog assets, prefer a concept-driven image that supports the article thesis without repeating the title literally.

## Anti-Patterns and Prompt Template

For the "AI slop" anti-pattern checklist and the prompt template to use when calling
the image generation tool, see `image-generation/SKILL.md` — this content is not
duplicated here.

## Channel Guidance

- LinkedIn or X launch image: 16:9 or 1.91:1, bold single message, product screenshot or conceptual hero, readable at feed size.
- Instagram or TikTok cover: 4:5 or 9:16, centered subject, high contrast, minimal text, strong hook.
- Blog header: 16:9, editorial composition, room for title overlay if needed, avoid ad-like CTA styling.
- Landing page hero: wide composition, clean negative space, product context, brand-consistent lighting and palette.
- Paid ad: clear benefit, high contrast, direct product/category cues, no tiny UI details, no dense copy.

## Iteration Rules

When revising a generated image:

- Change one or two variables at a time: composition, color, copy, product prominence, realism, or format.
- Preserve what worked from the previous result explicitly.
- If text rendering is poor, reduce the amount of text or move text into the surrounding page instead of forcing dense copy into the image.
- If brand fit is weak, anchor the next prompt in concrete brand traits: colors, typography feel, product screenshots, website style, or visual references.

## Output

Return the generated image and a brief note with:

- The intended use case and format.
- Any assumptions made.
- Suggested next iteration only when there is a clear improvement path.
