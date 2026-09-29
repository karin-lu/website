"""V5: continuous, rooted geological masses matching the four marked groups."""
import hashlib
import json
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
import river_core as core

HERE = Path(__file__).resolve().parent


def build_masses(rocks):
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    materials = {layer: list(next(ob for ob in rocks if ob['river_layer'] == layer).data.materials)
                 for layer in (core.NEAR, core.FAR)}
    templates = {}
    library = core.collection('79_MASS_LIBRARY_V5')
    for kind in ('red', 'cyan', 'green', 'orange'):
        ob = core.append_rock(HERE/'cache-v5'/kind/'rock.blend', 'V5 library / '+kind)
        core.move(ob, library); core.move(ob.parent, library)
        templates[kind] = ob
    library.hide_render = True; library.hide_viewport = True
    result, report = [], []

    def mass(name, kind, layer, bounds, depth, attachment, group=None, mirror=False):
        # Bounds are world X/Z. One generated closed volume owns the entire
        # silhouette, including the saddle and terraces between former props.
        x0, x1, z0, z1 = bounds
        src = templates[kind]
        ob = src.copy(); ob.data = src.data.copy()
        ob.name = name
        core.collection(layer).objects.link(ob)
        root = bpy.data.objects.new(name+' / placement', None)
        core.collection(layer).objects.link(root)
        ob.parent = root; ob.matrix_parent_inverse = Matrix.Identity(4)
        rid = hashlib.sha256(name.encode()).hexdigest()[:24]
        ob['river_id'] = rid; ob['river_layer'] = layer
        ob['river_attachment'] = attachment
        ob['river_moisture'] = .8 if layer == core.NEAR else .48
        ob['river_marker_group'] = group or 'route'
        root['river_formation'] = rid
        bb = [Vector(p) for p in ob.bound_box]
        lo = Vector(tuple(min(p[k] for p in bb) for k in range(3)))
        hi = Vector(tuple(max(p[k] for p in bb) for k in range(3)))
        ob.location = -(lo+hi)*.5
        root.location = ((x0+x1)/2, depth, (z0+z1)/2)
        width = x1-x0
        root.scale = ((-1 if mirror else 1)*width/(hi.x-lo.x),
                      min(width*.38, 6)/(hi.y-lo.y), (z1-z0)/(hi.z-lo.z))
        ob.data.materials.clear()
        for mat in materials[layer]: ob.data.materials.append(mat)
        core.copy_recipe_helpers(src, ob); core.seal(ob)
        result.append(ob)
        report.append({'name':name, 'group':group, 'attachment':attachment,
                       'boundsXZ':list(bounds), 'depth':depth, 'recipe':kind})
        return ob

    distance = scene['river_distance']; cx, cz = scene['river_origin']
    def screen(name, kind, layer, box, depth, attachment):
        left, right, top, bottom = box
        k = (distance+depth)/distance
        bounds = (cx+(left/1672-.5)*6.24*k, cx+(right/1672-.5)*6.24*k,
                  cz+(.5-bottom/941)*3.51*k, cz+(.5-top/941)*3.51*k)
        return mass(name, kind, layer, bounds, depth, attachment, kind)

    screen('V5 / red terraced bank', 'red', core.NEAR, (220,810,345,1850), 34, 'floor')
    screen('V5 / cyan twin ridge', 'cyan', core.FAR, (505,895,242,1650), 84, 'floor')
    screen('V5 / green ceiling buttress', 'green', core.FAR, (840,1215,-1700,610), 82, 'ceiling')
    screen('V5 / orange riverbank', 'orange', core.NEAR, (940,1430,510,1850), 34, 'floor')

    # Keep the original side framing. Stretching these tilted parents would
    # sweep the walls into the opening and obscure the new terraced banks.
    for ob in rocks:
        if 'weathered buttress' in ob.name:
            ob['river_attachment'] = 'wall'
            result.append(ob)
        elif 'ceiling' in ob.name:
            ob['river_attachment'] = 'ceiling'
            result.append(ob)

    # Alternate banks at the cave sides with ceiling masses over its interior.
    # Their roots extend beyond the route framing without stretching terraces.
    for index in range(6):
        members = [ob for ob in rocks if f' / {index}-' in ob.name]
        if not members: continue
        points = [ob.matrix_world @ v.co for ob in members for v in ob.data.vertices]
        x0, x1 = min(p.x for p in points), max(p.x for p in points)
        lower = min(p.z for p in points)
        depth = min(ob.parent.location.y for ob in members)
        if index in (1,2,4):
            mass(f'V5 / route chamber {index} bank', 'red' if index == 2 else 'orange', core.NEAR,
                 (x0,x1,-35,max(p.z for p in points)), depth, 'floor', mirror=bool(index%2))
        else:
            mass(f'V5 / route chamber {index} ceiling', 'green', core.NEAR,
                 (x0,x1,lower,55), depth, 'ceiling', mirror=bool(index%2))

    for ob in rocks:
        if ob not in result:
            bpy.data.objects.remove(ob, do_unlink=True)
    scene['river_mass_report'] = json.dumps(report)
    bpy.context.view_layer.update()
    return result
