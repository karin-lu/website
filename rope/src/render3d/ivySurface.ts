import * as THREE from "three";

type Face = { triangle: THREE.Triangle; normal: THREE.Vector3; box: THREE.Box3; centre: THREE.Vector3 };
type Node = { box: THREE.Box3; left?: Node; right?: Node; faces?: Face[] };
type Contact = { point: THREE.Vector3; normal: THREE.Vector3; distance: number; signed: number };
/** Small static BVH shared by path generation and foliage clearance. */
export class VineSurface {
  private root: Node;
  constructor(positions: Float32Array | number[]) {
    if (positions.length < 9 || positions.length % 9 || positions.length > 900_000 ||
        Array.from(positions).some(n => !Number.isFinite(n))) throw new Error("The rock surface is invalid or too large.");
    const faces: Face[] = [];
    for (let i = 0; i < positions.length; i += 9) {
      const triangle = new THREE.Triangle(new THREE.Vector3().fromArray(positions, i),
        new THREE.Vector3().fromArray(positions, i + 3), new THREE.Vector3().fromArray(positions, i + 6));
      if (triangle.getArea() < 1e-12) continue;
      faces.push({ triangle, normal: triangle.getNormal(new THREE.Vector3()),
        box: new THREE.Box3().setFromPoints([triangle.a, triangle.b, triangle.c]),
        centre: triangle.getMidpoint(new THREE.Vector3()) });
    }
    if (!faces.length) throw new Error("The selected rock has no usable faces.");
    const build = (items: Face[]): Node => {
      const box = new THREE.Box3(); items.forEach(f => box.union(f.box));
      if (items.length <= 10) return { box, faces: items };
      const size = box.getSize(new THREE.Vector3());
      const axis = size.x >= size.y && size.x >= size.z ? "x" : size.y >= size.z ? "y" : "z";
      items.sort((a, b) => a.centre[axis] - b.centre[axis]);
      const mid = items.length >> 1;
      return { box, left: build(items.slice(0, mid)), right: build(items.slice(mid)) };
    };
    this.root = build(faces);
  }
  nearest(p: THREE.Vector3, max = Infinity): Contact | null {
    let best = max, found: Face | null = null;
    const nearest = new THREE.Vector3(), temp = new THREE.Vector3();
    const visit = (node: Node): void => {
      if (node.box.distanceToPoint(p) > best) return;
      if (node.faces) {
        for (const face of node.faces) {
          face.triangle.closestPointToPoint(p, temp);
          const distance = p.distanceTo(temp);
          if (distance < best) { best = distance; found = face; nearest.copy(temp); }
        }
      } else {
        const a = node.left!, b = node.right!;
        if (a.box.distanceToPoint(p) < b.box.distanceToPoint(p)) { visit(a); visit(b); }
        else { visit(b); visit(a); }
      }
    };
    visit(this.root);
    if (!found) return null;
    const face = found as Face;
    const delta = p.clone().sub(nearest);
    const side = delta.dot(face.normal);
    // At convex corners use the separating vector; flat faces keep their normal.
    const normal = side >= 0 && best > 1e-8 ? delta.clone().divideScalar(best) : face.normal.clone();
    return { point: nearest, normal, distance: best, signed: side < -1e-7 ? -best : best };
  }
  project(p: THREE.Vector3, clearance: number): THREE.Vector3 {
    for (let k = 0; k < 4; k++) {
      const hit = this.nearest(p);
      if (!hit || hit.signed >= clearance - 1e-7) break;
      p.copy(hit.point).addScaledVector(hit.normal, clearance);
    }
    return p;
  }
  clear(a: THREE.Vector3, b: THREE.Vector3, clearance: number): boolean {
    const count = Math.max(2, Math.ceil(a.distanceTo(b) / Math.max(clearance * 1.5, 0.008)));
    const p = new THREE.Vector3();
    for (let i = 0; i <= count; i++) {
      p.lerpVectors(a, b, i / count);
      const contact = this.nearest(p, clearance * 3);
      if (contact && contact.signed < clearance * 0.82) return false;
    }
    return true;
  }
}

export const rand = (seed: number, i: number, salt = 0): number => {
  let n = (seed ^ Math.imul(i + 1, 374761393) ^ Math.imul(salt + 1, 668265263)) >>> 0;
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
};
