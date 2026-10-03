# Восстановление workstation с Unraid из Live USB

Дата: 2026-10-03. Статус: спецификация для проверки пользователем;
код нового recovery ещё не реализован.

## Цель и согласованный сценарий

Пользователь загружает этот ноутбук с Linux Live USB, имеет SSH-доступ
к Unraid и выбирает конкретный ранее переданный снимок Timeshift, которого
может уже не быть на ноутбуке. Одна автономная команда получает снимок,
проверяет его, сохраняет текущую систему и готовит загрузку восстановленной.
Локальный журнал backup и работа установленной ОС для этого не требуются.

Предлагаемый интерфейс Live USB:

```console
sudo bash ws-restore
```

Интерактивный сценарий: SSH host/port/user/key или готовый alias → host ID
→ проверенный каталог дат → выбранный снимок → system или system+HOME →
подтверждение целевого Btrfs filesystem → получение и проверки → обзор
изменений → явное подтверждение переключения → результат и инструкция загрузки.
Скрипт не перезагружает компьютер автоматически.

## Рассмотренные способы

1. Автономный recovery с проверками и журналом: выбран. Не зависит от
   локального Timeshift, Nix, Home Manager и рабочего checkout.
2. Импорт remote копии в Timeshift с восстановлением его metadata: не входит
   в эту версию. Добавляет зависимость от формата Timeshift и его GUI/restore.
3. Короткий shell script, выполняющий rename по порядку: недостаточен, так
   как прерывание между заменой root и HOME требует распознавания состояния.

## Границы первой версии

- Только существующий исправный Btrfs filesystem этого workstation,
  сохранённая разметка, root `@`, HOME `@home` на том же filesystem.
- SSH alias либо явно заданные host, port, user и файл ключа. Для receiver
  используется выделенный forced-command key. Пароли/ключи не копируются
  в recovery bundle, каталог NAS или журнал SSD.
- Каталог NAS должен позволять подтвердить source filesystem UUID. Локальная
  цель обязана иметь тот же UUID; поддержка нового SSD с изменившимся UUID
  и форматирование диска не входят в эту версию.
- LUKS, если есть, пользователь предварительно открывает обычными средствами.
- system восстанавливается всегда. HOME включается только явным выбором;
  если у выбранного снимка нет HOME, его нельзя подменить текущим HOME
  или HOME другого времени.
- `@nix`, `@vms`, `@cache`, `@tmp`, `@log`, `@swap`, EFI и разметка остаются
  существующими. Скрипт показывает это в плане; отсутствие требуемого mount
  из восстановленного fstab запрещает переключение.
- Нет расписания, автоматической очистки старой системы/полученных копий,
  автоматического reboot, VM restore или запуска VM.
- Проверка identity/readonly не объявляется полной проверкой содержимого.
  Успех означает подготовленный offline rollback root/HOME; фактическую
  загрузку и состояние приложений проверяет пользователь после reboot.

## Автономный файл и доставка

В репозитории логика recovery хранится в Python-модулях, shell entrypoints
остаются короткими. Новая команда `ws backup recovery-export OUTPUT`
собирает один файл `ws-restore`: Bash launcher с вложенным Python zipapp,
содержащим только необходимые модули. Bundle не содержит пользовательскую
конфигурацию, state, private keys, результаты тестов и сторонние файлы.

Launcher распаковывает только вложенный payload в собственный временный
root-owned каталог, запускает Python zipapp с сохранённым stdin/TTY,
удаляет только свой временный каталог при выходе. Полученные snapshots
и журнал на SSD не относятся к временным файлам launcher.

Live зависимости: Bash, Python 3 standard library, OpenSSH, btrfs-progs,
util-linux (`findmnt`, `lsblk`, `blkid`, `mount`, `umount`, `flock`). Nix,
fish, jq, checkout и установка Timeshift на Live не нужны. Dependency check
до сетевых/дисковых изменений показывает недостающие команды и выходит;
скрипт не запускает пакетный менеджер автоматически.

