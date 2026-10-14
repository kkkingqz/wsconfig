# Distrobox containers and their exported applications. The catalog of
# containers is distrobox/catalog.toml (what the user edits; its comments
# say the keys); this file is the logic: the hooks by name, the defaults,
# the LogPixels by the display scale, and what it builds into
# ~/.local/share/wsconfig/distrobox (one link to the store) for ws box and
# ws windows:
#
#   containers.ini  manifest for `distrobox assemble` (its own format)
#   boxes.json      the containers in order, for wsbox and wswin: name,
#                   image, home, hooks, exports (ALIAS: desktop file inside
#                   the container), gpu, default, and for Windows boxes
#                   profile, driver, dpi, init_overrides (ws help plan-v2, 2.6)
#
# Which host has which: hosts/HOST/boxes.toml (lib/ws_catalog.py).
{ config, lib, pkgs, facts, core, wsConfig, ... }:
let
  # LogPixels of new prefixes by the display scale (lib/scale.nix).
  scale = import ../lib/scale.nix { inherit lib facts; };
  # The same for every container unless a container sets it.
  defaults = {
    init = false;
    nvidia = false;
    pull = true;
    root = false;
    start_now = false;
    entry = false;
  };

  keyOrder = [ "init" "nvidia" "pull" "root" "start_now" "entry" ];

  # Hooks run as root on every container start (init_hooks at the end of
  # distrobox-init, pre_init_hooks before its package setup).
  #
  # Their path is fixed when a container is created, so it must not change:
  # not the core in the store (a new path with every change, gone after a
  # garbage collection; /nix is not even mounted in the container), but
  # copies of distrobox/arch and distrobox/wine of the core in
  # ~/.local/share/wsconfig/hooks, renewed by every switch (the host
  # HOME is mounted in the container). Run through sh: no shebang or mode
  # is needed, and a hook derives nothing from the owner or mode of its
  # files; what it needs, such as the user of a build, is an argument
  # (ws help plan-v2, stage 5).
  hooks = "${config.home.homeDirectory}/.local/share/wsconfig/hooks";

  # The hook names of catalog.toml: NAME -> { path under hooks; fixed:
  # arguments from Nix; needsArgs: the catalog gives arguments, else it
  # gives none }. ntsync gets the user: makepkg runs as the user of the
  # container, which distrobox makes for the host user.
  hookTable = {
    ntsync = { path = "arch/wsbox-host-ntsync/install-hook"; fixed = [ facts.user ]; };
    pacman-install = { path = "arch/pacman-install-hook"; needsArgs = true; };
    multilib = { path = "arch/multilib-hook"; };
    winehq-install = { path = "wine/winehq-install-hook"; };
    locale = { path = "wine/locale-hook"; needsArgs = true; };
  };
  hookLine = box: line:
    let
      words = lib.filter (w: w != "") (lib.splitString " " line);
      name = lib.head words;
      args = lib.tail words;
      h = hookTable.${name} or (throw
        "distrobox/catalog.toml: ${box}: unknown hook ${name} (hooks: ${lib.concatStringsSep ", " (lib.attrNames hookTable)})");
    in
    if (h.needsArgs or false) && args == [ ] then
      throw "distrobox/catalog.toml: ${box}: hook ${name} needs arguments"
    else if !(h.needsArgs or false) && args != [ ] then
      throw "distrobox/catalog.toml: ${box}: hook ${name} takes no arguments"
    else lib.concatStringsSep " " ([ "sh" "${hooks}/${h.path}" ] ++ (h.fixed or [ ]) ++ args);

  schema = import ../lib/schema.nix { inherit lib; };
  boxType = schema.table {
    keys = {
      name = schema.string;
      image = schema.string;
      packages = schema.strings;
      pre_init_hooks = schema.strings;
      init_hooks = schema.strings;
      default = schema.oneOf [ "ask" "no" "yes" ];
      gpu = schema.oneOf [ "amd" ];
      exports = schema.attrsOf schema.string;
      settings = schema.table {
        keys = lib.genAttrs keyOrder (_: schema.bool);
      };
      windows = schema.table {
        keys = {
          profile = schema.oneOf [ "wine" "proton" ];
          driver = schema.oneOf [ "wayland" "x11" ];
          dpi = schema.int;
          init_overrides = schema.string;
        };
        required = [ "profile" ];
      };
    };
    required = [ "name" "image" ];
  };
  catalog = (import ../lib/config.nix { inherit lib; }).read {
    file = wsConfig + "/distrobox/catalog.toml";
    type = schema.table { keys.boxes = schema.listOf boxType; required = [ "boxes" ]; };
  };

  # The catalog in the form of the rest of this file.
  fromToml = b:
    {
      inherit (b) name image;
      preInitHooks = map (hookLine b.name) (b.pre_init_hooks or [ ]);
      initHooks = map (hookLine b.name) (b.init_hooks or [ ]);
    }
    // lib.optionalAttrs (b ? packages) { inherit (b) packages; }
    // lib.optionalAttrs (b ? default) { inherit (b) default; }
    // lib.optionalAttrs (b ? gpu) { inherit (b) gpu; }
    // lib.optionalAttrs (b ? exports) { inherit (b) exports; }
    // lib.optionalAttrs (b ? settings) { inherit (b) settings; }
    // lib.optionalAttrs (b ? windows) {
      windows = {
        inherit (b.windows) profile;
        # LogPixels by the display scale (lib/scale.nix): 128 per 1.0 through
        # XWayland with native scaling (driver x11), 96 otherwise (the
        # Wayland driver does not scale; Proton).
        dpi = b.windows.dpi or (if (b.windows.driver or null) == "x11" then scale.dpiX11 else scale.dpi);
      }
      // lib.optionalAttrs (b.windows ? driver) { inherit (b.windows) driver; }
      // lib.optionalAttrs (b.windows ? init_overrides) { initOverrides = b.windows.init_overrides; };
    };

  containers = map fromToml catalog.boxes;

  value = v: if lib.isBool v then lib.boolToString v else toString v;

  containerSection = c:
    let
      home = "\${HOME}/distrobox/${c.name}";
    in
    ''
      [${c.name}]
      image=${c.image}
      home="${home}"
    ''
    + lib.concatMapStrings (k: "${k}=${value (defaults // (c.settings or { })).${k}}\n")
      keyOrder
    + lib.optionalString (c ? packages)
      "additional_packages=\"${lib.concatStringsSep " " c.packages}\"\n"
    + lib.concatMapStrings (h: "pre_init_hooks=\"${h}\"\n") (c.preInitHooks or [ ])
    + lib.concatMapStrings (h: "init_hooks=\"${h}\"\n") (c.initHooks or [ ]);

  # Values as strings, as the tools compare them.
  boxEntry = c:
    let
      w = c.windows or { };
      opt = k: v: lib.optionalAttrs (v != null) { ${k} = toString v; };
    in
    {
      inherit (c) name image;
      home = "\${HOME}/distrobox/${c.name}";
      pre_init_hooks = c.preInitHooks or [ ];
      init_hooks = c.initHooks or [ ];
      exports = c.exports or { };
      default = c.default or "ask";
    }
    // opt "gpu" (c.gpu or null)
    // opt "profile" (w.profile or null)
    // opt "driver" (w.driver or null)
    // opt "dpi" (w.dpi or null)
    // opt "init_overrides" (w.initOverrides or null);

  distroboxConfig = pkgs.runCommandLocal "workstation-distrobox-config" { } ''
    mkdir -p $out
    cp ${pkgs.writeText "containers.ini"
      (lib.concatStringsSep "\n" (map containerSection containers))} $out/containers.ini
    cp ${pkgs.writeText "boxes.json" (builtins.toJSON (map boxEntry containers))} $out/boxes.json
  '';

  names = map (c: c.name) containers;
