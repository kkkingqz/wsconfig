title: ws-plan-legion-go-agent
section: 1
date: 2026-10-26
source: Workstation
volume: User Commands

# LEGION GO — ИНСТРУКЦИЯ ДЛЯ CLAUDE НА УСТРОЙСТВЕ

Этот файл — для Claude, запущенного на `legiongo`. Памяти сессий с mbp16
у тебя нет: всё, что из неё нужно, — здесь. Сохрани разделы 1 и 2 в свою
память (по одному правилу на файл), чтобы они пережили новые сессии.

Пользователь начинает так: «Открой `ws help plan-legion-go-agent` и
продолжай план legiongo». Текст тот же, что в
`~/Projects/wsconfig/docs/plans/legion-go-agent.md`, если ядро склонировано
(раздел 5).

# 1. Правила пользователя

Это его слова и решения, они обязательны:

1. **Отвечать по-русски.** Код, комментарии в коде, вывод и справка
   скриптов, сообщения коммитов — по-английски, документы в `docs/` —
   по-русски, как в репозитории.
2. **Push сразу после каждого коммита** (`git push`; в конфигурации —
   `ws sync`): CI идёт только после push. Коммитить — когда работа сделана
   и проверена, или когда просят. В конце сообщения коммита — строка
   `Co-Authored-By` из системной подсказки сессии.
3. **tower (Unraid, `tower.local`) — без изменений без подтверждения.**
   Только чтение, пока пользователь не сказал «да» на конкретное действие.
4. **Не будить диски tower.** Без явного подтверждения не запускать то, что
   может раскрутить HDD: `smartctl`, `sdparm`, `sg_*`, `hdparm`, `blkid`,
   `btrfs filesystem show`, `fdisk`/`parted` на дисках, любое
   чтение/`ls`/`find`/`du`/`stat` в `/mnt/diskN`, `/mnt/user`, `/mnt/user0`
   и пулах на HDD. Состояние дисков — только из `/var/local/emhttp/disks.ini`
   (`spundown="1"` — спит) или `/proc/diskstats`.
5. **mbp16 не трогать** — ни файлы, ни поведение. Изменение общего кода
   проверяется на то, что mbp16 собирается так же (раздел 5).
6. **Чужие решения — не приписывать.** «Пользователь решил» — только если
   он это сказал; предложение Claude, на которое он не ответил, остаётся
   предложением.
7. **Медленные тесты не перезапускать вслепую.** Весь набор ядра идёт
   около минуты; если заметно дольше — сначала найти причину.
8. **sudo-пароль не вводить никогда.** Команды с sudo пользователь
   запускает сам; дай ему команду одной строкой.
9. **Ядро `kkkingqz/wsconfig` публичное:** в нём не должно быть адресов,
   UUID и другого, что относится к конкретной машине или сети, — это место
   конфигурации.

# 2. Окружение

- Claude Desktop — Flatpak (`com.anthropic.ClaudeDesktop`). Bash
  выполняется в песочнице: там нет git, apt, systemctl, nix, а `/usr` и
  `/etc` — от рантайма Flatpak. Команды хоста — `flatpak-spawn --host bash
  -lc '…'` (`-l` — чтобы в PATH были `ws` и Nix). Если `flatpak-spawn`
  отвечает `ServiceUnknown` — нет override: пользователь выполняет
  `flatpak override --user --talk-name=org.freedesktop.Flatpak com.anthropic.ClaudeDesktop`
  и перезапускает приложение (`flatpak kill com.anthropic.ClaudeDesktop`).
- Панель Terminal приложения тоже работает в песочнице: `ws apply` там не
  найдёт git и nix. Запускать через `flatpak-spawn --host`.
- `/home/king` из песочницы читается и пишется, а scratchpad песочницы хост
  не видит: временные файлы для команд хоста — в `~/.cache/<имя>`, потом
  удалить.
- Оболочка пользователя — fish: команды для него — без bash-синтаксиса
  (`d=$(…)`), либо внутри `bash -c '…'`.
- Два репозитория (`ws help architecture-v2`):
  - **конфигурация** — `~/wsconfig`, приватный `github.com/kkkingqz/wsbodya`:
    `hosts/legiongo/` (`host.toml`, `apt.txt`, `apt/`, выбор хоста в
    `flatpak.toml`, `boxes.toml`, `widgets.toml`), каталоги, `home/`;
    `flake.lock` закрепляет ревизию ядра. Публикует `ws sync` (commit,
    `git pull --rebase`, push). Её меняет и mbp16: перед работой — `git
    -C ~/wsconfig pull --rebase`;
  - **ядро** — `github.com/kkkingqz/wsconfig` (публичное): `ws`, `libexec/`,
    `system/`, `gaming/`, `docs/`. На машине оно в Nix store; для правок
    нужен клон (раздел 5).
