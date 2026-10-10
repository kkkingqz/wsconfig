# Lenovo Legion Go (gen 1, 83E1; helpws plan-legion-go, 3.5 and 3.6): the
# settings Bazzite gives it, on Ubuntu. The power key's long press (scancode
# 0x67 -> F16) is in the hwdb of systemd 259 already. Still open, by the
# inventory on the device (stage 5): RGB of the sticks (3.7), the ICC
# profile, mt7921e ASPM.
{ file, ... }:
{
  files = [
    # sysctl: split lock, watchdogs, map count, reclaim, writeback, inotify
    (file "/etc/sysctl.d/60-ws-legion-go.conf" "system/files/sysctl.d/60-ws-legion-go.conf" "0644")
    # I/O schedulers: kyber for SSDs, bfq for microSD and disks
    (file "/etc/udev/rules.d/60-ws-io-schedulers.rules" "system/files/udev/60-ws-io-schedulers.rules" "0644")
    # nice down to -8 for Proton and Wine
    (file "/etc/security/limits.d/60-ws-nice.conf" "system/files/security/legion-go-nice.conf" "0644")
    (file "/etc/modprobe.d/ws-legion-go-blacklist.conf" "system/files/modprobe/legion-go-blacklist.conf" "0644")

    # Speakers: convolver of Bazzite (impulse multiwayCor48.wav from
    # ublue-os/bazzite 7f903b9, Apache-2.0, sha256 ebcf104a…138d) and the
    # WirePlumber rules of its 83E1 profile.
    (file "/usr/local/share/ws/legion-go/multiwayCor48.wav" "system/files/pipewire/legion-go/multiwayCor48.wav" "0644")
    (file "/etc/pipewire/pipewire.conf.d/60-ws-legion-go-speakers.conf" "system/files/pipewire/legion-go/60-ws-legion-go-speakers.conf" "0644")
    (file "/etc/wireplumber/wireplumber.conf.d/60-ws-legion-go.conf" "system/files/wireplumber/60-ws-legion-go.conf" "0644")
  ];
}
