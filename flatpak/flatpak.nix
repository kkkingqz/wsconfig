# Flatpak declarations: the catalog flatpak/catalog.toml (remotes, apps,
# overrides; lib/flatpak_catalog.py), the choice of this host
# nix/hosts/HOST/flatpak.toml (yes, no and own overrides; lib/catalog.nix)
# and desktop overrides. wsflatpak stays the owner of apply/check and reads
# what is built here from ~/.local/share/wsconfig/flatpak (one link to
# the store):
#
#   flatpak.json      remotes (NAME: URL), apps (REMOTE APP of the catalog,
#                     in order, every host), overrides (APP: filesystems,
#                     environment, session_bus) of this host (ws help
#                     plan-v2, 2.6)
#   desktop/APP.desktop
#
# Change: the catalog and the choice through wsflatpak (install, manage,
# filesystem, env, talk, ...), the rest here; then `ws apply`,
# `wsflatpak apply` (or `ws apply`).
# apply resets the overrides of every managed app before setting the declared
# ones, so a key removed here disappears too. Desktop overrides are linked
# into ~/.local/share/applications by home-manager, on a host that has the
# app (elsewhere the launcher would start nothing).
{ lib, pkgs, wsHost, wsConfig, facts, core, ... }:
let
  catalog = import ../lib/catalog.nix { inherit lib; hosts = wsConfig + "/nix/hosts"; };
  # @claude@, @chatgpt@ in the desktop files: the scale factors of the host;
  # @ws-gpu@: ws-gpu of the core in the store.
  scale = import ../lib/scale.nix { inherit lib facts; };
  fill = f: pkgs.writeText (baseNameOf f) (builtins.replaceStrings
    [ "@claude@" "@chatgpt@" "@ws-gpu@" ] [ scale.claude scale.chatgpt "${core}/libexec/ws-gpu" ]
    (builtins.readFile f));

  flatpak = builtins.fromTOML (builtins.readFile (wsConfig + "/flatpak/catalog.toml"));
  inherit (flatpak) remotes;
  apps = flatpak.apps or [ ];
  host = catalog.choice wsHost "flatpak";
  hostOverrides = host.overrides or { };
  stateOf = app: catalog.stateIn host app (lib.findFirst (a: a.id == app) { } apps).default or "ask";

  # The values of each app on this host (catalog, then its own section):
  # the keys `wsflatpak apply` sets with `flatpak override`:
  # Context.filesystems, Environment, "Session Bus Policy" (talk only).
  valuesOf = a: catalog.overridesOf a (hostOverrides.${a.id} or { });
  duplicateKeys = lib.concatMap (a:
    let keys = map (x: catalog.itemKey x) (valuesOf a); in
    map (k: "${a.id} ${k}") (lib.filter (k: lib.count (x: x == k) keys > 1) (lib.unique keys))
  ) apps;

  overrides = lib.listToAttrs (lib.concatMap (a:
    let
      values = valuesOf a;
      of = kind: map (x: x.value) (lib.filter (x: x.kind == kind) values);
      env = lib.listToAttrs (map (v:
        let kv = builtins.match "([^=]+)=(.*)" v; in
        lib.nameValuePair (lib.elemAt kv 0) (lib.elemAt kv 1)) (of "env"));
    in
    lib.optional (values != [ ]) (lib.nameValuePair a.id {
      filesystems = of "filesystem";
      environment = env;
      session_bus = lib.genAttrs (of "talk") (_: "talk");
    })
  ) apps);

  # Full files, ours: Claude on Wayland at the factor of lib/scale.nix with its
  # URL handler; ChatGPT likewise;
  # Steam through ws-gpu (the AMD dGPU when the boot has it, Intel otherwise),
  # steam:// included, with -console.
  desktop = [
    ./desktop/com.anthropic.ClaudeDesktop.desktop
    ./desktop/com.valvesoftware.Steam.desktop
    ./desktop/io.github.rulin132.ChatGPT.desktop
  ];
  # Linked: those of the apps this host has (APP.desktop, state yes).
  linkedDesktop = lib.filter (f: stateOf (lib.removeSuffix ".desktop" (baseNameOf f)) == "yes") desktop;

  manifest = builtins.toJSON {
    inherit remotes overrides;
    apps = map (a: { inherit (a) remote; app = a.id; }) apps;
  };

  flatpakConfig = pkgs.runCommandLocal "workstation-flatpak-config" { } (''
    mkdir -p $out/desktop
    cp ${pkgs.writeText "flatpak.json" manifest} $out/flatpak.json
  '' + lib.concatMapStrings (f: ''
    cp ${fill f} $out/desktop/${baseNameOf f}
  '') desktop);
in
{
  assertions = map (a: {
    assertion = remotes ? ${a.remote};
    message = "flatpak/catalog.toml: ${a.id} uses undeclared remote ${a.remote}";
  }) apps ++ map (k: {
    assertion = false;
    message = "flatpak: ${k} has two values on ${wsHost} (catalog.toml and nix/hosts/${wsHost}/flatpak.toml)";
  }) duplicateKeys ++ map (app: {
    assertion = lib.any (a: a.id == app) apps;
    message = "nix/hosts/${wsHost}/flatpak.toml: overrides of ${app}, not in flatpak/catalog.toml";
  }) (lib.attrNames hostOverrides);

  xdg.dataFile = {
    "wsconfig/flatpak".source = flatpakConfig;
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
