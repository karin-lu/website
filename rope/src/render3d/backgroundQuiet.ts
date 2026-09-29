import type * as THREE from "three";

// Runtime art direction stays with v5 when its Blender package is re-exported.
// Gameplay is composed afterward and never receives this treatment.
export function usesQuietBackground(url: string): boolean {
  return new URL(url, "https://background.invalid/").pathname ===
    "/backgrounds/river-dream-v5/package.json";
}

const treated = new WeakSet<THREE.Material>();

export function applyQuietBackground(material: THREE.Material, plate = false): void {
  if (treated.has(material)) return;
  treated.add(material);
  const compile = material.onBeforeCompile;
  const cacheKey = material.customProgramCacheKey();
  material.onBeforeCompile = function (shader, renderer) {
    compile.call(this, shader, renderer);
    if (!plate) {
      shader.vertexShader = `varying float vQuietDepth;\n${shader.vertexShader}`.replace(
        "#include <project_vertex>",
        "#include <project_vertex>\nvQuietDepth = -mvPosition.z;",
      );
      shader.fragmentShader = `varying float vQuietDepth;\n${shader.fragmentShader}`;
    }
    shader.fragmentShader = shader.fragmentShader.replace("#include <opaque_fragment>", `
      // Linear blue-gray pivot compresses contrast instead of darkening the ball's backdrop.
      outgoingLight = mix(vec3(dot(outgoingLight, vec3(0.2126, 0.7152, 0.0722))), outgoingLight, 0.92);
      outgoingLight = mix(outgoingLight, vec3(0.028, 0.064, 0.092), ${plate ? "0.16" : "0.22"});
      ${plate ? "" : "outgoingLight = mix(outgoingLight, vec3(0.028, 0.064, 0.092), 0.14 * smoothstep(35.0, 115.0, vQuietDepth));"}
      #include <opaque_fragment>
    `);
  };
  material.customProgramCacheKey = () => `${cacheKey}|quiet-cave-v1:${plate ? "plate" : "depth"}`;
  material.needsUpdate = true;
}
