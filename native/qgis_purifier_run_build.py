import os
import subprocess
from pathlib import Path

from qgis_purifier_prepare import prepare

state = Path(os.environ["TMPDIR"]) / "qgis-state"
env = os.environ.copy()
env.update(prepare(state, os.environ["QGIS_PURIFIER_ENVIRONMENT"]))
env.update(HOME=str(state / "home"), QT_QPA_PLATFORM="offscreen")
subprocess.run(
    [
        os.environ["QGIS_PURIFIER_COMMAND_BINARY"],
        "--json",
        "run",
        str(Path(__file__).with_name("qgis_purifier_build.py")),
        "--",
    ],
    env=env,
    check=True,
)
