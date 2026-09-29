import assert from "node:assert/strict";
import type { ViteDevServer } from "vite";
import { invalidateLevelFile } from "../src/server/levelInvalidation";
import { BallLevel } from "../src/level/ballLevel";
import { Level } from "../src/level/level";
import { modelFromDisk, modelToDisk } from "../src/editor/model";
import { spawnAtCheckpoint, spawnWithoutEntry, type RawLevelData } from "../src/level/levelFormat";

// The graph uses normalized IDs. The reported failure looked up a native
// Windows path and invalidated nothing, leaving normal play on older JSON.
const windowsFile = String.raw`C:\Users\Karin\projects\trisball\website\rope\levels\ball.json`;
const normalized = windowsFile.replaceAll("\\", "/");
const nativeFile = process.platform === "win32" ? windowsFile : normalized;
const client = { id: normalized };
const clientQuery = { id: `${normalized}?import` };
const ssr = { id: normalized };
const invalidated: unknown[] = [];
const lookups: string[] = [];
const graph = (mods: unknown[]) => ({
  getModulesByFile: (file: string) => {
    lookups.push(file);
    return file === normalized ? new Set(mods) : undefined;
  },
  invalidateModule: (mod: unknown) => invalidated.push(mod),
});
const server = {
  environments: { client: { moduleGraph: graph([client, clientQuery]) }, ssr: { moduleGraph: graph([ssr]) } },
} as unknown as Pick<ViteDevServer, "environments">;
if (process.platform === "win32") assert.equal(graph([client]).getModulesByFile(windowsFile), undefined);
lookups.length = 0;
invalidateLevelFile(server, nativeFile);
assert.deepEqual(lookups, [normalized, normalized]);
assert.deepEqual(invalidated, [client, clientQuery, ssr]);
invalidated.length = 0;
invalidateLevelFile(server, normalized);
assert.deepEqual(invalidated, [client, clientQuery, ssr]);
invalidated.length = 0;
invalidateLevelFile(server, `${normalized}.unrelated`);
assert.deepEqual(invalidated, []);

// Normal play, checkpoint/reset construction and editor test construction all
// retain the package without altering the physics data they build from.
const raw: RawLevelData = {
  player: { x: 100, y: 200, radius: 8 }, bodies: [],
  checkpoints: [{ name: "middle", x: 500, y: 600 }],
  backgroundPackage: "/backgrounds/river/package.json",
};
for (const data of [raw, spawnAtCheckpoint(raw, "middle"), spawnWithoutEntry(modelToDisk(modelFromDisk(raw)))]) {
  assert.equal(new BallLevel(data).visualSource.data.backgroundPackage, raw.backgroundPackage);
  assert.equal(new Level(data).visualSource.data.backgroundPackage, raw.backgroundPackage);
}
console.log("level invalidation: Windows/client/SSR cache keys and playable/editor package propagation passed");
