# The GNOME Shell extensions of the workstation: the list is
# gnome/config.toml ([[extensions]], disabled_extensions; what the user
# edits, its comments say the sources). Here: the extensions that depend on
# the host, the checks, and what everything else reads: enabled-extensions
# (dconf, written by ws apply), the links of pinned EGO extensions, and
# ~/.local/share/wsconfig/gnome/extensions.json (order: every UUID in
# order; by_source: SOURCE: [UUID]; pins: UUID: VERSION; ws help plan-v2,
# 2.6) for ws gnome extensions, ws-gnome check, test and status, ws check
# repo and ws update extensions.
#
# Source nix: files delivered by a Home Manager module of a flake input
# (the wswidgets adapter, widgets/widgets.nix) on ws apply; only enabled
# here.
{ config, lib, pkgs, facts, wsHost, wsConfig, ... }:
let
  gnome = import ./config.nix { inherit lib wsHost wsConfig; };

  # Hibernation is set up where facts.kernelParams has resume= (ws help
  # suspend, Hibernate). systemd finds a swap file without it, so
  # CanHibernate alone would offer an untested hibernate elsewhere.
  hibernate = lib.any (lib.hasPrefix "resume=") facts.kernelParams;

  extensions = (gnome.extensions or [ ])
  # Hibernate in the power menu where logind allows it (ws help suspend).
  ++ lib.optional hibernate { uuid = "workstation-hibernate@local"; source = "local"; }
  # The panel adapter of the widget layer (ws help widgets): its files come
  # from the wswidgets module (source "nix"), here it is only enabled.
  ++ lib.optional facts.widgets
    { uuid = config.programs.wswidgets.extensionUuid; source = "nix"; };

  disabledUbuntu = gnome.disabled_extensions or [ ];

  bySource = source: map (e: e.uuid) (lib.filter (e: e.source == source) extensions);

  egoExtension = import ../nix/pkgs/gnome-extensions.nix {
    inherit lib;
    inherit (pkgs) stdenvNoCC fetchurl unzip;
  };
  pinned = map (e: egoExtension ({ inherit (e) uuid; } // e.pin))
    (lib.filter (e: e ? pin) extensions);
in
{
  assertions = [
    {
      assertion = lib.all (e: e.source == "ego") (lib.filter (e: e ? pin) extensions);
      message = "gnome/config.toml: pin is only for ego extensions";
    }
    {
      assertion = lib.all (e: lib.elem e.source [ "ubuntu" "ego" "local" "nix" ]) extensions;
      message = "gnome-extensions.nix: unknown source";
    }
    {
      assertion = lib.all (u: builtins.pathExists (./extensions + "/${u}/metadata.json"))
        (bySource "local");
      message = "gnome/config.toml: a local extension has no gnome/extensions/<uuid>/metadata.json";
    }
  ];

  home.file = lib.listToAttrs (map (ext:
    lib.nameValuePair ".local/share/gnome-shell/extensions/${ext.uuid}" {
      source = "${ext}/share/gnome-shell/extensions/${ext.uuid}";
      recursive = true;
    }) pinned);

  dconf.settings."org/gnome/shell" = {
    enabled-extensions = bySource "ego" ++ bySource "local" ++ bySource "nix";
    disabled-extensions = disabledUbuntu;
  };

  xdg.dataFile."wsconfig/gnome/extensions.json".text = builtins.toJSON {
    order = map (e: e.uuid) extensions;
    by_source = lib.genAttrs (lib.unique (map (e: e.source) extensions)) bySource;
    pins = lib.listToAttrs (map (e: lib.nameValuePair e.uuid (toString e.pin.version))
      (lib.filter (e: e ? pin) extensions));
  };
}
