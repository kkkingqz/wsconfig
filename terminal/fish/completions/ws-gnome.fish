# Completions for ws-gnome.
complete -c ws-gnome -f

complete -c ws-gnome -n 'not __fish_seen_subcommand_from status check test help' -a status -d 'Read-only GNOME inventory'
complete -c ws-gnome -n 'not __fish_seen_subcommand_from status check test help' -a check -d 'Compare session with gnome/gnome.nix'
complete -c ws-gnome -n 'not __fish_seen_subcommand_from status check test help' -a test -d 'Final GNOME host smoke-test'
complete -c ws-gnome -n 'not __fish_seen_subcommand_from status check test help' -a help -d 'Show ws-gnome help'
