"""Blender recipes, independent guides, packed PBR maps and a small sidebar."""
import json
import time
import uuid
import bpy
import numpy as np
from bpy.props import FloatProperty, StringProperty, EnumProperty, PointerProperty
from mathutils import Vector, Matrix
from .model import DEFAULTS, validate
from .surface import build_surfaces, bark_atlas
from .rootlets import grow


class RootSettings(bpy.types.PropertyGroup):
    depth: FloatProperty(name='Thickness', default=.38, min=.02, max=5, subtype='DISTANCE')
    taper: FloatProperty(name='Taper', default=.65, min=0, max=1)
    age: FloatProperty(name='Age', default=.65, min=0, max=1)
    bark_strength: FloatProperty(name='Bark relief', default=.7, min=0, max=2)
    rootlet_density: FloatProperty(name='Rootlets', default=.25, min=0, max=1)
    seed: StringProperty(name='Seed', default='roots')
    quality: EnumProperty(name='Detail', items=[('DRAFT','Draft','Fast blockout'),
        ('PREVIEW','Preview','Working detail'),('FINAL','Final','Closer surface sampling')], default='PREVIEW')
    status: StringProperty(default='')


def owner(ob):
    while ob is not None:
        if ob.get('grown_by') == 'roots': return ob
        ob=ob.parent
    return None


def _world(ob):
    # Hidden guide collections have no evaluated matrix_world. Compose their
    # authored transforms, as the existing formations/Game workflow does.
    local=ob.matrix_basis.copy()
    return _world(ob.parent) @ ob.matrix_parent_inverse @ local if ob.parent else local


def _points(ob,closed=True):
    if ob.type == 'CURVE':
        if len(ob.data.splines)!=1: raise ValueError('Use one outline per curve object')
        spline=ob.data.splines[0]
        if spline.type!='POLY' or bool(spline.use_cyclic_u)!=closed:
            raise ValueError('Use a closed Poly curve for an outline, or an open Poly curve for a centreline')
        # Linked Game outlines are 2D curves rotated into the gameplay XZ
        # plane. matrix_world, not the raw control coordinates, is authoritative.
        return [_world(ob) @ Vector(p.co[:3]) for p in spline.points]
    if ob.type == 'MESH' and closed and len(ob.data.polygons)==1:
        return [_world(ob) @ ob.data.vertices[i].co for i in ob.data.polygons[0].vertices]
    raise ValueError('Select closed Poly curves or single-face meshes')


def _line_paths(ob):
    """Read open Poly/Bezier strokes or a bare mesh tree without faces."""
    matrix = _world(ob)
    if ob.type == 'CURVE':
        from mathutils.geometry import interpolate_bezier
        paths = []
        for spline in ob.data.splines:
            if spline.use_cyclic_u:
                raise ValueError('Root line guides must be open')
            if spline.type == 'POLY':
                paths.append([matrix @ Vector(p.co[:3]) for p in spline.points])
            elif spline.type == 'BEZIER':
                path = []
                for a,b in zip(spline.bezier_points,spline.bezier_points[1:]):
                    path.extend(interpolate_bezier(a.co,a.handle_right,b.handle_left,b.co,9)[:-1])
                if len(spline.bezier_points): path.append(spline.bezier_points[-1].co)
                paths.append([matrix @ p for p in path])
            else:
                raise ValueError('Use open Poly or Bezier curves for root lines')
        return paths
    if ob.type == 'MESH' and not ob.data.polygons and ob.data.edges:
        return [[matrix @ ob.data.vertices[i].co for i in e.vertices] for e in ob.data.edges]
    raise ValueError('Select open curves or a tree of mesh edges without faces')


