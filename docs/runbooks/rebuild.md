title: ws-rebuild
section: 1
date: 2026-09-28
source: Workstation
volume: User Commands

# UBUNTU T2 WORKSTATION — REBUILD

# 0. До удаления рабочей системы

Собрать то, чего нет в репозитории, и унести архив с ноутбука:

```console
ws collect                      # ./ws-collect-HOST-DATE.tar.gz, спрашивает sudo
ws checkpoint create before-reinstall
```

`ws collect` (`ws collect --help`) кладёт в архив:

- `baseline/` — `ws baseline capture --with-sudo`: проверки, GNOME,
  Flatpak, Distrobox, ссылки, системные файлы, пакеты — эталон, с которым
  сравнивается новая установка (`ws baseline diff`);
- `boot/` — `/proc/cmdline`, fstab, `refind_linux.conf`, `lsblk`, `blkid`,
  `efibootmgr -v`, subvolumes Btrfs;
- `apt/` — sources, ручные и held пакеты, `dpkg -l`;
- `firmware/` — файлы `/lib/firmware/brcm` без пакета: Wi-Fi/Bluetooth
  Apple, взятые из macOS (без macOS их больше не получить);
- `state/` — `~/.local/state/workstation` (backup сочетаний, checkpoints);
- `virt/` — описания VM, сетей и пулов, NVRAM и TPM (без дисков: backup
  `@vms` — `helpws plan-final`);
- `meta/` — коммит и незакоммиченные изменения.

Отдельно: пользовательские данные, нужные Btrfs snapshots, установочный
T2-Ubuntu ISO и его SHA256. Незапушенные коммиты — `git push`.

# 1. Подготовка macOS / T2

Если macOS остаётся:

- обновить firmware Mac;
- оставить Apple EFI;
- в Recovery разрешить загрузку альтернативной ОС;
- Apple Secure Boot для Linux отключён;
- не форматировать Apple EFI;
- сохранить возможность получить Apple Wi‑Fi/Bluetooth firmware из macOS.

# 2. Установка Ubuntu

Целевая система:

```text
Ubuntu 26.04.1 LTS
GNOME 50
Wayland
amd64
MacBookPro16,1 / T2
```

Актуальный T2-Ubuntu image (t2linux). Разметка — только manual:

```text
Apple EFI     /boot/efi, не форматировать
ESP rEFInd    отдельный раздел (сейчас nvme0n1p3), не монтируется
Linux root    Btrfs
```

UUID и PARTUUID новой установки другие: их записать в
`nix/hosts/<host>/facts.nix` (`rootUuid`, `refindEspPartuuid`) до `ws system
apply` — из них собираются `refind_linux.conf`, `refind.conf` и manifest.
Старые значения — в `boot/blkid.txt` архива.

# 3. Btrfs layout

Целевая структура:

```text
@  @home  @cache  @tmp  @log
@nix       создаёт bootstrap.sh (раздел 6.0)
@vms       состояние VM в /var/lib/vms, создаёт bootstrap.sh; backup — отдельно
@steam     Steam из apt в ~/.local/share/Steam (nativeSteam = "yes"), создаёт
           bootstrap.sh; вне snapshots и backup @home
```

Root грузится с `rootflags=subvol=@`. Установщик Ubuntu 26.04 при ручной
разметке Btrfs subvolumes не создаёт вовсе: `/` оказывается в корне
файловой системы (subvolid=5; проверено в VM, фаза 6 в `helpws
history-nix`). Проверенного скрипта раскладки нет: subvolumes создают из
live-системы (`btrfs subvolume create`, перенос каталогов, строки в fstab) —
прежняя раскладка и fstab есть в `boot/` архива.

```bash
findmnt /
sudo btrfs subvolume list /
cat /etc/fstab
```

# 4. T2 repository, kernel и firmware

```text
linux-t2                  held (патч t2bce под версию ядра, helpws suspend)
apple-t2-audio-config
Apple Wi‑Fi/Bluetooth firmware
```

