{
  description = "Workstation configuration (Nix delivers, layer owners stay)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    # Widget layer (widgets/widgets.nix, ws help widgets): runtime, QML and
    # GNOME adapter of ~/Projects/wswidgets, pinned here like nixpkgs.
    wswidgets = {
      url = "github:kkkingqz/wswidgets";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  # The outputs of the test configuration tests/config (lib/mkconfig.nix,
  # what a configuration repository gets: its hosts are the checks of the
  # core), the checks of the core libraries and lib.mkConfig for a
  # configuration repository. The data of a real workstation is not here.
  outputs = inputs@{ nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      inherit (nixpkgs) lib;
      mkConfig = import ./lib/mkconfig.nix;
      own = mkConfig { root = ./tests/config; inherit inputs; };
    in
    own // {
      lib = { inherit mkConfig; };

      checks.${system} = own.checks.${system} // {
        scale = assert import ./lib/test-scale.nix { inherit lib; };
          pkgs.writeText "scale" "lib/scale.nix: sizes by the display scale";
        host = assert import ./lib/test-host.nix { inherit lib; };
          pkgs.writeText "host" "lib/host.nix checks host.toml";
        config = assert import ./lib/test-config.nix { inherit lib; };
          pkgs.writeText "config" "lib/config.nix merges and checks module TOML";
        catalog = assert import ./lib/test-catalog.nix { inherit lib; };
          pkgs.writeText "catalog" "lib/catalog.nix reads the host choices";
      };
    };
}
