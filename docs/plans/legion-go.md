title: ws-plan-legion-go
section: 1
date: 2026-10-10
source: Workstation
volume: User Commands

# LEGION GO (GEN 1) — ПОДГОТОВКА

Цель — wsconfig на Lenovo Legion Go 1 (8APU1, DMI `83E1`) третьим хостом.
База та же, что на mbp16: Ubuntu 26.04, GNOME, Nix и home-manager поверх
неё. Сверху — игровой режим в духе SteamOS из тех компонентов, которые
Bazzite ставит на Fedora. Устройство в первую очередь игровое, поэтому
основной режим — Game Mode (gamescope + Steam), GNOME — режим рабочего стола.

Состояние: план. На устройстве ещё ничего не делалось, в репозитории есть
только этот документ. Bazzite изучен 2026-10-10 по `ublue-os/bazzite`
`7f903b9`: Containerfile, `system_files`, `hwsupport`. Отдельно просмотрены
ядро OGC, steamos-manager (OGC `dev` `9b62985`), InputPlumber `0.81.0` и
gamescope-session (OGC).

# 1. Устройство

```text
DMI          LENOVO 83E1, product_version "Legion Go 8APU1"
APU          Ryzen Z1 Extreme (Phoenix), iGPU Radeon 780M (RDNA3, amdgpu)
память       16 ГБ LPDDR5X, общая с GPU (размер UMA задаётся в BIOS)
экран        8.8" 2560×1600, 60/144 Гц; панель портретная: поворот делает
             quirk ядра (drm_panel_orientation_quirks, left side up)
сеть         MediaTek MT7922 (mt7921e), Bluetooth (btusb)
контроллеры  съёмные, USB 17ef:6182–6185 / 61eb–61ee: гироскоп, тачпад,
             колесо, FPS-режим, кнопки Legion L/R
диск         NVMe M.2 2242; microSD (GL9755)
```

Что уточнить на месте (этап 3): объём SSD, версию BIOS, кодек и усилитель,
датчики (акселерометр, освещённость), PCI-адрес аудио. В профилях Bazzite
он записан как `c2:00.6`.

# 2. Что Bazzite ставит поверх Fedora

Образы собираются цепочкой: Fedora 44 Atomic → `bazzite` (рабочий стол) →
`bazzite-deck` (Game Mode, загрузка как SteamOS). Для портативных
устройств предназначен `bazzite-deck`. Ниже компоненты сгруппированы, по
каждому указано, как он связан с Legion Go 1 и что с ним делаем мы.

## 2.1 Ядро

У Bazzite своё ядро — OGC (Open Gaming Collective: Bazzite, ChimeraOS и
другие). Ветки `ogc-7.x.y` — это stable плюс набор `features/*`:

- `lenovo` — сейчас только `hid-lenovo-go-s`;
- `asus`, `msi-claw`, `ayaneo`, `onexplayer`, `zotac`, `steamdeck` —
  другие устройства;
- `panels` — quirks ориентации экрана;
- `scheduler` — EEVDF и `cgroup_mode`;
- `vram-overcommit` и `dmem-cgroups` — TTM;
- `vrr` — HDMI 2.1 VRR и ALLM;
- `fixes` — TSC при сне, amdgpu, Bluetooth.

Поверх ядра ставятся kmods: xone, kvmfr, openrazer, v4l2loopback,
ryzen_smu, zenergy, драйверы рулей.

Поддержка Legion Go 1 в mainline:

```text
панель            quirk "Legion Go 8APU1"                         есть в 7.0
lenovo-wmi-gamezone  platform_profile, в т.ч. custom              есть в 7.0
lenovo-wmi-other  firmware-attributes lenovo-wmi-other-0:         есть в 7.0
                  лимиты PPT (это и есть TDP)
lenovo-wmi-capdata  данные для них                                есть в 7.0
hid-lenovo-go     настройка контроллеров через sysfs              с 7.1
```

Для Go 1 OGC не добавляет ничего функционального. Ядро Ubuntu 26.04
(generic, HWE и OEM) сейчас везде 7.0 (generic `7.0.0-38`): в нём нет только
`hid-lenovo-go`. InputPlumber работает с контроллерами через hidraw и без
этого драйвера.

Своё ядро не собираем (решение 4); Secure Boot на устройстве выключен
(пользователь). Что меняет каждое готовое ядро относительно generic Ubuntu
(конфиги разобраны 2026-10-10: Ubuntu `Ubuntu-7.0.0-38.38`, XanMod и
Liquorix 7.2.9; Zabbly — по README):