T2 repository (t2linux, codename `resolute`) — если installer его не
подключил. Пакеты — `nix/hosts/mbp16/apt.txt` (ставит `bootstrap.sh`).

Firmware: `get-apple-firmware.service` (`ws system apply`) берёт её из macOS
при загрузке. Без macOS — из архива:

```console
sudo cp -a firmware/* /lib/firmware/brcm/
```

Проверка:

```bash
uname -r
lsmod | grep -E 't2bce|appletb|brcmfmac|hci_bcm'
wpctl status
bluetoothctl show
```

Патченые модули t2bce — `ws-suspend t2bce-build && ws-suspend t2bce-install`,
i915 с PSR — `ws-psr build && ws-psr install` (раздел 8).

# 5. Boot / rEFInd

rEFInd — основное меню. Всё, что ему нужно, собирается из репозитория
(`facts.nix`: `kernelParams`, `refindDefaultParams`, `rootUuid`):

```text
/boot/refind_linux.conf      ставит ws system apply
EFI/BOOT/refind.conf (ESP)   копируется вручную (helpws workstation, GRAPHICS)
grub.d drop-ins              ставит ws system apply (GRUB — recovery)
```

Параметры ядра: `intel_iommu=on iommu=pt pm_async=off`. Пункт «Ubuntu»
добавляет `ws.dgpu=off modprobe.blacklist=amdgpu pcie_aspm=force
pcie_aspm.policy=powersave` (AMD без драйвера убрана с шины и выключена, её
порт запаркован, ASPM у ядра; `helpws suspend`, `helpws workstation`), ручной
«Ubuntu (AMD)» грузит `/boot/ws` без них, GRUB (recovery) — тоже. Всё из
`facts.nix`. Generic-ядро Ubuntu не ставится: ядро только T2 (`linux-t2`),
запасной путь — пункты GRUB и снапшоты Timeshift (раздел 12). Метапакеты
`linux-generic-hwe-*`, если их поставил установщик, удалить вместе с
generic-ядром (2026-10-02).

# 6. GNOME baseline

Нужен штатный Ubuntu desktop:

```text
GDM3
GNOME Shell
Mutter
Wayland
Ubuntu Dock
Nautilus
GNOME Settings
NetworkManager
BlueZ
PipeWire/WirePlumber
XWayland
xdg-desktop-portal + GNOME backend
```

Проверить:

```bash
echo "$XDG_SESSION_TYPE"
echo "$XDG_CURRENT_DESKTOP"
systemctl status gdm3 --no-pager
systemctl --user is-active pipewire
systemctl --user is-active wireplumber
```

Не ставить SwayNC/SwayOSD/swaylock/swayidle и не заменять штатные GNOME components.


# 6.0. Bootstrap и слои

После разделов 2–5 (Ubuntu, Btrfs, T2, rEFInd) и штатного GNOME вся
конфигурация ставится так (`helpws layers`):

```console
sudo apt install git
git clone https://github.com/kkkingqz/wsconfig.git ~/wsconfig
~/wsconfig/bootstrap.sh
# reboot: группы nix-users, libvirt, input, PATH из 00-nix.fish, fish как login shell
#   (logout/login не хватает, пока открыта другая сессия пользователя, например ssh)
ws system apply     # системные файлы (sudo); затем reboot, если менялись modprobe/udev/cmdline
ws apply            # расширения → tiling → клавиатура → Flatpak → Distrobox
# logout/login: новые расширения GNOME активируются только в новой сессии
ws apply            # шаг keyboard, не прошедший preflight в первый раз
ws check            # проверки всех владельцев и verify (связи между слоями)
```

