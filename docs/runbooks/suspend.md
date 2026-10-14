title: ws-suspend
section: 1
date: 2026-10-02
source: Workstation
volume: User Commands

# UBUNTU T2 SUSPEND

## Текущее состояние

```text
MacBookPro16,1
T2 kernel 7.2.7-1-t2-resolute
sleep        deep / S3 only
cmdline      intel_iommu=on iommu=pt pm_async=off
             + «Ubuntu»: ws.dgpu=off modprobe.blacklist=amdgpu
                         pcie_aspm=force pcie_aspm.policy=powersave
t2bce        0.07-nostatefix1 (локальная сборка, updates/t2bce)
Touch Bar    родной режим (см. helpws touchbar)
AMD dGPU     ws.dgpu=off: выключена, убрана с шины PCI, порт CPU запаркован
hibernate    /swap/swapfile 32G, resume=UUID=… resume_offset=… (host.toml)
крышка, Suspend          suspend-then-hibernate: 24 ч S3, затем hibernate
кнопка питания, Hibernate  hibernate
```

Слой состоит из шести частей:

```text
deep-only sleep        systemd никогда не откатывается на s2idle
Broadcom Wi-Fi guards  ASPM off на время сна, без D3cold
t2bce fix              no-state fallback не роняет ядро
dGPU off the bus       amdgpu не участвует в S3 с выключенной картой
Thunderbolt ACPI seed  resume ~3 с вместо ~23 с
hibernate              стек T2 снимается до образа и поднимается после
```

Всё управляется командой `ws suspend`:

```console
ws suspend status
ws suspend apply
ws suspend t2bce-build [KERNEL]
ws suspend t2bce-install [KERNEL]
ws suspend t2bce-rollback [KERNEL]
ws suspend swap-setup [SIZE]
ws suspend check
```

`ws suspend apply` — обёртка над `ws system apply`: ставит все системные
файлы хоста из `system` (Nix), а не только слой suspend; проверка
без изменений — `ws system diff`.

## Deep-only sleep

```text
/etc/systemd/sleep.conf.d/80-deep-only.conf
  SuspendState=mem
  MemorySleepMode=deep
```

По умолчанию systemd после неудачного S3 пробует `freeze` (s2idle). На T2
s2idle виснет. С этим файлом неудачный suspend просто возвращает в рабочую
сессию.

## Broadcom BCM4364

```text
/usr/lib/systemd/system-sleep/80-broadcom-aspm       hook systemd-sleep
/usr/local/sbin/broadcom-aspm-suspend-guard          disable / restore
/etc/systemd/system/broadcom-aspm-restore.service    restore после resume
/etc/udev/rules.d/70-bcm4364-no-d3cold.rules         d3cold_allowed=0
```

Перед сном guard сохраняет ASPM-биты Wi-Fi (`05:00.0`) и root port
(`00:1c.0`) и выключает ASPM; после resume `broadcom-aspm-restore.service`
ждёт стабильный `brcmfmac` и возвращает L1. Цель — избежать
`brcmf_pcie_pm_enter_D3: Timeout on response for entering D3 substate`.
После установки guard таймаутов D3 не было.

Hook лежит в `/usr/lib/systemd/system-sleep/`, потому что systemd-sleep
читает hooks оттуда.

## AMD dGPU при ws.dgpu=off

```text
/usr/local/sbin/ws-dgpu-off                  удаление карты с шины PCI и снятие питания
/etc/systemd/system/ws-dgpu-off.service      при загрузке, до GDM
/usr/local/sbin/ws-dgpu-park                 «парковка» порта CPU 00:01.0, как в macOS
/usr/lib/systemd/system-sleep/70-ws-dgpu-park  она же после resume
```

При загрузке с `ws.dgpu=off` (rEFInd «Ubuntu») `ws-dgpu-off` убирает AMD с
шины PCI и выключает её. С 2026-10-01 в этом пункте ещё и
`modprobe.blacklist=amdgpu`: драйвер карту не трогает вовсе, и скрипт

1. убирает весь пакет с шины (`echo 1 > .../0000:01:00.0/remove`), пока карта
   включена и без драйвера (HDMI-аудио `03:00.1` с `snd_hda_intel` уходит
   вместе с ним, как обычное горячее удаление);
