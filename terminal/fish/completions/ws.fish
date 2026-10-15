# Completions for ws. Step names come from ws itself (ws steps), baseline and
# checkpoint names from ~/.local/state/wsconfig.
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
    set -l d ~/.local/state/wsconfig/$dir
    test -d $d; and path basename $d/*/
end

# ws MODULE ARG...: the owner of the layer (ws modules); its arguments are
# completed as if the owner were typed.
function __ws_module_owner
    set -l cmd (commandline -opc)
    test (count $cmd) -ge 2; or return 1
    ws modules 2>/dev/null | string replace -rf -- "^$cmd[2] " ''
end

function __ws_module_args
    set -l owner (__ws_module_owner); or return
    set -l cmd (commandline -opc)
    complete -C "$owner $cmd[3..] "(commandline -ct)
end

complete -c ws -n __ws_needs_command -a '(ws modules 2>/dev/null | string replace -r " (.*)" "\tLayer module (\$1)")'
complete -c ws -n '__ws_module_owner >/dev/null' -a '(__ws_module_args)'
complete -c ws -n __ws_needs_command -a diff -d 'Package difference of the next generation'
complete -c ws -n __ws_needs_command -a apply -d 'Apply the configuration: apt, system, home, modules'
complete -c ws -n __ws_needs_command -a sync -d 'Publish the data files (commit, pull --rebase, push)'
complete -c ws -n '__ws_after sync' -l dry-run -d 'Only show what it would do'
complete -c ws -n __ws_needs_command -a update -d 'Update everything not pinned'
complete -c ws -n __ws_needs_command -a check -d 'All owner checks and cross-layer verify'
complete -c ws -n __ws_needs_command -a system -d 'System file tree: diff, check, manifest, tree'
complete -c ws -n __ws_needs_command -a baseline -d 'Functional baseline: capture, diff, list'
complete -c ws -n __ws_needs_command -a checkpoint -d 'Commit <-> working state'
complete -c ws -n __ws_needs_command -a collect -d 'Machine state archive for a rebuild'
complete -c ws -n __ws_needs_command -a btrfs -d 'Btrfs layout of a fresh install'
complete -c ws -n '__ws_at btrfs' -a make -d '@, @home, @cache, @tmp, @log; two runs'
complete -c ws -n '__ws_after btrfs' -l dry-run -d 'Only show the steps'
complete -c ws -n '__ws_after btrfs' -l yes -d 'Answer its questions with yes'
complete -c ws -n __ws_needs_command -a setup -d 'First setup of this PC (install.sh runs it)'
complete -c ws -n __ws_needs_command -a clean -d 'Remove what nothing uses, after a plan'
complete -c ws -n '__ws_after clean' -a 'nix podman flatpak' -d 'Scope'
complete -c ws -n '__ws_after clean' -l dry-run -d 'Only the plan'
complete -c ws -n '__ws_after clean' -l keep-days -x -d 'nix: keep generations younger (30)'
complete -c ws -n '__ws_after clean' -l yes -d 'No questions (scopes by name)'
complete -c ws -n '__ws_after setup' -l repo -r -d 'A configuration that exists (URL or PATH)'
complete -c ws -n '__ws_after setup' -l new -r -F -d 'A new configuration in DIR (~/wsconfig)'
complete -c ws -n '__ws_after setup' -l host -x -d 'The host when the hostname finds none'
complete -c ws -n '__ws_at backup' -a 'plan status list check send restore-test recovery-export'
complete -c ws -n '__ws_at backup list' -l json -d 'Machine-readable list'
complete -c ws -n '__ws_at backup plan; or __ws_at backup send' -a 'home vms all'
complete -c ws -n '__ws_at backup restore-test' -a 'system home vms'
complete -c ws -n '__ws_at backup check' -l remote -d 'Check configured receiver over SSH'
complete -c ws -n __ws_needs_command -a host -d 'Flake host of this machine'
complete -c ws -n __ws_needs_command -a fact -d 'String fact of this host'
complete -c ws -n '__ws_after host' -l for-marks -d 'Fail unless the name fits a list mark'
complete -c ws -n '__ws_after fact' -l host -x -a '(path basename ~/wsconfig/hosts/*/)' -d 'Fact of another host'
complete -c ws -n __ws_needs_command -a news -d 'home-manager news'

complete -c ws -n '__ws_after apply' -a '(ws steps apply)'
complete -c ws -n '__ws_after update' -a '(ws steps update)'

complete -c ws -n '__ws_at check' -a 'apt repo home virt steam gaming backup' -d 'One owner check'
complete -c ws -n '__ws_at check' -s v -l verbose -d 'All messages'
complete -c ws -n '__ws_at check apt; or __ws_at check repo; or __ws_at check home; or __ws_at check virt; or __ws_at check steam; or __ws_at check gaming; or __ws_at check backup' -l json -d 'Result object'

complete -c ws -n '__ws_at system' -a 'diff check manifest tree'
complete -c ws -n '__ws_at system check' -l json -d 'Result object'

complete -c ws -n '__ws_at baseline' -a 'capture diff list'
complete -c ws -n '__ws_after baseline; and not __ws_at baseline' -a '(__ws_state_names baseline)'
complete -c ws -n '__ws_after baseline' -l no-boxes -d 'Skip wsbox check'
complete -c ws -n '__ws_after baseline' -l with-sudo -d 'Also dpkg verify, initramfs, ESP'

complete -c ws -n '__ws_at checkpoint' -a 'create list show diff remove'
complete -c ws -n '__ws_at checkpoint show; or __ws_at checkpoint diff; or __ws_at checkpoint remove' -a '(__ws_state_names checkpoints)'
complete -c ws -n '__ws_after checkpoint' -l baseline -d 'diff: capture and compare a baseline'

