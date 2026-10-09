// Compare a clean pinned scene with the regenerated export. This guards the
// narrow merge: a bush edit must not move rocks or replace painted textures.
import assert from 'node:assert/strict';
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { MeshoptDecoder } from 'meshoptimizer';
import * as THREE from 'three';
await MeshoptDecoder.ready;
const [before, after] = process.argv.slice(2);
assert.ok(before && after, 'usage: bun run scripts/test-fuller-ivy.mts original.glb fuller.glb');
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({'meshopt.decoder':MeshoptDecoder});
const old = await io.read(before), next = await io.read(after);
const a = old.getRoot(), b = next.getRoot();
assert.equal(a.listNodes().length, b.listNodes().length);
assert.equal(a.listTextures().length, b.listTextures().length);
for (let i=0; i<a.listTextures().length; i++)
  assert.deepEqual(a.listTextures()[i].getImage(), b.listTextures()[i].getImage(), 'original painted textures preserved');
let changed=0, nonIvy=0;
for (let i=0; i<a.listNodes().length; i++) {
  const left=a.listNodes()[i], right=b.listNodes()[i];
  assert.equal(left.getName(),right.getName());
  assert.deepEqual(left.getMatrix(),right.getMatrix(),'scene transforms preserved');
  const lp=left.getMesh()?.listPrimitives() ?? [], rp=right.getMesh()?.listPrimitives() ?? [];
  assert.equal(lp.length,rp.length);
  for (let p=0;p<lp.length;p++) {
    assert.equal(lp[p].getMaterial()?.getName(),rp[p].getMaterial()?.getName());
    if (/^Ivy(Clumps)?$/.test(lp[p].getMaterial()?.getName() ?? '')) { changed++; continue; }
    assert.deepEqual(lp[p].getIndices()?.getArray(),rp[p].getIndices()?.getArray(),'non-ivy topology preserved');
    for (const semantic of lp[p].listSemantics())
      assert.deepEqual(lp[p].getAttribute(semantic)?.getArray(),rp[p].getAttribute(semantic)?.getArray(), 'non-ivy geometry preserved');
    nonIvy++;
  }
}
// Measure isolated card diagonals in world space, ignoring solid underlays.
function sizes(root: typeof a) {
  const lengths:number[]=[];
  for (const node of root.listNodes()) for (const prim of node.getMesh()?.listPrimitives() ?? []) {
    if (!/^Ivy$/.test(prim.getMaterial()?.getName() ?? '')) continue;
    const pos=prim.getAttribute('POSITION')!, uv=prim.getAttribute('TEXCOORD_0')!, idx=prim.getIndices()!;
    const parents=Array.from({length:pos.getCount()},(_,i)=>i);
    const find=(i:number):number=>parents[i]===i?i:(parents[i]=find(parents[i]));
    const indices=idx.getArray()!;
    for(let i=0;i<indices.length;i+=3) { const r=find(indices[i]); parents[find(indices[i+1])]=r; parents[find(indices[i+2])]=r; }
    const parts=new Map<number,number[]>();
    for(let i=0;i<parents.length;i++) { const r=find(i); if(!parts.has(r))parts.set(r,[]);parts.get(r)!.push(i); }
    const world=new THREE.Matrix4().fromArray(node.getWorldMatrix());
    for(const ids of parts.values()) {
      if(ids.length!==4) continue;
      const us=ids.map(i=>uv.getElement(i,[])[0]); if(Math.max(...us)-Math.min(...us)<.02)continue;
      const points=ids.map(i=>new THREE.Vector3().fromArray(pos.getElement(i,[])).applyMatrix4(world));
      lengths.push(Math.max(...points.flatMap(p=>points.map(q=>p.distanceTo(q)))));
    }
  }
  return { count:lengths.length, mean:lengths.reduce((s,v)=>s+v,0)/lengths.length };
}
const original=sizes(a), fuller=sizes(b), ratio=fuller.mean/original.mean;
assert.equal(changed,5,'all five painted ivy bushes rebuilt');
assert.ok(fuller.count>original.count,'larger leaves retain and improve coverage');
assert.ok(ratio>1.18 && ratio<1.4,`larger cards: ${ratio}`);
console.log(`Five bushes updated; ${nonIvy} other primitives and all textures unchanged. Average leaf card size +${((ratio-1)*100).toFixed(1)}%; ${original.count} → ${fuller.count} individual leaf cards.`);
