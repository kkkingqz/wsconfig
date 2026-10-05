title: ws-backup
section: 1
date: 2026-10-03
source: Workstation
volume: User Commands

# BACKUP — BTRFS / UNRAID

Механизм подготовлен для снимков Timeshift (@ и @home) и отдельного @vms.
SSH-адрес пока не задан, реальный
сервер не проверен. Backup считается работающим только после передачи и
проверки восстановления. Подготовка NAS — также `docs/plans/unraid-backup-preparation.md`.

## Команды

```console
ws backup                             # все существующие снимки Timeshift, затем очистка ro-копий
ws backup plan                        # Timeshift workflow без сети, sudo и snapshots
ws backup plan home|vms|all            # план отдельного backup текущих live sources
ws backup status                      # конфигурация, успешные передачи, restore tests
ws backup list [--json]               # локальные копии в /var/lib/workstation-backup (sudo)
ws backup check                       # проверка полноты локальной конфигурации
ws backup check --remote              # проверка receiver по SSH
ws backup send home|vms|all
ws backup restore-test system|home|vms ID TARGET --verify RELATIVE_FILE
ws backup recovery-export OUTPUT      # один автономный ws-restore для Live USB
```

`list` показывает локальные копии всех scope: дату создания, источник
(снимок Timeshift или отдельный send), статус передачи и какая из них —
сохранённый parent для следующей инкрементальной передачи. Копия без ro-флага
помечается `NOT READ-ONLY`. `wsbackup list` — та же команда.
`ws check backup` без sudo и сети проверяет mount `@wsbackup`, его строку fstab,
alias SSH и ключ.

`plan/status` работают без адреса. `check` без `--remote` проверяет формат и
полноту config, а не фактическое состояние Btrfs. Источники проверяются root
helper перед snapshot. Без полной конфигурации backup/send/restore отказывают до
sudo и сети. `send all` сохраняет каждый scope отдельно: успешный HOME не отменяется
при отказе VM. Запись последнего успешного parent меняется только после
успешных процессов и проверки received_uuid/ro на NAS.

## Что попадает в копию

По умолчанию читаются завершённые Btrfs-снимки Timeshift из
`timeshift-btrfs/snapshots` на source filesystem. Helper создаёт собственный
read-only mount top-level subvolid=5 в закрытом временном каталоге `/run`,
проверяет UUID и размонтирует только свой mount. Порядок — от старых к новым
по metadata Timeshift; inventory фиксируется на начало запуска.

`@` передаётся как system, `@home` — как home, каждый через отдельную ro-копию.
Отсутствующий @home виден в `missing_home`; текущий HOME вместо него не
снимается. Повреждённые/неполные metadata перечислены в `excluded` с причиной.
Coverage определяется составом Timeshift: содержимое вложенных subvolumes и
отдельных mounts Btrfs send рекурсивно не переносит. @vms сюда не входит.
Команда не создаёт новые Timeshift-снимки и не меняет их ro-флаги или retention.

Повторно подтверждённый origin UUID пропускается после проверки снимка на NAS.
Writable Timeshift-снимок фиксируется при первом импорте. Изменения после
загрузки в тот же снимок из GRUB не версионируются повторным запуском backup;
для новой версии нужен новый Timeshift-снимок. Совпадение имени при другом UUID
считается новым источником.

Отдельный `send home` снимает текущий @home целиком: все пользователи /home, проекты, настройки, .var/app,
HOME Distrobox/Wine и caches. Нативный btrfs send не исключает файлы.
Вложенные subvolumes и отдельные mounts не копируются рекурсивно;
при их обнаружении snapshot отказывает до явного решения о дополнительном scope.

`send vms` снимает @vms целиком: диски, XML, NVRAM, TPM из `/var/lib/vms`. VM должны быть
выключены и не запускаться во время snapshot; активные VM или ошибка libvirt
останавливают операцию. Автоматического shutdown/freeze нет. Состояние
проверяется до и после snapshot; администратор обеспечивает окно без запуска VM.
HOME snapshot согласован на уровне filesystem; для важной открытой базы
данных закрыть приложение или сделать штатный export перед backup.

## Локальная конфигурация

Пример-шаблон: `backup/config.example.json`. Рабочий файл:
`~/.local/state/workstation/backup/config.json`, рядом с состоянием backup
(не хранить machine-local адреса и ключи в Git).

Пример после настройки NAS — заменить все значения:

