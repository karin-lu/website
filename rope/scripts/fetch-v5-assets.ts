// Pinned v5 runtime assets live in the fork's release store, outside Git.
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import assets from "../src/render3d/backgroundAssets.json";

export async function fetchV5Assets(): Promise<void> {
  const root = resolve(import.meta.dirname, "..");
  for (const asset of assets.runtime) {
    const destination = resolve(root, asset.path);
    const valid = (bytes: Uint8Array): boolean => bytes.length === asset.bytes &&
      createHash("sha256").update(bytes).digest("hex") === asset.sha256;
    if (existsSync(destination) && valid(readFileSync(destination))) continue;
    const response = await fetch(`${assets.baseUrl}/${asset.name}`);
    if (!response.ok) throw new Error(`V5 asset ${asset.name}: HTTP ${response.status}`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (!valid(bytes)) throw new Error(`V5 asset ${asset.name}: size or SHA-256 mismatch`);
    mkdirSync(dirname(destination), { recursive: true });
    const temporary = `${destination}.${process.pid}.tmp`;
    writeFileSync(temporary, bytes);
    renameSync(temporary, destination);
    console.log(`[v5 assets] ${asset.name}`);
  }
}

if (import.meta.main) await fetchV5Assets();
