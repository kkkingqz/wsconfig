# The TOML of a module, merged and checked (ws help plan-v2, 7.0;
# ws help architecture-v2, 10): the defaults of the core, then the common
# file of the configuration, then the file of the host when it has one.
#
#   read { file = ../gnome/config.toml; host = ../nix/hosts/mbp16/gnome.toml;
#          type = schema.table { … }; defaults = { … }; }
#
# Merge: tables merge by key, a scalar or a list of a later file replaces
# the earlier one (a list of the host replaces the common list). A table
# against a scalar is an error naming the file and the parameter. Every
# file is checked by TYPE on its own (unknown keys, types), the merged
# result also for the required keys. A missing host file is no error; a
# missing common file is one unless OPTIONAL.
{ lib }:
let
  schema = import ./schema.nix { inherit lib; };
in
rec {
  # B over A; PATH and WHERE (the file of B) name a conflict. Returns
  # { value; problems; }.
  merge = where: path: a: b:
    if builtins.isAttrs a && builtins.isAttrs b then
      let
        keys = lib.unique (lib.attrNames a ++ lib.attrNames b);
        at = k: if path == "" then k else "${path}.${k}";
        each = k:
          if !(a ? ${k}) then { value = b.${k}; problems = [ ]; }
          else if !(b ? ${k}) then { value = a.${k}; problems = [ ]; }
          else merge where (at k) a.${k} b.${k};
        parts = lib.genAttrs keys each;
      in
      {
        value = lib.mapAttrs (_: p: p.value) parts;
        problems = lib.concatMap (k: parts.${k}.problems) keys;
      }
    else if builtins.isAttrs a || builtins.isAttrs b then
      {
        value = b;
        problems = [ "${where}: ${path} is ${if builtins.isAttrs b then "a table" else "a value"} here, ${if builtins.isAttrs a then "a table" else "a value"} before" ];
      }
    else { value = b; problems = [ ]; };

  # NAME of a path for the messages: relative to the repository when it is
  # in the store copy of the flake.
  shown = file:
    let s = toString file; m = builtins.match "/nix/store/[^/]+/(.*)" s; in
    if m == null then s else lib.head m;

  # The data of FILE, or null when it is missing.
  load = file: if builtins.pathExists file then builtins.fromTOML (builtins.readFile file) else null;

  read = { file, host ? null, type, defaults ? { }, optional ? false }:
    let
      common = load file;
      own = if host == null then null else load host;
      fileProblems = f: d:
        if d == null then [ ]
        else map (m: "${shown f}: ${m}")
          # Required keys only for the result: a host file adds or replaces.
          ((schema.problems (type // { check = p: v: lib.filter (m: !(lib.hasPrefix "no " m)) (type.check p v); }) d));
      missing = lib.optional (common == null && !optional) "${shown file}: missing";
      step1 = merge (shown file) "" defaults (if common == null then { } else common);
      step2 = if own == null then { value = step1.value; problems = [ ]; }
        else merge (shown host) "" step1.value own;
      result = step2.value;
      resultProblems = map (m: "${shown file}${lib.optionalString (own != null) " + ${shown host}"}: ${m}")
        (lib.filter (lib.hasPrefix "no ") (schema.problems type result));
      all = missing ++ fileProblems file common ++ fileProblems host own
        ++ step1.problems ++ step2.problems ++ resultProblems;
    in
    if all != [ ] then throw "${lib.concatStringsSep "; " all} (ws help rebuild)" else result;
}
