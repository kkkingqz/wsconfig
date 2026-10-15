title: ws-layers
section: 1
date: 2026-09-28
source: Workstation
volume: User Commands

# LAYERS, OWNERS AND RULES

Ubuntu остаётся базовой системой; Nix и home-manager доставляют
конфигурацию поверх неё. Подробности каждого слоя — в runbooks
(`ws help <topic>`), где что лежит — `ws help workstation`.

## Порядок

```text
install.sh         свежая Ubuntu: git, gh, @nix и Nix из apt, затем ws setup
ws setup           новый ПК: всё ниже по порядку, вопросы в начале (ws help setup)
ws btrfs make      раскладка Btrfs свежей установки: @, @home, @cache, @tmp, @log
ws-prepare         шаг ws setup: apt-списки, @vms и libvirt, @steam, @wsbackup,
                   группы, fish, первый ws apply home
ws apply           всё по порядку: выбор новых позиций, сборка, apt и
                   системные файлы (sudo — только когда есть что делать),
                   home-manager, затем владельцы: расширения, tiling,
                   клавиатура, Flatpak, Distrobox, виджеты, скрипты; в конце — что
                   осталось (вход, перезагрузка, ws sync)
ws check           проверки всех владельцев и связей между слоями
```

Хост — `hosts/<host>/` (`host.toml`, `apt.txt`): `mbp16`
(MacBookPro16,1, T2) и `wsvm` (проверочная VM, generic-pc, GRUB; VM удалена
2026-10-02), выбирается по `hostname` в `host.toml` (`ws host`).
Пользовательский слой у всех хостов общий (`nix/home/default.nix`),
системный — `system/common.nix` плюс профили по фактам `boot` и `hardware`
(`system/boot/`, `system/hardware/`); проверки железа (T2, Touch Bar, dGPU)
и `/boot/ws` идут только там, где они есть (`ws fact`).

`host.toml` — факты хоста по разделам:

```
[host]        hostname, user, wsconfig
[platform]    hardware, boot, kernelParams, displayScale (1 без него),
              timezone, xremapIgnore; у rEFInd: refindDefaultParams,
              rootUuid, refindEspPartuuid
[layers]      vm, nativeSteam, gameMode, widgets — true или false
[container]   только при boot = "container": server, image, port,
              mounts, devices (ws container)
```

Проверяет файл только Nix (`lib/host.nix`): неизвестный раздел или ключ,
не тот тип, нет обязательного, `gameMode = true` без `nativeSteam = true`
— ошибка `ws apply` с именем файла. Без Nix факты читает
`lib/ws_facts.py` (`ws fact`, `ws setup`, `ws-prepare`); `true` и `false`
он печатает как `yes` и `no`.

## Слои и владельцы

```text
слой             источник                              применяет            проверяет
пользователь     nix/home/, terminal/, bin/, libexec/  ws apply            ws check home
система          system/*.nix, system/files/           ws apply system      ws system check
apt              hosts/*apt.txt                    ws setup, apt       ws check apt
клавиатура       keyboard/*.nix, xremap.yml            ws apply, ws keyboard apply   ws keyboard check
GNOME            gnome/gnome.nix, gnome-extensions.nix ws apply, ws apply extensions ws gnome check
виджеты          widgets/*.txt, flake input wswidgets  wswidgets, ws apply ws check widgets
скрипты          scripts/ конфигурации, scripts.nix    ws apply, ws script  ws script check
Flatpak          flatpak/*.txt, flatpak.nix            ws flatpak apply      ws flatpak check
Distrobox        distrobox/catalog.toml, distrobox.nix ws box apply          ws box check
Windows          windows/apps.toml (+ боксы Distrobox)  ws apply, ws windows     ws windows check
Remmina          remmina/*.nix, system/apt-machine.txt        ws apply, ws setup    ws check apt
suspend / T2     system/hardware, system/kernel/t2bce  ws apply system, ws suspend t2bce-*   ws suspend check
VM               apt.txt, ws-prepare, virt/virt.nix     ws setup, virt-manager               ws check virt
Steam (apt)      steam/apt.txt, steam/bootstrap.bash   ws setup             ws check steam
Game Mode        gaming/*, system/gaming.nix           ws game               ws game check
checkout         весь репозиторий                      git                  ws check repo
```

