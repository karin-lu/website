import assert from "node:assert/strict";
import * as THREE from "three";
import { Vec2 } from "../src/engine/vec2";
import type { Camera } from "../src/render/camera";
import { modelFromDisk, modelToDisk } from "../src/editor/model";
import { readClipboard, writeClipboard } from "../src/editor/clipboard";
import { normalizeLevelData, scaleLevelData, type RawLevelData } from "../src/level/levelFormat";
import { BackgroundPackage, backgroundPlateMapping, syncBackgroundCamera, type BackgroundPackageLoader } from "../src/render3d/backgroundPackage";
import { backgroundAssetUrl, parseBackgroundManifest, type BackgroundManifest } from "../src/render3d/backgroundManifest";
import { levelStoredFiles } from "../src/render3d/levelAssets";
import { cameraDistance } from "../src/render3d/space";

const manifest: BackgroundManifest = {
  version: 1, colorSpace: "srgb-display",
  camera: { fovYDeg: 19.455672, distance: 10.2375, origin: [10.85, -8] },
  layers: [{ id: "near", file: "near.glb" }, { id: "far", file: "far.glb", bytes: 200 }],
  backdrop: { file: "backdrop.png", worldWidth: 18, worldHeight: 11, origin: [10.85, -8], pan: 0.02 },
  hideBodyIds: [205],
};
const close = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-8, `${a} differs from ${b}`);
const camera: Camera = { position: new Vec2(10.85, 8), zoom: 2, viewportWidth: 1920, viewportHeight: 1080 };
const backgroundCamera = new THREE.PerspectiveCamera();
syncBackgroundCamera(backgroundCamera, camera, manifest);
close(backgroundCamera.position.y, -8);
const projection = backgroundCamera.projectionMatrix.clone();
const nearPoint = new THREE.Vector3(13, -7, -30);
const foregroundPoint = new THREE.Vector3(13, -7, 0);
const beforeNear = nearPoint.clone().project(backgroundCamera);
const beforeForeground = foregroundPoint.clone().project(backgroundCamera);
syncBackgroundCamera(backgroundCamera, { ...camera, position: new Vec2(11.85, 8), zoom: 5 }, manifest);
assert.deepEqual(backgroundCamera.projectionMatrix.toArray(), projection.toArray(), "zoom response defaults to zero");
close(backgroundCamera.position.z, manifest.camera.distance);
const afterNear = nearPoint.clone().project(backgroundCamera);
const afterForeground = foregroundPoint.clone().project(backgroundCamera);
close((afterNear.x - beforeNear.x) / (afterForeground.x - beforeForeground.x), manifest.camera.distance / (manifest.camera.distance + 30));
syncBackgroundCamera(backgroundCamera, camera, { ...manifest, camera: { ...manifest.camera, zoomResponse: 1 } });
close(backgroundCamera.position.z, cameraDistance(camera, manifest.camera.fovYDeg));
syncBackgroundCamera(backgroundCamera, camera, manifest);
const plate = backgroundPlateMapping(backgroundCamera, manifest);
close(plate.offsetX, (1 - plate.repeatX) / 2);
close(plate.offsetY, (1 - plate.repeatY) / 2);
assert.ok(plate.covered);
syncBackgroundCamera(backgroundCamera, { ...camera, position: new Vec2(20.85, -2) }, manifest);
const movedPlate = backgroundPlateMapping(backgroundCamera, manifest);
close(movedPlate.offsetX - plate.offsetX, 10 * 0.02 / 18);
close(movedPlate.offsetY - plate.offsetY, 10 * 0.02 / 11);
syncBackgroundCamera(backgroundCamera, { ...camera, viewportWidth: 1080, viewportHeight: 1920 }, manifest);
close(backgroundPlateMapping(backgroundCamera, manifest).repeatY, plate.repeatY);

assert.equal(backgroundAssetUrl("/backgrounds/river/package.json", "near.glb"), "/backgrounds/river/near.glb");
assert.equal(backgroundAssetUrl("https://example.com/scenery/package.json", "near.glb"), "https://example.com/scenery/near.glb");
assert.throws(() => parseBackgroundManifest({ ...manifest, camera: { ...manifest.camera, distance: 0 } }));
assert.throws(() => parseBackgroundManifest({ ...manifest, layers: [manifest.layers[0], manifest.layers[0]] }));
assert.throws(() => parseBackgroundManifest({ ...manifest, hideBodyIds: [-1] }));
assert.throws(() => parseBackgroundManifest({ ...manifest, replaceSceneScenery: "true" }));
const foliageFog = { color: [.028, .064, .092] as [number, number, number], near: 20, far: 190 };
assert.deepEqual(parseBackgroundManifest({ ...manifest, foliageFog }).foliageFog, foliageFog);
for (const invalidFog of [null, { ...foliageFog, color: [0, 1] }, { ...foliageFog, color: [0, -1, 0] },
  { ...foliageFog, color: [0, 0, Infinity] }, { ...foliageFog, color: [0, 0, 1.01] },
  { ...foliageFog, near: -1 }, { ...foliageFog, far: 20 }, { ...foliageFog, far: NaN }]) {
  assert.throws(() => parseBackgroundManifest({ ...manifest, foliageFog: invalidFog }));
}

