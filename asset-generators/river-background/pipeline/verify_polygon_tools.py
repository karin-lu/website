"""Exercise polygon tools in an isolated Blender process, without saving artwork."""
import sys
import json
from pathlib import Path
import bpy
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import layer_editor as e
import river_core as c
e.register()
e.start_editing(bpy.context,c.NEAR)
e.flush_edit_mode()
original = len(e.rocks(c.NEAR))
h = e.handles()[0]
for item in e.handles():
    for p in item.data.splines[0].points: p.select=False
h.data.splines[0].points[0].select=True
e.resume_points(bpy.context,h)
def op(action):
    assert bpy.ops.river.layer_polygon(action=action)=={'FINISHED'}, action
op('COPY')
assert len(json.loads(bpy.context.scene[e.CLIPBOARD]))==1
op('PASTE'); e.flush_edit_mode()
new = next(r for r in e.rocks(c.NEAR) if r.get('river_new_polygon'))
assert new in e.pending_rocks(c.NEAR)
assert new['river_id']!=e.owner_for(h)['river_id']
assert len(e.rocks(c.NEAR))==original+1
e.finish_editing(apply=False)
assert len(e.rocks(c.NEAR))==original
e.start_editing(bpy.context,c.FAR)
expected_depth=sum(c.authored_world(r.parent or r).translation.y for r in e.rocks(c.FAR))/len(e.rocks(c.FAR))
op('PASTE'); e.flush_edit_mode()
new = next(r for r in e.rocks(c.FAR) if r.get('river_new_polygon'))
assert abs(new.parent.location.y-expected_depth)<1e-5
assert c.recipe_for(new)['params']==json.loads(bpy.context.scene[e.CLIPBOARD])[0]['recipe']['params']
e.finish_editing(apply=False)
e.start_editing(bpy.context,c.NEAR)
op('NEW'); e.flush_edit_mode()
h = next(h for h in e.handles() if e.owner_for(h).get('river_new_polygon'))
for item in e.handles():
    for p in item.data.splines[0].points: p.select=False
h.data.splines[0].points[0].select=True
e.resume_points(bpy.context,h)
op('ADD_POINT'); e.flush_edit_mode()
assert len(h.data.splines[0].points)==5
e.resume_points(bpy.context,h)
op('REMOVE_POINT'); e.flush_edit_mode()
assert len(h.data.splines[0].points)==4
for p in h.data.splines[0].points: p.select=False
h.data.splines[0].points[0].select=True
e.resume_points(bpy.context,h)
op('REMOVE_POINT'); e.flush_edit_mode()
assert len(h.data.splines[0].points)==3
before = [list(p.co) for p in h.data.splines[0].points]
for p in h.data.splines[0].points: p.select=False
h.data.splines[0].points[0].select=True
e.resume_points(bpy.context,h)
try: bpy.ops.river.layer_polygon(action='REMOVE_POINT')
except RuntimeError: pass
e.flush_edit_mode()
assert [list(p.co) for p in h.data.splines[0].points]==before
e.apply_outlines()
assert len(e.pending_rocks(c.NEAR))>=1
assert not json.loads(bpy.context.scene[e.STATE])['new_owners']
recipe=c.recipe_for(e.owner_for(h))
(HERE/'verification/layer-editor/new-polygon-recipe.json').write_text(json.dumps(recipe))
worker=HERE/'verification/layer-editor/new-polygon-worker/rock.blend'
if worker.exists():
    target=e.owner_for(h)
    c.replace_from_worker(target,worker)
    assert len(target.data.polygons)>0 and not target.get('river_new_polygon')
    assert target not in e.pending_rocks(c.NEAR)
    print('NEW_POLYGON_REBUILD_PASSED')
e.finish_editing()
e.start_editing(bpy.context,c.NEAR); e.flush_edit_mode()
h=e.handles()[0]; rid=h['river_editor_owner']
for item in e.handles():
    for p in item.data.splines[0].points: p.select=False
h.data.splines[0].points[0].select=True
e.resume_points(bpy.context,h); op('DELETE')
assert h.get('river_editor_deleted') and h.hide_get()
e.finish_editing(apply=False)
assert any(r['river_id']==rid for r in e.rocks(c.NEAR))
e.start_editing(bpy.context,c.NEAR); e.flush_edit_mode()
h=next(h for h in e.handles() if h['river_editor_owner']==rid)
for item in e.handles():
    for p in item.data.splines[0].points: p.select=False
h.data.splines[0].points[0].select=True
e.resume_points(bpy.context,h); op('DELETE'); e.apply_outlines()
assert not any(r['river_id']==rid for r in e.rocks(c.NEAR))
assert any(r.get('river_id')==rid for r in c.collection(c.BACKUPS).all_objects)
e.finish_editing()
print('POLYGON_TOOLS_PASSED: clipboard, cross-layer paste, discard, new polygon, insert/remove, minimum 3, staged deletion, backup')