`bootstrap.sh` (от пользователя, sudo вызывает сам; `--dry-run` только
показывает шаги): subvolume `@nix` и строка `/nix` в fstab → пакеты из
`nix/hosts/apt.txt` и `nix/hosts/<host>/apt.txt` (PPA fish и
nautilus-my-computer; `purge:snapd` — без snap; в списке хоста
`source:NAME` — репозиторий `nix/hosts/<host>/apt/NAME.sources` с ключом
`NAME.asc`, `arch:NAME` — архитектура dpkg, оба до пакетов) → при
`vm = "yes"` в
`facts.nix`: пакеты `virt/apt.txt`, `@vms` в `/var/lib/vms` с
bind-монтированиями в пути libvirt, пул и сеть `default`
(`virt/bootstrap.bash`) → при `nativeSteam = "yes"`: пакеты
`steam/apt.txt` (Steam из apt, i386) и subvolume `@steam` в
`~/.local/share/Steam` (`steam/bootstrap.bash`; до первого запуска Steam);
при `gameMode = "yes"` — пакеты `gaming/apt.txt` → группы `nix-users`,
`input` (xremap читает клавиатуры), при `vm = "yes"` и `libvirt` → fish как
login shell → первый `ws switch` (заменяемые файлы сохраняются как
`*.pre-hm`). Хост определяется по `hostname` в `nix/hosts/*/facts.nix` (`ws
host`, переопределяет `WS_HOST=<name>`); для новой машины — каталог
`nix/hosts/<name>/` с `facts.nix` (в том числе `vm`, `nativeSteam` и
`gameMode` — `"yes"` или `"no"`) и `apt.txt`. Повторный запуск ничего не меняет.

Шаг `ws apply`, чей preflight не прошёл (exit 69), выводится в конце как
`PREFLIGHT`; отдельный шаг — `ws apply keyboard`.

Шаги `flatpak` и `distrobox` ставят то, что помечено для этой машины
(`HOST=yes` в `flatpak/apps.txt` и `distrobox/hosts.txt`), и спрашивают о не
предложенных: «Поставить все? [Y/n]», на `n` — список с галочками (Space).
Ответ записывается пометкой этой машины; `ws switch` коммитит. Новая машина
получает вопрос обо всём с `all=ask` (`helpws flatpak`, `helpws distrobox`).

`ws system diff` сравнивает системные файлы (`/etc`, `/boot`, `/usr/local`,
`/usr/lib/systemd/system-sleep`), собранные Nix из `system/`, с
установленными; ничего не меняет. Пустой вывод — система совпадает с repo.
`ws check apt` сравнивает списки apt с установленными пакетами и только
сообщает о различиях. `ws check` запускает проверки владельцев: `ws check
repo` (checkout), `ws check home` (home-manager, Nix, man), `ws-keyboard
check`, `ws-gnome check`, `wsflatpak check`, `wsbox check`, `wswin check`,
`ws-suspend check`, `ws system check`, `ws check apt` и последним
`ws-workstation-verify` — только связи между слоями (GNOME ↔ клавиатура,
ядро ↔ t2bce, загрузка ↔ dGPU, Distrobox ↔ NTSync). Каждая проверка с
`--json` печатает один объект `{"status","passes","warnings","failures",
"messages"}` (`lib/check.bash`); `ws check` читает только его, текст для
людей можно менять.
`ws update` обновляет всё, что не закреплено, до последних версий: apt
(`sudo apt full-upgrade`, `linux-t2` остаётся held), Nix (`nix flake update`,
разница пакетов, switch; изменившийся `flake.lock` закоммитить), Flatpak,
пакеты внутри контейнеров (`wsbox update`) и расширения с
extensions.gnome.org (GNOME Shell скачивает обновления, как Extension
Manager; ставятся после logout/login). Отдельный шаг — `ws update nix`.
Закреплены намеренно: ядро (`linux-t2`, `system/kernel/t2bce/t2bce.nix`),
xremap (`nix/pkgs/xremap.nix`), расширения с `pin`, образы по digest.
Новости home-manager (изменения опций после обновления `flake.lock`) — `ws
news`; `ws switch` о них не уведомляет (`news.display = "silent"`), а
`home-manager news` без `--flake` конфигурацию не находит.

