"""Shared foliage construction used by Connected v5.

Use build_connected.py for v5, or refit_grotto.py for a saved scene.
"""
import hashlib
import json
import math
import random
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'pipeline'))
import river_core as core


def main(revision=3, refit=False, output_dir=None, save_result=True):
    scene = bpy.context.scene
    if refit and scene.get('river_candidate') != f'river-dream-v{revision}':
        raise ValueError('Refitting requires the matching saved candidate scene')
    source = Path(bpy.data.filepath)
    out = Path(output_dir) if output_dir else HERE / f'output-v{revision}'
    if save_result:
        out.mkdir(exist_ok=True)
    scene.name = f'Sunken Grotto v{revision} / layered grotto'
    scene['river_candidate'] = f'river-dream-v{revision}'
    from configure_scene import configure
    configure()
    scene['river_export_path'] = str(core.ROOT / f'rope/public/backgrounds/river-dream-v{revision}')
    scene['river_preserved_bake_lighting'] = True
    scene['river_foliage_fog_color'] = [.028,.064,.092]
    scene['river_foliage_fog_near'] = 20.
    scene['river_foliage_fog_far'] = 190.
    scene['river_near_decimate'] = .16
    scene['river_far_decimate'] = .10
    scene['river_near_haze'] = .19
    scene['river_far_haze'] = .40
    scene['river_haze_color'] = [.028, .064, .092]
    # Retain original recipes, source outlines and helper collections untouched.
    rocks = []
    removed = 0
    for layer in (core.NEAR, core.FAR):
        for ob in list(core.collection(layer).all_objects):
            if ob.type != 'MESH':
                continue
            if 'river_recipe' in ob:
                rocks.append(ob)
            else:
                bpy.data.objects.remove(ob, do_unlink=True)
                removed += 1

    if revision == 4 and not refit:
        from grotto_geology import enrich_formations
        rocks = enrich_formations(rocks)
    if revision == 5 and not refit:
        from connected_grotto import build_masses
        rocks = build_masses(rocks)
    if revision == 5:
        scene['river_near_decimate'] = .30
        scene['river_far_decimate'] = .25
        scene['river_near_haze'] = .14
        scene['river_far_haze'] = .38
    if revision == 4:
        scene['river_near_decimate'] = .24
        scene['river_far_decimate'] = .14
        scene['river_near_haze'] = .12
        scene['river_far_haze'] = .34

    # Soft continuous pigment on the rock itself: broad patches, feathered
    # transitions, only upward faces. All of this is baked, not a runtime shader.
    for mat in ([] if refit else {m for ob in rocks for m in ob.data.materials if m}):
        ns, links = mat.node_tree.nodes, mat.node_tree.links
        bs = ns.get('Principled BSDF')
        base = tuple(bs.inputs['Base Color'].default_value)
        geom = ns.new('ShaderNodeNewGeometry')
        separate = ns.new('ShaderNodeSeparateXYZ')
        links.new(geom.outputs['Normal'], separate.inputs[0])
        slope = ns.new('ShaderNodeMapRange')
        slope.inputs['From Min'].default_value = .25
        slope.inputs['From Max'].default_value = .85
        links.new(separate.outputs['Z'], slope.inputs['Value'])
        tex = ns.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value = .85
        tex.inputs['Detail'].default_value = 2
        links.new(geom.outputs['Position'], tex.inputs['Vector'])
        ramp = ns.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position = .36
        ramp.color_ramp.elements[1].position = .61
        links.new(tex.outputs['Fac'], ramp.inputs['Fac'])
        mask = ns.new('ShaderNodeMath'); mask.operation = 'MULTIPLY'
        links.new(slope.outputs['Result'], mask.inputs[0])
        links.new(ramp.outputs['Color'], mask.inputs[1])
        mix = ns.new('ShaderNodeMixRGB'); mix.blend_type = 'MIX'
        mix.inputs[1].default_value = (*[c*.85 for c in base[:3]], 1)
        mix.inputs[2].default_value = (.028, .046, .025, 1)
        links.new(mask.outputs[0], mix.inputs[0])
        links.new(mix.outputs[0], bs.inputs['Base Color'])
        links.new(mix.outputs[0], bs.inputs['Emission Color'])
        bs.inputs['Emission Strength'].default_value = .20

    if revision == 4 and not refit:
        from grotto_geology import enrich_materials
        enrich_materials(rocks)
    if revision == 5 and not refit:
        from grotto_geology import enrich_materials
        enrich_materials(rocks, strength=.35)

    atlas = bpy.data.images.load(str(HERE/'textures/foliage-components-v3.png'))
    atlas.pack()
    width, height = atlas.size
    pixels = np.asarray(atlas.pixels[:], dtype=np.float32).reshape(height, width, 4)
    # Inspect alpha to locate each isolated component and its actual stem root.
    # This avoids treating the center of an asymmetric painted sprig as a root.
    bounds,roots=[],[]
    top_pixels=pixels[::-1]
    for sprite,(qx,qy) in enumerate(((0,0),(1,0),(0,1),(1,1))):
        ox,oy=qx*(width//2),qy*(height//2)
        aa=top_pixels[oy:oy+height//2,ox:ox+width//2,3]>.15
        yy,xx=np.where(aa)
        x0,y0=max(ox,int(xx.min()+ox)-3),max(oy,int(yy.min()+oy)-3)
        x1,y1=min(ox+width//2,int(xx.max()+ox)+4),min(oy+height//2,int(yy.max()+oy)+4)
        bounds.append((x0,y0,x1,y1))
        root_rows=top_pixels[y0:y0+10,x0:x1,3] if sprite==2 else top_pixels[y1-10:y1,x0:x1,3]
        _,rx=np.where(root_rows>.15)
        roots.append(float(np.median(rx)+x0))
    mats = {}
    for layer, factor in ((core.NEAR, (.42,.54,.57,1)), (core.FAR, (.55,.70,.85,1))):
        mat = bpy.data.materials.new('V3 / unshaded leaf albedo / '+layer)
        mat.use_nodes = True
        mat.use_backface_culling = False
        mat['river_alpha_mode'] = 'MASK'
        mat['river_alpha_cutoff'] = .42
        mat['river_color_factor'] = factor
        ns, links = mat.node_tree.nodes, mat.node_tree.links
        bs = ns.get('Principled BSDF')
        tex = ns.new('ShaderNodeTexImage'); tex.image = atlas
        tint = ns.new('ShaderNodeMixRGB'); tint.blend_type='MULTIPLY'
        tint.inputs[0].default_value=1; tint.inputs[2].default_value=factor
        links.new(tex.outputs['Color'], tint.inputs[1])
        links.new(tint.outputs[0], bs.inputs['Base Color'])
        links.new(tint.outputs[0], bs.inputs['Emission Color'])
        links.new(tex.outputs['Alpha'], bs.inputs['Alpha'])
        bs.inputs['Emission Strength'].default_value=.16
        bs.inputs['Specular IOR Level'].default_value=0
        bs.inputs['Roughness'].default_value=1
        mats[layer]=mat

    moss_image=bpy.data.images.load(str(HERE/'textures/soft-moss-v2.png')); moss_image.pack()
    moss_mat=mats[core.NEAR].copy(); moss_mat.name='V3 / locally lit surface moss'
    moss_mat['river_color_factor']=(.25,.35,.37,1)
    for node in moss_mat.node_tree.nodes:
        if node.type=='TEX_IMAGE': node.image=moss_image
        if node.type=='MIX_RGB': node.inputs[2].default_value=(.25,.35,.37,1)
    moss_patches=[]
    cards = []
    def card(name, anchor, size, sprite, layer, seed, parent=None):
        rng = random.Random(seed)
        x0,y0,x1,y1=bounds[sprite]
        # Short curved components, each tightly bounded to visible alpha.
        # Geometry trims empty texture margins; MASK handles holes within leaves.
        verts, faces, uvs = [], [], []
        bands=5 if layer==core.NEAR else 3
        aspect=(x1-x0)/(y1-y0)
        for band in range(bands):
            ya=round(y0+(y1-y0)*band/bands)
            yb=round(y0+(y1-y0)*(band+1)/bands)
            mask=pixels[height-yb:height-ya,x0:x1,3]>.1
            occupied=np.where(mask.any(axis=0))[0]
            if len(occupied)==0: continue
            xa=max(x0,x0+int(occupied[0])-3); xb=min(x1,x0+int(occupied[-1])+4)
            start=len(verts)
            for x,y in ((xa,yb),(xb,yb),(xb,ya),(xa,ya)):
                t=(y-y0)/(y1-y0)
                z=(1-t)*size if sprite!=2 else -t*size
                dx=((x-roots[sprite])/(x1-x0))*size*aspect
                # A drooping tip and a depth bow keep cards from looking rigid.
                f=t if sprite==2 else 1-t
                dx+=math.sin(f*math.pi)*size*.12
                bend=math.sin(f*math.pi*.85)*size*.24
                z-=math.sin(f*math.pi*.5)**3*size*.10 if sprite!=2 else 0
                verts.append((dx,bend,z))
                uvs.append((x/width,1-y/height))
            faces.append(tuple(range(start,start+4)))
        mesh=bpy.data.meshes.new(name); mesh.from_pydata(verts,[],faces)
        uv=mesh.uv_layers.new(name='UVMap')
        for face in mesh.polygons:
            for loop in face.loop_indices: uv.data[loop].uv=uvs[mesh.loops[loop].vertex_index]
        mesh.materials.append(mats[layer])
        ob=bpy.data.objects.new(name,mesh); core.collection(layer).objects.link(ob)
        ob.location=anchor
        ob.rotation_euler=(rng.uniform(-.45,.35),rng.uniform(-.65,.65),rng.uniform(-.8,.8))
        ob.visible_shadow=False
        ob['river_preserve_material']=True
        ob['river_sprite']=sprite
        if parent:
            ob.parent=parent
            ob.matrix_parent_inverse=parent.matrix_world.inverted()
        cards.append(ob)
        return ob

    bpy.context.view_layer.update()
    clusters=[]
    if revision == 5:
        from growth_patches import growth_sites, patch_weight
        for rock in rocks:
            rock['river_growth_sites'] = json.dumps(growth_sites(
                rock, scene['river_distance'], rock['river_layer'] == core.FAR))
    for index,rock in enumerate(rocks):
        if any(word in rock.name for word in ('ceiling','hanging tooth','buttress','spire')): continue
        stable_seed = int(hashlib.sha256(str(rock.get('river_id', rock.name)).encode()).hexdigest()[:7], 16)
        if revision >= 4:
            index = stable_seed
        layer=rock['river_layer']; rng=random.Random(6100+index)
        moisture = rock.get('river_moisture', .55) if revision >= 4 else .55
        target_clusters = (rng.choice((1, 2, 3, 4)) if moisture > .5 else rng.choice((0, 1))) if revision >= 4 else 2
        if revision == 5:
            target_clusters = len(json.loads(rock['river_growth_sites']))
        rock['river_plant_seed'] = 6100+index
        rock['river_attachment_rule'] = 'upward facets, visible contour; rerun layered pass after shape edits'
        if target_clusters == 0:
            continue
        rock.data.calc_loop_triangles()
        verts=[rock.matrix_world@v.co for v in rock.data.vertices]
        bvh=BVHTree.FromPolygons(verts,[tuple(t.vertices) for t in rock.data.loop_triangles],all_triangles=True)
        lo=Vector(tuple(min(v[k] for v in verts) for k in range(3)))
        hi=Vector(tuple(max(v[k] for v in verts) for k in range(3)))
        candidates=[]
        for i in range(80):
            x=lo.x+(hi.x-lo.x)*rng.uniform(.15,.85)
            y=lo.y+(hi.y-lo.y)*rng.uniform(.10,.55)
            hit,n,_,_=bvh.ray_cast(Vector((x,y,hi.z+1)),Vector((0,0,-1)))
            if hit is not None and n.z>.45 and hit.z>lo.z+(hi.z-lo.z)*.45:
                candidates.append(hit)
        candidates.sort(key=lambda p:p.y)
        selected=[]
        for hit in candidates:
            spacing = .10 if revision == 5 else (.15 if revision == 4 else .23)
            if all(abs(hit.x-other.x)>(hi.x-lo.x)*spacing for other in selected): selected.append(hit)
            if len(selected)==(target_clusters if layer==core.NEAR or revision == 5 else 1): break
        # From the fixed front-facing game camera, a root on a rear top facet
        # can project onto a blank cliff face. Fit roots to the visible upper
        # contour instead. The downward ray provides a stable source x; front
        # rays locate the upper silhouette at that x, independent of camera pan.
        anchored=[]
        for hit in selected:
            for step in range(180):
                z=hi.z-(hi.z-lo.z)*step/180
                front,_,_,_=bvh.ray_cast(Vector((hit.x,lo.y-1,z)),Vector((0,1,0)),hi.y-lo.y+2)
                if front is not None:
                    anchored.append(front)
                    break
        selected=anchored
        sites = json.loads(rock['river_growth_sites']) if revision == 5 else []
        if revision == 5:
            selected = [Vector(site['root']) for site in sites if not site['ceiling']]
        scale=(10.2375+rock.parent.location.y)/10.2375
        if layer==core.NEAR and selected:
            # A thin fitted decal, not a solid cap. Texture alpha opens bare
            # stone gaps; sampled surface heights follow the procedural rock.
            pv,pf,puv=[],[],[]; grid={}; nx,ny=22,12
            if revision == 5:
                nx = math.ceil((hi.x-lo.x)/(scale*.08125))
                ny = math.ceil((hi.y-lo.y)*.72/(scale*.08125))
            for iy in range(ny+1):
                for ix in range(nx+1):
                    u,v=ix/nx,iy/ny
                    x=lo.x+(hi.x-lo.x)*u; y=lo.y+(hi.y-lo.y)*v*.72
                    if revision == 5:
                        x, y = lo.x+ix*scale*.08125, lo.y+iy*scale*.08125
                    if revision == 5 and patch_weight(x, y, sites) < .08: continue
                    hit,n,_,_=bvh.ray_cast(Vector((x,y,hi.z+1)),Vector((0,0,-1)))
                    if hit is None or n.z<.24 or (revision != 5 and hit.z<lo.z+(hi.z-lo.z)*.60): continue
                    grid[ix,iy]=len(pv)
                    pv.append(tuple(hit+n*scale*.012))
                    puv.append((ix/8, iy/8) if revision == 5 else (u,v))
            for ix,iy in list(grid):
                keys=((ix,iy),(ix+1,iy),(ix+1,iy+1),(ix,iy+1))
                if not all(k in grid for k in keys): continue
                face=tuple(grid[k] for k in keys)
                if max(pv[k][2] for k in face)-min(pv[k][2] for k in face)>scale*.35: continue
                pf.append(face)
            if pf:
                mesh=bpy.data.meshes.new(rock.name+' / surface moss texture')
                mesh.from_pydata(pv,[],pf); mesh.materials.append(moss_mat)
                uv=mesh.uv_layers.new(name='UVMap')
                for face in mesh.polygons:
                    # Split UV seams at tile boundaries to retain [0,1] atlas
                    # coordinates while preserving a constant world texel scale.
                    base = tuple(math.floor(min(puv[k][axis] for k in face.vertices)) for axis in (0,1)) if revision == 5 else (0,0)
                    for loop in face.loop_indices:
                        uv.data[loop].uv=tuple(puv[mesh.loops[loop].vertex_index][axis]-base[axis] for axis in (0,1))
                patch=bpy.data.objects.new(rock.name+' / surface moss texture',mesh); core.collection(layer).objects.link(patch)
                patch['river_preserve_material']=True; patch['river_surface_moss']=True
                patch.visible_shadow=False
                patch.parent=rock.parent; patch.matrix_parent_inverse=rock.parent.matrix_world.inverted()
                moss_patches.append(patch)
        depth=rock.parent.location.y
        distance_size=max(.45,min(1.,(36/max(36,depth))**.65))
        for i,hit in enumerate(selected):
            component_count=rng.randint(3,6 if revision >= 4 else 5) if layer==core.NEAR else rng.randint(1,2)
            if revision == 5: component_count = rng.randint(2, 4) if layer == core.NEAR else 1
            cluster={'rock':rock.name,'layer':layer,'depth':depth,'pieces':component_count,'screenSizeFactor':distance_size}
            clusters.append(cluster)
            for j in range(component_count):
                # Back cards sit deeper and lower. Roots overlap only locally;
                # crown silhouettes vary with asymmetric heights and yaw.
                offset=Vector((rng.uniform(-.022,.022)*scale,rng.uniform(-.12,-.045)*scale,-.035))
                if revision == 5:
                    offset = Vector((rng.uniform(-.10,.10)*scale, -.025*scale, -.012*scale))
                sprite=rng.choice((0,1,3)) if layer==core.NEAR else rng.choice((1,3))
                height_range=((.085,.180) if revision >= 4 else (.100,.140)) if layer==core.NEAR else (.070,.110)
                ob=card(rock.name+f' / layered sprig {i}-{j}',hit+offset,
                        scale*distance_size*rng.uniform(*height_range),sprite,layer,index*100+i*10+j,rock.parent)
                ob['river_cluster']=len(clusters)-1
                ob['river_distance_size']=distance_size
        if selected and layer==core.NEAR and revision != 5:
            hit=selected[0]
            if index%3==0 or (revision >= 4 and moisture > .7):
                for j in range(5 if revision >= 4 and moisture > .7 else 3):
                    pos=hit+Vector((math.sin(j*.8)*scale*.028,-.14-scale*.02*j,-j*scale*.105))
                    ob=card(rock.name+f' / trailing stem {j}',pos,scale*.13,2,layer,index*10+j,rock.parent)
                    ob.scale.x=.60
                    ob.rotation_euler=(0,rng.uniform(-.12,.12),rng.uniform(-.2,.2))

    cx,cz=scene['river_origin']; distance=scene['river_distance']
    for i,(u,v,length) in enumerate(() if revision == 5 else ((257,85,165),(580,40,230),(955,69,170),(1317,30,180))):
        depth=43; k=(distance+depth)/distance
        anchor=(cx+(u/1672-.5)*6.24*k,depth,cz+(.5-v/941)*3.51*k)
        total=length/941*3.51*k
        for j in range(6):
            pos=Vector(anchor)+Vector((math.sin(j*.7+i)*k*.035,-j*.016,-total*j/6))
            ob=card(f'V3 / vault ivy {i} / section {j}',pos,total/6*1.15,2,core.NEAR,800+i*10+j)
            ob.scale.x=.62
            ob.rotation_euler=(.08*math.sin(j),.10*math.cos(j+i),.14*math.sin(j+i))

    hanging_moss_report = None
    if revision == 5:
        from hanging_moss import add_hanging_moss
        hanging_cards, hanging_moss_report = add_hanging_moss(rocks)

    # Diffuse lighting is baked once; no extra lights or fog passes at runtime.
    for ob in ([] if refit else core.collection('40_LIGHTING').objects):
        if ob.type=='LIGHT':
            if 'fill' in ob.name: ob.data.energy*=.65
            if ob.data.type=='SUN': ob.data.energy*=.72
    scene['river_revision_notes']='Small compound curved sprigs; fewer simpler pieces at distance; local irradiance baked for all textures; additive foliage haze; surface moss shares cave light.'
    if revision == 4:
        scene['river_revision_notes'] += ' Compound fracture ledges, mineral strata and cavity shading; stable formation seeds and moisture-dependent planting. Use refit_grotto.py after geometry edits.'
    if revision == 5:
        scene['river_revision_notes'] += ' Shared moisture-driven growth patches, world-scale moss and geometry-rooted ceiling trails. Four continuous marker-group masses; three floor-rooted banks/ridges and one ceiling buttress. Later chambers alternate rooted banks and ceiling masses. Refit with refit_grotto.py.'
    notes=bpy.data.texts.new('V3 / implementation notes')
    notes.write(scene['river_revision_notes']+'\nAtlas packed; cards editable. Original master preserved.\n')
    bpy.context.view_layer.update()
    if save_result:
        bpy.ops.wm.save_as_mainfile(filepath=str(out/'river_dream.blend'))
    report=json.loads((HERE/'output/build_report.json').read_text())
    report.update(name=scene.name,package=scene['river_export_path'],sourceMasterSha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  sceneSpecSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),removedPlantMeshes=removed,
                  foliageCards=len(cards),foliageTriangles=sum(len(o.data.polygons)*2 for o in cards),
                  mossSurfacePatches=len(moss_patches),mossSurfaceTriangles=sum(len(o.data.polygons)*2 for o in moss_patches),
                  clusters=clusters,spriteBounds=bounds,spriteRoots=roots,
                  atlasSha256=hashlib.sha256((HERE/'textures/foliage-components-v3.png').read_bytes()).hexdigest())
    report['rocks'] = len(rocks)
    if hanging_moss_report is not None:
        report['hangingMoss'] = hanging_moss_report
    if revision == 4:
        report['geology'] = json.loads(scene['river_geology_report'])
        report['sceneSpecSha256'] = hashlib.sha256(Path(__file__).read_bytes() + (HERE/'grotto_geology.py').read_bytes()).hexdigest()
    if revision == 5:
        report['masses'] = json.loads(scene['river_mass_report'])
        report['routeRocks'] = sum(row['group'] is None for row in report['masses'])
        report['sceneSpecSha256'] = hashlib.sha256(Path(__file__).read_bytes() + (HERE/'connected_grotto.py').read_bytes() + (HERE/'mass-recipes-v5.json').read_bytes() + (HERE/'grotto_geology.py').read_bytes() + (HERE/'hanging_moss.py').read_bytes() + (HERE/'growth_patches.py').read_bytes() + (HERE/'textures/hanging-moss-soft-strands-v5.png').read_bytes()).hexdigest()
    if refit:
        report['refittedFrom'] = str(source)
        report['sourceMasterSha256'] = hashlib.sha256((HERE/'output/river_dream.blend').read_bytes()).hexdigest()
    if save_result:
        (out/'build_report.json').write_text(json.dumps(report,indent=2))
    print('REVISED_READY',json.dumps(report),flush=True)
    return report


if __name__=='__main__': main()
