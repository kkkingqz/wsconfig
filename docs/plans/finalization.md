title: ws-plan-final
section: 1
date: 2026-10-03
source: Workstation
volume: User Commands

# PLAN — BACKUP / INVENTORY / FINALIZATION

## Цель

После завершения application layer превратить workstation из «настроенной системы» в воспроизводимую и восстанавливаемую.

# 1. System inventory

Инвентарь — `ws collect` (`helpws rebuild`, раздел 0): эталон `ws baseline
capture --with-sudo` (проверки, GNOME и расширения, Flatpak, Distrobox,
ссылки, системные файлы, пакеты apt и Nix), загрузка (cmdline, fstab,
`refind_linux.conf`, Btrfs), apt (`apt-mark showmanual`, `dpkg -l`,
sources), firmware Apple из macOS, описания VM. Прежний
список команд в `~/system-state` им заменён.

Граница установки (2026-10-02): каждый пакет, поставленный вручную, есть в
`nix/hosts/apt.txt` или `nix/hosts/<host>/apt.txt`, остальное `apt-mark
showmanual` — от установщика Ubuntu (`ws check apt`, INFO). Сверено с
`/var/log/apt/history.log`: недостающие внесены, лишние удалены
(`and`, `swayidle`, `brightnessctl`, `mesa-utils`, `powertop`, `evtest`,
`waveterm`). Snap нет: `purge:snapd` и pin
(`/etc/apt/preferences.d/ws-no-snapd`), Firefox — Flatpak.

Архив хранить вне ноутбука и пересобирать после заметных изменений.

Чистка 2026-10-02 (решения пользователя): удалены VM `wsvm` и
`ubuntu-test`, контейнер `ubuntu`, Rust в `arch`, все snap вместе со snapd,
generic-ядра и старое T2 `7.2.6`, `linux-tools`, логи, остатки сборок и
настроек удалённых программ; `@root` и `@srv` слиты в `@`. Занято на `/`:
137 → 99 ГБ.

---

# 2. Внешний backup Timeshift и пользовательских данных

Локальные snapshots не защищают от потери диска. Механизм внешнего backup
реализован и перенесён в `main`: `ws backup` передаёт все завершённые
существующие снимки Timeshift на Unraid с Btrfs. `@` передаётся как `system`,
`@home` — как `home`, если он есть в снимке. Новые снимки Timeshift команда
не создаёт. SSH-адрес и рабочая конфигурация ещё не заданы; реальная передача
и восстановление с NAS пока не проверены. Инструкция — `helpws backup` и
`docs/plans/unraid-backup-preparation.md`.

После успеха всего batch остаётся последняя управляемая локальная readonly
копия для каждого scope — parent следующей инкрементальной передачи.
Исходные снимки Timeshift не удаляются. Очистка NAS выполняется вручную;
расписание внешнего backup не реализовано.

Проверить, что важные данные действительно входят в выбранные subvolumes:

```text
~/Projects
~/Games / saves
Wine HOME/prefixes
important ~/.var/app
~/.config
~/.local/bin
~/.local/share/applications
~/system-state
T2-specific config files
```

Нативная репликация передаёт subvolume целиком, включая caches/runtimes;
выборочных исключений файлов нет. Вложенные subvolumes и отдельные mounts
не входят в snapshot рекурсивно. Отсутствие `@home` в снимке означает, что
этим снимком HOME не сохранён; текущий HOME вместо него не подставляется.
Для данных вне покрытия нужен отдельный backup.

---

# 2a. Backup VM — @vms (обязательно)

Всё состояние VM — на subvolume `@vms` (`/var/lib/vms`, `helpws virt`):
диски, NVRAM, TPM, описания. Root snapshots его не содержат, `ws collect`
дисков не содержит. Без отдельного backup потеря диска или переустановка —
это потеря VM.

Реализована явная команда `ws backup send vms`: readonly snapshot всего
`@vms` → `btrfs send` → SSH → Unraid. VM должны оставаться выключенными
во время создания snapshot; состояние проверяется до и после него.
Автоматического выключения, freeze или экспорта отдельных VM нет.
Обычный `ws backup` не включает `@vms`; очистка Timeshift batch не удаляет
копии, созданные `send vms` или `send home`.

Остаётся проверить и определить:

