# t2gmux, the gmux driver of KaiT2en (helpws plan-dgpu): powers the AMD dGPU
# of MacBookPro16,1 off and on the way macOS does (ACPI PWRD), replacing
# apple-gmux. `ws-gmux build` fetches modules/t2gmux at this commit and builds
# it for a kernel in podman.
#
# Newer commit: change it here, `ws switch`, `ws-gmux build`, `ws-gmux
# install`, test (helpws plan-dgpu).
#
# Built into ~/.local/share/workstation/t2gmux/source.json (repo, commit;
# helpws plan-v2, 2.6), read by ws-gmux.
{ ... }:
let
  repo = "kaiT2en/KaiT2en-Fedora";
  commit = "398dd080cb1f382b975b133ec42394649eb9cccc"; # 2026-10-01, t2gmux 0.8
in
{
  assertions = [{
    assertion = builtins.match "[0-9a-f]{40}" commit != null;
    message = "t2gmux.nix: the KaiT2en commit is not a full 40-character hash";
  }];

  xdg.dataFile."workstation/t2gmux/source.json".text = builtins.toJSON { inherit repo commit; };
}
