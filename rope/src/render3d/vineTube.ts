import * as THREE from "three";
import { VINE_VISUAL_RADIUS } from "../level/vines";
import { forEachBraidPoint } from "../render/vineBraid";
import { vineMaterial, type VineCurvePoint } from "../render/vineCurve";
import { VineTwist } from "../render/vineTwist";
import type { VineLeafLag } from "./vineLeafLag";

const SIDES = 12, RING = SIDES + 1;
const OLIVE = new THREE.Color("#637848"), BARK = new THREE.Color("#6d6243"), MOSS = new THREE.Color("#7e9155");
function softBand(a: number, b: number, x: number): number {
  const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t);
}

// TubeGeometry's ring topology, with reusable dynamic buffers instead of a
// fresh Curve/TubeGeometry every frame. A transported frame avoids twisting
// the tube's normals at bends; adjacent sections share their vertices.
export class VineTube {
  growthLength = 0;
  readonly leafMotions: VineLeafLag[] = [];
  readonly twist = new VineTwist();
  readonly mesh: THREE.Mesh;
  private geometry = new THREE.BufferGeometry();
  private capacity = 0;
  private rings = 0;
  private centres = new Float32Array(0);
  private previous = new Float64Array(0);
  private previousCount = 0;
  private previousSeed = -1;
  private previousAttached = false;
  private readonly previousTint = new THREE.Color(-1, -1, -1);
  private readonly tangent = new THREE.Vector3();
  private readonly previousTangent = new THREE.Vector3();
  private readonly transport = new THREE.Quaternion();
  private readonly normal = new THREE.Vector3();
  private readonly binormal = new THREE.Vector3();
  private readonly radial = new THREE.Vector3();
  private readonly surfaceNormal = new THREE.Vector3();
  private readonly around = new THREE.Vector3();
  private readonly paint = new THREE.Color();
  private readonly leafEdgeStart = new THREE.Vector3();
  private readonly leafEdgeEnd = new THREE.Vector3();

  constructor(material: THREE.Material) {
    this.mesh = new THREE.Mesh(this.geometry, material);
    this.mesh.name = "vine-braid-tube";
    this.mesh.castShadow = this.mesh.receiveShadow = true;
    this.mesh.frustumCulled = false;
  }

