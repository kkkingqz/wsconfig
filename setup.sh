#!/usr/bin/env bash
set -euo pipefail

# First setup of a new PC on wsconfig (helpws setup), from a fresh Ubuntu
# 26.04 to a checked workstation. On the fresh system, in a terminal:
#
#   wget -qO- https://raw.githubusercontent.com/kkkingqz/wsconfig/main/setup.sh | bash
#
# git, gh, xdg-terminal-exec → GitHub login (gh auth login in the browser)
# → ~/wsconfig → the host: the one whose facts.nix has this hostname, else
# asked (an existing one gives the PC its hostname, a new one is made from
# generic-pc, committed and pushed) → all questions at once: Flatpak apps,
# Distrobox boxes and overrides without a mark of this host (checklists,
# lib/setup_marks.py), package licenses, the go → ws btrfs make → reboot → ws btrfs
# make → bootstrap.sh → reboot → ws system apply, ws apply → reboot → ws
# apply, ws check (FAIL does not stop: listed at the end) → Timeshift and
# its first snapshot, the backup key → ws switch, ws checkpoint create setup,
# git push.
#
# Each run starts where the last one stopped: the state of the system and
# the steps done in ~/.local/state/workstation/setup. Until the end a GNOME
# autostart entry runs it again after each login, so after a reboot the
# user only logs in. GRUB hosts only: rEFInd (mbp16) is helpws rebuild.

repo_url=https://github.com/kkkingqz/wsconfig.git
repo="$HOME/wsconfig"
state="${XDG_STATE_HOME:-$HOME/.local/state}/workstation/setup"
autostart="$HOME/.config/autostart/ws-setup.desktop"

die() {
    echo "setup: $*" >&2
    exit 1
}

say() {
    printf '\n== %s\n' "$*"
}

# yes/no question; $2 is the answer on Enter (y or n).
ask() {
    local a hint='[Y/n]'
    [[ "${2:-y}" == y ]] || hint='[y/N]'
    read -r -p "$1 $hint " a || a=
    [[ -n "$a" ]] || a="${2:-y}"
    [[ "$a" == [yYдД]* ]]
}

done_step() { [[ -e "$state/$1.done" ]]; }
mark_step() { mkdir -p "$state" && date -Is > "$state/$1.done"; }

# A string fact of a facts.nix, as bin/ws reads it.
fact_in() {
    sed -nE "s/^[[:space:]]*$2 = \"([^\"]*)\";.*/\1/p" "$1" 2>/dev/null | head -n1
}

ws() { "$repo/bin/ws" "$@"; }

[[ $EUID -ne 0 ]] || die "run as the desktop user, not root"

# wget | bash (or a copy elsewhere): the checkout first, then its setup.sh
# with the terminal as input.
if [[ "$(readlink -f "${BASH_SOURCE[0]:-}" 2>/dev/null)" != "$repo/setup.sh" ]]; then
    if [[ ! -d "$repo/.git" ]]; then
        if ! command -v git >/dev/null 2>&1; then
            say "git"
            sudo apt-get update </dev/tty
            sudo apt-get install -y git </dev/tty
        fi
        git clone "$repo_url" "$repo"
    fi
    exec bash "$repo/setup.sh" "$@" </dev/tty
fi

autostarted=false
[[ "${1:-}" != --autostart ]] || autostarted=true
# The terminal of the autostart closes with the script: keep it open.
if [[ "$autostarted" == true ]]; then
    trap 'echo; read -r -p "Enter — закрыть окно " _ || true' EXIT
fi
[[ -t 0 ]] || die "run it in a terminal: it asks questions"
mkdir -p "$state"
# One run at a time (the autostart and a terminal); exec keeps the PID.
if old="$(cat "$state/pid" 2>/dev/null)" && [[ "$old" != "$$" ]] \
    && tr '\0' ' ' < "/proc/$old/cmdline" 2>/dev/null | grep -q 'setup\.sh'; then
    die "setup.sh is already running (PID $old)"
fi
echo "$$" > "$state/pid"
# The Nix profile, as 00-nix.fish puts it into login shells.
[[ ! -d "$HOME/.nix-profile/bin" ]] || PATH="$HOME/.nix-profile/bin:$PATH"

reboot_now() {
    say "Перезагрузка: $1"
    echo "После входа setup.sh продолжит сам."
    read -r -p "Enter — перезагрузить " _ || true
    trap - EXIT
    sudo systemctl reboot
    exit 0
}

push() {
    git -C "$repo" push -q origin HEAD:main || die "git push failed (network, GitHub login?); run setup.sh again"
}

