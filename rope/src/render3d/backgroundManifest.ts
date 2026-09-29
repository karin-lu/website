// A scenery package uses Three coordinates and metres, independently of the
// pixel units of the level file. Asset paths are relative to this manifest.
export interface BackgroundAsset {
  file: string;
  bytes?: number;
}

export interface BackgroundManifest {
  version: 1;
  colorSpace?: "srgb-display";
  camera: {
    fovYDeg: number;
    distance: number;
    origin: [number, number];
    zoomResponse?: number;
  };
  layers: (BackgroundAsset & { id: string })[];
  backdrop: BackgroundAsset & {
    worldWidth: number;
    worldHeight: number;
    origin: [number, number];
    pan: number;
  };
  // Zero-based indices in LevelData.bodies; level bodies have no persistent ID.
  hideBodyIds?: number[];
  // Replace only unbound Blender scene scenery; body-bound dressing stays.
  replaceSceneScenery?: boolean;
  // Linear RGB; applies only to opt-in textured foliage with baked lighting.
  foliageFog?: { color: [number, number, number]; near: number; far: number };
}

export function parseBackgroundManifest(value: unknown): BackgroundManifest {
  const data = value as BackgroundManifest | null;
  const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);
  const pair = (v: unknown): boolean => Array.isArray(v) && v.length === 2 && v.every(finite);
  const asset = (v: BackgroundAsset | undefined): boolean =>
    !!v && typeof v.file === "string" && v.file.trim().length > 0 &&
    (v.bytes === undefined || (finite(v.bytes) && v.bytes >= 0));
  const fog = data?.foliageFog;
  if (!data || data.version !== 1 || !data.camera || !data.backdrop ||
    !finite(data.camera.fovYDeg) || data.camera.fovYDeg <= 0 || data.camera.fovYDeg >= 180 ||
    !finite(data.camera.distance) || data.camera.distance <= 0 || !pair(data.camera.origin) ||
    (data.camera.zoomResponse !== undefined &&
      (!finite(data.camera.zoomResponse) || data.camera.zoomResponse < 0 || data.camera.zoomResponse > 1)) ||
    !Array.isArray(data.layers) || data.layers.length === 0 ||
    data.layers.some((layer) => !asset(layer) || typeof layer.id !== "string" || !layer.id) ||
    new Set(data.layers.map((layer) => layer.id)).size !== data.layers.length ||
    !asset(data.backdrop) || !finite(data.backdrop.worldWidth) || data.backdrop.worldWidth <= 0 ||
    !finite(data.backdrop.worldHeight) || data.backdrop.worldHeight <= 0 ||
    !pair(data.backdrop.origin) || !finite(data.backdrop.pan) || data.backdrop.pan < 0 ||
    (data.hideBodyIds !== undefined && (!Array.isArray(data.hideBodyIds) ||
      data.hideBodyIds.some((id) => !Number.isInteger(id) || id < 0))) ||
    (data.replaceSceneScenery !== undefined && typeof data.replaceSceneScenery !== "boolean") ||
    (fog !== undefined && (!fog || !Array.isArray(fog.color) || fog.color.length !== 3 ||
      fog.color.some((n) => !finite(n) || n < 0 || n > 1) ||
      !finite(fog.near) || fog.near < 0 || !finite(fog.far) || fog.far <= fog.near))) {
    throw new Error("invalid version 1 background manifest");
  }
  return data;
}

export function backgroundAssetUrl(manifestUrl: string, file: string): string {
  const base = "https://background.invalid/";
  const url = new URL(file, new URL(manifestUrl, base));
  return url.origin === new URL(base).origin ? url.pathname + url.search + url.hash : url.href;
}

export function backgroundStoredFiles(manifestUrl: string, manifest: BackgroundManifest):
  { file: string; bytes: number }[] {
  return [
    { file: manifestUrl, bytes: 0 },
    ...[...manifest.layers, manifest.backdrop].map((asset) => ({
      file: backgroundAssetUrl(manifestUrl, asset.file), bytes: asset.bytes ?? 0,
    })),
  ];
}
