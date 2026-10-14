# The outputs of a configuration built with this core (ws help plan-v2,
# 8.2): homeConfigurations, checks and packages for the data in ROOT. The
# core flake gives them for itself (root = ./.) and as lib.mkConfig for a
# configuration repository:
#
#   outputs = inputs: inputs.wsconfig.lib.mkConfig { root = ./.; inherit inputs; };
#
# ROOT holds the data only (nix/hosts, the catalogs and TOML of the
# modules); the code is always that of this file. The modules read the data
# from ROOT through the specialArg wsConfig, never relative to themselves.
# INPUTS: nixpkgs, home-manager and wswidgets of the configuration (its
# flake.lock pins them).
{ root, inputs }:
let
  inherit (inputs) nixpkgs home-manager wswidgets;
  system = "x86_64-linux";
  pkgs = nixpkgs.legacyPackages.${system};
  inherit (nixpkgs) lib;

  hostsDir = root + "/nix/hosts";
  # Every directory of nix/hosts is a host: host.toml and apt.txt.
  hosts = lib.attrNames (lib.filterAttrs (_: type: type == "directory")
    (builtins.readDir hostsDir));
  # The facts of host.toml, checked (lib/host.nix).
  factsOf = (import ./host.nix { inherit lib; }).factsOf hostsDir;

  mkHome = host: home-manager.lib.homeManagerConfiguration {
    inherit pkgs;
    extraSpecialArgs = {
      inherit man wswidgets core;
      facts = factsOf host;
      # The root of the data: the modules read their catalogs and TOML and
      # the host choices nix/hosts/HOST/*.toml from it (lib/catalog.nix).
      wsConfig = root;
      # The flake host (ws host).
      wsHost = host;
      # The state directory under $HOME (WS_STATE of lib/common.bash).
      wsState = ".local/state/wsconfig";
      inherit xremap;
    };
    modules = [ ../nix/home ];
  };

  # The core in the store: ws and its tools (nix/pkgs/ws.nix).
  core = pkgs.callPackage ../nix/pkgs/ws.nix { };
  # Man pages from docs/ with lowdown from nixpkgs.
  man = pkgs.callPackage ../nix/pkgs/man.nix { };
  xremap = pkgs.callPackage ../nix/pkgs/xremap.nix { };
  # System file tree of the host; `ws system diff|check` compares it.
  mkSystem = host: pkgs.callPackage ../system { facts = factsOf host; };

  perHost = f: lib.listToAttrs (lib.concatMap f hosts);
in
{
  homeConfigurations = perHost (host: [{
    name = "${(factsOf host).user}@${host}";
    value = mkHome host;
  }]);

  checks.${system} = perHost (host: [
    { name = "home-${host}"; value = (mkHome host).activationPackage; }
    { name = "system-${host}"; value = mkSystem host; }
  ]) // {
    inherit man core;
  };

  # Tools `ws` runs, pinned by flake.lock.
  packages.${system} = perHost (host: [
    { name = "system-${host}"; value = mkSystem host; }
  ]) // {
    home-manager = home-manager.packages.${system}.home-manager;
    nvd = pkgs.nvd;
    inherit xremap man;
    ws = core;
  };
}
