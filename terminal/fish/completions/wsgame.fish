# Completions for wsgame (helpws gaming).
complete -c wsgame -f
complete -c wsgame -n __fish_use_subcommand -a fetch -d 'Download the sources, check sha256'
complete -c wsgame -n __fish_use_subcommand -a build -d 'Build the .debs in a podman container'
complete -c wsgame -n __fish_use_subcommand -a test -d 'Install and purge in a clean container'
complete -c wsgame -n __fish_use_subcommand -a install -d 'Install the packages (gameMode hosts)'
complete -c wsgame -n __fish_use_subcommand -a check -d 'Packages, services, display manager'
complete -c wsgame -n __fish_use_subcommand -a status -d 'Pinned, built and installed versions'
complete -c wsgame -n __fish_use_subcommand -a mode -d 'Switch the session now'
complete -c wsgame -n '__fish_seen_subcommand_from check' -l json -d 'Result object'
complete -c wsgame -n '__fish_seen_subcommand_from mode' -a 'game desktop'
