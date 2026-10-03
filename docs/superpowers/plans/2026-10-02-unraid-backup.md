# Workstation → Unraid Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Подготовить проверяемый механизм полного и инкрементального backup @home и @vms на Unraid, который можно настроить позже без SSH-адреса сейчас.

**Architecture:** Read-only snapshots исходных Btrfs subvolumes передаются btrfs send/receive через SSH. Отдельный принимающий helper на Unraid ограничивает команды и место записи. Локальный координатор записывает успешные пары UUID и не считает завершённой оборванную передачу.

**Tech Stack:** Bash для shell entrypoints; Python 3 standard library для локальной конфигурации, журнала и команд; btrfs-progs, OpenSSH, flock, libvirt CLI. На Unraid helper требует только Bash и штатные btrfs/flock/findmnt; установка Python на NAS не требуется.

**Spec:** `docs/superpowers/specs/2026-10-02-wsconfig-maintenance-design.md`, раздел 3, и уточнения пользователя: Unraid с Btrfs, адрес позже, механизм подготовить сейчас.

**Execution status:** Механизм Tasks 1–4 подготовлен в `wsconfig-backup`.
Связанные source/receiver/client и документация фиксируются одним коммитом,
чтобы история не содержала несовместимые промежуточные версии протокола.
Ниже сохранён исходный checklist; детальный журнал исполнения — локальный
`.superpowers/sdd/2026-10-02-unraid-backup/progress.md`. Реальная передача,
проверка восстановления HOME/VM и deployment на Unraid ожидают адреса сервера.

## Global Constraints

- Существующие изменения ChatGPT launcher/remote не включать в коммиты backup.
- Никаких подключений к серверу, реальных backup, расписания и изменений Unraid без заданной конфигурации.
- Нативный backup сохраняет весь @home, включая caches; выборочное исключение файлов и шифрование данных на NAS не входят в btrfs send. SSH защищает передачу; режим хранения определяется на Unraid.
- Nested subvolumes не входят рекурсивно в snapshot; plan обнаруживает их и отказывается утверждать полное покрытие без явного решения.
- Snapshot VM включает весь @vms: диски, XML, NVRAM, TPM. При работающих VM backup vms прекращается до snapshot; автоматического выключения VM нет.
- При недостаточных правах предлагается обычный sudo prompt; новые NOPASSWD-права не устанавливаются автоматически.
- Никаких restore поверх /home, /var/lib/vms, libvirt binds или текущих VM; только отдельная целевая директория.
- Retention, prune и автоматическое удаление локальных/удалённых snapshots отсутствуют в первой версии.
- Перед чтением source и созданием snapshot проверяются ожидаемые UUID Btrfs и фактический subvolume, а не только имя каталога.
- Перед инкрементальной передачей проверяются локальный UUID parent и received_uuid удалённого parent; parent обязан оставаться read-only на обеих сторонах.
- Использовать send protocol 1 для совместимости, без compressed-data до проверки версий сервера.
- Размер/успех передачи не заменяет restore test. Локальные тесты не объявляются проверкой реального сервера.

## Review Focus

1. Symlink либо другой filesystem вместо configured receiver root: отказ до receive.
2. Потеря SSH после частичного receive: успешный parent не меняется, partial не становится backup.
3. Запуск VM во время создания snapshot: повторная проверка состояния отклоняет копию; требуется окно без запуска VM.
4. Nested subvolume в HOME: явно показать отсутствующее покрытие, не сообщать «весь HOME сохранён».
5. Переданный SSH argument с shell syntax: whitelist scopes и ID, никакого eval или произвольного remote command.

## Task 1: Конфигурация и план без побочных эффектов

**Files:** Create `bin/wsbackup`, `lib/backup.py`, `backup/config.example.json`, `tests/test_backup.py`; Modify `bin/ws` usage/dispatch, `terminal/fish/completions/ws.fish`.

