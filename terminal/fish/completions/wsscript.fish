# wsscript (libexec/wsscript): the scripts of the configuration, ws help scripts.

function __wsscript_needs_command
    test (count (commandline -opc)) -eq 1
end

function __wsscript_using
    set -l cmd (commandline -opc)
    test (count $cmd) -ge 2
    and contains -- $cmd[2] $argv
end

# NAME<TAB>DESCRIPTION of every script of scripts/.
function __wsscript_names
    ws script names 2>/dev/null
end

complete -c wsscript -f
complete -c wsscript -n __wsscript_needs_command -a list -d 'Scripts of scripts/ and their state here'
complete -c wsscript -n __wsscript_needs_command -a add -d 'New script: yes here, git add, ws apply'
complete -c wsscript -n __wsscript_needs_command -a edit -d 'Edit the file of the checkout'
complete -c wsscript -n __wsscript_needs_command -a enable -d 'Enable scripts here, then ws apply'
complete -c wsscript -n __wsscript_needs_command -a disable -d 'Disable scripts here, then ws apply'
complete -c wsscript -n __wsscript_needs_command -a delete -d 'Delete a script on every host'
complete -c wsscript -n __wsscript_needs_command -a apply -d 'Offer scripts not offered here yet'
complete -c wsscript -n __wsscript_needs_command -a check -d 'Links and files against the choice'
complete -c wsscript -n __wsscript_needs_command -a help -d 'Usage'
complete -c wsscript -n '__wsscript_using edit enable disable delete' -a '(__wsscript_names)'
complete -c wsscript -n '__wsscript_using add' -F
complete -c wsscript -n '__wsscript_using add enable disable delete' -s n -l no-apply -d 'Only edit; ws apply later'
complete -c wsscript -n '__wsscript_using apply' -l select -d 'Offer the declined scripts again'
complete -c wsscript -n '__wsscript_using check' -l json -d 'One result object'
