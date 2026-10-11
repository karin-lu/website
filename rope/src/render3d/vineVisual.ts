// Plain cords use instanced capsules; braids use continuous dynamic tubes.
// Each braid has one reusable mesh containing its three strands. Unlike a
// scene chain's wrap nodes, a vine's path comes from its real physics links.
//
// It is drawn HERE rather than left to the 2D overlay, and that is the whole
// reason this file exists. A cord painted flat over the scene disappears the
// moment the overlay does - which is every 3D-only view the editor has, and
// every orbited one, since the overlay is a projection of the gameplay plane and
// is dropped as soon as the camera leaves it. A vine is not chrome, it is the
// level; and drawn in the scene it also gets what the flat cord could never
// have: it goes behind the geometry in front of it, and the level's own lights
// fall on it.
//
// Plain cords use a capsule rather than a cylinder because of the joints. The cord bends at every
// link, and two cylinders meeting at an angle leave a notch on the outside of
// the bend; the hemispherical caps fill it at any angle, which is what lets the
// segments be laid independently with no mitre to compute.

import * as THREE from "three";
import { Vec2 } from "../engine/vec2";
import { VINE_VISUAL_RADIUS, type VineCord } from "../level/vines";
import { VINE_COLOR } from "../render/vines";
import { sampleVineCurve, vineMaterial, type VineCurvePoint } from "../render/vineCurve";
import { VineTube, vineLeafGeometry } from "./vineTube";
import { makeVineLeafMaterial, makeVineLeafShadowMaterial } from "./vineLeafMaterial";
import { VineLeafLag } from "./vineLeafLag";
import { vineRandom } from "../render/vineGrowth";
import { forEachVineLeaf } from "../render/vineLeaves";
import { braidLeafAttachment } from "../render/vineBraid";
import { threeY } from "./space";

// White: the instance colour MULTIPLIES the shared material, so the default has
// to be the material's own colour rather than a tint over it. The material is
// therefore built in the vine green and an authored colour replaces it.
const DEFAULT_TINT = new THREE.Color(1, 1, 1);

// How much longer than its gap each capsule is drawn. The caps already fill the
// outside of a bend; this covers the INSIDE, where the two segments' ends pull
// apart as the cord turns.
const OVERLAP = 1.08;

// Starting capacity: a 3 m vine at the default spacing is 20 segments, so this
// is a dozen vines before the buffer has to grow.
const INITIAL_SEGMENTS = 256;

// A capsule is built along +y, and every path here is laid along a tangent, so
// the instance rotation is "turn +y onto the tangent" - one quaternion from the
// angle, exactly as the chain turns its +x.
const FORWARD = new THREE.Vector3(0, 0, 1);

export class VineLayer {
  private mesh: THREE.InstancedMesh;
  private readonly braids = new Map<VineCord, VineTube>();
  private leafMesh: THREE.InstancedMesh;
  private capacity = INITIAL_SEGMENTS;
  private count = 0;
  private leafCapacity = INITIAL_SEGMENTS;
  private leafCount = 0;
  private readonly geometry: THREE.BufferGeometry;
  private readonly braidMaterial: THREE.Material;
  private readonly curve: VineCurvePoint[] = [];
  private readonly curveStorage: VineCurvePoint[] = [];
  private readonly leafGeometry: THREE.BufferGeometry;
  private readonly leafAttachment = { across: 0, depth: 0 };
  private readonly material: THREE.Material;
  private readonly leafMaterial: THREE.Material;
  private readonly leafDepthMaterial: THREE.Material;
  private readonly leafDistanceMaterial: THREE.Material;
  // Scratch, reused every frame: a transform sync must not allocate.
  private readonly m = new THREE.Matrix4();
  private readonly q = new THREE.Quaternion();
  private readonly leafFrame = new THREE.Matrix4();
  private readonly leafOutward = new THREE.Vector3();
  private readonly leafSurfaceNormal = new THREE.Vector3();
  private readonly leafWidth = new THREE.Vector3();
  private readonly leafNormal = new THREE.Vector3();
  private readonly inverseLeaf = new THREE.Quaternion();
  private readonly leafLag = new THREE.Vector3();
  private readonly pos = new THREE.Vector3();
  private readonly scl = new THREE.Vector3(1, 1, 1);
  private readonly tint = new THREE.Color();
  private readonly path: Vec2[] = [];
  private readonly a3 = new THREE.Vector3();
  private readonly dir3 = new THREE.Vector3();

