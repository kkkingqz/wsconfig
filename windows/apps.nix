# Windows programs with a GNOME launcher. The boxes and their profiles are in
# distrobox/distrobox.nix; wswin installs and runs (helpws windows).
#
# Built into ~/.local/share/wsconfig/windows/apps.json for wswin and one
# launcher ~/.local/share/applications/ws-win-NAME.desktop per program
# (Exec: wswin run NAME).
#
#   box      Windows box; default: defaultBox
#   prefix   "default" ($HOME/.wine of the box) or the name of an own prefix
#            ($HOME/prefixes/NAME); default: "default"
#   exe      path inside the prefix (drive_c/...)
#   args     arguments, split at spaces
#   env      KEY=VALUE ..., split at spaces
#   icon     theme icon name, or a file inside the prefix (has a dot: "winbox.png")
#   title, categories, wmClass (default: the exe file name)
#
# Add a program: wswin install [--box BOX] [--prefix NAME] SETUP.exe, then
# an entry here, ws switch.
#
# A double click on an .exe in Files runs it in the standard prefix of
# defaultBox (ws-win-exe.desktop: wswin exec FILE); switch makes it the
# default application for the .exe types with xdg-mime.
#
# The launchers only on a host that has the box: yes in
# nix/hosts/HOST/boxes.toml, else the default of the box in distrobox.nix
# (lib/catalog.nix); apps.json lists every program.
{ config, lib, wsHost, core, ... }:
let
  defaultBox = "wine-wayland";
  catalog = import ../lib/catalog.nix { inherit lib; };
  hasBox = box: catalog.has wsHost "boxes" box (config.ws.boxDefaults.${box} or "ask");

  # LC_CTYPE of every Windows program (wswin): the codepage for non-Unicode
  # programs, as "Language for non-Unicode programs" in Windows. With the
  # session's C.UTF-8 Wine takes cp1252 and loses Cyrillic (the title of the
  # GOG installer). Wine then also takes the UI language from it unless
  # LC_MESSAGES is set: uiLocale keeps it English, as the host session.
  ansiLocale = "ru_RU.UTF-8";
  uiLocale = "en_US.UTF-8";

  apps = {
    winbox = {
      title = "WinBox 3";
      # Native Wayland since 2026-09-28 (was wine/XWayland, LogPixels 192).
      box = "wine-wayland";
      prefix = "winbox";
      exe = "drive_c/Program Files/WinBox/winbox.exe";
      # No Mono prompt: WinBox does not use .NET.
      env = "WINEDLLOVERRIDES=mscoree=";
      # From the AUR winbox3 package, copied into the prefix.
      icon = "winbox.png";
      categories = "Network;RemoteAccess;";
    };
  };

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

  # What wswin reads (helpws plan-v2, 2.6).
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
    message = "windows/apps.nix: ${name}: name/prefix [A-Za-z0-9._-] (not exe: ws-win-exe.desktop), exe relative to the prefix";
  }) full;

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
