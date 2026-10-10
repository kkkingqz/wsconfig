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

function __wsflatpak_user_apps
    if command -q flatpak
        flatpak list --user --app --columns=application 2>/dev/null
    end
end

function __wsflatpak_config_lines
    string replace -r '#.*$' '' < "$argv[1]"
end

function __wsflatpak_declared_apps
    set -l file (__wsflatpak_repo)/flatpak/apps.txt
    if test -f "$file"
        __wsflatpak_config_lines "$file" | while read -l remote app
            string match -q '#*' -- "$remote"; and continue
            test -n "$app"; and echo (string split ' ' -- "$app")[1]
        end
    end
end

function __wsflatpak_override_apps
    __wsflatpak_user_apps
    set -l file (__wsflatpak_repo)/flatpak/overrides.txt
    if test -f "$file"
        __wsflatpak_config_lines "$file" | while read -l app kind value
            contains -- "$kind" filesystem env talk; and echo "$app"
        end
    end
end

function __wsflatpak_override_values
    set -l args (__wsflatpak_positional_args)
    set -l file (__wsflatpak_repo)/flatpak/overrides.txt
    if test -f "$file"; and test (count $args) -ge 1
        __wsflatpak_config_lines "$file" | while read -l app kind value
            if test "$app" = "$args[1]"; and test "$kind" = "$argv[1]"
                set value (string split ' ' -- "$value")[1]
                if test "$kind" = env
                    string split -m1 -f1 '=' -- "$value"
                else
                    echo "$value"
                end
            end
        end
    end
end

function __wsflatpak_managed_remotes
    set -l cfg "$HOME/.local/share/workstation/flatpak"
    if set -q WSFLATPAK_CONFIG; and test -n "$WSFLATPAK_CONFIG"
        set cfg "$WSFLATPAK_CONFIG"
    end
    if test -f "$cfg/remotes.conf"
        __wsflatpak_config_lines "$cfg/remotes.conf" | while read -l name url
            test -n "$name"; and not string match -q '#*' -- "$name"; and echo "$name"
        end
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
complete -c wsflatpak -s h -l help -d 'Показать справку'

complete -c wsflatpak -n __wsflatpak_needs_command -a install -d 'Установить приложения и runtimes в домашний каталог'
complete -c wsflatpak -n __wsflatpak_needs_command -a manage -d 'Добавить приложение в apps.txt'
complete -c wsflatpak -n __wsflatpak_needs_command -a unmanage -d 'Убрать приложение из apps.txt'
complete -c wsflatpak -n __wsflatpak_needs_command -a remove -d 'Удалить приложение и его данные'
complete -c wsflatpak -n __wsflatpak_needs_command -a uninstall -d 'Алиас remove'
complete -c wsflatpak -n __wsflatpak_needs_command -a permissions -d 'Показать права приложения'
complete -c wsflatpak -n __wsflatpak_needs_command -a reset-permissions -d 'Сбросить overrides и права порталов'
complete -c wsflatpak -n __wsflatpak_needs_command -a info -d 'Показать сведения о приложении'
complete -c wsflatpak -n __wsflatpak_needs_command -a update -d 'Обновить пользовательские приложения и runtimes'
complete -c wsflatpak -n __wsflatpak_needs_command -a cleanup -d 'Удалить ненужные runtimes'
complete -c wsflatpak -n __wsflatpak_needs_command -a list -d 'Список пользовательских приложений и runtimes'
complete -c wsflatpak -n __wsflatpak_needs_command -a search -d 'Поиск приложений в remotes'
complete -c wsflatpak -n __wsflatpak_needs_command -a run -d 'Запустить приложение'
complete -c wsflatpak -n __wsflatpak_needs_command -a status -d 'Показать состояние Flatpak'
complete -c wsflatpak -n __wsflatpak_needs_command -a check -d 'Проверить соответствие конфигурации'
complete -c wsflatpak -n __wsflatpak_needs_command -a test -d 'Проверить порталы, звук и конфигурацию'
complete -c wsflatpak -n __wsflatpak_needs_command -a apply -d 'Установить объявленные приложения, runtimes и применить overrides'
complete -c wsflatpak -n __wsflatpak_needs_command -a filesystem -d 'Объявить доступ к файлам'
complete -c wsflatpak -n __wsflatpak_needs_command -a unfilesystem -d 'Убрать объявленный доступ к файлам'
complete -c wsflatpak -n __wsflatpak_needs_command -a host -d 'Объявить filesystem=host'
complete -c wsflatpak -n __wsflatpak_needs_command -a unhost -d 'Убрать объявленный filesystem=host'
complete -c wsflatpak -n __wsflatpak_needs_command -a env -d 'Объявить переменную окружения'
complete -c wsflatpak -n __wsflatpak_needs_command -a unenv -d 'Убрать объявленную переменную окружения'
complete -c wsflatpak -n __wsflatpak_needs_command -a talk -d 'Объявить доступ к имени session bus'
complete -c wsflatpak -n __wsflatpak_needs_command -a untalk -d 'Убрать объявленный доступ к session bus'
complete -c wsflatpak -n __wsflatpak_needs_command -a remote-add -d 'Показать декларацию нового remote для flatpak.nix'
complete -c wsflatpak -n __wsflatpak_needs_command -a help -d 'Общая справка или справка по команде'
complete -c wsflatpak -n '__wsflatpak_using_command help; and __wsflatpak_at_position 1' \
    -a 'install manage unmanage remove uninstall permissions reset-permissions info filesystem unfilesystem host unhost env unenv talk untalk remote-add update cleanup list search run check status test apply help' \
    -d 'Справка по команде'

