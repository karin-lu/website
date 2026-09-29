"""Export a saved artist scene in a disposable Blender process.

Cycles bakes lighting into vertex colors on evaluated copies. Source meshes,
materials, modifiers, source slabs and hand edits are never written back.
"""
import argparse, hashlib, json, math, os, sys, tempfile, time, struct, subprocess, shutil, uuid
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

HERE=Path(__file__).resolve().parent; sys.path.insert(0,str(HERE))
import river_core as core

def gpu():
    try:
        pref=bpy.context.preferences.addons['cycles'].preferences
        pref.compute_device_type='OPTIX'; pref.get_devices()
        found=False
        for device in pref.devices:
            device.use=device.type!='CPU'; found |= device.use
        bpy.context.scene.cycles.device='GPU' if found else 'CPU'
    except Exception: bpy.context.scene.cycles.device='CPU'

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def emission_material(name,attribute=None,image=None):
    mat=bpy.data.materials.new(name); mat.use_nodes=True
    ns=mat.node_tree.nodes; ns.clear()
    out=ns.new('ShaderNodeOutputMaterial'); emit=ns.new('ShaderNodeEmission')
    mat.node_tree.links.new(emit.outputs[0],out.inputs[0])
    if attribute:
        vc=ns.new('ShaderNodeVertexColor'); vc.layer_name=attribute
        mat.node_tree.links.new(vc.outputs['Color'],emit.inputs['Color'])
    if image:
        tex=ns.new('ShaderNodeTexImage'); tex.image=image
        mat.node_tree.links.new(tex.outputs['Color'],emit.inputs['Color'])
    return mat

def show_only(names):
    for col in bpy.context.scene.collection.children:
        col.hide_render=col.name not in names
        col.hide_viewport=col.name not in names

def bake_plate(stage,width):
    s=bpy.context.scene
    show_only({core.BACK,'40_LIGHTING','01_CAMERAS'})
    camdata=bpy.data.cameras.new('Export / atlas camera'); camdata.type='ORTHO'; camdata.sensor_fit='HORIZONTAL'
    camdata.ortho_scale=float(s.get('river_plate_width',10))
    cam=bpy.data.objects.new('Export / atlas camera',camdata); core.collection('01_CAMERAS').objects.link(cam)
    cam.location=(0,-10,0); cam.rotation_euler=(math.pi/2,0,0); s.camera=cam
    s.render.resolution_x=width
    s.render.resolution_y=round(width*float(s.get('river_plate_height',7))/float(s.get('river_plate_width',10)))
    s.render.resolution_percentage=100; s.render.image_settings.file_format='PNG'; s.render.image_settings.color_mode='RGB'
    s.render.filepath=str(stage/'backdrop.png'); s.cycles.samples=24
    bpy.ops.render.render(write_still=True)
    return stage/'backdrop.png'

