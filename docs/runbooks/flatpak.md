title: ws-flatpak
section: 1
date: 2026-10-03
source: Workstation
volume: User Commands

# FLATPAK — DESKTOP APPLICATIONS

GUI-приложения — Flatpak (user installation), host остаётся чистым. Как слой
строился: `helpws history-flatpak`.

## Источник

```text
flatpak/apps.txt        управляемые приложения: REMOTE APP, по строке
flatpak/overrides.txt   overrides приложений: APP KIND VALUE, по строке
flatpak/flatpak.nix     remotes, свои .desktop; читает оба списка
flatpak/desktop/*.desktop  полные .desktop, заменяющие штатные
bin/wsflatpak           владелец: install, apply, check
```

`ws switch` собирает `~/.local/share/workstation/flatpak/` (`flatpak.json`:
remotes, приложения и overrides этого хоста; `desktop/`) и ставит свои `.desktop` в
`~/.local/share/applications` — только приложений с пометкой `HOST=yes` для
этой машины (без пометки — по `all=`): у не поставленного приложения ярлык
ничего бы не запускал. После `apply`, изменившего пометки, — `ws switch`.
`ws flatpak apply` добавляет remotes, ставит приложения и применяет overrides; overrides управляемого приложения сначала
сбрасываются, так что строка, убранная из `overrides.txt`, исчезает.

Какие приложения на какой машине, записано в самом `apps.txt` — пометками
после `REMOTE APP` (`lib/ws_marks.py`); имя машины — `ws host`:

```text
flathub org.gimp.GIMP mbp16=yes wsvm=no all=ask
```

- `HOST=yes` — стоит на этой машине; `apply` ставит без вопроса.
- `HOST=no` — на этой машине отказались; `apply` не трогает.
- `HOST=ask` — не предложено; `apply` спрашивает.
- `all=…` действует только для машины без своей пометки (`all=yes` —
  ставить везде, где не сказано иначе). Нет ни своей пометки, ни `all` — ask.

`ws flatpak install|manage APP` ставит своей машине `yes` (новая строка
получает `all=ask`), `ws flatpak remove APP` удаляет строку, если других
машин в ней нет, иначе ставит своей `no`; `unmanage` удаляет строку целиком.

О не предложенных `apply` выводит список и спрашивает «Поставить все?
[Y/n]». На `n` — список с галочками: ↑/↓ выбирают строку, Space ставит и
снимает галочку, `a` переключает все, Enter ставит отмеченные, Esc/q
отменяет только вопрос: предложенные остаются `ask` (спросит в следующий
раз), остальное `apply` делает. Ответ пишется в `apps.txt` (`HOST=yes` /
`HOST=no`), `ws switch` ставит `.desktop` новых `yes`, `ws sync` публикует файл. Уже
установленное без пометки получает `yes` молча.
`ws flatpak apply --select` спрашивает и о `HOST=no` (они без галочки). Без
терминала не предложенные не ставятся. `check`: `yes`, но не установлено —
FAIL; установлено, но `no` или без пометки — WARN; `no`/`ask` без установки
— INFO.

Remotes: `flathub`, `flatpark` (Claude Desktop). Новый remote — строка
`NAME = "URL.flatpakrepo";` в `remotes` файла `flatpak/flatpak.nix`
(`ws flatpak remote-add NAME URL` печатает её), затем `ws switch &&
ws flatpak apply`; приложение из него — `ws flatpak install --remote NAME
APP`. Только user remotes: system remotes `ws flatpak check` считает ошибкой,
remote не из `flatpak.nix` — предупреждением. Браузер — Firefox
(`org.mozilla.firefox`): snap в системе нет (`purge:snapd`, `helpws rebuild`, раздел 6.0).

## Установить и убрать

```console
ws flatpak help                     # общая справка и список команд
ws flatpak help install             # справка и примеры конкретной команды
ws flatpak install --help            # то же через --help
```

Fish дополняет команды, флаги, пользовательские remotes, App ID и полные refs
для установки (используется кеш remote). Для `unmanage` предлагаются приложения
из `apps.txt`, включая уже удалённые; для `unfilesystem`, `unenv` и `untalk` —
объявленные значения выбранного приложения из `overrides.txt`.

`install` и `apply` устанавливают приложение и его требуемый runtime в
пользовательскую установку (`~/.local/share/flatpak/` при стандартном
`XDG_DATA_HOME`). Если runtime доступен только системно, он дополнительно
устанавливается для пользователя. Для него используются пользовательские
remotes: сначала remote приложения, затем остальные по имени, пока не
найдётся точный runtime. Remote приложения может не содержать его. Ошибка
установки runtime завершает команду с ошибкой. Права доступа к файлам
задаются отдельно через overrides.