in
{
  # The default of each container, for windows/apps.nix (its launchers
  # follow the choice of the box).
  options.ws.boxDefaults = lib.mkOption {
    type = lib.types.attrsOf (lib.types.enum [ "ask" "no" "yes" ]);
    readOnly = true;
    internal = true;
    description = "Default (ask, no, yes) of each container of distrobox/distrobox.nix.";
  };

  # The Windows boxes (with windows = { profile }), for windows/apps.nix.
  options.ws.windowsBoxes = lib.mkOption {
    type = lib.types.listOf lib.types.str;
    readOnly = true;
    internal = true;
    description = "The containers of distrobox/catalog.toml with a Windows profile.";
  };

  config.ws.windowsBoxes = map (c: c.name) (lib.filter (c: c ? windows) containers);

  config.ws.boxDefaults = lib.listToAttrs (map (c: lib.nameValuePair c.name (c.default or "ask")) containers);

  config.assertions = [{
    assertion = lib.length names == lib.length (lib.unique names);
    message = "distrobox.nix: duplicate container name";
  }] ++ map (c: {
    assertion = lib.elem (c.windows.profile or "wine") [ "wine" "proton" ]
      && lib.elem (c.gpu or "amd") [ "amd" ];
    message = "distrobox.nix: ${c.name}: profile is wine or proton, gpu is amd";
  }) containers;

  config.xdg.dataFile."wsconfig/distrobox".source = distroboxConfig;

  # The copies of the hooks (see hooks above): replaced as a whole.
  config.home.activation.distroboxHooks = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
    hooks=${lib.escapeShellArg hooks}
    run rm -rf "$hooks.new"
    run mkdir -p "$hooks.new"
    run cp -r ${core}/distrobox/arch ${core}/distrobox/wine "$hooks.new/"
    run chmod -R u+w "$hooks.new"
    run rm -rf "$hooks"
    run mv "$hooks.new" "$hooks"
  '';
}
