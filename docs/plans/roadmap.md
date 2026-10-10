title: ws-roadmap
section: 1
date: 2026-09-28
source: Workstation
volume: User Commands

# UBUNTU T2 WORKSTATION — ROADMAP

Этот набор продолжает уже реализованный baseline и **не повторяет** законченные работы.

## Зафиксированный baseline

Считаем уже готовыми и не перенастраиваем без отдельной причины:

- Ubuntu 26.04.1 LTS;
- GNOME 50 / Wayland / GDM3;
- rEFInd + T2 kernel `7.2.7-1-t2-resolute`;
- Btrfs root с `@`, `@home`, `@cache`, `@tmp`, `@log`; snapshots — Timeshift;
- Wi-Fi, Bluetooth, T2 audio, microphone, camera;
- Intel UHD 630 как primary GPU; AMD dGPU выключена при загрузке (rEFInd «Ubuntu», `helpws workstation`), offload в «Ubuntu (AMD)»;
- рабочий `deep/S3` suspend/resume;
- suspend layer: deep-only, Broadcom guard, patched `t2bce` (`helpws suspend`); ASPM у ядра в пункте «Ubuntu» (`powersave`), порт выключенной AMD запаркован (`ws-dgpu-park`);
- Touch Bar в родном режиме (`hid-appletb-kbd` + `ws-touchbar-fn`):
  - F1…F12 по умолчанию;
  - media/brightness при удержании Fn;
  - без `tiny-dfr`/`appletbdrm`: режим дисплея Touch Bar ломал suspend;
- финальный macOS-style keyboard layer:
  - EN/RU/UA;
  - CapsLock EN/RU и Fn+CapsLock -> UA;
  - GDM/login EN и GNOME lock screen EN;
  - Tiling Assistant, Tile Editing Mode, Always on Top и Smart Popup;
- Nix + home-manager поверх Ubuntu (`helpws history-nix`, тег `nix-v1`):
  `bootstrap.sh` → `ws switch` → `ws system apply` → `ws apply`, проверка —
  `ws check`; задачи после миграции — там же, «После миграции»;
- development/toolchains не должны расползаться по host;
- не использовать `powertop --auto-tune`, TLP, auto-cpufreq и агрессивный USB runtime PM для Touch Bar.

## Что осталось

1. `helpws plan-t2`
   Hibernate и suspend-then-hibernate сделаны 2026-10-02 (крышка/Suspend →
   24 ч S3, затем hibernate; `helpws suspend`). Touch ID отложен до релиза
   t2touch с проверенным S3 и установкой вне Omarchy (2026-10-02).
   Battery audit и fan policy закрыты 2026-10-01 (forced ASPM, AMD без
   amdgpu с запаркованным портом, PSR, быстрый resume; вентиляторы штатно).

2. `helpws plan-final`
   Сделано 2026-10-02: инвентарь (`ws collect`), граница установки (apt,
   `purge:snapd`), snapshots и откат — Timeshift с входом из GRUB
   (проверено), чистка машины. Backup-механизм Timeshift @/@home с сохранением
   последнего ro-parent каждого scope и отдельный `send vms` подготовлены
   (`helpws backup`), цель — Unraid/Btrfs; осталось задать SSH-конфигурацию,
   выполнить первый реальный перенос и restore test. Финальный smoke-test
   также остаётся.

3. `helpws plan-legion-go`
   Legion Go 1 третьим хостом `legiongo` (план 2026-10-10): Ubuntu и
   wsconfig как на mbp16, ядро XanMod, загрузка в GNOME, Game Mode из
   компонентов Bazzite (InputPlumber, steamos-manager, gamescope-session,
   нативный Steam, SDDM), питание — PPD, swap — zswap. Слои хоста —
   пометками Flatpak и Distrobox и фактом `vm = "no"`. Хост в репозитории
   заведён (без ключа XanMod); на устройстве ничего не начато.

Отложено:

- `helpws plan-hyprland` — предложение Hyprland + Caelestia рядом с GNOME,
  адаптировано к текущему host/wsconfig 2026-10-02; установка не начата.
  Отдельный desktop lock/profile, session lifecycle и portals, собственный
  keyboard backend, проверяемая delta к upstream startup; GNOME baseline
  сохраняется. Начинать с compatibility/GPU gate и baseline capture.
- `helpws plan-dgpu` — AMD через t2gmux (KaiT2en), отложен 2026-10-01
  (решение пользователя): у 16,1 включение карты выключает машину. Сейчас
  `apple-gmux` + `ws-dgpu-park` (PC7 с выключенной картой); вернуться, когда
  KaiT2en починит включение;
- фикс t2bce через DKMS — только если сборка в podman станет неудобной;
  `build-essential` на host противоречит правилу про toolchains.

`01` можно выполнять отдельно: базовый suspend и Touch Bar уже работают,
поэтому Touch ID/hibernate/fan tuning не блокируют остальное.

## Завершённые слои

Как строились — `docs/history/` (`helpws history-…`), как работают —
`docs/runbooks/`:

```text
GNOME host layer        2026-09-23   history-gnome     gnome
Flatpak                 2026-09-24   history-flatpak   flatpak
Distrobox / Podman      2026-09-26   history-distrobox distrobox
Windows / Wine / Steam  2026-09-28   history-windows   windows
VM: KVM / libvirt       2026-09-29   history-virt      virt
Nix + home-manager      2026-09-28   history-nix       rebuild, workstation
Второе железо (VM)      2026-10-01   history-nix       rebuild
```

## Главное правило

Каждая категория должна завершаться рабочим checkpoint (`ws checkpoint create NAME`). Если изменение затрагивает kernel, boot, GNOME extensions, power или T2 hardware — перед ним делается Btrfs snapshot.
