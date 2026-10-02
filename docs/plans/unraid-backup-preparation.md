# Подготовка Unraid для backup workstation

Это проект инструкции перед настройкой сервера. Сервер ещё не обследован;
адрес, версия Unraid, имя pool/disk и UUID будут подставлены после подключения.
Команды установки пока не выполнялись.

## Выбранный транспорт

Btrfs read-only snapshot → `btrfs send` → SSH → `btrfs receive`.
Первый перенос полный, последующие используют неизменённый общий parent.
Передавать @home и @vms отдельно. Snapshot @home включает caches и не включает
содержимое вложенных subvolumes; их необходимо обнаружить отдельно.

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
   штатный root SSH использовать с forced-command helper и ограничениями
   forwarding/PTY. Helper допускает только заранее определённый host, scopes
   и snapshot IDs. Он не исполняет произвольную строку SSH_ORIGINAL_COMMAND.
6. Проверить Bash, btrfs-progs, flock и findmnt. Для начальной совместимости
   используется Btrfs stream protocol 1; новые stream options включаются
   только после проверки обеих сторон.
7. После настройки выполнить probe, полный backup небольшой тестовой
   subvolume и восстановление в отдельный каталог. Потом — @home и @vms.
   Полученный UUID, ro и exit code проверяются; это ещё не заменяет чтение
   файлов и загрузку восстановленной VM.
8. Определить ручную retention после измерения размеров. Сохранять общий
   parent на обеих сторонах. Автоматический prune и удаление partial в первой
   версии не предусмотрены.

## На ноутбуке

- Добавить отдельный SSH Host alias; проверить host key по доверенному каналу.
- Создать локальный config с receiver path/UUID/host ID, без пароля и ключа
  в Git. Сам private key хранится обычным способом в ~/.ssh.
- Для VM организовать окно без работающих/запускаемых VM. Механизм не будет
  выключать их автоматически. Сейчас libvirt VM отсутствуют — реальный VM
  restore test выполняется, когда есть выбранная VM для проверки.
- Настроить отдельный источник read-only snapshots вне @home и @vms.
  Инициализация требует sudo; никаких новых NOPASSWD-прав по умолчанию.
- Не включать timer до первого успешного полного backup и restore test.

## Ограничения

SSH шифрует передачу; Btrfs stream сам по себе не шифрует данные на NAS.
Read-only snapshot работающего HOME согласован на уровне filesystem, но не
гарантирует логическую согласованность каждой открытой базы приложения.
Для критичных баз нужен отдельный export/закрытие приложения перед snapshot.
Snapshot VM делается только при выключенных VM.

## Первичные источники

- [Btrfs send: read-only snapshots и общий parent](https://btrfs.readthedocs.io/en/latest/btrfs-send.html)
- [Btrfs receive: требования и завершение приёма](https://btrfs.readthedocs.io/en/latest/btrfs-receive.html)
- [Unraid: root SSH и ограничения share users](https://docs.unraid.net/unraid-os/system-administration/secure-your-server/user-management/)
