"""Prepare an editable river scene and a cards-only export, with a source backup."""
from pathlib import Path
import sys
import shutil
import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "blender"))
import moss_cards
moss_cards.register()
scene = bpy.context.scene
hosts = [o for o in scene.objects if moss_cards.is_moss(o)]
if not hosts:
    raise RuntimeError("No moss mounds in this source scene")
backup = ROOT / ".cache" / "moss-cards" / "river-before-cards.blend"
backup.parent.mkdir(parents=True, exist_ok=True)
if not backup.exists():
    shutil.copy2(bpy.data.filepath, backup)
for ob in bpy.context.selected_objects:
    ob.select_set(False)
for host in hosts:
    host.select_set(True)
bpy.context.view_layer.objects.active = hosts[0]
bpy.ops.moss_cards.generate()
cards = [o for o in scene.objects if moss_cards.is_card(o)]
assert len(cards) > 100
for ob in bpy.context.selected_objects:
    ob.select_set(False)
cards[0].select_set(True); bpy.context.view_layer.objects.active = cards[0]
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == "VIEW_3D":
            area.spaces.active.shading.type = "MATERIAL"
            area.spaces.active.show_region_ui = True
            area.spaces.active.region_3d.view_location = hosts[0].matrix_world.translation
            area.spaces.active.region_3d.view_distance = 4
bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
packed = moss_cards.pack_for_export(cards, bpy.context)
for ob in bpy.context.selected_objects:
    ob.select_set(False)
for ob in packed:
    ob.select_set(True)
output = ROOT / ".cache" / "moss-cards" / "river-cards.glb"
bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB", use_selection=True,
                          export_animations=False, export_cameras=False, export_lights=False)
print(f"MOSS_CARDS_READY: {len(cards)} editable cards, {len(packed)} packed patches; source saved, backup at {backup}")
