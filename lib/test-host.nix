# lib/host.nix checks host.toml (nix flake check, host).
{ lib }:
let
  host = import ./host.nix { inherit lib; };
  ok = {
    host = { hostname = "h"; user = "u"; wsconfig = "wsconfig"; };
    platform = { hardware = "generic-pc"; boot = "grub"; kernelParams = [ "quiet" ]; displayScale = 1.5; };
    layers = { vm = true; nativeSteam = false; gameMode = false; widgets = true; };
  };
  with' = section: attrs: ok // { ${section} = ok.${section} // attrs; };
  container = {
    server = "root@s"; image = "local/x"; port = 3390; mounts = [ "/a:~" ]; devices = [ ];
  };
  fails = data: !(builtins.tryEval (host.factsIn "t" data)).success;
in
assert host.problems ok == [ ];
# One set for the modules, values as written.
assert (host.factsIn "t" ok).vm == true && (host.factsIn "t" ok).displayScale == 1.5
  && (host.factsIn "t" ok).hostname == "h" && !((host.factsIn "t" ok) ? container);
assert host.problems (with' "layers" { vm = "yes"; }) == [ "layers.vm must be true or false" ];
assert host.problems (with' "platform" { kernelParams = "quiet"; })
  == [ "platform.kernelParams must be a list of strings" ];
assert host.problems (with' "host" { vm = true; }) == [ "unknown key vm in [host]" ];
assert host.problems (ok // { extra = { }; }) == [ "unknown section [extra]" ];
assert host.problems (removeAttrs ok [ "layers" ]) == [ "no section [layers]" ];
assert host.problems (ok // { host = removeAttrs ok.host [ "user" ]; }) == [ "no user in [host]" ];
assert host.problems (with' "layers" { gameMode = true; })
  == [ "layers.gameMode = true needs layers.nativeSteam = true" ];
assert host.problems (with' "layers" { gameMode = true; nativeSteam = true; }) == [ ];
assert host.problems (with' "platform" { displayScale = 5; })
  == [ "platform.displayScale must be between 1 and 4" ];
# [container] exactly with boot = "container".
assert host.problems (with' "platform" { boot = "container"; })
  == [ "boot = \"container\" needs a section [container]" ];
assert host.problems (ok // { inherit container; }) == [ "[container] only with boot = \"container\"" ];
let boxed = with' "platform" { boot = "container"; } // { inherit container; }; in
assert host.problems boxed == [ ] && (host.factsIn "t" boxed).container.port == 3390;
assert host.problems (boxed // { container = container // { port = "3390"; }; })
  == [ "container.port must be a port number" ];
assert fails (with' "layers" { vm = "no"; }) && !(fails ok);
true
