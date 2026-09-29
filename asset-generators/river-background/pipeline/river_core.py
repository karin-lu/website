"""Blender authoring operations. Never resets, saves over, or regenerates a scene."""
from __future__ import annotations
import hashlib, json, math, os, subprocess, sys, tempfile, uuid
from pathlib import Path
import bpy, bmesh
from mathutils import Matrix, Vector

HERE=Path(__file__).resolve().parent
HOME=HERE.parent
ROOT=HERE.parents[2]
NEAR='10_BACKGROUND_NEAR'; FAR='20_BACKGROUND_FAR'; BACK='30_BACKDROP_SOURCE'
RECIPES='80_ROCK_RECIPES'; BACKUPS='81_PREVIOUS_MESHES'
LAYERS=(NEAR,FAR,BACK)

REFERENCE_COLLECTIONS=('00_REFERENCE / gameplay','00_REFERENCE / ball')

def foreground_preview(scene, visible=True):
    """Show locked gameplay guides in the artist view; they never become scenery."""
    missing=[name for name in REFERENCE_COLLECTIONS if bpy.data.collections.get(name) is None]
    if missing:
        raise ValueError('Foreground references missing: '+', '.join(missing))
    count=0
    for name in REFERENCE_COLLECTIONS:
        col=bpy.data.collections[name]
        col.hide_viewport=not visible
        col.hide_render=not visible
        col.hide_select=True
        # Snapshot: visibility writes invalidate Blender's live all_objects iterator.
        for ob in list(col.all_objects):
            ob.hide_select=True
            ob['river_reference_only']=True
            ancestor=ob
            old_backdrop=bool(ob.get('river_old_backdrop'))
            while ancestor:
                old_backdrop |= 'body 205 ' in ancestor.name
                ancestor=ancestor.parent
            if old_backdrop:
                ob.hide_render=True
                ob.hide_set(True)
            count+=1
        # A collection can also be excluded/hidden separately in each view layer.
        def enable_path(layer):
            if layer.collection==col:
                layer.exclude=False
                layer.hide_viewport=False
                return True
            contains=False
            for child in layer.children:
                contains=enable_path(child) or contains
            if contains:
                layer.exclude=False
                layer.hide_viewport=False
            return contains
        for view_layer in scene.view_layers:
            enable_path(view_layer.layer_collection)
    scene['river_foreground_preview']=bool(visible)
    return count

def opening_composition(scene):
    """Use the shared opening framing and a clearly masked camera view."""
    cam=bpy.data.objects.get('Route replay / fixed background zoom')
    if cam is None:
        cam=bpy.data.objects.get('01 Opening / background camera')
    if cam is None:
        raise ValueError('The river opening camera is missing')
    scene.frame_set(1)
    scene.camera=cam
    cam.data.show_passepartout=True
    cam.data.passepartout_alpha=1
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type=='VIEW_3D':
                space=area.spaces.active
                space.region_3d.view_perspective='CAMERA'
                space.region_3d.view_camera_offset=(0,0)
                # The camera frame fills most of the viewport while leaving its border.
                space.region_3d.view_camera_zoom=18
                space.lock_camera=False
                space.clip_end=1000
                space.overlay.show_overlays=False
                space.shading.type='MATERIAL'
                space.shading.use_scene_world=True
                space.shading.use_scene_lights=True
    return cam

def collection(name):
    c=bpy.data.collections.get(name)
    if c is None:
        c=bpy.data.collections.new(name); bpy.context.scene.collection.children.link(c)
    return c

def move(obj,col):
    for old in list(obj.users_collection): old.objects.unlink(obj)
    col.objects.link(obj)

def mesh_hash(mesh):
    h=hashlib.sha256()
    for v in mesh.vertices: h.update(('%0.9g,%0.9g,%0.9g;' % tuple(v.co)).encode())
    for p in mesh.polygons: h.update(str(tuple(p.vertices)).encode())
    return h.hexdigest()

def seal(obj):
    obj['river_mesh_hash']=mesh_hash(obj.data)

def authored_world(ob):
    """Hidden recipe collections do not get an evaluated matrix_world."""
    local=ob.matrix_basis.copy()
    if ob.parent:
        return authored_world(ob.parent) @ ob.matrix_parent_inverse @ local
    return local

def datablocks():
    return {item for prop in bpy.data.bl_rna.properties if prop.type=='COLLECTION'
            for item in getattr(bpy.data,prop.identifier) if isinstance(item,bpy.types.ID)}

