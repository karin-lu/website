"""Blender subprocess entry: invoke upstream mesh assembly without its stage/export."""
import json
from pathlib import Path
import sys
import bpy

HERE=Path(__file__).resolve().parent
GENERATOR=HERE.parents[2]/'rope/tools/blender/boulders'
sys.path.insert(0,str(GENERATOR))
from blender_build import assemble_rock, mesh_health
from stone_materials import stone_material, worn_edge_color
from params import param

out=Path(sys.argv[sys.argv.index('--')+1])
rock=json.loads((out/'geometry.json').read_text())['rocks'][0]
spec=rock['spec']
bpy.ops.wm.read_factory_settings(use_empty=True)
dst=bpy.data.collections.new('RESULT'); bpy.context.scene.collection.children.link(dst)
src=bpy.data.collections.new('SOURCE_SLABS'); bpy.context.scene.collection.children.link(src)
mats=[stone_material('Blue limestone '+str(i),spec['color'],.88+i*param(spec,'variation'),spec) for i in range(5)]
mats.append(stone_material('Worn limestone',worn_edge_color(spec['color'],spec),1,spec))
obj=assemble_rock(rock,dst,src,mats)
obj.name='SceneryRock'; obj['river_recipe']=(out/'recipe.json').read_text()
health=mesh_health(obj)
if not len(obj.data.polygons) or health['volume']<=0 or health['nonmanifold_edges']:
    raise RuntimeError('Invalid generated scenery rock: '+str(health))
src.hide_render=True; src.hide_viewport=True
(out/'health.json').write_text(json.dumps(health,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(out/'rock.blend'))
print('SCENERY_ROCK_READY',json.dumps(health),flush=True)
