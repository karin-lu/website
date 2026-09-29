"""Fine complete moss strands: soft contrast, uniform scale and curved lips."""
import hashlib
import json
import math
import random
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import river_core as core

HERE = Path(__file__).resolve().parent


def add_hanging_moss(rocks):
    for layer in (core.NEAR, core.FAR):
        for ob in list(core.collection(layer).all_objects):
            if ob.get('river_hanging_moss'):
                bpy.data.objects.remove(ob, do_unlink=True)
    image_path = HERE / 'textures/hanging-moss-soft-strands-v5.png'
    image = bpy.data.images.load(str(image_path), check_existing=True)
    image.pack()
    pixels = np.asarray(image.pixels[:],dtype=np.float32).reshape(image.size[1],image.size[0],4)[::-1]
    mask = pixels[:,:,3] > .15
    iw,ih = image.size
    sprites=[]
    sprite_edge_alpha=[]
    # Each isolated column contains its whole crown and naturally tapered tip.
    occupied=mask.any(axis=0)
    edges=np.diff(np.r_[False,occupied,False].astype(int))
    spans=list(zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)))
    assert len(spans)==7, 'Missing seven isolated complete strands'
    for left,right in spans:
        yy,xx=np.where(mask[:,left:right])
        x0,x1=max(0,left-3),min(iw,right+3)
        y0,y1=max(0,int(yy.min())-3),min(ih,int(yy.max())+4)
        border=np.concatenate((pixels[y0,x0:x1,3],pixels[y1-1,x0:x1,3],
                               pixels[y0:y1,x0,3],pixels[y0:y1,x1-1,3]))
        assert border.max()<.15, 'Visible clipped sprite edge'
        sprite_edge_alpha.append(float(border.max()))
        sprites.append((x0/iw,x1/iw,y0/ih,y1/ih))
    mats = {}
    for layer, tint in ((core.NEAR, (.20, .29, .32, 1)), (core.FAR, (.24, .35, .44, 1))):
        name = 'V5 / draped moss / ' + layer
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.use_nodes = True
        mat.use_backface_culling = False
        mat['river_alpha_mode'] = 'MASK'
        mat['river_alpha_cutoff'] = .38
        mat['river_color_factor'] = tint
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        nodes.clear()
        out = nodes.new('ShaderNodeOutputMaterial')
        bs = nodes.new('ShaderNodeBsdfPrincipled')
        tex = nodes.new('ShaderNodeTexImage'); tex.image = image
        color = nodes.new('ShaderNodeMixRGB'); color.blend_type = 'MULTIPLY'
        color.inputs[0].default_value = 1; color.inputs[2].default_value = tint
        links.new(tex.outputs['Color'], color.inputs[1])
        links.new(color.outputs[0], bs.inputs['Base Color'])
        links.new(color.outputs[0], bs.inputs['Emission Color'])
        links.new(tex.outputs['Alpha'], bs.inputs['Alpha'])
        links.new(bs.outputs[0], out.inputs[0])
        bs.inputs['Emission Strength'].default_value = .16
        bs.inputs['Roughness'].default_value = 1
        bs.inputs['Specular IOR Level'].default_value = 0
        mats[layer] = mat

    from growth_patches import growth_sites
    bpy.context.view_layer.update()
    cards, clusters = [], []
    for rock in sorted(rocks, key=lambda ob: ob.name):
        layer = rock['river_layer']
        rock.data.calc_loop_triangles()
        pts = [rock.matrix_world @ v.co for v in rock.data.vertices]
        lo = Vector(tuple(min(p[i] for p in pts) for i in range(3)))
        hi = Vector(tuple(max(p[i] for p in pts) for i in range(3)))
        bvh = BVHTree.FromPolygons(pts, [tuple(t.vertices) for t in rock.data.loop_triangles], all_triangles=True)
        seed = int(hashlib.sha256(str(rock.get('river_id', rock.name)).encode()).hexdigest()[:8], 16)
        rng = random.Random(seed + 9517)
        ceiling = rock.get('river_attachment') == 'ceiling' or 'ceiling' in rock.name or 'ceiling buttress' in rock.name
        scale = (bpy.context.scene['river_distance'] + (lo.y + hi.y) / 2) / bpy.context.scene['river_distance']
        sites = growth_sites(rock, bpy.context.scene['river_distance'], layer == core.FAR)
        rock['river_growth_sites'] = json.dumps(sites)

        def front(x, z):
            hit, normal, _, _ = bvh.ray_cast(Vector((x, lo.y - 2, z)), Vector((0, 1, 0)), hi.y - lo.y + 4)
            return hit, normal

        def contour(x):
            # Find the visible front silhouette, then refine to within 1/4096 height.
            span = hi.z - lo.z
            direction = 1 if ceiling else -1
            start = lo.z if ceiling else hi.z
            for step in range(257):
                z = start + direction * span * step / 256
                hit, normal = front(x, z)
                if hit is None: continue
                low, high = max(0, step - 1) / 256, step / 256
                for _ in range(4):
                    mid = (low + high) / 2
                    probe, _ = front(x, start + direction * span * mid)
                    if probe is None: low = mid
                    else: high = mid
                return front(x, start + direction * span * (high + .0003))[0]
            return None

        for index, site in enumerate(sites):
            if not site['spill']: continue
            center = site['root'][0]
            width = site['radius'] * 2
            length = width * .86
            roots = [contour(center + width * (i / 16 - .5)) for i in range(17)]
            if sum(p is not None for p in roots) < 14: continue
            # Missing edge rays are filled from the nearest valid root.
            for i, p in enumerate(roots):
                if p is None:
                    nearest = min((j for j in range(17) if roots[j] is not None), key=lambda j: abs(j - i))
                    roots[i] = roots[nearest].copy(); roots[i].x = center + width * (i / 16 - .5)
            # A sheet across a cliff discontinuity stretches painted leaves.
            # Keep only coherent ledges; bare steep stone breaks up the planting.
            if max(p.z for p in roots) - min(p.z for p in roots) > width * .80:
                continue
            if any(abs(a.z - b.z) > length * .45 for a, b in zip(roots, roots[1:])):
                continue

            cluster_id = len(clusters)
            cluster_cards = []
            # Match the reference's loose individual strands. Only the longest
            # sprites are scaled by .90, equally in both axes to retain leaves.
            style = site['style']
            count = {'tuft': 4, 'sparse': 3, 'cascade': 7}[style]
            if layer == core.FAR: count = min(count, 3)
            specs = []
            for piece in range(count):
                sprite = rng.randrange(len(sprites))
                size = rng.uniform(.34, .55) if style == 'tuft' else rng.uniform(.48, .95)
                if style == 'cascade' and piece == count//2: size = 1.05
                specs.append(('main strand', sprite, size,
                              -.38 + .76*(piece+rng.uniform(.1,.9))/count,
                              rng.uniform(.025,.045)))
            for piece,(role,sprite,size_factor,x_offset,offset) in enumerate(specs):
                group=piece
                u0,u1,v0,v1=sprites[sprite]
                mid = (u0 + u1) / 2
                group_rng = random.Random(seed+index*61+group)
                group_jitter = group_rng.uniform(-.010,.010)
                root = contour(center + width * (x_offset+group_jitter))
                if root is None: continue
                world_per_texel = width / iw * size_factor
                full_width,full_height = iw*world_per_texel,ih*world_per_texel
                painted_height = full_height*(v1-v0)
                # Use the front lip's depth, retaining the ledge's height so
                # the leafy crown is exposed above the edge rather than buried.
                ledge_z=root.z
                attachment,_ = front(root.x,root.z-painted_height*.06)
                if attachment is not None: root.y=attachment.y
                root.z=ledge_z+painted_height*(-.025 if ceiling else .010)
                bend = min(.12,(v1-v0)*.24)
                crown_angle=math.radians(32)
                radius = full_height * bend / (math.pi / 2-crown_angle)
                def drape(t):
                    travel=t-v0
                    if travel<=bend:
                        theta=crown_angle+(math.pi/2-crown_angle)*travel/bend
                        return radius*(1-math.sin(theta)),radius*math.cos(theta)
                    s=full_height*(travel-bend)
                    r=full_height*((v1-v0)-bend)/math.radians(5)
                    return -r*(1-math.cos(s/r)),-r*math.sin(s/r)
                # The entire hanging section is rigid in X/Z. Sampling the rock
                # only chooses one depth offset; it never deforms leaf geometry.
                clearance = scale * offset
                needed = []
                for u in (u0,mid,u1):
                    for f in (0.,.04,.08,.12,.18,.25,.35,.60,.85,.98,1.):
                        y_rel,z_rel=drape(v0+(v1-v0)*f)
                        x = root.x + full_width * (u-mid)
                        z = root.z+z_rel
                        hit, _ = front(x,z)
                        if hit is not None: needed.append(root.y+y_rel-hit.y+clearance)
                shift = max([clearance,*needed])
                root.y -= shift
                if role == 'front strand': root.z -= painted_height*.015
                rows = [v0+bend*i/6 for i in range(7)]
                rows.extend(v0+(v1-v0)*f for f in (.40,.70,1.))
                ts = sorted({v0,v1,*[t for t in rows if v0 < t < v1]})
                verts, uvs, faces = [], [], []
                for t in ts:
                    y_rel,z_rel=drape(t)
                    y,z=root.y+y_rel,root.z+z_rel
                    for u in (u0,u1):
                        x = root.x + full_width * (u-mid)
                        origin = rock.matrix_world.translation
                        verts.append(tuple(Vector((x, y, z)) - origin)); uvs.append((u, 1 - t))
                for iy in range(len(ts) - 1):
                    a = iy * 2
                    faces.append((a,a+1,a+3,a+2))
                name = rock.name + f' / hanging moss {index} / {role} {group}'
                mesh = bpy.data.meshes.new(name); mesh.from_pydata(verts, [], faces)
                mesh.materials.append(mats[layer])
                uv = mesh.uv_layers.new(name='UVMap')
                for poly in mesh.polygons:
                    for li in poly.loop_indices: uv.data[li].uv = uvs[mesh.loops[li].vertex_index]
                ob = bpy.data.objects.new(name, mesh); core.collection(layer).objects.link(ob)
                ob.location = rock.matrix_world.translation
                ob.visible_shadow = False
                ob['river_preserve_material'] = True
                ob['river_hanging_moss'] = True
                ob['river_moss_role'] = role
                ob['river_moss_owner'] = rock['river_id']
                ob['river_moss_cluster'] = cluster_id
                ob['river_moss_group'] = group
                ob['river_moss_sprite'] = sprite
                ob['river_moss_reference_scale'] = size_factor
                ob['river_moss_complete_silhouette'] = True
                ob['river_moss_world_per_texel'] = world_per_texel
                ob['river_attachment_rule'] = 'complete fine strand; independent root; uniform scale; bend at lip'
                ob.parent = rock.parent
                ob.matrix_parent_inverse = rock.parent.matrix_world.inverted()
                cards.append(ob)
                cluster_cards.append(ob)
            if cluster_cards:
                clusters.append({'rock':rock.name,'index':index,'width':width,'length':length,'style':style,'layers':1,'moisture':site['moisture'],
                                 'completeStrands':len(cluster_cards),'cards':len(cluster_cards)})
    bpy.context.view_layer.update()
    report = {'clusters': clusters, 'cards': len(cards), 'triangles': sum(len(o.data.polygons) * 2 for o in cards),
              'texture': str(image_path), 'textureSha256': hashlib.sha256(image_path.read_bytes()).hexdigest(),
              'construction':'shared moisture patches; geometry roots; complete strands; uniform scale',
              'spriteBounds':sprites,'spriteBorderAlpha':sprite_edge_alpha,
              'detail':'soft contrast; mixed intermediate lengths; complete exposed crowns and tips'}
    bpy.context.scene['river_hanging_moss_report'] = json.dumps(report)
    return cards, report
