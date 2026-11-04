"""Activate the real locked workbench in QGIS's normal GUI under Xvfb."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin/qgis"
xvfb = Path(sys.argv[2]).resolve() / "bin/xvfb-run"
resources = Path(sys.argv[3]).resolve()
source = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="qgis-gui-") as temporary:
    root = Path(temporary)
    project = root / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".qgis-purifier"),
    )
    marker = root / "gui.json"
    runtime = root / "runtime"
    runtime.mkdir(mode=0o700)
    bus = ET.Element("busconfig")
    ET.SubElement(bus, "type").text = "session"
    ET.SubElement(bus, "listen").text = "unix:tmpdir=" + str(runtime)
    ET.SubElement(bus, "auth").text = "EXTERNAL"
    policy = ET.SubElement(bus, "policy", context="default")
    for attribute in ["own", "send_destination", "receive_sender"]:
        ET.SubElement(policy, "allow", {attribute: "*"})
    bus_config = root / "bus.conf"
    ET.ElementTree(bus).write(bus_config, encoding="UTF-8", xml_declaration=True)
    macro = root / "qgis_gui_probe.py"
    macro.write_text(
        "import os,json,traceback\nfrom pathlib import Path\n"
        "from qgis.PyQt.QtCore import QTimer\ntry:\n"
        "    import qgis.utils\n"
        "    from pyplugin_installer.installer import QgsPluginInstaller\n"
        "    plugin=qgis.utils.plugins['latlontools']\n"
        "    assert plugin.__class__.__name__ == 'LatLonTools'\n"
        "    import latlontools\n"
        "    assert Path(latlontools.__file__).resolve().is_relative_to('/nix/store')\n"
        "    try: QgsPluginInstaller.installPlugin(None,None)\n"
        "    except RuntimeError as error: assert 'locked' in str(error)\n"
        "    else: raise AssertionError('GUI plugin manager not frozen')\n"
        f"    Path({str(marker)!r}).write_text(json.dumps({{'plugin':'LatLonTools'}}))\n"
        "except BaseException:\n    os.write(2,traceback.format_exc().encode());os._exit(17)\n"
        "QTimer.singleShot(0,lambda:os._exit(0))\n"
    )
    password = root / "auth-password"
    password.write_text("purifier-private-test-password\n")
    (root / "auth").mkdir()
    env = os.environ.copy() | {
        "QGIS_PURIFIER_PROJECT": str(project),
        "QGIS_AUTH_PASSWORD_FILE": str(password),
        "QGIS_AUTH_DB_DIR_PATH": str(root / "auth"),
        "QTWEBENGINE_DISABLE_SANDBOX": "1",
        "LIBGL_ALWAYS_SOFTWARE": "1",
        "QT_QPA_PLATFORM": "xcb",
        "FONTCONFIG_FILE": str(resources / "fonts.conf"),
        "NO_AT_BRIDGE": "1",
        "HOME": str(root / "home"),
        "DBUS_SYSTEM_BUS_ADDRESS": "unix:path=" + str(root / "no-system-bus"),
        "XDG_RUNTIME_DIR": str(runtime),
    }
    (root / "home").mkdir()
    for name in [
        "WAYLAND_DISPLAY",
        "WAYLAND_SOCKET",
        "DBUS_SESSION_BUS_ADDRESS",
        "SESSION_MANAGER",
        "AT_SPI_BUS_ADDRESS",
        "QT_QPA_PLATFORMTHEME",
        "DBUS_STARTER_ADDRESS",
        "DBUS_STARTER_BUS_TYPE",
        "XDG_ACTIVATION_TOKEN",
        "DESKTOP_STARTUP_ID",
    ]:
        env.pop(name, None)
    subprocess.run(
        [
            str(xvfb),
            "-a",
            str(resources / "bin/dbus-run-session"),
            "--dbus-daemon=" + str(resources / "bin/dbus-daemon"),
            "--config-file=" + str(bus_config),
            "--",
            str(cli),
            "--nologo",
            "--noversioncheck",
            "--code",
            str(macro),
        ],
        env=env,
        cwd=project,
        check=True,
        timeout=60,
    )
    assert json.loads(marker.read_text()) == {"plugin": "LatLonTools"}
print("native QGIS GUI plugin activation passed")
