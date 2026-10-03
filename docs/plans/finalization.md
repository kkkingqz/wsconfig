title: ws-plan-final
section: 1
date: 2026-09-21
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

# 2. Что backup'ить отдельно от Btrfs snapshots

Snapshots root не являются backup.

Отдельно сохранять:

```text
~/Projects
~/Games / saves
Wine HOME/prefixes
important ~/.var/app
~/.config — выборочно
~/.local/bin
~/.local/share/applications
~/system-state
T2-specific config files
```

Не backup'ить автоматически огромные caches/runtimes, если они восстанавливаются установкой.

---

# 2a. Backup VM — @vms (обязательно)

Механизм подготовлен: `ws backup plan|send|restore-test`, `helpws backup`.
Цель выбрана — Unraid с Btrfs. SSH-адрес и рабочая конфигурация пока не заданы;
первый реальный перенос HOME/@vms и восстановление ещё не выполнены.
Native backup копирует subvolumes целиком, включая caches HOME. Нет расписания
и автоматической retention. Детали подготовки NAS — `helpws backup`.

Всё состояние VM — на subvolume `@vms` (`/var/lib/vms`, `helpws virt`):
диски, NVRAM, TPM, описания. Root snapshots его не содержат, `ws collect`
дисков не содержит. Без отдельного backup потеря диска или переустановка —
это потеря VM. Решить и проверить:

- что копируется: весь `@vms` или только выбранные VM (тестовые VM,
  пересоздаваемые с ISO, можно не хранить);
- как: read-only snapshot `@vms` (согласованная копия; VM выключены или
  `virsh domfsfreeze`/managedsave) → `btrfs send` (полный, затем
  инкрементальный от прошлого snapshot) на внешний диск с Btrfs; или
  `qemu-img convert -c` отдельных дисков плюс `virt/` из `ws collect`;
- куда и как часто; сколько копий хранить;
- NOCOW: у образов нет контрольных сумм Btrfs, поэтому копия проверяется
  отдельно (`qemu-img check`, загрузка VM из копии);
- restore test: вернуть одну VM из backup на чистый `@vms` и загрузить её с
  прежними NVRAM и TPM.

Команда (`ws vms backup` или часть общего backup) — по итогам решения;
`ws check virt` тогда предупреждает о слишком старом backup.

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

Отдельно помнить: rollback root не восстанавливает HOME, `@vms` и projects —
у них свой backup.

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
- user data backup определён;
- backup `@vms` определён и восстановление VM из него проверено;
- Btrfs rollback документирован и проверен;
- final smoke-test проходит;
- восстановление не зависит от памяти о старых чатах.