2. снимает питание портом gmux `0x50` (1, 10 мс, 0) — то же, что `apple-gmux`
   делает при vga_switcheroo `OFF`;
3. паркует порт CPU (`ws-dgpu-park`, ниже).

Так ~0,8 с вместо ~11 с (инициализация `amdgpu` только ради `OFF`; GDM ждёт
этот скрипт). После S3 `apple-gmux` питание сам не снимает (`gmux_resume`
повторяет только `OFF`, а его не было), но хук `70-ws-dgpu-park` всегда
заканчивает снятием питания. Проверено 2026-10-01: PC7 ~78 %, рельс AMD
`PG0R` ~0,09 W.

Без `modprobe.blacklist=amdgpu` скрипт идёт старым путём через vga_switcheroo
(ниже): он и описывает, почему карту нельзя оставлять на шине.

Без удаления S3 не работает. `amdgpu` в `suspend_noirq` для S3 всегда делает
`MODE1 reset` и не проверяет, что карта выключена (так и в upstream).
Регистры выключенной карты читаются как `ffffffff`, сброс падает, `amdgpu`
возвращает `-22`, и S3 прерывается:

```text
amdgpu 0000:03:00.0: psp reg (0x16080) wait timed out ... read: ffffffff
amdgpu 0000:03:00.0: GPU mode1 reset failed
amdgpu 0000:03:00.0: PM: failed to suspend noirq: error -22
```

Откат прерванного S3 роняет оба xHCI-контроллера Thunderbolt (`HC died`), и
через несколько минут система погибает без единой строки в логе.

Включать карту на время сна нельзя. Она стоит за PCIe-коммутатором внутри
пакета Navi 14 (`01:00.0`, `02:00.0`), который теряет конфигурацию вместе с
питанием: после `ON` карта недоступна (`Unable to change power state from
D3cold to D0`), `PSP create ring failed`. У автора
поддержки gmux для T2 на MacBookPro16,1 то же и после `pci rescan` (LKML,
«apple-gmux: support MMIO gmux type on T2 Macs», 2023-02).

Поэтому после `OFF` скрипт убирает с шины весь пакет, начиная с `01:00.0`:
драйверы карты в S3 не участвуют, а `apple-gmux` после resume сам снова
снимает с неё питание (`gmux_resume`). Порядок важен:

1. Сначала HDMI-аудио карты (`03:00.1`), пока карта включена. При `OFF`
   vga_switcheroo блокирует его ALSA-карту (`card->shutdown`), и удаление
   после `OFF` навсегда виснет в `snd_card_free` (процесс в состоянии D;
   спать после этого нельзя, перезагрузка виснет в конце).
2. `OFF` и проверка: конфигурационное пространство карты и `01:00.0`
   читается как `ffff`.
3. `echo 1 > /sys/bus/pci/devices/0000:01:00.0/remove`.
4. `ws-dgpu-park` (ниже).

### Парковка порта CPU (ws-dgpu-park)

`apple-gmux` только снимает питание. Порт CPU `00:01.0` (ACPI `PEG0`)
после этого ищет устройство и держит пакет CPU в PC2/PC3 (helpws plan-t2,
раздел 1: −0,9 W на CPU и PC7 ~80 % после парковки). macOS перед снятием
питания вызывает ACPI `GFX0.PWRD(1)` → `PUPD(0)` (SSDT `PEG0GFX0`): линк в
Gen1, LTR выкл., запрос L2 (`Q0L2`, 0x248 бит 7), затем PHY порта выкл.
(`RC20` 0xC20[5:4], `RC38` 0xC38 бит 3, `BND0..3` бит 31 0x91C…0x97C).
`ws-dgpu-park` делает то же через `setpci` и порт gmux `0x50`
(`/sys/kernel/debug/apple_gmux/selected_port{,_data}`): на ~0,5 с включает
карту, ждёт тренировки линка, L2, PHY, снимает питание (`0x50`: 1, 10 мс, 0).

- Только после удаления карты с шины: обращение ядра к карте за линком в L2
  вешает машину.
