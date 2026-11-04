{
  lib,
  runCommand,
  writeText,
  fetchurl,
  fetchgit,
  python3,
  original,
  purifier,
  sdk,
}:
{
  lock,
  fetchers ? { },
}:
let
  checked = purifier.checkLock lock;
  tree = purifier.tree (
    {
      name = "qgis-locked-plugin-archives";
      entries = checked.entries;
      inherit
        runCommand
        writeText
        fetchurl
        fetchgit
        python3
        ;
    }
    // fetchers
  );
  context = writeText "qgis-lock.json" (builtins.toJSON checked.data);
  request = writeText "qgis-native-install-request.json" (
    builtins.toJSON {
      action = "install";
      catalog = checked.data.native.catalog;
      entries = map (e: {
        inherit (e) path;
        inherit (e.qgis) version;
        archive = "${tree}/${e.path}";
      }) checked.entries;
    }
  );
in
assert lib.assertMsg (checked.data.sdk == sdk) "QGIS SDK changed; update the purifier lock";
runCommand "qgis-locked-environment" { passthru = { inherit tree; }; } ''
  export HOME="$TMPDIR/home" XDG_CONFIG_HOME="$TMPDIR/config" XDG_DATA_HOME="$TMPDIR/data" XDG_CACHE_HOME="$TMPDIR/cache" QT_QPA_PLATFORM=offscreen
  export QGIS_CUSTOM_CONFIG_PATH="$TMPDIR/profile" QGIS_PURIFIER_RESPONSE="$TMPDIR/installed.json"
  mkdir -p "$HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$out/plugins" "$out/expressions"
  touch "$out/expressions/__init__.py"
  ${python3}/bin/python ${../native}/qgis_purifier_install_request.py ${request} "$out/plugins" "$TMPDIR/request.json"
  export QGIS_PURIFIER_REQUEST="$TMPDIR/request.json"
  ${original}/bin/qgis_process --json run ${../native}/qgis_purifier_native.py -- > "$TMPDIR/native.json"
  ${python3}/bin/python ${../native}/qgis_purifier_verify.py "$QGIS_PURIFIER_RESPONSE"
  ln -s ${context} "$out/lock.json"
''
