title: ws-virt
section: 1
date: 2026-09-28
source: Workstation
volume: User Commands

# VIRTUAL MACHINES — KVM / LIBVIRT / VIRT-MANAGER

VM работают на host: KVM, QEMU и libvirt связаны с ядром, устройствами и
сетью, в контейнер их не унести. Управление — `virt-manager`, подключение —
`qemu:///system`. Как слой строился и что проверено: `helpws history-virt`.

## Что где

Слой VM есть только на машинах с `vm = "yes"` в
`nix/hosts/<host>/facts.nix` (mbp16 — `yes`, wsvm — `no`). С `vm = "no"`
пакеты, `@vms`, группа `libvirt`, описание прошивки и `~/VMs` не ставятся,
`ws check virt` ничего не проверяет.

```text
virt/apt.txt                qemu, libvirt, virt-manager, SPICE, OVMF, swtpm, virtiofsd
virt/bootstrap.bash         шаг 3 bootstrap.sh: @vms и bind-монтирования, пул и сеть default
bootstrap.sh                группа libvirt
system/virt.nix             описание прошивки OVMF (qcow2-переменные)
virt/virt.nix               ~/VMs -> /var/lib/libvirt/images
bin/ws-check-virt           ws check virt
```

Всё состояние VM — на subvolume `@vms` (смонтирован в `/var/lib/vms`),
libvirt видит его на своих путях через bind-монтирования (fstab):

```text
@vms/images  /var/lib/libvirt/images  диски и ISO: без copy-on-write,
                                      root:libvirt 2775, пул «default»
@vms/qemu    /var/lib/libvirt/qemu    переменные UEFI (nvram/), метаданные
                                      snapshots, сохранённые состояния
@vms/swtpm   /var/lib/libvirt/swtpm   состояние TPM каждой VM
@vms/xml     /etc/libvirt/qemu        описания VM и сетей, autostart
@vms/firmware                         шаблон переменных UEFI в qcow2
~/VMs                                 ссылка на /var/lib/libvirt/images
virbr0, 192.168.122.0/24              NAT-сеть «default»
```

`@vms` не входит в snapshots `@`: откат `@` не трогает ни диски, ни
описания, ни UEFI и TPM, а snapshots не раздуваются. Если откатить `@` на
состояние до `@vms` (без его строк в fstab), libvirt увидит старые пустые
каталоги `@` — VM не пропадут, вернутся с `bootstrap.sh`. Без
copy-on-write у образов нет контрольных сумм Btrfs и сжатия — обычная цена
за qcow2 без фрагментации.

Переустановка `@vms` не сохраняет: диски — backup `@vms`
(`helpws plan-final`), описания, NVRAM и TPM — ещё и `ws collect`
(`virt/`), вернуть — `virsh -c qemu:///system define FILE`, NVRAM и
`swtpm/` на прежние пути. Кэш DHCP (`/var/lib/libvirt/dnsmasq`) остаётся на
`@`: он пересоздаётся.

`~/VMs` — ссылка на `/var/lib/libvirt/images`: ISO кладутся в
`~/VMs/iso/`. virt-manager заводит пул на каждый каталог, выбранный через
«Browse Local» (так появились `iso` и `iso-1` → `~/VMs/iso`), и это
штатно: qemu получает путь через HOME и проходит его по ACL
`user:libvirt-qemu:--x` на HOME (только проход, не чтение; ставит
`bootstrap.sh`, проверяет `ws check virt`). AppArmor пропускает файл по
настоящему пути в пуле. Проверено 2026-10-02: временная VM с ISO из
`~/VMs/iso` запускается.

## Сеть

Только NAT (`default`, virbr0): host ходит к гостю по его IP, гость — в сеть
через host. Мост (bridge) не используется: Wi-Fi не мостится на L2, а
проводной сети у машины нет.

## Создать VM

`virt-manager` → «Create a new virtual machine»: ISO из `~/VMs/iso/`
(«Browse Local» или пул), диск — в пуле `default`. То же
командой (так создавалась тестовая `ubuntu-test`, удалена 2026-10-02):

```console
virt-install --connect qemu:///system --name NAME --osinfo ubuntu25.10 \
  --memory 8192 --vcpus 4 --cpu host-passthrough --boot uefi \
  --disk size=40,format=qcow2,bus=virtio,pool=default \
  --network network=default,model=virtio --graphics spice --video virtio \
  --cdrom /var/lib/libvirt/images/iso/FILE.iso --noautoconsole
```

Получается:

```text
машина      q35, host-passthrough
прошивка    OVMF Secure Boot с ключами Microsoft (OVMF_CODE_4M.ms.fd) и TPM
            (tpm-crb, swtpm): osinfo Ubuntu выбирает их сам
диск        qcow2 virtio, разреженный, без CoW (атрибут C от каталога)
сеть        default (NAT), virtio
экран       SPICE, virtio-gpu, канал spice-vdagent
```

В osinfo Ubuntu 26.04 пока нет — ближайший `ubuntu25.10`. Размеры (4 vCPU,
8 ГБ, 40 ГБ) — наши; host: 12 потоков, 32 ГБ.

Mini ISO (`*-mini-iso-*`) скачивает полный образ и держит его в RAM: с 8 ГБ
установка падает в debug shell («failed to determine size reservation for
memmap»). На время установки — 16 ГБ и больше (`ubuntu-test` ставилась с
18 ГБ), потом память можно вернуть. Полный ISO этого не требует.

## Snapshots