```text
Ubuntu generic 7.0 (база)
  патчи      mainline 7.0 + патчи Ubuntu: AppArmor (в т.ч. ограничение
             user namespaces), lockdown при Secure Boot, каталог ubuntu/
  конфиг     HZ 1000, PREEMPT_LAZY (dynamic), sched_ext, MGLRU, amd-pstate
             active, THP madvise, BBR модулем (по умолчанию cubic),
             CGROUP_DMEM; lenovo-wmi-gamezone/other/capdata — модули
  Go 1       нет hid-lenovo-go (RGB через sysfs) и лимита заряда
  прочее     подписано, обновления безопасности Canonical

Ubuntu HWE 7.3 (из 26.10)
  патчи      те же патчи и конфиг Ubuntu на 7.3
  Go 1       + hid-lenovo-go (7.1), + лимит заряда charge_types и лимиты
             температуры (7.2); в 7.3 драйверы Lenovo те же, что в 7.2
  когда      26.10 выходит 15.10; для 26.04 — по обычному графику:
             hwe-edge, затем 26.04.2 (~февраль 2027)

Zabbly (stable mainline, сейчас 7.2.x)
  патчи      почти чистый mainline: только idmap для cephfs (+2 отката
             для aarch64); патчей Ubuntu нет
  конфиг     производная от конфига Ubuntu, «почти всё модулями»;
             рассчитан на Incus
  Go 1       всё, что есть в 7.2
  прочее     apt-репозиторий, обновления раз в неделю; на новую ветку
             переходит только после её первого bugfix-релиза; не подписано

XanMod MAIN 7.2.9
  патчи      BBRv3 по умолчанию, le9uo (защита анонимных и чистых страниц
             при нехватке памяти, 15%), TCP collapse от Cloudflare, full-cone
             NAT, ACS override для IOMMU, часть патчей Clear Linux,
             дополнительные опции CPU (graysky), драйверы EC Steam Deck,
             binder
  конфиг     сборка x86-64-v3, HZ 250, PREEMPT_LAZY (dynamic), sched_ext,
             THP always, MGLRU; Lenovo WMI и hid-lenovo-go есть
  прочее     apt (resolute), один основной автор; не подписано

Liquorix 7.2.9
  патчи      zen (ZEN_INTERACTIVE), планировщик PDS (Project C) вместо EEVDF,
             BBRv3 по умолчанию
  конфиг     полный PREEMPT, HZ 1000, sched_ext нет (несовместим с PDS),
             ntsync встроен; hid-lenovo-go есть, а lenovo-wmi-gamezone,
             -other, -capdata не включены
  Go 1       нет platform_profile: PPD не переключает режимы прошивки,
             нет TDP и hwmon вентилятора — не подходит
```

`kernel.ubuntu.com/mainline` — без обновлений, только для отладки. У OGC и
CachyOS пакетов `.deb` нет.

Secure Boot выключен, поэтому главный минус сторонних ядер — отсутствие
подписи — не мешает. Liquorix не подходит, ядро Ubuntu 7.0 лишено
`hid-lenovo-go` и лимита заряда, HWE 7.3 для 26.04 ещё нет. Остаются Zabbly
и XanMod.

### Zabbly и XanMod (7.2.9, 2026-10-10)

Оба собраны из одного и того же 7.2.9 (выпуск 2026-10-03), поэтому драйверы
Go 1 (`lenovo-wmi-*`, `hid-lenovo-go`, quirk панели) у них одинаковые.
Различаются патчи, конфиг и упаковка.

```text
                   Zabbly                          XanMod MAIN (x64v3)
кто                Stéphane Graber (Incus),        Alexandre Frade, один
                   коммерческая поддержка Zabbly   основной автор
цель               свежий mainline с широкой       производительность
                   поддержкой железа; под Incus    десктопа и игр
патчи              только idmap для cephfs         BBRv3, le9uo, TCP collapse,
                                                   full-cone NAT, ACS override,
                                                   часть Clear Linux, опции CPU
                                                   graysky, EC Steam Deck, binder
конфиг             производная от Ubuntu,          свой
                   «почти всё модулями»
компилятор         под каждый релиз Ubuntu         clang 21 (Debian), без LTO
                   (уточнить по /boot/config)
архитектура        x86-64 (базовая)                x86-64-v3 (Zen 4 это умеет)
таймер             как Ubuntu: HZ 1000,            HZ 250, NO_HZ_IDLE
                   NO_HZ_FULL
вытеснение         как Ubuntu: PREEMPT_LAZY        PREEMPT_LAZY (dynamic)
                   (dynamic)
cpufreq по умолч.  как Ubuntu: schedutil →         performance → amd-pstate-epp
                   amd-pstate-epp в powersave      в policy performance (до
                                                   старта PPD; см. ниже)
zswap              как Ubuntu: выключен            включён (lzo)
THP                как Ubuntu: madvise             always
память             MGLRU                           MGLRU + le9uo (защита 15%
                                                   анонимных и чистых страниц)
TCP                как Ubuntu: cubic, BBR модулем  BBRv3 встроен, по умолчанию
LSM                как Ubuntu: AppArmor по         AppArmor собран, но не в
                   умолчанию (без патчей Ubuntu)   списке LSM: выключен
sched_ext, ntsync  есть                            есть
модули             сжаты как в Ubuntu (уточнить)   без сжатия
DKMS               нужен gcc на host               нужен clang на host
пакеты             linux-zabbly → image +          linux-xanmod-x64v3 → image +
                   headers; ~640 МБ после          headers; ~600 МБ после
                   установки; ещё linux-libc-dev   установки
                   7.2.9 — заменит пакет Ubuntu,
                   если тот стоит (нужен pin)
версии             ждёт первого bugfix новой       MAIN — сразу; EDGE — новее
                   ветки; 7.1.13, 7.2.4–7.2.9      (сейчас тоже 7.2.9);
                   в репозитории                   7.2.4–7.2.9 в репозитории
обновления         apt, раз в неделю               apt (resolute), по выходу stable
```

Его плюсы — 250 Гц, le9uo, x86-64-v3, THP always — для Go 1 не измерены.
Zabbly ведёт себя как ядро Ubuntu, только новее.

**Мы: XanMod MAIN x64v3 (решение 4).** Generic-ядро Ubuntu остаётся
запасным пунктом в GRUB. XanMod подключается своим источником apt
(`deb.xanmod.org`, `resolute`) с ключом: это файлы системного слоя, не
строка в `apt.txt`. Его умолчания под наши решения:

- **cpufreq.** Governor по умолчанию — `performance` (amd-pstate-epp:
  MinPerf не ниже номинала, EPP 0). Он действует только до старта PPD.
  PPD 0.30 при каждом переключении сам пишет `scaling_governor`, EPP,
  boost и минимальную частоту:

  ```text
  режим PPD          governor     EPP                         boost  мин. частота
  энергосбережение   powersave    power                       выкл   cpuinfo_min
  баланс             powersave    balance_performance (сеть)  вкл    lowest_nonlinear
                                  balance_power (батарея)
  производительность performance  performance                 вкл    lowest_nonlinear
  ```

  Плюс `platform_profile` (quiet / balanced / performance) и amdgpu:
  `power_dpm_force_performance_level` low в энергосбережении,
  `panel_power_savings` только на батарее. Максимум без оглядки на батарею —
  режим «Производительность», в GNOME или Legion L + Y. На батарее PPD его
  не урезает и сохраняет режим между загрузками. Сверх режима прошивки
  performance — только `custom` с PPT через firmware-attributes (до ~30 Вт),
  мимо PPD. `cpufreq.default_governor=powersave` (решение пользователя)
  действует до старта PPD и на случай, если PPD не запущен.
- **zswap** — наш swap (решение пользователя, 2.6). В XanMod он включён по
  умолчанию (lzo); задаём `zswap.compressor=zstd` (встроен в XanMod).
- **AppArmor** не нужен (решение пользователя): у XanMod его нет в списке
  LSM, `lsm=` не задаём. Пакет `apparmor` без LSM ничего не делает;
  ограничения Ubuntu на user namespaces нет, Steam (pressure-vessel),
  bwrap и podman работают без профилей.
- **DKMS** собирает модули clang'ом. Если понадобится `acpi_call`
  (вентилятор, 2.8), на host нужен clang — это toolchain, решать отдельно.

## 2.2 Графика и игровые библиотеки

Bazzite ставит Mesa с патчами Valve (`terra-mesa`, versionlock). Патчи нужны
ограничителю FPS в gamescope: сессия выставляет
`STEAM_GAMESCOPE_DYNAMIC_FPSLIMITER`. Xwayland и WirePlumber тоже берутся
из Terra. Кроме них — MangoHud с mangoapp, vkBasalt, obs-vkcapture,
OpenXR, libFAudio и umu-launcher. Пакет `gamemode` Bazzite наоборот
удаляет.

**Мы:** Mesa из Ubuntu (26.0.8). В Game Mode проверяем ограничитель FPS;
если он не работает, убираем переменную из сессии. Сторонний Mesa без
причины не берём.

## 2.3 Game Mode (`bazzite-deck`)

| Компонент | Что делает | У нас |
| --- | --- | --- |
| gamescope (форк OGC) | композитор Game Mode; в форке жесты касанием, `--custom-refresh-rates`, правки ориентации | `gamescope` из apt (3.16.20, upstream 3.16.31). Профиль экрана Legion Go (`lenovo.legiongo.lcd.lua`, 60/144 Гц) есть и в 3.16.20. Собирать новее — только если понадобится |
| gamescope-session-plus, gamescope-session-steam (OGC) | скрипты сессии и `gamescope-session-plus@.service`; `device-quirks` для 83E1: `ORIENTATION=left`, `STEAM_DISPLAY_REFRESH_LIMITS=60,144` | берём. Это скрипты, сборка не нужна. Неподдерживаемые опции gamescope скрипт проверяет сам |
| gamescope-session-ogui-steam | OpenGamepadUI как overlay поверх Steam; по умолчанию у Bazzite для портативных не от Valve | на старте не берём: обычная сессия Steam |
| Steam (нативный пакет) и `bootstrap_steam.tar.gz` (Nobara) | клиент и его первичная распаковка | нативный Steam (`steam-installer`, multiverse, i386), как у Bazzite, SteamOS и ChimeraOS. Для flatpak-Steam gamescope-сессия не рассчитана: Steam вызывает на host `steamos-session-select` и прочие helpers. Первый запуск — в GNOME, чтобы клиент обновился |
| steamos-manager (OGC `dev`) | DBus API между Steam и ОС: TDP, профиль производительности, частота GPU, переключение Game Mode ↔ рабочий стол, цели InputPlumber. `legion-go-series.toml`: профиль через `lenovo-wmi-gamezone` (`custom`), TDP через `firmware_attribute` `lenovo-wmi-other-0`, цели InputPlumber `deck-uhid`, `keyboard`, `mouse` | собираем (Rust) в podman → `.deb` |
| InputPlumber (ShadowBlip) | `50-legion_go.yaml`: исходные устройства скрыты, вместо них виртуальный контроллер Steam Deck (`deck-uhid`) с гироскопом, задними кнопками и Legion L/R | `.deb` из релиза (0.81.0), версия и sha256 закреплены |
| PowerStation | TDP для устройств без WMI-драйвера | для 83E1 не нужен (`steamos-manager-hardware`). Не ставим |
| powerbuttond | короткое нажатие питания — сон через Steam, долгое — меню; logind при этом `HandlePowerKey=ignore` | собираем (Valve `holo/powerbuttond` 4.2, C) |
| SDDM вместо GDM | autologin с `Relogin=true` в `gamescope-session-*.desktop`. Режим переключается файлами `/etc/sddm.conf.d/zz-holo-autologin.conf` и `zzt-holo-temp-login.conf`, это делает steamos-manager. Обвязка: `os-session-select` (вызывает Steam, внутри `steamosctl`), `gnome-session-oneshot`, `return-to-gamemode`, правила polkit | SDDM на этом хосте, autologin в GNOME (решение 2; у Bazzite так же — `/etc/bazzite/desktop_autologin`). Переключение режимов в steamos-manager умеет только SDDM. На mbp16 остаётся GDM |
| mangoapp (MangoHud) | оверлей производительности Steam в Game Mode (`STEAM_USE_MANGOAPP`) | в `mangohud` Ubuntu mangoapp нет. Собираем MangoHud в podman |
| extest | `libextest.so`: Steam Input на Wayland-рабочем столе | берём (готовая `.so` релиза `ublue-os/extest`) |
| Decky Loader, gamemode-news-hook, steam-notif-daemon, sdgyrodsu, jupiter-*, vpower, galileo-mura | плагины, новости, Deck | Decky — этап 9; остальное только для Deck |

