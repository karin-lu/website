import type { Material } from "three";

// Applied only by the v5 background package. Work on the sampled RGB after
// baked vertex lighting, leaving the original atlas alpha and cutout intact.
export function applyBackgroundMossQuieting(material: Material): void {
  if (material.userData.river_preserve_material !== true ||
      !/\bmoss\b/i.test(material.name) ||
      material.userData.river_moss_quieting === true) return;

  const compile = material.onBeforeCompile;
  const cacheKey = material.customProgramCacheKey.bind(material);
  // Capture the previous key before replacing onBeforeCompile: Three's
  // default key reads that callback, so a bound call would read our new one.
  const previousKey = cacheKey();
  material.onBeforeCompile = function (shader, renderer) {
    compile.call(this, shader, renderer);
    shader.fragmentShader = shader.fragmentShader.replace(
      "#include <color_fragment>",
      `#include <color_fragment>
      float mossLuminance = dot(diffuseColor.rgb, vec3(0.2126, 0.7152, 0.0722));
      diffuseColor.rgb = mix(vec3(mossLuminance), diffuseColor.rgb, 0.72) * 0.90;`,
    );
  };
  material.customProgramCacheKey = () => `${previousKey}|river-moss-quiet-1`;
  material.userData.river_moss_quieting = true;
  material.needsUpdate = true;
}
