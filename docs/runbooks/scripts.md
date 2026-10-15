title: ws-scripts
section: 1
date: 2026-10-15
source: Workstation
volume: User Commands

# WORKSTATION SCRIPTS

Свои скрипты пользователя: файл в `scripts/` конфигурации — команда с тем
же именем. Скрипт запускается по имени (`photos-import ARG…`) из
терминала, сочетания клавиш GNOME или .desktop; `ws script run` нет.
Какие скрипты стоят на каком хосте — выбор хоста, как у Flatpak и
Distrobox. Модуль — `ws script` (`libexec/wsscript`), сборка —
`scripts/scripts.nix` ядра.

## Где что

```text
~/wsconfig/scripts/
├── catalog.toml        необязательный: default и описание
├── photos-import       скрипт: имя файла = команда, любой язык (shebang)
├── disk-report.py
└── lib/                резерв под библиотеки (не команда)

hosts/HOST/scripts.toml   yes = [...], no = [...]
~/.local/bin/NAME         ссылка на ~/wsconfig/scripts/NAME у скриптов yes
```

- Скрипт — любой обычный файл `scripts/`, кроме скрытых, `catalog.toml`
  и `lib/`. Команда — имя файла как есть: `scripts/foo.py` → `foo.py`.
  Допустимы буквы, цифры и `. _ + -`, первым — буква или цифра.
- Описание для `ws script list` и чеклистов — первая строка-комментарий
  после shebang.
- `~/.local/bin/NAME` ведёт прямо в checkout: правка файла действует
  сразу, без apply. Новый скрипт или другой выбор — `ws apply scripts`.
- `~/.local/bin` уже в PATH: у fish (`user-bin.fish` ядра), у сессии
  GNOME и у bash (`~/.profile` Ubuntu).
- Сборка — `~/.local/share/wsconfig/scripts/scripts.json`: какие скрипты
  стоят по последней сборке (`ws script list`, `ws script check`).

## Добавить скрипт

Руками: положить файл в `~/wsconfig/scripts/` и запустить `ws apply`.

- `ws apply` сам делает `git add` нового файла `scripts/` и пишет
  `added to Git: scripts/NAME`. Flake видит только файлы Git, поэтому без
  этого скрипта не было бы в сборке.
- Чеклист `ws apply` спрашивает, ставить ли скрипт на этом хосте; ответ
  пишется в `hosts/HOST/scripts.toml`.
- Шаг `scripts` (`ws script apply`) ставит бит исполнения скриптам этого
  хоста; Git хранит его.
- `ws sync` публикует файл и выбор; на другом хосте после `git pull`
  `ws apply` спрашивает о новом скрипте в общем чеклисте.

Командой:

```sh
ws script add photos-import          # заготовка bash, yes здесь, ws apply scripts
ws script add backup-db ~/tmp/db.sh  # готовый файл
ws script edit photos-import         # $VISUAL / $EDITOR на файле checkout
```

`ws script add` отказывает, если имя занято ядром (`ws`, `xremap`),
`home/.local/bin/` конфигурации или командой системы: `~/.local/bin`
стоит в PATH раньше `/usr/bin`, скрипт спрятал бы её.

Автодобавление в Git — только для `scripts/` (ws help architecture-v2,
раздел 7): здесь файл и есть позиция каталога. Файл, который не должен
стать скриптом, — в `.gitignore` конфигурации. Файл, удалённый руками,
уходит из Git в следующем `ws sync`.

## Выбор хоста

```sh
ws script list                    # имя, выбор здесь, linked, описание
ws script enable photos-import    # yes здесь, ws apply scripts
ws script disable photos-import   # no здесь (файл остаётся), ws apply scripts
ws script delete photos-import    # git rm, выбор всех хостов, ws apply scripts
ws script apply --select          # спросить и об отклонённых
```

`-n` (`--no-apply`) у add, enable, disable и delete только правит файлы;
применит следующий `ws apply`.

Default позиции — ask: `ws apply` и `ws setup` спрашивают. Другой default
или описание — запись в `scripts/catalog.toml`:

```toml
[[scripts]]
name = "photos-import"
default = "yes"          # ask, no или yes
description = "Import photos from the camera card"
```

`yes` ставит скрипт на каждом хосте без своего выбора, без вопроса;
`no` — не предлагает (`ws script apply --select` спросит).

## Проверка

`ws script check` (входит в `ws check`):

- имена и подкаталоги `scripts/`, форма `catalog.toml` (то, на чём
  сборка упадёт) — FAIL;
- записи `catalog.toml` и выбор хостов без файла — WARN;
- сборка против выбора этого хоста — WARN, `ws apply scripts`;
- у каждого скрипта сборки: ссылка ведёт в checkout, файл исполняемый
  (иначе FAIL), есть shebang, имя не прячет команду системы (WARN).

Ошибки сборки называют файл: недопустимое имя, подкаталог кроме `lib/`,
неверный `catalog.toml`, скрипт этого хоста по пути, который ставит ядро
или `home/`.

## Библиотеки

`scripts/lib/` — резерв: не команда и не в PATH. Скрипт находит его по
своему настоящему пути — ссылка ведёт в checkout, `lib/` рядом:

```sh
lib="$(dirname "$(readlink -f "$0")")/lib"
. "$lib/common.sh"
```

Выбор и доставка библиотек, зависимости скрипта от библиотеки —
открытый вопрос (ws help plan-v2, раздел 16, вопрос 6).

## СМ. ТАКЖЕ

ws help architecture-v2 (разделы 7 и 9.3), ws help plan-v2 (этап 10),
ws help setup.