- Запаркованный порт заново не тренируется: повтор в той же загрузке ничего
  не делает. S3 порт сбрасывает — поэтому хук `70-ws-dgpu-park` после
  resume.
- Ошибка парковки не фатальна: карта выключена, пакет просто остаётся в PC3.
- t2gmux (KaiT2en, `PWRD` из драйвера) на 16,1 пока не подходит: включение
  выключает машину, а после его `OFF` карту нельзя убрать с шины
  (helpws plan-dgpu).

Если карта уже выключена, скрипт отказывается работать. Запуск только до GDM:
vga_switcheroo при `OFF` открытых клиентов не проверяет.

После удаления `amdgpu` до перезагрузки остаётся клиентом vga_switcheroo
(`1:DIS: :Off:0000:03:00.0` в `/sys/kernel/debug/vgaswitcheroo/switch`).
Писать туда нельзя: `ON` включает питание gmux и даёт Oops в
`amdgpu_switcheroo_set_state`, после чего блокировка vga_switcheroo занята
навсегда.

## ASPM

С 2026-10-01 пункт «Ubuntu» снова грузится с `pcie_aspm=force
pcie_aspm.policy=powersave` (`refindDefaultParams` в `host.toml`); «Ubuntu
(AMD)» и GRUB (recovery) — без них. Прошивка объявляет, что ASPM не
поддерживается (FADT), и оставляет его выключенным на всём Thunderbolt;
с `force` ядро берёт ASPM себе: L1 на Thunderbolt (~1,15 W), Clock PM и L0s
на остальных линках (ещё ~0,6 W); L1.1/L1.2 политика `powersave` выключает,
`powersupersave` не экономнее (helpws plan-t2, раздел 1).

Убирали его 2026-09-25 из осторожности: все отказы T2 случились с forced
ASPM, но вместе с Touch Bar в режиме дисплея; с родным Touch Bar и forced
ASPM было 16 циклов S3 без сбоев (helpws history-suspend), 2026-10-01 — ещё
циклы с t2bce 0.07-nostatefix1. `ws suspend check` предупреждает, если в
пункте «Ubuntu» параметров нет; `ws system check` — если вернётся
`/etc/default/grub.d/90-pcie-aspm.cfg` (forced ASPM для GRUB/recovery не
нужен).

## Thunderbolt: быстрый resume

```text
/usr/local/sbin/ws-tb-acpi-seed               читает регионы ACPI Thunderbolt
/etc/systemd/system/ws-tb-acpi-seed.service   при загрузке, до первого сна
```

До 2026-10-01 каждый выход из S3 занимал ~23 с (так было с первой
загрузки, с AMD и без неё). Трассировка (`pm_print_times` +
`function_graph`): ~20 с уходят в `pci_pm_resume_noirq` двух Titan Ridge —
мост `UPSB` (06:00.0, 7c:00.0) ~6,7 с и NHI (08:00.0, 7e:00.0) ~3,3 с,
последовательно из-за `pm_async=off`. Это `_PS0` прошивки (SSDT,
`OSDW()` = Darwin): `PCED` и `CRMW` ходят в почтовый ящик TB через
PCI_Config регионы `UPSB` (`H530`, `H548`, `A1E0`..`A1E2`).

Причина в ACPICA: адрес PCI региона вычисляется один раз, при первом
обращении, и `acpi_hw_get_pci_device_info()` (`drivers/acpi/acpica/hwpci.c`)
берёт для моста его Primary Bus Number. Первое обращение к регионам `UPSB`
случается в первом resume, когда мост только что получил питание и
Primary Bus ещё 0: регионы до конца загрузки смотрят на хост-мост 00:00.0
(`UPSB.AVND` = `3EC48086` вместо `15EA8086`, `UPSB._BBN` = 0). Почтовый
ящик там не отвечает, `CIOR`/`CIOW` ждут тайм-аут в цикле `Stall`, `CRMW`
повторяет 5 раз — отсюда и ~16 с занятого CPU в `systemd-suspend.service`.
Исправление в ACPICA предложено, не принято:
open-acpica/acpica#1235 (omarchy-pkgs несёт его патчем `0771`).

