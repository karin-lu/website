# Blender background pipeline v5

Connected v5 (Sunken Grotto) on Epictris `main` at `f522917`. The branch
preserves the current game, levels, physics and existing Blender scene tools.
V5 is selected explicitly with `?level=BALL&render=3d&background=river-dream-v5`.
When the package is ready, it replaces unbound scene scenery; body-bound scene
dressing and gameplay visuals remain. Removing the parameter restores main's
scene. Failed package loads also retain main's scenery.

## Fresh checkout

Install Bun, Python 3.11+ and Blender 5.2 (the version used for these sources).
From `rope`, run:

```sh
bun install --frozen-lockfile
bun run assets:fetch
bun run dev -- --host 127.0.0.1 --port 5190
```

Open <http://127.0.0.1:5190/?level=BALL&render=3d&background=river-dream-v5>.
The existing `assets:fetch` also downloads the three pinned v5 runtime files.
`bun run assets:fetch-v5` fetches just those files. Their total size is
6,955,374 bytes, with 24,240 decoded triangles across the two layers.

## Blender editing

From the repository root:

```sh
python -m venv rope/.venv
# Windows:
rope/.venv/Scripts/python -m pip install -r rope/tools/blender/requirements.txt
rope/.venv/Scripts/python asset-generators/river-background/fetch_authoring.py
rope/.venv/Scripts/python asset-generators/river-background/open_editor.py
```

On macOS/Linux use `rope/.venv/bin/python`. Set `BLENDER` to the executable or
pass `--blender` to the launcher. Set `RIVER_PYTHON` to override the generator
Python; the launcher defaults to the interpreter used to launch it.

The authoring archive includes the current runtime master, the separate artist
master, the packed bootstrap scene, build metadata and three source textures.
It excludes historical scene backups, rock caches, logs and screenshots.
The fetch refuses to overwrite any differing local artwork.

Use the launcher after moving/cloning the checkout: it binds scene paths and
Python to this checkout before registering the River sidebar. Old embedded
"START HERE" texts retain the original machine's paths; use the launcher.
The packed gameplay guides describe the original v5 composition and are static
references; validate against the current game in the browser.

See [layer editing](dream-candidate/LAYER-EDITOR.md) for polygon, depth,
rebuild and vegetation controls. Edit the artist file, save, then choose
**Export saved background**. This updates the local v5 package.

For a headless export, from the repository root in PowerShell:

```powershell
$blender = 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
& $blender --background asset-generators/river-background/dream-candidate/output-v5/river_dream_layer_editor.blend --python-exit-code 1 --python asset-generators/river-background/pipeline/export_background.py -- --output rope/public/backgrounds/river-dream-v5 --width 2048 --samples 12 --no-preview
```

The delivered runtime package is the last export of `output-v5/river_dream.blend`.
The artist file is also preserved, so exporting it can change that composition.
Neither export modifies gameplay collision or overwrites the input scene.

## Procedural rebuild

`dream-candidate/mass-recipes-v5.json` defines the outlines and generator
parameters. `connected_grotto.py` defines their placement. `growth_patches.py`,
`hanging_moss.py` and `build_layered.py` implement the shared planting stages.
The boulder generator is reused directly from `rope/tools/blender/boulders`.

Run `build_rocks.py` with the generator Python to populate `cache-v5` (use
`--blender` if needed). Then open the downloaded `output/river_dream.blend`
bootstrap in background Blender and run `build_connected.py`. This intentionally
replaces `output-v5/river_dream.blend`; preserve manual edits first. It does not
replace the separate artist master. Use **Refit plants** inside the layer editor
to update vegetation without rebuilding rock geometry.

## Verification

See [the recorded results and inherited failures](VALIDATION.md).

From `rope`:

```sh
bun run typecheck
bun run scripts/test-background-package.ts
bun run scripts/test-level-invalidation.ts
node ../asset-generators/river-background/pipeline/verify_package.mjs public/backgrounds/river-dream-v5
bun run build
# With the development server running, and authoring assets downloaded:
bun run scripts/verify-dream-route.ts all
```

Set `PREVIEW_URL` or `CHROMIUM` when the server or browser uses another location.
The route checks capture console diagnostics with each image. They check camera
coverage and settled time samples, not a full playthrough or hardware FPS.
Blender scripts `pipeline/verify_layer_editor.py`, `verify_depth_tools.py` and
`verify_polygon_tools.py` exercise the actual editor; run each with the saved v5
master, `--background` and `--python-exit-code 1`. They do not save over it.

## Storage and future updates

Source code and the package manifest are in Git. Binary assets follow the
repository's release-store convention. SHA-256 and byte counts are pinned in
`rope/src/render3d/backgroundAssets.json`; downloads fail on mismatches.
The archive and runtime files live in the fork's `blender-pipeline-v5-assets`
release. A subsequent accepted export needs new release assets and updated pins
alongside `rope/public/backgrounds/river-dream-v5/package.json`. Do not replace
bytes behind existing pins. Generated local output remains ignored.
