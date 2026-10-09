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

Rock-hugging ivy bushes retain a compact inner carpet at 1.25–1.45 times the
exported leaf size. Sparse outer fans grow along the visible silhouette, at
most one per 18 cm cell, with at least 14 cm between fan roots. Each fan adds
one rotated outer blade, sized 1.65–2.4 times the export. A soft arch and short
3.5–6.5 cm extension follow its original stem with an outward lean; the tip
droops gently under gravity. This replaces duplicates at every root and the
uniform, oversized outward push that made the bushes tangled and stiff.
Neighbouring leaves share subtle warm/cool green variation. Bases remain
shaded (91–95% of their painted colour); inner tips stay muted (101–104%)
while the exposed outer layer is lighter (113–120%). Companions reuse the
painted leaf atlas. Fern clumps retain their own leaf shapes.
Ferns retain their published geometry. Companion cards share the ivy material
and mesh, so they do not introduce additional draw calls.
Host lookup traverses the unnamed groups inserted by the glTF exporter before
finding the named ivy ancestor and its rock. Scene checks verify that every
ivy primitive finds its rock through this hierarchy.

Every ivy bush receives one solid, uniform green cushion beneath its leaves.
A density union follows the seated stalks, is smoothed four times, and is
extracted as a single rounded surface. Individual ellipsoid meshes are no
longer rendered. The backing uses one averaged inner-green colour from the
painted leaf texture and vertex colours, with smooth surface shading.
Its centre is buried in the rock and the leaves sit over its shallow cap.
The support shares one material, adds one draw per bush, and adds no leaf
cards or collision. Blades rise over this cap while their stalks stay tucked in.
All bush blades use the existing fuzzy painted leaf atlas, including the
previous clump-atlas bush. Solid stem UVs remain intact. The backing is recessed
farther into the host. Visible blade rows project onto its actual surface with
6 mm clearance; stems stay concealed. A lower alpha cutoff and
alpha-to-coverage preserve the softer painted silhouette edges.

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
