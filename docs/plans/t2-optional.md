title: ws-plan-t2
section: 1
date: 2026-09-28
source: Workstation
volume: User Commands

# PLAN — T2 OPTIONAL / POWER / AUTH

## Цель

Добавить только действительно полезные T2-функции, не ломая уже рабочие:

- `deep/S3`;
- Intel primary + AMD offload;
- штатный Touch Bar;
- Wi-Fi/Bluetooth/audio/camera.

Этот этап **не является обязательным** для завершения workstation.

# 1. Battery audit

Нужно получить реальную базовую цифру расхода:

- idle на батарее;
- suspend `deep/S3` на 30–60 минут;
- повторить несколько раз;
- сравнить процент и энергию до/после.

Инструмент — `ws-battery` (сам перезапускается через sudo: ключи SMC и
счётчики RAPL читает только root):

```console
ws-battery now [SECONDS]      мощность по линиям питания, среднее за SECONDS (10)
ws-battery devices [SECONDS]  каждое устройство выключить (или включить) на SECONDS: его мощность
ws-battery idle MINUTES       среднее за MINUTES, лог
ws-battery sleep              уснуть сейчас; после пробуждения — энергия за сон, пробуждения
```

Логи — `~/.local/state/workstation/battery/` (`idle-*.tsv`, `sleep.tsv`).

Откуда цифры (MacBookPro16,1, разведка 2026-10-01):

- SMC меряет мощность по линиям питания: `PSTR` — вся система, `PPBR` —
  батарея (совпадает с ток × напряжение `BAT0`), линии `PC0R` (CPU),
  `PM0C` (память), `PG0R` (AMD dGPU, при `ws.dgpu=off` ~0,09 W), `POLR`
  (на ней видно Wi-Fi и Bluetooth), `PO5R` (5 V, на ней подсветка
  клавиатуры), `PORR`, `PSLC`, `PH0R`, `PH1R` — назначение последних не
  установлено; `PHPC` — CPU на входе регулятора.
- RAPL делит пакет CPU: ядра, iGPU (`uncore`), память (`dram`).
- Подсветка экрана ни на одной линии: её и радио `ws-battery devices`
  меряет выключением на несколько секунд (разница `PSTR`, среднее до и
  после). Линии вместе считают на ~2 W больше, чем `PSTR` без подсветки,
  поэтому «rest» в `ws-battery now` — подсветка минус ~2 W (−2,1 W с
  выключенным экраном, 0 при 28 %, 5,4 W при 100 %). Какая линия
  пересекается с другими, не установлено; `PORR` с яркостью не меняется.

Замеры 2026-10-01 (на батарее, сеанс не в простое: GNOME и Claude,
PSTR 12,5 W при яркости 28 %), `ws-battery devices`:

```text
подсветка экрана 28 %       2,08 W    100 % — ещё +5,6 W (PSTR 18,5 W)
Wi-Fi (power save on)       1,21 W    POLR
подсветка клавиатуры 100 %  0,50 W    PO5R
Bluetooth (ничего не подключено) 0,21–0,34 W  POLR
подсветка Touch Bar         0,11 W
CPU (PC0R)                  4,4 W     RAPL: ядра 0,3, iGPU 0,2, пакет 3,2
```

Claude Desktop (окно на экране, свёрнуто, закрыто) на мощность не влияет:
14,68 / 14,75 / 14,80 W.

### Пакет CPU не глубже PC3 (2026-10-01)

Ядра в простое — C10, но пакет — только PC2/PC3 (`package_cstate_show`:
PC6–PC10 нулевые с загрузки; `ws-battery now` показывает долю каждого).
Из 3,1 W пакета ядра и iGPU — 0,5 W, остальное — пакет сам по себе.

- FADT: `the system doesn't support PCIe ASPM` — ядро ASPM не управляет,
  остаётся то, что включила прошивка: T2/NVMe (`00:1b.0`) — L1 + L1.1, Wi-Fi
  (`00:1c.0`) — L1 + L1.1 + L1.2; порты CPU для Thunderbolt (`00:01.1`,
  `00:01.2`) и всё дерево Titan Ridge — ASPM выключен.
