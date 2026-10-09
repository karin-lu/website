"""Build the Blender extension ZIP, including its supplied tuft atlas."""
from pathlib import Path
import zipfile

source = Path(__file__).resolve().parent / "moss_cards"
output = Path(__file__).resolve().parents[2] / ".cache" / "addons" / "moss_cards.zip"
output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and not path.name.startswith("test_"):
            archive.write(path, path.relative_to(source).as_posix())
print(output)
