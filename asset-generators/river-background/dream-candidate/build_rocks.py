"""Build the dream candidate's reproducible v5 procedural rock library.

Run with ordinary Python. Each isolated worker assembles its mesh in Blender;
the existing generator and scenery pipeline are left untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
WORKER = HERE.parent / 'pipeline' / 'rock_worker.py'
DEFAULT_BLENDER = os.environ.get('BLENDER') or shutil.which('blender') or 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'


def run(command, log_path):
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
    log_path.write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
    if result.returncode:
        tail = (result.stdout + '\n' + result.stderr)[-5000:]
        raise RuntimeError(f'Rock subprocess failed ({result.returncode}); see {log_path}\n{tail}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', default=str(DEFAULT_BLENDER))
    parser.add_argument('--only', nargs='+', help='Build only the named recipes')
    parser.add_argument('--recipes', type=Path, default=HERE/'mass-recipes-v5.json')
    parser.add_argument('--cache-root', type=Path, default=HERE/'cache-v5')
    parser.add_argument('--report', type=Path, default=HERE/'mass-library-report-v5.json')
    args = parser.parse_args()
    blender = Path(args.blender).resolve()
    if not blender.is_file():
        parser.error(f'Blender executable does not exist: {blender}')
    recipes = json.loads(args.recipes.read_text(encoding='utf-8'))
    chosen = args.only or list(recipes['rocks'])
    unknown = sorted(set(chosen) - set(recipes['rocks']))
    if unknown:
        parser.error('Unknown recipes: ' + ', '.join(unknown))
    module_spec = importlib.util.spec_from_file_location('candidate_rock_worker', WORKER)
    worker_module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(worker_module)
    generator_hash = worker_module.fingerprint()
    report_path = args.report
    report = json.loads(report_path.read_text()) if report_path.exists() else {'version': 1, 'rocks': {}}
    report['generatorHash'] = generator_hash
    report['recipes'] = str(args.recipes)
    for name in chosen:
        recipe = recipes['rocks'][name]
        serialized = json.dumps(recipe, sort_keys=True, separators=(',', ':'))
        repair_hash = hashlib.sha256((HERE / 'repair_rocks.py').read_bytes()).hexdigest()
        digest = hashlib.sha256((serialized + generator_hash + repair_hash).encode()).hexdigest()
        output = args.cache_root / name
        output.mkdir(parents=True, exist_ok=True)
        fingerprint_path = output / 'fingerprint.json'
        cached = (fingerprint_path.exists() and (output / 'rock.blend').exists()
                  and (output / 'dimensions.json').exists() and (output / 'validation.json').exists()
                  and json.loads(fingerprint_path.read_text()).get('fingerprint') == digest)
        start = time.monotonic()
        if not cached:
            request_path = output / 'input-recipe.json'
            request_path.write_text(json.dumps(recipe, indent=2), encoding='utf-8')
            print(f'Building {name} (seed {recipe["params"]["seed"]})', flush=True)
            run([sys.executable, str(WORKER), str(request_path), str(output), '--blender', str(blender)], output / 'build.log')
            run([str(blender), '--background', str(output / 'rock.blend'), '--python-exit-code', '1',
                 '--python', str(HERE / 'repair_rocks.py'), '--', str(output)], output / 'repair.log')
            inspect_script = output / 'inspect_dimensions.py'
            inspect_script.write_text(
                "import bpy, json\nfrom pathlib import Path\n"
                "from mathutils import Vector\n"
                "obj = bpy.data.objects['SceneryRock']\n"
                "corners = [obj.matrix_world @ Vector(v) for v in obj.bound_box]\n"
                "result = {'dimensions': list(obj.dimensions), 'boundsMin': [min(v[i] for v in corners) for i in range(3)], 'boundsMax': [max(v[i] for v in corners) for i in range(3)], 'vertices': len(obj.data.vertices), 'faces': len(obj.data.polygons)}\n"
                f"Path({str(output / 'dimensions.json')!r}).write_text(json.dumps(result, indent=2))\n",
                encoding='utf-8')
            run([str(blender), '--background', str(output / 'rock.blend'), '--python-exit-code', '1', '--python', str(inspect_script)], output / 'inspect.log')
            fingerprint_path.write_text(json.dumps({'fingerprint': digest, 'generatorHash': generator_hash}, indent=2))
        dimensions = json.loads((output / 'dimensions.json').read_text())
        health = json.loads((output / 'health.json').read_text())
        validation = json.loads((output / 'validation.json').read_text())
        report['rocks'][name] = dict(dimensions, health=health, seed=recipe['params']['seed'],
                                    validation=validation, fingerprint=digest, blendPath=str(output / 'rock.blend'),
                                    recipePath=str(output / 'recipe.json'), cacheReused=cached,
                                    elapsedSeconds=round(time.monotonic() - start, 2))
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'{name}: ready, dimensions={dimensions["dimensions"]}, cacheReused={cached}', flush=True)


if __name__ == '__main__':
    main()
