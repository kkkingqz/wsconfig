# Подготовка Unraid для backup workstation

Механизм реализован и перенесён в `main`; инструкция запуска — `helpws backup`.
Ниже — подготовка к первому реальному использованию. Команды установки на сервере
пока не выполнялись.

## Сервер (обследован 2026-10-04, только чтение)

- `tower.local` (192.168.113.113), Unraid 7.3.2, ядро 6.18.38, btrfs-progs 7.0,
  OpenSSH 10.4, sudo 1.9.17; bash 5.3, flock и findmnt есть.
- Приёмник: `/mnt/disk6/wsbackup`. disk6 — Btrfs на массиве под parity,
  UUID `66f9196f-99fd-403b-a20f-35671c5b62fe`, 5,5 ТБ, свободно 4,5 ТБ. Соседний
  `/mnt/disk6/btrfs-backup` принадлежит другому механизму и не трогается.
  Подкаталог станции: `HOST_ID=mbp16`.
- SMB/NFS shares не экспортируются; share `Backups` исключает disk6.
- `/boot` на ZFS (права сохраняются), `/root/.ssh` → `/boot/config/ssh/root`.
  `sshd_config`: `AllowUsers root`, `rc.sshd` правит в нём только адреса и порт.
- Docker работает (для Kopia).

## Выбранный транспорт

Btrfs read-only snapshot → `btrfs send` → SSH → `btrfs receive`.
Первый перенос полный, последующие используют неизменённый общий parent.
`ws backup` передаёт все завершённые существующие снимки Timeshift:
`@` как `system`, `@home` как `home`, если он присутствует. Для каждого scope
своя цепочка parent. Команда не создаёт новые снимки Timeshift и не меняет
исходные. После успеха всего batch она удаляет промежуточные управляемые
локальные readonly-копии, оставляя последнюю для каждого scope. При ошибке
передачи очистка этого запуска не выполняется.

`@vms` передаётся отдельно командой `ws backup send vms` при выключенных VM.
Явный `ws backup send home` сохраняет текущий HOME. Эти ручные копии не входят
в очистку Timeshift. Snapshot передаёт subvolume целиком, включая caches,
и не включает содержимое вложенных subvolumes и отдельных mounts;
их покрытие необходимо проверить отдельно.

Если обязательны выборочные исключения каталогов или шифрование repository
независимо от NAS, следует выбрать файловый backup (например, restic) вместо
нативной репликации. Это другой дизайн, не дополнительный режим первой версии.

## Что потребуется на сервере

1. Выбрать физический Btrfs filesystem и прямой путь `/mnt/<pool-or-disk>/...`.
   `/mnt/user/...` не использовать как аргумент receive: проверить `findmnt -T`
   и `btrfs filesystem show` для реального расположения, не полагаться на имя
   share. Зафиксировать UUID и убедиться, что filesystem не меняется при reboot.
2. Выделить каталог только для workstation backup. Система приёма должна
   проверять ожидаемый UUID и отказывать, если pool не смонтирован. Размер
   первого backup оценивается до переноса; нельзя обещать коэффициент сжатия.
3. Не давать mover и файловым клиентам менять полученные snapshots. Исключить
   receiver-каталог из записываемых SMB/NFS shares; либо предоставить отдельные
   read-only восстановительные копии. Нельзя менять ro-флаг оригиналов,
   используемых как incremental parent.
4. Установить root-owned receiving helper и его config в постоянное место.
   На Unraid проверить persistence команды и SSH authorized key после reboot;
   хранение временной копии только в RAM-файловой системе не достаточно.
5. Выделить SSH-ключ только для backup. Стандартные share users не имеют SSH;
   подключение идёт под системным пользователем `wsbackup` с ForceCommand,
   приём — через sudo, разрешающий одну команду (`backup/unraid/boot.sh`,
   `helpws backup`). Без PTY и forwarding. Helper допускает только заранее определённый host, scopes
   и snapshot IDs. Он не исполняет произвольную строку SSH_ORIGINAL_COMMAND.
6. Проверить Bash, btrfs-progs, flock и findmnt. Для начальной совместимости
   используется Btrfs stream protocol 1; новые stream options включаются
   только после проверки обеих сторон.
7. Установить актуальный receiver с разрешёнными scopes `system`, `home`,
   `vms` и capability `recovery-catalog-v1`. Установить вместе receiver,
   common и `catalog.bash` с сохранением относительной структуры. Metadata
   `.catalog` хранить на том же постоянном Btrfs, без writable SMB/NFS.
   Проверить их сохранение после reboot. Python/jq на сервере не нужны. После настройки выполнить `ws backup check --remote`, затем первый
   Timeshift batch и восстановление `system`/`home` в отдельные пустые
   Btrfs-каталоги с проверкой файлов. Создать следующий снимок Timeshift,
   повторить `ws backup` и проверить инкрементальную передачу и сохранение
   последней локальной readonly-копии для каждого scope. Отдельно проверить
   `send vms` и загрузку восстановленной VM. UUID, ro и exit code не заменяют
   проверку содержимого и загрузку VM.
8. Определить ручную retention после измерения размеров. Сохранять общий
   parent на обеих сторонах. На NAS автоматического prune и удаления partial
   нет: полученные снимки и незавершённые приёмы сохраняются. Локальная
   автоматическая очистка относится только к управляемым копиям Timeshift,
   не к исходным снимкам, ручным HOME/VM backup или данным на NAS.

## На ноутбуке

- Добавить отдельный SSH Host alias; проверить host key по доверенному каналу.
- Создать локальный config с receiver path/UUID/host ID, без пароля и ключа
  в Git. Сам private key хранится обычным способом в ~/.ssh.
- Для VM организовать окно без работающих/запускаемых VM. Механизм не
  выключает их автоматически; выбрать VM для реального restore test.
- Настроить корень управляемых readonly-копий как отдельный subvolume
  на исходном Btrfs filesystem вне @home и @vms.
  Инициализация требует sudo; никаких новых NOPASSWD-прав по умолчанию.
- Проверить `ws backup plan` и отсутствие неожиданного пропуска HOME;
  снимок без @home не сохраняет HOME. После настройки использовать
  `ws backup status` для проверки результатов batch и cleanup.
- Расписание внешнего backup не реализовано. Настраивать его отдельно
  только после успешных полного/инкрементального переносов и restore test.

## Ограничения

SSH шифрует передачу; Btrfs stream сам по себе не шифрует данные на NAS.
Read-only snapshot работающего HOME согласован на уровне filesystem, но не
гарантирует логическую согласованность каждой открытой базы приложения.
Для критичных баз нужен отдельный export/закрытие приложения перед snapshot.
Snapshot VM делается только при выключенных VM.

После очистки старой локальной копии `restore-test` не может сравнить
содержимое этого backup с исходником. Для проверки SHA-256 выбирать сохранённый
parent и явно указанные файлы. Аварийное восстановление старых копий с NAS
выполняется автономным `ws-restore` из Live USB (`helpws recovery`), без
локального backup journal. До очистки batch публикует metadata/backfill;
при ошибке публикации cleanup не происходит. Реальную приёмку выполнить
по `tests/recovery/live-checklist.md`; recovery не запускается на live root.

## Первичные источники

- [Btrfs send: read-only snapshots и общий parent](https://btrfs.readthedocs.io/en/latest/btrfs-send.html)
- [Btrfs receive: требования и завершение приёма](https://btrfs.readthedocs.io/en/latest/btrfs-receive.html)
- [Unraid: root SSH и ограничения share users](https://docs.unraid.net/unraid-os/system-administration/secure-your-server/user-management/)
