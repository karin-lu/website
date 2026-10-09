"""Artist-owned moss cards. Geometry is saved directly, never regrown on export."""
import math
import os
import random

import bpy
bl_info = {"name": "Moss Foliage Cards", "author": "Karin", "version": (1, 0, 0),
           "blender": (4, 2, 0), "location": "3D View > Sidebar > Foliage Cards",
           "description": "Place and reshape artist-owned moss tufts", "category": "Object"}
from bpy.props import EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils

CELLS = ((.035, .520, .440, .295), (.507, .525, .477, .205),
         (.075, .029, .354, .374), (.520, .021, .460, .173))
ROWS = (0, .25, .65, 1)
PREFIX = "MossCard__"
_paint_pixels = {}


def is_card(ob):
    return ob is not None and ob.type == "MESH" and ob.get("grown_by") == "moss_cards"


def is_moss(ob):
    if ob.type != "MESH" or ob.get("grown_by") != "moss":
        return False
    # This saved material flag also works when the Moss add-on's RNA
    # properties have not been registered in a clean Blender session.
    if any(mat and mat.get("moss_decal") for mat in ob.data.materials):
        return False
    kind = getattr(getattr(ob, "moss", None), "kind", None)
    if kind is None:
        kind = ob.get("moss", {}).get("kind", 0)
    return kind not in {"TEXTURE", 1}


def active_host(context):
    ob = context.object
    return ob.parent if is_card(ob) else ob if ob and is_moss(ob) else None


def surface(host):
    mesh = host.data
    mesh.calc_loop_triangles()
    positions = [host.matrix_world @ v.co for v in mesh.vertices]
    triangles = [tuple(t.vertices) for t in mesh.loop_triangles]
    return BVHTree.FromPolygons(positions, triangles, all_triangles=True), positions, triangles


def mark_host(host):
    host["moss_cards_authored"] = True
    # This marker survives export even when every card is deliberately hidden.
    # A regrown mound's marker is restored by prepare_export.
    for slot in host.material_slots:
        if slot.material and slot.material.name.endswith(".moss"):
            mat = slot.material.copy() if slot.material.users > 1 else slot.material
            mat.name += ".authored"
            slot.material = mat


def material():
    mat = bpy.data.materials.get("MossCards")
    if mat:
        return mat
    source = bpy.data.images.load(os.path.join(os.path.dirname(__file__), "assets", "moss-tuft-atlas.png"), check_existing=True)
    width, height = source.size
    import numpy as np
    pixels = np.empty(width * height * 4, dtype=np.float32)
    source.pixels.foreach_get(pixels)
    pixels = pixels.reshape(height, width, 4)
    # Keep the cutout and subtle painterly detail, with the dark root fading
    # into the moss. This is baked into the atlas, so Blender and glTF agree.
    detail = .98 + .02 * pixels[:, :, :1]
    pixels[:, :, :3] = detail
    for u, v, w, h in CELLS:
        x0, x1 = int(u * width), min(width, math.ceil((u + w) * width))
        y0, y1 = int(v * height), min(height, math.ceil((v + h) * height))
        t = np.clip((np.arange(y0, y1) / height - v) / h / .22, 0, 1)
        pixels[y0:y1, x0:x1, 3] *= (t * t * (3 - 2 * t))[:, None]
    image = bpy.data.images.new("MossCards atlas", width, height, alpha=True)
    image.pixels.foreach_set(pixels.ravel())
    image["generated_by"] = "tools/blender/moss_cards"
    image.pack()
    mat = bpy.data.materials.new("MossCards")
    mat.use_nodes = True
    mat.use_backface_culling = False
    mat.surface_render_method = "DITHERED"
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 1
    tex = nodes.new("ShaderNodeTexImage"); tex.image = image
    color = nodes.new("ShaderNodeVertexColor"); color.layer_name = "CardTint"
    mix = nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
    inputs = {i.identifier: i for i in mix.inputs}
    inputs["Factor_Float"].default_value = 1
    links.new(tex.outputs["Color"], inputs["A_Color"])
    links.new(color.outputs["Color"], inputs["B_Color"])
    links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    return mat


