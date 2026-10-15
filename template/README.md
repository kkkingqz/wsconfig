# Workstation configuration

The data of a workstation set up with wsconfig (github:kkkingqz/wsconfig):
the core (`ws`, its modules and tools) is the flake input `wsconfig`,
pinned by flake.lock (`ws update core`); this repository holds what is the
user's. `ws setup --new` made it from the template of the core.

- `wsconfig.toml`: the schema version the core reads
- `hosts/HOST/`: host.toml (facts), apt.txt, the choices of the catalogs
  (flatpak.toml, boxes.toml, widgets.toml) and the host files of the
  modules (gnome.toml, keyboard.toml, terminal.toml, backup.toml)
- `apt.txt`: apt packages on every host, on top of what the core needs
- `flatpak/`, `distrobox/`, `windows/`, `gnome/`, `keyboard/`,
  `terminal/`: catalogs and settings of the modules (TOML; their comments
  say the keys)
- `home/`: personal settings, mirroring $HOME; every tracked file home/P is
  a link ~/P into this checkout
- `backup/config.toml`: the backup target, if set (ws help backup)

`ws apply` builds and applies it, `ws sync` publishes what changed. Help:
`ws help`, the architecture: `ws help architecture-v2`.
