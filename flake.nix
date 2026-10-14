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

      # Every directory of nix/hosts is a host: facts.nix and apt.txt.
      hosts = lib.attrNames (lib.filterAttrs (_: type: type == "directory")
        (builtins.readDir ./nix/hosts));
      factsOf = host:
        let facts = import ./nix/hosts/${host}/facts.nix; in
        assert lib.assertMsg (lib.elem (facts.vm or null) [ "yes" "no" ])
          "nix/hosts/${host}/facts.nix: vm must be \"yes\" or \"no\" (helpws virt)";
        assert lib.assertMsg (lib.elem (facts.nativeSteam or null) [ "yes" "no" ])
          "nix/hosts/${host}/facts.nix: nativeSteam must be \"yes\" or \"no\" (helpws plan-legion-go)";
        assert lib.assertMsg (lib.elem (facts.widgets or null) [ "yes" "no" ])
          "nix/hosts/${host}/facts.nix: widgets must be \"yes\" or \"no\" (helpws widgets)";
        assert lib.assertMsg (lib.elem (facts.gameMode or null) [ "yes" "no" ])
          "nix/hosts/${host}/facts.nix: gameMode must be \"yes\" or \"no\" (helpws plan-legion-go)";
        # The Game Mode session runs the apt Steam: the flatpak cannot reach
        # the host helpers (steamos-session-select, steamosctl).
        assert lib.assertMsg (facts.gameMode == "no" || facts.nativeSteam == "yes")
          "nix/hosts/${host}/facts.nix: gameMode = \"yes\" needs nativeSteam = \"yes\"";
        facts;

      mkHome = host: home-manager.lib.homeManagerConfiguration {
        inherit pkgs;
        extraSpecialArgs = {
          inherit man wswidgets;
          facts = factsOf host;
          # The flake host (ws host): its workstation marks in
          # flatpak/apps.txt and distrobox/hosts.txt (lib/ws_marks.nix).
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
        ws-marks = assert import ./lib/test-ws-marks.nix { inherit lib; };
          pkgs.writeText "ws-marks" "lib/ws_marks.nix reads the workstation marks";
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
