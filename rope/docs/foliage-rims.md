# Rooted bushes and moss rims

The foliage branch dresses the published Blender scene when it loads in the
level editor and game. Collisions and level placement stay as authored.

Each rock-hugging bush has one smooth, solid green backing. The original
Blender leaf stalks define its shape. A smoothed density union is extracted
as a single surface; the support uses one averaged inner-green colour and
is recessed into its host rock. It has no collision and adds one draw per bush.

The rendered bush leaves grow on this backing instead of their original
rock-root carpet. The front-facing surface is sampled from the side-scroller
camera direction (+z), keeping its nearest visible depth at every 3.5 cm sample.
Overlapping fuzzy painted blades cover that surface, including the strip
just below the rock. Each stalk attaches within 6 mm of the backing. Blades
curve toward the camera with subtly varied angles and gentle colour changes.
All bushes use the original painted fuzzy leaf atlas, including the previous
clump-atlas bush. Solid backing and leafy cover remain separate shared-material
meshes. The fern clumps retain their own geometry and leaf shapes.

Host lookup traverses unnamed groups inserted by glTF before finding the
named ivy ancestor and its rock. Scene checks verify every bush finds its host,
receives a backing and front cover, and has seated roots and clear blades.

Opaque moss mounds receive a fringe from the user's supplied tuft atlas.
Placement welds split UV-chart vertices and samples open rims and front
silhouettes. Edge cards are 6–12 cm tall, with irregular lean and overlapping
placement every 4.5 cm. Lower rims also receive moss. Their lower rows conform
to the cushion: the bottom is buried and visible roots sit within 1 mm of it.
Tuft colours sample the painted moss texture and its glTF UV transform. Roots
match the local colour and tips lighten by 6%, with matching surface normals.
The budget is 1400 cards per mound, with one additional draw per mound.

The moss tuft atlas is the T_MossTuft_Atlas.png supplied in files.zip on
2026-10-09. Its accompanying render, breakdown, Blender file and script
informed the cushion-and-fringe treatment.

Checks:

- bun run scripts/test-ivy-geometry.ts
- bun run scripts/test-moss-fringe.ts
- bun run scripts/test-foliage-scene.mts (requires fetched scene assets)
- bun run typecheck
- bun run build
