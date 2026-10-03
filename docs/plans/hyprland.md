title: ws-plan-hyprland
section: 1
source: Workstation
volume: User Commands

# Миграция на Hyprland и Caelestia с сохранением Ubuntu GNOME

## Результат

План рассчитан на установленную на `mbp16` Ubuntu 26.04 с GDM, GNOME,
Nix поверх Ubuntu, Intel GPU и T2 kernel. Пользователь `king` получает в
GDM две рабочие Wayland-сессии:
`Ubuntu` и `Hyprland (ws)`. После проверки повседневную работу можно вести в
Hyprland; GNOME остаётся исправной резервной сессией. Установка, обновление,
откат и удаление Hyprland не меняют системные настройки GNOME.

Hyprland и Caelestia устанавливаются из отдельной зафиксированной Nix
generation. Команды `ws-hypr`, описанные ниже, составляют интерфейс, который
предстоит реализовать; до реализации их нельзя считать установленными.

## Границы миграции

| Владелец | Что остаётся под его управлением |
| --- | --- |
| Ubuntu | GNOME, GDM, kernel и T2-драйверы, system D-Bus, PipeWire, WirePlumber, NetworkManager, BlueZ, UPower, UDisks, базовые GTK/Flatpak portals и системная политика питания |
| Основной Home Manager | Общие CLI, приложения, ссылки на `bin/` и существующая конфигурация GNOME |
| `ws-hypr` | Отдельный Nix runtime, конфигурация Hyprland/Caelestia, GDM entry, launcher, пользовательские units, XDPH, выбранная generation и её GC roots |

Не добавлять Hyprland в основной `flake.nix` и общий `home.packages`. Не менять
глобальные `/etc/environment`, HM session variables, fish environment,
системные порталы или настройки темы GNOME ради новой сессии. Не запускать
upstream `caelestia install/update`: файлы и обновления должен контролировать
`ws-hypr`. В первой версии не добавлять KDE, UWSM и dock. Дополнительный
lock/idle helper допускается лишь после проверки функций Caelestia.

Сохранять текущую boot/GPU policy и host suspend/hibernate policy. Проверять
Hyprland сначала на Intel graphics в обычном режиме загрузки. Не менять
kernel, параметры T2, dGPU, ASPM, USB или системные sleep units в рамках
миграции. В обычной загрузке `Ubuntu` AMD отключена до GDM, поэтому
Thunderbolt DisplayPort и внешние мониторы недоступны; это не ошибка
Hyprland. Для проверки внешнего монитора использовать существующий пункт
загрузки `Ubuntu (AMD)` после успешной проверки встроенного экрана.

## Структура и источники

Добавить в `wsconfig`:

```text
bin/ws-hypr                    управление generations, checks и удалением
bin/ws-hyprland-session        стабильный GDM launcher
hypr/flake.nix                 независимый desktop flake
hypr/flake.lock                зафиксированный граф desktop inputs
hypr/desktop.nix               runtime, manifest и config view
hypr/session.nix               session helpers, units и portals
hypr/patches/                  минимальные проверяемые integration patches
hypr/overrides/hypr-vars.lua   пользовательские значения поверх upstream
hypr/overrides/hypr-user.lua   дополнительные правила и привязки
hypr/overrides/caelestia.nix   изменения настроек shell/CLI
docs/runbooks/hyprland.md      операции после завершения миграции
```

Использовать `nix/hosts/mbp16/facts.nix` для имени хоста, пользователя и пути
к checkout. `nix/home/links.nix` может доставлять `ws-hypr` как общий скрипт,
но не должен активировать второй Home Manager profile в том же `HOME`.
Новые Nix source-файлы надо добавить в Git до flake evaluation: Git-backed
flake не видит неизвестные ему файлы.

Desktop flake фиксирует:

- `github:hyprwm/hyprnix` — release-oriented Hyprland и совместимый XDPH;
- `github:caelestia-dots/shell/stable` — Caelestia Shell через output
  `with-cli` либо отдельный CLI output; Quickshell из того же dependency graph;
- `github:caelestia-dots/caelestia` с `flake = false` — исходные dotfiles.

