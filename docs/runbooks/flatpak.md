title: ws-flatpak
section: 1
date: 2026-10-14
source: Workstation
volume: User Commands

# FLATPAK — DESKTOP APPLICATIONS

GUI-приложения — Flatpak (user installation), host остаётся чистым. Как слой
строился: `ws help history-flatpak`.

## Источник

```text
flatpak/catalog.toml          каталог: remotes и все приложения, по порядку;
                              у приложения remote, default и общие overrides
nix/hosts/HOST/flatpak.toml   выбор машины (yes, no) и её свои overrides
flatpak/flatpak.nix           свои .desktop; собирает каталог и выбор машины
flatpak/desktop/*.desktop     полные .desktop, заменяющие штатные
libexec/wsflatpak             владелец: install, apply, check
```

`ws apply` собирает `~/.local/share/wsconfig/flatpak/` (`flatpak.json`:
remotes, приложения каталога и overrides этой машины; `desktop/`) и ставит
свои `.desktop` в `~/.local/share/applications` — только приложений, которые
на этой машине в состоянии yes: у не поставленного приложения ярлык ничего
бы не запускал. После `apply`, изменившего выбор, — `ws apply`.
`ws flatpak apply` добавляет remotes, ставит приложения и применяет
overrides; overrides управляемого приложения сначала сбрасываются, так что
значение, убранное из каталога или файла машины, исчезает.

Каталог — всё, что вообще можно поставить (`lib/flatpak_catalog.py`):

```toml
[remotes]
flathub = "https://dl.flathub.org/repo/flathub.flatpakrepo"

[[apps]]
# комментарии приложения — внутри его таблицы (уходят вместе с ним)
id = "com.anydesk.Anydesk"
remote = "flathub"
env = { GDK_SCALE = "2" }
talk = ["org.kde.StatusNotifierWatcher"]
```

Какие приложения на какой машине — её `nix/hosts/HOST/flatpak.toml`
(`lib/ws_catalog.py`, `ws help plan-v2`, этап 3); имя машины — `ws host`:

```toml
yes = ["org.gimp.GIMP", "com.mikrotik.WinBox"]   # стоят здесь
no = ["com.valvesoftware.Steam"]                 # отказались
```

- `yes` — стоит на этой машине; `apply` ставит без вопроса.
- `no` — на этой машине отказались; `apply` не трогает.
- Нет ни там, ни там — `default` приложения в каталоге: `ask` (по
  умолчанию; `apply` спрашивает), `no` (не предлагать) или `yes` (ставить на
  каждой машине без своего выбора).

Каждая машина пишет только свой файл: общей строки, в которой сталкивались
бы пометки двух машин, нет. `ws flatpak install|manage APP` ставит приложение
в `yes` этой машины (новое — ещё и в конец каталога, `default` ask),
`ws flatpak remove APP` — в `no` (запись каталога остаётся для других
машин), `unmanage` убирает запись из каталога вместе с её overrides и выбор
приложения из файлов всех машин. Комментарии и порядок файлов сохраняются
(tomlkit).

О не предложенных `apply` выводит список и спрашивает «Поставить все?
[Y/n]». На `n` — список с галочками: ↑/↓ выбирают строку, Space ставит и
снимает галочку, `a` переключает все, Enter ставит отмеченные, Esc/q
отменяет только вопрос: предложенные остаются ask (спросит в следующий
раз), остальное `apply` делает. Ответ пишется в `yes` / `no` этой машины,
`ws apply` ставит `.desktop` новых `yes`, `ws sync` публикует файл. Уже
установленное в состоянии ask попадает в `yes` молча.
`ws flatpak apply --select` спрашивает и о `no` (они без галочки). Без
терминала не предложенные не ставятся. `check`: `yes`, но не установлено —
FAIL; установлено, но `no` или ask — WARN; `no`/ask без установки — INFO.

Remotes: `flathub`, `flatpark` (Claude Desktop), `chatgpt`. Новый remote —
строка `NAME = "URL"` в `[remotes]` каталога (`ws flatpak remote-add NAME
URL` печатает её), затем `ws apply flatpak`; приложение из него
— `ws flatpak install --remote NAME APP`. Только user remotes: system
remotes `ws flatpak check` считает ошибкой, remote не из каталога —
предупреждением. Браузер — Firefox (`org.mozilla.firefox`): snap в системе
нет (`purge:snapd`, `ws help rebuild`, раздел 6.0).

