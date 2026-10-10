title: ws-windows
section: 1
date: 2026-09-28
source: Workstation
volume: User Commands

# WINDOWS PROGRAMS — WINE / PROTON / STEAM

Как слой строился и почему так: `helpws history-windows`.

## Контейнеры

```text
wine-wayland  Arch                 Wine из Arch, родной Wayland-драйвер;
                                   контейнер по умолчанию
wine          Ubuntu релиза host   WineHQ stable, XWayland: программы, которым
                                   Wayland-драйвер не подходит
proton        Arch                 umu-launcher + Proton: игры, тяжёлое 3D
```

Описаны в `distrobox/distrobox.nix` (`windows = { profile; driver; dpi; }`),
живут как обычные managed boxes: `wsbox status`, `wsbox update`,
`wsbox recreate NAME`. HOME каждого — `~/distrobox/NAME`, переживает
recreate. Что ставится при создании:

```text
wine-wayland  wsbox-host-ntsync, затем wine wine-mono wine-gecko winetricks
              (distrobox/arch/pacman-install-hook)
wine          репозиторий WineHQ для релиза контейнера, winehq-stable,
              winetricks (distrobox/wine/winehq-install-hook)
proton        [multilib] (distrobox/arch/multilib-hook), umu-launcher,
              32-битные Mesa/Vulkan, wsbox-host-ntsync
```

Proton и Steam Runtime umu скачивает при первом запуске в
`~/distrobox/proton/.local/share/{Steam/compatibilitytools.d,umu}`.

## Prefixes

```text
стандартный   ~/distrobox/BOX/.wine
свой          ~/distrobox/BOX/prefixes/NAME
```

При создании prefix `wswin` задаёт драйвер (`wine-wayland`: `Graphics=wayland`
в `HKCU\Software\Wine\Drivers`) и DPI контейнера (`wine`: `LogPixels=192`,
200% при `xwayland-native-scaling`). Настройки стандартного prefix общие для
всех программ в нём.

`wine-wayland`: `LogPixels=144` (150%, масштаб экрана 1.5) — Wayland-драйвер
сам не масштабирует окна (проверено на Notepad++ 2026-09-28).

## Кодировка

Windows-программы запускаются с `LC_CTYPE=ru_RU.UTF-8` (`ansiLocale` в
`windows/apps.nix`) — как «Язык программ, не поддерживающих Юникод» в
Windows: кодировка `cp1251` для не-Unicode программ. С `C.UTF-8` сессии Wine
брал `cp1252`, и кириллица пропадала (заголовок установщика GOG). Без
`LC_MESSAGES` Wine взял бы из `LC_CTYPE` и язык интерфейса; `uiLocale`
(`LC_MESSAGES=en_US.UTF-8`) оставляет его английским, как в сессии host. Локаль есть в Arch-контейнерах
(glibc-locales), в `wine` её создаёт `distrobox/wine/locale-hook`.

## wswin

```console
wswin list
wswin install [--box BOX] [--prefix NAME] [--desktop[=WxH]] SETUP.exe|.msi [ARG...]
wswin portable [--box BOX] [--prefix NAME] FILE.exe|DIR|FILE.zip [APPNAME]
wswin run APP [ARG...]
wswin exec [--box BOX] [--prefix NAME] [--desktop[=WxH]] PROGRAM [ARG...]
wswin prefix [--box BOX] NAME init [--dpi N]
wswin prefix [--box BOX] NAME winecfg|regedit|kill|path
wswin prefix [--box BOX] NAME winetricks [ARG...]
wswin prefix [--box BOX] NAME remove
wswin shell [--box BOX] [--prefix NAME]
wswin menu [--box BOX] [--prefix NAME] add [PROGRAM.exe [TITLE]]
wswin menu list|sync
wswin menu remove ID
```

- По умолчанию `--box wine-wayland` и стандартный prefix (`NAME` = `default`).
- В `proton` всё идёт через `umu-run` (`GAMEID=umu-default`, если не задан).
- `--desktop[=WxH]`: программа в виртуальном рабочем столе Wine (`explorer
  /desktop=wswin-PREFIX,WxH`). Для установщиков, которые под X11 забирают
  фокус обратно при каждом переключении на другое окно (установщик GOG в
  Proton; `UseTakeFocus=N` не помогает — программа сама вызывает активацию).
  Wine 11 / Proton 10 под XWayland с масштабом открывают стол на весь экран,
  размер игнорируется (проверено 2026-09-28).
- Файлы из host HOME, `/tmp`, `/media`, `/mnt` видны в контейнере по тому же
  пути.
