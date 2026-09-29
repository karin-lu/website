"""Front-facing, camera-projected polygon editing for River scenery layers.

Run this script once after opening a saved River scene. Editing handles are
non-rendering curves on the gameplay plane; inverse projection preserves every
formation's original depth, tilt and placement.
"""
import json
import math
import sys
import uuid
from pathlib import Path

import bpy
from bpy.props import StringProperty, FloatProperty, BoolProperty
from mathutils import Matrix, Quaternion, Vector

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import river_core as core

HANDLES = '82_LAYER_EDITOR / projected outlines'
PREVIEWS = '83_LAYER_EDITOR / projected scenery'
STATE = 'river_layer_editor_state'
CLIPBOARD = 'river_polygon_clipboard'


def rocks(layer):
    return sorted((ob for ob in core.collection(layer).all_objects
                   if ob.type == 'MESH' and 'river_recipe' in ob and not ob.get('river_backup')),
                  key=lambda ob: ob.name)


def camera_center(scene):
    x, z = scene['river_origin']
    return Vector((x, -scene['river_distance'], z))


def project(point, center):
    if point.y - center.y <= 1e-6:
        raise ValueError('Outline lies behind the editing camera')
    return center + (point - center) * (-center.y / (point.y - center.y))


def unproject(point, center, rock):
    inverse = core.authored_world(rock).inverted()
    origin = inverse @ center
    direction = inverse.to_3x3() @ (point - center)
    if abs(direction.y) < 1e-9:
        raise ValueError(rock.name + ': outline plane is edge-on to the camera')
    t = -origin.y / direction.y
    if t <= 0:
        raise ValueError(rock.name + ': outline plane is behind the camera')
    result = origin + direction * t
    return [result.x, result.z]


def poly_points(ob):
    if ob.type != 'CURVE' or len(ob.data.splines) != 1:
        raise ValueError(ob.name + ': keep one polygon per formation')
    spline = ob.data.splines[0]
    if spline.type != 'POLY' or not spline.use_cyclic_u:
        raise ValueError(ob.name + ': outline must be a closed polygon')
    points = [core.authored_world(ob) @ Vector(p.co[:3]) for p in spline.points]
    if 'river_editor_owner' in ob:
        # Handles represent a 2D canvas. Depth is never an authored value,
        # including for old files with accidental out-of-plane edits.
        for point in points: point.y = 0
    return points


def flatten_handles():
    """Migrate legacy 3D handles to native 2D curves, retaining world X/Z edits.

    Blender's native 2D curves use local X/Y, rotated to our world X/Z canvas.
    Point editing therefore has no third dimension to accidentally move into.
    """
    flush_edit_mode()
    count = 0
    plane = Matrix.Rotation(math.pi/2,4,'X')
    for ob in handles():
        if ob.data.dimensions == '2D' and ob.get('river_editor_flat_version') == 1:
            continue
        points = poly_points(ob)
        ob.parent = None
        ob.matrix_parent_inverse.identity()
        ob.matrix_world = plane
        for pt, world in zip(ob.data.splines[0].points,points):
            pt.co = (world.x,world.z,0,1)
        ob.data.dimensions = '2D'
        ob.data.fill_mode = 'NONE'
        ob.lock_location = (False,True,False)
        ob.lock_rotation = (True,True,True)
        ob.lock_scale = (False,False,True)
        ob['river_editor_flat_version'] = 1
        count += 1
    return count


def lock_flat_view(context):
    scene = context.scene
    if STATE not in scene: return
    state = json.loads(scene[STATE])
    if 'view_locks' not in state:
        state['view_locks'] = [[screen.name,index,area.spaces.active.region_3d.lock_rotation]
                               for screen in bpy.data.screens for index,area in enumerate(screen.areas)
                               if area.type == 'VIEW_3D']
        scene[STATE] = json.dumps(state)
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D': continue
            rv = area.spaces.active.region_3d
            rv.view_rotation = Quaternion((1,0,0),math.pi/2)
            rv.view_perspective = 'ORTHO'
            rv.lock_rotation = True


def validate_polygon(points):
    if len(points) < 3 or any(not math.isfinite(n) for p in points for n in p):
        raise ValueError('A polygon needs at least three finite points')
    edges = list(zip(points, points[1:] + points[:1]))
    if any(math.dist(a, b) < 1e-6 for a, b in edges):
        raise ValueError('Remove duplicate neighboring outline points')
    area = sum(a[0]*b[1]-b[0]*a[1] for a, b in edges)
    if abs(area) < 1e-8:
        raise ValueError('Outline has zero area')
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def on_segment(a, b, p):
        return (abs(cross(a, b, p)) < 1e-8 and
                min(a[0], b[0])-1e-8 <= p[0] <= max(a[0], b[0])+1e-8 and
                min(a[1], b[1])-1e-8 <= p[1] <= max(a[1], b[1])+1e-8)
    for i, (a, b) in enumerate(edges):
        for j, (c, d) in enumerate(edges):
            if j <= i+1 or (i == 0 and j == len(edges)-1):
                continue
            if ((cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0)
                    or any((on_segment(a,b,c), on_segment(a,b,d),
                            on_segment(c,d,a), on_segment(c,d,b)))):
                raise ValueError('Outline crosses or touches itself')


