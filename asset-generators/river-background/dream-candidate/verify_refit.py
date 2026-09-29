"""Regression check: refitting preserves stone/light and stable plant placement."""
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_layered import main, core


def snapshot():
    bpy.context.view_layer.update()
    rocks = {ob['river_id']: (core.mesh_hash(ob.data), tuple(tuple(row) for row in ob.matrix_world))
             for layer in (core.NEAR, core.FAR) for ob in core.collection(layer).all_objects
             if ob.type == 'MESH' and 'river_recipe' in ob}
    plants = {ob.name: (core.mesh_hash(ob.data), tuple(tuple(row) for row in ob.matrix_world))
              for ob in bpy.context.scene.objects if 'river_sprite' in ob}
    lights = {ob.name: ob.data.energy for ob in core.collection('40_LIGHTING').objects if ob.type == 'LIGHT'}
    return rocks, plants, lights


before = snapshot()
revision = int(bpy.context.scene['river_candidate'].rsplit('v', 1)[1])
main(revision=revision, refit=True, output_dir=HERE/f'staging-check/refit-v{revision}')
after = snapshot()
assert before == after, 'Refit changed stone, light or deterministic vegetation'
print(f'V{revision}_REFIT_PASSED: identical rocks, plants and lighting', flush=True)
