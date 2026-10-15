function __wsflatpak_needs_command
    test (count (commandline -opc)) -eq 1
end

function __wsflatpak_using_command
    set -l tokens (commandline -opc)
    test (count $tokens) -ge 2; and test "$tokens[2]" = "$argv[1]"
end

function __wsflatpak_positional_args
    set -l tokens (commandline -opc)
    set -l remote_value 0
    set -l literal 0
    for token in $tokens[3..-1]
        if test $remote_value -eq 1
            set remote_value 0
            continue
        end
        if test $literal -eq 1
            echo "$token"
            continue
        end
        switch $token
            case --remote
                set remote_value 1
            case --
                set literal 1
            case '-*'
            case '*'
                echo "$token"
        end
    end
end

function __wsflatpak_at_position
    set -l tokens (commandline -opc)
    test "$tokens[-1]" != --remote; or return 1
    set -l args (__wsflatpak_positional_args)
    test (count $args) -eq (math "$argv[1] - 1")
end

# Readers of the JSON manifests (lib/ws_common.py) and of the catalog
# (lib/flatpak_catalog.py), next to this file in the checkout it is linked
# from.
set -g __wsflatpak_lib (path normalize (path dirname (path resolve (status filename)))/../../../lib)
set -g __wsflatpak_common $__wsflatpak_lib/ws_common.py

function __wsflatpak_repo
    if set -q WSCONFIG; and test -n "$WSCONFIG"
        echo "$WSCONFIG"
    else
        set -l script (command -s wsflatpak)
        if test -n "$script"
            path dirname (path dirname (path resolve "$script"))
        else
            echo "$HOME/wsconfig"
        end
    end
end

function __wsflatpak_catalog
    WSCONFIG=(__wsflatpak_repo) python3 $__wsflatpak_lib/flatpak_catalog.py $argv 2>/dev/null
end

function __wsflatpak_user_apps
    if command -q flatpak
        flatpak list --user --app --columns=application 2>/dev/null
    end
end

function __wsflatpak_declared_apps
    __wsflatpak_catalog apps
end

function __wsflatpak_override_apps
    __wsflatpak_user_apps
    __wsflatpak_catalog override-apps
end

function __wsflatpak_override_values
    set -l args (__wsflatpak_positional_args)
    test (count $args) -ge 1; and __wsflatpak_catalog values $args[1] $argv[1]
end

function __wsflatpak_managed_remotes
    set -l cfg "$HOME/.local/share/wsconfig/flatpak"
    if set -q WSFLATPAK_CONFIG; and test -n "$WSFLATPAK_CONFIG"
        set cfg "$WSFLATPAK_CONFIG"
    end
    if test -f "$cfg/flatpak.json"
        python3 $__wsflatpak_common get "$cfg/flatpak.json" remotes
    else if command -q flatpak
        flatpak remotes --user --columns=name 2>/dev/null
    end
end

function __wsflatpak_install_apps
    command -q flatpak; or return
    set -l tokens (commandline -opc)
    test "$tokens[-1]" != --remote; or return
    set -l remote flathub
    for index in (seq 3 (count $tokens))
        if test "$tokens[$index]" = --remote; and test $index -lt (count $tokens)
            set remote $tokens[(math "$index + 1")]
        else if string match -q -- '--remote=*' "$tokens[$index]"
            set remote (string replace -- '--remote=' '' "$tokens[$index]")
        end
    end
    flatpak remote-ls --user --cached --app --columns=ref "$remote" 2>/dev/null | while read -l ref
        string split -f1 / -- "$ref"
        echo "app/$ref"
    end
end

complete -c wsflatpak -e
complete -c wsflatpak -f
complete -c wsflatpak -s h -l help -d 'Show help'