`hypr/flake.lock` независим от основного `flake.lock`. `ws update nix` не
обновляет desktop runtime. Перед первым build выбрать совместимые revisions:
проверить Lua entrypoint и вызываемый `hl.*` API у выбранного Hyprland,
settings schema и startup/keybind commands у Caelestia. Если текущие dots
не совместимы с release Hyprland, зафиксировать совместимый revision dots
и причину в generation manifest. Не подменять release compositor веткой
`main` ради обхода несовместимости. Выбранный Hyprland должен предоставлять
`start-hyprland` и автоматическое управление `hyprland-session.target`;
наличие обоих свойств проверять на собранной generation.

Caelestia `with-cli` добавляет Hyprland из своего Nix package graph в
runtime dependencies. Переопределить эту зависимость на тот же Hyprland,
который выбран из `hyprnix`, и проверить итоговый `PATH`/closure: launcher
и shell commands не должны вызывать две разные версии compositor.

Дополнительно к зависимостям shell включать только реально нужные desktop
helpers, fonts, clipboard, screenshot/record, audio controls, keyring и
night-light tools. Существующие
terminal, browser, file manager и Flatpak app IDs используются вместо
upstream defaults после инвентаризации команд в config. Не переносить
целиком список пакетов для другого дистрибутива.

## Модель generation и файлов

`ws-hypr` хранит state в `~/.local/state/workstation/hyprland/`:

- `selected` — rooted generation для следующего входа;
- `running` — отдельный GC root generation действующей сессии;
- history и manifest — версии inputs, точный lock, Nix store paths,
  checksums overrides, schema, внешние host dependencies и результат checks;
- transaction journal — начатые и завершённые изменения owner paths;
- backups — исходное содержимое заменённых принадлежащих owner файлов.

GC roots создаются Nix profile/root механизмом. Обычная произвольная
символьная ссылка не считается достаточной защитой от garbage collection.
`candidate` становится `selected` только после успешной сборки и static
checks. `known-good` присваивается только после ручной проверки входа и
команды `ws-hypr mark-good`.

Каждая generation содержит read-only view pinned upstream config и
сгенерированный `shell.json` только с настройками, отличающимися от defaults.
Ссылки `~/.config/hypr` и `~/.config/caelestia/shell.json` указывают на
generation текущей сессии. Launcher устанавливает их до запуска compositor;
`update`, `switch` и `rollback` во время сессии меняют только `selected`.
Пока compositor и его services работают, targets ссылок не меняются.
После остановки services ссылки приводятся к `selected`, затем снимается
`running` root. Если cleanup не завершён, root сохраняется и `check`
сообщает о residue. Так reload живой сессии не смешивает две generations.

`hypr-vars.lua` и `hypr-user.lua` остаются ссылками на checkout. Их ручная
правка и writable `scheme/current.lua` — явные исключения из pin: изменения
могут действовать после reload и не откатываются вместе с Nix closure.
`status` сообщает об изменении checksum. Перед rollback проверять их
совместимость с целевой generation; для полного отката пользовательской
delta нужен сохранённый Git revision или её snapshot.

До install проверять все целевые пути. Файлы другого владельца не
перезаписывать: конфликт останавливает операцию до мутаций. Owner manifest
фиксирует каждый созданный link, unit, root artifact и backup; remove
удаляет только объекты, чьё содержимое и тип совпадают с manifest.

## Этап 1. Подготовить исходную точку

Все проверки хоста выполнять в host terminal. Перед началом отделить
посторонние изменения checkout от Hyprland-работы. Исходный commit должен
быть чистым, а активная Home Manager generation и установленное system tree
должны ему соответствовать. `ws checkpoint create` отказывает при dirty
checkout или несовпадении HM generation. Не применять посторонние изменения
к живой системе только ради создания checkpoint.

1. Проверить `git status --short`, `ws system check` и текущую HM generation.
   Если состояния расходятся, привести их к согласованному исходному
   commit отдельной работой; перед `ws switch` просмотреть его diff.
2. Запустить `ws check` и записать существующие WARN/FAIL. Полная команда
   запускает также проверки контейнеров.
3. Создать исходный checkpoint: `ws checkpoint create pre-hyprland`.
   Команда сама захватывает baseline и удерживает HM/system store paths.
