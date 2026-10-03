# Widget Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать переиспользуемый framework Quickshell с двумя кнопками GNOME и анимированными окнами, корректно работающими при системном масштабе 150%.

**Architecture:** Один Quickshell runtime читает реестр и управляет общим lifecycle окон. Одно GNOME extension создаёт кнопки, размещает окна и управляет фокусом. Каждый виджет добавляется Item-компонентом и записью Nix; UI и анимации не зависят от desktop adapter.

**Tech Stack:** Nix/Home Manager, Quickshell, Qt Quick/QML, JavaScript ES modules, GJS/Gio/Meta/St, systemd user services, Python unittest для файловой интеграции.

**Spec:** [Согласованный проект](../specs/2026-10-03-widget-framework-design.md).

## Global Constraints

- Target GNOME Shell 50, Wayland; реальная машина — GNOME 50.1, eDP-1, 3072×1920, scale 1.5.
- Конфигурация Quickshell — `workstation-widgets`; public IPC target — `widgets`; schemaVersion и protocolVersion — 1.
- UUID — `workstation-widgets@local`; namespace window title — `workstation-widgets:<id>`, сопоставление дополнительно по PID runtime.
- ID — `[a-z][a-z0-9-]*`; width/height — положительные целые логические пиксели; panelPosition — left/center/right, default right.
- В каждый момент раскрывается один виджет; состояние принадлежит Controller; после рестарта все закрыты.
- Фазы — closed/preparing/opening/open/closing; placement timeout 2000 мс, lease renew 2000 мс, expiry 6000 мс, анимация полного раскрытия 180 мс, зазор под кнопкой 8 логических пикселей.
- Qt выполняет системное масштабирование. Не задавать глобальные QT_SCALE_FACTOR/QT_SCREEN_SCALE_FACTORS, не менять session environment, GNOME, portals, host Qt/GTK или graphics stack.
- Новые runtime/QML файлы, новые JS-модули extension и owner-check должны доставляться существующими владельцами wsconfig.
- Не менять имеющиеся пользовательские правки docs/architecture/workstation.md, docs/plans/roadmap.md, docs/plans/hyprland.md и system/.
- Hyprland adapter, системные сервисы виджетов, plugin marketplace и отдельный runtime на каждый виджет не входят в реализацию.

## Review Focus

1. Разрыв подписки во время открытия: lease закрывает панель, reconnect получает snapshot без восстановления устаревшего открытия. Тесты задач 3 и 5.
2. Клик по своей кнопке одновременно с потерей фокуса: одно toggle, без повторного открытия. Тест задачи 6.
3. QML-компонент с ошибкой: доступность других ID сохраняется, кнопка ошибочного виджета сообщает отказ. Тест задачи 4.
4. Маленький монитор и дробный scale: clamp/scroll сохраняют доступ к содержимому и кнопке закрытия. Тесты задач 5 и 8.
5. Новая поставка многомодульного extension: удаляется устаревший owner-файл, сохраняется сторонний файл. Тест задачи 2.

## Структура файлов и общие контракты

Работа ведётся в изолированном worktree через using-git-worktrees. Контекст
main не очищать и не переносить пользовательские изменения в коммиты задачи.
Документы проекта и плана прочитать перед реализацией. Применение конфигурации
к активной машине — после прохода проверок сборки; Shell не перезапускать и
сессию пользователя не завершать автоматически.

Основное дерево определено spec. Дополнительные небольшие модули:

