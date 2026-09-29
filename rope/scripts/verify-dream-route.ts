// Real-renderer QA for the isolated Sunken Grotto candidate. Run from rope:
// bun run scripts/verify-dream-route.ts [all|routes|motion|playable]
// DREAM_ROUTES=1,4,8 selects coverage points; PREVIEW_URL overrides the local server.
import assert from "node:assert/strict";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import sharp from "sharp";
import { grab } from "../src/tools/shotRunner";

const group = process.argv[2] ?? "all";
assert.ok(["all", "routes", "motion", "playable"].includes(group));
const variant = "river-dream-v5";
const revisionSuffix = variant.slice("river-dream".length);
const artifactFolder = `sunken-grotto${revisionSuffix}`;
const sceneOutput = `output${revisionSuffix}`;
const folder = resolve(`artifacts/background-runtime/${artifactFolder}`);
mkdirSync(folder, { recursive: true });
const reportPath = resolve(`../asset-generators/river-background/dream-candidate/${sceneOutput}/build_report.json`);
const report = JSON.parse(readFileSync(reportPath, "utf8"));
const manifestBytes = readFileSync(`public/backgrounds/${variant}/package.json`);
const manifest = JSON.parse(manifestBytes.toString("utf8"));
assert.equal(manifest.layers.length, 2);
assert.deepEqual(manifest.hideBodyIds, []);
assert.equal(manifest.replaceSceneScenery, true);
const level = JSON.parse(readFileSync("levels/ball.json", "utf8"));
const chromium = process.env.CHROMIUM ?? "C:/Program Files/Google/Chrome/Application/chrome.exe";
const baseUrl = process.env.PREVIEW_URL ?? "http://127.0.0.1:5190";
const packageUrl = `/backgrounds/${variant}/package.json`;
const identity = {
  variant,
  manifestSha256: createHash("sha256").update(manifestBytes).digest("hex"),
  sceneSpecSha256: report.sceneSpecSha256,
  sceneBlendSha256: createHash("sha256").update(readFileSync(resolve(`../asset-generators/river-background/dream-candidate/${sceneOutput}/river_dream.blend`))).digest("hex"),
  layers: manifest.layers, backdrop: manifest.backdrop,
};
const captureReportPath = resolve(folder, "capture-report.json");
const previous = existsSync(captureReportPath) ? JSON.parse(readFileSync(captureReportPath, "utf8")) : null;
const captures: Record<string, unknown>[] = previous?.identity?.manifestSha256 === identity.manifestSha256 ? previous.captures : [];
function saveCapture(capture: Record<string, unknown>): void {
  const priorIndex = captures.findIndex((entry) => entry.name === capture.name);
  if (priorIndex >= 0) captures[priorIndex] = capture;
  else captures.push(capture);
  writeFileSync(captureReportPath, JSON.stringify({ identity, evidenceScope: {
    routes: "Camera coverage points with temporary ball poses; not validated safe player spawns.",
    timeSamples: "Settled frames with held input 2; rendering across simulation time, not traversal proof.",
    performance: "Headless/SwiftShader capture costs only. Hardware FPS is unmeasured.",
  }, captures }, null, 2));
}

function check(log: { level: string; text: string }[]): any {
  assert.ok(!log.some((entry) => entry.level === "error"), "page console contains errors");
  const entry = log.find((entry) => entry.text.startsWith("background "));
  assert.ok(entry, "background diagnostics missing");
  const status = JSON.parse(entry.text.slice("background ".length));
  assert.equal(status.url, packageUrl);
  assert.equal(status.phase, "ready");
  assert.equal(status.error, null);
  assert.equal(status.layers, 2);
  assert.deepEqual(status.hiddenBodies, []);
  assert.equal(status.replaceSceneScenery, true);
  assert.equal(status.plateCovered, true);
  return status;
}