def copies_by_cell():
    # Opt-in cards: object river_preserve_material=True; finite atlas UVs in
    # [0,1]; an image-backed base-color material. Material overrides are
    # river_alpha_mode (MASK/OPAQUE), river_alpha_cutoff, river_color_factor RGBA.
    # All material edits below affect disposable copies only.
    s=bpy.context.scene
    for name in (core.NEAR,core.FAR):
        c=core.collection(name); c.hide_render=False; c.hide_viewport=False
    bpy.context.view_layer.update(); deps=bpy.context.evaluated_depsgraph_get()
    groups={}; preserved_materials={}; export=core.collection('90_EXPORT_PREVIEW')
    for layer in (core.NEAR,core.FAR):
        for source in list(core.collection(layer).all_objects):
            if source.type!='MESH' or source.hide_render: continue
            preserve=source.get('river_preserve_material') is True
            mesh=bpy.data.meshes.new_from_object(source.evaluated_get(deps),preserve_all_data_layers=preserve,depsgraph=deps)
            if not mesh.polygons: bpy.data.meshes.remove(mesh); continue
            mesh.transform(source.matrix_world)
            if preserve:
                if not mesh.uv_layers.active: raise ValueError('Preserved material needs active UVs: '+source.name)
                uv=np.empty(len(mesh.uv_layers.active.data)*2,dtype=np.float32)
                mesh.uv_layers.active.data.foreach_get('uv',uv)
                if not np.isfinite(uv).all() or np.any(uv<0) or np.any(uv>1):
                    raise ValueError('Preserved UVs must be finite atlas coordinates in [0,1]: '+source.name)
                if not mesh.materials or any(mat is None for mat in mesh.materials):
                    raise ValueError('Preserved geometry needs materials: '+source.name)
                for index,mat in enumerate(list(mesh.materials)):
                    if mat not in preserved_materials:
                        copy=mat.copy(); copy.name=mat.name+' / preserved export'
                        copy['river_preserve_material']=True
                        if s.get('river_preserved_bake_lighting') is True: copy['river_preserved_bake_lighting']=True
                        mode=str(mat.get('river_alpha_mode','MASK'))
                        cutoff=float(mat.get('river_alpha_cutoff',.5))
                        if mode not in ('MASK','OPAQUE') or not math.isfinite(cutoff) or not 0<=cutoff<=1:
                            raise ValueError('Invalid preserved alpha settings: '+mat.name)
                        copy['river_alpha_mode']=mode; copy['river_alpha_cutoff']=cutoff
                        if 'river_color_factor' in mat:
                            factor=list(mat['river_color_factor'])
                            if len(factor)!=4 or any(not math.isfinite(v) or not 0<=v<=1 for v in factor):
                                raise ValueError('Invalid preserved color factor: '+mat.name)
                            copy['river_color_factor']=factor
                        preserved_materials[mat]=copy
                    mesh.materials[index]=preserved_materials[mat]
                # Atlas appearance must not accidentally multiply old mesh colors.
                for color in list(mesh.color_attributes): mesh.color_attributes.remove(color)
            ob=bpy.data.objects.new('Export / '+source.name,mesh); export.objects.link(ob)
            # Partition by the formation centre for predictable route culling.
            centre=source.matrix_world.translation
            key=(layer,math.floor(centre.x/16),math.floor(centre.z/16))
            if preserve: key=(*key,'preserved')
            groups.setdefault(key,[]).append(ob)
    show_only({'90_EXPORT_PREVIEW','40_LIGHTING','01_CAMERAS'})
    out=[]
    for key,objects in groups.items():
        bpy.ops.object.select_all(action='DESELECT')
        for ob in objects: ob.select_set(True)
        ob=objects[0]; bpy.context.view_layer.objects.active=ob
        bpy.ops.object.join(); ob.name='/'.join(map(str,key))
        # Keep silhouettes while removing facets smaller than background pixels.
        preserve=len(key)==4
        if len(ob.data.polygons)>2000 and not preserve:
            ratio=float(s.get('river_near_decimate',.55) if key[0]==core.NEAR else s.get('river_far_decimate',.38))
            if not math.isfinite(ratio): raise ValueError('Nonfinite background decimation ratio')
            dec=ob.modifiers.new('Background detail budget','DECIMATE'); dec.ratio=max(.01,min(1,ratio))
            bpy.ops.object.modifier_apply(modifier=dec.name)
        tri=ob.modifiers.new('Export triangles','TRIANGULATE'); bpy.ops.object.modifier_apply(modifier=tri.name)
        ob['background_only']=True; ob['depth_layer']='near' if key[0]==core.NEAR else 'far'
        if preserve:
            ob['river_preserve_material']=True
            if s.get('river_preserved_bake_lighting') is True:
                ob['river_preserved_bake_lighting']=True
                # The neutral-white bake proxy has no atlas alpha. It must
                # never cast rectangular card shadows onto rocks or cards.
                ob.visible_shadow=False
            out.append(ob); continue
        # Old vertex colors may be present on manual artist geometry; preserve
        # them for the source shader and bake into a distinct active layer.
        color=ob.data.color_attributes.new(name='RiverPrelit',type='FLOAT_COLOR',domain='CORNER')
        ob.data.color_attributes.active_color=color
        ob.data.color_attributes.render_color_index=ob.data.color_attributes.find('RiverPrelit')
        out.append(ob)
    return out