- Thunderbolt не засыпает никогда: у корневых роутеров `0-0`/`1-0` runtime
  PM нет (`unsupported`), домен держит NHI (`08:00.0`, `7e:00.0`), NHI —
  мосты и порты CPU. `71-tb-xhci-awake.rules` тут ни при чём: xHCI,
  отпущенные в runtime suspend, мощность не меняют (14,64 → 14,58 W).
- Опыт `~/.cache/tb-idle-test3.sh` (драйвер `thunderbolt` отвязан от обоих
  NHI на минуту, xHCI — `auto`): всё дерево и порты CPU в D3hot, **PSTR
  14,70 → 13,28 W (−1,4 W)**, пакет RAPL 3,11 → 1,75 W. Пакет при этом всё
  равно PC3 — есть второй ограничитель.
- Экран: PSR i915 не включает (`i915_edp_psr_status: No such device`;
  позже: панель умеет, мешал квирк Apple — см. «Экран при работе»), DMC загружен, DC5 — 1 раз с загрузки, DC6 — 0. Без PSR при
  включённом экране PC8+ недостижимы.
- LTR: Wi-Fi (`SOUTHPORT_A`, `00:1c.0`) — 61 мкс, T2 (`SOUTHPORT_E`) — 2 мс.

Что ещё проверено (2026-10-01, `~/.cache/*-test.sh`, `ws-battery now` по
10 с на шаг, шаги накопительные):

```text
                                  обычная загрузка   pcie_aspm=force
экран включён (59 %)                  15,27 W           13,94 W
экран погашен (mutter, как GNOME)      8,36 W            6,11 W
+ Thunderbolt спит                     7,48 W            6,02 W
+ PCH xHCI/SRAM/LPC/SEP runtime PM     7,26 W            6,33 W
+ Wi-Fi выключен                       5,84 W            4,96 W
```

Пакет при этом везде PC2/PC3. Не держат PC6 (каждое проверено отдельно):
`pkg-cstate-limit` (MSR `0xE2` = 0x8: unlimited, не заперт), экран (при
погашенном DC5 работает), Thunderbolt, PCH xHCI, Wi-Fi, Bluetooth, LTR (с
`ltr_ignore` всех IP — то же), Link Disable на порту AMD `00:01.0`, обмен с T2
(при погашенном экране `bce_dma` — 0 прерываний/с). `pcie_aspm=force
pcie_aspm.policy=powersave` даёт L1 на Thunderbolt и L0s на Wi-Fi (−1,3 W
с экраном, −2,25 W без), но выключает L1.1/L1.2, которые прошивка включала
на T2 и Wi-Fi. Блоки PCH без power gating в простое: OPI-DMI, SPA, SPE,
LPSS (UART Bluetooth — и при выключенном Bluetooth), NPK (Trace Hub).

Причина PC3 — выключенная AMD. Загрузка без `ws.dgpu=off` с
`pcie_aspm=force` (весь путь `00:01.0 → 01:00.0 → 02:00.0 → 03:00.0` в
L1/L0s): пакет PC7 65–82 % времени. Так же было в переписке с ChatGPT (до
25.09: AMD на шине, forced ASPM, `powersave` → PC7 ~70 %). После
`ws-dgpu-off` (gmux снимает питание, пакет AMD убран с шины) порт
`00:01.0` остаётся без устройства, и пакет — только PC2/PC3; `Link
Disable` на порту не помогает.

Экран погашен, `ws-battery now` по 10 с (2026-10-01):

```text
                                       PSTR      CPU PC0R   AMD PG0R   пакет
AMD выключена, обычная загрузка        8,36 W    3,63 W     0,09 W     PC3
AMD выключена, force + powersave       6,0 W     2,3 W      0,09 W     PC3
AMD выключена, force + powersupersave  6,3 W     2,7 W      0,09 W     PC3
AMD на шине, force + powersave         9,75–10,0 W  2,2–2,8 W  3,2–3,7 W  PC7
AMD на шине, force + powersupersave    8,5–9,25 W   1,6–1,8 W  —          PC7
```