def flush_edit_mode():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def handles():
    col = bpy.data.collections.get(HANDLES)
    return [ob for ob in col.objects if 'river_editor_owner' in ob] if col else []


def changed_outlines():
    """Validate every changed handle before touching any source outline."""
    scene = bpy.context.scene
    if STATE not in scene:
        return []
    state = json.loads(scene[STATE])
    center = Vector(state['center'])
    result = []
    for handle in handles():
        if handle.get('river_editor_deleted'): continue
        points = poly_points(handle)
        baseline = json.loads(handle['river_editor_baseline'])
        if len(points) == len(baseline) and all((p-Vector(q)).length < 1e-6 for p,q in zip(points,baseline)):
            continue
        rock = next((ob for ob in rocks(state['layer']) if ob['river_id'] == handle['river_editor_owner']), None)
        if rock is None:
            raise ValueError('An edited formation was deleted; cancel editing and reopen the layer')
        if any(abs(a-b) > 1e-6 for row1,row2 in zip(core.authored_world(rock),json.loads(handle['river_editor_matrix']))
               for a,b in zip(row1,row2)):
            raise ValueError(rock.name + ': placement changed during outline editing; cancel and reopen')
        outline = [unproject(p, center, rock) for p in points]
        validate_polygon(outline)
        core.assert_rebuildable(rock)
        result.append((handle, rock, outline, points))
    return result


def apply_outlines():
    flush_edit_mode()
    flatten_handles()
    changed = changed_outlines()
    for handle, rock, outline, points in changed:
        guide = bpy.data.objects[rock['river_outline']]
        guide.parent = rock
        guide.matrix_parent_inverse.identity()
        guide.matrix_basis.identity()
        spline = guide.data.splines[0]
        # Recreate the spline to support both inserted and removed points.
        guide.data.splines.remove(spline)
        spline = guide.data.splines.new('POLY'); spline.points.add(len(outline)-1)
        for pt, (x,z) in zip(spline.points, outline):
            pt.co = (x,0,z,1)
        spline.use_cyclic_u = True
        handle['river_editor_baseline'] = json.dumps([list(p) for p in points])
    if STATE in bpy.context.scene:
        state = json.loads(bpy.context.scene[STATE])
        for handle in list(handles()):
            if not handle.get('river_editor_deleted'): continue
            rock = owner_for(handle)
            if rock:
                root = rock.parent or rock
                items = [root, *root.children_recursive]
                backup = core.collection(core.BACKUPS)
                backup.hide_render = True; backup.hide_viewport = True
                rock['river_backup'] = True
                for ob in items:
                    if any(c.name == state['layer'] for c in ob.users_collection):
                        core.move(ob, backup)
                        ob.hide_set(True)
            remove_handle(handle)
        state['new_owners'] = []
        bpy.context.scene[STATE] = json.dumps(state)
    return len(changed)


def finish_editing(apply=True):
    scene = bpy.context.scene
    flush_edit_mode()
    if STATE not in scene:
        return
    if apply:
        apply_outlines()
    state = json.loads(scene[STATE])
    if not apply:
        for rid in state.get('new_owners', []):
            rock = next((r for r in rocks(state['layer']) if r['river_id'] == rid), None)
            if rock: remove_new_rock(rock)
    for name, hidden in state['collections'].items():
        col = bpy.data.collections.get(name)
        if col: col.hide_viewport = hidden
    for name, values in state['objects'].items():
        ob = bpy.data.objects.get(name)
        if ob:
            ob.hide_select, ob.display_type, hidden = values
            ob.hide_set(hidden)
    for screen_name,index,locked in state.get('view_locks',[]):
        screen = bpy.data.screens.get(screen_name)
        if screen and index < len(screen.areas) and screen.areas[index].type == 'VIEW_3D':
            screen.areas[index].spaces.active.region_3d.lock_rotation = locked
    for handle in handles():
        data = handle.data
        bpy.data.objects.remove(handle, do_unlink=True)
        if data.users == 0: bpy.data.curves.remove(data)
    previews = bpy.data.collections.get(PREVIEWS)
    if previews:
        for ob in list(previews.objects):
            data = ob.data; bpy.data.objects.remove(ob,do_unlink=True)
            if data.users == 0: bpy.data.meshes.remove(data)
    del scene[STATE]


