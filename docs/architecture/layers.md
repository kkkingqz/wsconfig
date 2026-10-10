title: ws-layers
section: 1
date: 2026-09-28
source: Workstation
volume: User Commands

# LAYERS, OWNERS AND RULES

Ubuntu остаётся базовой системой; Nix и home-manager доставляют
конфигурацию поверх неё. Подробности каждого слоя — в runbooks
(`helpws <topic>`), где что лежит — `helpws workstation`.

## Порядок

```text
bootstrap.sh       @nix, apt-списки, @vms и libvirt, @steam, группы, fish, первый ws switch
ws switch          home-manager: пользовательский слой, собранные списки
ws system apply    системные файлы из system/ (sudo)
ws apply           владельцы по порядку: расширения, tiling, клавиатура,
                   Flatpak, Distrobox
ws check           проверки всех владельцев и связей между слоями
```

Хост — `nix/hosts/<host>/` (`facts.nix`, `apt.txt`): `mbp16`
(MacBookPro16,1, T2) и `wsvm` (проверочная VM, generic-pc, GRUB; VM удалена
2026-10-02), выбирается по `hostname` в `facts.nix` (`ws host`).
Пользовательский слой у всех хостов общий (`nix/home/default.nix`),
системный — `system/common.nix` плюс профили по фактам `boot` и `hardware`
(`system/boot/`, `system/hardware/`); проверки железа (T2, Touch Bar, dGPU)
и `/boot/ws` идут только там, где они есть (`ws fact`).

## Слои и владельцы

```text
слой             источник                              применяет            проверяет
пользователь     nix/home/, terminal/, bin/            ws switch            ws check home
система          system/*.nix, system/files/           ws system apply      ws system check
apt              nix/hosts/*apt.txt                    bootstrap.sh, apt    ws check apt
клавиатура       keyboard/*.nix, xremap.yml            ws switch, ws-keyboard apply   ws-keyboard check
GNOME            gnome/gnome.nix, gnome-extensions.nix ws switch, ws apply extensions ws-gnome check
Flatpak          flatpak/*.txt, flatpak.nix            wsflatpak apply      wsflatpak check
Distrobox        distrobox/distrobox.nix               wsbox apply          wsbox check
Windows          windows/apps.nix (+ боксы Distrobox)  ws switch, wswin     wswin check
suspend / T2     system/hardware, system/kernel/t2bce  ws system apply, ws-suspend t2bce-*   ws-suspend check
VM               apt.txt, bootstrap.sh, virt/virt.nix   bootstrap.sh, virt-manager           ws check virt
Steam (apt)      steam/apt.txt, steam/bootstrap.bash   bootstrap.sh         ws check steam
checkout         весь репозиторий                      git                  ws check repo
```

Связи между слоями (GNOME ↔ клавиатура, ядро ↔ t2bce, загрузка ↔ dGPU,
Distrobox ↔ NTSync) проверяет `ws-workstation-verify`. Формат проверок —
`helpws checks`.

## Правила

- **Один источник для каждой настройки.** Всё, что выбираем мы, объявлено
  в Nix, по файлу на область. Скрипты применяют и проверяют то, что собрано
  из Nix, и не держат своих копий списков. Родные форматы программ остаются
  (`xremap.yml`, ghostty, fish, udev/modprobe, `*.gschema.xml`,
  `containers.ini`); простой текст — `nix/hosts/*apt.txt` (его читает
  `bootstrap.sh` до Nix) и `flatpak/apps.txt`, `flatpak/overrides.txt` (их правит `wsflatpak`).
- **Владелец выдаёт список.** Системный слой — `ws system manifest`,
  пользовательский — активное поколение home-manager, Distrobox —
  `containers.ini`, расширения — собранный список. Проверки, baseline и
  checkpoint читают эти списки, а не свои.
- **Nix доставляет, владельцы остаются.** `wsflatpak`, `wsbox`, `ws-gnome`,
  `ws-keyboard`, `ws-suspend`, `wswin` работают как раньше и читают
  собранное Nix.
- **`bin/` — ссылки на checkout.** Скрипты не собираются в store: им нужны
  утилиты host (`gsettings`, `gdbus`, `busctl`, PyGObject), правка работает
  сразу. Поэтому откат поколения home-manager не откатывает скрипты —
  состояние задаёт коммит (`ws checkpoint`).
- **Последние версии.** Закреплено только то, что нужно: ядро (`linux-t2`
  held, патч t2bce под него), xremap (`nix/pkgs/xremap.nix`), расширения с
  `pin`. Остальное обновляет `ws update`.
- **В репозитории — только отличия** от стандартной системы:
  `/etc/default/grub` — пакетный, настройки — drop-in'ы `grub.d`.

## Где что хранится

```text
~/wsconfig                      всё, что правится (git, GitHub kkkingqz/wsconfig)
~/.local/share/workstation      собранное Nix и скачанное (ссылки в store, сборка t2bce)
~/.local/state/workstation      состояние: backup сочетаний, baseline, checkpoints,
                                применённое системное дерево
~/distrobox/<имя>               HOME каждого контейнера
/var/lib/vms                    всё состояние VM: subvolume @vms вне snapshots @
                                (диски, UEFI, TPM, XML; bind в пути libvirt; ~/VMs)
~/.local/share/Steam            Steam из apt (nativeSteam = "yes"): subvolume @steam
                                вне snapshots и backup @home
```

Путь checkout — `wsconfig` в `facts.nix`; скрипты находят его по своему
пути (`WSCONFIG` переопределяет).

## Состояние и возврат

```text
ws baseline capture|diff    функциональный снимок: проверки, GNOME, Flatpak, ...
ws checkpoint create|diff   коммит ↔ поколение home-manager, системное дерево, ядро
ws collect                  архив машины для rebuild (helpws rebuild, раздел 0)
Timeshift                   snapshots @ и @home, вход из GRUB (helpws rebuild, раздел 12)
```
