# Patched t2bce modules (helpws suspend): for every kernel release the
# linux-t2-patches commit whose 1001-Add-t2bce-driver-stack.patch produced
# its in-tree t2bce. `ws-suspend t2bce-build` fetches that patch, applies
# nostate-fix.patch and builds the modules for the kernel.
#
# New kernel: add its release and commit here, `ws apply`, then
# `ws-suspend t2bce-build KERNEL` (helpws suspend).
#
# Built into ~/.local/share/wsconfig/t2bce/sources.json (KERNEL: COMMIT;
# helpws plan-v2, 2.6), read by ws-suspend, ws-psr and ws-workstation-verify.
{ lib, ... }:
let
  sources = {
    "7.2.7-1-t2-resolute" = "9e773c8876708924dd5e0e5d3093068a0f806ea1";
  };
in
{
  assertions = [{
    assertion = lib.all (c: builtins.match "[0-9a-f]{40}" c != null) (lib.attrValues sources);
    message = "t2bce.nix: a linux-t2-patches commit is not a full 40-character hash";
  }];

  xdg.dataFile."wsconfig/t2bce/sources.json".text = builtins.toJSON sources;
}