```json
{
  "schema_version": 1,
  "ssh_host": "wsbackup-unraid",
  "remote_host_id": "mbp16",
  "source_fs_uuid": "00000000-0000-0000-0000-000000000000",
  "receiver_fs_uuid": "00000000-0000-0000-0000-000000000000",
  "source_snapshot_root": "/var/lib/workstation-backup",
  "remote_root": "/mnt/disk6/wsbackup"
}
```

Это пример, не готовая конфигурация. Получить настоящий source UUID:
`findmnt -nro UUID -T /`, сверить Timeshift storage, /home и /var/lib/vms.
Поддерживается Timeshift Btrfs layout @/@home на source filesystem;
отдельный @vms ожидается на том же filesystem для `send vms`.
Paths и IDs ограничены ASCII без пробелов, `..`, управляющих символов.

В `~/.ssh/config` создать alias wsbackup-unraid с HostName, User wsbackup,
IdentityFile для выделенного backup key и IdentitiesOnly yes. Проверить
серверный host key обычным SSH по доверенному fingerprint до автоматического
запуска: клиент использует BatchMode и StrictHostKeyChecking=yes.
Таймаут подключения — 10 секунд; время всей передачи не ограничивается.

Локальные ro-копии (последний parent каждого scope) хранятся в отдельной
top-level subvolume `@wsbackup`, смонтированной в `/var/lib/workstation-backup`
строкой fstab, как `@vms`. Вложенная в `@` subvolume при откате Timeshift или
Live USB уехала бы вместе со старым `@`: в восстановленной системе parents
пропали бы, следующий backup стал бы полным, а старый `@` не удалялся бы.
Timeshift показывает только свои снимки и эти копии не видит; снимок `@` не
захватывает вложенные subvolumes. Live USB restore сохраняет `@wsbackup` и
принимает её строку fstab.

Создать один раз (ROOT_UUID — `findmnt -nro UUID -T /`):

```console
sudo mount -o subvolid=5 /dev/disk/by-uuid/ROOT_UUID /mnt
sudo btrfs subvolume create /mnt/@wsbackup
sudo chmod 0700 /mnt/@wsbackup
sudo umount /mnt
sudo mkdir -p /var/lib/workstation-backup
echo 'UUID=ROOT_UUID  /var/lib/workstation-backup  btrfs  subvol=@wsbackup,noatime  0 0' | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
sudo mount /var/lib/workstation-backup
sudo bash ~/wsconfig/backup/wsbackup-source --uuid ROOT_UUID --root /var/lib/workstation-backup init
```

`init` только проверяет: каталог — отдельный mount top-level subvolume (не `@`,
не `@home`) на source filesystem. Сам он subvolume не создаёт. Те же условия
проверяет каждое действие helper и `ws check backup`.

Helper не устанавливается в /usr/local и не получает NOPASSWD.
Перед каждым требующим root действием координатор выполняет `sudo -v`
с видимым запросом в терминале. Затем helper запускается через `sudo -n`
с сохранением управляющего терминала. Пароль не читается из Btrfs stream.
Запускать backup/send/restore-test из терминала; при отсутствии авторизации операция
отказывает до запуска передачи. Скрипты запускаются
на Ubuntu host; из Flatpak сначала использовать `flatpak-spawn --host`.

## Unraid: подготовка приёмника

Обычные share users Unraid не имеют SSH, а `btrfs receive` требует root.
Поэтому подключение идёт под отдельным системным пользователем `wsbackup`, а приём
выполняется от root через sudo. sudo разрешает ему одну команду без пароля:
приёмник с его config. Ключ ноутбука не попадает в authorized keys root. Обход
ограничений ключа в OpenSSH дал бы только непривилегированного `wsbackup`. Сам
приём остаётся root: это ключ только для доверенного workstation, btrfs receive
не является sandbox для недоверенного Btrfs stream.

Unraid при загрузке восстанавливает `/etc`, `/usr/local` и пользователей из образа.
Поэтому всё ставит `backup/unraid/boot.sh` при каждой загрузке из копии на flash.
Повторный запуск ничего не меняет. Скрипт:

- создаёт `wsbackup` (оболочка bash для ForceCommand, пароль `*`, своя группа);
- ставит receiver, common и config в `/usr/local/libexec/wsbackup/` с владельцем root;
- кладёт ключи в `/etc/ssh/wsbackup_authorized_keys` и правило в `/etc/sudoers.d/wsbackup`.
  sudo сохраняет только `SSH_ORIGINAL_COMMAND`;
- добавляет `wsbackup` в существующий `AllowUsers` и блок `Match User wsbackup`:
  свой файл ключей, `ForceCommand`, без PTY, forwarding и паролей. Конфиг
  проверяется `sshd -t` до записи; listener перезапускается, открытые сессии
  остаются. `rc.sshd` правит в конфиге только адреса и порт, поэтому блок
  переживает его reload.

