# gnome/config.toml with the host file hosts/HOST/gnome.toml, read and
# checked once for gnome.nix (settings) and gnome-extensions.nix
# (extensions, disabled_extensions); lib/config.nix.
{ lib, wsHost, wsConfig }:
let
  schema = import ../lib/schema.nix { inherit lib; };
  dconfValue = schema.scalar "a text, number, true/false or a list of texts"
    (v: builtins.isString v || builtins.isInt v || builtins.isFloat v || builtins.isBool v
      || (builtins.isList v && lib.all builtins.isString v));
  extension = schema.table {
    keys = {
      uuid = schema.string;
      source = schema.oneOf [ "ubuntu" "ego" "local" ];
      pin = schema.table { keys = { version = schema.int; hash = schema.string; }; required = [ "version" "hash" ]; };
    };
    required = [ "uuid" "source" ];
  };
in
(import ../lib/config.nix { inherit lib; }).read {
  file = wsConfig + "/gnome/config.toml";
  host = wsConfig + "/hosts/${wsHost}/gnome.toml";
  type = schema.table {
    keys = {
      settings = schema.attrsOf (schema.attrsOf dconfValue);
      extensions = schema.listOf extension;
      disabled_extensions = schema.strings;
    };
  };
}
