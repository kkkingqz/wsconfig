{
  description = "Workstation configuration (Nix delivers, layer owners stay)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    # Widget layer (widgets/widgets.nix, helpws widgets): runtime, QML and
    # GNOME adapter of ~/Projects/wswidgets, pinned here like nixpkgs.
    wswidgets = {
      url = "github:kkkingqz/wswidgets";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { nixpkgs, home-manager, wswidgets, ... }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      inherit (nixpkgs) lib;

      # Every directory of nix/hosts is a host: host.toml and apt.txt.
      hosts = lib.attrNames (lib.filterAttrs (_: type: type == "directory")
        (builtins.readDir ./nix/hosts));
      # The facts of host.toml, checked (lib/host.nix).
      factsOf = (import ./lib/host.nix { inherit lib; }).factsOf ./nix/hosts;

      mkHome = host: home-manager.lib.homeManagerConfiguration {
        inherit pkgs;
        extraSpecialArgs = {
          inherit man wswidgets;
          facts = factsOf host;
          # The flake host (ws host): its choices nix/hosts/HOST/*.toml
          # (lib/catalog.nix).
          wsHost = host;
          # The state directory under $HOME (WS_STATE of lib/common.bash).
          wsState = ".local/state/wsconfig";
          xremap = pkgs.callPackage ./nix/pkgs/xremap.nix { };
        };
        modules = [ ./nix/home ];
      };

      # Man pages from docs/ with lowdown from nixpkgs.
      man = pkgs.callPackage ./nix/pkgs/man.nix { };
      # System file tree of the host; `ws system diff|check` compares it.
      mkSystem = host: pkgs.callPackage ./system { facts = factsOf host; };

      perHost = f: lib.listToAttrs (lib.concatMap f hosts);
    in {
      homeConfigurations = perHost (host: [{
        name = "${(factsOf host).user}@${host}";
        value = mkHome host;
      }]);

      checks.${system} = perHost (host: [
        { name = "home-${host}"; value = (mkHome host).activationPackage; }
        { name = "system-${host}"; value = mkSystem host; }
      ]) // {
        inherit man;
        scale = assert import ./lib/test-scale.nix { inherit lib; };
          pkgs.writeText "scale" "lib/scale.nix: sizes by the display scale";
        host = assert import ./lib/test-host.nix { inherit lib; };
          pkgs.writeText "host" "lib/host.nix checks host.toml";
        catalog = assert import ./lib/test-catalog.nix { inherit lib; };
          pkgs.writeText "catalog" "lib/catalog.nix reads the host choices";
      };

      # Tools `ws` runs, pinned by flake.lock.
      packages.${system} = perHost (host: [
        { name = "system-${host}"; value = mkSystem host; }
      ]) // {
        home-manager = home-manager.packages.${system}.home-manager;
        nvd = pkgs.nvd;
        xremap = pkgs.callPackage ./nix/pkgs/xremap.nix { };
        man = man;
      };
    };
}
