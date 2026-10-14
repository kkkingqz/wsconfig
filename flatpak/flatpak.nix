# Flatpak declarations: user remotes, managed apps (apps.txt), per-app
# overrides (overrides.txt) and desktop overrides. wsflatpak stays the owner of apply/check
# and reads what is built here from ~/.local/share/workstation/flatpak (one link to the store):
#
#   flatpak.json      remotes (NAME: URL), apps (REMOTE APP of apps.txt,
#                     in order, without the workstation marks), overrides
#                     (APP: filesystems, environment, session_bus) of this
#                     workstation (helpws plan-v2, 2.6)
#   desktop/APP.desktop
#
# Change: apps.txt and overrides.txt through wsflatpak (install, manage,
# filesystem, env, talk, ...), the rest here; then `ws switch`,
# `wsflatpak apply` (or `ws apply`).
# apply resets the overrides of every managed app before setting the declared
# ones, so a key removed here disappears too. Desktop overrides are linked
# into ~/.local/share/applications by home-manager, on a workstation whose
# mark for the app is yes (elsewhere the launcher would start nothing).
{ lib, pkgs, wsHost, facts, ... }:
let
  marks = import ../lib/ws_marks.nix { inherit lib; };
  # @claude@, @chatgpt@ in the desktop files: the scale factors of the host.
  scale = import ../lib/scale.nix { inherit lib facts; };
  fill = f: pkgs.writeText (baseNameOf f) (builtins.replaceStrings
    [ "@claude@" "@chatgpt@" ] [ scale.claude scale.chatgpt ] (builtins.readFile f));

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

  # APP KIND VALUE [HOST=yes|no ... all=yes|no] lines of overrides.txt;
  # wsflatpak edits that file. Only the lines that apply to this workstation
  # (yes: own mark, else all=, else yes) are built into the keys `wsflatpak
  # apply` sets with `flatpak override`: Context.filesystems, Environment,
  # "Session Bus Policy" (talk only).
  overrideLines = lib.concatMap (raw:
    let
      line = lib.head (lib.splitString "#" raw);
      m = builtins.match "[[:space:]]*([^[:space:]]+)[[:space:]]+(filesystem|env|talk)[[:space:]]+([^[:space:]]+)(([[:space:]]+[A-Za-z0-9][A-Za-z0-9_-]*=(yes|no))*)[[:space:]]*" line;
    in
    if builtins.match "[[:space:]]*" line != null then [ ]
    else if m == null then throw "flatpak/overrides.txt: invalid line: ${raw}"
    else if marks.stateIn (marks.marksIn (lib.elemAt m 3)) wsHost "yes" != "yes" then [ ]
    else [ { app = lib.elemAt m 0; kind = lib.elemAt m 1; value = lib.elemAt m 2; } ]
  ) (lib.splitString "\n" (builtins.readFile ./overrides.txt));

  # One value per key on a workstation, as wsflatpak keeps it: an env name,
  # a filesystem path whatever its mode (:ro, :rw, :create).
  overrideKey = x:
    if x.kind == "env" then lib.head (lib.splitString "=" x.value)
    else if x.kind == "filesystem" then
      let m = builtins.match "(.*):(ro|rw|create)" x.value; in if m == null then x.value else lib.head m
    else x.value;
  duplicateKeys = lib.filter (k: lib.count (x: "${x.app} ${x.kind} ${overrideKey x}" == k) overrideLines > 1)
    (lib.unique (map (x: "${x.app} ${x.kind} ${overrideKey x}") overrideLines));

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
    { filesystems = fs; environment = env; session_bus = bus; }
  ) (lib.groupBy (x: x.app) overrideLines);

  # Full files, ours: Claude on Wayland at the factor of lib/scale.nix with its
  # URL handler; ChatGPT likewise;
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

  manifest = builtins.toJSON {
    inherit remotes overrides;
    apps = map (x: { inherit (x) remote app; }) apps;
  };

  flatpakConfig = pkgs.runCommandLocal "workstation-flatpak-config" { } (''
    mkdir -p $out/desktop
    cp ${pkgs.writeText "flatpak.json" manifest} $out/flatpak.json
  '' + lib.concatMapStrings (f: ''
    cp ${fill f} $out/desktop/${baseNameOf f}
  '') desktop);
in
{
  assertions = map (x: {
    assertion = remotes ? ${x.remote};
    message = "flatpak/apps.txt: ${x.app} uses undeclared remote ${x.remote}";
  }) apps ++ map (k: {
    assertion = false;
    message = "flatpak/overrides.txt: ${k} has two values on ${wsHost} (mark one ${wsHost}=no)";
  }) duplicateKeys;

  xdg.dataFile = {
    "workstation/flatpak".source = flatpakConfig;
  } // lib.listToAttrs (map (f:
    lib.nameValuePair "applications/${baseNameOf f}" {
      source = "${flatpakConfig}/desktop/${baseNameOf f}";
    }) linkedDesktop);

  # The document portal after a relogin: systemd cannot kill the old
  # fusermount3 (setuid root), and with auto_unmount it unmounts
  # $XDG_RUNTIME_DIR/doc after the new portal has mounted it; every flatpak
  # then fails with "bwrap: Can't find source path .../doc/by-app/APP".
  # Wait for it (at most 10 s) before the start.
  xdg.configFile."systemd/user/xdg-document-portal.service.d/ws-wait-fusermount.conf".text = ''
    [Service]
    ExecStartPre=-${pkgs.writeShellScript "ws-doc-portal-wait" ''
      for _ in $(${pkgs.coreutils}/bin/seq 50); do
        ${pkgs.procps}/bin/pgrep -U "$(${pkgs.coreutils}/bin/id -u)" -f "fusermount3 .* -- $1\$" >/dev/null || exit 0
        ${pkgs.coreutils}/bin/sleep 0.2
      done
    ''} %t/doc
  '';

  # x-scheme-handler/claude comes from mimeinfo.cache next to the link.
  home.activation.flatpakDesktopDatabase = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
    if [ -x /usr/bin/update-desktop-database ]; then
      run /usr/bin/update-desktop-database "$HOME/.local/share/applications"
    fi
  '';
}
