title: ws-gaming
section: 1
date: 2026-10-10
source: Workstation
volume: User Commands

# GAMING — GAME MODE (GAMESCOPE + STEAM)

Game Mode — отдельная сессия gamescope + Steam, как в SteamOS, на хосте с
`gameMode = true` в `host.toml` (сейчас legiongo; `helpws plan-legion-go`).
Компоненты взяты из Bazzite и собраны в `.deb`: всё ставит dpkg, вне
пакетов ничего не лежит. Переключение GNOME ↔ Game Mode — steamos-manager
через автологин SDDM, без экрана входа.

## Слои

```text
gaming/sources.nix     источники: url, sha256, версия пакета (ws apply →
                       ~/.local/share/wsconfig/gaming/sources.json, на
                       каждом хосте: собирать можно где угодно)
gaming/build.sh        сборка в контейнере Ubuntu релиза host (podman)
gaming/apt.txt         из Ubuntu, ставит bootstrap.sh: gamescope, mangoapp
steam/apt.txt          Steam из apt (nativeSteam = true)
system/gaming.nix      автологин SDDM, os-session-select, Return to Game
                       Mode, HandlePowerKey=ignore (ws apply system)
libexec/wsgame         владелец: fetch, build, install, check, mode
```

## Пакеты

```text
steamos-manager          OGC (как в Bazzite), сборка Rust: DBus между Steam и
                         ОС, переключение сессий (файлы SDDM), цели
                         InputPlumber. platform.toml [session]: ubuntu.desktop,
                         gamescope-session-plus@steam; у device-файла Legion
                         Go убраны TDP и профиль производительности —
                         platform_profile только у power-profiles-daemon
powerbuttond             Valve 4.2 + debounce Terra после сна: кнопка питания в
                         Game Mode (коротко — сон через Steam, долго — меню)
gamescope-session-plus   скрипты OGC, gamescope-session-plus@.service, quirks
                         устройств (83E1: поворот left, 60/144 Гц)
gamescope-session-steam  сессия Steam Big Picture (steamos-session-select →
                         /usr/libexec/os-session-select из system/gaming.nix)
extest                   libextest.so (i386): Steam Input на Wayland-рабочем
                         столе (LD_PRELOAD в клиент Steam)
inputplumber             .deb upstream: виртуальный контроллер Steam Deck
sddm, weston             из Ubuntu: display manager и compositor его greeter
mangoapp                 из Ubuntu (gaming/apt.txt): оверлей Steam
```

## Команды

```console
ws game build              # fetch (sha256) и сборка .deb в podman, любой хост
ws game test               # поставить и снять .deb в чистом контейнере Ubuntu
ws game status             # закреплённая, собранная и установленная версия
ws game install            # gameMode = true: apt install .deb + sddm, weston
# reboot: SDDM вместо GDM, автологин в GNOME
ws game check              # то же, что ws check gaming
ws game mode game          # переключить сейчас (steamosctl)
```

`install` выбирает sddm display manager через debconf (без вопроса), GDM
остаётся установленным. Включает `inputplumber.service`, запускает
пользовательский steamos-manager и ставит режим входа по умолчанию
`desktop` (steamos-manager сам начинает с Game Mode).

Новая версия: `url`, `sha256`, `version` в `gaming/sources.nix` → `ws
apply` → `ws game build` → `ws game install`.

## Переключение

```text
GNOME → Game Mode    «Return to Game Mode» (ярлык, TryExec=steamosctl) или
                     ws game mode game: steamosctl пишет
                     /etc/sddm.conf.d/zzt-holo-temp-login.conf, сессия
                     завершается, SDDM (Relogin=true) входит в gamescope
Game Mode → GNOME    Steam → Power → Switch to Desktop → os-session-select
                     plasma → steamosctl switch-to-desktop-mode ubuntu.desktop
по умолчанию         /etc/sddm.conf.d/10-ws-autologin.conf: ubuntu.desktop;
                     zz-holo-autologin.conf steamos-manager идёт после него
```

xremap в Game Mode не работает (`helpws keyboard`); кнопкой питания там
владеет powerbuttond, в GNOME — gsd-power (`HandlePowerKey=ignore`).

## Проверка

`ws game check` (в `ws check`): на хосте без `gameMode` — только сообщение;
до `ws game install` — «not installed yet», без FAIL. Дальше: пакеты и их
версии, sddm и weston, display manager, `steamos-manager.service` и
`inputplumber.service` включены, пользовательский steamos-manager включён
глобально, powerbuttond в wants сессии Steam, `platform.toml` с
`ubuntu.desktop`, device-файл Legion Go без `tdp_limit`, PPD активен, режим
входа по умолчанию `desktop`.
