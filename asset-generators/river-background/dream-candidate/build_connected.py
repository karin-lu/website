"""Build the quieter v5 from the original candidate, preserving older versions."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_layered import main
main(revision=5)
