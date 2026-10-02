title: ws-backup
section: 1
date: 2026-10-02
source: Workstation
volume: User Commands

# BACKUP — BTRFS / UNRAID

Механизм подготовлен для @home и @vms. SSH-адрес пока не задан, реальный
сервер не проверен. Backup считается работающим только после передачи и
проверки восстановления. Подготовка NAS — также `docs/plans/unraid-backup-preparation.md`.

## Команды

```console
ws backup plan [home|vms|all]          # без сети, sudo и создания snapshots
ws backup status                      # конфигурация, успешные передачи, restore tests
ws backup check                       # проверка полноты локальной конфигурации
ws backup check --remote              # проверка receiver по SSH
ws backup send home|vms|all
ws backup restore-test home|vms ID TARGET --verify RELATIVE_FILE
```

`plan/status` работают без адреса. `check` без `--remote` проверяет формат и
полноту config, а не фактическое состояние Btrfs. Источники проверяются root
helper перед snapshot. Без полной конфигурации send/restore отказывают до
sudo и сети. `all` сохраняет каждый scope отдельно: успешный HOME не отменяется
при отказе VM. Запись последнего успешного parent меняется только после
успешных процессов и проверки received_uuid/ro на NAS.

## Что попадает в копию

@home целиком: все пользователи /home, проекты, настройки, .var/app,
HOME Distrobox/Wine и caches. Нативный btrfs send не исключает файлы.
Вложенные subvolumes и отдельные mounts не копируются рекурсивно;
при их обнаружении snapshot отказывает до явного решения о дополнительном scope.

@vms целиком: диски, XML, NVRAM, TPM из `/var/lib/vms`. VM должны быть
выключены и не запускаться во время snapshot; активные VM или ошибка libvirt
останавливают операцию. Автоматического shutdown/freeze нет. Состояние
проверяется до и после snapshot; администратор обеспечивает окно без запуска VM.
HOME snapshot согласован на уровне filesystem; для важной открытой базы
данных закрыть приложение или сделать штатный export перед backup.

## Локальная конфигурация

Пример-шаблон: `backup/config.example.json`. Рабочий файл:
`~/.config/workstation/backup.json` (не хранить machine-local адреса и ключи в Git).

Пример после настройки NAS — заменить все значения:

```json
{
  "schema_version": 1,
  "ssh_host": "wsbackup-unraid",
  "remote_host_id": "mbp16",
  "source_fs_uuid": "00000000-0000-0000-0000-000000000000",
  "receiver_fs_uuid": "00000000-0000-0000-0000-000000000000",
  "source_snapshot_root": "/var/lib/workstation-backup",
  "remote_root": "/mnt/backup/workstation"
}
```

Это пример, не готовая конфигурация. Получить настоящий source UUID:
`findmnt -nro UUID -T /home`, отдельно сверить /var/lib/vms. Оба scope
первой версии ожидаются на одном source filesystem, subvolumes @home/@vms.
Paths и IDs ограничены ASCII без пробелов, `..`, управляющих символов.

В `~/.ssh/config` создать alias wsbackup-unraid с HostName, User root,
IdentityFile для выделенного backup key и IdentitiesOnly yes. Проверить
серверный host key обычным SSH по доверенному fingerprint до автоматического
запуска: клиент использует BatchMode и StrictHostKeyChecking=yes.
Таймаут подключения — 10 секунд; время всей передачи не ограничивается.

После проверки UUID и свободного места подготовить отдельную local subvolume
вне @home/@vms. ROOT_UUID ниже заменить настоящим UUID:

```console
sudo bash ~/wsconfig/backup/wsbackup-source --uuid ROOT_UUID --root /var/lib/workstation-backup init
```

Helper не устанавливается в /usr/local и не получает NOPASSWD.
Каждое требующее root действие проходит обычный sudo. Скрипты запускаются
на Ubuntu host; из Flatpak сначала использовать `flatpak-spawn --host`.

## Unraid: подготовка приёмника

Обычные share users в Unraid не имеют SSH. Используется отдельный root key
с forced command. Это ключ только для доверенного workstation: btrfs receive
не является sandbox для недоверенного Btrfs stream.

