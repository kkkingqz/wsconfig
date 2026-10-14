# Links from $HOME into the checkout (~/<facts.wsconfig>), one file each.
# ws is no link into the checkout: ~/.local/bin/ws is bin/ws of the core in
# the store (nix/pkgs/ws.nix), and so is helpws, the help of the docs. The
# internal tools are not in PATH (helpws plan-v2, stage 5): ws runs them,
# Nix callers use their store paths, and ~/.local/share/wsconfig/libexec
# points at libexec/ of the core for callers that need a fixed path (the
# input-source extension runs ws-caps-led).
# home-manager owns the links; the files stay in the checkout and are edited
# there (mkOutOfStoreSymlink: no copy in the store, no switch after edits).
# New files in the listed directories are linked on the next `ws switch`.
{ config, lib, facts, core, ... }:
let
  repo = "${config.home.homeDirectory}/${facts.wsconfig}";
  src = ../..;

  link = path: config.lib.file.mkOutOfStoreSymlink "${repo}/${path}";

  # Regular files of a checkout directory (the flake sees tracked files only).
  filesIn = dir:
    builtins.attrNames (lib.filterAttrs (_: type: type == "regular")
      (builtins.readDir (src + "/${dir}")));

  # The executables of DIR of the core, as links into the store.
  coreDir = { from, to, filter ? (_: true) }:
    lib.listToAttrs (map (name: {
      name = "${to}/${name}";
      value.source = "${core}/${from}/${name}";
    }) (builtins.filter filter (filesIn from)));

  linkDir = { from, to, filter ? (_: true) }:
    lib.listToAttrs (map (name: {
      name = "${to}/${name}";
      value.source = link "${from}/${name}";
    }) (builtins.filter filter (filesIn from)));

in
{
  xdg.dataFile = {
    "wsconfig/libexec".source = "${core}/libexec";
    # MICRO_CONFIG_HOME of helpws; micro writes its buffers/ there.
    "wsconfig/micro-help/settings.json".source = link "terminal/micro-help/settings.json";
    "wsconfig/micro-help/bindings.json".source = link "terminal/micro-help/bindings.json";
  };

  home.file = lib.mkMerge [
    (linkDir { from = "terminal/fish"; to = ".config/fish"; })
    (linkDir { from = "terminal/fish/conf.d"; to = ".config/fish/conf.d"; })
    (linkDir { from = "terminal/fish/functions"; to = ".config/fish/functions"; })
    (linkDir { from = "terminal/fish/completions"; to = ".config/fish/completions"; })
    (linkDir {
      from = "terminal/ghostty";
      to = ".config/ghostty";
      filter = lib.hasSuffix ".ghostty";
    })
    (coreDir { from = "bin"; to = ".local/bin"; })
    { ".local/bin/helpws".source = "${core}/libexec/helpws"; }
    {
      ".config/nix/nix.conf".source = link "nix/nix.conf";
      ".config/xdg-terminals.list".source = link "terminal/xdg-terminals/xdg-terminals.list";
      ".config/ubuntu-xdg-terminals.list".source =
        link "terminal/xdg-terminals/ubuntu-xdg-terminals.list";
      ".local/share/applications/ghostty-open-here.desktop".source =
        link "terminal/xdg-terminals/ghostty-open-here.desktop";
    }
  ];
}
