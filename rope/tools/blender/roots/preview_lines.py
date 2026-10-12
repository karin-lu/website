"""Run in background Blender: --python preview_lines.py -- OUTPUT_DIRECTORY."""
import sys
import json
from pathlib import Path
import bpy
import bmesh
import numpy as np
from mathutils import Vector

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import roots
from roots import addon

out=Path(sys.argv[sys.argv.index('--')+1]).resolve()
out.mkdir(parents=True,exist_ok=True)
roots.register()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene

examples=[
    ('Branching gesture',[[[0,0],[.05,.7],[.3,1.5],[.15,2.2],[.65,2.9]],
                         [[.3,1.5],[-.45,1.95],[-.95,2.15],[-1.25,2.65]],
                         [[.15,2.2],[.8,2.35],[1.2,2.75]],
                         [[-.45,1.95],[-.6,2.55],[-.45,2.9]]]),
    ('Trailing roots',[[[-1,2.9],[-.7,2.2],[-.1,1.8],[.15,1.1],[.65,.55],[1.05,.45]],
                       [[-.1,1.8],[-.55,1.3],[-.35,.75],[-.65,.15]],
                       [[.15,1.1],[.9,1.25],[1.3,.95]]]),
    ('Spreading roots',[[[0,2.9],[-.1,2.2],[.15,1.5],[-.05,.95],[-.8,.55],[-1.3,.1]],
                        [[.15,1.5],[.8,1],[.95,.45],[1.4,.2]],
                        [[-.05,.95],[.05,.35],[.5,.05]],
                        [[-.8,.55],[-1.15,.7],[-1.45,.65]]])]

def curve(path,name,offset):
    data=bpy.data.curves.new(name,'CURVE');data.dimensions='3D'
    spline=data.splines.new('POLY');spline.points.add(len(path)-1)
    for p,(x,z) in zip(spline.points,path): p.co=(x+offset,0,z,1)
    ob=bpy.data.objects.new(name,data);scene.collection.objects.link(ob)
    return ob

def material(name,color):
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    shader=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    shader.inputs['Base Color'].default_value=(*color,1)
    shader.inputs['Roughness'].default_value=.95
    return mat

guide_mat=material('Sketch lines',(.40,.49,.41))
hosts=[]
for index,(label,paths) in enumerate(examples):
    x=index*3.35
    sources=[curve(p,f'Stroke {index}-{j}',x) for j,p in enumerate(paths)]
    host=addon.create_lines(sources,name=label)
    hosts.append(host)
    host.roots.depth=.48
    addon.rebuild(host)
    for source in sources:
        source.location.z+=3.6
        source.data.bevel_depth=.013
        source.data.bevel_resolution=3
        source.data.materials.append(guide_mat)
    text=bpy.data.curves.new(label,'FONT');text.body=label;text.size=.16;text.align_x='CENTER'
    ob=bpy.data.objects.new(label+' label',text);scene.collection.objects.link(ob)
    ob.location=(x,-.12,-.35);ob.rotation_euler=(np.pi/2,0,0)
    text.materials.append(guide_mat)

# Exercise the saved recipe and an invalid edit without losing the valid mesh.
host=hosts[0]
guide=next(c for c in host.children if c.get('root_role')=='spine')
old=host.data
guide.data.splines[0].points[0].co.y=1
try:
    addon.rebuild(host)
    raise AssertionError('Nonplanar guide accepted')
except ValueError:
    assert host.data==old
finally:
    guide.data.splines[0].points[0].co.y=0

def aim(ob,target): ob.rotation_euler=(Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler()
scene.world.color=(.22,.22,.22)
for name,location,energy,size in [('Key',(-3,-5,8),1250,7),('Fill',(9,-3,5),650,6)]:
    light=bpy.data.lights.new(name,'AREA');light.energy=energy;light.shape='DISK';light.size=size
    ob=bpy.data.objects.new(name,light);scene.collection.objects.link(ob);ob.location=location;aim(ob,(3,0,3))
camera=bpy.data.objects.new('Line study camera',bpy.data.cameras.new('Line study camera'))
scene.collection.objects.link(camera);scene.camera=camera;camera.data.type='ORTHO';camera.data.ortho_scale=10.8
camera.location=(3.35,-18,3.1);aim(camera,(3.35,0,3.1))
scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=True
scene.render.resolution_x=1600;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX'
scene.render.image_settings.file_format='PNG'
scene.render.filepath=str(out/'line-roots.png')
bpy.ops.wm.save_as_mainfile(filepath=str(out/'line-roots.blend'))
bpy.ops.render.render(write_still=True)
camera.location=(0,-12,1.35);aim(camera,(0,0,1.35));camera.data.ortho_scale=3.65
scene.render.resolution_x=1100;scene.render.resolution_y=1100
scene.render.filepath=str(out/'bark-closeup.png')
bpy.ops.render.render(write_still=True)
camera.data.ortho_scale=10.8
scene.render.resolution_x=1600;scene.render.resolution_y=1100
camera.location=(6.8,-18,4.8);aim(camera,(3.35,0,3.1))
scene.render.filepath=str(out/'line-roots-oblique.png')
bpy.ops.render.render(write_still=True)
report=[]
for host in hosts:
    mesh=host.data
    mesh.calc_loop_triangles()
    bm=bmesh.new();bm.from_mesh(mesh)
    assert all(e.is_manifold for e in bm.edges),host.name+' has an open surface'
    assert bm.calc_volume(signed=True)>0,host.name+' has inverted volume'
    unseen=set(bm.verts);islands=0
    while unseen:
        islands+=1;stack=[unseen.pop()]
        while stack:
            vertex=stack.pop()
            for edge in vertex.link_edges:
                neighbor=edge.other_vert(vertex)
                if neighbor in unseen: unseen.remove(neighbor);stack.append(neighbor)
    assert islands==1,host.name+' has detached fragments'
    bm.free()
    report.append(dict(name=host.name,vertices=len(mesh.vertices),triangles=len(mesh.loop_triangles)))
    host.select_set(True)
for ob in scene.objects:
    if ob not in hosts: ob.select_set(False)
bpy.ops.export_scene.gltf(filepath=str(out/'line-roots.glb'),use_selection=True,export_format='GLB')
bpy.ops.wm.open_mainfile(filepath=str(out/'line-roots.blend'))
for host,result in addon.rebuild_all(bpy.context.scene): assert result is not None,host.roots.status
(out/'report.json').write_text(json.dumps(report,indent=2))
print('LINE ROOTS: save/reopen/rebuild, invalid-edit preservation and glTF export PASS',flush=True)
