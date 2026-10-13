title: ws-widgets
section: 1
date: 2026-10-13
source: Workstation
volume: User Commands

# WORKSTATION WIDGETS

Слой виджетов Quickshell с кнопками на панели GNOME. Код (runtime, QML,
GNOME adapter, `ws-widgets`, тесты и документация) — отдельный проект
wswidgets: `~/Projects/wswidgets`, <https://github.com/kkkingqz/wswidgets>,
полное описание в его `docs/ws-widgets.md`. Здесь — только установка.

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

## Какие виджеты включены

`widgets/widgets.txt`: ID из `catalog.nix` проекта по одному в строке,
`#` — комментарий, порядок строк — порядок кнопок. Неизвестный ID
останавливает `ws switch` со списком доступных.

```console
$EDITOR ~/wsconfig/widgets/widgets.txt
ws switch
ws check widgets
```

## Версия wswidgets

wsconfig закреплён на коммите wswidgets в `flake.lock`, как nixpkgs.

```console
nix flake update wswidgets --flake ~/wsconfig   # взять новые коммиты из GitHub
ws switch                                       # применить; flake.lock закоммитить
```

`ws update nix` обновляет его вместе с остальными inputs. Проверить
незакоммиченные изменения из checkout, не трогая `flake.lock`:

```console
ws switch --override-input wswidgets path:$HOME/Projects/wswidgets
```

Следующий обычный `ws switch` возвращает закреплённую версию.

## Проверка

`ws check widgets` (входит в `ws check`): на хосте с `widgets = "yes"` —
диагностика `ws-widgets check --tsv` (доставка, сервис, IPC, adapter) и
совпадение manifest с `widgets/widgets.txt`; на остальных — только INFO.

## Отключение

`widgets = "no"` в `facts.nix` и `ws switch`: Home Manager убирает файлы
слоя и сервис, расширение исчезает из `enabled-extensions`.
