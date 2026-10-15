# The scripts of the configuration (ws help scripts): every file of
# scripts/ is a command of that name. On a host: those with yes in
# hosts/HOST/scripts.toml, or default = "yes" in scripts/catalog.toml and no
# choice of the host (lib/catalog.nix, lib/scripts.nix).
#
# Each is a link ~/.local/bin/NAME into the checkout
# (~/<facts.wsconfig>/scripts/NAME; mkOutOfStoreSymlink, as home/ of
# nix/home/links.nix): an edit takes effect at once, a new script or another
# choice with ws apply scripts. A script finds scripts/lib/ next to its real
# path (readlink -f "$0"; ws help plan-v2, 10.5).
#
# ~/.local/share/wsconfig/scripts/scripts.json: the scripts of this build,
# for ws script list and check.
#
# A build error names the file: a name that is no command name, a
# directory other than lib/, a wrong scripts/catalog.toml, a script of this
# host at a path the core or home/ installs.
{ config, lib, facts, wsConfig, wsHost, ... }:
let
  repo = "${config.home.homeDirectory}/${facts.wsconfig}";
  catalog = import ../lib/catalog.nix { inherit lib; hosts = wsConfig + "/hosts"; };
  scripts = import ../lib/scripts.nix { inherit lib; };

  # What else lands in ~/.local/bin: bin/ of the core (nix/home/links.nix),
  # xremap (keyboard/xremap.nix), home/.local/bin of the configuration.
  filesIn = dir: lib.optionals (builtins.pathExists dir)
    (lib.attrNames (builtins.readDir dir));
  reserved = lib.genAttrs (filesIn ../bin) (n: "the ${n} of the core")
    // { xremap = "xremap of the core (keyboard/xremap.nix)"; }
    // lib.genAttrs (filesIn (wsConfig + "/home/.local/bin")) (n: "home/.local/bin/${n} of the configuration");

  host = scripts.forHost {
    dir = wsConfig + "/scripts";
    inherit catalog reserved;
    host = wsHost;
  };
in
{
  assertions = map (message: { assertion = false; inherit message; }) host.errors;

  home.file = lib.listToAttrs (map (name: {
    name = ".local/bin/${name}";
    value.source = config.lib.file.mkOutOfStoreSymlink "${repo}/scripts/${name}";
  }) host.names);

  xdg.dataFile."wsconfig/scripts/scripts.json".text = builtins.toJSON {
    scripts = host.names;
    dir = "${repo}/scripts";
  };
}