- `ws` — точка входа (`ws --help`); темы документации — `ws help` (страницы
  из `docs/` ядра, `ws help plan-legion-go` — план). Состояние машины,
  которого нет в репозиториях, — `~/.local/state/wsconfig/`.
- initramfs в Ubuntu 26.04 — dracut, не initramfs-tools.
- Загрузка — GRUB (`boot = "grub"`), меню на портретной панели повёрнуто;
  в GRUB без USB-клавиатуры не попасть.

# 3. С чего начать

1. Понять, где остановились:
   - `ls ~/.local/state/wsconfig/setup/` — пройденные шаги `ws setup`
     (`choices`, `btrfs`, `prepare`, `layers`, `check`, `timeshift`,
     `backup`, `finish`); пока есть `~/.config/autostart/ws-setup.desktop`,
     setup не закончен — `ws setup` без аргументов продолжит с первого
     непройденного (его запускает пользователь: он спрашивает sudo);
   - `~/.local/state/wsconfig/setup/check.txt` — вывод `ws check` из
     setup (`check-fail.txt` — только FAIL);
   - `git -C ~/wsconfig log --oneline -10`, `git -C ~/wsconfig status` и
     `ws checkpoint list`;
   - раздел «Этапы» плана (`ws help plan-legion-go`, раздел 5) — отметки
     «сделано» с датой.
2. `ws check` — сводка всех владельцев; `ws check gaming`, `ws check steam`,
   `ws check apt`; `ws game status`.
3. Рассказать пользователю, на каком этапе машина и что дальше, и только
   потом что-то менять.

# 4. План

Источник — `ws help plan-legion-go`. Этапы 0–3 делает пользователь до
тебя (BIOS, установка Ubuntu, `install.sh --repo`); этап 4 `ws setup`
проходит сам. Твоя работа — проверки этапа 4 и этапы 5–9:

- **4. База.** Проверить по списку в плане: `uname -r` (XanMod),
  `/proc/cmdline` против `kernelParams` в `~/wsconfig/hosts/legiongo/host.toml`,
  AppArmor не активен, governor `powersave` до PPD, поворот, касания,
  Wi-Fi, Bluetooth, `ws check steam` (`@steam` смонтирован). Инвентарь:
  `ws collect` (архив; раздел `hardware/`), выжимку — в `docs/history/`
  ядра (новый файл — по правилам раздела 5).
- **5. Железо.** Сон s2idle, PPD → `platform_profile`/governor/EPP,
  вентилятор, `charge_types`, `ws suspend swap-setup 16g` и zswap, звук на
  свёртке (PCI-адрес аудио в правилах взят из Bazzite — сверить с
  `pw-cli ls Node`; наушники: свёртка рассчитана на динамики), sysctl,
  планировщик I/O. Подробно — в плане.
- **6. Game Mode.** Пакеты собраны и проверены на mbp16 (этап 2); на
  устройстве `ws game build` → `ws game test` → `ws game install`
  (пакеты, sddm вместо GDM) → reboot. Проверки — в плане, среди них:
  xremap и `workstation-widgets` в Game Mode не работают (`systemctl
  --user status xremap workstation-widgets`), и нет перезапускающегося
  `wsdbus-ctl watch`.
- **7. Рабочий стол** на портативном.
- **8. Recovery и backup.** Приёмник на tower для нескольких машин в
  ядре есть (`ws help backup`), но на tower ещё не поставлен — это
  изменение сервера, только с подтверждением пользователя. `ws-restore`
  умеет только rEFInd; для legiongo — ручной путь (`ws help recovery`,
  «Хосты с GRUB»).
- **9. Опционально** — каждое с замером до и после.

Каждый этап — снимок Timeshift перед изменением ядра, загрузки и питания
(`sudo timeshift --create --comments …` — пользователь) и в конце
`ws checkpoint create NAME`. Результаты проверок — в план (отметка
«сделано ДАТА» и что выяснилось), находки о железе — в `docs/history/`.

