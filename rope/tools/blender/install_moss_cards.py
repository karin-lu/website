"""Install the local add-on without replacing the user's other preferences."""
from pathlib import Path
import shutil
import sys
import bpy
import addon_utils

source = Path(__file__).resolve().parent / "moss_cards"
target = Path(bpy.utils.user_resource("SCRIPTS", path="addons", create=True)) / "moss_cards"
update = "--update" in sys.argv
if target.exists() and not update:
    raise RuntimeError(f"An add-on already exists at {target}; kept intact")
if target.exists():
    assert 'id = "moss_cards"' in (target / "blender_manifest.toml").read_text(), "Kept unrelated installed add-on intact"
shutil.copytree(source, target, dirs_exist_ok=update, ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))
sys.path.insert(0, str(target.parent))
addon_utils.modules_refresh()
addon_utils.enable("moss_cards", default_set=True, persistent=True)
assert "moss_cards" in bpy.context.preferences.addons
bpy.ops.wm.save_userpref()
print(f"MOSS_CARDS_INSTALLED: {target}")
