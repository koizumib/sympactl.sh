#!/bin/bash

# ---- 設定 ----
XML_GENERATOR="/usr/local/bin/sympactl_utils/generate_xml.bash"
CMD_UTIL="/usr/local/bin/sympactl_utils/sympa_cmd_util.bash"
LOG_FILE="/var/log/sympa_ml.log"
LISTFILE_DIR="."  # カレントディレクトリに .list ファイルがある想定

# ---- ログ出力関数 ----
log() {
    local msg="$1"
    local timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "$timestamp $msg" | tee -a
}

log_error() {
    local msg="$1"
    local timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo -e "\e[31m$timestamp $msg\e[0m"
}

# ---- 引数確認 ----
if [ $# -ne 1 ]; then
    log "Usage: $0 <csv_file>"
    exit 1
fi

CSV_FILE="$1"

if [ ! -r "$CSV_FILE" ]; then
    log "CSV file not found or not readable: $CSV_FILE"
    exit 1
fi

# ---- Sympaユーティリティ読み込み ----
if ! source "$CMD_UTIL"; then
    log "Failed to source Sympa command utility: $CMD_UTIL"
    exit 1
fi


# ---- CSV書式チェック ----
if ! validate_csv_format "$CSV_FILE"; then
    log "CSV format validation failed. Exiting."
    exit 1
fi

# ---- メイン処理 ----
while IFS=',' read -r CMD LISTNAME DESCRIPTION; do
    log "=== Processing: $CMD $LISTNAME ==="

    # CMDが有効なものであるかチェック
    case "$CMD" in
        CREATE|REPLACE|REMOVE)
            ;;
        *)
            log "Unknown action: $CMD"
            exit 1
            ;;
    esac

    # CREATEまたはREPLACEの場合のみ .list ファイル存在チェック
    if [[ "$CMD" == "CREATE" || "$CMD" == "REPLACE" ]]; then
        LISTFILE="${LISTFILE_DIR}/${LISTNAME}.list"
        if [ ! -f "$LISTFILE" ]; then
            log "List file not found: $LISTFILE"
            continue
        fi

        # .listファイルから読み込み
        owners=()
        editors=()
        members=()
        if ! load_ml_file "$LISTFILE"; then
            log "Failed to load list file: $LISTFILE"
            continue
        fi

        OWNER_CSV=$(IFS=','; echo "${owners[*]}")
    fi

    case "$CMD" in
        CREATE)
            if list_exists "$LISTNAME"; then
                log "List already exists. Skipping: $LISTNAME"
                continue
            fi

            BACKUP_DIR=$(backup_ml "$LISTNAME") || {
                log "Failed to create backup for list: $LISTNAME"
                exit 1
            }

            TMP_XML=$(mktemp) || {
                log "Failed to create temporary XML file"
                exit 1
            }
            chmod 644 "$TMP_XML"
            if ! "$XML_GENERATOR" "$LISTNAME" "$LISTNAME" "$DESCRIPTION" "$OWNER_CSV" "public_web_forum" > "$TMP_XML"; then
                log "Failed to generate XML"
                restore_ml "$LISTNAME" "$BACKUP_DIR"
                rm -f "$TMP_XML"
                exit 1
            fi

            log "Creating list from: $TMP_XML"
            if ! create_list "$TMP_XML" 2>&1 | tee -a "$LOG_FILE"; then
                log "Failed to create list"
                restore_ml "$LISTNAME" "$BACKUP_DIR"
                rm -f "$TMP_XML"
                exit 1
            fi

            # メンバー追加（空チェック付き）
            if [ "${#members[@]}" -gt 0 ]; then
                TMP_MEMBERS=$(mktemp) || {
                    log "Failed to create temporary members file"
                    exit 1
                }
                printf "%s\n" "${members[@]}" > "$TMP_MEMBERS"
                if ! add_members "$LISTNAME" "$TMP_MEMBERS"; then
                    log "Failed to add members"
                    rm -f "$TMP_MEMBERS"
                    exit 1
                fi
                rm -f "$TMP_MEMBERS"
            else
                log "No members specified. Skipping member addition."
            fi

            # エディタ追加（空チェック付き）
            if [ "${#editors[@]}" -gt 0 ]; then
                TMP_EDITORS=$(mktemp) || {
                    log "Failed to create temporary editors file"
                    exit 1
                }
                printf "%s\n" "${editors[@]}" > "$TMP_EDITORS"
                if ! add_editor "$LISTNAME" "$TMP_EDITORS"; then
                    log "Failed to add editors"
                    rm -f "$TMP_EDITORS"
                    exit 1
                fi
                rm -f "$TMP_EDITORS"
            else
                log "No editors specified. Skipping editor addition."
            fi

            rm -f "$TMP_XML"
            ;;

        REPLACE)
            BACKUP_DIR=$(backup_ml "$LISTNAME") || {
                log "Failed to create backup for list: $LISTNAME"
                exit 1
            }

            if ! list_exists "$LISTNAME"; then
                log "List not found. Creating: $LISTNAME"

                TMP_XML=$(mktemp) || {
                    log "Failed to create temporary XML file"
                    exit 1
                }
                chmod 644 "$TMP_XML"
                if ! "$XML_GENERATOR" "$LISTNAME" "$LISTNAME" "$DESCRIPTION" "$OWNER_CSV" "public_web_forum" > "$TMP_XML"; then
                    log "Failed to generate XML"
                    restore_ml "$LISTNAME" "$BACKUP_DIR"
                    rm -f "$TMP_XML"
                    exit 1
                fi

                log "Creating list from: $TMP_XML"
                if ! create_list "$TMP_XML" 2>&1 | tee -a "$LOG_FILE"; then
                    log "Failed to create list"
                    restore_ml "$LISTNAME" "$BACKUP_DIR"
                    rm -f "$TMP_XML"
                    exit 1
                fi

                rm -f "$TMP_XML"
            else
                log "List exists. Clearing all roles in: $LISTNAME"
                if ! del_members "$LISTNAME"; then
                    log "Failed to delete members"
                fi
                if ! del_editors "$LISTNAME"; then
                    log "Failed to delete editors"
                fi
                if ! del_owners "$LISTNAME"; then
                    log "Failed to delete owners"
                fi
            fi

            # オーナー追加（空チェック付き）
            if [ "${#owners[@]}" -gt 0 ]; then
                TMP_OWNERS=$(mktemp) || {
                    log "Failed to create temporary owners file"
                    exit 1
                }
                printf "%s\n" "${owners[@]}" > "$TMP_OWNERS"
                if ! add_owners "$LISTNAME" "$TMP_OWNERS"; then
                    log "Failed to add owners"
                    restore_ml "$LISTNAME" "$BACKUP_DIR"
                    rm -f "$TMP_OWNERS"
                    exit 1
                fi
                rm -f "$TMP_OWNERS"
            else
                log "No owners specified. Skipping owner addition."
            fi

            # メンバー追加（空チェック付き）
            if [ "${#members[@]}" -gt 0 ]; then
                TMP_MEMBERS=$(mktemp) || {
                    log "Failed to create temporary members file"
                    exit 1
                }
                printf "%s\n" "${members[@]}" > "$TMP_MEMBERS"
                if ! add_members "$LISTNAME" "$TMP_MEMBERS"; then
                    log "Failed to add members"
                    restore_ml "$LISTNAME" "$BACKUP_DIR"
                    rm -f "$TMP_MEMBERS"
                    exit 1
                fi
                rm -f "$TMP_MEMBERS"
            else
                log "No members specified. Skipping member addition."
            fi

            # エディタ追加（空チェック付き）
            if [ "${#editors[@]}" -gt 0 ]; then
                TMP_EDITORS=$(mktemp) || {
                    log "Failed to create temporary editors file"
                    exit 1
                }
                printf "%s\n" "${editors[@]}" > "$TMP_EDITORS"
                if ! add_editor "$LISTNAME" "$TMP_EDITORS"; then
                    log "Failed to add editors"
                    restore_ml "$LISTNAME" "$BACKUP_DIR"
                    rm -f "$TMP_EDITORS"
                    exit 1
                fi
                rm -f "$TMP_EDITORS"
            else
                log "No editors specified. Skipping editor addition."
            fi
            ;;

        REMOVE)
            BACKUP_DIR=$(backup_ml "$LISTNAME") || {
                log "Failed to create backup for list: $LISTNAME"
                exit 1
            }
            if list_exists "$LISTNAME"; then
                log "Purging list: $LISTNAME"
                if ! purge_list "$LISTNAME"; then
                    log "Failed to purge list"
                    restore_ml "$LISTNAME" "$BACKUP_DIR"
                    exit 1
                fi
            else
                log "List not found. Skipping PURGE: $LISTNAME"
            fi
            ;;

        *)
            log "Unknown action: $CMD"
            ;;
    esac

done < "$CSV_FILE"
