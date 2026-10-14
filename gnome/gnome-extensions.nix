# The one list of GNOME Shell extensions of the workstation. Everything else
# reads it: enabled-extensions (dconf, written by ws switch), the links of
# pinned EGO extensions, and ~/.local/share/workstation/gnome/extensions.json
# (order: every UUID in order; by_source: SOURCE: [UUID]; pins: UUID:
# VERSION; helpws plan-v2, 2.6) for ws gnome extensions,
# ws-gnome check, test and status, ws check repo and ws update extensions.
#
# source:
#   ubuntu  gnome-shell-ubuntu-extensions (apt); enabled by the Ubuntu session
#           mode (/usr/share/gnome-shell/modes/ubuntu.json), not written here
#   ego     extensions.gnome.org. Without pin: `ws apply extensions` installs
#           the latest version for the running GNOME Shell if it is missing,
#           Extension Manager updates it (`ws update extensions` asks GNOME
#           Shell for updates the same way). With
#           pin = { version = N; hash = "sha256-..."; } (N: the number in the
#           EGO download URL): built by nix/pkgs/gnome-extensions.nix and linked
#           file by file by ws switch; not updated
#   local   gnome/extensions/<uuid> in this repository, copied (schemas
#           compiled) by ws gnome extensions (ws apply extensions)
#   nix     files delivered by a Home Manager module of a flake input (the
#           wswidgets adapter, widgets/widgets.nix) on ws switch; only
#           enabled here
#
# enabled-extensions is written on every ws switch: an extension enabled or
# disabled by hand (Extension Manager, gnome-extensions) is reset by the next
# switch; add or remove it here instead. New extensions load after
# logout/login on Wayland.
{ config, lib, pkgs, facts, ... }:
let
  # Hibernation is set up where facts.kernelParams has resume= (helpws
  # suspend, Hibernate). systemd finds a swap file without it, so
  # CanHibernate alone would offer an untested hibernate elsewhere.
  hibernate = lib.any (lib.hasPrefix "resume=") facts.kernelParams;

  extensions = [
    { uuid = "ubuntu-dock@ubuntu.com"; source = "ubuntu"; }
    { uuid = "ubuntu-appindicators@ubuntu.com"; source = "ubuntu"; }
    { uuid = "ding@rastersoft.com"; source = "ubuntu"; }
    { uuid = "tiling-assistant@ubuntu.com"; source = "ubuntu"; }
    { uuid = "web-search-provider@ubuntu.com"; source = "ubuntu"; }

    # Used; enabled since before the repository.
    { uuid = "window-monitor-pro@muhammed.hussien2030.gmail.com"; source = "ego"; }
    # WM_CLASS bridge for xremap application filters (ws-xremap waits for it).
    { uuid = "xremap@k0kubun.com"; source = "ego"; }
    # D-Bus window control for ws-window (helpws keyboard).
    { uuid = "window-control@carlo9890.github.io"; source = "ego"; }

    { uuid = "workstation-smart-popup@local"; source = "local"; }
    { uuid = "workstation-input-source@local"; source = "local"; }
    { uuid = "workstation-dock-spring@local"; source = "local"; }
  ]
  # Hibernate in the power menu where logind allows it (helpws suspend).
  ++ lib.optional hibernate { uuid = "workstation-hibernate@local"; source = "local"; }
  # The panel adapter of the widget layer (helpws widgets): its files come
  # from the wswidgets module (source "nix"), here it is only enabled.
  ++ lib.optional (facts.widgets == "yes")
    { uuid = config.programs.wswidgets.extensionUuid; source = "nix"; };

  # Extensions of the Ubuntu session mode that stay off: the mode enables
  # them whatever enabled-extensions says, only disabled-extensions wins.
  # snapd is purged (nix/hosts/apt.txt), so its prompt and Snap Store search
  # have nothing to talk to.
  disabledUbuntu = [
    "snapd-prompting@canonical.com"
    "snapd-search-provider@canonical.com"
  ];

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
      message = "gnome-extensions.nix: pin is only for ego extensions";
    }
    {
      assertion = lib.all (e: lib.elem e.source [ "ubuntu" "ego" "local" "nix" ]) extensions;
      message = "gnome-extensions.nix: unknown source";
    }
    {
      assertion = lib.all (u: builtins.pathExists (./extensions + "/${u}/metadata.json"))
        (bySource "local");
      message = "gnome-extensions.nix: a local extension has no gnome/extensions/<uuid>/metadata.json";
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

  xdg.dataFile."workstation/gnome/extensions.json".text = builtins.toJSON {
    order = map (e: e.uuid) extensions;
    by_source = lib.genAttrs (lib.unique (map (e: e.source) extensions)) bySource;
    pins = lib.listToAttrs (map (e: lib.nameValuePair e.uuid (toString e.pin.version))
      (lib.filter (e: e ? pin) extensions));
  };
}
