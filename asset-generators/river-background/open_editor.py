"""Open the v5 artist scene using this checkout's River controls."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--blender', default=os.environ.get('BLENDER') or shutil.which('blender') or
                    'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe')
args = parser.parse_args()
scene = ROOT / 'dream-candidate/output-v5/river_dream_layer_editor.blend'
if not scene.is_file():
    parser.error('Fetch authoring assets first: python asset-generators/river-background/fetch_authoring.py')
if not Path(args.blender).is_file():
    parser.error('Set BLENDER or pass --blender with the Blender executable path')
env = {**os.environ, 'RIVER_PYTHON': os.environ.get('RIVER_PYTHON', sys.executable)}
subprocess.Popen([args.blender, '--factory-startup', str(scene), '--python',
                  str(ROOT / 'pipeline/open_layer_editor.py')], env=env)
