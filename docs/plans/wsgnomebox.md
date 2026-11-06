title: ws-plan-wsgnomebox
section: 1
date: 2026-11-06
source: Workstation
volume: User Commands

# WSGNOMEBOX — ХОСТ WSCONFIG В КОНТЕЙНЕРЕ НА TOWER

Цель — полный хост wsconfig в Docker на tower (Unraid), вход по RDP, рядом с
`gnomebox-desktop`. Это Ubuntu 26.04 и GNOME с Nix и home-manager поверх них,
как на mbp16, только без железа. Из текущего gnomebox ничего не переносится:
ни файлы, ни домашний каталог, ни пользователь.

Состояние на 2026-11-06:

- этап 1 сделан 2026-10-12, клавиатура (3.4) тоже;
- потом пришли разделение на ядро и конфигурацию (ws help plan-v2, этап 8)
  и `ws setup` (этап 9): хост переехал в `hosts/wsgnomebox/` конфигурации,
  сборка образа — из двух репозиториев, `bootstrap.sh` и `setup.sh`
  удалены;
- 2026-11-06 `install.sh` и `ws setup` научились контейнеру (3.2),
  `[container]` — лимиту памяти `memory`;
- образ после разделения ещё не собирался (этап 1, повторная проверка);
- на tower ничего не делалось.

Проверено локально 2026-10-12, в rootless podman на mbp16 без GPU (ещё
по раскладке одного репозитория и с `bootstrap.sh`):

- образ собирается (~12 минут, 3.4 ГБ);
- в контейнере systemd в состоянии `running`, без упавших юнитов;
- gnome-remote-desktop слушает 3389, вход по RDP доходит до сессии
  экрана входа GDM;
- `bootstrap.sh` и первый `ws switch` проходят;
- после пересоздания контейнера с теми же каталогами `ws system check`,
  `ws-check-home` и `ws check apt` без FAIL.

Не проверено, ждёт tower:

- картинка в RDP: без GPU кадр чёрный, gnome-shell рисует программно, а
  кодировщику gnome-remote-desktop нужен EGL;
- rootless podman: у теста вложенный rootless, ему не хватает subuid;
- `ws check` в настоящей сессии GNOME.

EULA шрифтов Microsoft для образа принята пользователем 2026-10-12:
`container/image-setup` ставит её ответ в debconf до apt.

Изменение `host.toml` хоста или apt-списков пересобирает слой apt
(~10 минут), остальные коммиты — только слой системного дерева.

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
данные      /mnt/nvm/wsgnomebox — шару создаёт пользователь (2026-11-06:
            nvmtwo, см. ниже)
ue5         /mnt/nvm/ue5 → ~/UE5 — шару создаёт пользователь (2026-11-06:
            nvmtwo)
projects    как у gnomebox → ~/Projects
RDP         порт 3390
```

Решение пользователя 2026-11-06: диск — nvmtwo, разворачивать и тестировать
сразу на tower. Шары `wsgnomebox` и `ue5` (только nvmtwo, как `projects`) и
каталоги создал Claude по этому решению; пароль в `config/` сгенерирован на
tower.

Тоже приняты пользователем 2026-10-12 (были предложениями Claude):

```text
пользователь king (UID 1000), как на mbp16 и legiongo
projects    /mnt/nvmtwo/projects напрямую, без shfs /mnt/user
клавиатура  вариант 2 из 3.4: клиент пропускает клавиши, сочетания — GNOME
```

Предложения Claude (ждут ответа):

```text
данные      внутри /mnt/nvmtwo/wsgnomebox: home, nix, grd, config
сеть        bridge по умолчанию; своя сеть и guacamole не нужны
память      memory = "16g" в [container] (2026-11-06): у gnomebox-desktop
            20 ГБ после OOM 2026-11-04, на tower 31 ГБ; вписать в
            host.toml после ws update core (схема старого ядра его не знает)
