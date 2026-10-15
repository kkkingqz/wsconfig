# wsconfig

Конфигурация рабочей станции: Ubuntu 26.04 + GNOME 50 (Wayland) на MacBook
Pro 16" 2019 с T2 (`MacBookPro16,1`). Ubuntu остаётся базовой системой; Nix и
home-manager доставляют конфигурацию поверх неё, владельцы слоёв (`ws`,
`ws flatpak`, `ws box`, `ws windows`, `ws keyboard`, `ws gnome`, `ws suspend`)
применяют и проверяют её.

Это ядро: `ws`, модули, их Nix и документация. Данные рабочей станции —
хосты, каталоги, выбор, личные настройки (`home/`) — в отдельном
репозитории конфигурации пользователя (`~/wsconfig`), чей `flake.nix`
берёт это ядро входом `wsconfig` (`ws help architecture-v2`). Пример
конфигурации — `tests/config/`, начало новой — `template/`. Checkout ядра для разработки —
`~/Projects/wsconfig`; `ws apply --core ~/Projects/wsconfig` собирает
конфигурацию с ним.

## Установка

Новый ПК — одной командой после установки Ubuntu (ESP и корень Btrfs). Все
вопросы задаются в начале, дальше нужны только перезагрузки (`ws help
setup`):

```console
wget -qO- https://raw.githubusercontent.com/kkkingqz/wsconfig/main/install.sh | bash -s -- --repo URL_КОНФИГУРАЦИИ
```

`--new` вместо `--repo URL` создаёт новую конфигурацию из `template/`.
`install.sh` ставит git, gh и Nix (`/nix` на `@nix`), а дальше всё делает
`ws setup` ядра этой ревизии: хост, выбор, раскладку Btrfs, подготовку
системы (`libexec/ws-prepare`), `ws apply`, `ws check`, Timeshift. На mbp16
(rEFInd) шаги `ws help rebuild`, разделы 2–5, делаются руками: `ws setup`
их проверяет (`ws setup --check`) и останавливается, пока они не сделаны.

Дальше: правка файла → `ws apply` (только нужное: `ws apply flatpak`,
`ws apply system`, …) → `ws check`. Обновления — `ws update`.

## Слои

```text
nix/            flake-хосты (host.toml, apt.txt), home-manager, пакеты
system/         системные файлы в /etc, /boot, /usr/local, ядро t2bce (ws system)
keyboard/       macOS-клавиатура: xremap, сочетания GNOME и Tiling Assistant
gnome/          профиль GNOME, расширения (свои — gnome/extensions/)
widgets/        слой виджетов: wswidgets из flake.lock; выбор — hosts/*/widgets.toml
scripts/        scripts.nix: скрипты scripts/ конфигурации → ~/.local/bin/NAME; выбор — hosts/*/scripts.toml
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
(`ws host`). Хост — каталог `hosts/<name>/` (`host.toml`, `apt.txt`);
новый делает `ws setup` из инвентаризации машины (`ws help setup`).

## Документация

`ws help TOPIC` открывает документ, `man ws-…` — ту же страницу.
Те же файлы — в `~/wsconfig/docs`: `ws apply` ставит туда ссылку на `docs/`
закреплённого ядра (в Git конфигурации её нет, `.gitignore`).

```text
docs/architecture/   layers (слои и правила), checks, workstation (подробно)
docs/runbooks/       setup, rebuild, keyboard, gnome, terminal, suspend,
                     touchbar, flatpak, distrobox, windows, remmina, virt,
                     gaming, backup, recovery
                     widgets (слой wswidgets: факт widgets, widgets.toml, ws widgets)
                     scripts (свои скрипты: scripts/, scripts.toml, ws script)
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
