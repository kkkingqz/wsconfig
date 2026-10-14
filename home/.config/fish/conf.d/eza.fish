if type -q eza
    function ls --wraps=eza
        command eza --icons=auto --hyperlink --group-directories-first $argv
    end

    function ll --wraps=eza
        command eza -lh --icons=auto --hyperlink --group-directories-first --git $argv
    end

    function la --wraps=eza
        command eza -lah --icons=auto --hyperlink --group-directories-first --git $argv
    end

    function lt --wraps=eza
        command eza --tree --level=2 --icons=auto --hyperlink --group-directories-first $argv
    end
end
