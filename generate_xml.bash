#!/bin/bash
set -euo pipefail
LC_ALL=C

escape_xml() {
  local s=$1
  s=${s//&/&amp;}
  s=${s//</&lt;}
  s=${s//>/&gt;}
  s=${s//\"/&quot;}
  s=${s//\'/&apos;}
  printf '%s' "$s"
}

usage() {
  echo "Usage: $0 <listname> <subject> <description> <comma-separated-owners> <type>" >&2
  exit 1
}

[[ $# -lt 5 ]] && usage

raw_listname=$1
raw_subject=$2
raw_description=$3
raw_owners_csv=$4
raw_type=$5

if [[ ! "$raw_listname" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "Error: listname must contain only alphanumeric/underscore/hyphen" >&2
  exit 1
fi

IFS=',' read -r -a owners <<< "$raw_owners_csv"
norm_owners=()
declare -A seen=()
for x in "${owners[@]}"; do
  # trim spaces
  x="${x#"${x%%[![:space:]]*}"}"
  x="${x%"${x##*[![:space:]]}"}"
  [[ -z "$x" ]] && continue
  if [[ ! "$x" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]]; then
    echo "Warning: owner '$x' does not look like an email; outputting as-is." >&2
  fi
  if [[ -z "${seen[$x]+_}" ]]; then
    norm_owners+=("$x")
    seen[$x]=1
  fi
done

LIST_NAME=$(escape_xml "$raw_listname")
LIST_SUBJECT=$(escape_xml "$raw_subject")
LIST_DESCRIPTION=$(escape_xml "$raw_description")
LIST_TYPE=$(escape_xml "$raw_type")

printf "%s\n" "<?xml version='1.0' encoding='utf-8'?>"
printf "%s\n" "<list>"
printf "    <listname>%s</listname>\n" "$LIST_NAME"
printf "    <type>%s</type>\n" "$LIST_TYPE"
printf "    <subject>%s</subject>\n" "$LIST_SUBJECT"
printf "    <description>%s</description>\n" "$LIST_DESCRIPTION"
cat <<'EOF'
    <status>open</status>
    <language>ja</language>
EOF

for owner in "${norm_owners[@]}"; do
  owner_esc=$(escape_xml "$owner")
  printf "%s\n" "    <owner multiple=\"1\">"
  printf "        <email>%s</email>\n" "$owner_esc"
  printf "%s\n" "    </owner>"
done

cat <<'EOF'
    <max_size />
    <reply_to_header>
        <value>sender</value>
        <other_email />
    </reply_to_header>
    <process_archive>off</process_archive>
    <archive>
        <web_access>private</web_access>
    </archive>
    <send>private</send>
    <topic>arts,computing,computing/apps,computing/network,economics,news</topic>
</list>
EOF
