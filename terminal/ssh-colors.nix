# SSH session foreground colors. Home Manager generates the Fish configuration;
# change these values here, then run `ws switch`.
{ ... }:
let
  colors = {
    tower = "#FFE066";
    default = "#FFB3B3";
  };
in
{
  home.file.".config/fish/functions/ssh.fish".text = ''
    if not status is-interactive
        return
    end

    function ssh --wraps ssh --description 'SSH with Ghostty session colors'
        # Keep pipes, files, scripts and other terminal emulators untouched.
        if test "$TERM_PROGRAM" != ghostty; or not isatty stdin; or not isatty stdout
            command ssh $argv
            return $status
        end

        # OpenSSH resolves Host aliases and options without connecting.
        set -l host (command ssh -G $argv 2>/dev/null |
            string match -r '^hostname .*' |
            string replace -r '^hostname ' "" |
            string lower |
            string replace -r '\.$' "")

        if test -z "$host"
            command ssh $argv
            return $status
        end

        set -l color '${colors.default}'
        switch "$host"
            case tower.local 192.168.113.113
                set color '${colors.tower}'
        end

        __ws_session_color "$color" ssh $argv
    end
  '';
}
