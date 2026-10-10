title: ws-plan-legion-go
section: 1
date: 2026-10-10
source: Workstation
volume: User Commands

# LEGION GO (GEN 1) — ПОДГОТОВКА

Цель — wsconfig на Lenovo Legion Go 1 (8APU1, DMI `83E1`) третьим хостом
`legiongo`. База та же, что на mbp16: Ubuntu 26.04, GNOME, Nix и
home-manager поверх неё. Устройство загружается в GNOME. Game Mode —
отдельная сессия gamescope + Steam, как в SteamOS; переключение в обе
стороны идёт без экрана входа. Компоненты Game Mode взяты из Bazzite
(`ublue-os/bazzite` `7f903b9`, изучен 2026-10-10) и перенесены на Ubuntu.

Состояние: план. На устройстве ничего не делалось, в репозитории есть только
этот документ.

# 1. Устройство

```text
DMI          LENOVO 83E1, product_version "Legion Go 8APU1"
APU          Ryzen Z1 Extreme (Phoenix, Zen 4), iGPU Radeon 780M (RDNA3)
память       16 ГБ LPDDR5X, общая с GPU (UMA задаётся в BIOS)
экран        8.8" 2560×1600, 60/144 Гц; панель портретная — поворот делает
             quirk ядра (drm_panel_orientation_quirks, left side up)
сеть         MediaTek MT7922 (mt7921e), Bluetooth (btusb)
контроллеры  съёмные, USB 17ef:6182–6185 / 61eb–61ee: гироскоп, тачпад,
             колесо, FPS-режим, кнопки Legion L/R
диск         NVMe M.2 2242; microSD (GL9755)
ОС сейчас    Windows на устройстве уже нет; Secure Boot выключен
```

Уточнить при установке (этап 3): объём SSD, версию BIOS, PCI-адрес аудио
(в профилях Bazzite — `c2:00.6`), датчики (акселерометр, освещённость).

# 2. Решения

Приняты пользователем 2026-10-10:

```text
ОС          Ubuntu 26.04 на весь SSD (Windows на устройстве уже нет)
загрузка    в GNOME через SDDM с autologin; Game Mode — gamescope + Steam,
            переключение через steamos-manager
ядро        XanMod; AppArmor не нужен; cpufreq.default_governor=powersave
питание     power-profiles-daemon
Steam       нативный
swap        zswap
контроллеры стек Bazzite (InputPlumber, steamos-manager), без HHD
вентилятор  сначала по умолчанию (прошивка)
RGB         выключить подсветку стиков — разобраться после установки
backup      отдельного backup сохранений игр нет
хост        legiongo
```

Из плана (под эти решения):

```text
ядро        пакет linux-xanmod-x64v3 (MAIN); generic-ядро Ubuntu — запасной
            пункт GRUB
параметры   bluetooth.disable_ertm=1 cpufreq.default_governor=powersave
            zswap.enabled=1 zswap.compressor=zstd
питание     steamos-manager без TDP и профиля
swap        swapfile 16 ГБ в @swap
диск        @steam вне снимков и backup
сессия      ubuntu.desktop (сессия GNOME в Ubuntu)
```

Набор слоёв хоста задаётся механизмами, которые уже есть (4.5):
Flatpak и Distrobox — пометками машины в `flatpak/apps.txt` и
`distrobox/hosts.txt`, VM — фактом `vm`. Открыто: значение `vm` для
`legiongo` (рекомендация — `"no"`).

# 3. Компоненты

## 3.1 Ядро XanMod

`linux-xanmod-x64v3` из `deb.xanmod.org` (suite `resolute`), MAIN —
сейчас 7.2.9. В нём есть всё нужное Go 1: quirk панели,
`lenovo-wmi-gamezone` (`platform_profile`), `lenovo-wmi-other`
(firmware-attributes: PPT, hwmon вентилятора, `charge_types`),
`lenovo-wmi-capdata`, `hid-lenovo-go` (RGB и настройки контроллеров).

Что важно в его сборке:

```text
сборка      x86-64-v3, clang 21 без LTO; DKMS-модулям нужен clang на host
конфиг      HZ 250, PREEMPT_LAZY, sched_ext, MGLRU, THP always, ntsync
патчи       BBRv3 по умолчанию, le9uo (защита страниц при нехватке памяти),
            часть Clear Linux, драйверы EC Steam Deck и др.
умолчания   governor performance → cpufreq.default_governor=powersave
            zswap включён, lzo   → zswap.compressor=zstd (zstd встроен)
            AppArmor не в списке LSM — так и оставляем
```