def frame_layer(context):
    points = [p for handle in handles() if not handle.get('river_editor_deleted') for p in poly_points(handle)]
    if not points: return
    lo = Vector(tuple(min(p[k] for p in points) for k in range(3)))
    hi = Vector(tuple(max(p[k] for p in points) for k in range(3)))
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D': continue
            space = area.spaces.active
            rv = space.region_3d
            rv.view_rotation = Quaternion((1,0,0), math.pi/2)
            rv.view_perspective = 'ORTHO'
            rv.view_location = (lo+hi)*.5
            aspect = max(.25, area.width/max(1, area.height))
            rv.view_distance = max((hi.x-lo.x)/aspect, hi.z-lo.z, 2)*1.8
            space.overlay.show_overlays = True
            space.overlay.show_floor = False
            space.shading.type = 'SOLID'
            space.shading.color_type = 'OBJECT'
            space.clip_end = 2000
            space.show_region_ui = True


def start_editing(context, layer):
    finish_editing(apply=True)
    scene = context.scene
    targets = rocks(layer)
    center = camera_center(scene)
    # Project all guides before changing scene visibility.
    projected = [(rock, [project(core.authored_world(rock) @ Vector((x,0,z)), center)
                         for x,z in core.recipe_for(rock)['outline']]) for rock in targets]
    state = {'layer':layer, 'center':list(center),
             'collections':{c.name:bool(c.hide_viewport) for c in bpy.data.collections},
             'objects':{ob.name:[ob.hide_select,ob.display_type,ob.hide_get()] for ob in scene.objects}}
    scene[STATE] = json.dumps(state)
    for col in bpy.data.collections:
        col.hide_viewport = col.name not in (layer, HANDLES, PREVIEWS, *core.REFERENCE_COLLECTIONS)
    col = core.collection(HANDLES); col.hide_render = True; col.hide_viewport = False
    previews = core.collection(PREVIEWS); previews.hide_render = True; previews.hide_viewport = False
    for ob in scene.objects:
        ob.hide_select = True
        if ob.name in core.collection(layer).all_objects: ob.hide_set(True)
        if ob.get('river_reference_only'): ob.display_type = 'WIRE'
    bpy.ops.object.select_all(action='DESELECT')
    # Flatten a read-only preview too: raw world-space scenery would be enlarged
    # in orthographic view compared with the perspective-projected handles.
    for rock in targets:
        if not rock.data.vertices: continue
        matrix = core.authored_world(rock)
        world = [matrix @ vertex.co for vertex in rock.data.vertices]
        min_depth = min(p.y for p in world)
        vertices = []
        for point in world:
            pos = project(point,center); pos.y = .04+(point.y-min_depth)*.0001
            vertices.append(pos)
        mesh = bpy.data.meshes.new('Preview / '+rock.name)
        mesh.from_pydata(vertices,[],[list(face.vertices) for face in rock.data.polygons])
        ob = bpy.data.objects.new(mesh.name,mesh); previews.objects.link(ob)
        ob['river_editor_preview_owner'] = rock['river_id']
        ob.hide_select = True; ob.hide_render = True; ob.color = (.14,.19,.23,1)
    for rock, points in projected:
        curve = bpy.data.curves.new('2D / '+rock.name, 'CURVE'); curve.dimensions = '3D'
        spline = curve.splines.new('POLY'); spline.points.add(len(points)-1); spline.use_cyclic_u = True
        for pt, pos in zip(spline.points, points): pt.co = (*pos,1)
        ob = bpy.data.objects.new(curve.name, curve); col.objects.link(ob)
        ob.hide_render = True; ob.show_in_front = True
        ob.color = (.95,.44,.16,1) if layer == core.NEAR else (.2,.75,.95,1)
        ob['river_editor_owner'] = rock['river_id']
        ob['river_editor_baseline'] = json.dumps([list(p) for p in points])
        ob['river_editor_matrix'] = json.dumps([list(row) for row in core.authored_world(rock)])
        ob.select_set(True)
    if handles(): context.view_layer.objects.active = handles()[0]
    flatten_handles()
    frame_layer(context)
    lock_flat_view(context)
    if handles():
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.curve.select_all(action='DESELECT')


def pending_rocks(layer):
    result = []
    for ob in rocks(layer):
        current = core.recipe_for(ob)['outline']
        built = json.loads(ob['river_recipe'])['outline']
        if ob.get('river_new_polygon') or len(current) != len(built) or any(math.dist(a,b) > 1e-5 for a,b in zip(current,built)):
            validate_polygon(current); core.assert_rebuildable(ob); result.append(ob)
    return result


