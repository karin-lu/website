// The berry of a berry vine and its leafy cap (`starberryVisual.ts`). The
// shape refines karin-lu's round lantern berry (`add-boulder-and-root-generation`,
// f831e14); the flesh and the cap follow Tris's reference: a dark, translucent
// amber fruit with a faint light glowing at its heart, pale flecks suspended
// in it catching that light, under a cap of leaves stacked on it and on each
// other, their tips flaring out (`berryCapGeometry`).

import * as THREE from "three";
import { STALK_KNOT_HEIGHT, STALK_RADIUS } from "../render/starberryArt";

const hash = (x: number, y: number, z: number): number => {
  const n = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453;
  return n - Math.floor(n);
};

// Soft paint dabs in the flesh, as directions on the unit sphere with a size and a
// brightness each.
const FLECKS = Array.from({ length: 28 }, (_, i) => {
  const u = hash(i, 1, 7) * 2 - 1;
  const phi = hash(i, 2, 9) * Math.PI * 2;
  const s = Math.sqrt(1 - u * u);
  return {
    x: s * Math.cos(phi),
    y: u,
    z: s * Math.sin(phi),
    size: 0.12 + hash(i, 3, 5) * 0.16,
    strength: 0.3 + hash(i, 4, 3) * 0.4,
  };
});

// The flecks as a map over the berry's UVs: 0 in the flesh, up to 1 at a
// fleck's heart. Data, not colour (`NoColorSpace`): the berry's shader reads
// it as how much fleck is there (`roundBerryMaterial`).
export function roundBerryTexture(): THREE.DataTexture {
  const width = 256;
  const height = 128;
  const pixels = new Uint8Array(width * height * 4);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      // three's SphereGeometry UV: u around from -x, v from the bottom pole.
      const phi = (x / (width - 1)) * Math.PI * 2;
      const theta = (1 - y / (height - 1)) * Math.PI;
      const nx = -Math.cos(phi) * Math.sin(theta);
      const ny = Math.cos(theta);
      const nz = Math.sin(phi) * Math.sin(theta);
      let fleck = 0;
      for (const f of FLECKS) {
        const d = 1 - (nx * f.x + ny * f.y + nz * f.z);
        if (d > f.size * f.size * 2) continue;
        const r = Math.sqrt(2 * d) / f.size;
        fleck = Math.max(fleck, f.strength * Math.pow(Math.max(0, 1 - r * r), 2));
      }
      const at = (y * width + x) * 4;
      const v = Math.round(255 * fleck);
      pixels[at] = pixels[at + 1] = pixels[at + 2] = v;
      pixels[at + 3] = 255;
    }
  }
  const texture = new THREE.DataTexture(pixels, width, height);
  texture.colorSpace = THREE.NoColorSpace;
  texture.magFilter = THREE.LinearFilter;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.generateMipmaps = true;
  texture.needsUpdate = true;
  return texture;
}

