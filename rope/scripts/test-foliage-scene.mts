import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { MeshoptDecoder } from 'meshoptimizer';
import * as THREE from 'three';
import { curveIvyGeometry } from '../src/render3d/ivyGeometry';
import { ivyHostSurface } from '../src/render3d/ivyGeometry';
import { buildMossFringe } from '../src/render3d/mossFringe';
import assert from 'node:assert/strict';
await MeshoptDecoder.ready;
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({'meshopt.decoder':MeshoptDecoder});
const doc = await io.read('public/scenes/river/scene.glb');
const root = new THREE.Group();
const objects = new Map<any,THREE.Group>();
for (const node of doc.getRoot().listNodes()) {
  const group = new THREE.Group(); group.name=node.getName(); group.userData.name=node.getName();
  group.matrix.fromArray(node.getMatrix()); group.matrixAutoUpdate=false; objects.set(node,group);
}
for (const [node,group] of objects) (objects.get(node.getParentNode()) ?? root).add(group);
let leaves=0,companions=0,tufts=0,mounds=0;
for (const node of doc.getRoot().listNodes()) {
  for (const prim of node.getMesh()?.listPrimitives() ?? []) {
    const mat = prim.getMaterial()!;
    const geo = new THREE.BufferGeometry();
    for (const [semantic,name] of [['POSITION','position'],['NORMAL','normal'],['TEXCOORD_0','uv'],['COLOR_0','color']]) {
      const a = prim.getAttribute(semantic); if (!a) continue;
      const values = Array.from(a.getArray()!); const ct = a.getComponentType();
      if (a.getNormalized()) for (let i=0;i<values.length;i++) values[i] /= ct===5121?255:ct===5123?65535:ct===5122?32767:1;
      geo.setAttribute(name,new THREE.Float32BufferAttribute(values,a.getElementSize()));
    }
    if (prim.getIndices()) geo.setIndex(Array.from(prim.getIndices()!.getArray()!));
    const material = new THREE.MeshStandardMaterial(); material.name=mat.getName();
    material.alphaTest=mat.getAlphaMode()==='MASK'?.5:0; material.transparent=mat.getAlphaMode()==='BLEND';
    objects.get(node)!.add(new THREE.Mesh(geo,material));
  }
}
root.updateMatrixWorld(true);
root.traverse(o=>{
  if (!(o instanceof THREE.Mesh)) return;
  const material = o.material as THREE.Material;
  if (/^Ivy(Clumps)?$/.test(material.name)) {
    const curved=curveIvyGeometry(o.geometry,o.matrixWorld,ivyHostSurface(o));
    assert.ok(curved.userData.curvedIvy,'exported cards are recognized');
    for (const v of curved.getAttribute('position').array) assert.ok(Number.isFinite(v));
    leaves += curved.userData.ivyLeafCards;
    companions += curved.userData.rockBushCompanionLeaves;
  }
  if (/\.moss$/.test(material.name)) {
    const fringe=buildMossFringe(o.geometry,o.matrixWorld,ivyHostSurface(o));
    assert.ok(fringe.userData.mossFringeCards > 0 && fringe.userData.mossFringeCards <= 1400);
    for (const v of fringe.getAttribute('position').array) assert.ok(Number.isFinite(v));
    tufts+=fringe.userData.mossFringeCards; mounds++;
    console.log(`${o.parent!.name}: ${fringe.userData.mossFringeCards} moss edge cards`);
  }
});
assert.equal(mounds,3); assert.ok(leaves>1000); assert.ok(companions>1000);
console.log(`Published river scene passed: ${leaves} curved leaf cards including ${companions} rooted companions, ${tufts} edge tufts across ${mounds} moss mounds.`);
