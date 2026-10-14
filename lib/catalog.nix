# The choice of a host for Nix (lib/ws_catalog.py writes it; helpws
# plan-v2, stage 3): nix/hosts/HOST/MODULE.toml with yes = [...] and
# no = [...]. A name in neither has the default of its catalog position
# (ask, no or yes). The tools validate the files; this only reads.
# HOSTS: the directory of the host directories (tests: a fixture).
{ lib, hosts ? ../nix/hosts }:
rec {
  # { yes = [ ... ]; no = [ ... ]; } of HOST for MODULE (flatpak, boxes,
  # widgets); both empty without a file.
  choice = host: module:
    let
      file = hosts + "/${host}/${module}.toml";
      data = if builtins.pathExists file then builtins.fromTOML (builtins.readFile file) else { };
    in
    { yes = data.yes or [ ]; no = data.no or [ ]; } // removeAttrs data [ "yes" "no" ];

  # yes, no or ask of NAME in CHOICE, DEFAULT when it has neither.
  stateIn = c: name: default:
    if lib.elem name c.yes then "yes" else if lib.elem name c.no then "no" else default;

  state = host: module: name: default: stateIn (choice host module) name default;

  has = host: module: name: default: state host module name default == "yes";

  # Flatpak overrides as lib/flatpak_catalog.py computes them. The key of a
  # value: the env name, the filesystem path without its mode, the bus.
  keyOf = kind: value:
    if kind == "env" then lib.head (lib.splitString "=" value)
    else if kind == "filesystem" then
      let m = builtins.match "(.*):(ro|rw|create)" value; in if m == null then value else lib.head m
    else value;

  # [ { kind; value; } ] of a catalog entry or a host section; env as NAME=VALUE.
  valuesOf = e:
    map (value: { kind = "filesystem"; inherit value; }) (e.filesystems or [ ])
    ++ lib.mapAttrsToList (k: v: { kind = "env"; value = "${k}=${v}"; }) (e.env or { })
    ++ map (value: { kind = "talk"; inherit value; }) (e.talk or [ ]);

  itemKey = x: "${x.kind} ${keyOf x.kind x.value}";

  # The values of catalog entry APP on a host with SECTION
  # ([overrides."APP"] of its flatpak.toml): the catalog ones without the
  # skipped and those the host replaces, then the host's.
  overridesOf = app: section:
    let
      own = valuesOf section;
      drop = (section.skip or [ ]) ++ map itemKey own;
    in
    lib.filter (x: !(lib.elem (itemKey x) drop)) (valuesOf app) ++ own;
}