def validate_worker(ob,slabs):
    if not ob or ob.type!='MESH' or not slabs:
        raise ValueError('Worker file has no complete rock')
    mesh=ob.data
    if not mesh.vertices or not mesh.polygons or any(not math.isfinite(n) for v in mesh.vertices for n in v.co):
        raise ValueError('Worker rock mesh must have finite vertices and faces')
    bm=bmesh.new()
    try:
        bm.from_mesh(mesh)
        volume=abs(bm.calc_volume(signed=True))
        if any(not e.is_manifold for e in bm.edges) or any(not v.link_faces for v in bm.verts):
            raise ValueError('Worker rock mesh must be watertight')
        if not math.isfinite(volume) or volume<=1e-12 or any(f.calc_area()<=1e-12 for f in bm.faces):
            raise ValueError('Worker rock mesh must have nonzero volume and faces')
    finally:
        bm.free()
    try:
        recipe=json.loads(ob['river_recipe'])
        outline=recipe['outline']; params=recipe['params']
        if not isinstance(outline,list) or len(outline)<3 or not isinstance(params,dict): raise ValueError()
        if any(len(p)!=2 or any(not isinstance(n,(int,float)) or not math.isfinite(n) for n in p) for p in outline):
            raise ValueError()
        area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(outline,outline[1:]+outline[:1]))
        if abs(area)<=1e-12 or not isinstance(recipe['preset'],str): raise ValueError()
        if not isinstance(params['depth'],(int,float)) or not math.isfinite(params['depth']) or params['depth']<=0:
            raise ValueError()
    except (KeyError,TypeError,ValueError):
        raise ValueError('Worker file has no valid rock recipe') from None
    if not any(s.type=='MESH' and len(s.data.polygons) for s in slabs.objects):
        raise ValueError('Worker file has no source slabs')
    return recipe

def outline_object(outline,name,parent,owner):
    curve=bpy.data.curves.new(name,'CURVE'); curve.dimensions='3D'
    line=curve.splines.new('POLY'); line.points.add(len(outline)-1)
    for pt,(x,z) in zip(line.points,outline): pt.co=(x,0,z,1)
    line.use_cyclic_u=True
    ob=bpy.data.objects.new(name,curve); collection(RECIPES).objects.link(ob)
    ob.parent=parent; ob.matrix_parent_inverse=Matrix.Identity(4); ob['river_outline_owner']=owner
    ob.hide_render=True; ob.display_type='WIRE'; ob.show_in_front=True
    return ob

def append_rock(file,name,layer=NEAR):
    before=datablocks()
    try:
        with bpy.data.libraries.load(str(file),link=False) as (src,dst):
            dst.objects=['SceneryRock']; dst.collections=['SOURCE_SLABS']
        ob=dst.objects[0]; slabs=dst.collections[0]
        recipe=validate_worker(ob,slabs)
        col=collection(layer); col.objects.link(ob)
        root=bpy.data.objects.new(name+' / placement',None); col.objects.link(root)
        root.empty_display_type='PLAIN_AXES'; root.empty_display_size=.2
        ob.parent=root; ob.matrix_parent_inverse=Matrix.Identity(4); ob.name=name
        rid=str(uuid.uuid4()); ob['river_id']=rid; ob['river_mode']='PROCEDURAL'; ob['river_layer']=layer
        root['river_formation']=rid
        slabs.name='Sources / '+name+' / '+rid[:8]
        collection(RECIPES).children.link(slabs); slabs.hide_render=True; slabs.hide_viewport=True
        for s in slabs.objects:
            s.parent=ob; s.matrix_parent_inverse=Matrix.Identity(4)
        ob['river_sources']=slabs.name
        guide=outline_object(recipe['outline'],name+' / outline',ob,rid)
        ob['river_outline']=guide.name
        collection(RECIPES).hide_render=True
        collection(RECIPES).hide_viewport=True
        seal(ob)
        return ob
    except Exception:
        imported=datablocks()-before
        if imported: bpy.data.batch_remove(ids=imported)
        raise

def copy_recipe_helpers(source,target):
    """Copy construction in rock coordinates, including any artist guide/slab edits."""
    relative=authored_world(source).inverted()
    def local_for(helper):
        # A moved linked duplicate still refers to the original rock's helpers.
        if helper.parent and 'river_recipe' in helper.parent:
            return helper.matrix_parent_inverse @ helper.matrix_basis
        return relative @ authored_world(helper)
    src=bpy.data.collections.get(source.get('river_sources',''))
    if src:
        copies=bpy.data.collections.new('Sources / '+target.name+' / '+target['river_id'][:8])
        collection(RECIPES).children.link(copies); copies.hide_viewport=True; copies.hide_render=True
        for s in src.objects:
            local=local_for(s)
            n=s.copy(); n.data=s.data.copy(); copies.objects.link(n)
            n.parent=target; n.matrix_parent_inverse=Matrix.Identity(4); n.matrix_basis=local
        target['river_sources']=copies.name
    guide=bpy.data.objects.get(source.get('river_outline',''))
    if guide:
        local=local_for(guide)
        n=guide.copy(); n.data=guide.data.copy(); collection(RECIPES).objects.link(n)
        n.parent=target; n.matrix_parent_inverse=Matrix.Identity(4); n.matrix_basis=local
        n['river_outline_owner']=target['river_id']; target['river_outline']=n.name

