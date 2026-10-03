title: ws-workstation
section: 1
date: 2026-09-28
source: Workstation
volume: User Commands

# UBUNTU T2 WORKSTATION

**Платформа:** MacBook Pro 16" 2019 (`MacBookPro16,1`, Intel/T2)

> Текущее рабочее состояние workstation подробно. Слои и правила —
> `helpws layers`, проверки — `helpws checks`, терминал — `helpws terminal`.

---

# PLATFORM

- **Ubuntu 26.04.1 LTS**
- **GNOME 50**
- **Wayland**
- **GDM3**
- **rEFInd** как основное boot menu
- T2 kernel: `7.2.7-1-t2-resolute` (+ локально исправленный `t2bce`, см. `helpws suspend`)
- Generic-ядро Ubuntu удалено (2026-10-02); запасной путь — GRUB и снапшоты Timeshift
- Secure Boot отключён для T2 Linux

---

# FILESYSTEM / RECOVERY

Root работает на **Btrfs**.

## Subvolumes

```text
@
@home
@cache
@tmp
@log
@nix          /nix: Nix store, отдельно от @ (откат @ не трогает /nix)
@vms          /var/lib/vms: состояние VM (диски, UEFI, TPM, XML), вне snapshots @
@swap         /swap: swapfile 32G для hibernate (swapfile нельзя в томе со snapshots)
timeshift-btrfs  snapshots Timeshift (@, @home); создаёт Timeshift
```

## Root boot

```text
rootflags=subvol=@
```

rEFInd берёт ядро из default subvolume (`@`, по ID). Snapshots и откат —
Timeshift (`@`, `@home`), загрузка в snapshot — GRUB, после restore хук
переставляет default на новый `@` (`helpws rebuild`, раздел 12).

---

# GNOME DESKTOP

Используется максимально штатный Ubuntu/GNOME stack:

```text
GDM3
  ↓
GNOME Shell + Mutter
  ↓
Wayland
```

Работают:

- Ubuntu Dock;
- Quick Settings;
- GNOME Settings;
- Nautilus;
- notifications и OSD;
- NetworkManager integration;
- Bluetooth integration;
- PipeWire / WirePlumber;
- XWayland для legacy applications.

Extensions, являющиеся частью текущего workstation baseline:

```text
xremap@k0kubun.com
window-control@carlo9890.github.io
Tiling Assistant
workstation-smart-popup@local
workstation-dock-spring@local
workstation-input-source@local
workstation-hibernate@local
```

`Window Monitor Pro` используется и входит в baseline расширений; keyboard/Touch Bar
baseline от него не зависит.

---


# GNOME MANAGED APPEARANCE

Штатный GNOME appearance/Dock baseline хранится декларативно в
`dconf.settings` home-manager и записывается `ws switch`:

```text
gnome/gnome.nix
```

Управление:

```console
ws-gnome status
ws-gnome check
```

Текущий профиль фиксирует небольшой curated набор appearance и Ubuntu Dock
settings. Он намеренно **не** управляет:

```text
display scale / monitors.xml
Mutter experimental-features
input sources / shortcuts
GNOME extension enablement
wallpaper
Flatpak / Distrobox / Wine settings
```

Фактический scale встроенного display сейчас `1.5`; он выбран через GNOME
Settings и остаётся inventory-only.

Интеграция приложений — у их слоёв:

```text
Flatpak theme / scale / portals  -> helpws flatpak
Distrobox GUI / Wayland / Qt     -> helpws distrobox
Wine                             -> helpws windows, только внутри Distrobox
```

Wine на host не устанавливается.

Подробности:

```console
helpws gnome
```

---


# HOST QT INTEGRATION

Host Qt applications используют штатную GNOME/Wayland integration:

```text
qgnomeplatform-qt5
qgnomeplatform-qt6
qtwayland5
qt6-wayland
```

Qt5 и Qt6 автоматически используют native Wayland и GNOME dark appearance.
Глобальные `QT_QPA_PLATFORM`, `QT_QPA_PLATFORMTHEME`, `QT_STYLE_OVERRIDE` и
`QT_SCALE_FACTOR` не задаются.

