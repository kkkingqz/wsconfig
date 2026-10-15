title: ws-setup
section: 1
date: 2026-10-15
source: Workstation
volume: User Commands

# SETUP — НОВЫЙ ПК НА WSCONFIG

`install.sh` и `ws setup` ведут свежую Ubuntu 26.04 до проверенной рабочей
станции. Сообщения и вопросы — на английском. Все вопросы задаются в начале, дальше от пользователя нужны
только перезагрузки и вход. Хост с GRUB проходит весь путь сам. Хост с
rEFInd (T2, mbp16) проходит его с проверкой ручных шагов (ниже, «T2 и
rEFInd»).

## Запуск

Сначала установить Ubuntu: ESP и корень Btrfs без отдельного `/boot`
(`ws help rebuild`, разделы 2–3). Затем в терминале — для конфигурации,
которая уже есть:

```console
wget -qO- https://raw.githubusercontent.com/kkkingqz/wsconfig/main/install.sh | bash -s -- --repo URL_КОНФИГУРАЦИИ
```

или для новой конфигурации:

```console
wget -qO- https://raw.githubusercontent.com/kkkingqz/wsconfig/main/install.sh | bash -s -- --new
```

`wget` есть в Ubuntu Desktop сразу, `curl` — нет. Ещё аргументы:
`--host ИМЯ` (имя хоста, если по `hostname` его не найти) и `--core REV`
(ветка, тег или коммит ядра; без него — `main`).

`install.sh` делает только то, без чего `ws` не запустится:

1. Проверяет: не root, Ubuntu 26.04, `/` на Btrfs.
2. Ставит из apt `git`, `gh`, `python3-tomlkit`, `xdg-terminal-exec` и
   `util-linux-extra` (`sg`).
3. Один раз переводит REV в коммит (`git ls-remote`).
4. Создаёт подвольюм `@nix` в `/nix`. Для этого берёт `lib/btrfs.bash` той
   же ревизии.
5. Ставит Nix из apt (`nix-bin`, `nix-setup-systemd`) и `nix-daemon.socket`,
   добавляет пользователя в группу `nix-users`.
6. Собирает `ws` этой ревизии в GC root `~/.local/state/wsconfig/setup/ws`
   и записывает ревизию в `.../setup/core`.
7. Запускает `ws setup` с остальными аргументами. Группа в этой сессии ещё
   не действует, поэтому через `sg nix-users`.

Повторный запуск `install.sh` не повторяет сделанное.

## Конфигурация и ядро

- `--repo URL|PATH` клонирует конфигурацию в `~/wsconfig`. Для URL GitHub
  сначала входит в GitHub (`gh auth login` в браузере по одноразовому
  коду), так доступен и закрытый репозиторий; git получает `gh auth
  setup-git`, имя и email — из аккаунта.
  - Существующий клон того же URL — продолжение.
  - Непустой каталог с чем-то другим — отказ: ничего не перезаписывается.
- `--new [DIR]` создаёт конфигурацию в DIR (`~/wsconfig`) из `template/`
  ядра:
  - flake.nix, wsconfig.toml, .gitignore, README, `apt.txt`, каталоги
    модулей;
  - flake.lock закрепляет ядро ревизии setup, а nixpkgs, home-manager и
    wswidgets — как flake.lock этого ядра (связка, которую собрал его CI);
  - `git init` и локальный коммит; наружу ничего не уходит;
  - каталог только новый или пустой.
- Конфигурацию ведёт её ядро. Если flake.lock закрепляет другую ревизию,
  `ws setup` собирает её из самой конфигурации (`nix build
  git+file:~/wsconfig#ws`) в тот же GC root и запускается заново уже ею.
  - Ядро старше `ws setup` — отказ: сначала `ws update core` на другой
    машине.
  - Затем ядро проверяет схему конфигурации (`wsconfig.toml`).
- После перезагрузки `ws setup` подтягивает `main` конфигурации (`git pull
  --ff-only`, если в ней нет изменений), а следом и её ядро.

## Что спрашивает

1. Пароль sudo — в начале каждого запуска.
2. Хост. Если есть `host.toml` с этим `hostname` — это он. Иначе выбор из
   хостов конфигурации (отмечен тот, что назван как этот ПК) или «new
   host…» и имя (в поле — `hostname`); `--host` — без вопроса. Имя:
   строчные латинские буквы, цифры, `-` и `_`, до 23 знаков; из него же
   пользователь приёмника `wsbackup-HOST` на Unraid.
   - Существующий хост даёт ПК свой `hostname`.
   - Новое имя — новый хост из инвентаризации машины
     (`lib/ws_inventory.py`, без root):
     - железо по DMI: MacBookPro16,1 → `t2-mbp16`, Legion Go (83E1) →
       `legion-go`, остальное → `generic-pc`;
     - загрузка по железу: rEFInd на T2, GRUB на остальном;
     - масштаб экрана из `~/.config/monitors.xml`;
     - виртуальная машина или нет, есть ли `/dev/kvm`.

     Железо не из списка и виртуальную машину человек подтверждает. Если в
     конфигурации есть хост того же железа, setup спрашивает, взять ли его
     за основу: тогда берутся параметры ядра, `apt.txt`, `apt/`, а выбор
     хоста — нет. Затем слои: VM (без `/dev/kvm` — нет без вопроса),
     виджеты, Steam из apt, Game Mode.

   Новый хост коммитится. Публикуется он вместе с выбором после вопроса
   «Publish the new host and the choices (ws sync)?». Без remote `ws sync` коммитит локально.
