# Step of bootstrap.sh for hosts with nativeSteam = "yes" (helpws
# plan-legion-go), sourced by it (run, subvolume_mount). The apt Steam keeps
# its client, libraries, compatdata and shader cache in ~/.local/share/Steam:
# that directory is the subvolume @steam, so Timeshift snapshots and the
# backup of @home leave the games out. Before the first start of Steam: an
# existing, non-empty directory stops bootstrap.sh.

steam_dir="$HOME/.local/share/Steam"
# As the user: subvolume_mount would create missing parents as root.
run install -d "$HOME/.local/share"
subvolume_mount @steam "$steam_dir" noatime,compress=zstd:1
# A new subvolume belongs to root.
if [[ "$(stat -c %U "$steam_dir" 2>/dev/null)" == "$(id -un)" ]]; then
    echo "$steam_dir belongs to $(id -un)"
else
    run sudo chown "$(id -un):$(id -gn)" "$steam_dir"
fi