```

Ответ пользователя 2026-10-12 (RDP-клиент): Remmina, см. 3.4.

# 3. Как это ложится на wsconfig

## 3.1 Хост `hosts/wsgnomebox/` конфигурации

Хост лежит в конфигурации (`~/wsconfig`, закрытый kkkingqz/wsbodya), код
контейнера — в ядре (`~/Projects/wsconfig`).

`host.toml`:

- `[host]`: `hostname = "wsgnomebox"`, `user = "king"`, `wsconfig =
  "wsconfig"`;
- `[platform]`: `hardware = "container-nvidia"` (ядро:
  `system/hardware/container-nvidia.nix`), `boot = "container"` — нет
  загрузчика, ядра, initramfs, Timeshift (`system/boot/container.nix`),
  `displayScale = 1`, `timezone = "Europe/Kyiv"`;
- `[layers]`: `vm`, `nativeSteam`, `gameMode` — `false`, `widgets = true`;
- `[container]` — сервер, образ, порт, каталоги, устройства и (с
  2026-11-06) необязательный `memory` для `ws container`; `~` в цели
  каталога — домашний каталог `user`. Схема — `lib/host.nix` ядра.

`hosts/wsgnomebox/apt.txt`: то, что у настоящей машины ставит установщик,
а у `ubuntu:26.04` нет (`ubuntu-minimal`, `rec:ubuntu-desktop-minimal`,
`locales`, `man-db` …), `gnome-remote-desktop`, `openssl`, `mesa-utils`,
`vulkan-tools`, `pciutils`; инструменты сборки и утилиты, которые были в
gnomebox (`build-essential`, `cmake`, `fakeroot`, `libalgorithm-*-perl`,
`python3-pytest`, `mc`, `nano`; решение пользователя 2026-10-12).
podman, distrobox, fuse-overlayfs, passt, git, gh, `xdg-terminal-exec` —
в `system/apt.txt` ядра. Btrfs, Timeshift и `steam-devices` — в
`system/apt-machine.txt`, контейнеру его не ставят (`lib/apt.bash`,
`ws check apt`, `ws baseline`).

## 3.2 Общий код

Пути store у mbp16, legiongo и wsvm (`checks.x86_64-linux.home-*` и
`system-*`) после изменений те же, что до.

- **`system/common.nix`**: uinput, ntsync, GRUB и Timeshift — только при
  `boot != "container"`; порядок файлов у остальных хостов не меняется.
- **`lib/apt.bash`**: шаг apt (PPA, `source:`, `arch:`, `rec:`, пометки
  manual, `purge:`). Его вызывают `libexec/ws-prepare` и сборка образа
  (`container/image-setup`).
- **`install.sh`** в контейнере (`systemd-detect-virt --container`):
  вместо проверки Btrfs — `/nix` должен быть каталогом сервера, `@nix`
  не создаётся; пакеты уже в образе, остальное как везде.
- **`ws setup`** при `boot = "container"` (2026-11-06):
  - хост — только по hostname, который дал `ws container run`; новый хост
    и `hostnamectl` в контейнере — отказ; на машине вне контейнера хост
    `boot = "container"` — отказ с подсказкой `ws container build/run`;
  - лицензии не спрашивает (ответ в образе), шагов btrfs, timeshift и
    backup нет;
  - вместо перезагрузки — выход из сеанса (`gnome-session-quit`): новый
    вход по RDP, автозапуск продолжает;
  - prepare → `ws apply` (дважды) → `ws check` → `ws checkpoint create
    setup`, как везде.
- **`libexec/ws-prepare`** (бывший `bootstrap.sh`) при `boot =
  "container"`: `/nix` — монтирование сервера, нет `@nix`, `@wsbackup`,
  установки apt (пакеты в образе; сравнивает `ws check apt`) и группы
  `input` (нет xremap); группы и fish уже даны образом — шаги 6 и 7
  только проверяют; первый `ws apply home` — как везде.
- **`ws system apply`**: юниты `masked` из манифеста маскирует, udev не
  трогает в контейнере. **`ws system check`**: GRUB в контейнере не
  проверяет.
- **Клавиатура**: xremap в контейнере не ставится, его часть — сочетания
  GNOME (3.4).
- **Проверки** в контейнере пропускают ядро, ntsync сервера, @nix и xremap
  (`ws-check-home`, `ws-keyboard check`, `ws-workstation-verify`); что ещё
  падает в настоящей сессии — этап 6.

## 3.3 Образ и контейнер — `container/`

```text
container/Dockerfile       стадия nix: дерево system-HOST (как ws system tree);
                           стадия ubuntu:26.04: image-setup, system-install;
                           аргументы CONFIG и CORE — где они в контексте
container/image-setup      шаг apt (lib/apt.bash), пользователь UID 1000 с
                           группами sudo, nix-users и fish, LANG, часовой пояс
container/system-install   файлы и состояния юнитов дерева в образ,
                           graphical.target
