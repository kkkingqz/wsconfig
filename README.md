# wsconfig

Конфигурация рабочей станции: Ubuntu 26.04 + GNOME 50 (Wayland) на MacBook
Pro 16" 2019 с T2 (`MacBookPro16,1`). Ubuntu остаётся базовой системой; Nix и
home-manager доставляют конфигурацию поверх неё, владельцы слоёв (`ws`,
`wsflatpak`, `wsbox`, `wswin`, `ws-keyboard`, `ws-gnome`, `ws-suspend`)
применяют и проверяют её.

## Установка

После Ubuntu, Btrfs, ядра T2 и rEFInd (`docs/runbooks/rebuild.md`, разделы
1–5):

```console
sudo apt install git
git clone https://github.com/kkkingqz/wsconfig.git ~/wsconfig
~/wsconfig/bootstrap.sh     # @nix, apt-списки, @vms и libvirt, группы, fish, первый ws switch
# logout/login
ws system apply             # системные файлы (sudo)
ws apply                    # расширения → tiling → клавиатура → Flatpak → Distrobox
# logout/login, затем ещё раз ws apply
ws check                    # все проверки
```

Дальше: правка файла → `ws switch` (пользовательский слой) или
`ws system apply` (системный) → `ws check`. Обновления — `ws update`.

## Слои

```text
nix/            flake-хосты (facts.nix, apt.txt), home-manager, пакеты
system/         системные файлы в /etc, /boot, /usr/local, ядро t2bce (ws system)
keyboard/       macOS-клавиатура: xremap, сочетания GNOME и Tiling Assistant
gnome/          профиль GNOME, расширения (свои — gnome/extensions/)
widgets/        общий Quickshell framework, реестр виджетов и GNOME adapter
terminal/       Ghostty, fish, micro, xdg-terminal-exec
flatpak/        приложения (apps.txt), remotes и overrides (wsflatpak)
distrobox/      контейнеры Distrobox и их hooks (wsbox)
windows/        Windows-программы в контейнерах Wine/Proton (wswin)
virt/           виртуальные машины: KVM, libvirt, virt-manager (ссылка ~/VMs)
bin/            команды; ссылками в ~/.local/bin
lib/check.bash  общий формат проверок (--json для ws check)
docs/           документация, из неё собираются man-страницы
```

Хосты — `mbp16` (эта машина) и `wsvm` (проверочная VM фазы 6; сама VM
удалена 2026-10-02, описание оставлено), выбираются по `hostname` в
`facts.nix` (`ws host`); новый хост — каталог `nix/hosts/<name>/`
(`facts.nix`, `apt.txt`).

## Документация

`helpws TOPIC` открывает документ, `man ws-…` — ту же страницу.

```text
docs/architecture/   layers (слои и правила), checks, workstation (подробно)
docs/runbooks/       rebuild, keyboard, gnome, terminal, suspend, touchbar,
                     flatpak, distrobox, windows, virt
                     widgets (ws-widgets: сервис, проверка и добавление Item)
docs/plans/          roadmap и незавершённые планы
docs/history/        как строились завершённые слои
```

## Состояние и восстановление

```text
ws check                        проверки всех владельцев и связей между слоями
ws checkpoint create NAME       какой коммит соответствует рабочему состоянию
ws baseline capture NAME        функциональный снимок для сравнения
ws collect                      архив машины перед переустановкой (sudo)
```