  constructor(private readonly scene: THREE.Scene) {
    // A unit-length capsule: the per-instance y scale is then the segment's own
    // length, and nothing has to rebuild geometry as a vine bends.
    this.geometry = new THREE.CapsuleGeometry(VINE_VISUAL_RADIUS, 1, 3, 8);
    this.leafGeometry = vineLeafGeometry();
    this.material = new THREE.MeshStandardMaterial({
      color: new THREE.Color(VINE_COLOR),
      roughness: 0.85,
      metalness: 0,
    });
    this.braidMaterial = new THREE.MeshStandardMaterial({ color: 0xffffff, vertexColors: true, roughness: .91 });
    this.braidMaterial.customProgramCacheKey = () => "painted-vine-stem-v1";
    this.braidMaterial.onBeforeCompile = shader => {
      shader.fragmentShader = shader.fragmentShader.replace("#include <roughnessmap_fragment>", /* glsl */`
        #include <roughnessmap_fragment>
        roughnessFactor = clamp(roughnessFactor - .10 * smoothstep(.05, .22, vColor.g), .78, .94);
      `);
    };
    this.leafMaterial = makeVineLeafMaterial();
    this.leafDepthMaterial = makeVineLeafShadowMaterial(false);
    this.leafDistanceMaterial = makeVineLeafShadowMaterial(true);
    this.mesh = this.makeMesh(this.capacity);
    this.leafMesh = this.makeMesh(this.leafCapacity, this.leafGeometry, this.leafMaterial);
    scene.add(this.mesh);
    this.leafMesh.name = "vine-leaves";
    scene.add(this.leafMesh);
  }