def bake_geometry(objects,samples):
    cards=[ob for ob in objects if ob.get('river_preserved_bake_lighting') is True]
    objects=[ob for ob in objects if not ob.get('river_preserve_material')]
    s=bpy.context.scene; s.cycles.samples=samples
    s.render.bake.target='VERTEX_COLORS'; s.render.bake.use_clear=True
    s.render.bake.use_pass_direct=True; s.render.bake.use_pass_indirect=True
    s.render.bake.use_pass_diffuse=True; s.render.bake.use_pass_glossy=False
    s.render.bake.use_pass_transmission=False; s.render.bake.use_pass_emit=True
    for i,ob in enumerate(objects):
        bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active=ob
        print('BAKE_CELL',i+1,len(objects),ob.name,len(ob.data.polygons),flush=True)
        bpy.ops.object.bake(type='COMBINED',target='VERTEX_COLORS')
    # Keep the original stone shaders in the scene while sampling card light.
    # Replacing them with baked emission first would feed the bake a new GI field.
    if cards: bake_card_lighting(cards)
    mat=emission_material('River / baked diffuse and atmosphere','RiverPrelit')
    for ob in objects:
        col=ob.data.color_attributes['RiverPrelit']; arr=np.empty(len(col.data)*4,dtype=np.float32)
        col.data.foreach_get('color',arr); arr=arr.reshape(-1,4)
        if not np.isfinite(arr).all(): raise ValueError('Nonfinite baked colors: '+ob.name)
        # Atmosphere is a separately authored background-only color wash. This
        # is deliberately independent of gameplay fog and is baked once.
        amount=float(s.get('river_near_haze',.15) if ob['depth_layer']=='near' else s.get('river_far_haze',.47))
        fog=np.array(s.get('river_haze_color',(.068,.135,.175)),dtype=np.float32)
        arr[:,:3]=np.clip(arr[:,:3]*(1-amount)+fog*amount,0,1); arr[:,3]=1
        col.data.foreach_set('color',arr.ravel())
        for other in list(ob.data.color_attributes):
            if other.name!='RiverPrelit': ob.data.color_attributes.remove(other)
        ob.data.materials.clear(); ob.data.materials.append(mat)
        for face in ob.data.polygons: face.material_index=0

def bake_card_lighting(objects):
    # Atlas pigmentation stays in the restored texture. This is neutral-white
    # diffuse irradiance plus the same .16 ambient emission used by the stones.
    # No layer haze is applied: card distance grading remains an art decision.
    white=bpy.data.materials.new('River / neutral card irradiance'); white.use_nodes=True
    shader=white.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=(1,1,1,1)
    shader.inputs['Metallic'].default_value=0; shader.inputs['Roughness'].default_value=1
    shader.inputs['Emission Color'].default_value=(1,1,1,1); shader.inputs['Emission Strength'].default_value=.16
    for i,ob in enumerate(objects):
        originals=list(ob.data.materials); indices=[face.material_index for face in ob.data.polygons]
        color=ob.data.color_attributes.new(name='RiverCardLight',type='FLOAT_COLOR',domain='CORNER')
        ob.data.color_attributes.active_color=color
        ob.data.color_attributes.render_color_index=ob.data.color_attributes.find('RiverCardLight')
        try:
            ob.data.materials.clear(); ob.data.materials.append(white)
            for face in ob.data.polygons: face.material_index=0
            bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active=ob
            print('BAKE_CARD_LIGHT',i+1,len(objects),ob.name,len(ob.data.polygons),flush=True)
            bpy.ops.object.bake(type='COMBINED',target='VERTEX_COLORS')
            arr=np.empty(len(color.data)*4,dtype=np.float32); color.data.foreach_get('color',arr); arr=arr.reshape(-1,4)
            if not np.isfinite(arr).all(): raise ValueError('Nonfinite card irradiance: '+ob.name)
            arr[:,:3]=np.clip(arr[:,:3],0,1); arr[:,3]=1; color.data.foreach_set('color',arr.ravel())
        finally:
            ob.data.materials.clear()
            for material in originals: ob.data.materials.append(material)
            for face,index in zip(ob.data.polygons,indices): face.material_index=index

