// Add Blender's artist-owned cards to the existing scene without changing its rocks or ivy.
import assert from 'node:assert/strict';
import { NodeIO, Node } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { copyToDocument, dedup, unpartition } from '@gltf-transform/functions';
import { MeshoptDecoder, MeshoptEncoder } from 'meshoptimizer';
import * as THREE from 'three';

const [input, cardsFile, output] = process.argv.slice(2);
assert.ok(input && cardsFile && output, 'usage: merge-moss-cards.mts scene.glb cards.glb output.glb');
await Promise.all([MeshoptDecoder.ready, MeshoptEncoder.ready]);
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
  'meshopt.decoder': MeshoptDecoder, 'meshopt.encoder': MeshoptEncoder,
});
const original = await io.read(input), cards = await io.read(cardsFile);
const nodes = cards.getRoot().listNodes().filter(n => n.getName().startsWith('MossCards__') && n.getMesh());
assert.ok(nodes.length > 0, 'Blender exported at least one packed moss patch');
const copies = copyToDocument(original, cards, nodes);
for (const node of nodes) {
  const hostName = node.getName().slice('MossCards__'.length);
  const host = original.getRoot().listNodes().find(n => n.getName() === hostName);
  assert.ok(host, `original scene has moss ${hostName}`);
  for (const child of [...host.listChildren()]) if (child.getName().startsWith('MossCards__')) child.dispose();
  const copy = copies.get(node) as Node;
  const local = new THREE.Matrix4().fromArray(host.getWorldMatrix()).invert()
    .multiply(new THREE.Matrix4().fromArray(node.getWorldMatrix()));
  copy.setMatrix(local.toArray()); host.addChild(copy);
  const mark = (n: Node): void => {
    for (const primitive of n.getMesh()?.listPrimitives() ?? []) {
      const material = primitive.getMaterial();
      if (material?.getName().endsWith('.moss')) material.setName(material.getName() + '.authored');
    }
    for (const child of n.listChildren()) if (!child.getName().startsWith('MossCards__')) mark(child);
  };
  mark(host);
  console.log(`Installed authored Blender cards on ${hostName}`);
}
await original.transform(dedup(), unpartition());
await io.write(output, original);