Checkpoint — какой коммит соответствовал какому рабочему состоянию.
`bin/`, fish и Ghostty — ссылки в checkout (`nix/home/links.nix`), поэтому
откат поколения home-manager не откатывает пользовательский слой: ключ —
коммит, поколение и системное дерево — то, что из него собрано.

```console
ws checkpoint create before-update   # тег checkpoint/before-update (локальный)
ws checkpoint list
ws checkpoint diff before-update     # коммиты, пакеты (nvd), системное дерево, ядро
ws checkpoint diff before-update --baseline
ws checkpoint show before-update     # что записано и команды возврата
ws checkpoint remove before-update
```

`create` без sudo и только для согласованного состояния: checkout без
изменений, активное поколение собрано из этого коммита (иначе `ws switch`),
`ws system check` без различий (иначе `ws system apply`). Записывает в
`~/.local/state/workstation/checkpoints/NAME/` коммит, поколение, системное
дерево, ядро, установленные ядра и held-пакеты, держит поколение и дерево
GC roots и снимает `ws baseline capture checkpoint-NAME --no-boxes`.
Сам ничего не откатывает; `show` печатает шаги: `git switch --detach
checkpoint/NAME`, `ws switch`, `ws system apply`, `ws apply`, загрузка
записанного ядра. После этого logout/login для загрузки скопированных
расширений GNOME, повторный `ws apply` для шагов, ожидавших новую сессию,
и `ws check`. Применение владельцев обязательно: home-manager доставляет
декларации, а сочетания клавиш, tiling, runtime overrides Flatpak и копии
локальных расширений применяются отдельно. Checkpoint возвращает
конфигурацию; данные приложений и версии установленных Flatpak/контейнеров
восстанавливаются своими средствами.
`ws system apply` дополнительно пишет в `~/.local/state/workstation/system/`
ссылку `applied` на поставленное дерево и строку в `history` (дата, коммит,
дерево, результат).

Flatpak: remotes объявлены в `flatpak/flatpak.nix`, приложения — в
`flatpak/apps.txt`, overrides — в `flatpak/overrides.txt` (оба правит
`wsflatpak`, `ws switch` коммитит); `ws switch` собирает из них
`~/.local/share/workstation/flatpak/` и ставит `.desktop` Claude, шаг `flatpak`
в `ws apply` (`wsflatpak apply`) добавляет remotes, ставит приложения и
применяет overrides (`helpws flatpak`).

Разделы 6.1–10 ниже описывают те же шаги по отдельности.

# 6.1. Managed GNOME appearance

После clone repository сначала проверить текущий desktop state:

```console
ws-gnome status
ws-gnome check
```

Source of truth:

```text
gnome/gnome.nix
```

Профиль записывает `ws switch` (home-manager `dconf.settings`); отдельного
шага в `ws apply` нет. Drift в `ws-gnome check` значит, что ключ изменили
вручную: следующий `ws switch` запишет значение из `gnome.nix` снова.

Профиль не управляет display scale, `monitors.xml`, Mutter
experimental flags, keyboard/input sources, extension enablement, wallpaper,
Flatpak, Distrobox или Wine.

Display scale после reinstall выбирается штатно через `Settings -> Displays`:
logical scale `1.5`.

Wine не устанавливать на host: Windows-программы живут в контейнерах
`wine-wayland`, `wine`, `proton` (`helpws windows`).


# 6.2. Host Qt integration

`qgnomeplatform-qt5`, `qgnomeplatform-qt6`, `qtwayland5`, `qt6-wayland` — в
`nix/hosts/apt.txt` (ставит `bootstrap.sh`, сверяет `ws check apt`).
Глобальных Qt overrides (`QT_QPA_PLATFORM` и т. п.) нет, это проверяет
`ws check home`. Qt5 и Qt6 сами берут native Wayland и QGnomePlatform.


