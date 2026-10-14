function fzf_cd_browser --description 'Interactive directory browser'
    set -l current $PWD
    set -l marker (mktemp)
    
    while true
        printf '' > $marker
        
        set -l fixed ./
        set -l dirs
        
        if test "$current" != /
            set -a fixed ../
        end
        
        for p in $current/* $current/.*
            if test -d "$p"
                set -l name (path basename "$p")
                
                if test "$name" != "."; and test "$name" != ".."
                    set -a dirs "$name/"
                end
            end
        end
        
        if test (count $dirs) -gt 0
            set dirs (printf '%s\n' $dirs | sort -fu)
        end
        
        set -l item (
            printf '%s\n' $fixed $dirs |
                env \
                                    -u FZF_DEFAULT_OPTS \
                                    -u FZF_DEFAULT_OPTS_FILE \
                                    fzf \
                                        --height=70% \
                                        --layout=reverse \
                                        --border=top \
                                        --no-multi \
                                        --prompt='cd> ' \
                                        --header="$current   Enter: open   ./: select   Ctrl+Enter: select + close   Esc: cancel" \
                                        --bind="alt-enter:execute-silent(printf 1 > $marker)+accept"
        )
        
        set -l fzf_status $status
        
        if test $fzf_status -ne 0
            break
        end
        
        if test -z "$item"
            continue
        end
        
        # ./ = accept currently displayed directory
        if test "$item" = "./"
            cd -- "$current"
            break
        end
        
        # IMPORTANT: define target outside if/else blocks.
        set -l target
        
        if test "$item" = "../"
            set target (path normalize "$current/..")
        else
            set -l name (string replace -r '/$' '' -- "$item")
            set target (path normalize "$current/$name")
        end
        
        if not test -d "$target"
            continue
        end
        
        # Ctrl+Enter -> Ghostty sends Alt+Enter.
        if test -s "$marker"
            cd -- "$target"
            break
        end
        
        # Normal Enter: enter directory but keep browser open.
        set current "$target"
    end
    
    rm -f $marker
    commandline -f repaint
end
