"""Read-only checks for the v3 procedural master and its painted foliage cards."""
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Matrix
from mathutils.bvhtree import BVHTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'pipeline'))
import river_core as core


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def uses_packed_texture(node, path):
    # Refits create Blender .001/.002 image datablocks. Validate the packed
    # bytes rather than requiring identity with an older unused datablock.
    return (node.type == 'TEX_IMAGE' and node.image and node.image.packed_file and
            hashlib.sha256(node.image.packed_file.data).hexdigest() == sha(path))


def main():
    from configure_scene import configure
    configure()
    scene_path = Path(bpy.data.filepath).resolve()
    revision = int(bpy.context.scene.get('river_candidate', 'river-dream-v3').rsplit('v', 1)[1])
    output = HERE / f'output-v{revision}'
    initial_hash = sha(scene_path)
    ball = core.ROOT / 'rope/levels/ball.json'
    initial_ball_hash = sha(ball)
    failures = []
    def check(condition, description):
        if not condition: failures.append(description)
    check(scene_path == (output / 'river_dream.blend').resolve(), 'Wrong source scene loaded')
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    scenery = {ob for name in (core.NEAR, core.FAR) for ob in bpy.data.collections[name].all_objects if ob.type == 'MESH'}
    rocks = [ob for ob in scenery if 'river_recipe' in ob]
    cards = [ob for ob in scenery if 'river_sprite' in ob]
    moss_patches = [ob for ob in scenery if ob.get('river_surface_moss')]
    build_report = json.loads((output / 'build_report.json').read_text())
    if revision == 5:
        marked = [ob for ob in rocks if ob.get('river_marker_group') in ('red','cyan','green','orange')]
        check(sorted(ob['river_marker_group'] for ob in marked) == ['cyan','green','orange','red'],
              'Each marker color must own exactly one formation')
        for ob in marked:
            remaining = set(range(len(ob.data.vertices)))
            adjacency = [set() for _ in ob.data.vertices]
            for edge in ob.data.edges:
                a,b = edge.vertices
                adjacency[a].add(b); adjacency[b].add(a)
            components = 0
            while remaining:
                components += 1
                todo = [remaining.pop()]
                while todo:
                    for neighbor in adjacency[todo.pop()]:
                        if neighbor in remaining:
                            remaining.remove(neighbor); todo.append(neighbor)
            check(components == 1, ob.name + ': disconnected rock pieces')
            zs = [(core.authored_world(ob) @ v.co).z for v in ob.data.vertices]
            if ob['river_attachment'] == 'floor':
                check(min(zs) < -25, ob.name + ': ground root can enter opening view')
            else:
                check(max(zs) > 50, ob.name + ': ceiling root is too short')
        check(len(rocks) < 20, 'V5 has reverted to excessive separate formations')
    check(len(rocks) == build_report['rocks'] and len(cards) == build_report['foliageCards'], 'Rock/card counts disagree with build report')
    check(len(moss_patches) == build_report.get('mossSurfacePatches', 0), 'Surface moss count disagrees with build report')
    check(sum(len(ob.data.polygons)*2 for ob in cards) == build_report['foliageTriangles'], 'Card triangle count disagrees with build report')
    check(sum(len(ob.data.polygons)*2 for ob in moss_patches) == build_report['mossSurfaceTriangles'], 'Moss triangle count disagrees with build report')
    check(scene.get('river_preserved_bake_lighting') is True, 'Textured surface light bake is not enabled')
    check(list(scene.get('river_foliage_fog_color', [])) == [.028,.064,.092] and
          scene.get('river_foliage_fog_near') == 20 and scene.get('river_foliage_fog_far') == 190,
          'Foliage haze scene settings are missing or incorrect')
    rock_rows = []
    recipe_collection = bpy.data.collections[core.RECIPES]
    for ob in sorted(rocks, key=lambda ob: ob.name):
        try:
            helpers = bpy.data.collections[ob['river_sources']]
            recipe = core.validate_worker(ob, helpers)
            guide = bpy.data.objects[ob['river_outline']]
            check(guide.parent == ob and guide.get('river_outline_owner') == ob['river_id'], ob.name + ': outline ownership')
            authored = core.recipe_for(ob)
            error = max(abs(a[i] - b[i]) for a,b in zip(recipe['outline'], authored['outline']) for i in (0,1))
            check(len(recipe['outline']) == len(authored['outline']) and error < 2e-5, ob.name + ': recipe outline mismatch')
            check(ob.parent and ob.parent.get('river_formation') == ob['river_id'], ob.name + ': missing recipe placement root')
            check(core.mesh_hash(ob.data) == ob['river_mesh_hash'], ob.name + ': mesh seal changed')
            check(helpers in list(recipe_collection.children) and helpers.hide_render, ob.name + ': source helpers containment')
            check(not(set(helpers.all_objects) & scenery), ob.name + ': source slabs leak into scenery')
            min_y = min((core.authored_world(ob) @ v.co).y for v in ob.data.vertices)
            check(min_y > 0, ob.name + ': crosses foreground Y=0')
            rock_rows.append({'name': ob.name, 'seed': recipe['params']['seed'], 'worldMinY': min_y, 'sourceSlabs': len(helpers.objects)})
        except Exception as exc:
            failures.append(ob.name + ': ' + str(exc))
    sprite_bounds = build_report['spriteBounds']
    sprite_roots = build_report['spriteRoots']
    atlas = bpy.data.images.get('foliage-components-v3.png')
    check(bool(atlas and atlas.packed_file and atlas.channels == 4), 'Foliage atlas is not packed RGBA')
    check(len(sprite_bounds) == len(sprite_roots) == 4 and all(
          0 <= x0 < x1 <= atlas.size[0] and 0 <= y0 < y1 <= atlas.size[1] and x0 <= root <= x1
          for (x0,y0,x1,y1),root in zip(sprite_bounds,sprite_roots)), 'Dynamic sprite bounds or stem roots are invalid')
    pixels = np.asarray(atlas.pixels[:], dtype=np.float32).reshape(-1,4)
    alpha = pixels[:,3]
    alpha_report = {'width': atlas.size[0], 'height': atlas.size[1], 'channels': atlas.channels,
                    'alphaMinimum': float(alpha.min()), 'alphaMaximum': float(alpha.max()),
                    'transparentFraction': float(np.mean(alpha < .01)), 'opaqueFraction': float(np.mean(alpha > .99))}
    check(alpha_report['transparentFraction'] > .1 and alpha_report['opaqueFraction'] > .02, 'Atlas alpha is not a useful cutout')
    card_rows = []
    for ob in sorted(cards, key=lambda ob: ob.name):
        minimum_y = min((core.authored_world(ob) @ v.co).y for v in ob.data.vertices)
        check(minimum_y > 0, ob.name + ': card crosses foreground Y=0')
        local_vertices = np.asarray([tuple(vertex.co) for vertex in ob.data.vertices])
        singular_values = np.linalg.svd(local_vertices-local_vertices.mean(axis=0), compute_uv=False)
        check(singular_values[-1] > 1e-5, ob.name + ': component geometry is flat instead of bowed')
        check(ob.data.uv_layers.active is not None, ob.name + ': missing UV layer')
        uvs = [tuple(loop.uv) for loop in ob.data.uv_layers.active.data]
        check(all(math.isfinite(x) and 0 <= x <= 1 for uv in uvs for x in uv), ob.name + ': invalid atlas UVs')
        sprite = int(ob['river_sprite'])
        x0,y0,x1,y1 = sprite_bounds[sprite]
        check(all(x0/atlas.size[0]-1e-6 <= uv[0] <= x1/atlas.size[0]+1e-6 and
                  1-y1/atlas.size[1]-1e-6 <= uv[1] <= 1-y0/atlas.size[1]+1e-6 for uv in uvs),
              ob.name + ': UV coordinates outside intended sprite')
        check(len(ob.data.materials) == 1, ob.name + ': expected single painted material')
        mat = ob.data.materials[0]
        bs = mat.node_tree.nodes.get('Principled BSDF')
        check(mat.get('river_alpha_mode') == 'MASK' and abs(mat.get('river_alpha_cutoff',0)-.42)<1e-6,
              ob.name + ': alpha material export settings')
        check(bs and bs.inputs['Alpha'].is_linked and bs.inputs['Base Color'].is_linked, ob.name + ': missing color/alpha links')
        texture_nodes = [node for node in mat.node_tree.nodes if uses_packed_texture(node, HERE/'textures/foliage-components-v3.png')]
        check(bool(texture_nodes), ob.name + ': atlas texture missing from material')
        check(not mat.use_backface_culling, ob.name + ': foliage must be visible from both sides')
        parent_error = None
        if ob.parent:
            product = core.authored_world(ob.parent) @ ob.matrix_parent_inverse
            parent_error = max(abs(product[i][j] - Matrix.Identity(4)[i][j]) for i in range(4) for j in range(4))
            check(parent_error < 1e-4, ob.name + ': placement parent inverse does not preserve authored world anchor')
        card_rows.append({'name': ob.name, 'sprite': sprite, 'worldMinY': minimum_y, 'faces': len(ob.data.polygons),
                          'parent': ob.parent.name if ob.parent else None, 'parentInverseMaximumError': parent_error,
                          'curvatureSingularValue': float(singular_values[-1])})
    cluster_rows = []
    for index,cluster in enumerate(build_report['clusters']):
        pieces = [ob for ob in cards if ob.get('river_cluster') == index]
        near = cluster['layer'] == core.NEAR
        minimum, maximum = ((2, 4) if near else (1, 1)) if revision == 5 else ((3, 6 if revision >= 4 else 5) if near else (1, 2))
        check(len(pieces) == cluster['pieces'] and minimum <= len(pieces) <= maximum,
              f'Cluster {index}: component budget mismatch')
        supporting = bpy.data.objects.get(cluster['rock'])
        check(supporting is not None and all(ob.parent == supporting.parent for ob in pieces),
              f'Cluster {index}: components not attached to supporting rock root')
        check(all(abs(ob.get('river_distance_size',0)-cluster['screenSizeFactor'])<1e-6 for ob in pieces),
              f'Cluster {index}: distance size metadata mismatch')
        check(all(ob.name in bpy.data.collections[cluster['layer']].all_objects for ob in pieces),
              f'Cluster {index}: incorrect depth collection')
        check(all(len(ob.data.polygons) <= (5 if near else 3) for ob in pieces), f'Cluster {index}: strip detail budget')
        if not near:
            check(cluster['screenSizeFactor'] < .65 and all(ob['river_sprite'] in (1,3) for ob in pieces),
                  f'Cluster {index}: distant foliage must be smaller and use simple sprites')
        normals = [(core.authored_world(ob).to_3x3().inverted().transposed() @ ob.data.polygons[0].normal).normalized() for ob in pieces]
        orientation_spread = max((1-abs(a.dot(b)) for i,a in enumerate(normals) for b in normals[i+1:]), default=0)
        if len(pieces)>1:
            check(orientation_spread > .001, f'Cluster {index}: compound cards share a flat orientation')
        cluster_rows.append(dict(cluster, actualPieces=len(pieces), orientationSpread=orientation_spread))
    moss_image = bpy.data.images.get('soft-moss-v2.png')
    check(bool(moss_image and moss_image.packed_file and moss_image.channels == 4), 'Soft moss image is not packed RGBA')
    moss_alpha = np.asarray(moss_image.pixels[:], dtype=np.float32).reshape(-1,4)[:,3]
    moss_alpha_report = {'width': moss_image.size[0], 'height': moss_image.size[1],
                         'alphaMinimum': float(moss_alpha.min()), 'alphaMaximum': float(moss_alpha.max()),
                         'transparentFraction': float(np.mean(moss_alpha < .01)),
                         'featheredFraction': float(np.mean((moss_alpha > .01) & (moss_alpha < .99)))}
    check(moss_alpha_report['alphaMaximum'] > .42 and moss_alpha_report['transparentFraction'] > .01 and
          moss_alpha_report['featheredFraction'] > .01, 'Moss image lacks visible, open, feathered alpha areas')
    moss_rows = []
    for patch in sorted(moss_patches, key=lambda ob: ob.name):
        vertices = [core.authored_world(patch) @ vertex.co for vertex in patch.data.vertices]
        minimum_y = min(vertex.y for vertex in vertices)
        check(minimum_y > 0, patch.name + ': moss crosses foreground Y=0')
        check(patch.get('river_preserve_material'), patch.name + ': material must survive export')
        check(0 < len(patch.data.polygons) <= 22*12 and len(vertices) <= 23*13,
              patch.name + ': moss must be a sparse fitted surface grid')
        check(patch.data.uv_layers.active is not None, patch.name + ': missing UV layer')
        check(all(math.isfinite(x) and 0 <= x <= 1 for loop in patch.data.uv_layers.active.data for x in loop.uv),
              patch.name + ': moss UV outside image bounds')
        supporting = [rock for rock in rocks if rock.parent == patch.parent]
        check(len(supporting) == 1, patch.name + ': missing unique supporting recipe root')
        maximum_surface_distance = None
        if len(supporting) == 1:
            rock = supporting[0]
            rock.data.calc_loop_triangles()
            rock_vertices = [core.authored_world(rock) @ vertex.co for vertex in rock.data.vertices]
            bvh = BVHTree.FromPolygons(rock_vertices, [tuple(tri.vertices) for tri in rock.data.loop_triangles], all_triangles=True)
            maximum_surface_distance = max(bvh.find_nearest(vertex)[3] for vertex in vertices)
            scale = (10.2375 + rock.parent.location.y)/10.2375
            check(maximum_surface_distance <= scale*.012 + 1e-3,
                  patch.name + ': moss vertices float away from supporting rock')
        mat = patch.data.materials[0]
        check(mat.get('river_alpha_mode') == 'MASK' and abs(mat.get('river_alpha_cutoff',0)-.42)<1e-6,
              patch.name + ': moss alpha export settings')
        check(any(uses_packed_texture(node, HERE/'textures/soft-moss-v2.png') for node in mat.node_tree.nodes),
              patch.name + ': packed moss image absent from shader')
        bs = mat.node_tree.nodes.get('Principled BSDF')
        check(bs.inputs['Alpha'].is_linked and bs.inputs['Base Color'].is_linked,
              patch.name + ': moss color/alpha links missing')
        moss_rows.append({'name': patch.name, 'faces': len(patch.data.polygons), 'vertices': len(vertices),
                          'worldMinY': minimum_y, 'maximumSupportingSurfaceDistance': maximum_surface_distance})
    moss_materials = {mat for ob in rocks for mat in ob.data.materials if mat}
    check(all(mat.node_tree and any(node.type == 'TEX_NOISE' for node in mat.node_tree.nodes) and
              mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].is_linked for mat in moss_materials),
          'Rock moss is not connected to the surface shader')
    original = HERE / 'output/river_dream.blend'
    original_hash = sha(original)
    ball_hash = sha(ball)
    check(original_hash == '70481788d0c15a0d34d6440b63c84a699d43686d666050d20c9332b287675b00', 'Original Sunken Grotto master changed')
    check(original_hash == build_report['sourceMasterSha256'], 'Build report source master hash mismatch')
    check(ball_hash == initial_ball_hash, 'BALL level changed during verification')
    check(not any(marker.camera for marker in scene.timeline_markers), 'Camera-bound timeline markers remain')
    check(Path(scene['river_export_path']).resolve() == (core.ROOT/f'rope/public/backgrounds/river-dream-v{revision}').resolve(), 'Export destination incorrect')
    check(sha(scene_path) == initial_hash, 'Saved v3 scene changed during verification')
    report = {'passed': not failures, 'failures': failures, 'sceneSha256': initial_hash,
              'verificationMode': 'Read-only; no scene writes', 'rocks': len(rocks), 'cards': len(cards),
              'cardTriangles': sum(len(ob.data.polygons)*2 for ob in cards), 'mossMaterials': len(moss_materials),
              'mossSurfacePatches': len(moss_patches), 'mossSurfaceTriangles': sum(len(ob.data.polygons)*2 for ob in moss_patches),
              'softMossImage': moss_alpha_report, 'mossPatchDetails': moss_rows,
              'clusters': cluster_rows, 'spriteBounds': sprite_bounds, 'spriteRoots': sprite_roots,
              'localLightingBakeEnabled': True,
              'foliageFog': {'color': list(scene['river_foliage_fog_color']), 'near': scene['river_foliage_fog_near'], 'far': scene['river_foliage_fog_far']},
              'atlas': alpha_report, 'preservedMasterSha256': original_hash, 'preservedBallSha256': ball_hash,
              'rockDetails': rock_rows, 'cardDetails': card_rows}
    report_path = output / 'layered-verification-report.json'
    report_path.write_text(json.dumps(report, indent=2))
    print('V3_SOURCE_VERIFICATION', json.dumps({k:report[k] for k in ('passed','failures','rocks','cards','cardTriangles')}), flush=True)
    if failures: raise RuntimeError('V3 source checks failed; see ' + str(report_path))


if __name__ == '__main__': main()
