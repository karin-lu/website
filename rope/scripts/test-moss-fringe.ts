import assert from 'node:assert/strict';
import * as THREE from 'three';
import { buildMossFringe } from '../src/render3d/mossFringe';

// The export splits UV charts, so adjacent triangles have duplicate vertices.
const patch = new THREE.BufferGeometry();
patch.setAttribute('position', new THREE.Float32BufferAttribute([
  0, 0, 0, 1, 0, 0, 1, .5, 0, 0, 0, 0, 1, .5, 0, 0, .5, 0,
], 3));
const fringe = buildMossFringe(patch, new THREE.Matrix4());
assert.ok(fringe.userData.mossFringeCards > 15 && fringe.userData.mossFringeCards < 60);
const positions = fringe.getAttribute('position');
for (const v of positions.array) assert.ok(Number.isFinite(v));
for (let i = 0; i < positions.count; i += 6) {
  const x = (positions.getX(i) + positions.getX(i + 1)) / 2;
  const y = (positions.getY(i) + positions.getY(i + 1)) / 2;
  assert.ok(Math.min(Math.abs(x), Math.abs(x - 1), Math.abs(y), Math.abs(y - .5)) < .06,
    'tufts stay near the exterior rim, never the internal UV seam');
}
assert.deepEqual(positions.array, buildMossFringe(patch, new THREE.Matrix4()).getAttribute('position').array);
const translated = buildMossFringe(patch, new THREE.Matrix4().makeTranslation(2, 3, 4));
assert.equal(translated.userData.mossFringeCards, fringe.userData.mossFringeCards, 'placement is host-local');
for (const v of fringe.getAttribute('uv').array) assert.ok(v >= 0 && v <= 1);
assert.equal(patch.getAttribute('position').count, 6, 'cached mound stays intact');
patch.setAttribute('uv', new THREE.Float32BufferAttribute([0,0,1,0,1,1,0,0,1,1,0,1], 2));
const ground = new THREE.Color('#6f913b');
const matched = buildMossFringe(patch, new THREE.Matrix4(), undefined, 8107, () => ground.clone());
const colour = matched.getAttribute('color');
assert.ok(Math.abs(colour.getX(0) - ground.r) < 1e-6, 'tuft root matches sampled moss colour');
assert.ok(Math.abs(colour.getY(0) - ground.g) < 1e-6);
assert.ok(colour.getY(4) > colour.getY(0), 'the colour fades gently toward lighter tips');
console.log('Moss rim welding, bounded density, rooted cards and deterministic placement passed.');
