"""Verify one generated replacement, vegetation refit, and source preservation."""
import hashlib
import json
import math
import sys
from pathlib import Path
import bpy

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE),str(HERE.parent/'dream-candidate')]
import layer_editor as editor
import river_core as core
from build_layered import main

output = HERE/'verification/layer-editor'
source = Path(bpy.data.filepath)
digest = hashlib.sha256(source.read_bytes()).hexdigest()
target = bpy.data.objects[(output/'target-name.txt').read_text()]
before = {ob.name:core.mesh_hash(ob.data) for layer in (core.NEAR,core.FAR) for ob in editor.rocks(layer)}
matrix = core.authored_world(target).copy()
old_mesh = target.data
core.replace_from_worker(target,output/'rebuilt/rock.blend')
assert target.data != old_mesh
assert core.authored_world(target) == matrix
assert all(math.dist(a,b)<1e-5 for a,b in zip(core.recipe_for(target)['outline'],
           json.loads((output/'edited-recipe.json').read_text())['outline']))
assert not editor.pending_rocks(core.NEAR)
assert any(ob.get('river_backup') for ob in core.collection(core.BACKUPS).objects)
assert all(core.mesh_hash(bpy.data.objects[name].data)==value for name,value in before.items() if name!=target.name)
edited_hash = core.mesh_hash(target.data)
report = main(revision=5,refit=True,save_result=False)
assert core.mesh_hash(target.data) == edited_hash
assert bpy.data.filepath == str(source)
assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
assert report['foliageCards'] > 0 and report['mossSurfacePatches'] > 0
result = {'passed':True,'replacedRock':target.name,'placementPreserved':True,'otherRocksPreserved':True,
          'previousMeshBackedUp':True,'vegetationRefitPreservesEditedRock':True,
          'foliageCards':report['foliageCards'],'mossPatches':report['mossSurfacePatches'],
          'originalFileUnchanged':True,'saveDestinationPreserved':True}
(output/'rebuild-checks.json').write_text(json.dumps(result,indent=2))
print('LAYER_REBUILD_CHECKS_PASSED',json.dumps(result))
