import * as THREE from "three";
import type { FoliageCards } from "../level/foliageCards";
import { CELLS } from "./mossFringe";

const originals = new WeakMap<THREE.Mesh, THREE.BufferGeometry>();
const signatures = new WeakMap<THREE.Mesh, string>();
export function disposeMossCardEdits(root: THREE.Object3D): void {
  for (const mesh of mossCards(root)) {
    const original = originals.get(mesh);
    if (original && mesh.geometry !== original) mesh.geometry.dispose();
    originals.delete(mesh); signatures.delete(mesh);
  }
}
export function mossCards(root: THREE.Object3D): THREE.Mesh[] {
  const meshes: THREE.Mesh[] = [];
  root.traverse(o => { if (o instanceof THREE.Mesh && typeof o.userData.mossPatch === "string") meshes.push(o); });
  return meshes;
}
/** Each mount owns its edited geometry; the decoded scene and other levels stay untouched. */
export function applyMossCardEdits(root: THREE.Object3D, edits: FoliageCards = {}): void {
  for (const mesh of mossCards(root)) {
    const patch = edits[mesh.userData.mossPatch] ?? {};
    const signature = JSON.stringify(patch);
    if (signatures.get(mesh) === signature) continue;
    signatures.set(mesh, signature);
    let source = originals.get(mesh);
    if (!source) { source = mesh.geometry; originals.set(mesh, source); }
    const previous = mesh.geometry;
    const geometry = source.clone();
    const pos = geometry.getAttribute("position"), uv = geometry.getAttribute("uv");
    const count = source.userData.mossFringeCards as number;
    const indices: number[] = [], faceCards: number[] = [];
    for (let card = 0; card < count; card++) {
      const edit = patch[String(card)];
      const base = card * 8;
      if (edit) {
        const p = (i: number) => new THREE.Vector3().fromBufferAttribute(source!.getAttribute("position"), base + i);
        const centre = p(2).add(p(3)).multiplyScalar(.5);
        const side = p(3).sub(p(2)).normalize();
        const up = p(6).add(p(7)).multiplyScalar(.5).sub(centre);
        up.addScaledVector(side, -up.dot(side)).normalize();
        const normal = side.clone().cross(up).normalize();
        const length = p(6).add(p(7)).multiplyScalar(.5).distanceTo(centre);
        for (let i = 0; i < 8; i++) {
          const v = p(i).sub(centre);
          v.addScaledVector(side, v.dot(side) * ((edit.width ?? 1) - 1));
          v.addScaledVector(up, v.dot(up) * ((edit.height ?? 1) - 1));
          v.applyAxisAngle(normal, edit.rotation ?? 0);
          v.addScaledVector(normal, (edit.curve ?? 0) * length * Math.max(0, (geometry.getAttribute("tuftHeight").getX(base + i) - .25) / .75) ** 2);
          v.add(centre).add(new THREE.Vector3(...(edit.offset ?? [0, 0, 0])));
          const offset = edit.points?.[i];
          if (offset) v.add(new THREE.Vector3(...offset));
          pos.setXYZ(base + i, v.x, v.y, v.z);
          if (edit.variant !== undefined) {
            const cell = CELLS[Math.max(0, Math.min(3, Math.round(edit.variant)))];
            const t = geometry.getAttribute("tuftHeight").getX(base + i);
            uv.setXY(base + i, cell[0] + (i % 2) * cell[2], cell[1] + t * cell[3]);
          }
        }
      }
      if (!edit?.hidden) for (let i = 0; i < 18; i++) {
        indices.push(source.index!.getX(card * 18 + i));
        if (i % 3 === 0) faceCards.push(card);
      }
    }
    geometry.setIndex(indices);
    geometry.userData.faceCards = faceCards;
    if (Object.keys(patch).length) {
      geometry.computeVertexNormals();
      // Recompute the sculpted card only; preserve the painted shading of every other tuft.
      const normal = geometry.getAttribute("normal"), original = source.getAttribute("normal");
      if (original) for (let card = 0; card < count; card++) {
        if (patch[String(card)] && !patch[String(card)].hidden) continue;
        for (let i = card * 8; i < card * 8 + 8; i++) normal.setXYZ(i, original.getX(i), original.getY(i), original.getZ(i));
      }
    }
    geometry.computeBoundingSphere(); geometry.computeBoundingBox();
    mesh.geometry = geometry;
    if (previous !== source) previous.dispose();
  }
}
