# Live USB Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Один автономный `ws-restore` получает выбранный Timeshift snapshot
с Unraid, готовит offline rollback существующего workstation и поддерживает
проверяемые status/resume/rollback без локального backup journal.

**Architecture:** Ограниченный Bash receiver публикует каталог подтверждённых
Timeshift copies. Python recovery отделяет выбор NAS records и SSH от проверки
локального target и durable Btrfs transaction. Export собирает launcher с
вложенным zipapp из whitelist модулей, без checkout/config/key/state.

**Tech Stack:** Python 3 standard library, Bash, Btrfs stream protocol 1,
OpenSSH, util-linux, существующие unittest/subprocess boundary fixtures.

**Spec:** `docs/superpowers/specs/2026-10-03-live-usb-recovery-design.md`.
Пользователь утвердил спецификацию сообщением «делай» после её предъявления.

## Global Constraints

- Только существующий исправный Btrfs filesystem, сохранённая разметка,
  root `@`, HOME `@home` на том же filesystem и исходный filesystem UUID.
- Никаких deployment, реальной передачи Unraid, переключения host root/HOME
  или автоматической перезагрузки: подключение NAS пока не настроено.
- Полученные readonly snapshots не менять; создавать writable candidates.
- `@nix`, `@vms`, `@cache`, `@tmp`, `@log`, `@swap`, EFI и разметка не откатываются.
- Нет автоматического удаления old/restored/received/partial subvolumes.
- Смена root и HOME не атомарна: journal intent → mutation → filesystem sync
  → durable result, с reconciliation по фактическим UUID после прерывания.
- Native Live dependencies: Bash, Python 3 standard library, OpenSSH,
  btrfs-progs, util-linux; на NAS Bash без Python/jq.
- SSH host verification остаётся включённой; secrets не входят в bundle/state.
- При ошибке публикации NAS metadata локальная cleanup запрещена.
- До rename нужен законченный preflight и явное подтверждение конкретного плана.
- Все команды являются argv без shell=True/eval/source пользовательских данных.
- Реальные destructive commands в tests направлять только на disposable fixture
  либо специально подготовленную VM. Не вводить runtime флаг обхода host checks.
- На исполнении использовать изолированный worktree по using-git-worktrees;
  не трогать активную ветку `wsconfig` с отдельной работой над widgets.

## Review Focus

1. На NAS прежний Timeshift name использован с другим origin UUID: не склеить
   неоднозначные system/HOME в произвольную пару (Task 1).
2. SSH alias настроен в HOME пользователя, но recovery запущен через sudo:
   запрашивать явный config/key, не угадывать root identity и не отключать
   known_hosts (Task 5).
3. Live автоматически смонтировал target или активировал его swap:
   отказ до receive/rename, только диагностировать чужие mounts (Task 3).
4. В journal сохранена фаза до rename, а процесс погиб после rename:
   recovery сверяет реальные UUID и не повторяет mutation вслепую (Task 4).
5. Старый snapshot содержит неизвестный boot/fstab формат или subvolid:
   подготовить проверяемый path-based candidate либо отказать до замены (Task 3).

## Файлы и контракты

Все recovery imports должны работать из source `lib/` и из exported zipapp.
Модули не вычисляют REPO/HOME при import и не запускают команды до вызова CLI.

- `lib/recovery_catalog.py`: строгие CatalogRecord и RecoverySelection JSON,
  группировка/ambiguity; никаких subprocess и локальных mutations.
- `backup/unraid/catalog.bash`: fixed-schema parsing, durable metadata publish,
  list; подключается только root-owned receiver, не пользовательский файл.
- `lib/recovery_platform.py`: реальная граница argv/Btrfs/mount/fsync,
  read-only target discovery и typed snapshot inspection.
- `lib/recovery_transaction.py`: transaction JSON, offline plan, preflight,
  prepare/switch/status/resume/rollback через RecoveryPlatform.