Generic-ядро Ubuntu (7.0) остаётся установленным: им проверяем, если
что-то сломается на XanMod. Параметры ядра общие для обоих
(`GRUB_CMDLINE_LINUX_DEFAULT` из `facts.nix`). В generic-ядре zstd — модуль,
zswap там может стартовать с lzo; AppArmor там активен.

## 3.2 Питание: power-profiles-daemon

PPD 0.30 при каждом переключении режима сам пишет `platform_profile`,
governor, EPP, boost и минимальную частоту, поэтому умолчание ядра
действует только до его старта:

```text
режим PPD          platform_profile  governor     EPP                  boost
энергосбережение   quiet/low-power   powersave    power                выкл
баланс             balanced          powersave    balance_performance  вкл
                                                  (сеть) / balance_power
                                                  (батарея)
производительность performance       performance  performance          вкл
```

Плюс amdgpu: `power_dpm_force_performance_level` low в энергосбережении,
`panel_power_savings` только на батарее. Режим переключается в GNOME или
кнопками Legion L + Y; PPD сохраняет его между загрузками.

Максимум без оглядки на батарею — «Производительность». Режимы прошивки
дают примерно 8 / 15 / 20 Вт. Выше — только `custom` с PPT через
`/sys/class/firmware-attributes/lenovo-wmi-other-0` (до ~30 Вт), мимо PPD.

steamos-manager остаётся для переключения режимов и InputPlumber. В нашем
пакете у device-файла 83E1 убраны `[performance_profile]` и `[tdp_limit]`:
ползунка TDP в QAM Steam нет, `platform_profile` принадлежит только PPD.

## 3.3 Swap: zswap

```text
swapfile   /swap/swapfile 16 ГБ в @swap: ws-suspend swap-setup 16g
           (без CoW и снимков, строка fstab, печатает resume_offset);
           16 ГБ = RAM, поэтому позже возможен hibernate
zswap      zswap.enabled=1 zswap.compressor=zstd; пул 20% RAM и shrinker —
           умолчания, меняем по замеру
sysctl     swappiness и page-cluster — умолчания ядра, подбираем замером
проверка   /sys/module/zswap/parameters/*, swapon --show,
           /sys/kernel/debug/zswap/* (stored_pages, written_back_pages)
```

## 3.4 Game Mode

| Компонент | Что делает | Откуда, в каком виде |
| --- | --- | --- |
| gamescope | композитор Game Mode; профиль экрана Legion Go (`lenovo.legiongo.lcd.lua`, 60/144 Гц) | apt, 3.16.20 |
| gamescope-session-plus, gamescope-session-steam | скрипты и `gamescope-session-plus@.service`; `device-quirks` для 83E1: `ORIENTATION=left`, `STEAM_DISPLAY_REFRESH_LIMITS=60,144`; неподдерживаемые опции gamescope скрипт пропускает сам | OGC, скрипты → `.deb` |
| Steam | клиент; первый запуск — в GNOME, чтобы он обновился | `steam-installer` (multiverse), i386 |
| steamos-manager | DBus между Steam и ОС: переключение Game Mode ↔ GNOME (файлы SDDM), цели InputPlumber (`deck-uhid`, `keyboard`, `mouse`) | OGC `dev` (`9b62985`, как у Bazzite), сборка Rust → `.deb` |
| InputPlumber | `50-legion_go.yaml`: исходные устройства скрыты, вместо них виртуальный контроллер Steam Deck — гироскоп, задние кнопки, Legion L/R | релиз 0.81.0, `.deb` (sha256 закреплён) |
| powerbuttond | кнопка питания в Game Mode: коротко — сон через Steam, долго — меню | Valve `holo/powerbuttond` 4.2, сборка → `.deb` |
| MangoHud с mangoapp | оверлей производительности Steam (`STEAM_USE_MANGOAPP`); в `mangohud` Ubuntu mangoapp нет | сборка → `.deb` |
| extest | `libextest.so`: Steam Input на Wayland-рабочем столе | релиз `ublue-os/extest` → `.deb` |
| SDDM | autologin в `ubuntu.desktop`, `Relogin=true`; steamos-manager пишет `zz-holo-autologin.conf` и `zzt-holo-temp-login.conf` | apt, ставит `wsgame install` на этапе 6: при установке Ubuntu спрашивает display manager, до этого работает GDM; конфиги — системный слой |
| обвязка сессии | `os-session-select` (Steam → `steamosctl`), «Return to Game Mode», polkit, `platform.toml` (`[session] desktop = "ubuntu.desktop"`, режим входа по умолчанию — desktop) | по образцу Bazzite, под `gnome-session --session=ubuntu` — системный слой |