```text
widgets/runtime/default.nix                 Quickshell closure и launcher
widgets/manifest.nix                        валидация реестра и JSON
widgets/quickshell/framework/model.mjs      чистый reducer lifecycle
widgets/quickshell/framework/manifest.mjs   runtime validation manifest
widgets/quickshell/framework/Style.qml      общие размеры/анимация
gnome/extensions/workstation-widgets@local/lib/geometry.mjs
gnome/extensions/workstation-widgets@local/lib/protocol.mjs
gnome/extensions/workstation-widgets@local/lib/dismissal.mjs
lib/gnome_extension_files.py                owner manifest и безопасная доставка
bin/ws-widgets-check                       check.bash формат проверок
tests/widgets/run-tests.js                 GJS runner чистых ES modules
tests/widgets/qml/shell.qml                headless тесты QML composition
tests/widgets/probe/shell.qml              окно для проверки runtime на GNOME
tests/test_gnome_extension_files.py        доставка файлов extension
tests/test_ws_widgets.py                   CLI/service/check integration
```

Pure JS экспортируется из .mjs: его импортируют QML и GJS tests. Модули с
Shell imports тестируются через вынесенные чистые policy/geometry функции
и live checks; не эмулировать всю GNOME Shell в unit tests.
GJS runner предоставляет assert(condition) и именованный запуск manifest/model/
geometry/protocol/dismissal; без аргумента запускает все зарегистрированные
на текущем этапе suites. Fixtures создаются в каждом suite и не зависят
от production registry. Новые Nix/QML файлы добавляются в Git перед flake
evaluation, отдельными путями, без добавления пользовательских правок.

Manifest: `{schemaVersion: 1, widgets: [{id, enabled, label, iconName,
component, width, height, panelPosition, panelOrder}]}`. Component — безопасный
относительный путь под QML root; запрещены абсолютные пути, `..`, URL и
выход через symlink за root. Отключённые записи валидируются, но кнопок не создают.

Runtime config: JSON `{schemaVersion: 1, qsPath, configName:
"workstation-widgets", manifestPath, adapter: "gnome"}` по пути
`~/.config/workstation/widgets/runtime.json`; manifest расположен рядом.
QML entrypoint — `~/.config/quickshell/workstation-widgets/shell.qml`.
Extension читает эти же файлы, абсолютный qsPath доставляет Nix.

Snapshot: `{protocolVersion: 1, instanceId, pid, revision, selectedId,
widgets: {id: {phase, desiredOpen, requestId, available}}, lastError}`.
selectedId — строка ID или null; requestId — возрастающее целое; revision
возрастает при изменении snapshot. Каждая смена целевой видимости обновляет
requestId, чтобы отсекать старые placement/animation callbacks.
Для проверки связи snapshot также содержит `adapter: {ready, leaseExpiresAt}`;
leaseExpiresAt — отметка по монотонным часам runtime, сравнение выполняет
runtime. Checker использует ready и health response, не сравнивает часы
разных процессов.

Публичный IPC: toggle/show/hide(id: string): bool, hideAll(): void,
status(): string, stateChanged(snapshot: string). bool означает принятие
запроса, не завершение раскрытия.
Внутренний target `widgetAdapter`: adapterReady(instanceId: string): bool,
renewAdapterLease(instanceId: string): bool,
placed(id: string, requestId: int): bool,
placementFailed(id: string, requestId: int, reason: string): bool,
setGeometry(id: string, requestId: int, panelWidth: int, panelHeight: int): bool,
setAnimationsEnabled(enabled: bool): void. Внутренние команды явно типизировать;
дополнительная geometry команда нужна для ограничения размера до раскрытия.

## Task 1: Совместимый runtime и техническая проверка окна

**Files:** Create `widgets/runtime/default.nix`, `tests/widgets/probe/shell.qml`, `tests/widgets/probe/check.py`; Modify `flake.nix` (packages/checks для widgets-runtime).

**Interfaces:** Consumes существующий pkgs из закреплённого flake.lock. Produces package `widgets-runtime` с `bin/qs-widgets`, передающим аргументы qs без shell interpolation, и probe IPC target `probe`: status(): string, show(): void, hide(): void.

