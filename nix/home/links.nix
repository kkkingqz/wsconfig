# What lands in $HOME as files of a checkout or of the core (ws help
# plan-v2, 8.3).
#
# Personal settings: home/ of the configuration mirrors $HOME. Every file
# home/P the flake sees (tracked by Git) is a link ~/P into the checkout
# (~/<facts.wsconfig>/home/P; mkOutOfStoreSymlink: no copy in the store, an
# edit takes effect without a switch). A new file: git add, then ws apply.
#
# Parts of the core: links into the core in the store (nix/pkgs/ws.nix),
# replaced on ws apply: ~/.local/bin/ws, the fish completions, conf.d/
# 00-nix.fish and user-bin.fish, ~/.config/nix/nix.conf, the micro config
# that `ws help` reads and ~/.local/share/wsconfig/libexec (for callers that need a
# fixed path: the input-source extension runs ws-caps-led). A file of home/
# at one of these paths, or at a path another module writes (home.file,
# xdg.configFile, xdg.dataFile: ssh.fish of terminal/ssh-colors.nix, …), is
# a build error naming it: nothing overwrites anything silently.
{ config, options, lib, facts, core, wsConfig, ... }:
let
  repo = "${config.home.homeDirectory}/${facts.wsconfig}";
  coreSrc = ../..;

  # Regular files of a directory under ROOT (the flake sees tracked files only).
  filesIn = root: dir:
    builtins.attrNames (lib.filterAttrs (_: type: type == "regular")
      (builtins.readDir (root + "/${dir}")));

  # The files of DIR of the core as links into the store, at TO/NAME.
  coreDir = { from, to }:
    lib.listToAttrs (map (name: {
      name = "${to}/${name}";
      value.source = "${core}/${from}/${name}";
    }) (filesIn coreSrc from));

  coreFiles = coreDir { from = "bin"; to = ".local/bin"; }
    // coreDir { from = "terminal/fish/completions"; to = ".config/fish/completions"; }
    // {
      ".config/fish/conf.d/00-nix.fish".source = "${core}/terminal/fish/conf.d/00-nix.fish";
      ".config/fish/conf.d/user-bin.fish".source = "${core}/terminal/fish/conf.d/user-bin.fish";
      ".config/nix/nix.conf".source = "${core}/nix/nix.conf";
    };
  # Under $HOME too, through xdg.dataFile.
  coreData = {
    "wsconfig/libexec".source = "${core}/libexec";
    # MICRO_CONFIG_HOME of ws help (libexec/helpws); micro writes its buffers/ there.
    "wsconfig/micro-help/settings.json".source = "${core}/terminal/micro-help/settings.json";
    "wsconfig/micro-help/bindings.json".source = "${core}/terminal/micro-help/bindings.json";
  };
  dataHome = lib.removePrefix "${config.home.homeDirectory}/" config.xdg.dataHome;
  coreTargets = lib.attrNames coreFiles ++ map (p: "${dataHome}/${p}") (lib.attrNames coreData);

  homeDir = wsConfig + "/home";
  # home/P relative paths, every file below home/.
  personal = lib.optionals (builtins.pathExists homeDir)
    (map (f: lib.removePrefix "${toString homeDir}/" (toString f))
      (lib.filesystem.listFilesRecursive homeDir));
  # A personal path that is or lies inside a path of the core.
  ofCore = p: lib.any (c: p == c || lib.hasPrefix "${c}/" p) coreTargets;
  conflicts = lib.filter ofCore personal;

  # The paths under $HOME the other modules define, by where they are.
  otherDefs = opt: lib.concatMap (d: lib.attrNames d.value)
    (lib.filter (d: d.file != toString ./links.nix) opt.definitionsWithLocations);
  configHome = lib.removePrefix "${config.home.homeDirectory}/" config.xdg.configHome;
  others = otherDefs options.home.file
    ++ map (p: "${configHome}/${p}") (otherDefs options.xdg.configFile)
    ++ map (p: "${dataHome}/${p}") (otherDefs options.xdg.dataFile);
  ofOthers = p: lib.any (o: p == o || lib.hasPrefix "${o}/" p) others;
in
{
  assertions = map (p: {
    assertion = false;
    message = "home/${p}: ~/${p} is installed by the core (nix/home/links.nix); remove it from home/";
  }) conflicts
  ++ map (p: {
    assertion = false;
    message = "home/${p}: ~/${p} is written by a module of the core; remove it from home/ (or change the module's settings)";
  }) (lib.filter (p: !(ofCore p) && ofOthers p) personal);

  xdg.dataFile = coreData;

  home.file = coreFiles // lib.listToAttrs (map (p: {
    name = p;
    value.source = config.lib.file.mkOutOfStoreSymlink "${repo}/home/${p}";
  }) (lib.filter (p: !(ofCore p)) personal));
}
