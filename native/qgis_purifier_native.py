"""Run QGIS's catalog, installer and dependency helpers inside qgis_process."""

import json
import os
import traceback
from pathlib import Path

from qgis.core import QgsProcessingAlgorithm, QgsProcessingOutputNumber


class QgisPurifierNative(QgsProcessingAlgorithm):
    def name(self):
        return "qgis_purifier_native"

    def displayName(self):
        return "QGIS purifier native operation"

    def group(self):
        return "Purifier"

    def groupId(self):
        return "purifier"

    def createInstance(self):
        return QgisPurifierNative()

    def initAlgorithm(self, config=None):
        self.addOutput(QgsProcessingOutputNumber("OUTPUT", "Output"))

    def processAlgorithm(self, parameters, context, feedback):
        try:
            request = json.loads(Path(os.environ["QGIS_PURIFIER_REQUEST"]).read_text())
            result = operate(request)
            Path(os.environ["QGIS_PURIFIER_RESPONSE"]).write_text(
                json.dumps(result, sort_keys=True) + "\n"
            )
            return {"OUTPUT": 1}
        except BaseException:
            os.write(2, traceback.format_exc().encode())
            os._exit(1)


def operate(request):
    import qgis.utils
    from pyplugin_installer import installer_data

    if request["action"] == "catalog":
        from qgis.core import (
            QgsSettingsEntryBool,
            QgsSettingsEntryStringList,
            QgsSettingsTree,
        )
        from qgis.PyQt.QtCore import QEventLoop, QTimer, QUrl

        repositories = installer_data.repositories
        repositories.load()
        loop = QEventLoop()
        repositories.checkingDone.connect(loop.quit)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(30000)
        repositories.requestFetching(
            installer_data.officialRepo[0], QUrl.fromLocalFile(request["feed"])
        )
        loop.exec()
        state = repositories.all()[installer_data.officialRepo[0]]
        if state["state"] != 2 or state["error"]:
            raise ValueError(f"native repository fetch failed: {state['error']}")
        # qgis_process does not construct the GUI manager's settings node.
        node = QgsSettingsTree.treeRoot().createChildNode("plugin-manager")
        settings = [
            QgsSettingsEntryBool("allow-experimental", node, False),
            QgsSettingsEntryBool("allow-deprecated", node, False),
            QgsSettingsEntryStringList("seen-plugins", node, []),
        ]
        installer_data.plugins.getAllInstalled()
        installer_data.plugins.rebuild()
        assert len(settings) == 3
        return installer_data.plugins.all()

    from pyplugin_installer.unzip import unzip

    destination = Path(request["destination"])
    destination.mkdir(parents=True, exist_ok=True)
    metadata = {}
    for entry in request["entries"]:
        unzip(entry["archive"], str(destination))
        value = installer_data.plugins.getInstalledPlugin(
            entry["path"], str(destination / entry["path"]), True
        )
        if not value or value["error"]:
            raise ValueError(f"native plugin validation failed: {value}")
        if value["version_installed"] != entry["version"]:
            raise ValueError(f"plugin version mismatch: {entry['path']}")
        metadata[entry["path"]] = value
    expected = {entry["path"] for entry in request["entries"]}
    if {p.name for p in destination.iterdir()} != expected:
        raise ValueError("archive contains files outside the selected plugin roots")
    qgis.utils.plugin_paths = [str(destination)]
    qgis.utils.updateAvailablePlugins()
    from pyplugin_installer.plugindependencies import find_dependencies

    dependencies = {}
    for name in sorted(metadata):
        install, upgrade, missing = find_dependencies(
            name, plugin_data=request["catalog"]
        )
        if missing:
            raise ValueError(f"unavailable native plugin dependencies: {missing}")
        dependencies[name] = {**install, **upgrade}
    return {"metadata": metadata, "dependencies": dependencies}