# 6.3. Distrobox / Podman managed layer

Host-пакеты (`podman`, `distrobox`, `uidmap`, …) ставит `bootstrap.sh`,
модуль `ntsync` — `ws system apply`, контейнеры — шаг `distrobox` в `ws
apply` (`wsbox apply`). HOME контейнеров (`~/distrobox/<имя>/`) приходит с
восстановленным HOME пользователя; без него контейнеры создаются пустыми.

Вручную после создания:

- AUR в `arch` — через `paru`, если его нет:

  ```fish
  set tmp (mktemp -d)
  git clone https://aur.archlinux.org/paru.git "$tmp/paru"
  cd "$tmp/paru"
  makepkg -si
  cd
  rm -rf "$tmp"
  ```

  затем нужные AUR-пакеты и `wsbox apply arch` (экспорты).
- WinBox, если prefix потерян: `wswin prefix --box wine-wayland winbox init`
  и `winbox.exe` (WinBox 3.x, mikrotik.com) в
  `~/distrobox/wine-wayland/prefixes/winbox/drive_c/Program Files/WinBox/`.
- Rust в `touchbar-build`, если его HOME потерян: rustup в HOME контейнера
  (`~/distrobox/touchbar-build/.rustup`, `.cargo`).

`wsbox-host-ntsync` (`NTSYNC-MODULE`) Arch-контейнеры ставят сами (init
hook), Wine/WineHQ/umu — хуки Windows-контейнеров. Steam — flatpak, правила
контроллеров — `steam-devices` (apt-список).

```console
wsbox check
```

Подробности: `helpws distrobox`, `helpws windows`.


# 6.4. Keyboard / shortcuts

Системная часть (uinput, GDM/login только US, Touch Bar: udev, modprobe,
`ws-touchbar-fn`) — `ws system apply` (раздел 6.0; при изменении modprobe
пересобирает initramfs). Пользовательская — шаги `extensions`, `tiling`,
`keyboard` в `ws apply`; после первой установки расширений нужен
logout/login и ещё один `ws apply`.

```console
ws-keyboard check
ws-input-source status
```

Ожидаемое поведение:

```text
CapsLock             EN <-> RU; UA -> EN
Fn+CapsLock          UA
Control+Space        EN -> RU -> UA -> EN
GDM/login            EN
GNOME lock screen    EN
```

# 7. Графика

Целевое состояние:

```text
Intel UHD 630  → primary desktop GPU
AMD dGPU       → выключена в rEFInd «Ubuntu» (ws.dgpu=off), render/offload в «Ubuntu (AMD)»
```

Выключение AMD ставит `ws system apply` (`ws-dgpu-off`, `helpws workstation`,
GRAPHICS). Других AMD power tweaks не воспроизводить.

После восстановления проверить реальное распределение GPU, а не только наличие двух adapters.

# 8. Suspend / power

Целевой режим:

```text
deep / S3
```

Файлы слоя сна уже поставил `ws system apply` (раздел 6.0). Патченые модули
t2bce собираются под установленное ядро:

```console
ws-suspend t2bce-build
ws-suspend t2bce-install
ws-psr build
ws-psr install
sudo reboot
```

`ws-psr` — i915 с PSR на панели Apple (helpws plan-t2, раздел 1), без него
экран стоит ~1 W больше.

`t2bce-build` требует `podman` и `linux-headers` текущего ядра. Если для
установленного ядра нет записи в `system/kernel/t2bce/t2bce.nix`, сначала
проверить upstream (`helpws suspend`, раздел «Обновление ядра»).

Проверить:

```bash
ws-suspend check
ws-suspend status
```

Затем ручной тест:

```bash
systemctl suspend
```

После resume проверить Wi‑Fi, Bluetooth, audio, camera, GPU и Touch Bar.

Не запускать:

```text
powertop --auto-tune
TLP
auto-cpufreq
```

Touch Bar USB runtime PM специально не оптимизировать.

