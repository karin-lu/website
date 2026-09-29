"""Refit saved v5 masters with preservation and determinism checks."""
import json
import sys
from pathlib import Path
import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_layered import main, core


def protected():
    return {
        'rocks': {ob.name: (core.mesh_hash(ob.data), tuple(tuple(r) for r in ob.matrix_world))
                  for ob in bpy.context.scene.objects if ob.type == 'MESH' and 'river_recipe' in ob},
        'lights': {ob.name: ob.data.energy for ob in bpy.context.scene.objects if ob.type == 'LIGHT'},
    }


def plants():
    return {ob.name: (core.mesh_hash(ob.data), tuple(tuple(r) for r in ob.matrix_world))
            for ob in bpy.context.scene.objects if ob.type == 'MESH' and
            (ob.get('river_hanging_moss') or ob.get('river_surface_moss') or 'river_sprite' in ob)}


path = Path(bpy.data.filepath)
assert bpy.context.scene.get('river_candidate') == 'river-dream-v5'
assert not bpy.context.scene.get('river_layer_editor_state'), 'Finish pending outline edits first'
before = protected()
report = main(revision=5, refit=True, save_result=False)
assert before == protected(), 'Refit changed stone or lighting'
first = plants()
assert first and report['hangingMoss']['cards'] > 0 and report['mossSurfacePatches'] > 0
main(revision=5, refit=True, save_result=False)
second = plants()
assert first == second, 'Non-deterministic planting: ' + str([(k, first.get(k), second.get(k)) for k in first.keys() | second.keys() if first.get(k) != second.get(k)][:2])
assert before == protected()
assert not any('vault ivy' in ob.name for ob in bpy.context.scene.objects)
for ob in bpy.context.scene.objects:
    if ob.type == 'MESH' and ob.get('river_preserve_material'):
        assert ob.data.uv_layers.active, ob.name
        assert all(0 <= value <= 1 for uv in ob.data.uv_layers.active.data for value in uv.uv), ob.name
    if ob.get('river_hanging_moss'):
        assert ob.get('river_moss_complete_silhouette') and ob.parent, ob.name
bpy.ops.wm.save_as_mainfile(filepath=str(path))
report['growthVerification'] = {'stoneAndLightsPreserved': True, 'deterministic': True,
                               'fixedScreenVinesRemoved': True, 'atlasUVsValid': True,
                               'plantMeshes': len(first)}
(path.parent / (path.stem+'-growth-report.json')).write_text(json.dumps(report, indent=2))
if path.stem == 'river_dream':
    (path.parent/'build_report.json').write_text(json.dumps(report, indent=2))
print('GROWTH_REFIT_PASSED', json.dumps(report['growthVerification']), flush=True)
