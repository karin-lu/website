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
let leaves=0,leafContacts=0,hostContacts=0,tufts=0,mounds=0,authored=0;
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
    const curved=curveIvyGeometry(o.geometry,o.matrixWorld,host);
    assert.ok(curved.userData.curvedIvy,'exported cards are recognized');
    assert.equal(curved.userData.attachments.length,curved.userData.ivyLeafCards,'every leaf has support');
    for (const attachment of curved.userData.attachments) {
      assert.ok(Math.abs(new THREE.Vector3().fromArray(attachment.point).distanceTo(new THREE.Vector3().fromArray(attachment.supportPoint))-.002)<1e-5,
        'the stalk meets its support with 2 mm clearance');
    }
    for (const v of curved.getAttribute('position').array) assert.ok(Number.isFinite(v));
    leaves+=curved.userData.ivyLeafCards; leafContacts+=curved.userData.leafContacts; hostContacts+=curved.userData.hostContacts;
  }
  if (/^MossCards(?:\.\d+)?$/.test(material.name)) {
    const geo = o.geometry;
    assert.ok(geo.index && geo.getAttribute('uv') && geo.getAttribute('color'));
    assert.equal(geo.index!.count % 18, 0, 'authored cards retain six triangles each');
    tufts += geo.index!.count / 18; authored++;
  }
  if (/\.moss\.authored$/.test(material.name)) mounds++;
  if (/\.moss$/.test(material.name)) {
    const fringe=buildMossFringe(o.geometry,o.matrixWorld,ivyHostSurface(o));
    assert.ok(fringe.userData.mossFringeCards > 0 && fringe.userData.mossFringeCards <= 1400);
    for (const v of fringe.getAttribute('position').array) assert.ok(Number.isFinite(v));
    tufts+=fringe.userData.mossFringeCards; mounds++;
    console.log(`${o.parent!.name}: ${fringe.userData.mossFringeCards} moss edge cards`);
  }
});
assert.equal(mounds,3); if(authored) assert.equal(authored,3); assert.ok(leaves>1000); assert.ok(leafContacts>1000); assert.ok(hostContacts>0);
console.log(`Original river layers passed: ${leaves} curved leaves, ${leafContacts} leaf/underlay contacts, ${hostContacts} rock contacts, ${tufts} moss tufts.`);