Steam нативный или flatpak (решение 3):

```text
                  нативный (steam-installer)         flatpak (Flathub)
Game Mode         как в SteamOS и Bazzite: Steam     не рассчитан: из sandbox Steam
                  вызывает на host                   не видит helpers host; нужны свои
                  steamos-session-select, steamosctl шимы и права DBus, так никто
                  и polkit-helpers                   не делает
host              i386 multiarch: 32-битные Mesa,    только steam-devices
                  glibc и другие (сотни МБ,
                  обновляются вместе с amd64)
Mesa в играх      Ubuntu 26.0.8, как у gamescope     runtime Flathub (обычно новее)
Steam Input       extest через LD_PRELOAD            extest придётся класть в sandbox
  в GNOME
изоляция          нет                                sandbox
AppArmor          профиль steam в Ubuntu — проверить не касается
как на mbp16      нет (там flatpak)                  да
```

**Мы (рекомендация):** нативный Steam: в Game Mode другого
работающего варианта нет.

## 2.4 Питание: power-profiles-daemon или steamos-manager

Оба пишут один и тот же `platform_profile` (lenovo-wmi-gamezone), поэтому
вместе не работают: PPD сбрасывает режим `custom`, и ползунок TDP
перестаёт действовать. Bazzite решает по образу. На `bazzite-deck` у
портативных `tuned` и `tuned-ppd` замаскированы, владеет steamos-manager.
На обычных образах работает `tuned-ppd`, а steamos-manager нет.

```text
              power-profiles-daemon 0.30        steamos-manager
режимы        экономия, баланс,                 профили прошивки и custom
              производительность
TDP           только режимы прошивки            ползунок в ваттах: PPT через
              (примерно 8 / 15 / 20 Вт)         lenovo-wmi-other, режим custom
CPU           EPP amd-pstate по режиму          boost, governor
GPU           экономия панели amdgpu (ABM)      ручная частота (ppfeaturemask),
              в режиме экономии                 профиль питания GPU
Game Mode     ползунка TDP в QAM нет            ползунок и профиль в QAM,
                                                как в SteamOS
GNOME         штатный переключатель режимов     расширение
                                                tdp-control@opengamingcollective.org
лимит заряда  нет                               для Go 1 нет (умеет Deck,
                                                Ally, Claw)
```

Режим прошивки переключается и кнопками Legion L + Y, при любом владельце.
karg `amdgpu.ppfeaturemask` = текущее значение | `0x4000` (OverDrive)
нужен steamos-manager для частоты GPU. ryzenadj и ryzen_smu (undervolt) у
Bazzite есть, но выключены.

**Мы: PPD (решение 6).** Владелец питания — штатный power-profiles-daemon:
переключатель в GNOME, кнопки Legion L + Y. steamos-manager остаётся ради
переключения режимов и InputPlumber. В нашем `.deb` у device-файла 83E1
убраны `[performance_profile]` и `[tdp_limit]`: так он не трогает
`platform_profile` и PPT, а ползунка TDP в QAM нет. Karg ppfeaturemask и
расширение tdp-control не нужны, undervolt не трогаем.

## 2.5 Особенности 83E1 в Bazzite

```text
аудио     PipeWire filter-chain: свёртка multiwayCor48.wav на динамики (sink
          «Legion GO»); WirePlumber: приоритет HDMI, внутренний микрофон,
          headroom 1024 / period 256, suspend-timeout 0; громкость sink 100%
          (DSP рассчитан на неё)
цвет      ICC Legion_GO_BT1886.icc
hwdb      AT-клавиатура 83E1: scancode 0x67 → F16 (долгое нажатие питания)
gamescope ORIENTATION=left, 60/144 Гц; вложенный рабочий стол 2560×1600
GNOME     масштаб 200% (в KDE 150%)
kargs     bluetooth.disable_ertm=1 (везде), ppfeaturemask (портативные);
          IOMMU не выключать
Wi-Fi     mt7921e disable_aspm=Y (глобально для всех mt7921)
```

**Мы:** берём аудио, hwdb и `bluetooth.disable_ertm=1` (ppfeaturemask не нужен, 2.4). ICC проверяем на глаз. ASPM у Wi-Fi
выключаем только при обрывах, это стоит энергии (как в battery audit mbp16).
Bazzite под Apache-2.0: `.wav` (1 МБ) можно положить в репозиторий с
указанием источника либо скачивать с закреплённой sha256.

## 2.6 Общие настройки системы

```text
sysctl   kernel.split_lock_mitigate=0, vm.max_map_count=2147483642, bbr +
         tcp_mtu_probing, inotify 8192/524288; deck: swappiness=180,
         watermark_boost_factor=0, watermark_scale_factor=125, dirty_bytes,
         page-cluster=0, nmi/soft watchdog=0
zram     zstd, min(ram/2, 16 ГБ)
I/O      kyber для NVMe и SSD, bfq для microSD и HDD (udev)
прочее   ntsync; nice до -8 (limits, Proton); logind KillUserProcesses;
         постоянный journald; blacklist sp5100_tco
sched    scx_lavd через scx_loader (deck; Steam переключает режимы)
VRAM     dmemcg-booster / uresourced-dmemcg: приоритет памяти GPU активному
         приложению (dmem cgroup + патчи TTM из OGC)
```

