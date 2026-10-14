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
libexec/wsbox                    владелец: apply, check, update, recreate
```

`ws switch` собирает в `~/.local/share/workstation/distrobox/`:

```text
containers.ini   манифест distrobox assemble
boxes.json       контейнеры по порядку: image, home, hooks, exports
                 (ALIAS: .desktop внутри контейнера), gpu, default; у
                 Windows-боксов profile, driver, dpi, init_overrides
                 (ws box, ws windows)
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

Windows-боксы и `ws windows` — `helpws windows`.

HOME каждого — `~/distrobox/NAME`; он переживает `recreate`. Rootfs —
расходный. HOME хоста смонтирован в контейнер по тому же пути
(`/home/USER/wsconfig`, `/home/USER/touchbar`).

Образы — теги: `archlinux:latest`, для build-контейнеров и
`wine` — релиз host (`@HOST_VERSION_ID@` из `/etc/os-release`). После
обновления Ubuntu `ws box check` покажет drift образа → `ws box recreate NAME`.
Digest (`repo@sha256:…`) тоже поддерживается.

## Команды

```console
ws box list | status [NAME] | apps [NAME]
ws box check [--json]
ws box dry-run [NAME]
ws box apply [--select|NAME]   создать недостающие, восстановить экспорты
ws box update [NAME...]        пакеты внутри (distrobox upgrade)
ws box recreate NAME           новый rootfs, тот же HOME
ws box remove NAME
ws box enter NAME | run NAME CMD [ARG...] | stop NAME
ws box export NAME APP | unexport NAME APP
```

`apply` не трогает существующий контейнер. `recreate` и `remove` меняют
только rootfs; описание в `distrobox.nix` и HOME остаются.

`distrobox.nix` — каталог: все контейнеры, которые можно создать. Какие
есть на машине — её `nix/hosts/HOST/boxes.toml` (`lib/ws_catalog.py`,
`helpws plan-v2`, этап 3):

```toml
yes = ["arch", "wine-wayland"]   # созданы здесь
no = ["proton"]                  # отказались
```

Контейнер, которого нет ни там, ни там, получает свой `default` из
`distrobox.nix`: `ask` (по умолчанию) — предложить, `no` — не предлагать
(`t2bce-build`, `touchbar-build`: только T2), `yes` — создать на каждой
машине без своего выбора. `ws box create NAME` и `ws box apply NAME` ставят
контейнер в `yes`, `ws box remove NAME` — в `no` (описание в `distrobox.nix`
остаётся). `recreate` выбор не трогает. Каждая машина пишет только свой
файл, комментарии в нём сохраняются; публикует его `ws sync`.

`apply` без имени создаёт контейнеры с `yes`, о тех, что в состоянии ask,
спрашивает «Поставить все? [Y/n]», на `n` — список с галочками (Space, `a`,
Enter, Esc/q), ответ пишется в `boxes.toml`. Esc/q отменяет только вопрос:
предложенные остаются ask, контейнеры с `yes` всё равно создаются.
`ws box apply --select` спрашивает и о `no`. Без терминала не предложенные не
создаются.

В Fish + Ghostty `ws box enter NAME`, `distrobox enter NAME` и
`distrobox-enter -n NAME` меняют обычный цвет текста до выхода из контейнера.
Цвета контейнеров и fallback задаются в `terminal/distrobox-colors.nix`
и применяются через `ws switch`. Подробнее: `helpws terminal`,
раздел «Цвета Distrobox-сессий».

## Изменить контейнер

1. Правка `distrobox/distrobox.nix`, `ws switch`.
2. Новый контейнер — `ws box apply NAME`; другой образ, пакеты или hooks —
   `ws box recreate NAME`.
3. `ws box check`.

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

`ws box check` проверяет пакет и отсутствие `linux`/`mkinitcpio` в
контейнерах; `ws-workstation-verify` — модуль host и `/dev/ntsync` внутри.

## Граница host

На host не ставятся toolchains проектов (Python-версии, pipx, Rust, Node
managers, SDK) и Wine. Исключения — инфраструктура, ядро и железо,
интеграция desktop, виртуализация.

## Проверка

```console
ws box check
ws check
```
