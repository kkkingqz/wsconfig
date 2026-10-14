# keyboard/config.toml with the host file nix/hosts/HOST/keyboard.toml,
# read and checked once for keyboard.nix (shortcuts, layouts) and
# xremap.nix (the preset's xremap.yml); lib/config.nix. presets: the
# presets of the core, NAME -> its .nix (keyboard/presets/NAME.nix) and
# keyboard/presets/NAME-xremap.yml.
{ lib, wsHost, wsConfig }:
let
  schema = import ../lib/schema.nix { inherit lib; };
  shortcutValue = schema.scalar "a list of texts, a text or true/false"
    (v: builtins.isString v || builtins.isBool v || (builtins.isList v && lib.all builtins.isString v));
  presets = { macos = ./presets/macos.nix; };
in
{
  inherit presets;
  data = (import ../lib/config.nix { inherit lib; }).read {
    file = wsConfig + "/keyboard/config.toml";
    host = wsConfig + "/nix/hosts/${wsHost}/keyboard.toml";
    type = schema.table {
      keys = {
        preset = schema.oneOf (lib.attrNames presets);
        layouts = schema.strings;
        shortcuts = schema.attrsOf (schema.attrsOf shortcutValue);
        tiling = schema.attrsOf schema.strings;
      };
      required = [ "preset" "layouts" ];
    };
  };
}
