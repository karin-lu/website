import * as THREE from "three";
import { VineSurface, rand } from "./ivySurface";

/** Bend the Blender atlas cards, retaining their UVs and painted colours.
 * glTF flips Blender's V coordinate: the stalk is at the high-V end.
 * Connected rock underlays, constant-UV stems and segmented hanging strands
 * are retained. Only isolated, rectangular two-triangle cards are rebuilt. */
export function curveIvyGeometry(source: THREE.BufferGeometry, world: THREE.Matrix4, rock?: VineSurface, fuzzyAtlas=false): THREE.BufferGeometry {
  if (source.userData.curvedIvy) return source;
  const position = source.getAttribute("position"), uv = source.getAttribute("uv");
  if (!position || !uv || !source.index) return source;
  const index = source.index, parent = new Int32Array(position.count);
  for (let i = 0; i < parent.length; i++) parent[i] = i;
  const find = (i: number): number => { while (parent[i] !== i) { parent[i] = parent[parent[i]!]!; i = parent[i]!; } return i; };
  for (let i = 0; i < index.count; i += 3) {
    const a = find(index.getX(i)); parent[find(index.getX(i + 1))] = a; parent[find(index.getX(i + 2))] = a;
  }
  const components = new Map<number, number[]>();
  for (let i = 0; i < position.count; i++) {
    const root = find(i); let list = components.get(root);
    if (!list) components.set(root, list = []); list.push(i);
  }
  const inverse = world.clone().invert(), normalMatrix = new THREE.Matrix3().getNormalMatrix(world);
  const values: Record<string, number[]> = {};
  for (const key of Object.keys(source.attributes)) values[key] = [];
  const triangles: number[] = [], replaced = new Set<number>();
  let count = 0, leafCards = 0, companionLeaves = 0;
  const outerFans = new Set<string>();
  const fanRoots: THREE.Vector3[] = [];
  const supportSites: { point: number[]; normal: number[]; uv: number[]; colour: number[] }[] = [];
  const get = (id: number) => new THREE.Vector3().fromBufferAttribute(position, id).applyMatrix4(world);
  for (const ids of components.values()) {
    if (ids.length !== 4) continue;
    const us = ids.map(i => uv.getX(i)), vs = ids.map(i => uv.getY(i));
    const loU = Math.min(...us), hiU = Math.max(...us), loV = Math.min(...vs), hiV = Math.max(...vs);
    const du = hiU - loU, dv = hiV - loV;
    if (du < .02 || dv < .02 || dv / du > 1.6 || du / dv > 1.6) continue;
    // Quantized exports need a tolerance at their UV corners.
    const corner = (u: number, v: number) => ids.find(i => Math.abs(uv.getX(i) - u) < .0002 && Math.abs(uv.getY(i) - v) < .0002);
    const corners = [corner(loU, hiV), corner(hiU, hiV), corner(loU, loV), corner(hiU, loV)];
    if (corners.some(i => i === undefined) || new Set(corners).size !== 4) continue;
    const [a, b, c, d] = corners as number[];
    const points = [get(a!), get(b!), get(c!), get(d!)];
    const bottom = points[0]!.clone().lerp(points[1]!, .5), top = points[2]!.clone().lerp(points[3]!, .5);
    const height = bottom.distanceTo(top), width = points[0]!.distanceTo(points[1]!);
    if (height < .005 || height > 1.5) continue;
    const n = source.getAttribute("normal");
    const normal = n ? new THREE.Vector3().fromBufferAttribute(n, a!).applyMatrix3(normalMatrix).normalize()
      : points[1]!.clone().sub(points[0]!).cross(top.clone().sub(bottom)).normalize();
    const base = du > .195 ? .16 : .09;
    const anchor = bottom.clone().lerp(top, base), pull = new THREE.Vector3();
    const hit = rock?.nearest(anchor, Math.max(.4, height * 1.2));
    if (hit) {
      // The stalk is the attachment, not the centre of the transparent card.
      // A capped pull left the upper carpet sheets suspended above their host.
      const target = hit.point.clone().addScaledVector(hit.normal, .002);
      pull.subVectors(target, anchor);
    }
    const curl = .09 + .07 * rand(2401, a!, 1), fold = .07 + .06 * rand(2401, a!, 2);
    const outward = (hit?.normal ?? normal).clone();
    const seated = anchor.clone().add(pull);
    const colour = source.getAttribute('color');
    supportSites.push({ point: seated.toArray(), normal: outward.toArray(), uv: [(loU + hiU) / 2, hiV - dv * .55],
      colour: [0, 1, 2].map(k => colour ? corners.reduce<number>((sum, id) => sum + colour.getComponent(id!, k), 0) / 4 : 1) });
    const cell = [seated.x, seated.y, seated.z].map(v => Math.floor(v / .18));
    const fanKey = cell.join(',');
    // A compact original carpet fills the rock. Only well-spaced locations
    // facing the silhouette get an outer blade; never duplicate every root.
    const fan = components.size > 16 && Math.hypot(outward.x, outward.y) > .35 && !outerFans.has(fanKey)
      && fanRoots.every(root => root.distanceToSquared(seated) >= .14 * .14);
    if (fan) { outerFans.add(fanKey); fanRoots.push(seated); }
    const copies = fan ? 2 : 1;
    leafCards += copies; companionLeaves += copies - 1;
    const rows = [0, base, .4, .7, 1];
    const geometric = points[1]!.clone().sub(points[0]!).cross(top.clone().sub(bottom));
    const reverse = geometric.dot(normal) * Math.sign(world.determinant()) < 0;
    for (let copy = 0; copy < copies; copy++) {
      const offset = count;
      const turn = (rand(3197, a!, 5) - .5) * (copy ? .65 : .25);
      const size = copy ? Math.min(2.4, Math.max(1.65 + .3 * rand(3197, a!, 6), .11 / height))
        : 1.25 + .20 * rand(3197, a!, 6);
      const shoot = top.clone().sub(bottom).normalize().applyAxisAngle(normal, turn);
      // Grow away from the host, with some inherited stem direction and a
      // gentle upward bias. Each layer opens at a different angle and reach.
      shoot.addScaledVector(outward, .65).normalize();
      const reach = copy ? .035 + .030 * rand(3197, a!, 11) : .008;
      // Neighbouring leaves share a restrained tint; the exposed layer is
      // lighter as a whole rather than randomly mottled throughout the bush.
      const cluster = cell[0]! * 7387 + cell[1]! * 1933 + cell[2]! * 967;
      const colourVariation = rand(3197, cluster, 21);
      const rootShade = .91 + .04 * colourVariation;
      const tipShade = copy ? 1.13 + .07 * colourVariation : 1.01 + .03 * colourVariation;
      const warmth = (rand(3197, cluster, 31) - .5) * .04;
      // Mix the existing painted, ragged-edged atlas silhouettes into the
      // visible layer, preserving solid UVs used by the stems/underlay.
      const fuzzy = fuzzyAtlas || (components.size > 16 && du < .195);
      const fuzzyCell = Math.floor(rand(6203, a!, 8 + copy) * 15);
      const fuzzyU = (fuzzyCell % 4) * .25 + .03;
      const fuzzyV = Math.floor(fuzzyCell / 4) * .25 + .03;
      for (const s of rows) for (const u of [0, .5, 1]) {
        const weights = [(1 - u) * (1 - s), u * (1 - s), (1 - u) * s, u * s];
        const p = new THREE.Vector3(); points.forEach((point, k) => p.addScaledVector(point, weights[k]!));
        // Grow from the seated stalk, so a larger leaf cannot lift its root.
        p.sub(anchor).multiplyScalar(size).applyAxisAngle(normal, turn).add(anchor);
        const t = Math.max(0, (s - base) / (1 - base));
        p.add(pull).addScaledVector(normal, height * ((copy ? .18 : .10) * Math.sin(Math.PI * t) - .2 * curl * t * t)
          + width * fold * (2 * u - 1) ** 2 * Math.sin(Math.PI * t)
          + (copy ? .025 : .009) * Math.sin(Math.PI * t));
        p.addScaledVector(shoot, reach * t * t * (3 - 2 * t));
        // Seat the blade over the larger cushion while its stalk stays buried.
        p.addScaledVector(outward, .065 * Math.sin(t * Math.PI / 2));
        if (copy) p.y -= .025 * t * t * t;
        // The same surface projection used by vines prevents curling into stone.
        rock?.project(p, s <= base ? .002 : .005);
        p.applyMatrix4(inverse);
        for (const [name, output] of Object.entries(values)) {
          const attr = source.getAttribute(name);
          for (let k = 0; k < attr.itemSize; k++) {
            if (name === "position") output.push(p.getComponent(k));
            else {
              const value = corners.reduce<number>((sum, id, j) => sum + attr.getComponent(id!, k) * weights[j]!, 0);
              if (name === 'uv' && fuzzy) {
                output.push(k === 0 ? fuzzyU + u * .19 : fuzzyV + (1 - s) * .19);
              } else if (name === "color" && k < 3) {
                const outer = t * t * (3 - 2 * t);
                const shade = THREE.MathUtils.lerp(rootShade, tipShade, outer);
                const hue = k === 0 ? 1 + warmth : k === 2 ? 1 - warmth : 1;
                output.push(THREE.MathUtils.clamp(value * shade * hue, 0, 1));
              } else output.push(value);
            }
          }
        }
        count++;
      }
      for (let r = 0; r < rows.length - 1; r++) for (let col = 0; col < 2; col++) {
        const i = offset + r * 3 + col;
        const face = [i, i + 1, i + 4, i, i + 4, i + 3];
        if (reverse) for (let j = 0; j < face.length; j += 3) [face[j + 1], face[j + 2]] = [face[j + 2]!, face[j + 1]!];
        triangles.push(...face);
      }
    }
    ids.forEach(i => replaced.add(i));
  }
  if (!replaced.size) return source;
  const preserved = new Map<number, number>();
  for (let i = 0; i < index.count; i++) {
    const id = index.getX(i); if (replaced.has(id)) continue;
    let at = preserved.get(id);
    if (at === undefined) {
      at = count++; preserved.set(id, at);
      for (const [name, output] of Object.entries(values)) {
        const attr = source.getAttribute(name);
        for (let k = 0; k < attr.itemSize; k++) output.push(attr.getComponent(id, k));
      }
    }
    triangles.push(at);
  }
  const geometry = new THREE.BufferGeometry();
  for (const [name, output] of Object.entries(values)) geometry.setAttribute(name, new THREE.Float32BufferAttribute(output, source.getAttribute(name).itemSize));
  geometry.setIndex(triangles); geometry.computeVertexNormals(); geometry.computeBoundingBox(); geometry.computeBoundingSphere();
  geometry.userData.curvedIvy = true;
  geometry.userData.ivyLeafCards = leafCards;
  geometry.userData.rockBushCompanionLeaves = companionLeaves;
  geometry.userData.rockBushFanRoots = fanRoots.map(root => root.toArray());
  geometry.userData.ivySupportSites = supportSites;
  return geometry;
}

