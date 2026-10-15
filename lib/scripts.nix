# The scripts of a configuration for Nix (ws help scripts), as
# lib/ws_catalog.py reads them (script_files, script_entries): every file
# of DIR (wsConfig + "/scripts") is a script, its name the command, except
# hidden ones, catalog.toml (the defaults and descriptions) and lib/ (kept
# for libraries, ws help plan-v2, 10.5). DIR may be missing: no scripts.
{ lib }:
let
  schema = import ./schema.nix { inherit lib; };
  entryType = schema.table {
    keys = {
      name = schema.string;
      default = schema.oneOf [ "ask" "no" "yes" ];
      description = schema.string;
    };
    required = [ "name" ];
  };
  catalogType = schema.table { keys.scripts = schema.listOf entryType; };
in
rec {
  # The command names lib/ws_catalog.py takes (SCRIPT_NAME).
  namePattern = "[A-Za-z0-9][A-Za-z0-9._+-]*";
  dirs = [ "lib" ];

  read = dir:
    let
      entries = lib.filterAttrs (n: _: !(lib.hasPrefix "." n) && n != "catalog.toml")
        (if builtins.pathExists dir then builtins.readDir dir else { });
      files = lib.attrNames (lib.filterAttrs (_: t: t == "regular" || t == "symlink") entries);
      subdirs = lib.attrNames (lib.filterAttrs (n: t: t == "directory" && !(lib.elem n dirs)) entries);
      badNames = lib.filter (n: builtins.match namePattern n == null) files;
      catalogFile = dir + "/catalog.toml";
      catalog = if builtins.pathExists catalogFile then builtins.fromTOML (builtins.readFile catalogFile) else { };
      catalogProblems = schema.problems catalogType catalog;
      defaults = lib.listToAttrs (map (e: { inherit (e) name; value = e.default or "ask"; })
        (lib.optionals (catalogProblems == [ ]) (catalog.scripts or [ ])));
    in
    {
      # The scripts, by name.
      names = lib.filter (n: !(lib.elem n badNames)) files;
      # The catalog default of NAME: ask without an entry.
      default = name: defaults.${name} or "ask";
      # What the build refuses, each naming its file.
      errors =
        map (n: "scripts/${n}: not a command name (letters, digits and . _ + -, a letter or digit first)") badNames
        ++ map (d: "scripts/${d}/: no directories in scripts/ but ${lib.concatStringsSep ", " dirs}/") subdirs
        ++ map (p: "scripts/catalog.toml: ${p}") catalogProblems;
    };

  # The scripts of HOST (yes of hosts/HOST/scripts.toml or catalog default
  # yes; CATALOG: lib/catalog.nix) and what the build refuses, RESERVED
  # (names other parts install in ~/.local/bin) included.
  forHost = { dir, catalog, host, reserved ? { } }:
    let
      s = read dir;
      chosen = lib.filter (n: catalog.has host "scripts" n (s.default n)) s.names;
    in
    {
      names = lib.filter (n: !(reserved ? ${n})) chosen;
      errors = s.errors ++ map (n: "scripts/${n}: ~/.local/bin/${n} is ${reserved.${n}}; rename the script")
        (lib.filter (n: reserved ? ${n}) chosen);
    };
}
