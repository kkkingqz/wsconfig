# lib/scale.nix: mbp16 keeps its hand-made values (nix flake check, scale).
{ lib }:
let
  at = s: import ./scale.nix { inherit lib; facts = { displayScale = s; }; };
in
assert at 1.5 == { claude = "1.5"; chatgpt = "1.333333"; dpi = 144; dpiX11 = 192; };
assert at 2 == { claude = "1.125"; chatgpt = "1"; dpi = 192; dpiX11 = 256; };
assert (import ./scale.nix { inherit lib; facts = { }; }).dpi == 96;
# A container host: the RDP client scales, Claude and ChatGPT do not.
assert import ./scale.nix { inherit lib; facts = { boot = "container"; displayScale = 1; }; }
  == { claude = "1"; chatgpt = "1"; dpi = 96; dpiX11 = 128; };
true
