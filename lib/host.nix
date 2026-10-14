# The facts of a host for Nix (helpws plan-v2, stage 4):
# nix/hosts/HOST/host.toml with the sections [host], [platform], [layers]
# and, on a container host, [container]. Only Nix checks the values;
# lib/ws_facts.py reads the file without checking it.
# facts: the keys of host, platform and layers in one set, plus container
# when the file has it (the modules read facts.NAME).
{ lib }:
let
  string = { name = "a string"; ok = builtins.isString; };
  strings = { name = "a list of strings"; ok = v: builtins.isList v && lib.all builtins.isString v; };
  bool = { name = "true or false"; ok = builtins.isBool; };
  number = { name = "a number"; ok = v: builtins.isInt v || builtins.isFloat v; };

  # Section -> key -> type; required keys are listed in `required`.
  schema = {
    host = { hostname = string; user = string; wsconfig = string; };
    platform = {
      hardware = string;
      boot = string;
      kernelParams = strings;
      # Display scale of GNOME (lib/scale.nix), 1 without it.
      displayScale = number;
      # Set by the installer on a real machine; image-setup on a container.
      timezone = string;
      # Input devices xremap must not grab (keyboard/xremap.nix).
      xremapIgnore = strings;
      # rEFInd (system/boot/refind-grub-recovery.nix).
      refindDefaultParams = strings;
      rootUuid = string;
      refindEspPartuuid = string;
    };
    layers = { vm = bool; nativeSteam = bool; gameMode = bool; widgets = bool; };
    container = {
      server = string;
      image = string;
      port = { name = "a port number"; ok = v: builtins.isInt v && v > 0 && v < 65536; };
      mounts = strings;
      devices = strings;
    };
  };
  required = {
    host = [ "hostname" "user" "wsconfig" ];
    platform = [ "hardware" "boot" "kernelParams" ];
    layers = [ "vm" "nativeSteam" "gameMode" "widgets" ];
    container = [ "server" "image" "port" "mounts" "devices" ];
  };

  # Messages of everything wrong in DATA, [ ] when it is fine.
  problems = data:
    let
      sections = lib.attrNames data;
      unknownSections = map (s: "unknown section [${s}]")
        (lib.filter (s: !(schema ? ${s})) sections);
      inSection = s:
        let d = data.${s}; in
        if !builtins.isAttrs d then [ "${s} must be a section [${s}]" ]
        else
          map (k: "unknown key ${k} in [${s}]") (lib.filter (k: !(schema.${s} ? ${k})) (lib.attrNames d))
          ++ lib.concatMap (k: lib.optional (schema.${s} ? ${k} && !schema.${s}.${k}.ok d.${k})
               "${s}.${k} must be ${schema.${s}.${k}.name}") (lib.attrNames d)
          ++ map (k: "no ${k} in [${s}]") (lib.filter (k: !(d ? ${k})) required.${s});
      missing = map (s: "no section [${s}]")
        (lib.filter (s: !(data ? ${s})) [ "host" "platform" "layers" ]);
      flat = lib.foldl' (a: s: a // (if builtins.isAttrs (data.${s} or null) then data.${s} else { })) { }
        [ "host" "platform" "layers" ];
      container = flat.boot or null == "container";
      rules =
        # The Game Mode session runs the apt Steam: the flatpak cannot reach
        # the host helpers (steamos-session-select, steamosctl).
        lib.optional ((flat.gameMode or false) == true && (flat.nativeSteam or false) != true)
          "layers.gameMode = true needs layers.nativeSteam = true"
        ++ lib.optional (container && !(data ? container))
          "boot = \"container\" needs a section [container]"
        ++ lib.optional (!container && data ? container)
          "[container] only with boot = \"container\""
        ++ lib.optional (flat ? displayScale && number.ok flat.displayScale
                         && (flat.displayScale < 1 || flat.displayScale > 4))
          "platform.displayScale must be between 1 and 4";
    in
    unknownSections ++ missing
    ++ lib.concatMap inSection (lib.filter (s: schema ? ${s}) sections)
    ++ rules;
in
rec {
  inherit problems;

  # The facts of DATA (a parsed host.toml); WHERE names it in the error.
  factsIn = where: data:
    let p = problems data; in
    if p != [ ] then throw "${where}: ${lib.concatStringsSep "; " p} (helpws rebuild)"
    else data.host // data.platform // data.layers // lib.optionalAttrs (data ? container) {
      inherit (data) container;
    };

  # The facts of nix/hosts/HOST under HOSTS.
  factsOf = hosts: host:
    factsIn "nix/hosts/${host}/host.toml" (builtins.fromTOML (builtins.readFile (hosts + "/${host}/host.toml")));
}