def _guide(host,points,role,name,grab_edges=None):
    data=bpy.data.curves.new(name,'CURVE');data.dimensions='3D'
    spline=data.splines.new('POLY');spline.points.add(len(points)-1)
    inverse=_world(host).inverted()
    for p,world in zip(spline.points,points): p.co=(*(inverse @ world),1)
    spline.use_cyclic_u=role=='outline'
    ob=bpy.data.objects.new(name,data);host.users_collection[0].objects.link(ob)
    ob.parent=host;ob.matrix_parent_inverse=Matrix.Identity(4)
    ob['root_role']=role;ob['root_owner']=host['root_recipe']
    ob['grab_edges']=json.dumps(grab_edges or [])
    ob.hide_render=True;ob.hide_set(True)
    return ob


def _inputs(host):
    roots=[];spines=[];inverse=_world(host).inverted()
    for ob in sorted(host.children,key=lambda o:o.name):
        role=ob.get('root_role')
        if role not in ('outline','spine'): continue
        points=np.array([tuple(inverse @ p) for p in _points(ob,role=='outline')])
        if np.ptp(points[:,1])>.0001: raise ValueError('Root guides must be planar in local XZ')
        if abs(points[:,1].mean())>.0001: raise ValueError('Keep root guides on the root’s local depth plane')
        if role=='spine': spines.append(points[:,[0,2]])
        else:
            polygon=points[:,[0,2]]
            broken=json.loads(ob.get('broken_edges','[]'));caps=[]
            area=sum(np.cross(a,b) for a,b in zip(polygon,np.roll(polygon,-1,axis=0)))
            for i in broken:
                if not isinstance(i,int) or not 0<=i<len(polygon):
                    raise ValueError('Broken-end edge was removed; clear its markings and select again')
                a,b=polygon[i],polygon[(i+1)%len(polygon)];edge=b-a
                length=float(np.linalg.norm(edge))
                inward=np.array([-edge[1],edge[0]])/max(length,1e-8)*(1 if area>0 else -1)
                caps.append(dict(a=a.tolist(),b=b.tolist(),inward=inward.tolist(),
                                 band=min(.16,max(.025,length*.3))))
            roots.append(dict(id=ob.get('root_id',ob.name),polygon=polygon.tolist(),
                              grab_edges=json.loads(ob.get('grab_edges','[]')),end_profiles=caps))
    if host.get('root_input') == 'lines':
        return roots,spines
    return validate(roots),spines


def _image(name,pixels,data=False):
    h,w,_=pixels.shape
    im=bpy.data.images.new(name,width=w,height=h,alpha=True)
    im.colorspace_settings.name='Non-Color' if data else 'sRGB'
    rgba=np.ones((h,w,4),np.float32);rgba[:,:,:3]=pixels
    im.pixels.foreach_set(rgba.ravel());im.update();im.pack()
    im['generated_by']='roots';im['author']='Tristan Bray';im['license']='CC0-1.0'
    return im


def _material(part):
    resolution={'DRAFT':256,'PREVIEW':512,'FINAL':1024}[part['settings']['quality']]
    color,normal,orm=bark_atlas(part,resolution)
    images=[_image(part['id']+' '+name,pixels,data) for name,pixels,data in
            [('bark',color,False),('normal',normal,True),('roughness',orm[:,:,1:2].repeat(3,axis=2),True)]]
    mat=bpy.data.materials.new(part['id']+' bark');mat.use_nodes=True
    mat['root_generated']=True
    nodes=mat.node_tree.nodes;links=mat.node_tree.links
    shader=nodes.get('Principled BSDF')
    textures=[]
    for image in images:
        node=nodes.new('ShaderNodeTexImage');node.image=image;textures.append(node)
    links.new(textures[0].outputs['Color'],shader.inputs['Base Color'])
    normal_node=nodes.new('ShaderNodeNormalMap');normal_node.inputs['Strength'].default_value=1
    normal_node.uv_map='Bark'
    links.new(textures[1].outputs['Color'],normal_node.inputs['Color'])
    links.new(normal_node.outputs['Normal'],shader.inputs['Normal'])
    links.new(textures[2].outputs['Color'],shader.inputs['Roughness'])
    return mat