- `lib/recovery.py`: argparse, TTY prompts, SSH, selection и receive.
- `lib/recovery_bundle.py`: deterministic zipapp и автономный Bash launcher.
- `bin/ws-restore`: source launcher для разработки; экспорт не зависит от него.
- `lib/backup.py`, `lib/backup_timeshift.py`, receiver и fish completions:
  export dispatch, metadata capability/backfill, совместимость backup CLI.

`CatalogRecord`: schema_version=1, host_id, source_fs_uuid, scope=system|home,
id, source_uuid, origin_uuid, timeshift_name, timestamp. TOKEN/UUID constraints
совпадают с backup.py; timestamp — положительный integer, не bool,
timeshift_name — валидная дата формата YYYY-MM-DD_HH-MM-SS.

`RecoverySelection`: schema_version=1, host_id, source_fs_uuid, timeshift_name,
timestamp, system: CatalogRecord, home: CatalogRecord|null. Разные names,
timestamps, source filesystem UUID либо host IDs в одной selection запрещены.

`TargetInfo`: device, uuid, model, size_bytes, available_bytes, current_mounts,
active_swap, subvolumes. `SnapshotInfo`: uuid, parent_uuid, received_uuid,
subvolume_id, readonly. Tests используют те же поля с fixture platform.

### Task 1: Проверенный NAS catalog

**Files:** Create `lib/recovery_catalog.py`, `backup/unraid/catalog.bash`,
`tests/test_recovery_catalog.py`; Modify `backup/unraid/wsbackup-receiver`,
`tests/test_backup_receiver.py`.

**Interfaces:**
- `validate_record(value: dict) -> dict`: вернуть нормализованный CatalogRecord
  либо ValueError; неизвестные/недостающие поля и oversized input отклоняются.
- `build_selections(records: list[dict]) -> list[dict]`: упорядоченные по UTC
  RecoverySelection; unknown HOME не подставляется. Duplicate same-origin
  deliveries сворачиваются детерминированно по ID; different-origin group
  возвращает ValueError с именем неоднозначной группы.
- `catalog-put HOST SCOPE ID SOURCE_UUID ORIGIN_UUID SOURCE_FS_UUID TIMESTAMP NAME`:
  ровно 9 command words, success output — один CatalogRecord JSON.
- `catalog-list HOST`: JSON Lines records, capability `recovery-catalog-v1`.
  Host связан с configured HOST_ID, scopes только system/home.

- [ ] Написать catalog validation tests: valid pair; absent HOME -> home=null;
  mixed UUID/name/time/host; bool timestamp; injection; same-name changed origin;
  duplicate same-origin deterministic choice; max 10,000 records и 2,048 bytes
  на record, отказ при превышении вместо молчаливого усечения.
- [ ] Написать receiver tests: put после receive; missing/wrong UUID/writable
  snapshot; повтор identical put; conflicting put; symlink metadata dir/file;
  wrong owner/writable metadata; oversized/corrupt record; missing snapshot
  excluded with stderr; list без metadata не превращает partial в snapshot.
- [ ] Запустить `python3 -m unittest discover -s tests -p 'test_recovery_catalog.py' -v`
  и receiver suite; подтвердить RED новых тестов.
- [ ] Реализовать validation/grouping и Bash catalog под существующим flock.
  JSON files имеют один канонический порядок полей, строгое anchored parsing
  без JSON dependency на NAS. Метаданные лежат в ROOT/HOST/.catalog/SCOPE/ID.json,
  owner root, mode 0600, dirs 0700; все paths проходят safe_path/filesystem_check.
  Temporary write, sync, rename, sync; исключить временные файлы из list.
- [ ] Повторить catalog/receiver tests; подтвердить GREEN и прежнюю защиту
  forced-command от произвольного SSH_ORIGINAL_COMMAND.
- [ ] Зафиксировать только файлы Task 1.

### Task 2: Durable metadata в Timeshift batch

**Files:** Modify `lib/backup_timeshift.py`, `tests/backup_fixture.py`,
`tests/test_backup_timeshift.py`, `tests/test_backup_retention.py`;
Create `tests/test_backup_catalog.py`.

