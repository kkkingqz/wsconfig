title: ws-plan-towerws
section: 1
date: 2026-10-12
source: Workstation
volume: User Commands

# TOWERWS — ХОСТ WSCONFIG В КОНТЕЙНЕРЕ НА TOWER

Цель — полный хост wsconfig в Docker на tower (Unraid), вход по RDP, рядом с
`gnomebox-desktop`. Это Ubuntu 26.04 и GNOME с Nix и home-manager поверх них,
как на mbp16, только без железа. Из текущего gnomebox ничего не переносится:
ни файлы, ни домашний каталог, ни пользователь.

Состояние: план. На tower ничего не делалось. Имя хоста `towerws` и пути
ниже — предложение Claude, пока не подтверждённое.

# 1. Образец: gnomebox-desktop

Изучен 2026-10-12, только чтение. Сборка — `/mnt/nvmtwo/gnomebox/build/`,
шаблон — `my-gnomebox-desktop.xml`.

```text
образ       ubuntu:26.04 + ubuntu-desktop-minimal, gnome-remote-desktop,
            flatpak, podman/distrobox; apt с Recommends (1463 пакета)
init        systemd (/sbin/init), STOPSIGNAL SIGRTMIN+3, graphical.target,
            gdm + gnome-remote-desktop (системный RDP, Remote Login)
маски       udev (все юниты), udisks2, colord, tpm-udev, netplan-configure,
            NetworkManager-wait-online, snapd
GPU         --runtime=nvidia, NVIDIA_DRIVER_CAPABILITIES=all,
            /dev/dri/renderD128; RTX 3060, драйвер 610.57.04
права       --cgroupns=host, /sys/fs/cgroup rw, seccomp=unconfined,
            systempaths=unconfined, cap SYS_ADMIN SYS_RESOURCE SYS_NICE
            SYS_TTY_CONFIG MKNOD DAC_READ_SEARCH; не privileged
tmpfs       /run, /run/lock, /tmp; shm 16 ГБ; pids 16384
устройства  /dev/fuse, /dev/net/tun (rootless podman)
сеть        bridge gnomebox-net, порт 3389
данные      /home/desktop, /var/lib/gnome-remote-desktop, /config (ro,
            пароли) — на nvmtwo; /shares/projects ← /mnt/user/projects
```

Приёмы, которые нужны и здесь, — пишутся заново в репозитории:

- `entrypoint` при каждом старте:
  - ставит пароль пользователя из `/config`;
  - добавляет пользователя в группы-владельцы `/dev/dri/*` и `/dev/fuse`;
  - делает ссылку NVIDIA GBM (`libnvidia-allocator.so.1` →
    `gbm/nvidia-drm_gbm.so`);
  - отмонтирует `/proc/driver/nvidia/params`, иначе bubblewrap и rootless
    podman не смонтируют procfs.
- Oneshot перед `gnome-remote-desktop`:
  - создаёт постоянный TLS-сертификат;
  - выполняет `grdctl --system rdp set-tls-*`, `set-credentials` из `/config`
    и `enable`.
- subuid/subgid для rootless podman; в домашнем каталоге после первого
  запуска — никакого `chown -R`.

# 2. Решения

Приняты пользователем 2026-10-12:

```text
хост        полный хост wsconfig (bootstrap, системный слой, home-manager)
где         tower, рядом с gnomebox-desktop (тот продолжает работать)
перенос     ничего из gnomebox-desktop
mounts      projects (как у gnomebox) и новый ue5
шара ue5    создаёт пользователь сам
корень      пакеты apt — в образе; пересоздание контейнера = пересборка
            образа, состояние воспроизводится
```

Предложения Claude (ждут ответа):

```text
имя         хост и контейнер towerws, hostname towerws, пользователь king
            (UID 1000)
данные      /mnt/nvmtwo/towerws/{home,nix,grd,config}
порт        RDP 3390 → 3389 (3389 занят gnomebox)
сеть        bridge по умолчанию; своя сеть не нужна, guacamole не нужен
mounts      /mnt/nvmtwo/projects и /mnt/<пул>/ue5 напрямую (без shfs
            /mnt/user: быстрее для сборок UE5 и не касается HDD), в
            контейнере — ~/Projects и ~/UE5 или /shares/… как у gnomebox
```

# 3. Как это ложится на wsconfig

## 3.1 Хост `nix/hosts/towerws/`

`facts.nix`: `hostname = "towerws"`, `user = "king"`, `vm = "no"`,
`nativeSteam = "no"`, `gameMode = "no"`, `displayScale` — по размеру окна
RDP. Новые значения фактов:

- `boot = "container"`: нет загрузчика, ядра, initramfs, Timeshift. Для
  него — `system/boot/container.nix` с файлами контейнера (маски юнитов,
  oneshot RDP, GBM).
- `hardware = "container-nvidia"`: `system/hardware/container-nvidia.nix`.

`apt.txt` хоста:

- `gnome-remote-desktop`, `podman`, `uidmap`, `fuse-overlayfs`, `passt`,
  `mesa-utils`, `vulkan-tools`, `openssl`;
- без `qemu-guest-agent`, драйверов железа, `linux-*`.

## 3.2 Общий код

Всё ниже — при `boot = "container"`. mbp16 и legiongo должны собираться в
те же пути store (`nix eval --raw .#checks.x86_64-linux.home-mbp16.outPath`
и `system-mbp16` до и после).

