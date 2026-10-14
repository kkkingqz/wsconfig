# Windows programs with a GNOME launcher: the logic of windows/apps.toml
# (what the user edits; its comments say the keys). Builds
# ~/.local/share/wsconfig/windows/apps.json for ws windows, one launcher
# ws-win-NAME.desktop per program and ws-win-exe.desktop for a double click
# on an .exe.
#
# The launchers only on a host that has the box: yes in
# hosts/HOST/boxes.toml, else the default of the box in
# distrobox/catalog.toml (lib/catalog.nix); apps.json lists every program.
{ config, lib, wsHost, wsConfig, core, ... }:
let
  catalog = import ../lib/catalog.nix { inherit lib; hosts = wsConfig + "/hosts"; };
  hasBox = box: catalog.has wsHost "boxes" box (config.ws.boxDefaults.${box} or "ask");

  schema = import ../lib/schema.nix { inherit lib; };
  windows = (import ../lib/config.nix { inherit lib; }).read {
    file = wsConfig + "/windows/apps.toml";
    type = schema.table {
      keys = {
        default_box = schema.string;
        ansi_locale = schema.string;
        ui_locale = schema.string;
        apps = schema.attrsOf (schema.table {
          keys = lib.genAttrs [ "box" "prefix" "exe" "args" "env" "icon" "title" "categories" "wm_class" ]
            (_: schema.string);
          required = [ "exe" ];
        });
      };
      required = [ "default_box" "ansi_locale" "ui_locale" ];
    };
  };
  defaultBox = windows.default_box;
  ansiLocale = windows.ansi_locale;
  uiLocale = windows.ui_locale;
  apps = lib.mapAttrs (_: a: removeAttrs a [ "wm_class" ]
    // lib.optionalAttrs (a ? wm_class) { wmClass = a.wm_class; }) (windows.apps or { });

  withDefaults = name: a: {
    box = defaultBox;
    prefix = "default";
    args = "";
    env = "";
    title = name;
    icon = "application-x-executable";
    categories = "";
    wmClass = baseNameOf a.exe;
  } // a;

  # The prefix on the host (the container HOME is ~/distrobox/BOX).
  prefixDir = a: "${config.home.homeDirectory}/distrobox/${a.box}/"
    + (if a.prefix == "default" then ".wine" else "prefixes/${a.prefix}");

  iconOf = a: if lib.hasInfix "." a.icon then "${prefixDir a}/${a.icon}" else a.icon;

  full = lib.mapAttrs withDefaults apps;

  exeTypes = [
    "application/vnd.microsoft.portable-executable"
    "application/x-ms-dos-executable"
    "application/x-msdownload"
  ];

  exeDesktop = ''
    [Desktop Entry]
    Type=Application
    Name=Wine (${defaultBox})
    Comment=Run a Windows program in the standard prefix of ${defaultBox}
    Exec=${core}/bin/ws windows exec --box ${defaultBox} %f
    Icon=application-x-ms-dos-executable
    Terminal=false
    NoDisplay=true
    MimeType=${lib.concatMapStrings (t: "${t};") exeTypes}
  '';

  # What wswin reads (ws help plan-v2, 2.6).
  appsJson = builtins.toJSON {
    default_box = defaultBox;
    lc_ctype = ansiLocale;
    lc_messages = uiLocale;
    apps = lib.mapAttrs (_: a: { inherit (a) box prefix exe args env; }) full;
  };

  desktop = name: a: ''
    [Desktop Entry]
    Type=Application
    Name=${a.title}
    Exec=${core}/bin/ws windows run ${name}
    Icon=${iconOf a}
    Terminal=false
    Categories=${a.categories}
    StartupWMClass=${a.wmClass}
    X-Workstation-Box=${a.box}
  '';
in
{
  assertions = lib.mapAttrsToList (name: a: {
    assertion = builtins.match "[A-Za-z0-9._-]+" name != null && name != "exe"
      && builtins.match "[A-Za-z0-9._-]+" a.prefix != null
      && !(lib.hasPrefix "/" a.exe);
    message = "windows/apps.toml: ${name}: name/prefix [A-Za-z0-9._-] (not exe: ws-win-exe.desktop), exe relative to the prefix";
  }) full
  # A launcher of a box that is no Windows box would start nothing.
  ++ map (box: {
    assertion = lib.elem box config.ws.windowsBoxes;
    message = "windows/apps.toml: ${box} is no Windows box of distrobox/catalog.toml (windows = { profile = ... }); Windows boxes: ${lib.concatStringsSep ", " config.ws.windowsBoxes}";
  }) (lib.unique ([ defaultBox ] ++ lib.mapAttrsToList (_: a: a.box) full));

  xdg.dataFile = {
    "wsconfig/windows/apps.json".text = appsJson;
  } // lib.optionalAttrs (hasBox defaultBox) {
    "applications/ws-win-exe.desktop".text = exeDesktop;
  } // lib.mapAttrs' (name: a:
    lib.nameValuePair "applications/ws-win-${name}.desktop" { text = desktop name a; })
    (lib.filterAttrs (_: a: hasBox a.box) full);

  # Only these keys of ~/.config/mimeapps.list; the rest stays the user's.
  home.activation.wswinExeDefault = lib.mkIf (hasBox defaultBox) (lib.hm.dag.entryAfter [ "flatpakDesktopDatabase" ] ''
    if [ -x /usr/bin/xdg-mime ]; then
      for t in ${lib.concatStringsSep " " exeTypes}; do
        if [ "$(/usr/bin/xdg-mime query default "$t")" != ws-win-exe.desktop ]; then
          run /usr/bin/xdg-mime default ws-win-exe.desktop "$t"
        fi
      done
    fi
  '');
}
