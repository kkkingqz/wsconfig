# Timeshift Batch Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ws backup` передаёт все существующие снимки Timeshift на Unraid и после успешного batch оставляет только последний локальный read-only parent для каждого scope.

**Architecture:** Privileged helper читает Timeshift storage и создаёт управляемые read-only копии. Координатор отправляет system/home отдельно через существующий ограниченный receiver, ведёт устойчивый журнал и очищает только зарегистрированные копии после завершения inventory.

**Tech Stack:** Python 3 standard library, Bash, Btrfs send protocol 1, OpenSSH, sudo, flock; существующие unittest boundary fixtures и PTY regression.

**Spec:** `docs/superpowers/specs/2026-10-03-timeshift-batch-backup-design.md` — одобрена пользователем 2026-10-03.

**Execution status (2026-10-03):** Реализация и исправления review перенесены
в `main`. Локальные проверки выполнены; исходный checklist ниже сохранён как
история плана. Deployment на Unraid, реальные полная/инкрементальная передачи
и восстановление ещё не выполнены: конфигурация сервера не задана.
Актуальная инструкция — `docs/runbooks/backup.md`.

## Global Constraints

- Работать в существующем `/home/king/wsconfig-backup`, ветка `wsconfig-backup`; primary checkout и его сторонние изменения не трогать.
- Без hooks Timeshift, worker, нового расписания и автоматического создания Timeshift snapshots.
- Без deployment, реальных передач и удаления текущих локальных снимков: адрес Unraid не задан.
- Источники Timeshift: @ → system, @home → home. @vms остаётся отдельной явной командой.
- Одна сохранённая read-only копия для system и одна для home; раздельные parent chains.
- Отсутствие @home не заменять snapshot текущего HOME; coverage показывать явно.
- Исходные Timeshift snapshots не менять и не удалять; remote retention не входит в задачу.
- Очистка начинается только после успешной обработки всего inventory; ошибка передачи запрещает очистку этого запуска.
- Удаление только Btrfs subvolume delete проверенных зарегистрированных ro copies; без rm -rf.
- Sudo prompt отдельно от stream; сохранить controlling tty и существующий PTY regression.
- Старые journal records остаются после удаления копий; restore-test без baseline не заявляет проверку содержимого.

## Review Focus

1. Timeshift удаляет источник после inventory: если read-only copy ещё не создана — отказ без очистки; после создания отправка независима.
2. NAS опубликовал snapshot, но связь потерялась до подтверждения: повторный запуск проверяет pending ID и UUID, а не заменяет snapshot.
3. Старый snapshot исчез на NAS, локальная копия уже очищена: повторный импорт ещё существующего Timeshift источника и новая передача без замены других remote snapshots.
4. Журнал parent сохранён, но процесс погиб посередине очистки: retained parent остаётся, удаление повторяемо.
5. В backup root неизвестная/writable копия или изменённый UUID: не удалять её и явно завершить cleanup ошибкой.

## Файлы и границы ответственности

- `lib/timeshift_inventory.py`: чтение metadata и формирование упорядоченного inventory; никаких сетевых действий или удаления.
- `backup/wsbackup-timeshift`: привилегированная проверка storage, inventory, импорт и ограниченное удаление managed copies.
- `lib/backup_timeshift.py`: batch journal, pending/resume, выбор parent и cleanup.
- `lib/backup.py`: общий транспорт, конфигурация/CLI и вызов batch; не дублировать SSH/stream/sudo/state primitives.
- `backup/btrfs-common.bash`, `backup/wsbackup-source`, `backup/unraid/wsbackup-receiver`: scope system, inspect/send и UUID-guarded delete.
- `tests/test_backup_timeshift.py`, `tests/backup_fixture.py`: batch integration и модель Timeshift/Btrfs границы.
- `bin/ws`, `terminal/fish/completions/ws.fish`, `docs/runbooks/backup.md`, `README.md`, `docs/plans/roadmap.md`: интерфейс и документация.

## Task 1: Inventory и read-only импорт Timeshift

**Files:** Create `lib/timeshift_inventory.py`, `backup/wsbackup-timeshift`, `tests/test_backup_timeshift.py`; Modify `tests/backup_fixture.py`.

**Interfaces:**
- `read_inventory(root: pathlib.Path) -> list[dict]`: записи `timeshift_name`, `timestamp`, `scope`, `origin_uuid`; scope system/home, сортировка timestamp затем scope. Только завершённые snapshots с корректным info.json и subvolumes.
- Helper: `--uuid UUID --root MANAGED_ROOT inventory`; `import SCOPE COPY_ID TIMESHIFT_NAME EXPECTED_ORIGIN_UUID`. JSON output содержит Timeshift identity и UUID новой ro copy.
- Managed destination: `MANAGED_ROOT/SCOPE/COPY_ID`; token-validated COPY_ID, canonical paths, same expected filesystem.
- Для чтения top-level Timeshift storage helper создаёт собственный private mount в root-owned temporary directory под `/run`, проверяет UUID и FSROOT `/`, использует read-only mount subvolid=5 и гарантирует cleanup только своего mount. Не полагаться на временный mount Timeshift и не размонтировать чужой.
- Источник только `timeshift-btrfs/snapshots/TIMESHIFT_NAME/{@,@home}`; metadata сверяется с реально установленным Timeshift 25.12.4. Неполный/повреждённый snapshot показывается как исключённый с причиной, не считается подтверждённым.

