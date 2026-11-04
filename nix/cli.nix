{
  lib,
  runCommand,
  writeText,
  makeWrapper,
  python3,
  original,
  sdk,
  nix,
  gh,
  cacert,
  nixpkgsSrc,
  purifierSrc,
}:
let
  integration = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../qgis_purifier
      ../native
      ./.
    ];
  };
  realize = writeText "qgis-purifier-realize.nix" ''
    { lockPath, projectPath, target ? "environment" }:
    let
      pkgs = import (builtins.storePath "${nixpkgsSrc}") {};
      scope = import ${integration}/nix/scope.nix {
        inherit pkgs;
        nixpkgsSrc = builtins.storePath "${nixpkgsSrc}";
        purifierSrc = builtins.storePath "${purifierSrc}";
      };
      lockFile = builtins.toPath lockPath;
      src = if target == "environment" then builtins.toPath projectPath else builtins.path {
        path = builtins.toPath projectPath;
        name = "qgis-project";
        filter = path: type: !(builtins.elem (baseNameOf path) [ ".git" ".qgis-purifier" "__pycache__" "result" ]);
      };
      build = scope.buildQgisProject { inherit src lockFile; };
    in if target == "environment" then scope.environment { lock = scope.readLock { inherit src lockFile; }; }
       else if target == "project" then build.packages.project
       else if target == "release" then build.release
       else throw "Unknown QGIS purifier target"
  '';
in
runCommand "qgis-purifier" { nativeBuildInputs = [ makeWrapper ]; } ''
  mkdir -p "$out/bin"
  for name in qgis-purifier qgis qgis_process; do
    makeWrapper ${python3}/bin/python "$out/bin/$name" \
      --add-flags '-m qgis_purifier.main' \
      --set PYTHONPATH ${integration} \
      --set QGIS_PURIFIER_COMMAND "$name" \
      --set QGIS_PURIFIER_NATIVE ${integration}/native \
      --set QGIS_PURIFIER_GUI ${original}/bin/qgis \
      --set QGIS_PURIFIER_CMD ${original}/bin/qgis_process \
      --set QGIS_PURIFIER_ORIGINAL ${original} \
      --set QGIS_PURIFIER_FEED_VERSION ${lib.versions.majorMinor original.version} \
      --set QGIS_PURIFIER_SDK ${sdk} \
      --set QGIS_PURIFIER_REALIZE ${realize} \
      --set-default QGIS_PURIFIER_GH ${gh}/bin/gh \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set-default NIX_SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --prefix PATH : ${
        lib.makeBinPath [
          nix
          gh
        ]
      }
  done
''