4. До установки GDM entry и первого входа создать Timeshift snapshot,
   проверить его наличие и состав включённых Btrfs subvolumes. Если
   восстановление из snapshot не настроено, завершить его настройку до
   изменения системных файлов. Проверить, что GNOME по-прежнему доступен.
5. Проверить на Ubuntu работающий Nix daemon, GDM, host PipeWire,
   WirePlumber, `xdg-desktop-portal` с GTK backend, PAM password
   authentication и доступ пользователя к Intel render node в
   Wayland-сессии. Зависимости, отсутствующие на хосте, записать в
   manifest и установить до первого входа; NixOS paths вроде
   `/run/current-system/sw` на Ubuntu не использовать.

Если пункт 1 не выполнен, можно сохранить диагностические read-only
результаты, но не считать их rollback anchor. Реализацию вести в отдельной
ветке или worktree от исходного commit; не включать посторонний staged
материал в её commits.

**Переход к следующему этапу:** исходный checkpoint создан, известны
исходные WARN/FAIL, GNOME проходит свои текущие проверки.

## Этап 2. Собрать и проверить desktop runtime

1. Зафиксировать inputs в `hypr/flake.lock` и собрать Hyprland, XDPH,
   Caelestia Shell с CLI, Quickshell и требуемые helpers. Сохранить версии
   и store paths в manifest; убедиться, что Caelestia wrapper использует
   выбранный Hyprland.
2. Проверить Lua syntax/config API, shell settings schema и наличие всех
   реально вызываемых программ. Ошибка любого из этих checks запрещает
   создание `selected`.
3. Построить config view из pinned upstream tree. Не копировать upstream
   defaults в Git. Patch обязан удалять startup-запись GNOME cursor
   `gsettings`, автоматическую очистку корзины, дублирующие agents и
   services; остальные обработчики сохраняются. Patch проверяет ожидаемый
   фрагмент и при изменении upstream завершается ошибкой.
4. Для `scheme/current.lua` создать единственное нужное writable исключение
   в owner state. Проверить все другие места записи Caelestia CLI и shell:
   GNOME/GTK/Qt, terminal/editor и wallpaper settings не меняются без
   явного override.
5. Проверить host Mesa через `eglinfo -p gbm -B` и доступ к Intel render
   node. Для Nix Hyprland на Ubuntu использовать `start-hyprland` из
   выбранной generation: поддерживаемая версия подключает nixGL при
   необходимости. Проверка host EGL не заменяет запуск Nix compositor:
   фактическое разрешение driver libraries и GPU проверить при первом
   входе из GDM. Не подменять глобальные graphics paths и не включать
   глобальный HM `targets.genericLinux`.
6. Проверить PAM-файлы выбранной Caelestia generation. Её lock screen
   использует `assets/pam.d/passwd` из shell tree, а не автоматически
   Ubuntu `/etc/pam.d`. Исключить неподходящие NixOS module paths и
   необязательную биометрию. Не включать автоматическую блокировку и
   lock-before-sleep до проверки password unlock в живой сессии.

Сборка и static tests не объявляют runtime пригодным для входа.

**Переход к следующему этапу:** closure и config view воспроизводимо
собираются из lock; patch и schema checks проходят; GNOME не изменён.

## Этап 3. Реализовать управление сессией

`ws-hypr` предоставляет:

```text
ws-hypr install
ws-hypr update
ws-hypr switch
ws-hypr status
ws-hypr check [--json]
ws-hypr mark-good
ws-hypr rollback
ws-hypr remove
```

- `install` проверяет paths и host dependencies, строит locked runtime,
  создаёт selected root, config links и user units, затем устанавливает
  root-owned GDM entry и launcher. Отказ возвращает уже изменённые owner
  paths по journal. Не перезапускать GDM во время рабочего GNOME login.
- `update` под owner lock строит candidate с новым lock во временном месте,
  запускает build/check, показывает разницу inputs/closure и только после
  успеха сохраняет lock, root и переключает `selected`. Failed update не
  меняет `selected`, `running` или текущие config links.
- `switch` выбирает уже собранную checked generation для следующего login.
  `rollback` выбирает предыдущую `known-good` generation после проверки
  mutable overrides. В живой сессии обе команды не заменяют runtime.
