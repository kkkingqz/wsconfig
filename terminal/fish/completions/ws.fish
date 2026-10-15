# Completions for ws: generated from the usage of its commands, not kept
# here (lib/ws_complete.py, ws help terminal). The spec is built with the
# core (share/ws/complete.json); a checkout of the core builds it on the
# first Tab after a change.
complete -c ws -e
complete -c ws -f

function __ws_complete
    set -l core (path dirname (path dirname (path resolve (command -s ws))))
    test -f $core/lib/ws_complete.py; or return
    set -l words (commandline -opc)[2..] (commandline -ct)
    for line in (python3 $core/lib/ws_complete.py complete -- $words 2>/dev/null)
        switch $line
            case @files
                __fish_complete_path (commandline -ct)
            case @commands
                __fish_complete_command (commandline -ct)
            case '*'
                echo $line
        end
    end
end

complete -c ws -a '(__ws_complete)'
