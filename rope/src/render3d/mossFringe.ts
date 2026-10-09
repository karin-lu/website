import * as THREE from "three";
import { VineSurface, rand } from "./ivySurface";

type Face = { normal: THREE.Vector3; centre: THREE.Vector3 };
type Edge = { a: number; b: number; faces: Face[] };
// Cropped, padded cells in the supplied tuft atlas; base first, V up.
const CELLS = [
  [.035, .520, .440, .295], [.507, .525, .477, .205],
  [.075, .029, .354, .374], [.520, .021, .460, .173],
] as const;

/** Small tufts at the open rim and camera-facing silhouette of a moss mound.
 * Weld by position: the printed mound has a separate UV chart per triangle.
 * Geometry is returned in the mound's local frame and rides its host rock. */
export function buildMossFringe(source: THREE.BufferGeometry, world: THREE.Matrix4,
  rock?: VineSurface, seed = 8107): THREE.BufferGeometry {
  const pos = source.getAttribute("position"), index = source.index;
  const result = new THREE.BufferGeometry();
  if (!pos) return result;
  const welded = new Map<string, number>(), points: THREE.Vector3[] = [], ids: number[] = [];
  for (let i = 0; i < pos.count; i++) {
    const p = new THREE.Vector3().fromBufferAttribute(pos, i).applyMatrix4(world);
    const key = [p.x, p.y, p.z].map(v => Math.round(v * 2000)).join(",");
    let id = welded.get(key);
    if (id === undefined) { id = points.length; points.push(p); welded.set(key, id); }
    ids.push(id);
  }
  const edges = new Map<string, Edge>();
  const count = index?.count ?? pos.count;
  for (let i = 0; i < count; i += 3) {
    const tri = [0, 1, 2].map(j => ids[index ? index.getX(i + j) : i + j]);
    const [a, b, c] = tri.map(id => points[id]);
    const normal = b.clone().sub(a).cross(c.clone().sub(a));
    if (normal.lengthSq() < 1e-12) continue;
    // Mirrored hosts still have outward surface normals.
    normal.normalize().multiplyScalar(Math.sign(world.determinant()));
    const face = { normal, centre: a.clone().add(b).add(c).multiplyScalar(1 / 3) };
    for (let j = 0; j < 3; j++) {
      const a = tri[j], b = tri[(j + 1) % 3], key = `${Math.min(a, b)},${Math.max(a, b)}`;
      let edge = edges.get(key);
      if (!edge) { edge = { a, b, faces: [] }; edges.set(key, edge); }
      edge.faces.push(face);
    }
  }
  const positions: number[] = [], normals: number[] = [], uvs: number[] = [], colours: number[] = [], triangles: number[] = [];
  const inverse = world.clone().invert(), localNormals = new THREE.Matrix3().getNormalMatrix(inverse);
  const occupied = new Set<string>();
  let card = 0, serial = 0;
  // Spread a capped budget around the whole patch instead of filling the
  // first portion of Blender's triangle ordering and leaving the rest bare.
  const scattered = [...edges.values()].sort((a, b) =>
    rand(seed, a.a * 331 + a.b, 17) - rand(seed, b.a * 331 + b.b, 17));
  for (const edge of scattered) {
    const n = serial++;
    const boundary = edge.faces.length === 1;
    const silhouette = edge.faces.some(f => f.normal.z > .12) && edge.faces.some(f => f.normal.z <= .12);
    if (!boundary && !silhouette) continue;
    const face = edge.faces.reduce((a, b) => a.normal.z > b.normal.z ? a : b);
    if (face.normal.z < -.15 || face.normal.y < -.65) continue;
    const a = points[edge.a], b = points[edge.b], length = a.distanceTo(b);
    const steps = Math.ceil(length / .065);
    for (let k = 0; k < steps && card < 600; k++) {
      if (rand(seed, n * 101 + k, 8) < .18) continue; // leave breathing gaps
      const t = (k + .22 + .55 * rand(seed, n * 101 + k, 1)) / steps;
      const p = a.clone().lerp(b, t);
      const inward = face.centre.clone().sub(p).normalize();
      // The dark base overlaps the mound instead of sitting above its outline.
      p.addScaledVector(inward, .016);
      rock?.project(p, .003);
      const key = [p.x, p.y, p.z].map((v, j) => Math.round((v - points[0].getComponent(j)) / .045)).join(",");
      if (occupied.has(key)) continue;
      occupied.add(key);
      const r = rand(seed, n * 101 + k, 2);
      const width = .070 + r * .065, height = .028 + rand(seed, n * 101 + k, 3) * .038;
      // Spread along the rock's rim, with a slight upward lift. Face +z, the
      // side-scroller camera, rather than copying an edge-on ground card.
      const up = face.normal.clone().multiplyScalar(.7).addScaledVector(inward, boundary ? -.5 : 0);
      up.z = 0; up.y += .28;
      if (up.lengthSq() < .05) up.set(0, 1, 0);
      up.normalize();
      const right = new THREE.Vector3(up.y, -up.x, 0);
      const yaw = (rand(seed, n * 101 + k, 4) - .5) * .55;
      right.applyAxisAngle(up, yaw);
      const normal = face.normal.clone().add(new THREE.Vector3(0, .45, .75)).normalize().applyMatrix3(localNormals).normalize();
      const cell = CELLS[Math.floor(rand(seed, n * 101 + k, 5) * CELLS.length)];
      const base = positions.length / 3;
      const tint = new THREE.Color("#526b2c").multiplyScalar(.87 + r * .25);
      for (let row = 0; row < 3; row++) for (let side = 0; side < 2; side++) {
        const v = row / 2, span = row === 0 ? .82 : 1;
        const vertex = p.clone().addScaledVector(right, (side - .5) * width * span)
          .addScaledVector(up, height * (v - .22)).addScaledVector(face.normal, .004 + Math.sin(v * Math.PI) * .012)
          .applyMatrix4(inverse);
        positions.push(vertex.x, vertex.y, vertex.z); normals.push(normal.x, normal.y, normal.z);
        uvs.push(cell[0] + side * cell[2], cell[1] + v * cell[3]);
        const shade = .68 + .32 * v;
        colours.push(tint.r * shade, tint.g * shade, tint.b * shade);
      }
      for (let row = 0; row < 2; row++) {
        const i = base + row * 2;
        triangles.push(i, i + 1, i + 3, i, i + 3, i + 2);
      }
      card++;
    }
  }
  result.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  result.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
  result.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  result.setAttribute("color", new THREE.Float32BufferAttribute(colours, 3));
  result.setIndex(triangles); result.computeBoundingSphere(); result.computeBoundingBox();
  result.userData.mossFringeCards = card;
  return result;
}

