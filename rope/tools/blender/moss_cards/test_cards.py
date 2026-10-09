"""Run with Blender --background --factory-startup --python this-file."""
import os
import sys
import tempfile
from pathlib import Path
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import moss_cards as cards
cards.register()
bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
mesh = bpy.data.meshes.new("Test mound")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 0, .5), (0, 0, .5)], [], [(0, 1, 2, 3)])
host = bpy.data.objects.new("Test.moss", mesh); bpy.context.collection.objects.link(host)
host["grown_by"] = "moss"; host.location = (2, 3, 4)
host["moss"] = {"kind": 1}
assert not cards.is_moss(host), "texture-only moss must not receive generated cards"
host["moss"] = {"kind": 0}
mat = bpy.data.materials.new("Test.moss"); mat.use_nodes = True; mesh.materials.append(mat)
host.select_set(True); bpy.context.view_layer.objects.active = host; bpy.context.view_layer.update()
assert bpy.ops.moss_cards.generate() == {"FINISHED"}
objects = [o for o in bpy.context.scene.objects if cards.is_card(o)]
assert 10 < len(objects) < 1400, len(objects)
assert host.data.materials[0].name.endswith(".moss.authored")
assert all(o.parent == host and len(o.data.vertices) == 8 for o in objects)
count = len(objects); bpy.ops.moss_cards.generate()
assert len([o for o in bpy.context.scene.objects if cards.is_card(o)]) == count, "no duplicate generation"
card = objects[0]
for o in bpy.context.selected_objects: o.select_set(False)
card.select_set(True); bpy.context.view_layer.objects.active = card
original = [v.co.copy() for v in card.data.vertices]
bpy.ops.moss_cards.curve(amount=.25)
assert (card.data.vertices[7].co - original[7]).length > .001
assert (card.data.vertices[2].co - original[2]).length < 1e-7, "curving preserves the root"
card.data.vertices[6].co.x += .03
edited = card.data.vertices[6].co.copy()
card.location.y -= .3; bpy.context.view_layer.update()
bpy.ops.moss_cards.snap(); bpy.context.view_layer.update()
root = card.matrix_world @ ((card.data.vertices[2].co + card.data.vertices[3].co) / 2)
assert abs(root.y - 3) < .002, "transformed root returns to moss"
cards.set_variant(card, 3)
assert card["moss_card_variant"] == 3
assert not cards.prepare_export(bpy.context.scene)
assert card.data.vertices[6].co == edited, "manual reshaping survives export preparation"
with tempfile.TemporaryDirectory() as directory:
    blend = os.path.join(directory, "cards.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    card_name = card.name
    bpy.ops.wm.open_mainfile(filepath=blend)
    loaded = bpy.data.objects[card_name]
    assert loaded.data.vertices[6].co == edited, "vertex edits survive save/reopen"
    bpy.ops.object.select_all(action="DESELECT")
    loaded.select_set(True); bpy.context.view_layer.objects.active = loaded
    glb = os.path.join(directory, "card.glb")
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_animations=False)
    assert os.path.getsize(glb) > 1000
    # Read the glTF JSON chunk to prove colour, shape and alpha really export.
    import struct, json
    data = Path(glb).read_bytes(); length = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + length])
    primitive = doc["meshes"][0]["primitives"][0]
    assert "COLOR_0" in primitive["attributes"] and "TEXCOORD_0" in primitive["attributes"]
    assert doc["materials"][0].get("alphaMode") in {"BLEND", "MASK"}
    source_cards = [o for o in bpy.context.scene.objects if cards.is_card(o)]
    loaded.modifiers.new("Artist subdivision", "SUBSURF").levels = 1
    packed = cards.pack_for_export(source_cards, bpy.context)
    assert len(packed) == 1, "one draw per moss patch"
    assert len(packed[0].data.vertices) > count * 8, "artist modifiers are evaluated into export copies"
    assert loaded.data.vertices[6].co == edited, "packing never changes artist-owned meshes"
    assert packed[0].data.color_attributes.get("CardTint") and packed[0].data.uv_layers.active
print(f"MOSS_CARDS_TEST_PASS: {count} editable cards; root snapping, curvature, UV variants, save/reopen and glTF export")
