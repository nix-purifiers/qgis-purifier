{
  lib,
  runCommand,
  python3,
  original,
  environment,
  readLock,
  gnutar,
  gzip,
}:
{
  src,
  lockFile ? src + "/qgis-purifier.lock.json",
  script ? "build.py",
  fetchers ? { },
  doCheck ? false,
  checkCommand ? "",
}:
let
  lock = readLock { inherit src lockFile; };
  profile = environment { inherit lock fetchers; };
  projectSource = lib.cleanSourceWith {
    inherit src;
    filter =
      path: type:
      !(builtins.elem (baseNameOf path) [
        ".git"
        ".qgis-purifier"
        "__pycache__"
        "result"
      ]);
  };
  project = runCommand "qgis-project" { } ''
    export QGIS_PURIFIER_ENVIRONMENT=${profile} QGIS_PURIFIER_COMMAND_BINARY=${original}/bin/qgis_process
    export QGIS_PURIFIER_OUTPUT="$out"
    mkdir -p "$out"
    cp -r ${projectSource} project
    chmod -R u+w project
    cd project
    export QGIS_PURIFIER_SCRIPT="$PWD/"${lib.escapeShellArg script}
    ${python3}/bin/python ${../native}/qgis_purifier_run_build.py
    ${lib.optionalString doCheck checkCommand}
  '';
  release =
    runCommand "qgis-project-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        mkdir -p "$out"
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -cf - -C ${project} . | gzip -n > "$out/qgis-project.tar.gz"
      '';
in
{
  packages = {
    default = project;
    inherit project;
    environment = profile;
  };
  tests = project;
  inherit release;
  fetches = lock.entries;
}
