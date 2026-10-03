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
  # Ghostty's packaged launcher enables ssh-env. Its deferred first-prompt
  # setup defines `ssh` after autoloaded user functions. Compose with that
  # transport instead of losing either its integration or our session color.
  home.file.".config/fish/conf.d/ssh-colors.fish".text = ''
    if not status is-interactive
        return
    end

    function __ws_ssh_color_install --on-event fish_prompt --on-event fish_preexec
        # Nested definitions in Ghostty report their source as "stdin" in
        # Fish, so identify the upstream wrapper by its function description.
        set -l details (functions --details --verbose ssh)
        if contains -- 'SSH wrapper with Ghostty integration' $details
            functions --erase __ws_ssh_transport
            functions --copy ssh __ws_ssh_transport
            source "$__fish_config_dir/functions/ssh.fish"
        end
    end
    __ws_ssh_color_install
  '';

  home.file.".config/fish/functions/__ws_ssh_transport.fish".text = ''
    function __ws_ssh_transport
        command ssh $argv
    end
  '';

  home.file.".config/fish/functions/ssh.fish".text = ''
    if not status is-interactive
        return
    end

    function ssh --wraps ssh --description 'SSH with Ghostty session colors'
        # Keep pipes, files, scripts and other terminal emulators untouched.
        if test "$TERM_PROGRAM" != ghostty; or not isatty stdin; or not isatty stdout
            __ws_ssh_transport $argv
            return $status
        end

        # OpenSSH resolves Host aliases and options without connecting.
        set -l host (command ssh -G $argv 2>/dev/null |
            string match -r '^hostname .*' |
            string replace -r '^hostname ' "" |
            string lower |
            string replace -r '\.$' "")

        if test -z "$host"
            __ws_ssh_transport $argv
            return $status
        end

        set -l color '${colors.default}'
        switch "$host"
            case tower.local 192.168.113.113
                set color '${colors.tower}'
        end

        __ws_session_color "$color" --function __ws_ssh_transport $argv
    end
  '';
}