- [ ] Добавить probe с FloatingWindow, прозрачным цветом до первого показа, panel 420×580 и фиксированными minimumSize/maximumSize. status возвращает actual width/height, DPR и PID; компонент стартует скрытым. check.py проверяет формат результата, размеры и наличие qs ipc listen.
- [ ] Запустить `python3 tests/widgets/probe/check.py --runtime ./result/bin/qs-widgets --headless`; ожидается отказ из-за отсутствующего runtime. Отсутствие самого тестового runner не считать доказательством red.
- [ ] Реализовать closure из pkgs.quickshell и process-local launcher с QT_QPA_PLATFORM=wayland для normal run; headless override разрешён только явно. Закреплённая ревизия nixpkgs содержит Quickshell 0.3.0 с IPC signals. Не добавлять его в общий PATH/home.packages.
- [ ] Выполнить `nix build .#widgets-runtime` и headless check с offscreen/software. Ожидается exit 0, импорт Quickshell/Io и валидный IPC JSON. Runtime launcher и QS config-selection syntax проверяются фактическим --help, не догадкой.
- [ ] Запустить probe в текущей GNOME-сессии и проверить рамку, прозрачность, фактические размеры и DPR при 150%, а также GPU/Qt Wayland загрузку. Завершить только probe PID. Непроверенное размещение под кнопкой оставить задаче 5; здесь не считать оконную интеграцию доказанной.
- [ ] Если runtime несовместим, локализовать причину в closure; применить локальный package override release 0.3.1 с проверенным source hash. Отдельный widgets/runtime flake использовать только если пакет нельзя собрать на текущем graph; причину и revision записать. После замены повторить этот же probe.
- [ ] Коммит только runtime, probe и flake exposure: `build: add scoped Quickshell widget runtime`.

## Task 2: Реестр и доставка многомодульных extensions

**Files:** Create `widgets/registry.nix`, `widgets/manifest.nix`, `widgets/quickshell/framework/manifest.mjs`, `lib/gnome_extension_files.py`, `tests/test_gnome_extension_files.py`, `tests/widgets/run-tests.js`, `tests/widgets/test-manifest.js`; Modify `bin/ws-keyboard-install-extensions`, `bin/ws-gnome-check`; Add Nix checks в `flake.nix`.

**Interfaces:** Produces Nix function `{lib, registry, qmlRoot} -> manifest attrset`; JS `validateManifest(value): entries` throws descriptive Error. Python `source_files(root): list[str]`, `install_files(source, destination): list[str]`, `verify_files(source, destination): list[str]`. Owner filenames сохраняются в `.ws-owned-files.json` внутри extension destination; `gschemas.compiled` не является source file.

- [ ] Добавить failing tests: duplicate ID, width=0/1.5, неизвестная position/schema, traversal и symlink escape отклоняются; disabled entry остаётся disabled. Для доставки:

```python
def test_upgrade_preserves_foreign_file(self):
    install_files(source_v1, destination)
    (destination / "foreign.txt").write_text("keep")
    install_files(source_v2, destination)
    self.assertTrue((destination / "lib/new.js").exists())
    self.assertFalse((destination / "lib/old.js").exists())
    self.assertEqual((destination / "foreign.txt").read_text(), "keep")
```

