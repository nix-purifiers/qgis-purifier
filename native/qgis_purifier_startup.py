"""QGIS executes this before PyQGIS is importable; keep this loader stdlib-only."""

import importlib.util
import os
import traceback
from pathlib import Path

try:
    spec = importlib.util.spec_from_file_location(
        "qgis_purifier_guard",
        Path(os.environ["PYQGIS_STARTUP"]).with_name("qgis_purifier_guard.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.install()
except BaseException:
    os.write(2, traceback.format_exc().encode())
    os._exit(1)
