# Sources of the Game Mode packages (helpws gaming, helpws plan-legion-go
# 3.4): what wsgame fetches, checks by sha256, builds and installs. Built
# into ~/.local/share/wsconfig/gaming/sources.json on every host: the
# packages can be built on any machine with podman (wsgame build), they are
# installed only where gameMode = "yes" (wsgame install).
#
#   url      downloaded once into ~/.local/share/wsconfig/gaming/src
#   sha256   of that file; a mismatch stops wsgame
#   version  Debian version of the package wsgame makes (or installs)
#   build    steamos-manager, powerbuttond: built by gaming/build.sh in an
#            Ubuntu container of the host release; the others are packed
#            as they are (deb: installed as published)
#
# New version: url, sha256, version here, `ws switch`, `wsgame build`,
# `wsgame install`. mangoapp comes from Ubuntu (gaming/apt.txt).
{ lib, ... }:
let
  sources = {
    # DBus between Steam and the OS: session switch (SDDM files),
    # InputPlumber targets. OGC fork, dev branch as in Bazzite.
    steamos-manager = {
      url = "https://github.com/OpenGamingCollective/steamos-manager/archive/9b62985123eab1ca47bc7042e350475329e327b2.tar.gz";
      sha256 = "f42c098ea9423d3f0323819e5aabb2cf3fdd260bbcaeb8f5e9099e13e4f4351b";
      version = "26.4.1+git20261008.9b62985-1ws1";
      build = true;
    };
    # Power key in Game Mode (Valve, holo), with Terra's debounce after
    # resume (sleep loop on handhelds, 2026-09-25).
    powerbuttond = {
      url = "https://gitlab.steamos.cloud/holo/powerbuttond/-/archive/v4.2/powerbuttond-v4.2.tar.gz";
      sha256 = "26dd54000dd267114b00fae4db14250244fe75f198adf420459ecf050b5be29d";
      version = "4.2-1ws1";
      build = true;
    };
    powerbuttond-debounce = {
      url = "https://raw.githubusercontent.com/terrapkg/packages/06b75e418ce68bb03be8057cdacc36bae734a124/anda/games/powerbuttond/0001-wake-debounce-and-throttle.patch";
      sha256 = "da50edc106b82ff3adfb96c29b11648510a382015e3d879c3cf237935642160b";
      version = "";
    };
    # Session scripts (gamescope-session-plus@.service, device quirks: 83E1
    # left, 60/144 Hz) and the Steam client session of OGC.
    gamescope-session-plus = {
      url = "https://github.com/OpenGamingCollective/gamescope-session/archive/08e65a62ed3d7acc6ae17db637091d402a55ae2a.tar.gz";
      sha256 = "73b266e6dd01d1aabb60f0c6ff63e00b559112785240c6a43d244ea41496ad49";
      version = "0~git20261002.08e65a6-1ws1";
    };
    gamescope-session-steam = {
      url = "https://github.com/OpenGamingCollective/gamescope-session-steam/archive/82c45fc112775e3fa927d5c326c39b21f1761cc1.tar.gz";
      sha256 = "5129c0269158dc7714ea90ba6f525d30c32c668e5fb7741e1e02da9ed7c53b46";
      version = "0~git20260919.82c45fc-1ws1";
    };
    # Controllers: virtual Steam Deck controller (deck-uhid); upstream .deb.
    # Not 0.82.0 (2026-10-10) yet: on 83E1 it takes accel_3d for the
    # controller IMU and its udev rule hides the accelerometer from
    # iio-sensor-proxy, so GNOME loses auto-rotation. Upgrade after stage 6
    # of helpws plan-legion-go, checking rotation, gyro and buttons.
    inputplumber = {
      url = "https://github.com/ShadowBlip/InputPlumber/releases/download/v0.81.0/inputplumber_0.81.0-1_amd64.deb";
      sha256 = "6433ceb6aca8c3dfbaae94e914cc9fa4936c1ed299d0954510c699f510247c57";
      version = "0.81.0-1";
      deb = true;
    };
    # Steam Input on the Wayland desktop (LD_PRELOAD into the 32-bit client).
    extest = {
      url = "https://github.com/ublue-os/extest/releases/download/1.0.4/libextest.so";
      sha256 = "99211f1efb265ad15d07fcabd334f97f6f146f66d73597410db5509d0c91d885";
      version = "1.0.4-1ws1";
    };
  };
in
{
  assertions = lib.mapAttrsToList (name: s: {
    assertion = builtins.match "[0-9a-f]{64}" s.sha256 != null && lib.hasPrefix "https://" s.url;
    message = "gaming/sources.nix: ${name} needs an https url and a full sha256";
  }) sources;

  xdg.dataFile."wsconfig/gaming/sources.json".text = builtins.toJSON sources;
}
