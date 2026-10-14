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
}
