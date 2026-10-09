import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { MeshoptDecoder } from 'meshoptimizer';
import * as THREE from 'three';
import { curveIvyGeometry } from '../src/render3d/ivyGeometry';
import { ivyHostSurface } from '../src/render3d/ivyGeometry';
import { buildMossFringe } from '../src/render3d/mossFringe';
import { buildBushSupport } from '../src/render3d/bushSupport';
import { buildBushLeafCover } from '../src/render3d/bushLeafCover';
import { VineSurface } from '../src/render3d/ivySurface';
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
let leaves=0,companions=0,tufts=0,mounds=0,cushions=0;
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
    const host=ivyHostSurface(o);
    assert.ok(host, `the rock host is found through unnamed groups for ${o.parent!.parent!.name}`);
    const curved=curveIvyGeometry(o.geometry,o.matrixWorld,host,true);
    const before = curved.getAttribute('position').count;
    const cushion = buildBushSupport(curved, o.matrixWorld, () => new THREE.Color('#638a38'));
    const cover=buildBushLeafCover(cushion,curved,o.matrixWorld);
    assert.ok(cover.userData.cameraCoverCards>0, 'every bush has camera-facing leaf coverage');
    const soup: number[]=[];
    const p=new THREE.Vector3(), supportPosition=cushion.getAttribute('position');
    for (let i=0;i<supportPosition.count;i++) p.fromBufferAttribute(supportPosition,i).applyMatrix4(o.matrixWorld).toArray(soup,soup.length);
    const backingSurface=new VineSurface(soup);
    for (let card=0;card<cover.userData.cameraCoverCards;card+=7) for (const vertex of [4,6,7,8,10,13]) {
      p.fromBufferAttribute(cover.getAttribute('position'),card*15+vertex).applyMatrix4(o.matrixWorld);
      assert.ok(backingSurface.nearest(p)!.signed >= .0058, 'visible leaves clear the backing surface');
    }
    for (const root of cover.userData.bushLeafRoots as number[][]) {
      const contact=backingSurface.nearest(new THREE.Vector3().fromArray(root))!;
      assert.ok(contact.distance<=.00601, 'each leaf grows directly on the blob surface');
    }
    assert.ok(cushion.userData.bushSupportLobes > 0, 'every rock bush receives solid support');
    assert.equal(cushion.userData.bushSupportLobes, 1, 'the support is a fused surface instead of separate lobes');
    assert.equal(cushion.userData.continuousBushSupport, true);
    const backingColour = cushion.getAttribute('color');
    for (let i=1;i<backingColour.count;i++) for (let channel=0;channel<3;channel++) {
      assert.equal(backingColour.getComponent(i,channel), backingColour.getComponent(0,channel),
        'one consistent green palette covers the whole backing');
    }
    for (const value of cushion.getAttribute('position').array) assert.ok(Number.isFinite(value));
    assert.equal(curved.getAttribute('position').count, before, 'support adds no leaf cards');
    assert.deepEqual(cushion.getAttribute('position').array,
      buildBushSupport(curved, o.matrixWorld, () => new THREE.Color('#638a38')).getAttribute('position').array,
      'the organic support remains stable between loads');
    cushions++;
    assert.ok(curved.userData.curvedIvy,'exported cards are recognized');
    const roots = curved.userData.rockBushFanRoots as number[][];
    for (let i=0;i<roots.length;i++) for (let j=0;j<i;j++) {
      assert.ok(new THREE.Vector3().fromArray(roots[i]).distanceTo(new THREE.Vector3().fromArray(roots[j])) >= .13999,
        'outer fans keep room between their roots, including across cell boundaries');
    }
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
assert.equal(mounds,3); assert.ok(leaves>1000);
assert.equal(cushions,5, 'all five ivy bushes get a green cushion');
assert.ok(companions>20 && companions < leaves * .25, 'outer fans are sparse over a compact inner carpet');
console.log(`Published river scene passed: ${leaves} curved leaf cards including ${companions} rooted companions, ${tufts} edge tufts across ${mounds} moss mounds.`);
