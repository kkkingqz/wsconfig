# wswidgets (libexec/wswidgets): the widget layer, ws help widgets.

function __wswidgets_needs_command
    test (count (commandline -opc)) -eq 1
end

function __wswidgets_using
    set -l cmd (commandline -opc)
    test (count $cmd) -ge 2
    and contains -- $cmd[2] $argv
end

# Every widget of the installed wswidgets (written by ws apply).
function __wswidgets_catalog
    set -l catalog ~/.local/share/workstation/widgets/catalog.json
    test -f $catalog; and python3 -c 'import json, sys
for w in json.load(open(sys.argv[1])): print(w["id"] + "\t" + w["label"])' $catalog 2>/dev/null
end

function __wswidgets_enabled
    wswidgets enabled 2>/dev/null
end

complete -c wswidgets -f
complete -c wswidgets -n __wswidgets_needs_command -a list -d 'Widgets of the pinned wswidgets and their state here'
complete -c wswidgets -n __wswidgets_needs_command -a enabled -d 'IDs enabled here, panel order'
complete -c wswidgets -n __wswidgets_needs_command -a enable -d 'Enable widgets here, then ws apply'
complete -c wswidgets -n __wswidgets_needs_command -a disable -d 'Disable widgets here, then ws apply'
complete -c wswidgets -n __wswidgets_needs_command -a apply -d 'Offer widgets not offered here yet'
complete -c wswidgets -n __wswidgets_needs_command -a update -d 'Newest wswidgets from GitHub into flake.lock, switch'
complete -c wswidgets -n __wswidgets_needs_command -a version -d 'The pinned wswidgets revision'
complete -c wswidgets -n __wswidgets_needs_command -a status -d 'The running widget runtime'
complete -c wswidgets -n __wswidgets_needs_command -a check -d 'ws check widgets'
complete -c wswidgets -n __wswidgets_needs_command -a help -d 'Usage'
complete -c wswidgets -n '__wswidgets_using enable' -a '(__wswidgets_catalog)'
complete -c wswidgets -n '__wswidgets_using disable' -a '(__wswidgets_enabled)'
complete -c wswidgets -n '__wswidgets_using enable disable update' -s n -l no-switch -d 'Only edit; ws apply later'
complete -c wswidgets -n '__wswidgets_using apply' -l select -d 'Offer the declined widgets again'
complete -c wswidgets -n '__wswidgets_using check' -l json -d 'One result object'
