# Distrobox foreground colors. Change these here, then run `ws switch`.
{ lib, ... }:
let
  defaultColor = "#FFB3B3";
  colors = {
    arch = "#8BE9FD";
    wine-wayland = "#C4A7E7";
    wine = "#FFB86C";
    proton = "#A6E3A1";
    t2bce-build = "#89B4FA";
    touchbar-build = "#F5C2E7";
  };

  cases = lib.concatStringsSep "\n" (lib.mapAttrsToList (name: color: ''
    case ${name}
        set color '${color}'
  '') colors);

  wrapper = program: subcommand: ''
    if not status is-interactive
        return
    end
    function ${program} --wraps ${program}
      ${if subcommand then ''
        if test "$argv[1]" = enter
            __ws_distrobox_color ${program} $argv
        else
            command ${program} $argv
        end
      '' else ''
        __ws_distrobox_color ${program} $argv
      ''}
    end
  '';
in
{
  home.file = {
    ".config/fish/functions/distrobox.fish".text = wrapper "distrobox" true;
    ".config/fish/functions/distrobox-enter.fish".text = wrapper "distrobox-enter" false;
    ".config/fish/functions/wsbox.fish".text = wrapper "wsbox" true;
    ".config/fish/functions/__ws_distrobox_color.fish".text = ''
      function __ws_distrobox_color
          set -l program "$argv[1]"
          set -l args $argv[2..-1]
          set -l enter_args $args
          if contains -- "$program" distrobox wsbox
              set enter_args $args[2..-1]
          end

          set -l box "$DBX_CONTAINER_NAME"
          if test "$program" = wsbox
              set box "$enter_args[1]"
          else
              set -l i 1
              while test $i -le (count $enter_args)
                  switch "$enter_args[$i]"
                      case -- -e --exec
                          break
                      case -h --help -V --version -d --dry-run -T -H --no-tty
                          command "$program" $args
                          return $status
                      case -n --name
                          set i (math $i + 1)
                          set box "$enter_args[$i]"
                      case -a --additional-flags
                          set i (math $i + 1)
                      case '-*'
                          # Remaining switches take no separate value.
                      case '*'
                          set box "$enter_args[$i]"
                  end
                  set i (math $i + 1)
              end
          end

          set -l color '${defaultColor}'
          switch "$box"
              ${cases}
          end
          __ws_session_color "$color" "$program" $args
      end
    '';
  };
}
