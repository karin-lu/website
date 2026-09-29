// Run: node verify_package.mjs <package-directory>
// Decodes Meshopt data and verifies the actual exported appearance and route coverage.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

export const here = path.dirname(fileURLToPath(import.meta.url));
export const require = createRequire(path.resolve(here, '../../../rope/package.json'));
export const {NodeIO, Document, PropertyType, Logger} = require('@gltf-transform/core');
export const {ALL_EXTENSIONS, EXTMeshoptCompression, KHRMaterialsUnlit} = require('@gltf-transform/extensions');
export const {MeshoptEncoder, MeshoptDecoder} = require('meshoptimizer');
const {getBounds} = require('@gltf-transform/functions');
const sharp = require('sharp');

export const assert = (condition, message) => { if (!condition) throw new Error(message); };
export const sha256 = (data) => crypto.createHash('sha256').update(data).digest('hex');
export const fileHash = (file) => sha256(fs.readFileSync(file));
export const json = (file) => JSON.parse(fs.readFileSync(file, 'utf8'));
export function atomicJSON(file, data) {
  const temp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(temp, `${JSON.stringify(data, null, 2)}\n`);
  fs.renameSync(temp, file);
}
export async function createIO() {
  await Promise.all([MeshoptEncoder.ready, MeshoptDecoder.ready]);
  return new NodeIO().setLogger(new Logger(Logger.Verbosity.WARN)).registerExtensions(ALL_EXTENSIONS).registerDependencies({
    'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptDecoder,
  });
}

export function assetPath(directory, asset) {
  assert(asset && typeof asset.file === 'string' && path.basename(asset.file) === asset.file &&
    !asset.file.includes('\\') && !asset.file.includes('/') && asset.file !== '.', 'Asset must be a local package basename');
  const file = path.join(directory, asset.file);
  assert(fs.existsSync(file), `Missing package asset: ${asset.file}`);
  const bytes = fs.statSync(file).size;
  assert(Number.isInteger(asset.bytes) && bytes === asset.bytes, `Byte count mismatch: ${asset.file}`);
  const hash = fileHash(file);
  assert(asset.sha256 === hash, `SHA-256 mismatch: ${asset.file}`);
  assert(asset.file.includes(hash.slice(0, 12)), `Filename is not content hashed: ${asset.file}`);
  return file;
}

export function validateManifest(manifest) {
  const finite = (v) => typeof v === 'number' && Number.isFinite(v);
  const pair = (v) => Array.isArray(v) && v.length === 2 && v.every(finite);
  assert(manifest?.version === 1 && manifest.colorSpace === 'srgb-display', 'Expected version 1 display-color package');
  assert(Array.isArray(manifest.layers) && manifest.layers.length === 2 &&
    [...manifest.layers.map((l) => l.id)].sort().join(',') === 'far,near', 'Expected one near and one far layer');
  const camera = manifest.camera, plate = manifest.backdrop;
  assert(camera && finite(camera.fovYDeg) && camera.fovYDeg > 0 && camera.fovYDeg < 180 &&
    finite(camera.distance) && camera.distance > 0 && pair(camera.origin), 'Invalid background camera');
  assert((camera.zoomResponse ?? 0) === 0, 'Route verification requires the authored fixed background camera distance');
  assert(plate && finite(plate.worldWidth) && plate.worldWidth > 0 && finite(plate.worldHeight) &&
    plate.worldHeight > 0 && pair(plate.origin) && finite(plate.pan) && plate.pan >= 0, 'Invalid image plate mapping');
  assert(manifest.hideBodyIds === undefined || (Array.isArray(manifest.hideBodyIds) &&
    manifest.hideBodyIds.every((id) => Number.isInteger(id) && id >= 0)), 'Invalid hidden foreground body indices');
  if (manifest.foliageFog !== undefined) {
    const fog = manifest.foliageFog;
    assert(fog && Array.isArray(fog.color) && fog.color.length === 3 && fog.color.every((v) => finite(v) && v >= 0 && v <= 1) &&
      finite(fog.near) && finite(fog.far) && fog.near >= 0 && fog.far > fog.near, 'Invalid preserved foliage fog');
  }
}