const raw: RawLevelData = { player: { x: 1085, y: 800, radius: 8 }, bodies: [], backgroundPackage: "/backgrounds/river/package.json" };
assert.equal(normalizeLevelData(raw).backgroundPackage, raw.backgroundPackage);
assert.equal(scaleLevelData(scaleLevelData(raw, 0.01), 100).backgroundPackage, raw.backgroundPackage);
const model = modelFromDisk(raw);
assert.equal(modelToDisk(model).backgroundPackage, raw.backgroundPackage);
const bare = modelToDisk(modelFromDisk({ player: raw.player, bodies: [] }));
assert.ok(!Object.hasOwn(bare, "backgroundPackage"), "absent package remains absent");
assert.ok(!writeClipboard(model, []).includes("backgroundPackage"));
const payload = JSON.parse(writeClipboard(model, []));
assert.equal(readClipboard(JSON.stringify({ ...payload, backgroundPackage: raw.backgroundPackage }))!.backgroundPackage, undefined);
const files = levelStoredFiles(raw, undefined, manifest);
for (const file of ["package.json", "near.glb", "far.glb", "backdrop.png"]) assert.ok(files.some((f) => f.file === `/backgrounds/river/${file}`));
assert.equal(files.find((f) => f.file.endsWith("far.glb"))!.bytes, 200);

function resources() {
  const geometry = new THREE.BoxGeometry();
  const material = new THREE.MeshBasicMaterial({ vertexColors: true });
  const texture = new THREE.DataTexture(new Uint8Array([255, 255, 255, 255]), 1, 1);
  const counts = { geometry: 0, material: 0, texture: 0 };
  geometry.addEventListener("dispose", () => counts.geometry++);
  material.addEventListener("dispose", () => counts.material++);
  texture.addEventListener("dispose", () => counts.texture++);
  const near = new THREE.Mesh(geometry, material);
  const far = new THREE.Mesh(geometry, material);
  return { near, far, texture, material, counts };
}
const r = resources();
const requested: string[] = [];
const loader: BackgroundPackageLoader = {
  manifest: async () => ({ ...manifest, replaceSceneScenery: true }),
  layer: async (url) => { requested.push(url); return url.endsWith("near.glb") ? r.near : r.far; },
  texture: async () => r.texture,
};
const background = new BackgroundPackage(loader);
background.setPackage(raw.backgroundPackage);
assert.equal(background.ready, false);
assert.equal(background.replaceSceneScenery, false, "retain current scene while loading");
assert.deepEqual(background.hideBodyIds, []);
await background.wait();
assert.equal(background.ready, true);
assert.equal(background.replaceSceneScenery, true, "replace scenery only after all assets load");
assert.deepEqual(background.hideBodyIds, [205]);
assert.equal(r.material.vertexColors, true, "authored vertex color materials survive");
assert.equal(r.material.toneMapped, false);
assert.equal(r.material.fog, false, "baked rocks do not receive runtime haze");
assert.equal(background.scene.fog, null, "legacy manifests retain their appearance");
assert.equal(r.texture.colorSpace, THREE.SRGBColorSpace);
background.setPackage(raw.backgroundPackage);
await background.wait();
assert.equal(requested.length, 2, "editor rebuild does not reload the same URL");

const gameplay = new THREE.Scene();
const gameplayFog = new THREE.Fog("#112233", 5, 500);
gameplay.fog = gameplayFog;
const clearColor = new THREE.Color("#123456");
gameplay.background = clearColor;
let throwOnGame = false;
const order: string[] = [];
const renderer = {
  autoClear: true,
  info: { autoReset: true, reset: () => {} },
  shadowMap: { enabled: true },
  clear: () => order.push("clear"), clearDepth: () => order.push("depth"),
  render: (scene: THREE.Scene) => {
    if (scene === gameplay) {
      assert.equal(gameplay.background, null);
      assert.equal(renderer.shadowMap.enabled, true);
      order.push("game");
      if (throwOnGame) throw new Error("draw failure");
    } else {
      assert.equal(renderer.shadowMap.enabled, false);
      order.push(scene === background.scene ? "layers" : "plate");
    }
  },
};
background.render(renderer as unknown as THREE.WebGLRenderer, gameplay, backgroundCamera);
assert.deepEqual(order, ["clear", "plate", "layers", "depth", "game"]);
assert.equal(gameplay.background, clearColor);
assert.equal(gameplay.fog, gameplayFog, "background composition must not change gameplay fog");
assert.equal(renderer.autoClear, true);
assert.equal(renderer.info.autoReset, true);
throwOnGame = true;
assert.throws(() => background.render(renderer as unknown as THREE.WebGLRenderer, gameplay, backgroundCamera));
assert.equal(gameplay.background, clearColor);
assert.equal(renderer.autoClear, true);
assert.equal(renderer.shadowMap.enabled, true);
assert.equal(renderer.info.autoReset, true);
background.dispose();
assert.equal(background.replaceSceneScenery, false, "restore current scene on teardown");
assert.deepEqual(r.counts, { geometry: 1, material: 1, texture: 1 });

