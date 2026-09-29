"""Bind a v5 scene to this checkout, without saving artwork."""
import os
from pathlib import Path
import bpy

HERE = Path(__file__).resolve().parent


def configure():
    scene = bpy.context.scene
    if scene.get('river_candidate') != 'river-dream-v5':
        return
    root = HERE.parents[2]
    source = HERE.parent / 'dream-candidate'
    scene['river_pipeline_path'] = str(HERE)
    scene['river_export_path'] = str(root / 'rope/public/backgrounds/river-dream-v5')
    scene['river_export_staging_path'] = str(source / '.exports')
    scene['river_level'] = 'rope/levels/ball.json'
    scene.pop('river_python', None)
    if os.environ.get('RIVER_PYTHON'):
        scene['river_python'] = os.environ['RIVER_PYTHON']
    # Images in the delivered scenes are packed; retain portable disk fallbacks.
    for image in bpy.data.images:
        name = Path(image.filepath.replace('\\', '/')).name
        local = source / 'textures' / name
        if local.is_file():
            image.filepath = str(local)


if __name__ == '__main__':
    configure()