def make_unique(ob):
    if ob.type!='MESH' or 'river_recipe' not in ob: raise ValueError('Select a generated rock')
    ob.data=ob.data.copy()
    ob['river_id']=str(uuid.uuid4())
    # The object's own outline/sources must also become independent.
    copy_recipe_helpers(ob,ob)
    # Do not mark existing hand edits procedural simply by making data unique.
    if mesh_hash(ob.data)!=ob.get('river_mesh_hash'): ob['river_mode']='MANUAL'
    seal(ob)

def recipe_for(ob):
    recipe=json.loads(ob['river_recipe'])
    guide=bpy.data.objects.get(ob.get('river_outline',''))
    if guide:
        if guide.type!='CURVE' or len(guide.data.splines)!=1: raise ValueError('Use one closed polygon outline')
        spline=guide.data.splines[0]
        if spline.type!='POLY' or not spline.use_cyclic_u: raise ValueError('Outline must be a closed poly curve')
        # Hidden guides keep authored transforms even when Blender skips evaluation.
        mat=(guide.matrix_parent_inverse @ guide.matrix_basis if guide.parent==ob
             else authored_world(ob).inverted() @ authored_world(guide))
        coords=[mat @ Vector(p.co[:3]) for p in spline.points]
        if max(abs(p.y) for p in coords)>.001: raise ValueError('Keep outline in the rock X/Z plane')
        recipe['outline']=[[p.x,p.z] for p in coords]
    return recipe

def assert_rebuildable(ob):
    if ob.type!='MESH' or 'river_recipe' not in ob: raise ValueError('Select a procedural rock mesh')
    if ob.get('river_mode')=='MANUAL': raise ValueError('Manual mesh protected. Use Rebuild as new variant.')
    if mesh_hash(ob.data)!=ob.get('river_mesh_hash'):
        raise ValueError('Mesh has hand edits. Keep manual mesh or rebuild as a new variant.')
    if ob.data.shape_keys or ob.vertex_groups or any(m.type in {'MULTIRES','HOOK','SURFACE_DEFORM','MESH_DEFORM'} for m in ob.modifiers):
        raise ValueError('Topology-dependent edits detected. Rebuild as a new variant.')

def backup(ob):
    old=ob.copy(); old.data=ob.data.copy(); old.name=ob.name+' / previous'
    c=collection(BACKUPS); c.objects.link(old); c.hide_render=True; c.hide_viewport=True
    old['river_id']=str(uuid.uuid4()); old['river_backup']=True
    copy_recipe_helpers(ob,old)
    return old

def remove_unused_helpers(sources_name,guide_name):
    if not any(o.get('river_sources')==sources_name for o in bpy.data.objects):
        sources=bpy.data.collections.get(sources_name)
        if sources:
            for item in list(sources.objects):
                data=item.data; bpy.data.objects.remove(item,do_unlink=True)
                if data and data.users==0: bpy.data.batch_remove(ids=[data])
            bpy.data.collections.remove(sources)
    if not any(o.get('river_outline')==guide_name for o in bpy.data.objects):
        guide=bpy.data.objects.get(guide_name)
        if guide:
            data=guide.data; bpy.data.objects.remove(guide,do_unlink=True)
            if data and data.users==0: bpy.data.batch_remove(ids=[data])

def replace_from_worker(ob,file,variant=False):
    if not variant: assert_rebuildable(ob)
    fresh=append_rock(file,ob.name+' / new',ob.get('river_layer',NEAR))
    if variant:
        fresh.parent.matrix_world=ob.parent.matrix_world.copy() if ob.parent else ob.matrix_world.copy()
        fresh.matrix_basis=ob.matrix_basis.copy() if ob.parent else Matrix.Identity(4)
        return fresh
    backup(ob)
    previous_sources=ob.get('river_sources',''); previous_guide=ob.get('river_outline','')
    old_mesh=ob.data; ob.data=fresh.data
    ob['river_recipe']=fresh['river_recipe']; ob['river_mode']='PROCEDURAL'
    if 'river_new_polygon' in ob: del ob['river_new_polygon']
    # Retain artist material overrides if slots still have corresponding roles.
    for i,mat in enumerate(old_mesh.materials):
        if i<len(ob.data.materials): ob.data.materials[i]=mat
    # Move generated construction data into the target's local frame.
    sources=bpy.data.collections[fresh['river_sources']]
    for s in sources.objects:
        s.parent=ob; s.matrix_parent_inverse=Matrix.Identity(4)
    ob['river_sources']=sources.name
    newguide=bpy.data.objects[fresh['river_outline']]
    newguide.parent=ob; newguide.matrix_parent_inverse=Matrix.Identity(4)
    newguide['river_outline_owner']=ob['river_id']
    ob['river_outline']=newguide.name
    root=fresh.parent
    bpy.data.objects.remove(fresh,do_unlink=True); bpy.data.objects.remove(root,do_unlink=True)
    remove_unused_helpers(previous_sources,previous_guide)
    ob['river_attachments_review']='Geometry rebuilt: review moss and plant attachment positions.'
    seal(ob); return ob

