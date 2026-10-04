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

## Автоматическая проверка реализации — 2026-10-04

- Проверенный результат после интеграции актуального main: `9c8334093542f28b210246b0796aab7d0ef343d7`.
- `python3 -m unittest discover -s tests -v`: **221 passed**, 1146.573 s.
- Исправлены все 8 замечаний независимого read-only review: настоящий TTY,
  foreign default до mutations, boot recheck при resume, привязка journal к
  filesystem UUID, root/initrd references, обязательный HOME fstab, EFI source,
  bind mounts в выбранном HOME. Новые regressions сначала воспроизвели ошибки.
- Recovery focused suite после исправлений: 64 passed; TTY проверяется настоящим
  controlling PTY, kernel Btrfs и SSH transport остаются test boundaries.
- Реальный syntax script CI (Bash/Python/fish): exit 0.
- `nix flake check --print-build-logs`: all checks passed, включая man ws-recovery.
- `ws check repo --json`: 151 passes, 0 failures; ожидаемые предупреждения:
  feature branch, ранее существовавший HOME path в widget checklist, старый
  локальный config workstation. Файлы recovery secrets не содержат.
- Autonomous export: whitelist/пустой HOME/help/version/corruption/receive-refusal
  tests passed. Подготовленный artifact проверен SHA-256 и `--version`.

Эти результаты подтверждают реализацию и regression checks. Пункты реальной
VM/Unraid/power-loss/boot приёмки выше по-прежнему **не выполнены**. Первая
загрузка поддерживается обычной rEFInd entry с восстановленными
vmlinuz/initrd/refind_linux.conf; альтернативные EFI/AMD/GRUB paths требуют
отдельной приёмки. Production restore на этом компьютере не запускался.
