# Recovery catalog operations. Loaded only by the root-owned receiver.
# Data is fixed-schema JSON, never executable shell or sourced configuration.
catalog_token='[A-Za-z0-9][A-Za-z0-9_-]{0,63}'
catalog_uuid='[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}'
catalog_name='[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}'
catalog_pattern='^\{"schema_version":1,"host_id":"('"$catalog_token"')","source_fs_uuid":"('"$catalog_uuid"')","scope":"(system|home)","id":"('"$catalog_token"')","source_uuid":"('"$catalog_uuid"')","origin_uuid":"('"$catalog_uuid"')","timeshift_name":"('"$catalog_name"')","timestamp":([1-9][0-9]{0,9})\}$'

catalog_owned() {
    local path="$1" permissions
    safe_path "$path"
    [[ "$(stat -c %u "$path")" == "$EUID" ]] || die 'catalog has wrong owner'
    permissions="$(stat -c %a "$path")"
    (( (8#$permissions & 8#022) == 0 )) || die 'catalog is group/world writable'
}

catalog_validate() {
    [[ ${#catalog_values[@]} == 8 ]] || die 'invalid catalog fields'
    [[ "${catalog_values[0]}" == "$host_id" ]] || die 'catalog host not permitted'
    token "${catalog_values[0]}"; uuid "${catalog_values[1]}"
    [[ "${catalog_values[2]}" == system || "${catalog_values[2]}" == home ]] || die 'invalid catalog scope'
    token "${catalog_values[3]}"
    uuid "${catalog_values[4]}"; uuid "${catalog_values[5]}"
    [[ "${catalog_values[6]}" =~ ^${catalog_name}$ ]] || die 'invalid Timeshift name'
    [[ "${catalog_values[7]}" =~ ^[1-9][0-9]{0,9}$ ]] || die 'invalid Timeshift timestamp'
    local name="${catalog_values[6]}" checked
    checked="$(date -u -d "${name:0:10} ${name:11:2}:${name:14:2}:${name:17:2}" '+%Y-%m-%d_%H-%M-%S' 2>/dev/null)" || die 'invalid Timeshift date'
    [[ "$checked" == "$name" ]] || die 'invalid Timeshift date'
}

catalog_json() {
    printf '{"schema_version":1,"host_id":"%s","source_fs_uuid":"%s","scope":"%s","id":"%s","source_uuid":"%s","origin_uuid":"%s","timeshift_name":"%s","timestamp":%s}\n' "${catalog_values[@]}"
}

catalog_read() {
    local path="$1" text
    [[ -f "$path" ]] || die 'catalog record is not a file'
    catalog_owned "$path"
    [[ "$(stat -c %s "$path")" -le 2048 ]] || die 'catalog record too large'
    text="$(cat -- "$path")"
    [[ "$text" =~ $catalog_pattern ]] || die 'invalid catalog record'
    catalog_values=("${BASH_REMATCH[@]:1}")
    catalog_validate
}

catalog_directory() {
    local path="$1" create="$2"
    safe_path "$path"
    if [[ ! -e "$path" && "$create" == yes ]]; then
        mkdir -m0700 -- "$path"
    fi
    if [[ -e "$path" ]]; then
        [[ -d "$path" ]] || die 'catalog path is not a directory'
        catalog_owned "$path"
    fi
}

catalog_put() {
    catalog_values=("$host" "${words[6]}" "${words[2]}" "${words[3]}" "${words[4]}" "${words[5]}" "${words[8]}" "${words[7]}")
    catalog_validate
    local scope="${catalog_values[2]}" id="${catalog_values[3]}"
    local destination="$root/$host/$scope/$id"
    safe_path "$destination"
    [[ -d "$destination" ]] || die 'catalog snapshot missing'
    inspect_snapshot "$destination"
    [[ "$received_uuid" == "${catalog_values[4]}" ]] || die 'catalog received UUID mismatch'
    local directory="$root/$host/.catalog" file encoded previous temp
    catalog_directory "$root/$host" no
    catalog_directory "$directory" yes
    directory="$directory/$scope"
    catalog_directory "$directory" yes
    file="$directory/$id.json"; safe_path "$file"
    encoded="$(catalog_json)"
    if [[ -e "$file" ]]; then
        catalog_read "$file"
        previous="$(catalog_json)"
        [[ "$encoded" == "$previous" ]] || die 'catalog record conflict'
    else
        temp="$(mktemp "$directory/.pending-XXXXXXXX")"
        printf '%s\n' "$encoded" > "$temp"
        # Sync the content before publishing, then persist the directory rename.
        btrfs filesystem sync "$root" >&2
        mv -- "$temp" "$file"
        btrfs filesystem sync "$root" >&2
    fi
    printf '%s\n' "$encoded"
}

catalog_list() {
    local directory="$root/$host/.catalog" scope path snapshot count=0
    catalog_directory "$root/$host" no
    catalog_directory "$directory" no
    [[ -d "$directory" ]] || return 0
    shopt -s nullglob
    for scope in system home; do
        catalog_directory "$directory/$scope" no
        for path in "$directory/$scope/"*.json; do
            (( ++count <= 10000 )) || die 'too many catalog records'
            catalog_read "$path"
            [[ "${catalog_values[2]}" == "$scope" && "$(basename "$path")" == "${catalog_values[3]}.json" ]] || die 'catalog filename identity mismatch'
            snapshot="$root/$host/$scope/${catalog_values[3]}"
            safe_path "$snapshot"
            if [[ ! -d "$snapshot" ]]; then
                printf 'catalog snapshot missing: %s\n' "${catalog_values[3]}" >&2
                continue
            fi
            inspect_snapshot "$snapshot"
            [[ "$received_uuid" == "${catalog_values[4]}" ]] || die 'catalog received UUID mismatch'
            catalog_json
        done
    done
}