Что уже решено (не пересматривать без причины): XanMod MAIN x64v3 +
запасное generic-ядро серии 7.0 без HWE; Steam из apt (`rec:steam-installer`),
не Flatpak; компоненты Game Mode из Bazzite/OGC собраны в `.deb`
(`ws game`); PPD вместо TDP-демонов; пакеты apt — без Recommends, кроме
строк `rec:` (почему — план, 4.2); InputPlumber 0.81.0 до конца этапа 6.

# 5. Как менять репозитории

- **Конфигурация** (`~/wsconfig`): факты и пакеты хоста —
  `hosts/legiongo/`, выбор приложений и боксов — `ws flatpak …`,
  `ws box apply --select` или файлы хоста. Применить — `ws apply` (всё по
  очереди) или его шаги: `ws apply home`, `ws apply apt`, `ws apply
  system` (sudo — пользователь). Сравнить без изменений: `ws diff`,
  `ws system diff`. Опубликовать — `ws sync`.
- **Ядро** — железо в `system/hardware/legion-go.nix`, Game Mode в
  `system/gaming.nix`, `gaming/`, `libexec/wsgame`, документы в `docs/`:
  1. клон: `gh repo clone kkkingqz/wsconfig ~/Projects/wsconfig`;
  2. проверить на машине: `ws apply --core ~/Projects/wsconfig` (собирает
     конфигурацию с этим клоном, `flake.lock` не меняется);
  3. commit и push ядра, CI зелёный;
  4. `ws update core` в конфигурации (закрепляет новую ревизию), затем
     `ws apply`, `ws sync`.
  Общий код меняется так, чтобы mbp16 и wsvm остались прежними.
- Перед коммитом ядра (в `~/Projects/wsconfig`):
  - `python3 -m unittest discover -s tests`;
  - `ws check repo` (синтаксис, shellcheck, man-страницы);
  - `nix flake check`;
  - shellcheck той же версии, что в CI:
    `nix shell --inputs-from . nixpkgs#shellcheck -c shellcheck -x -P SCRIPTDIR -S warning ФАЙЛЫ`;
  - при изменении общего кода: у mbp16 те же пути store до и после — из
    конфигурации, с клоном ядра:
    `nix eval --raw ~/wsconfig#checks.x86_64-linux.home-mbp16.outPath --override-input wsconfig ~/Projects/wsconfig`
    и так же `system-mbp16` (и wsvm); «до» — тот же вызов при `git stash`
    в клоне, не `flake.lock` (он может отставать). Документы входят в
    home (`ws help`, man), поэтому правка `docs/` меняет путь home —
    сравнивать коммиты без документов.
- Новая страница в `docs/` ядра — с шапкой (`title:`, `section:`, `date:`,
  `source:`, `volume:`) и темой в `libexec/helpws`: это проверяет
  `tests/test_helpws.py`; дополнение `ws` её подхватывает само.
- После push — CI GitHub Actions (`gh run list`, `gh run watch`) должен
  быть зелёным.
- Стиль: как в окружающем коде; документы — короткие фразы по делу, без
  лишних оговорок.

# 6. Чего не делать

- BIOS N3CN42WW не ставить (Lenovo отозвала); прошивку контроллеров Go 1
  через fwupd не обновлять (предлагается прошивка Go 2).
- Не включать HWE-ядро и не менять ядро по умолчанию без снимка Timeshift.
- Не перезапускать `ws btrfs make` после того, как раскладка сделана.
- Не ставить пакеты apt со всеми Recommends: среди них seatd (libseat
  выбирает его раньше logind — gamescope ушёл бы с пути SteamOS) и тема
  GTK для Qt.
- Не класть в ядро адреса, UUID и данные этой машины — они в
  `hosts/legiongo/` конфигурации.
- Ничего не менять на tower и mbp16 без явного «да».

# 7. Известные риски

Раздел 6 плана. Главное: `ws setup` и `ws btrfs make` до этого устройства
на железе с GRUB не прогонялись (живая проверка на VM wsvm отложена, ws
help plan-v2, 9.10); если `@` не загрузится — в GRUB `c`, затем
`configfile /boot/grub/grub.cfg` (старый корень). Первый `ws apply`
до перезахода останавливает `ws keyboard apply` («log out/in and rerun»):
расширения GNOME и wsdbus ещё не загружены — второй `ws apply` после
reboot это снимает. `hid-lenovo-go` вместе с InputPlumber — проверить
гироскоп и кнопки. gamescope 3.16.20 может быть старше нужного клиенту
Steam. На generic-ядре AppArmor может не дать стартовать pressure-vessel.
