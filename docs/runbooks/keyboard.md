title: ws-keyboard
section: 1
date: 2026-09-25
source: Workstation
volume: User Commands

# KEYBOARD — macOS-STYLE PROFILE ON GNOME

## Назначение

Текущий профиль воспроизводит привычную macOS-семантику на встроенной
Apple/T2 keyboard и на обычной PC/Windows keyboard, не меняя физический смысл
модификаторов глобально:

```text
Apple Command   = PC Win   = Linux Super
Apple Option    = PC Alt   = Linux Alt
Apple Control   = PC Ctrl  = Linux Ctrl
```

`Ctrl` остаётся настоящим `Ctrl`, поэтому terminal/TUI shortcuts не ломаются.

Профиль один: macOS-style с одинаковой семантикой модификаторов на Apple и
PC keyboard. Параметры запуска xremap (`--desktop gnome`,
`--watch=config,device`) заданы в unit `xremap.service`
(`keyboard/xremap.nix`, переменные `XREMAP_DESKTOP`, `XREMAP_WATCH`).

## Архитектура

```text
physical keyboard
      │
      ├── GNOME / Mutter
      │     system shortcuts, workspaces, lock, screenshots
      │
      ├── xremap
      │     application shortcuts, Apple Fn mode,
      │     Nautilus/Finder layer, tiling normalization,
      │     layout helper launches
      │
      ├── workstation-input-source@local
      │     deterministic EN/RU/UA selection,
      │     logical Caps state, lock-screen EN
      │
      ├── workstation-smart-popup@local
      │     Smart Tiling Popup
      │
      ├── Window Control
      │     application/window actions
      │
      ├── Tiling Assistant
      │     tiling backend and private accelerators
      │
      └── Ghostty
            terminal-safe native Super bindings
```

xremap запускается как systemd user service и создаёт virtual input device:

```text
workstation-xremap
```

`Dynamic Function Row Virtual Input Device` исключён из xremap как защита от
петли между xremap и Touch Bar daemon. В текущем родном режиме Touch Bar такого
устройства нет.

## Основные системные shortcuts

```text
Command/Win+Tab              next application
Shift+Command/Win+Tab        previous application
Command/Win+Above_Tab        windows of current application
Control+Down                 windows of current application

Command/Win+Space            Overview / search
Control+Up                   Overview

Control+Left                 previous workspace
Control+Right                next workspace

Command/Win+M                minimize
Control+Command/Win+F        fullscreen
F11                          show desktop

Control+Command/Win+Q        lock screen

Shift+Command/Win+3          screenshot
Shift+Command/Win+4          screenshot UI
Shift+Command/Win+5          screenshot / recording UI
```

Внутренне workspace navigation проходит через private chords:

```text
Control+Left   -> Control+Alt+Super+Left
Control+Right  -> Control+Alt+Super+Right
```

Standalone `Super` отключён как Mutter overlay key:

```text
org.gnome.mutter overlay-key = ''
```

Поэтому Command/Win без второй клавиши ничего не открывает.

GNOME Shell `Super+1..9` и Ubuntu Dock numeric hotkeys отключены, чтобы
`Shift+Command/Win+3/4/5` и application `Command/Win+number` не перехватывались
Shell/Dock.

## EN / RU / UA

Пользовательская сессия содержит ровно три XKB source:

```text
EN = us
RU = ru
UA = ua
```

Переключение выполняет локальный GNOME extension
`workstation-input-source@local`. xremap только вызывает `ws-input-source`.

### CapsLock

```text
CapsLock:
EN -> RU
RU -> EN
UA -> EN
```

CapsLock физически не используется как letter-case modifier. Он хранит
логическое binary state EN/RU.

Сам XKB-lock в сессии выключен опцией `caps:none`
(`org.gnome.desktop.input-sources xkb-options`, задаётся `ws apply keyboard`
из `keyboard/keyboard.nix`). xremap читает evdev до XKB, поэтому
переключение раскладки работает как прежде. Без опции настоящий CapsLock
включался через сочетания, которые xremap пропускает
(`Shift/Ctrl/Super+CapsLock`), и любым нажатием, пока xremap перезапускается
(`ws switch`): текст шёл заглавными при обычном индикаторе. На GDM/login
опция не действует, там CapsLock обычный.

### Ukrainian override

На встроенной Apple keyboard:

```text
Fn+CapsLock        -> UA
Option+CapsLock    -> UA
```

На PC keyboard:

```text
Alt+CapsLock       -> UA
```

UA является третьим override-state и не заменяет запомненное binary EN/RU
состояние. При обычном `CapsLock` из UA выполняется переход в EN.

### Deterministic cycle

```text
Control+Space:
EN -> RU -> UA -> EN

Control+Alt+Space:
EN <- RU <- UA <- EN
```

Порядок не зависит от MRU GNOME.

### Overview / поиск

Command/Win+Space (и любой другой вход в Overview: Control+Up, hot corner,
кнопка Activities) включает EN, чтобы запрос в поиске набирался латиницей:

```text
RU/UA -> Overview -> EN -> закрытие Overview -> RU/UA
EN    -> Overview -> EN (ничего не меняется)
```

- Это временный EN, как на lock screen: `caps-binary-state` не меняется,
  LED гаснет на время Overview и возвращается вместе с раскладкой.
- Ручное переключение внутри Overview (CapsLock, Fn/Option+CapsLock,
  Control+Space, меню раскладок в панели) отменяет возврат: остаётся
  выбранная раскладка.
- Блокировка экрана при открытом Overview тоже отменяет возврат.

Реализация — сигналы `Main.overview` `showing`/`hidden` в
`workstation-input-source@local`. Правка `extension.js` применяется после
logout/login.

### Caps LED

```text
EN       LED off
RU       LED on
UA       LED on
lock     LED off
overview LED off (временный EN)
```

Внутренний helper:

```text
bin/ws-caps-led
```

вызывается GNOME extension через `~/.local/share/workstation/wsconfig/bin/`
(ссылка home-manager на checkout). Это не пользовательская команда, в
`~/.local/bin` её нет (`binExcluded` в `nix/home/links.nix`).

## GDM login и GNOME lock screen

Это два разных механизма.

### GDM/login

Системная keyboard configuration задаёт только US layout:

```text
XKBLAYOUT="us"
XKBVARIANT=""
```

Group-switching `grp:*` и `grp_led:*` options для login screen не используются.

Итог:

```text
GDM/login -> EN only
```

### Lock screen / unlock-dialog

Lock screen относится к текущей пользовательской GNOME Shell session, поэтому
его обслуживает `workstation-input-source@local`.

Extension загружается в session modes:

```text
user
unlock-dialog
```

При входе в `unlock-dialog` действует invariant:

```text
current input source = EN
```

GNOME Shell может reload'ить `InputSourceManager` при переходе password entry
в password input purpose. Поэтому extension повторно принудительно ставит EN
на каждом `current-source-changed`, пока активен `unlock-dialog`.

Используется сигнал GNOME Shell 50 `locked-changed`.

Важно: lock screen **не изменяет** сохранённый `caps-binary-state`. После
unlock обычная EN/RU/UA логика продолжает работать.

Итог:

```text
GDM/login                 EN
GNOME lock/unlock         EN
unlocked user session     EN / RU / UA
```

## Application shortcuts — xremap

Generic GUI applications:

```text
Command/Win+C / V / X        copy / paste / cut
Command/Win+A                select all
Command/Win+Z                undo
Shift+Command/Win+Z          redo
Command/Win+S / O / P        save / open / print
Command/Win+F                find
Command/Win+N / T            new / new tab
Command/Win+W                close
Command/Win+Q                Ctrl+Q where supported
Command/Win+,                preferences where Ctrl+, is supported

Command/Win+Left/Right       line start/end
Command/Win+Up/Down          document start/end
Option/Alt+Left/Right        previous/next word
Shift+Option/Alt+Left/Right  select by word
Option/Alt+Backspace         delete previous word
```

`exact_match: true` не даёт generic mappings поглощать более длинные system
combinations.

## Terminal layer

Terminal classes исключены из generic GUI mapping.

xremap выполняет только navigation, которую GNOME иначе перехватил бы:

```text
Command/Win+Left          Ctrl+A
Command/Win+Right         Ctrl+E
Command/Win+Backspace     Ctrl+U
Option/Alt+Left           Alt+B
Option/Alt+Right          Alt+F
```

Ghostty имеет собственные native bindings:

```text
Command/Win+C / V         copy / paste
Command/Win+A             select all
Command/Win+F             search
Command/Win+T             new tab
Command/Win+N             new window
Command/Win+W             close surface
Command/Win+Q             close all Ghostty windows
Command/Win+,             open config
Command/Win+= / - / 0     font larger / smaller / reset
```

Физический `Ctrl+C` остаётся terminal interrupt.

## Nautilus / Finder layer

Когда активен GNOME Files / Nautilus:

```text
Command/Win+1             grid / icon view
Command/Win+2             list view

Command/Win+Up            parent directory
Command/Win+Down          open selected item
Command/Win+[             back
Command/Win+]             forward

Command/Win+I             Properties
Command/Win+Backspace     Move to Trash
Shift+Command/Win+N       New Folder

Shift+Command/Win+G       location entry / Go to Folder
Command/Win+K             Network view
Shift+Command/Win+.       show/hide hidden files
Space                     Quick Look through GNOME Sushi

Shift+Command/Win+H       Home
Shift+Command/Win+C       Computer /
Shift+Command/Win+O       Documents
Shift+Command/Win+D       Desktop
```

`ws-nautilus-current` меняет location именно текущего Nautilus window/tab.

`Shift+Command/Win+N -> Ctrl+Shift+N` остаётся EN-layout-dependent, потому что
это printable Ctrl-letter shortcut приложения.

Не реализованы Finder features без прямого Nautilus equivalent:

```text
Command/Win+3             Column View
Command/Win+4             Gallery View
Command/Win+J             View Options
Command/Win+D             Duplicate
Command/Win+E             Eject
Shift+Command/Win+U       Utilities
```

## Application/window actions

Используется GNOME extension:

```text
window-control@carlo9890.github.io
```

через helper `ws-window`.

```text
Option+Command/Win+Esc       GNOME System Monitor
Command/Win+H                minimize windows of current app
Option+Command/Win+H         minimize all other applications
Option+Command/Win+W         politely close windows of current app
Option+Command/Win+M         minimize windows of current app

Shift+Command/Win+Q          logout with confirmation
Option+Shift+Command/Win+Q   logout immediately
```

Force-kill по shortcut не выполняется.

## Tiling Assistant

Backend:

```text
Tiling Assistant
preferred UUID: tiling-assistant@ubuntu.com
fallback UUID:  tiling-assistant@leleat-on-github
```

Private accelerators:

```text
Shift+Ctrl+Alt+Super+Left    tile left
Shift+Ctrl+Alt+Super+Right   tile right
Shift+Ctrl+Alt+Super+Up      tile top
Shift+Ctrl+Alt+Super+Down    tile bottom
Shift+Ctrl+Alt+Super+F       Fill
Shift+Ctrl+Alt+Super+C       Center
Shift+Ctrl+Alt+Super+R       Restore previous size
Shift+Ctrl+Alt+Super+E       Tile Editing Mode
Shift+Ctrl+Alt+Super+T       Always on Top
Shift+Ctrl+Alt+Super+Space   Smart Popup
```

Пользователь напрямую private chords не нажимает.

### Apple keyboard

Apple HID превращает Fn+arrows до xremap:

```text
Fn+Left   -> Home
Fn+Right  -> End
Fn+Up     -> PageUp
Fn+Down   -> PageDown
```

Поэтому user-facing shortcuts:

```text
Fn+Control+Left/Right/Up/Down   tile half
Fn+Control+F                    Fill
Fn+Control+C                    Center
Fn+Control+R                    Restore

Fn+Option+Left/Right/Up/Down    spatial focus
Fn+Option+E                     Tile Editing Mode
Fn+Option+T                     Always on Top
```

Spatial focus кратковременно включает Tile Editing Mode, передаёт arrow и
подтверждает выбор `Enter`.

### PC keyboard

```text
Control+Win+Left/Right/Up/Down  tile half

Alt+Win+Left/Right/Up/Down      spatial focus
Alt+Win+E                       Tile Editing Mode
Alt+Win+T                       Always on Top
```

## Smart Popup

Локальный GNOME extension:

```text
workstation-smart-popup@local
```

Trigger:

```text
Apple: Right Option + Right Command
PC:    Right Alt + Right Win
```

Оба порядка нажатия правых modifiers поддерживаются.

Extension использует Tiling Assistant как backend:

1. получает текущую tile group;
2. вычисляет свободные rectangles на текущем monitor;
3. при нескольких областях показывает selector и позволяет выбрать область
   стрелками;
4. открывает Tiling Assistant popup со списком доступных windows;
5. выбранное окно добавляется в tile group.

Если свободная область одна, промежуточный selector пропускается.

## Touch Bar / Fn

Touch Bar работает в родном режиме: кнопки рисует T2, режимом управляет
`hid-appletb-kbd` (`/etc/modprobe.d/tb.conf`, `mode=1`). Touch Bar закреплён в
USB configuration 1, `appletbdrm` и `tiny-dfr` не используются.

Поведение:

```text
normal       F1..F12
hold Fn      media / brightness
release Fn   F1..F12
```

xremap забирает события встроенной клавиатуры, поэтому штатное переключение
по Fn в `hid-appletb-kbd` за ним не срабатывает. xremap для Apple Fn использует:

```text
skip_key_event: false
```

поэтому KEY_FN остаётся на virtual keyboard `workstation-xremap`. Его слушает
`ws-touchbar-fn.service`: пока Fn зажата, `hid-appletb-kbd` переключается в
mode 2 (media/brightness), при отпускании возвращается mode 1.

Подробности Touch Bar:

```console
helpws touchbar
```

## Source of truth

Repository:

```text
keyboard/xremap.yml
keyboard/keyboard.nix          сочетания GNOME и private chords Tiling

bin/ws-keyboard
bin/ws-keyboard-apply
bin/ws-keyboard-status
bin/ws-xremap
bin/ws-window
bin/ws-nautilus-current
bin/ws-input-source
bin/ws-caps-led
bin/ws-tiling-apply
bin/ws-keyboard-install-extensions
bin/ws-keyboard-system-apply
bin/ws-keyboard-check

keyboard/xremap.nix
nix/pkgs/xremap.nix
system/files/udev/99-workstation-uinput.rules

system/files/udev/90-touchbar-native.rules
system/files/modprobe/tb.conf
system/files/modprobe/touchbar-native.conf
system/files/usr/local/libexec/ws-touchbar-fn
system/files/systemd/system/ws-touchbar-fn.service

gnome/extensions/workstation-smart-popup@local/
  extension.js
  metadata.json
  schemas/org.gnome.shell.extensions.workstation-smart-popup.gschema.xml

gnome/extensions/workstation-input-source@local/
  extension.js
  metadata.json
  schemas/org.gnome.shell.extensions.workstation-input-source.gschema.xml
```

Generated `gnome/extensions/*/schemas/gschemas.compiled` не коммитится.

Machine-local state — вне checkout, в `~/.local/state/workstation/keyboard/`:
`gsettings-backup.tsv` (сочетания GNOME до первого `ws-keyboard apply`, их
возвращает `ws-keyboard restore`) и `xremap.disabled`.

## Runtime installation

Command helpers устанавливаются в `~/.local/bin` как symlink на repository
(ссылки home-manager, `ws switch`).

xremap binary — из Nix: `nix/pkgs/xremap.nix`, upstream
`xremap-linux-x86_64-gnome.zip` v0.15.13 по hash:

```text
~/.local/bin/xremap -> /nix/store/…-xremap-gnome-0.15.13/bin/xremap
```

Обновление xremap: версия и hash в `nix/pkgs/xremap.nix`, затем `ws switch`
и `ws-keyboard restart`.

xremap service — `systemd.user.services.xremap` home-manager
(`keyboard/xremap.nix`); unit и ссылку в
`graphical-session.target.wants` ставит `ws switch`:

```text
~/.config/systemd/user/xremap.service -> /nix/store/…-xremap.service
Environment=XREMAP_BIN=/nix/store/…-xremap-gnome-0.15.13/bin/xremap
Environment=XREMAP_CONFIG=/nix/store/…-xremap.yml
ExecStart=/usr/bin/bash ~/wsconfig/bin/ws-xremap
```

`XREMAP_CONFIG` — сборка `keyboard/xremap.yml` в store: `@repo@` в
путях `launch` (`@repo@/bin/ws-input-source`) заменяется на checkout этого
home. Правка `xremap.yml` применяется через `ws switch`: unit меняется, и
home-manager перезапускает сервис (`--watch=config` store-файл не видит).
Без `XREMAP_CONFIG` `ws-xremap` не запускается.

