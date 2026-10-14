function fish_title
    set -l cwd (prompt_pwd --dir-length=0)

    if test -n "$argv[1]"
        printf "%s — %s\n" "$cwd" "$argv[1]"
    else
        printf "%s\n" "$cwd"
    end
end
