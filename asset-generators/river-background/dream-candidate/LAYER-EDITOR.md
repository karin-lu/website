# V5 background layer editor

Run **open_editor.py** as described in the [pipeline README](../README.md). It opens the separate artist file
`output-v5/river_dream_layer_editor.blend` and enables the controls automatically.
In the 3D View, press **N** and select the **River** tab.

The launcher enables the controls and updates paths for the current checkout.
No add-on installation is required. Use the launcher rather than the old
embedded START HERE text, which contains paths from the original machine.

## Edit a layer

1. Choose **Edit Near** or **Edit Far** in **2D Background Layers**.
2. All formation outlines in that layer enter point editing together. The other
   layer is hidden; scenery previews are locked. The gameplay guide remains.
3. Click or box-select points. **G** moves them; native 2D curves keep the points
   flat automatically. Scroll to zoom; **Shift+middle mouse** pans. **Frame whole
   layer** returns to the frontal view. **Tab** switches between selecting
   outline objects and their points.
4. Use the **Polygons** controls in the Layers panel:
   - **Copy** copies outlines containing selected points, or selected outline
     objects in Object Mode. **Paste** creates independent copies in the current
     layer, slightly offset. The clipboard works between Near and Far.
   - **New polygon** starts a four-point outline at the view center. Move its
     points, then rebuild to generate a rock.
   - **Delete polygon** removes selected polygons and their previews. **Discard
     unapplied edits** restores them; Apply, Preview, switching layers or Rebuild
     commits removal and retains the formations in `81_PREVIOUS_MESHES`.
   - **Add point** inserts midpoints between selected neighboring points. With
     one point selected, it inserts on the next edge around the polygon.
   - **Remove points** removes selected points, keeping at least three and
     rejecting crossing or degenerate outlines.
5. **Rebuild this layer** applies the outlines and regenerates only changed
   rocks. Generation runs separately; **Esc** discards its results. Previous
   rock meshes are retained in `81_PREVIOUS_MESHES`.
6. Repeat for the other layer. Then **Refit vegetation** repositions the moss
   and plants onto the edited geometry in the current scene.
7. **Composition preview**, **Ctrl+S**, then **Export saved background** in the
   River Background panel below. Export targets the existing `river-dream-v5`
   package. Check the result at
   <http://127.0.0.1:5190/?level=BALL&render=3d&background=river-dream-v5> when the
   game server is running.

**Apply outline edits** saves the handle shapes into source outlines without
rebuilding yet. **Discard unapplied edits** discards changes since the last
Apply and restores the composition view. Preview and switching layers also
apply valid pending handle edits; use Rebuild Near/Far afterward.

The original `river_dream.blend` is preserved. Save artwork to the dedicated
artist file. Re-running the procedural scene builder replaces the original
master, so export the artist file for manual work.

## Move layers and rocks in depth

The **Depth** box has **Whole layer** and **Selected rocks** Forward/Back buttons.
**Step** is the distance per click. Forward moves toward the camera; Back moves
away. Near and Far remain separate layers at every depth.

While editing a layer, select any points on the rocks you want to move, then use
**Selected rocks**. In Object Mode, select the outline objects instead. Outside
the flat editor, select rock meshes or their placement objects in the 3D view.

**Keep screen size** preserves the reference camera's framing by scaling around
the camera while changing depth and parallax. For a whole layer, the average
placement depth changes by Step and the entire layer receives one shared scale.
Turn it off for a straight depth translation: distant objects appear smaller.
Attached plants and moss move with their formation; whole-layer moves also move
standalone layer scenery. No rock rebuild is needed.

Depth edits are immediate. **Ctrl+Z** undoes them; **Ctrl+S** saves them.
**Discard unapplied edits** only discards polygon shape edits, not depth moves.
Moves preserve pending shape edits, and moving scenery behind the camera is
rejected before anything changes.

## How the flat editing view works

Near and far outlines are perspective-projected onto the gameplay plane using
the background camera's reference origin and distance. All handles lie on one
X/Z plane. The inverse projection intersects each edited camera ray with its
formation's original local outline plane. This retains depth, tilted planes,
mirroring, scaling and parent placement. It matches the reference camera's
projected outline scale; the game still supplies perspective, lighting and
parallax as the camera moves.

Locked, projected copies of the rock surfaces sit behind the outlines. Those
previews show the last built geometry; they update when the layer is reopened
after rebuilding. Source outlines and projected previews are authoring helpers,
not exported assets. The final faceted mesh may differ slightly from the recipe
boundary because of the procedural fracture and weathering construction.

Invalid, intersecting and degenerate polygons are rejected before
any source outline is changed. Manual mesh edits are protected by the existing
River rebuild validation. Batch results are validated before mesh replacement.
Rebuild failure leaves the existing meshes in place and retains the applied
source outlines for correction and retry.

The editing view stays frontal, and the handles use native Blender 2D curves
with depth and rotation locked. Older 3D handles are automatically flattened
when the controls load, retaining all horizontal and vertical shape edits.
Accidental depth coordinates never become part of a rock's outline recipe.

## Verification

`pipeline/verification/layer-editor/checks.json` records real Blender projection,
isolation and outline-edit checks. `rebuild-checks.json` records a real generated
replacement, backup and vegetation refit with the original saved file unchanged.
The test edit is confined to verification files; it is not in the artist file
or runtime package.
