"""Refit planting to the loaded, saved v4/v5 geometry without rebuilding stone.

Writes the matching output-vN/river_dream.blend. Export again for the game.
"""
import sys
import bpy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_layered import main

candidate = bpy.context.scene.get('river_candidate')
if candidate not in ('river-dream-v4', 'river-dream-v5'):
    raise ValueError('Load a v4 or v5 master before refitting')
main(revision=int(candidate[-1]), refit=True)
