# Приёмка Live USB recovery на одноразовой VM

Статус 2026-10-04: **не выполнено**. Подготовленная изолированная VM с Btrfs,
rEFInd и отдельным SSH receiver отсутствует. Автотесты подменяют kernel/SSH;
они не подтверждают настоящие receive, fsync при отключении питания или boot.

1. Создать отдельные одноразовые VM: Ubuntu workstation с UEFI/rEFInd, Btrfs
   `@`, `@home`, `@nix`, `@vms`, `@cache`, `@tmp`, `@log`, `@swap`; отдельный
   Linux receiver на другом Btrfs filesystem. Не использовать host SSD,
   production Unraid, их ключи и пути. Live USB той же архитектуры.
2. Поставить receiver/common/catalog и forced-command key. Проверить
   root ownership/modes, UUID, capability и persistence после receiver reboot.
3. Создать Timeshift A с разными SYSTEM/HOME marker files, сделать первый
   `ws backup`. Изменить markers, создать B, повторить batch; проверить
   incremental parent и одну управляемую локальную ro-копию на scope.
4. Export `ws-restore` на отдельный USB, сверить SHA-256. Удалить локальный
   backup journal и источник A только в VM, оставить NAS A; изменить live
   markers ещё раз. Boot Live, target UUID остаётся прежним.
5. Проверить отказ для automount, active swap, неправильного UUID и отсутствующих
   HOME/kernel/initrd/modules. Не должен происходить switch.
6. Из NAS выбрать A, сначала без HOME, отказаться от switch. UUID старого `@`
   и HOME markers прежние. Повторить с подтверждением; boot: SYSTEM=A,
   HOME=current. Проверить rEFInd/default, noresume, mounts, Nix limitations.
7. Offline rollback; boot: исходный SYSTEM/HOME и default. Новые copies
   остались, изменения в них не потеряны.
8. Из Live восстановить A вместе с HOME. Boot: оба markers=A; @nix/@vms/EFI
   и прочие preserved copies прежние. Не должно быть автоматического reboot.
9. На отдельном повторении прервать stream. Убедиться, что partial остаётся,
   новый receive использует другое пустое место, current root/HOME прежние.
10. Для каждого root/HOME rename и set-default выключить VM до mutation и
    после неё до записи результата. Boot Live, проверить status по UUID,
    resume до complete, boot. Повторить interruptions в rollback, затем boot.
11. Подложить foreign UUID/destination и изменённый journal: отказ без overwrite.
    Проверить отсутствие удаления originals, старых systems и partials.
12. Записать VM/image/kernel/btrfs-progs/SSH версии, commands, UUID до/после,
    SHA-256 artifact, markers и boot results для каждого сценария. Удалять
    тестовые VM только после фиксации результатов.

Отдельная последующая приёмка: фактическая версия Unraid, её storage/persistence,
настоящий forced key, snapshot A после полного и incremental backup; затем
загрузка конкретного MacBook через его rEFInd. VM не подтверждает T2 hardware
или восстановление настоящего NAS. Данные host/NAS не использовать в тестах.