step_tools() {
    local -a missing=()
    local c
    for c in git gh xdg-terminal-exec; do
        command -v "$c" >/dev/null 2>&1 || missing+=("$c")
    done
    ((${#missing[@]})) || return 0
    say "apt: ${missing[*]}"
    sudo apt-get update
    sudo apt-get install -y "${missing[@]}"
}

step_github() {
    local name email
    if ! gh auth status --hostname github.com >/dev/null 2>&1; then
        say "GitHub: вход в браузере (одноразовый код)"
        gh auth login --hostname github.com --git-protocol https --web --scopes user:email
    fi
    if ! git config --global --get-all credential.https://github.com.helper 2>/dev/null | grep -q 'gh auth git-credential'; then
        gh auth setup-git --hostname github.com
    fi
    if [[ -z "$(git config --global user.name)" ]]; then
        name="$(gh api user --jq '.name // .login')"
        git config --global user.name "$name"
    fi
    if [[ -z "$(git config --global user.email)" ]]; then
        email="$(gh api user/emails --jq 'map(select(.primary))[0].email' 2>/dev/null || true)"
        [[ -n "$email" && "$email" != null ]] \
            || email="$(gh api user --jq '"\(.id)+\(.login)@users.noreply.github.com"')"
        git config --global user.email "$email"
    fi
    [[ -n "$(git config --global init.defaultBranch)" ]] || git config --global init.defaultBranch main
}

# The newest setup.sh of main; a run that pulled starts it anew.
step_pull() {
    local before
    [[ -z "$(git -C "$repo" status --porcelain)" ]] || { echo "$repo has changes: not pulled"; return 0; }
    [[ "$(git -C "$repo" symbolic-ref --short HEAD 2>/dev/null)" == main ]] || return 0
    before="$(git -C "$repo" rev-parse HEAD)"
    if ! git -C "$repo" pull -q --ff-only origin main; then
        echo "git pull failed: going on with this version"
        return 0
    fi
    if [[ "$(git -C "$repo" rev-parse HEAD)" != "$before" ]]; then
        exec bash "$repo/setup.sh" "$@"
    fi
}

# Host name as a directory and a mark can carry it (lib/ws_marks.py).
valid_name() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_-]*$ && "$1" != all ]]; }

set_hostname() {
    local new="$1" old
    old="$(hostname)"
    [[ "$old" != "$new" ]] || return 0
    say "hostname: $old -> $new"
    sudo hostnamectl set-hostname "$new"
    # sudo resolves the hostname through /etc/hosts.
    sudo sed -i -E "s/^(127\.0\.1\.1[[:space:]]+).*/\1$new/" /etc/hosts
    grep -Eq "^127\.0\.1\.1[[:space:]]+$new\$" /etc/hosts \
        || printf '127.0.1.1\t%s\n' "$new" | sudo tee -a /etc/hosts >/dev/null
}

new_host() {
    local name="$1" dir="$repo/nix/hosts/$1" vm=no steam=no game=no
    say "Новый хост $name (generic-pc, GRUB)"
    if ask "Виртуальные машины (libvirt, helpws virt)?" n; then
        vm=yes
    fi
    if ask "Steam из apt (вместо Flatpak; helpws plan-legion-go)?" n; then
        steam=yes
        if ask "Game Mode (сессия Steam как в SteamOS)?" n; then
            game=yes
        fi
    fi
    mkdir -p "$dir"
    cat > "$dir/facts.nix" <<EOF
# $name: made by setup.sh from generic-pc on $(date +%F) (helpws setup).
{
  # \`ws host\` finds the host by it.
  hostname = "$name";
  user = "$(id -un)";
  wsconfig = "wsconfig";
  hardware = "generic-pc";
  # Virtual machines (helpws virt).
  vm = "$vm";
  # Native Steam (steam/apt.txt, @steam) and the Game Mode session
  # (gaming/apt.txt; helpws plan-legion-go).
  nativeSteam = "$steam";
  gameMode = "$game";
  boot = "grub";
  kernelParams = [ "quiet" "splash" ];
}
EOF
    printf '# apt packages of %s on top of nix/hosts/apt.txt.\n' "$name" > "$dir/apt.txt"
    git -C "$repo" add "nix/hosts/$name"
    git -C "$repo" commit -q -m "Hosts: $name from generic-pc (setup.sh)" -- "nix/hosts/$name"
    push
}

