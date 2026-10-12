"""Blender volume union and exportable painted vertex colours for line roots."""
import bpy
import bmesh
import numpy as np
from .lines import tubes, surface_details


def build(graph):
    vertices, faces = tubes(graph)
    mesh = bpy.data.meshes.new('Flowing root')
    mesh.from_pydata(vertices.tolist(), [], faces.tolist())
    mesh.update()
    scratch = bpy.data.objects.new('Root volume build', mesh)
    bpy.context.scene.collection.objects.link(scratch)
    result = None
    try:
        # Union the growth volumes before smoothing: forks become a continuous
        # surface rather than tubes with visible intersection seams.
        modifier = scratch.modifiers.new('Joined growth', 'REMESH')
        modifier.mode = 'VOXEL'
        modifier.voxel_size = graph['settings']['depth']/{'DRAFT':22,'PREVIEW':38,'FINAL':56}[graph['settings']['quality']]
        modifier.use_smooth_shade = True
        smooth = scratch.modifiers.new('Soft fork shoulders', 'SMOOTH')
        smooth.factor = .85
        smooth.iterations = 24
        decimate = scratch.modifiers.new('Efficient surface', 'DECIMATE')
        decimate.ratio = .48
        decimate.use_collapse_triangulate = True
        result = bpy.data.meshes.new_from_object(scratch.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        result.name = 'Painted flowing root'
        # Sub-voxel terminal slivers can detach during the volume conversion.
        # Remove only tiny remnants; a disconnected structural limb is an error.
        bm = bmesh.new()
        try:
            bm.from_mesh(result)
            unseen = set(bm.verts)
            islands = []
            while unseen:
                component = [unseen.pop()]
                for vertex in component:
                    for edge in vertex.link_edges:
                        neighbor = edge.other_vert(vertex)
                        if neighbor in unseen:
                            unseen.remove(neighbor)
                            component.append(neighbor)
                islands.append(component)
            islands.sort(key=len,reverse=True)
            if not islands: raise ValueError('Root is too small at this detail level')
            fragments = [v for island in islands[1:] for v in island]
            if len(fragments) > max(24,len(islands[0])*.01):
                raise ValueError('Root has a detached limb; increase Detail or tighten its junction')
            if fragments:
                bmesh.ops.delete(bm,geom=fragments,context='VERTS')
                bm.to_mesh(result)
                result.update()
        finally:
            bm.free()
        for polygon in result.polygons:
            polygon.use_smooth = True
        position = np.empty(len(result.vertices)*3)
        result.vertices.foreach_get('co', position)
        position = position.reshape(-1,3)
        normals = np.asarray([v.normal[:] for v in result.vertices])
        rgba = np.ones((len(position),4), np.float32)
        for start in range(0,len(position),4096):
            region = slice(start,start+4096)
            rgba[region,:3], relief = surface_details(position[region],graph)
            # Add the bark after smoothing the union, so the smoothing pass
            # cannot polish away all the wood's irregular surface planes.
            position[region] += normals[region]*relief[:,None]
        result.vertices.foreach_set('co',position.astype(np.float32).ravel())
        result.update()
        colors = result.color_attributes.new(name='Root paint',type='FLOAT_COLOR',domain='POINT')
        colors.data.foreach_set('color',rgba.ravel())
        result.color_attributes.active_color = colors
        mat = bpy.data.materials.new('Root · painted umber')
        mat.use_nodes = True
        mat['root_generated'] = True
        shader = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        shader.inputs['Roughness'].default_value = .94
        shader.inputs['Specular IOR Level'].default_value = .05
        color = mat.node_tree.nodes.new('ShaderNodeVertexColor')
        color.layer_name = 'Root paint'
        mat.node_tree.links.new(color.outputs['Color'],shader.inputs['Base Color'])
        result.materials.append(mat)
        return result
    except Exception:
        if result is not None:
            bpy.data.meshes.remove(result)
        raise
    finally:
        bpy.data.objects.remove(scratch,do_unlink=True)
        bpy.data.meshes.remove(mesh)
