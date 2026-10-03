title: ws-terminal
section: 1
date: 2026-09-21
source: Workstation
volume: User Commands

# TERMINAL WORKSTATION

**Ghostty + Fish — рабочий справочник**

> Этот документ — краткая практическая справка по текущей терминальной среде.
> Для полного состояния workstation используй `helpws workstation`.

---

## БЫСТРЫЙ СТАРТ

### Основные команды

```console
helpws                 # этот справочник
helpws workstation     # вся workstation подробно
helpws man ws-terminal
helpws man ws-workstation
```

### Главные сочетания

```text
Ctrl+T                  новый tab Ghostty
Ctrl+Shift+C / V        Linux-style copy / paste
Command/Win+C / V       macOS-style copy / paste
Command/Win+T           macOS-style new tab
Ctrl+R                  fuzzy history Fish
Option+C                directory browser
Ctrl+Shift+F            поиск в scrollback
Esc                     выход из helpws / Micro
```

---

# GHOSTTY

## Визуальный baseline

```ini
theme = Desert
background-opacity = 0.90
```

- Тема **Desert** используется без ручной коррекции палитры.
- Оконное оформление — нативное GTK4/libadwaita под GNOME.
- Буквенные hotkeys привязаны к **physical keys**, поэтому не зависят от текущей раскладки.

## Tabs

```text
Ctrl+T                  новый tab
Ctrl+Shift+W            закрыть tab
Ctrl+Tab                следующий tab
Ctrl+Shift+Tab          предыдущий tab
Ctrl+Shift+PageUp       переместить tab влево
Ctrl+Shift+PageDown     переместить tab вправо
Option+1 ... Option+9   перейти к tab 1 ... 9
Option+0                перейти к tab 10
```

## Windows / surfaces

```text
Ctrl+Shift+N            новое окно
Ctrl+Shift+X            закрыть текущую surface
Ctrl+Shift+Q            закрыть окно
```

## Splits

```text
Option+-                split вниз
Option+\                split вправо

Option+H                split слева
Option+J                split снизу
Option+K                split сверху
Option+L                split справа

Ctrl+Shift+←/↓/↑/→      альтернативная навигация

Ctrl+Shift+Option+←     resize влево
Ctrl+Shift+Option+→     resize вправо
Ctrl+Shift+Option+↑     resize вверх
Ctrl+Shift+Option+↓     resize вниз

Ctrl+Shift+Option+Space zoom / unzoom split
Ctrl+Shift+Option+E     выровнять splits
```

## Clipboard

```text
Ctrl+Shift+C            copy
Ctrl+Shift+V            paste
Shift+Insert            paste
```

Ghostty настроен так, что буквенные shortcuts используют физические клавиши. Поэтому `Ctrl+Shift+C/V` работают одинаково в English / Українська / Русская раскладках.

### macOS-style semantic layer

На Linux Apple `Command` и PC `Win` обе являются `Super`. Ghostty имеет native
bindings, поэтому terminal Ctrl semantics не ломаются.

```text
Command/Win+C           copy
Command/Win+V           paste
Command/Win+A           select all
Command/Win+F           search
Command/Win+T           new tab
Command/Win+N           new window
Command/Win+W           close surface
Command/Win+Q           close all Ghostty windows
Command/Win+,           open config
Command/Win+= / - / 0   font larger / smaller / reset
```

В терминале `Command/Win+Left/Right`, `Command/Win+Backspace` и
`Option/Alt+Left/Right` реализованы terminal-specific слоем xremap. Это
позволяет обойти штатный GNOME `Super+Left/Right` tiling до того, как
сочетание попадёт в Mutter.

Полный workstation keyboard profile: `helpws keyboard`.

### Clipboard security

- чтение clipboard через terminal protocol — с подтверждением;
- запись разрешена;
- paste protection включена;
- `copy-on-select` включён.

## Search и scrollback

```text
Ctrl+Shift+F            поиск в scrollback
Shift+PageUp            страница вверх
Shift+PageDown          страница вниз
Option+PageUp           небольшой шаг вверх
Option+PageDown         небольшой шаг вниз
Ctrl+Shift+Home         начало scrollback
Ctrl+Shift+End          конец scrollback
Ctrl+Option+Home        предыдущий shell prompt
Ctrl+Option+End         следующий shell prompt
```

## Font size

```text
Ctrl+=                  увеличить
Ctrl+-                  уменьшить
Ctrl+0                  reset
```

## Service keys

```text
Ctrl+Shift+P            command palette
Ctrl+Shift+Delete       clear screen
Ctrl+Option+R           reload Ghostty config
Ctrl+Shift+Option+,     открыть Ghostty config
```

## URL

Ghostty распознаёт обычные URL и OSC8 links. Для OSC8 включён preview реального адреса.

