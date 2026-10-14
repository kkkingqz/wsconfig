# Keyboard layer data: the GNOME shortcuts and input sources of the
# macOS-style profile and the private Tiling Assistant chords. Not dconf.settings: ws-keyboard-apply sets
# the shortcuts only after its preflight and after xremap started (some
# bindings depend on xremap), saves the originals once and `ws-keyboard
# restore` puts them back; home-manager would write them on every switch.
#
# Built for the scripts into ~/.local/share/wsconfig/keyboard/keyboard.json
# (ws help plan-v2, 2.6):
#   shortcuts  [{schema, key, value, kind: required|optional}], value as
#              `gsettings get` prints it; read by ws-keyboard-apply (set,
#              backup, preflight), ws-keyboard check and ws-keyboard status
#   tiling     [{key, binding}], appended by ws-tiling-apply to the Tiling
#              Assistant defaults; checked by ws-keyboard check
#
# The shortcuts are the preset of the core (keyboard/presets/macos.nix);
# keyboard/config.toml (and hosts/HOST/keyboard.toml) chooses the
# preset and the layouts and may override keys of the preset.
# Change: keyboard/config.toml, then `ws apply keyboard` (or `ws apply
# tiling`). The original GNOME values of a key new in the preset are not in
# the existing backup (~/.local/state/wsconfig/keyboard/gsettings-backup.tsv).
{ lib, facts, core, wsHost, wsConfig, ... }:
let
  # GVariant text as it is, for values that are not strings or string arrays.
  raw = text: { gvariant = text; };

  # A container host (boot = "container", ws help plan-wsgnomebox): keys come
  # over RDP from Remmina, which passes them as typed (keyboard/presets/macos-xremap.yml,
  # &vm_consoles); no xremap runs here. GNOME takes what xremap does on a
  # machine: the private CapsLock chords, workspaces, window actions and
  # tiling on the physical keys. Not here: the macOS GUI shortcuts
  # (Command+C in GTK apps), Fn+Ctrl+F/C/R and Fn+Option tiling, Smart
  # Popup on the right modifiers, the Nautilus and terminal remaps.
  rdp = facts.boot == "container";
  bin = "${core}/libexec";
  # NAME = [ BINDING COMMAND ]: GNOME custom shortcuts.
  rdpCommands = {
    ws-caps = [ "<Shift><Control><Alt>space" "${bin}/ws-input-source caps" ];
    ws-ua = [ "<Shift><Control><Alt>u" "${bin}/ws-input-source ua" ];
    ws-task-manager = [ "<Alt><Super>Escape" "${bin}/ws-window task-manager" ];
    ws-hide-current = [ "<Super>h" "${bin}/ws-window hide-current" ];
    ws-hide-others = [ "<Alt><Super>h" "${bin}/ws-window hide-others" ];
    ws-close-current = [ "<Alt><Super>w" "${bin}/ws-window close-current" ];
    ws-minimize-current = [ "<Alt><Super>m" "${bin}/ws-window minimize-current" ];
    ws-logout = [ "<Shift><Super>q" "${bin}/ws-window logout" ];
    ws-logout-now = [ "<Alt><Shift><Super>q" "${bin}/ws-window logout-now" ];
  };
  customDir = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings";
  rdpShortcuts = {
    "org.gnome.settings-daemon.plugins.media-keys".custom-keybindings =
      map (name: "${customDir}/${name}/") (lib.attrNames rdpCommands);
  } // lib.mapAttrs' (name: v: lib.nameValuePair
    "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:${customDir}/${name}/"
    { inherit name; binding = lib.elemAt v 0; command = lib.elemAt v 1; })
    rdpCommands;

  kb = import ./config.nix { inherit lib wsHost wsConfig; };
  keyboard = kb.data;
  inherit (kb) presets;
  preset = import presets.${keyboard.preset} { inherit lib rdp; };

  # The layouts workstation-input-source knows (ws help keyboard): EN first,
  # then RU and UA in any order or not at all.
  knownLayouts = [ "us" "ru" "ua" ];
  layouts = keyboard.layouts;
  layoutProblems =
    lib.optional (layouts == [ ] || lib.head layouts != "us") "layouts must start with \"us\""
    ++ lib.optional (lib.unique layouts != layouts) "layouts has a layout twice"
    ++ map (l: "unknown layout ${l} (layouts: ${lib.concatStringsSep ", " knownLayouts})")
      (lib.filter (l: !(lib.elem l knownLayouts)) layouts);

  # Overrides only of keys the preset sets: the backup and ws keyboard
  # restore know only those.
  unknownOverrides = lib.concatLists (lib.mapAttrsToList (sch: keys:
    map (k: "shortcuts.${sch}.${k}") (lib.filter (k: !((preset.shortcuts.${sch} or { }) ? ${k})) (lib.attrNames keys)))
    (keyboard.shortcuts or { }))
    ++ map (k: "tiling.${k}") (lib.filter (k: !(preset.tiling ? ${k})) (lib.attrNames (keyboard.tiling or { })));
  problems = layoutProblems
    ++ map (k: "${k} is not a key of the preset ${keyboard.preset}") unknownOverrides;

  overridden = lib.recursiveUpdate preset.shortcuts (keyboard.shortcuts or { });
  shortcuts0 = overridden // {
    "org.gnome.desktop.input-sources" = (overridden."org.gnome.desktop.input-sources" or { }) // {
      # In the order of layouts: workstation-input-source switches among them.
      # The installer leaves only its own layout.
      sources = raw ("[" + lib.concatMapStringsSep ", " (l: "('xkb', '${l}')") layouts + "]");
    };
  };
  # media-keys already has screensaver: merged, not replaced.
  shortcuts = lib.recursiveUpdate shortcuts0 (lib.optionalAttrs rdp rdpShortcuts);

  optional = [ "org.gnome.shell.extensions.dash-to-dock/hot-keys" ];

  tiling0 = preset.tiling // (keyboard.tiling or { });
  tiling = tiling0 // lib.optionalAttrs rdp {
    # Over RDP the keys xremap turns into the chords above: Fn+Ctrl+arrows
    # of the Apple keyboard (Ctrl+Home/End/PageUp/PageDown), Ctrl+Super+
    # arrows and Option+Super+E/T of a PC keyboard.
    tile-left-half = tiling0.tile-left-half ++ [ "<Control>Home" "<Control><Super>Left" ];
    tile-right-half = tiling0.tile-right-half ++ [ "<Control>End" "<Control><Super>Right" ];
    tile-top-half = tiling0.tile-top-half ++ [ "<Control>Page_Up" "<Control><Super>Up" ];
    tile-bottom-half = tiling0.tile-bottom-half ++ [ "<Control>Page_Down" "<Control><Super>Down" ];
    tile-edit-mode = tiling0.tile-edit-mode ++ [ "<Alt><Super>e" ];
    toggle-always-on-top = tiling0.toggle-always-on-top ++ [ "<Alt><Super>t" ];
  };

  # GVariant text exactly as `gsettings get` prints it.
  quote = s: "'" + lib.replaceStrings [ "\\" "'" ] [ "\\\\" "\\'" ] s + "'";
  gvariant = v:
    if lib.isAttrs v then v.gvariant
    else if lib.isBool v then lib.boolToString v
    else if lib.isString v then quote v
    else if v == [ ] then "@as []"
    else "[" + lib.concatMapStringsSep ", " quote v + "]";

  shortcutEntries = lib.flatten (lib.mapAttrsToList (schema: keys:
    lib.mapAttrsToList (key: value:
      let
        path = "${lib.replaceStrings [ "." ] [ "/" ] schema}/${key}";
      in
      {
        inherit schema key;
        value = gvariant value;
        kind = if lib.elem path optional then "optional" else "required";
      })
      keys) shortcuts);

  tilingEntries = lib.flatten (lib.mapAttrsToList (key: bindings:
    map (binding: { inherit key binding; }) bindings) tiling);
in
{
  assertions = [{
    assertion = problems == [ ];
    message = "keyboard/config.toml: " + lib.concatStringsSep "; " problems;
  }];

  xdg.dataFile."wsconfig/keyboard/keyboard.json".text = builtins.toJSON {
    shortcuts = shortcutEntries;
    tiling = tilingEntries;
    # xremap.nix takes keyboard/presets/PRESET-xremap.yml of the core unless
    # the configuration has keyboard/xremap.yml (ws keyboard check).
    inherit (keyboard) preset;
  };
}