Bundle заранее сохраняют на USB вместе с публичным SSH host fingerprint
и необходимым private key, хранящимся отдельно. Он работает без доступа
к GitHub. Offline --help и --version не требуют root или подключения NAS.

## Каталог восстановления на Unraid

Receiver остаётся Bash и не требует Python/jq на NAS. Btrfs stream protocol 1
не меняется. Probe добавляет capabilities, включая `recovery-catalog-v1`.
Новые операции forced-command: публикация метаданных Timeshift и чтение
каталога одного настроенного HOST_ID. Они не допускают произвольные пути,
shell, другие hosts, изменение readonly-флага или удаление снимков.

Для каждой успешной Timeshift copy каталог хранит schema_version, host ID,
source filesystem UUID, scope, ID, source_uuid управляемой копии,
origin_uuid Timeshift subvolume, timeshift_name и timestamp UTC.
Record связан с существующим remote subvolume: source_uuid обязан совпасть
с его received_uuid, snapshot должен быть readonly. Имя record выводится
только из проверенных scope/ID внутри отдельного root-owned metadata directory.

Публикация metadata — ограниченная команда с фиксированными token/UUID/
integer аргументами, без произвольного JSON stdin или свободного текста.
Receiver формирует JSON сам, сериализует операции существующим flock,
записывает временный файл, выполняет durable sync и публикует atomic rename
с последующим filesystem sync. Нет source/eval metadata. Совпадающая повторная
публикация идемпотентна; конфликтующие данные для того же ID дают отказ.

Чтение каталога валидирует формат, размер и identity records, проверяет
существование/UUID/readonly каждого предлагаемого snapshot. Снимок без
metadata, partial, неизвестная схема, symlink и writable snapshot нельзя
предлагать как точку восстановления. Отсутствующие remote copies исключаются
с диагностикой; повреждённые metadata не интерпретируются как данные другого
снимка. Метаданные не являются разрешением исполнять код или выбирать путь.

Группировка system/home: source_fs_uuid + timeshift_name + timestamp.
Для выбора HOME требуется однозначная подтверждённая пара этих полей.
Повторные доставки одинакового origin_uuid могут отображаться как одна
точка с явно выбранным подтверждённым экземпляром. Если в одной группе для
scope есть разные origin_uuid, группа неоднозначна: автоматического выбора
по времени доставки нет, переключение этой группы запрещено.

## Изменение Timeshift backup и совместимость

Перед batch требуется capability нового receiver; старый receiver вызывает
понятный отказ до отправки Timeshift копий. Явный legacy `send home|vms|all`
сохраняет прежний интерфейс и не становится Timeshift recovery catalog.

Перед локальной очисткой `ws backup` публикует и подтверждает metadata всех
доступных успешных Timeshift records текущего настроенного target, включая
старые records, чьи источники Timeshift уже исчезли. Локальный readonly
baseline для публикации не нужен: используются durable journal и remote
inspect. Записи, которых больше нет на NAS, не публикуются как доступные.
Отсутствие необходимых полей старого record явно диагностируется.

Завершённая передача и публикация metadata имеют отдельные состояния.
Ошибка каталога не отменяет существующий snapshot и не запускает cleanup.
Следующий запуск повторяет публикацию без повторной отправки подтверждённой
копии. Даже запуск без новых Timeshift snapshots выполняет backfill metadata.
При разрыве SSH после публикации повторная идентичная запись безопасна.

## SSH и выбор цели в Live

SSH host key проверяется штатным OpenSSH. Recovery не отключает проверку,
не принимает новый fingerprint автоматически и не перезаписывает known_hosts.
Private key/alias заранее доступны процессу recovery; при `sudo` скрипт
не угадывает identity file из root HOME, а запрашивает путь или явный config.
Адрес, user и port проверяются; subprocess argv передаётся без shell=True.
Remote command состоит только из разрешённых receiver tokens.

