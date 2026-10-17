title: ws-gnome
section: 1
date: 2026-09-25
source: Workstation
volume: User Commands

# GNOME DESKTOP

Этот документ описывает управляемую часть GNOME layer workstation.

## Архитектурные границы

GNOME остаётся максимально штатным Ubuntu desktop:

```text
GDM3
GNOME Shell + Mutter
Wayland
Ubuntu Dock
Quick Settings
Nautilus
GNOME Settings
xdg-desktop-portal + GNOME backend
PipeWire / WirePlumber
```

Не заменяем штатные panel, Dock, notifications или OSD.

Текущий display scale уже выбран через `Settings -> Displays` и считается
рабочим. На этой машине фактический logical monitor scale — `1.5`. GNOME
appearance profile его не задаёт и не меняет.

Стандартную кнопку `Show Applications` и меню приложений пока не заменяем.

## Приложения

Тема, масштаб и порталы приложений — у их слоёв: Flatpak (`ws help flatpak`),
Distrobox (`ws help distrobox`), Wine (`ws help windows`; Wine только в
контейнерах, на host не ставится).

# Управляемый appearance profile

Source of truth (с 2026-09-27):

```text
gnome/config.toml               значения: [settings."DCONF/DIR"] KEY = значение
hosts/HOST/gnome.toml       свои значения хоста поверх общих (если нужен)
gnome/gnome.nix                 логика: ключи железа, проверка чужих ключей
```

Профиль — `dconf.settings` home-manager. Его записывает `ws apply`
(`dconf load`) при каждой активации:

- ручное изменение этих ключей (в Settings, Tweaks, `gsettings set`)
  откатывается следующим `ws apply`; менять значение — в `gnome/config.toml`;
- ключ, убранный из `gnome/config.toml`, при следующем `ws apply` сбрасывается к
  значению по умолчанию;
- значения пишутся явно, даже если совпадают с дефолтом Ubuntu, чтобы
  изменённый дефолт дистрибутива не пришёл незаметно.

Изменение:

```console
$EDITOR ~/wsconfig/gnome/config.toml
ws apply
ws gnome check
ws sync             # опубликовать файл
```

Откат — `git revert`/правка и `ws apply` (или активация предыдущего
поколения home-manager).

Текущий профиль фиксирует только небольшой curated набор GNOME/GTK и Ubuntu
Dock settings, полученный с рабочей системы 2026-09-23.

Текущий visual baseline:

```text
color scheme      prefer-dark
accent            orange
GTK theme         Yaru-dark
icons             Yaru-dark
cursor            Yaru
UI font           Ubuntu Sans 11
document font     Sans 11
monospace         Ubuntu Sans Mono 11
Ubuntu Dock       bottom
Dock icon size    50
Dock autohide     true
Show Applications true
click action      focus-minimize-or-appspread
```

Остальные текущие Dock settings тоже записаны в `gnome/config.toml`.

## Что profile намеренно НЕ управляет

```text
display scale / monitors.xml
org.gnome.mutter experimental-features
input sources
keyboard shortcuts            ws-keyboard-apply (с restore)
Tiling Assistant bindings     ws-tiling-apply
GNOME extension enablement
wallpaper
Flatpak settings
Distrobox settings
Wine settings
```

Keyboard shortcuts не перенесены в `dconf.settings`: `ws keyboard restore`
и откат неудачного apply возвращают сочетания GNOME, а home-manager
записывал бы их обратно при каждом `ws apply`.

# ws gnome

Основной wrapper:

```console
ws gnome status
ws gnome check
ws gnome test
```

Применяет профиль `ws apply`; откат — правка в репозитории и снова
`ws apply`.

## status

```console
ws gnome status
```

Read-only inventory. Показывает GNOME/Wayland session, Mutter display state,
appearance, Dock, extensions, portals, host toolkit environment и состояние
managed profile.

Прямой вызов:

```console
ws-gnome-status
```

## check

```console
ws gnome check
```

Сравнивает сессию (`gsettings get`) с `~/.local/share/wsconfig/gnome/
settings.json` — списком `{schema, key, value}`, который home-manager собирает
из того же набора, что `gnome/config.toml`. Ничего не меняет. Прямой вызов —
`ws-gnome-check`.

Exit status:

```text
0  profile полностью совпадает
1  есть drift или ошибка проверки
```

# Safety ownership rules

`gnome/gnome.nix` проверяет при сборке (assertion), что во всём
`dconf.settings` нет ключей других workstation layers:

```text
org.gnome.desktop.interface text-scaling-factor
org.gnome.mutter experimental-features / overlay-key
org.gnome.desktop.input-sources/*
org.gnome.desktop.wm.keybindings/*
org.gnome.shell.keybindings/*
org.gnome.settings-daemon.plugins.media-keys/*
org.gnome.shell.extensions.dash-to-dock hot-keys
org.gnome.shell.extensions.tiling-assistant/*
```

Таким образом GNOME appearance profile не может случайно переписать display,
keyboard, Tiling Assistant или extension baseline.


