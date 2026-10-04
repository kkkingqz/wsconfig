title: ws-recovery
section: 1
date: 2026-10-04
source: Workstation
volume: User Commands

# RECOVERY — LIVE USB / UNRAID

`ws-restore` получает выбранную дату Timeshift с Unraid и возвращает её на
тот же исправный SSD. Локальный backup journal и checkout не нужны. Требуются
существующий Btrfs filesystem с прежним UUID, `@`, `@home` и сохранённые
подтомы workstation, а также штатный rEFInd. Новый диск, форматирование,
разметка, разблокировка LUKS и восстановление EFI в этот механизм не входят.

Механизм проверен автоматическими тестами с подменой границ Btrfs/SSH.
Реальная загрузка восстановленной системы и настоящий Unraid пока не проверены;
приёмочный сценарий находится в `tests/recovery/live-checklist.md`.

## Подготовка USB заранее

На рабочем компьютере, из актуального wsconfig:

```console
ws backup recovery-export /media/king/USB/ws-restore
sha256sum /media/king/USB/ws-restore
```

Export не требует настроенного backup, sudo или сети. Он выводит SHA-256 файла.
Сохранить эту сумму отдельно и проверить её перед восстановлением. Повторный
export не перезаписывает файл; явная замена — `recovery-export OUTPUT --force`.
Это один Bash-файл с Python zipapp внутри. Ключи, config, текущий HOME и журнал
не включаются. Отдельно подготовить SSH private key, `known_hosts` и SSH config
на носителе, доступном из Live USB. Ключ должен разрешать receiver `probe`,
`catalog-list`, `inspect`, `send`; общий backup forced-command key это умеет.

Пример отдельного config (подставить реальные пути и адрес):

```sshconfig
Host wsbackup-unraid
    HostName 192.0.2.10
    User root
    IdentitiesOnly yes
    UserKnownHostsFile /media/ubuntu/USB/known_hosts
    StrictHostKeyChecking yes
```

Пути в config должны существовать именно в Live-среде, включая Include,
IdentityFile и UserKnownHostsFile. Host key проверить заранее по доверенному
каналу. Указать config и key абсолютными путями: после sudo домашний каталог
пользователя не используется для угадывания ключей. Ключ должен быть доступен
OpenSSH без интерактивного ввода пароля (`BatchMode=yes`); при использовании
агента проверить доступность его сокета для запускаемого процесса.

## Запуск из Live USB

Загрузить подходящую Ubuntu Live с поддержкой Btrfs. Нужны Bash, Python 3
со стандартной библиотекой, OpenSSH client, btrfs-progs и util-linux:
`ssh`, `btrfs`, `lsblk`, `blkid`, `findmnt`, `mount`, `umount`.
Скрипт диагностирует недостающие команды, пакеты автоматически не устанавливает.

Не открывать установленный SSD в файловом менеджере: Live может смонтировать
его автоматически. Перед запуском самостоятельно размонтировать его mounts и
выключить swap на этом filesystem, если они активны. Скрипт отказывает при
чужих mounts/swap и не отключает их автоматически. USB с ключами должен быть
отдельным от восстанавливаемого filesystem.

```console
sha256sum /media/ubuntu/USB/ws-restore
sudo bash /media/ubuntu/USB/ws-restore
```

Мастер спрашивает диск, SSH host/user/port, абсолютные config/key и backup host ID
(по умолчанию `mbp16`). Можно передать параметры заранее:

```console
sudo bash /media/ubuntu/USB/ws-restore \
  --host wsbackup-unraid --config /media/ubuntu/USB/ssh_config \
  --key /media/ubuntu/USB/id_ed25519 --host-id mbp16
```

Выбрать дату из каталога NAS. SYSTEM восстанавливается всегда. HOME берётся
только из той же даты и только при ответе `YES`; при отказе текущий `@home`
сохраняется. Отсутствующий HOME другой датой не заменяется.

Для каждой выбранной копии выполняется полный Btrfs send с NAS: incremental
parent на ноутбуке не требуется. Приём идёт в отдельный каталог, результат
должен содержать ровно один readonly snapshot с ожидаемым received UUID.
Повторная отправка received snapshot сохраняет UUID исходного потока,
отличающийся от локального UUID копии на NAS. Затем создаются writable candidates;
readonly originals не меняются.

