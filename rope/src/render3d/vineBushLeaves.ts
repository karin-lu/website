import * as THREE from "three";
import library from "../../tools/blender/foliage/pieces/leaves.json";
import { rand, VineSurface } from "./ivySurface";

const leaves = library.leaves.filter(p => p.id.startsWith("paint-"));

/** Broad painted vine leaves on the bush's existing stalks, sharing its atlas.
 * All growth starts on solid-cell support vertices, never in empty space. */
export function buildVineBushLeaves(source: THREE.BufferGeometry, world: THREE.Matrix4,
  rock?: VineSurface): THREE.BufferGeometry {
  const pos = source.getAttribute("position"), uv = source.getAttribute("uv");
  const result = new THREE.BufferGeometry();
  if (!pos || !uv) return result;
  const cells = new Map<string, number[]>();
  for (let i = 0; i < pos.count; i++) {
    const key = `${uv.getX(i)},${uv.getY(i)}`;
    let ids = cells.get(key); if (!ids) cells.set(key, ids = []); ids.push(i);
  }
  const supports = [...cells.values()].sort((a, b) => b.length - a.length)[0] ?? [];
  if (supports.length < 12) return result;
  const box = new THREE.Box3(), support: THREE.Vector3[] = [];
  for (const id of supports) {
    const p = new THREE.Vector3().fromBufferAttribute(pos, id).applyMatrix4(world);
    support.push(p); box.expandByPoint(p);
  }
  const size = THREE.MathUtils.clamp(box.getSize(new THREE.Vector3()).length(), .7, 1.2);
  const solidUv = new THREE.Vector2(uv.getX(supports[0]), uv.getY(supports[0]));
  const inverse = world.clone().invert(), normalMatrix = new THREE.Matrix3().getNormalMatrix(inverse);
  const positions: number[] = [], normals: number[] = [], colours: number[] = [], uvs: number[] = [], indices: number[] = [];
  const used: THREE.Vector3[] = [];
  const write = (p: THREE.Vector3, n: THREE.Vector3, u: number, v: number, colour: THREE.Color) => {
    p.applyMatrix4(inverse); n.applyMatrix3(normalMatrix).normalize();
    positions.push(p.x, p.y, p.z); normals.push(n.x, n.y, n.z);
    uvs.push(u, v); colours.push(colour.r, colour.g, colour.b);
  };
  for (let attempt = 0; attempt < 240 && used.length < 32; attempt++) {
    const anchor = support[Math.floor(rand(5191, attempt, 1) * support.length)].clone();
    if (used.some(p => p.distanceToSquared(anchor) < (size * .025) ** 2)) continue;
    used.push(anchor.clone());
    const side = rand(5191, attempt, 2) > .5 ? 1 : -1;
    const along = new THREE.Vector3(side * (.55 + .35 * rand(5191, attempt, 3)),
      .25 + .55 * rand(5191, attempt, 4), .12).normalize();
    const across = new THREE.Vector3(along.y, -along.x, 0).normalize();
    const face = new THREE.Vector3(0, .25, 1).normalize();
    const base = anchor.clone().addScaledVector(along, size * .035);
    const piece = leaves[Math.floor(rand(5191, attempt, 5) * leaves.length)];
    const length = size * (.17 + .10 * rand(5191, attempt, 6)), width = length * piece.geometryAspect;
    const shade = new THREE.Color(["#4e7132", "#5b7b35", "#42652c"][attempt % 3]);
    const paint = new THREE.Color(piece.avgColour);
    const tint = new THREE.Color(shade.r / paint.r, shade.g / paint.g, shade.b / paint.b);
    let offset = positions.length / 3;
    // A short petiole connects the painted stalk to its parent branch.
    const brown = new THREE.Color("#536039");
    for (let ring = 0; ring < 2; ring++) for (let j = 0; j < 6; j++) {
      const angle = j * Math.PI / 3, n = across.clone().multiplyScalar(Math.cos(angle)).addScaledVector(face, Math.sin(angle));
      write((ring ? base : anchor).clone().addScaledVector(n, size * .004), n.clone(), solidUv.x, solidUv.y, brown);
    }
    for (let j = 0; j < 6; j++) {
      const next = (j + 1) % 6;
      indices.push(offset + j, offset + next, offset + 6 + next, offset + j, offset + 6 + next, offset + 6 + j);
    }
    offset = positions.length / 3;
    for (let row = 0; row < 5; row++) for (let col = 0; col < 3; col++) {
      const v = row / 4, u = col / 2, t = Math.max(0, (v - piece.baseUv[1]) / (1 - piece.baseUv[1]));
      const p = base.clone().addScaledVector(along, (v - piece.baseUv[1]) * length)
        .addScaledVector(across, (u - piece.baseUv[0]) * width)
        .addScaledVector(face, length * (.12 * Math.sin(t * Math.PI) - .05 * t * t));
      // Clearance preserves the connection: the basal strip remains on its stalk.
      if (v > .25) rock?.project(p, .006);
      const n = face.clone().addScaledVector(across, (u - .5) * .35).addScaledVector(along, .25);
      const [ru, rv, rw, rh] = piece.atlasRect;
      write(p, n, (ru + u * rw) * .5, 1 - (534 + (rv + v * rh) * 1193.5) / 1728,
        tint.clone().multiplyScalar(.88 + .12 * t));
    }
    for (let row = 0; row < 4; row++) for (let col = 0; col < 2; col++) {
      const i = offset + row * 3 + col;
      indices.push(i, i + 1, i + 4, i, i + 4, i + 3);
    }
  }
  result.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  result.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
  result.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  result.setAttribute("color", new THREE.Float32BufferAttribute(colours, 3));
  result.setIndex(indices); result.computeBoundingBox(); result.computeBoundingSphere();
  result.userData.vineBushLeaves = used.length;
  return result;
}