Это относится только к host applications; Qt в контейнерах этим не
настраивается.

---

## Dock spring loading

При внешнем file drag (например, из Nautilus) используется локальный extension:

```text
workstation-dock-spring@local
```

Поведение:

```text
hover running Dock app  1300 ms -> existing window comes forward
minimized app            existing window restores/focuses
other workspace          existing window/workspace activates
closed app               nothing happens; application is not launched
```

Extension не перехватывает сам drop и не патчит Ubuntu Dock или Desktop Icons
NG.

Dock Spring behavior:

```text
running/minimized app + external file hover ~1.3 s -> existing window focuses
closed app + hover                              -> no action
```

# KEYBOARD / SHORTCUTS

Используется финальный macOS-style semantic profile для Apple и PC keyboards:

```text
Apple Command = PC Win = Super
Apple Option  = PC Alt = Alt
Apple Control = PC Ctrl = Ctrl
```

Архитектура:

```text
GNOME/Mutter                    system shortcuts
xremap                          application/Fn/Nautilus mappings
workstation-input-source@local  EN/RU/UA + Caps + unlock-dialog/overview EN
workstation-smart-popup@local   Smart Tiling Popup
Window Control                  application/window actions
Tiling Assistant                tiling backend
Ghostty                         terminal-safe Super layer
```

Подтверждённые input-source rules:

```text
CapsLock             EN <-> RU; UA -> EN
Fn+CapsLock          UA
Control+Space        EN -> RU -> UA -> EN
Control+Alt+Space    reverse cycle
GDM/login            EN only
GNOME lock screen    EN only
```

Source of truth:

```text
keyboard/
terminal/ghostty/

bin/ws-keyboard*
bin/ws-xremap
bin/ws-window
bin/ws-nautilus-current
bin/ws-input-source
bin/ws-caps-led
bin/ws-tiling-apply
bin/ws-keyboard-check

gnome/extensions/workstation-input-source@local/
gnome/extensions/workstation-smart-popup@local/
gnome/extensions/workstation-dock-spring@local/
gnome/extensions/workstation-hibernate@local/

keyboard/xremap.nix
system/files/udev/99-workstation-uinput.rules

system/files/udev/90-touchbar-native.rules
system/files/modprobe/
system/files/usr/local/libexec/ws-touchbar-fn
system/files/systemd/system/ws-touchbar-fn.service
```

Generated `gschemas.compiled` не является source file и не коммитится. Machine-local state (backup сочетаний GNOME, флаг выключенного
xremap) — в `~/.local/state/workstation/`, не в checkout.

Полный справочник:

```console
helpws keyboard
```

Полная проверка:

```console
ws check
```

---

# T2 HARDWARE

Работают:

- keyboard;
- trackpad;
- Wi‑Fi;
- Bluetooth;
- T2 audio;
- microphone;
- camera;
- Touch Bar;
- suspend/resume.

T2 hardware обслуживается T2Linux kernel stack.

USB-контроллеры Thunderbolt (`09:00.0`, `7f:00.0`, `8086:15ec`) держатся
вне runtime suspend правилом `71-tb-xhci-awake.rules`. Драйвер
`thunderbolt` пишет `device links to tunneled native ports are missing!` и
не будит уснувший xHCI при подключении, поэтому USB 3-часть устройства
(хаб, сетевая карта AX88179A) не появлялась: видна была только USB 2-часть
на PCH xHCI `00:14.0`. Проверка: `cat /sys/bus/pci/devices/0000:09:00.0/power/control`
должно быть `on`.

`ws-tb-acpi-seed.service` при загрузке читает регионы ACPI Thunderbolt,
чтобы ACPICA запомнила их настоящие адреса PCI: иначе `_PS0` прошивки при
каждом resume опрашивает хост-мост и выход из сна занимает ~23 с вместо
~3 с (helpws suspend, Thunderbolt).

---