# 9. Touch Bar

Родной режим Touch Bar: кнопки рисует T2, режимом управляет
`hid-appletb-kbd`, Fn за xremap пробрасывает `ws-touchbar-fn`. Отдельный
пакет не нужен; `tiny-dfr` **не устанавливать** (причины: `helpws touchbar`).
Всё ставит `ws system apply` (раздел 6.0), режим меняется после reboot.

Целевое поведение:

```text
обычно          -> F1..F12
держим Fn       -> media / brightness
отпускаем Fn    -> F1..F12
```

Проверить:

```console
ws-suspend check      # USB configuration 1, без appletbdrm, ws-touchbar-fn active
```

Не устанавливать Touch Bar renderer/daemon, которые переводят Touch Bar в
режим дисплея (`tiny-dfr`, `react-drm`, `mac-touchbar-plus`).

---

# 10. GNOME extensions

Для keyboard/window/tiling layer используются:

```text
xremap@k0kubun.com
window-control@carlo9890.github.io
Tiling Assistant (Ubuntu UUID либо upstream fallback)
workstation-smart-popup@local
workstation-dock-spring@local
workstation-input-source@local
workstation-hibernate@local (пункт Hibernate; только где logind разрешает hibernate)
```

Список всех расширений и источник каждого — `gnome/gnome-extensions.nix`;
`enabled-extensions` из него пишет `ws switch`.

`workstation-*` sources находятся в `wsconfig` и устанавливаются
командой:

```console
ws-keyboard-install-extensions
```

(шаг `extensions` в `ws apply`). После изменения `extension.js` на Wayland
выполнить logout/login.

Расширения с extensions.gnome.org (`xremap@k0kubun.com`,
`window-control@carlo9890.github.io`,
`window-monitor-pro@muhammed.hussien2030.gmail.com`) ставит тот же шаг
`extensions`, если их нет: последнюю версию для текущего GNOME Shell
(`gnome-extensions install`). Дальше их обновляет Extension Manager (или
`ws update extensions`). Включает их `ws switch` (`enabled-extensions`); на
новой машине — logout/login после первого `ws switch` и `ws apply`.

Закрепить версию: `pin = { version = N; hash = "sha256-…"; }` у расширения
в `gnome/gnome-extensions.nix` (N — номер из ссылки на zip EGO), `ws
switch`. Такое расширение ставит Nix ссылками, и обновлять его в Extension
Manager нельзя: `ws-gnome check` покажет FAIL «files not from Nix», `ws update
extensions` при закреплённых расширениях отказывается.

`Window Monitor Pro` обязателен в списке расширений; клавиатура от него не
зависит.

После logout/login проверить:

```text
running Dock app + external file drag + 1.3 s hover
    -> existing window comes forward

closed Dock app + external file drag + long hover
    -> nothing happens
```


---

# 10.1. Проверка GNOME

```console
ws-gnome test        # автоматическая часть: RESULT: AUTOMATED CHECKS PASSED
```

Затем по его списку вручную, в том числе Dock Spring:

```text
running/minimized app + file hover ~1.3 s -> окно выходит вперёд
closed pinned app + long file hover       -> приложение не запускается
Nautilus -> drop в окно приложения        -> работает
```

---

# 11. Финальная проверка

```bash
ws check
```

Сравнить с эталоном старой системы из архива `ws collect`:

```console
tar -xzf ws-collect-HOST-DATE.tar.gz
cp -a ws-collect-HOST-DATE/baseline ~/.local/state/workstation/baseline/before-reinstall
ws baseline capture after-reinstall
ws baseline diff before-reinstall after-reinstall
```

Ожидаемые отличия — только то, что зависит от установки (UUID, версии
пакетов, хэши изменённых файлов).

Затем вручную проверить:

