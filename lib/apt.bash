# shellcheck shell=bash disable=SC2154 # repo, host, host_list, container, vm, native_steam, game_mode: the caller's
# apt step of bootstrap.sh (ws help rebuild): PPAs, source: repositories,
# arch:, the packages of the apt lists (rec: with their recommends), manual
# marks, purge:. Also run as root by the image build of a container host
# (container/apt-install, ws help plan-wsgnomebox).
#
# Needs: those variables, run (prints instead with --dry-run) and die.
# purge: is checked by a simulation first (apt_purge_check).
# ws check apt and ws-baseline read the same lists (apt_host sets the
# variables from the facts; ws help plan-v2, 2.3).

# The apt lists of the host, by its facts: the only place that chooses them.
apt_lists() {
    printf '%s\n' "$repo/nix/hosts/apt.txt" "$host_list"
    # Real machines only, not a container host (ws help plan-wsgnomebox).
    [[ "$container" == true ]] || echo "$repo/nix/hosts/machine-apt.txt"
    # VM packages only on hosts with vm = true (ws help virt).
    [[ "$vm" == no ]] || echo "${WS_CORE:-$repo}/virt/apt.txt"
    # Native Steam and the Game Mode session (ws help plan-legion-go).
    [[ "$native_steam" == no ]] || echo "${WS_CORE:-$repo}/steam/apt.txt"
    [[ "$game_mode" == no ]] || echo "${WS_CORE:-$repo}/gaming/apt.txt"
}

# Package and PPA lines of the apt lists, without comments and blanks: the
# only cleaning of their lines.
apt_lines() {
    local f
    while IFS= read -r f; do
        [[ -r "$f" ]] && sed -e 's/#.*//' -e 's/[[:space:]]//g' -e '/^$/d' "$f"
    done < <(apt_lists)
    return 0
}

# The variables of apt_lists from the facts of HOST (lib/ws_facts.py), for
# the tools that run with the checkout; bootstrap.sh and the image build
# set them themselves. A layer fact that is not "yes" counts as no.
apt_host() {
    host="$1"
    host_list="$repo/nix/hosts/$host/apt.txt"
    container=false
    [[ "$(apt_fact boot)" != container ]] || container=true
    vm=no native_steam=no game_mode=no
    [[ "$(apt_fact vm)" != yes ]] || vm=yes
    [[ "$(apt_fact nativeSteam)" != yes ]] || native_steam=yes
    [[ "$(apt_fact gameMode)" != yes ]] || game_mode=yes
}

apt_fact() {
    WS_CONFIG="$repo" python3 "${WS_CORE:-$repo}/lib/ws_facts.py" fact --host "$host" "$1" 2>/dev/null
}