# GRAPHICS

```text
Intel UHD 630      → primary GPU
AMD Radeon dGPU    → render/offload GPU
```

Intel используется для desktop: `apple-gmux force_igd=y` переключает панель
на Intel, gnome-shell и все приложения рисуют на нём. Когда AMD включена
(«Ubuntu (AMD)»), она доступна через GPU offload (`switcherooctl launch`,
«Запустить с дискретной видеокартой»).

Яркость встроенного экрана сохраняет штатная служба
`systemd-backlight@backlight:gmux_backlight.service`. У `gmux_backlight`
родитель на шине PNP: `path_id` не определяет его путь, и стандартное
правило `99-systemd.rules` пропускает запуск службы. Правило
`system/files/udev/99-z-gmux-backlight.rules` запускает её без `path_id`;
оно устанавливается профилем `t2-mbp16` через `ws system apply`.
При apply служба также перезапускается для текущего сеанса. Уровень
сохраняется при выключении в
`/var/lib/systemd/backlight/backlight:gmux_backlight` и восстанавливается
при загрузке. Проверка: `ws system check`, затем изменить яркость и
перезагрузиться; статус службы —
`systemctl status systemd-backlight@backlight:gmux_backlight.service`.

Runtime PM у amdgpu на этом Mac нет (`Runtime PM not available`: ни ATPX, ни
ACPI `_PR3`, ни BACO), поэтому включённая AMD постоянно в D0. Выключают её
при загрузке: в пункте «Ubuntu» `amdgpu` не загружается вовсе
(`modprobe.blacklist=amdgpu`), `ws-dgpu-off` убирает карту с шины PCI, и gmux
снимает с неё питание. Способ выбирается пунктом rEFInd:

```text
Ubuntu          ws.dgpu=off modprobe.blacklist=amdgpu → ws-dgpu-off.service убирает AMD с шины PCI и снимает питание до GDM
Ubuntu (AMD)    AMD включена: внешние мониторы, GPU offload
macOS
Recovery        GRUB, AMD включена
```

- Без AMD **не работают внешние мониторы**: все Thunderbolt DP выведены на
  dGPU (`card2-DP-4…7`). Для монитора загрузиться в «Ubuntu (AMD)».
- Выключение только при загрузке: карта, убранная с шины, до перезагрузки не
  возвращается (её PCIe-коммутатор теряет конфигурацию с питанием).
- Без `amdgpu` (с 2026-10-01): раньше `ws-dgpu-off` ждал полной инициализации
  `amdgpu` (~9 с, из них ~4,5 с повторов AUX на разъёме `eDP-2`, панель
  переключена на i915) только чтобы выключить карту через vga_switcheroo, и
  GDM ждал его. Теперь скрипт за ~0,8 с убирает пакет Navi 14
  (`01:00.0`–`03:00.1`) с шины, пока карта включена, снимает питание портом
  gmux `0x50` (как `apple-gmux` при vga_switcheroo OFF) и паркует порт CPU:
  пользовательская часть загрузки 20,5 → 9,6 с, PC7 ~78 %. Без `amdgpu` на
  шине S3 тоже не ломается. Подробности — `helpws suspend`.
- `default_selection +`: rEFInd предлагает пункт прошлой загрузки.
- «Ubuntu (AMD)» — ручной пункт в `system/files/esp/refind.conf` (шаблон).
  Он грузит
  `/boot/ws/vmlinuz` и `/boot/ws/initrd.img`, жёсткие ссылки на новейшее ядро и
  его initrd (rEFInd не следует по symlink). Их обновляет `ws-boot-links` из
  `/etc/kernel/postinst.d`, `/etc/kernel/postrm.d` и
  `/etc/initramfs/post-update.d`; первый раз — `ws system apply`.
- Параметры ядра всех пунктов — из `nix/hosts/mbp16/facts.nix`
  (`kernelParams`, `rootUuid`): `refind_linux.conf`, GRUB (`grub.d`) и
  `@AMD_OPTIONS@` в `refind.conf` собираются из них; «Ubuntu» добавляет
  `refindDefaultParams` (`ws.dgpu=off`). Править только `facts.nix`.
