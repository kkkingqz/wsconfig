# Completions for ws-gnome.
complete -c ws-gnome -f

complete -c ws-gnome -n 'not __fish_seen_subcommand_from status check test extensions help' -a status -d 'Read-only GNOME inventory'
complete -c ws-gnome -n 'not __fish_seen_subcommand_from status check test extensions help' -a check -d 'Compare session with gnome/gnome.nix'
complete -c ws-gnome -n 'not __fish_seen_subcommand_from status check test extensions help' -a test -d 'Final GNOME host smoke-test'
complete -c ws-gnome -n 'not __fish_seen_subcommand_from status check test extensions help' -a extensions -d 'Install the EGO and local extensions'
complete -c ws-gnome -n 'not __fish_seen_subcommand_from status check test extensions help' -a help -d 'Show ws-gnome help'