1. Выбрать прямой путь на физическом Btrfs pool/disk, например
   `/mnt/backup/workstation`, не `/mnt/user/...`. Проверить `findmnt -T PATH`
   и `btrfs filesystem show`; зафиксировать настоящий UUID.
2. Создать root-owned каталог приёма с mode 0700. Он не должен быть доступен
   на запись через SMB/NFS, Docker volumes или mover. Если pool не смонтирован
   или UUID поменялся, helper должен отказать.
3. Скопировать `backup/unraid/wsbackup-receiver` и
   `backup/btrfs-common.bash`, сохранив относительную структуру. Например,
   `/boot/config/wsbackup/unraid/wsbackup-receiver` и
   `/boot/config/wsbackup/btrfs-common.bash`. Config:
   `/boot/config/wsbackup/receiver.conf`, по `receiver.conf.example`.
4. На Unraid boot flash может не поддерживать POSIX-права как Btrfs. Поэтому
   хранить исходные файлы на flash, а при boot запуском локального admin script
   устанавливать их в `/usr/local/libexec/wsbackup/` с root ownership:
   helper/common 0755/0644, config 0600, директории 0755. Перед SSH проверить
   это после reboot. Не изменять общие SSH настройки сервера автоматически.
5. Добавить выделенный public key в root authorized keys через поддерживаемую
   текущей версией Unraid настройку. Prefix строки ключа:

```text
restrict,command="/bin/bash /usr/local/libexec/wsbackup/unraid/wsbackup-receiver /usr/local/libexec/wsbackup/receiver.conf" ssh-ed25519 PUBLIC_KEY workstation-backup
```

`PUBLIC_KEY` — действительный public key. При невозможности использовать
`restrict` на выбранном OpenSSH явно отключить PTY, forwarding и user rc.
Ограничение ключа не отменяет необходимость защищать каталоги helper/config
от записи другими пользователями. Проверить persistence authorized key после
перезагрузки средствами именно установленной версии Unraid.

Receiver поддерживает только probe, inspect, receive и send для одного HOST_ID,
scope home/vms и безопасного snapshot ID. SSH_ORIGINAL_COMMAND не исполняется.
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

Локальные snapshots: SOURCE_ROOT/home/ID и SOURCE_ROOT/vms/ID.
На NAS: REMOTE_ROOT/HOST_ID/SCOPE/ID. Полученные snapshots остаются ro.
Изменение ro-флага общего parent нарушает условия инкрементальной передачи.

Во время receive используется `.partial-ID`. Отказ оставляет его для
диагностики и не публикует snapshot. Клиент не считает копию успешной даже
если сервер успел опубликовать её, но связь потерялась до подтверждения:
проверить inspect и журнал, а следующий send создаёт новый ID.

`~/.local/state/workstation/backup/` содержит last-success.json, записи
snapshots, журналы operations и restore-tests. Ошибка/SIGINT/SIGTERM записывают
отказ; SIGKILL/потеря питания могут оставить статус running. Такой запуск
следует считать незавершённым до проверки, не успешным.

Нет автоматического удаления partial, prune или расписания. Локальные
snapshots удерживают старые данные и расходуют место по мере изменений:
контролировать свободное место и назначить retention после первых измерений.
Оставлять общий parent на обеих сторонах. Если remote parent отсутствует,
следующая передача становится явно обозначенным full. Writable или
несовпадающий parent вызывает отказ.

## Проверка восстановления

Первый тест — в отдельный пустой каталог Btrfs вне /home и /var/lib/vms.
TARGET должен находиться на source filesystem UUID, указанном в config.
Исходный local snapshot сохраняется для сравнения контрольных сумм.

Пример (ID взять из status, создать TARGET отдельно):

```console
ws backup restore-test home ID /var/tmp/wsbackup-restore --verify king/wsconfig/README.md
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
snapshot. При потере SSD этот интерфейс не заменяет disaster recovery:
использовать receiver inspect/send и локальный wsbackup-restore из восстановленного
checkout для получения remote snapshot в пустую отдельную Btrfs директорию;
затем возвращать данные по rebuild/virt инструкции. Проверку такого сценария
нужно выполнить на реальном NAS до объявления системы восстановления готовой.

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
