#!/bin/sh
set -eu

patch_dir="$1"
root_dir="$2"
cleanup="${3:-}"

if [ ! -d "$patch_dir" ]; then
    echo "Patch directory missing: $patch_dir" >&2
    exit 1
fi

echo "Applying patches from $(basename "$patch_dir")"

for patch in "$patch_dir"/*.patch; do
    [ -e "$patch" ] || continue
    target_rel="$(awk 'NR==1 {print $2}' "$patch")"
    if [ -z "$target_rel" ]; then
        echo "Patch header missing target: $(basename "$patch")" >&2
        exit 1
    fi
    target_path="$root_dir/$target_rel"
    if [ ! -e "$target_path" ]; then
        echo "Skipping patch (target missing): $(basename "$patch")"
        continue
    fi
    echo "Applying patch: $(basename "$patch")"
    patch_log="$(mktemp)"
    if patch --batch --forward -p0 -d "$root_dir" < "$patch" >"$patch_log" 2>&1; then
        rm -f "$patch_log"
        continue
    fi
    if grep -q "Reversed (or previously applied) patch detected" "$patch_log"; then
        echo "Patch already applied: $(basename "$patch")"
        rm -f "$patch_log"
        continue
    fi
    cat "$patch_log"
    rm -f "$patch_log"
    exit 1
done

if [ "$cleanup" = "--cleanup" ]; then
    rm -rf "$patch_dir"
fi
