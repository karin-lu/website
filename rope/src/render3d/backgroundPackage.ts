import * as THREE from "three";
import type { Camera } from "../render/camera";
import { gltfLoader } from "./assets";
import { withDownload } from "./download";
import { backgroundAssetUrl, parseBackgroundManifest, type BackgroundManifest } from "./backgroundManifest";
import { CAMERA_FAR, cameraDistance, threeY } from "./space";
import { applyQuietBackground, usesQuietBackground } from "./backgroundQuiet";
import { applyBackgroundMossQuieting } from "./backgroundMoss";

export interface BackgroundPackageLoader {
  manifest(url: string): Promise<BackgroundManifest>;
  layer(url: string, bytes: number): Promise<THREE.Object3D>;
  texture(url: string, bytes: number): Promise<THREE.Texture>;
}

const LOADER: BackgroundPackageLoader = {
  manifest: (url) => withDownload(url, 0, async (href) => {
    const response = await fetch(href);
    if (!response.ok) throw new Error(`background manifest returned ${response.status}`);
    return parseBackgroundManifest(await response.json());
  }),
  layer: async (url, bytes) => {
    const loading = gltfLoader();
    return withDownload(url, bytes, async (href) => (await (await loading).loadAsync(href)).scene);
  },
  texture: (url, bytes) => withDownload(url, bytes, (href) => new THREE.TextureLoader().loadAsync(href)),
};

// The only simulation conversion: package geometry already uses Three's world
// frame. Camera travel changes X/Y immediately; zero response keeps Z fixed.
export function syncBackgroundCamera(
  target: THREE.PerspectiveCamera, camera: Camera, manifest: BackgroundManifest,
): void {
  const reference = manifest.camera;
  const response = reference.zoomResponse ?? 0;
  target.fov = reference.fovYDeg;
  target.aspect = camera.viewportWidth / camera.viewportHeight;
  const distance = response === 0 ? reference.distance :
    reference.distance * Math.pow(cameraDistance(camera, reference.fovYDeg) / reference.distance, response);
  target.position.set(camera.position.x, threeY(camera.position.y), distance);
  target.quaternion.identity();
  target.far = Math.max(CAMERA_FAR, distance + CAMERA_FAR);
  target.updateProjectionMatrix();
  target.updateMatrixWorld();
}

export function backgroundPlateMapping(camera: THREE.PerspectiveCamera, manifest: BackgroundManifest): {
  repeatX: number; repeatY: number; offsetX: number; offsetY: number; covered: boolean;
} {
  const plate = manifest.backdrop;
  const height = 2 * camera.position.z * Math.tan(camera.fov * Math.PI / 360);
  const repeatX = height * camera.aspect / plate.worldWidth;
  const repeatY = height / plate.worldHeight;
  const offsetX = (1 - repeatX) / 2 + (camera.position.x - plate.origin[0]) * plate.pan / plate.worldWidth;
  const offsetY = (1 - repeatY) / 2 + (camera.position.y - plate.origin[1]) * plate.pan / plate.worldHeight;
  return {
    repeatX, repeatY, offsetX, offsetY,
    covered: offsetX >= 0 && offsetY >= 0 && offsetX + repeatX <= 1 && offsetY + repeatY <= 1,
  };
}

// All decoded resources belong to this instance, unlike the shared prop cache.
// Dispose each shared geometry/material/texture once, including late arrivals.
export function disposeBackgroundObjects(objects: readonly THREE.Object3D[], extraTextures: readonly THREE.Texture[] = []): void {
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>(extraTextures);
  for (const object of objects) object.traverse((node) => {
    const mesh = node as THREE.Mesh;
    if (mesh.geometry) geometries.add(mesh.geometry);
    if (mesh.material) for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      materials.add(material);
      for (const value of Object.values(material)) if ((value as THREE.Texture | null)?.isTexture) textures.add(value as THREE.Texture);
    }
  });
  for (const geometry of geometries) geometry.dispose();
  for (const material of materials) material.dispose();
  for (const texture of textures) {
    texture.dispose();
    // GLTFLoader may decode embedded textures to ImageBitmaps.
    const image = texture.image as { close?: () => void } | undefined;
    image?.close?.();
  }
}

