// Publish this branch's river scene to the user's fork, without replacing the
// main repository's scene. Uses Git's existing GitHub credential helper.
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const repo = 'karin-lu/website';
const tag = 'foliage-assets-20261009';
const credential = spawnSync('git', ['credential', 'fill'], {
  input: 'protocol=https\nhost=github.com\n\n', encoding: 'utf8',
  env: { ...process.env, GIT_TERMINAL_PROMPT: '0' },
});
const token = credential.stdout?.split('\n').find(s => s.startsWith('password='))?.slice(9).trim();
if (credential.status !== 0 || !token) throw new Error('GitHub authentication unavailable');
const headers = { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' };
const base = `https://api.github.com/repos/${repo}/releases`;
let res = await fetch(`${base}/tags/${tag}`, { headers });
if (res.status === 404) res = await fetch(base, {
  method: 'POST', headers, body: JSON.stringify({ tag_name: tag, target_commitish: 'foliage',
    name: 'Foliage branch scene assets', prerelease: true,
    body: 'River scene with larger, fuller Blender-grown ivy for the foliage branch.' }),
});
if (!res.ok) throw new Error(`GitHub release request failed (${res.status})`);
const release = await res.json() as { upload_url: string; assets: {name:string}[] };
const bytes = readFileSync('public/scenes/river/scene.glb');
const hash = createHash('sha256').update(bytes).digest('hex');
const name = `scene-river-${hash.slice(0, 12)}.glb`;
if (!release.assets.some(a => a.name === name)) {
  const up = await fetch(`${release.upload_url.split('{')[0]}?name=${name}`, {
    method: 'POST', headers: { ...headers, 'Content-Type': 'model/gltf-binary' }, body: bytes,
  });
  if (!up.ok) throw new Error(`Scene upload failed (${up.status})`);
}
const manifestPath = 'src/render3d/sceneAssets.json';
const url = `https://github.com/${repo}/releases/download/${tag}/${name}`;
const download = await fetch(url);
if (!download.ok) throw new Error(`Public scene download failed (${download.status})`);
const downloaded = new Uint8Array(await download.arrayBuffer());
if (createHash('sha256').update(downloaded).digest('hex') !== hash)
  throw new Error('Published scene does not match the tested file');
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
manifest.river = { ...manifest.river, sha256: hash, bytes: bytes.length,
  url };
writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
console.log(`Published ${name} to ${repo}; scene manifest updated.`);
