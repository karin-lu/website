import * as THREE from "three";
import { VineSurface, rand } from "./ivySurface";
import { LeafSupport } from './leafSupport';

/** Bend the Blender atlas cards, retaining their UVs and painted colours.
 * glTF flips Blender's V coordinate: the stalk is at the high-V end.
 * Connected rock underlays, constant-UV stems and segmented hanging strands
 * are retained. Only isolated, rectangular two-triangle cards are rebuilt. */
export function curveIvyGeometry(source: THREE.BufferGeometry, world: THREE.Matrix4, rock?: VineSurface,
  opaque?: (uv:THREE.Vector2)=>boolean): THREE.BufferGeometry {
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
  let count = 0, leafCards=0, leafContacts=0, hostContacts=0;
  const attachments: {point:number[];supportPoint:number[];kind:string}[]=[];
  const support=new LeafSupport(opaque);
  const get = (id: number) => new THREE.Vector3().fromBufferAttribute(position, id).applyMatrix4(world);
  // The solid original underlay is a valid support, not a new backing blob.
  for (let i=0;i<index.count;i+=3) {
    const ids=[index.getX(i),index.getX(i+1),index.getX(i+2)];
    if (ids.every(id=>Math.abs(uv.getX(id)-uv.getX(ids[0]!))<.00001 && Math.abs(uv.getY(id)-uv.getY(ids[0]!))<.00001))
      support.add(ids.map(get),ids.map(id=>new THREE.Vector2(uv.getX(id),uv.getY(id))));
  }
  const depths=new Map<number[],number>();
  for (const ids of components.values()) depths.set(ids,rock?.nearest(ids.reduce((p,id)=>p.add(get(id)),new THREE.Vector3()).divideScalar(ids.length))?.distance ?? 0);
  const sorted=[...components.values()].sort((a,b)=>depths.get(a)!-depths.get(b)!);
  for (const ids of sorted) {
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
    let base = du > .195 ? .16 : .09;
    // A fuzzy atlas may have transparent space before its painted stalk.
    // Seat the visible leaf itself, not an invisible point on its rectangle.
    if (opaque) for (let s=.02;s<=.4;s+=.01) {
      if (opaque(new THREE.Vector2((loU+hiU)*.5,hiV-(hiV-loV)*s))) { base=s; break; }
    }
    const anchor = bottom.clone().lerp(top, base), pull = new THREE.Vector3();
    const leafHit=support.below(anchor.clone().addScaledVector(normal,.004),normal,Math.max(.4,height*1.2));
    const hit=leafHit ?? rock?.nearest(anchor);
    if (hit) {
      const target=hit.point.clone().addScaledVector(hit.normal,.002);
      pull.subVectors(target,anchor);
      attachments.push({point:target.toArray(),supportPoint:hit.point.toArray(),kind:leafHit?'leaf':'host'});
      if (leafHit) leafContacts++; else hostContacts++;
    }
    const curl = .025 + .02 * rand(2401, a!, 1), fold = .025 + .02 * rand(2401, a!, 2);
    const rows = [0, base, base+(1-base)*.34, base+(1-base)*.67, 1], offset = count;
    const worldPoints:THREE.Vector3[]=[];
    for (const s of rows) for (const u of [0, .5, 1]) {
      const weights = [(1 - u) * (1 - s), u * (1 - s), (1 - u) * s, u * s];
      const p = new THREE.Vector3(); points.forEach((point, k) => p.addScaledVector(point, weights[k]!));
      const t = Math.max(0, (s - base) / (1 - base));
      p.add(pull).addScaledVector(normal, height * (.045 * Math.sin(Math.PI * t) - curl * t * t)
        + width * fold * (2 * u - 1) ** 2 * Math.sin(Math.PI * t));
      // The same surface projection used by vines prevents curling into stone.
      if (s>base) {
        const beneath=support.below(p.clone().addScaledVector(normal,.08),normal,.16);
        const backing=beneath ?? rock?.nearest(p,height*.35);
        if (backing) {
          const gap=p.clone().sub(backing.point).dot(backing.normal);
          // Keep the blade nestled into the bush, with only a small soft
          // arch between its seated base and tip. A rooted stalk alone can
          // still leave a conspicuous air gap beneath the broad blade.
          const maxGap=.002+height*.022*Math.sin(Math.PI*t);
          if (gap<.002) p.copy(backing.point).addScaledVector(backing.normal,.002);
          else if (gap>maxGap) p.addScaledVector(backing.normal,maxGap-gap);
        }
      }
      rock?.project(p, .002);
      worldPoints.push(p.clone());
      p.applyMatrix4(inverse);
      for (const [name, output] of Object.entries(values)) {
        const attr = source.getAttribute(name);
        for (let k = 0; k < attr.itemSize; k++) {
          if (name === "position") output.push(p.getComponent(k));
          else output.push(corners.reduce<number>((sum, id, j) => sum + attr.getComponent(id!, k) * weights[j]!, 0));
        }
      }
      count++;
    }
    const geometric = points[1]!.clone().sub(points[0]!).cross(top.clone().sub(bottom));
    const reverse = geometric.dot(normal) * Math.sign(world.determinant()) < 0;
    for (let r = 0; r < rows.length - 1; r++) for (let col = 0; col < 2; col++) {
      const i = offset + r * 3 + col;
      const face = [i, i + 1, i + 4, i, i + 4, i + 3];
      if (reverse) for (let j = 0; j < face.length; j += 3) [face[j + 1], face[j + 2]] = [face[j + 2]!, face[j + 1]!];
      triangles.push(...face);
      for (let j=0;j<face.length;j+=3) {
        const at=face.slice(j,j+3);
        support.add(at.map(id=>worldPoints[id-offset]!),at.map(id=>new THREE.Vector2(values.uv![id*2]!,values.uv![id*2+1]!)));
      }
    }
    ids.forEach(i => replaced.add(i));
    leafCards++;
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
  geometry.setIndex(triangles);
  // Blender deliberately shades each painted leaf with the rounded host's
  // hull normal. Recomputing normals from the contact-adjusted triangles
  // turns small bends into dark creases and exposes the card's triangulation.
  // Keep those authored normals, including on the connected underlay.
  if (!geometry.getAttribute('normal')) geometry.computeVertexNormals();
  geometry.computeBoundingBox(); geometry.computeBoundingSphere();
  geometry.userData.curvedIvy = true;
  Object.assign(geometry.userData,{ivyLeafCards:leafCards,leafContacts,hostContacts,attachments});
  return geometry;
}

/** Read the nearest opaque host into the vine generator's surface structure. */
export function ivyHostSurface(mesh: THREE.Mesh): VineSurface | undefined {
  let host = mesh.parent;
  const ivyName = (o: THREE.Object3D) => /\.(ivy|moss)(\.shadow)?$/.test(String(o.userData.name ?? o.name));
  for (let ancestor=mesh.parent;ancestor;ancestor=ancestor.parent) {
    if (ivyName(ancestor)) { host=ancestor; break; }
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