def owner_for(handle):
    state = json.loads(bpy.context.scene[STATE])
    return next((r for r in rocks(state['layer']) if r['river_id'] == handle['river_editor_owner']), None)


def remove_handle(handle):
    data = handle.data
    bpy.data.objects.remove(handle, do_unlink=True)
    if not data.users: bpy.data.curves.remove(data)


def remove_new_rock(rock):
    root = rock.parent
    guide = rock.get('river_outline',''); sources = rock.get('river_sources','')
    data = rock.data
    bpy.data.objects.remove(rock, do_unlink=True)
    if root and not root.children: bpy.data.objects.remove(root, do_unlink=True)
    if not data.users: bpy.data.meshes.remove(data)
    core.remove_unused_helpers(sources, guide)


def selected_polygons(context):
    editing = context.mode == 'EDIT_CURVE'
    flush_edit_mode()
    available = [h for h in handles() if not h.get('river_editor_deleted')]
    if editing:
        return [h for h in available if any(p.select for p in h.data.splines[0].points)]
    return [h for h in available if h.select_get()]


def resume_points(context, active=None):
    bpy.ops.object.select_all(action='DESELECT')
    available = [h for h in handles() if not h.get('river_editor_deleted')]
    for handle in available: handle.select_set(True)
    if available:
        context.view_layer.objects.active = active if active in available else available[0]
        bpy.ops.object.mode_set(mode='EDIT')


def create_polygon(context, entry, offset=(0,0)):
    scene = context.scene; state = json.loads(scene[STATE]); layer = state['layer']
    points = [Vector((p[0]+offset[0],0,p[2]+offset[1])) for p in entry['points']]
    validate_polygon([[p.x,p.z] for p in points])
    rid = str(uuid.uuid4()); name = entry.get('name','New rock polygon')
    col = core.collection(layer)
    root = bpy.data.objects.new(name+' / placement', None); col.objects.link(root)
    root['river_formation'] = rid
    existing = rocks(layer)
    root.location.y = (sum(core.authored_world(r.parent or r).translation.y for r in existing)/len(existing)
                       if existing else (34 if layer == core.NEAR else 84))
    mesh = bpy.data.meshes.new(name)
    rock = bpy.data.objects.new(name,mesh); col.objects.link(rock); rock.parent = root
    rock['river_id'] = rid; rock['river_layer'] = layer; rock['river_mode'] = 'PROCEDURAL'
    rock['river_new_polygon'] = True
    recipe = json.loads(json.dumps(entry['recipe']))
    recipe['outline'] = [unproject(p,Vector(state['center']),rock) for p in points]
    rock['river_recipe'] = json.dumps(recipe)
    guide = core.outline_object(recipe['outline'],rock.name+' / outline',rock,rid)
    rock['river_outline'] = guide.name; core.seal(rock)
    for ob in (rock, root):
        state['objects'][ob.name] = [False,'TEXTURED',False]
        ob.hide_set(True); ob.hide_select = True
    state.setdefault('new_owners',[]).append(rid); scene[STATE] = json.dumps(state)
    curve = bpy.data.curves.new('2D / '+rock.name,'CURVE'); curve.dimensions = '3D'
    spline = curve.splines.new('POLY'); spline.points.add(len(points)-1); spline.use_cyclic_u = True
    for pt,p in zip(spline.points,points): pt.co = (*p,1); pt.select = True
    handle = bpy.data.objects.new(curve.name,curve); core.collection(HANDLES).objects.link(handle)
    handle.hide_render = True; handle.show_in_front = True
    handle.color = (.95,.44,.16,1) if layer == core.NEAR else (.2,.75,.95,1)
    handle['river_editor_owner'] = rid
    handle['river_editor_baseline'] = json.dumps([list(p) for p in points])
    handle['river_editor_matrix'] = json.dumps([list(row) for row in core.authored_world(rock)])
    flatten_handles()
    return handle