- «Ubuntu» с `ws.dgpu=off` проверен, включая S3 (`helpws suspend`);
  «Ubuntu (AMD)» загружается, Proton и Steam в нём работают на AMD; S3 в
  нём не проверялся.
- `refind.conf` лежит на отдельном ESP (`nvme0n1p3`), `ws system apply` его не
  ставит; копируется собранный (`ws system check` сравнивает его, когда ESP
  смонтирован):

```bash
sudo mount /dev/disk/by-partuuid/b3575417-21a5-43db-9c6e-dc2dd5510c76 /mnt
sudo cp /mnt/EFI/BOOT/refind.conf /mnt/EFI/BOOT/refind.conf.bak
sudo cp "$(ws system tree)/esp/EFI/BOOT/refind.conf" /mnt/EFI/BOOT/refind.conf
ws system check
sudo umount /mnt
```

Проверка: `journalctl -b -u ws-dgpu-off` (`DIS: :Off`, затем
`dGPU powered off; 0000:01:00.0 and everything below it removed from PCI`) и
`lspci -d 1002:` — пусто. Перед удалением скрипт проверяет, что
конфигурационное пространство карты читается как `ff ff`, то есть питание
снято: `power_state` для этого не годится, он остаётся `D3hot` (ACPI power
resource у dGPU нет, ядро не знает, что gmux снял питание).
В простое от батареи (2026-10-01, после forced ASPM и парковки порта): около
9 Вт с экраном на 28 %, 4 Вт с погашенным; с включённой AMD было около 24 Вт.

---

# SUSPEND / POWER

Рабочий режим:

```text
deep / S3, после 24 ч — hibernate (suspend-then-hibernate)
крышка, Suspend          suspend-then-hibernate
кнопка питания, Hibernate  hibernate
```

Слой сна:

```text
80-deep-only.conf          только S3, без отката на s2idle
Broadcom ASPM guard        ASPM Wi-Fi off на время сна, без D3cold
t2bce 0.07-nostatefix1     отказ T2 от stateful suspend не роняет ядро
Touch Bar родной режим     без appletbdrm / tiny-dfr
ws-t2-detach               стек T2 снят на время hibernate (у t2bce нет колбэков hibernation)
/swap/swapfile 32G         resume= / resume_offset= в facts.nix
```

ASPM в пункте «Ubuntu» у ядра (`pcie_aspm=force pcie_aspm.policy=powersave`,
с 2026-10-01): прошивка оставляет Thunderbolt без ASPM. Отказы T2 2026-09-22…25
были с forced ASPM, но и с Touch Bar в режиме дисплея (`helpws suspend`,
ASPM). Порт CPU выключенной AMD паркуется как в macOS (`ws-dgpu-park`).

Управление и подробности:

```console
ws-suspend status
helpws suspend
```

Дополнительный агрессивный power tuning сейчас не используется.

---

# TOUCH BAR

Родной режим: кнопки рисует T2, режимом управляет `hid-appletb-kbd`.
Touch Bar закреплён в USB configuration 1, `appletbdrm` не загружается.

```text
/etc/modprobe.d/tb.conf                      mode=1 fntoggle=1 autodim=1 ...
/etc/modprobe.d/touchbar-native.conf         blacklist appletbdrm
/etc/udev/rules.d/90-touchbar-native.rules   USB configuration 1
ws-touchbar-fn.service                       Fn bridge за xremap
```

Текущий режим:

```text
normal       F1..F12
hold Fn      media / brightness
release Fn   F1..F12
```

xremap пропускает `KEY_FN` (`skip_key_event: false`) и одновременно использует
Fn для своего Apple `apple_fn` mode. `ws-touchbar-fn` слушает Fn на
`workstation-xremap` и переключает `hid-appletb-kbd` mode 1/2.