Mesa — из Ubuntu (26.0.8). Сессия выставляет
`STEAM_GAMESCOPE_DYNAMIC_FPSLIMITER`, рассчитанный на Mesa с патчами
Valve. Если ограничитель FPS не работает, убираем переменную.

## 3.5 Правки под 83E1 (из Bazzite)

```text
аудио     PipeWire filter-chain: свёртка multiwayCor48.wav на динамики (sink
          «Legion GO»); WirePlumber: приоритет HDMI, внутренний микрофон,
          headroom 1024 / period 256, suspend-timeout 0; аппаратный sink —
          100% (DSP рассчитан на это). .wav (1 МБ, Apache-2.0) — в
          репозитории с указанием источника или по sha256
hwdb      AT-клавиатура 83E1: scancode 0x67 → F16 (долгое нажатие питания)
kargs     bluetooth.disable_ertm=1
ICC       Legion_GO_BT1886.icc — проверить на глаз, ставить по результату
Wi-Fi     mt7921e disable_aspm=Y — только при обрывах (стоит энергии)
```

## 3.6 Системные настройки (из Bazzite)

```text
sysctl   kernel.split_lock_mitigate=0, vm.max_map_count=2147483642,
         fs.inotify.max_user_instances=8192, max_user_watches=524288,
         vm.watermark_boost_factor=0, vm.watermark_scale_factor=125,
         vm.dirty_bytes=268435456, vm.dirty_background_bytes=134217728,
         kernel.nmi_watchdog=0, soft_watchdog=0, watchdog=0,
         net.ipv4.tcp_mtu_probing=1 (BBR в XanMod и так по умолчанию)
I/O      udev: kyber для NVMe и SSD, bfq для microSD
limits   nice до -8 (Proton)
modprobe blacklist sp5100_tco
logind   HandlePowerKey=ignore — в Game Mode кнопкой владеет powerbuttond,
         в GNOME — сам GNOME
```

## 3.7 Вентилятор и RGB

Вентилятор: кривую выбирает прошивка по режиму, а режим — PPD. Если не
устроят шум или температура (этап 9): hwmon `lenovo-wmi-other`
(`fanN_target`, фиксированные обороты, `0` — авто) с демоном кривой либо
кривая в EC через `acpi_call` — DKMS, значит clang на host.

RGB стиков (после установки): `hid-lenovo-go` даёт
`/sys/class/leds/go:rgb:joystick_rings` — `enabled` = `false`;
udev-правило на появление светодиода переживает переподключение
контроллеров. На generic-ядре 7.0 драйвера нет: там тот же HID-отчёт, что
шлёт HHD — `05 06 70 02 {03|04} 00 01` в hidraw с usage page `0xFFA0`.

# 4. Как это ложится на wsconfig

## 4.1 Хост `nix/hosts/legiongo/`

```text
facts.nix  hostname = "legiongo", user king, wsconfig,
           hardware = "legion-go", boot = "grub", rootUuid, gaming,
           vm = "no" (рекомендация; факт обязателен, 4.5),
           kernelParams = quiet splash bluetooth.disable_ertm=1
                          cpufreq.default_governor=powersave
                          zswap.enabled=1 zswap.compressor=zstd
apt.txt    source:xanmod, arch:i386,
           linux-xanmod-x64v3, steam-installer, gamescope,
           openssh-server, amd64-microcode, lm-sensors, evtest
           (sddm ставит wsgame, 4.4)
```

## 4.2 `bootstrap.sh`

- `source:NAME` — ставит `nix/hosts/<host>/apt/NAME.sources` и ключ из
  репозитория до установки пакетов, как `ppa:` (XanMod).
- `arch:i386` — `dpkg --add-architecture i386` до `apt-get update` (Steam).
- Subvolume `@steam` в `~/.local/share/Steam` (строка fstab, как `@vms`) —
  на хостах с фактом `gaming`. Факт появляется на этапе 6, поэтому там
  `bootstrap.sh` запускается повторно (шаги идемпотентны), до первого
  запуска Steam.
