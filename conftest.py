import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).parent / "backend" / "tests" / "conftest.py"))