complete -c ws -n __ws_needs_command -a container -d 'A host in a Docker container on the server'
complete -c ws -n '__ws_at container' -a build -d 'Image from HEAD and the pinned core'
complete -c ws -n '__ws_at container' -a run -d 'Replace the container with the latest image'
complete -c ws -n '__ws_at container' -a status -d 'Container and image commit against HEAD'
complete -c ws -n '__ws_after container' -l dry-run -d 'Print the docker command'

complete -c ws -n '__ws_after collect' -l no-firmware -d 'Without the Apple firmware'
complete -c ws -n '__ws_after collect' -F

complete -c ws -n '__ws_after backup; and __ws_after recovery-export' -F
complete -c ws -n '__ws_after backup; and __ws_after recovery-export' -l force -d 'Replace existing recovery export'

complete -c ws -n __ws_needs_command -a help -d 'Documentation: ws help TOPIC'

# ws help TOPIC: the topics of libexec/helpws (tests/test_helpws.py keeps
# the list equal to its case).
set -l ws_help_topics readme layers architecture architecture-v2 arch-v2 checks check workstation system baseline terminal term ghostty fish keyboard keys touchbar touch-bar suspend sleep power gnome desktop rebuild reinstall setup install new distrobox box boxes wsbox flatpak wsflatpak windows wine wswin steam proton remmina rdp virt vm vms libvirt kvm gaming game gamemode wsgame backup wsbackup recovery restore ws-restore widgets widget wswidgets scripts script wsscript clean status summary roadmap plans plan-t2 plan-dgpu dgpu t2gmux plan-final plan-unraid unraid plan-legion-go legion-go legiongo plan-legion-go-agent legion-go-agent plan-wsgnomebox wsgnomebox plan-hyprland hyprland plan-v2 v2 history-gnome plan-gnome history-flatpak plan-flatpak history-distrobox plan-dev history-windows plan-windows history-nix plan-nix history-suspend history-touchbar history-virt plan-virt man help

function __ws_help_topic -a name desc
    complete -c ws -n "__ws_after help; and not __fish_seen_subcommand_from $ws_help_topics" -a $name -d $desc
end

__ws_help_topic readme 'README: entry point'
__ws_help_topic layers 'Layers, owners, rules'
__ws_help_topic architecture-v2 'wsconfig v2: core, configuration repository, shared mechanisms'
__ws_help_topic checks 'ws check: owners, --json format'
__ws_help_topic workstation 'Current workstation in detail'
__ws_help_topic setup 'New PC on wsconfig: install.sh, ws setup'
__ws_help_topic rebuild 'Reinstall to the current state'
__ws_help_topic keyboard 'macOS-style keyboard layer'
__ws_help_topic gnome 'GNOME desktop'
__ws_help_topic terminal 'Ghostty + Fish handbook'
__ws_help_topic suspend 'Suspend / T2 power layer'
__ws_help_topic touchbar 'Touch Bar'
__ws_help_topic flatpak 'Flatpak applications'
__ws_help_topic distrobox 'Managed Distrobox / Podman'
__ws_help_topic windows 'Wine / Proton / Steam'
__ws_help_topic remmina 'Remmina RDP client from Nix: H.264, files'
__ws_help_topic virt 'Virtual machines: KVM, libvirt, virt-manager'
__ws_help_topic gaming 'Game Mode: gamescope + Steam session'
__ws_help_topic backup 'Backup to Unraid: Timeshift, Btrfs send'
__ws_help_topic recovery 'Restore a date from Unraid (ws-restore, Live USB)'
__ws_help_topic widgets 'Shared widget runtime'
__ws_help_topic scripts 'Own scripts, run by name'
__ws_help_topic clean 'ws clean: Nix generations, Podman images, Flatpak runtimes'
__ws_help_topic status 'Project summary: done and left'
__ws_help_topic roadmap 'What is left'
__ws_help_topic plan-t2 'T2 optional / power / auth'
__ws_help_topic plan-dgpu 'AMD dGPU through t2gmux'
__ws_help_topic plan-final 'Backup / inventory / finalization'
__ws_help_topic plan-unraid 'Unraid receiver: survey, preparation'
__ws_help_topic plan-legion-go 'Legion Go: host, Game Mode from Bazzite parts'
__ws_help_topic plan-legion-go-agent 'Legion Go: instructions for Claude on the device'
__ws_help_topic plan-wsgnomebox 'wsgnomebox: wsconfig host in a container on tower'
__ws_help_topic plan-hyprland 'Hyprland + Caelestia next to GNOME'
__ws_help_topic plan-v2 'wsconfig v2: cleanup, shared mechanisms, two repositories'
__ws_help_topic history-gnome 'How the GNOME layer was built'
__ws_help_topic history-flatpak 'How the Flatpak layer was built'
__ws_help_topic history-distrobox 'How the Distrobox layer was built'
__ws_help_topic history-windows 'How the Windows layer was built'
__ws_help_topic history-nix 'Nix + home-manager migration'
__ws_help_topic history-suspend 'Suspend / Touch Bar failures and fixes'
__ws_help_topic history-virt 'How the VM layer was built'
__ws_help_topic man 'Open generated man page in Micro'

functions -e __ws_help_topic
complete -c ws -n '__ws_at help man' -a '(path basename ~/.local/share/man/man1/ws-*.1 | string replace -r "\.1\$" "")'
complete -c ws -n __ws_needs_command -a 'battery gmux psr gpu' -d 'Hardware diagnostics'