def _mesh(part):
    mesh=bpy.data.meshes.new(part['id'])
    try:
        mesh.from_pydata(part['vertices'].tolist(),[],part['faces'].tolist());mesh.update()
        uv=mesh.uv_layers.new(name='Bark')
        uv.data.foreach_set('uv',part['uv'].astype(np.float32).ravel())
        for polygon in mesh.polygons: polygon.use_smooth=True
        # Use Blender's MikkTSpace loop tangents, exactly the basis glTF carries.
        mesh.calc_tangents(uvmap='Bark')
        part['tangents']=np.array([(*loop.tangent,loop.bitangent_sign) for loop in mesh.loops]).reshape(-1,3,4)
        part['normals']=np.array([normal.vector[:] for normal in mesh.corner_normals]).reshape(-1,3,3)
        mesh.materials.append(_material(part))
    except Exception:
        _dispose(mesh)
        raise
    return mesh


def _dispose(mesh):
    materials=list(mesh.materials);bpy.data.meshes.remove(mesh)
    for mat in materials:
        if mat.users==0 and mat.get('root_generated'):
            images=[n.image for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image]
            bpy.data.materials.remove(mat)
            for im in images:
                if im.users==0: bpy.data.images.remove(im)


def rebuild(host):
    start=time.perf_counter();roots,spines=_inputs(host)
    settings={key:getattr(host.roots,key) for key in DEFAULTS}
    line_mode=host.get('root_input')=='lines'
    if line_mode:
        from .lines import tree
        from .line_mesh import build
        graph=tree(spines,settings)
        parts=[]
    else:
        parts=build_surfaces(roots,settings['seed'],settings,spines or None)
        structural=list(parts)
        for part in structural: parts.extend(grow(part))
    meshes=[]
    # Build all replacements before touching the old preview.
    try:
        if line_mode: meshes.append(build(graph))
        else:
            for part in parts: meshes.append(_mesh(part))
    except Exception:
        for mesh in meshes: _dispose(mesh)
        raise
    old=host.data;host.data=meshes[0]
    for child in list(host.children):
        if child.get('root_role')=='surface':
            data=child.data;bpy.data.objects.remove(child,do_unlink=True)
            if data.users==0: _dispose(data)
    if old.users==0: _dispose(old)
    for part,mesh in zip(parts[1:],meshes[1:]):
        ob=bpy.data.objects.new(part['id'],mesh);host.users_collection[0].objects.link(ob)
        ob.parent=host;ob['root_role']='surface';ob['root_owner']=host['root_recipe']
    if line_mode:
        host.data.calc_loop_triangles()
    triangles=len(host.data.loop_triangles) if line_mode else sum(len(p['faces']) for p in parts)
    rootlets=sum(p.get('rootlet_count',0) for p in parts)
    host.roots.status=f'{triangles:,} triangles · {rootlets} rootlets · {time.perf_counter()-start:.1f}s'
    host['root_settings']=json.dumps(settings)
    return dict(triangles=triangles,rootlets=rootlets,parts=parts)


def create_lines(sources,collection=None,name='Flowing root'):
    from .lines import tree
    paths=[path for ob in sources for path in _line_paths(ob)]
    if not paths: raise ValueError('Select open root lines')
    points=np.asarray([tuple(p) for path in paths for p in path])
    if np.ptp(points[:,1])>.0001: raise ValueError('Draw root lines on one XZ depth plane')
    tree([[[p.x,p.z] for p in path] for path in paths])
    if collection is None:
        collection=next((c for c in bpy.context.scene.collection.children if c.get('root_outputs') and c.library is None),None)
        if collection is None:
            collection=bpy.data.collections.new('Roots');collection['root_outputs']=True
            bpy.context.scene.collection.children.link(collection)
        collection.hide_render=False
    host=bpy.data.objects.new(name,bpy.data.meshes.new(name));collection.objects.link(host)
    host.matrix_world=Matrix.Translation(Vector(points.mean(axis=0)))
    host['grown_by']='roots';host['root_recipe']=uuid.uuid4().hex;host['root_input']='lines'
    try:
        for i,path in enumerate(paths):
            _guide(host,path,'spine',f'Root line {i:04d}')
        rebuild(host)
    except Exception:
        for child in list(host.children):
            data=child.data;bpy.data.objects.remove(child,do_unlink=True)
            if data.users==0: bpy.data.curves.remove(data)
        data=host.data;bpy.data.objects.remove(host,do_unlink=True)
        if data.users==0: _dispose(data)
        raise
    return host