**Мы:** берём sysctl, кроме настроек под zram (swappiness 180,
page-cluster 0: у нас zswap, их подбираем замером), I/O, nice и watchdog;
zram не берём (2.6). NTSync уже есть
(Distrobox). scx_lavd и dmemcg — этап 9: только с замером, на ядре без
патчей TTM из OGC.

### zram и zswap

```text
          zram                               zswap
что       блочное устройство в RAM: swap     сжатый кэш перед дисковым swap:
          прямо в памяти, сжатый             перехватывает выгружаемые страницы
нужен     нет                                да (swapfile или раздел); без него
диск                                         ничего не делает
когда     растёт до заданного размера, дальше пул заполнен (по умолчанию 20%
полон     — OOM                              RAM) — старые страницы пишутся на
                                             диск
диск      не пишет                           пишет при нехватке памяти
сон в     нет: образ в RAM не сохранить      да, через тот же swapfile
диск
вместе    zswap поверх zram сжимает страницы второй раз и потом всё равно
          отдаёт их в zram — смысла нет, выбирают одно
```

Памяти у Go 1 видно меньше 16 ГБ: из них BIOS отдаёт GPU UMA (6–8 ГБ).
Сжатый swap здесь полезен. Варианты:

1. **Только zram** (как Bazzite): zstd, `min(ram/2, 16 ГБ)`,
   swappiness 180, `zswap.enabled=0`. SSD не изнашивается, но hibernate нет.
2. **zswap + swapfile в `@swap`**: один механизм, при нехватке — на SSD;
   hibernate возможен (swapfile ≥ RAM, `resume=`/`resume_offset`, как на
   mbp16).
3. **zram (высокий приоритет) + swapfile (низкий, только для hibernate)**,
   zswap выключен.

**Мы: вариант 2, zswap + swapfile (решение пользователя).**

```text
swapfile   /swap/swapfile в @swap: ws-suspend swap-setup 16g (как на mbp16:
           без CoW и снимков, строка fstab, печатает resume_offset)
           16 ГБ = RAM: hibernate остаётся возможным (этап 9)
kargs      zswap.enabled=1 zswap.compressor=zstd — для обоих ядер GRUB
           (в generic-ядре zswap выключен по умолчанию, zstd там модуль:
           при загрузке он может откатиться на lzo — для запасного ядра
           не страшно)
пул        max_pool_percent 20 (по умолчанию), shrinker включён (по
           умолчанию в обоих ядрах) — меняем только по замеру
проверка   /sys/module/zswap/parameters/*, swapon --show,
           /sys/kernel/debug/zswap/* (stored_pages, written_back_pages)
```

## 2.7 Не берём

Homebrew, ujust и ujust-picker, Bazaar и Bazzite Portal — их делают
`ws`, Nix, Flatpak. uupd и topgrade — есть `ws update`. greenboot,
snapper и btrfs-assistant — есть Timeshift. Ещё мимо: Waydroid, Sunshine,
cockpit, tailscale, OpenRazer, CEC, SELinux-обвязка, NVIDIA,
rom-properties и GSConnect. input-remapper конфликтовал бы с
InputPlumber и xremap. bees (дедупликация) — только если префиксы Proton
займут много места. Lutris решаем вместе со слоем Windows (решение 5).

## 2.8 HHD вместо этого стека

HHD (Handheld Daemon, `hhd-dev/hhd`) раньше стоял в Bazzite. В текущем
образе его нет: вместо него InputPlumber и steamos-manager (OGC). Сравнение
для Go 1 на Ubuntu (HHD 4.1.12, `a87fb30`):

| | HHD | InputPlumber + steamos-manager |
| --- | --- | --- |
| Контроллеры | эмуляция DualSense Edge или Xbox: гироскоп, задние кнопки, ярлыки Legion | виртуальный Steam Deck (`deck-uhid`): Steam видит Deck, со своими значками и кнопками Steam/QAM |
| TDP | свой оверлей в gamescope (двойное нажатие боковой кнопки) и приложение для рабочего стола | ползунок в QAM Steam; в GNOME — tdp-control |
| Вентилятор | кривые, полная скорость | нет, управляет прошивка |
| Лимит заряда 80% | есть | нет (с ядром 7.2+ — `charge_types`) |
| RGB | есть | нет из коробки (`hid-lenovo-go`, 7.1+) |
| GNOME | заменяет power-profiles-daemon своим DBus: штатный переключатель режимов управляет TDP | PPD маскируется (2.4) |
| Game Mode ↔ GNOME | не переключает | steamos-manager и SDDM |
| Доступ к прошивке | `acpi_call` (внешний DKMS-модуль): прямые вызовы методов WMI в ACPI; при Secure Boot нужна подпись MOK, lockdown может мешать | драйверы ядра `lenovo-wmi-*`, Secure Boot не мешает |
| Установка на Ubuntu | только скрипт `install.sh` через curl в локальный venv; ломается при обновлении Python, зависимости ставятся вручную; под Nix автор не рекомендует, советует свой дистрибутив Anatase | InputPlumber — `.deb`, steamos-manager — сборка, сессия — скрипты |
| Кто развивает | в основном один автор; он против драйверов контроллеров в mainline | OGC (Bazzite, ChimeraOS и другие); steamos-manager — Valve; InputPlumber используется в SteamOS |

Итог. По Lenovo-функциям HHD богаче: вентилятор, заряд, RGB, всё в одном
оверлее, плюс штатный переключатель GNOME. Стек Bazzite лучше ложится на
wsconfig: драйверы ядра вместо `acpi_call`, `.deb` вместо
curl, Steam работает как в SteamOS, режимы переключаются. Лимит заряда
приходит с ядром 7.2+.