`tiny-dfr` (режим дисплея Touch Bar, `appletbdrm`) не используется: все
сбои suspend на этой машине случились в режиме дисплея
(`helpws history-suspend`).

Подробности:

```console
helpws touchbar
```

---

# APPLICATION ARCHITECTURE

```text
Host
├── kernel / drivers / GNOME / network / audio / virtualization
│   └── apt
│
├── ordinary GUI applications
│   └── Flatpak
│
├── development / toolchains
│   └── Distrobox + Podman
│
└── Windows applications
    └── separate Wine environments / prefixes
```

Host сознательно не используется как общий development environment.

## Managed Distrobox layer

Source of truth:

```text
distrobox/distrobox.nix                контейнеры и экспорты
system/files/modules-load.d/ntsync.conf         ставит ws system apply
distrobox/arch/wsbox-host-ntsync/  PKGBUILD NTSYNC-MODULE для Arch-контейнеров
distrobox/arch/*-hook, wine/       хуки установки Windows-контейнеров
windows/apps.nix                   Windows-программы с launcher (helpws windows)
bin/wsbox, bin/wswin, bin/ws-gpu
```

Контейнеры объявлены в `distrobox/distrobox.nix` (общие
значения по умолчанию, у контейнера — только образ, HOME, пакеты,
экспорты). `ws switch` собирает из них `containers.ini` (формат
`distrobox assemble`) и `exports.ini` в `~/.local/share/workstation/distrobox/`,
`wsbox` читает оттуда. Изменение: правка `distrobox.nix`, `ws switch`,
затем `wsbox apply NAME` или `wsbox recreate NAME`.

Managed containers:

```text
arch     Arch rolling (archlinux:latest) / AUR applications
wine-wayland  Arch, Wine с Wayland-драйвером: Windows-программы по умолчанию; WinBox 3.x
wine     Ubuntu релиза хоста, WineHQ stable, XWayland
proton   Arch, umu-launcher + Proton: игры, AMD при наличии (helpws windows)
t2bce-build     Ubuntu релиза хоста, сборка ядра/модулей вручную (kernel headers с хоста)
touchbar-build  Ubuntu релиза хоста, порт Touch Bar (~/touchbar): dev-пакеты DRM/Wayland,
                Rust (rustup) в HOME контейнера: ~/.rustup, ~/.cargo
```

У каждого контейнера свой persistent HOME — `~/distrobox/<имя>/` (так же
для новых); HOME хоста смонтирован в контейнер по своему пути, исходники
(`~/touchbar`) видны как `/home/<user>/touchbar`. Rootfs считается disposable: пакеты — `packages` контейнера
в `distrobox.nix` (`additional_packages` в собранном `containers.ini`).

Образы — теги, не digest. Пакеты внутри обновляет `wsbox update [NAME...]`
(`distrobox upgrade`: apt в Ubuntu, pacman в Arch; AUR — вручную `paru`);
новый образ берётся только при `wsbox recreate NAME`: rootfs пересоздаётся,
HOME остаётся, пакеты из AUR в `arch` ставятся заново (`helpws rebuild`,
раздел 6.3). Build-контейнеры берут релиз Ubuntu хоста (`@HOST_VERSION_ID@`
в `distrobox.nix`, `wsbox` подставляет `VERSION_ID` из `/etc/os-release`):
то, что в них собирается, должно совпадать с хостом. После обновления
Ubuntu `wsbox check` покажет image drift — `wsbox recreate NAME`. Закрепить
образ: `repo@sha256:…` в `distrobox.nix`, `wsbox check` сверит repo digest.

Arch-контейнеры (`arch`, `wine-wayland`, `proton`) используют NTSync из host
T2 kernel. Host загружает `ntsync`, а `wsbox-host-ntsync` внутри Arch только
удовлетворяет virtual dependency `NTSYNC-MODULE`, поэтому container-local
`linux`/`mkinitcpio` не нужны.

Управление и проверка:

```console
wsbox status
wsbox apps
wsbox check
wsbox apply [NAME]
```