- Пакеты из локальных `.deb` `ws check apt` получает от `wsgame`, а не из
  списка.

## 4.3 Системный слой

Две части, чтобы GDM работал, пока Game Mode не готов:

```text
system/hardware/legion-go.nix   этап 5: sysctl.d, udev (I/O, позже RGB),
                                hwdb (F16), PipeWire/WirePlumber 83E1,
                                limits.d, modprobe.d
system/gaming.nix               этап 6, при факте gaming: sddm.conf.d,
                                polkit, os-session-select, Return to Game
                                Mode, platform.toml, logind.conf.d;
                                units: sddm enabled, gdm3 masked,
                                inputplumber, steamos-manager
```

## 4.4 Игровой слой `gaming/`, владелец `wsgame`

Источники и версии объявлены в Nix (`gaming/sources.nix`: tag или commit
плюс sha256), собирает и ставит владелец («Nix доставляет, владельцы
остаются»):

```text
wsgame build     в сборочном контейнере gaming-build (distrobox.nix,
                 образ — Ubuntu релиза host, как t2bce-build):
                 steamos-manager (device-файл 83E1 без TDP и профиля),
                 MangoHud с mangoapp, powerbuttond → .deb
wsgame fetch     по sha256: InputPlumber .deb; extest и gamescope-session
                 (-plus, -steam), обёрнутые в .deb
wsgame install   apt install ./*.deb — файлы принадлежат dpkg; sddm из apt
                 (display manager — sddm, без вопроса debconf)
wsgame check     пакеты и версии, сервисы, DBus steamos-manager, цели
                 InputPlumber, файлы SDDM, PPD — единственный владелец
                 platform_profile
wsgame mode game|desktop   то же, что steamosctl (терминал, ssh)
```

Новые версии upstream показывает `ws update`, переход — правка
`sources.nix`. Toolchains на host не ставятся.

## 4.5 Зависящее от хоста в других слоях

- **xremap.** Не запускать в gamescope-сессии: его тянет
  `graphical-session.target`, а её поднимает и `gamescope-session-plus`. В
  `--ignore` — виртуальные устройства InputPlumber и Steam и клавиатура
  FPS-режима контроллера.
- **Клавиатура.** Шаги для GDM (EN на экране входа) после перехода на SDDM
  не применять.
- **GNOME.** Масштаб 2.0, экранная клавиатура, ярлык «Return to Game Mode»;
  режимы питания — штатный переключатель (PPD).
- **Steam в GNOME** — со своим launcher и extest (LD_PRELOAD).
- **Flatpak — пометки в `flatpak/apps.txt`.** Заранее, на этапе 1:
  `com.valvesoftware.Steam legiongo=no` (Steam нативный). Остальное — с
  `all=ask`: первый `ws apply` на устройстве спрашивает «Поставить все?
  [Y/n]» или даёт список с галочками, ответы становятся пометками
  `legiongo=yes|no`. Пересмотреть потом — `wsflatpak apply --select`.
- **Свои `.desktop` Flatpak** (`flatpak/desktop/`: Steam, Claude, ChatGPT)
  `ws switch` сейчас ставит на всех машинах. На `legiongo` flatpak-Steam
  стал бы неработающим пунктом рядом с нативным — ставить их только для
  приложений с пометкой `yes` на этой машине.
- **Distrobox — пометки в `distrobox/hosts.txt`.** `t2bce-build` и
  `touchbar-build` нужны только на mbp16 — `all=no`. Новый `gaming-build` —
  `mbp16=yes legiongo=yes all=no` (собирать можно на обеих). `arch`,
  `wine-wayland`, `wine`, `proton` — вопрос на первом `ws apply`.
- **VM** — факт `vm` в `facts.nix`: при `"no"` `bootstrap.sh` не ставит
  `virt/apt.txt`, `@vms`, libvirt и группу `libvirt`, `ws check virt` молчит.
- **Факты масштаба** — DPI Wine (LogPixels 192 при 200%), масштаб Claude и
  AnyDesk — нужны, только если эти боксы и приложения получат
  `legiongo=yes`.
- **git на устройстве.** `ws switch` коммитит пометки локально. Чтобы они
  дошли до mbp16, на `legiongo` нужен доступ к GitHub (`gh auth login` —
  вводит пользователь), а перед `ws switch` на любой машине — `git pull`.
- **Проверки.** `ws check gaming`; verify — связи InputPlumber ↔
  steamos-manager ↔ SDDM ↔ xremap.

## 4.6 Диск