export function rawGLB(file) {
  const raw = fs.readFileSync(file);
  assert(raw.length >= 20 && raw.readUInt32LE(0) === 0x46546c67 && raw.readUInt32LE(4) === 2 &&
    raw.readUInt32LE(8) === raw.length && raw.readUInt32LE(16) === 0x4e4f534a, 'Invalid GLB container');
  const doc = JSON.parse(raw.subarray(20, 20 + raw.readUInt32LE(12)).toString('utf8').trim());
  assert((doc.buffers ?? []).every((b) => !b.uri) && (doc.images ?? []).every((i) => !i.uri), 'GLB has external references');
  assert(!(doc.cameras?.length || doc.skins?.length || doc.animations?.length),
    'Background layer contains cameras, skins or animation');
  if (doc.images?.length || doc.textures?.length) {
    const binStart = 20 + raw.readUInt32LE(12);
    assert(binStart + 8 <= raw.length && raw.readUInt32LE(binStart + 4) === 0x004e4942, 'Missing embedded image buffer');
    const bin = raw.subarray(binStart + 8, binStart + 8 + raw.readUInt32LE(binStart));
    for (const image of doc.images ?? []) {
      const view = doc.bufferViews?.[image.bufferView];
      assert(Number.isInteger(image.bufferView) && view?.buffer === 0 && Number.isInteger(view.byteLength) && view.byteLength > 0 &&
        Number.isInteger(view.byteOffset ?? 0) && (view.byteOffset ?? 0) >= 0 && (view.byteOffset ?? 0) + view.byteLength <= bin.length,
        'Invalid embedded image buffer view');
      const bytes = bin.subarray(view.byteOffset ?? 0, (view.byteOffset ?? 0) + view.byteLength);
      assert(image.mimeType === 'image/png' ? bytes.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10])) :
        image.mimeType === 'image/jpeg' && bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255, 'Unsupported or invalid embedded image');
    }
    for (const texture of doc.textures ?? []) {
      assert(Number.isInteger(texture.source) && doc.images?.[texture.source], 'Invalid embedded texture source');
      assert(texture.sampler === undefined || (Number.isInteger(texture.sampler) && doc.samplers?.[texture.sampler]), 'Invalid texture sampler');
    }
    for (const sampler of doc.samplers ?? []) {
      assert([undefined,9728,9729].includes(sampler.magFilter) && [undefined,9728,9729,9984,9985,9986,9987].includes(sampler.minFilter) &&
        [undefined,33071,33648,10497].includes(sampler.wrapS) && [undefined,33071,33648,10497].includes(sampler.wrapT), 'Invalid texture sampler settings');
    }
  }
  assert(!(doc.extensionsUsed ?? []).some((name) => /lights|physics|collision/i.test(name)),
    'Background layer contains lighting or physics extensions');
  return doc;
}

function vertexToken(primitive, index, semantics) {
  return semantics.map((semantic) => `${semantic}:${primitive.getAttribute(semantic).getElement(index, []).join(',')}`).join(';');
}
function materialToken(material) {
  const texture = material.getBaseColorTexture(), info = material.getBaseColorTextureInfo();
  return JSON.stringify({base: material.getBaseColorFactor(), alpha: material.getAlphaMode(),
    cutoff: material.getAlphaCutoff(), doubleSided: material.getDoubleSided(), unlit: true,
    ...(texture ? {imageSha256: sha256(texture.getImage()), mimeType: texture.getMimeType(),
      texCoord: info.getTexCoord(), wrap: [info.getWrapS(), info.getWrapT()], filters: [info.getMagFilter(), info.getMinFilter()]} : {})});
}
function triangleDigest(primitive) {
  const semantics = primitive.listSemantics().filter((s) => s !== 'COLOR_1').sort();
  const positions = primitive.getAttribute('POSITION');
  const tokens = Array.from({length: positions.getCount()}, (_, i) => vertexToken(primitive, i, semantics));
  const indices = primitive.getIndices()?.getArray();
  const count = indices?.length ?? positions.getCount();
  const hashes = [];
  const material = materialToken(primitive.getMaterial());
  for (let i = 0; i < count; i += 3) {
    const corners = [0, 1, 2].map((j) => tokens[indices ? indices[i + j] : i + j]);
    // Triangle order and cyclic corner order may change during Meshopt reordering.
    const rotations = [0, 1, 2].map((start) => [0, 1, 2].map((j) => corners[(start + j) % 3]).join('|'));
    hashes.push(sha256(`${material}|${rotations.sort()[0]}`));
  }
  return hashes;
}