3. Списки с галочками (`lib/ws_catalog.py offer --all --setup`):
   - что предлагается: приложения каталога Flatpak, контейнеры Distrobox,
     при `widgets = true` виджеты, скрипты `scripts/` (ws help scripts) и
     overrides Flatpak — всё, где у этого хоста нет выбора;
   - что отмечено: `default` ask и yes отмечены, no — нет; overrides — общие
     значения каталога у приложений, которые на хосте будут;
   - куда записывается: `yes`/`no` в `hosts/HOST/*.toml` (снятый override —
     `skip` хоста), затем публикация (`ws sync`); `ws apply` потом ничего
     не спрашивает;
   - один список Gum на модуль: Space ставит и снимает галочку, Ctrl+A —
     все, Enter принимает, Esc — выход без записи;
   - при `nativeSteam = true` Steam из Flatpak не предлагается: `no` без
     вопроса (Steam там из apt).
4. Лицензии пакетов, которые иначе спросил бы apt посреди подготовки
   системы: Microsoft core fonts (`ubuntu-restricted-extras`) и, при
   `nativeSteam = true`, Steam (debconf).
5. «Start?» — дальше без вопросов.
6. С `--new`, в самом конце: «Create a private GitHub repository for the configuration?»; по
   умолчанию «нет». На «да» setup входит в GitHub и делает `gh repo create
   --private ИМЯ --source ~/wsconfig --push`. Позже это можно сделать той
   же командой.

## Что делает дальше

```text
ws btrfs make --yes      раскладка Btrfs, шаг 1 (ws help rebuild, раздел 3);
                         @nix остаётся на верхнем уровне
reboot
ws btrfs make --yes      шаг 2: проверка, старый корень удаляется
подготовка системы       libexec/ws-prepare: apt, @vms, @steam, @wsbackup,
                         группы, fish, первый ws apply home
reboot
ws apply                 первый проход: apt, системные файлы, home-manager, модули;
                         новые расширения GNOME — после входа
reboot
ws apply
ws check                 FAIL не останавливает: список — в конце
Timeshift                /etc/timeshift/timeshift.json, если его нет: Btrfs,
                         @home, monthly 1, weekly 3, boot 3 (как mbp16);
                         снимок «setup» («setup, ws check FAIL» при FAIL)
backup                   ключ ~/.ssh/wsbackup_ed25519 (@wsbackup — подготовка)
ws apply home, ws checkpoint create setup, ws sync после вопроса
```

После каждой перезагрузки `ws setup` после входа продолжает сам:
- до конца в `~/.config/autostart/ws-setup.desktop` лежит его запуск в
  терминале (`xdg-terminal-exec .../setup/ws/bin/ws setup --autostart`), в
  конце файл удаляется;
- пройденные шаги — `~/.local/state/wsconfig/setup/*.done`, остальное
  определяется по системе;
- повторный запуск (`ws setup`) начинает с первого непройденного;
- ошибка команды останавливает с сообщением, окно автозапуска ждёт Enter.

FAIL в `ws check` setup не останавливает:
- снимок Timeshift получает комментарий «setup, ws check FAIL»;
- в конце печатаются строки FAIL, весь вывод —
  `~/.local/state/wsconfig/setup/check.txt`;
- `ws checkpoint create setup` при расхождении системы с деревом не
  создаётся.

После исправления: `ws check`, `sudo timeshift --create --comments
checked`, `ws checkpoint create setup`.

## T2 и rEFInd

Хост с `boot = "refind-grub-recovery"` (mbp16) идёт тем же путём, кроме
`ws btrfs make`. Его шаги `ws help rebuild` (разделы 2–5) делаются руками,
`ws setup` их проверяет и останавливается со списком того, что осталось.
После исправления — снова `ws setup`.

До подготовки системы:
- `/` на `@`, `@` — подвольюм по умолчанию;
- ядро T2;
- `rootUuid` — UUID `/`;
- `refindEspPartuuid` — отдельный раздел vfat, не `/boot/efi`.

После `ws apply`:
- firmware Wi‑Fi (`brcmfmac4364`);
- `resume=`/`resume_offset=` в `kernelParams` — `/swap/swapfile`;
- `refind.conf` на ESP — собранный (ESP монтируется только для чтения на
  время сравнения).

`ws setup --check` показывает обе группы и ничего не меняет. На хосте с
GRUB он отвечает, что ручных шагов нет.

## Не сделано

- **Backup на Unraid для нового хоста.** Приёмник умеет несколько машин
  (`hosts/HOST/` на flash, пользователь `wsbackup-HOST`; `ws help backup`,
  «Несколько workstation»), но на tower новый `boot.sh` ещё не стоит:
  это работа на сервере с подтверждением. setup готовит только сторону ПК
  (`@wsbackup`, ключ). `backup/config.toml` и alias SSH он не пишет.
- **Восстановление с Unraid на GRUB.** `ws-restore` (Live USB) умеет только
  rEFInd. Для нового хоста — Timeshift на месте или вручную с NAS (`ws help
  recovery`, «Хосты с GRUB»).
- **Живой прогон T2.** Проверки T2 проверены тестами и `ws setup --check`
  на mbp16. Весь путь — при следующей переустановке mbp16.
- **Живой прогон GRUB** (`--new` и `--repo` на свежей Ubuntu) — `ws help
  plan-v2`, 9.10; до него проверены тесты на заглушках, сборка
  результата `--new` и shellcheck.
