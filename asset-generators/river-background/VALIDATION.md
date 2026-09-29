# V5 integration verification

Verified on Windows with Bun 1.4.2 and Blender 5.2 against Epictris `main`
`f522917`, on 2026-09-29. Gameplay levels, engine and simulation files are
unchanged from that base.

Passed:

- TypeScript typecheck and Vite production build.
- Background package tests: camera/parallax, atlas coverage, serialization,
  preloads, loading/failure/disposal and readiness-gated scene replacement.
- Windows level invalidation tests.
- Decoded GLB hashes, bounds, colors and coverage of 593 current-level route
  samples at 16:9, 21:9, 4:3 and portrait ratios.
- Eight route captures, four settled time samples and the normal playable
  page. All report two ready layers, covered atlas, scene replacement and
  clean captured consoles. The time-sample montage was generated separately.
- Blender source validation, near/far layer editing, polygon operations and
  depth tools. Packed textures are checked by their bytes, including Blender
  image duplicates created during refits.
- Real procedural rock generation, exact mesh validation, replacement with
  backup, and vegetation refit. Placement, other rocks and the saved input
  scene are preserved.

`bun run test` completed with **59/65 steps passing**. Its six failing suites
were rerun against an untouched archive of `f522917` and reproduced:

| Suite | Failing checks |
| --- | --- |
| contacts | hook-sparks; chain-sweep |
| movers | shipped mover contact-speed bar |
| vines | ring-square |
| sleep | arena |
| assets | local manifest file availability; generated credits |
| playtest | trash expiration; mid-session restart |

The asset-availability result depends on locally fetched files; the initial
full suite ran before that fetch completed. The other failures were retained
for comparison rather than changing unrelated game behavior in this branch.
The full suite is not claimed green. Captures are renderer checks, not a full
playthrough or hardware performance measurements.
