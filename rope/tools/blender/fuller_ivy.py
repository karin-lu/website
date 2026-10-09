"""Regrow only the river's painted ivy; leave the rest of the scene intact.

Run in Blender with --background assets-src/scenes/river.blend --python ...
The saved scene keeps its original settings; this recipe scales each bush's
own settings, so rerunning it does not accumulate size increases.
"""
import sys
import argparse
import json
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'blender'))
# Windows checkouts can represent the shared-package symlink as a text file.
import stampbrush
sys.modules['ivy.stampbrush'] = stampbrush
import ivy
from ivy import ops

ivy.register()
args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--only', help='Preview one painted bush before rebuilding all of them')
parser.add_argument('--output', required=True)
options = parser.parse_args(args)
objects = ops.ivy_objects(bpy.context.scene)
payload = {}
for ob in objects:
    if options.only and ob.name != options.only:
        continue
    s = ob.ivy
    s.live = False
    # Area grows with the square of leaf size. Increase fill slightly more
    # than that to preserve the leaf count and improve overlap as well.
    s.leaf_min *= 1.15
    s.leaf_max *= 1.15
    s.clump_min *= 1.15
    s.clump_max *= 1.15
    s.thickness *= 1.20
    s.leaf_fill *= 1.35
    s.clump_fill *= 1.35
    s.edge_fill *= 1.20
    result = ops.rebuild(ob)
    if result is None:
        raise RuntimeError(f'Missing host for {ob.name}')
    # Emit world geometry in the game/glTF frame, preserving the original
    # UV atlas and colours. The merger puts it into the existing node's frame.
    matrix = np.array(ob.matrix_world)
    world = result.vertices @ matrix[:3, :3].T + matrix[:3, 3]
    normals = result.normals @ np.linalg.inv(matrix[:3, :3])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    world = world[:, [0, 2, 1]] * np.array([1, 1, -1])
    normals = normals[:, [0, 2, 1]] * np.array([1, 1, -1])
    uv = result.uvs.copy()
    uv[:, :, 1] = 1 - uv[:, :, 1]
    payload[ob.name] = dict(position=world.tolist(), normal=normals.tolist(),
                            triangles=result.triangles.tolist(), uv=uv.tolist(),
                            color=result.colors.tolist(), leaves=int(result.leaves))
    print('FULLER_IVY', ob.name, result.leaves, 'leaves', flush=True)
if not payload:
    raise RuntimeError('No ivy objects matched')
Path(options.output).parent.mkdir(parents=True, exist_ok=True)
Path(options.output).write_text(json.dumps(payload, separators=(',', ':')))
