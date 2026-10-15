{
  description = "Workstation configuration (data of wsconfig; ws help architecture-v2)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    wswidgets = {
      url = "github:kkkingqz/wswidgets";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    # The core: ws, its modules and tools; pinned here, ws update core.
    wsconfig = {
      url = "github:kkkingqz/wsconfig";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.home-manager.follows = "home-manager";
      inputs.wswidgets.follows = "wswidgets";
    };
  };

  # The outputs are those of the core for the data here.
  outputs = inputs: inputs.wsconfig.lib.mkConfig { root = ./.; inherit inputs; };
}