**Interfaces:**
- `ws backup plan [home|vms|all]`: локальный JSON/text план, без sudo, snapshots и сетевых вызовов; без адреса работает.
- `ws backup status`: состояние configured/unconfigured, последние успешные передачи и restore tests.
- `load_config(path: pathlib.Path) -> dict`: JSON schema_version=1; ssh_host (SSH alias), remote_host_id, source_fs_uuid, receiver_fs_uuid, source_snapshot_root, remote_root. Не содержит паролей и private keys. Remote-поля могут отсутствовать только для plan/status.
- `build_plan(config: dict, scope: str) -> dict`: явные источники /home и /var/lib/vms, ожидаемые Btrfs subvolumes и незаданные remote поля.
- User config: `~/.config/workstation/backup.json`, state: `~/.local/state/workstation/backup/`; template не используется как рабочая конфигурация автоматически.

- [ ] Написать тесты: unconfigured plan успешен и перечисляет отсутствующие remote поля; send без них отказывает до запуска SSH/sudo; неизвестные поля/пустой host ID/небезопасные пути отклоняются; публичный CLI правильно передаёт scope.
- [ ] Запустить `python3 -m unittest discover -s tests -p 'test_backup*.py' -v`; увидеть ожидаемый отказ до реализации.
- [ ] Реализовать интерфейсы и dispatch в ws; no config sourcing, no eval.
- [ ] Повторить тесты; plan/status не должны менять target filesystem.
- [ ] Зафиксировать только перечисленные файлы явным git add/commit.

## Task 2: Исходные snapshots и согласованность VM

**Files:** Modify `lib/backup.py`; Create `backup/wsbackup-source`, `tests/test_backup_source.py`.

**Interfaces:**
- Root helper `wsbackup-source snapshot SCOPE ID` / `send SCOPE ID [PARENT_ID]` / `inspect SCOPE ID`. Scope только home/vms, ID только `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`.
- Snapshot root создаётся отдельным subvolume того же filesystem вне @home и @vms; расположение явно задаёт local config. Source helper проверяет реальные filesystem/subvolume и не позволяет выбрать произвольный root-источник.
- `create_source_snapshot(config: dict, scope: str, snapshot_id: str) -> dict`: read-only snapshot, UUID и время; частичный результат сохраняется в журнале.
- `assert_vms_stopped() -> None`: libvirt system connection; проверка ошибки связи обязательна, пустой успешный список разрешён. Проверка до и после snapshot. Managedsave state остаётся частью @vms, живые VM не замораживаются автоматически.

- [ ] Тесты: работающая VM и ошибка virsh отказывают до snapshot; wrong filesystem и nested subvolumes обнаруживаются; source parent неизменяемый; ошибки snapshot/send не скрываются; запись успешного parent не меняется при отказе.
- [ ] Подтвердить RED; использовать fake command executables только для privilege/Btrfs/libvirt границы, реальное файловое состояние и subprocess exit codes.
- [ ] Реализовать helper и координатор; один flock per backup, pipefail для stream, timeout SSH connection без ограничения времени всей передачи.
- [ ] Подтвердить GREEN полного набора тестов; system helper не устанавливать и не вызывать на реальном root в этих тестах.
- [ ] Зафиксировать изменения отдельным коммитом.

## Task 3: Ограниченный приём на Unraid и передача

**Files:** Create `backup/unraid/wsbackup-receiver`, `backup/unraid/receiver.conf.example`, `tests/test_backup_receiver.py`; Modify `lib/backup.py`.