for cmd in permissions reset-permissions info run remove uninstall manage filesystem host env talk
    complete -c wsflatpak -n "__wsflatpak_using_command $cmd; and __wsflatpak_at_position 1" -a '(__wsflatpak_user_apps)'
end
complete -c wsflatpak -n '__wsflatpak_using_command unmanage; and __wsflatpak_at_position 1' -a '(__wsflatpak_declared_apps)'
for cmd in unfilesystem unhost unenv untalk
    complete -c wsflatpak -n "__wsflatpak_using_command $cmd; and __wsflatpak_at_position 1" -a '(__wsflatpak_override_apps)'
end

complete -c wsflatpak -n '__wsflatpak_using_command install' -a '(__wsflatpak_install_apps)'
complete -c wsflatpak -n '__wsflatpak_using_command install; and __wsflatpak_at_position 1' -l unmanaged -d 'Не добавлять в apps.txt'
complete -c wsflatpak -n '__wsflatpak_using_command install; and test (count (__wsflatpak_positional_args)) -eq 0' -l remote -x -a '(__wsflatpak_managed_remotes)' -d 'Remote для установки (по умолчанию flathub)'
complete -c wsflatpak -n '__wsflatpak_using_command manage; and __wsflatpak_at_position 2' -a '(__wsflatpak_managed_remotes)'
complete -c wsflatpak -n '__wsflatpak_using_command run; and __wsflatpak_at_position 1' -l direct -d 'Запуск через flatpak run вместо .desktop'
for cmd in remove uninstall
    complete -c wsflatpak -n "__wsflatpak_using_command $cmd" -l keep-data -d 'Сохранить данные приложения'
end
for cmd in install update cleanup
    complete -c wsflatpak -n "__wsflatpak_using_command $cmd" -s y -l assumeyes -d 'Автоматически подтвердить действия'
    complete -c wsflatpak -n "__wsflatpak_using_command $cmd" -l noninteractive -d 'Выполнить без интерактивных вопросов'
end
complete -c wsflatpak -n '__wsflatpak_using_command check' -l json -d 'Вывести результат проверки в JSON'
complete -c wsflatpak -n '__wsflatpak_using_command filesystem; and __wsflatpak_at_position 2' -F -a 'host host:ro home home:ro xdg-download xdg-documents xdg-desktop xdg-pictures xdg-videos xdg-music' -d 'Каталог и необязательный режим :ro/:rw'
complete -c wsflatpak -n '__wsflatpak_using_command unfilesystem; and __wsflatpak_at_position 2' -a '(__wsflatpak_override_values filesystem)'
complete -c wsflatpak -n '__wsflatpak_using_command unenv; and __wsflatpak_at_position 2' -a '(__wsflatpak_override_values env)'
complete -c wsflatpak -n '__wsflatpak_using_command untalk; and __wsflatpak_at_position 2' -a '(__wsflatpak_override_values talk)'
complete -c wsflatpak -n '__wsflatpak_using_command talk; and __wsflatpak_at_position 2' -a 'org.freedesktop.Flatpak org.kde.StatusNotifierWatcher'
complete -c wsflatpak -n '__wsflatpak_using_command apply' -l select -d 'Спросить и о помеченных HOST=no'