def painted_color(host, point, triangle_index, fallback, inverse=None):
    """Sample the mound's existing print, rather than inventing a new green."""
    mesh = host.data
    if not mesh.uv_layers.active or triangle_index is None:
        return fallback
    triangle = mesh.loop_triangles[triangle_index]
    if triangle.material_index >= len(mesh.materials):
        return fallback
    mat = mesh.materials[triangle.material_index]
    image = next((n.image for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image), None) if mat and mat.node_tree else None
    if not image or not image.size[0]:
        return fallback
    from mathutils.geometry import barycentric_transform
    local = (inverse if inverse is not None else host.matrix_world.inverted()) @ point
    verts = [mesh.vertices[i].co for i in triangle.vertices]
    uv = mesh.uv_layers.active.data
    tex = [Vector((*uv[i].uv, 0)) for i in triangle.loops]
    mapped = barycentric_transform(local, *verts, *tex)
    w, h = image.size
    x, y = min(w - 1, max(0, int(mapped.x * w))), min(h - 1, max(0, int(mapped.y * h)))
    key = image.as_pointer()
    if key not in _paint_pixels:
        import numpy as np
        data = np.empty(w * h * 4, dtype=np.float32)
        image.pixels.foreach_get(data)
        _paint_pixels[key] = data.reshape(h, w, 4)
    rgb = _paint_pixels[key][y, x, :3]
    return tuple(c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb)


