"""Consume exported native geometry, external locks and exact release assets."""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin/qgis-purifier"
original = Path(sys.argv[2]).resolve() / "bin/qgis_process"
source = Path(__file__).resolve().parents[1]


def call(arguments, *, env, cwd):
    result = subprocess.run(
        arguments, check=True, env=env, cwd=cwd, text=True, capture_output=True
    )
    return result.stdout.strip()


with tempfile.TemporaryDirectory(prefix="qgis-artifacts-") as temporary:
    root = Path(temporary)
    project = root / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".qgis-purifier"),
    )
    env = os.environ.copy() | {
        "HOME": str(root / "home"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "QT_QPA_PLATFORM": "offscreen",
    }
    for name in ["home", "data", "config", "cache"]:
        (root / name).mkdir()
    args = [str(cli), "--project", str(project)]
    build = Path(call([*args, "build"], env=env, cwd=root))
    geometry = json.loads((build / "points.geojson").read_text())
    assert geometry["features"][0]["geometry"]["coordinates"] == [7.0, 42.0]
    consumer = root / "native_geojson_consumer.py"
    marker = root / "consumed.json"
    consumer.write_text(
        "import json\nfrom pathlib import Path\n"
        "from qgis.core import QgsVectorLayer,QgsProcessingAlgorithm,QgsProcessingOutputNumber\n"
        "class Consumer(QgsProcessingAlgorithm):\n"
        "    def name(self): return 'consumer'\n"
        "    def displayName(self): return 'Consumer'\n"
        "    def group(self): return 'Test'\n"
        "    def groupId(self): return 'test'\n"
        "    def createInstance(self): return Consumer()\n"
        "    def initAlgorithm(self,config=None): self.addOutput(QgsProcessingOutputNumber('OUTPUT','Output'))\n"
        "    def processAlgorithm(self,parameters,context,feedback):\n"
        f"        layer=QgsVectorLayer({str(build / 'points.geojson')!r},'points','ogr')\n"
        "        assert layer.isValid() and layer.featureCount()==1\n"
        "        point=next(layer.getFeatures()).geometry().asPoint()\n"
        "        assert point.x()==7 and point.y()==42\n"
        f"        Path({str(marker)!r}).write_text(json.dumps([point.x(),point.y()]))\n"
        "        return {'OUTPUT':1}\n"
    )
    call([str(original), "--json", "run", str(consumer), "--"], env=env, cwd=root)
    assert json.loads(marker.read_text()) == [7.0, 42.0]
    release = Path(call([*args, "bundle"], env=env, cwd=root))
    archive = release / "qgis-project.tar.gz"
    with tarfile.open(archive) as tar:
        assert (
            tar.extractfile("./points.geojson").read()
            == (build / "points.geojson").read_bytes()
        )
    external = root / "external-lock.json"
    shutil.copyfile(project / "qgis-purifier.lock.json", external)
    replay = Path(call([*args, "--lock", str(external), "bundle"], env=env, cwd=root))
    assert (replay / archive.name).read_bytes() == archive.read_bytes()
    fake = root / "gh"
    fake.write_text(
        f"#!{sys.executable}\nimport json,os,sys\nfrom pathlib import Path\n"
        "Path(os.environ['UPLOAD_RECORD']).write_text(json.dumps(sys.argv[1:]))\n"
        "Path(os.environ['UPLOAD_BYTES']).write_bytes(Path(sys.argv[4]).read_bytes())\n"
    )
    fake.chmod(0o755)
    publish_env = env | {
        "QGIS_PURIFIER_GH": str(fake),
        "UPLOAD_RECORD": str(root / "upload.json"),
        "UPLOAD_BYTES": str(root / "upload.tar.gz"),
    }
    call([*args, "publish", "--tag", "proof"], env=publish_env, cwd=root)
    record = json.loads((root / "upload.json").read_text())
    assert record[:3] == ["release", "upload", "proof"] and record[3] == str(archive)
    assert (root / "upload.tar.gz").read_bytes() == archive.read_bytes()
print("native QGIS artifact consumers passed")
