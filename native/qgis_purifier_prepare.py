"""Use a writable private QGIS profile with immutable dependency code."""

import json
import sys
from pathlib import Path


def prepare(state, environment):
    state = Path(state).resolve()
    environment = Path(environment).resolve()
    profile = state / "profiles/default"
    python = profile / "python"
    target = str(environment / "expressions")
    record = state / "expressions.json"
    previous = json.loads(record.read_text()) if record.exists() else None
    if python.exists():
        for item in python.iterdir():
            if (
                item.name == "expressions"
                and item.is_symlink()
                and str(item.readlink()) in {target, previous}
            ):
                continue
            raise ValueError(f"unlocked QGIS Python code in private profile: {item}")
    python.mkdir(parents=True, exist_ok=True)
    expressions = python / "expressions"
    if expressions.is_symlink() and str(expressions.readlink()) != target:
        expressions.unlink()
    if not expressions.is_symlink():
        expressions.symlink_to(target)
    record.write_text(json.dumps(target) + "\n")
    for directory in ["config", "data", "cache", "home"]:
        (state / directory).mkdir(exist_ok=True)
    return {
        "QGIS_CUSTOM_CONFIG_PATH": str(state),
        "QGIS_PLUGINPATH": str(environment / "plugins"),
        "PYQGIS_STARTUP": str(Path(__file__).with_name("qgis_purifier_startup.py")),
        "QGIS_PURIFIER_ENVIRONMENT": str(environment),
        "XDG_CONFIG_HOME": str(state / "config"),
        "XDG_DATA_HOME": str(state / "data"),
        "XDG_CACHE_HOME": str(state / "cache"),
    }


if __name__ == "__main__":
    print(json.dumps(prepare(sys.argv[1], sys.argv[2])))