Windows-программы, prefixes, `wswin`, Steam: `helpws windows`. WinBox —
prefix `winbox` в `wine-wayland` (переживает destructive rebuild):

```text
~/distrobox/wine-wayland/prefixes/winbox
LogPixels = 0x90 = 144 DPI = 150%
```

Подробности:

```console
helpws distrobox
```

---

# TERMINAL ENVIRONMENT

## Ghostty

Основной лёгкий terminal:

```text
Ghostty 1.3.0
GTK4 / libadwaita
Wayland
OpenGL renderer
```

Визуальный baseline:

```ini
theme = Desert
background-opacity = 0.90
```

Работают:

- tabs;
- splits;
- search;
- scrollback;
- clipboard protection;
- URL handling;
- shell integration;
- cwd inheritance для tabs/splits/windows;
- notifications после долгих команд в unfocused surfaces;
- physical layout-independent hotkeys.

Конфиги:

```text
~/.config/ghostty/config.ghostty
~/.config/ghostty/behavior.ghostty
~/.config/ghostty/keybinds.ghostty
~/.config/ghostty/shell-keys.ghostty
```

## Fish

Основной interactive shell:

```text
fish 4.9.3
```

Установлен из stable PPA:

```text
ppa:fish-shell/release-4
```

Работают:

- syntax highlighting;
- autosuggestions;
- contextual completion;
- history;
- Emacs-style line editing;
- Git-aware prompt.

Основные конфиги:

```text
~/.config/fish/config.fish
~/.config/fish/conf.d/00-nix.fish
~/.config/fish/conf.d/eza.fish
~/.config/fish/conf.d/fzf-options.fish
~/.config/fish/conf.d/git-prompt.fish
~/.config/fish/conf.d/user-bin.fish
~/.config/fish/functions/fish_prompt.fish
~/.config/fish/functions/fish_right_prompt.fish
~/.config/fish/functions/fzf_cd_browser.fish
~/.config/fish/completions/helpws.fish
```

## fzf

```text
Ctrl+R     → fuzzy history
Option+C   → directory browser
```

`Ctrl+T` от fzf отключён, потому что `Ctrl+T` занят Ghostty.

Directory browser:

```text
Enter на каталоге     → открыть и остаться в browser
../ + Enter           → уровень вверх
./ + Enter            → принять current directory и выйти
Ctrl+Enter            → принять выбранный directory и выйти
Esc                   → cancel
```

## zoxide

```console
z NAME
zi
```

Для Fish >= 4.8 используется compatibility workaround из-за embedded `cd` function.

## eza

```console
ls
ll
la
lt
```

Используются icons, hyperlinks, directories first и Git metadata для long modes.

---

# HELP SYSTEM

## helpws

Пользовательский terminal help viewer:

```console
helpws
helpws terminal
helpws ghostty
helpws fish
helpws keys
helpws workstation
helpws man ws-terminal
helpws man ws-workstation
```

Fish completion работает для topics, например:

```console
helpws wo<Tab>
```

дополняется до:

```text
helpws workstation
```

Viewer — **Micro в read-only режиме** с отдельной конфигурацией.

Управление:

```text
стрелки / PgUp / PgDn   navigation
mouse / wheel           scroll
Ctrl+F                  search
Ctrl+C                  copy
Esc                     exit
Ctrl+Q                  exit
```

Micro help-viewer использует true-color scheme и Markdown syntax highlighting.

## Documentation source

```text
~/wsconfig/README.md            входная точка
~/wsconfig/docs/architecture/   слои и правила, проверки, этот документ
~/wsconfig/docs/runbooks/       как работает и что делать, по слоям
~/wsconfig/docs/plans/          roadmap и незавершённые планы
~/wsconfig/docs/history/        как строились завершённые слои
```

`helpws` находит документ по `title:`, не по пути.

## Man generation

Man pages собирает Nix (`nix/pkgs/man.nix`): `bin/ws-doc-build` —
`lowdown -s -t man` (lowdown из nixpkgs), по странице на `title:` каждого
`docs/**/*.md`. `ws switch` ставит их ссылками в `~/.local/share/man/man1`; в git `man/` нет,
`ws check home` предупреждает, если страницы старше `docs/`. После правки документа:

```console
ws switch
```

Просмотр:

```console
man ws-terminal
man ws-workstation
```

---

# USER SCRIPTS / WRAPPERS

Единое место runtime symlink'ов:

```text
~/.local/bin
```

Исходники собственных wrapper'ов хранятся в Git repository:

```text
~/wsconfig/bin
```

Правило:

```text
executable source   ~/wsconfig/bin/<tool>
runtime link        ~/.local/bin/<tool>
config source       ~/wsconfig/<область>/...
generated           ~/.local/share/workstation/...
```

Shebang:

```sh
#!/usr/bin/env fish
#!/usr/bin/env bash
#!/usr/bin/env python3
```

---

# WORKSTATION CONFIG REPOSITORY

Единый обычный Git repository:

```text
~/wsconfig
```

Актуальная структура включает:

Всё, что правится, лежит в `~/wsconfig` (каталог задаёт `wsconfig` в
`nix/hosts/<host>/facts.nix`), по областям: в каждой — её объявление в Nix
и родные файлы программ. Сгенерированное и скачанное — в
`~/.local/share/workstation/`, состояние (backup сочетаний, baseline) — в
`~/.local/state/workstation/`, HOME контейнеров — в `~/distrobox/<имя>/`.

```text
wsconfig/
├── bootstrap.sh          новая машина: @nix → apt → @vms/libvirt → группы → fish → ws switch
├── flake.nix, flake.lock nixpkgs 26.05 + home-manager, обновляет ws update nix
├── nix/
│   ├── hosts/            apt.txt всех хостов; <host>/facts.nix, apt.txt
│   ├── home/             default.nix (слой всех хостов), links.nix (ссылки на
│   │                     checkout), cli.nix, man.nix
│   ├── pkgs/             xremap.nix (закреплён), man.nix (man из docs/),
│   │                     gnome-extensions.nix (расширение EGO с pin)
│   └── nix.conf
├── system/               default.nix, common.nix, boot/, hardware/ (Nix),
│   ├── files/            файлы для / (udev, modprobe, systemd, usr, esp, …)
│   ├── kernel/t2bce/     nostate-fix.patch, t2bce.nix (ядро -> коммит linux-t2-patches)
│   ├── kernel/t2gmux/    t2gmux.nix (коммит KaiT2en; helpws plan-dgpu, отложен)
│   └── kernel/i915-psr/  apple-psr.patch (PSR панели Apple; ws-psr, helpws plan-t2)
├── gnome/                gnome.nix, gnome-extensions.nix, extensions/<uuid>/
├── keyboard/             keyboard.nix, xremap.nix, xremap.yml
├── terminal/             fish/, ghostty/, micro-help/, xdg-terminals/
├── flatpak/              flatpak.nix, apps.txt, overrides.txt, desktop/
├── distrobox/            distrobox.nix, arch/ (wsbox-host-ntsync, хуки), wine/
├── windows/              apps.nix (Windows-программы с launcher)
├── bin/
│   ├── ws                switch, diff, apply, update, check, system, baseline
│   ├── dotgit
│   ├── helpws
│   ├── ws-doc-build
│   ├── ws-keyboard
│   ├── ws-keyboard-apply
│   ├── ws-keyboard-status
│   ├── ws-keyboard-check  ws-keyboard check
│   ├── ws-keyboard-install-extensions
│   ├── ws-keyboard-system-apply
│   ├── ws-workstation-verify  связи между слоями (последний шаг ws check)
│   ├── ws-check-repo, ws-check-home  ws check repo / home
│   ├── ws-suspend, ws-suspend-check
│   ├── ws-baseline, ws-checkpoint, ws-collect
│   ├── ws-gnome
│   ├── ws-gnome-check
│   ├── ws-gnome-status
│   ├── ws-xremap
│   ├── ws-window
│   ├── ws-nautilus-current
│   ├── ws-input-source
│   ├── ws-caps-led
│   ├── ws-tiling-apply
│   ├── wsbox, wsflatpak
│   ├── wswin             Windows-программы: install, run, prefixes
│   ├── wswin-check       wswin check
│   └── ws-gpu            AMD для Proton/Steam, если она есть
├── lib/check.bash       общий формат результата проверок (--json для ws check)
├── README.md
└── docs/                architecture/, runbooks/, plans/, history/
```

