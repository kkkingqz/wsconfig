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

```nix
# nix/hosts/<host>/facts.nix
widgets = "yes";   # "no" — без виджетов
```

С `widgets = "yes"` `ws switch` подключает модуль Home Manager из flake input
`wswidgets` (`widgets/widgets.nix`): Quickshell и Mesa в своём closure,
`workstation-widgets.service`, QML, manifest/runtime JSON, файлы расширения
`workstation-widgets@local` и команду `ws-widgets`.
`gnome/gnome-extensions.nix` включает расширение (источник `nix`: файлы даёт
модуль, `ws apply extensions` его не копирует). После первого включения слоя
нужен новый вход в GNOME.

## Какие виджеты на каком хосте

`widgets/widgets.txt` — как `flatpak/apps.txt` и `distrobox/hosts.txt`
(`helpws flatpak`, `helpws distrobox`): `ID HOST=STATE... all=STATE`, STATE
yes (включён), no (отказались), ask (не предложен; `wswidgets apply`
спрашивает). `all=` действует на хосте без своей пометки, строка без
пометок — ask. Порядок строк — порядок кнопок. ID — из `catalog.nix`
закреплённой версии wswidgets.

```text
example mbp16=yes all=ask
compact mbp16=yes legiongo=no all=ask
```

Файл правит `wswidgets`, публикует `ws sync`; править руками тоже
можно. `setup.sh` на новом хосте (с `widgets = "yes"`) спрашивает о
строках без пометки этого хоста вместе с Flatpak и Distrobox.

## wswidgets

```console
wswidgets list                 # виджеты закреплённой версии и их состояние здесь
wswidgets enable clock         # host=yes в widgets.txt, затем ws switch
wswidgets disable compact      # убрать строку или host=no, затем ws switch
wswidgets apply                # спросить о виджетах в состоянии ask (чеклист)
wswidgets apply --select       # и об отклонённых (no)
wswidgets update               # новая версия с GitHub (см. ниже)
wswidgets version              # закреплённая ревизия
wswidgets enabled              # ID, включённые здесь, в порядке панели
wswidgets status               # ws-widgets status: запущенный runtime
wswidgets check [--json]       # = ws check widgets
```

`-n` (`--no-switch`) у enable, disable и update только правит файл или
`flake.lock`; применит следующий `ws switch`. Новый виджет каталога без
строки в `widgets.txt` — ask: его предлагает `wswidgets apply`, в том числе
из `ws apply` (шаг `widgets`).

## Версия wswidgets

wsconfig закреплён на коммите wswidgets в `flake.lock`, как nixpkgs.
`wswidgets update`: `nix flake update wswidgets`, ссылка на сравнение
коммитов на GitHub, новые и удалённые виджеты, `ws switch` и коммит
`flake.lock`. Если в новой версии нет виджета, включённого в `widgets.txt`
на каком-либо хосте, update отказывается и не трогает `flake.lock`: сначала
`wswidgets disable`. Неудачный `ws switch` возвращает прежний `flake.lock`.
`ws update nix` тоже обновляет wswidgets вместе с остальными inputs.

Проверить незакоммиченные изменения из checkout проекта, не трогая
`flake.lock`: `ws switch --override-input wswidgets path:$HOME/Projects/wswidgets`;
следующий обычный `ws switch` возвращает закреплённую версию.

## Проверка

`ws check widgets` (входит в `ws check`): на хосте с `widgets = "yes"` —
диагностика `ws-widgets check --tsv` (доставка, сервис, IPC, adapter) и
совпадение manifest с `wswidgets enabled`; на остальных — только INFO.

## Отключение

Виджет: `wswidgets disable ID`. Весь слой: `widgets = "no"` в `facts.nix` и
`ws switch` — Home Manager убирает файлы слоя и сервис, расширение исчезает
из `enabled-extensions`; пометки в `widgets.txt` остаются.
