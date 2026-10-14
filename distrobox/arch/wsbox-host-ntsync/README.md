# wsbox-host-ntsync

`wsbox-host-ntsync` is a deliberately empty Arch package for the `arch`
Distrobox managed by this workstation configuration.

The Distrobox container uses the host kernel. The real NTSync kernel module
is therefore loaded on the Ubuntu host, and `/dev/ntsync` is passed through
to the container.

Arch Linux package `ntsync-autoload` depends on the virtual capability
`NTSYNC-MODULE`. Without this provider, pacman/paru may satisfy that
capability by installing an Arch kernel package inside the container,
together with `mkinitcpio` and initramfs files that are not used by Distrobox.

This package provides only the virtual capability:

    NTSYNC-MODULE

It does not contain a kernel module and must only be installed when the host
kernel actually provides NTSync and `/dev/ntsync` is available to the
container.

Installed automatically: `install-hook` is the init hook of the `arch`
container in `distrobox/distrobox.nix`; distrobox runs it as root at the end
of container setup (and at every start, where it does nothing once the
package is installed). It builds the package as the owner of the checkout
(makepkg refuses root) and installs it with pacman.

Recovery order:

1. Load `ntsync` on the host (`ws system apply`: modules-load.d/ntsync.conf).
2. `ws box apply arch` or `ws box recreate arch` (the hook installs this package).
3. Install Wine / WinBox (paru).
4. Run `ws box apply arch` to restore managed application exports.
