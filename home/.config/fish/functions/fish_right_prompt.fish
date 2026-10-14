function fish_right_prompt
    set -l duration $CMD_DURATION

    if test -n "$duration"; and test "$duration" -ge 2000
        set_color brblack
        printf "%.1fs" (math "$duration / 1000")
        set_color normal
    end
end
