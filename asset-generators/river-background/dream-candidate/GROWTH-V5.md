# V5 growth patches

`growth_patches.py` samples each saved rock's visible contour and checks for
usable upward shelves. Stable formation seeds, moisture and ledge width decide
the number of sites. Sites are spaced apart to retain bare stone.

The layered builder and hanging-moss pass use the same sites. Surface moss forms
irregular local beds with constant texture scale; sprigs grow at their lips.
Only some beds spill over. Ceiling trails are rooted in the actual lower rock
contour instead of the old fixed screen coordinates. Hanging clusters alternate
between tufts, sparse strands and cascades, retaining complete atlas silhouettes
and uniform scaling. Far layers use fewer sites and strands.

Each formation stores `river_growth_sites` as JSON for inspection. Refit after
editing geometry; existing stone and lighting are preserved. `refit_growth_v5.py`
runs the refit twice, checks deterministic meshes and transforms, validates UVs
and attachments, and saves back to the loaded v5 file. This supports both the
runtime master and the separately edited layer-editor master.

Run Blender in background with the desired saved v5 file and
`--python-exit-code 1 --python refit_growth_v5.py` (use full script path).
Then export the runtime master using `pipeline/export_background.py` to
`rope/public/backgrounds/river-dream-v5` with width 2048 and 12 samples.
For runtime review, run `scripts/verify-dream-route.ts routes` from `rope`
with `DREAM_VARIANT=river-dream-v5` and `PREVIEW_URL` pointing to the local server.

Historical backup scenes are excluded from this clean distribution.
This is static background planting; no runtime wind shader was added.
