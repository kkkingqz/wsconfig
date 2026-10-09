title: ws-widgets
section: 1
date: 2026-10-09
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
`~/.local/share/workstation/widgets/`, ссылку
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

Обычное закрытие соединения (ответ CLI, перезагрузка расширения) не пишется в журнал:
сервис запускается с `--log-rules quickshell.io.socket.warning=false`. Обрыв adapter
виден в состоянии (`adapter.connected`, `lastError`) и в `ws check widgets`.

status и check читают состояние. show/toggle/hide обращаются к уже запущенному
runtime и возвращают отказ без подключённого adapter, а также для неизвестного,
выключенного или сломанного ID.
Принятый show означает начало handshake, а не завершение анимации. Повторное
нажатие, Esc, кнопка «Закрыть», внешний клик, потеря фокуса, overview, смена
workspace и блокировка закрывают окно.

check проверяет доставку, активность сервиса, protocol/PID, доступность
компонентов, активность extension и соединение adapter. Отсутствие активной
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
        Label { text: "Мой виджет"; color: context.foreground }
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
  unloadOnClose = false;
  width = 360;
  height = 240;
  panelPosition = "right";
  panelOrder = 2;
}
```

Применить `ws switch`: новый manifest меняет unit и перезапускает runtime,
а extension перечитывает кнопки после изменения runtime/manifest JSON.
При изменениях кода самого extension нужна доставка и новый вход в GNOME.
Runtime не следит за файлами QML (`settings.watchFiles: false`): конфигурация —
symlink в репозиторий, и смена ветки перезагружала бы его на лету без сокета.
После правки QML перезапустить его явно: `ws-widgets restart`.
В GNOME 50 `ReloadExtension` через D-Bus не работает, а disable/enable
использует уже импортированный JS-модуль. Это следует из
[реализации Shell D-Bus](https://github.com/GNOME/gnome-shell/blob/50.1/js/ui/shellDBus.js)
и [менеджера расширений](https://github.com/GNOME/gnome-shell/blob/50.1/js/ui/extensionSystem.js).
Для нового содержимого extension менять не требуется.

При автоматизированном disable/enable нужно дождаться состояния `INACTIVE`
в `gnome-extensions info workstation-widgets@local` перед enable. EOF сокета
означает закрытие adapter, но менеджер GNOME ещё может завершать выключение
и повторное включение других расширений. Немедленный enable в этот момент
может оставить `Enabled: Yes`, `State: INACTIVE`. Для восстановления отключить
расширение, дождаться `INACTIVE` и включить снова.
Реестр проверяет уникальные ID, положительные целые размеры и безопасный
относительный путь существующего компонента. `enabled = false` убирает кнопку.

Widget — Item с обязательным context. Контекст содержит widgetId,
contentWidth/contentHeight, devicePixelRatio, phase, background, foreground,
mutedForeground и requestClose(). Фон контейнера и цвета текста берутся из
фактического оформления меню GNOME, включая светлую/тёмную и пользовательскую
Shell theme. Adapter передаёт палитру при подключении и изменении стиля;
открытые окна обновляются без повторного открытия и без периодического опроса.
Содержимое использует context.foreground для основного текста и
context.mutedForeground для второстепенного.
Компонент загружается при первом открытии и сохраняется после закрытия.
`unloadOnClose = true` в registry выгружает содержимое после закрытия; следующее
открытие загрузит его заново. По умолчанию false, чтобы повторное открытие было быстрым.
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
анимируются clipping и opacity за 300 мс с мягким разгоном и замедлением.
Повторный клик закрывает панель; смена направления продолжает переход с
текущего раскрытия. Прозрачные поля и ещё скрытая часть
имеют пустой input region. Если GNOME отключает анимации, переход мгновенный.

GNOME adapter определяет внешние клики через reactive picking Mutter: скрытая
область, прозрачные поля и округлённые углы пропускают клик и закрывают виджет.
Внешний клик во время preparing отменяет запрос размещения.
Adapter отправляет `placed` только после проверки геометрии и фактического
получения фокуса Mutter. До этого окно остаётся в preparing, поэтому потеря
фокуса старого окна при переключении не закрывает новое. Если фокус не получен,
срабатывает существующий таймаут размещения. Время клика используется только
для соответствующего открытия; закрытие и отмена очищают его.
До подключения adapter поверхность не отображается. Adapter через InjectionManager
подавляет `_shouldAnimateActor` только для проверенного PID runtime и
зарегистрированного ID окна; это исключает наложение анимации Shell на QML.
При отключении adapter восстанавливает метод. Этот внутренний API проверен
по исходникам Shell 50.1; его работу в GUI проверяет live checklist.

## Контракт и восстановление

Runtime слушает `$XDG_RUNTIME_DIR/workstation-widgets/control.sock`.
Systemd создаёт каталог с правами 0700, а UMask=0077 сервиса создаёт сокет
с правами 0700. Сокет доступен только текущему UID: клиенты отклоняют каталог
и сокет с любыми битами group/other. CLI и Gio дополнительно проверяют права
и UID сервера (SO_PEERCRED/Gio credentials); PID snapshot должен совпадать с
PID peer. Quickshell сам пересоздаёт сокет, оставшийся после падения.

Протокол — JSON-строки с protocolVersion 2. Первое сообщение: hello с ролью
adapter или cli. Единственный adapter получает snapshot при подключении и
после изменения состояния. Новый adapter вытесняет старый. Команды adapter:
toggle, hideAll, placed, placementFailed, setGeometry, setAnimations, setTheme.
CLI отправляет одну команду status/show/hide/toggle/hideAll и получает ответ;
Quickshell процессы для команд и подписки больше не запускаются.
Ответы связаны с запросами через seq; requestId относится к размещению окна.

Фазы: closed → preparing → opening → open → closing → closed.
requestId отсекает устаревшие ответы, revision упорядочивает события instance.
На размещение даётся 2 секунды: одноразовый таймер ближайшего дедлайна.
В штатном простое нет периодических таймеров ни для IPC, ни для модели.
Обрыв adapter немедленно закрывает окна и записывает lastError. Повторное
подключение очищает эту ошибку. Без adapter show/toggle отклоняются.
После рестарта runtime все окна закрыты; adapter подключается с паузами
250/500/1000/2000 мс, проверяет новый PID. Отключение extension закрывает
соединение и отменяет чтение, запись, запросы и переподключение.

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
