# V5 hanging moss

The master and artist layer editor use the reference's seven isolated fine leafy strand silhouettes, with subdued highlights and lifted green shadows. The packed texture is `textures/hanging-moss-soft-strands-v5.png`.

Each of the 15 rock patches contains independent main strands, three intermediate strands, three small complete short strands and a front strand where appropriate. The opening artist scene has 161 cards / 2898 triangles. Broad compact tufts and cropped crown strips are removed. Every sprite includes its complete crown and tapered tip, with transparent borders below the material cutoff. Original short main strands retain their scale. The longest main strands use 90% of the reference scale in both axes, shortening them 10% while keeping leaf proportions.

The upper section curves over the rock lip at a visible angle, with a shallow forward bow below. Crowns sit at the ledge height and depth clearance includes their entire upper arc, preventing the rock from hiding their rounded tops. Depth clearance is sampled from the rock without stretching the texture. Measured UV edge scales remain within 0.4% of uniform. Each card is attached to its formation parent. The layer editor's Refit plants control regenerates the same moss. Existing rock meshes and other plants are preserved.

The artist composition is preserved in `output-v5/river_dream_layer_editor.blend`. The delivered runtime package is the latest export of `output-v5/river_dream.blend`. Preview: <http://127.0.0.1:5190/?level=BALL&render=3d&background=river-dream-v5>.

Historical backups and intermediate reports are excluded from this clean distribution. Use **Refit plants** in the layer editor to update moss and vegetation after editing the rock geometry.