def set_variant(ob, variant):
    cell = CELLS[variant]
    layer = ob.data.uv_layers.active or ob.data.uv_layers.new(name="UVMap")
    for loop in ob.data.loops:
        vertex = loop.vertex_index
        layer.data[loop.index].uv = (cell[0] + (vertex % 2) * cell[2], cell[1] + ROWS[vertex // 2] * cell[3])
    ob["moss_card_variant"] = variant


def make_card(context, host, point, normal, width, height, variant, tint, tree=None, up=None, inverse=None):
    tree = tree or surface(host)[0]
    up = up or Vector((normal.x, 0, normal.z + .35))
    if up.length_squared < .01:
        up = Vector((0, 0, 1))
    up.normalize()
    right = up.cross(Vector((0, -1, 0))).normalized()
    inverse = inverse if inverse is not None else host.matrix_world.inverted()
    vertices = []
    steep = abs(normal.z) < .6
    for row, t in enumerate(ROWS):
        for side in range(2):
            span = .62 if row == 0 else .85 if row == 1 else 1
            p = point + right * ((side - .5) * width * span) + up * (height * (t - (.42 if steep else .30)))
            p += normal * (math.sin(t * math.pi) * (.006 if steep else .016))
            nearest, n, _, distance = tree.find_nearest(p)
            if nearest is not None and row < 2:
                p = nearest + n * (-.006 if row == 0 else .001)
            elif nearest is not None and steep and distance > height * .18:
                p = nearest.lerp(p, height * .18 / distance)
            vertices.append(inverse @ p)
    root = (vertices[2] + vertices[3]) * .5
    faces = [(row * 2, row * 2 + 1, row * 2 + 3, row * 2 + 2) for row in range(3)]
    mesh = bpy.data.meshes.new("Moss card")
    mesh.from_pydata([v - root for v in vertices], [], faces); mesh.update()
    ob = bpy.data.objects.new(f"{PREFIX}{host.name}", mesh)
    collection = bpy.data.collections.get("Moss Cards")
    if not collection:
        collection = bpy.data.collections.new("Moss Cards"); context.scene.collection.children.link(collection)
    collection.objects.link(ob)
    ob.parent = host; ob.location = root
    ob["grown_by"] = "moss_cards"; ob["moss_card_host"] = host.name
    mesh.materials.append(material())
    set_variant(ob, variant)
    colors = mesh.color_attributes.new(name="CardTint", type="FLOAT_COLOR", domain="CORNER")
    for loop in mesh.loops:
        t = ROWS[loop.vertex_index // 2]
        colors.data[loop.index].color = (*[c * (1 + .06 * t * t) for c in tint], 1)
    mesh.color_attributes.active_color = colors
    for poly in mesh.polygons:
        poly.use_smooth = True
    mark_host(host)
    return ob


class MossCardSettings(bpy.types.PropertyGroup):
    variant: EnumProperty(name="Tuft shape", items=[(str(i), f"Tuft {i + 1}", "") for i in range(4)])
    width: FloatProperty(name="Width", default=.14, min=.01, soft_max=.5, subtype="DISTANCE", unit="LENGTH")
    height: FloatProperty(name="Height", default=.09, min=.01, soft_max=.5, subtype="DISTANCE", unit="LENGTH")
    density: FloatProperty(name="Density", default=1, min=.1, max=3)
    seed: IntProperty(name="Seed", default=8107, min=0)
    tint: FloatVectorProperty(name="Fallback colour", subtype="COLOR", size=3, default=(.085, .15, .024), min=0, max=1)


class MOSS_CARDS_OT_generate(bpy.types.Operator):
    bl_idname = "moss_cards.generate"
    bl_label = "Create Cards on Moss Rims"
    bl_description = "Create editable tufts on selected moss mounds; existing artist-owned cards are kept"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def execute(self, context):
        hosts = [o for o in context.selected_objects if is_moss(o)]
        if not hosts and active_host(context):
            hosts = [active_host(context)]
        if not hosts:
            self.report({"ERROR"}, "Select a moss mound first"); return {"CANCELLED"}
        settings = context.scene.moss_card_settings
        created = 0
        _paint_pixels.clear()
        for host in hosts:
            if host.get("moss_cards_authored"):
                continue
            tree, points, triangles = surface(host)
            inverse = host.matrix_world.inverted()
            edges = {}
            welded, ids = {}, []
            for point in points:
                key = tuple(round(c * 2000) for c in point)
                ids.append(welded.setdefault(key, len(welded)))
            for index, triangle in enumerate(triangles):
                a, b, c = [points[i] for i in triangle]
                normal = (b - a).cross(c - a).normalized()
                centre = (a + b + c) / 3
                for j in range(3):
                    ia, ib = triangle[j], triangle[(j + 1) % 3]
                    edge = tuple(sorted((ids[ia], ids[ib])))
                    edges.setdefault(edge, []).append((index, normal, centre, points[ia], points[ib]))
            rng = random.Random(settings.seed)
            rim = list(edges.values()); rng.shuffle(rim)
            occupied = set(); budget = 0
            for faces in rim:
                boundary = len(faces) == 1
                silhouette = any(f[1].y < -.12 for f in faces) and any(f[1].y >= -.12 for f in faces)
                if not boundary and not silhouette:
                    continue
                index, normal, centre, a, b = min(faces, key=lambda f: f[1].y)
                if normal.y > .15:
                    continue
                steep = abs(normal.z) < .6
                steps = max(1, math.ceil((b - a).length / ((.075 if steep else .05) / settings.density)))
                for k in range(steps):
                    if budget >= 1400:
                        break
                    point = a.lerp(b, (k + .1 + .8 * rng.random()) / steps)
                    inward = (centre - point).normalized()
                    point += inward * ((.025 if steep else .015) + .015 * rng.random())
                    cell = tuple(round(c / .025) for c in point)
                    if cell in occupied:
                        continue
                    occupied.add(cell)
                    up = normal * .7 + inward * (-.5 if boundary else 0)
                    up.y = 0; up.z += .1 if boundary else .28
                    width = (.075 + rng.random() * .055) if steep else (.105 + rng.random() * .08)
                    height = (.032 + rng.random() * .034) if steep else (.06 + rng.random() * .06)
                    tint = painted_color(host, point, index, settings.tint, inverse)
                    make_card(context, host, point, normal, width, height, rng.randrange(4), tint, tree, up, inverse)
                    budget += 1; created += 1
            mark_host(host)
        _paint_pixels.clear()
        self.report({"INFO"}, f"Created {created} editable cards; existing cards kept")
        return {"FINISHED"}


class MOSS_CARDS_OT_place(bpy.types.Operator):
    bl_idname = "moss_cards.place"
    bl_label = "Place Card on Moss"
    bl_description = "Click moss to place a card; Shift keeps placing; Esc or right click finishes"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if context.mode != "OBJECT":
            self.report({"ERROR"}, "Return to Object Mode first"); return {"CANCELLED"}
        self.host = active_host(context)
        if not self.host:
            self.report({"ERROR"}, "Select a moss mound or one of its cards"); return {"CANCELLED"}
        _paint_pixels.clear()
        self.tree = surface(self.host)[0]
        self.inverse = self.host.matrix_world.inverted()
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Click moss to place a tuft · Shift: place more · Esc: finish")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type in {"ESC", "RIGHTMOUSE"}:
            context.workspace.status_text_set(None); return {"FINISHED"}
        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"PASS_THROUGH"}
        area = context.area
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        if not region:
            return {"RUNNING_MODAL"}
        coord = (event.mouse_x - region.x, event.mouse_y - region.y)
        if not (0 <= coord[0] < region.width and 0 <= coord[1] < region.height):
            return {"RUNNING_MODAL"}
        view = area.spaces.active.region_3d
        origin = view3d_utils.region_2d_to_origin_3d(region, view, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, view, coord)
        point, normal, index, _ = self.tree.ray_cast(origin, direction)
        if point is None:
            self.report({"INFO"}, "Click the selected moss surface"); return {"RUNNING_MODAL"}
        settings = context.scene.moss_card_settings
        ob = make_card(context, self.host, point, normal, settings.width, settings.height, int(settings.variant),
                       painted_color(self.host, point, index, settings.tint, self.inverse), self.tree, inverse=self.inverse)
        for selected in context.selected_objects:
            selected.select_set(False)
        ob.select_set(True); context.view_layer.objects.active = ob
        if not event.shift:
            context.workspace.status_text_set(None); return {"FINISHED"}
        return {"RUNNING_MODAL"}


class MOSS_CARDS_OT_variant(bpy.types.Operator):
    bl_idname = "moss_cards.variant"
    bl_label = "Apply Tuft Shape"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and any(is_card(ob) for ob in context.selected_objects)

    def execute(self, context):
        for ob in context.selected_objects:
            if is_card(ob) and len(ob.data.vertices) == 8:
                set_variant(ob, int(context.scene.moss_card_settings.variant))
        return {"FINISHED"}


class MOSS_CARDS_OT_curve(bpy.types.Operator):
    bl_idname = "moss_cards.curve"
    bl_label = "Curve Selected Cards"
    bl_options = {"REGISTER", "UNDO"}
    amount: FloatProperty(name="Curve", default=.15, min=-1, max=1)

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and any(is_card(ob) for ob in context.selected_objects)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        for ob in context.selected_objects:
            if not is_card(ob) or len(ob.data.vertices) != 8:
                continue
            points = ob.data.vertices
            root = (points[2].co + points[3].co) / 2
            tip = (points[6].co + points[7].co) / 2
            normal = (points[3].co - points[2].co).cross(tip - root).normalized()
            for i, vertex in enumerate(points):
                t = max(0, (ROWS[i // 2] - .25) / .75)
                vertex.co += normal * ((tip - root).length * self.amount * t * t)
            ob.data.update()
        return {"FINISHED"}


class MOSS_CARDS_OT_snap(bpy.types.Operator):
    bl_idname = "moss_cards.snap"
    bl_label = "Attach Roots to Moss"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and any(is_card(ob) for ob in context.selected_objects)

    def execute(self, context):
        for ob in context.selected_objects:
            if not is_card(ob) or not ob.parent or len(ob.data.vertices) < 4:
                continue
            tree = surface(ob.parent)[0]
            root = ob.matrix_world @ ((ob.data.vertices[2].co + ob.data.vertices[3].co) / 2)
            point, normal, _, _ = tree.find_nearest(root)
            if point is None:
                continue
            matrix = ob.matrix_world.copy(); matrix.translation += point + normal * .001 - root
            ob.matrix_world = matrix
        return {"FINISHED"}


class MOSS_CARDS_PT_panel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"; bl_region_type = "UI"
    bl_category = "Foliage Cards"; bl_label = "Moss Foliage Cards"

    def draw(self, context):
        layout = self.layout; settings = context.scene.moss_card_settings
        layout.label(text="Select moss, then create or place cards")
        layout.prop(settings, "density"); layout.prop(settings, "seed")
        layout.operator("moss_cards.generate", icon="PARTICLES")
        layout.separator()
        layout.prop(settings, "variant"); layout.prop(settings, "width"); layout.prop(settings, "height")
        layout.operator("moss_cards.place", icon="ADD")
        layout.operator("moss_cards.variant")
        layout.operator("moss_cards.curve")
        layout.operator("moss_cards.snap", icon="SNAP_ON")
        layout.separator()
        layout.label(text="G: move · R: rotate · S: scale")
        layout.label(text="Tab: edit vertices · O: proportional edit")
        layout.label(text="Magnet: Face / Project for surface moves")
        layout.label(text="Save .blend, then export the scene")


def prepare_export(scene):
    """Restore authored markers after moss regrowth without touching any card mesh."""
    warnings = []
    for host in scene.objects:
        if host.get("moss_cards_authored") and host.type == "MESH":
            mark_host(host)
    for ob in scene.objects:
        if is_card(ob) and (not ob.parent or ob.parent.name not in scene.objects or ob.parent.hide_render):
            ob.hide_render = True
            warnings.append(f"{ob.name}: moss host missing or hidden; card omitted")
    return warnings


def pack_for_export(objects, context):
    """Combine evaluated card geometry per mound without changing saved meshes.
    Read every card before adding export objects, avoiding dependency-graph
    updates per card. The exporter never saves these temporary packed meshes.
    """
    groups = {}
    for ob in objects:
        if is_card(ob):
            groups.setdefault(ob.parent, []).append(ob)
    kept = [ob for ob in objects if not is_card(ob)]
    depsgraph = context.evaluated_depsgraph_get()
    payloads = []
    for host, cards in groups.items():
        inverse = host.matrix_world.inverted()
        vertices, faces, uvs, colors, material_indices, materials = [], [], [], [], [], []
        for ob in cards:
            evaluated = ob.evaluated_get(depsgraph) if ob.modifiers else None
            mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph) if evaluated else ob.data
            matrix = inverse @ ob.matrix_world
            start = len(vertices)
            vertices.extend(matrix @ v.co for v in mesh.vertices)
            uv = mesh.uv_layers.active
            tint = mesh.color_attributes.get("CardTint")
            slots = []
            for mat in mesh.materials:
                if mat not in materials:
                    materials.append(mat)
                slots.append(materials.index(mat))
            for poly in mesh.polygons:
                faces.append(tuple(start + i for i in poly.vertices))
                material_indices.append(slots[poly.material_index] if slots else 0)
                for i in poly.loop_indices:
                    uvs.append(tuple(uv.data[i].uv) if uv else (0, 0))
                    at = i if tint and tint.domain == "CORNER" else mesh.loops[i].vertex_index
                    colors.append(tuple(tint.data[at].color) if tint else (1, 1, 1, 1))
            if evaluated:
                evaluated.to_mesh_clear()
        payloads.append((host, cards, vertices, faces, uvs, colors, material_indices, materials))
    for host, cards, vertices, faces, uvs, colors, material_indices, materials in payloads:
        mesh = bpy.data.meshes.new("Packed moss cards")
        mesh.from_pydata(vertices, [], faces); mesh.update()
        uv = mesh.uv_layers.new(name="UVMap")
        for i, value in enumerate(uvs):
            uv.data[i].uv = value
        tint = mesh.color_attributes.new(name="CardTint", type="FLOAT_COLOR", domain="CORNER")
        for i, value in enumerate(colors):
            tint.data[i].color = value
        mesh.color_attributes.active_color = tint
        for mat in materials:
            mesh.materials.append(mat)
        for poly, index in zip(mesh.polygons, material_indices):
            poly.material_index = index; poly.use_smooth = True
        packed = bpy.data.objects.new(f"MossCards__{host.name}", mesh)
        context.scene.collection.objects.link(packed); packed.parent = host
        packed["grown_by"] = "moss_cards"
        kept.append(packed)
        for ob in cards:
            ob.hide_render = True
    return kept


CLASSES = (MossCardSettings, MOSS_CARDS_OT_generate, MOSS_CARDS_OT_place,
           MOSS_CARDS_OT_variant, MOSS_CARDS_OT_curve, MOSS_CARDS_OT_snap, MOSS_CARDS_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.moss_card_settings = PointerProperty(type=MossCardSettings)


def unregister():
    del bpy.types.Scene.moss_card_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
