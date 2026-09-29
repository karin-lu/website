"""Isolated scenery adapter for the existing v5 polygon boulder generator.

Run with ordinary Python, not Blender Python. The upstream generator is never
modified; its geometry is assembled in a separate Blender process.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GENERATOR = ROOT / 'rope/tools/blender/boulders'

PRESETS = {
    'terrace': {'outline': [[-1.65,3.35],[-.8,3.48],[.55,3.42],[1.65,3.25],[1.52,2.45],[1.23,.8],[1.1,-1.45],[.88,-3.7],[-.78,-3.8],[-1.04,-2.1],[-1.2,.05],[-1.47,1.9]], 'depth':1.55},
    'pillar': {'outline': [[-.7,1.9],[.6,1.8],[.85,.6],[.6,-1.9],[-.8,-1.8],[-.92,-.2]], 'depth':1.3},
    'wall': {'outline': [[-1.45,1.9],[1.3,2.0],[1.6,.5],[1.35,-1.8],[-1.4,-2.0],[-1.65,.0]], 'depth':1.5},
    'arch': {'outline': [[-2.1,.7],[-.6,1.05],[1,.83],[2.1,.4],[1.8,-.6],[.5,-.15],[-.6,-.3],[-1.95,-.65]], 'depth':1.2},
    'distant': {'outline': [[-.95,1.7],[.85,1.65],[1.1,.2],[.65,-1.8],[-.8,-1.7],[-1.15,.1]], 'depth':1.0},
}


def check_memory():
    """Fail clearly before starting a volume build on exhausted Windows commit."""
    if os.name != 'nt':
        return
    import ctypes
    class MemoryStatus(ctypes.Structure):
        _fields_ = [('length',ctypes.c_ulong),('load',ctypes.c_ulong),
                    ('total_physical',ctypes.c_ulonglong),('available_physical',ctypes.c_ulonglong),
                    ('total_commit',ctypes.c_ulonglong),('available_commit',ctypes.c_ulonglong),
                    ('total_virtual',ctypes.c_ulonglong),('available_virtual',ctypes.c_ulonglong),
                    ('available_extended_virtual',ctypes.c_ulonglong)]
    status = MemoryStatus(); status.length = ctypes.sizeof(status)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) and status.available_commit < 2*1024**3:
        raise MemoryError('Not enough available system memory to generate a rock. '
                          'Close unused Blender instances and retry. Existing rock meshes are retained.')

def fingerprint():
    h = hashlib.sha256()
    h.update(Path(__file__).read_bytes()); h.update((HERE/'assemble_worker.py').read_bytes())
    for p in sorted(GENERATOR.glob('*.py')) + [GENERATOR/'params.json']:
        h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()

def prepare(recipe, output):
    sys.path.insert(0, str(GENERATOR))
    import rockgen
    kind = recipe.get('preset', 'terrace')
    base = PRESETS[kind]
    params = {'seed':31, 'depth':base['depth'], 'slabsPerArea':1.3,
              'faceBudget':1000, 'detail':.25, 'voxelCap':.045,
              'tolerance':.07, 'weathering':.25, 'variation':.025,
              'grainScale':0, 'bumpStrength':0, 'wornEdgeLift':1.12,
              'color':[.028,.063,.082]}
    params.update(recipe.get('params', {}))
    outline = recipe.get('outline', base['outline'])
    request = {'outline':outline, 'params':params}
    source = output/'request.json'; source.write_text(json.dumps(request))
    spec = rockgen.read_specs(source)[0]
    spec['name'] = 'SceneryRock'
    # Use the approved construction, with scenery-specific scale/detail values.
    rock = rockgen.make_rock(spec)
    (output/'geometry.json').write_text(json.dumps({'rocks':[rock]}, separators=(',',':')))
    resolved = {'version':1, 'preset':kind, 'outline':outline, 'params':params,
                'generator':str(GENERATOR), 'generatorHash':fingerprint()}
    (output/'recipe.json').write_text(json.dumps(resolved, indent=2))

def main():
    p = argparse.ArgumentParser()
    p.add_argument('recipe'); p.add_argument('output'); p.add_argument('--blender', required=True)
    p.add_argument('--repair', help='Optional candidate cleanup followed by exact worker validation')
    a = p.parse_args(); output = Path(a.output).resolve(); output.mkdir(parents=True, exist_ok=True)
    check_memory()
    prepare(json.loads(Path(a.recipe).read_text(encoding='utf-8-sig')), output)
    subprocess.run([a.blender,'--background','--factory-startup','--python-exit-code','1',
                    '--python',str(HERE/'assemble_worker.py'),'--',str(output)],check=True)
    if not (output/'rock.blend').is_file():
        raise RuntimeError('Worker produced no rock.blend')
    if a.repair:
        subprocess.run([a.blender,'--background',str(output/'rock.blend'),'--python-exit-code','1',
                        '--python',a.repair,'--',str(output)],check=True)

if __name__ == '__main__': main()
