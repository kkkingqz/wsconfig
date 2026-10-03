title: ws-widgets
section: 1
date: 2026-10-03
source: Workstation
volume: User Commands

# WORKSTATION WIDGETS

Один Quickshell runtime, общий контейнер QML и один GNOME adapter.
`widgets/registry.nix` задаёт кнопки и содержимое. GNOME extension
`workstation-widgets@local` размещает прозрачное окно под кнопкой и только
после этого разрешает анимацию. В каждый момент открывается один виджет.

## Установка

Из checkout, содержащего реализацию:

```console
ws switch
ws apply extensions
# При первой установке: выйти из GNOME и войти снова.
ws-widgets check
```

Home Manager создаёт manifest/runtime JSON в
`~/.config/workstation/widgets/`, ссылку
`~/.config/quickshell/workstation-widgets` на QML в checkout и user service
`workstation-widgets.service`. Расширение устанавливается существующим
владельцем extensions. При работе в отдельном worktree сначала перенести
ветку в основной checkout: production-ссылка адресует checkout из facts.nix.
Основной checkout может оставаться на ветке `wsconfig`; merge в `main`
для установки не требуется.
Не активировать generation, ссылающуюся на основной checkout без этих файлов.

Runtime запускается вместе с graphical-session.target только в GNOME Wayland,
останавливается с сессией и ограничивает частоту рестартов. Quickshell и Mesa
из закреплённого nixpkgs находятся в отдельном closure; launcher задаёт EGL
vendor только для своего процесса. Qt получает scale из Wayland. Дополнительный
`QT_SCALE_FACTOR` не нужен.

## Команды

```console
ws-widgets start
ws-widgets stop
ws-widgets restart
ws-widgets status
ws-widgets check --json
ws check widgets --json
ws-widgets toggle example
ws-widgets show compact
ws-widgets hide compact
ws-widgets hide-all
journalctl --user -u workstation-widgets.service -b
```

status и check читают состояние. show/toggle/hide обращаются к уже запущенному
runtime и возвращают отказ для неизвестного, выключенного или сломанного ID.
Принятый show означает начало handshake, а не завершение анимации. Повторное
нажатие, Esc, кнопка «Закрыть», внешний клик, потеря фокуса, overview, смена
workspace и блокировка закрывают окно.

check проверяет доставку, активность сервиса, protocol/PID, доступность
компонентов, активность extension и adapter lease. Отсутствие активной
GUI-сессии или ещё не загруженный adapter отмечаются явно. Проверка не
подтверждает визуальное размещение; для него существует live checklist.

## Добавление виджета

Создать `widgets/quickshell/widgets/my-widget/Widget.qml`:

```qml
import QtQuick
import QtQuick.Controls
Item {
    required property QtObject context
    implicitHeight: 160
    Column {
        width: parent.width
        spacing: 16
        Label { text: "Мой виджет"; color: "white" }
        Button { text: "Закрыть"; onClicked: context.requestClose() }
    }
}
```

Добавить в `widgets/registry.nix`:

```nix
{
  id = "my-widget";
  label = "Мой виджет";
  iconName = "starred-symbolic";
  component = "widgets/my-widget/Widget.qml";
  width = 360;
  height = 240;
  panelPosition = "right";
  panelOrder = 2;
}
```

Применить `ws switch`: новый manifest меняет unit и перезапускает runtime,
а extension перечитывает кнопки после изменения runtime/manifest JSON.
При изменениях кода самого extension нужна доставка и новый вход в GNOME.
В GNOME 50 `ReloadExtension` через D-Bus не работает, а disable/enable
использует уже импортированный JS-модуль. Это следует из
[реализации Shell D-Bus](https://github.com/GNOME/gnome-shell/blob/50.1/js/ui/shellDBus.js)
и [менеджера расширений](https://github.com/GNOME/gnome-shell/blob/50.1/js/ui/extensionSystem.js).
Для нового содержимого extension менять не требуется.
Реестр проверяет уникальные ID, положительные целые размеры и безопасный
относительный путь существующего компонента. `enabled = false` убирает кнопку.

Widget — Item с обязательным context. Контекст содержит widgetId,
contentWidth/contentHeight, devicePixelRatio, phase и requestClose().
Компонент загружается при первом открытии и сохраняется после закрытия.
Ошибка компонента меняет значок кнопки на предупреждение и сообщает причину
через GNOME notification; другие виджеты продолжают работать.
Содержимое задаёт implicitHeight для прокрутки и не создаёт собственное окно.
Размеры width/height реестра задают всю панель в логических пикселях: padding
16 внутри, прозрачное поле 12 снаружи, radius 16. Surface = panel + 24;
content = panel − 32. Example: panel 420×580, surface 444×604, content 388×548.
Compact: panel 320×240, surface 344×264, content 288×208.
При scale 1.5 панели занимают 630×870 и 480×360 физических пикселей.

При маленькой рабочей области adapter уменьшает панель перед раскрытием.
ScrollView сохраняет доступ к содержимому. Размер поверхности не анимируется;
анимируются clipping и opacity за 180 мс. Прозрачные поля и ещё скрытая часть
имеют пустой input region. Если GNOME отключает анимации, переход мгновенный.

## Контракт и восстановление

Public IPC target `widgets`: toggle/show/hide(string) → bool, hideAll(),
status() → JSON, stateChanged(string). Target `widgetAdapter` содержит
handshake, geometry, animation setting и lease. CLI вызывает IPC с `--`
перед target: иначе Quickshell трактует имя show как служебную команду.

Фазы: closed → preparing → opening → open → closing → closed.
requestId отсекает устаревшие ответы. Подписка подключается до status;
revision упорядочивает события одного instance. Placement timeout 2 секунды.
Adapter продлевает lease каждые 2 секунды; потеря связи закрывает окна за
6 секунд. После рестарта runtime все окна закрыты, adapter принимает новый PID.

Отключение: `ws-widgets stop` и отключить extension через GNOME Extensions.
Постоянное удаление: убрать импорт widgets.nix и UUID из списка extensions,
применить ws switch. Исходники и чужие файлы расширений автоматически не
удаляются. Установщик удаляет только устаревшие файлы из своего owner manifest.
Перед возвратом основного checkout на ветку без framework остановить runtime,
переключить ветку и применить `ws switch`: QML-ссылка ведёт в живой checkout.

## Проверки разработки

```console
nix build .#widgets-runtime
gjs -m tests/widgets/run-tests.js
python3 -m unittest discover -s tests -q
python3 tests/widgets/check-qml.py ./result/bin/qs-widgets
nix build .#checks.x86_64-linux.widgets-manifest \
  .#checks.x86_64-linux.widgets-qml \
  .#checks.x86_64-linux.widgets-tests \
  .#checks.x86_64-linux.widgets-runtime --no-link
nix build .#checks.x86_64-linux.home-mbp16 \
  .#checks.x86_64-linux.home-wsvm --no-link
```

Wayland smoke без GNOME-кнопок:

```console
nix build .#checks.x86_64-linux.widgets-manifest -o /tmp/widgets-manifest
python3 tests/widgets/check-runtime.py --runtime ./result/bin/qs-widgets \
  --manifest /tmp/widgets-manifest --wayland
```

Тест использует временную конфигурацию, вручную подтверждает placement и
завершает только собственные процессы. Его результат не заменяет проверку
GNOME extension под кнопками. Фактическая матрица —
`tests/widgets/live-checklist.md`. Поддерживаемая Shell version сейчас 50;
Hyprland adapter не реализован.