  sync(curve: readonly VineCurvePoint[], seed: number, tint: THREE.Color, attachedAtBothEnds = false): void {
    const count = curve.length;
    this.mesh.visible = count >= 2;
    if (count < 2) return;
    if (!this.growthLength) this.growthLength = vineMaterial(curve.at(-1)!);
    let changed = count !== this.previousCount || seed !== this.previousSeed || !tint.equals(this.previousTint) || attachedAtBothEnds !== this.previousAttached;
    for (let i = 0; !changed && i < count; i++) {
      const p = curve[i]!, k = i * 7;
      changed = p.x !== this.previous[k] || p.y !== this.previous[k + 1] || p.tx !== this.previous[k + 2] ||
        p.ty !== this.previous[k + 3] || vineMaterial(p) !== this.previous[k + 4] ||
        (p.twist ?? 0) !== this.previous[k + 5] || (p.stretch ?? 1) !== this.previous[k + 6];
    }
    if (!changed) return;
    if (count > this.capacity) {
      this.capacity = Math.max(64, 2 ** Math.ceil(Math.log2(count)));
      this.geometry.dispose();
      this.geometry = new THREE.BufferGeometry();
      const vertices = 3 * (this.capacity * RING + 2);
      for (const name of ["position", "normal", "color"]) {
        this.geometry.setAttribute(name, new THREE.BufferAttribute(new Float32Array(vertices * 3), 3).setUsage(THREE.DynamicDrawUsage));
      }
      this.geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(3 * this.capacity * SIDES * 6), 1).setUsage(THREE.DynamicDrawUsage));
      this.mesh.geometry = this.geometry;
      this.centres = new Float32Array(this.capacity * 3 * 4);
      this.previous = new Float64Array(this.capacity * 7);
      this.rings = 0;
    }
    const stride = this.capacity * RING + 2;
    if (this.rings !== count) {
      const indices = this.geometry.index!;
      let k = 0;
      for (let s = 0; s < 3; s++) {
        const offset = s * stride, startCap = offset + this.capacity * RING, endCap = startCap + 1;
        for (let i = 0; i < count - 1; i++) for (let j = 0; j < SIDES; j++) {
          const a = offset + i * RING + j, b = a + RING;
          indices.setX(k++, a); indices.setX(k++, a + 1); indices.setX(k++, b);
          indices.setX(k++, b); indices.setX(k++, a + 1); indices.setX(k++, b + 1);
        }
        for (let j = 0; j < SIDES; j++) {
          indices.setX(k++, startCap); indices.setX(k++, offset + j + 1); indices.setX(k++, offset + j);
          indices.setX(k++, endCap); indices.setX(k++, offset + (count - 1) * RING + j);
          indices.setX(k++, offset + (count - 1) * RING + j + 1);
        }
      }
      this.geometry.setDrawRange(0, k);
      indices.needsUpdate = true;
      this.rings = count;
    }
    forEachBraidPoint(curve, seed, (i, x, y, z, strand, girth) => {
      const k = (strand * this.capacity + i) * 4;
      this.centres[k] = x; this.centres[k + 1] = -y; this.centres[k + 2] = z;
      this.centres[k + 3] = VINE_VISUAL_RADIUS * .52 * girth;
    }, this.growthLength, attachedAtBothEnds);
    const position = this.geometry.getAttribute("position"), normals = this.geometry.getAttribute("normal"), colors = this.geometry.getAttribute("color");
    for (let s = 0; s < 3; s++) {
      const shade = s === 0 ? 1.02 : s === 1 ? .97 : .94;
      const phase = seed * .71 + s * 1.9;
      this.normal.set(0, 0, 1);
      for (let i = 0; i < count; i++) {
        const k = (s * this.capacity + i) * 4;
        const before = (s * this.capacity + Math.max(0, i - 1)) * 4;
        const after = (s * this.capacity + Math.min(count - 1, i + 1)) * 4;
        this.tangent.set(this.centres[after]! - this.centres[before]!, this.centres[after + 1]! - this.centres[before + 1]!, this.centres[after + 2]! - this.centres[before + 2]!);
        const length = this.tangent.length();
        if (length > 1e-8) this.tangent.multiplyScalar(1 / length); else this.tangent.set(0, -1, 0);
        if (i) {
          // Minimal rotation, unlike repeated projection which introduces
          // artificial roll on curved/helical strand centrelines.
          this.transport.setFromUnitVectors(this.previousTangent, this.tangent);
          this.normal.applyQuaternion(this.transport);
        }
        this.previousTangent.copy(this.tangent);
        this.normal.addScaledVector(this.tangent, -this.normal.dot(this.tangent));
        if (this.normal.lengthSq() < 1e-8) {
          this.normal.set(Math.abs(this.tangent.x) < .9 ? 1 : 0, Math.abs(this.tangent.x) < .9 ? 0 : 1, 0);
          this.normal.addScaledVector(this.tangent, -this.normal.dot(this.tangent));
        }
        this.normal.normalize();
        this.binormal.crossVectors(this.tangent, this.normal).normalize();
        const slope = length > 1e-8 ? (this.centres[after + 3]! - this.centres[before + 3]!) / length : 0;
        const growth = vineMaterial(curve[i]!) / vineMaterial(curve.at(-1)!) * this.growthLength;
        for (let j = 0; j <= SIDES; j++) {
          const angle = (j % SIDES) * Math.PI * 2 / SIDES;
          this.radial.copy(this.normal).multiplyScalar(Math.cos(angle)).addScaledVector(this.binormal, Math.sin(angle));
          const ridge = 1 + .018 * Math.cos(angle * 3 + phase) + .012 * Math.sin(angle * 4 + growth * .8);
          const ridgeSlope = -.054 * Math.sin(angle * 3 + phase) + .048 * Math.cos(angle * 4 + growth * .8);
          const v = s * stride + i * RING + j, radius = this.centres[k + 3]! * ridge;
          position.setXYZ(v, this.centres[k]! + this.radial.x * radius, this.centres[k + 1]! + this.radial.y * radius, this.centres[k + 2]! + this.radial.z * radius);
          this.around.copy(this.normal).multiplyScalar(-Math.sin(angle)).addScaledVector(this.binormal, Math.cos(angle));
          this.surfaceNormal.copy(this.radial).addScaledVector(this.tangent, -slope).addScaledVector(this.around, -ridgeSlope / ridge).normalize();
          normals.setXYZ(v, this.surfaceNormal.x, this.surfaceNormal.y, this.surfaceNormal.z);
          const patch = softBand(-.25, .25, Math.sin(growth * 4.1 + Math.sin(angle * 2 + phase) * 1.3 + phase));
          const stroke = softBand(.35, .7, Math.sin(angle * 4 + Math.sin(growth * 1.5 + phase) * .6) * Math.sin(growth * 6.2 + phase));
          this.paint.copy(BARK).lerp(OLIVE, patch).lerp(MOSS, stroke * .6);
          const inwardX = curve[i]!.x - this.centres[k]!, inwardY = -curve[i]!.y - this.centres[k + 1]!, inwardZ = -this.centres[k + 2]!;
          const contact = Math.max(0, (this.radial.x * inwardX + this.radial.y * inwardY + this.radial.z * inwardZ) / Math.max(1e-6, Math.hypot(inwardX, inwardY, inwardZ)));
          const cavity = 1 - .14 * contact;
          colors.setXYZ(v, this.paint.r * tint.r * shade * cavity, this.paint.g * tint.g * shade * cavity, this.paint.b * tint.b * shade * cavity);
        }
        if (i === 0 || i === count - 1) {
          const v = s * stride + this.capacity * RING + (i === 0 ? 0 : 1), sign = i === 0 ? -1 : 1;
          position.setXYZ(v, this.centres[k]!, this.centres[k + 1]!, this.centres[k + 2]!);
          normals.setXYZ(v, this.tangent.x * sign, this.tangent.y * sign, this.tangent.z * sign);
          colors.setXYZ(v, OLIVE.r * tint.r * shade, OLIVE.g * tint.g * shade, OLIVE.b * tint.b * shade);
        }
      }
    }
    position.needsUpdate = normals.needsUpdate = colors.needsUpdate = true;
    for (let i = 0; i < count; i++) {
      const p = curve[i]!, k = i * 7;
      this.previous[k] = p.x; this.previous[k + 1] = p.y; this.previous[k + 2] = p.tx;
      this.previous[k + 3] = p.ty; this.previous[k + 4] = vineMaterial(p);
      this.previous[k + 5] = p.twist ?? 0; this.previous[k + 6] = p.stretch ?? 1;
    }
    this.previousCount = count; this.previousSeed = seed; this.previousTint.copy(tint);
    this.previousAttached = attachedAtBothEnds;
  }

  // Use the exposed support edge of the WHOLE braid at this material station.
  // A surface normal on just one strand can point its leaf into another strand.
  // Interpolation along a rendered longitudinal edge keeps the root on the
  // actual mesh, while the supporting plane leaves every strand behind it.
  leafSurface(fraction: number, centre: THREE.Vector3, outward: THREE.Vector3, point: THREE.Vector3, normal: THREE.Vector3): boolean {
    const target = this.previous[(this.rings - 1) * 7 + 4]! * fraction;
    let ring = 0;
    while (ring + 1 < this.rings - 1 && this.previous[(ring + 1) * 7 + 4]! < target) ring++;
    const aDistance = this.previous[ring * 7 + 4]!, bDistance = this.previous[(ring + 1) * 7 + 4]!;
    const t = Math.max(0, Math.min(1, (target - aDistance) / (bDistance - aDistance)));
    const positions = this.geometry.getAttribute("position");
    const stride = this.capacity * RING + 2;
    let exposed = -Infinity;
    for (let s = 0; s < 3; s++) for (let j = 0; j < SIDES; j++) {
      const a = s * stride + ring * RING + j, b = a + RING;
      this.leafEdgeStart.fromBufferAttribute(positions, a);
      this.leafEdgeEnd.fromBufferAttribute(positions, b);
      this.leafEdgeStart.lerp(this.leafEdgeEnd, t);
      const support = this.leafEdgeStart.dot(outward) - centre.dot(outward);
      if (support <= exposed) continue;
      exposed = support; point.copy(this.leafEdgeStart);
    }
    normal.copy(outward);
    return Number.isFinite(exposed);
  }

  dispose(): void { this.geometry.dispose(); this.mesh.removeFromParent(); }
}

// A pointed blade with an arched midrib, cupped edges and a drooping tip.
export function vineLeafGeometry(): THREE.BufferGeometry {
  const rows = 18, columns = 10, positions: number[] = [], indices: number[] = [], uvs: number[] = [];
  for (let i = 0; i <= rows; i++) {
    const t = i / rows, width = .29 * Math.pow(Math.sin(Math.PI * t), .8);
    for (let j = 0; j <= columns; j++) {
      const across = j / columns * 2 - 1;
      positions.push(width * across * (across < 0 ? .92 : 1.08) + .025 * Math.sin(Math.PI * 2 * t),
        t - .08 * t * t * t, (.045 + .026 * Math.exp(-Math.abs(across) * 9) - .018 * across * across) * Math.sin(Math.PI * t) - .08 * t * t * t);
      uvs.push(j / columns, t);
    }
  }
  for (let i = 0; i < rows; i++) for (let j = 0; j < columns; j++) {
    const a = i * (columns + 1) + j, b = a + columns + 1;
    indices.push(a, a + 1, b, b, a + 1, b + 1);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices); geometry.computeVertexNormals();
  return geometry;
}