apt_install() {
    mapfile -t ppas < <(apt_lines | sed -n 's/^ppa://p')
    mapfile -t sources < <(apt_lines | sed -n 's/^source://p')
    mapfile -t archs < <(apt_lines | sed -n 's/^arch://p')
    # rec:NAME lines keep their prefix here: the install below takes their
    # recommends.
    mapfile -t packages < <(apt_lines | grep -v '^ppa:\|^purge:\|^source:\|^arch:')
    mapfile -t purges < <(apt_lines | sed -n 's/^purge://p')
    added=false
    for ppa in "${ppas[@]}"; do
        if grep -rqsF "ppa.launchpadcontent.net/$ppa/" /etc/apt/sources.list.d/; then
            echo "PPA present: $ppa"
        else
            run sudo add-apt-repository -y --no-update "ppa:$ppa"
            added=true
        fi
    done
    # Other repositories of the host: nix/hosts/<host>/apt/NAME.sources (deb822)
    # with its key NAME.asc, installed as ws-NAME; the file must point
    # Signed-By at the installed key.
    for name in "${sources[@]}"; do
        src="$repo/nix/hosts/$host/apt/$name.sources"
        key="$repo/nix/hosts/$host/apt/$name.asc"
        [[ -r "$src" && -r "$key" ]] \
            || die "source:$name needs nix/hosts/$host/apt/$name.sources and $name.asc"
        grep -qx "Signed-By: /etc/apt/keyrings/ws-$name.asc" "$src" \
            || die "nix/hosts/$host/apt/$name.sources: Signed-By must be /etc/apt/keyrings/ws-$name.asc"
        if cmp -s "$src" "/etc/apt/sources.list.d/ws-$name.sources" \
            && cmp -s "$key" "/etc/apt/keyrings/ws-$name.asc"; then
            echo "source present: $name"
        else
            run sudo install -D -m0644 "$key" "/etc/apt/keyrings/ws-$name.asc"
            run sudo install -D -m0644 "$src" "/etc/apt/sources.list.d/ws-$name.sources"
            added=true
        fi
    done
    # ws-NAME belongs to bootstrap.sh: one whose source: line is gone goes too,
    # or apt would keep installing from it.
    for f in /etc/apt/sources.list.d/ws-*.sources; do
        [[ -e "$f" ]] || continue
        name="${f##*/ws-}"
        name="${name%.sources}"
        [[ " ${sources[*]} " == *" $name "* ]] && continue
        run sudo rm -f "$f" "/etc/apt/keyrings/ws-$name.asc"
        added=true
    done
    for arch in "${archs[@]}"; do
        if dpkg --print-foreign-architectures | grep -qx "$arch"; then
            echo "architecture present: $arch"
        else
            run sudo dpkg --add-architecture "$arch"
            added=true
        fi
    done
    # Right after the first boot of a fresh install unattended-upgrades holds
    # the dpkg lock for minutes: wait for it instead of failing (phase 6, wsvm).
    apt_get=(sudo apt-get -o DPkg::Lock::Timeout=600)
    # Packages come without their recommends: what a host needs is listed.
    # A rec:NAME line is the exception (metapackages whose content is
    # Recommends, Steam's 32-bit libraries); apt takes recommends only when it
    # installs a package, so these go first, in their own install, before
    # anything else can pull them in as a plain dependency.
    missing=()
    missing_rec=()
    for line in "${packages[@]}"; do
        pkg="${line#rec:}"
        # "hold ok installed" counts too (linux-t2 is held).
        dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q ' ok installed$' && continue
        if [[ "$line" == rec:* ]]; then
            missing_rec+=("$pkg")
        else
            missing+=("$pkg")
        fi
    done
    packages=("${packages[@]#rec:}")
    if ((${#missing_rec[@]} + ${#missing[@]})); then
        run "${apt_get[@]}" update
        ((${#missing_rec[@]} == 0)) \
            || run "${apt_get[@]}" install -y --install-recommends "${missing_rec[@]}"
        ((${#missing[@]} == 0)) \
            || run "${apt_get[@]}" install -y --no-install-recommends "${missing[@]}"
    else
        [[ "$added" == false ]] || run "${apt_get[@]}" update
        echo "all ${#packages[@]} packages installed"
    fi
    # A listed package the standard install already has as a dependency
    # (python3-gi) stays auto-installed: apt autoremove could take it.
    mapfile -t auto < <(apt-mark showauto "${packages[@]}" 2>/dev/null)
    if ((${#auto[@]})); then
        run sudo apt-mark -o DPkg::Lock::Timeout=600 manual "${auto[@]}"
    else
        echo "all listed packages marked manual"
    fi
    present=()
    for pkg in "${purges[@]}"; do
        if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q ' installed$'; then
            present+=("$pkg")
        else
            echo "not installed: $pkg"
        fi
    done
    ((${#present[@]} == 0)) && return 0
    apt_purge_check "${present[@]}"
    run "${apt_get[@]}" purge -y "${present[@]}"
}

# purge: removes only what the list names. apt would take the packages that
# depend on them too: the simulation (no root needed) shows it, and then
# nothing is removed; the person decides (ws help plan-v2, stage 6).
apt_purge_check() {
    local sim extra
    sim="$(apt-get -s -o Debug::NoLocking=1 purge "$@" 2>&1)" \
        || die "apt-get -s purge $* failed:
$sim"
    extra="$(sed -nE 's/^(Purg|Remv) ([^ ]+).*/\2/p' <<<"$sim" | sed 's/:[a-z0-9]*$//' \
        | grep -vxF -f <(printf '%s\n' "$@") || true)"
    [[ -z "$extra" ]] || die "purge: of $* would also remove: $(echo $extra)
nothing removed; remove them by hand or drop the purge: line"
}
