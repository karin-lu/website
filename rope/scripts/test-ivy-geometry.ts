import assert from 'node:assert/strict';
import * as THREE from 'three';
import { curveIvyGeometry } from '../src/render3d/ivyGeometry';
import { VineSurface } from '../src/render3d/ivySurface';

const card = new THREE.BufferGeometry();
card.setAttribute('position', new THREE.Float32BufferAttribute([-.1, 0, .07, .1, 0, .07, -.1, .3, .07, .1, .3, .07], 3));
card.setAttribute('uv', new THREE.Float32BufferAttribute([0, .19, .19, .19, 0, 0, .19, 0], 2));
card.setAttribute('color', new THREE.Float32BufferAttribute(Array(4).fill([.2, .6, .1]).flat(), 3));
card.setIndex([0, 1, 3, 0, 3, 2]);
card.computeVertexNormals();
const rock = new VineSurface(new Float32Array([-2,-2,0, 2,-2,0, 2,2,0, -2,-2,0, 2,2,0, -2,2,0]));
const curved = curveIvyGeometry(card, new THREE.Matrix4(), rock);
assert.equal(curved.getAttribute('position').count, 15);
assert.equal(curved.index!.count, 48);
assert.ok(curved.getAttribute('position').getZ(4) < .02, 'leaf base settles against the rock');
assert.ok(curved.getAttribute('position').getZ(7) > curved.getAttribute('position').getZ(4), 'leaf rises from its attachment');
assert.ok(curved.getAttribute('position').getZ(13) < curved.getAttribute('position').getZ(10), 'tip curls down');
for (const value of curved.getAttribute('position').array) assert.ok(Number.isFinite(value));
for (let i = 0; i < 15; i++) {
  assert.ok(curved.getAttribute('position').getZ(i) >= .0019, 'no rock penetration');
  assert.ok(curved.getAttribute('uv').getX(i) >= 0 && curved.getAttribute('uv').getX(i) <= .191);
  assert.ok(Math.abs(curved.getAttribute('color').getY(i) - .6) < .00001);
}
assert.deepEqual(curved.getAttribute('position').array, curveIvyGeometry(card, new THREE.Matrix4(), rock).getAttribute('position').array);
assert.equal(curveIvyGeometry(curved, new THREE.Matrix4(), rock), curved, 'no repeated bending');
assert.equal(card.getAttribute('position').count, 4, 'source remains intact');
const stem = card.clone(); stem.setAttribute('uv', new THREE.Float32BufferAttribute(Array(8).fill(.99), 2));
assert.equal(curveIvyGeometry(stem, new THREE.Matrix4(), rock), stem, 'constant UV support geometry is retained');
const mirrored = curveIvyGeometry(card, new THREE.Matrix4().makeScale(-1, 1, 1), rock);
assert.ok(mirrored.getAttribute('normal').getZ(7) > 0, 'mirrored hosts retain the correct leaf winding');
const stacked = new THREE.BufferGeometry();
const upper=card.clone(); upper.translate(0,.08,.07);
for (const name of Object.keys(card.attributes)) stacked.setAttribute(name,new THREE.Float32BufferAttribute([
  ...card.getAttribute(name).array,...upper.getAttribute(name).array],card.getAttribute(name).itemSize));
stacked.setIndex([0,1,3,0,3,2,4,5,7,4,7,6]);
const layered=curveIvyGeometry(stacked,new THREE.Matrix4(),rock,()=>true);
assert.equal(layered.userData.ivyLeafCards,2,'original leaf count is retained');
assert.equal(layered.userData.leafContacts,1,'the upper stalk rests on the lower leaf');
assert.ok(layered.getAttribute('position').getZ(19)>.004,'the original upper layer is supported above the rock');
const masked=curveIvyGeometry(stacked,new THREE.Matrix4(),rock,()=>false);
assert.equal(masked.userData.leafContacts,0,'transparent atlas pixels cannot support a stalk');
assert.equal(masked.userData.hostContacts,2,'unsupported stalks fall back to a real host');
console.log('Original leaf layers, alpha-aware attachments, texture preservation and clearance checks passed.');