**Interfaces:**
- `catalog_record(c: dict, record: dict) -> dict`: map successful Timeshift
  journal + configured source UUID в CatalogRecord Task 1.
- `publish_catalog(c: dict, state: Path, records: list[dict]) -> dict`:
  remote inspect, put, validate acknowledgement, durable journal field
  catalog_published; результат published/missing arrays.
- run_batch требует capability до inventory/send и завершает publish/backfill
  до cleanup, включая remote-confirmed skipped/history records без local copy.

- [ ] Написать tests: old receiver refuses до snapshot/stream; backfill without
  local snapshot или Timeshift source; no new inventory still publishes old
  records; missing remote not catalogued; failure after stream doesn't clear
  local copies; disconnect after put reconciles без повторного stream;
  неверный acknowledgement и journal write failure запрещают cleanup.
- [ ] Запустить новый suite и подтвердить RED до изменения координатора.
- [ ] Реализовать publish/backfill, проверку capability и durable field.
  Нельзя доверять cached catalog_published вместо актуальной remote проверки;
  legacy send/restore-test не меняются. Результат batch включает catalog status.
- [ ] Повторить новый suite и все test_backup*.py; подтвердить GREEN,
  отдельно проверить missing-home semantics и existing pending resume.
- [ ] Зафиксировать файлы Task 2.

### Task 3: Offline target и boot preflight

**Files:** Create `lib/recovery_platform.py`, `tests/recovery_fixture.py`,
`tests/test_recovery_preflight.py`; Create initial
`lib/recovery_transaction.py` с plan/preflight/prepare.

**Interfaces:**
- `RecoveryPlatform.run(argv: list[str], input_data: bytes|None=None) -> bytes`.
- `discover_targets() -> list[dict]`, `inspect_snapshot(path: Path) -> dict`,
  `sync_filesystem(top: Path) -> None`, `save_json(path: Path, value: dict) -> None`.
- `open_target(device: str, expected_uuid: str)` context manager: verify no
  чужих mounts/swap, create own root-owned mountpoint, mount subvolid=5,
  flock, recheck identity; yield top Path и TargetInfo; unmount только own.
- `build_plan(selection: dict, target: dict, include_home: bool) -> dict`.
- `preflight(top: Path, selection: dict, received: dict, platform) -> dict`:
  никаких rename; `prepare_candidates(...) -> dict`: writable copies и boot edits.

- [ ] Написать tests: wrong UUID/device, duplicate UUID devices, installed root,
  other mount, active swap, symlink top/candidate paths, missing @/@home;
  HOME disabled не требует home record; выбранный HOME отсутствует -> отказ.
- [ ] Написать boot tests: restored root UUID matches target; fstab paths exist;
  root/HOME numeric subvolid converted to paths; unsupported fstab/boot syntax
  refuses; selected kernel has initrd/modules; noresume присутствует в каждой
  поддерживаемой Linux entry; readonly baseline untouched; preserved @nix/VM
  and EFI explicitly in plan; original boot config сохранён в candidate.
- [ ] Запустить preflight suite; подтвердить RED.
- [ ] Реализовать argv-only platform и strict supported parsers.
  JSON lsblk/findmnt и /proc/swaps — input data с проверкой типов, не команды.
  Available space выводится как оценка, не обещание успешного receive.
  Unknown absolute symlinks в candidate checks разрешаются только в целевой
  root tree, не в root Live USB. Никаких chroot/rebuild/EFI changes.
- [ ] Повторить preflight suite, подтвердить GREEN; fake platform внедряется
  через Python constructor в tests, не через обходящий host checks CLI flag.
- [ ] Зафиксировать файлы Task 3.

### Task 4: Переключение, reconciliation и обратный откат

**Files:** Modify `lib/recovery_transaction.py`, `tests/recovery_fixture.py`;
Create `tests/test_recovery_transaction.py`.

**Interfaces:**
- `create_transaction(top: Path, plan: dict, platform) -> dict`:
  уникальный transaction ID и durable state в top/ws-recovery/transactions/ID.json.