---

# PHYSICAL HOTKEYS

Ghostty преобразует physical key в стандартную terminal sequence. Это делает shell hotkeys независимыми от раскладки.

```text
Ctrl+R      → ASCII Ctrl-R
Option+C    → ESC c / Alt-C
Ctrl+A      → ASCII Ctrl-A
Ctrl+E      → ASCII Ctrl-E
Option+B    → Alt-B
Option+F    → Alt-F
Ctrl+Enter  → Alt+Enter
```

`Ctrl+Enter → Alt+Enter` используется directory browser на `fzf`.

---

# FISH 4.9.3

## Что работает штатно

- syntax highlighting;
- autosuggestions;
- contextual `Tab` completion;
- command history;
- Emacs-style line editing;
- shell integration с Ghostty.

## Цвета SSH-сессий

При запуске `ssh` из Fish в Ghostty обычный текст сессии меняет цвет:
`tower.local` и `192.168.113.113` — жёлтый, остальные серверы — бледно-красный.
После выхода, ошибки подключения или Ctrl+C возвращается цвет темы Ghostty.
Алиасы из `~/.ssh/config` определяются по итоговому `HostName` (`ssh -G`).
Цвета задаются в `terminal/ssh-colors.nix`, изменения применяются через `ws switch`.
Home Manager генерирует `~/.config/fish/functions/ssh.fish`; Fish загружает его
при первом вызове `ssh`, в том числе в уже открытом shell.
Если Ghostty включает `ssh-env` или `ssh-terminfo`, его функция `ssh`
сохраняется как транспорт и вызывается внутри цветовой обёртки. Hook в
`~/.config/fish/conf.d/ssh-colors.fish` учитывает настройку интеграции
после первого приглашения. После добавления этого hook откройте новую вкладку
или выполните `source ~/.config/fish/conf.d/ssh-colors.fish` в локальном Fish.
Вывод в файлы и pipes проходит без управляющих команд цвета. Явные ANSI-цвета
удалённого prompt и программ сохраняются; `command ssh` обходит обёртку.

## Цвета Distrobox-сессий

`distrobox enter NAME`, `distrobox-enter -n NAME` и `wsbox enter NAME`
меняют обычный цвет текста Ghostty на время сессии. Цвет каждого контейнера
и fallback для остальных задаются в `terminal/distrobox-colors.nix`;
после правки — `ws switch`. Имя определяется из аргументов или
`DBX_CONTAINER_NAME`; без явного имени применяется fallback.

Восстановлением цветов SSH и Distrobox управляет `terminal/session-colors.nix`.
После выхода или Ctrl+C возвращается предыдущий цвет. Переменная
`WS_TERMINAL_FOREGROUND` передаётся Distrobox во вложенные shells, поэтому
вложенный вызов этих обёрток восстанавливает цвет внешней сессии.
Явные ANSI-цвета программ сохраняются. `list`, `status`, `--help`, `--dry-run`,
`--no-tty`, вывод в файлы и pipes не меняют цвет терминала.

## Autosuggestions

Пример:

```text
ввод:
doc

предложение:
docker compose up -d ...
```

Принять всё:

```text
→
Ctrl+F
Ctrl+E
End
```

Принять следующий shell token:

```text
Ctrl+→
```

## Completion

```console
git <Tab>
systemctl <Tab>
ssh <Tab>
cd ~/Do<Tab>
helpws wo<Tab>
```

`helpws wo<Tab>` должен дополниться до `helpws workstation`.

## Редактирование command line

```text
Ctrl+A                  начало строки
Ctrl+E                  конец строки
Ctrl+B / Ctrl+F         символ назад / вперёд
Option+B / Option+F     слово назад / вперёд
Option+← / Option+→     слово назад / вперёд в macOS-style profile
Ctrl+U                  удалить к началу строки
Ctrl+K                  удалить до конца строки
Ctrl+W                  удалить предыдущий компонент
Option+Backspace        удалить предыдущее слово
```

---

# HISTORY — CTRL+R

`Ctrl+R` открывает fuzzy history через `fzf`.

```text
печатать                фильтровать
↑ / ↓                   выбрать
Enter                   принять запись
Esc                     отменить
```

Стандартный `fzf Ctrl+T` отключён, потому что `Ctrl+T` занят Ghostty новым tab.

---

# DIRECTORY BROWSER — OPTION+C

`Option+C` открывает браузер **только текущего уровня**, а не всё рекурсивное дерево.

Пример:

```text
./
../
.config/
.local/
Desktop/
Documents/
Downloads/
...
```

Управление:

```text
Enter на каталоге       войти и остаться в browser
../ + Enter             уровень вверх
./ + Enter              принять текущий каталог и выйти
Ctrl+Enter              принять выделенный каталог и выйти
Esc                     отменить
```