Btrfs по `helpws rebuild`: `@`, `@home`, `@cache`, `@tmp`, `@log`, `@nix`,
`@swap` (3.3), `@steam` — клиент, библиотека, compatdata и shadercache вне
Timeshift и backup. Сохранения, которых нет в Steam Cloud, живут только на
устройстве. microSD — вторая библиотека Steam.

# 5. Этапы

Каждый этап заканчивается `ws checkpoint create NAME`. Перед изменением
ядра, загрузки и питания делается снимок Timeshift.

0. **Устройство.**
   - Версия BIOS — в BIOS setup. Целевая — N3CN40WW (январь 2026);
     N3CN42WW (июнь 2026) Lenovo отозвала после случаев, когда устройство
     переставало загружаться, — не ставить.
   - UMA frame buffer задать вручную, 6–8 ГБ (legion-go-tricks: при авто
     бывает мерцание); загрузка с USB разрешена.
   - Прошивка контроллеров остаётся как есть.
   - USB-C хаб, клавиатура, флешка с Ubuntu 26.04.
1. **Репозиторий на mbp16.** Хост `legiongo` (4.1), `bootstrap.sh` (4.2),
   обе системные части (4.3), каркас `gaming/`, `wsgame` и контейнер
   `gaming-build` (4.4), пометки и `.desktop` Flatpak, xremap и прочее из
   4.5, `helpws gaming`. На mbp16 ничего не меняется: те же пути store для
   home, system и man, `ws check` без FAIL, CI зелёный.
2. **Пакеты на mbp16.** `wsbox apply gaming-build`, `wsgame build` и
   `wsgame fetch`; пакеты ставятся и снимаются в чистом контейнере Ubuntu
   26.04.
3. **Ubuntu.** Установка 26.04 с USB на весь диск, hostname `legiongo`,
   пользователь `king`, Btrfs и subvolumes, как в фазе 6 (`helpws
   history-nix`). Инвентарь в `docs/history/`:
   - `ws collect`; DMI, `lspci -nnk`, `lsusb`, `libinput list-devices`;
   - `/sys/class/firmware-attributes/lenovo-wmi-other-0/attributes/`,
     `platform_profile_choices`, hwmon, iio;
   - `aplay -l`, `pw-cli ls Node` (PCI-адрес аудио для 3.5);
   - `fwupdmgr get-devices`: видит ли fwupd BIOS (Windows нет — других
     способов обновить BIOS, кроме Windows с USB, не остаётся).
4. **База wsconfig.** `bootstrap.sh` (ставит XanMod и Steam) → reboot в
   XanMod → `ws system apply` → `ws apply` (шаги flatpak и distrobox
   спрашивают о не помеченных) → `ws switch` (коммитит пометки
   `legiongo`) → `git push` → `ws check`, как в `helpws rebuild`. GDM ещё
   работает. Проверить:
   `uname -r`, параметры ядра, AppArmor не активен, governor `powersave` до
   PPD, поворот, касания, Wi-Fi, Bluetooth.
5. **Железо.** `system/hardware/legion-go.nix`, `ws-suspend swap-setup 16g`.
   Проверить:
   - s2idle (`amd_s2idle.py`), яркость, автоповорот, батарея;
   - режимы PPD → `platform_profile`, governor, EPP → вентилятор;
   - есть ли hwmon вентилятора и `charge_types` (лимит заряда; включать
     ли — решить по результату);
   - zswap: включён, zstd, swapfile активен;
   - звук на свёртке, после сна (известный шум первые ~30 с).
6. **Game Mode.** Факт `gaming` → `bootstrap.sh` (`@steam`) →
   `wsgame install` (пакеты и sddm) → `ws system apply` (SDDM вместо GDM)
   → первый запуск Steam в GNOME. Проверить:
   - autologin в GNOME; «Return to Game Mode» и «Switch to Desktop» в обе
     стороны; не остаются ли процессы после переключения (если остаются —
     logind `KillUserProcesses`);
   - QAM без ползунка TDP, режим PPD не сбрасывается; оверлей mangoapp;
     ограничитель FPS;
   - сон и кнопка питания в Game Mode;
   - контроллеры снятые и пристёгнутые: гироскоп, задние кнопки, Legion
     L/R; экран 60/144 Гц; внешний монитор по USB-C.