- [ ] Написать `test_inventory_oldest_first`, `test_missing_home_reports_coverage`, `test_incomplete_metadata_not_imported`, `test_wrong_fs_or_symlink_refused`, `test_origin_uuid_changed_import_refused`, `test_timeshift_deleted_before_import_refused`, `test_import_keeps_original_writable_and_creates_ro_copy`; проверять реальные helper exits/files через boundary fixtures.
- [ ] Запустить `python3 -m unittest discover -s tests -p '*timeshift*.py' -v`; подтвердить RED по отсутствующим интерфейсам.
- [ ] Реализовать parser и helper. Для import повторно проверить origin UUID прямо перед snapshot; не менять Timeshift ro-флаг. Источник, исчезнувший после inventory, даёт ошибку.
- [ ] Повторить targeted suite и `bash -n backup/wsbackup-timeshift`; GREEN. Не выполнять helper на реальном Btrfs.
- [ ] Зафиксировать перечисленные файлы: `feat(backup): inventory and import Timeshift snapshots`.

## Task 2: Передача scope system и устойчивое подтверждение

**Files:** Modify `lib/backup.py`, `backup/btrfs-common.bash`, `backup/wsbackup-source`, `backup/unraid/wsbackup-receiver`, `tests/test_backup_receiver.py`, `tests/backup_fixture.py`; Create/Modify `lib/backup_timeshift.py`, `tests/test_backup_timeshift.py`.

**Interfaces:**
- Общие helpers разрешают system для inspect/send managed copies, receiver protocol system сохраняет прежний token whitelist.
- `send_copy(config: dict, scope: str, copy_id: str, copy_uuid: str, parent: dict | None) -> dict`: проверяет parent, использует существующие SSH/stream primitives, возвращает подтверждённый record; без нового snapshot live source.
- `confirm_pending(config: dict, record: dict) -> bool`: remote inspect того же ID. Отсутствует → False; UUID/ro mismatch → ошибка; совпадает → можно записать успех без повторного stream.
- Batch records под `state/timeshift/`: Timeshift identity, config identity, copy ID/UUID, parent, status pending/success, mode, coverage. Pending фиксируется до stream, success после inspect. Persist file и содержащую directory через fsync перед dependent action.
- Ключ origin: configured target identity + scope + origin UUID. При remote потере создаётся новый copy ID и ro copy, старая successful record остаётся историей.

- [ ] Написать `test_system_receiver_accepts_only_fixed_scope`, `test_pending_record_precedes_stream`, `test_disconnect_after_publish_resumes_without_duplicate`, `test_parent_mismatch_refuses`, `test_original_timeshift_removed_after_import_still_sends`.
- [ ] Запустить targeted suites; подтвердить RED, не подменять coordinator/receiver функции mocks.
- [ ] Реализовать `send_copy`/`confirm_pending`, system whitelist и durable records, сохранив существующие home/vms commands и sudo handling.
- [ ] Запустить весь unittest suite; GREEN, включая PTY send/restore и failure journal.
- [ ] Коммит: `feat(backup): transfer imported system snapshots with resumable confirmation`.

## Task 3: Batch всех существующих снимков и parent chains

**Files:** Modify `lib/backup_timeshift.py`, `lib/backup.py`, `tests/test_backup_timeshift.py`, `tests/backup_fixture.py`.

**Interfaces:**
- `run_batch(config: dict, state: pathlib.Path) -> dict`: под существующим operation flock фиксирует inventory один раз, обрабатывает старые→новые, возвращает transferred/skipped/missing-home и retained per scope.
- Для каждого origin remote подтверждение обязательно даже при local success record. Already confirmed не отправлять повторно. Missing remote → reimport/send нового экземпляра.
- Parent каждой новой передачи — последний подтверждённый managed local+remote экземпляр того же scope. При потере общего parent явный full; UUID/ro mismatch — отказ.
- Если новых снимков нет, batch всё равно проверяет inventory и parents, затем разрешает cleanup. Пустой inventory не создаёт снимки Timeshift; показывает отсутствие источников и не удаляет retained parent.

