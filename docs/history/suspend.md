title: ws-history-suspend
section: 1
date: 2026-09-28
source: Workstation
volume: User Commands

# SUSPEND / T2 — HISTORY

> История: как искали причины сбоев сна и почему слой устроен так.
> Действующее описание — `helpws suspend`, `helpws touchbar`.

## Сбои и что из них следовало

```text
2026-09-22 19:25   отказ T2 (stateful suspend rejected), затем NULL dereference
2026-09-23 17:31   то же                                  в t2bce_dma_reserve_submission
2026-09-24 14:11   то же                                  → локальный патч t2bce
2026-09-25 12:00   brcmfmac не ушёл в D3, S3 прервался, systemd перешёл в s2idle
                   и система зависла → deep-only sleep, Broadcom guard
2026-09-25         pcie_aspm=force убран из refind_linux.conf (все отказы T2 были с ним)
2026-09-25         no-state путь патченого t2bce проверен (stateful_sleep=N): чисто
2026-09-26         удалён 90-pcie-aspm.cfg (forced ASPM для ядер GRUB)
2026-10-01         battery audit (helpws plan-t2): pcie_aspm=force + powersave
                   снова в пункте «Ubuntu» (−1,3…−2,3 W); порт CPU
                   выключенной AMD паркуется как в macOS (ws-dgpu-park):
                   пакет CPU PC3 → PC7, с погашенным экраном 8,4 → 5,1 W;
                   S3 с этим прошёл чисто, хук после resume паркует снова
2026-09-27 22:31   прерванный S3 с выключенной AMD (MODE1 reset amdgpu), xHCI TB
2026-09-28 08:51   «HC died», смерть без логов → ws-dgpu-off убирает карту с шины
2026-09-28         включение карты на время сна: D3cold → D0 не выходит; удаление
                   HDMI-аудио после OFF виснет в snd_card_free; запись ON в
                   vgaswitcheroo после удаления — Oops (старый hook сна)
2026-11-06 09:14   «Ubuntu (AMD)»: Oops в ttm_lru_bulk_move_tail (amdgpu_cs_ioctl)
2026-11-08 13:18   через секунды после resume, в первом случае — после hybrid-sleep
                   накануне (дампы в EFI pstore). Баг TTM ядер 7.1–7.2.7
                   (CVE-2026-98166, drm/amd#5387): после гибернационного swapout
                   буфер остаётся в bulk_move → use-after-free. Исправлен в
                   7.2.8/7.3 → linux-t2 7.3.3-2; t2bce-патч урезан
                   (teardown из deqrocks/t2bce#9 вошёл в 7.3), i915 + яркость gmux
```

## ASPM

`pcie_aspm=force pcie_aspm.policy=powersave` стояли в `/boot/refind_linux.conf`
до 2026-09-25, для ядер GRUB — в `/etc/default/grub.d/90-pcie-aspm.cfg` до
2026-09-26. Все три отказа T2 случились с ними и с Touch Bar в режиме дисплея.

## Touch Bar в режиме дисплея (2026-09-22 .. 2026-09-25)

С 2026-09-22 по 2026-09-25 Touch Bar работал в режиме дисплея: сначала через
`tiny-dfr`, затем, после удаления `tiny-dfr`, его подхватывал GNOME/Mutter как
второй монитор. Сводка по всем S3-циклам на kernel 7.2.x
(`/var/log/syslog`, `/var/log/kern.log`):

| Touch Bar | pcie_aspm | S3 циклов | сбои |
|---|---|---|---|
| родной (configuration 1) | force | 16 | 0 |
| родной | default | 4 | 0 |
| дисплей, работает tiny-dfr | force | 3 | 2 отказа T2 |
| дисплей, рисует Mutter | force | 7 | 1 отказ T2 |
| дисплей, никто не рисует | force | 6 | 1 зависание без логов |
| дисплей, Mutter или никто | default | 13 | 1 зависание без логов |

Зависание 2026-09-25 12:00 (brcmfmac не ушёл в D3, systemd откатился на s2idle)
в таблицу не включено: к Touch Bar оно не относится.

Отказ T2 — это `t2bce_core: remote rejected stateful suspend payload`; за ним
драйвер уходил в no-state fallback и падал с NULL dereference в
`t2bce_dma_reserve_submission` (upstream:
t2linux/T2-Debian-and-Ubuntu-Kernel#215). Оба зависания без логов случились,
когда `tiny-dfr` останавливали прямо перед сном.

Кроме того, без udev-правила `tiny-dfr` (`99-touchbar-seat.rules`) GNOME
использует `appletbdrm` как обычный KMS output. При resume Touch Bar
переподключается, и так однажды получился чёрный экран с
`drmModeAtomicCommit: Invalid argument`.

## Эксперименты с отрисовкой

Ранее исследовались:

```text
react-drm
mac-touchbar-plus
tiny-dfr (2026-09-22 .. 2026-09-25)
tiny-dfr-sleep.service (остановка tiny-dfr на время сна)
```

`react-drm` удавалось запустить с DRM renderer 2008x60, но draggable UI
(sliders/progress) был недостаточно надёжен. `tiny-dfr` работал, но в режиме
дисплея suspend был ненадёжен (см. выше).

## Возврат к tiny-dfr (не рекомендуется)

Не рекомендуется, пока сбои suspend в режиме дисплея не исправлены upstream.
Если всё же нужно:

```console
sudo systemctl disable --now ws-touchbar-fn.service
sudo rm /etc/udev/rules.d/90-touchbar-native.rules /etc/modprobe.d/touchbar-native.conf
sudo update-initramfs -u
sudo apt install tiny-dfr
sudo reboot
```