export class BackgroundPackage {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(34, 16 / 9, 0.1, CAMERA_FAR);
  private readonly plateScene = new THREE.Scene();
  private readonly plateCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 2);
  private url: string | undefined;
  private generation = 0;
  private disposed = false;
  private loading: Promise<void> = Promise.resolve();
  private manifest: BackgroundManifest | null = null;
  private plate: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial> | null = null;
  private phase: "none" | "loading" | "ready" | "failed" = "none";
  private error: string | null = null;
  private plateCovered = true;

  constructor(private readonly loader: BackgroundPackageLoader = LOADER) {
    this.plateCamera.position.z = 1;
  }

  setPackage(url: string | undefined): void {
    if (this.disposed || url === this.url) return;
    this.url = url;
    const generation = ++this.generation;
    this.clear();
    this.error = null;
    this.phase = url ? "loading" : "none";
    this.loading = url ? this.load(url, generation) : Promise.resolve();
  }

  get ready(): boolean { return this.phase === "ready"; }
  get hideBodyIds(): readonly number[] { return this.manifest?.hideBodyIds ?? []; }
  get replaceSceneScenery(): boolean { return this.ready && this.manifest?.replaceSceneScenery === true; }

  status(): {
    url: string | null; phase: string; error: string | null; plateCovered: boolean;
    layers: number; hiddenBodies: readonly number[]; replaceSceneScenery: boolean;
    camera: { position: [number, number, number]; fovYDeg: number; aspect: number } | null;
  } {
    return {
      url: this.url ?? null, phase: this.phase, error: this.error, plateCovered: this.plateCovered,
      layers: this.scene.children.length, hiddenBodies: this.hideBodyIds,
      replaceSceneScenery: this.replaceSceneScenery,
      camera: this.ready ? {
        position: [this.camera.position.x, this.camera.position.y, this.camera.position.z],
        fovYDeg: this.camera.fov, aspect: this.camera.aspect,
      } : null,
    };
  }

  async wait(): Promise<void> { await this.loading; }

  private async load(url: string, generation: number): Promise<void> {
    let layers: THREE.Object3D[] = [];
    let texture: THREE.Texture | null = null;
    try {
      const manifest = parseBackgroundManifest(await this.loader.manifest(url));
      const quiet = usesQuietBackground(url);
      if (generation !== this.generation || this.disposed) return;
      const assets = [...manifest.layers, manifest.backdrop];
      const results = await Promise.allSettled(assets.map((asset, i) => {
        const href = backgroundAssetUrl(url, asset.file);
        return i < manifest.layers.length ? this.loader.layer(href, asset.bytes ?? 0) : this.loader.texture(href, asset.bytes ?? 0);
      }));
      const failures: unknown[] = [];
      results.forEach((result, i) => {
        if (result.status === "rejected") failures.push(result.reason);
        else if (i < manifest.layers.length) layers.push(result.value as THREE.Object3D);
        else texture = result.value as THREE.Texture;
      });
      if (failures.length) throw failures[0];
      if (generation !== this.generation || this.disposed) {
        disposeBackgroundObjects(layers, texture ? [texture] : []);
        return;
      }
      for (const layer of layers) {
        layer.traverse((object) => {
          const mesh = object as THREE.Mesh;
          if (!mesh.isMesh) return;
          mesh.castShadow = false;
          mesh.receiveShadow = false;
          // Keep glTF's unlit material and COLOR_0. Baked display appearance
          // must bypass gameplay ACES tone mapping, just like the image plate.
          for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
            material.toneMapped = false;
            if (quiet) {
              applyBackgroundMossQuieting(material);
              applyQuietBackground(material);
            }
            const textured = material as THREE.Material & { map?: THREE.Texture | null; fog?: boolean };
            // Stone vertex colors already include atmosphere. Only preserved
            // foliage textures with baked lighting receive the optional haze.
            const litTexture = textured.map?.isTexture === true &&
              material.userData.river_preserve_material === true &&
              material.userData.river_preserved_bake_lighting === true;
            const useFog = !!manifest.foliageFog && litTexture;
            // Use the main framebuffer's existing MSAA for small cutout edges.
            if (litTexture && material.alphaTest > 0) material.alphaToCoverage = true;
            if (textured.fog !== useFog) {
              textured.fog = useFog;
              material.needsUpdate = true;
            }
          }
        });
        this.scene.add(layer);
      }
      const plateTexture = texture! as THREE.Texture;
      plateTexture.colorSpace = THREE.SRGBColorSpace;
      plateTexture.wrapS = plateTexture.wrapT = THREE.ClampToEdgeWrapping;
      this.plate = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.MeshBasicMaterial({
        map: plateTexture, depthWrite: false, depthTest: false, toneMapped: false,
      }));
      this.plate.frustumCulled = false;
      if (quiet) applyQuietBackground(this.plate.material, true);
      this.plateScene.add(this.plate);
      const fog = manifest.foliageFog;
      this.scene.fog = fog ? new THREE.Fog(
        new THREE.Color().setRGB(...fog.color, THREE.LinearSRGBColorSpace), fog.near, fog.far,
      ) : null;
      this.manifest = manifest;
      this.phase = "ready";
    } catch (error) {
      disposeBackgroundObjects(layers, texture ? [texture] : []);
      if (generation !== this.generation || this.disposed) return;
      this.phase = "failed";
      this.error = error instanceof Error ? error.message : String(error);
      console.warn(`[background] ${url} failed; retaining the level background:`, error);
    }
  }

  sync(camera: Camera): void {
    if (!this.manifest || !this.plate) return;
    syncBackgroundCamera(this.camera, camera, this.manifest);
    const mapping = backgroundPlateMapping(this.camera, this.manifest);
    const texture = this.plate.material.map!;
    texture.repeat.set(mapping.repeatX, mapping.repeatY);
    texture.offset.set(mapping.offsetX, mapping.offsetY);
    this.plateCovered = mapping.covered;
  }

  // One scoped composition. Existing viewport/scissor and render target remain
  // untouched. The gameplay depth starts empty and its scene background is
  // restored even when rendering throws.
  render(renderer: THREE.WebGLRenderer, gameplay: THREE.Scene, camera: THREE.Camera): void {
    if (!this.ready) { renderer.render(gameplay, camera); return; }
    const autoClear = renderer.autoClear;
    const autoReset = renderer.info.autoReset;
    const shadowEnabled = renderer.shadowMap.enabled;
    const background = gameplay.background;
    try {
      renderer.autoClear = false;
      if (autoReset) renderer.info.reset();
      renderer.info.autoReset = false;
      renderer.clear(true, true, true);
      renderer.shadowMap.enabled = false;
      renderer.render(this.plateScene, this.plateCamera);
      renderer.render(this.scene, this.camera);
      renderer.clearDepth();
      renderer.shadowMap.enabled = shadowEnabled;
      gameplay.background = null;
      renderer.render(gameplay, camera);
    } finally {
      gameplay.background = background;
      renderer.shadowMap.enabled = shadowEnabled;
      renderer.autoClear = autoClear;
      renderer.info.autoReset = autoReset;
    }
  }

  async prewarm(renderer: THREE.WebGLRenderer): Promise<void> {
    if (!this.ready) return;
    await renderer.compileAsync(this.plateScene, this.plateCamera);
    await renderer.compileAsync(this.scene, this.camera);
    for (const root of [this.scene, this.plateScene]) root.traverse((object) => {
      const mesh = object as THREE.Mesh;
      if (!mesh.material) return;
      for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
        for (const value of Object.values(material)) {
          const texture = value as THREE.Texture | null;
          if (texture?.isTexture && texture.image) renderer.initTexture(texture);
        }
      }
    });
  }

  // Upload culled geometry in the warm frame, then restore authored visibility.
  warmDraw(renderer: THREE.WebGLRenderer): void {
    if (!this.ready) return;
    const restore: Array<() => void> = [];
    this.scene.traverse((object) => {
      const { visible, frustumCulled } = object;
      restore.push(() => { object.visible = visible; object.frustumCulled = frustumCulled; });
      object.visible = true;
      object.frustumCulled = false;
    });
    const autoClear = renderer.autoClear;
    const shadows = renderer.shadowMap.enabled;
    try {
      renderer.autoClear = false;
      renderer.shadowMap.enabled = false;
      renderer.render(this.plateScene, this.plateCamera);
      renderer.render(this.scene, this.camera);
    } finally {
      renderer.autoClear = autoClear;
      renderer.shadowMap.enabled = shadows;
      for (const put of restore) put();
    }
  }

  private clear(): void {
    disposeBackgroundObjects([this.scene, this.plateScene]);
    this.scene.clear();
    this.scene.fog = null;
    this.plateScene.clear();
    this.plate = null;
    this.manifest = null;
    this.plateCovered = true;
  }

  dispose(): void {
    this.disposed = true;
    ++this.generation;
    this.clear();
    this.phase = "none";
  }
}