Перед переключением выводятся filesystem UUID, устройство/модель/место, дата,
IDs, UUID старых и новых подтомов и пути сохранённых копий. Чтобы заменить
систему, ввести `RESTORE restore-…` с показанным transaction ID целиком.
Любой другой ответ оставляет старую систему и подготовленные копии.

Проверяются kernel/initrd/modules и поддерживаемые fstab/rEFInd параметры.
В candidate сохраняются исходные boot config, root/HOME subvolid приводятся
к путям `@`/`@home`, старые resume параметры убираются и добавляется `noresume`.
EFI и bootloader не переустанавливаются. При неизвестном формате — отказ до
замены. `@nix`, `@vms`, `@cache`, `@tmp`, `@log`, `@swap` и EFI сохраняются.
Удалённые Nix GC поколения могут потребовать пересборки после загрузки;
диски VM остаются текущими, а не возвращаются к выбранной дате.

После успешного переключения default subvolume устанавливается на новый `@`.
Скрипт размонтирует собственный mount при выходе. Перезагрузить вручную;
автоматической перезагрузки нет. После загрузки проверить файлы, services,
Nix generation и `ws check`.

## Прерывание, status, resume, rollback

Переключение root/HOME не атомарно. До и после каждого rename/default сохраняется
журнал в top-level `ws-recovery/transactions/restore-….json` с fsync/Btrfs sync.
Реальные UUID и пути проверяются при каждом продолжении; одному phase marker
скрипт не доверяет. Журнал остаётся на целевом SSD, SSH credentials в нём нет.

Если питание/процесс прервались, снова загрузиться с Live USB. Не удалять
копии и не переименовывать подтомы вручную. При обычном запуске мастер сначала
предлагает незавершённую transaction: `status`, `resume` или `rollback`.
Можно указать действие прямо:

```console
sudo bash /media/ubuntu/USB/ws-restore status
sudo bash /media/ubuntu/USB/ws-restore resume --transaction restore-TRANSACTION_HEX
sudo bash /media/ubuntu/USB/ws-restore rollback --transaction restore-TRANSACTION_HEX
```

Вместо `restore-TRANSACTION_HEX` использовать ID из status. При нескольких дисках
добавить `--device /dev/nvme0n1p4 --uuid FILESYSTEM_UUID` с проверенными значениями.
Эти команды работают в терминале; prompts читаются через `/dev/tty`, не stdin
потока Btrfs. `--help` и `--version` доступны без sudo и сети.

Фазы: `selected` — ещё требуется NAS/приём; `received` — readonly copies
получены; `preparing`/`prepared` — создание/готовность candidates;
`switching`, `root-saved`, `root-installed`, `home-saved`, `home-installed`,
`boot-selected` — незавершённая замена; `complete` — замена закончена;
`rollback*` — возврат; `rolled-back` — прежние root/HOME/default возвращены.

`resume` после незавершённого приёма снова запросит SSH-параметры. Уже готовые
копии проверяются и используются, failed partial остаётся для диагностики,
новый приём начинается в новом пустом каталоге. После получения NAS для
продолжения switch/rollback не нужен.

`rollback` запрашивает `ROLLBACK restore-…`, возвращает старые root/HOME и
original default. Восстановленные копии, включая изменения после загрузки,
сохраняются под отдельными именами. Повторный rollback безопасен. Скрипт
не удаляет старые системы, readonly baselines, partials или журналы; место
освобождать вручную после проверки восстановления. Чужой UUID, занятый путь
или противоречивый журнал приводят к отказу без слепого overwrite/rollback.

## Если даты NAS не видны

Установить новый receiver вместе с `catalog.bash` и `btrfs-common.bash` по
`helpws backup`. Probe должен содержать `recovery-catalog-v1`. Каталог —
root-owned JSON Lines metadata в `ROOT/HOST_ID/.catalog/system|home/ID.json`;
Python/jq на NAS не требуются. Helper проверяет metadata и реальные readonly
snapshots, пропавшие copies не предлагает.

На рабочем компьютере выполнить `ws backup`: перед локальной очисткой он
публикует metadata и backfill всех подтверждённых successful records, в том
числе давно переданных копий без локального baseline. При ошибке публикации
cleanup не выполняется. Если metadata никогда не публиковались, локальный
journal уже потерян, а NAS хранит только IDs, дата не угадывается по имени:
нужна отдельная проверенная миграция metadata до восстановления мастером.