- первый полный перенос и следующий инкрементальный;
- частоту backup и ручное хранение копий VM на обеих сторонах;
- NOCOW: у образов нет контрольных сумм Btrfs, поэтому копия проверяется
  отдельно (`qemu-img check`, загрузка VM из копии);
- restore test: получить копию в отдельный пустой Btrfs-каталог командой
  `ws backup restore-test vms ID TARGET --verify RELATIVE_FILE`, затем
  отдельно проверить загрузку VM с прежними NVRAM и TPM в изолированной
  среде. Команда не восстанавливает поверх рабочих VM и не проверяет их
  загрузку автоматически.

---

# 3. Snapshot policy

Snapshot делать перед:

- kernel/T2 changes;
- boot/rEFInd changes;
- GNOME extensions;
- power/sleep changes;
- large application infrastructure changes;
- virtualization config changes.

Не создавать snapshot перед каждым обычным Flatpak update.

Инструмент — Timeshift (`@` и `@home`; решение пользователя 2026-10-02),
`helpws rebuild`, раздел 12. Перед перечисленным — ручной снапшот с
комментарием (GUI или `sudo timeshift --create --comments "…"`);
расписание пользователь настраивает в GUI. Пары до/после для apt не
нужны (решение пользователя).

---

# 4. Restore test

Хотя бы один раз проверить реальный сценарий:

1. создать snapshot;
2. внести безопасное тестовое изменение;
3. убедиться, что snapshot виден;
4. выполнить документированный rollback;
5. убедиться, что root возвращён корректно.

В проверенном ниже rollback HOME не восстанавливался: Restore выполнен
без `@home`. Восстановление HOME нужно отдельно выбрать и проверить;
`@vms` в снимки Timeshift не входит.

Внешний backup требует отдельной проверки после настройки Unraid: полный
Timeshift batch, следующий инкрементальный batch, сохранение последнего
локального parent и восстановление `system`/`home` в отдельные каталоги с
проверкой файлов. Для снимков с уже удалённой локальной копией `restore-test`
не может сравнить содержимое с исходником; проверять таким способом нужно
сохранённый parent. Процедура аварийного восстановления — `helpws backup`.

**Итог (2026-10-02): проверено.** Загрузка в снапшот из GRUB («Timeshift
snapshots»): корень — снапшот, `ws check` без FAIL. Откат: снапшот →
`/etc/ws-restore-test` → Restore без @home → rEFInd: файла нет, корень `@`,
ядро T2, хук перенёс default subvolume 256 → 285. Прежний recovery
(`system-backup-snapshot`, `/.snapshots`) убран; `@root` и `@srv` слиты в `@`
(попадают в снапшоты; решение пользователя 2026-10-02).

---

# 5. Финальный smoke-test

### Desktop

- GNOME login;
- Overview;
- Ubuntu Dock;
- Quick Settings;
- Settings;
- Nautilus;
- notifications;
- lock/unlock.

### Hardware

- keyboard/trackpad;
- F1–F12 Touch Bar;
- Fn media;
- Touch Bar autodim/off;
- Wi-Fi;
- Bluetooth;
- audio/mic;
- camera;
- Intel desktop;
- AMD offload.

### Power

- `deep/S3`;
- resume;
- lid behavior;
- battery status.

### App layer

- Flatpak file chooser;
- Flatpak screen sharing;
- dev Distrobox;
- Python/uv;
- IDE export;
- Wine app;
- Steam/Proton;
- virt-manager.

Optional features проверяются только если были реально включены:

- Touch ID;
- t2fanrd;
- hibernate;
- suspend-then-hibernate.

---

# 6. Maintenance routine

### Ubuntu

```bash
sudo apt update
sudo apt full-upgrade
```

После T2 kernel update отдельно проверить:

- boot;
- graphics;
- audio;
- Touch Bar;
- suspend/resume.

### Flatpak

```bash
flatpak update --user
flatpak uninstall --user --unused
```

### Distrobox / Podman

```bash
distrobox-upgrade --all
podman images
podman ps -a
```

Не запускать destructive prune автоматически без просмотра данных.

---

# DONE WHEN

Система считается завершённой как workstation, когда:

- весь используемый software имеет понятный installation boundary;
- host inventory сохранён;
- внешняя передача Timeshift и восстановление system/HOME проверены,
  покрытие пользовательских данных известно;
- backup `@vms` определён и восстановление VM из него проверено;
- Btrfs rollback документирован и проверен;
- final smoke-test проходит;
- восстановление не зависит от памяти о старых чатах.
