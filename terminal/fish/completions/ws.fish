# Completions for ws. Step names come from ws itself (ws steps), baseline and
# checkpoint names from ~/.local/state/workstation.
complete -c ws -f

function __ws_needs_command
    test (count (commandline -opc)) -eq 1
end

# ws WORD [WORD2]: true when the words after `ws` start with the arguments
# and nothing else follows yet.
function __ws_at
    set -l cmd (commandline -opc)
    test (count $cmd) -eq (math (count $argv) + 1)
    and test "$cmd[2..]" = "$argv"
end

function __ws_after
    set -l cmd (commandline -opc)
    test (count $cmd) -ge 2
    and test "$cmd[2]" = "$argv[1]"
end

function __ws_state_names -a dir
    set -l d ~/.local/state/workstation/$dir
    test -d $d; and path basename $d/*/
end

complete -c ws -n __ws_needs_command -a switch -d 'home-manager switch, commit flatpak/apps.txt'
complete -c ws -n __ws_needs_command -a diff -d 'Package difference of the next generation'
complete -c ws -n __ws_needs_command -a apply -d 'Run the layer owners in order'
complete -c ws -n __ws_needs_command -a update -d 'Update everything not pinned'
complete -c ws -n __ws_needs_command -a check -d 'All owner checks and cross-layer verify'
complete -c ws -n __ws_needs_command -a system -d 'System file tree: diff, check, apply'
complete -c ws -n __ws_needs_command -a baseline -d 'Functional baseline: capture, diff, list'
complete -c ws -n __ws_needs_command -a checkpoint -d 'Commit <-> working state'
complete -c ws -n __ws_needs_command -a collect -d 'Machine state archive for a rebuild'
complete -c ws -n __ws_needs_command -a btrfs -d 'Btrfs layout of a fresh install'
complete -c ws -n '__ws_at btrfs' -a make -d '@, @home, @cache, @tmp, @log; two runs'
complete -c ws -n '__ws_at btrfs make' -l dry-run -d 'Only show the steps'
complete -c ws -n __ws_needs_command -a backup -d 'Native Btrfs backup to Unraid'
complete -c ws -n '__ws_at backup' -a 'plan status list check send restore-test recovery-export'
complete -c ws -n '__ws_at backup list' -l json -d 'Machine-readable list'
complete -c ws -n '__ws_at backup plan; or __ws_at backup send' -a 'home vms all'
complete -c ws -n '__ws_at backup restore-test' -a 'system home vms'
complete -c ws -n '__ws_at backup check' -l remote -d 'Check configured receiver over SSH'
complete -c ws -n __ws_needs_command -a host -d 'Flake host of this machine'
complete -c ws -n __ws_needs_command -a fact -d 'String fact of this host'
complete -c ws -n __ws_needs_command -a news -d 'home-manager news'

complete -c ws -n '__ws_after apply' -a '(ws steps apply)'
complete -c ws -n '__ws_after update' -a '(ws steps update)'

complete -c ws -n '__ws_at check' -a 'apt repo home virt steam backup' -d 'One owner check'
complete -c ws -n '__ws_at check' -s v -l verbose -d 'All messages'
complete -c ws -n '__ws_at check apt; or __ws_at check repo; or __ws_at check home; or __ws_at check virt; or __ws_at check steam; or __ws_at check backup' -l json -d 'Result object'

complete -c ws -n '__ws_at system' -a 'diff check apply manifest tree'
complete -c ws -n '__ws_at system check' -l json -d 'Result object'

complete -c ws -n '__ws_at baseline' -a 'capture diff list'
complete -c ws -n '__ws_after baseline; and not __ws_at baseline' -a '(__ws_state_names baseline)'
complete -c ws -n '__ws_after baseline' -l no-boxes -d 'Skip wsbox check'
complete -c ws -n '__ws_after baseline' -l with-sudo -d 'Also dpkg verify, initramfs, ESP'

complete -c ws -n '__ws_at checkpoint' -a 'create list show diff remove'
complete -c ws -n '__ws_at checkpoint show; or __ws_at checkpoint diff; or __ws_at checkpoint remove' -a '(__ws_state_names checkpoints)'
complete -c ws -n '__ws_after checkpoint' -l baseline -d 'diff: capture and compare a baseline'

complete -c ws -n '__ws_after collect' -l no-firmware -d 'Without the Apple firmware'
complete -c ws -n '__ws_after collect' -F

complete -c ws -n '__ws_after backup; and __ws_after recovery-export' -F
complete -c ws -n '__ws_after backup; and __ws_after recovery-export' -l force -d 'Replace existing recovery export'