# GNOME extension policy

Единственный список расширений — `[[extensions]]` в `gnome/config.toml`
(с 2026-09-27 один список; раньше свои копии были в verify,
`ws-gnome-test`, `ws-gnome-status`, installer и здесь). Для каждого
расширения — uuid и источник; поставщика контракта wsdbus (всегда) и
расширения, зависящие от хоста (гибернация, адаптер виджетов), добавляет
`gnome/gnome-extensions.nix`:

```text
ubuntu  gnome-shell-ubuntu-extensions (apt), включает режим сессии Ubuntu
ego     extensions.gnome.org: ставит ws apply extensions, обновляет
        Extension Manager; с pin — версия через Nix (nix/pkgs/gnome-extensions.nix)
local   gnome/extensions/<uuid>, копирует ws gnome extensions
nix     файлы из модуля Home Manager входа flake (wsdbus, wswidgets),
        ставит ws apply home
```

Из списка собираются:

- `enabled-extensions` (ego + local + nix, `dconf.settings`) и пустой
  `disabled-extensions` — пишет `ws apply`. Расширение, включённое или
  выключенное вручную (Extension Manager, `gnome-extensions`), следующий
  `ws apply` вернёт к списку; добавлять и убирать — в `gnome/config.toml`.
- `~/.local/share/wsconfig/gnome/extensions.json` (`order` — все UUID по
  порядку, `by_source` — по источникам, `pins` — версии pin) — его читают
  `ws gnome check`, `ws-gnome-test`, `ws-gnome-status`, `ws check repo`,
  `ws update extensions` и `ws gnome extensions`.

Все расширения списка обязательны. Посмотреть текущий список:

```console
python3 -m json.tool ~/.local/share/wsconfig/gnome/extensions.json
```

`wsdbus@kkkingqz.github.io` — поставщик контракта рабочего стола
[wsdbus](https://github.com/kkkingqz/wsdbus) (`gnome/wsdbus.nix`): фокус,
окна и команды для `ws-window`, блокировка и схема для виджетов. Он заменил
`window-monitor-pro@muhammed.hussien2030.gmail.com` и
`window-control@carlo9890.github.io` (2026-10-17, wsdbus W14, W15). После их
удаления из `gnome/config.toml` файлы остаются в
`~/.local/share/gnome-shell/extensions`, выключенными; убрать их —
`gnome-extensions uninstall UUID`. `xremap` по-прежнему ставит
`ws apply extensions` с extensions.gnome.org.

Неизвестные дополнительные extensions автоматически не отключаются; verifier
только выдаёт WARN.

# Dock spring-loaded drag-and-drop

Local extension:

```text
workstation-dock-spring@local
```

Проверенное поведение:

```text
source drag             external file drag, например Nautilus
target                  Ubuntu Dock application icon
hover delay             1300 ms
already running app     focus/restore existing window
window other workspace  switch/focus existing window
closed app              do nothing; never launch
drop handling           extension does not consume the drop
```

Рабочий сценарий: начать drag файла в Nautilus, удержать его над иконкой уже
запущенного приложения ~1.3 s, после появления окна продолжить тот же drag в
окно и отпустить файл.

Desktop Icons NG и `ubuntu-dock@ubuntu.com` этим extension не патчатся и не
заменяются.

# Smoke-test

```console
ws gnome test
```

или:

```console
ws-gnome-test
```

Автоматическая часть read-only и не проверяет Touch Bar, Flatpak, Distrobox
или Wine.

После неё helper печатает ручной checklist для тех GUI interactions, которые
нельзя достоверно проверить без действий пользователя.


# Host Qt5/Qt6

Для host Qt applications используется минимальная GNOME integration layer:

```text
qgnomeplatform-qt5
qgnomeplatform-qt6
qtwayland5
qt6-wayland
```

Проверено на временных JuffEd (Qt5) и FeatherPad (Qt6):

```text
Qt5 normal launch  -> libqwayland-generic.so
Qt6 normal launch  -> libqwayland.so
dark appearance    -> автоматически через QGnomePlatform
display scale      -> compositor/Qt Wayland
```

Никакие глобальные overrides не используются:

```text
QT_QPA_PLATFORM
QT_QPA_PLATFORMTHEME
QT_STYLE_OVERRIDE
QT_SCALE_FACTOR
```

Это важно: обычное Qt приложение получает native Wayland и GNOME appearance
без workstation-specific environment hacks.

Пакеты — `system/apt.txt` (`ws check apt`), отсутствие overrides —
`ws check home`. Qt в контейнерах этим не настраивается.

---


# Colors

Штатный Ubuntu/GNOME visual profile:

```text
color scheme   prefer-dark
accent         orange
GTK theme      Yaru-dark
icons          Yaru-dark
cursor         Yaru
```

Не используем custom GTK/libadwaita palette, custom GNOME Shell CSS или
стороннюю GTK theme как workstation baseline. Это сохраняет максимально
штатное поведение GNOME и снижает риск несовместимости после обновлений.