- `observe_transaction(top: Path, tx: dict, platform) -> dict`: классифицировать
  реальные UUID/paths/default, без mutation и доверия одному phase marker.
- `switch_transaction(top: Path, tx: dict, platform, confirmed: bool) -> dict`.
- `resume_transaction(top: Path, tx: dict, platform, confirmed: bool) -> dict`.
- `rollback_transaction(top: Path, tx: dict, platform, confirmed: bool) -> dict`.

- [ ] Написать tests для spec phases selected/received/prepared/switching/
  root-saved/root-installed/home-saved/home-installed/boot-selected/complete.
  Для каждого mutation прервать до вызова и после вызова до journal result;
  observe+resume должны продолжить по UUID без двойного rename.
- [ ] Написать tests: system-only leaves HOME; system+HOME matches one selection;
  default updates to new @; отказ confirmation; чужой destination/UUID;
  stale/modified journal; interrupted rollback and repeated rollback;
  rollback restores original default and retains restored copies.
- [ ] Запустить transaction suite, подтвердить RED.
- [ ] Реализовать durable intent/result с filesystem sync между mutations.
  Old names и candidates заранее записать в transaction и проверить absence.
  Нет rm-rf/subvolume-delete; исключение не запускает слепой automatic rollback.
  Every transition выполняется under target lock и после fresh mount/swap check.
- [ ] Повторить transaction suite; проверить SIGTERM/KeyboardInterrupt и
  injected process death, status сообщает частичное состояние и recovery action.
- [ ] Зафиксировать файлы Task 4.

### Task 5: SSH, получение и интерактивный Live CLI

**Files:** Create `lib/recovery.py`, `bin/ws-restore`,
`tests/test_recovery_cli.py`; Modify `tests/recovery_fixture.py`.

**Interfaces:**
- `read_catalog(ssh_options: dict, host_id: str) -> list[dict]`: bounded JSON Lines,
  Task 1 validation, capability probe, host/filesystem consistency.
- `receive_selection(top: Path, tx: dict, ssh_options: dict, platform) -> dict`:
  fresh inspect, full send/receive, expected sole snapshot/readonly/received_uuid;
  durable receive phases; restart failed stream в новый пустой каталог.
- `main(argv: list[str]|None=None) -> int`: default wizard и status/resume/rollback;
  --help/--version без root/network; прочие operations root и controlling TTY.

- [ ] Написать tests: SSH config/key explicit under sudo, known_hosts check
  unchanged, IPv4/IPv6/DNS and port validation, injection args, secret-free state;
  catalog damaged/too large, receive UUID mismatch/extra entries/writable;
  fail stream leaves current @/@home, retry doesn't overwrite partial.
- [ ] Написать CLI tests: selecting date and system/HOME, display target/model/
  UUID/IDs/old paths, full confirmation before switching, no reboot;
  unfinished transaction offers status/resume/rollback before fresh operation;
  non-TTY refuses mutations; stdout stream не используется для prompts.
- [ ] Запустить CLI suite; подтвердить RED.
- [ ] Реализовать wizard и source launcher, используя Tasks 1, 3, 4 contracts.
  Prompts через /dev/tty; subprocess send/receive error codes проверяются оба.
  Никогда не запускать remote arbitrary shell или изменять global SSH settings.
- [ ] Повторить CLI tests и transaction suite; подтвердить GREEN.
- [ ] Зафиксировать файлы Task 5.

### Task 6: Автономный export и существующий backup CLI

**Files:** Create `lib/recovery_bundle.py`, `tests/test_recovery_bundle.py`;
Modify `lib/backup.py`, `bin/ws`, `terminal/fish/completions/ws.fish`.

**Interfaces:**
- `export_bundle(output: Path) -> dict`: output, sha256, version; atomic write
  mode 0755, отказ overwrite existing file без явного export flag.
- `ws backup recovery-export OUTPUT`: работает без NAS config, sudo и network;
  parser dispatch до load_config/required remote fields.
- Bundle entrypoint — recovery.main, modules только recovery_catalog,
  recovery_platform, recovery_transaction, recovery и zipapp __main__.

