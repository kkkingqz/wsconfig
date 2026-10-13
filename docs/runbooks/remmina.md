title: ws-remmina
section: 1
date: 2026-10-13
source: Workstation
volume: User Commands

# REMMINA — RDP CLIENT

Remmina (RDP, VNC, SPICE) — из Nix, а не из apt: у FreeRDP Ubuntu нет H.264,
у Remmina 1.4.43 — файлов через буфер обмена RDP. Только на реальных
машинах (`boot` не `container`): контейнерный хост сам RDP-сервер
(`helpws plan-wsgnomebox`).

## Источник

```text
remmina/package.nix     Remmina из nixpkgs + патчи
remmina/patches/        mr2776, mr2777, reuse-file-context (.diff)
remmina/remmina.nix     пакет, .desktop, иконки, ключи remmina.pref
remmina/remmina-pref.py ставит эти ключи, остальное не трогает
nix/hosts/machine-apt.txt  purge: пакетов remmina из apt
```

`ws switch` ставит `remmina` в `~/.nix-profile/bin`, ярлыки
`org.remmina.Remmina.desktop` и `org.remmina.Remmina-file.desktop` в
`~/.local/share/applications` (Exec — путь в `/nix/store`: `~/.nix-profile/share`
не в `XDG_DATA_DIRS`) и иконки в `~/.local/share/icons`. ID ярлыков те же, что
у пакета apt: `rdp://`, файлы `.remmina` и разрешение GNOME на перехват
клавиатуры (`helpws keyboard`) остаются за Remmina. `bootstrap.sh` удаляет
пакеты apt (`purge:`), `ws check apt` проверяет, что их нет.

## Патчи

- **!2776** — утечки памяти буфера обмена; в upstream влит после 1.4.43,
  !2777 на нём построен.
- **!2777** — файлы через буфер обмена в обе стороны (FreeRDP
  `CliprdrFileContext`): копировать на сервере — вставлять в Files, и
  наоборот. Файлы с сервера — FUSE в `/tmp/com.freerdp.client.cliprdr.PID`
  через `/usr/bin/fusermount3` (`fuse3` приходит с flatpak и fuse-overlayfs).
  Merge request открыт; diff — состояние 2026-10-12.
- **reuse-file-context** — наш. После перенаправления RDS-брокером (так
  подключается 192.168.113.113) канал буфера открывается заново; !2777
  создавал второй файловый контекст, старый с FUSE-монтированием оставался,
  и вставка файлов с сервера ничего не находила. Один контекст на
  подключение, как в xfreerdp.

Новая Remmina в nixpkgs останавливает `ws switch` (assert в `package.nix`):
проверить, влиты ли !2776 и !2777 и применяются ли diff, затем поднять версию
в assert.

## Качество

Быстрое подключение (строка поиска в главном окне) берёт значения из
профиля по умолчанию — группы `[remmina]` в `~/.config/remmina/remmina.pref`.
`ws switch` ставит там:

```text
[remmina]      quality=9          Best (без ws switch — Poor)
               colordepth=99      кодек выбирает сервер: H.264 (AVC420)
               network=autodetect сервер меряет канал
[remmina_pref] rdp_quality_9=180  Best: всё, плюс сглаживание шрифтов и
                                  композиция (у Remmina 80, без композиции)
```

Остальные ключи файла — Remmina; изменённые в настройках эти четыре
`ws switch` вернёт. Сохранённые профили — со своими значениями.

Замер 2026-10-13 (перетаскивание окон на 192.168.113.113, 15 с): Remmina из
apt — RemoteFX Progressive, 19.5 кадра/с; эта сборка — H.264, 24.1; KRDC —
H.264, 25.7. AVC444 сервер не выбирает (политика Windows «Prioritize
H.264/AVC 444»), больше 30 кадров/с Windows по RDP не отдаёт без
`DWMFRAMEINTERVAL` на сервере.

Какой кодек выбран:

```console
WLOG_LEVEL=WARN WLOG_FILTER=com.freerdp.channels.rdpgfx.client:DEBUG remmina 2>&1 | grep -m3 'Got GFX'
```

## Проверка

```console
ws check apt        # purged: remmina…
remmina --version
```
