import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as THREE from 'three';
const [original, modified] = process.argv.slice(2);
const before=JSON.parse(readFileSync(original,'utf8'))['Terrace.002.ivy'];
const after=JSON.parse(readFileSync(modified,'utf8'))['Terrace.002.ivy'];
assert.deepEqual(before.triangles,after.triangles,'leaf topology and count retained');
assert.deepEqual(before.uv,after.uv,'painted atlas retained');
assert.deepEqual(before.color,after.color,'original greens retained');
const parents=before.position.map((_:unknown,i:number)=>i);
const find=(i:number):number=>parents[i]===i?i:(parents[i]=find(parents[i]));
const tex=new Map<number,number[]>();
before.triangles.forEach((face:number[],t:number)=>{
  const r=find(face[0]); face.forEach((id,c)=>{parents[find(id)]=r;tex.set(id,before.uv[t][c]);});
});
const groups=new Map<number,number[]>();
parents.forEach((_:number,i:number)=>{const r=find(i); if(!groups.has(r))groups.set(r,[]);groups.get(r)!.push(i);});
let changed=0, turnedDown=0;
for(const ids of groups.values()) {
  if(ids.length!==4)continue;
  const min=Math.min(...ids.map(id=>tex.get(id)![1])),max=Math.max(...ids.map(id=>tex.get(id)![1]));
  if(max-min<.02)continue;
  function frame(data:typeof before) {
    const bottom=new THREE.Vector3(),top=new THREE.Vector3();
    ids.forEach(id=>(Math.abs(tex.get(id)![1]-max)<1e-6?bottom:top).add(new THREE.Vector3().fromArray(data.position[id])));
    bottom.multiplyScalar(.5);top.multiplyScalar(.5);
    return {base:bottom.clone().lerp(top,.09),tip:top,direction:top.clone().sub(bottom)};
  }
  const a=frame(before),b=frame(after);
  assert.ok(a.base.distanceTo(b.base)<1e-6,'every stalk retains its generated attachment position');
  if(a.tip.distanceTo(b.tip)>1e-5) {
    changed++;
    assert.ok(b.direction.y<0,'modified outer leaves point downward in the camera frame');
    if(a.direction.y>0)turnedDown++;
  }
}
assert.ok(changed>200 && turnedDown>100,'the outer band changes meaningfully');
console.log(`${changed} outer leaves fan downward; ${turnedDown} formerly upward leaves corrected. Stalk positions, leaf count, textures and colours preserved.`);
