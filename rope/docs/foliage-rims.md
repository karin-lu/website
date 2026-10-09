# Rooted leaves and moss rims

The `foliage` branch dresses the published Blender scene when it loads, in both
the level editor and the game. It does not change collisions or level placement.

Ivy cards retain their atlas UVs and painted colours. Their visible stalk point
is seated 2 mm above the nearest opaque host surface, with a curved blade and
rock clearance. Previously the translation was capped at 8 cm, which left raised
carpet layers floating above their host.

Opaque `.moss` materials receive a short fringe of cutout tuft cards. Placement
welds the mound's split UV-chart vertices, then samples its open rim and the
silhouette facing the side-scroller camera (+z). Bases overlap the mound; size,
spacing, atlas cell and tint vary deterministically. Soft surface-biased normals,
dark bases and a shared material help the fringe read as part of the cushion.
Tuft colours are sampled from each mound's painted texture at their attachment,
including its glTF UV transform. Roots match the local moss and tips gradually
lighten by 6%; the reference atlas contributes its cutout silhouette and slight
texture detail rather than a dark grayscale band. Normals are interpolated from
the mound so the join also shares its lighting.

Rock-hugging ivy bushes have blades at least 2–2.4 times their exported size,
with a size floor for tiny cards (growth is capped at four times). A rounded
6.5 cm arch and 3.5 cm tip lift expand the silhouette beyond the flat carpet.
Every card
in an ivy carpet receives one or two rotated companions at the same
seated stalk. Companions reuse the original painted leaf UVs and colours,
with slightly shaded bases. The greenery grows in overlapping layers around
the rock rather than adding broad leaves to the separate fern clumps.
Ferns retain their published geometry. Companion cards share the ivy material
and mesh, so they do not introduce additional draw calls.
Host lookup traverses the unnamed groups inserted by the glTF exporter before
finding the named ivy ancestor and its rock. Scene checks verify that every
ivy primitive finds its rock through this hierarchy.

Moss edge cards are 6–12 cm tall, with irregular lean and overlapping placement
every 4.5 cm. Downward-facing rims also receive moss, filling the lower outline.
Both ends of each card's lower two rows conform to the moss cushion: the bottom
row is buried and the visible root sits within 1 mm of the surface. The alpha
ramp finishes at this root row, preventing a transparent gap under the tuft.

Cards ride their original host and have no collision. The budget is at most
1400 cards per mound, distributed around its rim, with one draw call per mound.

`src/render3d/assets/moss-tuft-atlas.png` is the `T_MossTuft_Atlas.png` supplied by
the user in `files.zip` on 2026-10-09. The accompanying moss render, breakdown,
Blender file and script informed the cushion-and-fringe treatment. The existing
painted moss and rocks remain the base appearance.

Checks:

- `bun run scripts/test-ivy-geometry.ts`
- `bun run scripts/test-moss-fringe.ts`
- `bun run scripts/test-foliage-scene.mts` (requires `bun run assets:fetch`)
- `bun run typecheck`
- `bun run build`
