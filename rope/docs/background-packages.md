# Layered scenery packages

A level may set `backgroundPackage` to a manifest URL such as
`/backgrounds/river/package.json`. The reference survives normalisation, pixel
scaling, editor saves and undo. Packages contain scenery only; they never add,
remove or alter physics, collision shapes or grapple targets.

The [v5 pipeline](../../asset-generators/river-background/README.md) is available
at `?level=BALL&render=3d&background=river-dream-v5`. The default level is unchanged.
Its manifest uses `replaceSceneScenery: true` and no hidden body indices. After
successful loading, only the current Blender scene's unbound scenery is hidden;
body-bound dressing remains visible. Loading/failure/removal restores the scene.
This avoids the obsolete body-205 reference used by the pre-scene prototype.

```json
{
  "version": 1,
  "colorSpace": "srgb-display",
  "camera": {
    "fovYDeg": 19.455157102803206,
    "distance": 10.2375,
    "origin": [10.85, -8],
    "zoomResponse": 0
  },
  "layers": [
    { "id": "near", "file": "near.glb" },
    { "id": "far", "file": "far.glb" }
  ],
  "backdrop": {
    "file": "backdrop.png",
    "worldWidth": 10,
    "worldHeight": 7,
    "origin": [10.85, -8],
    "pan": 0.02
  },
  "hideBodyIds": [205]
}
```

All coordinates are Three world coordinates in metres: X right, Y up, negative
Z behind gameplay. Camera `origin` records the export's reference framing. Layer
transforms are already in world space; the runtime does not relocate, rescale or
apply an additional per-object parallax factor. The package camera follows the
gameplay camera's X/Y immediately and stays head-on. Camera shake/orbit has no
separate background implementation.

`zoomResponse` defaults to zero, preserving the reference distance and lens when
gameplay zoom changes. A value of one follows the camera distance required to
frame the gameplay plane with the package lens; intermediate values interpolate
the distance ratio geometrically. A depth B behind gameplay has natural pan
response D/(D+B), with D the current package camera distance.

The plate is drawn through a separate orthographic full-frame pass, cropping its
world-sized atlas to the reference camera window. Its UV centre is offset by
`(cameraXY - backdrop.origin) * pan / worldSize`. Thus `pan: 0.02` moves the atlas
window by 2% of world camera travel. Texture edges use clamp-to-edge; exported
coverage should keep the entire sampled window inside the atlas.
`Scene3D.backgroundStatus()` reports whether that window is covered, along with
loading phase, layer count, the current background camera and any failure.
`shot.html?...&backgroundDiagnostics=1` prints this status and render counters
into the captured console. All screenshot paths wait for package settlement,
including lazy shader probes that skip prewarm. Editor free views still use the head-on package
camera centred on their target; package composition is authored for gameplay.
For actual gameplay camera regions/zoom, add `gameCamera=1` to a shot request
without `at`/`zoom` overrides. This samples the same render-side camera controller
at 60 Hz during replay; the diagnostic log includes its position and zoom.
`viewPose=X,Y,Z,YAW,PITCH,HALFHEIGHT,FOV` checks the editor free-view path, with
the target in Three coordinates and angles in degrees. Package camera position
follows that target's X/Y while its distance and lens stay independently fixed.

Verify the normal playable page as well as `shot.html`: a shot with an embedded
level reads that bundle, while normal play reads the registry's imported level.
The playable page exposes read-only `window.__background` diagnostics and prints
them after warm-up when `backgroundDiagnostics=1` is present. Its status should
be `ready` with two layers for the river package. The development server
invalidates level imports after disk/API writes using Vite's normalized file
paths; filesystem paths on Windows otherwise silently miss the module cache.

GLBs are self-contained, may use Meshopt compression, and should export prelit
unlit materials with `COLOR_0` as linear RGB. The runtime preserves those
materials and vertex colors, disables their tone mapping, and creates no package
lights. The display-referred plate is decoded as sRGB and also bypasses gameplay
ACES. `colorSpace` is informational in version 1. Geometry and plate should be
exported through the same display transform.

`hideBodyIds` are **zero-based indices in the authored `bodies` array**, because
level bodies have no persistent IDs. A listed body's visual root is hidden only
after every package file loads successfully. Its physics remains intact. Body
reordering requires updating the manifest. While loading, after failure, or when
the package reference is removed, the original backdrop continues to render.

The runtime draws plate, near/far geometry, resets depth, then draws gameplay;
it restores scene background, renderer clearing and shadow state afterwards.
Package resources belong to the renderer instance and are disposed on replacement
or teardown, including stale async arrivals. Keeping the same URL across editor
revisions reuses the loaded package.

An optional `bytes` field on each layer/backdrop supports download accounting.
The Vite preload builder reads local manifests under `public/`, includes their
assets at first paint, and fills missing file sizes from disk. Remote packages
load normally at runtime. Scene warm-up waits for the package, compiles its
materials and uploads its textures/culled geometry before play starts.

Run `bun run scripts/test-background-package.ts` for camera/parallax, atlas
mapping, serialization, preloads, load failure, renderer state and disposal checks.

With the development server on port 5190, run
`bun run scripts/verify-background-render.ts v5 auto follow 120` to capture
an actual gameplay camera frame. `baseline` removes the package for comparison;
numeric zoom and `X,Y` camera arguments pin reference/coverage frames. Captures
and console diagnostics are written under `artifacts/background-runtime/`.
The optional trailing arguments are an editor view pose (or an empty string)
and the recorded held-input bitmask. Set `CHROMIUM` if Chrome is installed
outside the driver's Windows default. These headless SwiftShader captures
verify appearance and draw counters; their duration does not measure GPU speed.
