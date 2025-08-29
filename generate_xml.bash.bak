#!/bin/bash

# 引数チェック
if [ "$#" -lt 5 ]; then
    echo "Usage: $0 <listname> <subject> <description> <comma-separated-owners> <type>" >&2
    exit 1
fi

LIST_NAME="$1"
LIST_SUBJECT="$2"
LIST_DESCRIPTION="$3"
OWNERS_CSV=$(echo "$4" | tr -d '"')  # ダブルクォートを除去
LIST_TYPE="$5"

# カンマ区切り→改行へ変換
IFS=',' read -ra OWNER_ARRAY <<< "$OWNERS_CSV"

# XML出力
echo "<?xml version='1.0' encoding='utf-8'?>"
echo "<list>"
echo "    <listname>${LIST_NAME}</listname>"
echo "    <type>${LIST_TYPE}</type>"
echo "    <subject>${LIST_SUBJECT}</subject>"
echo "    <description>${LIST_DESCRIPTION}</description>"
echo "    <status>open</status>"
echo "    <language>ja</language>"

for owner in "${OWNER_ARRAY[@]}"; do
    echo "    <owner multiple=\"1\">"
    echo "        <email>${owner}</email>"
    echo "    </owner>"
done

echo "    <max_size />"
echo "    <reply_to_header>"
echo "        <value>sender</value>"
echo "        <other_email />"
echo "    </reply_to_header>"
echo "    <process_archive>off</process_archive>"
echo "    <archive>"
echo "        <web_access>private</web_access>"
echo "    </archive>"
echo "    <send>private</send>"
echo "    <topic>arts,computing,computing/apps,computing/network,economics,news</topic>"
echo "</list>"