## Установить и убрать

```console
ws flatpak help                     # общая справка и список команд
ws flatpak help install             # справка и примеры конкретной команды
ws flatpak install --help            # то же через --help
```

Fish дополняет команды, флаги, пользовательские remotes, App ID и полные refs
для установки (используется кеш remote). Для `unmanage` предлагаются приложения
каталога, включая уже удалённые; для `unfilesystem`, `unenv` и `untalk` —
объявленные значения выбранного приложения (каталог и файлы машин).

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
ws flatpak install APP                # ставит; yes этой машины (и в каталог)
ws flatpak install --unmanaged APP    # только ставит
ws flatpak manage APP [REMOTE]        # уже установленное — в yes (и в каталог)
ws flatpak unmanage APP               # убрать из каталога и выбора всех машин
ws flatpak remove APP                 # удаляет; no этой машины
ws flatpak apply [--select]           # ставит yes, спрашивает об ask
ws apply                            # собирает каталог и выбор
ws sync                              # публикует: коммит, pull --rebase, push
```

`ws apply` добавляет изменённые `catalog.toml` и выбор машин
`nix/hosts/*/*.toml` в сборку и ничего не коммитит: в конце он называет
неопубликованные файлы данных. Коммит и push делает только `ws sync`
(`ws help plan-v2`, 2.7).

## Разрешения и окружение

Постоянные — в каталоге, в записи приложения: `filesystems` (`[Context]
filesystems`), `env` (`Environment`), `talk` (`Session Bus Policy`, только
`talk`). Они действуют на каждой машине, где приложение стоит. Свои
значения машины — в `[overrides."APP"]` её `flatpak.toml`. Их добавляют и
убирают команды, как `install` — выбор; систему они не меняют:

```console
ws flatpak filesystem APP SPEC        # home:ro, xdg-download, /mnt/x:ro, ...
ws flatpak host APP                   # = filesystem APP host
ws flatpak env APP KEY VALUE          # или KEY=VALUE; новое значение заменяет
ws flatpak talk APP BUS
ws flatpak env --host APP KEY VALUE   # только эта машина
ws flatpak unfilesystem|unhost|unenv|untalk [--all] APP ...
ws apply                            # собирает (публикует ws sync)
ws flatpak apply                      # применяет
```

APP — ID, имя или часть имени установленного приложения, оно должно быть в
каталоге (`ws flatpak manage APP`). Значение — одно слово без `#`.

```toml
# nix/hosts/legiongo/flatpak.toml
[overrides."com.anydesk.Anydesk"]
env = { GDK_SCALE = "1" }                       # вместо GDK_SCALE=2 каталога
skip = ["talk org.kde.StatusNotifierWatcher"]   # значение каталога не здесь
```

- На машине у ключа одно значение: имя env, путь filesystem при любом
  режиме, имя шины. Значение машины заменяет значение каталога с тем же
  ключом; `skip` перечисляет значения каталога (`KIND KEY`), которые на этой
  машине не применяются.
- Без `--host` значение пишется в каталог и заменяет там значение того же
  ключа; своё значение и `skip` этой машины для ключа снимаются, чтобы оно
  действовало и здесь. С `--host` — в файл машины.
- `un…` убирает значение на этой машине: своё — из её файла, общее —
  через `skip` там же. С `--all` общее удаляется из каталога (и `skip`
  других машин для него).
- Две действующие на машине записи одного ключа `ws apply` отвергает.

```console
ws flatpak permissions APP
ws flatpak reset-permissions APP
```

Свои `.desktop`: Claude Desktop (Wayland, масштаб 1.5, URL handler), Steam
через `ws-gpu run` (`ws help windows`, GPU).

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
`filesystem=host`, приложения каталога в состоянии yes установлены из своих
remotes, overrides применены, свои `.desktop` приложений с `yes` на месте
(ярлык приложения без `yes` — WARN, нужен `ws apply`), каталог собран;
приложение или remote вне объявленных и выбор машины для приложения вне
каталога — предупреждение.