Пример:

```text
Option+C
Downloads/ + Enter
project/ + Enter
./ + Enter
```

Результат:

```text
cwd = ~/Downloads/project
```

---

# ZOXIDE

## Быстрый jump

```console
z down
z project
z docker
```

## Интерактивный выбор

```console
zi
```

Разделение ролей:

```text
Option+C    browser текущего дерева
z NAME      быстрый jump по ранее посещённым каталогам
zi          fuzzy search по базе zoxide
```

---

# EZA

```console
ls      # компактный список
ll      # long + Git
la      # hidden + long + Git
lt      # tree depth=2
```

Используются:

- icons;
- hyperlinks;
- directories first;
- Git metadata для `ll` / `la`.

---

# PROMPT

Пример:

```text
king@MacBookPro-k ~/project (main *) ❯
```

Prompt показывает:

- user / host;
- cwd;
- Git branch/state;
- ненулевой exit status.

После долгой команды справа показывается duration:

```text
12.7s
```

---

# HELPWS

`helpws` открывает Markdown в **Micro read-only**.

```console
helpws
helpws terminal
helpws ghostty
helpws fish
helpws keys
helpws workstation
helpws man ws-terminal
helpws man ws-workstation
```

### Навигация в helpws

```text
стрелки / PgUp / PgDn   навигация
мышь / wheel            прокрутка
Ctrl+F                  поиск
Ctrl+C                  copy
Esc                     выход
Ctrl+Q                  альтернативный выход
```

Micro для `helpws` использует отдельную конфигурацию и не меняет настройки обычного Micro.

---

# USER SCRIPTS / WRAPPERS

Единое место пользовательских executable:

```text
~/.local/bin
```

Правило:

```text
executable       ~/.local/bin/<tool>
config           ~/.config/<tool>/...
data             ~/.local/share/<tool>/...
```

Предпочтительные shebang:

```sh
#!/usr/bin/env fish
#!/usr/bin/env bash
#!/usr/bin/env python3
```

---

# WORKSTATION CONFIG GIT

Единый обычный Git repository:

```text
~/wsconfig
```

Терминальная часть: `terminal/` (fish, ghostty, micro-help, xdg-terminals),
`bin/` (`dotgit`, `helpws`, `ws-doc-build`), `docs/`. Весь репозиторий —
`helpws readme`.

Каталог checkout — настройка хоста: `wsconfig` в
`nix/hosts/<host>/facts.nix` (относительно `$HOME`). Скрипты находят
checkout по собственному пути (ссылки в `~/.local/bin`), переменная
`WSCONFIG` его переопределяет.

Реальные пути в `$HOME` используют symlink'и на repository.

```console
dotgit status
dotgit diff
dotgit add <file>
dotgit commit -m "message"
```

`dotgit` — wrapper вокруг:

```console
git -C ~/wsconfig
```

---

# ДОКУМЕНТАЦИЯ

Markdown в `docs/` — источник истины (`architecture/`, `runbooks/`,
`plans/`, `history/`); `helpws` находит страницу по `title:`.

Man pages собирает Nix из `docs/` (`nix/pkgs/man.nix`: `ws-doc-build` с
lowdown из nixpkgs) и ставит `ws switch` в `~/.local/share/man/man1`; в git их
нет. После правки документа:

```console
ws switch
```

Просмотр:

```console
helpws
helpws workstation
man ws-terminal
man ws-workstation
```

---

# ОСНОВНЫЕ ПУТИ

## Ghostty

```text
~/.config/ghostty/config.ghostty
~/.config/ghostty/behavior.ghostty
~/.config/ghostty/keybinds.ghostty
~/.config/ghostty/shell-keys.ghostty
```

## Fish

```text
~/.config/fish/config.fish
~/.config/fish/conf.d/        00-nix, eza, fzf-options, git-prompt, user-bin
~/.config/fish/functions/     prompt, title, fzf_cd_browser
~/.config/fish/completions/   ws, helpws, wsbox, wsflatpak, wswin, ws-gnome
```

Все файлы из `terminal/fish/` (и `terminal/ghostty/*.ghostty`, команды `bin/`)
подключены ссылками home-manager в checkout (`nix/home/links.nix`);
новый файл подключается следующим `ws switch`. Man pages — из сборки Nix
(`nix/home/man.nix`). fzf, zoxide, eza, micro — из Nix
(`nix/home/cli.nix`). fzf ≥ 0.70 занимает Shift+Tab; `config.fish` возвращает туда
`complete-and-search` fish.

## Help viewer

```text
~/wsconfig/terminal/micro-help/           settings.json, bindings.json
~/.local/share/workstation/micro-help/    MICRO_CONFIG_HOME helpws: ссылки на них + buffers/
```