class RIVER_OT_layer_polygon(bpy.types.Operator):
    bl_idname = 'river.layer_polygon'; bl_label = 'Edit layer polygons'
    bl_options = {'REGISTER','UNDO'}
    action: StringProperty(default='COPY')

    @classmethod
    def poll(cls, context):
        return STATE in context.scene and not context.scene.get('river_layer_editor_busy')

    def execute(self, context):
        editing = context.mode == 'EDIT_CURVE'
        try:
            selected = selected_polygons(context)
            active = None
            if self.action in ('COPY','DELETE','ADD_POINT','REMOVE_POINT') and not selected:
                raise ValueError('Select polygon points first, or press Tab and select an outline')
            if self.action == 'COPY':
                entries = []
                for handle in selected:
                    points = poly_points(handle)
                    validate_polygon([[p.x,p.z] for p in points])
                    rock = owner_for(handle)
                    entries.append({'name':rock.name+' copy', 'recipe':core.recipe_for(rock),
                                    'points':[list(p) for p in points]})
                context.scene[CLIPBOARD] = json.dumps(entries)
                self.report({'INFO'}, f'Copied {len(entries)} polygons. Paste into either layer.')
            elif self.action in ('PASTE','NEW'):
                if self.action == 'PASTE':
                    entries = json.loads(context.scene.get(CLIPBOARD,'[]'))
                    if not entries: raise ValueError('Copy a polygon first')
                else:
                    center = camera_center(context.scene)
                    if context.area and context.area.type == 'VIEW_3D':
                        center = context.space_data.region_3d.view_location.copy()
                    x,z = center.x,center.z
                    entries = [{'name':'New rock polygon', 'recipe':{'version':1,'preset':'wall','params':{}},
                                'points':[[x-1,0,z-1],[x+1,0,z-1],[x+1,0,z+1],[x-1,0,z+1]]}]
                for h in handles():
                    for p in h.data.splines[0].points: p.select = False
                for entry in entries:
                    active = create_polygon(context,entry,(.25,.25) if self.action == 'PASTE' else (0,0))
                self.report({'INFO'}, 'Polygon added. Rebuild this layer to generate its rock.')
            elif self.action == 'DELETE':
                for handle in selected:
                    handle['river_editor_deleted'] = True; handle.hide_set(True); handle.select_set(False)
                    col = bpy.data.collections.get(PREVIEWS)
                    if col:
                        for preview in col.objects:
                            if preview.get('river_editor_preview_owner') == handle['river_editor_owner']:
                                preview.hide_set(True)
                self.report({'INFO'}, 'Polygons removed. Apply or rebuild to keep; Discard restores them.')
            elif self.action in ('ADD_POINT','REMOVE_POINT'):
                changes = []
                for handle in selected:
                    old = list(handle.data.splines[0].points)
                    chosen = [i for i,p in enumerate(old) if p.select]
                    if not chosen: raise ValueError('Press Tab and select points on the outline first')
                    if self.action == 'REMOVE_POINT':
                        values = [(p.co.copy(),False) for i,p in enumerate(old) if i not in chosen]
                    else:
                        edges = {i for i in chosen if (i+1)%len(old) in chosen}
                        if not edges and len(chosen)==1: edges = {chosen[0]}
                        if not edges: raise ValueError('Select one point or adjacent points to add a midpoint')
                        values = []
                        for i,p in enumerate(old):
                            values.append((p.co.copy(),False))
                            if i in edges: values.append(((p.co+old[(i+1)%len(old)].co)*.5,True))
                    validate_polygon([[p.x,p.y] for p,_ in values])
                    changes.append((handle,values))
                for handle,values in changes:
                    handle.data.splines.clear()
                    spline = handle.data.splines.new('POLY'); spline.use_cyclic_u = True
                    spline.points.add(len(values)-1)
                    for p,(co,select) in zip(spline.points,values): p.co = co; p.select = select
                active = selected[0]
            if editing or self.action in ('PASTE','NEW','ADD_POINT','REMOVE_POINT'):
                resume_points(context,active)
            redraw_controls(context)
            return {'FINISHED'}
        except Exception as exc:
            if editing: resume_points(context)
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}