После получения каталога пользователь выбирает дату и scope. Recovery
показывает host ID, source UUID, выбранные IDs и физическую локальную цель:
device, filesystem UUID, модель/размер и свободное место. Наличие совпадающего
UUID не заменяет явного выбора пользователем. Несколько возможных devices,
неверный UUID, неподдерживаемый layout или mounted установленная система
дают отказ. Не монтировать диск только по имени nvme0n1p4.

Проверять mount table и активный swap: целевой filesystem не может быть
корнем выполняемой ОС, смонтирован как рабочий root/HOME в Live или обслуживать
активный swap. Собственный top-level mount recovery выполняется с subvolid=5;
скрипт размонтирует только созданный им mount. По filesystem действует один
root-owned recovery lock, held на протяжении операции.

## Получение и preflight

Получение идёт в отдельные новые root-owned каталоги на целевом Btrfs,
по одному для system/home. Receiver send остаётся full без parent: старые
локальные снимки и локальный журнал backup не требуются. Перед каждым send
повторно проверить remote inspect относительно выбранной metadata.

После receive требуется единственный ожидаемый subvolume, readonly=true и
received_uuid, равный source_uuid каталога. Не менять полученный readonly
snapshot на writable: создать отдельный writable snapshot для будущего `@`.
Незавершённый receive остаётся помеченным в журнале; повтор получает данные
в новый пустой каталог, а не поверх partial. Partials не удаляются автоматически.

До первого rename выполнить весь preflight: root/HOME layout, выбранные UUID,
доступное место, отсутствие посторонних файлов на будущих paths, fstab и
boot configuration восстановленного root. Найденные UUID/ID в config должны
соответствовать цели; неподдерживаемая конфигурация даёт отказ без переключения.
UUID NAS, readonly и exit code не подменяют проверку важных данных.

Проверить kernel/initrd, `/lib/modules` и rEFInd root flags. Если boot entries
или fstab используют старые subvolid, подготовить проверенную замену на пути
`@`/`@home` только в writable candidate; received baseline не менять.
В первой загрузке должен действовать noresume. Изменение refind_linux.conf
должно иметь ограниченный parser и резервную копию; неизвестный формат — отказ.
Существующие EFI partitions, rEFInd files и swapfile не изменяются.

Показать сохранение отдельных subvolumes и риск отсутствующих Nix store paths
после GC: восстановленный HOME может ссылаться на уже удалённые generations.
Не заявлять восстановление @nix и не запускать rebuild/chroot автоматически.

## Транзакция переключения

На верхнем уровне filesystem создаётся отдельный root-owned recovery state
directory с durable JSON journal. Журнал содержит target UUID, transaction ID,
выбранные metadata/UUID, UUID текущих и будущих subvolumes, прежний default ID,
paths полученных/candidate/сохранённых copies и завершённые фазы. SSH secrets
не записываются. JSON save использует fsync файла, atomic rename и fsync
каталога; после изменения Btrfs namespace/default выполняется filesystem sync.

Порядок фаз:

1. selected: каталог и local target подтверждены, root/HOME не менялись;
2. received: все выбранные copies получены и проверены;
3. prepared: writable candidates и boot edits готовы, preflight завершён;
4. switching: пользователь подтвердил конкретный план замены;
5. root-saved: старый `@` переименован в уникальное резервное имя;
6. root-installed: candidate переименован в `@`;
7. home-saved и home-installed, если выбран HOME;
8. boot-selected: default subvolume установлен на UUID/ID нового `@`;
9. complete: postflight и filesystem sync завершены.

Намерение записывается до каждого mutation, результат после sync. Recovery
не считает journal единственным источником истины: после SIGKILL/power loss
сверяет реальные UUID subvolumes и default ID. Нет предположения об атомарности
двух rename или всей root/HOME операции. Если найден чужой UUID/path или
необъяснимое состояние, остановиться и показать диагностику без удаления.

