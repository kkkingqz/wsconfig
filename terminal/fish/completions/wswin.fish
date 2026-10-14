# wswin: Windows programs in the Windows boxes (ws help windows).

function __wswin_apps
    # Built by home-manager from windows/apps.nix.
    set -l ini ~/.local/share/wsconfig/windows/apps.ini
    test -f $ini; and string match -rg '^\[([^]]+)\]$' < $ini | string match -v wswin
end

function __wswin_boxes
    # Built by home-manager from distrobox/distrobox.nix: boxes with a profile.
    set -l ini ~/.local/share/wsconfig/distrobox/boxes.ini
    test -f $ini; or return
    set -l box
    while read -l line
        if string match -qr '^\[(?<name>[^]]+)\]$' -- $line
            set box $name
        else if string match -q 'profile=*' -- $line
            echo $box
        end
    end < $ini
end

function __wswin_needs_command
    test (count (commandline -opc)) -eq 1
end

function __wswin_using
    set -l cmd (commandline -opc)
    test (count $cmd) -ge 2; and test "$cmd[2]" = "$argv[1]"
end

complete -c wswin -f
complete -c wswin -n __wswin_needs_command -a list -d 'Programs and prefixes'
complete -c wswin -n __wswin_needs_command -a check -d 'Check the Windows layer (--json for ws check)'
complete -c wswin -n __wswin_needs_command -a install -d 'Run an installer in a box/prefix'
complete -c wswin -n __wswin_needs_command -a run -d 'Start a program from windows/apps.nix'
complete -c wswin -n __wswin_needs_command -a exec -d 'Run any program in a box/prefix'
complete -c wswin -n __wswin_needs_command -a prefix -d 'init, winecfg, winetricks, remove ...'
complete -c wswin -n __wswin_needs_command -a shell -d 'Shell in a box with WINEPREFIX'
complete -c wswin -n __wswin_needs_command -a portable -d 'Copy a portable program into a prefix'
complete -c wswin -n __wswin_needs_command -a menu -d 'Host menu entries: add, list, sync, remove'

complete -c wswin -n '__wswin_using run' -a '(__wswin_apps)'
for c in install exec prefix shell portable menu
    complete -c wswin -n "__wswin_using $c" -l box -x -a '(__wswin_boxes)' -d 'Windows box'
end
for c in install exec shell portable menu
    complete -c wswin -n "__wswin_using $c" -l prefix -x -d 'Prefix name (default: standard)'
end
complete -c wswin -n '__wswin_using install; or __wswin_using exec; or __wswin_using portable' -F
complete -c wswin -n '__wswin_using menu' -a 'add list sync remove'
complete -c wswin -n '__wswin_using prefix' -a 'init winecfg regedit winetricks kill path remove'