- [ ] Написать tests: export without config/network; generated standalone
  --help/--version из другого каталога с пустым HOME/config/state;
  whitelist/secret scan; corrupted/truncated payload diagnostic;
  temp extraction root-owned, cleanup only own dir, stdin/TTY сохранены;
  dependency diagnostic без package manager; exported scenario использует
  fixture command boundary и проходит receive/selection/refusal flow.
- [ ] Запустить bundle tests, подтвердить RED.
- [ ] Реализовать deterministic zipapp embedded base64 в Bash launcher.
  Launcher создаёт private mktemp dir, decode и exec payload via Python;
  trap очищает только свой payload dir. Exported app не импортирует backup.py
  и не рассчитывает repository paths. Print build SHA-256 для переноса на USB.
- [ ] Повторить bundle tests, ws help/completion regression, bash/fish syntax;
  проверить весь artifact без checkout и native source launcher.
- [ ] Зафиксировать файлы Task 6.

### Task 7: Документация и интеграционная проверка

**Files:** Create `docs/runbooks/recovery.md`,
`tests/recovery/live-checklist.md`; Modify `docs/runbooks/backup.md`,
`docs/plans/unraid-backup-preparation.md`, `README.md`, `.github/workflows/check.yml`.

- [ ] Написать recovery runbook с man title ws-recovery: export на USB, Live
  dependencies и key/config, wizard, terminal statuses, resume/rollback,
  missing metadata/backfill и границы сохранённого @nix/VM/EFI.
  Не показывать новые команды как уже установленные до готовности export.
- [ ] Обновить Unraid deployment: receiver/common/catalog.bash вместе,
  capabilities, durable каталог, persistence после reboot, no Python on NAS.
- [ ] Обновить CI shell syntax inventory для нового Bash helper и modules;
  полный unittest discover уже включает recovery suites, не дублировать runs.
- [ ] Выполнить полный Python suite, реальный CI syntax script,
  `ws check repo --json` и `nix flake check --print-build-logs`; ошибки устранить
  до интеграции. Nix man включает helpws recovery.
- [ ] Подготовить disposable VM checklist: выбранная Ubuntu/Btrfs @/@home,
  штатный bootloader VM, отдельный SSH receiver; first full + incremental backup,
  old NAS-only snapshot restore без local journal, boot, interrupted switching,
  resume, rollback+boot; домашние файлы разных дат и marker root должны совпасть.
  VM filesystem и ключи отдельны от host и настоящего Unraid.
- [ ] Выполнить реальные VM checks только при наличии подготовленной VM;
  сохранить точные результаты и отдельно pending host rEFInd/NAS acceptance.
  Если VM недоступна, код не объявлять проверенным на реальном Btrfs/boot.
- [ ] Выполнить whole-change review transaction, paths, SHA/UUID semantics,
  metadata compatibility и fixture fidelity; исправить findings и повторить
  только затронутые checks. Выбор исполнителя/reviewer фиксируется при handoff.
- [ ] Зафиксировать docs/CI/results отдельным коммитом и перенести проверенную
  feature в main согласно текущему разрешению пользователя на локальную
  интеграцию. Не включать незавершённые изменения других worktrees и не push.

## Самопроверка плана

Spec coverage: NAS dates/metadata/backfill — Tasks 1–2; target/boot/readonly —
Task 3; journal и interruption/rollback — Task 4; SSH/TTY/full receive — Task 5;
single-file export — Task 6; docs/VM/host acceptance — Task 7. Review Focus
соответствует конкретным tests Tasks 1/3/4/5. Все публичные contracts используют
одни CatalogRecord/RecoverySelection/TargetInfo/SnapshotInfo shapes.

## Execution handoff

План ожидает проверки пользователем и выбора выполнения. Рекомендация —
inline/native: интерфейсы каталога, journal и receive связаны последовательно;
один implementer сможет сохранять согласованность их состояний. Если выбран
subagent-driven, использовать skill и свежий task/review context по этапам.
Независимо от метода source worktree и реальные host/NAS данные не являются
полигоном для destructive recovery tests.