- boot через rEFInd;
- загрузка в снапшот Timeshift из GRUB;
- Wi‑Fi;
- Bluetooth;
- speakers/mic;
- camera;
- Intel primary / AMD offload;
- `deep/S3` suspend;
- Touch Bar F1…F12 / hold-Fn media (родной режим);
- GNOME Overview / Dock / Quick Settings / Nautilus;
- keyboard profile: Caps/UA/GDM/lock behavior;
- Smart Popup / tiling / Window Control.
- Dock Spring: running app activates after ~1.3 s hover;
- Dock Spring: closed app remains closed on hover.

После этого установка восстановлена; `ws checkpoint create after-reinstall`.

# 12. Recovery

Снапшоты — Timeshift (`timeshift`, GUI и CLI), тип BTRFS: `@` и `@home`
(включить «Include @home subvolume in backups»), BTRFS qgroups выключены.
Расписание и хранение — в GUI, `/etc/timeshift/timeshift.json` принадлежит
Timeshift. Снапшоты лежат на верхнем уровне Btrfs в
`timeshift-btrfs/snapshots/<дата>/{@,@home}`. Другие subvolumes Timeshift не
умеет: `@nix`, `@vms`, `@steam`, `@log`, `@cache` в снапшоты не входят (VM —
своими снапшотами libvirt, `helpws virt`, и backup `@vms`, `helpws
plan-final`; игры Steam — заново из Steam).

Из проверенного состояния (после раздела 11) — первый снапшот:

```console
sudo timeshift --create --comments "after-reinstall"
```

Что добавляет репозиторий (`system/common.nix`, `ws system apply`):

```text
/etc/grub.d/42_ws_timeshift          подменю GRUB «Timeshift snapshots»
/etc/timeshift/backup-hooks.d/50-ws-update-grub
                                     update-grub после каждого снапшота
/etc/timeshift/restore-hooks.d/50-ws-default-subvolume
                                     default subvolume → новый @ после restore
```

## Загрузка в снапшот

rEFInd → GRUB → «Timeshift snapshots» → снапшот (новые сверху; в названии
метка, комментарий и ядро). Грузится самое новое ядро T2 с initrd внутри
снапшота, корень — сам снапшот (`findmnt -no SOURCE /` показывает
`[/timeshift-btrfs/snapshots/…/@]`). Пункты GRUB идут без
`facts.refindDefaultParams`, как «Ubuntu (AMD)»: AMD с `amdgpu`. Снапшоты
Timeshift доступны для записи: изменения такой загрузки остаются в
снапшоте. Снапшот, удалённый Timeshift, пропадает из меню при следующем
`update-grub`. Проверено 2026-10-02.

## Откат

Timeshift → снапшот → Restore (из обычной системы или из загрузки в
снапшот). `@home` откатывается только с галочкой @home в окне Restore —
иначе HOME остаётся как есть. Timeshift переносит текущий `@` в каталог
снапшотов (он виден в списке, удалить, когда всё проверено) и делает новый
`@` из снапшота. rEFInd берёт ядро и initrd из default subvolume, а он
хранится по ID: хук `50-ws-default-subvolume` переставляет его на новый `@`
(если default — верхний уровень, 5, как на машинах только с GRUB, — не
трогает). Перед перезагрузкой проверить:

```console
sudo btrfs subvolume get-default /     # новый ID, path @
```

Затем перезагрузка через rEFInd «Ubuntu». Проверено 2026-10-02: файл,
созданный после снапшота, исчез, ядро T2, default 256 → 285.

`/nix` лежит в отдельном `@nix`: откат `@` не ломает ссылки home-manager в
`/nix/store`.

## До Timeshift

До 2026-10-02 recovery делал `system-backup-snapshot`: `/.snapshots/backup-ro`
и `/.snapshots/recovery`, пункт GRUB «Backup snapshot», копии ядра в
`/boot/recovery` (`helpws history-nix`). Скрипт, пункт GRUB и `/boot/recovery*`
убирает `ws system apply`; subvolume `.snapshots` со старыми снапшотами и его
строку в fstab — вручную.
