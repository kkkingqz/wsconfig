title: ws-setup
section: 1
date: 2026-10-10
source: Workstation
volume: User Commands

# SETUP — НОВЫЙ ПК НА WSCONFIG

`setup.sh` ведёт свежую Ubuntu 26.04 до проверенной рабочей станции: все
вопросы — в начале, дальше от пользователя только перезагрузки и вход.
Только хосты с GRUB (`boot = "grub"`); mbp16 с rEFInd — `helpws rebuild` (ниже,
«Не сделано»).

## Запуск

Установка Ubuntu: ESP и корень Btrfs без отдельного `/boot`
(`helpws rebuild`, разделы 2–3). Затем в терминале:

```console
wget -qO- https://raw.githubusercontent.com/kkkingqz/wsconfig/main/setup.sh | bash
```

`wget` есть в Ubuntu Desktop сразу, `curl` — нет. Скрипт ставит `git`,
клонирует `~/wsconfig` и продолжает уже оттуда; повторный запуск —
`~/wsconfig/setup.sh`.

## Что спрашивает

1. Пароль sudo — в начале каждого запуска.
2. Вход в GitHub: `gh auth login` в браузере по одноразовому коду; git
   получает `gh auth setup-git`, имя и email — из аккаунта, если их ещё нет.
3. Хост. Есть `facts.nix` с этим `hostname` — он. Нет — имя: существующий
   хост даёт ПК свой `hostname`; новое имя — новый хост из generic-pc
   (`hardware = "generic-pc"`, GRUB, `quiet splash`) с тремя вопросами: VM,
   Steam из apt, Game Mode. Новый хост коммитится и пушится сразу.
4. Списки с галочками (`lib/setup_marks.py`): приложения Flatpak,
   контейнеры Distrobox и overrides Flatpak — всё, где нет пометки этого
   хоста. `all=yes` и `ask` отмечены, `all=no` — нет; overrides — только
   приложений, которые на хосте будут. Ответ — `HOST=yes|no` на каждой
   показанной строке, коммит и пуш; `ws apply` потом ничего не спрашивает.
   Esc — выход без записи.
5. Лицензии пакетов, которые иначе спросил бы apt посреди `bootstrap.sh`:
   Microsoft core fonts (`ubuntu-restricted-extras`) и, при
   `nativeSteam = "yes"`, Steam (debconf).
6. «Начать?» — дальше без вопросов.

## Что делает дальше

```text
ws btrfs make --yes      раскладка Btrfs, шаг 1 (helpws rebuild, раздел 3)
reboot
ws btrfs make --yes      шаг 2: проверка, старый корень удаляется
bootstrap.sh             @nix, apt, @vms, @steam, @wsbackup, группы, fish, ws switch
reboot
ws system apply
ws apply                 первый проход: новые расширения GNOME — после входа
reboot
ws apply
ws check                 FAIL не останавливает: список — в конце
Timeshift                /etc/timeshift/timeshift.json, если его нет: Btrfs,
                         @home, monthly 1, weekly 3, boot 3 (как mbp16);
                         снимок «setup» («setup, ws check FAIL» при FAIL)
backup                   ключ ~/.ssh/wsbackup_ed25519 (@wsbackup — bootstrap.sh)
ws switch, ws checkpoint create setup, git push
```

После каждой перезагрузки после входа setup.sh продолжает сам: до конца в
`~/.config/autostart/ws-setup.desktop` лежит его запуск в терминале
(`xdg-terminal-exec`); в конце файл удаляется. Пройденные шаги —
`~/.local/state/workstation/setup/*.done`, остальное определяется по
системе; повторный запуск начинает с первого непройденного. Ошибка
команды останавливает с сообщением, окно автозапуска ждёт Enter.

FAIL в `ws check` setup.sh не останавливает: снимок Timeshift получает
комментарий «setup, ws check FAIL», в конце печатаются строки FAIL (весь
вывод — `~/.local/state/workstation/setup/check.txt`). `ws checkpoint
create setup` при расхождении системы с деревом не создаётся. После
исправления: `ws check`, `sudo timeshift --create --comments checked`,
`ws checkpoint create setup`.

## Не сделано

- **Backup на Unraid для нового хоста.** Приёмник принимает один `HOST_ID`
  (`receiver.conf`, сейчас mbp16): другому хосту нужны свои config и ключ на
  сервере — отдельная работа на tower с подтверждением. setup.sh готовит
  только сторону ПК (`@wsbackup`, ключ); `config.json` и alias SSH
  (`helpws backup`) не пишет.
- **mbp16 (rEFInd).** setup.sh отказывает (`boot = "refind-grub-recovery"`);
  переустановка — по `helpws rebuild`. Вернуться позже:
  - значения диска в `facts.nix` после переустановки: `rootUuid`,
    `refindEspPartuuid`, `resume=UUID` и `resume_offset` в `kernelParams`;
  - репозиторий T2 и `linux-t2`, удаление generic-ядра, firmware Wi‑Fi и
    Bluetooth из macOS или архива (`helpws rebuild`, раздел 4);
  - `refind.conf` на отдельный ESP вручную (раздел 5);
  - восстановление из архива `ws collect` (состояние, baseline).
- Сценарий целиком не прогонялся: проверены тесты списков и раскладки, синтаксис
  и shellcheck.