async function capture(name: string, data: any, frame: number, held: number, at?: [number, number]): Promise<string> {
  const bundleName = `${name}.json`;
  data.backgroundPackage = packageUrl;
  writeFileSync(resolve(folder, bundleName), JSON.stringify({
    level: "BALL", controller: "ball", data,
    frames: Array.from({ length: frame }, () => ({ h: held, mx: data.player.x * 0.01, my: data.player.y * 0.01 })),
  }));
  const query = new URLSearchParams({
    bundle: `/artifacts/background-runtime/${artifactFolder}/${bundleName}`,
    frame: String(frame), render: "3d", backgroundDiagnostics: "1", background: variant,
  });
  if (at) {
    query.set("zoom", "3.076923076923077");
    query.set("at", at.join(","));
  } else query.set("gameCamera", "1");
  const url = `${baseUrl}/shot.html?${query}`;
  const out = resolve(folder, `${name}.png`);
  const result = await grab(chromium, { url, out, gpu: true, width: 1920, height: 1080, timeoutMs: 60000 });
  writeFileSync(resolve(folder, `${name}.console.json`), JSON.stringify(result, null, 2));
  const status = check(result.log);
  assert.equal(status.camera.position[0], status.gameplayCamera.position[0]);
  assert.equal(status.camera.position[1], -status.gameplayCamera.position[1]);
  saveCapture({ name, kind: at ? "camera-coverage" : "settled-time-sample", url, out, frame, held, at, status, elapsedMs: result.elapsedMs, rasterizer: "headless/SwiftShader" });
  console.log(JSON.stringify({ name, out, status, elapsedMs: result.elapsedMs }));
  return out;
}

if (group === "all" || group === "routes") {
  assert.equal(report.checkpoints.length, 8);
  const requestedRoutes = process.env.DREAM_ROUTES?.split(",").map((value) => Number(value.trim()));
  if (requestedRoutes) {
    assert.ok(requestedRoutes.length > 0 && requestedRoutes.every((n) => Number.isInteger(n) && n >= 1 && n <= 8),
      "DREAM_ROUTES must contain comma-separated checkpoint numbers from 1 to 8");
    assert.equal(new Set(requestedRoutes).size, requestedRoutes.length, "DREAM_ROUTES must not contain duplicates");
  }
  const checkpoints = [...report.checkpoints.entries()].filter(([index]) => !requestedRoutes || requestedRoutes.includes(index + 1));
  const panels: { input: Buffer; left: number; top: number }[] = [];
  for (const [panelIndex, [index, [x, z]]] of checkpoints.entries()) {
    // Build report is Blender X/Z; gameplay Y is the negative Blender Z.
    const at: [number, number] = [x, -z];
    const data = structuredClone(level);
    data.player.x = at[0] * 100;
    data.player.y = at[1] * 100;
    const name = `route-${String(index + 1).padStart(2, "0")}`;
    const out = await capture(name, data, 0, 0, at);
    const label = Buffer.from(`<svg width="640" height="390"><rect y="360" width="640" height="30" fill="#11151a"/><text x="12" y="381" fill="#dae3e9" font-family="sans-serif" font-size="16">${name}: (${x.toFixed(2)}, ${(-z).toFixed(2)})</text></svg>`);
    const input = await sharp({ create: { width: 640, height: 390, channels: 4, background: "#11151a" } })
      .composite([{ input: await sharp(out).resize(640, 360).png().toBuffer(), top: 0, left: 0 }, { input: label, top: 0, left: 0 }]).png().toBuffer();
    panels.push({ input, left: (panelIndex % 2) * 640, top: Math.floor(panelIndex / 2) * 390 });
  }
  await sharp({ create: { width: 1280, height: Math.ceil(checkpoints.length / 2) * 390, channels: 4, background: "#11151a" } })
    .composite(panels).png().toFile(resolve(folder, "route-sheet.png"));
}

if (group === "all" || group === "motion") {
  for (const frame of [0, 120, 240, 360]) {
    await capture(`motion-f${frame}-h2`, structuredClone(level), frame, 2);
  }
  const composed = spawnSync(process.execPath, ["scripts/compose-dream-motion.mjs"], { stdio: "inherit", windowsHide: true });
  assert.equal(composed.status, 0, "motion montage failed");
}

if (group === "all" || group === "playable") {
  const url = `${baseUrl}/?level=BALL&render=3d&background=${variant}&backgroundDiagnostics=1`;
  const out = resolve(folder, "playable.png");
  const result = await grab(chromium, {
    url, out, gpu: true, width: 1920, height: 1080, timeoutMs: 60000,
    readyExpression: "window.__background?.phase === 'ready' && !!window.__level && !document.getElementById('loading')",
  });
  writeFileSync(resolve(folder, "playable.console.json"), JSON.stringify(result, null, 2));
  const status = check(result.log);
  saveCapture({ name: "playable", kind: "normal-playable-page", url, out, status, elapsedMs: result.elapsedMs, rasterizer: "headless/SwiftShader" });
  console.log(JSON.stringify({ name: "playable", out, status }));
}
