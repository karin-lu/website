import assert from "node:assert/strict";
import * as THREE from "three";
import { buildMossFringe, CELLS } from "../src/render3d/mossFringe";
import { applyMossCardEdits } from "../src/render3d/mossCardEdits";
import { emptyModel, modelFromDisk, modelToDisk } from "../src/editor/model";
import { scaleLevelData } from "../src/level/levelFormat";
import type { FoliageCards } from "../src/level/foliageCards";
import { FoliageEditor } from "../src/editor/foliage";

const patch = new THREE.PlaneGeometry(1, .5);
const source = buildMossFringe(patch, new THREE.Matrix4());
const mesh = new THREE.Mesh(source); mesh.userData.mossPatch = "test.moss";
const other = mesh.clone(); const original = source.getAttribute("position").array.slice();
const edits: FoliageCards = { "test.moss": { "0": { width: 1.7, height: 1.4, curve: .2, rotation: .3, variant: 2, offset: [.2, -.1, .03], points: Array.from({length: 8}, (_, i) => [0, 0, i === 7 ? .04 : 0]) } } };
applyMossCardEdits(mesh, edits);
assert.notEqual(mesh.geometry, source);
assert.equal(other.geometry, source);
assert.deepEqual(source.getAttribute("position").array, original, "shared source remains untouched");
assert.notDeepEqual(mesh.geometry.getAttribute("position").array.slice(0, 24), original.slice(0, 24));
assert.deepEqual(mesh.geometry.getAttribute("position").array.slice(24), original.slice(24), "other cards retain their positions");
assert.deepEqual(mesh.geometry.getAttribute("normal").array.slice(24), source.getAttribute("normal").array.slice(24), "other cards retain painted normals");
for (const value of mesh.geometry.getAttribute("position").array) assert.ok(Number.isFinite(value));
assert.ok(Math.abs(mesh.geometry.getAttribute("uv").getX(0) - CELLS[2][0]) < .000001);
const firstGeometry = mesh.geometry;
applyMossCardEdits(mesh, structuredClone(edits));
assert.equal(mesh.geometry, firstGeometry, "unchanged edits do not rebuild");
edits["test.moss"]["1"] = { hidden: true };
applyMossCardEdits(mesh, edits);
assert.equal(mesh.geometry.index!.count, source.index!.count - 18);
assert.equal(mesh.geometry.userData.faceCards[6], 2, "picking maps correctly after hiding a card");
applyMossCardEdits(mesh, {});
assert.deepEqual(mesh.geometry.getAttribute("position").array, original, "reset and undo restore source");
assert.deepEqual(mesh.geometry.getAttribute("normal").array, source.getAttribute("normal").array);
const model = emptyModel(); model.scene = "ball"; model.foliageCards = structuredClone(edits);
const disk = modelToDisk(model), loaded = modelFromDisk(JSON.parse(JSON.stringify(disk)));
assert.deepEqual(loaded.foliageCards, edits, "all card edits survive editor save/load");
assert.deepEqual(scaleLevelData(disk, 1 / 100).foliageCards, edits, "moss-local metres are not scaled with the gameplay plane");
loaded.foliageCards["test.moss"]["0"].offset![0] = 9;
assert.equal(model.foliageCards["test.moss"]["0"].offset![0], .2, "load does not alias saved or live state");
// Exercise the real drag handler with a camera and translated moss surface.
// No browser or renderer is needed to test pointer-to-surface placement.
const mound = new THREE.Mesh(patch); mound.position.set(.5, .1, 0); mound.add(mesh); mound.updateMatrixWorld(true);
const camera = new THREE.PerspectiveCamera(45, 1, .01, 100);
camera.position.set(.5, .1, 4); camera.lookAt(.5, .1, 0); camera.updateMatrixWorld(true);
const root = new THREE.Vector3().fromBufferAttribute(mesh.geometry.getAttribute("position"), 2)
  .add(new THREE.Vector3().fromBufferAttribute(mesh.geometry.getAttribute("position"), 3)).multiplyScalar(.5);
const live: FoliageCards = {}; let actions = 0;
const controller = Object.create(FoliageEditor.prototype) as any;
controller.active = true; controller.selected = { patch: "test.moss", card: 0 }; controller.ray = new THREE.Raycaster();
controller.host = {
  canvas: { getBoundingClientRect: () => ({ left: 0, top: 0, width: 200, height: 200 }) },
  camera: () => camera, edits: () => live, editable: () => true, begin: () => actions++, changed: () => {},
};
controller.gesture = { mesh, edit: {}, plane: new THREE.Plane(new THREE.Vector3(0, 0, 1), 0),
  start: new THREE.Vector3(.5, .1, 0), root, point: -1, moved: false };
function dragTo(local: THREE.Vector3): void {
  const ndc = local.clone().applyMatrix4(mound.matrixWorld).project(camera);
  controller.move({ clientX: (ndc.x + 1) * 100, clientY: (1 - ndc.y) * 100, preventDefault() {}, stopImmediatePropagation() {} });
  const expected = local.clone().sub(root), actual = new THREE.Vector3(...live["test.moss"]["0"].offset!);
  assert.ok(actual.distanceTo(expected) < 1e-6, "card root follows the actual translated moss surface");
}
dragTo(new THREE.Vector3(.1, .1, 0));
dragTo(new THREE.Vector3(.2, .05, 0));
assert.equal(actions, 1, "rapid pointer moves without rendering make one undoable action without drift");
console.log("Moss card editing: selection mapping, geometry isolation, shaping, reset and save/load passed.");