**Interfaces:**
- Receiver читает root-owned конфигурацию с единственным receiver root, ожидаемым filesystem UUID и разрешённым host ID.
- Forced SSH command принимает только `probe HOST`, `inspect HOST SCOPE ID`, `receive HOST SCOPE ID`, `send HOST SCOPE ID`; hostname/scopes/ID проверяются по whitelist. SSH_ORIGINAL_COMMAND не исполняется.
- `probe` возвращает protocol_version=1, btrfs-progs version, target UUID и свободное место. `inspect` возвращает UUID, received_uuid и ro.
- На входящую передачу создаётся отдельный staging directory под root/HOST/SCOPE. Только успешный receive и проверка ro/received_uuid публикуют snapshot. Старые snapshots не заменяются. Partial сохраняется отдельно с меткой failed; пользователь видит путь, автоматическое recursive удаление отсутствует.
- Root path проверяется как реальный каталог непосредственно на ожидаемом Btrfs filesystem, без symlink components. Receive под глобальным lock receiver.
- `ws backup send SCOPE`: probe → проверить parent → source snapshot → btrfs send | SSH receive → inspect → записать успешную пару UUID. `all` выполняет обе scope последовательно и отдельно фиксирует успех каждой.
- Отсутствие remote parent вызывает явно отмеченный full backup; несовпадающий или writable parent — отказ, не скрытый fallback.

- [ ] Тесты: command injection, scope traversal, root symlink, wrong filesystem, concurrent receive, duplicate snapshot, broken pipe, invalid received_uuid, unchanged successful parent after failure.
- [ ] Подтвердить RED, реализовать протокол и helper, подтвердить GREEN.
- [ ] Проверить `bash -n backup/unraid/wsbackup-receiver` и весь unittest suite.
- [ ] Добавить receiver templates в repository, без автодеплоя на сервер.
- [ ] Зафиксировать изменения.

## Task 4: Проверка восстановления и рабочая инструкция

**Files:** Modify `lib/backup.py`, `tests/test_backup.py`; Create `docs/runbooks/backup.md`; Modify `docs/plans/finalization.md`, `docs/plans/roadmap.md`, `README.md`.

**Interfaces:**
- `ws backup restore-test SCOPE ID TARGET`: явно пустая отдельная директория на Btrfs; receive remote snapshot в неё, проверить UUID и выборочные контрольные суммы файлов. Никогда автоматически не подменять live пути.
- VM filesystem check не заменяет загрузку VM. Для итогового restore test: проверить диски, вернуть XML/NVRAM/TPM в изолированное VM-хранилище, запустить выбранную копию без конфликтов UUID/сети. Этот реальный тест выполняется после подключения NAS.
- `ws backup check`: локальная готовность и полнота параметров, без сети; `ws backup check --remote` отдельно запускает probe/inspect после настройки.
- Successful restore marker отдельно от successful send. Не считать восстановление проверенным, если выполнилась только передача.

- [ ] Тесты: непустая target, target внутри live home/VM storage, wrong filesystem, checksum mismatch, no server address; отсутствие success marker при любом отказе.
- [ ] Подтвердить RED, реализовать проверки/CLI, подтвердить GREEN всего suite.
- [ ] Документировать server provisioning: прямой Btrfs path, UUID, root-owned helper/config, выделенный forced-command key, отсутствие SSH у share users, сохранение настройки после reboot, ro snapshots, отсутствие mover/SMB writers для receiver root, capacity и ручную retention.
- [ ] Обновить roadmap честно: механизм подготовлен; реальная передача и HOME/VM restore ожидают подключения сервера.
- [ ] Выполнить `python3 -m unittest discover -s tests -v`, `ws check repo`, `git diff --check`; smoke-test plan/status без адреса.
- [ ] Зафиксировать документацию и интеграцию.

## Исполнение и завершение

Предлагается исполнение последовательно в текущем чате. Перед кодом пользователь
просматривает этот план и выбирает исполнение. Изолированный worktree предпочтителен:
bin/ активного checkout связаны с установленной системой. Нужно согласовать
worktree, затем следовать using-git-worktrees и executing-plans.

Механизм считается подготовленным после тестов и готовых server templates;
backup считается работающим только после передачи и реального restore test.
Без адреса Unraid завершить вторую часть критерия невозможно.
