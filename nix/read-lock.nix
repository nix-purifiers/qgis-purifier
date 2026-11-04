{ lib }:
{
  src,
  lockFile ? src + "/qgis-purifier.lock.json",
}:
let
  raw = if builtins.pathExists lockFile then builtins.fromJSON (builtins.readFile lockFile) else { };
  data = if builtins.isAttrs raw then raw else { };
  entries = data.entries or [ ];
  component = s: builtins.isString s && builtins.match "[A-Za-z_][A-Za-z0-9_]*" s != null;
  selection =
    if builtins.pathExists (src + "/qgis-purifier.json") then
      builtins.fromJSON (builtins.readFile (src + "/qgis-purifier.json"))
    else
      null;
  valid =
    (data.version or null) == 1
    && (data.purifier or null) == "qgis"
    && builtins.isString (data.sdk or null)
    && builtins.isAttrs (data.selection or null)
    && data.selection == selection
    && builtins.isList (data.selection.plugins or null)
    && builtins.all component data.selection.plugins
    && builtins.isAttrs (data.native.catalog or null)
    && builtins.isList entries
    && builtins.all (
      e:
      builtins.isAttrs e
      && component (e.path or null)
      && builtins.isString (e.url or null)
      && lib.hasPrefix "https://" e.url
      && builtins.isString (e.hash or null)
      && builtins.match "sha256-[A-Za-z0-9+/]{43}=" e.hash != null
      && builtins.isString (e.qgis.version or null)
    ) entries
    && builtins.length (lib.unique (map (e: e.path) entries)) == builtins.length entries
    && builtins.all (id: builtins.elem id (map (e: e.path) entries)) data.selection.plugins;
in
{
  purifier = "qgis";
  inherit data entries;
  problems = lib.optional (
    !valid
  ) "QGIS lock is missing, malformed, or stale; run qgis-purifier lock --update";
  outputs = {
    packages = [
      "default"
      "environment"
      "project"
    ];
    tests = [ "default" ];
    release = [ "default" ];
  };
}
