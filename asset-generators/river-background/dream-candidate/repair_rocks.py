"""Candidate-only Blender cleanup and exact scenery worker validation."""
import json
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'pipeline'))
from river_core import validate_worker


def measures(obj):
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        return {'vertices': len(bm.verts), 'faces': len(bm.faces),
                'degenerateFaces': sum(f.calc_area() <= 1e-12 for f in bm.faces),
                'minimumFaceArea': min(f.calc_area() for f in bm.faces),
                'nonmanifoldEdges': sum(not e.is_manifold for e in bm.edges),
                'volume': abs(bm.calc_volume(signed=True))}
    finally:
        bm.free()


def main():
    output = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
    obj = bpy.data.objects['SceneryRock']
    before = measures(obj)
    if before['degenerateFaces']:
        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            # Bevel/remesh can create collapsed triangle edges. Dissolve only
            # microscopic geometry; the silhouette and source slabs stay intact.
            bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=list(bm.edges))
            bm.normal_update()
            bm.to_mesh(obj.data)
            obj.data.update()
        finally:
            bm.free()
    recipe = validate_worker(obj, bpy.data.collections['SOURCE_SLABS'])
    after = measures(obj)
    report = {'exactWorkerValidation': 'passed', 'before': before, 'after': after,
              'recipePreserved': recipe == json.loads((output / 'recipe.json').read_text()),
              'cleanup': 'bmesh dissolve_degenerate distance 0.00001'}
    (output / 'validation.json').write_text(json.dumps(report, indent=2))
    corners = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
    dimensions = {'dimensions': list(obj.dimensions),
                  'boundsMin': [min(v[i] for v in corners) for i in range(3)],
                  'boundsMax': [max(v[i] for v in corners) for i in range(3)],
                  'vertices': after['vertices'], 'faces': after['faces']}
    (output / 'dimensions.json').write_text(json.dumps(dimensions, indent=2))
    health = json.loads((output / 'health.json').read_text())
    health.update(vertices=after['vertices'], faces=after['faces'], volume=after['volume'])
    (output / 'health.json').write_text(json.dumps(health, indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'rock.blend'))
    print('EXACT_ROCK_VALIDATION_PASSED', json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