// Waxy skin over light-absorbing flesh. Physical transmission carries the
// scenery through the fruit; a short object-space volume integral describes
// its own light, so rotating the camera cannot paint a highlight on its heart.
// Thickness is in local radii; absorption distance is world metres, updated
// on resize. A chord through the fruit makes its edges thinner than its heart.
export function roundBerryMaterial(flecks: THREE.Texture, seed = 0): {
  material: THREE.MeshPhysicalMaterial;
  glow: { value: number };
} {
  const glow = { value: 1 };
  const material = new THREE.MeshPhysicalMaterial({
    color: 0xffefd2,
    emissive: 0xffffff,
    emissiveMap: flecks,
    roughness: 0.25,
    metalness: 0,
    transmission: 0.97,
    thickness: 2,
    attenuationColor: new THREE.Color(0xffdf9e),
    attenuationDistance: 0.72,
    ior: 1.24,
    clearcoat: 0,
    clearcoatRoughness: 0.15,
    specularIntensity: 0.22,
  });
  material.onBeforeCompile = (shader) => {
    shader.uniforms.berryGlow = glow;
    shader.uniforms.berryPaintSeed = { value: seed };
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", `#include <common>
        varying vec3 vBerryLocal;
        varying vec3 vBerryEye;`)
      .replace("#include <begin_vertex>", `#include <begin_vertex>
        vBerryLocal = position;
        mat4 berryViewInverse = inverse(modelViewMatrix);
        vBerryEye = isOrthographic
          ? position + (berryViewInverse * vec4(0.0, 0.0, 100.0, 0.0)).xyz
          : (berryViewInverse * vec4(0.0, 0.0, 0.0, 1.0)).xyz;`);
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>
        uniform float berryGlow;
        uniform float berryPaintSeed;
        varying vec3 vBerryLocal;
        varying vec3 vBerryEye;`)
      .replace(
        "#include <emissivemap_fragment>",
        `#include <emissivemap_fragment>
        float berryFleck = totalEmissiveRadiance.r;
        // Broad translucent brush dabs, with no dots or sharp skin detail.
        diffuseColor.rgb *= mix(vec3(0.98, 0.96, 0.93), vec3(1.04, 1.02, 0.99), berryFleck);
        // Large, softly blended pigment washes, fixed to the fruit as it turns.
        float paintPhase = berryPaintSeed * 0.731;
        vec3 paintPoint = vBerryLocal;
        float amberWash = smoothstep(-0.65, 0.8,
          sin(paintPoint.x * 3.1 + paintPoint.y * 1.7 + paintPhase)
          * cos(paintPoint.z * 2.4 - paintPoint.y * 1.3 + paintPhase * 0.6));
        float goldWash = smoothstep(-0.4, 0.9,
          sin(paintPoint.y * 3.4 - paintPoint.z * 2.1 + paintPhase + 2.0));
        vec3 pigment = mix(vec3(1.03, 1.12, 1.12), vec3(1.06, 0.72, 0.58), amberWash * 0.7);
        pigment = mix(pigment, vec3(1.05, 1.16, 1.23), goldWash * 0.32);
        diffuseColor.rgb *= pigment;
        vec3 berryRay = normalize(vBerryLocal - vBerryEye);
        float berryB = dot(vBerryLocal, berryRay);
        float berryChord = max(0.0, -berryB + sqrt(max(0.0,
          berryB * berryB + 1.0 - dot(vBerryLocal, vBerryLocal))));
        vec3 berryLight = vec3(0.0);
        // A broad luminous heart diffused through amber pulp. Absorption grows
        // with distance through the flesh, independently in each colour.
        for (int sampleIndex = 0; sampleIndex < 8; sampleIndex++) {
          float distanceIn = berryChord * (float(sampleIndex) + 0.5) / 8.0;
          vec3 samplePoint = vBerryLocal + berryRay * distanceIn;
          float heart = exp(-2.8 * dot(samplePoint, samplePoint));
          berryLight += vec3(1.8, 0.85, 0.16) * (0.20 + heart)
            * exp(-vec3(0.35, 0.65, 1.6) * distanceIn) * berryChord / 8.0;
        }
        berryLight += vec3(0.06, 0.035, 0.012) * berryFleck
          * (0.15 + length(berryLight));
        totalEmissiveRadiance = berryLight * pigment * berryGlow * 0.82;`,
      )
      .replace("#include <lights_physical_pars_fragment>", `
        #include <lights_physical_pars_fragment>
        void RE_Direct_Berry(const in IncidentLight light, const in vec3 position,
          const in vec3 n, const in vec3 viewDir, const in vec3 coatNormal,
          const in PhysicalMaterial mat, inout ReflectedLight reflected) {
          RE_Direct_Physical(light, position, n, viewDir, coatNormal, mat, reflected);
          float back = max(0.0, -dot(n, light.direction));
          float forwardScatter = pow(max(0.0, dot(viewDir, -light.direction)), 3.0);
          vec3 absorbed = exp(-vec3(0.7, 1.4, 3.0) * (0.25 + back));
          // Shadow-attenuated scene light passing through the flesh, warmest
          // through its thick middle and strongest toward a light behind it.
          reflected.directDiffuse += light.color * absorbed * back
            * (0.12 + 0.32 * forwardScatter) * RECIPROCAL_PI;
        }
        #undef RE_Direct
        #define RE_Direct RE_Direct_Berry
      `)
      .replace("#include <transmission_fragment>", THREE.ShaderChunk.transmission_fragment.replace(
        "material.thickness = thickness;",
        "material.thickness = thickness * clamp(berryChord * 0.5, 0.025, 1.0);",
      ));
  };
  material.customProgramCacheKey = () => "painterly-berry-volume-v7";
  return { material, glow };
}

