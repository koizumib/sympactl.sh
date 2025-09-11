#!/bin/bash

# === 設定 ===
SYMPA_CMD="/usr/sbin/sympa"
LISTDATA_DIR="/var/lib/sympa/list_data"
DOMAIN="sympa.dg-verification.net"

# エラー時は即終了
set -e

# === ログ出力関数 ===
log() {
    local msg="$1"
    local timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "$timestamp $msg"
}

log_error() {
    local msg="$1"
    local timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo -e "\e[31m$timestamp $msg\e[0m"
}

# === メーリングリスト存在確認 ===
list_exists() {
    local listname="$1"
    sympa export_list "$DOMAIN" 2>/dev/null | grep -Fxq "$listname"
}

# === Sympaコマンド実行ユーティリティ ===
run_sympa_command() {
    local sympa_cmd=("$@")
    local result

    if ! result=$( "${sympa_cmd[@]}" 2>&1 ); then
        echo "Sympa command failed: ${sympa_cmd[*]}" >&2
        echo "Error output: $result" >&2
        return 1
    fi

    echo "$result"
    return 0
}

# === メーリングリスト操作 ===
purge_list() {
    local listname="$1"
    echo "Purging list: ${listname}@${DOMAIN}"
    "$SYMPA_CMD" --purge_list "${listname}@${DOMAIN}"
}

close_list() {
    local listname="$1"
    echo "Closing list: ${listname}@${DOMAIN}"
    "$SYMPA_CMD" --close_list "${listname}@${DOMAIN}"
}

create_list() {
    local xml_file="$1"
    echo "Creating list from: $xml_file"
    run_sympa_command "$SYMPA_CMD" --create_list --robot "$DOMAIN" --input_file "$xml_file"
}

add_members() {
    local listname="$1"
    local member_file="$2"
    echo "Adding members to ${listname}@${DOMAIN}"
    "$SYMPA_CMD" add --quiet --role=member "${listname}@${DOMAIN}" < "$member_file"
}

add_editor() {
    local listname="$1"
    local editor_file="$2"
    echo "Adding editors to ${listname}@${DOMAIN}"
    "$SYMPA_CMD" add --quiet --role=editor "${listname}@${DOMAIN}" < "$editor_file"
}

add_owners() {
    local listname="$1"
    local owner_file="$2"
    echo "Adding owners to ${listname}@${DOMAIN}"
    "$SYMPA_CMD" add --quiet --role=owner "${listname}@${DOMAIN}" < "$owner_file"
}

del_members() {
    local listname="$1"
    echo "Deleting all members from ${listname}@${DOMAIN}"
    local emails
    emails=$(get_list_emails "$listname" "member") || return 1
    [[ -z "$emails" ]] && return 0
    echo "$emails" | "$SYMPA_CMD" del --quiet --role=member "${listname}@${DOMAIN}"
}

del_editors() {
    local listname="$1"
    echo "Deleting all editors from ${listname}@${DOMAIN}"
    local emails
    emails=$(get_list_emails "$listname" "editor") || return 1
    [[ -z "$emails" ]] && return 0
    echo "$emails" | "$SYMPA_CMD" del --quiet --role=editor "${listname}@${DOMAIN}"
}

del_owners() {
    local listname="$1"
    echo "Deleting all owners from ${listname}@${DOMAIN}"
    local emails
    emails=$(get_list_emails "$listname" "owner") || return 1
    [[ -z "$emails" ]] && return 0
    echo "$emails" | "$SYMPA_CMD" del --quiet --role=owner "${listname}@${DOMAIN}"
}

# === ユーティリティ関数 ===
get_list_emails() {
    local listname="$1"
    local role="$2"
    local file="${LISTDATA_DIR}/${listname}/${role}.dump"

    dump_list_roles "$listname" || return 1
    [[ -f "$file" ]] || return 0

    extract_emails "$file"
}

# === リスト一覧取得 ===
get_all_lists() {
    local output
    if ! output=$($SYMPA_CMD export_list "$DOMAIN" 2>/dev/null); then
        echo "エラー: export_list に失敗しました" >&2
        return 1
    fi
    echo "$output"
}

# === リストのdump実行 ===
dump_list_roles() {
    local listname="$1"
    if ! $SYMPA_CMD dump --roles=member,owner,editor "${listname}@${DOMAIN}" >/dev/null 2>&1; then
        echo "警告: dump 失敗 - $listname" >&2
        return 1
    fi
    return 0
}

# === dumpファイルからメール抽出 ===
extract_emails() {
    local file="$1"
    awk '/^email / { print $2 }' "$file"
}

