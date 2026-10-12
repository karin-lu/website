# Roots

The Roots Blender extension grows static, painterly branching wood from open
line sketches. The recommended **Grow from Line Tree** workflow interprets a
branch diagram and generates its own tapered silhouette. The legacy outline
mode ports the silhouette-constrained surface generator
from `add-boulder-and-root-generation` at `15b09cc1` into the current scene workflow.
The retired editor generator, level geometry objects and generated-asset manifest
are not restored. No root mesh or material is read by gameplay.

## Authoring

### Line trees (recommended)

Select open **Poly** or **Bezier** curves in the XZ plane and use **Grow from
Line Tree**. A curve may contain multiple open splines. A mesh containing only
edges is also accepted. Make the main stroke the active object; its first point
is the thick growth base. For an edge mesh, the first stored edge's first vertex
is the base; curves give more explicit control over direction.

Draw the main gesture and attach side strokes anywhere along it. Endpoints
within 30% of Thickness snap onto another stroke, including its middle; lines
that merely cross through their middles do not connect. Keep the strokes as one
connected tree. Loops and disconnected strokes are rejected with a message;
create separate recipes for separate roots. Side strokes can be drawn in either
direction. Use extra strokes for small side roots: this mode deliberately does
not scatter decorative whiskers.

**Thickness** is the nominal main-root diameter in metres. The thick attachment
has a shallow slanted cut instead of a round cap. **Taper** changes the distribution
of thickness through the tree. **Age** gently darkens the pigment, **Bark relief**
controls shallow fibre grooves, and **Seed** varies bends, cross sections and
brushwork. **Detail** sets
the volume sampling resolution. These controls are not identical to legacy
outline settings: thickness is not a strict depth bound in line mode, and the
bark is modelled directly rather than using a normal map.

The generator relaxes bends, eases limbs out of their parent, allocates thickness
according to downstream branch length, and tapers to fine tips. Overlapping
growth volumes are voxel-unioned and smoothed into one surface. Limbs have
asymmetric cross sections with six broad wood planes and very slow twisting.
Restrained bend variation and reduced smoothing retain angular changes without
bulbous swellings. After the junctions are joined, shallow fibre grooves are
displaced along the surface normals. `painted_bark.py` supplies both colour and
relief: broad neighbouring umber strokes, long nearly straight splits and fine
dry-brush streaks. The palette uses a narrow range of warm brown values, without
cream ridges, coloured patches or swirling knot rings. The material is
matte with very low specular reflectance. Colours are stored per vertex and
exported in glTF with the actual displaced surface. There is no image or texture
dependency. Tiny tips
below the voxel size can shorten slightly; use Final for small roots.

**Show / Hide Guides** reveals editable local copies. Select additional open
Poly strokes with the generated root active and use **Copy Selected Centrelines**
to add branches. Regenerate after editing. Source objects stay independent and
unchanged; hide those source curves if their bevels are visible in a render.
The old valid mesh survives a failed regeneration. This is scenic artwork: its
relaxed shape is not guaranteed to match gameplay collision boundaries.

### Legacy exact outlines

Install with `just roots-install` (Blender 4.2+, tested with 5.2). Open the Roots
tab in the viewport sidebar. Select closed **Poly** curves or single-face meshes
in the gameplay XZ plane, then **Grow from Selected Outlines**. Select overlapping
outlines together to make one welded system; separate islands remain separate
meshes. Point/edge contacts alone do not fuse. Overlaps may leave holes.
The shared installer uses a directory junction on Windows when symbolic-link
privileges are unavailable, and safely reuses a junction to this same checkout.
Generated roots live in a local **Roots** collection even when the selected
reference belongs to the linked/hidden Guide collection.

Collision outlines linked through Game can be selected too. The extension copies
their authored points and pose to independent local guides; it never edits or
retains a live link to the reference. Hidden reference collections are supported.
All collision-reference edges are protected from decorative rootlets unless the
reference explicitly provides a `grab_edges` custom-property index list. Editing
a level later does not update its art guides automatically. Name the generated
root like the body when it should follow that body, as for other scene dressing.

Select a root and change **Thickness**, **Taper**, **Age**, **Bark relief**,
**Rootlets**, **Seed** or **Detail**, then **Regenerate**. Thickness is the total
occupied depth bound in metres; taper reduces thin limbs relative to the widest
limb. Age controls weathering, knots and restrained base contact colour. Regenerate
builds replacements before swapping the preview; invalid guides keep the last
valid surface. Settings, guides and packed maps persist in the `.blend`.

**Show / Hide Guides** reveals the local source curves for editing. Their points
must stay on the root's local XZ plane. To mark a broken end, select both points
of its edge in Edit Mode and use **Mark / Unmark Selected Broken Ends**; regenerate
after leaving Edit Mode. Break facets and end grain vary in depth/material, keeping
the authored XY projection. If points are inserted/removed, recheck the indexed
broken and protected edges (custom properties `broken_edges` and `grab_edges`).

