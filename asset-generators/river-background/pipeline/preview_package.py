"""Render the actual exported GLBs and atlas in a clean scene for round-trip QA."""
import argparse,json,math,sys,struct,subprocess,shutil,tempfile
from pathlib import Path
import bpy
from mathutils import Vector
HERE=Path(__file__).resolve().parent; sys.path.insert(0,str(HERE))
from export_background import emission_material,gpu

p=argparse.ArgumentParser(); p.add_argument('package'); p.add_argument('--source'); p.add_argument('--width',type=int,default=1280)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]); root=Path(a.package).resolve(); manifest=json.loads((root/'package.json').read_text())
bpy.ops.wm.read_factory_settings(use_empty=True); s=bpy.context.scene
s.render.engine='CYCLES'; s.cycles.samples=8; s.cycles.use_denoising=True; gpu()
s.view_settings.view_transform='Standard'; s.view_settings.look='None'; s.view_settings.exposure=0
s.render.resolution_x=a.width; s.render.resolution_y=round(a.width*9/16); s.render.resolution_percentage=100
s.render.image_settings.file_format='PNG'; s.render.image_settings.color_mode='RGB'
for layer in manifest['layers']:
    file=root/layer['file']; raw=file.read_bytes(); size=struct.unpack_from('<I',raw,12)[0]
    header=json.loads(raw[20:20+size])
    if 'EXT_meshopt_compression' in header.get('extensionsRequired',[]):
        decoded=Path(tempfile.mkdtemp(prefix='river-preview-'))/(layer['id']+'.glb')
        subprocess.run([shutil.which('node') or 'C:/Program Files/nodejs/node.exe',str(HERE/'decode_preview.mjs'),str(file),str(decoded)],check=True)
        file=decoded
    bpy.ops.import_scene.gltf(filepath=str(file))
d=manifest['camera']['distance']; cx,cz=manifest['camera']['origin']; k=(d+240)/d
data=bpy.data.cameras.new('Runtime matched camera'); data.lens=12/math.tan(math.radians(manifest['camera']['fovYDeg']/2))
data.sensor_fit='VERTICAL'; data.sensor_height=24; data.clip_end=600
cam=bpy.data.objects.new('Runtime matched camera',data); s.collection.objects.link(cam)
cam.location=(cx,-d,cz); cam.rotation_euler=(math.pi/2,0,0); s.camera=cam
plate=manifest['backdrop']
bpy.ops.mesh.primitive_plane_add(size=2,location=(cx,240,cz),rotation=(math.pi/2,0,0))
back=bpy.context.object; back.name='Atlas'; back.scale=(plate['worldWidth']*k/2,plate['worldHeight']*k/2,1)
back.data.materials.append(emission_material('Distant image',image=bpy.data.images.load(str(root/plate['file']))))
s.world=bpy.data.worlds.new('Preview world'); s.world.use_nodes=True
s.world.node_tree.nodes['Background'].inputs[0].default_value=(.04,.08,.12,1)
s.world.node_tree.nodes['Background'].inputs[1].default_value=.3
bpy.context.view_layer.update()
print('PREVIEW_CAMERA',list(cam.location),data.lens,flush=True)
refs=[]; checkpoints=[]
if a.source:
    # Import references before rendering, keeping the source scene untouched.
    sys.path.insert(0,str(HERE.parent))
    from foreground_guide import import_foreground,add_ball_guide
    ref,_=import_foreground(include_proxies=True); ball,_=add_ball_guide(); refs=[ref,ball]
    # Visibility changes invalidate Blender's live all_objects iterator.
    for ob in list(ref.all_objects):
        ancestor=ob
        while ancestor:
            if 'body 205 ' in ancestor.name:
                ob.hide_render=True; break
            ancestor=ancestor.parent
    report=Path(a.source).parent/'build_report.json'
    checkpoints=json.loads(report.read_text()).get('checkpoints',[]) if report.exists() else []
    for name,position,power in [('Preview key',(7,-4,-3),850),('Preview fill',(15,-2,-5),250)]:
        data=bpy.data.lights.new(name,'AREA'); data.energy=power; data.shape='DISK'; data.size=7
        light=bpy.data.objects.new(name,data); s.collection.objects.link(light); light.location=position
        light.rotation_euler=(Vector((10.85,0,-8))-light.location).to_track_quat('-Z','Y').to_euler()
    bpy.context.view_layer.update()
for col in refs: col.hide_render=True
s.render.filepath=str(root/'opening_background.png'); bpy.ops.render.render(write_still=True)
if refs:
    for col in refs: col.hide_render=False
    s.render.filepath=str(root/'opening_with_gameplay.png'); bpy.ops.render.render(write_still=True)
    for col in refs: col.hide_render=True
for i,(x,z) in enumerate(checkpoints[1:],2):
    cam.location=(x,-d,z)
    back.location=(x-(x-cx)*plate['pan']*k,240,z-(z-cz)*plate['pan']*k)
    s.render.resolution_x=800; s.render.resolution_y=450
    s.render.filepath=str(root/f'route_{i:02d}.png'); bpy.ops.render.render(write_still=True)
print('PACKAGE_PREVIEWS_READY',str(root),flush=True)
