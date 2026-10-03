# Shared foreground lifecycle for interactive Ghostty sessions.
{ ... }:
{
  home.file.".config/fish/functions/__ws_session_color.fish".text = ''
    # Restore at the next prompt too: Ctrl+C can abort a Fish function.
    function __ws_session_color_reset --on-event fish_prompt
        if not set -q __ws_session_color_active
            return
        end
        if test -n "$__ws_session_color_previous"
            printf '\x1b]10;%s\x1b\x5c' "$__ws_session_color_previous"
            set -gx WS_TERMINAL_FOREGROUND "$__ws_session_color_previous"
        else
            printf '\x1b]110\x1b\x5c'
            set -e WS_TERMINAL_FOREGROUND
        end
        set -e __ws_session_color_active __ws_session_color_previous
    end

    function __ws_session_color
        # Arguments: color, executable, then its original arguments.
        if test "$TERM_PROGRAM" != ghostty; or not isatty stdin; or not isatty stdout
            command $argv[2..-1]
            return $status
        end

        set -g __ws_session_color_previous ""
        if string match -rq '^#[[:xdigit:]]{6}$' -- "$WS_TERMINAL_FOREGROUND"
            set -g __ws_session_color_previous "$WS_TERMINAL_FOREGROUND"
        end
        # Distrobox forwards this variable to nested shells. Internal cleanup
        # state is local to this Fish process and is never exported.
        set -gx WS_TERMINAL_FOREGROUND "$argv[1]"
        set -g __ws_session_color_active 1
        printf '\x1b]10;%s\x1b\x5c' "$argv[1]"
        command $argv[2..-1]
        set -l session_status $status
        __ws_session_color_reset
        return $session_status
    end
  '';
}
