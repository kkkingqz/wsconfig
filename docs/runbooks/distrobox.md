title: ws-distrobox
section: 1
date: 2026-09-28
source: Workstation
volume: User Commands

# DISTROBOX / PODMAN — MANAGED CONTAINERS

Приложения и toolchains, которым не место на host, живут в контейнерах
Distrobox под rootless Podman. Как слой появился: `helpws history-distrobox`.

## Источник

```text
distrobox/distrobox.nix          контейнеры, пакеты, hooks, экспорты
distrobox/arch/…, distrobox/wine/…  hooks (root, при каждом старте; сделанное пропускают)
distrobox/arch/wsbox-host-ntsync/   пакет-заглушка NTSYNC-MODULE для Arch
bin/wsbox                        владелец: apply, check, update, recreate
```

`ws switch` собирает в `~/.local/share/workstation/distrobox/`:

```text
containers.ini   манифест distrobox assemble
exports.ini      [BOX] ALIAS=.desktop внутри контейнера
boxes.ini        [BOX] home, gpu; у Windows-боксов profile, driver, dpi (wswin)
```

Host-пакеты (`podman`, `distrobox`, `uidmap`, …) — в `nix/hosts/apt.txt`,
модуль `ntsync` — `system/files/modules-load.d/ntsync.conf` (`ws system apply`).

## Контейнеры

```text
arch            Arch: AUR (paru), makepkg; без Wine
wine-wayland    Windows-программы, Wine с Wayland-драйвером (по умолчанию)
wine            Windows-программы через XWayland, WineHQ stable
proton          игры: umu-launcher + Proton, GPU AMD при загрузке с ней
t2bce-build     ручные сборки ядра/модулей (релиз host)
touchbar-build  порт Touch Bar, Rust в своём HOME (релиз host)
```

Windows-боксы и `wswin` — `helpws windows`.

HOME каждого — `~/distrobox/NAME`; он переживает `recreate`. Rootfs —
расходный. HOME хоста смонтирован в контейнер по тому же пути
(`/home/USER/wsconfig`, `/home/USER/touchbar`).

Образы — теги: `archlinux:latest`, для build-контейнеров и
`wine` — релиз host (`@HOST_VERSION_ID@` из `/etc/os-release`). После
обновления Ubuntu `wsbox check` покажет drift образа → `wsbox recreate NAME`.
Digest (`repo@sha256:…`) тоже поддерживается.

## Команды

```console
wsbox list | status [NAME] | apps [NAME]
wsbox check [--json]
wsbox dry-run [NAME]
wsbox apply [NAME]            создать недостающие, восстановить экспорты
wsbox update [NAME...]        пакеты внутри (distrobox upgrade)
wsbox recreate NAME           новый rootfs, тот же HOME
wsbox remove NAME
wsbox enter NAME | run NAME CMD [ARG...] | stop NAME
wsbox export NAME APP | unexport NAME APP
```

`apply` не трогает существующий контейнер. `recreate` и `remove` меняют
только rootfs; описание в `distrobox.nix` и HOME остаются.

В Fish + Ghostty `wsbox enter NAME`, `distrobox enter NAME` и
`distrobox-enter -n NAME` меняют обычный цвет текста до выхода из контейнера.
Цвета контейнеров и fallback задаются в `terminal/distrobox-colors.nix`
и применяются через `ws switch`. Подробнее: `helpws terminal`,
раздел «Цвета Distrobox-сессий».

## Изменить контейнер

1. Правка `distrobox/distrobox.nix`, `ws switch`.
2. Новый контейнер — `wsbox apply NAME`; другой образ, пакеты или hooks —
   `wsbox recreate NAME`.
3. `wsbox check`.

Пакеты, поставленные руками внутри (AUR в `arch`), после `recreate` ставятся
снова: `helpws rebuild`, раздел 6.3.

## NTSync

Wine использует NTSync ядра host. В Arch `wine` тянет `ntsync-autoload`,
которому нужен `NTSYNC-MODULE`; без него pacman ставит в контейнер ядро Arch.
`wsbox-host-ntsync` объявляет `NTSYNC-MODULE` и ничего не содержит; hook
`install-hook` собирает и ставит его в `arch`, `wine-wayland`, `proton` при
первом старте.

```console
pacman -T NTSYNC-MODULE      # внутри: пустой вывод
ls -l /dev/ntsync            # и на host, и внутри
```

`wsbox check` проверяет пакет и отсутствие `linux`/`mkinitcpio` в
контейнерах; `ws-workstation-verify` — модуль host и `/dev/ntsync` внутри.

## Граница host

На host не ставятся toolchains проектов (Python-версии, pipx, Rust, Node
managers, SDK) и Wine. Исключения — инфраструктура, ядро и железо,
интеграция desktop, виртуализация.

## Проверка

```console
wsbox check
ws check
```