def redraw_controls(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D': area.tag_redraw()


def set_authored_world(ob, matrix):
    if ob.parent:
        ob.matrix_basis = ob.matrix_parent_inverse.inverted() @ core.authored_world(ob.parent).inverted() @ matrix
    else:
        ob.matrix_basis = matrix


def depth_roots(layer, selected=None):
    """Move every layer object once, or just selected formation placements."""
    if selected is not None:
        return list(dict.fromkeys(r.parent or r for r in selected))
    members = set(core.collection(layer).all_objects)
    return [ob for ob in members if ob.parent not in members and not ob.get('river_backup')]


def move_depth(context, layer, delta, keep_size=True, selected=None):
    flush_edit_mode()
    roots = depth_roots(layer,selected)
    if not roots: raise ValueError('Select polygon points or a rock first')
    center = camera_center(context.scene)
    pivot = sum(core.authored_world(root).translation.y for root in roots)/len(roots)
    if pivot-center.y <= .01 or pivot+delta-center.y <= .01:
        raise ValueError('Keep the layer in front of the camera')
    ratio = (pivot+delta-center.y)/(pivot-center.y)
    transform = (Matrix.Translation(center) @ Matrix.Scale(ratio,4) @ Matrix.Translation(-center)
                 if keep_size else Matrix.Translation((0,delta,0)))
    moved = set(roots)
    for root in roots: moved.update(root.children_recursive)
    # Historical meshes may share a formation parent. Keep their saved placement.
    historical = {ob:core.authored_world(ob).copy() for ob in moved if ob.get('river_backup')}
    layer_members = set(core.collection(layer).all_objects)
    for ob in moved & layer_members:
        if ob.type != 'MESH' or ob.get('river_backup') or not ob.data.vertices: continue
        matrix = transform @ core.authored_world(ob)
        if any((matrix @ Vector(corner)).y-center.y <= .01 for corner in ob.bound_box):
            raise ValueError('Move less forward: scenery would pass behind the camera')
    affected = [r for r in rocks(layer) if r in moved and not r.get('river_backup')]
    for rock in affected:
        matrix = transform @ core.authored_world(rock)
        recipe = core.recipe_for(rock)
        if any((matrix @ Vector((x,0,z))).y-center.y <= .01 for x,z in recipe['outline']):
            raise ValueError('Move less forward: an outline would pass behind the camera')
    # Preserve unapplied point edits and the unchanged baseline in rock coordinates.
    snapshots = []
    if STATE in context.scene:
        by_id = {r['river_id']:r for r in affected}
        for handle in handles():
            rock = by_id.get(handle['river_editor_owner'])
            if rock is None: continue
            points = [unproject(p,center,rock) for p in poly_points(handle)]
            baseline = [unproject(Vector(p),center,rock)
                        for p in json.loads(handle['river_editor_baseline'])]
            snapshots.append((handle,rock,points,baseline))
    matrices = {root:transform @ core.authored_world(root) for root in roots}
    for root,matrix in matrices.items(): set_authored_world(root,matrix)
    for ob,matrix in historical.items(): set_authored_world(ob,matrix)
    for handle,rock,points,baseline in snapshots:
        matrix = core.authored_world(rock)
        inverse = core.authored_world(handle).inverted()
        for pt,(x,z) in zip(handle.data.splines[0].points,points):
            world = project(matrix @ Vector((x,0,z)),center)
            local = inverse @ world; pt.co = (local.x,local.y,0,1)
        handle['river_editor_baseline'] = json.dumps([list(project(matrix @ Vector((x,0,z)),center)) for x,z in baseline])
        handle['river_editor_matrix'] = json.dumps([list(row) for row in matrix])
    previews = bpy.data.collections.get(PREVIEWS)
    if previews:
        by_id = {r['river_id']:r for r in affected}
        for preview in previews.objects:
            rock = by_id.get(preview.get('river_editor_preview_owner'))
            if rock is None: continue
            matrix = core.authored_world(rock)
            for vertex,source in zip(preview.data.vertices,rock.data.vertices):
                pos = project(matrix @ source.co,center); pos.y = .04
                vertex.co = pos
            preview.data.update()
    context.view_layer.update()
    return len(roots)


class RIVER_OT_layer_depth(bpy.types.Operator):
    bl_idname = 'river.layer_depth'; bl_label = 'Move background depth'
    bl_options = {'REGISTER','UNDO'}
    layer: StringProperty(default=core.NEAR)
    scope: StringProperty(default='LAYER')
    direction: FloatProperty(default=1)

    @classmethod
    def poll(cls, context):
        return not context.scene.get('river_layer_editor_busy')

    def execute(self, context):
        editing = context.mode == 'EDIT_CURVE'
        try:
            layer = json.loads(context.scene[STATE])['layer'] if STATE in context.scene else self.layer
            selected = None
            if self.scope == 'ROCKS':
                if STATE in context.scene:
                    selected = [owner_for(h) for h in selected_polygons(context)]
                else:
                    selected = []
                    candidates = set(rocks(layer))
                    for ob in context.selected_objects:
                        if ob in candidates: selected.append(ob)
                        else: selected.extend(r for r in candidates if r.parent == ob)
                if not selected: raise ValueError('Select polygon points or rock objects first')
            delta = self.direction*context.scene.river_depth_step
            count = move_depth(context,layer,delta,context.scene.river_depth_keep_size,selected)
            if editing: resume_points(context)
            redraw_controls(context)
            self.report({'INFO'}, f'Moved {count} placements {"back" if delta>0 else "forward"}. Save to keep depth changes.')
            return {'FINISHED'}
        except Exception as exc:
            if editing: resume_points(context)
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}


def draw_depth(layout, context, layer):
    box = layout.box(); box.label(text='Depth — '+('Near' if layer==core.NEAR else 'Far'))
    row = box.row(align=True)
    row.prop(context.scene,'river_depth_step',text='Step')
    box.prop(context.scene,'river_depth_keep_size',text='Keep screen size')
    for scope,label in (('LAYER','Whole layer'),('ROCKS','Selected rocks')):
        row = box.row(align=True); row.label(text=label)
        for direction,text in ((-1,'Forward'),(1,'Back')):
            op = row.operator('river.layer_depth',text=text)
            op.layer = layer; op.scope = scope; op.direction = direction