`ws-tb-acpi-seed` после загрузки читает по одному полю в каждом регионе
поддеревьев `\_SB.PCI0.PEG1/PEG2.UPSB` через отладчик ACPI ядра
(debugfs `acpi/acpidbg`, только чтение), пока номера шин настроены: ACPICA
запоминает правильные адреса, и `_PS0` проходит за доли секунды. Скрипт
сверяет `AVND` с ID устройства из sysfs и падает, если адрес уже
испорчен (запуск после сна): тогда до перезагрузки resume медленный.
Проверено 2026-10-01: фаза ACPI 20,1 с → 1,0 с, ядро от пробуждения до
`suspend exit` ~3 с; оба TB, их xHCI (линк x4) и домены bolt на месте.
Порты USB-C с подключённым устройством после пробуждения работают
(пользователь, 2026-10-01).

Состояние вручную:

```console
journalctl -b -u ws-tb-acpi-seed
sudo /usr/local/sbin/ws-tb-acpi-seed    # повторная проверка адресов
```

## t2bce: отказ stateful suspend

Иногда bridgeOS отвечает на запрос сохранения состояния отказом:

```text
t2bce_core: remote rejected stateful suspend payload
```

Штатный `t2bce` 0.07 после этого уходит в no-state fallback: удаляет VHCI,
пока очереди событий и mailbox уже на паузе, поэтому команды разборки не
получают ответа (`Possible desync`, `command queue timeout`,
`SQ/CQ unregister failed`). После resume `CQ registration failed`, и IRQ-поток
`bce_dma` падает с NULL dereference в `t2bce_dma_reserve_submission`.
Система намертво зависает (три таких случая: `helpws history-suspend`).

Upstream:

```text
t2linux/T2-Debian-and-Ubuntu-Kernel#215   отчёт (автор t2bce: fallback будет удалён)
deqrocks/t2bce#9                          черновик исправления fallback
```

### Локальный патч

```text
system/kernel/t2bce/nostate-fix.patch   патч к drivers/staging/t2bce из linux-t2-patches 1001
system/kernel/t2bce/t2bce.nix           версия ядра -> коммит linux-t2-patches
                                        (ws switch собирает ~/.local/share/workstation/t2bce/sources.json)
```

Патч:

1. переносит оставшуюся часть deqrocks/t2bce#9: транспорт и очереди событий
   VHCI открываются на время no-state teardown, ошибки прерывают suspend;
2. добавляет проверку NULL в `t2bce_core_reserve_submission()`;
3. делает `t2bce_core.stateful_sleep` параметром модуля (по умолчанию `Y`),
   чтобы no-state путь можно было проверить по команде;
4. помечает версии `0.07-nostatefix1` / `0.02-nostatefix1`.

Пересобираются все пять модулей `t2bce_*`, чтобы совпадали версии символов.
Сборка идёт в одноразовом контейнере podman (`ubuntu:` релиза хоста из
`/etc/os-release`) с заголовками
`/usr/src/linux-headers-KERNEL`; результат — `~/.local/share/workstation/t2bce/KERNEL/`.
Модули ставятся в `/lib/modules/KERNEL/updates/t2bce`: depmod ищет в
`updates` раньше, чем в `kernel`. Пакеты ядра не меняются.

### Проверка no-state пути

Сохранить работу, затем:

```console
echo N | sudo tee /sys/module/t2bce_core/parameters/stateful_sleep
systemctl suspend
```

После выхода из сна клавиатура, трекпад и Touch Bar появляются через пару
секунд. В `journalctl -b -k` должны быть `no_state_fallback=1` и
`path=no-state` и не должно быть `desync`, `queue timeout`, `BUG`/`Oops`.
Затем обязательно вернуть:

```console
echo Y | sudo tee /sys/module/t2bce_core/parameters/stateful_sleep
```


## Hibernate

### Почему стек T2 снимается

