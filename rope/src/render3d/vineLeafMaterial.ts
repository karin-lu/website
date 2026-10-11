import * as THREE from "three";

// The attachment stays fixed. Secondary movement and its derivative both vanish
// at the root; the normal follows the same deformation as the blade and shadow.
const leafVertexDeclarations = /* glsl */`
attribute vec4 leafShape;
attribute float leafFaceTurn;
varying vec2 vBotanicalUv;
vec3 botanicalBasePosition(vec3 p) {
  float t = uv.y;
  p.x += leafShape.x * sin(3.14159265 * t) + leafShape.z * t * t;
  p.z += leafShape.y * t * t * t + leafShape.w * t * t;
  return p;
}
vec3 botanicalPosition(vec3 p) {
  p = botanicalBasePosition(p);
  float turn = leafFaceTurn * smoothstep(.10, .45, uv.y);
  float c = cos(turn), s = sin(turn);
  p.xz = mat2(c, -s, s, c) * p.xz;
  return p;
}
`;

function patchLeafVertex(source: string, normals: boolean): string {
  source = source.replace("#include <common>", "#include <common>\n" + leafVertexDeclarations)
    .replace("#include <begin_vertex>", "#include <begin_vertex>\ntransformed = botanicalPosition(transformed);\nvBotanicalUv = uv;");
  if (normals) source = source.replace("#include <beginnormal_vertex>", /* glsl */`
    #include <beginnormal_vertex>
    float leafT = uv.y;
    float dxdy = leafShape.x * 3.14159265 * cos(3.14159265 * leafT) + 2.0 * leafShape.z * leafT;
    float dzdy = 3.0 * leafShape.y * leafT * leafT + 2.0 * leafShape.w * leafT;
    float leafDyDt = max(.5, 1.0 - .24 * leafT * leafT);
    objectNormal.y -= (dxdy * objectNormal.x + dzdy * objectNormal.z) / leafDyDt;
    float leafU = clamp((leafT - .10) / .35, 0.0, 1.0);
    float leafAngle = leafFaceTurn * leafU * leafU * (3.0 - 2.0 * leafU);
    float leafTurnDerivative = leafFaceTurn * 6.0 * leafU * (1.0 - leafU) / (.35 * leafDyDt);
    objectNormal.xz = mat2(cos(leafAngle), -sin(leafAngle), sin(leafAngle), cos(leafAngle)) * objectNormal.xz;
    vec3 turnedLeaf = botanicalPosition(position);
    objectNormal.y -= leafTurnDerivative * (turnedLeaf.z * objectNormal.x - turnedLeaf.x * objectNormal.z);
  `);
  return source;
}

export function makeVineLeafMaterial(): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: .68, side: THREE.DoubleSide });
  material.customProgramCacheKey = () => "botanical-vine-leaf-v2";
  material.onBeforeCompile = shader => {
    shader.vertexShader = patchLeafVertex(shader.vertexShader, true);
    shader.fragmentShader = shader.fragmentShader.replace("#include <common>", /* glsl */`
      #include <common>
      varying vec2 vBotanicalUv;
      float botanicalVeins(vec2 p) {
        float rib = 1.0 - smoothstep(.012, .031, abs(p.x - .5));
        float branches = abs(fract(p.y * 5.0 - abs(p.x - .5) * 1.65) - .5);
        float vein = (1.0 - smoothstep(.025, .06, branches)) * smoothstep(.04, .12, abs(p.x - .5));
        return max(rib, vein * .5);
      }
    `).replace("#include <color_fragment>", /* glsl */`
      #include <color_fragment>
      float leafVein = botanicalVeins(vBotanicalUv);
      float leafPaint = smoothstep(-.2, .2, sin(vBotanicalUv.y * 8.0 + sin(vBotanicalUv.x * 5.0) * 1.3));
      diffuseColor.rgb *= mix(vec3(.88, .94, .82), vec3(1.12, 1.04, .9), leafPaint);
      diffuseColor.rgb *= 1.0 - .17 * leafVein;
      if (!gl_FrontFacing) diffuseColor.rgb *= vec3(1.1, 1.12, 1.02);
    `).replace("#include <roughnessmap_fragment>", /* glsl */`
      #include <roughnessmap_fragment>
      roughnessFactor = clamp(roughnessFactor + .12 * leafVein - .055 * leafPaint, .5, .9);
    `).replace("#include <lights_physical_pars_fragment>", /* glsl */`
      #include <lights_physical_pars_fragment>
      void RE_Direct_Botanical(const in IncidentLight light, const in vec3 position, const in vec3 n,
        const in vec3 viewDir, const in vec3 coatNormal, const in PhysicalMaterial mat, inout ReflectedLight reflected) {
        RE_Direct_Physical(light, position, n, viewDir, coatNormal, mat, reflected);
        float back = max(0.0, -dot(n, light.direction));
        float edge = smoothstep(.2, .47, abs(vBotanicalUv.x - .5));
        float thin = (.11 + .13 * edge) * (1.0 - .65 * botanicalVeins(vBotanicalUv));
        reflected.directDiffuse += light.color * mat.diffuseColor * vec3(1.12, 1.0, .72) * back * thin * RECIPROCAL_PI;
      }
      #undef RE_Direct
      #define RE_Direct RE_Direct_Botanical
    `);
  };
  return material;
}

export function makeVineLeafShadowMaterial(distance: boolean): THREE.Material {
  const material = distance ? new THREE.MeshDistanceMaterial({ side: THREE.DoubleSide }) :
    new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking, side: THREE.DoubleSide });
  material.customProgramCacheKey = () => "botanical-vine-shadow-v2";
  material.onBeforeCompile = shader => { shader.vertexShader = patchLeafVertex(shader.vertexShader, false); };
  return material;
}
