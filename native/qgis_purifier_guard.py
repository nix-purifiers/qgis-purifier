"""Freeze native plugin management before QGIS loads project plugins."""

import importlib.abc
import importlib.machinery
import json
import os
import sys
import traceback
import types
from pathlib import Path


def frozen(*args, **kwargs):
    raise RuntimeError("QGIS plugins are locked; use qgis-purifier lock --update")


def install():
    environment = Path(os.environ["QGIS_PURIFIER_ENVIRONMENT"]).resolve()
    plugins = str((environment / "plugins").resolve())
    lock = json.loads((environment / "lock.json").read_text())

    class GuardedUtils(types.ModuleType):
        def __setattr__(self, name, value):
            if name == "plugin_paths":
                value = [plugins, str(Path(self.__file__).parents[1] / "plugins")]
            super().__setattr__(name, value)

    class Loader:
        def __init__(self, original):
            self.original = original

        def create_module(self, spec):
            return self.original.create_module(spec)

        def __getattr__(self, name):
            return getattr(self.original, name)

        def exec_module(self, module):
            try:
                self.original.exec_module(module)
                if module.__name__ == "qgis.utils":
                    from qgis.core import QgsApplication, QgsSettings
                    from qgis.PyQt.QtCore import QStandardPaths

                    profile = Path(QgsApplication.qgisSettingsDirPath()).resolve()
                    expected = (
                        Path(os.environ["QGIS_CUSTOM_CONFIG_PATH"]) / "profiles/default"
                    )
                    if profile != expected.resolve():
                        raise ValueError("locked QGIS profile was overridden")
                    for path in QStandardPaths.locateAll(
                        QStandardPaths.StandardLocation.AppDataLocation, "startup.py"
                    ):
                        if not Path(path).resolve().is_relative_to("/nix/store"):
                            raise ValueError(f"unlocked QGIS startup code: {path}")
                    mutable = profile / "python"
                    sys.path[:] = [
                        p
                        for p in sys.path
                        if not p or not Path(p).is_relative_to(mutable)
                    ]
                    module.__class__ = GuardedUtils
                    settings = QgsSettings()
                    for entry in lock["entries"]:
                        key = "/PythonPlugins/" + entry["path"]
                        if not settings.contains(key):
                            settings.setValue(key, True)
                elif module.__name__ == "pyplugin_installer.installer":
                    for name in [
                        "installPlugin",
                        "uninstallPlugin",
                        "installFromZipFile",
                    ]:
                        setattr(module.QgsPluginInstaller, name, frozen)
            except BaseException:
                os.write(2, traceback.format_exc().encode())
                os._exit(1)

    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname in {"qgis.utils", "pyplugin_installer.installer"}:
                spec = importlib.machinery.PathFinder.find_spec(fullname, path)
                spec.loader = Loader(spec.loader)
                return spec

    sys.meta_path.insert(0, Finder())
