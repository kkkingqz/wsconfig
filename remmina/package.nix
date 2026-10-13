# Remmina of nixpkgs (helpws remmina) with
#   mr2776.diff  !2776: clipboard leaks (merged upstream after 1.4.43;
#                !2777 builds on it)
#   mr2777.diff  !2777: files through the RDP clipboard, both directions
#                (open merge request, state of 2026-10-12)
#   reuse-file-context.diff  ours: one clipboard file context per
#                connection; the channel opens again after an RDS redirection
# FreeRDP of nixpkgs has H.264 (GFX AVC420/AVC444); the one of Ubuntu does
# not, Remmina from apt gets RemoteFX only.
{ lib, remmina }:
# A new Remmina in nixpkgs: check the merge requests (merged? the diffs
# still apply?) before raising this.
assert lib.assertMsg (remmina.version == "1.4.43")
  "remmina/package.nix: nixpkgs has Remmina ${remmina.version}, the patches are for 1.4.43 (helpws remmina)";
remmina.overrideAttrs (o: {
  pname = "remmina-ws";
  patches = (o.patches or [ ]) ++ [
    ./patches/mr2776.diff
    ./patches/mr2777.diff
    ./patches/reuse-file-context.diff
  ];
})