def create(outlines,collection=None,name='Root'):
    # Capture and validate before copying anything into the scene.
    if not outlines: raise ValueError('Select at least one closed root outline')
    paths=[_points(ob) for ob in outlines]
    points=np.array([tuple(p) for path in paths for p in path])
    if np.ptp(points[:,1])>.0001: raise ValueError('Select outlines on one XZ depth plane')
    validate([dict(id=ob.name,polygon=[[p.x,p.z] for p in path]) for ob,path in zip(outlines,paths)])
    if collection is None:
        # The active collection may be the linked/hidden collision Guide.
        # Generated scenery must live in its own local, renderable collection.
        scene=bpy.context.scene
        collection=next((c for c in scene.collection.children if c.get('root_outputs') and c.library is None),None)
        if collection is None:
            collection=bpy.data.collections.new('Roots');collection['root_outputs']=True
            scene.collection.children.link(collection)
        collection.hide_render=False
    mesh=bpy.data.meshes.new(name);host=bpy.data.objects.new(name,mesh)
    collection.objects.link(host);host.matrix_world=Matrix.Translation(Vector(points.mean(axis=0)))
    host['grown_by']='roots';host['root_recipe']=uuid.uuid4().hex
    try:
        for ob,path in zip(outlines,paths):
            # Collision references stay untouched, including their edge IDs.
            # Treat every reference edge as playable unless explicit metadata
            # supplies the protected subset. Local art guides are unrestricted.
            reference=ob.library is not None or ob.override_library is not None or ob.name.startswith('guide.')
            raw=ob.get('grab_edges')
            edges=json.loads(raw) if isinstance(raw,str) else list(raw) if raw is not None else list(range(len(path))) if reference else []
            guide=_guide(host,path,'outline','Root outline · '+ob.name,edges)
            guide['root_id']=ob.name
        rebuild(host)
    except Exception:
        for child in list(host.children):
            data=child.data;bpy.data.objects.remove(child,do_unlink=True)
            if data.users==0: bpy.data.curves.remove(data)
        data=host.data;bpy.data.objects.remove(host,do_unlink=True)
        if data.users==0: _dispose(data)
        raise
    return host


def rebuild_all(scene):
    # Rebuilding removes old child surfaces; don't retain their RNA handles
    # in a scene-object snapshot that will be read on the next iteration.
    hosts=[ob for ob in scene.objects if ob.get('grown_by')=='roots']
    for host in hosts:
        try: yield host,rebuild(host)
        except Exception as exc:
            host.roots.status=str(exc);yield host,None


