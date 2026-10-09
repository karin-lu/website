import * as THREE from "three";
import { VineSurface, rand } from "./ivySurface";

type Face = { normal: THREE.Vector3; centre: THREE.Vector3; corners: THREE.Vector3[];
  uvs: THREE.Vector2[]; shading?: THREE.Vector3[] };
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
  rock?: VineSurface, seed = 8107, sampleColour?: (uv: THREE.Vector2) => THREE.Color): THREE.BufferGeometry {
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
    const uv = source.getAttribute("uv"), shading = source.getAttribute("normal");
    const original = [0, 1, 2].map(j => index ? index.getX(i + j) : i + j);
    const face = { normal, centre: a.clone().add(b).add(c).multiplyScalar(1 / 3), corners: [a, b, c],
      uvs: original.map(j => uv ? new THREE.Vector2(uv.getX(j), uv.getY(j)) : new THREE.Vector2()),
      shading: shading ? original.map(j => new THREE.Vector3().fromBufferAttribute(shading, j)) : undefined };
    for (let j = 0; j < 3; j++) {
      const a = tri[j], b = tri[(j + 1) % 3], key = `${Math.min(a, b)},${Math.max(a, b)}`;
      let edge = edges.get(key);
      if (!edge) { edge = { a, b, faces: [] }; edges.set(key, edge); }
      edge.faces.push(face);
    }
  }
  const positions: number[] = [], normals: number[] = [], uvs: number[] = [], colours: number[] = [], triangles: number[] = [];
  const heights: number[] = [], soup: number[] = [];
  for (let i = 0; i < count; i++) points[ids[index ? index.getX(i) : i]].toArray(soup, soup.length);
  const mossSurface = soup.length ? new VineSurface(soup) : undefined;
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
    if (face.normal.z < -.15) continue;
    const a = points[edge.a], b = points[edge.b], length = a.distanceTo(b);
    const steps = Math.ceil(length / .045);
    for (let k = 0; k < steps && card < 1400; k++) {
      const t = (k + .22 + .55 * rand(seed, n * 101 + k, 1)) / steps;
      const p = a.clone().lerp(b, t);
      const inward = face.centre.clone().sub(p).normalize();
      // The dark base overlaps the mound instead of sitting above its outline.
      p.addScaledVector(inward, .012 + .012 * rand(seed, n * 101 + k, 9));
      const key = [p.x, p.y, p.z].map((v, j) => Math.round((v - points[0].getComponent(j)) / .025)).join(",");
      if (occupied.has(key)) continue;
      occupied.add(key);
      const r = rand(seed, n * 101 + k, 2);
      const width = .105 + r * .080, height = .060 + rand(seed, n * 101 + k, 3) * .060;
      // Spread along the rock's rim, with a slight upward lift. Face +z, the
      // side-scroller camera, rather than copying an edge-on ground card.
      const up = face.normal.clone().multiplyScalar(.7).addScaledVector(inward, boundary ? -.5 : 0);
      up.z = 0; up.y += boundary ? .10 : .28;
      if (up.lengthSq() < .05) up.set(0, 1, 0);
      up.normalize();
      up.applyAxisAngle(new THREE.Vector3(0, 0, 1), (rand(seed, n * 101 + k, 10) - .5) * .7);
      const right = new THREE.Vector3(up.y, -up.x, 0);
      const yaw = (rand(seed, n * 101 + k, 4) - .5) * .55;
      right.applyAxisAngle(up, yaw);
      const cell = CELLS[Math.floor(rand(seed, n * 101 + k, 5) * CELLS.length)];
      const base = positions.length / 3;
      const weights = new THREE.Triangle(...face.corners as [THREE.Vector3, THREE.Vector3, THREE.Vector3])
        .getBarycoord(p, new THREE.Vector3()) ?? new THREE.Vector3(1 / 3, 1 / 3, 1 / 3);
      weights.max(new THREE.Vector3()); weights.divideScalar(weights.x + weights.y + weights.z || 1);
      const mossUv = new THREE.Vector2();
      face.uvs.forEach((uv, j) => mossUv.addScaledVector(uv, weights.getComponent(j)));
      const tint = sampleColour?.(mossUv) ?? new THREE.Color("#526b2c");
      const normal = face.normal.clone().applyMatrix3(localNormals).normalize();
      if (face.shading) {
        normal.set(0, 0, 0);
        face.shading.forEach((n, j) => normal.addScaledVector(n, weights.getComponent(j)));
        normal.normalize();
      }
      const rows = [0, .25, .65, 1];
      for (let row = 0; row < rows.length; row++) for (let side = 0; side < 2; side++) {
        const v = rows[row], span = row === 0 ? .62 : row === 1 ? .85 : 1;
        const vertex = p.clone().addScaledVector(right, (side - .5) * width * span)
          .addScaledVector(up, height * (v - .30)).addScaledVector(face.normal, Math.sin(v * Math.PI) * .016);
        if (row < 2) {
          // Conform the whole foot to the cushion, hiding rectangular bases
          // even at corners where the two ends would otherwise hang in air.
          const foot = mossSurface?.nearest(vertex);
          if (foot) vertex.copy(foot.point).addScaledVector(foot.normal, row === 0 ? -.006 : .001);
        } else rock?.project(vertex, .004);
        vertex.applyMatrix4(inverse);
        positions.push(vertex.x, vertex.y, vertex.z); normals.push(normal.x, normal.y, normal.z);
        uvs.push(cell[0] + side * cell[2], cell[1] + v * cell[3]);
        heights.push(v);
        // The root matches its own patch; tips gently lighten from that colour.
        const shade = 1 + .06 * v * v;
        colours.push(tint.r * shade, tint.g * shade, tint.b * shade);
      }
      for (let row = 0; row < rows.length - 1; row++) {
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
  result.setAttribute("tuftHeight", new THREE.Float32BufferAttribute(heights, 1));
  result.setIndex(triangles); result.computeBoundingSphere(); result.computeBoundingBox();
  result.userData.mossFringeCards = card;
  return result;
}

/** Read the mound's actual painted colour, respecting its glTF UV transform. */
export function mossColourSampler(material: THREE.MeshStandardMaterial): ((uv: THREE.Vector2) => THREE.Color) | undefined {
  const texture = material.map;
  const image = texture?.image as (CanvasImageSource & { width: number; height: number }) | undefined;
  if (!texture || !image?.width || !image?.height) return;
  const canvas = document.createElement("canvas");
  canvas.width = image.width; canvas.height = image.height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return;
  ctx.drawImage(image, 0, 0);
  const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
  texture.updateMatrix();
  return uv => {
    const mapped = texture.transformUv(uv.clone());
    const x = THREE.MathUtils.clamp(Math.floor(mapped.x * canvas.width), 0, canvas.width - 1);
    const y = THREE.MathUtils.clamp(Math.floor(mapped.y * canvas.height), 0, canvas.height - 1);
    const at = (y * canvas.width + x) * 4;
    return new THREE.Color().setRGB(pixels[at] / 255, pixels[at + 1] / 255, pixels[at + 2] / 255,
      texture.colorSpace === THREE.SRGBColorSpace ? THREE.SRGBColorSpace : THREE.LinearSRGBColorSpace).multiply(material.color);
  };
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
    side: THREE.DoubleSide, alphaTest: .25, alphaToCoverage: true, roughness: 1, metalness: 0 });
  material.name = "Moss edge tufts";
  // The reference atlas has a dark grayscale base. Use its alpha/silhouette
  // and mild texture detail, keeping the sampled moss colour at the join.
  material.onBeforeCompile = shader => {
    shader.vertexShader = shader.vertexShader.replace("#include <common>", "#include <common>\nattribute float tuftHeight; varying float vTuftHeight;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvTuftHeight = tuftHeight;");
    shader.fragmentShader = shader.fragmentShader.replace("#include <common>", "#include <common>\nvarying float vTuftHeight;");
    shader.fragmentShader = shader.fragmentShader.replace("#include <map_fragment>", `
      #ifdef USE_MAP
        vec4 tuft = texture2D( map, vMapUv );
        diffuseColor *= vec4( vec3( mix( 0.98, 1.02, tuft.r ) ), tuft.a * smoothstep( 0.0, 0.22, vTuftHeight ) );
      #endif
    `);
  };
  material.customProgramCacheKey = () => "moss-rim-continuous-roots-v3";
  for (const mound of mounds) {
    const mats = Array.isArray(mound.material) ? mound.material : [mound.material];
    const mossMaterial = mats.find(m => /\.moss$/.test(m.name)) as THREE.MeshStandardMaterial;
    const geometry = buildMossFringe(mound.geometry, mound.matrixWorld, surfaceFor(mound), 8107, mossColourSampler(mossMaterial));
    if (!geometry.userData.mossFringeCards) { geometry.dispose(); continue; }
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = "Moss edge tufts";
    mesh.receiveShadow = true; mesh.castShadow = false;
    mound.add(mesh);
  }
}
