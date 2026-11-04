"""QGIS's normal application workflow with a frozen native extension profile."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def public_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("QGIS addon repositories must use public HTTPS URLs")
    return url


def selection(project):
    value = json.loads((project / "qgis-purifier.json").read_text())
    if set(value) != {"plugins"} or not isinstance(value["plugins"], list):
        raise ValueError("qgis-purifier.json needs a plugins list")
    if any(
        not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
        for name in value["plugins"]
    ):
        raise ValueError("invalid QGIS plugin identifier")
    if len(set(value["plugins"])) != len(value["plugins"]):
        raise ValueError("duplicate QGIS plugin")
    return value


def project_path(explicit):
    if explicit:
        return Path(explicit).resolve()
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "qgis-purifier.json").exists() or (
            parent / "qgis-purifier.lock.json"
        ).exists():
            return parent
    return current


def validate(project, lock):
    data = json.loads(lock.read_text())
    if data.get("version") != 1 or data.get("purifier") != "qgis":
        raise ValueError("unsupported QGIS lock")
    if data.get("sdk") != os.environ["QGIS_PURIFIER_SDK"]:
        raise ValueError("QGIS SDK changed; run qgis-purifier lock --update")
    if data.get("selection") != selection(project):
        raise ValueError("extension selection changed; run qgis-purifier lock --update")
    return data


def realize(project, lock, target="environment", out_link=None):
    args = [
        "nix",
        "build",
        "--impure",
        "--file",
        os.environ["QGIS_PURIFIER_REALIZE"],
        "--argstr",
        "projectPath",
        str(project),
        "--argstr",
        "lockPath",
        str(lock),
        "--argstr",
        "target",
        target,
        "--json",
    ]
    args += ["--out-link", str(out_link)] if out_link else ["--no-link"]
    result = run(args, stdout=subprocess.PIPE, text=True)
    return Path(json.loads(result.stdout)[0]["outputs"]["out"])


def qgis_env(resources):
    env = os.environ.copy()
    for name in ["QGIS_PLUGINPATH", "PYQGIS_STARTUP", "QGIS_PURIFIER_ENVIRONMENT"]:
        env.pop(name, None)
    for name, directory in {
        "HOME": "home",
        "XDG_CONFIG_HOME": "config",
        "XDG_DATA_HOME": "data",
        "XDG_CACHE_HOME": "cache",
    }.items():
        path = resources / directory
        path.mkdir(parents=True, exist_ok=True)
        env[name] = str(path)
    env.update(
        QT_QPA_PLATFORM="offscreen", QGIS_CUSTOM_CONFIG_PATH=str(resources / "profile")
    )
    return env


def native_operation(root, request):
    request_file = root / "request.json"
    response = root / "response.json"
    request_file.write_text(json.dumps(request))
    response.unlink(missing_ok=True)
    env = qgis_env(root / "user")
    env.update(
        QGIS_PURIFIER_REQUEST=str(request_file), QGIS_PURIFIER_RESPONSE=str(response)
    )
    run(
        [
            os.environ["QGIS_PURIFIER_CMD"],
            "--json",
            "run",
            str(Path(os.environ["QGIS_PURIFIER_NATIVE"]) / "qgis_purifier_native.py"),
            "--",
        ],
        env=env,
        stdout=sys.stderr,
    )
    return json.loads(response.read_text())


def prefetch(url):
    return json.loads(
        run(
            ["nix", "store", "prefetch-file", "--json", public_url(url)],
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
    )


def capture(project, lock):
    import shutil

    requested = selection(project)
    with tempfile.TemporaryDirectory(prefix="qgis-purifier-") as temporary:
        root = Path(temporary)
        # Use the SDK's version-specific official repository feed.
        version = os.environ["QGIS_PURIFIER_FEED_VERSION"]
        feed = (
            prefetch("https://plugins.qgis.org/plugins/plugins.xml?qgis=" + version)
            if requested["plugins"]
            else None
        )
        catalog = (
            native_operation(root, {"action": "catalog", "feed": feed["storePath"]})
            if feed
            else {}
        )
        selected = set(requested["plugins"])
        archives = {}
        while True:
            for name in sorted(selected):
                if name in archives:
                    continue
                item = catalog.get(name)
                if (
                    not item
                    or not item["available"]
                    or item["error"]
                    or item["experimental"]
                    or item["deprecated"]
                ):
                    raise ValueError(f"no compatible stable plugin: {name}")
                archives[name] = prefetch(item["download_url_stable"])
            destination = root / "plugins"
            if destination.exists():
                shutil.rmtree(destination)
            entries = [
                {
                    "path": name,
                    "version": catalog[name]["version_available_stable"],
                    "archive": archives[name]["storePath"],
                }
                for name in sorted(selected)
            ]
            installed = native_operation(
                root,
                {
                    "action": "install",
                    "catalog": catalog,
                    "entries": entries,
                    "destination": str(destination),
                },
            )
            dependencies = {
                item["id"]
                for group in installed["dependencies"].values()
                for item in group.values()
            }
            if dependencies <= selected:
                if any(installed["dependencies"].values()):
                    raise ValueError(
                        "native plugin dependency constraints are unsatisfied"
                    )
                break
            selected |= dependencies
        entries = [
            {
                "path": name,
                "url": public_url(catalog[name]["download_url_stable"]),
                "hash": archives[name]["hash"],
                "mirrors": [],
                "qgis": {"version": catalog[name]["version_available_stable"]},
            }
            for name in sorted(selected)
        ]
        data = {
            "version": 1,
            "purifier": "qgis",
            "sdk": os.environ["QGIS_PURIFIER_SDK"],
            "selection": requested,
            "native": {"catalog": {name: catalog[name] for name in sorted(selected)}},
            "entries": entries,
        }
        candidate = root / "qgis-purifier.lock.json"
        candidate.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        realize(project, candidate)
        lock.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=lock.parent, delete=False
        ) as output:
            output.write(candidate.read_text())
            pending = Path(output.name)
        try:
            os.replace(pending, lock)
        finally:
            pending.unlink(missing_ok=True)


def native_exec(project, lock, arguments, command="qgis_process"):
    original = os.environ[
        "QGIS_PURIFIER_CMD" if command == "qgis_process" else "QGIS_PURIFIER_GUI"
    ]
    if not lock.exists():
        print(
            "warning: no QGIS purifier lock; using ordinary, impure add-on resolution",
            file=sys.stderr,
        )
        env = os.environ.copy()
        env.pop("QGIS_PURIFIER_ENVIRONMENT", None)
        os.execve(original, [original, *arguments], env)
    validate(project, lock)
    state = project / ".qgis-purifier"
    state.mkdir(exist_ok=True)
    environment = realize(project, lock, out_link=state / "environment")
    native = Path(os.environ["QGIS_PURIFIER_NATIVE"])
    settings = json.loads(
        run(
            [
                sys.executable,
                str(native / "qgis_purifier_prepare.py"),
                str(state),
                str(environment),
            ],
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
    )
    env = os.environ.copy()
    env.update(settings)
    for index, argument in enumerate(arguments):
        if argument in {
            "--profiles-path",
            "--profile",
            "--customconfigpath",
            "--optionspath",
        } or any(
            argument.startswith(name + "=")
            for name in [
                "--profiles-path",
                "--profile",
                "--customconfigpath",
                "--optionspath",
            ]
        ):
            raise ValueError(
                "profile overrides are unavailable in a locked QGIS session"
            )
    os.execve(original, [original, *arguments], env)


def main():
    if os.environ.get("QGIS_PURIFIER_COMMAND") in {
        "qgis",
        "qgis_process",
    }:
        project = project_path(os.environ.get("QGIS_PURIFIER_PROJECT"))
        lock = Path(
            os.environ.get("QGIS_PURIFIER_LOCK", project / "qgis-purifier.lock.json")
        ).resolve()
        native_exec(project, lock, sys.argv[1:], os.environ["QGIS_PURIFIER_COMMAND"])
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    parser.add_argument("--lock")
    sub = parser.add_subparsers(dest="action", required=True)
    lock_parser = sub.add_parser("lock")
    lock_parser.add_argument("--update", action="store_true")
    sub.add_parser("prefetch")
    for name in ["build", "bundle"]:
        sub.add_parser(name)
    publish = sub.add_parser("publish")
    publish.add_argument("--tag", required=True)
    execute = sub.add_parser("exec")
    execute.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    project = project_path(args.project or os.environ.get("QGIS_PURIFIER_PROJECT"))
    lock = Path(
        args.lock
        or os.environ.get("QGIS_PURIFIER_LOCK", project / "qgis-purifier.lock.json")
    ).resolve()
    if args.action == "lock" and args.update:
        capture(project, lock)
        return
    if args.action == "exec":
        arguments = (
            args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        )
        native_exec(project, lock, arguments)
        return
    validate(project, lock)
    if args.action == "lock":
        realize(project, lock)
    elif args.action == "prefetch":
        print(realize(project, lock))
    elif args.action in {"build", "bundle"}:
        print(
            realize(project, lock, "project" if args.action == "build" else "release")
        )
    elif args.action == "publish":
        release = realize(project, lock, "release")
        run(
            [
                os.environ.get("QGIS_PURIFIER_GH", "gh"),
                "release",
                "upload",
                args.tag,
                str(release / "qgis-project.tar.gz"),
                "--clobber",
            ]
        )


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"qgis-purifier: {error}", file=sys.stderr)
        sys.exit(1)