- `mark-good` из Hyprland-сессии требует совпадения `running` и `selected`
  и успешного `ws-hypr check`. Вызов после smoke-test явно подтверждает
  ручную проверку; команда записывает generation ID и время.
- `status` различает installed/removed, candidate/selected/running,
  known-good, drift lock и mutable overrides. `check --json` использует
  протокол `lib/check.bash`.

Системный `/usr/share/wayland-sessions/ws-hyprland.desktop` вызывает
`/usr/local/bin/ws-hyprland-session` без version-specific store path.
В entry задать `Type=Application`, `Name=Hyprland (ws)`,
`Exec=/usr/local/bin/ws-hyprland-session` и `DesktopNames=Hyprland`;
проверить, что GDM выставляет ожидаемый desktop identity.
При install launcher берёт имя пользователя из host facts, а UID и
canonical HOME определяет через системную базу учётных записей.
Поскольку GDM entry виден всем, launcher проверяет identity до чтения
checkout, profile и state и отказывает другому пользователю.

Launcher запрещает одновременные graphical sessions одного UID. Он
разрешает `selected` один раз, создаёт `running` root, устанавливает
generation config links и запускает именно `start-hyprland` из generation
с закрытым session-local PATH и desktop environment. `XDG_DATA_DIRS`
сохраняет host и Flatpak application paths. После появления настоящих
`WAYLAND_DISPLAY` и Hypr socket импортировать `XDG_CURRENT_DESKTOP=Hyprland`,
`XDG_SESSION_TYPE=wayland`, `WAYLAND_DISPLAY` и нужные display variables
в user systemd и D-Bus activation environment до запуска portal и shell.

Hyprland сам управляет `hyprland-session.target` и
`graphical-session.target`; launcher не создаёт и не запускает их вручную.
Однократный session-ready helper, вызванный из Hyprland после создания
Wayland socket, сначала импортирует environment, затем запускает
`ws-hyprland-session.target`. Связать этот target через `PartOf` с
`hyprland-session.target` для остановки; не добавлять его в `WantedBy`
Hyprland target, иначе services могут стартовать до импорта environment.
Только собственные units этого target запускают Caelestia, polkit agent,
clipboard и keyboard helper. При logout или crash дождаться остановки
собственных services, проверить завершение Hypr-only processes, привести
config links к `selected` и только затем снять `running` root. Проверить штатный logout,
crash и следующий GNOME login. Сохранить прежние activation variables до
входа и восстановить допустимые значения при cleanup; отсутствие
Hypr-only значений в D-Bus activation environment проверить отдельно.
Одного `systemctl --user unset-environment` для этого недостаточно.

Portal frontend и GTK backend остаются host-owned. Owner устанавливает
`~/.config/xdg-desktop-portal/hyprland-portals.conf` для
`XDG_CURRENT_DESKTOP=Hyprland`: Nix XDPH обслуживает ScreenCast/Screenshot,
host GTK — FileChooser и проверенные fallback interfaces. До login
зарегистрировать XDPH `.portal` descriptor, D-Bus activation file и
user unit в путях, которые действительно читает Ubuntu portal frontend,
user bus и systemd --user. Одного `XDG_DATA_DIRS` в launcher недостаточно:
проверить обнаружение backend из окружения user manager. После завершения
GNOME login остановить оставшийся `xdg-desktop-portal-gnome.service`, если
user manager его сохранил. После импорта Hypr environment управляемо
перезапустить frontend, чтобы он прочитал новый desktop-specific config;
проверить ScreenCast и FileChooser в Flatpak. При возвращении в GNOME
восстановить GNOME portal routing и убедиться, что XDPH не активен.
GNOME-specific config и host portal
packages не заменять. Запускать ровно один polkit agent; system rules
и GNOME agent не менять.

