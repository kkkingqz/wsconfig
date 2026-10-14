function fish_prompt
    set -l last_status $status

    set_color green
    printf "%s@%s" $USER (prompt_hostname)

    set_color normal
    printf " "

    set_color blue
    printf "%s" (prompt_pwd)

    set_color normal
    fish_git_prompt

    if test $last_status -ne 0
        set_color red
        printf " [%d]" $last_status
    end

    if fish_is_root_user
        set_color red
        printf " # "
    else
        set_color green
        printf " ❯ "
    end

    set_color normal
end