const failedResources = resources();
const failing = new BackgroundPackage({
  manifest: async () => ({ ...manifest, foliageFog }),
  layer: async (url) => { if (url.endsWith("far.glb")) throw new Error("missing far layer"); return failedResources.near; },
  texture: async () => failedResources.texture,
});
const warn = console.warn;
try {
  console.warn = () => {};
  failing.setPackage(raw.backgroundPackage);
  await failing.wait();
} finally { console.warn = warn; }
assert.equal(failing.status().phase, "failed");
assert.equal(failing.ready, false);
assert.equal(failing.scene.fog, null, "failed package must not install its fog");
assert.deepEqual(failing.hideBodyIds, []);
assert.deepEqual(failedResources.counts, { geometry: 1, material: 1, texture: 1 });
failing.dispose();

const late = resources();
let resolveNear!: (object: THREE.Object3D) => void;
const nearPromise = new Promise<THREE.Object3D>((resolve) => { resolveNear = resolve; });
let started!: () => void;
const began = new Promise<void>((resolve) => { started = resolve; });
const replaced = new BackgroundPackage({
  manifest: async () => ({ ...manifest, foliageFog }),
  layer: (url) => { started(); return url.endsWith("near.glb") ? nearPromise : Promise.resolve(late.far); },
  texture: async () => late.texture,
});
replaced.setPackage(raw.backgroundPackage);
const oldWait = replaced.wait();
await began;
replaced.setPackage(undefined);
resolveNear(late.near);
await oldWait;
assert.equal(replaced.status().phase, "none");
assert.equal(replaced.scene.children.length, 0);
assert.equal(replaced.scene.fog, null, "late superseded load must not restore its fog");
assert.deepEqual(late.counts, { geometry: 1, material: 1, texture: 1 });
replaced.dispose();
const cardTexture = new THREE.DataTexture(new Uint8Array([255,255,255,255]),1,1);
const litCard = new THREE.MeshBasicMaterial({ map: cardTexture, alphaTest: .42 });
litCard.userData = { river_preserve_material: true, river_preserved_bake_lighting: true };
const oldCard = new THREE.MeshBasicMaterial({ map: cardTexture, alphaTest: .42 });
oldCard.userData = { river_preserve_material: true };
const untaggedTexture = new THREE.MeshBasicMaterial({ map: cardTexture, alphaTest: .42 });
const taggedStone = new THREE.MeshBasicMaterial({ vertexColors: true });
taggedStone.userData = { river_preserve_material: true, river_preserved_bake_lighting: true };
const opaqueLitTexture = new THREE.MeshBasicMaterial({ map: cardTexture });
opaqueLitTexture.userData = { river_preserve_material: true, river_preserved_bake_lighting: true };
let withFog = true;
const fogged = new BackgroundPackage({
  manifest: async () => withFog ? { ...manifest, foliageFog } : manifest,
  layer: async () => {
    const group = new THREE.Group();
    for (const material of [litCard, oldCard, untaggedTexture, taggedStone, opaqueLitTexture]) {
      group.add(new THREE.Mesh(new THREE.PlaneGeometry(), material));
    }
    return group;
  },
  texture: async () => new THREE.DataTexture(new Uint8Array([255,255,255,255]),1,1),
});
fogged.setPackage("/backgrounds/fogged/package.json");
await fogged.wait();
assert.ok(fogged.ready && fogged.scene.fog instanceof THREE.Fog);
assert.equal(litCard.fog, true, "only opted-in lit textures receive distance haze");
assert.equal(litCard.alphaToCoverage, true, "opted-in lit cutouts use existing MSAA for soft edges");
for (const mat of [oldCard, untaggedTexture, taggedStone, opaqueLitTexture]) assert.equal(mat.alphaToCoverage, false, "legacy and opaque materials keep their edge behavior");
for (const mat of [oldCard, untaggedTexture, taggedStone]) assert.equal(mat.fog, false);
close(fogged.scene.fog.color.r, foliageFog.color[0]);
close(fogged.scene.fog.color.g, foliageFog.color[1]);
close(fogged.scene.fog.color.b, foliageFog.color[2]);
assert.equal(fogged.scene.fog.near, 20);
assert.equal(fogged.scene.fog.far, 190);
withFog = false;
fogged.setPackage("/backgrounds/legacy/package.json");
assert.equal(fogged.scene.fog, null, "loading replacement clears previous fog");
await fogged.wait();
assert.ok(fogged.ready);
assert.equal(fogged.scene.fog, null, "ready legacy replacement keeps previous fog cleared");
assert.equal(litCard.fog, false, "opted-in material has no haze without manifest settings");
fogged.dispose();
console.log("background package: camera/motion, plate mapping, serialization, preloads, atomic loading, composition, and disposal passed");