**Мы: стек Bazzite, от HHD отказались (решение 9).** RGB и вентилятор —
без HHD, как ниже. Secure Boot выключен, так что `acpi_call`, если
понадобится, не требует подписи, и lockdown не мешает.

### RGB без HHD

Нужно только выключить подсветку стиков. Разбираемся после установки
(решение 9). InputPlumber RGB Go 1 не управляет.

- **Ядро 7.1+** (`hid-lenovo-go`; Zabbly, XanMod, HWE 7.3): светодиод
  `/sys/class/leds/go:rgb:joystick_rings` — `enabled` = `false` (или
  `brightness` 0). Ставит udev-правило на появление светодиода, поэтому
  срабатывает и после переподключения контроллеров.
- **Ядро 7.0:** тот же HID-отчёт, что посылает HHD (`rgb_enable`):
  `05 06 70 02 {03 левый | 04 правый} 00 01` в hidraw контроллера с usage
  page `0xFFA0`. Маленький oneshot по udev на появление hidraw.
- Сохраняет ли контроллер выключение сам после одной записи, проверить на
  этапе 6. Если сохраняет, правило только подстраховывает.

Светодиод кнопки питания — отдельная вещь: HHD управляет им через метод
WMI (`acpi_call`).

### Вентилятор без HHD

1. **Прошивка (по умолчанию).** Кривую выбирает EC по режиму прошивки
   (quiet, balanced, performance). PPD переключает режим, вентилятор идёт
   следом. Ничего ставить не нужно.
2. **hwmon `lenovo-wmi-other` (есть в 7.0).** `fanN_input` — обороты,
   `fanN_target` — фиксированные обороты в пределах `fanN_min..max`, `0` —
   вернуть авто. Появляется, только если прошивка Go 1 отдаёт данные о
   вентиляторе: проверить на этапе 3. Кривая поверх — демоном (например,
   fan2go с вентилятором через файл). Он обязан возвращать `0` при выходе и
   перед сном. `fancontrol` из lm-sensors не подходит: ему нужен pwm.
3. **Своя кривая в EC** — метод WMI `\_SB.GZFD.WMAB`, как в HHD и
   LegionGoRemapper: 10 точек через `acpi_call` (`acpi-call-dkms` из
   Ubuntu). Oneshot-скрипт при загрузке и после сна. Проверить, в каких
   режимах прошивка применяет кривую. В BIOS v29 кривая и custom TDP
   конфликтовали, исправлено в 29.1+.

Начинаем с варианта 1 (решение 9); остальные — только если не устроят шум
или температура.

# 3. Как это ложится на wsconfig

## 3.1 Хост

`nix/hosts/legiongo/` (решение 8):

```text
facts.nix  hostname = "legiongo", user king, wsconfig,
           hardware = "legion-go", boot = "grub", rootUuid,
           kernelParams: quiet splash bluetooth.disable_ertm=1
                         cpufreq.default_governor=powersave
                         zswap.enabled=1 zswap.compressor=zstd
                         — для обоих ядер GRUB (2.1, 2.6)
apt.txt    openssh-server, amd64-microcode, steam-installer (i386),
           sddm, gamescope, lm-sensors, evtest,
           linux-xanmod-x64v3 (источник и ключ — файлы системного слоя)
```

i386 multiarch для Steam: `bootstrap.sh` должен уметь
`dpkg --add-architecture` по строке apt-списка. Пакеты, собранные локально,
`ws check apt` получает от владельца, а не из списка.

## 3.2 Профиль железа `system/hardware/legion-go.nix`

```text
файлы   sysctl.d, udev (I/O), hwdb (F16),
        PipeWire/WirePlumber 83E1, logind.conf.d, modprobe.d,
        sddm.conf.d (Wayland, autologin в GNOME, Relogin), polkit,
        /usr/libexec/os-session-select, platform.toml steamos-manager
        ([session] desktop = "gnome.desktop")
        udev: RGB стиков off (2.8)
units   inputplumber, steamos-manager, powerbuttond (user), sddm,
        power-profiles-daemon (штатный); gdm3 — masked
```

`ws system apply` ставит файлы, как на mbp16. Проверки T2 и dGPU здесь не
выполняются, это уже работает (`ws fact hardware`).

## 3.3 Игровой слой: `gaming/`, владелец `wsgame`

По правилу «Nix доставляет, владельцы остаются»: источники и версии
объявлены в Nix (`gaming/sources.nix`: tag или commit плюс sha256), а
собирает и ставит владелец.

```text
wsgame build     podman, Ubuntu 26.04 (как t2bce и i915-psr): steamos-manager
                 (device-файл 83E1 без TDP и профиля, 2.4), MangoHud с
                 mangoapp, powerbuttond → .deb
wsgame fetch     по sha256: InputPlumber .deb релиза; extest .so и
                 gamescope-session(-steam) — обёрнутые в .deb
wsgame install   apt install ./*.deb: файлы принадлежат dpkg, удаление чистое
wsgame check     пакеты и версии, сервисы, DBus steamos-manager, firmware-
                 attributes, цели InputPlumber, SDDM-файлы
wsgame mode game|desktop   то же, что steamosctl (для терминала и ssh)
```

Новые upstream-версии показывает `ws update`, переход — правка
`sources.nix`. Toolchains на host не ставятся.

## 3.4 Слои, зависящие от хоста

Факты добавляются только там, где Legion Go действительно нужно другое
значение (правило фазы 6):

- **xremap.** Не запускать в gamescope-сессии: сейчас его тянет
  `graphical-session.target`, а её поднимает и `gamescope-session-plus`.
  Добавить в `--ignore` виртуальные устройства InputPlumber и Steam, а
  также клавиатуру FPS-режима контроллера.
