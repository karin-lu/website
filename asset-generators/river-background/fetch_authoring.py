"""Fetch the pinned v5 Blender sources. Existing artwork is never overwritten."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
assets = json.loads((ROOT / 'rope/src/render3d/backgroundAssets.json').read_text())
entry = assets['authoring']
with urllib.request.urlopen(assets['baseUrl'] + '/' + entry['name']) as response:
    data = response.read()
if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
    raise RuntimeError('Authoring archive size or SHA-256 mismatch')
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    files = []
    for item in archive.infolist():
        path = PurePosixPath(item.filename)
        if path.is_absolute() or '..' in path.parts or '\\' in item.filename or ':' in item.filename:
            raise RuntimeError('Invalid archive path: ' + item.filename)
        target = ROOT.joinpath(*path.parts).resolve()
        if not target.is_relative_to(HERE):
            raise RuntimeError('Authoring archive escapes its directory')
        if not item.is_dir():
            files.append((item, target))
    # Check everything before writing so a retry cannot partly replace artwork.
    for item, target in files:
        if target.exists() and target.read_bytes() != archive.read(item):
            raise RuntimeError(f'Existing artwork differs: {target}. Move it aside before fetching.')
    for item, target in files:
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item))
print(f'V5 authoring assets ready ({len(files)} files). Run open_editor.py to edit.')
