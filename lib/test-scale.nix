# lib/scale.nix: mbp16 keeps its hand-made values (nix flake check, scale).
{ lib }:
let
  at = s: import ./scale.nix { inherit lib; facts = { displayScale = s; }; };
in
assert at 1.5 == { claude = "1.5"; chatgpt = "1.333333"; dpi = 144; dpiX11 = 192; };
assert at 2 == { claude = "1.125"; chatgpt = "1"; dpi = 192; dpiX11 = 256; };
assert (import ./scale.nix { inherit lib; facts = { }; }).dpi == 96;
true
