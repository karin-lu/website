"""Headless visual study and Blender recipe/export smoke test.

blender -b --factory-startup --python-exit-code 1 --python
 tools/blender/roots/preview.py -- assets-src/studies/roots [--baseline DIR]
"""
import json
import os
import sys
import time
import types
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

TOOLS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOLS))
import roots
from roots import addon
from roots.fixtures import fixtures
from roots.model import stable_seed


def poly(r,collection):
    data=bpy.data.curves.new(r['id'],'CURVE');data.dimensions='3D'
    line=data.splines.new('POLY');line.points.add(len(r['polygon'])-1)
    for p,(x,z) in zip(line.points,r['polygon']): p.co=(x,0,z,1)
    line.use_cyclic_u=True
    ob=bpy.data.objects.new(r['id'],data);collection.objects.link(ob)
    return ob


def aim(ob,at): ob.rotation_euler=(Vector(at)-ob.location).to_track_quat('-Z','Y').to_euler()


def text(label,x,z,collection):
    data=bpy.data.curves.new(label,'FONT');data.body=label;data.size=.13;data.align_x='CENTER'
    ob=bpy.data.objects.new(label,data);collection.objects.link(ob)
    ob.location=(x,-.24,z);ob.rotation_euler=(np.pi/2,0,0)
    mat=bpy.data.materials.get('labels')
    if mat is None:
        mat=bpy.data.materials.new('labels');mat.diffuse_color=(.65,.72,.64,1)
    data.materials.append(mat)
    return ob


argv=sys.argv[sys.argv.index('--')+1:]
out=Path(argv[0]).resolve();out.mkdir(parents=True,exist_ok=True)
baseline=Path(argv[argv.index('--baseline')+1]).resolve() if '--baseline' in argv else None
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
roots.register();scene=bpy.context.scene
guides=bpy.data.collections.new('Guide study references');scene.collection.children.link(guides)
guides.hide_render=True
outputs=bpy.data.collections.new('Root study');scene.collection.children.link(outputs)
labels=bpy.data.collections.new('Guide study labels');scene.collection.children.link(labels)
report=[];hosts=[]
examples=fixtures()
for i,r in enumerate(examples):
    source=poly(r,guides)
    # Simulate the hidden guide collection used by the Game add-on.
    source.location.x=i*2.7
    before=[tuple(p.co) for p in source.data.splines[0].points]
    host=addon.create([source],name='Root '+r['id']);hosts.append(host)
    assert all(not c.hide_render and c.library is None and not c.name.lower().startswith('guide') for c in host.users_collection)
    host.roots.quality='PREVIEW';host.roots.rootlet_density=.65
    guide=next(c for c in host.children if c.get('root_role')=='outline')
    guide['broken_edges']=json.dumps({'fork':[3,6],'curved':[18],'taper':[2]}[r['id']])
    result=addon.rebuild(host)
    assert before==[tuple(p.co) for p in source.data.splines[0].points]
    assert all(c.hide_render for c in host.children if c.get('root_role')=='outline')
    report.append(dict(id=r['id'],triangles=result['triangles'],rootlets=result['rootlets'],
                       branches=len(result['parts'][0]['graph']['branches']),
                       junctions=len(result['parts'][0]['graph']['junctions'])))
    text('NEW · '+r['id'],i*2.7,-.28,labels)

# Invalid regeneration must leave the last valid surface in place.
host=hosts[0];guide=next(c for c in host.children if c.get('root_role')=='outline')
previous=host.data;point=guide.data.splines[0].points[1];saved=point.co.copy()
point.co=guide.data.splines[0].points[0].co.copy()
try:
    addon.rebuild(host)
    raise AssertionError('Invalid guide accepted')
except ValueError: assert host.data==previous
point.co=saved

if baseline:
    sys.path.insert(0,str(baseline))
    shim=types.ModuleType('polygon_roots');shim.stable_seed=stable_seed
    sys.modules['polygon_roots']=shim
    import sideview_surface as old
    for i,r in enumerate(examples):
        part=old.build_surfaces([r],'roots')[0]
        # Preserve the old flat normal and old bark field for a fair baseline.
        original=addon.bark_atlas
        addon.bark_atlas=lambda p,size: old.bark_atlas(p,size)
        try:
            part['settings']={'quality':'PREVIEW'}
            mesh=addon._mesh(part)
        finally: addon.bark_atlas=original
        ob=bpy.data.objects.new('OLD '+r['id'],mesh);outputs.objects.link(ob)
        ob.location=(i*2.7,0,2.95)
        text('OLD · '+r['id'],i*2.7,2.68,labels)

world=bpy.data.worlds.new('Root study world');world.use_nodes=True
world.node_tree.nodes.get('Background').inputs[0].default_value=(.12,.16,.2,1)
world.node_tree.nodes.get('Background').inputs[1].default_value=.45;scene.world=world
for name,position,power,size in [('key',(-3,-4,7),1000,5),('fill',(7,-2,4),650,4),('rim',(3,3,6),850,3)]:
    data=bpy.data.lights.new(name,'AREA');data.energy=power*.45;data.shape='DISK';data.size=size
    ob=bpy.data.objects.new(name,data);scene.collection.objects.link(ob);ob.location=position;aim(ob,(2.7,0,2.5))
data=bpy.data.cameras.new('Study camera');data.type='ORTHO';data.ortho_scale=9.2
camera=bpy.data.objects.new('Study camera',data);scene.collection.objects.link(camera);scene.camera=camera
scene.render.engine='CYCLES';scene.cycles.samples=32;scene.cycles.use_denoising=True
scene.render.resolution_x=1500;scene.render.resolution_y=1080 if baseline else 600;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX'
scene.view_settings.look='AgX - Medium High Contrast'
scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
center=(2.7,0,2.7 if baseline else 1.15)
camera.location=(2.7,-12,center[2]);aim(camera,center)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'roots-study.blend'))
for name,position in [('front',(2.7,-12,center[2])),('oblique',(6.7,-12,center[2]+2))]:
    camera.location=position;aim(camera,center)
    scene.render.filepath=str(out/(name+'.png'))
    bpy.ops.render.render(write_still=True)
    print('[roots study] rendered '+name,flush=True)

# Separate shippable fixture: no baseline or labels. Reopen to exercise saved
# recipes/properties/packed maps, then let the real scene exporter rebuild it.
for ob in list(outputs.objects):
    if ob.name.startswith('OLD '): ob.hide_render=True
camera.location=(2.7,-12,1.2);aim(camera,(2.7,0,1.2))
bpy.ops.wm.save_as_mainfile(filepath=str(out/'roots-fixture.blend'))
bpy.ops.wm.open_mainfile(filepath=str(out/'roots-fixture.blend'))
for host,result in roots.rebuild_all(bpy.context.scene):
    assert result is not None,host.roots.status
    assert any(c.get('root_role')=='outline' for c in host.children)
    for node in host.data.materials[0].node_tree.nodes:
        if node.type=='TEX_IMAGE':
            pixels=np.array(node.image.pixels[:]).reshape(-1,4)
            print('[roots study] packed image '+node.image.name+' mean '+str(pixels[:,:3].mean(axis=0)),flush=True)
(out/'report.json').write_text(json.dumps(report,indent=2))
print('[roots study] recipe persistence, invalid-rebuild preservation and renders PASS '+json.dumps(report),flush=True)