Связи между слоями (GNOME ↔ клавиатура, ядро ↔ t2bce, загрузка ↔ dGPU,
Distrobox ↔ NTSync) проверяет `ws-workstation-verify`. Формат проверок —
`ws help checks`.

## Правила

- **Один источник для каждой настройки.** Всё, что выбираем мы, объявлено
  в Nix, по файлу на область. Скрипты применяют и проверяют то, что собрано
  из Nix, и не держат своих копий списков. Родные форматы программ остаются
  (`xremap.yml`, ghostty, fish, udev/modprobe, `*.gschema.xml`,
  `containers.ini`); простой текст — `hosts/*apt.txt` (его читает
  подготовка `ws setup` до первой сборки); TOML — каталог `flatpak/catalog.toml` и выбор машин
  `hosts/*/*.toml` (их правят `ws flatpak`, `ws box`, `ws widgets`,
  `ws script`).
- **Владелец выдаёт список.** Системный слой — `ws system manifest`,
  пользовательский — активное поколение home-manager, Distrobox —
  `containers.ini`, расширения — собранный список. Проверки, baseline и
  checkpoint читают эти списки, а не свои.
- **Nix доставляет, владельцы остаются.** `ws flatpak`, `ws box`, `ws gnome`,
  `ws keyboard`, `ws suspend`, `ws windows` работают как раньше и читают
  собранное Nix.
- **Ядро — из store.** `ws` и внутренние исполнители (`bin/ws`,
  `libexec/`, `lib/`, модули) — копия checkout в store без данных
  (`nix/pkgs/ws.nix`); `~/.local/bin` ссылается на неё. Им по-прежнему нужны
  утилиты host (`gsettings`, `gdbus`, `busctl`, PyGObject, python3). Правка
  кода действует после `ws apply`; `~/Projects/wsconfig/bin/ws` (checkout
  ядра) берёт код сразу, `ws apply --core ~/Projects/wsconfig` собирает
  конфигурацию с ним. Откат поколения home-manager откатывает и инструменты;
  fish и Ghostty остаются ссылками в checkout, поэтому ключ состояния —
  коммит (`ws checkpoint`).
- **Последние версии.** Закреплено только то, что нужно: ядро (`linux-t2`
  held, патч t2bce под него), xremap (`nix/pkgs/xremap.nix`), расширения с
  `pin`. Остальное обновляет `ws update`.
- **В репозитории — только отличия** от стандартной системы:
  `/etc/default/grub` — пакетный, настройки — drop-in'ы `grub.d`.

## Где что хранится

```text
~/wsconfig                      всё, что правится (git, GitHub kkkingqz/wsconfig)
~/.local/share/wsconfig      собранное Nix и скачанное (ссылки в store, сборка t2bce)
~/.local/state/wsconfig      состояние: backup сочетаний, baseline, checkpoints,
                                применённое системное дерево
~/distrobox/<имя>               HOME каждого контейнера
/var/lib/vms                    всё состояние VM: subvolume @vms вне snapshots @
                                (диски, UEFI, TPM, XML; bind в пути libvirt; ~/VMs)
~/.local/share/Steam            Steam из apt (nativeSteam = true): subvolume @steam
                                вне snapshots и backup @home
```

Путь checkout — `wsconfig` в `host.toml`; скрипты находят его по своему
пути (`WSCONFIG` переопределяет).

## Состояние и возврат

```text
ws baseline capture|diff    функциональный снимок: проверки, GNOME, Flatpak, ...
ws checkpoint create|diff   коммит ↔ поколение home-manager, системное дерево, ядро
ws collect                  архив машины для rebuild (ws help rebuild, раздел 0)
Timeshift                   snapshots @ и @home, вход из GRUB (ws help rebuild, раздел 12)
```