# === リストのダンプ結果からロール情報を返す ===
parse_list_roles() {
    local listname="$1"
    local listdir="${LISTDATA_DIR}/${listname}"

    dump_list_roles "$listname" || return 1

    owner_emails=()
    editor_emails=()
    member_emails=()

    for role in owner editor member; do
        local file="${listdir}/${role}.dump"
        if [[ -f "$file" ]]; then
            mapfile -t parsed < <(extract_emails "$file")
            case "$role" in
                owner) owner_emails=("${parsed[@]}") ;;
                editor) editor_emails=("${parsed[@]}") ;;
                member) member_emails=("${parsed[@]}") ;;
            esac
        fi
    done
}

# === バックアップとリストア ===
backup_ml() {
    local listname="$1"
    local src_dir="/var/lib/sympa/list_data/$listname"
    local backup_dir="/tmp/sympa_backup_${listname}_$(date +%s)"
    "$SYMPA_CMD" dump --roles=member,owner,editor "${listname}@${DOMAIN}"

    if [ -d "$src_dir" ]; then
        mkdir "$backup_dir"
        chmod 644 -R "$backup_dir"
        cp -p "$src_dir"/*.dump "$backup_dir"/ 2>/dev/null || true
        cp -p "$src_dir"/config* "$backup_dir"/ 2>/dev/null || true
        echo "$backup_dir"
    else
        echo ""
    fi
}

restore_ml() {
    local listname="$1"
    local backup_dir="$2"
    local src_dir="/var/lib/sympa/list_data/$listname"

    if [ -d "$backup_dir" ]; then
        log "Restoring list data for ${listname}@${DOMAIN} from backup: $backup_dir"

        # ロールの削除（事前に dump 取得しないと削除対象が取得できないため）
        del_members "$listname"
        del_editors "$listname"
        del_owners "$listname"

        # ディレクトリ作成＆バックアップファイルを配置
        mkdir -p "$src_dir"
        cp -p "$backup_dir"/* "$src_dir"/ || {
            log "Failed to copy backup files"
            return 1
        }

        # ロール全体を復元
        if ! "$SYMPA_CMD" restore --roles=member,owner,editor "${listname}@${DOMAIN}"; then
            log "Sympa restore failed"
            return 1
        fi

        return 0
    else
        log "Backup directory does not exist: $backup_dir"
        return 1
    fi
}

# === .list ファイルパーサ ===
declare -a owners=()
declare -a editors=()
declare -a members=()

load_ml_file() {
    local file="$1"
    local section=""

    # ファイル存在チェック
    if [[ ! -f "$file" ]]; then
        echo "エラー: ファイルが存在しません: $file" >&2
        return 1
    fi
    if [[ ! -r "$file" ]]; then
        echo "エラー: ファイルが読み取れません: $file" >&2
        return 1
    fi

    while IFS= read -r line || [[ -n "$line" ]]; do
        # コメントと空白を除去
        line="${line%%#*}"
        line="${line%%;*}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"

        [[ -z "$line" ]] && continue

        case "$line" in
            "[owner]") section="owner" ;;
            "[editor]") section="editor" ;;
            "[member]") section="member" ;;
            \[*\])
                echo "エラー: 不明なセクション: $line" >&2
                return 1
                ;;
            *)
                if [[ -z "$section" ]]; then
                    echo "エラー: セクション定義前に値があります: $line" >&2
                    return 1
                fi
                case "$section" in
                    owner) owners+=("$line") ;;
                    editor) editors+=("$line") ;;
                    member) members+=("$line") ;;
                esac
                ;;
        esac
    done < "$file"

    return 0
}

# ---- CSV書式チェック関数 ----
validate_csv_format() {
    local file="$1"
    local line_number=0

    while IFS= read -r line || [[ -n "$line" ]]; do
        line_number=$((line_number + 1))

        # ダブルクォートで囲まれたカラムを正しく分割
        if ! echo "$line" | awk -F',' 'BEGIN { OFS="," } {
            for (i=1; i<=NF; i++) {
                if ($i ~ /^".*"$/ || $i ~ /^[^",]*$/) {
                    next
                } else {
                    exit 1
                }
            }
        }'; then
            log "Invalid CSV format at line $line_number: $line"
            return 1
        fi

        # 1カラム目のチェック (CREATE|REPLACE|REMOVE)
        local cmd=$(echo "$line" | cut -d',' -f1 | tr -d '"')
        if [[ ! "$cmd" =~ ^(CREATE|REPLACE|REMOVE)$ ]]; then
            log "Invalid command in column 1 at line $line_number: $cmd"
            return 1
        fi

        # 2カラム目のチェック (リスト名)
        local listname=$(echo "$line" | cut -d',' -f2 | tr -d '"')
        if ! echo "$listname" | grep -Eq "^[A-Za-z0-9!#$%&'*+/=?^_\`{|}~.-]+$"; then
            log "Invalid list name in column 2 at line $line_number: $listname"
            return 1
        fi
    done < "$file"

    return 0
}