class ROOTS_OT_create(bpy.types.Operator):
    bl_idname='roots.create';bl_label='Grow from Selected Outlines';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            host=create(list(context.selected_objects))
            for ob in context.selected_objects: ob.select_set(False)
            host.select_set(True);context.view_layer.objects.active=host
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class ROOTS_OT_create_lines(bpy.types.Operator):
    bl_idname='roots.create_lines';bl_label='Grow from Line Tree';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            sources=sorted(context.selected_objects,key=lambda ob:(ob!=context.object,ob.name))
            host=create_lines(sources)
            for ob in context.selected_objects: ob.select_set(False)
            host.select_set(True);context.view_layer.objects.active=host
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class ROOTS_OT_rebuild(bpy.types.Operator):
    bl_idname='roots.rebuild';bl_label='Regenerate';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        host=owner(context.object)
        if host is None: return {'CANCELLED'}
        try: rebuild(host)
        except Exception as exc:
            host.roots.status=str(exc);self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class ROOTS_OT_guides(bpy.types.Operator):
    bl_idname='roots.guides';bl_label='Show / Hide Guides';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        host=owner(context.object)
        if host is None: return {'CANCELLED'}
        guides=[c for c in host.children if c.get('root_role') in ('outline','spine')]
        show=any(c.hide_get() for c in guides)
        for c in guides: c.hide_set(not show)
        return {'FINISHED'}


class ROOTS_OT_spine(bpy.types.Operator):
    bl_idname='roots.spine';bl_label='Copy Selected Centrelines';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        host=owner(context.object)
        if host is None: return {'CANCELLED'}
        copies=[]
        try:
            sources=[o for o in context.selected_objects if o!=host and not owner(o)]
            if not sources: raise ValueError('Select open Poly centrelines, with the root active')
            paths=[_points(o,False) for o in sources]
            for ob,path in zip(sources,paths): copies.append(_guide(host,path,'spine','Root centreline · '+ob.name))
            rebuild(host)
        except Exception as exc:
            for ob in copies:
                data=ob.data;bpy.data.objects.remove(ob,do_unlink=True)
                bpy.data.curves.remove(data)
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class ROOTS_OT_break(bpy.types.Operator):
    bl_idname='roots.break_end';bl_label='Mark / Unmark Selected Broken Ends';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        guide=context.object
        if guide is None or guide.get('root_role')!='outline': return {'CANCELLED'}
        points=guide.data.splines[0].points
        selected=[i for i,p in enumerate(points) if p.select and points[(i+1)%len(points)].select]
        if not selected:
            self.report({'ERROR'},'In Edit Mode, select both points of an end edge');return {'CANCELLED'}
        broken=set(json.loads(guide.get('broken_edges','[]')))
        if all(i in broken for i in selected): broken.difference_update(selected)
        else: broken.update(selected)
        guide['broken_edges']=json.dumps(sorted(broken))
        return {'FINISHED'}


class ROOTS_PT_panel(bpy.types.Panel):
    bl_label='Roots';bl_idname='ROOTS_PT_panel';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='Roots'
    def draw(self,context):
        layout=self.layout;host=owner(context.object)
        if host is None:
            layout.label(text='Select a tree of open lines')
            layout.operator('roots.create_lines')
            layout.separator()
            layout.label(text='Legacy exact silhouettes')
            layout.operator('roots.create');return
        for key in ('depth','taper','age','bark_strength','rootlet_density','seed','quality'):
            if key=='rootlet_density' and host.get('root_input')=='lines': continue
            layout.prop(host.roots,key)
        if host.get('root_input')=='lines': layout.label(text='Draw small side roots as extra lines')
        layout.operator('roots.rebuild')
        layout.operator('roots.guides');layout.operator('roots.spine')
        if context.object and context.object.get('root_role')=='outline':
            layout.operator('roots.break_end')
        if host.roots.status: layout.label(text=host.roots.status)


CLASSES=(RootSettings,ROOTS_OT_create_lines,ROOTS_OT_create,ROOTS_OT_rebuild,ROOTS_OT_guides,ROOTS_OT_spine,ROOTS_OT_break,ROOTS_PT_panel)


def register():
    if hasattr(bpy.types.Object,'roots'): return
    for cls in CLASSES: bpy.utils.register_class(cls)
    bpy.types.Object.roots=PointerProperty(type=RootSettings)


def unregister():
    if not hasattr(bpy.types.Object,'roots'): return
    del bpy.types.Object.roots
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