- [ ] Запустить `python3 -m unittest discover -s tests -p test_gnome_extension_files.py` и `gjs -m tests/widgets/run-tests.js manifest`; подтвердить падение assertions/import конкретного отсутствующего модуля.
- [ ] Реализовать registry/validation, Python owner manifest и применение в существующем installer. Первая миграция не удаляет неизвестные старые файлы. Проверять unsafe source paths и symlinks; metadata и schemas проверять прежним способом. Registry временно пуст до задачи 4, не ссылаться на отсутствующий QML.
- [ ] Подключить проверку доставляемых модулей в ws-gnome-check без изменения result contract. Проверка должна обнаруживать отсутствие/изменение lib/*.js и не считать foreign.txt ошибкой.
- [ ] Повторить оба runner; проверить schemas regression, nested assets, отсутствующий файл и перенос/удаление модуля. Выполнить `nix build .#checks.x86_64-linux.widgets-manifest --no-link`; ожидается exit 0 и проверенные failure cases.
- [ ] Коммит: `feat: validate widget registry and deliver extension modules`.

## Task 3: Controller и контракт IPC

**Files:** Create `widgets/quickshell/framework/model.mjs`, `widgets/quickshell/framework/WidgetController.qml`, `widgets/quickshell/framework/WidgetIpc.qml`, `widgets/quickshell/framework/qmldir`, `tests/widgets/test-model.js`, `tests/widgets/qml/shell.qml`; Modify `tests/widgets/run-tests.js`, `flake.nix` (headless checks).

**Interfaces:** Consumes validated entries. Pure JS `createState(entries, instanceId, pid): State`, `reduce(state, event, nowMs): {state, accepted, effects}`; effects prepare/animate/hide/error. Events COMMAND(action,id), PLACED(id,requestId), FAILED(id,requestId,reason), FINISHED(id,requestId,phase), AVAILABLE(id,value), LEASE(instanceId), TICK. QML Controller produces snapshotJson and surface/animation requests, implements публичные и внутренние IPC методы из общего контракта.

- [ ] Добавить tests с контролируемым nowMs: preparing начинается после show, PLACED запускает opening; повторный toggle отменяет preparing; старый requestId не раскрывает новое окно; switching ждёт closed; unknown ID возвращает accepted=false. Пример обязательного свойства:

```javascript
const initial = createState(entries, 'instance-1', 42);
const shown = reduce(initial, {type: 'COMMAND', action: 'show', id: 'example'}, 0);
const timedOut = reduce(shown.state, {type: 'TICK'}, 2000);
assert(timedOut.state.widgets.example.phase === 'closed');
assert(timedOut.state.lastError !== null);
```

- [ ] Запустить `gjs -m tests/widgets/run-tests.js model`; подтвердить red. Добавить отдельные assertions lease expiry при 6000 мс и игнорирования renew старого instanceId; проверять границы timeout.
- [ ] Реализовать reducer и QML Controller с injectable clock для tests, монотонным временем в runtime. Смена instanceId сбрасывает всё; revision обеспечивает порядок. WidgetIpc — единственное место регистрации IPC functions/signals.
- [ ] Реализовать headless shell, проверяющий реальные QML imports и регистрацию функций. Использовать runtime задачи 1; assertions завершают процесс через Qt.exit(0/1), launcher не запускает рабочую конфигурацию.
- [ ] Повторить GJS model tests и `nix build .#checks.x86_64-linux.widgets-qml --no-link`; ожидается exit 0. В IPC smoke вызвать show unknown, status и listen stateChanged; проверить typed signatures и snapshot fields.
- [ ] Коммит: `feat: add shared widget controller and IPC lifecycle`.

## Task 4: Общий контейнер и два QML-виджета

**Files:** Create `widgets/quickshell/framework/Style.qml`, `widgets/quickshell/framework/WidgetRegistry.qml`, `widgets/quickshell/framework/WidgetHost.qml`, `widgets/quickshell/framework/PopupFrame.qml`, `widgets/quickshell/adapters/gnome/GnomePopupWindow.qml`, `widgets/quickshell/widgets/example/Widget.qml`, `widgets/quickshell/widgets/compact/Widget.qml`, `widgets/quickshell/shell.qml`, `tests/widgets/qml/broken/Widget.qml`; Modify `widgets/registry.nix`, `widgets/quickshell/framework/qmldir`, `tests/widgets/qml/shell.qml`.

**Interfaces:** WidgetHost takes definition/controller and provides loaded content. Content has `required property QtObject context`: widgetId, contentWidth/contentHeight, devicePixelRatio, phase, requestClose(). PopupFrame takes desired progress, animationsEnabled and content; emits animationFinished(id,requestId,phase). GnomePopupWindow создаёт поверхность, сообщает actual geometry и передаёт запросы Controller.

- [ ] Добавить failing QML tests: оба ID загружаются из registry и получают свой context; broken component помечается unavailable, compact продолжает открываться; visible сохраняется во время closing и становится false после FINISHED.
- [ ] Запустить widgets-qml check и подтвердить red. Fixture broken используется только тестами и не входит в production registry.
- [ ] Реализовать composition и общие стили: animation 180 мс на полный progress, radius 16, content padding 16, transparent outer gutter 12 с каждой стороны. Registry width/height означают всю видимую панель вместе с padding; размеры поверхности = panel + 24. Context contentWidth/Height = panel минус 32. Уменьшенные размеры не становятся отрицательными.
- [ ] Реализовать clipping/opacity анимацию и input Region: прозрачная область и ещё не раскрытая часть пропускают клики. Анимация начинается только после placement ack. При смене target продолжать от текущего progress; zero-duration режим завершается корректно. На window size constraint update не анимировать размеры поверхности.
- [ ] Добавить example 420×580 и compact 320×240 в registry. Пример содержит close и actual panel size/DPR; compact использует тот же контракт с другим содержимым. ScrollView сохраняет доступ к содержимому при clamp.
- [ ] Проверить headless import/contract tests и runtime probe с обеими поверхностями. Это проверяет QML и rendering, размещение выполняется в следующей задаче.
- [ ] Коммит: `feat: add reusable popup frame and demonstration widgets`.

## Task 5: GNOME-кнопки, IPC client и размещение

**Files:** Create `gnome/extensions/workstation-widgets@local/metadata.json`, `gnome/extensions/workstation-widgets@local/extension.js`, `gnome/extensions/workstation-widgets@local/lib/panelButtons.js`, `gnome/extensions/workstation-widgets@local/lib/ipcClient.js`, `gnome/extensions/workstation-widgets@local/lib/windowPlacement.js`, `gnome/extensions/workstation-widgets@local/lib/geometry.mjs`, `gnome/extensions/workstation-widgets@local/lib/protocol.mjs`, `tests/widgets/test-geometry.js`, `tests/widgets/test-protocol.js`, `tests/widgets/test-ipc-client.js`; Modify `tests/widgets/run-tests.js`.

**Interfaces:** `PanelButtons(entries, onToggle)` supplies getButton(id), update(snapshot), destroy(). `IpcClient(runtimeConfig, onSnapshot, onUnavailable)` supplies start(), call(target,method,args), destroy(). `WindowPlacement(controllerClient, buttons)` supplies update(snapshot), destroy(). Pure `placePopup(buttonRect, workArea, surfaceSize, gap=8): {x,y,width,height}` использует согласованные stage units. `acceptSnapshot(previous,incoming)` отвергает устаревшие revision того же instanceId.

- [ ] Добавить geometry tests для кнопок у левого/правого края, отрицательного monitor origin, рабочей области меньше surface; rect всегда внутри workArea. Protocol tests: новый instance принимается с меньшим revision, устаревший snapshot того же instance игнорируется, disconnect сбрасывает кнопки, malformed JSON/protocol отклоняются.
- [ ] Запустить GJS runner geometry/protocol; подтвердить red. IPC transport test использует subprocess double с контролируемым timeout, не читает Shell глобалы.
- [ ] Реализовать async client: subscribe перед status; один reader, очередь команд, timeout 2000 мс, bounded reconnect delay 250/500/1000/2000 мс (далее 2000), lease каждые 2000 мс после adapterReady. Уничтожение отменяет pending calls и timers; generation token не позволяет старому reader изменить новую связь.
- [ ] Для development доставить временный runtime.json/manifest.json, адресующие worktree и package задачи 1; сохранить прежние owner-файлы, если они уже существуют, и восстановить их после проверки. Это bootstrap до Home Manager задачи 7, а не второй production источник реестра.
- [ ] Реализовать кнопки и placement: title + PID, реальные button/workArea/frame rect, monitor selection, setGeometry до placed, activate с user-event timestamp, make_above для открытой панели. После resize дождаться actual geometry, затем подтвердить размещение; таймаут закрывает панель.
- [ ] Проверить API и stage/protocol coordinate conversion по установленному Mutter 50. Нельзя использовать документацию Meta 51 как доказательство наличия метода в 50. Исключить окно из switcher/dock доступным API без глобальной подмены window manager. Выключение extension очищает свои signals/actors/subprocesses.
- [ ] Доставить extension через installer задачи 2, запустить runtime по явному worktree path. Если Shell ещё не знает нового UUID, сообщить необходимость logout/login и продолжить независимые static/tests; не завершать сессию автоматически.
- [ ] Проверить на текущих 150%: появление под каждой кнопкой, отсутствие центральной вспышки/рамки/двойной анимации, focus, sizes и lease timeout. Если базовая оконная связка не работает, локализовать adapter defect до дальнейшей интеграции.
- [ ] Коммит: `feat: integrate widget buttons and window placement with GNOME`.

## Task 6: Закрытие, фокус и desktop lifecycle

**Files:** Create `gnome/extensions/workstation-widgets@local/lib/dismissal.mjs`, `tests/widgets/test-dismissal.js`; Modify `gnome/extensions/workstation-widgets@local/extension.js`, `gnome/extensions/workstation-widgets@local/lib/windowPlacement.js`, `widgets/quickshell/adapters/gnome/GnomePopupWindow.qml`, `widgets/quickshell/framework/PopupFrame.qml`, `tests/widgets/run-tests.js`, `tests/widgets/qml/shell.qml`.

**Interfaces:** Pure `shouldDismiss(event, context): boolean`; context включает active widget window family, собственные кнопки и текущий opening request. Extension подаёт Shell events и focus changes в policy, закрытие проходит через widgets.hide/hideAll.

- [ ] Добавить failing policy tests: own-button event не вызывает отдельный hide; unrelated focused window вызывает hide; transient child не вызывает hide; background/Shell outside click вызывает hide и возвращает EVENT_PROPAGATE. Добавить races captured-event → focus-window и focus-window → button callback: один пользовательский toggle, итог closed.
- [ ] Запустить dismissal runner; подтвердить red. Добавить QML Esc test: requestClose → closing → closed, без немедленного уничтожения окна.
- [ ] Реализовать focus/outside policy, фильтрацию собственной кнопки и transient chain. Обрабатывать overview, workspace change, screen lock, disable extension через hideAll. Реакция на background Shell events не создаёт глобальный modal grab.
- [ ] Передавать GNOME enable-animations в Controller, применять нулевую длительность при disabled, обновлять при изменении настройки. На monitor/scale change ограничить размер и повторно разместить панель без изменения UI scale.
- [ ] Повторить automated tests и live matrix быстрых кликов, focus, Esc, overview, workspace, lock/unlock, disable/re-enable. После restart runtime принять новый PID/instance и не пытаться управлять старым окном.
- [ ] Коммит: `fix: handle widget focus and desktop lifecycle reliably`.

## Task 7: Home Manager, сервис и команды владельца

**Files:** Create `widgets/widgets.nix`, `bin/ws-widgets`, `bin/ws-widgets-check`, `tests/test_ws_widgets.py`; Modify `nix/home/default.nix`, `gnome/gnome-extensions.nix`, `bin/ws`, `flake.nix` checks.

**Interfaces:** Home Manager доставляет runtime.json/manifest.json по общим путям и QML link; service `workstation-widgets.service`. CLI: start/stop/restart/status/check, toggle/show/hide ID, hide-all. `ws-widgets check --json` delegирует bash checker и печатает один object формата lib/check.bash. `ws check widgets` запускает этот owner.

- [ ] Добавить Python tests с command doubles: status/check не вызывает start/restart/install, CLI args передаются массивом, неизвестная команда exit 64, unknown ID exit nonzero, failed qs отражается в результате. `--json` stdout содержит только check object. Проверить отказ запуска вне GNOME/без WAYLAND_DISPLAY.
- [ ] Запустить `python3 -m unittest discover -s tests -p test_ws_widgets.py`; подтвердить red.
- [ ] Реализовать HM module и unit: PartOf/After/WantedBy graphical-session.target, process-local Qt options, ExecStart абсолютный scoped launcher, Restart=on-failure, RestartSec=2, StartLimitIntervalSec=60, StartLimitBurst=5. Session guard в launcher принимает ubuntu:GNOME/GNOME, другие desktop не запускает. Не hardcode номер wayland socket или UID.
- [ ] Добавить extension UUID в существующий единый список. Registry/manifest обновляются через ws switch. Сохранить штатные ways apply/check, не вводить отдельный источник настроек. CLI start использует systemctl user, IPC не создаёт второй runtime.
- [ ] Реализовать read-only owner checks manifest/runtime paths, service, extension ACTIVE, IPC protocol/PID, adapter lease; source/runtime module comparison делает GNOME owner. Для отсутствующей GUI-сессии report warn с причиной, не ложный pass оконных проверок.
- [ ] Выполнить tests, bash syntax, Nix home activation build для обоих хостов и widgets checks. Не активировать worktree generation, содержащую ссылки на неготовый main checkout; для development использовать явный worktree QML path и временную scoped unit/config.
- [ ] Коммит: `feat: deliver widget framework through workstation owners`.

## Task 8: Итоговая проверка, runbook и интеграция

**Files:** Create `docs/runbooks/widgets.md`, `tests/widgets/live-checklist.md`; Modify `README.md`, проект/план (статус и evidence), при необходимости checks только для выявленных ошибок.

**Interfaces:** Runbook описывает существующие CLI, единственный registry, Item/context contract, размеры panel/surface/content, запуск, check, developer tests, disable/rollback и ограничения GNOME 50. Metadata документа `title: ws-widgets`, section 1, source Workstation, volume User Commands.

- [ ] Прогнать GJS suite, новые Python tests и существующие unittest suite; widgets-qml, widgets-manifest и Nix home builds. Повторять только после изменений или непокрытых отказов. Проверить git diff --check и состав коммитов; результаты записать.
- [ ] Записать live evidence для двух разных ID/размеров при текущих 150%: physical coverage panel example 630×870 и compact 480×360 без gutter, actual Qt DPR, frame placement и доступность content. Добавить тест узкой workArea с прокруткой; не менять scale активного desktop автоматически.
- [ ] Проверить доступные дополнительные scale и внешний monitor только если доступны для проверки. Не проставлять PASS для отсутствующего монитора. Проверить Ubuntu Dock, Tiling Assistant, Alt-Tab, external click, invisible input mask, быстрые toggle, runtime kill/restart, lease expiry и extension cleanup.
- [ ] Провести independent review всей ветки по spec и Review Focus. Исправить подтверждённые замечания и повторить относящиеся к ним проверки.
- [ ] Написать runbook и README entry; отметить выполненные шаги и фактические ограничения. Проверить man build, что перечисленные команды действительно существуют, и что добавление compact требует только QML + registry.
- [ ] Коммит: `docs: document widget framework and verified GNOME behavior`.
- [ ] Интегрировать проверенные commits в main без перезаписи пользовательских правок; затем штатными ws switch/ws apply extensions доставить финальный источник. Проверить ws-widgets check и ws-gnome check. Не выполнять logout/reboot автоматически; если новый вход нужен для загрузки extension, чётко указать оставшуюся проверку.

## Самопроверка плана и исполнение

- [x] Все разделы spec связаны с задачами: runtime 1, registry/delivery 2,
  lifecycle/IPC 3, UI/scale 4, GNOME placement 5, desktop lifecycle 6,
  owners/service 7, validation/docs 8.
- [x] Контракты ID, snapshot, filenames и IPC согласованы между задачами.
- [x] Review Focus покрыт конкретными тестами, live checks отделены от unit.
- [x] Уточнены размеры панели, поверхности и content; не введён второй scale.
- [x] Технические ограничения проверяются до признания framework рабочим.
- [x] Пользователь согласовал проект и разрешил реализацию в отдельной ветке wsconfig; inline execution.

Рекомендуемое исполнение — Native: один исполнитель выполняет задачи по
порядку в этой сессии, затем отдельный reviewer проверяет всю ветку. Задачи
связаны общими IPC/lifecycle интерфейсами; последовательная работа сокращает
передачу контекста. Альтернатива — отдельный implementer и reviewer для
каждой задачи, с проверкой всей ветки в конце.

## Подтверждённые источники для исполнителя

- [Quickshell 0.3.0 в закреплённом nixpkgs](https://raw.githubusercontent.com/NixOS/nixpkgs/f5c082a40f7571c266e74e80ae2e68aadd8a9fc7/pkgs/by-name/qu/quickshell/package.nix).
- [IPC signals в Quickshell 0.3.0](https://quickshell.org/docs/v0.3.0/types/Quickshell.Io/IpcHandler/).
- [QML импорт ES modules](https://doc.qt.io/qt-6/qtqml-javascript-imports.html).
- Window API и Shell события проверяются по установленной версии GNOME 50
  и исходникам её пакетов; GNOME 51 documentation не подменяет эту проверку.

## Фактическое исполнение — ветка wsconfig

Задачи 1–7 реализованы отдельными коммитами; задача 8 — runtime/live smoke,
runbook и независимое ревью. Автоматические шаги выполнены. Чекбоксы live
матрицы не означают PASS: GNOME ещё не знает новый UUID, кнопки требуют
обычного нового входа. Интеграция в main отложена по последнему запросу
пользователя работать в отдельной ветке.

Первый прогон: Python 44/44; после синхронизации с main общий прогон
Python 122/122, GJS 37/37. Nix widgets-manifest, widgets-qml,
widgets-tests, widgets-runtime, home-mbp16, home-wsvm, man. Runtime probe DPR
1.5; production поверхности 444×604 и 344×264. Реальный GJS listener проверен
с разрывом во время открытия, reconnect и lease expiry. QML tests проверяют
clamp/scroll, lazy loading, broken component isolation и отключённые анимации.

Независимое ревью нашло три Important: центрирование под кнопкой, сообщение
об ошибке компонента через кнопку и lazy loading. Все воспроизведены RED и
исправлены с GREEN tests. Дополнительных minor findings нет.

Решения исполнителя:

- Native worktree tool не получил repository context; использован Git
  worktree. Цена: worktree не прикреплён в UI приложения, Git/файлы доступны.
- Реализация остаётся в отдельной wsconfig; main с пользовательскими
  изменениями не получает merge framework. После команды «продолжай» текущая
  main слита в wsconfig, ветка перенесена в основной checkout и применены
  ws switch / ws apply extensions. Пользовательские файлы, staged/unstaged
  diff сохранены побайтно. Цена: checkout должен содержать framework, пока
  активна production-ссылка на QML.
- Scoped launcher использует свой Mesa EGL vendor после отказа discovery.
  Цена: переносимость на другой GPU ещё требует проверки; настройки сессии
  не изменены.
- Реальный GNOME adapter, прочие scale и внешний монитор остаются live pending.
  Цена: возможные дефекты native placement/input/focus ещё не исключены.
- Hyprland adapter и содержательные системные виджеты остаются вне первого
  этапа. Цена: для них нужны следующие реализации поверх этого framework.