Текущий GNOME xremap service включён через `graphical-session.target`,
который Hyprland также запускает, а его backend и layout selector зависят
от GNOME. До первого Hyprland login перевести его `WantedBy` и `PartOf`
на `gnome-session.target` и проверить, что в Ubuntu он стартует и
останавливается вместе с GNOME. Для Hyprland поставить отдельный pinned
backend/config под собственным session target; если
совместимый remapper не найден, использовать native Hyprland binds для
первого smoke-test, но не считать клавиатуру перенесённой. Проверить один
input grabber, EN/RU/UA, CapsLock EN/RU, Fn+CapsLock UA, Command shortcuts,
исключения terminal/VM, выбор раскладки без GNOME D-Bus и EN на lock screen.
Host `ws-touchbar-fn` получает Fn от виртуального xremap input device:
без Hyprland remapper нельзя считать работу Fn-переключения Touch Bar
перенесённой или присваивать generation статус `known-good`.

## Этап 4. Проверить owner и установить GDM-сессию

До изменения host paths выполнить тесты на временных каталогах:

- install при свободных путях и отказ при чужом файле, symlink или unit;
- interrupted install/update и повторный запуск после journal recovery;
- failed candidate build, не меняющий `selected`;
- update/rollback при живой сессии без смены её runtime и config links;
- logout/crash cleanup, сохранение GC root при незавершённом cleanup;
- launcher под другим UID, не читающий state пользователя `king`;
- синтаксис сгенерированных units и отсутствие преждевременного
  `WantedBy=hyprland-session.target` у собственного target;
- remove, не удаляющий изменённый чужой root artifact;
- обновление основного `flake.lock` без изменения `hypr/flake.lock`.

Расширить `ws-gnome check`, `ws-keyboard check`, `wsflatpak test` и
`ws-workstation-verify` для трёх режимов: GNOME, Hyprland и отсутствие
graphical session. GNOME declarative checks выполняются всегда;
GNOME runtime assertions остаются обязательными в Ubuntu. В Hyprland
обязательны Hypr runtime и отсутствие GNOME input grabber. В TTY/SSH
неприменимые runtime assertions дают `N/A` через `info`, не ложный
`PASS` или `FAIL`. В частности, `wsflatpak test` не должен требовать
`xdg-desktop-portal-gnome.service` в Hyprland; он проверяет выбранный
portal backend и реальные операции. Добавить `ws-hypr check` в общий
`ws check`. Расширить baseline/checkpoint данными о desktop generation,
links, roots и portal
environment.

После тестов запустить `ws-hypr install` из GNOME. Проверить owner manifest,
root-owned GDM files, selected root, config links и `ws check`. GDM должен
предлагать `Ubuntu` и `Hyprland (ws)`. GNOME-сессию не завершать до готового
`selected` и работающего launcher.

До выхода из Ubuntu проверить, что GNOME xremap остался активным и XDPH
обнаруживается host portal frontend без его запуска. Порядок импорта
environment, выбор XDPH и отсутствие GNOME xremap окончательно проверять
после реального входа в Hyprland.

**Переход к первому входу:** `ws check` не показывает новых ошибок GNOME,
новая сессия видна в GDM, все owner paths соответствуют manifest.

## Этап 5. Первый вход и перенос повседневных функций

Завершить GNOME login и войти в `Hyprland (ws)` тем же пользователем.
Сначала проверить запуск через `start-hyprland`, аппаратный Intel
renderer, доступ к render node, наличие способа открыть terminal и
вернуться в GDM. При ошибке compositor использовать TTY для чтения
user journal, затем вернуться в Ubuntu; не менять GPU policy наугад.
Проверить, что `hyprland-session.target` запущен compositor, собственные
units стартовали после импорта environment, GNOME xremap не работает,
portal frontend выбрал XDPH и GTK. Затем выполнить smoke-test:

| Область | Что должно работать |
| --- | --- |
| Экран | Встроенная панель в доступном полном режиме, масштаб 1.5 как проверяемая цель; внешний монитор отдельно после загрузки `Ubuntu (AMD)` |
| Shell | Caelestia bar, workspaces, launcher, tray, notifications, OSD, restart shell и применение scheme |
| Приложения | Ghostty, установленный browser и file manager, Flatpak app IDs, `.desktop` lookup и открытие URI |
| Ввод | Все три раскладки, CapsLock/Fn shortcuts, Command shortcuts, app exclusions, один input grabber; отдельная проверка lock/unlock на EN |
| Portals | Реальный Flatpak FileChooser и ScreenCast с PipeWire stream; отдельно clipboard/history и notifications |
| Доступ | Polkit authentication dialog, host keyring/Secret Service и отсутствие второго agent |
| Звук и питание | PipeWire, T2 audio/input/Touch Bar после S3 и hibernate, lock до sleep, host suspend-then-hibernate без второй sleep policy |

