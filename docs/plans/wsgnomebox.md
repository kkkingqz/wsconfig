title: ws-plan-wsgnomebox
section: 1
date: 2026-10-12
source: Workstation
volume: User Commands

# WSGNOMEBOX — ХОСТ WSCONFIG В КОНТЕЙНЕРЕ НА TOWER

Цель — полный хост wsconfig в Docker на tower (Unraid), вход по RDP, рядом с
`gnomebox-desktop`. Это Ubuntu 26.04 и GNOME с Nix и home-manager поверх них,
как на mbp16, только без железа. Из текущего gnomebox ничего не переносится:
ни файлы, ни домашний каталог, ни пользователь.

Состояние: план. На tower ничего не делалось.

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
имя         wsgnomebox (хост, контейнер, hostname)
где         tower, рядом с gnomebox-desktop (тот продолжает работать)
перенос     ничего из gnomebox-desktop
корень      пакеты apt — в образе; пересоздание контейнера = пересборка
            образа, состояние воспроизводится
данные      /mnt/nvm/wsgnomebox — шару создаёт пользователь
ue5         /mnt/nvm/ue5 → ~/UE5 — шару создаёт пользователь
projects    как у gnomebox → ~/Projects
RDP         порт 3390
```

Тоже приняты пользователем 2026-10-12 (были предложениями Claude):

```text
пользователь king (UID 1000), как на mbp16 и legiongo
projects    /mnt/nvmtwo/projects напрямую, без shfs /mnt/user
клавиатура  вариант 2 из 3.4: клиент пропускает клавиши, сочетания — GNOME
```

Предложения Claude (ждут ответа):

```text
данные      внутри /mnt/nvm/wsgnomebox: home, nix, grd, config
сеть        bridge по умолчанию; своя сеть и guacamole не нужны
RDP-клиент  какой — неизвестно; от него зависит правило пропуска (3.4)
```

# 3. Как это ложится на wsconfig

## 3.1 Хост `nix/hosts/wsgnomebox/`

`facts.nix`: `hostname = "wsgnomebox"`, `user = "king"`, `vm = "no"`,
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
- **Клавиатура**: xremap в контейнере не работает, варианты — 3.4.
- **Остальные владельцы** без изменений: GNOME и расширения, Flatpak,
  Distrobox (rootless podman — как в gnomebox), terminal, widgets.

## 3.3 Образ и контейнер — `container/`

```text
container/Dockerfile       FROM ubuntu:26.04; systemd; пользователь king;
                           apt-списки хоста через общий скрипт из bootstrap.sh;
                           nix из apt; маски юнитов; entrypoint
container/entrypoint       то, что в 1 (пароль, группы устройств, GBM,
                           nvidia params) + ссылка на checkout
container/wsgnomebox.xml      шаблон Unraid (генерируется из facts.nix)
bin/ws container …         build | deploy | status
```

- **Сборка без файлов на tower**: `git archive HEAD | ssh root@tower docker
  build -t local/wsgnomebox:<коммит> -f container/Dockerfile -`. Контекст —
  сам коммит, образ помечен им.
- **Постоянные каталоги** (в `/mnt/nvm/wsgnomebox`):
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

## 3.4 Клавиатура через RDP

gnome-remote-desktop передаёт ввод в mutter через D-Bus (RemoteDesktop,
`NotifyKeyboardKeycode`) — виртуальным устройством Clutter, без
`/dev/input`. xremap и любые evdev-переназначатели (keyd,
input-remapper) его не видят. GNOME-сочетания и xkb (`caps:none`,
раскладки) применяются как обычно.

Варианты (пользователь выбрал 2):

1. **Перевод на клиенте.** xremap клиента (mbp16) переводит до
   RDP-клиента, как для любого окна. Работают: Command+C/V/… в GUI,
   приватные аккорды GNOME (`Shift+Ctrl+Alt+Super+…`) — если RDP-клиент
   захватывает клавиатуру. Не работают:
   - фильтр по приложению: клиент видит одно окно RDP, поэтому в
     терминале контейнера Command+C придёт как Ctrl+C (прерывание);
   - `launch:` (`ws-input-source`, `ws-window`, `ws-nautilus-current`)
     выполняются на клиенте, а не в контейнере.
2. **Клиент пропускает как есть, сочетания — на стороне GNOME.** RDP-клиент
   добавляется к `&vm_consoles` (как консоли VM), CapsLock уходит
   приватным аккордом. В контейнере вместо xremap — пользовательские
   сочетания GNOME на эти аккорды (`ws-input-source`), раскладки и
   окна (`ws-window`). Command+C/V в GUI-приложениях не переводятся:
   у GTK нет общего переназначения; в ghostty — свои `super+c/v`.
3. **Переводчик в GNOME Shell контейнера.** Расширение ловит клавиши
   на сцене Clutter и по фокусному приложению подменяет их через
   `Clutter.VirtualInputDevice` — то же, что xremap, но внутри mutter;
   правила — из `xremap.yml`. Полная замена xremap, но своя разработка:
   задержки, повторы, залипание модификаторов.
4. **Ввод через uinput.** Другой протокол вместо RDP (Sunshine/Moonlight
   создают устройства uinput) — тогда xremap работает как на железе.
   Нужны `/dev/uinput` и узлы `/dev/input` с tower, mutter без udev
   их не подхватит; заодно NVENC-поток лучше RDP для UE5. Самый
   тяжёлый путь.

# 4. Этапы

Каждый этап, который меняет tower, — с отдельного «да» пользователя на
конкретную команду.

1. **Репозиторий** (без tower): хост `wsgnomebox`, `boot`/`hardware`
   контейнера, условия в общем коде, `container/`, `ws container`.
   Проверка — тесты, `nix flake check`, пути mbp16/legiongo не изменились,
   сборка образа локально в podman на mbp16 (без GPU).
2. **Шары `wsgnomebox` и `ue5` на nvm** — пользователь создаёт сам.
3. **tower: каталоги и `/config`** в `/mnt/nvm/wsgnomebox` (подтверждение).
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
