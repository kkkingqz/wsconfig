# The macOS-style keyboard preset of the core (ws help keyboard): the GNOME
# shortcuts and the private Tiling Assistant chords that keyboard/xremap.yml
# and ws-input-source rely on; they change together. keyboard.nix takes the
# layouts and the overrides of keyboard/config.toml over it.
#   shortcuts  SCHEMA = { KEY = VALUE; }: list = string array, "" = empty
#              string
#   optional   SCHEMA/KEY that may be missing (ws-keyboard-apply skips them)
#   tiling     KEY = [ BINDING ... ], appended to the Tiling Assistant
#              defaults
# rdp: a container host, where the keys come over RDP (keyboard.nix).
{ lib, rdp }:
let
  shortcuts0 = {
    "org.gnome.desktop.wm.keybindings" = {
      # Application / window switching
      switch-applications = [ "<Super>Tab" ];
      switch-applications-backward = [ "<Shift><Super>Tab" ];
      switch-group = [ "<Super>Above_Tab" "<Control>Down" ];
      switch-group-backward = [ "<Shift><Super>Above_Tab" ];

      # Window actions
      minimize = [ "<Super>m" ];
      toggle-fullscreen = [ "<Control><Super>f" ];
      show-desktop = [ "F11" ];

      # Workspaces. Physical Ctrl+Left/Right are translated by xremap into
      # these private chords, leaving emitted application Ctrl+Left/Right
      # unclaimed by GNOME.
      switch-to-workspace-left = [ "<Control><Alt><Super>Left" ]
        # Over RDP: physical Ctrl+Left/Right, as xremap makes them.
        ++ lib.optional rdp "<Control>Left";
      switch-to-workspace-right = [ "<Control><Alt><Super>Right" ]
        ++ lib.optional rdp "<Control>Right";

      # Input sources
      switch-input-source = [ "<Control>space" ];
      switch-input-source-backward = [ "<Control><Alt>space" ];
    };

    "org.gnome.shell.keybindings" = {
      # Overview / Spotlight-style search
      toggle-overview = [ "<Super>space" "<Control>Up" ];

      # Free GNOME Shell Super-letter shortcuts that conflict with macOS
      # application semantics; otherwise GNOME Shell consumes the event
      # before xremap/Ghostty can see it.
      toggle-application-view = [ ];
      toggle-message-tray = [ ];
      toggle-quick-settings = [ ];
      focus-active-notification = [ ];

      # Screenshots
      screenshot = [ "<Shift><Super>3" ];
      show-screenshot-ui = [ "<Shift><Super>4" "<Shift><Super>5" ];
    }
    # Free Super+number from GNOME Shell / Ubuntu Dock: needed for
    # macOS-style Shift+Super+3/4/5 screenshots and leaves Command/Win+number
    # to applications.
    // lib.genAttrs (map (n: "switch-to-application-${toString n}") (lib.range 1 9))
      (_: [ ]);

    # Make Super a pure modifier: macOS Command alone does nothing, and no
    # accidental Overview after Command/Win+Arrow remaps.
    "org.gnome.mutter".overlay-key = "";

    # Lock screen. Some GNOME builds use a string here; ws-keyboard-apply
    # then sets the first element.
    "org.gnome.settings-daemon.plugins.media-keys".screensaver = [ "<Control><Super>q" ];

    # Ubuntu Dock numeric hot keys (Super+number); only where the Dock has it.
    "org.gnome.shell.extensions.dash-to-dock".hot-keys = false;

    # CapsLock selects the layout (xremap); its XKB lock is off in the
    # session. xremap passes Shift/Ctrl/Super+CapsLock through, and every
    # key while it restarts: without caps:none that turned on the real
    # CapsLock. grp_led:scroll is the value GNOME had here before.
    "org.gnome.desktop.input-sources".xkb-options = [ "grp_led:scroll" "caps:none" ];
  };

  # Private chords emitted by xremap (keyboard/xremap.yml), appended to
  # the Tiling Assistant defaults, never replacing them.
  #   <Shift><Control><Alt><Super>...  Fn+Ctrl+arrows, Fn+Ctrl+F/C/R, Fn+Option+E/T
  #   <Control><Alt><Super>F13..F19    earlier private chords; nothing emits them
  #                                    now, kept so existing setups do not change
  tiling0 = {
    tile-left-half = [ "<Shift><Control><Alt><Super>Left" "<Control><Alt><Super>F13" ];
    tile-right-half = [ "<Shift><Control><Alt><Super>Right" "<Control><Alt><Super>F14" ];
    tile-top-half = [ "<Shift><Control><Alt><Super>Up" "<Control><Alt><Super>F15" ];
    tile-bottom-half = [ "<Shift><Control><Alt><Super>Down" "<Control><Alt><Super>F16" ];
    tile-maximize = [ "<Shift><Control><Alt><Super>f" "<Control><Alt><Super>F17" ];
    center-window = [ "<Shift><Control><Alt><Super>c" "<Control><Alt><Super>F18" ];
    restore-window = [ "<Shift><Control><Alt><Super>r" "<Control><Alt><Super>F19" ];
    tile-edit-mode = [ "<Shift><Control><Alt><Super>e" ];
    toggle-always-on-top = [ "<Shift><Control><Alt><Super>t" ];
  };
in
{
  shortcuts = shortcuts0;
  optional = [ "org.gnome.shell.extensions.dash-to-dock/hot-keys" ];
  tiling = tiling0;
}