Nix доставляет, владельцы слоёв не меняются (`helpws layers`):
home-manager ставит ссылки на checkout (`~/.local/bin`, fish, Ghostty), man pages
и CLI (fzf, zoxide, eza, micro, nvd, xremap), unit `xremap.service` с
`xremap.yml` из store, `enabled-extensions` и закреплённые расширения
GNOME (`nix/pkgs/gnome-extensions.nix`), конфиг `wsflatpak` из
`flatpak/flatpak.nix`, профиль внешнего вида GNOME
(`gnome/gnome.nix`, `dconf.settings`); `ws system apply` ставит копии
системных файлов из сборки `system`; GNOME, Flatpak, Distrobox,
клавиатура — `bin/`-владельцы, их по порядку вызывает `ws apply`.
Основная проверка — `ws check`.

Runtime helper paths в `~/.local/bin` используют symlink на repository.
GNOME extension runtime copies являются реальными directories в
`~/.local/share/gnome-shell/extensions/`.

Сгенерированное (`gnome/extensions/*/schemas/gschemas.compiled`, `man/`
локальной сборки) не коммитится.

Перед commit используется:

```console
ws check repo
git status --short
git diff --check
git diff --cached --check
git diff --cached
```

Не используется `git add .` для workstation cleanup: source files добавляются
явно.

---

# НЕ ИСПОЛЬЗУЕТСЯ

Сейчас сознательно не используются:

- `react-drm`;
- `mac-touchbar-plus`;
- `tiny-dfr` и режим дисплея Touch Bar (`appletbdrm`);
- `powertop --auto-tune`;
- snap и snapd (удалены 2026-10-02, apt pin; Firefox — Flatpak);
- TLP;
- auto-cpufreq;
- агрессивный USB runtime PM для Touch Bar;
- custom GNOME Shell CSS;
- replacement GNOME panel/OSD/notifications stack;
- Kitty как основной terminal;
- XWayland workaround для terminal decorations;
- Starship;
- Oh My Fish;
- Fisher как обязательный framework;
- Neovim как часть terminal setup.

Touch Bar работает в родном режиме: `hid-appletb-kbd` + `ws-touchbar-fn`.

---

# СВОДКА

```text
Ubuntu 26.04.1 LTS
└── GNOME 50 / Wayland
    ├── T2 kernel 7.2.7-1-t2-resolute + patched t2bce
    ├── Intel primary; AMD выключена («Ubuntu») или offload («Ubuntu (AMD)»)
    ├── Wi-Fi / Bluetooth
    ├── PipeWire audio
    ├── Camera
    ├── deep / S3 suspend → hibernate через 24 ч
    ├── Btrfs + Timeshift snapshots (вход из GRUB)
    ├── Flatpak / Distrobox / Wine-Proton / KVM
    ├── Touch Bar, родной режим (hid-appletb-kbd)
    │   ├── F1..F12 default
    │   └── hold Fn -> media/brightness (ws-touchbar-fn)
    ├── macOS-style keyboard layer
    │   ├── GNOME/Mutter system shortcuts
    │   ├── xremap GUI/Fn/Nautilus mappings
    │   ├── EN/RU/UA + Caps LED
    │   ├── GDM/login EN
    │   ├── unlock-dialog EN
    │   ├── Tiling Assistant / Tile Editing Mode
    │   └── Smart Popup / Window Control
    └── terminal environment
        ├── Ghostty
        ├── Fish
        ├── fzf / zoxide / eza
        ├── helpws + Micro
        └── wsconfig Git repository
```