- **Клавиатурный слой.** Шаги для GDM (EN на экране входа) при SDDM не
  применять, раскладку экрана входа задаёт SDDM.
- **GNOME.** Масштаб 2.0, ярлык «Return to Game Mode» (`steamosctl
  switch-to-game-mode`), экранная клавиатура. Режимы питания — штатный
  переключатель (PPD).
- **Flatpak.** Свой список на хост. Steam здесь нативный, flatpak-версия не
  ставится.
- **Distrobox, Windows, VM.** Какие слои ставить, выбирается отдельно до
  установки (решение 5). Если VM не нужны, `bootstrap.sh` должен уметь
  обходиться без `@vms` и libvirt.
- **Масштаб в факты хоста.** DPI Wine (LogPixels 192 при 200%), масштаб
  Claude и AnyDesk.
- **Проверки.** `ws check gaming`; verify — связи InputPlumber ↔
  steamos-manager ↔ SDDM ↔ xremap, PPD — единственный владелец
  `platform_profile`.

## 3.5 Диск

Btrfs по `helpws rebuild`: `@`, `@home`, `@cache`, `@tmp`, `@log`, `@nix`,
`@swap` (swapfile 16 ГБ под zswap, 2.6). Отдельно — `@steam` в
`~/.local/share/Steam`: клиент, библиотека, compatdata и shadercache вне
Timeshift и backup, по аналогии с `@vms`. Отдельного backup сохранений нет
(решение 7): что не в Steam Cloud, живёт только на устройстве. microSD —
вторая библиотека Steam; форматирование из Game Mode (скрипты
steamos-manager) — позже.

# 4. Этапы

Каждый этап заканчивается `ws checkpoint create NAME`. Перед ядром, загрузкой
и питанием делается снимок Timeshift (главное правило roadmap).

0. **Устройство до установки.** Windows на нём уже нет (решение 1), поэтому
   Legion Space недоступен.
   - Версия BIOS — в BIOS setup. Целевая — N3CN40WW (январь 2026).
     N3CN42WW (июнь 2026) Lenovo отозвала после случаев, когда устройство
     переставало загружаться: её не ставить. Обновить BIOS теперь можно
     только через fwupd (если Lenovo публикует капсулы в LVFS; проверить на
     этапе 3) или с Windows на USB.
   - Прошивка контроллеров остаётся как есть: fwupd для Go 1 её не
     поддерживает (раньше предлагалась прошивка Go 2, fwupd #9734), а
     Legion Space недоступен.
   - В BIOS: UMA frame buffer задать вручную (6–8 ГБ — рекомендация
     legion-go-tricks против мерцания при авто), разрешить загрузку с USB.
     Secure Boot выключен.
   - Нужны USB-C хаб, клавиатура и флешка.
1. **Репозиторий на mbp16, без устройства.** Хост `legiongo`, профиль
   `legion-go`, факты для слоёв из 3.4, каркас `gaming/` и `wsgame`, страница
   `helpws gaming`. На mbp16 ничего не меняется: home generation, дерево
   system и man — те же пути store, `ws check` без FAIL. CI зелёный.
2. **Сборка пакетов в podman на mbp16.** Собрать `.deb` для
   steamos-manager, MangoHud с mangoapp и powerbuttond. Скачать
   InputPlumber и extest. Проверить, что пакеты ставятся и снимаются в чистом
   контейнере Ubuntu 26.04.
3. **Ubuntu на Legion Go.** Установка 26.04 с USB на весь диск,
   subvolumes, как в фазе 6. Инвентарь в `docs/history/` через `ws collect`
   и вручную:
   - DMI;
   - `lspci -nnk`, `lsusb`;
   - `/sys/class/firmware-attributes/lenovo-wmi-other-0/attributes/`;
   - варианты `platform_profile`;
   - hwmon, iio (акселерометр, свет);
   - `aplay -l`, `pw-cli ls Node`;
   - `libinput list-devices`;
   - `grep LENOVO_WMI /boot/config-*`, `SCHED_CLASS_EXT`;
   - `fwupdmgr get-devices`: видит ли fwupd BIOS. Без Windows BIOS больше
     нечем обновлять.
4. **База wsconfig (GDM, GNOME, без игрового слоя).** `bootstrap.sh` →
   `ws system apply` → `ws apply` → `ws check`, как в `helpws rebuild`.
   Поворот, касания, Wi-Fi и Bluetooth работают.
5. **Профиль железа.** Ядро (решение 4), kargs, аудио, hwdb, sysctl,
   swapfile и zswap, I/O. Проверить:
   - s2idle (`amd_s2idle.py`), яркость, автоповорот, батарея;
   - режимы PPD → `platform_profile` → вентилятор; hwmon вентилятора;
   - лимит заряда (`charge_types`, ядро 7.2+);
   - zswap: включён, zstd, swapfile активен; governor после загрузки
     (powersave до PPD, затем по режиму PPD);
   - звук после сна (известный шум первые ~30 с).
6. **Game Mode.**
   - InputPlumber; Steam (первый запуск в GNOME); gamescope и сессия;
     steamos-manager; mangoapp; powerbuttond.
   - Переход GDM → SDDM, autologin в GNOME (решение 2).
   - Проверить: переключение Game Mode ↔ GNOME в обе стороны; QAM без
     ползунка TDP, режим PPD не сбрасывается; оверлей; сон из Game Mode;
     кнопка питания.
   - RGB стиков выключен и остаётся выключенным после переподключения и
     сна.
   - Контроллеры: снятые и пристёгнутые, гироскоп, задние кнопки, Legion
     L/R.
   - Экран 60/144 Гц; внешний монитор по USB-C.
7. **Рабочий стол на портативном.** GNOME 200%, экранная клавиатура,
   контроллер как мышь (InputPlumber или Steam с extest),
   xremap вне Game Mode. Flatpak и Distrobox — по решению 5.
8. **Recovery и backup.** Timeshift и пункты GRUB, проверка отката.
   `wsbackup` на Unraid без `@steam` — позже, отдельным шагом.
9. **Опционально, каждое — с замером до и после.** Decky Loader, scx_lavd,
   dmemcg-booster, hibernate (swapfile уже есть: `resume=`/`resume_offset`
   в facts), Lutris или Heroic, эмуляторы.

# 5. Решения

Приняты пользователем 2026-10-10:

1. **Windows нет** (на устройстве её уже нет). Весь SSD — под Linux; BIOS и
   прошивка контроллеров — см. этап 0.
2. **Загрузка в GNOME** через SDDM с autologin. Game Mode включается из
   GNOME («Return to Game Mode»), обратно — «Switch to Desktop» в Steam.
3. **Steam нативный.**
4. **Ядро — XanMod MAIN x64v3**, своё не собираем; generic Ubuntu запасным
   пунктом в GRUB. AppArmor не нужен; `cpufreq.default_governor=powersave`
   (2.1).
5. **Набор слоёв** выбирается в отдельной сессии, до установки.
6. **Питание — PPD.** steamos-manager без TDP и профиля (2.4).
7. **Отдельного backup сохранений нет.**
8. **Хост — `legiongo`.**
9. **Без HHD.** Вентилятор — сначала по умолчанию (прошивка); RGB стиков —
   разбираемся после установки (2.8).
10. **Swap — zswap** со swapfile в `@swap`, без zram (2.6).

Secure Boot на устройстве выключен.

Открытых решений перед этапом 1 нет, кроме набора слоёв (5). Размер
swapfile — 16 ГБ по рекомендации (2.6), если не решим иначе.

# 6. Риски

- BIOS N3CN42WW: не ставить ни через fwupd, ни с Windows на USB.
- Windows нет: BIOS обновляется только через fwupd (если Lenovo публикует
  капсулы в LVFS; проверить на этапе 3) или с Windows на USB.
- Прошивка контроллеров через fwupd на Go 1: не обновлять.
- Без Mesa Valve может не работать ограничитель FPS gamescope (2.2).
- gamescope 3.16.20 старше того, на что рассчитан текущий клиент Steam.
  Запасной путь — сборка upstream или форка OGC в podman.
- SDDM вместо GDM: экран входа и lock screen GNOME ведут себя иначе, а шаги
  клавиатурного слоя для GDM здесь не работают.
- Ограничение AppArmor на user namespaces в generic-ядре (фаза 6): нативный
  Steam (pressure-vessel) проверить в первую очередь. На XanMod AppArmor не
  активен, ограничения нет — касается только запасного generic-ядра.
- `hid-lenovo-go` (ядро 7.1+) вместе с InputPlumber: проверить гироскоп и
  кнопки (в Bazzite Deck 44 у Go 1 не работает гироскоп).
- xremap может захватить виртуальные устройства InputPlumber (3.4).
- Звук после сна, автояркость. Bazzite и legion-go-tricks считают это
  известными недочётами.

# Источники

- Bazzite: <https://github.com/ublue-os/bazzite> (Containerfile,
  `system_files/deck`, `system_files/desktop/shared/usr/libexec/hwsupport`)