Разбор `powersave` (загрузка с `pcie_aspm=force`, политика меняется на ходу,
экран погашен; `~/.cache/aspm-ab-test.sh`):

```text
                                   PSTR    POLR    PORR    пакет RAPL
ASPM прошивки (policy default)     8,04 W  2,71 W  2,08 W  2,62 W
+ L1 на Thunderbolt (setpci)       6,89 W  2,53 W  1,91 W  1,35 W
+ L0s на Wi-Fi (setpci)            7,76 W  2,51 W  1,94 W  1,89 W   шум/хуже
policy powersave                   6,26 W  2,20 W  1,57 W  1,34 W
policy powersupersave              6,41 W  2,19 W  1,57 W  1,41 W
```

L1 на Thunderbolt — ~1,15 W (пакет CPU), остальные ~0,6 W `powersave` даёт
на `POLR`/`PORR` — вероятно, Clock PM (CLKREQ#), которую ядро включает
вместе с политикой; L0s на Wi-Fi сам по себе ничего не дал.
`powersupersave` ≈ `powersave`. С `pcie_aspm=force` и политикой `default`
переключатели `link/l1_aspm` L1 на Thunderbolt не включают (ядро держит
состояние прошивки).

PC7 экономит на CPU ~0,6–1 W, но AMD на шине стоит 3,2–4,7 W: выключенная
AMD выгоднее. Лучшее из проверенного — AMD выключена + `pcie_aspm=force
pcie_aspm.policy=powersave`: −2,3 W с погашенным экраном, −1,3 W с
включённым. PC7 при выключенной AMD дал бы ещё ~0,6–1 W, если порт
`00:01.0` уводить в сон правильно.

Решение пользователя (2026-10-01): `pcie_aspm=force
pcie_aspm.policy=powersave` — да; проверки сна (циклы `ws-battery sleep`)
и перенос в `facts.nix` — позже. Power Mode GNOME (power-profiles-daemon
0.30: EPP `intel_pstate`, `trickle_charge`) ASPM не трогает и работает
как раньше. Отключать Thunderbolt без устройств не нужно: L1 на его
линках даёт тот же выигрыш.

Дальше: выключать AMD так, чтобы порт `00:01.0` не держал пакет в PC3.

**Итог (2026-10-01, `bc7fa35`):** пункт «Ubuntu» — `pcie_aspm=force
pcie_aspm.policy=powersave`, `ws-dgpu-off` + `ws-dgpu-park` (парковка порта
AMD как в macOS, после resume — хук). Экран погашен, на батарее: 8,36 W
(PC3) → **5,1 W, пакет PC7 ~80 %**; после S3 — 5,2–5,6 W, PC7 72–76 %.
t2gmux отложен (ws help plan-dgpu). Расход во сне и экран при работе — ниже;
раздел закрыт.

`ws-battery idle 30` (2026-10-01, на батарее, экран 28 %, Wi-Fi и BT вкл.):
первые 15 мин с экраном — 9,3 W, затем GNOME гасит экран — **3,9–4,1 W**;
среднее за 30 мин 6,7 W (PSTR; по счётчику заряда 5,55 W), пакет PC7 78 %,
полной батареи (81,4 Wh) при таком режиме — 12 ч.

Первый `ws-battery sleep` (2026-10-01): S3 17:41–18:53 (73 мин), resume
чистый, `70-ws-dgpu-park` запарковал порт (`LTSS` 0x165). Отчёт упал на
`pm_wakeup_irq` (ENODATA, когда разбудило не прерывание; `bb20b3f`), расход
не посчитан — повторить.

Второй `ws-battery sleep` (2026-10-01, 26 мин S3, 68 %): 47 mAh, 0,53 Wh —
**~1,2 W, 1,5 %/ч, полной батареи хватит на ~2,8 суток сна**; одно
засыпание, лишних пробуждений нет. 26 мин мало для точности счётчика
заряда — для уточнения нужен сон на ночь.

Расход сна признан достаточным (пользователь, 2026-10-01).

Экран при работе (2026-10-01, `~/.cache/power-survey.sh`, `psr-check*.sh`,
только чтение). С запаркованным портом AMD пакет и при включённом экране
PC7 ~70 % (9,6 W при 26–28 %); без PSR конвейер дисплея каждый кадр читает
из памяти:

- PSR: панель его умеет (DPCD `0x070` = 01 — PSR1; `0x003` бит 6 и `0x701`
  бит 7 — условия i915 выполнены), но sink OUI `00:10:fa` (Apple, id
  `eDgba`) стоит в `drm_dp_helper.c` с `DP_DPCD_QUIRK_NO_PSR` («Apple panels
  need some additional handling»): штатный i915 — «PSR = no». Обработку
  нашёл KaiT2en (трасса AUX под macOS): `0x321` = 3c, `0x4d2` = 01, `0x4d1` =
  03, PSR без проверки CRC, затем `0x4d4` = 01; VBT у Apple нет — флаг PSR
  в обход. Патч в intel-gfx (v3, 2026-09-16, не принят), у KaiT2en —
  `patches/currently-testing`. У нас — `system/kernel/i915-psr/apple-psr.patch`
  (только i915; квирк пропускается внутри i915) и `ws-psr build/install`
  (kernel.org + `linux-t2-patches` по закреплённому для t2bce коммиту).
  **Результат (2026-10-01, `~/.cache/psr-ab.sh`: PSR вкл/выкл через
  `i915_edp_psr_debug` на неподвижном экране, 2 × 2 × 30 с, батарея,
  яркость 26 %):**

  ```text
              PSTR     CPU PC0R   память PM0C   пакет RAPL   PC7
  PSR вкл     8,11 W   1,29 W     0,25 W        0,37 W       88 %
  PSR выкл    9,13 W   2,41 W     0,55 W        0,62 W       75 %
  ```

  −1,0 W: пакет глубже, кадр не читается из памяти (панель +0,4 W на
  самообновление). PC8+ и DC6 нет и с PSR — их держит не экран (с
  погашенным экраном тоже PC7). Мерцаний и зависаний картинки нет
  (пользователь, 2026-10-01); выключить на одну загрузку — `i915.t2_apple_psr=0`, откат — `ws-psr
  rollback`.
- FBC: «pixel format not supported» — mutter 50 выводит кадр в `XR30`
  (10 бит): при одной видеокарте сначала пробует 10-битные форматы, выключателя
  нет (`maxbpc` в `monitors.xml` — глубина линка, не формат кадра); FBC
  Coffee Lake — только 8 бит.
- Предложения powertop (runtime PM PCH, устройства T2 и Wi-Fi, autosuspend
  USB-устройств за T2, NMI watchdog, writeback) не применяем: PCH уже
  замерен (без выигрыша), у драйверов T2 и `brcmfmac` runtime PM нет, USB за
  T2 — устройства ввода на мосту, который не засыпает.
- VBT у Mac нет (`i915_vbt` пуст) — i915 берёт значения по умолчанию.

Прочее при работе зависит от выбора пользователя: яркость (28 % ≈ 2 W, 100 % — ещё
+5,6 W; датчик `als` и `iio-sensor-proxy` работают, автояркость GNOME
выключена), профиль Power Mode на батарее, время до гашения экрана (15 мин).

Выключение AMD (2026-10-01). У `PEG0` нет power resources; выключать умеет
SSDT Apple `PEG0GFX0`: `\_SB.PCI0.PEG0.EGP0.EGP1.GFX0.PWRD(1)` →
`PUPD(0)`: линк в Gen1, LTR порта выкл., запрос L2 (`Q0L2`, 0x248 бит 7)
и только после L2 — PHY порта выкл. (`RC20` 0xC20[5:4]=3, `RC38` 0xC38
бит 3, `BND0..3` бит 31 0x91C/0x93C/0x95C/0x97C); питание снимает gmux
(порт `0x50`: 1, затем 0; `MBWR` в ACPI — тот же mailbox gmux). Так
делает macOS (AppleMuxControl2) и t2gmux проекта KaiT2en (замена
`apple_gmux`, для MacBookPro16,1/16,4 — `PWRD`; включение — `PWRD(0)`,
карта возвращается без перезагрузки): github.com/kaiT2en/KaiT2en-Fedora
`modules/t2gmux`, серия в ядро v3 — 2026-08-12. `ws-dgpu-off`
(switcheroo OFF → `apple-gmux` пишет только 1, 0) этого не делает.

Опыты (`~/.cache/amd-l2-test.sh`, `peg-*-test.sh`, `amd-park-test.sh`):
карта под питанием без драйвера (`modprobe.blacklist=amdgpu`, 9,6 W!),
D3hot, затем `Q0L2` → пакет PC7 83 %, пакет RAPL 2,8 → 0,9 W. После
снятия питания без этой последовательности порт в «нет устройства», PC3;
`Link Disable`, PHY или `Q0L2` на порту без карты не помогают. Повторный
«паркинг» в той же загрузке не работает: порт остаётся в L2-состоянии
(`LTSS` 0x165) и не тренируется. Обращения ядра к карте за линком в L2
вешают машину — карту сначала убирать из PCI. Отладочный интерфейс
apple-gmux: `/sys/kernel/debug/apple_gmux/selected_port{,_data}`.

**Работает (2026-10-01, `amd-park-test.sh`, свежая загрузка с `ws.dgpu=off`
и forced ASPM, от сети, экран погашен):** после `ws-dgpu-off` — питание
карты через gmux (`0x50` ← 1, 3), линк поднялся (`LTSS` 0x1e0 → 0x1e3),
Gen1, LTR выкл., `Q0L2` сбросился за 20 мс (`LTSS` 0x165), PHY выкл.,
`0x50` ← 1, 10 мс, 0. Пакет PC3 → **PC7 82 %**, PSTR 8,74 → 7,97 W, CPU
`PC0R` 3,43 → 2,52 W, пакет RAPL 2,09 → 1,05 W; switcheroo по-прежнему
`DIS Off`. Не проверено: состояние порта после S3 и повтор после пробуждения.

Не применять автоматические Powertop tweaks. Использовать Powertop только как инструмент наблюдения.

### Готово, если

- понятен реальный расход в idle;
- понятен расход в `deep/S3`;
- нет неожиданного wake source;
- текущий режим признан достаточным либо есть конкретная измеримая проблема.

---

# 2. Fan policy

**Итог (2026-10-01):** штатное управление вентиляторами признано нормальным
(пользователь: «они уже хорошо работают»); `t2fanrd` не нужен. Раздел закрыт.

Сначала оставить штатное управление.

Проверить:

```bash
sensors
```

и поведение вентиляторов:

- idle;
- браузер/video;
- CPU load;
- AMD offload load.

`t2fanrd` ставить только если штатное поведение реально неудовлетворительно.

### Если нужен t2fanrd

1. Сделать snapshot.
2. Установить daemon.
3. Сначала использовать консервативную кривую.
4. Проверить температуры и sleep/resume.
5. Не держать два fan controller одновременно.

### Готово, если

Либо штатное управление признано нормальным, либо `t2fanrd` даёт предсказуемое улучшение без побочных эффектов.

---

# 3. Touch ID

Touch ID — отдельная optional feature.

**Итог (2026-10-02): отложено до релиза.** Проверено: рабочий вариант один —
`macintog/t2touch` (форк `jmurth1234/t2-touchid-linux`; BiometricKit
bridgeOS через BridgeXPC по `t2_ncm`, отпечатки — через штатный fprintd,
регистрация из Linux). MacBookPro16,1 — его эталонная модель, но это
исследовательский прототип (0.0.1–0.1.0 за 15–19.09.2026): установщик
только для Omarchy (Arch), PAM — раскладки Arch; модули через DKMS
(транспорт SEP, при необходимости — подменённый `applesmc`); suspend/resume
на 16,1 «unqualified»; после холодного сброса bridgeOS бывает нужна
повторная регистрация. Сейчас SEP (`04:00.2`) без драйвера, `fprintd-list`
— «No devices available». Вернуться, когда будет выпуск с проверенным S3 и
установкой вне Omarchy.

План:

1. Сохранить парольный login/PAM как обязательный fallback.
2. Проверить актуальную поддержку `t2-touchid`.
3. Сделать snapshot.
4. Установить и настроить только после проверки текущей документации T2Linux.
5. Проверить:
   - login;
   - `sudo`;
   - lock/unlock;
   - поведение после reboot;
   - поведение после suspend/resume.

Учитывать, что T2 Touch ID может зависеть от состояния Secure Enclave/macOS после некоторых hard power-off/kernel failure сценариев.

### Готово, если

Touch ID является удобным дополнительным методом, но пароль всегда остаётся рабочим.

---

# 4. Hibernate — только если нужен

**Итог (2026-10-02): сделано** (`ws help suspend`, Hibernate). Цель —
suspend-then-hibernate для долгого сна. Swapfile 32G в `@swap`
(`ws-suspend swap-setup`), resume в cmdline. Upstream hibernate с `t2bce`
сломан (#213): стек T2 снимается до образа и поднимается после
(`ws-t2-detach`, хук systemd-sleep, модуль dracut для initrd загрузки с
образом); сеансы не замораживаются, иначе unbind звука виснет. Ручных
циклов 3/3 OK (обычный, со звуком, с ВМ на батарее): graphics, T2 audio,
Wi-Fi, Bluetooth, Touch Bar, порт AMD.

Сейчас `deep/S3` уже работает, поэтому hibernate не нужен для исправления suspend.

Перед настройкой решить, есть ли практическая цель:

- очень долгий сон;
- сохранение батареи на сутки/несколько суток;
- suspend-then-hibernate.

План:

1. Проверить swap:
   ```bash
   swapon --show
   ```
2. Убедиться, что swap достаточен для hibernate.
3. Настроить resume.
4. Выполнить минимум 3–5 ручных циклов:
   ```bash
   systemctl hibernate
   ```
5. Каждый раз проверить graphics, T2 audio, Wi-Fi, Bluetooth, Touch Bar.

### Stop condition

При нестабильном resume не автоматизировать hibernate.

---

# 5. Suspend-then-hibernate

**Итог (2026-10-02): сделано.** `HibernateDelaySec=24h`,
`SuspendEstimationSec=24h`. Крышка и Suspend в меню GNOME →
suspend-then-hibernate; кнопка питания и пункт Hibernate в меню
(`workstation-hibernate@local`) → hibernate; polkit-правило снимает запрет
Ubuntu на hibernate. Проверено: RTC будит из S3 и машина уходит в S4;
открытие крышки до срока — обычный resume из S3.

Только после полностью стабильного ручного hibernate.

Пример целевой политики:

```ini
[Sleep]
AllowSuspend=yes
AllowHibernation=yes
AllowSuspendThenHibernate=yes
HibernateDelaySec=30min
```

Сначала тестировать вручную:

```bash
systemctl suspend-then-hibernate
```

Только потом связывать с обычной desktop policy.

---

## Что специально не делаем

- не пытаемся добиться runtime PM AMD dGPU (его нет); AMD выключается только при загрузке, пунктом rEFInd «Ubuntu» (`ws help workstation`, GRAPHICS);
- не меняем работающий `deep/S3`;
- не трогаем runtime PM Touch Bar;
- не запускаем `powertop --auto-tune`;
- не ставим одновременно TLP/auto-cpufreq поверх штатного GNOME power stack.
