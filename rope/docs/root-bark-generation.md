# Painterly root bark

Created with the built-in OpenAI image-generation tool on 2026-10-16 using the
user's bark reference. Original preserved in `assets-src/painted-root/painted-root-base.png`;
the runtime map is `public/textures/painted-root-base.webp` (1024 square, WebP quality 92).
Binary files use the repository's release asset store; publish the pinned map
with `bun run assets:publish-stored` before pushing this change.
The map is hosted in the `assets` release of `karin-lu/website`, recorded by
`storeRepo` in its manifest because this contributor cannot publish upstream.
The normal asset fetch and publishing commands respect this per-map location;
an explicit `ASSET_REPO` environment override still selects a complete mirror.

Prompt:

> Create a seamless tileable flat 2D hand-painted tree-root bark ALBEDO TEXTURE for a 3D game, using the attached reference strictly as the texture/style reference. Fill the entire square image edge-to-edge with bark. No cylinder, no trunk silhouette, no border, no background, no perspective, no cast shadows, no text. Orthographic unwrapped surface. Long irregular longitudinal bark plates running vertically, wandering and splitting naturally, narrow deep dark umber crevices, broad warm ochre/clay/tan raised faces, selectively painted pale warm edge highlights, visibly layered gouache brush strokes and fine dry-brush hatching exactly like the reference. Strong readable separation of broad ridges and fissures even at game scale. Muted earthy colors, no orange saturation. About 12-16 substantial elongated bark plates across the full image width, with irregular length and width. The texture must wrap seamlessly left/right and top/bottom. Surface color painted into the texture rather than photographic lighting. Output a high-quality square game texture.

The renderer derives a tangent normal map once from the painted luminance, so
raised edges and relief follow the same strokes. The procedural maps remain a
headless-safe fallback while loading or if the stored image is unavailable.
