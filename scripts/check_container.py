"""Container regression suite; no external services or application data needed."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
for args in (
    ("scripts/check_publication.py",),
    ("-m", "unittest", "discover", "-s", "backend/tests", "-v"),
    ("-m", "unittest", "discover", "-s", "tests", "-v"),
    ("scripts/verify_artifacts.py",),
):
    subprocess.run([sys.executable, *args], cwd=root, check=True)
print("Container regression and frozen artifact checks passed.", flush=True)
