"""Install one of this repo's Blender add-ons into this machine's Blender.

    blender -b --python tools/blender/addon_install.py -- formations

Links tools/blender/<name> into the user's local extension repository
(`user_default`) rather than copying it, so an edit in the repo is the add-on
Blender runs after a restart (or Blender's "Reload Scripts"), enables it and
saves the preferences. Safe to re-run. The scene exporter does not need it:
it imports the packages from the repo itself."""

import os
import stat
import subprocess
import sys

import addon_utils
import bpy

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
if len(argv) != 1:
    sys.exit("usage: blender -b --python tools/blender/addon_install.py -- <add-on>")
NAME = argv[0]
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), NAME)
if not os.path.isfile(os.path.join(SRC, "blender_manifest.toml")):
    sys.exit(f"[{NAME}] {SRC} is not an add-on (no blender_manifest.toml)")
MODULE = f"bl_ext.user_default.{NAME}"

repo = next((r for r in bpy.context.preferences.extensions.repos if r.module == "user_default"), None)
if repo is None:
    sys.exit(f"[{NAME}] this Blender has no user_default extension repository")
root = repo.directory
os.makedirs(root, exist_ok=True)
dest = os.path.join(root, NAME)


def is_junction(path):
    # Blender 4.2's Python predates os.path.isjunction (Python 3.12).
    try:
        return os.lstat(path).st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT
    except (OSError, AttributeError):
        return False


if os.path.islink(dest):
    if os.path.realpath(dest) != os.path.realpath(SRC):
        os.unlink(dest)
elif is_junction(dest):
    if os.path.realpath(dest) != os.path.realpath(SRC):
        sys.exit(f"[{NAME}] {dest} is a junction to another checkout; refusing to replace it")
elif os.path.exists(dest):
    sys.exit(f"[{NAME}] {dest} exists and is not a link this script made; remove it first")
if not os.path.islink(dest) and not is_junction(dest):
    try:
        os.symlink(SRC, dest, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt" or exc.winerror != 1314:
            raise
        # A directory junction needs no administrator/Developer Mode privilege.
        # Both arguments are single-quoted PowerShell literals, not shell input.
        quoted_dest = dest.replace("'", "''")
        quoted_src = SRC.replace("'", "''")
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                        f"New-Item -ItemType Junction -Path '{quoted_dest}' -Target '{quoted_src}' | Out-Null"],
                       check=True)
print(f"[{NAME}] {dest} -> {SRC}")

bpy.ops.extensions.repo_refresh_all()
addon_utils.enable(MODULE, default_set=True, persistent=True)
if MODULE not in bpy.context.preferences.addons:
    sys.exit(f"[{NAME}] {MODULE} did not enable; see the errors above")
bpy.ops.wm.save_userpref()
print(f"[{NAME}] enabled and saved: its tab is in the 3D viewport's sidebar (N)")