complete -c wsflatpak -n __wsflatpak_needs_command -a install -d 'Install apps and runtimes into the home directory'
complete -c wsflatpak -n __wsflatpak_needs_command -a manage -d 'Add an app to the catalog'
complete -c wsflatpak -n __wsflatpak_needs_command -a unmanage -d 'Drop an app from the catalog'
complete -c wsflatpak -n __wsflatpak_needs_command -a remove -d 'Remove an app and its data'
complete -c wsflatpak -n __wsflatpak_needs_command -a uninstall -d 'Alias of remove'
complete -c wsflatpak -n __wsflatpak_needs_command -a permissions -d 'Show the permissions of an app'
complete -c wsflatpak -n __wsflatpak_needs_command -a reset-permissions -d 'Reset overrides and portal permissions'
complete -c wsflatpak -n __wsflatpak_needs_command -a info -d 'Show details of an app'
complete -c wsflatpak -n __wsflatpak_needs_command -a update -d 'Update user apps and runtimes'
complete -c wsflatpak -n __wsflatpak_needs_command -a cleanup -d 'Remove unused runtimes'
complete -c wsflatpak -n __wsflatpak_needs_command -a list -d 'List user apps and runtimes'
complete -c wsflatpak -n __wsflatpak_needs_command -a search -d 'Search apps in remotes'
complete -c wsflatpak -n __wsflatpak_needs_command -a run -d 'Run an app'
complete -c wsflatpak -n __wsflatpak_needs_command -a status -d 'Show the Flatpak state'
complete -c wsflatpak -n __wsflatpak_needs_command -a check -d 'Check against the configuration'
complete -c wsflatpak -n __wsflatpak_needs_command -a test -d 'Check portals, sound and the configuration'
complete -c wsflatpak -n __wsflatpak_needs_command -a apply -d 'Install declared apps and runtimes, apply overrides'
complete -c wsflatpak -n __wsflatpak_needs_command -a filesystem -d 'Declare file access'
complete -c wsflatpak -n __wsflatpak_needs_command -a unfilesystem -d 'Drop a declared file access'
complete -c wsflatpak -n __wsflatpak_needs_command -a host -d 'Declare filesystem=host'
complete -c wsflatpak -n __wsflatpak_needs_command -a unhost -d 'Drop a declared filesystem=host'
complete -c wsflatpak -n __wsflatpak_needs_command -a env -d 'Declare an environment variable'
complete -c wsflatpak -n __wsflatpak_needs_command -a unenv -d 'Drop a declared environment variable'
complete -c wsflatpak -n __wsflatpak_needs_command -a talk -d 'Declare access to a session bus name'
complete -c wsflatpak -n __wsflatpak_needs_command -a untalk -d 'Drop a declared session bus access'
complete -c wsflatpak -n __wsflatpak_needs_command -a remote-add -d 'Print the declaration of a new remote for flatpak/catalog.toml'
complete -c wsflatpak -n __wsflatpak_needs_command -a help -d 'General help or the help of a command'
complete -c wsflatpak -n '__wsflatpak_using_command help; and __wsflatpak_at_position 1' \
    -a 'install manage unmanage remove uninstall permissions reset-permissions info filesystem unfilesystem host unhost env unenv talk untalk remote-add update cleanup list search run check status test apply help' \
    -d 'Help of a command'

for cmd in permissions reset-permissions info run remove uninstall manage filesystem host env talk
    complete -c wsflatpak -n "__wsflatpak_using_command $cmd; and __wsflatpak_at_position 1" -a '(__wsflatpak_user_apps)'
end
complete -c wsflatpak -n '__wsflatpak_using_command unmanage; and __wsflatpak_at_position 1' -a '(__wsflatpak_declared_apps)'
for cmd in unfilesystem unhost unenv untalk
    complete -c wsflatpak -n "__wsflatpak_using_command $cmd; and __wsflatpak_at_position 1" -a '(__wsflatpak_override_apps)'
end

complete -c wsflatpak -n '__wsflatpak_using_command install' -a '(__wsflatpak_install_apps)'
complete -c wsflatpak -n '__wsflatpak_using_command install; and __wsflatpak_at_position 1' -l unmanaged -d 'Do not add to the catalog'
complete -c wsflatpak -n '__wsflatpak_using_command install; and test (count (__wsflatpak_positional_args)) -eq 0' -l remote -x -a '(__wsflatpak_managed_remotes)' -d 'Remote to install from (default flathub)'
complete -c wsflatpak -n '__wsflatpak_using_command manage; and __wsflatpak_at_position 2' -a '(__wsflatpak_managed_remotes)'
complete -c wsflatpak -n '__wsflatpak_using_command run; and __wsflatpak_at_position 1' -l direct -d 'Run with flatpak run instead of the .desktop'
for cmd in remove uninstall
    complete -c wsflatpak -n "__wsflatpak_using_command $cmd" -l keep-data -d 'Keep the data of the app'
end
for cmd in install update cleanup
    complete -c wsflatpak -n "__wsflatpak_using_command $cmd" -s y -l assumeyes -d 'Confirm actions automatically'
    complete -c wsflatpak -n "__wsflatpak_using_command $cmd" -l noninteractive -d 'Run without interactive questions'
end
complete -c wsflatpak -n '__wsflatpak_using_command check' -l json -d 'Print the check result as JSON'
complete -c wsflatpak -n '__wsflatpak_using_command filesystem; and __wsflatpak_at_position 2' -F -a 'host host:ro home home:ro xdg-download xdg-documents xdg-desktop xdg-pictures xdg-videos xdg-music' -d 'Directory and an optional mode :ro/:rw'
complete -c wsflatpak -n '__wsflatpak_using_command unfilesystem; and __wsflatpak_at_position 2' -a '(__wsflatpak_override_values filesystem)'
complete -c wsflatpak -n '__wsflatpak_using_command unenv; and __wsflatpak_at_position 2' -a '(__wsflatpak_override_values env)'
complete -c wsflatpak -n '__wsflatpak_using_command untalk; and __wsflatpak_at_position 2' -a '(__wsflatpak_override_values talk)'
complete -c wsflatpak -n '__wsflatpak_using_command talk; and __wsflatpak_at_position 2' -a 'org.freedesktop.Flatpak org.kde.StatusNotifierWatcher'
complete -c wsflatpak -n '__wsflatpak_using_command apply' -l select -d 'Ask about apps in no of this machine too'
for cmd in filesystem host env talk
    complete -c wsflatpak -n "__wsflatpak_using_command $cmd" -l host -d 'Only for this machine (hosts/HOST/flatpak.toml)'
    complete -c wsflatpak -n "__wsflatpak_using_command un$cmd" -l all -d 'Drop the common value from the catalog (all machines)'
end