class RIVER_OT_layer_edit(bpy.types.Operator):
    bl_idname = 'river.layer_edit'; bl_label = 'Edit background layer'; bl_options = {'REGISTER','UNDO'}
    action: StringProperty(default='NEAR')

    def execute(self, context):
        try:
            if context.scene.get('river_layer_editor_busy'):
                raise ValueError('Wait for the current rebuild to finish')
            if self.action in ('NEAR','FAR'):
                start_editing(context, core.NEAR if self.action == 'NEAR' else core.FAR)
            elif self.action == 'FRAME':
                flush_edit_mode(); frame_layer(context)
                if handles(): bpy.ops.object.mode_set(mode='EDIT')
            elif self.action == 'APPLY':
                was_editing = context.mode == 'EDIT_CURVE'
                count = apply_outlines(); self.report({'INFO'}, f'Applied {count} edited outlines; rebuild to update stone')
                if was_editing: resume_points(context)
            elif self.action == 'CANCEL':
                finish_editing(apply=False); core.opening_composition(context.scene)
            elif self.action == 'PREVIEW':
                finish_editing(); core.foreground_preview(context.scene, True); core.opening_composition(context.scene)
            elif self.action == 'REFIT':
                finish_editing()
                if any(pending_rocks(layer) for layer in (core.NEAR,core.FAR)):
                    raise ValueError('Rebuild changed rocks before refitting vegetation')
                path = HERE.parent/'dream-candidate'
                if str(path) not in sys.path: sys.path.insert(0,str(path))
                from build_layered import main
                main(revision=5, refit=True, save_result=False)
                for ob in rocks(core.NEAR)+rocks(core.FAR):
                    if 'river_attachments_review' in ob: del ob['river_attachments_review']
                core.opening_composition(context.scene)
                self.report({'INFO'}, 'Vegetation refitted in the current scene. Save to keep it.')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}


class RIVER_OT_layer_rebuild(bpy.types.Operator):
    bl_idname = 'river.layer_rebuild'; bl_label = 'Rebuild changed rocks'; bl_options = {'REGISTER','UNDO'}
    layer: StringProperty(default=core.NEAR)

    def execute(self, context):
        try:
            if context.scene.get('river_layer_editor_busy'):
                raise ValueError('A rebuild is already running')
            finish_editing()
            self._targets = pending_rocks(self.layer)
            if not self._targets:
                self.report({'INFO'}, 'No changed outlines in this layer'); return {'FINISHED'}
            self._completed = []; self._index = 0; self._cancelled = False
            self._launch()
            context.scene['river_layer_editor_busy'] = True
            self._timer = context.window_manager.event_timer_add(.5,window=context.window)
            context.window_manager.modal_handler_add(self)
            self.report({'INFO'}, f'Rebuilding {len(self._targets)} rocks. Esc discards the results.')
            return {'RUNNING_MODAL'}
        except Exception as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}

    def _launch(self):
        ob = self._targets[self._index]
        self._request = core.recipe_for(ob)
        self._proc, self._out, self._log = core.launch_worker(self._request)
        bpy.context.scene['river_layer_editor_progress'] = f'{self._index+1}/{len(self._targets)}: {ob.name}'
        redraw_controls(bpy.context)

    def _cleanup(self, context):
        context.window_manager.event_timer_remove(self._timer)
        context.scene['river_layer_editor_busy'] = False
        context.scene['river_layer_editor_progress'] = ''
        redraw_controls(context)

    def modal(self, context, event):
        if event.type == 'ESC':
            self._cancelled = True
        if event.type != 'TIMER' or self._proc.poll() is None: return {'PASS_THROUGH'}
        self._log.close()
        try:
            if self._cancelled:
                self._cleanup(context); self.report({'INFO'}, 'Rebuild cancelled; existing meshes retained')
                return {'CANCELLED'}
            if self._proc.returncode:
                raise ValueError(core.worker_failure(self._out))
            self._completed.append((self._targets[self._index],self._out/'rock.blend',self._request))
            self._index += 1
            if self._index < len(self._targets):
                self._launch(); return {'RUNNING_MODAL'}
            # Validate every result before replacing any current mesh.
            for ob, file, request in self._completed:
                core.assert_rebuildable(ob)
                if core.recipe_for(ob) != request:
                    raise ValueError(ob.name + ': outline changed during generation; retry rebuild')
                before = core.datablocks()
                try:
                    with bpy.data.libraries.load(str(file),link=False) as (_,dst):
                        dst.objects=['SceneryRock']; dst.collections=['SOURCE_SLABS']
                    core.validate_worker(dst.objects[0],dst.collections[0])
                finally:
                    imported = core.datablocks()-before
                    if imported: bpy.data.batch_remove(ids=imported)
            for ob, file, request in self._completed:
                core.replace_from_worker(ob,file)
                if 'river_new_polygon' in ob: del ob['river_new_polygon']
            self._cleanup(context)
            core.opening_composition(context.scene)
            self.report({'INFO'}, f'Rebuilt {len(self._completed)} rocks. Refit vegetation next.')
            return {'FINISHED'}
        except Exception as exc:
            self._cleanup(context); self.report({'ERROR'},str(exc)); return {'CANCELLED'}


