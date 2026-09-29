"""Enable the River sidebar when launched with the dedicated artist file."""
import sys
from pathlib import Path
import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import layer_editor

layer_editor.register()
print('V5_LAYER_CONTROLS_READY',bpy.data.filepath,
      bpy.context.scene.get('river_candidate'),flush=True)
for window in bpy.context.window_manager.windows:
    for area in window.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.show_region_ui = True

def show_controls():
    # Display the controls immediately, even when Blender remembers Item as
    # its active sidebar tab. The permanent panel remains in the River tab.
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D': continue
            region = next((r for r in area.regions if r.type == 'WINDOW'),None)
            if region:
                with bpy.context.temp_override(window=window,area=area,region=region):
                    bpy.ops.wm.call_panel(name='RIVER_PT_layer_editor',keep_open=True)
                return None
    return None

bpy.app.timers.register(show_controls,first_interval=1)

if '--capture-editor' in sys.argv:
    def capture():
        try:
            output = HERE/'verification/layer-editor/workspace.png'
            bpy.ops.screen.screenshot(filepath=str(output))
            print('EDITOR_SCREENSHOT',output,flush=True)
        except Exception as exc:
            print('EDITOR_SCREENSHOT_FAILED',str(exc),flush=True)
        return None
    bpy.app.timers.register(capture,first_interval=4)
