# The one list of GNOME Shell extensions of the workstation. Everything else
# reads it: enabled-extensions (dconf, written by ws switch), the links of
# pinned EGO extensions, and ~/.local/share/workstation/gnome/extensions
# ("UUID SOURCE [PINNED-VERSION]" per line) for
# ws-keyboard-install-extensions, ws-workstation-verify, ws-gnome-test and
# ws-gnome-status.
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
#           compiled) by ws-keyboard-install-extensions (ws apply extensions)
#
# enabled-extensions is written on every ws switch: an extension enabled or
# disabled by hand (Extension Manager, gnome-extensions) is reset by the next
# switch; add or remove it here instead. New extensions load after
# logout/login on Wayland.
{ config, lib, pkgs, ... }:
let
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
    # Hibernate in the power menu where logind allows it (helpws suspend).
    { uuid = "workstation-hibernate@local"; source = "local"; }
    { uuid = "workstation-widgets@local"; source = "local"; }
  ];

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
      assertion = lib.all (e: lib.elem e.source [ "ubuntu" "ego" "local" ]) extensions;
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
    enabled-extensions = bySource "ego" ++ bySource "local";
    disabled-extensions = disabledUbuntu;
  };

  xdg.dataFile."workstation/gnome/extensions".text = ''
    # Built from gnome/gnome-extensions.nix: UUID SOURCE [PINNED-VERSION]
  '' + lib.concatMapStrings (e:
    "${e.uuid} ${e.source}${lib.optionalString (e ? pin) " ${toString e.pin.version}"}\n")
    extensions;
}
