// A continuous woody surface at forks. Smooth-union the branch sweeps on a
// sparse grid, retaining a separate draw/picking mesh for each authored object.
// Only branched bodies pay for this; single roots use the direct ring mesh.
import * as THREE from "three";
import { edgeTable, triTable } from "three/addons/objects/MarchingCubes.js";

interface Segment {
  branch: number;
  a: THREE.Vector3;
  b: THREE.Vector3;
  radiiA: number[];
  radiiB: number[];
  s: number;
  endV: number;
  length: number;
}
interface Sample { d: number; branch: number; u: number; v: number; age: number; join: number }
interface Vertex { p: THREE.Vector3; n: THREE.Vector3; sample: Sample }

export function fuseRootForks(inputs: Map<number, THREE.BufferGeometry>, parents: ReadonlyMap<number, number> = new Map()): Map<number, THREE.BufferGeometry> {
  if (inputs.size < 2) return inputs;
  const sides = 40, stride = sides + 1;
  const segments: Segment[] = [];
  interface Ring { c: THREE.Vector3; radii: number[]; s: number }
  const branches = new Map<number, Ring[]>();
  const junctions = new Map<number, { parent: number; base: THREE.Vector3; side: THREE.Vector3; radius: number }>();
  const bounds = new THREE.Box3();
  let girth = Infinity;
  for (const [branch, geometry] of inputs) {
    const pos = geometry.getAttribute("position");
    const uv = geometry.getAttribute("uv");
    const rings: Ring[] = [];
    branches.set(branch, rings);
    let previous: Ring | undefined;
    for (let i = 0; i < pos.count; i += stride) {
      const c = new THREE.Vector3();
      for (let k = 0; k < sides; k++) c.add(new THREE.Vector3().fromBufferAttribute(pos, i + k));
      c.multiplyScalar(1 / sides);
      const radii = Array.from({ length: sides }, (_, k) => new THREE.Vector3().fromBufferAttribute(pos, i + k).distanceTo(c));
      const s = uv.getY(i);
      if (previous) {
        const length = c.distanceTo(previous.c);
        if (length > 1e-6) segments.push({ branch, a: previous.c, b: c, radiiA: previous.radii, radiiB: radii, s: previous.s, endV: s, length });
      }
      previous = { c, radii, s };
      rings.push(previous);
    }
    geometry.computeBoundingBox();
    bounds.union(geometry.boundingBox!);
    girth = Math.min(girth, geometry.boundingBox!.max.z - geometry.boundingBox!.min.z);
  }
  if (!segments.length) return inputs;
  // Register grain at the actual junction, parent first. Random UV offsets
  // belong to trunks; a lateral inherits the parent's phase instead of looking
  // like a separately wrapped stick. The end of the lateral stays authored.
  const ready = new Set<number>(), visiting = new Set<number>();
  const prepare = (child: number): void => {
    if (ready.has(child) || visiting.has(child)) return;
    visiting.add(child);
    const parent = parents.get(child), rings = branches.get(child);
    if (parent !== undefined && parent !== child && branches.has(parent) && rings && rings.length > 6) {
      prepare(parent);
      const base = rings[5]!; // five base-cap rings precede the first path ring
      const direction = rings[6]!.c.clone().sub(base.c).normalize();
      let nearest: Segment | undefined, station = 0, distance = Infinity;
      for (const seg of segments) if (seg.branch === parent) {
        const delta = seg.b.clone().sub(seg.a);
        const t = THREE.MathUtils.clamp(base.c.clone().sub(seg.a).dot(delta) / delta.lengthSq(), 0, 1);
        const d = seg.a.clone().addScaledVector(delta, t).distanceToSquared(base.c);
        if (d < distance) { nearest = seg; station = t; distance = d; }
      }
      if (nearest) {
        const tangent = nearest.b.clone().sub(nearest.a).normalize();
        const sign = tangent.dot(direction) < 0 ? -1 : 1;
        const attach = nearest.a.clone().lerp(nearest.b, station);
        const radius = Math.max(0.0025, ...base.radii);
        const parentV = THREE.MathUtils.lerp(nearest.s, nearest.endV, station);
        const baseV = base.s, oldBase = base.c.clone();
        const parentRadius = Math.max(...nearest.radiiA);
        const reach = radius * 4 + parentRadius;
        const side = direction.clone().addScaledVector(tangent, -direction.dot(tangent)).normalize();
        junctions.set(child, { parent, base: attach, side, radius });
        const total = Math.max(0.001, (rings[rings.length - 6]!.s - baseV) * 0.65);
        for (const ring of rings) {
          const s = Math.max(0, (ring.s - baseV) * 0.65);
          const fade = Math.exp(-s / reach) * Math.pow(Math.max(0, 1 - s / total), 2);
          ring.c.addScaledVector(attach.clone().sub(oldBase), fade)
            .addScaledVector(tangent.clone().multiplyScalar(sign).sub(direction), s * fade);
        }
        for (const seg of segments) if (seg.branch === child) {
          seg.s = parentV + (seg.s - baseV) * sign;
          seg.endV = parentV + (seg.endV - baseV) * sign;
          seg.length = seg.a.distanceTo(seg.b);
        }
      }
    }
    visiting.delete(child); ready.add(child);
  };
  for (const child of inputs.keys()) prepare(child);
  // Include the longer shoulders in the sparse grid's bounds.
  for (const seg of segments) {
    const r = Math.max(...seg.radiiA, ...seg.radiiB) * 2;
    bounds.expandByPoint(seg.a.clone().addScalar(r));
    bounds.expandByPoint(seg.a.clone().addScalar(-r));
  }
  const step = THREE.MathUtils.clamp(girth / 6, 0.006, 0.011);
  bounds.expandByScalar(step * 4);
  const origin = bounds.min;
  const nx = Math.ceil((bounds.max.x - origin.x) / step) + 2;
  const ny = Math.ceil((bounds.max.y - origin.y) / step) + 2;
  const key = (x: number, y: number, z: number): number => x + nx * (y + ny * z);
  const decode = (id: number): THREE.Vector3 => {
    const x = id % nx, yz = Math.floor(id / nx), y = yz % ny, z = Math.floor(yz / ny);
    return new THREE.Vector3(origin.x + x * step, origin.y + y * step, origin.z + z * step);
  };
  // XY bins are enough: every centreline lies in the gameplay plane. They
  // keep a long root from testing every segment at every voxel.
  const binSize = 0.16;
  const bins = new Map<string, Segment[]>();
  const cells = new Set<number>();
  for (const segment of segments) {
    const r = Math.max(...segment.radiiA, ...segment.radiiB) * 2 + step * 2;
    const lo = segment.a.clone().min(segment.b).addScalar(-r);
    const hi = segment.a.clone().max(segment.b).addScalar(r);
    for (let y = Math.floor(lo.y / binSize); y <= Math.floor(hi.y / binSize); y++) {
      for (let x = Math.floor(lo.x / binSize); x <= Math.floor(hi.x / binSize); x++) {
        const id = `${x},${y}`;
        const list = bins.get(id) ?? []; list.push(segment); bins.set(id, list);
      }
    }
    const low = lo.sub(origin).divideScalar(step).floor();
    const high = hi.sub(origin).divideScalar(step).ceil();
    // Only a narrow neighbourhood of the sweeps, not the body's empty box.
    for (let z = Math.max(0, low.z); z < high.z; z++) for (let y = Math.max(0, low.y); y < Math.min(ny - 1, high.y); y++) {
      for (let x = Math.max(0, low.x); x < Math.min(nx - 1, high.x); x++) cells.add(key(x, y, z));
    }
  }
  const sample = (p: THREE.Vector3): Sample => {
    const candidates = bins.get(`${Math.floor(p.x / binSize)},${Math.floor(p.y / binSize)}`) ?? [];
    const byBranch = new Map<number, Sample>();
    for (const seg of candidates) {
      const dx = seg.b.x - seg.a.x, dy = seg.b.y - seg.a.y;
      const t = THREE.MathUtils.clamp(((p.x - seg.a.x) * dx + (p.y - seg.a.y) * dy) / (seg.length * seg.length), 0, 1);
      const rx = p.x - seg.a.x - t * dx, ry = p.y - seg.a.y - t * dy;
      // Tube frame: its in-plane axis is (dy,-dx), matching rootMesh.
      const angle = Math.atan2(p.z, (rx * dy - ry * dx) / seg.length);
      const u = (angle / (2 * Math.PI) + 1) % 1;
      const side = u * sides, k = Math.floor(side), f = side - k;
      const radius = (arr: number[]): number => arr[k]! * (1 - f) + arr[(k + 1) % sides]! * f;
      const r = radius(seg.radiiA) * (1 - t) + radius(seg.radiiB) * t;
      const d = Math.hypot(rx, ry, p.z) - r;
      const old = byBranch.get(seg.branch);
      if (!old || d < old.d) byBranch.set(seg.branch, { d, branch: seg.branch, u, v: THREE.MathUtils.lerp(seg.s, seg.endV, t), age: THREE.MathUtils.smoothstep(r, 0.005, 0.04), join: 0 });
    }
    const ordered = [...byBranch.values()].sort((a, b) => a.d - b.d);
    const nearest = ordered[0];
    if (!nearest) return { d: 1, branch: 0, u: 0, v: 0, age: 0, join: 0 };
    let { d, u, v, age } = nearest;
    let join = 0;
    for (const other of ordered.slice(1)) {
      const a = junctions.get(nearest.branch), b = junctions.get(other.branch);
      const fork = a?.parent === other.branch ? a : b?.parent === nearest.branch ? b : undefined;
      // More wood under the lateral, less in the inner crotch: never a circular
      // collar. Girth sets the length scale, including on very fine branches.
      const side = fork ? p.clone().sub(fork.base).dot(fork.side) / fork.radius : 0;
      const blend = fork ? fork.radius * (2.1 - 0.65 * Math.tanh(side)) : 0.024;
      const h = Math.max(blend - Math.abs(d - other.d), 0) / blend;
      // Interpolate coordinates, not painted colours: this bends the ridges
      // through the fork without dissolving them into a blurry crossfade.
      const weight = h * h * (3 - 2 * h) * 0.5;
      const du = other.u - u - Math.round(other.u - u);
      u += du * weight;
      v = THREE.MathUtils.lerp(v, other.v, weight);
      age = THREE.MathUtils.lerp(age, other.age, weight);
      join = Math.max(join, h);
      d = Math.min(d, other.d) - h * h * blend * 0.25;
      // A slight uneven bark ridge follows the saddle, not the circumference.
      if (fork) d -= h * h * fork.radius * 0.07 * Math.max(0, Math.tanh(side)) * (0.8 + 0.2 * Math.sin(v * 23));
    }
    return { ...nearest, d, u: (u + 1) % 1, v, age, join };
  };
  const values = new Map<number, number>();
  const value = (id: number): number => {
    let v = values.get(id);
    if (v === undefined) { v = sample(decode(id)).d; values.set(id, v); }
    return v;
  };
  const vertices = new Map<string, Vertex>();
  const vertex = (a: number, b: number): Vertex => {
    const id = a < b ? `${a}:${b}` : `${b}:${a}`;
    const cached = vertices.get(id); if (cached) return cached;
    const va = value(a), vb = value(b);
    const p = decode(a).lerp(decode(b), va / (va - vb));
    const h = step * 0.4;
    const n = new THREE.Vector3();
    for (const axis of ["x", "y", "z"] as const) {
      const q = p.clone(); q[axis] += h; const plus = sample(q).d;
      q[axis] -= 2 * h; n[axis] = plus - sample(q).d;
    }
    n.normalize();
    const out = { p, n, sample: sample(p) }; vertices.set(id, out); return out;
  };
  interface Output { p: number[]; n: number[]; uv: number[]; age: number[]; join: number[] }
  const output = new Map<number, Output>();
  const offsets = [0, 1, nx + 1, nx, nx * ny, nx * ny + 1, nx * ny + nx + 1, nx * ny + nx];
  const edges = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]];
  for (const cell of cells) {
    const ids = offsets.map(o => cell + o);
    const cube = ids.reduce((bits, id, i) => bits | (value(id) < 0 ? 1 << i : 0), 0);
    if (!edgeTable[cube]) continue;
    const crossings = edges.map((edge, i) => (edgeTable[cube]! & (1 << i)) ? vertex(ids[edge[0]!]!, ids[edge[1]!]!) : undefined);
    for (let t = cube * 16; triTable[t] !== -1; t += 3) {
      const tri = [crossings[triTable[t]!]!, crossings[triTable[t + 1]!]!, crossings[triTable[t + 2]!]!];
      const center = tri.reduce((p, v) => p.add(v.p), new THREE.Vector3()).divideScalar(3);
      const face = new THREE.Vector3().crossVectors(tri[1]!.p.clone().sub(tri[0]!.p), tri[2]!.p.clone().sub(tri[0]!.p));
      if (face.dot(tri[0]!.n) < 0) [tri[1], tri[2]] = [tri[2]!, tri[1]!];
      const owner = sample(center).branch;
      const out = output.get(owner) ?? { p: [], n: [], uv: [], age: [], join: [] };
      output.set(owner, out);
      const seam = Math.max(...tri.map(v => v.sample.u)) - Math.min(...tri.map(v => v.sample.u)) > 0.5;
      for (const v of tri) {
        out.p.push(v.p.x, v.p.y, v.p.z); out.n.push(v.n.x, v.n.y, v.n.z);
        out.uv.push(v.sample.u + (seam && v.sample.u < 0.5 ? 1 : 0), v.sample.v);
        out.age.push(v.sample.age);
        out.join.push(v.sample.join);
      }
    }
  }
  const result = new Map<number, THREE.BufferGeometry>();
  for (const [owner, out] of output) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(out.p, 3));
    g.setAttribute("normal", new THREE.Float32BufferAttribute(out.n, 3));
    g.setAttribute("uv", new THREE.Float32BufferAttribute(out.uv, 2));
    g.setAttribute("rootAge", new THREE.Float32BufferAttribute(out.age, 1));
    g.setAttribute("rootJoin", new THREE.Float32BufferAttribute(out.join, 1));
    g.setAttribute("color", new THREE.Float32BufferAttribute(new Float32Array(out.p.length).fill(1), 3));
    g.computeBoundingSphere(); result.set(owner, g);
  }
  for (const g of inputs.values()) g.dispose();
  return result;
}
