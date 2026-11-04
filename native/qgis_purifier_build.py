"""Execute a project Python build in QGIS's native processing runtime."""

import os
import runpy
import traceback

from qgis.core import QgsProcessingAlgorithm, QgsProcessingOutputNumber


class QgisPurifierBuild(QgsProcessingAlgorithm):
    def name(self):
        return "qgis_purifier_build"

    def displayName(self):
        return "QGIS project build"

    def group(self):
        return "Purifier"

    def groupId(self):
        return "purifier"

    def createInstance(self):
        return QgisPurifierBuild()

    def initAlgorithm(self, config=None):
        self.addOutput(QgsProcessingOutputNumber("OUTPUT", "Output"))

    def processAlgorithm(self, parameters, context, feedback):
        try:
            runpy.run_path(os.environ["QGIS_PURIFIER_SCRIPT"], run_name="__main__")
            return {"OUTPUT": 1}
        except BaseException:
            os.write(2, traceback.format_exc().encode())
            os._exit(1)
