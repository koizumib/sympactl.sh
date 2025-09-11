#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
from pathlib import Path

try:
    # 必要関数のみインポート
    from sympa_ctl_utils import get_all_lists, get_list_emails, list_exists
except Exception as e:
    print(f"\x1b[31mFailed to load sympa_list_tool: {e}\x1b[0m", file=sys.stderr)
    sys.exit(1)

RED = "\x1b[31m"
RESET = "\x1b[0m"


def eprint_red(msg: str) -> None:
    print(f"{RED}{msg}{RESET}", file=sys.stderr)


def dump_members_of_lists(listnames: list[str]) -> int:
    """
    listnames に含まれる各MLの memberロールのメールアドレスをCSVで出力する。
    出力形式: "ml名","ユーザ名"（ヘッダ無し）
    あるMLで取得に失敗した場合は、そのMLをスキップし、他を続行する。
    """
    writer = csv.writer(sys.stdout, lineterminator="\n")
    exit_code = 0

    for ml in listnames:
        ok, members, err = get_list_emails(ml, "member")
        if not ok:
            # 最小限のエラー表示のみ
            eprint_red(f"skip {ml}: {err}")
            exit_code = 1  # どれか1つでも失敗があれば非0に
            continue
        for addr in members:
            writer.writerow([ml, addr])

    return exit_code


def main() -> int:
    # 引数: 0個または1個（'*' も可）
    if len(sys.argv) > 2:
        print(f"Usage: {Path(sys.argv[0]).name} [*|<listname>]", file=sys.stderr)
        return 1

    # 対象MLの決定
    targets: list[str] = []
    if len(sys.argv) == 1 or sys.argv[1] == "*":
        ok, lists, err = get_all_lists()
        if not ok:
            eprint_red(f"failed to get all lists: {err}")
            return 1
        targets = lists
    else:
        listname = sys.argv[1].strip()
        ok, exists, err = list_exists(listname)
        if not ok:
            eprint_red(f"failed to check list existence: {err}")
            return 1
        if not exists:
            eprint_red(f"list not found: {listname}")
            return 1
        targets = [listname]

    # 取得＆出力
    return dump_members_of_lists(targets)


if __name__ == "__main__":
    sys.exit(main())

