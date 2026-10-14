# wsconfig

Конфигурация рабочей станции: Ubuntu 26.04 + GNOME 50 (Wayland) на MacBook
Pro 16" 2019 с T2 (`MacBookPro16,1`). Ubuntu остаётся базовой системой; Nix и
home-manager доставляют конфигурацию поверх неё, владельцы слоёв (`ws`,
`ws flatpak`, `ws box`, `ws windows`, `ws keyboard`, `ws gnome`, `ws suspend`)
применяют и проверяют её.

## Установка

Новый ПК с GRUB — одной командой после установки Ubuntu (ESP и корень
Btrfs): все вопросы в начале, дальше только перезагрузки (`ws help setup`):

```console
wget -qO- https://raw.githubusercontent.com/kkkingqz/wsconfig/main/setup.sh | bash
```

Вручную, и для mbp16 (`docs/runbooks/rebuild.md`, разделы 1–2):

```console
sudo apt install git
git clone https://github.com/kkkingqz/wsconfig.git ~/wsconfig
~/wsconfig/bin/ws btrfs make  # раскладка Btrfs: @, @home, @cache, @tmp, @log
# reboot через GRUB, ещё раз ~/wsconfig/bin/ws btrfs make (раздел 3)
# mbp16: ядро T2 и rEFInd (разделы 4–5)
~/wsconfig/bootstrap.sh     # @nix, apt-списки, @vms и libvirt, @steam, группы, fish, первый ws apply home
# reboot
ws apply                    # apt, системные файлы (sudo), home-manager, расширения → tiling →
                            # клавиатура → Flatpak → Distrobox → виджеты
# logout/login, если ws apply так сказал, затем ещё раз ws apply
ws check                    # все проверки
```

Дальше: правка файла → `ws apply` (только нужное: `ws apply flatpak`,
`ws apply system`, …) → `ws check`. Обновления — `ws update`.

## Слои

```text
nix/            flake-хосты (host.toml, apt.txt), home-manager, пакеты
system/         системные файлы в /etc, /boot, /usr/local, ядро t2bce (ws system)
keyboard/       macOS-клавиатура: xremap, сочетания GNOME и Tiling Assistant
gnome/          профиль GNOME, расширения (свои — gnome/extensions/)
widgets/        слой виджетов: wswidgets из flake.lock; выбор — nix/hosts/*/widgets.toml
terminal/       Ghostty, fish, micro, xdg-terminal-exec
flatpak/        каталог приложений, remotes и overrides (catalog.toml, ws flatpak)
distrobox/      контейнеры Distrobox и их hooks (ws box)
windows/        Windows-программы в контейнерах Wine/Proton (ws windows)
remmina/        RDP-клиент Remmina из Nix: H.264, файлы через буфер
virt/           виртуальные машины: KVM, libvirt, virt-manager (ссылка ~/VMs)
bin/ws          единственная команда; ~/.local/bin/ws — из store (nix/pkgs/ws.nix)
libexec/        внутренние исполнители; их вызывает ws
lib/check.bash  общий формат проверок (--json для ws check)
docs/           документация, из неё собираются man-страницы
```

Хосты — `mbp16` (эта машина), `legiongo` (Lenovo Legion Go, Game Mode;
`ws help plan-legion-go`) и `wsvm` (проверочная VM фазы 6; сама VM удалена
2026-10-02, описание оставлено), выбираются по `hostname` в `host.toml`
(`ws host`). Хост — каталог `nix/hosts/<name>/` (`host.toml`, `apt.txt`);
новый на GRUB делает `setup.sh` из generic-pc (`ws help setup`).

## Документация

`ws help TOPIC` открывает документ, `man ws-…` — ту же страницу.

```text
docs/architecture/   layers (слои и правила), checks, workstation (подробно)
docs/runbooks/       setup, rebuild, keyboard, gnome, terminal, suspend,
                     touchbar, flatpak, distrobox, windows, remmina, virt,
                     gaming, backup, recovery
                     widgets (слой wswidgets: факт widgets, widgets.toml, ws widgets)
docs/plans/          roadmap и незавершённые планы
docs/history/        как строились завершённые слои
docs/superpowers/    specs/ и plans/: проекты и планы реализации backup и
                     recovery (без man-страниц и ws help; виджеты — в wswidgets)
```

## Состояние и восстановление

```text
ws check                        проверки всех владельцев и связей между слоями
ws checkpoint create NAME       какой коммит соответствует рабочему состоянию
ws baseline capture NAME        функциональный снимок для сравнения
ws collect                      архив машины перед переустановкой (sudo)
ws backup                       снимки Timeshift на Unraid и очистка старых ro-копий
ws backup plan                  план Timeshift backup, без SSH и изменений
ws backup recovery-export PATH  автономный ws-restore для Live USB
```

Backup: `ws help backup`. Механизм Btrfs send/receive подготовлен; адрес Unraid,
первый реальный перенос и restore test ещё нужны. Конфигурация — локальная,
таймера нет. После успешного batch остаётся по одному ro-parent system/home;
оригиналы Timeshift и копии на NAS не удаляются. VM передаются через `ws backup send vms`.

Восстановление выбранной даты с NAS на существующий SSD: `ws help recovery`.
Export не включает ключи и config; реальные NAS/boot acceptance checks пока не выполнены.