export function documentFacts(document, layer, {allowColor1 = false, signatures = true} = {}) {
  const root = document.getRoot();
  assert(root.listScenes().length === 1, 'Layer must contain one scene');
  assert(root.listCameras().length === 0 && root.listSkins().length === 0 && root.listAnimations().length === 0,
    'Layer contains non-background resources');
  for (const accessor of root.listAccessors()) {
    const array = accessor.getArray();
    assert(array && array.every(Number.isFinite), `Nonfinite decoded accessor: ${accessor.getName()}`);
  }
  const prefix = layer === 'near' ? '10_BACKGROUND_NEAR' : '20_BACKGROUND_FAR';
  const pattern = new RegExp(`^${prefix}/-?\\d+/-?\\d+(?:/preserved)?$`);
  const nodes = [], names = new Set(), usedTextures = new Set();
  let triangles = 0, primitives = 0, vertices = 0, bakedVertices = 0, litVertices = 0, texturedPrimitives = 0;
  const colorMin = [Infinity, Infinity, Infinity, Infinity], colorMax = [-Infinity, -Infinity, -Infinity, -Infinity];
  for (const node of root.listNodes()) {
    const name = node.getName(), extras = node.getExtras(), mesh = node.getMesh();
    assert(pattern.test(name) && !names.has(name), `Unexpected or duplicate spatial cell: ${name}`);
    names.add(name);
    assert(mesh && extras.background_only === true && extras.depth_layer === layer, `Bad cell metadata: ${name}`);
    assert(name.endsWith('/preserved') === (extras.river_preserve_material === true), `Preserved cell metadata mismatch: ${name}`);
    assert(extras.river_preserved_bake_lighting !== true || extras.river_preserve_material === true, `Card lighting on non-preserved cell: ${name}`);
    assert(!Object.entries(extras).some(([key, value]) => /reference|collision|physics|rigid|body.?id/i.test(key) && value),
      `Reference or collision metadata leaked into ${name}`);
    const matrix = node.getWorldMatrix();
    assert(matrix.every(Number.isFinite), `Nonfinite transform: ${name}`);
    const hashes = [];
    let nodeTriangles = 0;
    for (const primitive of mesh.listPrimitives()) {
      primitives++;
      assert(primitive.getMode() === 4 && primitive.listTargets().length === 0, `Cell is not static triangles: ${name}`);
      const positions = primitive.getAttribute('POSITION'), colors = primitive.getAttribute('COLOR_0');
      assert(positions && positions.getElementSize() === 3 && positions.getCount() > 0, `Missing positions: ${name}`);
      assert(allowColor1 || !primitive.getAttribute('COLOR_1'), `Unused COLOR_1 remains: ${name}`);
      assert(primitive.listAttributes().every((a) => a.getCount() === positions.getCount()), `Mismatched vertex attribute count: ${name}`);
      const material = primitive.getMaterial();
      assert(material?.getExtension('KHR_materials_unlit'), `Cell does not use KHR_materials_unlit: ${name}`);
      const texture = material.getBaseColorTexture();
      if (extras.river_preserve_material === true) {
        const uv = primitive.getAttribute('TEXCOORD_0');
        const lit = extras.river_preserved_bake_lighting === true;
        assert(lit === (material.getExtras().river_preserved_bake_lighting === true), `Card lighting metadata mismatch: ${name}`);
        if (lit) {
          assert(colors && colors.getElementSize() === 4 && colors.getCount() === positions.getCount() &&
            Array.from({length: colors.getCount()}, (_, i) => colors.getElement(i, [])).every((rgba) =>
              rgba.every((v) => Number.isFinite(v) && v >= 0 && v <= 1) && rgba[3] === 1),
            `Invalid baked card irradiance COLOR_0: ${name}`);
          litVertices += positions.getCount();
        } else assert(!colors, `Unlit v2 atlas has unexpected vertex colors: ${name}`);
        assert(texture && material.getExtras().river_preserve_material === true && uv &&
          uv.getElementSize() === 2 && uv.getCount() === positions.getCount() &&
          uv.getArray().every((v) => Number.isFinite(v) && v >= 0 && v <= 1), `Invalid preserved atlas UVs/material: ${name}`);
        assert(material.getBaseColorTextureInfo().getTexCoord() === 0 &&
          material.getBaseColorTextureInfo().listExtensions().length === 0, `Unsupported preserved texture mapping: ${name}`);
        assert(['MASK','OPAQUE'].includes(material.getAlphaMode()) && Number.isFinite(material.getAlphaCutoff()) &&
          material.getAlphaCutoff() >= 0 && material.getAlphaCutoff() <= 1 &&
          material.getBaseColorFactor().every((v) => Number.isFinite(v) && v >= 0 && v <= 1) &&
          material.getEmissiveFactor().every((v) => v === 0) && !material.getEmissiveTexture() &&
          !material.getNormalTexture() && !material.getOcclusionTexture() && !material.getMetallicRoughnessTexture() &&
          material.listExtensions().every((e) => e.extensionName === 'KHR_materials_unlit'), `Unsupported preserved atlas material: ${name}`);
        assert(texture.getImage()?.length && ['image/png','image/jpeg'].includes(texture.getMimeType()) &&
          (material.getAlphaMode() !== 'MASK' || texture.getMimeType() === 'image/png'), `Invalid preserved atlas image: ${name}`);
        texturedPrimitives++;
        usedTextures.add(texture);
      } else {
        assert(colors && [3, 4].includes(colors.getElementSize()) && colors.getCount() === positions.getCount(), `Missing baked COLOR_0: ${name}`);
        assert(material.getBaseColorFactor().every((v) => v === 1) && !texture &&
          material.getEmissiveFactor().every((v) => v === 0), `Baked base color is modified by material: ${name}`);
        bakedVertices += positions.getCount();
      }
      const indices = primitive.getIndices()?.getArray();
      const count = indices?.length ?? positions.getCount();
      assert(count > 0 && count % 3 === 0 && (!indices || indices.every((i) => Number.isInteger(i) && i >= 0 && i < positions.getCount())), `Invalid triangles: ${name}`);
      nodeTriangles += count / 3; vertices += positions.getCount();
      for (let i = 0; i < positions.getCount(); i++) {
        const p = positions.getElement(i, []), c = colors?.getElement(i, []);
        const worldZ = matrix[2] * p[0] + matrix[6] * p[1] + matrix[10] * p[2] + matrix[14];
        assert(worldZ < 0, `Background geometry crosses gameplay depth: ${name}`);
        if (c?.length === 3) c.push(1);
        c?.forEach((value, axis) => {
          assert(Number.isFinite(value) && value >= 0 && value <= 1, `Color outside [0,1]: ${name}`);
          colorMin[axis] = Math.min(colorMin[axis], value); colorMax[axis] = Math.max(colorMax[axis], value);
        });
      }
      if (signatures) for (const hash of triangleDigest(primitive)) hashes.push(hash);
    }
    assert(nodeTriangles > 0, `Empty cell: ${name}`);
    triangles += nodeTriangles;
    nodes.push({name, extras, matrix, triangles: nodeTriangles,
      ...(signatures ? {appearanceSha256: sha256(hashes.sort().join(''))} : {})});
  }
  assert(nodes.length > 0 && (bakedVertices ? colorMax[0] > colorMin[0] : texturedPrimitives > 0), 'Layer has no varying baked appearance or atlas');
  assert(root.listTextures().every((texture) => usedTextures.has(texture)), 'Layer contains an unused or unsupported texture');
  const bounds = getBounds(root.listScenes()[0]);
  assert([...bounds.min, ...bounds.max].every(Number.isFinite) && bounds.max[2] < 0, 'Invalid decoded background bounds');
  nodes.sort((a, b) => a.name.localeCompare(b.name));
  return {cells: nodes.length, triangles, primitives, vertices, bounds,
    colors: {min: bakedVertices || litVertices ? colorMin : null, max: bakedVertices || litVertices ? colorMax : null}, nodes,
    requiredExtensions: root.listExtensionsRequired().map((e) => e.extensionName).sort()};
}

