{
  description = "Workstation configuration (Nix delivers, layer owners stay)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { nixpkgs, home-manager, ... }:
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
          inherit man;
          facts = factsOf host;
          # The flake host (ws host): its workstation marks in
          # flatpak/apps.txt and distrobox/hosts.txt (lib/ws_marks.nix).
          wsHost = host;
          xremap = pkgs.callPackage ./nix/pkgs/xremap.nix { };
        };
        modules = [ ./nix/home ];
      };

      # Man pages from docs/ with lowdown from nixpkgs.
      man = pkgs.callPackage ./nix/pkgs/man.nix { };
      widgetsRuntime = import ./widgets/runtime { inherit pkgs; };
      widgetsManifest = import ./widgets/manifest.nix {
        inherit lib;
        registry = import ./widgets/registry.nix;
        qmlRoot = ./widgets/quickshell;
      };

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
        ws-marks = assert import ./lib/test-ws-marks.nix { inherit lib; };
          pkgs.writeText "ws-marks" "lib/ws_marks.nix reads the workstation marks";
        widgets-manifest = assert import ./widgets/test-manifest.nix { inherit lib; };
          pkgs.writeText "widgets-manifest.json" (builtins.toJSON widgetsManifest);
        widgets-qml = pkgs.runCommand "widgets-qml" { nativeBuildInputs = [ pkgs.python3 ]; } ''
          export HOME="$TMPDIR/home" XDG_RUNTIME_DIR="$TMPDIR/runtime"
          mkdir -p "$HOME" "$XDG_RUNTIME_DIR"
          chmod 700 "$XDG_RUNTIME_DIR"
          python ${./.}/tests/widgets/check-qml.py ${widgetsRuntime}/bin/qs-widgets
          touch "$out"
        '';
        widgets-tests = assert builtins.readFile ./widgets/quickshell/framework/manifest.mjs == builtins.readFile (./gnome/extensions + "/workstation-widgets@local/lib/manifest.mjs");
          pkgs.runCommand "widgets-tests" { nativeBuildInputs = [ pkgs.python3 pkgs.gjs ]; } ''
            cp -r ${./.} source
            chmod -R u+w source
            cd source
            patchShebangs bin/ws-widgets bin/ws-widgets-check
            python -m unittest discover -s tests -p test_gnome_extension_files.py
            python -m unittest discover -s tests -p test_ws_widgets.py
            gjs -m tests/widgets/run-tests.js
            touch "$out"
          '';
        widgets-runtime = pkgs.runCommand "widgets-runtime-integration" { nativeBuildInputs = [ pkgs.python3 pkgs.gjs ]; } ''
          export HOME="$TMPDIR/home" XDG_RUNTIME_DIR="$TMPDIR/runtime"
          mkdir -p "$HOME" "$XDG_RUNTIME_DIR"
          chmod 700 "$XDG_RUNTIME_DIR"
          python ${./.}/tests/widgets/check-runtime.py --runtime ${widgetsRuntime}/bin/qs-widgets \
            --manifest ${pkgs.writeText "widget-test-manifest.json" (builtins.toJSON widgetsManifest)}
          touch "$out"
        '';
      };

      # Tools `ws` runs, pinned by flake.lock.
      packages.${system} = perHost (host: [
        { name = "system-${host}"; value = mkSystem host; }
      ]) // {
        home-manager = home-manager.packages.${system}.home-manager;
        nvd = pkgs.nvd;
        xremap = pkgs.callPackage ./nix/pkgs/xremap.nix { };
        man = man;
        widgets-runtime = widgetsRuntime;
      };
    };
}