// Matte cap paint: its mesh supplies broad green-to-yellow brush tones.
// Keep this separate from the detailed botanical material on the vines.
export function berryCapMaterial(): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    vertexColors: true,
    roughness: 0.68,
    metalness: 0,
    side: THREE.DoubleSide,
  });
}

// Shared by the skin and the draped cap, so leaves rest on the actual fruit.
// A gently squat persimmon: broad shoulders and a softly tapered base.
// Keep the top at the existing stalk seat; the cap follows the same surface.
function berrySurface(x: number, y: number, z: number): [number, number, number] {
  const shoulder = 1.025 + 0.045 * y + 0.025 * Math.exp(-Math.pow((y - 0.35) / 0.5, 2));
  const seat = 0.032 * Math.exp(-(x * x + z * z) / 0.055) * Math.max(0, y);
  // Lift the upper arc a little to form a flatter, fuller shoulder.
  const upper = 0.035 * Math.sin(Math.PI * Math.max(0, Math.min(1, y)));
  // A shallow blossom-end dimple, smoothly fading into the rounded base.
  const dimple = 0.028 * Math.exp(-(x * x + z * z) / 0.03) * Math.max(0, -y);
  return [x * shoulder, 0.93 * y + 0.07 + upper - seat + dimple, z * shoulder];
}

// Small deterministic differences in fullness; height and stalk seats stay fixed.
export function berryFullness(seed: number, index: number): { width: number; depth: number } {
  return {
    width: 1 + 0.025 * Math.sin(seed * 1.73 + index * 9.17),
    depth: 1 + 0.018 * Math.sin(seed * 0.91 + index * 5.31),
  };
}

function berryShape(g: THREE.BufferGeometry): THREE.BufferGeometry {
  const p = g.getAttribute("position");
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i);
    const y = p.getY(i);
    const z = p.getZ(i);
    p.setXYZ(i, ...berrySurface(x, y, z));
  }
  p.needsUpdate = true;
  g.computeVertexNormals();
  return g;
}

export function roundBerryGeometry(): THREE.BufferGeometry {
  return berryShape(new THREE.SphereGeometry(1, 64, 48));
}

// A simple rosette of broad, softly cupped leaves. The cap keeps its
// draped silhouette, with broad painted tones instead of veins and mottling.
// Leaf-age greens in linear colour: cool mature green, fresh green and olive.
// Broad pigment washes keep the surfaces painterly rather than finely veined.
const LEAF_OLIVES = [
  [0.12, 0.28, 0.045],
  [0.24, 0.40, 0.065],
  [0.36, 0.47, 0.10],
] as const;
const LEAF_TIP = [0.48, 0.56, 0.16] as const;