Если в веб-интерфейсе изменить настройки SSH (Management Access) или обновить
Unraid, конфиг может вернуться к исходному. Тогда `ws backup` сообщит об ошибке
подключения. Исправление: `bash /boot/config/wsbackup/boot.sh` или перезагрузка.
После обновления Unraid выполнить `ws backup check --remote`.

Установка, один раз, от root на Unraid:

1. Выбрать прямой путь на физическом Btrfs pool/disk, не `/mnt/user/...`.
   Проверить `findmnt -T PATH` и `btrfs filesystem show`, записать UUID. Здесь:
   `/mnt/disk6/wsbackup` (Btrfs на массиве, под parity). Каталог создаётся root
   с mode 0700. Он не должен быть доступен на запись через SMB/NFS, Docker volumes
   или mover. Unraid показывает его как share; проверить, что она не экспортируется.
   Подкаталоги `HOST_ID/system|home|vms` и `.catalog` создаёт receiver.

   ```console
   mkdir -m 0700 /mnt/disk6/wsbackup
   ```

2. Скопировать на flash с сохранением структуры:
   - `backup/unraid/boot.sh`, `backup/unraid/wsbackup-receiver`,
     `backup/unraid/catalog.bash` и `backup/btrfs-common.bash` в
     `/boot/config/wsbackup/` (`unraid/` для двух файлов receiver);
   - `receiver.conf` по `receiver.conf.example`, mode 0600;
   - `authorized_keys` с одной строкой выделенного ключа:

```text
restrict,command="sudo -n /usr/local/libexec/wsbackup/unraid/wsbackup-receiver /usr/local/libexec/wsbackup/receiver.conf" ssh-ed25519 PUBLIC_KEY workstation-backup
```

   Команда в ключе дублирует ForceCommand sshd.
3. Запустить `bash /boot/config/wsbackup/boot.sh` и добавить эту же строку в конец
   `/boot/config/go`. Проверить после перезагрузки Unraid.

После обновления файлов в репозитории скопировать их на flash заново и повторить
`boot.sh`.

Receiver поддерживает probe, inspect, receive, send, catalog-put и catalog-list для одного HOST_ID,
scope system/home/vms и безопасного snapshot ID. SSH_ORIGINAL_COMMAND не исполняется.
Перед первым Timeshift batch обновить receiver и общий Btrfs helper на Unraid:
старый receiver не поддерживает каталог восстановления. Probe должен вернуть
scopes с system/home и capability recovery-catalog-v1. Metadata сохраняются
в ROOT/HOST_ID/.catalog; Python/jq на NAS не требуются. Перед cleanup
каждый batch подтверждает metadata, включая backfill успешных старых records.
При ошибке публикации локальная очистка не выполняется.
Серверные права и directory UUID проверяются перед работой. Приём сериализован
flock. Пример ручного probe после настройки alias:

```console
ssh -T wsbackup-unraid 'probe mbp16'
ws backup check --remote
```

Free space в probe — текущая оценка filesystem. Она не гарантирует, что
будущая передача поместится. Первый snapshot полный; размер и свободное место
оцениваются оператором перед отправкой. Protocol 1 выбран для совместимости.

## Состояние, ошибки и retention

Локальные snapshots: SOURCE_ROOT/system/ID, SOURCE_ROOT/home/ID и SOURCE_ROOT/vms/ID.
На NAS: REMOTE_ROOT/HOST_ID/SCOPE/ID. Полученные snapshots остаются ro.
Изменение ro-флага общего parent нарушает условия инкрементальной передачи.

Во время receive используется `.partial-ID`. Отказ оставляет его для
диагностики и не публикует snapshot. Клиент не считает копию успешной даже
если сервер успел опубликовать её, но связь потерялась до подтверждения.
Timeshift batch сначала проверяет pending ID: совпадающий remote received_uuid/ro
позволяет записать успех без повторной передачи. Если публикации нет, создаётся
новый ID и клон сохранённой ro-копии; старый partial не заменяется и не удаляется.
Legacy `send` создаёт новый ID при повторном запуске.

`~/.local/state/workstation/backup/` содержит last-success.json, записи
snapshots, журналы operations и restore-tests. Ошибка/SIGINT/SIGTERM записывают
отказ; SIGKILL/потеря питания могут оставить статус running. Такой запуск
следует считать незавершённым до проверки, не успешным.

