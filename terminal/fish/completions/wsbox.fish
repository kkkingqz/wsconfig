function __wsbox_needs_command
    set -l cmd (commandline -opc)
    test (count $cmd) -eq 1
end

function __wsbox_using_command
    set -l cmd (commandline -opc)

    test (count $cmd) -ge 2
    and test "$cmd[2]" = "$argv[1]"
end

function __wsbox_needs_box
    set -l cmd (commandline -opc)

    test (count $cmd) -eq 2
    and test "$cmd[2]" = "$argv[1]"
end

function __wsbox_managed_boxes
    # Built by home-manager from distrobox/distrobox.nix.
    set -l manifest ~/.local/share/workstation/distrobox/containers.ini

    if test -f $manifest
        string match -rg '^\[([^]]+)\]$' < $manifest
    end
end

function __wsbox_export_aliases_for_box
    set -l box $argv[1]
    # Built by home-manager from distrobox/distrobox.nix.
    set -l manifest ~/.local/share/workstation/distrobox/exports.ini

    if test -f $manifest
        awk -F= -v section="[$box]" '
            $0 == section {
                inside=1
                next
            }

            inside && /^\[/ {
                exit
            }

            inside && /=/ {
                key=$1
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
                if (key != "") print key
            }
        ' $manifest
    end
end

function __wsbox_current_export_aliases
    set -l cmd (commandline -opc)

    test (count $cmd) -eq 3; or return
    contains -- $cmd[2] export unexport; or return

    __wsbox_export_aliases_for_box $cmd[3]
end

complete -c wsbox -f

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a list \
    -d 'List Distrobox containers'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a status \
    -d 'Show managed container state'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a check \
    -d 'Check managed Distrobox policy'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a dry-run \
    -d 'Show generated create commands'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a apply \
    -d 'Create missing containers and apply managed exports'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a update \
    -d 'Upgrade packages inside managed containers'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a create \
    -d 'Create one managed container'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a enter \
    -d 'Enter managed container'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a run \
    -d 'Run command inside managed container'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a stop \
    -d 'Stop managed container'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a remove \
    -d 'Remove runtime container'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a recreate \
    -d 'Recreate container from manifest'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a apps \
    -d 'Show managed exports and available desktop files'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a export \
    -d 'Export one managed desktop application'

complete -c wsbox \
    -n '__wsbox_needs_command' \
    -a unexport \
    -d 'Remove one managed desktop export'

for cmd in status dry-run apply update create enter run stop remove recreate apps export unexport
    complete -c wsbox \
        -n "__wsbox_needs_box $cmd" \
        -a '(__wsbox_managed_boxes)'
end

complete -c wsbox \
    -n "__wsbox_needs_box apply" \
    -l select \
    -d 'Ask about containers skipped on this machine too'

complete -c wsbox \
    -n '__wsbox_using_command export' \
    -a '(__wsbox_current_export_aliases)' \
    -d 'Managed application alias'

complete -c wsbox \
    -n '__wsbox_using_command unexport' \
    -a '(__wsbox_current_export_aliases)' \
    -d 'Managed application alias'