/** One shared cutout material and atlas for every rim in a loaded scene. */
export async function addMossFringes(root: THREE.Object3D, surfaceFor: (mesh: THREE.Mesh) => VineSurface | undefined): Promise<void> {
  const mounds: THREE.Mesh[] = [];
  root.traverse(o => {
    if (!(o instanceof THREE.Mesh)) return;
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    if (mats.some(m => /\.moss$/.test(m.name) && !m.transparent && m.alphaTest === 0)) mounds.push(o);
  });
  if (!mounds.length) return;
  const atlas = await new THREE.TextureLoader().loadAsync(new URL("./assets/moss-tuft-atlas.png", import.meta.url).href);
  atlas.colorSpace = THREE.SRGBColorSpace;
  const material = new THREE.MeshStandardMaterial({ map: atlas, vertexColors: true,
    side: THREE.DoubleSide, alphaTest: .35, alphaToCoverage: true, roughness: 1, metalness: 0 });
  material.name = "Moss edge tufts";
  for (const mound of mounds) {
    const geometry = buildMossFringe(mound.geometry, mound.matrixWorld, surfaceFor(mound));
    if (!geometry.userData.mossFringeCards) { geometry.dispose(); continue; }
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = "Moss edge tufts";
    mesh.receiveShadow = true; mesh.castShadow = false;
    mound.add(mesh);
  }
}
