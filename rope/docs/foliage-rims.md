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
lighten by 12%; the reference atlas contributes its cutout silhouette and slight
texture detail rather than a dark grayscale band. Normals are interpolated from
the mound so the join also shares its lighting.

Rock-hugging ivy bushes have 32% larger blades and a fuller arch. About 45%
of their existing cards receive a smaller, rotated companion at the same
seated stalk. Companions reuse the original painted leaf UVs and colours,
with slightly shaded bases. The greenery grows in overlapping layers around
the rock rather than adding broad leaves to the separate fern clumps.
Ferns retain their published geometry. Companion cards share the ivy material
and mesh, so they do not introduce additional draw calls.

Moss edge cards are 4.5–10 cm tall, with irregular spacing and lean. Both ends
of each card's lower two rows conform to the moss cushion and sink into it;
an alpha ramp removes the exposed rectangular foot. This avoids floating
corners and the continuous serrated strip along a ledge.

Cards ride their original host and have no collision. The budget is at most
600 cards per mound, distributed around its rim, with one draw call per mound.

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
