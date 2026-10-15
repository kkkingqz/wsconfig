# Terminal CLI from Nix, in PATH through ~/.nix-profile/bin (00-nix.fish).
# lowdown is not needed here: man pages are built in Nix (nix/pkgs/man.nix).
# gum: for the core run from a checkout (ws --core PATH); the core in the
# store has its own libexec/gum (nix/pkgs/ws.nix).
{ pkgs, ... }:
{
  home.packages = with pkgs; [
    fzf
    zoxide
    eza
    micro
    nvd
    gum
  ];
}
