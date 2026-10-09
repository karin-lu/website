import assert from 'node:assert/strict';
import * as THREE from 'three';
import { fullerBushGeometry } from '../src/render3d/bushVolume';

const plant = new THREE.BufferGeometry();
plant.setAttribute('position', new THREE.Int16BufferAttribute([
  -3000, 0, 0, 3000, 0, 0, 29000, 25000, 0,
], 3, true));
plant.setAttribute('uv', new THREE.Float32BufferAttribute([.63,.44,.63,.44,.2,.2], 2));
plant.setAttribute('color', new THREE.Float32BufferAttribute([.03,.03,.01,.03,.03,.01,.3,.5,.2], 3));
const grown = fullerBushGeometry(plant);
assert.ok(grown.getAttribute('position').getX(2) > 1, 'quantized positions grow without wrapping');
assert.ok(grown.getAttribute('position').getY(2) > plant.getAttribute('position').getY(2));
assert.ok(Math.abs(grown.getAttribute('position').getX(0) + grown.getAttribute('position').getX(1)) < 1e-6,
  'the crown stays anchored while the plant expands');
assert.equal(fullerBushGeometry(grown), grown, 'no repeated enlargement');
assert.ok(plant.getAttribute('position').getX(2) < 1, 'cached source stays unchanged');
console.log('Bush crown anchoring and quantized geometry expansion passed.');