У `t2bce` есть только колбэки S3 (`.suspend/.resume`), для hibernation
(`freeze/thaw/poweroff/restore`) их нет. После восстановления образа T2
сброшен, очередей драйвера в нём нет: клавиатура, трекпад, Touch Bar и звук
мертвы (t2linux/T2-Debian-and-Ubuntu-Kernel#213, t2linux/kernel#22). Поэтому
перед записью образа стек T2 снимается, после восстановления поднимается,
и драйвер стартует как при загрузке:

```text
ws-t2-detach down   rmmod t2bce_vhci, unbind t2bce_audio (04:00.3), unbind t2bce_core (04:00.1)
ws-t2-detach up     bind core, 1 с, bind audio, modprobe t2bce_vhci,
                    затем rebind hid-appletb-kbd, когда появится appletb_backlight
                    (иначе «Failed to get backlight device», Touch Bar без подсветки)
ws-t2-detach cycle  down, 5 с, up: проверка без hibernate
```

Кто вызывает:

```text
60-ws-t2-hibernate     хук systemd-sleep: pre → down, post → up; hibernate,
                       hybrid-sleep и шаг hibernate в suspend-then-hibernate
                       (SYSTEMD_SLEEP_ACTION=hibernate); не вокруг S3
ws-t2-nofreeze.conf    SYSTEMD_SLEEP_FREEZE_USER_SESSIONS=0 для служб с hibernate
95ws-t2-resume         модуль dracut: в initrd загрузки с образом T2 снимается
                       до загрузки образа и поднимается, если образа нет
```

systemd-sleep по умолчанию замораживает `user.slice` до хуков. Unbind звука
ждёт (`snd_card_free`), пока PipeWire закроет карту, а замороженный PipeWire
её не закроет: unbind висит в D state, заморозка задач падает через 20 с,
hibernate отменяется, клавиатура и трекпад остаются мёртвыми. Сеансы поэтому
не замораживаются (ядро всё равно замораживает все задачи перед образом);
`ws-t2-detach down` отказывается работать при замороженном `user.slice`.

Initramfs собирает dracut (`update-initramfs` — его обёртка, файлы в
`/etc/initramfs-tools` не читаются). Ubuntu кладёт драйверы клавиатуры
(`t2bce`) в initrd, поэтому initrd загрузки с образом поднимает T2 — его
нужно снять до загрузки образа. Модуль `resume` dracut в hostonly-режиме
попадает в initrd, только если `resume=` уже был в cmdline при сборке;
`ws-hibernate.conf` добавляет его всегда.

### Swap и resume

```console
ws suspend swap-setup 32g    # @swap → /swap, /swap/swapfile, fstab; печатает offset
```

Swapfile — в отдельном subvolume `@swap` (без снапшотов, без CoW).
Параметры resume — в `nix/hosts/mbp16/host.toml` (`kernelParams`, все пункты
rEFInd и GRUB):

```text
resume=UUID=0cfd2add-849f-47b9-865d-2ac821ca529c   корневая ФС
resume_offset=31286754                              btrfs inspect-internal map-swapfile -r
```

После пересоздания swapfile offset меняется: обновить `host.toml`,
`ws system apply`, перезагрузка. После изменения модуля dracut или
`ws-t2-detach` — `sudo update-initramfs -u` (`ws suspend check`
предупреждает, если initrd старше).

### Когда

```text
крышка (от батареи и от сети)   suspend-then-hibernate   logind.conf.d/ws-sleep-keys.conf
Suspend в меню GNOME            suspend-then-hibernate   systemd-suspend.service.d/ws-suspend-then-hibernate.conf
systemctl suspend               suspend-then-hibernate   то же
Hibernate в меню GNOME          hibernate                workstation-hibernate@local
кнопка питания (Touch ID)       hibernate                power-button-action (gnome/gnome.nix), вне сеанса logind
```

Пункт Hibernate (`workstation-hibernate@local`) есть только на хостах с
`resume=` в `kernelParams` (`gnome/gnome-extensions.nix`): systemd находит
swapfile и без него, и на другом хосте CanHibernate предложил бы
непроверенную гибернацию.

Обычного S3 без перехода в hibernate больше нет: GNOME вызывает logind
`SuspendWithFlags`, и `systemd-suspend.service` переопределена на
`systemd-sleep suspend-then-hibernate`.

`85-ws-hibernate-delay.conf`: `HibernateDelaySec=24h`,
`SuspendEstimationSec=24h`. Через 24 ч S3 машину будит RTC, она уходит в
hibernate. Встроенное правило systemd 259, не отключается: на батарее, если
по замеренной скорости разряда заряд дойдёт до ~5% раньше 24 ч, systemd
будит машину раньше и уходит в hibernate. Скорость он замеряет только в
suspend-then-hibernate на батарее (заряд до и после S3, целые проценты) и
хранит в `/var/lib/systemd/sleep/`. Пока замера нет, первый такой сон —
24 ч без учёта заряда; при ~1,2 W в S3 риск только при заряде ниже
примерно трети.

Ubuntu запрещает hibernate пользователю (`com.ubuntu.desktop.rules`,
policykit-desktop-privileges). `50-ws-hibernate.rules` в
`/usr/local/share/polkit-1/rules.d` разрешает его активной локальной
сессии: polkit читает правила всех каталогов по имени файла, первое
сработавшее побеждает. `/etc/polkit-1/rules.d` пользователю не читается,
и `ws system check` не смог бы его сверить.

### Аварийный выход

Если загрузка с образом виснет — при следующем включении в rEFInd на
пункте F2 (или Insert): подменю, ещё раз F2 — правка строки параметров;
добавить `noresume`: система загрузится начисто,
образ будет проигнорирован (несохранённое в нём пропадёт). Ядро сбрасывает
подпись образа, когда читает его, поэтому зависание на resume не
повторяется в цикле.

Hibernate проверен только с пунктом rEFInd «Ubuntu» (`ws.dgpu=off`).
После hibernate включать тот же пункт. Восстановление в «Ubuntu (AMD)» не
проверено: ядро из образа считает AMD убранной с шины, а та загрузка её
включает.

## Обновление ядра

`linux-t2` заморожен (`apt-mark hold`): модули в `updates/` привязаны к одной
версии ядра, и новое ядро без пересборки загрузило бы штатный `t2bce`.
`ws suspend status` показывает `held`, `ws-workstation-verify` предупреждает,
если hold снят. Обновление — осознанный шаг:

1. Проверить, вошло ли исправление в upstream (#215, deqrocks/t2bce#9,
   `linux-t2-patches`). Если да — локальный патч больше не нужен.
2. Если нет — найти коммит `linux-t2-patches`, из которого собрано новое
   ядро, добавить его в `sources` в `system/kernel/t2bce/t2bce.nix` и
   выполнить `ws switch`.
3. Снять hold, обновить ядро, собрать и поставить модули, вернуть hold:

```console
sudo apt-mark unhold linux-t2
sudo apt install linux-t2
ws suspend t2bce-build NEW_KERNEL
ws suspend t2bce-install NEW_KERNEL
ws-psr build NEW_KERNEL
ws-psr install NEW_KERNEL
sudo apt-mark hold linux-t2
```

`ws-psr` — i915 с PSR на панели Apple (helpws plan-t2, раздел 1) из того же
коммита `linux-t2-patches`. Если `apple-psr.patch` не накладывается на новое
ядро, работает штатный i915 без PSR (экран ~+1 W), остальное не страдает.

`apt autoremove` после обновления не запускать: предыдущее ядро остаётся
пунктом GRUB для recovery.

Если патч не накладывается на новую версию `t2bce`, его нужно перенести
вручную. Предыдущее ядро с исправленными модулями остаётся в rEFInd.

## Откат

```console
ws suspend t2bce-rollback
sudo reboot
```

## Проверка

```console
ws suspend status
ws suspend check
ws-workstation-verify     # ядро ↔ t2bce
```

Ожидается:

```text
mem_sleep                 s2idle [deep]
cmdline                   «Ubuntu»: pcie_aspm=force pcie_aspm.policy=powersave
AMD CPU port              parked (ws-dgpu-park)
Thunderbolt ACPI          seeded (ws-tb-acpi-seed)
t2bce_core                0.07-nostatefix1, stateful_sleep=Y
runtime files             OK
```

`ws suspend check`, раздел Hibernation: swapfile активен и не меньше
MemTotal, `/sys/power/resume` выставлен initrd, `resume_offset` совпадает
с cmdline, initrd не старше модуля dracut и `ws-t2-detach`.

## Подтверждённый baseline

2026-09-25/26:

```text
stateful S3 cycle                          OK
forced no-state cycle                      OK
Touch Bar native mode S3 cycles            OK
модули из репозитория == установленные      srcversion совпадает
```

2026-09-28:

```text
S3 с AMD, убранной с шины (ws-dgpu-off вручную)       OK
S3 с AMD, убранной с шины при загрузке (8 минут)      OK
```

2026-10-02, hibernate (образ 9–10,5 ГБ, ~4 с на подъём T2):

```text
ручной hibernate                                    3/3 OK (обычный, со звуком, с ВМ на батарее)
suspend-then-hibernate (RTC через 2 мин → S4)       OK
Hibernate в меню, крышка 30 с (S3), крышка 4 мин (S4),
Suspend в меню (S4), кнопка питания (S4)             OK
```

После каждого: клавиатура, трекпад, Touch Bar с подсветкой, 2 звуковые
карты T2, Wi-Fi, Bluetooth, порт AMD снова запаркован. Работавшая ВМ
пережила hibernate.

После resume оба xHCI Thunderbolt пишут `xHC error in resume, USBSTS 0x401,
Reinit` и работают дальше; так же было и с включённой AMD.
`71-tb-xhci-awake.rules` держит их вне runtime suspend (см. `helpws
workstation`, T2 HARDWARE); на системный S3 это не влияет.

## Source of truth

```text
bin/ws-suspend
system/kernel/t2bce/nostate-fix.patch
system/kernel/t2bce/t2bce.nix
bin/ws-psr
system/kernel/i915-psr/apple-psr.patch
system/files/sleep.conf.d/80-deep-only.conf
system/files/udev/70-bcm4364-no-d3cold.rules
system/files/udev/71-tb-xhci-awake.rules
system/files/usr/local/sbin/broadcom-aspm-suspend-guard
system/files/usr/lib/systemd/system-sleep/80-broadcom-aspm
system/files/systemd/system/broadcom-aspm-restore.service
system/files/usr/local/sbin/ws-dgpu-off
system/files/systemd/system/ws-dgpu-off.service
system/files/usr/local/sbin/ws-dgpu-park
system/files/usr/lib/systemd/system-sleep/70-ws-dgpu-park
system/files/usr/local/sbin/ws-tb-acpi-seed
system/files/systemd/system/ws-tb-acpi-seed.service
system/files/usr/local/sbin/ws-t2-detach
system/files/usr/lib/systemd/system-sleep/60-ws-t2-hibernate
system/files/systemd/system/ws-t2-nofreeze.conf
system/files/systemd/system/ws-suspend-then-hibernate.conf
system/files/sleep.conf.d/85-ws-hibernate-delay.conf
system/files/logind.conf.d/ws-sleep-keys.conf
system/files/polkit/50-ws-hibernate.rules
system/files/dracut/ws-hibernate.conf
system/files/dracut/95ws-t2-resume/
gnome/extensions/workstation-hibernate@local/
nix/hosts/mbp16/host.toml              resume=, resume_offset=
```

## Не использовать

```text
выгрузку t2bce/apple-bce перед S3 (t2linux wiki: never unload t2bce); перед hibernate — только ws-t2-detach
hibernate без снятия стека T2; заморозку user.slice systemd-sleep вокруг hibernate
скрипты /etc/initramfs-tools (initramfs собирает dracut)
T2Linux-Suspend-Fix / t2-suspend.service / t2-resume.service
s2idle
pcie_aspm=force вместе с Touch Bar в режиме дисплея; pcie_ports=compat, i915.enable_guc=3
t2gmux на 16,1 (пока): ON выключает машину, после его OFF карту нельзя убрать с шины (helpws plan-dgpu)
Touch Bar display mode (appletbdrm, tiny-dfr) вместе с suspend
S3 с AMD, выключенной через vga_switcheroo, но оставленной на шине PCI
ON для AMD после OFF (карта до перезагрузки не оживает)
удаление HDMI-аудио AMD после OFF (виснет в snd_card_free)
ID_SEAT для узлов AMD: logind создаёт seat, GDM запускает на нём greeter
```
