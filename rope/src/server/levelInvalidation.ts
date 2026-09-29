import { normalizePath, type ViteDevServer } from "vite";

// Vite indexes files with forward slashes even on Windows. A filesystem path
// from path.join/watch must cross that boundary before consulting its graph.
export function invalidateLevelFile(server: Pick<ViteDevServer, "environments">, file: string): void {
  const id = normalizePath(file);
  for (const env of Object.values(server.environments)) {
    for (const mod of env.moduleGraph.getModulesByFile(id) ?? []) {
      env.moduleGraph.invalidateModule(mod);
    }
  }
}
