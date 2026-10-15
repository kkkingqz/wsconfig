title: ws-plan-legion-go-agent
section: 1
date: 2026-10-11
source: Workstation
volume: User Commands

# LEGION GO — ИНСТРУКЦИЯ ДЛЯ CLAUDE НА УСТРОЙСТВЕ

Этот файл — для Claude, запущенного на `legiongo`. Памяти сессий с mbp16
у тебя нет: всё, что из неё нужно, — здесь. Сохрани разделы 1 и 2 в свою
память (по одному правилу на файл), чтобы они пережили новые сессии.

Пользователь начинает так: «Прочитай `~/wsconfig/docs/plans/legion-go-agent.md`
и продолжай план legiongo».

# 1. Правила пользователя

Это его слова и решения, они обязательны:

1. **Отвечать по-русски.** Код, комментарии в коде и сообщения коммитов —
   по-английски, документы в `docs/` — по-русски, как в репозитории.
2. **Push сразу после каждого коммита** (`git push`): CI идёт только после
   push. Коммитить — когда работа сделана и проверена, или когда просят.
   В конце сообщения коммита — строка `Co-Authored-By` из системной
   подсказки сессии.
3. **tower (Unraid, `tower.local`, 192.168.113.113) — без изменений без
   подтверждения.** Только чтение, пока пользователь не сказал «да» на
   конкретное действие.
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
7. **Медленные тесты не перезапускать вслепую.** Весь набор идёт
   ~15–40 с; если дольше — сначала найти причину.
8. **sudo-пароль не вводить никогда.** Команды с sudo пользователь
   запускает сам; дай ему команду одной строкой.

# 2. Окружение

- Claude Desktop — Flatpak (`com.anthropic.ClaudeDesktop`). Bash
  выполняется в песочнице: там нет git, apt, systemctl, а `/usr` и `/etc` —
  от рантайма Flatpak. Команды хоста — `flatpak-spawn --host sh -c '…'`
  (или `bash -c`). Если `flatpak-spawn` отвечает `ServiceUnknown` — нет
  override: пользователь выполняет
  `flatpak override --user --talk-name=org.freedesktop.Flatpak com.anthropic.ClaudeDesktop`
  и перезапускает приложение (`flatpak kill com.anthropic.ClaudeDesktop`).
- `/home/king` из песочницы читается и пишется, а scratchpad песочницы хост
  не видит: временные файлы для команд хоста — в `~/.cache/<имя>`, потом
  удалить.
- Оболочка пользователя — fish: команды для него — без bash-синтаксиса
  (`d=$(…)`), либо внутри `bash -c '…'`.
- Репозиторий — `~/wsconfig` (`github.com/kkkingqz/wsconfig`, ветка `main`).
  Его меняет и сессия на mbp16: перед работой `git pull`, после коммита —
  push. Пометки `flatpak/apps.txt`, `distrobox/…`, `hosts.txt` у двух машин
  в одних файлах: `git pull` перед `ws switch`.
- `ws` — точка входа (`ws --help`); темы документации — `ws help` (страницы
  из `docs/`, `ws help plan-legion-go` — план). Состояние машины, которого
  нет в репозитории, — `~/.local/state/workstation/`.
- initramfs в Ubuntu 26.04 — dracut, не initramfs-tools.
- Загрузка — GRUB (`boot = "grub"`), меню на портретной панели повёрнуто;
  в GRUB без USB-клавиатуры не попасть.

# 3. С чего начать

1. Понять, где остановились:
   - `ls ~/.local/state/wsconfig/setup/` — пройденные шаги `ws setup`
     (`choices`, `prepare`, `apply1`, `apply2`, `check`, `timeshift`,
     `backup`; до плана v2, этап 9, — `bootstrap` вместо `prepare`); пока
     есть `~/.config/autostart/ws-setup.desktop`, setup не закончен — его
     перезапуск `ws setup` (до первого `ws apply home` —
     `~/.local/state/wsconfig/setup/ws/bin/ws setup`) продолжит с первого
     непройденного (его запускает пользователь: он спрашивает sudo);
   - `~/.local/state/wsconfig/setup/check.txt` — вывод `ws check` из
     setup;
   - `git -C ~/wsconfig log --oneline -10`, `git status` и
     `git tag -l 'checkpoint/*'`;
   - разделы «Этапы» в плане (`docs/plans/legion-go.md`, раздел 5) —
     отметки «сделано» с датой.
