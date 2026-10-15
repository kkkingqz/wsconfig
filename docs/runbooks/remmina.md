title: ws-remmina
section: 1
date: 2026-10-13
source: Workstation
volume: User Commands

# REMMINA — RDP CLIENT

Remmina (RDP, VNC, SPICE) — из Nix, а не из apt: у FreeRDP Ubuntu нет H.264,
у Remmina 1.4.43 — файлов через буфер обмена RDP. FreeRDP для неё собран
без OpenH264: декодеры H.264 FreeRDP перебирает по порядку и берёт первый
запустившийся, OpenH264 раньше ffmpeg, а он однопоточный. H.264
декодирует ffmpeg, на процессоре (VA-API у FreeRDP 3 экспериментальный и
выключен). Только на реальных
машинах (`boot` не `container`): контейнерный хост сам RDP-сервер
(`ws help plan-wsgnomebox`).

## Источник

```text
remmina/package.nix     Remmina из nixpkgs + патчи
remmina/patches/        mr2776, mr2777, reuse-file-context (.diff)
remmina/remmina.nix     пакет, .desktop, иконки, ключи remmina.pref
remmina/remmina-pref.py ставит эти ключи, остальное не трогает
system/apt-machine.txt  purge: пакетов remmina из apt
```

`ws apply` ставит `remmina` в `~/.nix-profile/bin`, ярлыки
`org.remmina.Remmina.desktop` и `org.remmina.Remmina-file.desktop` в
`~/.local/share/applications` (Exec — путь в `/nix/store`: `~/.nix-profile/share`
не в `XDG_DATA_DIRS`) и иконки в `~/.local/share/icons`. ID ярлыков те же, что
у пакета apt: `rdp://`, файлы `.remmina` и разрешение GNOME на перехват
клавиатуры (`ws help keyboard`) остаются за Remmina. Подготовка `ws setup` и `ws apply apt` удаляют
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

Новая Remmina в nixpkgs останавливает `ws apply` (assert в `package.nix`):
проверить, влиты ли !2776 и !2777 и применяются ли diff, затем поднять версию
в assert.

## Качество

Быстрое подключение (строка поиска в главном окне) берёт значения из
профиля по умолчанию — группы `[remmina]` в `~/.config/remmina/remmina.pref`.
`ws apply` ставит там:

```text
[remmina]      quality=9          Best (без ws apply — Poor)
               colordepth=99      кодек выбирает сервер: H.264 (AVC420)
               network=autodetect сервер меряет канал
[remmina_pref] rdp_quality_9=180  Best: всё, плюс сглаживание шрифтов и
                                  композиция (у Remmina 80, без композиции)
```

Остальные ключи файла — Remmina; изменённые в настройках эти четыре
`ws apply` вернёт. Сохранённые профили — со своими значениями.

Замер 2026-10-13 (перетаскивание окон на 192.168.113.113 — gnomebox-desktop
на tower, gnome-remote-desktop 50, 15 с): Remmina из apt — RemoteFX
Progressive, 19.5 кадра/с; эта сборка с OpenH264 — H.264 (AVC420), 24.1;
KRDC — H.264, 25.7. Это среднее за 15 с вместе с паузами движения, его
задаёт сам перетаскивающий.

Без OpenH264 (ffmpeg): пока картинка меняется, 50–60 кадров/с, поток
1.4 Мбит/с, кадр около 3 КБ, клиент на кадр 4 мс, неподтверждённых кадров
в пути нет.

Частоту задаёт не настройка: gnome-remote-desktop рисует до 60 кадров/с
(NVENC, постоянное качество, без предела битрейта) и шлёт следующий кадр,
когда клиент подтвердил предыдущие; при пинге меньше ~17 мс в пути не
больше двух кадров. Ограничить её могут канал (до tower через WireGuard
~73 Мбит/с) и время клиента на кадр.

Какой кодек выбран:

```console
WLOG_LEVEL=WARN WLOG_FILTER=com.freerdp.channels.rdpgfx.client:DEBUG remmina 2>&1 | grep -m3 'Got GFX'
```

## Проверка

```console
ws check apt        # purged: remmina…
remmina --version
```
