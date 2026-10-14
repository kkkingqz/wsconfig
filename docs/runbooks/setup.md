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
3. Хост. Есть `host.toml` с этим `hostname` — он. Нет — имя (строчные
   латинские буквы, цифры, `-` и `_`, до 23 знаков: из него и пользователь
   приёмника `wsbackup-HOST` на Unraid): существующий
   хост даёт ПК свой `hostname`; новое имя — новый хост из generic-pc
   (`hardware = "generic-pc"`, GRUB, `quiet splash`) с тремя вопросами: VM,
   Steam из apt, Game Mode. Новый хост коммитится; публикуется он вместе с
   выбором после вопроса «Опубликовать (ws sync)?».
4. Списки с галочками (`lib/ws_catalog.py offer --all --setup`): приложения каталога Flatpak,
   контейнеры Distrobox, при `widgets = true` виджеты и overrides Flatpak —
   всё, где у этого хоста нет выбора. `default` ask и yes отмечены, no — нет;
   overrides — общие значения каталога у приложений, которые на хосте будут.
   Ответ — `yes`/`no` в `nix/hosts/HOST/*.toml` (снятый override — `skip`
   хоста), затем публикация (`ws sync`); `ws apply` потом ничего не
   спрашивает. Esc — выход без записи. При `nativeSteam = true` Steam из
   Flatpak не предлагается: `no` без вопроса (Steam там из apt).
5. Лицензии пакетов, которые иначе спросил бы apt посреди `bootstrap.sh`:
   Microsoft core fonts (`ubuntu-restricted-extras`) и, при
   `nativeSteam = true`, Steam (debconf).
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
`~/.local/state/wsconfig/setup/*.done`, остальное определяется по
системе; повторный запуск начинает с первого непройденного. Ошибка
команды останавливает с сообщением, окно автозапуска ждёт Enter.

FAIL в `ws check` setup.sh не останавливает: снимок Timeshift получает
комментарий «setup, ws check FAIL», в конце печатаются строки FAIL (весь
вывод — `~/.local/state/wsconfig/setup/check.txt`). `ws checkpoint
create setup` при расхождении системы с деревом не создаётся. После
исправления: `ws check`, `sudo timeshift --create --comments checked`,
`ws checkpoint create setup`.

## Не сделано

- **Backup на Unraid для нового хоста.** Приёмник умеет несколько машин
  (`hosts/HOST/` на flash, пользователь `wsbackup-HOST`; `helpws backup`,
  «Несколько workstation»), но на tower новый `boot.sh` ещё не стоит —
  это работа на сервере с подтверждением. setup.sh готовит только сторону
  ПК (`@wsbackup`, ключ); `config.json` и alias SSH не пишет: адреса
  приёмника не хранятся в репозитории.
- **Восстановление с Unraid на GRUB.** `ws-restore` (Live USB) умеет только
  rEFInd; новый хост — Timeshift на месте или вручную с NAS (`helpws
  recovery`, «Хосты с GRUB»).
- **mbp16 (rEFInd).** setup.sh отказывает (`boot = "refind-grub-recovery"`);
  переустановка — по `helpws rebuild`. Вернуться позже:
  - значения диска в `host.toml` после переустановки: `rootUuid`,
    `refindEspPartuuid`, `resume=UUID` и `resume_offset` в `kernelParams`;
  - репозиторий T2 и `linux-t2`, удаление generic-ядра, firmware Wi‑Fi и
    Bluetooth из macOS или архива (`helpws rebuild`, раздел 4);
  - `refind.conf` на отдельный ESP вручную (раздел 5);
  - восстановление из архива `ws collect` (состояние, baseline).
- Сценарий целиком не прогонялся: проверены тесты списков и раскладки, синтаксис
  и shellcheck.