# What setup.sh needs from the facts of HOST, checked before the PC is renamed.
check_facts() {
    local facts="$repo/nix/hosts/$1/facts.nix"
    [[ "$(fact_in "$facts" user)" == "$(id -un)" ]] \
        || die "nix/hosts/$1/facts.nix: user = \"$(fact_in "$facts" user)\", this user is $(id -un)"
    [[ "$(fact_in "$facts" wsconfig)" == wsconfig ]] \
        || die "nix/hosts/$1/facts.nix: setup.sh knows only wsconfig = \"wsconfig\" (~/wsconfig)"
    [[ "$(fact_in "$facts" boot)" == grub ]] \
        || die "boot = \"$(fact_in "$facts" boot)\" in nix/hosts/$1/facts.nix: setup.sh knows only GRUB hosts; rEFInd: helpws rebuild"
}

step_host() {
    local name hosts current
    if host="$(ws host 2>/dev/null)"; then
        :
    else
        current="$(hostname)"
        hosts="$(cd "$repo/nix/hosts" && ls -d */ | tr -d / | tr '\n' ' ')"
        say "Хост для «$current» не найден"
        echo "Есть: $hosts"
        while :; do
            if valid_name "$current"; then
                read -r -p "Имя хоста (существующий или новый) [$current]: " name || die "no answer"
                name="${name:-$current}"
            else
                read -r -p "Имя хоста (существующий или новый): " name || die "no answer"
            fi
            valid_name "$name" && break
            echo "только буквы, цифры, - и _"
        done
        if [[ -r "$repo/nix/hosts/$name/facts.nix" ]]; then
            check_facts "$name"
            set_hostname "$(fact_in "$repo/nix/hosts/$name/facts.nix" hostname)"
        else
            new_host "$name"
            set_hostname "$name"
        fi
        host="$(ws host)"
    fi
    check_facts "$host"
    echo "Хост: $host"
}

# All questions before the long part: marks, the Steam license, consent.
step_choices() {
    local changed rc=0
    done_step choices && return 0
    say "Что будет на $host"
    changed="$(python3 "$repo/lib/setup_marks.py" "$repo" "$host")" || rc=$?
    ((rc == 0)) || die "lists not answered (setup_marks exit $rc); run setup.sh again"
    if [[ -n "$changed" ]]; then
        # shellcheck disable=SC2086 # paths without spaces, one per line
        git -C "$repo" commit -q -m "Marks: $host (setup.sh)" -- $changed
        push
        echo "Пометки $host: $(echo $changed)"
    fi
    # Licenses apt would ask about in the middle of bootstrap.sh.
    local -a eula=('Microsoft core fonts (ubuntu-restricted-extras)')
    local -a seed=('ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true')
    if [[ "$(ws fact nativeSteam)" == yes ]]; then
        eula+=('Valve Steam (steam-installer)')
        seed+=('steam steam/question select I AGREE' 'steam steam/license note ')
    fi
    say "Лицензии пакетов"
    printf '  %s\n' "${eula[@]}"
    ask "Принять?" || die "bootstrap.sh installs them: nothing started"
    printf '%s\n' "${seed[@]}" | sudo debconf-set-selections
    say "Дальше без вопросов"
    echo "Раскладка Btrfs (старый корень удаляется после проверки загрузки), bootstrap.sh,"
    echo "ws system apply, ws apply, ws check, Timeshift, ключ backup. Между ними — перезагрузки:"
    echo "после каждой войти, setup.sh продолжит сам. Нужен пароль sudo после каждого входа."
    ask "Начать?" || die "nothing started; run setup.sh again"
    mark_step choices
}

install_autostart() {
    [[ -e "$autostart" ]] && return 0
    mkdir -p "$(dirname "$autostart")"
    cat > "$autostart" <<EOF
[Desktop Entry]
Type=Application
Name=wsconfig setup
Comment=Continues setup.sh after a reboot (helpws setup); removed at its end
Exec=xdg-terminal-exec $repo/setup.sh --autostart
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF
}

step_btrfs() {
    case "$(findmnt -no OPTIONS / | tr ',' '\n' | sed -n 's/^subvol=//p')" in
        /)
            install_autostart
            say "Раскладка Btrfs, шаг 1"
            ws btrfs make --yes
            reboot_now "раскладка Btrfs, шаг 1 сделан"
            ;;
        /@)
            if [[ -e /var/lib/ws-btrfs-layout/old-root ]]; then
                say "Раскладка Btrfs, шаг 2"
                ws btrfs make --yes
            fi
            ;;
        *) die "/ is neither the top level of Btrfs nor @ (helpws rebuild, section 3)" ;;
    esac
}

step_bootstrap() {
    done_step bootstrap && return 0
    install_autostart
    say "bootstrap.sh"
    "$repo/bootstrap.sh"
    mark_step bootstrap
    reboot_now "группы, fish, PATH из Nix"
}