def export_glb(objects,layer,path):
    bpy.ops.object.select_all(action='DESELECT')
    selected=[ob for ob in objects if ob['depth_layer']==layer]
    for ob in selected: ob.select_set(True)
    bpy.context.view_layer.objects.active=selected[0]
    bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,
                              export_extras=True,export_yup=True,export_cameras=False,export_lights=False,
                              **({'export_vertex_color':'ACTIVE'} if any(ob.get('river_preserved_bake_lighting') for ob in selected) else {}))
    # Blender exports an emission attribute as COLOR_1 beside a constant-white
    # COLOR_0, but glTF emission does not consume vertex colors. Make the baked
    # color the unlit base color explicitly; keep the binary/accessors intact.
    raw=path.read_bytes(); size=struct.unpack_from('<I',raw,12)[0]
    doc=json.loads(raw[20:20+size]); tail=raw[20+size:]
    preserved_indices=set(); lit_preserved_indices=set()
    for index,mat in enumerate(doc.get('materials',[])):
        extras=mat.get('extras',{})
        if extras.get('river_preserve_material') is True:
            pbr=mat.get('pbrMetallicRoughness',{})
            if 'baseColorTexture' not in pbr: raise ValueError('Preserved material lost base-color image: '+mat.get('name',''))
            preserved_indices.add(index)
            if extras.get('river_preserved_bake_lighting') is True: lit_preserved_indices.add(index)
            mat['pbrMetallicRoughness']={**{k:v for k,v in pbr.items() if k in ('baseColorTexture','baseColorFactor')},
                                         'metallicFactor':0,'roughnessFactor':1}
            if 'river_color_factor' in extras: mat['pbrMetallicRoughness']['baseColorFactor']=extras['river_color_factor']
            mat['alphaMode']=extras['river_alpha_mode']
            if mat['alphaMode']=='MASK': mat['alphaCutoff']=extras['river_alpha_cutoff']
            else: mat.pop('alphaCutoff',None)
            for field in ('emissiveFactor','emissiveTexture','normalTexture','occlusionTexture'): mat.pop(field,None)
            mat['extensions']={'KHR_materials_unlit':{}}
            continue
        mat.pop('emissiveFactor',None)
        mat['pbrMetallicRoughness']={'baseColorFactor':[1,1,1,1],'metallicFactor':0,'roughnessFactor':1}
        mat.setdefault('extensions',{})['KHR_materials_unlit']={}
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']:
            attrs=primitive['attributes']
            if primitive.get('material') in preserved_indices:
                if 'TEXCOORD_0' not in attrs: raise ValueError('Preserved material lost UVs')
                if primitive.get('material') in lit_preserved_indices:
                    if 'COLOR_1' in attrs: attrs['COLOR_0']=attrs.pop('COLOR_1')
                    if 'COLOR_0' not in attrs: raise ValueError('Preserved material lost RiverCardLight colors')
                else:
                    attrs.pop('COLOR_0',None); attrs.pop('COLOR_1',None)
                continue
            if 'COLOR_1' in attrs: attrs['COLOR_0']=attrs.pop('COLOR_1')
            if 'COLOR_0' not in attrs: raise ValueError('Export lost baked vertex colors')
    doc['extensionsUsed']=list(dict.fromkeys([*doc.get('extensionsUsed',[]),'KHR_materials_unlit']))
    encoded=json.dumps(doc,separators=(',',':')).encode(); encoded+=b' '*((-len(encoded))%4)
    path.write_bytes(struct.pack('<III',0x46546c67,2,20+len(encoded)+len(tail))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+tail)
    # Bounds in the exported Three coordinate system.
    points=[ob.matrix_world@v.co for ob in selected for v in ob.data.vertices]
    pts=np.array([(p.x,p.z,-p.y) for p in points])
    return {'triangles':sum(len(ob.data.polygons) for ob in selected),'cells':len(selected),
            'bounds':{'min':pts.min(axis=0).tolist(),'max':pts.max(axis=0).tolist()}}