Внутренние snapshots qcow2 (virt-manager → «Manage VM snapshots», `virsh
snapshot-create-as`) — и работающей VM (с памятью), и выключенной; откат —
`snapshot-revert`. Для VM с UEFI libvirt требует переменные UEFI (NVRAM) в
qcow2, а шаблон пакета `ovmf` — raw, и переводить его libvirt не умеет.
Поэтому:

```text
/var/lib/vms/firmware/OVMF_VARS_4M.ms.qcow2      шаблон в qcow2 (bootstrap.sh)
/etc/qemu/firmware/30-...-qcow2-vars.json        описание прошивки: код пакета
                                                 raw, шаблон qcow2; приоритет
                                                 выше пакетных (system/virt.nix,
                                                 ws system apply)
```

Новая VM с `--boot uefi` (virt-manager — тоже) получает NVRAM
`NAME_VARS.qcow2` сама. VM, созданная раньше, — перевести один раз
(выключенной):

```console
n=/var/lib/libvirt/qemu/nvram/NAME_VARS
sudo qemu-img convert -f raw -O qcow2 $n.fd $n.qcow2
virsh -c qemu:///system dumpxml --inactive NAME > /tmp/NAME.xml
# строка <nvram>: template=/var/lib/vms/firmware/OVMF_VARS_4M.ms.qcow2,
# templateFormat='qcow2', format='qcow2', путь $n.qcow2
virsh -c qemu:///system define /tmp/NAME.xml
```

`ws check virt` отмечает WARN у VM с NVRAM в raw и проверяет, что шаблон
совпадает с пакетным (после обновления `ovmf` — снова `bootstrap.sh`).

## Устройства

Общая папка с host — virtiofs. Папка — в пуле (`~/VMs/share` =
`/var/lib/libvirt/images/share`, на `@vms`); в VM (выключенной) — общая
память и устройство (в virt-manager: «Memory → Enable shared memory»,
«Add Hardware → Filesystem», driver virtiofs, target — метка):

```console
virt-xml --connect qemu:///system NAME --edit --memorybacking source.type=memfd,access.mode=shared
virt-xml --connect qemu:///system NAME --add-device --filesystem driver.type=virtiofs,source.dir=/var/lib/libvirt/images/share,target.dir=share
```

В госте: `sudo mount -t virtiofs share /mnt/share` (постоянно — строка
`share /mnt/share virtiofs defaults,nofail 0 0` в fstab гостя). Владельцы
файлов передаются как есть (UID): пользователь гостя с UID 1000 пишет файлы
`king`, root гостя — root. Snapshots работающей VM с virtiofs делаются и
откатываются; содержимое папки в snapshot не входит.

USB-устройство в гостя — «Redirect USB device» в консоли (SPICE).

## Клавиатура

Окна консолей VM (`virt-manager`, `remote-viewer`, `virt-viewer`) xremap на
host не трогает (`keyboard/xremap.yml`, `&vm_consoles`): клавиши уходят в
гостя как есть, macOS-профиль работает в госте, если он там поставлен
(`bootstrap.sh`, `ws apply`). Иначе Command+C приходил бы в гостя как Ctrl+C
(в терминале — прерывание). Главное окно virt-manager — тот же класс, в нём
Command-сочетания тоже не переводятся.

Исключение — CapsLock (и Fn/Alt+CapsLock): его host перехватывает всегда.
SPICE держит lock-клавиши гостя равными host: пропущенный CapsLock включил
бы блокировку на host, и клиент перенёс бы её в гостя (ЗАГЛАВНЫЕ, которые
нечем выключить — каждый CapsLock перехватывает xremap). В консоль VM он
уходит служебным сочетанием: CapsLock — Shift+Ctrl+Alt+Space, Alt/Fn+CapsLock
— Shift+Ctrl+Alt+U; xremap гостя превращает их обратно в CapsLock-выбор
раскладки (EN/RU, UA). Ctrl+Space и Ctrl+Alt+Space уходят как есть. По
той же причине `ws-caps-led` в VM индикатор не зажигает: горящий для RU
CapsLock клиент SPICE «исправляет» нажатием CapsLock в гостя, и раскладка
возвращается на EN.

Если блокировка CapsLock всё же включилась (заглавные при выключенном
индикаторе), выключить её в обход xremap:

```console
systemctl --user stop xremap     # затем нажать CapsLock
systemctl --user start xremap
```

Клавиатура гостя — PC (`AT Translated Set 2 keyboard`): работают
PC-варианты профиля (`helpws keyboard`), например UA — Alt+CapsLock; Fn Apple
до гостя не доходит.

## Windows (заложено, не сделано)

Для Windows 11 есть всё на стороне host: OVMF с Secure Boot и ключами
Microsoft (`OVMF_CODE_4M.secboot.fd`, `OVMF_VARS_4M.ms.fd`) и эмуляция TPM
(`swtpm`). Понадобятся ещё ISO драйверов virtio-win (в Ubuntu его нет,
скачивается с fedorapeople) и 8 ГБ+ памяти. Переменные UEFI новой VM — в
qcow2, как у любой (раздел «Snapshots»). Сама VM в план virt не входила.

## Проброс GPU

Не делается: в «Ubuntu» AMD снята с шины, после выключения она не
возвращается в D0 (`helpws suspend`), а Intel — единственный экран host.

## Команды

```console
virt-manager
virsh -c qemu:///system list --all
virsh -c qemu:///system start|shutdown|destroy NAME
ws check virt
```

## Проверка

`ws check virt`: KVM, `virt-host-validate` без FAIL, пользователь в
`libvirt`, `qemu:///system` доступен, `@vms` смонтирован без CoW, пул и сеть
`default` запущены с автозапуском, OVMF и swtpm на месте, шаблон NVRAM в
qcow2 совпадает с пакетным, у каждой VM NVRAM в qcow2.
