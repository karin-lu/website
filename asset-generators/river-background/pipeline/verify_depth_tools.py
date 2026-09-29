"""Verify depth editing against a real v5 scene without writing artist data."""
import json
import sys
from pathlib import Path
import bpy
from mathutils import Vector
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import layer_editor as e
import river_core as c
e.register()
scene=bpy.context.scene
center=e.camera_center(scene)
def position(ob): return c.authored_world(ob).translation.copy()
def projected(rock):
    matrix=c.authored_world(rock)
    return [e.project(matrix@Vector((x,0,z)),center) for x,z in c.recipe_for(rock)['outline']]
near=e.rocks(c.NEAR); far=e.rocks(c.FAR)
rock=near[0]; root=rock.parent
original=c.authored_world(root).copy()
other={r.name:c.authored_world(r).copy() for r in near[1:]+far}
recipe=c.recipe_for(rock); mesh=c.mesh_hash(rock.data)
screen=projected(rock)
attachment=next((o for o in root.children if o!=rock and o.type=='MESH'),None)
if attachment:
    relative=c.authored_world(root).inverted()@c.authored_world(attachment)
backup=c.backup(rock); backup_matrix=c.authored_world(backup).copy()
e.move_depth(bpy.context,c.NEAR,12,True,[rock])
assert abs(position(root).y-original.translation.y-12)<1e-4
assert max((a-b).length for a,b in zip(screen,projected(rock)))<1e-4
assert c.recipe_for(rock)==recipe and c.mesh_hash(rock.data)==mesh
assert not e.pending_rocks(c.NEAR)
assert all(c.authored_world(bpy.data.objects[name])==matrix for name,matrix in other.items())
assert max(abs(a-b) for row1,row2 in zip(backup_matrix,c.authored_world(backup)) for a,b in zip(row1,row2))<1e-4
if attachment:
    current=c.authored_world(root).inverted()@c.authored_world(attachment)
    assert max(abs(a-b) for row1,row2 in zip(relative,current) for a,b in zip(row1,row2))<1e-4
e.move_depth(bpy.context,c.NEAR,-12,True,[rock])
e.start_editing(bpy.context,c.NEAR); e.flush_edit_mode()
h=next(h for h in e.handles() if e.owner_for(h)==rock)
h.data.splines[0].points[0].co.x+=.03
before_local=e.changed_outlines()[0][2]
screen_before=e.poly_points(h)
for item in e.handles():
    for p in item.data.splines[0].points: p.select=False
h.data.splines[0].points[0].select=True
e.resume_points(bpy.context,h)
scene.river_depth_step=5
assert bpy.ops.river.layer_depth(scope='ROCKS',direction=1)=={'FINISHED'}
assert bpy.context.mode=='EDIT_CURVE'
e.flush_edit_mode()
assert max((a-b).length for a,b in zip(screen_before,e.poly_points(h)))<1e-4
after_local=e.changed_outlines()[0][2]
assert max((Vector(a)-Vector(b)).length for a,b in zip(before_local,after_local))<1e-4
e.move_depth(bpy.context,c.NEAR,5,False,[rock])
assert max((a-b).length for a,b in zip(screen_before,e.poly_points(h)))>.01
assert len(e.changed_outlines())==1
e.finish_editing(apply=False)
assert not e.pending_rocks(c.NEAR)
# Whole layer includes standalone foliage and all roots, without moving Far.
roots=e.depth_roots(c.NEAR)
before={r:c.authored_world(r).copy() for r in roots}
far_before={r:c.authored_world(r).copy() for r in far}
e.move_depth(bpy.context,c.NEAR,7,False)
assert all(abs(position(r).y-m.translation.y-7)<1e-4 for r,m in before.items())
assert all(c.authored_world(r)==m for r,m in far_before.items())
screens={r:projected(r) for r in near}
e.move_depth(bpy.context,c.NEAR,9,True)
assert all(max((a-b).length for a,b in zip(points,projected(r)))<1e-4 for r,points in screens.items())
assert not e.pending_rocks(c.NEAR)
before={r:c.authored_world(r).copy() for r in roots}
try:
    e.move_depth(bpy.context,c.NEAR,-10000,False)
    raise AssertionError('Behind-camera move accepted')
except ValueError: pass
assert all(c.authored_world(r)==m for r,m in before.items())
report={'passed':True,'checks':['single rock depth','attached vegetation follows',
    'other rocks and Far unchanged','historical backups stay put','camera framing preserved',
    'true forward/back translation','unapplied outlines survive','point editing stays active',
    'whole layer and standalone scenery','no mesh rebuild needed','behind-camera move rejected atomically']}
(HERE/'verification/layer-editor/depth-checks.json').write_text(json.dumps(report,indent=2))
print('DEPTH_TOOLS_PASSED',json.dumps(report))
