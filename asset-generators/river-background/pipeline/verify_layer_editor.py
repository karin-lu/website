"""Exercise real v5 outlines, projection, layer isolation and edit validation."""
import hashlib
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import layer_editor as editor
import river_core as core

editor.register()
scene = bpy.context.scene
original_file = Path(bpy.data.filepath)
original_digest = hashlib.sha256(original_file.read_bytes()).hexdigest()
original_meshes = {ob.name:core.mesh_hash(ob.data) for layer in (core.NEAR,core.FAR) for ob in editor.rocks(layer)}
original_visibility = {col.name:col.hide_viewport for col in bpy.data.collections}
center = editor.camera_center(scene)
roundtrip_error = 0
counts = {}
for layer in (core.NEAR,core.FAR):
    for rock in editor.rocks(layer):
        for point in core.recipe_for(rock)['outline']:
            projected = editor.project(core.authored_world(rock) @ Vector((point[0],0,point[1])),center)
            restored = editor.unproject(projected,center,rock)
            roundtrip_error = max(roundtrip_error, (Vector(restored)-Vector(point)).length)
    editor.start_editing(bpy.context,layer)
    editor.flush_edit_mode()
    counts[layer] = len(editor.handles())
    assert counts[layer] == len(editor.rocks(layer))
    assert core.collection(core.FAR if layer == core.NEAR else core.NEAR).hide_viewport
    assert not editor.changed_outlines(), 'Untouched projected handles must not dirty recipes'
    assert all(h.hide_render and h.type == 'CURVE' for h in editor.handles())
    assert all(h.data.dimensions=='2D' and h.lock_location[1] and all(h.lock_rotation) for h in editor.handles())
    editor.finish_editing(apply=False)
assert roundtrip_error < 1e-4, roundtrip_error
assert all(bpy.data.collections[name].hide_viewport == value for name,value in original_visibility.items())

# Apply one real silhouette edit; all other rock meshes and outlines stay intact.
editor.start_editing(bpy.context,core.NEAR); editor.flush_edit_mode()
handle = next(h for h in editor.handles() if 'red terraced bank' in h.name)
rock = next(o for o in editor.rocks(core.NEAR) if o['river_id']==handle['river_editor_owner'])
original_recipe = core.recipe_for(rock)
handle.data.splines[0].points[0].co.x += .03
assert len(editor.changed_outlines()) == 1
assert editor.apply_outlines() == 1
assert len(editor.pending_rocks(core.NEAR)) == 1
assert not editor.pending_rocks(core.FAR)
edited_recipe = core.recipe_for(rock)
assert edited_recipe['outline'] != original_recipe['outline']
assert edited_recipe['params'] == original_recipe['params']
assert not editor.changed_outlines()
# Even data written outside the native 2D UI is treated as a flat canvas.
handle.data.splines[0].points[0].co.z = .1
assert not editor.changed_outlines(), 'Depth-only changes must not alter the silhouette'
assert all(p.y == 0 for p in editor.poly_points(handle))
assert core.recipe_for(rock) == edited_recipe
# Migrate a translated legacy 3D handle without losing its X/Z shape edits.
legacy = editor.handles()[1]
legacy.data.dimensions = '3D'
legacy['river_editor_flat_version'] = 0
legacy.location.x += .15
legacy.data.splines[0].points[0].co.z += .2
before_flatten = editor.poly_points(legacy)
assert editor.flatten_handles() == 1
assert all((a-b).length < 1e-5 for a,b in zip(before_flatten,editor.poly_points(legacy)))
assert all(p.co.z==0 for p in legacy.data.splines[0].points)
editor.finish_editing(apply=False)
assert not editor.handles()
assert all(core.mesh_hash(bpy.data.objects[name].data)==value for name,value in original_meshes.items())

for polygon in ([[0,0],[1,1],[0,1],[1,0]], [[0,0],[1,0],[1,0],[0,1]], [[0,0],[1,0],[2,0]]):
    try:
        editor.validate_polygon(polygon)
        raise AssertionError('Invalid polygon accepted')
    except ValueError:
        pass

output = HERE/'verification/layer-editor'
output.mkdir(parents=True, exist_ok=True)
(output/'edited-recipe.json').write_text(json.dumps(edited_recipe,indent=2))
(output/'target-name.txt').write_text(rock.name)
assert hashlib.sha256(original_file.read_bytes()).hexdigest() == original_digest
report = {'passed':True,'formations':counts,'maximumProjectionRoundtripError':roundtrip_error,
          'sourceFileUnchanged':True,'rockMeshesUnchanged':True,
          'checks':['near/far isolation','all outlines editable together','perspective projection including tilted rocks',
                    'one edited outline applied','unchanged outlines ignored','native 2D handles and depth locks',
                    'accidental depth ignored','legacy handle repair preserves X/Z edits',
                    'crossing/degenerate polygons rejected','visibility restored','helper geometry excluded from rendering']}
(output/'checks.json').write_text(json.dumps(report,indent=2))
print('LAYER_EDITOR_CHECKS_PASSED',json.dumps(report))
