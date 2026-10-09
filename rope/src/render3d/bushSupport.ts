import * as THREE from 'three';
import { MarchingCubes } from 'three/addons/objects/MarchingCubes.js';

type Site = { point: number[]; normal: number[]; uv: number[]; colour: number[] };

/** One fused, smooth backing surface following the bush's leaf roots.
 * The density field is smoothed before extracting the surface: no individual
 * spheres, internal seams or separate lobe silhouettes remain. */
export function buildBushSupport(leaves: THREE.BufferGeometry, world: THREE.Matrix4,
  sampleColour?: (uv: THREE.Vector2) => THREE.Color): THREE.BufferGeometry {
  const sites = (leaves.userData.ivySupportSites ?? []) as Site[];
  const result = new THREE.BufferGeometry();
  if (!sites.length) return result;
  const cells = new Map<string, Site>();
  const bounds = new THREE.Box3();
  for (const site of sites) {
    const point = new THREE.Vector3().fromArray(site.point);
    bounds.expandByPoint(point);
    const key = site.point.map(v => Math.floor(v / .10)).join(',');
    if (!cells.has(key)) cells.set(key, site);
  }
  bounds.expandByScalar(.28);
  const size = bounds.getSize(new THREE.Vector3()), centre = bounds.getCenter(new THREE.Vector3());
  const resolution = 96, stride = resolution * resolution;
  const material = new THREE.MeshBasicMaterial();
  const surface = new MarchingCubes(resolution, material, false, false, 100000);
  surface.isolation = .30;
  const tint = new THREE.Color(0, 0, 0);
  const delta = new THREE.Vector3();
  for (const site of cells.values()) {
    const normal = new THREE.Vector3().fromArray(site.normal).normalize();
    const root = new THREE.Vector3().fromArray(site.point).addScaledVector(normal, -.025);
    const colour = sampleColour?.(new THREE.Vector2().fromArray(site.uv)) ?? new THREE.Color('#4d742c');
    tint.add(colour.multiply(new THREE.Color().fromArray(site.colour)));
    const radius = .23, depth = .115;
    const lo = root.clone().addScalar(-radius).sub(bounds.min).divide(size).multiplyScalar(resolution);
    const hi = root.clone().addScalar(radius).sub(bounds.min).divide(size).multiplyScalar(resolution);
    for (let z=Math.max(1,Math.floor(lo.z));z<=Math.min(resolution-2,Math.ceil(hi.z));z++)
      for (let y=Math.max(1,Math.floor(lo.y));y<=Math.min(resolution-2,Math.ceil(hi.y));y++)
        for (let x=Math.max(1,Math.floor(lo.x));x<=Math.min(resolution-2,Math.ceil(hi.x));x++) {
          delta.set(bounds.min.x+x*size.x/resolution-root.x,
            bounds.min.y+y*size.y/resolution-root.y, bounds.min.z+z*size.z/resolution-root.z);
          const along=delta.dot(normal);
          const distance=(delta.lengthSq()-along*along)/(radius*radius)+along*along/(depth*depth);
          const index=x+y*resolution+z*stride;
          surface.field[index]=Math.max(surface.field[index]!,1-distance);
        }
  }
  tint.multiplyScalar(.88 / cells.size);
  // Low-pass the union into a single rounded envelope, rather than rendering
  // overlapping ellipsoids. Keep the boundary empty so the backing is closed.
  let field: Float32Array=surface.field, scratch: Float32Array=new Float32Array(field.length);
  for (let pass=0;pass<4;pass++) {
    scratch.fill(0);
    for (let z=1;z<resolution-1;z++) for (let y=1;y<resolution-1;y++) for (let x=1;x<resolution-1;x++) {
      const i=x+y*resolution+z*stride;
      scratch[i]=(field[i]!*4+field[i-1]!+field[i+1]!+field[i-resolution]!+field[i+resolution]!
        +field[i-stride]!+field[i+stride]!)/10;
    }
    [field,scratch]=[scratch,field];
  }
  surface.field.set(field);
  surface.update();
  const vertexCount=surface.geometry.drawRange.count;
  for (const name of ['position','normal']) {
    const attr=surface.geometry.getAttribute(name);
    result.setAttribute(name,new THREE.Float32BufferAttribute(Array.from(attr.array.slice(0,vertexCount*3)),3));
  }
  const transform=new THREE.Matrix4().makeScale(size.x/2,size.y/2,size.z/2);
  transform.setPosition(centre);
  result.applyMatrix4(world.clone().invert().multiply(transform));
  if (world.determinant()<0) {
    for (const name of ['position','normal']) {
      const attr=result.getAttribute(name);
      for (let i=0;i<vertexCount;i+=3) for (let k=0;k<3;k++) {
        const a=attr.getComponent(i+1,k); attr.setComponent(i+1,k,attr.getComponent(i+2,k)); attr.setComponent(i+2,k,a);
      }
    }
  }
  const colours=new Float32Array(vertexCount*3);
  for (let i=0;i<vertexCount;i++) tint.toArray(colours,i*3);
  result.setAttribute('color',new THREE.BufferAttribute(colours,3));
  result.computeBoundingBox(); result.computeBoundingSphere();
  result.userData.bushSupportLobes = vertexCount ? 1 : 0;
  result.userData.continuousBushSupport = true;
  surface.geometry.dispose(); material.dispose();
  return result;
}
