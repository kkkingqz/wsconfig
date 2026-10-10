# Distrobox containers and their exported applications. wsbox stays the owner
# of apply/check and reads what is built here from
# ~/.local/share/workstation/distrobox (one link to the store):
#
#   containers.ini  manifest for `distrobox assemble` (its own format)
#   exports.ini     [BOX] ALIAS=desktop file inside the container (wsbox)
#   boxes.ini       [BOX] home, gpu, and for Windows boxes profile, driver,
#                   dpi (wsbox, wswin)
#
# Change: edit this file, `ws switch`, then `wsbox apply NAME` (new container)
# or `wsbox recreate NAME` (changed image or packages; rootfs is replaced,
# the custom HOME stays).
#
# Images are tags, not digests: packages inside are updated in place by
# `wsbox update` (distrobox upgrade), a new image is used on recreate. A
# digest (repo@sha256:...) still works where a fixed image is needed; wsbox
# check then compares the repo digest.
{ config, lib, pkgs, facts, ... }:
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

  # The Ubuntu release of the host, substituted by wsbox from
  # /etc/os-release (VERSION_ID). For build containers: what they build must
  # match the host (kernel modules, binaries against the host glibc). After a
  # host release upgrade wsbox check reports image drift: wsbox recreate NAME.
  hostUbuntu = "docker.io/library/ubuntu:@HOST_VERSION_ID@";

  # The checkout as seen inside a container (the host HOME is mounted there).
  wsconfig = "${config.home.homeDirectory}/${facts.wsconfig}";

  # Hooks run as root on every container start (init_hooks at the end of
  # distrobox-init, pre_init_hooks before its package setup): each one
  # returns at once when its work is done.
  #
  # Before any Wine package on Arch: the host kernel provides ntsync, the
  # virtual provider keeps pacman/paru from pulling an Arch kernel.
  ntsyncHook = "${wsconfig}/distrobox/arch/wsbox-host-ntsync/install-hook";
  # Packages that need the provider (wine -> ntsync-autoload), so not
  # additional_packages: those are installed before the init hooks.
  pacmanHook = pkgs: "${wsconfig}/distrobox/arch/pacman-install-hook ${lib.concatStringsSep " " pkgs}";
  multilibHook = "${wsconfig}/distrobox/arch/multilib-hook";

  # Windows boxes (wswin, helpws history-windows):
  #   profile  wine: wine/winetricks; proton: umu-run
  #   driver   Wine graphics driver written into every new prefix
  #   dpi      LogPixels of a new prefix (192 = 200%)
  #   initOverrides  WINEDLLOVERRIDES for wineboot of a new prefix
  #   gpu      amd: DRI_PRIME to the AMD card when the boot has it (ws-gpu),
  #            Intel otherwise
  # A box for one program later: one more entry with the same profile.

  # In manifest order. HOME of every container: ~/distrobox/NAME (survives
  # recreate). The host HOME is mounted as well, at its own path: sources
  # such as ~/touchbar are reached as /home/<user>/touchbar.
  containers = [
    {
      name = "arch";
      # Arch is rolling: pacman -Syu inside (wsbox update). Recreate only
      # when needed; AUR packages are installed again by hand
      # (helpws rebuild).
      image = "docker.io/library/archlinux:latest";
      # base-devel: makepkg for the hook and for AUR (paru).
      packages = [ "base-devel" "git" ];
      # No Wine here since 2026-09-28 (WinBox moved to wine); the provider
      # stays so an AUR package that pulls wine does not pull a kernel.
      initHooks = [ ntsyncHook ];
    }
    {
      # Default Windows box: Wine from Arch with its native Wayland driver.
      name = "wine-wayland";
      image = "docker.io/library/archlinux:latest";
      # icoutils: icons of portable programs (wswin portable).
      packages = [ "base-devel" "git" "icoutils" "mesa" "vulkan-intel" "vulkan-radeon" ];
      initHooks = [ ntsyncHook (pacmanHook [ "wine" "wine-mono" "wine-gecko" "winetricks" ]) ];
      # LogPixels 96 x scale: the Wayland driver does not scale (144 at 1.5).
      windows = { profile = "wine"; driver = "wayland"; dpi = scale.dpi; };
    }
    {
      # Wine through XWayland (xwayland-native-scaling, so LogPixels 128 x
      # scale, 192 at 1.5):
      # programs the Wayland driver does not suit (none yet). WineHQ stable,
      # amd64 only (WoW64), from the hook.
      name = "wine";
      image = hostUbuntu;
      packages = [ "ca-certificates" "icoutils" "mesa-vulkan-drivers" ];
      initHooks = [
        "${wsconfig}/distrobox/wine/winehq-install-hook"
        # The Arch boxes have every locale (glibc-locales).
        "${wsconfig}/distrobox/wine/locale-hook ru_RU.UTF-8"
      ];
      # WineHQ has no Mono/Gecko packages: wineboot would ask to download
      # them; winetricks adds them to a prefix that needs them.
      windows = { profile = "wine"; driver = "x11"; dpi = scale.dpiX11; initOverrides = "mscoree,mshtml="; };
    }
    {
      # Games and heavy 3D: umu-launcher runs Proton (UMU-Proton by default)
      # in the Steam Runtime; both are downloaded into the container HOME.
      # multilib: umu-launcher and the 32-bit drivers for DXVK.
      name = "proton";
      image = "docker.io/library/archlinux:latest";
      packages = [
        "base-devel" "git" "icoutils" "mesa" "lib32-mesa" "vulkan-intel" "lib32-vulkan-intel"
        "vulkan-radeon" "lib32-vulkan-radeon" "vulkan-tools" "umu-launcher"
      ];
      preInitHooks = [ multilibHook ];
      initHooks = [ ntsyncHook ];
      gpu = "amd";
      # Proton draws through XWayland (xwayland-native-scaling): LogPixels
      # 96 x scale, as in wine-wayland.
      windows = { profile = "proton"; dpi = scale.dpi; };
    }
    {
      # Manual kernel/module builds; the t2bce modules themselves are built by
      # ws-suspend in a one-off container.
      name = "t2bce-build";
      image = hostUbuntu;
      packages = [ "build-essential" "bison" "flex" "kmod" "libelf-dev" "libssl-dev" ];
    }
    {
      # Touch Bar port (/home/<user>/touchbar). Rust: rustup in the
      # container HOME (~/distrobox/touchbar-build/.rustup, .cargo; PATH from
      # its .profile and fish conf.d), so it survives recreate.
      name = "touchbar-build";
      image = hostUbuntu;
      packages = [
        "build-essential" "git" "pkg-config" "libdrm-dev" "libegl-dev" "libgles-dev"
        "libinput-dev" "libsystemd-dev" "libudev-dev" "libwayland-dev" "ripgrep"
        "shellcheck" "systemd"
      ];
    }
  ];

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

  boxSection = c:
    let
      w = c.windows or { };
      kv = k: v: lib.optionalString (v != null) "${k}=${toString v}\n";
    in
    "[${c.name}]\n"
    + kv "home" "\${HOME}/distrobox/${c.name}"
    + kv "gpu" (c.gpu or null)
    + kv "profile" (w.profile or null)
    + kv "driver" (w.driver or null)
    + kv "dpi" (w.dpi or null)
    + kv "init_overrides" (w.initOverrides or null);

  exportSection = c: ''
    [${c.name}]
  '' + lib.concatStrings (lib.mapAttrsToList (alias: desktop: "${alias}=${desktop}\n")
    c.exports);

  distroboxConfig = pkgs.runCommandLocal "workstation-distrobox-config" { } ''
    mkdir -p $out
    cp ${pkgs.writeText "containers.ini"
      (lib.concatStringsSep "\n" (map containerSection containers))} $out/containers.ini
    cp ${pkgs.writeText "exports.ini"
      (lib.concatMapStrings exportSection (lib.filter (c: c ? exports) containers))} $out/exports.ini
    cp ${pkgs.writeText "boxes.ini"
      (lib.concatMapStringsSep "\n" boxSection containers)} $out/boxes.ini
  '';

  names = map (c: c.name) containers;
in
{
  assertions = [{
    assertion = lib.length names == lib.length (lib.unique names);
    message = "distrobox.nix: duplicate container name";
  }] ++ map (c: {
    assertion = lib.elem (c.windows.profile or "wine") [ "wine" "proton" ]
      && lib.elem (c.gpu or "amd") [ "amd" ];
    message = "distrobox.nix: ${c.name}: profile is wine or proton, gpu is amd";
  }) containers;

  xdg.dataFile."workstation/distrobox".source = distroboxConfig;
}