2. `ws check` — сводка всех владельцев; `ws check gaming`, `ws check steam`,
   `ws check apt`.
3. Рассказать пользователю, на каком этапе машина и что дальше, и только
   потом что-то менять.

# 4. План

Источник — `docs/plans/legion-go.md` (`ws help plan-legion-go`). Этапы 0–3
делает пользователь до тебя (BIOS, установка Ubuntu, `install.sh`); этап
4 `ws setup` проходит сам. Твоя работа — проверки этапа 4 и этапы 5–9:

- **4. База.** Проверить по списку в плане: `uname -r` (XanMod),
  `/proc/cmdline` против `kernelParams` в `nix/hosts/legiongo/facts.nix`,
  AppArmor не активен, governor `powersave` до PPD, поворот, касания,
  Wi-Fi, Bluetooth, `ws check steam` (`@steam` смонтирован). Инвентарь:
  `ws collect` (архив; раздел `hardware/`), выжимку — в `docs/history/`
  (новый файл — по правилам раздела 5).
- **5. Железо.** Сон s2idle, PPD → `platform_profile`/governor/EPP,
  вентилятор, `charge_types`, `ws-suspend swap-setup 16g` и zswap, звук на
  свёртке (PCI-адрес аудио в правилах взят из Bazzite — сверить с
  `pw-cli ls Node`; наушники: свёртка рассчитана на динамики), sysctl,
  планировщик I/O. Подробно — в плане.
- **6. Game Mode.** `wsgame build` → `wsgame install` (пакеты с
  рекомендациями, sddm вместо GDM) → reboot. Проверки — в плане, среди
  них: xremap и `workstation-widgets` в Game Mode не работают
  (`systemctl --user status xremap workstation-widgets`).
- **7. Рабочий стол** на портативном.
- **8. Recovery и backup.** Приёмник на tower для нескольких машин в
  репозитории есть (`ws help backup`), но на tower ещё не поставлен — это
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
(`wsgame`); PPD вместо TDP-демонов; пакеты apt — без Recommends, кроме
строк `rec:` (почему — план, 4.2).

# 5. Как менять репозиторий

- Изменения хоста — в `nix/hosts/legiongo/`, железа — в
  `system/hardware/legion-go.nix`, Game Mode — `system/gaming.nix`,
  `gaming/`, `bin/wsgame`. Общий код меняется так, чтобы mbp16 и wsvm
  остались прежними.
- Применение: `ws switch` (home-manager; коммитит пометки),
  `ws system apply` (системный слой, sudo — пользователь), `ws apply`
  (всё по очереди). Сравнить без изменений: `ws system diff`.
- Перед коммитом:
  - `python3 -m unittest discover -s tests -p 'test_*.py'`;
  - `ws check repo` (синтаксис, shellcheck, man-страницы);
  - `nix flake check`;
  - shellcheck той же версии, что в CI:
    `nix shell --inputs-from . nixpkgs#shellcheck -c shellcheck -x -P SCRIPTDIR -S warning ФАЙЛЫ`;
  - при изменении общего: у mbp16 те же пути store до и после —
    `nix eval --raw .#checks.x86_64-linux.home-mbp16.outPath` и
    `….system-mbp16.outPath` (так же wsvm).
- Новая страница в `docs/` — с шапкой (`title:`, `section:`, `date:`,
  `source:`, `volume:`), темой в `libexec/helpws` и строкой в
  `terminal/fish/completions/ws.fish`: это проверяет
  `tests/test_helpws.py`.
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
- Ничего не менять на tower и mbp16 без явного «да».

# 7. Известные риски

Раздел 6 плана. Главное: `ws setup` и `ws btrfs make` до этого устройства
на железе не прогонялись (только VM wsvm, ws help plan-v2, 9.10); если `@` не загрузится — в GRUB `c`, затем
`configfile /boot/grub/grub.cfg` (старый корень). `hid-lenovo-go` вместе с
InputPlumber — проверить гироскоп и кнопки. gamescope 3.16.20 может быть
старше нужного клиенту Steam. На generic-ядре AppArmor может не дать
стартовать pressure-vessel.