export async function validateEmbeddedTextures(document) {
  for (const texture of document.getRoot().listTextures()) {
    const image = texture.getImage();
    assert(image?.length, 'Embedded texture is empty');
    const metadata = await sharp(image, {failOn: 'error', limitInputPixels: 8192 * 8192}).metadata();
    assert(['png','jpeg'].includes(metadata.format) && metadata.width > 0 && metadata.height > 0,
      'Embedded texture has unsupported encoding or dimensions');
    assert(texture.getMimeType() === `image/${metadata.format}`, 'Embedded texture MIME does not match encoding');
    await sharp(image, {failOn: 'error', limitInputPixels: 8192 * 8192}).raw().toBuffer();
    for (const material of document.getRoot().listMaterials()) if (material.getBaseColorTexture() === texture && material.getAlphaMode() === 'MASK') {
      assert(metadata.hasAlpha, 'Masked atlas must contain an alpha channel');
    }
  }
}

export function compareFacts(before, after) {
  const geometryBefore = before.nodes.map((n) => [n.name, n.extras, n.matrix, n.triangles, n.appearanceSha256]);
  const geometryAfter = after.nodes.map((n) => [n.name, n.extras, n.matrix, n.triangles, n.appearanceSha256]);
  assert(JSON.stringify(geometryBefore) === JSON.stringify(geometryAfter), 'Optimization changed a spatial cell, triangle or decoded vertex attribute');
  assert(JSON.stringify(before.bounds) === JSON.stringify(after.bounds) && JSON.stringify(before.colors) === JSON.stringify(after.colors),
    'Optimization changed decoded bounds or color bounds');
}

