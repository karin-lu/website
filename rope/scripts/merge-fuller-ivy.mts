// Merge Blender's regenerated ivy into the pinned scene without rebaking rocks,
// moss, ferns or lighting. See tools/blender/fuller_ivy.py for the growth recipe.
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { MeshoptDecoder, MeshoptEncoder } from 'meshoptimizer';
import * as THREE from 'three';

const [input, payloadPath, output] = process.argv.slice(2);
assert.ok(input && payloadPath && output, 'usage: bun run scripts/merge-fuller-ivy.mts scene.glb ivy.json output.glb');
await Promise.all([MeshoptDecoder.ready, MeshoptEncoder.ready]);
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
  'meshopt.decoder': MeshoptDecoder, 'meshopt.encoder': MeshoptEncoder,
});
const doc = await io.read(input);
const buffer = doc.getRoot().listBuffers()[0]!;
const payload = JSON.parse(readFileSync(payloadPath, 'utf8')) as Record<string, {
  position: number[][]; normal: number[][]; color: number[][];
  uv: number[][][]; triangles: number[][]; leaves: number;
}>;
for (const [name, data] of Object.entries(payload)) {
  const owner = doc.getRoot().listNodes().find(n => n.getName() === name);
  const nodes = owner ? [owner, ...owner.listChildren()] : [];
  const node = nodes.find(n => n.getMesh()?.listPrimitives().some(p => /^Ivy(Clumps)?$/.test(p.getMaterial()?.getName() ?? '')));
  assert.ok(node?.getMesh(), `original scene contains ${name}`);
  const prims = node.getMesh()!.listPrimitives();
  assert.equal(prims.length, 1, 'ivy uses one original material');
  const prim = prims[0]!;
  assert.match(prim.getMaterial()!.getName(), /^Ivy(Clumps)?$/);
  const inverse = new THREE.Matrix4().fromArray(node.getWorldMatrix()).invert();
  const normalMatrix = new THREE.Matrix3().getNormalMatrix(inverse);
  const position: number[] = [], normal: number[] = [], color: number[] = [], uv: number[] = [], indices: number[] = [];
  const seen = new Map<string, number>();
  for (let t = 0; t < data.triangles.length; t++) for (let c = 0; c < 3; c++) {
    const id = data.triangles[t]![c]!;
    const tex = data.uv[t]![c]!;
    const key = `${id}/${tex[0]}/${tex[1]}`;
    let vertex = seen.get(key);
    if (vertex === undefined) {
      vertex = seen.size; seen.set(key, vertex);
      position.push(...new THREE.Vector3().fromArray(data.position[id]!).applyMatrix4(inverse).toArray());
      normal.push(...new THREE.Vector3().fromArray(data.normal[id]!).applyMatrix3(normalMatrix).normalize().toArray());
      color.push(...data.color[id]!); uv.push(...tex);
    }
    indices.push(vertex);
  }
  for (const [semantic, type, array] of [
    ['POSITION', 'VEC3', position], ['NORMAL', 'VEC3', normal],
    ['COLOR_0', 'VEC4', color], ['TEXCOORD_0', 'VEC2', uv],
  ] as const) prim.setAttribute(semantic, doc.createAccessor().setType(type).setArray(new Float32Array(array)).setBuffer(buffer));
  prim.setIndices(doc.createAccessor().setType('SCALAR').setArray(new Uint32Array(indices)).setBuffer(buffer));
  console.log(`Updated ${name}: ${data.leaves} generated leaves`);
}
await io.write(output, doc);
