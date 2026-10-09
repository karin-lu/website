import * as THREE from "three";

/** Enlarge the complete plant about its dark crown, including its stalks.
 * Quantized glTF positions must become floats before growing beyond [-1,1].
 * The optimizer can move the origin, so infer the crown from the solid atlas
 * cell and darkest support colour instead of scaling about the mesh origin. */
export function fullerBushGeometry(source: THREE.BufferGeometry, scale = 1.45): THREE.BufferGeometry {
  const position = source.getAttribute("position"), uv = source.getAttribute("uv"), colour = source.getAttribute("color");
  if (!position || source.userData.fullerBush) return source;
  const solid = new Map<string, number[]>();
  if (uv && colour) for (let i = 0; i < position.count; i++) {
    const key = `${uv.getX(i)},${uv.getY(i)}`;
    let ids = solid.get(key); if (!ids) solid.set(key, ids = []);
    ids.push(i);
  }
  const supports = [...solid.values()].sort((a, b) => b.length - a.length)[0] ?? [];
  const light = (i: number) => colour ? colour.getX(i) * .2126 + colour.getY(i) * .7152 + colour.getZ(i) * .0722 : 1;
  const darkest = supports.length ? Math.min(...supports.map(light)) : 0;
  const crown = supports.filter(i => light(i) <= darkest + .003);
  const pivot = new THREE.Vector3();
  for (const i of crown) pivot.add(new THREE.Vector3().fromBufferAttribute(position, i));
  if (crown.length) pivot.divideScalar(crown.length);
  const values: number[] = [], p = new THREE.Vector3();
  for (let i = 0; i < position.count; i++) {
    p.fromBufferAttribute(position, i).sub(pivot).multiplyScalar(scale).add(pivot);
    values.push(p.x, p.y, p.z);
  }
  const geometry = source.clone();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(values, 3));
  geometry.computeBoundingBox(); geometry.computeBoundingSphere();
  geometry.userData.fullerBush = true;
  return geometry;
}