step_layers() {
    if ! done_step system; then
        say "ws system apply"
        ws system apply
        mark_step system
    fi
    if ! done_step apply1; then
        say "ws apply (первый проход)"
        # New GNOME extensions activate only in a new session: steps with a
        # failed preflight run again after the reboot.
        ws apply || echo "ws apply: the rest after the reboot"
        mark_step apply1
        reboot_now "системные файлы и расширения GNOME"
    fi
    if ! done_step apply2; then
        say "ws apply"
        ws apply || die "ws apply failed: fix it, then setup.sh again"
        mark_step apply2
    fi
}

# FAIL does not stop setup: the snapshot is marked and the end lists them.
step_check() {
    done_step check && return 0
    say "ws check"
    rm -f "$state/check-fail.txt"
    if ! ws check | tee "$state/check.txt"; then
        grep -E '^ *FAIL ' "$state/check.txt" > "$state/check-fail.txt" \
            || echo "  FAIL  ws check (exit status)" > "$state/check-fail.txt"
    fi
    mark_step check
}

# Timeshift: Btrfs @ and @home; the schedule of mbp16 (helpws rebuild,
# section 12). Written once: afterwards the file belongs to Timeshift.
step_timeshift() {
    local conf=/etc/timeshift/timeshift.json uuid
    done_step timeshift && return 0
    say "Timeshift"
    uuid="$(findmnt -no UUID /)"
    if [[ ! -e "$conf" ]] || grep -Eq '"do_first_run" *: *"true"' "$conf"; then
        python3 - "$uuid" <<'PY' | sudo tee "$conf" >/dev/null
import json, sys
print(json.dumps({
    "backup_device_uuid": sys.argv[1], "parent_device_uuid": "",
    "do_first_run": "false", "btrfs_mode": "true",
    "include_btrfs_home_for_backup": "true", "include_btrfs_home_for_restore": "false",
    "stop_cron_emails": "true",
    "schedule_monthly": "true", "schedule_weekly": "true", "schedule_daily": "false",
    "schedule_hourly": "false", "schedule_boot": "true",
    "count_monthly": "1", "count_weekly": "3", "count_daily": "5",
    "count_hourly": "6", "count_boot": "3",
    "snapshot_size": "0", "snapshot_count": "0",
    "date_format": "%Y-%m-%d %H:%M:%S", "exclude": [], "exclude-apps": [],
}, indent=2))
PY
        echo "$conf: Btrfs $uuid, @home included, monthly 1, weekly 3, boot 3"
    else
        echo "$conf exists: kept"
    fi
    if [[ -s "$state/check-fail.txt" ]]; then
        sudo timeshift --create --scripted --comments "setup, ws check FAIL"
    else
        sudo timeshift --create --scripted --comments "setup"
    fi
    mark_step timeshift
}

# Backup (helpws backup): the local side. @wsbackup is bootstrap.sh; the
# key waits for the receiver, which takes only mbp16 so far.
step_backup() {
    local key="$HOME/.ssh/wsbackup_ed25519"
    done_step backup && return 0
    say "Backup"
    if [[ ! -e "$key" ]]; then
        install -d -m 0700 "$HOME/.ssh"
        ssh-keygen -q -t ed25519 -N "" -C "workstation-backup $host" -f "$key"
    fi
    echo "Локальные копии: /var/lib/workstation-backup (@wsbackup). Ключ: $key.pub"
    echo "Приёмник на Unraid пока принимает только mbp16: $host подключается отдельно (helpws setup)."
    mark_step backup
}

step_finish() {
    local checkpoint=true
    say "Готово"
    ws switch
    # A checkpoint needs a live system that matches its tree (ws system check).
    if ! git -C "$repo" rev-parse -q --verify refs/tags/checkpoint/setup >/dev/null; then
        ws checkpoint create setup || checkpoint=false
    fi
    [[ -z "$(git -C "$repo" log --oneline origin/main..HEAD 2>/dev/null)" ]] || push
    rm -f "$autostart"
    if [[ -s "$state/check-fail.txt" ]]; then
        echo "Хост $host настроен, но ws check нашёл FAIL ($state/check.txt):"
        cat "$state/check-fail.txt"
        echo "Снимок Timeshift — «setup, ws check FAIL». После исправления: ws check,"
        echo "sudo timeshift --create --comments checked, ws checkpoint create setup."
    else
        echo "Хост $host настроен: ws check без FAIL, снимок Timeshift «setup»."
    fi
    [[ "$checkpoint" == true ]] || echo "checkpoint setup не создан: ws checkpoint create setup после исправления."
}

sudo -v || die "sudo needed"
step_tools
step_github
step_pull "$@"
step_host
step_choices
step_btrfs
step_bootstrap
step_layers
step_check
step_timeshift
step_backup
step_finish
