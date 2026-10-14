title: ws-widgets
section: 1
date: 2026-10-13
source: Workstation
volume: User Commands

# WORKSTATION WIDGETS

Слой виджетов Quickshell с кнопками на панели GNOME. Код (runtime, QML,
GNOME adapter, `ws-widgets`, тесты и документация) — отдельный проект
wswidgets: <https://github.com/kkkingqz/wswidgets>, полное описание в его
`docs/ws-widgets.md`. Здесь — установка: какие виджеты на каком хосте и
какая версия wswidgets стоит. Всё берётся из версии, закреплённой в
`flake.lock`; локальный checkout (`~/Projects/wswidgets`) не нужен.

## Слой

Слой включается фактом хоста, как `vm`:

```toml
# hosts/<host>/host.toml
[layers]
widgets = true   # false — без виджетов
```

С `widgets = true` `ws apply` подключает модуль Home Manager из flake input
`wswidgets` (`widgets/widgets.nix`): Quickshell и Mesa в своём closure,
`workstation-widgets.service`, QML, manifest/runtime JSON, файлы расширения
`workstation-widgets@local` и команду `ws-widgets`.
`gnome/gnome-extensions.nix` включает расширение (источник `nix`: файлы даёт
модуль, `ws apply extensions` его не копирует). После первого включения слоя
нужен новый вход в GNOME.

## Какие виджеты на каком хосте

Каталог — виджеты `catalog.nix` закреплённой версии wswidgets. Выбор
хоста — `hosts/HOST/widgets.toml` (`lib/ws_catalog.py`, `ws help
plan-v2`, этап 3):

```toml
yes = ["example", "compact"]   # включены; порядок — порядок кнопок на панели
no = ["clock"]                 # отказались
```

Виджет, которого нет ни в `yes`, ни в `no`, — ask: его предлагает
`ws widgets apply`. Файл правит `ws widgets` (комментарии и порядок
сохраняются), публикует `ws sync`; править руками тоже можно. Каждый хост
пишет только свой файл. `setup.sh` на новом хосте (с `widgets = true`)
спрашивает о виджетах в состоянии ask вместе с Flatpak и Distrobox.

## wswidgets

```console
ws widgets list                 # виджеты закреплённой версии и их состояние здесь
ws widgets enable clock         # в yes этого хоста (в конец панели), затем ws apply
ws widgets disable compact      # в no этого хоста, затем ws apply
ws widgets apply                # спросить о виджетах в состоянии ask (чеклист)
ws widgets apply --select       # и об отклонённых (no)
ws widgets update               # новая версия с GitHub (см. ниже)
ws widgets version              # закреплённая ревизия
ws widgets enabled              # ID, включённые здесь, в порядке панели
ws widgets status               # ws-widgets status: запущенный runtime
ws widgets check [--json]       # = ws check widgets
```

`-n` (`--no-apply`) у enable, disable и update только правит файл или
`flake.lock`; применит следующий `ws apply`. Новый виджет каталога —
ask: его предлагает `ws widgets apply`, в том числе
из `ws apply` (шаг `widgets`).

## Версия wswidgets

wsconfig закреплён на коммите wswidgets в `flake.lock`, как nixpkgs.
`ws widgets update`: `nix flake update wswidgets`, ссылка на сравнение
коммитов на GitHub, новые и удалённые виджеты, `ws apply`; `flake.lock`
публикует `ws sync`. Если в новой версии нет виджета из `yes` какого-либо хоста
(`hosts/*/widgets.toml`), update отказывается и не трогает `flake.lock`: сначала
`ws widgets disable`. Неудачный `ws apply` возвращает прежний `flake.lock`.
`ws update nix` тоже обновляет wswidgets вместе с остальными inputs.

Проверить незакоммиченные изменения из checkout проекта, не трогая
`flake.lock`: `ws apply --override-input wswidgets path:$HOME/Projects/wswidgets`;
следующий обычный `ws apply` возвращает закреплённую версию.

## Проверка

`ws check widgets` (входит в `ws check`): на хосте с `widgets = true` —
диагностика `ws-widgets check --tsv` (доставка, сервис, IPC, adapter) и
совпадение manifest с `ws widgets enabled`; на остальных — только INFO.

## Отключение

Виджет: `ws widgets disable ID`. Весь слой: `widgets = false` в `host.toml` и
`ws apply` — Home Manager убирает файлы слоя и сервис, расширение исчезает
из `enabled-extensions`; выбор в `widgets.toml` остаётся.
