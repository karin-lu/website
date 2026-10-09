# Moss foliage cards in Blender

Install the **Moss Foliage Cards** extension ZIP from Blender Preferences → Get Extensions → Install from Disk. The local installation is already enabled on this machine. Restart Blender if it was open during installation.

Open `assets-src/scenes/river.blend`. Its **Moss Cards** collection contains individual editable tufts. Open the 3D View sidebar with **N**, then select **Foliage Cards**.

- Select a moss mound and use **Create Cards on Moss Rims** to populate it. Existing cards are kept; generation does not overwrite manual edits.
- **Place Card on Moss** places the chosen tuft where you click the selected moss. Hold Shift to keep placing; Esc finishes.
- Use **G**, **R**, **S** to move, rotate and scale a selected card. Enable Face snapping for surface moves; **Attach Roots to Moss** reseats moved card roots.
- **Tab** opens Edit Mode. Move the card's vertices or edges to reshape it. **O** enables proportional editing. All four atlas shapes use eight vertices across four rows.
- **Apply Tuft Shape** changes only UVs. **Curve Selected Cards** adds a gentle bend above the root, preserving manual vertex edits. These operations apply to selected cards in Object Mode.
- Duplicate with Shift+D; delete with X; hide from export using the Outliner's render visibility. Save the `.blend` to keep changes. Blender's undo handles all add-on operators.

Export with the existing scene recipe: `bun run scene:export ball --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"`. Publish scene assets before pushing a changed scene pin, as described in `docs/blender-scenes.md`.

The exporter keeps artist-owned card geometry, applies modifiers to copies, and combines those copies into one mesh per moss patch. It never saves the packed copies over the editable source. Hidden/excluded cards remain omitted. Authored moss materials end in `.moss.authored`, so the game does not add a second layer of procedural tufts, even if you hide every card.

The supplied atlas is packed with a fading root, subtle painted detail, and per-card colours sampled from the moss print. Cards follow their moss parent's transform. If the moss itself is substantially reshaped, reseat cards explicitly; export never discards your adjustments to refit them automatically.

The source before initial preparation is preserved at `.cache/moss-cards/river-before-cards.blend`.

Build the distributable ZIP with `python tools/blender/package_moss_cards.py`. Test in Blender with `--background --factory-startup --python-exit-code 1 --python tools/blender/moss_cards/test_cards.py`.
