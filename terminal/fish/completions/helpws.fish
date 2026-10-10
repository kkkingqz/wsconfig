# Completions for helpws.
complete -c helpws -f

set -l helpws_topics readme layers architecture checks check workstation system baseline terminal term ghostty fish keyboard keys touchbar touch-bar suspend sleep power gnome desktop rebuild reinstall install setup new distrobox box boxes wsbox flatpak wsflatpak windows wine wswin steam proton virt vm vms libvirt kvm roadmap plans plan-t2 plan-dgpu dgpu t2gmux plan-virt plan-final history-gnome history-flatpak history-distrobox history-windows history-nix history-suspend history-touchbar history-virt plan-gnome plan-flatpak plan-dev plan-windows plan-nix man help

function __helpws_topic -a name desc
    complete -c helpws -n "not __fish_seen_subcommand_from $helpws_topics" -a $name -d $desc
end

__helpws_topic readme 'README: entry point'
__helpws_topic layers 'Layers, owners, rules'
__helpws_topic checks 'ws check: owners, --json format'
__helpws_topic workstation 'Current workstation in detail'
__helpws_topic setup 'New PC on wsconfig: setup.sh'
__helpws_topic rebuild 'Reinstall to the current state'
__helpws_topic keyboard 'macOS-style keyboard layer'
__helpws_topic gnome 'GNOME desktop'
__helpws_topic terminal 'Ghostty + Fish handbook'
__helpws_topic suspend 'Suspend / T2 power layer'
__helpws_topic touchbar 'Touch Bar'
__helpws_topic flatpak 'Flatpak applications'
__helpws_topic distrobox 'Managed Distrobox / Podman'
__helpws_topic windows 'Wine / Proton / Steam'
__helpws_topic virt 'Virtual machines: KVM, libvirt, virt-manager'
__helpws_topic roadmap 'What is left'
__helpws_topic plan-t2 'T2 optional / power / auth'
__helpws_topic plan-dgpu 'AMD dGPU through t2gmux'
__helpws_topic plan-final 'Backup / inventory / finalization'
__helpws_topic history-gnome 'How the GNOME layer was built'
__helpws_topic history-flatpak 'How the Flatpak layer was built'
__helpws_topic history-distrobox 'How the Distrobox layer was built'
__helpws_topic history-windows 'How the Windows layer was built'
__helpws_topic history-nix 'Nix + home-manager migration'
__helpws_topic history-suspend 'Suspend / Touch Bar failures and fixes'
__helpws_topic history-virt 'How the VM layer was built'
__helpws_topic man 'Open generated man page in Micro'

functions -e __helpws_topic
complete -c helpws -n '__fish_seen_subcommand_from man' -a '(path basename ~/.local/share/man/man1/ws-*.1 | string replace -r "\.1\$" "")'
