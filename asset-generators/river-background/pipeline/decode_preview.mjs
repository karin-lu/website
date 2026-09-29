// Blender's importer cannot read EXT_meshopt_compression. Decode for QA only.
import {createIO} from './verify_package.mjs';
const [source,destination]=process.argv.slice(2);
if (!source || !destination) throw new Error('Pass input GLB and output GLB');
const io=await createIO(); const doc=await io.read(source);
for (const ext of doc.getRoot().listExtensionsUsed()) {
  if (ext.extensionName==='EXT_meshopt_compression') ext.dispose();
}
await io.write(destination,doc);