При установке нескольких приложений проверяется runtime каждого из них.
Проверка использует полный ref приложения с архитектурой и веткой;
`apply` обрабатывает все установленные ветки управляемого приложения.
Дополнительно установленный runtime не закрепляется автоматически, поэтому
`ws flatpak cleanup` может удалить его, когда он больше не нужен приложениям.

```console
ws flatpak install APP                # ставит, в apps.txt: HOST=yes
ws flatpak install --unmanaged APP    # только ставит
ws flatpak manage APP [REMOTE]        # уже установленное — HOST=yes
ws flatpak unmanage APP               # убрать строку из apps.txt
ws flatpak remove APP                 # удаляет; строку или HOST=no
ws flatpak apply [--select]           # ставит HOST=yes, спрашивает об ask
ws switch                            # собирает apps.txt
ws sync                              # публикует: коммит, pull --rebase, push
```

`ws switch` добавляет изменённые `apps.txt`, `overrides.txt` и выбор
хостов `nix/hosts/*/*.toml` в сборку и ничего не коммитит: в конце он называет
неопубликованные файлы данных. Коммит и push делает только `ws sync`
(`helpws plan-v2`, 2.7).

## Разрешения и окружение

Постоянные — строки `flatpak/overrides.txt`: `APP filesystem SPEC`
(`Context.filesystems`), `APP env KEY=VALUE` (`Environment`), `APP talk BUS`
(`Session Bus Policy`, только `talk`). Их добавляют и убирают команды, как
`install` — `apps.txt`; систему они не меняют:

```console
ws flatpak filesystem APP SPEC        # home:ro, xdg-download, /mnt/x:ro, ...
ws flatpak host APP                   # = filesystem APP host
ws flatpak env APP KEY VALUE          # или KEY=VALUE; новое значение заменяет
ws flatpak talk APP BUS
ws flatpak unfilesystem|unhost|unenv|untalk APP ...
ws switch                            # собирает overrides.txt (публикует ws sync)
ws flatpak apply                      # применяет
```

APP — ID, имя или часть имени установленного приложения. Значение — одно
слово без `#`.

У каждой строки свои пометки машин после `APP KIND VALUE`, только `yes` и
`no`: строка действует там, где `yes`; `all=` — для машины без своей
пометки; строка без пометок действует везде. `ws switch` собирает overrides
только из строк этой машины, `apply` и `check` работают с ними.

```text
com.anydesk.Anydesk env GDK_SCALE=2 mbp16=yes legiongo=no all=yes
com.anydesk.Anydesk env GDK_SCALE=1 legiongo=yes all=no
```

- `ws flatpak filesystem|host|env|talk` ставит своей машине `yes`; новая
  строка — `HOST=yes all=yes`.
- Другое значение того же ключа (имя env, путь filesystem при любом режиме)
  меняет строку на месте, если других машин в ней нет. Иначе та строка
  получает `HOST=no`, а новое значение — свою строку `HOST=yes all=no`.
- `un…` удаляет строку, если других машин в ней нет, иначе ставит `HOST=no`.
- На одной машине у ключа одно значение: две действующие строки одного ключа
  `ws switch` отвергает.

```console
ws flatpak permissions APP
ws flatpak reset-permissions APP
```

Свои `.desktop`: Claude Desktop (Wayland, масштаб 1.5, URL handler), Steam
через `ws-gpu run` (`helpws windows`, GPU).

## Прочее

```console
ws flatpak list | search TERM | info APP | run APP [ARG...]
ws flatpak update                     # flatpak update --user (ws update flatpak)
ws flatpak cleanup                    # unused runtimes
ws flatpak status
ws flatpak test                       # portals, PipeWire + check
```

Портал документов (`flatpak.nix`): после перелогина старый `fusermount3`
(setuid root, systemd его не убивает) с `auto_unmount` снимал
`/run/user/UID/doc` уже за новым порталом, и любой flatpak падал с
`bwrap: Can't find source path .../doc/by-app/APP`. Drop-in
`xdg-document-portal.service.d/ws-wait-fusermount.conf` ждёт его выхода
(до 10 с) перед стартом. Вручную: `systemctl --user restart xdg-document-portal`.

## Проверка

```console
ws flatpak check [--json]
ws check
```

`check`: remotes (системных нет), системная установка пуста, нет глобального
`filesystem=host`, приложения `apps.txt` установлены из своих remotes,
overrides применены, свои `.desktop` приложений с `yes` на месте (ярлык
приложения без `yes` — WARN, нужен `ws switch`); приложение или remote вне
объявленных — предупреждение.
