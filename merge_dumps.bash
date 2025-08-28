#!/bin/bash
set -euo pipefail

source /usr/local/bin/sympactl_utils/sympa_cmd_util.bash

LISTS=("$@")
if [ "${#LISTS[@]}" -eq 0 ]; then
    LISTS=("*")
fi

TARGET_LISTS=()
for list in "${LISTS[@]}"; do
    if [ "$list" = "*" ]; then
        mapfile -t all_lists < <(get_all_lists)
        TARGET_LISTS+=("${all_lists[@]}")
    else
        TARGET_LISTS+=("$list")
    fi
done

for listname in "${TARGET_LISTS[@]}"; do
    if ! parse_list_roles "$listname"; then
        echo "スキップ: $listname のダンプ失敗"
        continue
    fi

    echo ""
    echo "# $listname"

    echo "[owner]"
    if [ "${#owner_emails[@]}" -gt 0 ]; then
        printf "%s\n" "${owner_emails[@]}"
    else
        echo ""
    fi

    echo "[editor]"
    if [ "${#editor_emails[@]}" -gt 0 ]; then
        printf "%s\n" "${editor_emails[@]}"
    else
        echo ""
    fi

    echo "[member]"
    if [ "${#member_emails[@]}" -gt 0 ]; then
        printf "%s\n" "${member_emails[@]}"
    else
        echo ""
    fi
done