/** Read the nearest opaque host into the vine generator's surface structure. */
export function ivyHostSurface(mesh: THREE.Mesh): VineSurface | undefined {
  let host = mesh.parent;
  const ivyName = (o: THREE.Object3D) => /\.(ivy|moss)(\.shadow)?$/.test(String(o.userData.name ?? o.name));
  // Quantisation and multi-material exports insert unnamed groups between
  // the primitive mesh and its named ivy object. Find that object first.
  for (let ancestor = mesh.parent; ancestor; ancestor = ancestor.parent) {
    if (ivyName(ancestor)) { host = ancestor; break; }
  }
  while (host && ivyName(host)) host = host.parent;
  if (!host) return;
  const soup: number[] = [];
  host.traverse(node => {
    if (!(node instanceof THREE.Mesh) || node === mesh) return;
    const mats = Array.isArray(node.material) ? node.material : [node.material];
    if (mats.some(m => m.alphaTest > 0 || m.transparent)) return;
    const attr = node.geometry.getAttribute("position"), index = node.geometry.index;
    if (!attr) return;
    const winding = node.matrixWorld.determinant() < 0 ? [0, 2, 1] : [0, 1, 2];
    const p = new THREE.Vector3();
    for (let i = 0; i < (index?.count ?? attr.count); i += 3) for (const j of winding) {
      p.fromBufferAttribute(attr, index ? index.getX(i + j) : i + j).applyMatrix4(node.matrixWorld);
      soup.push(p.x, p.y, p.z);
    }
  });
  return soup.length ? new VineSurface(new Float32Array(soup)) : undefined;
}