function bezier(a, b, t) {
  const q = 1 - t;
  return ['x', 'y'].map((axis) => q ** 3 * a[axis] + 3 * q ** 2 * t * (a[axis] + (a[`out${axis.toUpperCase()}`] ?? 0)) +
    3 * q * t ** 2 * (b[axis] + (b[`in${axis.toUpperCase()}`] ?? 0)) + t ** 3 * b[axis]);
}
export function levelRoute(origin) {
  const levelFile = path.resolve(here, '../../../rope/levels/ball.json');
  const route = json(levelFile).cameraPaths[0], verts = route.verts;
  const world = ([x, y]) => [(route.x + x) * .01, -(route.y + y) * .01];
  assert((route.rot ?? 0) === 0, 'Route verification requires the saved unrotated level Bezier');
  const coarse = [];
  for (let i = 0; i < verts.length - 1; i++) for (let j = 0; j < 12; j++) coarse.push({i, t: j / 12, p: world(bezier(verts[i], verts[i + 1], j / 12))});
  coarse.push({i: verts.length - 2, t: 1, p: world([verts.at(-1).x, verts.at(-1).y])});
  const nearest = coarse.reduce((best, item) => Math.hypot(item.p[0] - origin[0], item.p[1] - origin[1]) <
    Math.hypot(best.p[0] - origin[0], best.p[1] - origin[1]) ? item : best);
  const points = [origin];
  for (let i = nearest.i; i < verts.length - 1; i++) {
    const start = i === nearest.i ? nearest.t : 0;
    for (let j = 0; j <= 64; j++) points.push(world(bezier(verts[i], verts[i + 1], start + (1 - start) * j / 64)));
    // Include exact scalar extrema, so a curve cannot escape between samples.
    for (const axis of ['x', 'y']) {
      const a = verts[i], b = verts[i + 1], p0 = a[axis], p1 = p0 + (a[`out${axis.toUpperCase()}`] ?? 0);
      const p3 = b[axis], p2 = p3 + (b[`in${axis.toUpperCase()}`] ?? 0);
      const A = -p0 + 3 * p1 - 3 * p2 + p3, B = 2 * (p0 - 2 * p1 + p2), C = p1 - p0;
      const discriminant = B * B - 4 * A * C;
      const roots = Math.abs(A) < 1e-12 ? (Math.abs(B) < 1e-12 ? [] : [-C / B]) :
        discriminant < 0 ? [] : [(-B - Math.sqrt(discriminant)) / (2 * A), (-B + Math.sqrt(discriminant)) / (2 * A)];
      for (const t of roots) if (t > start && t < 1) points.push(world(bezier(a, b, t)));
    }
  }
  return {points, file: 'rope/levels/ball.json', sha256: fileHash(levelFile)};
}

