#!/bin/bash
# VERSION_<source> come from /src/versions.env (gaming/sources.nix).
# shellcheck disable=SC2154
# Builds the Game Mode packages (wsgame build; helpws gaming) in a clean
# Ubuntu container of the host release. /src: the sources wsgame fetched
# (sha256 checked) and versions.env; /out: the .debs; /cargo: the crate
# cache between builds. Runs as root of a rootless podman container: the
# files land owned by the user.
#
#   steamos-manager         built (Rust); platform.toml [session] for GNOME on
#                           Ubuntu and OGC's gamescope session, the Legion Go
#                           device file without TDP limit and performance
#                           profile (power-profiles-daemon owns
#                           platform_profile); system and user services on
#   powerbuttond            built (C) with Terra's debounce after resume; the
#                           user service starts with the Steam session
#   gamescope-session-plus  OGC scripts as they are
#   gamescope-session-steam
#   extest                  libextest.so (i386) in /usr/lib/extest
#   inputplumber            the upstream .deb, copied
set -euo pipefail

# Written by wsgame build.
# shellcheck source=/dev/null
. /src/versions.env
export DEBIAN_FRONTEND=noninteractive

echo "== Build tools"
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    ca-certificates build-essential pkg-config dpkg-dev patch \
    cargo rustc clang libclang-dev libudev-dev libglib2.0-dev libspeechd-dev \
    libevdev-dev >/dev/null

