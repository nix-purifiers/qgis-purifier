"""Exercise the installed wrappers against real QGIS and a real public plugin."""

import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin"
original = Path(sys.argv[2]).resolve() / "bin/qgis_process"
source = Path(__file__).resolve().parents[1]
env = os.environ.copy() | {"QT_QPA_PLATFORM": "offscreen"}


def run(arguments, **kwargs):
    result = subprocess.run(
        arguments, check=False, env=env, capture_output=True, text=True, **kwargs
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"project networking works")

    def log_message(self, *args):
        pass


with tempfile.TemporaryDirectory(prefix="qgis-conformance-") as temporary:
    root = Path(temporary)
    project = root / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".qgis-purifier", "output"),
    )
    env["QGIS_PURIFIER_PROJECT"] = str(project)
    env["QGIS_PURIFIER_OUTPUT"] = str(project / "output")
    env["QGIS_PURIFIER_SCRIPT"] = str(project / "build.py")
    lock = project / "qgis-purifier.lock.json"
    digest = hashlib.sha256(lock.read_bytes()).hexdigest()
    script = (project / "build.py").read_text()
    script += """
import json, stat, urllib.request
import qgis.utils
from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QStandardPaths
from pyplugin_installer.installer import QgsPluginInstaller
settings = QgsSettings()
counter = int(settings.value("purifier/test-counter", 0)) + 1
settings.setValue("purifier/test-counter", counter)
settings.sync()
for method in ["installPlugin", "uninstallPlugin", "installFromZipFile"]:
    try: getattr(QgsPluginInstaller, method)(None, None)
    except RuntimeError as error: assert "locked" in str(error)
    else: raise AssertionError("native plugin manager was not frozen")
module = __import__("latlontools")
assert Path(module.__file__).resolve().is_relative_to("/nix/store")
assert not (Path(module.__file__).stat().st_mode & stat.S_IWUSR)
with urllib.request.urlopen(os.environ["QGIS_TEST_URL"]) as response:
    assert response.read() == b"project networking works"
(output / "proof.json").write_text(json.dumps({"counter":counter,"paths":qgis.utils.plugin_paths,"appdata":QStandardPaths.standardLocations(QStandardPaths.StandardLocation.AppDataLocation)}))
"""
    (project / "build.py").write_text(script)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env["QGIS_TEST_URL"] = f"http://127.0.0.1:{server.server_port}/"
    try:
        for counter, latitude in enumerate([42, 43, 42], 1):
            (project / "coordinates.csv").write_text(
                f"id,latitude,longitude\n1,{latitude},7\n"
            )
            run(
                [
                    cli / "qgis_process",
                    "--json",
                    "run",
                    source / "native/qgis_purifier_build.py",
                    "--",
                ],
                cwd=project,
            )
            geometry = json.loads((project / "output/points.geojson").read_text())
            assert geometry["features"][0]["geometry"]["coordinates"] == [
                7.0,
                float(latitude),
            ]
            proof = json.loads((project / "output/proof.json").read_text())
            assert proof["counter"] == counter
            assert all(
                Path(path).is_relative_to("/nix/store") for path in proof["paths"]
            )
            assert hashlib.sha256(lock.read_bytes()).hexdigest() == digest
    finally:
        server.shutdown()
        server.server_close()
    state = project / ".qgis-purifier"
    assert (state / "environment").resolve().is_relative_to("/nix/store")
    poison = state / "profiles/default/python/ambient.py"
    poison.write_text("raise AssertionError('ambient code executed')\n")
    rejected = subprocess.run(
        [cli / "qgis_process", "--version"],
        cwd=project,
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode and "unlocked QGIS Python code" in rejected.stderr
    assert poison.exists()
    poison.unlink()
    startup = Path(proof["appdata"][0]) / "startup.py"
    startup.parent.mkdir(parents=True, exist_ok=True)
    startup.write_text("raise AssertionError('ambient startup executed')\n")
    rejected = subprocess.run(
        [
            cli / "qgis_process",
            "--json",
            "run",
            source / "native/qgis_purifier_build.py",
            "--",
        ],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode and "unlocked QGIS startup code" in rejected.stderr, (
        rejected.stdout + rejected.stderr
    )
    startup.unlink()
    selection = project / "qgis-purifier.json"
    selection.write_text('{"plugins": []}')
    rejected = subprocess.run(
        [cli / "qgis_process", "--version"],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode and "selection changed" in rejected.stderr
    selection.write_text('{"plugins": ["latlontools"]}')
    # No lock must preserve native streams and status, adding just the warning.
    lock.unlink()
    for arguments in [["--version"], ["unknown-command"]]:
        expected = subprocess.run(
            [original, *arguments], check=False, env=env, capture_output=True
        )
        actual = subprocess.run(
            [cli / "qgis_process", *arguments],
            check=False,
            env=env,
            capture_output=True,
        )
        assert actual.returncode == expected.returncode
        assert actual.stdout == expected.stdout
        assert (
            actual.stderr
            == b"warning: no QGIS purifier lock; using ordinary, impure add-on resolution\n"
            + expected.stderr
        )
print("QGIS native source/preference/guard/network/fallback checks passed")