export async function atlasFacts(directory, manifest) {
  const plate = manifest.backdrop, camera = manifest.camera;
  const file = assetPath(directory, plate);
  const {data, info} = await sharp(file).ensureAlpha().raw().toBuffer({resolveWithObject: true});
  assert(info.width > 0 && info.height > 0 && Math.abs(info.width / info.height - plate.worldWidth / plate.worldHeight) < .002,
    'Atlas dimensions do not match the authored plate aspect');
  let min = 255, max = 0;
  for (let i = 0; i < data.length; i += 4) {
    assert(data[i + 3] === 255, 'Atlas has transparent pixels');
    for (let c = 0; c < 3; c++) { min = Math.min(min, data[i + c]); max = Math.max(max, data[i + c]); }
  }
  assert(max > min, 'Atlas contains no image variation');
  const route = levelRoute(camera.origin), height = 2 * camera.distance * Math.tan(camera.fovYDeg * Math.PI / 360);
  const coverage = [];
  for (const aspect of [16 / 9, 21 / 9, 4 / 3, 9 / 16]) {
    const repeatX = height * aspect / plate.worldWidth, repeatY = height / plate.worldHeight;
    let margin = Infinity;
    for (const [x, y] of route.points) {
      const ox = (1 - repeatX) / 2 + (x - plate.origin[0]) * plate.pan / plate.worldWidth;
      const oy = (1 - repeatY) / 2 + (y - plate.origin[1]) * plate.pan / plate.worldHeight;
      margin = Math.min(margin, ox, oy, 1 - ox - repeatX, 1 - oy - repeatY);
    }
    assert(margin >= 0, `Image atlas exposes an edge along the route at aspect ${aspect}: margin ${margin}`);
    coverage.push({aspect, minimumUVMargin: margin});
  }
  return {width: info.width, height: info.height, rgbBounds: [min, max],
    route: {file: route.file, sha256: route.sha256, points: route.points.length}, coverage};
}

export async function verifyPackage(directory, {manifest = null, writeReport = false, requireMeshopt = false} = {}) {
  directory = path.resolve(directory);
  manifest ??= json(path.join(directory, 'package.json'));
  validateManifest(manifest);
  const io = await createIO(), layers = {};
  const sourceReportFile = path.join(directory, 'export_report.json');
  const source = fs.existsSync(sourceReportFile) ? json(sourceReportFile) : null;
  const optimizationFile = path.join(directory, 'optimization.json');
  const optimization = fs.existsSync(optimizationFile) ? json(optimizationFile) : null;
  for (const layer of manifest.layers) {
    const file = assetPath(directory, layer), raw = rawGLB(file);
    const decoded = await io.read(file);
    await validateEmbeddedTextures(decoded);
    const facts = documentFacts(decoded, layer.id);
    if (requireMeshopt) assert((raw.extensionsRequired ?? []).includes('EXT_meshopt_compression'), 'Missing required Meshopt compression');
    const expected = source?.layers?.[layer.id];
    if (expected) {
      assert(facts.triangles === expected.triangles && facts.cells === expected.cells, `Source export topology mismatch: ${layer.id}`);
      const delta = Math.max(...facts.bounds.min.map((v, i) => Math.abs(v - expected.bounds.min[i])),
        ...facts.bounds.max.map((v, i) => Math.abs(v - expected.bounds.max[i])));
      assert(delta < .0001, `Source export bounds mismatch: ${layer.id}: ${delta}`);
    }
    const optimized = optimization?.layers?.[layer.id];
    if (optimized?.optimized?.sha256 === layer.sha256) {
      assert(optimized.triangles === facts.triangles && optimized.cells === facts.cells &&
        JSON.stringify(optimized.bounds) === JSON.stringify(facts.bounds) && JSON.stringify(optimized.colors) === JSON.stringify(facts.colors),
      `Recorded decoded geometry or color bounds mismatch: ${layer.id}`);
    }
    layers[layer.id] = {file: layer.file, bytes: layer.bytes, sha256: layer.sha256, ...facts};
  }
  const report = {passed: true, layers, atlas: await atlasFacts(directory, manifest)};
  if (writeReport) atomicJSON(path.join(directory, 'verification.json'), report);
  return report;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    assert(process.argv.length === 3, 'Usage: node verify_package.mjs <package-directory>');
    const report = await verifyPackage(process.argv[2], {writeReport: true});
    console.log(JSON.stringify({passed: report.passed, layers: Object.fromEntries(Object.entries(report.layers).map(([id, facts]) =>
      [id, {cells: facts.cells, triangles: facts.triangles, bytes: facts.bytes, colors: facts.colors}])), atlas: report.atlas}));
  } catch (error) {
    console.error(JSON.stringify({passed: false, error: error.message})); process.exitCode = 1;
  }
}