- [ ] Написать `test_all_existing_sent_oldest_first`, `test_next_run_only_new_snapshots_incremental`, `test_multiple_new_snapshots_chain_in_one_batch`, `test_confirmed_copies_skipped_after_local_prune`, `test_missing_remote_old_snapshot_reimported`, `test_same_name_new_origin_uuid_not_skipped`, `test_system_home_chains_independent`, `test_inventory_frozen_during_run`, `test_failure_mid_batch_preserves_progress_and_all_local_copies`.
- [ ] Подтвердить RED; проверять реальные parent arguments, delta receive и final payload, а не только поле mode.
- [ ] Реализовать `run_batch`, сохраняя отдельный success после каждого scope/snapshot; pending reconciliation перед новой отправкой.
- [ ] Полный unittest suite GREEN.
- [ ] Коммит: `feat(backup): synchronize all existing Timeshift snapshots`.

## Task 4: Очистка только управляемых старых копий

**Files:** Modify `lib/backup_timeshift.py`, `backup/wsbackup-timeshift`, `tests/test_backup_timeshift.py`, `tests/backup_fixture.py`.

**Interfaces:**
- `cleanup_copies(config: dict, state: pathlib.Path, retained: dict) -> dict`: вызывается только после успешного batch; перечитывает durable records и повторно проверяет retained local+remote UUID/ro. Нет recursive directory discovery как источника разрешения удаления.
- Helper `delete SCOPE COPY_ID EXPECTED_COPY_UUID RETAINED_ID`: требует отличающийся retained ID, проверяет оба registered destination subvolumes; удаление конкретного ro copy после UUID проверки. Удалённая уже зарегистрированная copy — idempotent результат, не ошибка.
- Cleanup result хранит deleted/skipped/error; ошибка даёт nonzero CLI exit, успешно принятые snapshots сохраняют success. Journal запись отмечает local_present=False только после удаления; snapshot success history не удаляется.

- [ ] Написать `test_success_keeps_one_copy_per_scope`, `test_failed_batch_never_calls_delete`, `test_interrupted_cleanup_resumes_without_parent_loss`, `test_unchanged_batch_finishes_cleanup`, `test_delete_refuses_retained_id`, `test_unknown_writable_or_changed_uuid_never_deleted`, `test_timeshift_and_remote_snapshots_untouched`, `test_parent_remote_disappears_before_cleanup_refuses`.
- [ ] Подтвердить RED, затем реализовать durable retained selection и UUID-guarded Btrfs deletion. Writable/unknown metadata не считать автоматически мусором.
- [ ] Полный suite GREEN, включая прерывание и повторный запуск после каждого cleanup шага.
- [ ] Коммит: `feat(backup): retain only the final verified local parents`.

## Task 5: Default CLI, восстановление и документация

**Files:** Modify `lib/backup.py`, `bin/ws`, `terminal/fish/completions/ws.fish`, `tests/test_backup.py`, `tests/test_backup_timeshift.py`, `docs/runbooks/backup.md`, `README.md`, `docs/plans/roadmap.md`.

**Interfaces:**
- `ws backup` без аргументов → Timeshift batch; `ws backup plan` показывает workflow/coverage/cleanup policy без сети и privileged действий. Явный `send vms` сохраняется; legacy home send остаётся явным и не участвует в Timeshift cleanup.
- `status` показывает batch, pending, coverage, retained IDs и local_present; старые успехи не исчезают из истории.
- `restore-test system|home ID TARGET --verify ...`: retained copy позволяет существующий checksum comparison; уже очищенная copy даёт понятный отказ «local baseline removed» без restore success marker. Не расширять автоматический live restore.
- Timeshift managed records отделены от legacy manual sends: cleanup не затрагивает legacy snapshots или vms.

- [ ] Написать `test_default_cli_runs_batch`, `test_unconfigured_plan_status_have_no_side_effects`, `test_unconfigured_backup_refuses_before_sudo_or_ssh`, `test_restore_pruned_copy_reports_missing_baseline`, `test_retained_system_restore_checks_payload`, `test_legacy_vm_command_preserved`.
- [ ] Подтвердить RED; реализовать dispatch/status/plan, completion и понятный restore baseline отказ.
- [ ] Обновить runbook/README/roadmap: default Timeshift batch, отдельные chains, cleanup после всего batch, recovery limitations, system/@home coverage и отдельный VM backup. Новая версия receiver с system нужна до запуска batch.
- [ ] Запустить фактические scripts job команды из `.github/workflows/check.yml`, полный unittest suite, `ws check repo --json`, `git diff --check`, Nix man build. Full flake assertion chatgpt, если остаётся, указать отдельно как известный base failure.
- [ ] Коммит: `docs(backup): document Timeshift batch synchronization and parent retention`.

## Handoff и итоговое ревью

Продолжить native/inline execution в этом же чате и worktree, как в предыдущем
backup плане. После выполнения задач — одно свежее whole-branch review с особым
вниманием к crash durability, import/cleanup boundaries и реальным parent UUID.
Устранить actionable findings и повторить затронутые проверки.

Готовность механизма подтверждается кодом и локальными тестами. Проверка реального
Unraid, system/HOME recovery и VM boot остаётся отложенной до подключения NAS.
