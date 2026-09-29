// Run: node optimize_package.mjs <package-directory>
// Publishes only after both compressed layers decode identically and atlas coverage passes.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {require, assert, fileHash, atomicJSON, createIO, assetPath,
  validateManifest, rawGLB, documentFacts, compareFacts, verifyPackage, PropertyType,
  EXTMeshoptCompression, MeshoptEncoder} from './verify_package.mjs';
const {dedup, weld, prune, reorder} = require('@gltf-transform/functions');

export async function optimizePackage(directory) {
  directory = path.resolve(directory);
  const manifestFile = path.join(directory, 'package.json'), original = fs.readFileSync(manifestFile);
  const manifest = JSON.parse(original.toString('utf8'));
  validateManifest(manifest);
  const io = await createIO();
  const stage = fs.mkdtempSync(path.join(directory, '.optimize-'));
  const report = {lossless: true, simplification: false, attributeQuantization: false,
    transforms: ['remove unused COLOR_1', 'dedup', 'bitwise weld', 'prune unused resources', 'reorder', 'Meshopt without filters'], layers: {}};
  const replacement = structuredClone(manifest);
  try {
    for (const layer of replacement.layers) {
      const sourceFile = assetPath(directory, layer);
      rawGLB(sourceFile);
      const document = await io.read(sourceFile);
      // Unlit glTF consumes COLOR_0 only; source appearance must already be corrected.
      documentFacts(document, layer.id, {allowColor1: true, signatures: false});
      for (const mesh of document.getRoot().listMeshes()) for (const primitive of mesh.listPrimitives()) primitive.setAttribute('COLOR_1', null);
      const before = documentFacts(document, layer.id);
      await document.transform(dedup(), weld(), prune({keepLeaves: true, keepExtras: true, keepAttributes: true,
        propertyTypes: [PropertyType.MESH, PropertyType.MATERIAL, PropertyType.TEXTURE, PropertyType.ACCESSOR, PropertyType.BUFFER]}),
      reorder({encoder: MeshoptEncoder, target: 'size', cleanup: false}),
      prune({propertyTypes: [PropertyType.ACCESSOR, PropertyType.BUFFER], keepAttributes: true, keepExtras: true}));
      document.createExtension(EXTMeshoptCompression).setRequired(true).setEncoderOptions({
        method: EXTMeshoptCompression.EncoderMethod.QUANTIZE,
      });
      // QUANTIZE here selects the lossless codec path; no quantize() transform runs.
      const staged = path.join(stage, `${layer.id}.glb`);
      await io.write(staged, document);
      const decoded = await io.read(staged), after = documentFacts(decoded, layer.id);
      compareFacts(before, after);
      const raw = rawGLB(staged);
      assert((raw.extensionsRequired ?? []).includes('EXT_meshopt_compression'), 'Compression was not declared required');
      assert((raw.bufferViews ?? []).every((view) => !view.extensions?.EXT_meshopt_compression?.filter ||
        view.extensions.EXT_meshopt_compression.filter === 'NONE'), 'Lossy Meshopt filters were enabled');
      const hash = fileHash(staged), bytes = fs.statSync(staged).size, name = `${layer.id}-${hash.slice(0, 12)}.glb`;
      report.layers[layer.id] = {source: {file: layer.file, bytes: layer.bytes, sha256: layer.sha256},
        optimized: {file: name, bytes, sha256: hash}, cells: after.cells, triangles: after.triangles,
        reductionPercent: 100 * (1 - bytes / layer.bytes), bounds: after.bounds, colors: after.colors,
        appearancePreserved: true};
      Object.assign(layer, {file: name, bytes, sha256: hash});
      fs.renameSync(staged, path.join(stage, name));
    }
    // Keep immutable previous files available while staging the new manifest.
    for (const layer of replacement.layers) {
      const staged = path.join(stage, layer.file), destination = path.join(directory, layer.file);
      if (fs.existsSync(destination)) {
        assert(fileHash(destination) === layer.sha256, `Content-hash collision: ${layer.file}`);
        fs.unlinkSync(staged);
      } else fs.renameSync(staged, destination);
    }
    const verified = await verifyPackage(directory, {manifest: replacement, requireMeshopt: true});
    report.atlas = verified.atlas;
    assert(fs.readFileSync(manifestFile).equals(original), 'Package changed during optimization; refusing to replace its manifest');
    // Manifest is the commit point; all hashed files have already been verified.
    atomicJSON(path.join(directory, 'optimization.json'), report);
    atomicJSON(path.join(directory, 'verification.json'), verified);
    atomicJSON(manifestFile, replacement);
    return report;
  } finally {
    for (const file of fs.readdirSync(stage)) fs.unlinkSync(path.join(stage, file));
    fs.rmdirSync(stage);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    assert(process.argv.length === 3, 'Usage: node optimize_package.mjs <package-directory>');
    const report = await optimizePackage(process.argv[2]);
    console.log(JSON.stringify({passed: true, lossless: report.lossless, layers: report.layers, atlas: report.atlas}));
  } catch (error) {
    console.error(JSON.stringify({passed: false, error: error.message})); process.exitCode = 1;
  }
}