Включает сервис home-manager; решает, работает ли xremap, по-прежнему
`ws-keyboard`. `restore` и неудачный `apply` создают флаг
`~/.local/state/workstation/keyboard/xremap.disabled` (в unit —
`ConditionPathExists=!…`), поэтому xremap не стартует и после
перезагрузки; `ws-keyboard apply` и `ws-keyboard start` флаг удаляют.

Наши GNOME extensions устанавливаются как реальные directories в:

```text
~/.local/share/gnome-shell/extensions/
```

`gschemas.compiled` генерируется в runtime copy через `glib-compile-schemas`.

После изменения `extension.js` на Wayland требуется logout/login для
гарантированной загрузки нового ES module.

## Apply

Сочетания GNOME профиля и private chords Tiling Assistant объявлены данными
в `keyboard/keyboard.nix`. `ws switch` собирает из них
`~/.local/share/workstation/keyboard/gnome-shortcuts.tsv` и `tiling-bindings.tsv`;
по ним работают `ws-keyboard-apply` (preflight, backup, установка),
`ws-tiling-apply`, `ws-keyboard check` и `ws-keyboard-status`. Это не `dconf.settings`:
сочетания ставятся только после preflight и запуска xremap, и
`ws-keyboard restore` должен уметь вернуть исходные.

Изменить сочетание:

```console
$EDITOR ~/wsconfig/keyboard/keyboard.nix
ws switch
ws-keyboard apply      # или ws-tiling-apply для Tiling
```

Исходное значение нового ключа в существующий backup не попадает: backup
делается один раз, до первого apply.

Основной профиль:

```console
ws-keyboard apply
```

Tiling private bindings применяются через:

```console
ws-tiling-apply
```

Extension sources устанавливаются через:

```console
ws-keyboard-install-extensions
```

System-level baseline (uinput udev, GDM EN, Touch Bar native mode: udev rule,
modprobe options, `ws-touchbar-fn.service`) применяется отдельно, потому что
требует `sudo`:

```console
ws-keyboard-system-apply
```

Это обёртка над `ws system apply`: ставит все системные файлы хоста из
`system` (Nix), только отличающиеся, с бэкапом в
`/var/backups/workstation/system-<время>/`; проверка без изменений —
`ws system diff`.

`ws-keyboard-apply` выполняет runtime preflight до изменения GNOME shortcuts.
Если xremap, `/dev/uinput`, GNOME xremap bridge или обязательные extensions не
готовы, GNOME bindings не должны оставаться частично применёнными.

## Restore

```console
ws-keyboard restore
```

восстанавливает исходный snapshot GNOME shortcuts, останавливает xremap и
ставит флаг `xremap.disabled` (см. «Runtime installation»): xremap не
стартует до `ws-keyboard apply` или `ws-keyboard start`.

Он не удаляет Tiling Assistant, Window Control, `ws-touchbar-fn` или локальные
GNOME extensions. Их lifecycle управляется отдельно.

## Проверка

Полная read-only проверка:

```console
ws-keyboard check
ws-workstation-verify     # GNOME ↔ клавиатура: мост xremap, Input Source, Tiling Assistant
```

Основные ручные diagnostics:

```console
ws-keyboard status
ws-keyboard devices
ws-keyboard gnome-apps
ws-input-source status

systemctl --user status xremap.service
journalctl --user -u xremap.service

gnome-extensions info xremap@k0kubun.com
gnome-extensions info window-control@carlo9890.github.io
gnome-extensions info workstation-smart-popup@local
gnome-extensions info workstation-input-source@local

systemctl status ws-touchbar-fn.service
```

## Подтверждённый baseline

На текущем `MacBookPro16,1`, GNOME 50.1 / Wayland подтверждены:

```text
Apple + PC semantic modifiers        OK
GNOME system shortcuts               OK
GUI application mappings             OK
Ghostty terminal-safe layer           OK
Nautilus / Finder layer               OK
Window Control actions                OK
Tiling Assistant mappings             OK
Tile Editing Mode / spatial focus     OK
Always on Top                         OK
Smart Popup                           OK
EN / RU / UA                          OK
CapsLock logic + LED                  OK
GDM/login EN                          OK
GNOME unlock-dialog EN                OK
Touch Bar F1/Fn media (native)        OK
xremap service / uinput               OK
```
