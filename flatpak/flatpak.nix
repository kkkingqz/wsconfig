# Flatpak declarations: user remotes, managed apps (apps.txt), per-app
# overrides (overrides.txt) and desktop overrides. wsflatpak stays the owner of apply/check
# and reads what is built here from ~/.local/share/workstation/flatpak (one link to the store):
#
#   remotes.conf      NAME URL
#   apps.conf         REMOTE APP (apps.txt without the workstation marks)
#   overrides/APP.conf, desktop/APP.desktop
#
# Change: apps.txt and overrides.txt through wsflatpak (install, manage,
# filesystem, env, talk, ...), the rest here; then `ws switch`,
# `wsflatpak apply` (or `ws apply`).
# apply resets the overrides of every managed app before setting the declared
# ones, so a key removed here disappears too. Desktop overrides are linked
# into ~/.local/share/applications by home-manager, on a workstation whose
# mark for the app is yes (elsewhere the launcher would start nothing).
{ lib, pkgs, wsHost, ... }:
let
  marks = import ../lib/ws_marks.nix { inherit lib; };

  remotes = {
    flathub = "https://dl.flathub.org/repo/flathub.flatpakrepo";
    flatpark = "https://dl.flatpark.org/flatpark.flatpakrepo";
    chatgpt = "https://rulin132.github.io/chatgpt-flatpak/chatgpt.flatpakrepo";
  };

  # REMOTE APP lines of apps.txt, in order; wsflatpak edits that file. The
  # workstation marks after them (HOST=yes|no|ask, all=...) are read by
  # wsflatpak from the checkout (lib/ws_marks.py), here only for the desktop
  # links.
  apps = lib.concatMap (raw:
    let
      line = lib.head (lib.splitString "#" raw);
      m = builtins.match "[[:space:]]*([^[:space:]=]+)[[:space:]]+([^[:space:]=]+)([[:space:]]+[A-Za-z0-9][A-Za-z0-9_-]*=(yes|no|ask))*[[:space:]]*" line;
    in
    if builtins.match "[[:space:]]*" line != null then [ ]
    else if m == null then throw "flatpak/apps.txt: invalid line: ${raw}"
    else [ { remote = lib.elemAt m 0; app = lib.elemAt m 1; } ]
  ) (lib.splitString "\n" (builtins.readFile ./apps.txt));

  # APP KIND VALUE lines of overrides.txt; wsflatpak edits that file. Built
  # into the keys `wsflatpak apply` sets with `flatpak override`:
  # Context.filesystems, Environment, "Session Bus Policy" (talk only).
  overrideLines = lib.concatMap (raw:
    let
      line = lib.head (lib.splitString "#" raw);
      m = builtins.match "[[:space:]]*([^[:space:]]+)[[:space:]]+(filesystem|env|talk)[[:space:]]+([^[:space:]]+)[[:space:]]*" line;
    in
    if builtins.match "[[:space:]]*" line != null then [ ]
    else if m == null then throw "flatpak/overrides.txt: invalid line: ${raw}"
    else [ { app = lib.elemAt m 0; kind = lib.elemAt m 1; value = lib.elemAt m 2; } ]
  ) (lib.splitString "\n" (builtins.readFile ./overrides.txt));

  overrides = lib.mapAttrs (app: entries:
    let
      values = kind: map (x: x.value) (lib.filter (x: x.kind == kind) entries);
      fs = values "filesystem";
      env = lib.listToAttrs (map (v:
        let kv = builtins.match "([^=]+)=(.*)" v; in
        if kv == null then throw "flatpak/overrides.txt: ${app} env needs KEY=VALUE: ${v}"
        else lib.nameValuePair (lib.elemAt kv 0) (lib.elemAt kv 1)
      ) (values "env"));
      bus = lib.genAttrs (values "talk") (_: "talk");
    in
    lib.optionalAttrs (fs != [ ]) { Context.filesystems = fs; }
    // lib.optionalAttrs (env != { }) { Environment = env; }
    // lib.optionalAttrs (bus != { }) { "Session Bus Policy" = bus; }
  ) (lib.groupBy (x: x.app) overrideLines);

  # Full files, ours: Claude on Wayland at scale 1.5 with its URL handler;
  # Steam through ws-gpu (the AMD dGPU when the boot has it, Intel otherwise),
  # steam:// included, with -console.
  desktop = [
    ./desktop/com.anthropic.ClaudeDesktop.desktop
    ./desktop/com.valvesoftware.Steam.desktop
    ./desktop/io.github.rulin132.ChatGPT.desktop
  ];
  # Linked: those of the apps this workstation has (APP.desktop, APP=yes).
  appMarks = marks.read ./apps.txt;
  linkedDesktop = lib.filter (f:
    marks.has appMarks (lib.removeSuffix ".desktop" (baseNameOf f)) wsHost) desktop;

  toIni = lib.generators.toINI {
    mkKeyValue = lib.generators.mkKeyValueDefault {
      mkValueString = v:
        if lib.isList v then lib.concatMapStrings (x: "${x};") v else toString v;
    } "=";
  };

  lines = f: set: lib.concatStrings (lib.mapAttrsToList f set);

  flatpakConfig = pkgs.runCommandLocal "workstation-flatpak-config" { } (''
    mkdir -p $out/overrides $out/desktop
    cp ${pkgs.writeText "remotes.conf" (lines (n: u: "${n} ${u}\n") remotes)} $out/remotes.conf
    cp ${pkgs.writeText "apps.conf" (lib.concatMapStrings (x: "${x.remote} ${x.app}\n") apps)} $out/apps.conf
  '' + lines (app: o: ''
    cp ${pkgs.writeText "${app}.conf" (toIni o)} $out/overrides/${app}.conf
  '') overrides + lib.concatMapStrings (f: ''
    cp ${f} $out/desktop/${baseNameOf f}
  '') desktop);
in
{
  assertions = map (x: {
    assertion = remotes ? ${x.remote};
    message = "flatpak/apps.txt: ${x.app} uses undeclared remote ${x.remote}";
  }) apps;

  xdg.dataFile = {
    "workstation/flatpak".source = flatpakConfig;
  } // lib.listToAttrs (map (f:
    lib.nameValuePair "applications/${baseNameOf f}" {
      source = "${flatpakConfig}/desktop/${baseNameOf f}";
    }) linkedDesktop);

  # x-scheme-handler/claude comes from mimeinfo.cache next to the link.
  home.activation.flatpakDesktopDatabase = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
    if [ -x /usr/bin/update-desktop-database ]; then
      run /usr/bin/update-desktop-database "$HOME/.local/share/applications"
    fi
  '';
}
