# Keyboard layer data: the GNOME shortcuts and input sources of the
# macOS-style profile and the private Tiling Assistant chords. Not dconf.settings: ws-keyboard-apply sets
# the shortcuts only after its preflight and after xremap started (some
# bindings depend on xremap), saves the originals once and `ws-keyboard
# restore` puts them back; home-manager would write them on every switch.
#
# Built for the scripts into ~/.local/share/workstation/keyboard/:
#   gnome-shortcuts.tsv  SCHEMA<TAB>KEY<TAB>VALUE<TAB>required|optional
#                        VALUE as `gsettings get` prints it; read by
#                        ws-keyboard-apply (set, backup, preflight),
#                        ws-workstation-verify and ws-keyboard-status
#   tiling-bindings.tsv  KEY<TAB>BINDING, appended by ws-tiling-apply to the
#                        Tiling Assistant defaults; checked by verify
#
# Change: edit here, `ws switch`, `ws apply keyboard` (or `ws apply tiling`).
# The original GNOME values of a newly added key are not in the existing
# backup (~/.local/state/workstation/keyboard/gsettings-backup.tsv).
{ lib, ... }:
let
  # GVariant text as it is, for values that are not strings or string arrays.
  raw = text: { gvariant = text; };

  # SCHEMA = { KEY = VALUE; }: list = string array, "" = empty string.
  shortcuts = {
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
      switch-to-workspace-left = [ "<Control><Alt><Super>Left" ];
      switch-to-workspace-right = [ "<Control><Alt><Super>Right" ];

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

    # Exactly EN, RU, UA in this order: workstation-input-source switches
    # among them (helpws keyboard). The installer leaves only its own layout.
    "org.gnome.desktop.input-sources".sources =
      raw "[('xkb', 'us'), ('xkb', 'ru'), ('xkb', 'ua')]";
    # CapsLock selects the layout (xremap); its XKB lock is off in the
    # session. xremap passes Shift/Ctrl/Super+CapsLock through, and every
    # key while it restarts: without caps:none that turned on the real
    # CapsLock. grp_led:scroll is the value GNOME had here before.
    "org.gnome.desktop.input-sources".xkb-options = [ "grp_led:scroll" "caps:none" ];
  };

  optional = [ "org.gnome.shell.extensions.dash-to-dock/hot-keys" ];

  # Private chords emitted by xremap (keyboard/xremap.yml), appended to
  # the Tiling Assistant defaults, never replacing them.
  #   <Shift><Control><Alt><Super>...  Fn+Ctrl+arrows, Fn+Ctrl+F/C/R, Fn+Option+E/T
  #   <Control><Alt><Super>F13..F19    earlier private chords; nothing emits them
  #                                    now, kept so existing setups do not change
  tiling = {
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

  # GVariant text exactly as `gsettings get` prints it.
  quote = s: "'" + lib.replaceStrings [ "\\" "'" ] [ "\\\\" "\\'" ] s + "'";
  gvariant = v:
    if lib.isAttrs v then v.gvariant
    else if lib.isBool v then lib.boolToString v
    else if lib.isString v then quote v
    else if v == [ ] then "@as []"
    else "[" + lib.concatMapStringsSep ", " quote v + "]";

  shortcutsTsv = lib.concatStrings (lib.flatten (lib.mapAttrsToList (schema: keys:
    lib.mapAttrsToList (key: value:
      let
        path = "${lib.replaceStrings [ "." ] [ "/" ] schema}/${key}";
      in
      "${schema}\t${key}\t${gvariant value}\t"
      + (if lib.elem path optional then "optional" else "required") + "\n")
      keys) shortcuts));

  tilingTsv = lib.concatStrings (lib.flatten (lib.mapAttrsToList (key: bindings:
    map (b: "${key}\t${b}\n") bindings) tiling));
in
{
  xdg.dataFile."workstation/keyboard/gnome-shortcuts.tsv".text =
    "# Built from keyboard/keyboard.nix: SCHEMA KEY VALUE required|optional\n"
    + shortcutsTsv;
  xdg.dataFile."workstation/keyboard/tiling-bindings.tsv".text =
    "# Built from keyboard/keyboard.nix: KEY BINDING\n" + tilingTsv;
}