class RIVER_PT_layer_editor(bpy.types.Panel):
    bl_label = '2D Background Layers'; bl_idname = 'RIVER_PT_layer_editor'
    bl_space_type = 'VIEW_3D'; bl_region_type = 'UI'; bl_category = 'River'
    bl_order = -10

    @classmethod
    def poll(cls, context):
        return context.scene.get('river_candidate') == 'river-dream-v5'

    def draw(self, context):
        l = self.layout; scene = context.scene
        l.enabled = not scene.get('river_layer_editor_busy',False)
        row = l.row(align=True)
        row.operator('river.layer_edit',text='Edit Near',icon='EDITMODE_HLT').action = 'NEAR'
        row.operator('river.layer_edit',text='Edit Far',icon='EDITMODE_HLT').action = 'FAR'
        if STATE in scene:
            state = json.loads(scene[STATE]); l.label(text='Editing '+('Near' if state['layer']==core.NEAR else 'Far'))
            l.operator('river.layer_edit',text='Frame whole layer').action = 'FRAME'
            l.label(text='G: move. Tab: points / polygons.')
            box = l.box(); box.label(text='Polygons')
            row = box.row(align=True)
            row.operator('river.layer_polygon',text='Copy').action = 'COPY'
            paste = row.row(align=True); paste.enabled = bool(scene.get(CLIPBOARD))
            paste.operator('river.layer_polygon',text='Paste').action = 'PASTE'
            row = box.row(align=True)
            row.operator('river.layer_polygon',text='New polygon').action = 'NEW'
            row.operator('river.layer_polygon',text='Delete polygon').action = 'DELETE'
            row = box.row(align=True)
            row.operator('river.layer_polygon',text='Add point').action = 'ADD_POINT'
            row.operator('river.layer_polygon',text='Remove points').action = 'REMOVE_POINT'
            box.label(text='Select points to choose a polygon.')
            draw_depth(l,context,state['layer'])
            l.operator('river.layer_edit',text='Apply outline edits').action = 'APPLY'
            l.operator('river.layer_rebuild',text='Rebuild this layer').layer = state['layer']
            l.operator('river.layer_edit',text='Discard unapplied edits').action = 'CANCEL'
        else:
            row = l.row(align=True)
            row.operator('river.layer_rebuild',text='Rebuild Near').layer = core.NEAR
            row.operator('river.layer_rebuild',text='Rebuild Far').layer = core.FAR
            draw_depth(l,context,core.NEAR)
            draw_depth(l,context,core.FAR)
        row = l.row(align=True)
        row.operator('river.layer_edit',text='Refit plants',icon='PARTICLES').action = 'REFIT'
        row.operator('river.layer_edit',text='Preview',icon='CAMERA_DATA').action = 'PREVIEW'
        if STATE not in scene: l.label(text='Save, then use Export saved background below.')
        if scene.get('river_layer_editor_busy'): l.label(text=scene.get('river_layer_editor_progress','Working…'))


CLASSES = (RIVER_OT_layer_depth,RIVER_OT_layer_polygon,RIVER_OT_layer_edit,RIVER_OT_layer_rebuild,RIVER_PT_layer_editor)


def register():
    from configure_scene import configure
    configure()
    import river_tools
    river_tools.register()
    bpy.types.Scene.river_depth_step = FloatProperty(name='Depth step',description='Distance for each forward or back click',default=5,min=.01,soft_max=50)
    bpy.types.Scene.river_depth_keep_size = BoolProperty(name='Keep screen size',description='Preserve camera framing while changing depth and parallax',default=True)
    for cls in CLASSES:
        old = getattr(bpy.types,cls.__name__,None)
        if old: bpy.utils.unregister_class(old)
        bpy.utils.register_class(cls)
    bpy.context.scene['river_layer_editor_busy'] = False
    if STATE in bpy.context.scene:
        was_editing = bpy.context.mode == 'EDIT_CURVE'
        flatten_handles()
        lock_flat_view(bpy.context)
        if was_editing and bpy.context.object:
            bpy.ops.object.mode_set(mode='EDIT')


if __name__ == '__main__': register()