При ошибке до switching текущие `@`/`@home` не меняются. Во время switching
не скрывать частичное состояние и не перезагружать; показать пути сохранённой
системы и команду продолжения/отката. Автоматический rollback при неожиданном
исключении не заменяет проверяемую процедуру восстановления журнала.

## Продолжение и обратный откат

Автономный файл поддерживает `status`, `resume` и `rollback` выбранной
transaction. Вызов без аргументов при незавершённой transaction предлагает
эти действия прежде, чем разрешить новую замену.

Resume повторяет проверки filesystem, snapshots и фактических UUID,
продолжает с первой невыполненной фазы. Подтверждение switching не выводится
из истёкшего времени или отсутствия пользователя.

Rollback из Live USB сохраняет текущую восстановленную root/HOME под новыми
уникальными именами, возвращает зарегистрированные прежние `@`/`@home`
и original default subvolume. Он имеет собственные намерения/фазы журнала
и те же проверки UUID, mount и active swap. Если HOME первоначально не
откатывался, rollback его не трогает. Если после успешного restore ОС уже
запускалась, явно сообщить, что rollback HOME возвращает его прежнее состояние;
новые данные остаются в сохранённой restored HOME copy.

Никакие old/restored/received/partial subvolumes не удаляются автоматически.
После успешного restore показываются текущие/default UUID/ID, paths старой
системы и краткие проверки после ручной перезагрузки (`findmnt`, `uname`,
`ws check`). Удаление резервных copies — отдельная ручная операция.

## Файлы и ответственность

- `backup/unraid/wsbackup-receiver`: безопасный metadata publish/list,
  capability probe и связь records с реальными received snapshots.
- `lib/backup_timeshift.py`: публикация/backfill metadata, durable состояние
  публикации, запрет cleanup при её ошибке.
- `lib/recovery_catalog.py`: schema, matching и нормализованный выбор дат;
  не выбирает диски и не выполняет rename.
- `lib/recovery.py`: SSH, интерактивный сценарий, план и CLI recovery.
- `lib/recovery_transaction.py`: offline target checks, Btrfs transitions,
  durable journal, status/resume/rollback.
- `lib/recovery_bundle.py`: экспорт автономного launcher/zipapp по whitelist.
- `lib/backup.py` и completions: export dispatch, совместимость existing CLI.
- `tests/`: receiver/catalog, transaction boundaries и автономный bundle.
- `docs/runbooks/backup.md`, отдельный recovery runbook и Unraid preparation:
  установка receiver, export, Live dependencies, восстановление и откат.

## Проверка и критерии готовности

Обязательные regression: существующие backup tests, forced-command injection,
UUID mismatch, metadata corruption/conflict, старый receiver, backfill без
Timeshift source и без local baseline, ошибка metadata запрещает cleanup,
missing HOME и неоднозначная группа не заменяются другими данными.

Recovery tests выполняют реальное файловое состояние и subprocess boundary
fixtures: wrong/active filesystem и swap, failed receive, partial, wrong UUID,
проверка fstab/boot до rename, посторонние destination paths, отказ подтверждения,
system-only, system+HOME, прерывание до/после каждого mutation включая смену
default, crash window между mutation и journal save, повторный resume и rollback.
Не принимать отсутствие test marker за разрешение трогать host filesystem.

Bundle запускается из каталога без checkout, с пустыми пользовательскими
config/state, проходит --help, dependency diagnostics и сценарий с boundary
fixtures. Проверить, что в artifact нет key/config/state и что prompts не
потребляют Btrfs stream/stdin pipeline. NAS не получает новую Python dependency.

Перед объявлением восстановления готовым нужна реальная проверка в disposable
VM с Btrfs, SSH receiver, раздельными root/HOME и загрузкой после restore;
проверить interrupted switching и обратный rollback. Отдельно проверить boot
policy rEFInd на этом host только в согласованном реальном restore test.
Fake Btrfs tests не подтверждают kernel behavior, VM boot или работу Unraid.
Без подключённого NAS код и локальные проверки можно подготовить; deployment
и реальная передача не объявляются выполненными.