libexec/ws-container       ws container build|run|status HOST [--dry-run]
```

Файлы контейнера — в системном дереве (`system/files/container/`), их
сравнивает `ws system check`:

- `ws-container-init` (entrypoint, на каждом старте): пароль пользователя
  из `/config/password`, каркас `/nix`, домашний каталог (владелец,
  `/etc/skel` в первый раз, без `chown -R`), группы `/dev/dri` и
  `/dev/fuse`, хуки `/usr/local/lib/ws-container/init.d/`;
- `50-nvidia` (хук `container-nvidia`): ссылка GBM, снятие
  `/proc/driver/nvidia/params`;
- `ws-rdp-init` и его юнит перед `gnome-remote-desktop`: TLS в
  `/var/lib/gnome-remote-desktop`, учётные данные из `/config/rdp-user` и
  `/config/rdp-password`, `grdctl --system rdp enable`;
- `/etc/containers/storage.conf`: overlay через fuse-overlayfs;
- маски: udev, udisks2, colord, tpm-udev, NetworkManager-wait-online,
  bluetooth.

- **Сборка без файлов на tower**: `ws container build wsgnomebox` из
  чистого checkout конфигурации. Контекст — `config/` (`git archive HEAD`
  конфигурации) и `core/` (ядро, закреплённое её `flake.lock`, из
  локального store, или HEAD чистого `--core PATH`), по ssh в `docker
  build -f core/container/Dockerfile -`. Сервер в GitHub не ходит: система
  собирается с `--override-input wsconfig path:/src/core`. Образ
  `local/wsgnomebox:КОНФИГУРАЦИЯ-ЯДРО` и `:latest`, метки
  `org.opencontainers.image.revision` и `org.wsconfig.core.revision`
  (ws help plan-v2, 8.7).
- **Запуск**: `ws container run wsgnomebox` — `docker rm -f` и `docker
  run` с правами из 1, каталогами, устройствами и `memory` (`--memory` и
  такой же `--memory-swap`) из `[container]`; проверяет, что каталоги на
  сервере есть. Шаблона Unraid нет: контейнер виден в
  разделе Docker, но правится только через `ws container run`.
- **Системный слой после пересоздания**: дерево ставится в образ при
  сборке (`system-install`), так что новый контейнер стартует с ним. Это
  вместо oneshot с `ws system apply` на каждом старте: тот требовал бы
  sudo без пароля. Изменение `system/` без пересборки — `ws system apply`
  внутри до следующего образа.
- **Постоянные каталоги** (`/mnt/nvmtwo/wsgnomebox`): `home`, `nix`, `grd`,
  `config` (ro) и `~/Projects`, `~/UE5`.
- **Пароли**: в `/mnt/nvmtwo/wsgnomebox/config` (`password`, `rdp-user`,
  `rdp-password`), не в репозитории; создаёт пользователь.

## 3.4 Клавиатура через RDP

gnome-remote-desktop передаёт ввод в mutter через D-Bus (RemoteDesktop,
`NotifyKeyboardKeycode`) — виртуальным устройством Clutter, без
`/dev/input`. xremap и любые evdev-переназначатели (keyd,
input-remapper) его не видят. GNOME-сочетания и xkb (`caps:none`,
раскладки) применяются как обычно.

Варианты (пользователь выбрал 2, клиент — Remmina; сделано 2026-10-12,
`ws help keyboard`, «Через RDP: wsgnomebox»):

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
   сборка образа локально в podman на mbp16 (без GPU). Сделано 2026-10-12;
   после разделения (plan-v2, этап 8) — повторить сборку образа из двух
   репозиториев и `ws setup` внутри (контекст как у `ws container build`).
   Перед этапом 4: `ws update core` в конфигурации, `memory = "16g"` в
   `[container]`.
2. **Шары `wsgnomebox` и `ue5` на nvmtwo** — сделано 2026-11-06.
3. **tower: каталоги и `/config`** в `/mnt/nvmtwo/wsgnomebox` — сделано
   2026-11-06.
4. **tower: сборка образа** `ws container build` (подтверждение; место
   Docker на ssdintel — 38 ГБ свободно на 2026-10-12, образ ~8–10 ГБ).
5. **tower: запуск** `ws container run wsgnomebox` (подтверждение). Проверки:
   - systemd `running`;
   - вход по RDP на 3390;
   - `nvidia-smi`, `glxinfo -B` и `vulkaninfo --summary` на NVIDIA;
   - rootless podman;
   - flatpak с bubblewrap.
6. **Внутри** (терминал в RDP): `wget -qO- …/install.sh | bash -s --
   --repo https://github.com/kkkingqz/wsbodya` (ws help setup). Дальше
   `ws setup` сам: вход в GitHub, клон в `~/wsconfig`, ядро из `flake.lock`,
   выбор приложений, prepare → выход и вход по RDP → `ws apply` → выход и
   вход → `ws apply` → `ws check` → `ws checkpoint create setup`.
7. **Пересоздание**: удалить и создать контейнер заново → всё, кроме
   корня, на месте, `ws check` без FAIL.
8. **UE5**: сборка или запуск редактора из `~/UE5`, Vulkan на NVIDIA через
   RDP; замер памяти.

# 5. Риски

- **Память**: на tower 31 ГБ, свободно ~14 ГБ при работающих сервисах и
  gnomebox (2026-10-12). 2026-11-04 Firefox в gnomebox-desktop занял
  ~20 ГБ, tower ушёл в OOM; у gnomebox-desktop теперь `--memory=20g`.
  UE5 Editor просит 32 ГБ и больше. Два рабочих стола и UE5 одновременно
  — вероятная нехватка; лимит wsgnomebox — `memory` в `[container]`, swap
  на tower нет (предложен zram, не сделан).
- **GPU**: одна RTX 3060 (12 ГБ, 3.3 ГБ уже заняты) на два GNOME и
  UE5.
- **Место Docker** на ssdintel: 83 % занято (2026-10-12), образ и слои —
  туда; перед этапом 4 проверить заново.
- **`/mnt/user`** (shfs): если шара не «только кэш», запись может пойти на
  HDD массива и будить диски; прямой путь пула это исключает.
- **xremap** в RDP не работает (3.4).
- **Права контейнера** (SYS_ADMIN, seccomp off) — как у gnomebox; это не
  изоляция от tower.