- **`system/common.nix`**: GRUB/Timeshift (`42_ws_timeshift`, хуки) и
  `ntsync`/uinput — не для контейнера. Перенос в оба профиля загрузки (`grub`,
  `refind-grub-recovery`) меняет порядок манифеста и путь store у mbp16.
  Поэтому — условие `facts.boot != "container"` в `common.nix`: дерево у
  остальных не меняется.
- **`bootstrap.sh`**:
  - пропустить проверку Btrfs-корня и подтома `@`;
  - пропустить `@nix`, `@vms`, `@steam`, `@wsbackup` (`/nix` — bind-каталог);
  - установка пакетов apt разбивается: её же вызывает сборка образа (шаг
    `--apt-only` или отдельный скрипт, читающий те же списки);
  - `chsh fish`, группы и первый `ws switch` — в работающем контейнере.
- **`setup.sh`**: сейчас требует `boot == grub`. Для контейнера — свой
  короткий путь: `bootstrap.sh` → `ws system apply` → `ws apply` →
  `ws check`, без `ws btrfs make`, Timeshift и backup.
- **`ws check`, `ws-workstation-verify`**: проверки ядра, GRUB, Timeshift,
  suspend, udev и xremap — пропуск при `boot = "container"` (как сейчас для
  T2 по `ws fact`).
- **Клавиатура**: RDP-ввод приходит в mutter как виртуальное устройство, не
  через `/dev/input` — xremap его не видит. Раскладки и сочетания GNOME
  работают; переназначения xremap (macOS-style) — нет. Нужен факт (например
  `xremap = "no"`) или пропуск по `boot`.
- **Остальные владельцы** без изменений: GNOME и расширения, Flatpak,
  Distrobox (rootless podman — как в gnomebox), terminal, widgets.

## 3.3 Образ и контейнер — `container/`

```text
container/Dockerfile       FROM ubuntu:26.04; systemd; пользователь king;
                           apt-списки хоста через общий скрипт из bootstrap.sh;
                           nix из apt; маски юнитов; entrypoint
container/entrypoint       то, что в 1 (пароль, группы устройств, GBM,
                           nvidia params) + ссылка на checkout
container/towerws.xml      шаблон Unraid (генерируется из facts.nix)
bin/ws container …         build | deploy | status
```

- **Сборка без файлов на tower**: `git archive HEAD | ssh root@tower docker
  build -t local/towerws:<коммит> -f container/Dockerfile -`. Контекст —
  сам коммит, образ помечен им.
- **Постоянные каталоги**:
  - `/nix` (store и профили home-manager);
  - `/home/king` (checkout `~/wsconfig`, `~/.local/state/workstation`,
    Flatpak `--user`, distrobox);
  - `/var/lib/gnome-remote-desktop` (TLS);
  - `/config` (ro, пароли);
  - projects, ue5.
- **Системный слой после пересоздания**: oneshot `ws-container-apply`
  выполняет `ws system apply` без вопросов (root, `/nix` уже есть). Корень
  контейнера каждый раз приходит в состояние коммита образа плюс
  `system/` из checkout.
- **Пароли**: в `/config` на tower, не в репозитории. Файлы создаёт
  пользователь. sudo внутри — пароль из `/config`.

# 4. Этапы

Каждый этап, который меняет tower, — с отдельного «да» пользователя на
конкретную команду.

1. **Репозиторий** (без tower): хост `towerws`, `boot`/`hardware`
   контейнера, условия в общем коде, `container/`, `ws container`.
   Проверка — тесты, `nix flake check`, пути mbp16/legiongo не изменились,
   сборка образа локально в podman на mbp16 (без GPU).
2. **Шара ue5** — пользователь создаёт сам.
3. **tower: каталоги и `/config`** на nvmtwo (подтверждение).
4. **tower: сборка образа** `ws container build` (подтверждение; место
   Docker на ssdintel — 38 ГБ свободно на 2026-10-12, образ ~8–10 ГБ).
5. **tower: шаблон и запуск** (подтверждение). Проверки:
   - systemd `running`;
   - вход по RDP на 3390;
   - `nvidia-smi`, `glxinfo -B` и `vulkaninfo --summary` на NVIDIA;
   - rootless podman;
   - flatpak с bubblewrap.
6. **Внутри**: `bootstrap.sh` → `ws system apply` → `ws apply` → `ws check`;
   `ws checkpoint create setup`.
7. **Пересоздание**: удалить и создать контейнер заново → всё, кроме
   корня, на месте, `ws check` без FAIL.
8. **UE5**: сборка или запуск редактора из `~/UE5`, Vulkan на NVIDIA через
   RDP; замер памяти.

# 5. Риски

- **Память**: на tower 31 ГБ, свободно ~14 ГБ при работающих сервисах и
  gnomebox. UE5 Editor просит 32 ГБ и больше. Два рабочих стола и
  UE5 одновременно — вероятная нехватка; лимит `--memory` и swap не заданы.
- **GPU**: одна RTX 3060 (12 ГБ, 3.3 ГБ уже заняты) на два GNOME и
  UE5.
- **Место Docker** на ssdintel: 83 % занято, образ и слои — туда.
- **`/mnt/user`** (shfs): если шара не «только кэш», запись может пойти на
  HDD массива и будить диски; прямой путь пула это исключает.
- **xremap** в RDP не работает (3.2).
- **Права контейнера** (SYS_ADMIN, seccomp off) — как у gnomebox; это не
  изоляция от tower.
