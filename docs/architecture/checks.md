title: ws-checks
section: 1
date: 2026-09-28
source: Workstation
volume: User Commands

# CHECKS

Каждый слой проверяет его владелец; `ws check` запускает всех и сводит
итог. Все проверки только читают.

## Кто что проверяет

```text
ws check repo           checkout: git, мусор, синтаксис, исполняемые bin/, устаревшие пути
ws check home           поколение home-manager, Nix и @nix, man, окружение сессии
ws-keyboard check       xremap, сочетания GNOME и Tiling из keyboard.nix, источники ввода
ws-gnome check          профиль gnome.nix, расширения: набор, pin, ACTIVE, копии, schemas
wsflatpak check         remotes, приложения apps.txt, overrides, .desktop
wsbox check             контейнеры, образы, HOME, экспорты, hooks, wsbox-host-ntsync
wswin check             Windows-боксы, программы, .exe, ссылки меню
ws-suspend check        deep sleep, t2bce stateful sleep, Touch Bar
ws system check         файлы и units manifest, шаблон grub, nofail, раскладка GDM,
                        устаревшие файлы (старый recovery, /.snapshots)
ws check apt            apt-списки против установленного, purge: (snapd) снят
ws check virt           KVM, libvirt, @vms без CoW, пул и сеть default, OVMF и swtpm,
                        NVRAM VM в qcow2, проход qemu в HOME (пулы в ~/VMs)
ws check steam          ~/.local/share/Steam на @steam (fstab, владелец), клиент Steam
ws-workstation-verify   связи: GNOME ↔ клавиатура, ядро ↔ t2bce, загрузка ↔ dGPU,
                        Distrobox ↔ NTSync host
```

verify идёт последним: `wsbox check` к тому времени поднял контейнеры.

## Формат результата

Общий код — `lib/check.bash`: `pass`, `warn`, `fail`, `info`, `section`,
`check_finish`. Без аргументов проверка печатает текст для людей
(`  PASS  …`, итог `PASS=… WARN=… FAIL=…`). С `--json` — один объект:

```json
{"status": "pass|warn|fail", "passes": 0, "warnings": 0, "failures": 0,
 "messages": [{"level": "pass|warn|fail|info", "text": "..."}]}
```

`ws check` запускает каждую проверку с `--json` и читает только этот объект;
текст можно менять, не ломая сводку. Проверка без объекта или с ненулевым
кодом без failures считается одной ошибкой. `wsflatpak` (Python) выдаёт тот
же объект.

```console
ws check            # WARN/FAIL по каждой проверке и итог
ws check -v         # все сообщения
```

## Новая проверка

1. `. "$repo/lib/check.bash"`, флаг `--json` → `check_json_mode`.
2. `pass`/`warn`/`fail`/`info`, в конце `check_finish` (код 1 при FAIL).
3. Строка в `check_steps` в `bin/ws`, при необходимости — в
   `ws-baseline capture`.

Проверяется поведение и совпадение со списком владельца, а не фрагменты
кода и не текст документации.