// The cap's tiers, laid bottom first: how many leaves (the least, and how many
// more), how far down the fruit they run (radians of arc, and the spread), the
// leaf's greatest half-width as a share of its length, how far the tip curls
// off (berry radii), and the green it leans to (0 dark to 1 light).
const CAP_TIERS = [
  { count: 5, extra: 0, reach: 0.90, reachSpread: 0.07, width: 0.245, curl: 0, light: 0.6 },
  { count: 3, extra: 1, reach: 0.54, reachSpread: 0.06, width: 0.29, curl: 0, light: 0.72 },
] as const;
// How far out from the stalk's axis a leaf's base grips the knot, in stalk
// radii: just outside the knot's swelling (`roundBerryKnot`).
const KNOT_GRIP = 1.35;
// How far the leaf's halves fall away from its midrib, as a share of its
// half-width: the fold that gives each leaf its keel.
const LEAF_FOLD = 0.12;
// Compact smooth mesh, with samples concentrated near the rounded ends.
const LEAF_ROWS = 16;
const LEAF_COLUMNS = 8;

// One leaf's centreline and outline over the fruit, in the berry's frame.
interface CapLeaf {
  phi: number;
  reach: number;
  width: number;
  bow: number;
  sweep: number;
  curl: number;
}

// Where along the fruit the leaf's centreline is at `t` (radians from the
// top), out from under the knot.
function leafTheta(leaf: CapLeaf, t: number): number {
  return 0.12 + leaf.reach * t;
}

function leafAzimuth(leaf: CapLeaf, t: number): number {
  return leaf.phi + leaf.bow * Math.sin(Math.PI * t) + leaf.sweep * t;
}

// Half the leaf's width at `t`, radians of arc: a narrow base, widest a third
// of the way along, with a softly tapered tip.
function leafHalfWidth(leaf: CapLeaf, t: number): number {
  return leaf.width * leaf.reach * Math.pow(Math.max(0, Math.sin(Math.PI * t)), 0.5 + 0.28 * t) * (0.70 + 0.45 * t);
}

// The direction of the point `across` (-1 to 1) of the way across the leaf at
// `t`: its width laid round the fruit, not across a chord of it.
function leafDirection(leaf: CapLeaf, t: number, across: number, out: THREE.Vector3): THREE.Vector3 {
  const theta = leafTheta(leaf, t);
  const phi = leafAzimuth(leaf, t);
  const half = leafHalfWidth(leaf, t);
  out.set(Math.sin(theta) * Math.cos(phi), Math.cos(theta), Math.sin(theta) * Math.sin(phi));
  return out.addScaledVector(SIDEWAYS.set(-Math.sin(phi), 0, Math.cos(phi)), Math.tan(across * half)).normalize();
}
const SIDEWAYS = new THREE.Vector3();

