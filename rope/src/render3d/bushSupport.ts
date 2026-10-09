import * as THREE from 'three';
import { rand } from './ivySurface';

type Site = { point: number[]; normal: number[]; uv: number[]; colour: number[] };

/** Overlapping, embedded green lobes beneath the leaf carpet. One mesh per
 * bush, with no new leaf cards and no change to the original foliage. */
export function buildBushSupport(leaves: THREE.BufferGeometry, world: THREE.Matrix4,
  sampleColour?: (uv: THREE.Vector2) => THREE.Color): THREE.BufferGeometry {
  const sites = (leaves.userData.ivySupportSites ?? []) as Site[];
  const cells = new Map<string, Site>();
  for (const site of sites) {
    const key = site.point.map(v => Math.floor(v / .12)).join(',');
    if (!cells.has(key)) cells.set(key, site);
  }
  const sphere = new THREE.SphereGeometry(1, 16, 10);
  const vertices = sphere.getAttribute('position'), indices = sphere.index!;
  const inverse = world.clone().invert(), localNormal = new THREE.Matrix3().getNormalMatrix(inverse);
  const positions: number[] = [], normals: number[] = [], colours: number[] = [], faces: number[] = [];
  let lobe = 0;
  for (const site of cells.values()) {
    const n = new THREE.Vector3().fromArray(site.normal).normalize();
    const right = new THREE.Vector3(0, 1, 0).cross(n);
    if (right.lengthSq() < .01) right.set(1, 0, 0);
    right.normalize();
    const up = n.clone().cross(right).normalize();
    // Most of the cushion sits inside the host; its rounded cap fills the
    // spaces beneath blades without forming a separate floating blob.
    const centre = new THREE.Vector3().fromArray(site.point).addScaledVector(n, -.025);
    const width = .155 + .020 * rand(6203, lobe, 1), height = .140 + .018 * rand(6203, lobe, 2);
    const depth = .082 + .012 * rand(6203, lobe, 3);
    const tint = sampleColour?.(new THREE.Vector2().fromArray(site.uv)) ?? new THREE.Color('#4d742c');
    tint.multiply(new THREE.Color().fromArray(site.colour)).multiplyScalar(.88);
    const offset = positions.length / 3;
    for (let i = 0; i < vertices.count; i++) {
      const v = new THREE.Vector3().fromBufferAttribute(vertices, i);
      const irregular = 1 + .018 * Math.sin(v.x * 5 + lobe * .7) * Math.sin(v.y * 4);
      const p = centre.clone().addScaledVector(right, v.x * width * irregular)
        .addScaledVector(up, v.y * height * irregular).addScaledVector(n, v.z * depth * irregular).applyMatrix4(inverse);
      const normal = right.clone().multiplyScalar(v.x / width).addScaledVector(up, v.y / height)
        .addScaledVector(n, v.z / depth).applyMatrix3(localNormal).normalize();
      positions.push(p.x, p.y, p.z); normals.push(normal.x, normal.y, normal.z);
      const shade = .96 + .04 * Math.max(0, v.z);
      colours.push(tint.r * shade, tint.g * shade, tint.b * shade);
    }
    const mirrored = world.determinant() < 0;
    for (let i = 0; i < indices.count; i += 3) {
      faces.push(offset + indices.getX(i), offset + indices.getX(i + (mirrored ? 2 : 1)), offset + indices.getX(i + (mirrored ? 1 : 2)));
    }
    lobe++;
  }
  sphere.dispose();
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colours, 3));
  geometry.setIndex(faces); geometry.computeBoundingBox(); geometry.computeBoundingSphere();
  geometry.userData.bushSupportLobes = lobe;
  return geometry;
}