work=/build
rm -rf "$work"
mkdir -p "$work/stage" /out
rm -f /out/*.deb

# Shared-library Depends of ELF files in a staged tree.
shlibs() {
    local tmp f
    local -a args=()
    tmp="$(mktemp -d)"
    mkdir "$tmp/debian"
    printf 'Source: ws\n\nPackage: ws\nArchitecture: any\n' > "$tmp/debian/control"
    for f in "$@"; do
        args+=("-e$f")
    done
    (cd "$tmp" && dpkg-shlibdeps -O "${args[@]}" 2>/dev/null) | sed -n 's/^shlibs:Depends=//p'
    rm -rf "$tmp"
}

# NAME VERSION ARCH DEPENDS DESCRIPTION: control file and .deb of the staged
# tree $work/stage/NAME; maintainer scripts already in its DEBIAN/.
deb() {
    local name="$1" version="$2" arch="$3" depends="$4" description="$5"
    local stage="$work/stage/$name"
    mkdir -p "$stage/DEBIAN"
    {
        echo "Package: $name"
        echo "Version: $version"
        echo "Architecture: $arch"
        echo "Maintainer: wsconfig <noreply@users.noreply.github.com>"
        echo "Installed-Size: $(du -sk --exclude=DEBIAN "$stage" | cut -f1)"
        [[ -z "$depends" ]] || echo "Depends: $depends"
        echo "Section: games"
        echo "Priority: optional"
        echo "Description: $description"
        echo " Built by wsconfig (gaming/build.sh, helpws gaming)."
    } > "$stage/DEBIAN/control"
    dpkg-deb --root-owner-group --build "$stage" "/out/${name}_${version}_${arch}.deb" >/dev/null
    echo "built: ${name}_${version}_${arch}.deb"
}

# Unpacks a source archive into its own directory, prints the top directory.
unpack() {
    local dir="$work/src/$1"
    mkdir -p "$dir"
    tar -xzf "/src/$1.tar.gz" -C "$dir"
    find "$dir" -mindepth 1 -maxdepth 1 -type d | head -n1
}

echo
echo "== steamos-manager $VERSION_steamos_manager"
src="$(unpack steamos-manager)"
stage="$work/stage/steamos-manager"
# install runs cargo again: the same CARGO_HOME, so it finds the build done.
(cd "$src" && export CARGO_HOME=/cargo && make build && make install DESTDIR="$stage")
# The sessions of this system: GNOME on Ubuntu, OGC's Steam session.
cat >> "$stage/usr/share/steamos-manager/platform.toml" <<'EOF'

# wsconfig (gaming/build.sh): GNOME on Ubuntu, OGC's Steam session.
[session]
gamescope_session_service = "gamescope-session-plus@steam.service"
gamescope_session_desktop = "gamescope-session-steam.desktop"
desktop = "ubuntu.desktop"
EOF
# Legion Go: no TDP slider and no performance profile in Steam, so
# power-profiles-daemon stays the only owner of platform_profile.
devices="$stage/usr/share/steamos-manager/devices/legion-go-series.toml"
sed -i '/^\[performance_profile\]/,$d' "$devices"
! grep -q 'tdp_limit\|performance_profile' "$devices" || { echo "TDP still in $devices" >&2; exit 1; }
mkdir -p "$stage/DEBIAN"
cat > "$stage/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
    systemctl daemon-reload || true
    systemctl enable steamos-manager.service || true
    systemctl --global enable steamos-manager.service steamos-manager-session-cleanup.service || true
    systemctl reload dbus.service || true
fi
EOF
cat > "$stage/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = remove ]; then
    systemctl --global disable steamos-manager.service steamos-manager-session-cleanup.service || true
    systemctl disable --now steamos-manager.service || true
fi
EOF
chmod 0755 "$stage/DEBIAN/postinst" "$stage/DEBIAN/prerm"
deb steamos-manager "$VERSION_steamos_manager" amd64 \
    "$(shlibs "$stage/usr/lib/steamos-manager" "$stage/usr/bin/steamosctl"), dbus, systemd" \
    "SteamOS Manager: DBus between Steam and the OS (OGC)"

echo
echo "== powerbuttond $VERSION_powerbuttond"
src="$(unpack powerbuttond)"
stage="$work/stage/powerbuttond"
# Its Makefile links the libraries before the object: with Ubuntu's
# --as-needed they would be dropped, so the link comes after it here.
# shellcheck disable=SC2046 # the linker flags of pkg-config are words
(cd "$src" && patch -p1 < /src/powerbuttond-debounce.patch && make powerbuttond.o \
    && cc -O2 powerbuttond.o -o steamos-powerbuttond $(pkg-config --libs libevdev libudev) \
    && make install DESTDIR="$stage")
# Started by the Steam session (gamescope-session-plus@steam), not by
# SteamOS's gamescope-session.service.
sed -i '/^Requisite=gamescope-session.service$/d' "$stage/usr/lib/systemd/user/steamos-powerbuttond.service"
rm -r "$stage/usr/lib/systemd/user/gamescope-session.service.wants"
install -d "$stage/usr/lib/systemd/user/gamescope-session-plus@steam.service.wants"
ln -s ../steamos-powerbuttond.service "$stage/usr/lib/systemd/user/gamescope-session-plus@steam.service.wants/"
mkdir -p "$stage/DEBIAN"
cat > "$stage/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
    systemd-hwdb update || true
    udevadm control --reload-rules || true
    udevadm trigger --subsystem-match=input --action=change || true
fi
EOF
chmod 0755 "$stage/DEBIAN/postinst"
deb powerbuttond "$VERSION_powerbuttond" amd64 \
    "$(shlibs "$stage/usr/lib/hwsupport/steamos-powerbuttond"), systemd" \
    "Power button daemon of SteamOS for the Game Mode session"

for name in gamescope-session-plus gamescope-session-steam; do
    echo
    version="VERSION_${name//-/_}"
    echo "== $name ${!version}"
    src="$(unpack "$name")"
    stage="$work/stage/$name"
    mkdir -p "$stage"
    cp -a "$src/usr" "$stage/"
    find "$stage/usr/bin" "$stage/usr/share/gamescope-session-plus" -type f \
        \( -path '*/usr/bin/*' -o -name gamescope-session-plus \) -exec chmod 0755 {} +
done
deb gamescope-session-plus "$VERSION_gamescope_session_plus" all \
    "gamescope, bash, systemd, dbus-bin" \
    "Gamescope session scripts and gamescope-session-plus@.service (OGC)"
deb gamescope-session-steam "$VERSION_gamescope_session_steam" all \
    "gamescope-session-plus, steam-installer" \
    "Steam Big Picture session for gamescope-session-plus (OGC)"

echo
echo "== extest $VERSION_extest"
stage="$work/stage/extest"
install -D -m0644 /src/extest.so "$stage/usr/lib/extest/libextest.so"
deb extest "$VERSION_extest" i386 "libc6, libgcc-s1" \
    "Steam Input on Wayland desktops (XTest for the Steam client, LD_PRELOAD)"

echo
echo "== inputplumber $VERSION_inputplumber"
cp /src/inputplumber.deb "/out/inputplumber_${VERSION_inputplumber}_amd64.deb"
echo "copied: inputplumber_${VERSION_inputplumber}_amd64.deb"