7. **Рабочий стол на портативном.** GNOME 200%, экранная клавиатура,
   контроллер как мышь (InputPlumber или Steam с extest), xremap только в
   GNOME и без виртуальных устройств, RGB стиков выключен (3.7); Flatpak и
   Distrobox — по пометкам `legiongo` (этап 4).
8. **Recovery и backup.** Timeshift и пункты GRUB (XanMod и generic),
   проверка отката. `wsbackup` на Unraid без `@steam` — отдельным шагом.
9. **Опционально, каждое — с замером до и после.** Вентилятор сверх
   прошивки (3.7), режим `custom` TDP, swappiness и page-cluster, Decky
   Loader, scx_lavd, hibernate (`resume=`/`resume_offset` из swap-setup в
   facts), Lutris или Heroic, эмуляторы.

# 6. Риски

- BIOS N3CN42WW — не ставить; BIOS обновляется только через fwupd (если
  Lenovo публикует капсулы в LVFS) или с Windows на USB.
- Прошивку контроллеров Go 1 через fwupd не обновлять: для них предлагалась
  прошивка Go 2 (fwupd #9734).
- GRUB выбирает по умолчанию самое новое ядро: когда generic-ядро Ubuntu
  станет новее XanMod (HWE 7.3), по умолчанию загрузится оно. Закрепить
  пункт XanMod (`GRUB_DEFAULT`) или переход сделать осознанно.
- XanMod — один основной автор; DKMS-модули потребуют clang на host.
- Ограничитель FPS gamescope без Mesa с патчами Valve может не работать
  (3.4).
- gamescope 3.16.20 старше того, на что рассчитан текущий клиент Steam;
  запасной путь — сборка upstream в podman.
- SDDM вместо GDM: экран входа и lock screen ведут себя иначе, шаги
  клавиатурного слоя для GDM здесь не работают.
- `hid-lenovo-go` вместе с InputPlumber: проверить гироскоп и кнопки (в
  Bazzite Deck 44 у Go 1 не работает гироскоп).
- xremap может захватить виртуальные устройства InputPlumber (4.5).
- Пометки двух машин в одних файлах: если `ws switch` на mbp16 и на
  `legiongo` закоммитит `apps.txt` или `hosts.txt` без `git pull`, при
  слиянии будет конфликт.
- На generic-ядре AppArmor ограничивает user namespaces: при загрузке в
  него Steam (pressure-vessel) может не стартовать.
- Звук после сна и автояркость — известные недочёты Go 1 на Linux.

# Источники

- Bazzite: <https://github.com/ublue-os/bazzite> (Containerfile,
  `system_files/deck`, `system_files/desktop/shared/usr/libexec/hwsupport`);
  Handheld Wiki, Legion Go:
  <https://docs.bazzite.gg/Handheld_and_HTPC_edition/Handheld_Wiki/Lenovo_Legion_Go/>
- steamos-manager (OGC): <https://github.com/OpenGamingCollective/steamos-manager>
- gamescope-session, gamescope-session-steam (OGC):
  <https://github.com/OpenGamingCollective/gamescope-session>,
  <https://github.com/OpenGamingCollective/gamescope-session-steam>
- InputPlumber: <https://github.com/ShadowBlip/InputPlumber>
- powerbuttond: <https://gitlab.steamos.cloud/holo/powerbuttond>
- extest: <https://github.com/ublue-os/extest>
- XanMod: <https://xanmod.org/>, конфиг <https://gitlab.com/xanmod/linux>
  (`CONFIGS/x86_64/config`, 7.2), индекс `deb.xanmod.org/dists/resolute`
- power-profiles-daemon 0.30: `src/ppd-driver-amd-pstate.c`,
  `src/ppd-driver-platform-profile.c`
- Linux 7.2: `drivers/cpufreq/amd-pstate.c`, `drivers/cpufreq/cpufreq.c`,
  `mm/zswap.c`, `Documentation/ABI/testing/sysfs-driver-hid-lenovo-go`
- HHD (HID-отчёт RGB): <https://github.com/hhd-dev/hhd>
  (`src/hhd/device/legion_go/tablet/hid.py`)
- legion-go-tricks (UMA): <https://github.com/aarron-lee/legion-go-tricks>
- fwupd #9734: <https://github.com/fwupd/fwupd/issues/9734>
- Отзыв BIOS N3CN42WW:
  <https://www.notebookcheck.net/Lenovo-quietly-removes-BIOS-update-that-bricked-Legion-Go-handhelds-but-affected-users-are-still-left-with-unusable-devices.1363023.0.html>