Automatic centrelines follow curved limbs, forks and nested junctions. For an
ambiguous broad shape or a limb below the inference grid resolution, select open
Poly centreline curves with the root active, then **Copy Selected Centrelines**.
Their ends must meet (within two inference cells) into one connected network per
island, and their full segments must stay inside the outline. The copies are
editable root children; delete them to return to automatic inference. Centreline
overrides currently apply to a single connected root island: create separate
recipes for disconnected islands needing overrides.

## Geometry and materials

The following describes legacy outline recipes. Line recipes use `lines.py`
for graph construction, smoothing, taper, growth volumes and painted colour;
`line_mesh.py` joins the volumes in Blender. Both paths use the same saved recipe,
regeneration and scene-export lifecycle.

`tools/blender/roots/graph.py` thins a sampled polygon union, collapses junction
plateaus, removes short side spurs and traces a rooted branch graph. Smoothed
centrelines stay inside the silhouette. Bark coordinates follow each branch's
arc length and align recursively with its actual parent. A smooth partition of
the coordinates blends junctions, rather than compositing two grain textures.
Loops retain holes; the grain uses a spanning traversal and may need authored
centrelines/art direction at a closing loop junction.

The grid only finds the flow. `surface.py` tessellates the **exact union** including
all authored edges and intersections. A squared-depth Poisson solve samples local
branch widths, applies taper and rounds the volume through forks; fork shoulders,
asymmetric growth and base swelling act only in depth. Boundary vertices remain
welded between front/back. Final depth is bounded including geometry relief.

Draft, Preview and Final change structural sampling and atlas resolution (256,
512 and 1024 maximum pixels respectively), not three copies of one mesh called
LOD. Long outlines bound sampling by extent, although highly complex outlines can
still create many exact-intersection strips. This is static authoring, not a
runtime LOD system. NumPy is the only Python dependency (bundled with Blender).

Broad bark colour patches dominate the fine pores and fissures. Knots gather at
real junctions. Damp colour is restrained to the low base; a little moss colour
appears on sheltered upward faces there. This is a local height heuristic, not
a query against scene terrain: for roots above ground, age/contact colouring may
need art direction. Rootlets grow along subordinate curved branches with seeded
size and spacing. Their complete swept tubes must stay at least 9 cm clear of
protected playable edges; a fully protected outline can suppress all rootlets.

Normals use finite differences of the continuous world-space relief field and
are transformed into Blender's MikkTSpace loop basis. Neighboring atlas pixels
are never treated as neighboring surface positions. The maps use OpenGL tangent
normals and Non-Color data; colour is sRGB, roughness is Non-Color. Charts have
gutters with dilated pixels. `scene_export.py` exports tangents for scenes that
contain Roots, keeping the same shading basis in glTF. The roots rebuild **before**
ivy/moss/foliage so those tools can use the fresh surface. Broken recipes are
reported and omitted with their descendants, as for other growth tools.
On Windows checkouts with Git directory links stored as text files, the exporter
mounts the existing shared stamp-brush package explicitly for ivy/moss/foliage;
real symlinks and installed extensions are unchanged.

## Verification and preview

The line workflow has a separate study showing the input diagram above its
generated root. From `rope/`:

```sh
blender -b --factory-startup --python-exit-code 1 --python tools/blender/roots/preview_lines.py -- assets-src/studies/roots/line-study
```

It renders `line-roots.png`, `line-roots-oblique.png` and `bark-closeup.png`, saves an editable `line-roots.blend`, exports
`line-roots.glb`, and checks failed-edit preservation and save/reopen/rebuild.
`test_lines.py` covers nested forks, loose endpoint attachment, branch direction,
crossing semantics, invalid graphs, closed growth volumes, deterministic geometry
and finite colour. Painted bark also checks circular seam continuity, bounded
relief, restrained pigment contrast and shallow thick-end geometry. The full test discovery below runs both
line and legacy tests. The Blender study checks closed, positive-volume surfaces
with one connected component per root.

From `rope/`:

```sh
python -m unittest discover -s tools/blender/roots -t tools/blender -v
blender -b --factory-startup --python-exit-code 1 --python tools/blender/roots/preview.py -- assets-src/studies/roots
blender -b assets-src/studies/roots/roots-fixture.blend --factory-startup --python-exit-code 1 --python tools/blender/scene_export.py -- assets-src/studies/roots/roots.glb assets-src/studies/roots/export.json
```

`preview.py` checks independent sources, invalid-rebuild preservation and saved
recipe persistence, and renders front/oblique fixtures with captured console
logs. Optional `--baseline DIR` compares old `sideview_surface.py` and
`stylised_bark.py` extracted verbatim from `15b09cc1`, under identical lighting.
Tests cover exact contours, closed positive-volume meshes, depth bounds, nested
forks, curved flow, taper, holes/islands, rotated/mirrored normal bases, meaningful
detail levels, deterministic maps and rootlet clearance. These checks do not
replace inspecting the renders or a manual Blender authoring session.

Study binaries belong in ignored `assets-src/studies/roots/`; no production
level, scene pin or published asset is changed by making this preview. Export
real scenes with `just scene <level>` and publish using the existing scene workflow.