До настройки idle/sleep вручную вызвать Caelestia lock, убедиться в отказе
при неверном пароле и разблокировке верным паролем; держать доступным TTY
для восстановления. Проверить, что PAM modules и account policy
работают на Ubuntu. Если Caelestia lock не проходит, отключить его
lock command и выбрать один проверенный host-compatible locker, закрепив
его и idle helper в desktop closure. Только после успешного ручного
lock/unlock включить auto-lock и lock-before-sleep, проверить, что sleep
не начинается до фактической блокировки, затем тестировать S3 и hibernate.
Не менять системную политику питания ради shell menu.

Протестировать logout, повторный Hyprland login, падение compositor и
возврат в Ubuntu. В GNOME сравнить checks, cursor/theme, keyboard,
portal routing и user environment с исходным checkpoint. После
успешного Intel smoke-test при необходимости загрузиться в `Ubuntu (AMD)`
и проверить Hyprland с внешним монитором: AMD остаётся включённой по
существующей boot policy, в сессии её не переключать. Затем снова
проверить Ubuntu GNOME в обычном режиме загрузки. Завершив полный
smoke-test, вернуться в Hyprland и выполнить
`ws-hypr mark-good`.

**Результат этапа:** обе GDM-сессии работают; новая generation имеет
`known-good`; GNOME не получил Hypr-only services, variables или backend.

## Этап 6. Доказать обновление, откат и удаление

1. Собрать заведомо неуспешный candidate и убедиться, что действующая
   generation и lock не изменились.
2. Во время Hyprland login выбрать другую checked generation; подтвердить,
   что compositor, config view и `shell.json` остаются от `running` до
   logout, а следующий login использует `selected`.
3. Проверить rollback к предыдущей `known-good` generation, включая
   несовместимую mutable delta и прерванную transaction. При несовместимости
   rollback отказывает до переключения.
4. Из Ubuntu выполнить `ws-hypr remove`. Он требует отсутствия активной
   Hyprland-сессии, сверяет owner paths, убирает GDM entry, launcher,
   units, activation/config links и все Hypr GC roots. Неизвестные или
   изменённые чужие файлы сохраняются; их наличие даёт отчёт и отказ
   до удаления. Общий HM profile и исходные overrides в checkout остаются.
   Общий Nix GC не запускается.
5. Сравнить GNOME с checkpoint и повторно установить layer из сохранённого
   lock и overrides. Проверить вход, затем при необходимости снова удалить.

`docs/runbooks/hyprland.md` после выполнения этапов должен содержать
рабочие команды install/update/status/check/rollback/remove, расположение
manifest/journal и порядок восстановления входа через Ubuntu GNOME.
Dock рассматривается отдельно после подтверждения, что Caelestia покрывает
основной shell UX.

## Критерии завершения

- GDM предлагает две рабочие сессии; Ubuntu GNOME сохраняет прежние
  settings, extensions, клавиатуру, applications и owner checks.
- Hyprland/Caelestia воспроизводимо собираются из собственного lock;
  update основного Nix flake не затрагивает desktop generation.
- Runtime и immutable config запущенной сессии закреплены до logout;
  изменяемые Lua overrides и scheme явно показаны как исключения.
- GPU, display, keyboard parity, portals, polkit/keyring, shell,
  password lock/unlock, lock-before-sleep, S3/hibernate и T2 devices
  проверены в живой сессии.
- `ws check` корректен в GNOME, Hyprland и без graphical session;
  `status` различает selected, running, candidate и known-good.
- Failed update не меняет рабочую сессию; rollback выбирает полный
  known-good runtime с проверкой mutable delta.
- Remove из GNOME убирает все принадлежащие layer объекты и GC roots;
  GNOME после удаления совпадает с исходным baseline.
- Повторный install из сохранённых lock и overrides восстанавливает
  рабочую Hyprland-сессию.