- Двойной клик по `.exe` в «Файлах» — `wswin exec --box wine-wayland FILE`:
  стандартный prefix `wine-wayland` (создаётся при первом запуске), запуск
  из каталога файла. Обработчик `ws-win-exe.desktop` (`windows/apps.nix`),
  `ws switch` делает его приложением по умолчанию для типов `.exe`
  (`xdg-mime`, только эти ключи `~/.config/mimeapps.list`). Установщик,
  запущенный так, работает, но пунктов меню не предлагает (нет терминала для
  вопросов): для этого — `wswin install` или потом `wswin menu add`.

## Меню GNOME

Установщик создаёт ярлыки Windows (`.lnk`) в меню «Пуск» и на рабочем столе
prefix. После установщика `wswin install` спрашивает про каждый новый ярлык
этого prefix, добавить ли его в меню host (по одному вопросу на exe; ярлыки
не на exe пропускаются). Так же во всех контейнерах, включая `proton`
(Proton не создаёт Linux-пунктов Wine). Позже — `wswin menu --box BOX
--prefix NAME add`; пункт на любой exe —
`wswin menu --box BOX --prefix NAME add PROGRAM.exe [TITLE]` (путь на host
или внутри prefix). Иконка берётся из exe (`icoutils` в контейнере), запуск
— из каталога программы.

```console
wswin install --prefix foo ~/Downloads/foo-setup.exe
```

Portable-программа (exe, каталог или zip) копируется в
`PREFIX/drive_c/Portable/APPNAME`; если exe несколько — выбор по номеру;
иконка берётся из exe (`icoutils` в контейнере), затем вопрос про меню:

```console
wswin portable --prefix tools ~/Downloads/tool.zip
```

Пункт меню хранится в prefix (`PREFIX/.wswin/menu/wswin-BOX-PREFIX-NAME.desktop`
и иконка), в `~/.local/share/applications` — ссылка на него. Запуск:
`wswin exec --box BOX --prefix NAME …`. Удаляется вместе с prefix
(`wswin prefix … remove`) или `wswin menu remove ID`; после новой
системы с сохранённым HOME — `wswin menu sync`.

Программы, которые должны возвращаться вместе с репозиторием, — в
`windows/apps.nix` (`exe` — путь внутри prefix), `ws switch`: launcher
`ws-win-NAME.desktop` (`wswin run NAME`), как у WinBox. Launcher ставится
только на машине, где box программы помечен `HOST=yes` в
`distrobox/hosts.txt` (`helpws distrobox`); `ws-win-exe.desktop` и обработчик
`.exe` — там, где помечен `wine-wayland`. `wswin check` программы других
box не проверяет (INFO).

## GPU

```console
ws-gpu status
```

`proton` (`gpu = "amd"` в `distrobox.nix`) и Steam работают на AMD, если
система загружена в rEFInd «Ubuntu (AMD)», иначе на Intel. `ws-gpu` ищет
render node с драйвером `amdgpu` при каждом запуске и передаёт
`DRI_PRIME=pci-0000_03_00_0`; `wsbox enter/run proton` добавляют его через
`distrobox enter --additional-flags`, поэтому контейнер один для обеих
загрузок. `wine` и `wine-wayland` GPU не выбирают.

## Steam

`com.valvesoftware.Steam` (flatpak, `flatpak/flatpak.nix`), udev-правила
контроллеров — `steam-devices` (apt). Свой launcher
`flatpak/desktop/com.valvesoftware.Steam.desktop` (тот же id, поэтому и
`steam://`) запускает Steam через `ws-gpu run` и с `-console` (вкладка
консоли: `steam://open/console`). Прямой `flatpak run` из терминала GPU не
выбирает.

## WinBox

`wine-wayland`, свой prefix `winbox`, `drive_c/Program Files/WinBox/winbox.exe`,
`LogPixels=144`, без Mono (`WINEDLLOVERRIDES=mscoree=`).

## Удаление

Программа или игра со своим prefix — вместе с её пунктами меню:

```console
wswin prefix --box BOX NAME remove
```

Контейнер целиком (навсегда):

1. `wsbox remove BOX` — rootfs (пока контейнер ещё в `distrobox.nix`);
2. убрать контейнер из `distrobox/distrobox.nix` и его программы из
   `windows/apps.nix`, `ws switch`;
3. `rm -rf ~/distrobox/BOX` — HOME: prefixes, программы, сохранения;
4. `wswin menu sync` — убрать ссылки меню, ставшие битыми (`ws check`
   предупреждает о них).

`wsbox remove`/`recreate` HOME не трогают намеренно: пересоздание
контейнера не теряет программ. Шаги по отдельности проверены (recreate,
удаление prefix со ссылками, предупреждение `ws check`); цепочка целиком не
прогонялась.

## Проверка

```console
ws check
wsbox check
wswin list
```
