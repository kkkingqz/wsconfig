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

`ws switch` собирает `~/.local/share/workstation/flatpak/` (`remotes.conf`,
`apps.conf`, `overrides/`, `desktop/`) и ставит свои `.desktop` в
`~/.local/share/applications`. `wsflatpak apply` добавляет remotes, ставит
приложения и применяет overrides; overrides управляемого приложения сначала
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

`wsflatpak install|manage APP` ставит своей машине `yes` (новая строка
получает `all=ask`), `wsflatpak remove APP` удаляет строку, если других
машин в ней нет, иначе ставит своей `no`; `unmanage` удаляет строку целиком.

О не предложенных `apply` выводит список и спрашивает «Поставить все?
[Y/n]». На `n` — список с галочками: ↑/↓ выбирают строку, Space ставит и
снимает галочку, `a` переключает все, Enter ставит отмеченные, Esc/q
отменяет только вопрос: предложенные остаются `ask` (спросит в следующий
раз), остальное `apply` делает. Ответ пишется в `apps.txt` (`HOST=yes` /
`HOST=no`), `ws switch` коммитит его. Уже установленное без пометки получает `yes` молча.
`wsflatpak apply --select` спрашивает и о `HOST=no` (они без галочки). Без
терминала не предложенные не ставятся. `check`: `yes`, но не установлено —
FAIL; установлено, но `no` или без пометки — WARN; `no`/`ask` без установки
— INFO.

Remotes: `flathub`, `flatpark` (Claude Desktop). Новый remote — строка
`NAME = "URL.flatpakrepo";` в `remotes` файла `flatpak/flatpak.nix`
(`wsflatpak remote-add NAME URL` печатает её), затем `ws switch &&
wsflatpak apply`; приложение из него — `wsflatpak install --remote NAME
APP`. Только user remotes: system remotes `wsflatpak check` считает ошибкой,
remote не из `flatpak.nix` — предупреждением. Браузер — Firefox
(`org.mozilla.firefox`): snap в системе нет (`purge:snapd`, `helpws rebuild`, раздел 6.0).

## Установить и убрать

```console
wsflatpak help                     # общая справка и список команд
wsflatpak help install             # справка и примеры конкретной команды
wsflatpak install --help            # то же через --help
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
`wsflatpak cleanup` может удалить его, когда он больше не нужен приложениям.

```console
wsflatpak install APP                # ставит, в apps.txt: HOST=yes
wsflatpak install --unmanaged APP    # только ставит
wsflatpak manage APP [REMOTE]        # уже установленное — HOST=yes
wsflatpak unmanage APP               # убрать строку из apps.txt
wsflatpak remove APP                 # удаляет; строку или HOST=no
wsflatpak apply [--select]           # ставит HOST=yes, спрашивает об ask
ws switch                            # собирает и коммитит apps.txt
```

`ws switch` добавляет изменённые `apps.txt`, `overrides.txt` и
`distrobox/hosts.txt` в сборку и после успешного switch коммитит их (без
push).

## Разрешения и окружение

Постоянные — строки `flatpak/overrides.txt`: `APP filesystem SPEC`
(`Context.filesystems`), `APP env KEY=VALUE` (`Environment`), `APP talk BUS`
(`Session Bus Policy`, только `talk`). Их добавляют и убирают команды, как
`install` — `apps.txt`; систему они не меняют:

```console
wsflatpak filesystem APP SPEC        # home:ro, xdg-download, /mnt/x:ro, ...
wsflatpak host APP                   # = filesystem APP host
wsflatpak env APP KEY VALUE          # или KEY=VALUE; новое значение заменяет
wsflatpak talk APP BUS
wsflatpak unfilesystem|unhost|unenv|untalk APP ...
ws switch                            # собирает и коммитит overrides.txt
wsflatpak apply                      # применяет
```

APP — ID, имя или часть имени установленного приложения. Значение — одно
слово без `#`.

```console
wsflatpak permissions APP
wsflatpak reset-permissions APP
```

Свои `.desktop`: Claude Desktop (Wayland, масштаб 1.5, URL handler), Steam
через `ws-gpu run` (`helpws windows`, GPU).

## Прочее

```console
wsflatpak list | search TERM | info APP | run APP [ARG...]
wsflatpak update                     # flatpak update --user (ws update flatpak)
wsflatpak cleanup                    # unused runtimes
wsflatpak status
wsflatpak test                       # portals, PipeWire + check
```

## Проверка

```console
wsflatpak check [--json]
ws check
```

`check`: remotes (системных нет), системная установка пуста, нет глобального
`filesystem=host`, приложения `apps.txt` установлены из своих remotes,
overrides применены, свои `.desktop` на месте; приложение или remote вне
объявленных — предупреждение.
