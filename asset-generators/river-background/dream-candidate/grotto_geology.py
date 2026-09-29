"""Deterministic compound geology and baked surface treatment for River Dream."""
import hashlib
import json
import math
import random

import bpy
from mathutils import Matrix, Vector
import river_core as core


def enrich_formations(rocks):
    bpy.context.view_layer.update()
    additions = []
    rows = []
    templates = {name: bpy.data.objects.get('Library / ' + name) for name in ('shelf_b', 'ledge', 'crag')}
    for rock in sorted(rocks, key=lambda ob: ob.name):
        seed = int(hashlib.sha256(rock['river_id'].encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        if any(word in rock.name for word in ('ceiling', 'hanging tooth', 'spire')):
            continue
        world = [rock.matrix_world @ v.co for v in rock.data.vertices]
        low = Vector(tuple(min(v[k] for v in world) for k in range(3)))
        high = Vector(tuple(max(v[k] for v in world) for k in range(3)))
        size = high-low
        center = (low+high)*.5
        wet = 'Waterfall' in rock.name or 'garden' in rock.name.lower() or seed % 5 == 0
        rock['river_moisture'] = .86 if wet else rng.uniform(.2, .65)
        # Each ledge overlaps its host: distinct strata, never free-floating props.
        count = 2 if rock['river_layer'] == core.NEAR else 1
        for j in range(count):
            kind = 'ledge' if j == 0 else ('crag' if seed % 2 else 'shelf_b')
            src = templates[kind]
            ob = src.copy()
            ob.data = src.data.copy()
            ob.name = rock.name + f' / fracture ledge {j}'
            layer = rock['river_layer']
            core.collection(layer).objects.link(ob)
            root = bpy.data.objects.new(ob.name+' / placement', None)
            core.collection(layer).objects.link(root)
            ob.parent = root
            ob.matrix_parent_inverse = Matrix.Identity(4)
            rid = hashlib.sha256(ob.name.encode()).hexdigest()[:24]
            ob['river_id'] = rid
            ob['river_layer'] = layer
            ob['river_moisture'] = rock['river_moisture']
            root['river_formation'] = rid
            bounds = [Vector(c) for c in ob.bound_box]
            lo = Vector(tuple(min(v[k] for v in bounds) for k in range(3)))
            hi = Vector(tuple(max(v[k] for v in bounds) for k in range(3)))
            ob.location = -(lo+hi)*.5
            width = size.x*rng.uniform(.44,.72)
            height = size.z*(rng.uniform(.09,.17) if j == 0 else rng.uniform(.19,.28))
            root.scale = (width/(hi.x-lo.x), size.y*.48/(hi.y-lo.y), height/(hi.z-lo.z))
            side = -1 if (seed+j)%2 else 1
            root.location = (center.x+side*size.x*.24, low.y+size.y*.24,
                             low.z+size.z*(.69 if j == 0 else .38))
            root.rotation_euler = (0, math.radians(side*rng.uniform(9,23)), math.radians(rng.uniform(-7,7)))
            ob.data.materials.clear()
            for mat in rock.data.materials:
                ob.data.materials.append(mat)
            core.copy_recipe_helpers(src, ob)
            core.seal(ob)
            additions.append(ob)
            rows.append({'name': ob.name, 'host': rock['river_id'], 'seed': seed, 'kind': kind})
    # Narrow side keys reveal strata while retaining the dark cave exposure.
    for name, position, target, power in (
        ('V4 / opening fissure bounce', (1,20,9), (10,40,-6), 6500),
        ('V4 / upper gallery bounce', (22,28,33), (13,48,18), 8200),
    ):
        data = bpy.data.lights.new(name, 'AREA')
        data.energy = power
        data.shape = 'DISK'
        data.size = 12
        data.color = (.48,.68,.78)
        ob = bpy.data.objects.new(name, data)
        core.collection('40_LIGHTING').objects.link(ob)
        ob.location = position
        ob.rotation_euler = (Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler()
    bpy.context.scene['river_geology_report'] = json.dumps(rows)
    bpy.context.view_layer.update()
    return rocks+additions


def enrich_materials(rocks, strength=.72):
    for mat in {m for ob in rocks for m in ob.data.materials if m}:
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bs = nodes.get('Principled BSDF')
        original = bs.inputs['Base Color'].links[0].from_socket
        geom = nodes.new('ShaderNodeNewGeometry')
        mapping = nodes.new('ShaderNodeVectorMath'); mapping.operation = 'MULTIPLY'
        mapping.inputs[1].default_value = (.55,.55,2.8)
        links.new(geom.outputs['Position'], mapping.inputs[0])
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 1.1
        noise.inputs['Detail'].default_value = 2.5
        noise.inputs['Roughness'].default_value = .65
        links.new(mapping.outputs['Vector'], noise.inputs['Vector'])
        ramp = nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position = .25
        ramp.color_ramp.elements[0].color = (.42,.49,.55,1)
        ramp.color_ramp.elements[1].position = .74
        ramp.color_ramp.elements[1].color = (1.28,1.2,1.08,1)
        links.new(noise.outputs['Fac'], ramp.inputs[0])
        mineral = nodes.new('ShaderNodeMixRGB'); mineral.blend_type = 'MULTIPLY'
        mineral.inputs[0].default_value = strength
        links.new(original, mineral.inputs[1]); links.new(ramp.outputs['Color'], mineral.inputs[2])
        # Curvature adds cavity pigment without an AO ray query at every shader
        # evaluation. Actual light/shadow contacts still come from the bake.
        crevice = nodes.new('ShaderNodeValToRGB')
        crevice.color_ramp.elements[0].position = .34
        crevice.color_ramp.elements[0].color = (.38,.43,.48,1)
        crevice.color_ramp.elements[1].position = .52
        crevice.color_ramp.elements[1].color = (1,1,1,1)
        links.new(geom.outputs['Pointiness'], crevice.inputs[0])
        cavity = nodes.new('ShaderNodeMixRGB'); cavity.blend_type = 'MULTIPLY'
        cavity.inputs[0].default_value = .65
        links.new(mineral.outputs[0], cavity.inputs[1]); links.new(crevice.outputs['Color'], cavity.inputs[2])
        links.new(cavity.outputs[0], bs.inputs['Base Color'])
        links.new(cavity.outputs[0], bs.inputs['Emission Color'])
        bs.inputs['Emission Strength'].default_value = .10