// One compact cap mesh with baked shape and broad vertex-painted colours.
// The matte material needs no vine deformation attributes or textures.
// `size` is the berry's radius (metres): the stalk is the same thickness on
// every berry, so where a leaf's base grips it, in the berry's units, depends
// on it.
export function berryCapGeometry(seed: number, berry: number, size: number): THREE.BufferGeometry {
  // The stalk's radius in berry radii.
  const stalk = STALK_RADIUS / size;
  const out = new THREE.Vector3();
  const around = new THREE.Vector3();
  const random = (leaf: number, salt: number): number => hash(seed * 0.0137 + berry * 7.31, leaf * 1.73 + salt, 3.3);
  const positions: number[] = [];
  const uvs: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  let leafIndex = 0;
  const phase = random(0, 3) * Math.PI * 2;
  const lowerAngles: number[] = [];
  for (const [tier, spec] of CAP_TIERS.entries()) {
    const n = spec.count + Math.floor(random(tier, 4) * (spec.extra + 1));
    // Inner blades occupy actual gaps between lower blades, rather than
    // rotating a separate evenly spaced rosette over them.
    for (let k = 0; k < n; k++, leafIndex++) {
      const r = (salt: number): number => random(leafIndex + 11, salt);
      const gap = Math.floor(k * lowerAngles.length / n);
      const phi = tier === 0
        ? phase + ((k + (r(1) - 0.5) * 0.12) * Math.PI * 2) / n
        : (lowerAngles[gap]! + (lowerAngles[(gap + 1) % lowerAngles.length]!
          + (gap === lowerAngles.length - 1 ? Math.PI * 2 : 0))) * 0.5;
      if (tier === 0) lowerAngles.push(phi);
      const leaf: CapLeaf = {
        phi,
        reach: spec.reach + spec.reachSpread * (r(2) - 0.5) * 2,
        width: spec.width * (0.90 + 0.20 * r(3)),
        bow: (r(4) - 0.5) * 0.18,
        sweep: (r(5) - 0.5) * 0.16,
        curl: spec.curl * (0.7 + 0.6 * r(6)),
      };
      const pick = r(7) + (spec.light - 0.5) * 0.6;
      const tone = LEAF_OLIVES[pick < 0.35 ? 0 : pick < 0.75 ? 1 : 2];
      const shade = 0.88 + 0.12 * r(8);
      // Smooth drapes with a fixed upper-tier lift keep the two rosettes
      // separated without an iterative stacking/lean solver.
      const rows = LEAF_ROWS + 1;
      const columns = LEAF_COLUMNS + 1;
      const fold = (t: number, across: number): number =>
        LEAF_FOLD * leafHalfWidth(leaf, t) * (1 - across * across);
      const start = positions.length / 3;
      for (let row = 0; row < rows; row++) {
        const t = 0.5 - 0.5 * Math.cos(Math.PI * row / LEAF_ROWS);
        // Rising out of the stalk at the base, and curling off what it rests
        // on at the tip, late and sharply.
        const rise = 0.06 * Math.pow(Math.max(0, 1 - t / 0.25), 2);
        const tip = THREE.MathUtils.smoothstep(t, 0.62, 1);
        const curl = leaf.curl * tip * tip;
        for (let column = 0; column < columns; column++) {
          const across = (column / LEAF_COLUMNS) * 2 - 1;
          const dir = leafDirection(leaf, t, across, out);
          const cushion = 0.028 * Math.sin(Math.PI * t) * (1 - across * across);
          const lying = 1.07 + cushion + tier * 0.12 + 0.014 * (k % 2) * Math.sin(Math.PI * t) + fold(t, across) + rise;
          const radius = lying + curl * 0.6;
          // The curl turns the tip out AND up, back toward the stalk, as the
          // reference's tips turn.
          let [x, y, z] = berrySurface(dir.x * radius, dir.y * radius, dir.z * radius);
          // Both layers follow the shoulder without an upward tip curve.
          y += curl;
          // Hug the shoulder along the blade; only the final tip flares out.
          const spread = 1;
          x *= spread;
          z *= spread;
          // The base GROWS OUT OF THE STALK: blended from where the leaf lies
          // to a collar round the knot (`roundBerryKnot`), wrapped part way
          // round it - each tier a little higher up the knot than the one
          // under it, as the inner leaves are.
          const grip = 1 - THREE.MathUtils.smoothstep(t, 0, 0.42);
          if (grip > 0) {
            const phi = leafAzimuth(leaf, 0);
            out.set(Math.cos(phi), 0, Math.sin(phi));
            around.set(-Math.sin(phi), 0, Math.cos(phi));
            const collar = stalk * (KNOT_GRIP + 0.12 * tier);
            const wrap = across * 0.60;
            const cx = (out.x * Math.cos(wrap) + around.x * Math.sin(wrap)) * collar;
            const cz = (out.z * Math.cos(wrap) + around.z * Math.sin(wrap)) * collar;
            const cy = 1 + stalk * (0.35 + 0.55 * tier);
            x += (cx - x) * grip;
            y += (cy - y) * grip;
            z += (cz - z) * grip;
          }
          positions.push(x, y, z);
          uvs.push(column / LEAF_COLUMNS, t);
          // Pigment follows growth: cool shaded bases, warmer tips and margins,
          // with one or two soft uneven washes instead of speckles or vein lines.
          const margin = Math.pow(Math.abs(across), 3);
          const wash = 0.5 + 0.5 * Math.sin(t * 8 + r(9) * 6.28 + across * 2.2);
          const yellow = (0.18 + 0.24 * r(10)) * t * t + 0.10 * margin * t
            + 0.08 * wash * Math.sin(Math.PI * t);
          const base = 0.72 + 0.28 * THREE.MathUtils.smoothstep(t, 0, 0.5);
          const highlight = 1 + 0.12 * Math.exp(-Math.pow((across + 0.18) / 0.65, 2))
            * Math.sin(Math.PI * t);
          for (let channel = 0; channel < 3; channel++) {
            const rootBlend = 1 - THREE.MathUtils.smoothstep(t, 0, 0.45);
            const paint = (tone[channel]! * shade * base * (1 - yellow)
              + LEAF_TIP[channel]! * yellow) * highlight * (0.96 + wash * 0.08);
            colors.push(paint * (1 - rootBlend) + [0.10, 0.23, 0.04][channel]! * rootBlend);
          }
        }
      }
      for (let row = 0; row < LEAF_ROWS; row++) {
        for (let column = 0; column < LEAF_COLUMNS; column++) {
          const a = start + row * (LEAF_COLUMNS + 1) + column;
          const b = a + LEAF_COLUMNS + 1;
          indices.push(a, a + 1, b, b, a + 1, b + 1);
        }
      }
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  g.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  g.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  g.setIndex(indices);
  g.computeVertexNormals();
  thickenCap(g);
  // A small green calyx collar joins the blade bases to the woody stem.
  // Merge it into the cap so it adds no material or draw call.
  const collar = new THREE.LatheGeometry([
    new THREE.Vector2(stalk * 2.05, 1 - stalk * 0.3),
    new THREE.Vector2(stalk * 1.95, 1 + stalk * 0.2),
    new THREE.Vector2(stalk * 1.42, 1 + stalk * 0.8),
    new THREE.Vector2(stalk * 1.10, 1 + stalk * 1.3),
  ], 12);
  const offset = g.getAttribute("position").count;
  for (const name of ["position", "normal", "uv"] as const) {
    const existing = g.getAttribute(name);
    g.setAttribute(name, new THREE.Float32BufferAttribute(
      [...existing.array, ...collar.getAttribute(name).array], existing.itemSize));
  }
  const collarColors = Array.from({ length: collar.getAttribute("position").count }, () => [0.10, 0.23, 0.04]).flat();
  g.setAttribute("color", new THREE.Float32BufferAttribute([...g.getAttribute("color").array, ...collarColors], 3));
  g.setIndex([...g.index!.array, ...Array.from(collar.index!.array, index => index + offset)]);
  collar.dispose();
  g.computeBoundingSphere();
  return g;
}

// A real underside and a closed, softly rounded edge, rather than a
// double-sided zero-thickness sheet. Each leaf keeps its own topology.
function thickenCap(g: THREE.BufferGeometry): void {
  const p = g.getAttribute("position");
  const n = g.getAttribute("normal");
  const uv = g.getAttribute("uv");
  const color = g.getAttribute("color");
  const count = p.count;
  const positions = Array.from(p.array);
  const uvs = Array.from(uv.array);
  const colors = Array.from(color.array);
  const front = Array.from(g.index!.array);
  const indices = [...front];
  for (let i = 0; i < count; i++) {
    const across = uv.getX(i) * 2 - 1;
    // A fleshy centre thinning smoothly into the outline and tip.
    const along = Math.sqrt(Math.max(0, Math.sin(Math.PI * uv.getY(i))));
    // Inflate both sides, so the visible top is plump rather than hiding
    // all the added thickness beneath the blade. An oval section gives the
    // rim and nose soft transitions without adding vertices.
    const thickness = 0.020 + 0.070 * along * Math.sqrt(Math.max(0, 1 - across * across));
    const top = thickness * 0.60;
    const bottom = thickness * 0.40;
    positions[i * 3] = p.getX(i) + n.getX(i) * top;
    positions[i * 3 + 1] = p.getY(i) + n.getY(i) * top;
    positions[i * 3 + 2] = p.getZ(i) + n.getZ(i) * top;
    positions.push(p.getX(i) - n.getX(i) * bottom,
      p.getY(i) - n.getY(i) * bottom, p.getZ(i) - n.getZ(i) * bottom);
    uvs.push(uv.getX(i), uv.getY(i));
    // The underside is a little paler and less saturated, like a real leaf.
    colors.push(color.getX(i) * 0.82 + 0.035, color.getY(i) * 0.84 + 0.045, color.getZ(i) * 0.8 + 0.035);
  }
  for (let i = 0; i < front.length; i += 3) {
    indices.push(front[i]! + count, front[i + 2]! + count, front[i + 1]! + count);
  }
  const stride = LEAF_COLUMNS + 1;
  const leafVertices = (LEAF_ROWS + 1) * stride;
  for (let start = 0; start < count; start += leafVertices) {
    const perimeter: number[] = [];
    for (let c = 0; c < LEAF_COLUMNS; c++) perimeter.push(start + c);
    for (let r = 0; r < LEAF_ROWS; r++) perimeter.push(start + r * stride + LEAF_COLUMNS);
    for (let c = LEAF_COLUMNS; c > 0; c--) perimeter.push(start + LEAF_ROWS * stride + c);
    for (let r = LEAF_ROWS; r > 0; r--) perimeter.push(start + r * stride);
    for (let i = 0; i < perimeter.length; i++) {
      const a = perimeter[i]!, b = perimeter[(i + 1) % perimeter.length]!;
      indices.push(a, a + count, b, b, a + count, b + count);
    }
  }
  g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  g.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  g.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  g.setIndex(indices);
  g.computeVertexNormals();
  g.computeBoundingSphere();
}

// The knot: the stalk's end swelling into the top of the berry, in STALK
// radii (`STALK_RADIUS`), its origin on the berry's top and +y up the stalk -
// placed there and scaled by the stalk, not the berry, so it is the stalk's
// own thickness on every berry. The leaves' bases grip it (`KNOT_GRIP`).
export function roundBerryKnot(): THREE.BufferGeometry {
  const positions: number[] = [];
  const indices: number[] = [];
  const profile = [
    [2.0, -1.2],
    [2.05, -0.15],
    [1.35, 0.8],
    [0.86, 2.0],
    [0.78, STALK_KNOT_HEIGHT / STALK_RADIUS],
  ];
  const rings = new THREE.CatmullRomCurve3(profile.map(([r, h]) => new THREE.Vector3(r!, h!, 0)))
    .getPoints(12).map(p => [p.x, p.y]);
  const around = 12;
  for (const [ring, [radius, height]] of rings.entries()) {
    for (let i = 0; i <= around; i++) {
      const angle = (i / around) * Math.PI * 2;
      const wobble = 1 + 0.015 * Math.sin(angle * 3 + ring * 0.2);
      positions.push(Math.cos(angle) * radius! * wobble, height!, Math.sin(angle) * radius! * wobble);
      if (ring < rings.length - 1 && i < around) {
        const a = ring * (around + 1) + i;
        const b = a + around + 1;
        // Wound to face out of the collar.
        indices.push(a, b, a + 1, a + 1, b, b + 1);
      }
    }
  }
  // Closed at the top, where the stalk runs into it.
  const top = positions.length / 3;
  positions.push(0, rings.at(-1)![1]!, 0);
  const last = (rings.length - 1) * (around + 1);
  for (let i = 0; i < around; i++) indices.push(last + i, top, last + i + 1);
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  g.setIndex(indices);
  g.computeVertexNormals();
  return g;
}
