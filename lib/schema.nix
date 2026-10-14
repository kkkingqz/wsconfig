# Types and checks of the TOML files of the configuration (ws help plan-v2,
# 7.0): host.toml (lib/host.nix) and the files of the modules
# (lib/config.nix). A type is { name; check = PATH: VALUE: [ MESSAGE ]; }:
# the messages of everything wrong, [ ] when it is fine. PATH names the
# value as the user finds it in the file: platform.kernelParams.
{ lib }:
rec {
  # A value that passes OK; NAME says what it must be.
  scalar = name: ok: {
    inherit name;
    check = path: v: lib.optional (!ok v) "${path} must be ${name}";
  };

  string = scalar "a string" builtins.isString;
  strings = scalar "a list of strings" (v: builtins.isList v && lib.all builtins.isString v);
  bool = scalar "true or false" builtins.isBool;
  int = scalar "a whole number" builtins.isInt;
  number = scalar "a number" (v: builtins.isInt v || builtins.isFloat v);
  port = scalar "a port number" (v: builtins.isInt v && v > 0 && v < 65536);
  oneOf = values: scalar ("one of " + lib.concatMapStringsSep ", " (v: ''"${v}"'') values)
    (v: lib.elem v values);

  # A list whose every element is of type T: PATH[1], PATH[2], … in the
  # messages (TOML has no index, the file does: the first, the second).
  listOf = t: {
    name = "a list of ${t.name}";
    check = path: v:
      if !builtins.isList v then [ "${path} must be a list" ]
      else lib.concatLists (lib.imap1 (i: e: t.check "${path}[${toString i}]" e) v);
  };

  # A table of any keys, every value of type T.
  attrsOf = t: {
    name = "a table of ${t.name}";
    check = path: v:
      if !builtins.isAttrs v then [ "${path} must be a table" ]
      else lib.concatLists (lib.mapAttrsToList (k: e: t.check "${path}.${k}" e) v);
  };

  # A table of known KEYS (key -> type); REQUIRED of them must be there.
  # Messages as for host.toml: "unknown key k in [path]", "path.k must be
  # …", "no k in [path]".
  table = { keys, required ? [ ] }: {
    name = "a table";
    check = path: v:
      let
        at = k: if path == "" then k else "${path}.${k}";
        shown = if path == "" then "the file" else "[${path}]";
      in
      if !builtins.isAttrs v then [ "${path} must be a table" ]
      else
        map (k: "unknown key ${k} in ${shown}") (lib.filter (k: !(keys ? ${k})) (lib.attrNames v))
        ++ lib.concatMap (k: lib.optionals (keys ? ${k}) (keys.${k}.check (at k) v.${k})) (lib.attrNames v)
        ++ map (k: "no ${k} in ${shown}") (lib.filter (k: !(v ? ${k})) required);
  };

  # The messages of DATA against type T, at the top of a file.
  problems = t: data: t.check "" data;

  # DATA when it is fine, else a throw naming WHERE (the file) and every
  # problem.
  checked = where: t: data:
    let p = problems t data; in
    if p != [ ] then throw "${where}: ${lib.concatStringsSep "; " p} (ws help rebuild)" else data;
}