  private makeMesh(capacity: number, geometry = this.geometry, material = this.material): THREE.InstancedMesh {
    const mesh = new THREE.InstancedMesh(geometry, material, capacity);
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    // The count is set per frame, and a vine swings across the level, so the
    // mesh's own bounds are never a useful cull test.
    mesh.frustumCulled = false;
    mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(capacity * 3), 3);
    if (geometry === this.leafGeometry) {
      // Release the previous GPU attribute before replacing a grown instance
      // buffer. The blade's CPU geometry is retained and reuploaded once.
      if (geometry.getAttribute("leafShape")) geometry.dispose();
      geometry.setAttribute("leafShape", new THREE.InstancedBufferAttribute(new Float32Array(capacity * 4), 4).setUsage(THREE.DynamicDrawUsage));
      geometry.setAttribute("leafFaceTurn", new THREE.InstancedBufferAttribute(new Float32Array(capacity), 1).setUsage(THREE.DynamicDrawUsage));
      mesh.customDepthMaterial = this.leafDepthMaterial;
      mesh.customDistanceMaterial = this.leafDistanceMaterial;
    }
    return mesh;
  }

  private grow(needed: number): void {
    let capacity = this.capacity;
    while (capacity < needed) capacity *= 2;
    this.scene.remove(this.mesh);
    this.mesh.dispose();
    this.capacity = capacity;
    this.mesh = this.makeMesh(capacity);
    this.scene.add(this.mesh);
  }

  // Every vine on the level, laid this frame.
  sync(vines: readonly VineCord[], alpha: number, time = 0): void {
    this.count = 0;
    this.leafCount = 0;
    for (const [vine, tube] of this.braids) {
      if (!vines.includes(vine) || vine.braidSeed === null) { tube.dispose(); this.braids.delete(vine); }
      else tube.mesh.visible = false;
    }
    for (const vine of vines) {
      vine.path(alpha, this.path);
      if (this.path.length < 2) continue;
      this.tint.set(vine.color ?? DEFAULT_TINT);
      if (vine.braidSeed === null) this.lay(this.path);
      else {
        sampleVineCurve(this.path, this.curve, this.curveStorage, vine.restLength);
        let tube = this.braids.get(vine);
        if (!tube) { tube = new VineTube(this.braidMaterial); this.braids.set(vine, tube); this.scene.add(tube.mesh); }
        tube.twist.update(this.curve, time, vine.attachedAtBothEnds ?? false);
        tube.sync(this.curve, vine.braidSeed, this.tint, vine.attachedAtBothEnds);
        this.layLeaves(this.path, vine.braidSeed, tube, time);
      }
    }
    // Grow only after the walk, then fill the fresh buffers before displaying
    // them. Otherwise their untouched matrices draw capsules at the origin.
    let resized = false;
    if (this.count > this.capacity) { this.grow(this.count); resized = true; }
    if (this.leafCount > this.leafCapacity) {
      resized = true;
      while (this.leafCapacity < this.leafCount) this.leafCapacity *= 2;
      this.scene.remove(this.leafMesh);
      this.leafMesh.dispose();
      this.leafMesh = this.makeMesh(this.leafCapacity, this.leafGeometry, this.leafMaterial);
      this.leafMesh.name = "vine-leaves";
      this.scene.add(this.leafMesh);
    }
    if (resized) { this.sync(vines, alpha, time); return; }
    this.mesh.count = Math.min(this.count, this.capacity);
    this.mesh.instanceMatrix.needsUpdate = true;
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
    this.leafMesh.count = Math.min(this.leafCount, this.leafCapacity);
    this.leafMesh.instanceMatrix.needsUpdate = true;
    if (this.leafMesh.instanceColor) this.leafMesh.instanceColor.needsUpdate = true;
    this.leafGeometry.getAttribute("leafShape").needsUpdate = true;
    this.leafGeometry.getAttribute("leafFaceTurn").needsUpdate = true;
  }

  private layLeaves(points: readonly Vec2[], seed: number, tube: VineTube, time: number): void {
    let localLeaf = 0;
    forEachVineLeaf(points, seed, (x, y, side, length, tone, tx, ty, turn, fraction) => {
      const leaf = localLeaf++;
      const j = this.leafCount++;
      if (j >= this.leafCapacity) return;
      const nx = -ty, ny = tx;
      braidLeafAttachment(seed, fraction, tube.growthLength, side, this.leafAttachment);
      this.pos.set(x + nx * this.leafAttachment.across, threeY(y + ny * this.leafAttachment.across), this.leafAttachment.depth);
      this.a3.set(x, threeY(y), 0);
      const target = fraction * vineMaterial(this.curve.at(-1)!);
      let ring = 0;
      while (ring + 1 < this.curve.length - 1 && vineMaterial(this.curve[ring + 1]!) < target) ring++;
      const a = this.curve[ring]!, b = this.curve[ring + 1]!;
      const t = (target - vineMaterial(a)) / Math.max(1e-8, vineMaterial(b) - vineMaterial(a));
      const roll = (a.twist ?? 0) * (1 - t) + (b.twist ?? 0) * t;
      const across = side * .8 * Math.cos(roll) - .6 * Math.sin(roll);
      const depth = side * .8 * Math.sin(roll) + .6 * Math.cos(roll);
      this.leafOutward.set(nx * across, threeY(ny * across), depth);
      this.leafSurfaceNormal.copy(this.leafOutward);
      tube.leafSurface(fraction, this.a3, this.leafOutward, this.pos, this.leafSurfaceNormal);
      // Keep the blade's width tangent to the stem surface. Free roll around
      // its growth axis used to turn an edge back into the braid.
      this.dir3.set(tx * (.72 + turn * .12), threeY(ty * (.72 + turn * .12)) - .28, turn * .18);
      this.dir3.addScaledVector(this.leafSurfaceNormal, -this.dir3.dot(this.leafSurfaceNormal)).normalize();
      this.dir3.multiplyScalar(.78).addScaledVector(this.leafSurfaceNormal, .62).normalize();
      this.leafWidth.crossVectors(this.dir3, this.leafSurfaceNormal).normalize();
      this.leafNormal.crossVectors(this.leafWidth, this.dir3).normalize();
      this.leafFrame.makeBasis(this.leafWidth, this.dir3, this.leafNormal);
      this.q.setFromRotationMatrix(this.leafFrame);
      // Keep the attached base tangent to the stem, then gently turn the broad
      // blade toward the gameplay plane after it has cleared the braid.
      this.leafGeometry.getAttribute("leafFaceTurn").setX(j,
        Math.max(-1.05, Math.min(1.05, Math.atan2(this.leafWidth.z, this.leafNormal.z))) * (.7 + .3 * vineRandom(seed, leaf, 22)));
      const motion = tube.leafMotions[leaf] ?? (tube.leafMotions[leaf] = new VineLeafLag());
      this.inverseLeaf.copy(this.q).invert();
      this.leafLag.copy(motion.update(this.pos, time, length)).applyQuaternion(this.inverseLeaf).multiplyScalar(1 / length);
      const shape = this.leafGeometry.getAttribute("leafShape");
      shape.setXYZW(j, (vineRandom(seed, leaf, 20) - .5) * .09,
        vineRandom(seed, leaf, 21) > .8 ? -.09 : .015, this.leafLag.x, this.leafLag.z);
      this.scl.set(length * (1 + turn * .18), length, length);
      this.m.compose(this.pos, this.q, this.scl);
      this.leafMesh.setMatrixAt(j, this.m);
      const green = tone === 0 ? [0.08, 0.18, 0.05] :
        tone === 1 ? [0.13, 0.26, 0.065] : [0.23, 0.34, 0.1];
      this.leafMesh.instanceColor?.setXYZ(j, green[0]!, green[1]!, green[2]!);
    }, this.curve, tube.growthLength);
    this.scl.set(1, 1, 1);
  }

  private lay(points: readonly Vec2[]): void {
    for (let i = 0; i < points.length - 1; i++) {
      const a = points[i]!;
      const b = points[i + 1]!;
      const d = b.sub(a);
      const len = d.length();
      if (len < 1e-6) continue;
      const j = this.count++;
      if (j >= this.capacity) continue; // grown on the next frame; see above
      // The capsule's +y turned onto the segment, in three's frame.
      this.q.setFromAxisAngle(FORWARD, Math.atan2(threeY(d.y), d.x) - Math.PI / 2);
      this.pos.set((a.x + b.x) / 2, threeY((a.y + b.y) / 2), 0);
      this.scl.set(1, len * OVERLAP, 1);
      this.m.compose(this.pos, this.q, this.scl);
      this.mesh.setMatrixAt(j, this.m);
      this.mesh.instanceColor?.setXYZ(j, this.tint.r, this.tint.g, this.tint.b);
    }
    // The scale is per instance and `scl` is scratch, so it has to be handed
    // back to the identity the next caller assumes.
    this.scl.set(1, 1, 1);
  }

  clear(): void {
    this.count = 0;
    this.mesh.count = 0;
    for (const tube of this.braids.values()) { tube.mesh.visible = false; tube.leafMotions.length = 0; tube.twist.reset(); }
    this.leafMesh.count = 0;
  }

  dispose(): void {
    this.scene.remove(this.mesh);
    this.mesh.dispose();
    for (const tube of this.braids.values()) tube.dispose();
    this.braids.clear();
    this.scene.remove(this.leafMesh);
    this.leafMesh.dispose();
    this.geometry.dispose();
    this.braidMaterial.dispose();
    this.leafGeometry.dispose();
    this.material.dispose();
    this.leafMaterial.dispose();
    this.leafDepthMaterial.dispose();
    this.leafDistanceMaterial.dispose();
  }
}
