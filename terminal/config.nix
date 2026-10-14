# terminal/config.toml with the host file hosts/HOST/terminal.toml,
# read and checked once for distrobox-colors.nix and ssh-colors.nix;
# lib/config.nix.
{ lib, wsHost, wsConfig }:
let
  schema = import ../lib/schema.nix { inherit lib; };
  color = schema.scalar "a color \"#RRGGBB\""
    (v: builtins.isString v && builtins.match "#[0-9A-Fa-f]{6}" v != null);
in
(import ../lib/config.nix { inherit lib; }).read {
  file = wsConfig + "/terminal/config.toml";
  host = wsConfig + "/hosts/${wsHost}/terminal.toml";
  type = schema.table {
    keys = {
      distrobox = schema.table {
        keys = { default = color; boxes = schema.attrsOf color; };
        required = [ "default" ];
      };
      ssh = schema.table {
        keys = {
          default = color;
          hosts = schema.listOf (schema.table {
            keys = { names = schema.strings; inherit color; };
            required = [ "names" "color" ];
          });
        };
        required = [ "default" ];
      };
    };
    required = [ "distrobox" "ssh" ];
  };
}