`ws backup` хранит отдельные inventory, records, parents, last-batch и cleanup
в `state/timeshift/`. `status` показывает coverage, pending, retained IDs и
`local_present`; история остаётся после удаления копий.

После успешной обработки всего inventory удаляются зарегистрированные старые
Timeshift ro-копии. Остаётся одна последняя подтверждённая копия system и одна
home; следующая передача использует её как parent, следующие снимки batch —
предыдущую успешно переданную копию того же scope. Перед очисткой журнал
parents сохраняется через fsync; retained проверяются локально и на NAS.
Удаление — только конкретного Btrfs subvolume с совпадающим UUID и ro=true.
Неизвестная/writable копия или UUID mismatch останавливают очистку.

При ошибке передачи очистки этого запуска нет. Ошибка удаления даёт nonzero
exit и запись cleanup.error; следующий успешный запуск, даже без новых снимков,
завершает очистку, сохраняя parents. Если remote снимок исчез, сохранившаяся
проверенная ro-копия клонируется и передаётся с новым ID, сохраняя первоначальное
содержимое. Если ro-копии уже нет, импортируется ещё существующий Timeshift origin.
Если источник исчез до создания первой копии, текущий batch отказывает без
очистки. Следующий запуск помечает такой невыполнимый импорт как `abandoned`,
сохраняет историю ошибки и обрабатывает новый inventory. Уже созданные копии
продолжают передаваться даже после удаления исходного Timeshift-снимка.

Исходные Timeshift-снимки, legacy `send home`, VM, NAS snapshots и partials
автоматически не удаляются. Расписания нет. Контролировать свободное место
локально и на NAS; remote retention настраивается отдельно и должен сохранять
общий parent. Если remote parent отсутствует,
следующая передача становится явно обозначенным full. Writable или
несовпадающий parent вызывает отказ.

## Проверка восстановления

Первый тест — в отдельный пустой каталог Btrfs вне /home и /var/lib/vms.
TARGET должен находиться на source filesystem UUID, указанном в config.
Исходный local snapshot сохраняется для сравнения контрольных сумм.
Для Timeshift нужен retained ID из status. Очищенный ID даёт отказ
`local baseline removed` до восстановления: без локального оригинала
restore-test не может подтвердить SHA-256 относительно исходника.

Пример (ID взять из status, создать TARGET отдельно):

```console
ws backup restore-test home ID /var/tmp/wsbackup-restore --verify king/wsconfig/README.md
ws backup restore-test system ID /var/tmp/wsbackup-restore --verify etc/hostname
```

Можно повторить `--verify` для нескольких реальных обычных файлов. Symlink
не принимается как verification file. Проверяются UUID удалённого snapshot,
received_uuid восстановленной копии, ro и SHA-256 выбранных файлов. При
несовпадении не появляется successful restore marker. Snapshot обратно на
ноутбуке сохраняет received_uuid первоначального источника: повторная отправка
полученного snapshot использует received_uuid, а не его собственный UUID на NAS.
Это поведение [send_subvol_begin в ядре Linux](https://raw.githubusercontent.com/torvalds/linux/master/fs/btrfs/send.c)
учтено отдельно в тестовой модели.

Для VM аналогичный файловый тест не заменяет запуск копии. После подключения
NAS отдельно проверить qemu-img, XML/NVRAM/TPM и загрузить выбранную VM в
изолированном хранилище без конфликтов с рабочей VM/сетью. В JSON отметка
vm_boot_verified остаётся false; автоматического запуска нет.

Restore-test требует локальную successful snapshot record и сохранённый local
snapshot. Восстановление старой даты, доступной только на NAS, выполняется
автономным `ws-restore` из Live USB: export, SSH preparation, выбор SYSTEM/HOME,
status/resume/rollback — `helpws recovery`. Checkout и локальный backup journal
для этого не нужны. Реальная приёмка NAS/boot ещё предстоит.

## Проверка кода

```console
python3 -m unittest discover -s ~/wsconfig/tests -v
ws check repo
```

Тесты реально выполняют shell helpers, клиент, pipeline, lock и запись файлов,
но подменяют Btrfs/sudo/SSH/libvirt границы. Они не подтверждают реальную работу
ядра Btrfs, конфигурацию Unraid или восстановление VM.

Источники: [Btrfs send](https://btrfs.readthedocs.io/en/latest/btrfs-send.html),
[Btrfs receive](https://btrfs.readthedocs.io/en/latest/btrfs-receive.html),
[Unraid user model](https://docs.unraid.net/unraid-os/system-administration/secure-your-server/user-management/).
