# Sizes that follow the display scale of the host (host.toml
# platform.displayScale, 1.5 on mbp16): GNOME scales Wayland apps itself, these do not.
#   claude    --force-device-scale-factor of Claude: 2.25 in total
#   chatgpt   the same for ChatGPT: Chromium's factor multiplies the scale,
#             2 in total (1.5 × 4/3)
#   dpi       LogPixels of Wine on Wayland and of Proton: 96 per 1.0
#   dpiX11    LogPixels of Wine through XWayland (native scaling): 128 per 1.0
# On mbp16 they are the values set by hand before: 1.5, 1.333333, 144, 192.
{ lib, facts }:
let
  scale = 1.0 * (facts.displayScale or 1);
  # 1.500000 -> "1.5", 1.000000 -> "1": as written in a command line.
  number = x:
    let s = toString x; m = builtins.match "([0-9]+)\\.([0-9]*[1-9])?0*" s; in
    if m == null then s
    else lib.elemAt m 0 + lib.optionalString (lib.elemAt m 1 != null) ".${lib.elemAt m 1}";
  round = x: builtins.floor (x + 0.5);
in
assert lib.assertMsg (scale >= 1.0 && scale <= 4.0)
  "host.toml: displayScale must be between 1 and 4, not ${toString scale}";
{
  claude = number (2.25 / scale);
  chatgpt = number (2.0 / scale);
  dpi = round (96 * scale);
  dpiX11 = round (128 * scale);
}
