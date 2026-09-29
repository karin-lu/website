// River package QA using the existing gated screenshot runner and a server on
// port 5190. Override CHROMIUM when Chrome is installed elsewhere.
// Usage: bun run scripts/verify-background-render.ts package auto follow 120
// Optional trailing arguments: editor view pose (or ""), held-input bitmask.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import assert from "node:assert/strict";
import { grab } from "../src/tools/shotRunner";

const mode = process.argv[2] ?? "v5";
const zoom = process.argv[3] ?? "3.076923076923077";
const at = process.argv[4] ?? "10.85,8";
const frame = Number(process.argv[5] ?? 0);
const pose = process.argv[6];
const held = Number(process.argv[7] ?? 0);
const folder = resolve("artifacts/background-runtime");
mkdirSync(folder, { recursive: true });
const data = JSON.parse(readFileSync("levels/ball.json", "utf8"));
if (mode === "baseline") delete data.backgroundPackage;
else data.backgroundPackage = "/backgrounds/river-dream-v5/package.json";
const suffix = `${mode}-${zoom.replace(".", "_")}-${at.replaceAll(",", "_")}-f${frame}${pose ? "-freeview" : ""}${held ? `-h${held}` : ""}`;
const bundle = `${suffix}.json`;
writeFileSync(resolve(folder, bundle), JSON.stringify({
  level: "BALL", controller: "ball", data,
  frames: Array.from({ length: frame }, () => ({ h: held, mx: data.player.x * 0.01, my: data.player.y * 0.01 })),
}));
const query = new URLSearchParams({
  bundle: `/artifacts/background-runtime/${bundle}`, frame: String(frame),
  render: "3d", backgroundDiagnostics: "1",
});
if (zoom !== "auto") query.set("zoom", zoom);
if (at !== "follow") query.set("at", at);
else query.set("gameCamera", "1");
if (pose) query.set("viewPose", pose);
const out = resolve(folder, `${suffix}.png`);
const chromium = process.env.CHROMIUM ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const result = await grab(chromium, {
  url: `http://127.0.0.1:5190/shot.html?${query}`, out, gpu: true,
  width: 1920, height: 1080, timeoutMs: 45000,
});
writeFileSync(resolve(folder, `${suffix}.console.json`), JSON.stringify(result, null, 2));
for (const entry of result.log) console.log(`[page] ${entry.level}: ${entry.text}`);
console.log(JSON.stringify({ out, elapsedMs: result.elapsedMs, rasterizer: "headless/SwiftShader" }));
if (result.log.some((entry) => entry.level === "error")) throw new Error("page console contains errors");
const diagnostic = result.log.find((entry) => entry.text.startsWith("background "));
assert.ok(diagnostic, "background diagnostics were not captured");
const status = JSON.parse(diagnostic.text.slice("background ".length));
if (mode !== "baseline") {
  assert.equal(status.phase, "ready", "the package must be ready, not a fallback frame");
  const manifestPath = "public/backgrounds/river-dream-v5/package.json";
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  assert.equal(status.url, data.backgroundPackage);
  assert.equal(status.layers, 2);
  assert.deepEqual(status.hiddenBodies, []);
  assert.equal(status.replaceSceneScenery, true);
  if ((manifest.camera.zoomResponse ?? 0) === 0) assert.equal(status.camera.position[2], manifest.camera.distance);
  assert.equal(status.camera.position[0], status.viewPose?.target.x ?? status.gameplayCamera.position[0]);
  assert.equal(status.camera.position[1], status.viewPose?.target.y ?? -status.gameplayCamera.position[1]);
}