- Bazzite Handheld Wiki, Legion Go:
  <https://docs.bazzite.gg/Handheld_and_HTPC_edition/Handheld_Wiki/Lenovo_Legion_Go/>
- Ядро OGC: <https://github.com/OpenGamingCollective/linux>
- steamos-manager (OGC): <https://github.com/OpenGamingCollective/steamos-manager>
- gamescope-session (OGC): <https://github.com/OpenGamingCollective/gamescope-session>
- InputPlumber: <https://github.com/ShadowBlip/InputPlumber>
- legion-go-tricks: <https://github.com/aarron-lee/legion-go-tricks>
- fwupd #9734: <https://github.com/fwupd/fwupd/issues/9734>
- HHD: <https://github.com/hhd-dev/hhd>
- Zabbly: <https://github.com/zabbly/linux>, индекс
  `pkgs.zabbly.com/kernel/stable/dists/resolute`; XanMod: <https://xanmod.org/>,
  индекс `deb.xanmod.org/dists/resolute`,
  конфиг <https://gitlab.com/xanmod/linux> (`CONFIGS/x86_64/config`, 7.2);
  Liquorix: <https://liquorix.net/>, <https://github.com/damentz/liquorix-package>
- Ядро Ubuntu: `git.launchpad.net/~ubuntu-kernel/ubuntu/+source/linux/+git/resolute`,
  тег `Ubuntu-7.0.0-38.38` (`debian.master/config/annotations`)
- `hid-lenovo-go`: `Documentation/ABI/testing/sysfs-driver-hid-lenovo-go` (7.2)
- amd-pstate и выбор policy: `drivers/cpufreq/amd-pstate.c`,
  `drivers/cpufreq/cpufreq.c` (7.2)
- Ubuntu 26.10 с Linux 7.3:
  <https://www.phoronix.com/news/Ubuntu-26.10-With-Linux-7.3>
- Отзыв BIOS N3CN42WW:
  <https://www.notebookcheck.net/Lenovo-quietly-removes-BIOS-update-that-bricked-Legion-Go-handhelds-but-affected-users-are-still-left-with-unusable-devices.1363023.0.html>