def assemble_sources(ob):
    """Explicitly join artist-edited construction slabs, without rerunning the recipe."""
    src=bpy.data.collections.get(ob.get('river_sources',''))
    if not src: raise ValueError('No source slabs found')
    scratch=collection('90_EXPORT_PREVIEW'); copies=[]
    active=bpy.context.view_layer.objects.active
    try:
        for s in src.objects:
            if s.type!='MESH': continue
            n=s.copy(); n.data=s.data.copy(); scratch.objects.link(n)
            n.parent=None; n.matrix_world=authored_world(ob).inverted() @ authored_world(s)
            copies.append(n)
        if not copies: raise ValueError('Source collection is empty')
        base=copies[0]
        bpy.context.view_layer.update()
        bpy.context.view_layer.objects.active=base
        for n in copies[1:]:
            mod=base.modifiers.new('Assemble edited slab','BOOLEAN'); mod.operation='UNION'; mod.solver='EXACT'; mod.object=n
            bpy.ops.object.modifier_apply(modifier=mod.name)
        if not len(base.data.polygons): raise ValueError('Assembly produced no faces')
        backup(ob); ob.data=base.data.copy(); ob.data.transform(authored_world(base))
        ob['river_mode']='MANUAL'; seal(ob)
    finally:
        for n in copies: bpy.data.objects.remove(n,do_unlink=True)
        bpy.context.view_layer.objects.active=active

def change_depth(ob,depth):
    root=ob.parent or ob
    scene=bpy.context.scene; d=scene.get('river_distance',10.2375)
    cx,cz=scene.get('river_origin',[10.85,-8])
    old=root.location.y
    if d+old<=0 or d+depth<=0: raise ValueError('Depth must remain behind camera')
    ratio=(d+depth)/(d+old)
    root.location.x=cx+(root.location.x-cx)*ratio
    root.location.z=cz+(root.location.z-cz)*ratio
    root.location.y=depth; root.scale*=ratio
    layer=NEAR if depth<60 else FAR
    for item in [root,*root.children_recursive]:
        lineage=item
        hidden_backup=False
        while lineage:
            if lineage.get('river_backup') or any(c.name==BACKUPS for c in lineage.users_collection):
                hidden_backup=True; break
            lineage=lineage.parent
        if hidden_backup or item.get('river_outline_owner') or any(c.name.startswith('Sources /') for c in item.users_collection): continue
        move(item,collection(layer)); item['river_layer']=layer

def python_path():
    preferred=os.environ.get('RIVER_PYTHON') or bpy.context.scene.get('river_python')
    if preferred and Path(preferred).is_file(): return preferred
    import shutil
    for candidate in (str(ROOT/'rope/.venv/Scripts/python.exe'), str(ROOT/'rope/.venv/bin/python'), shutil.which('python3'), shutil.which('python')):
        if candidate and Path(candidate).is_file() and 'blender' not in candidate.lower(): return candidate
    raise ValueError('Set scene river_python to ordinary Python with numpy, scipy and shapely')

def launch_worker(recipe):
    out=Path(tempfile.mkdtemp(prefix='river-rock-'))
    (out/'input.json').write_text(json.dumps(recipe))
    log=open(out/'worker.log','w',encoding='utf-8')
    kwargs={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    command=[python_path(),str(HERE/'rock_worker.py'),str(out/'input.json'),str(out),
             '--blender',bpy.app.binary_path]
    if bpy.context.scene.get('river_candidate') == 'river-dream-v5':
        command += ['--repair',str(HOME/'dream-candidate/repair_rocks.py')]
    proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,**kwargs)
    return proc,out,log


def worker_failure(output):
    path=Path(output)/'worker.log'
    details=path.read_text(encoding='utf-8',errors='replace') if path.exists() else ''
    if 'MemoryError' in details or 'out of memory' in details.lower():
        return 'Rock generation ran out of memory. Close unused Blender instances and retry. Existing meshes retained.'
    return 'Generation failed; meshes retained. See '+str(path)

def export_command(output):
    if not bpy.data.filepath or bpy.data.is_dirty:
        raise ValueError('Save your Blender scene before exporting. Export uses the saved scene.')
    return [bpy.app.binary_path,'--background',bpy.data.filepath,'--python-exit-code','1',
            '--python',str(HERE/'export_background.py'),'--','--output',str(output)]