def main():
    from configure_scene import configure
    configure()
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); p.add_argument('--plate-only',action='store_true')
    p.add_argument('--staging-root',help='Optional scratch directory outside a watched public asset tree (same filesystem as output)')
    p.add_argument('--width',type=int,default=2048); p.add_argument('--samples',type=int,default=8); p.add_argument('--no-preview',action='store_true')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]); out=Path(a.output).resolve(); out.mkdir(parents=True,exist_ok=True)
    s=bpy.context.scene
    staging=Path(a.staging_root or s.get('river_export_staging_path',str(out))).resolve()
    staging.mkdir(parents=True,exist_ok=True)
    # Python 3.13 mkdtemp creates owner-only Windows ACLs. In a sandboxed
    # Blender worker those directories cannot be scanned by the user's Vite
    # process. These contain public art, so inherit the project directory ACL.
    stage=staging/('.export-'+uuid.uuid4().hex)
    stage.mkdir(mode=0o777); start=time.time()
    s.render.engine='CYCLES'; gpu(); s.view_settings.view_transform='Standard'; s.view_settings.look='None'; s.view_settings.exposure=0
    plate=bake_plate(stage,a.width)
    if a.plate_only:
        os.replace(plate,out/'backdrop-preview.png'); print('PLATE_READY',out/'backdrop-preview.png'); return
    objects=copies_by_cell(); bake_geometry(objects,a.samples)
    manifest={'version':1,'colorSpace':'srgb-display','camera':{'fovYDeg':math.degrees(2*math.atan(12/70)),
              'distance':float(s.get('river_distance',10.2375)),'origin':list(s.get('river_origin',[10.85,-8])),
              'zoomResponse':float(s.get('river_zoom_response',0))},'layers':[],
              'backdrop':{'worldWidth':float(s.get('river_plate_width',10)),'worldHeight':float(s.get('river_plate_height',7)),
              'origin':list(s.get('river_origin',[10.85,-8])),'pan':float(s.get('river_plate_pan',.02))},
              'hideBodyIds':[], 'replaceSceneScenery': True}
    if 'river_foliage_fog_color' in s:
        color=list(s['river_foliage_fog_color']); near=float(s.get('river_foliage_fog_near',20)); far=float(s.get('river_foliage_fog_far',190))
        if len(color)!=3 or any(not math.isfinite(v) or not 0<=v<=1 for v in color) or not math.isfinite(near) or not math.isfinite(far) or not 0<=near<far:
            raise ValueError('Invalid preserved foliage fog settings')
        manifest['foliageFog']={'color':color,'near':near,'far':far}
    report={'source':bpy.data.filepath,'sourceSha256':digest(Path(bpy.data.filepath)),'layers':{},'bake':'Cycles Combined to vertex colors; diffuse + emission, no specular; atmosphere wash once'}
    if s.get('river_preserved_bake_lighting') is True:
        report['cardLighting']={'attribute':'RiverCardLight','neutralEmission':.16,'hazeBaked':False,'cardShadows':False}
    for layer in ('near','far'):
        file=stage/(layer+'.glb'); report['layers'][layer]=export_glb(objects,layer,file)
        sha=digest(file); name=f'{layer}-{sha[:12]}.glb'; os.replace(file,stage/name)
        manifest['layers'].append({'id':layer,'file':name,'bytes':(stage/name).stat().st_size,'sha256':sha})
    sha=digest(plate); name='backdrop-'+sha[:12]+'.png'; os.replace(plate,stage/name)
    manifest['backdrop'].update(file=name,bytes=(stage/name).stat().st_size,sha256=sha)
    (stage/'package.json').write_text(json.dumps(manifest,indent=2))
    if not a.no_preview:
        # Use a fresh scene and the exported GLBs, so this verifies the actual
        # material/axis round trip instead of rendering the pre-export objects.
        subprocess.run([bpy.app.binary_path,'--background','--factory-startup','--python-exit-code','1',
                        '--python',str(HERE/'preview_package.py'),'--',str(stage),'--source',bpy.data.filepath],check=True)
    node=shutil.which('node') or 'C:/Program Files/nodejs/node.exe'
    subprocess.run([node,str(HERE/'optimize_package.mjs'),str(stage)],check=True)
    subprocess.run([node,str(HERE/'verify_package.mjs'),str(stage)],check=True)
    manifest=json.loads((stage/'package.json').read_text())
    for asset in [*manifest['layers'],manifest['backdrop']]:
        os.replace(stage/asset['file'],out/asset['file'])
    for file in stage.glob('*.png'): os.replace(file,out/file.name)
    for name in ('optimization.json','verification.json'):
        if (stage/name).exists(): os.replace(stage/name,out/name)
    report['seconds']=round(time.time()-start,2)
    os.replace(stage/'package.json',out/'package.json')
    (out/'export_report.json').write_text(json.dumps(report,indent=2))
    print('BACKGROUND_PACKAGE_READY',json.dumps(report),flush=True)

if __name__=='__main__': main()
