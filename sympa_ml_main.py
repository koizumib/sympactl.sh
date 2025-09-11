#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
import shutil
from pathlib import Path

try:
    from config import LISTFILE_DIR
except Exception as e:
    print(f"\x1b[31mFailed to load config: {e}\x1b[0m", file=sys.stderr)
    sys.exit(1)

try:
    from sympa_list_tool import (
        SympaError,
        generate_list_xml,
        load_ml_file,
        list_exists,
        create_list,
        add_members,
        add_editor,
        add_owners,
        del_members,
        del_editors,
        del_owners,
        backup_ml,
        restore_ml,
        purge_list, 
        mktemp_with_content,
    )
except Exception as e:
    print(f"\x1b[31mFailed to load sympa_list_tool: {e}\x1b[0m", file=sys.stderr)
    sys.exit(1)


RED = "\x1b[31m"
RESET = "\x1b[0m"


def eprint_red(msg: str) -> None:
    print(f"{RED}{msg}{RESET}", file=sys.stderr)


def rm_tree(path: Path | None) -> None:
    if not path:
        return
    try:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def write_temp_xml(xml_text: str) -> Path | None:
    try:
        tmp = mktemp_with_content(prefix="sympa_create_", suffix=".xml")
        tmp.write_text(xml_text, encoding="utf-8")
        tmp.chmod(0o644)
        return tmp
    except Exception as e:
        eprint_red(f"Failed to create temporary XML: {e}")
        return None


def handle_create(listname: str, description: str) -> tuple[bool, str]:
    # 既存チェック
    ok, exists, err = list_exists(listname)
    if not ok:
        eprint_red(str(err))
        return False, "LIST_EXISTS_FAILED"
    if exists:
        print(f"SKIP CREATE (already exists): {listname}")
        return True, "SKIPPED"

    # .list 読み込み
    listfile = Path(LISTFILE_DIR) / f"{listname}.list"
    if not listfile.exists():
        eprint_red(f".list not found: {listfile}")
        return False, "LISTFILE_NOT_FOUND"

    ok, ml, err = load_ml_file(listfile)
    if not ok:
        eprint_red(str(err))
        return False, "LOAD_LISTFILE_FAILED"

    owners_csv = ",".join(ml.owners)

    # XML 生成
    try:
        xml_text = generate_list_xml(listname, listname, description, owners_csv, "public_web_forum")
    except Exception as e:
        eprint_red(f"XML generation error: {e}")
        return False, "XML_GENERATION_FAILED"

    tmp_xml = write_temp_xml(xml_text)
    if tmp_xml is None:
        return False, "XML_TMP_FAILED"

    # create_list → 直後に必ず XML を削除
    try:
        ok, _, err = create_list(tmp_xml)
    finally:
        tmp_xml.unlink(missing_ok=True)

    if not ok:
        eprint_red(str(err))
        return False, "CREATE_LIST_FAILED"

    # 以降の失敗は purge でロールバック
    # メンバー
    if ml.members:
        try:
            tmp_mem = mktemp_with_content(prefix="sympa_members_", suffix=".txt")
            tmp_mem.write_text("\n".join(ml.members) + "\n", encoding="utf-8")
            ok, _, err = add_members(listname, tmp_mem)
            tmp_mem.unlink(missing_ok=True)
            if not ok:
                eprint_red(str(err))
                ok_purge, _, err_purge = purge_list(listname)
                if not ok_purge:
                    eprint_red(f"purge after failure also failed: {err_purge}")
                return False, "ADD_MEMBERS_FAILED"
        except Exception as e:
            eprint_red(f"Failed to materialize members file: {e}")
            ok_purge, _, err_purge = purge_list(listname)
            if not ok_purge:
                eprint_red(f"purge after failure also failed: {err_purge}")
            return False, "ADD_MEMBERS_IO_FAILED"

    # エディタ
    if ml.editors:
        try:
            tmp_edit = mktemp_with_content(prefix="sympa_editors_", suffix=".txt")
            tmp_edit.write_text("\n".join(ml.editors) + "\n", encoding="utf-8")
            ok, _, err = add_editor(listname, tmp_edit)
            tmp_edit.unlink(missing_ok=True)
            if not ok:
                eprint_red(str(err))
                ok_purge, _, err_purge = purge_list(listname)
                if not ok_purge:
                    eprint_red(f"purge after failure also failed: {err_purge}")
                return False, "ADD_EDITORS_FAILED"
        except Exception as e:
            eprint_red(f"Failed to materialize editors file: {e}")
            ok_purge, _, err_purge = purge_list(listname)
            if not ok_purge:
                eprint_red(f"purge after failure also failed: {err_purge}")
            return False, "ADD_EDITORS_IO_FAILED"

    print(f"OK CREATE {listname}")
    return True, "OK"


def handle_replace(listname: str, description: str) -> tuple[bool, str]:
    # 存在確認
    ok, exists, err = list_exists(listname)
    if not ok:
        eprint_red(str(err))
        return False, "LIST_EXISTS_FAILED"

    if not exists:
        eprint_red(f"SKIP REPLACE (list not found): {listname}")
        return True, "SKIPPED"

    # バックアップ（失敗したらスキップ）
    ok, backup_dir, err = backup_ml(listname)
    if not ok:
        eprint_red(str(err))
        return False, "BACKUP_FAILED"

    # .list 読み込み
    listfile = Path(LISTFILE_DIR) / f"{listname}.list"
    if not listfile.exists():
        eprint_red(f".list not found: {listfile}")
        rm_tree(backup_dir)
        return False, "LISTFILE_NOT_FOUND"

    ok, ml, err = load_ml_file(listfile)
    if not ok:
        eprint_red(str(err))
        rm_tree(backup_dir)
        return False, "LOAD_LISTFILE_FAILED"

    # 既存ロール削除（失敗しても続行、ログのみ）
    ok, _, err = del_members(listname)
    if not ok and err:
        eprint_red(f"del_members: {err}")
    ok, _, err = del_editors(listname)
    if not ok and err:
        eprint_red(f"del_editors: {err}")
    ok, _, err = del_owners(listname)
    if not ok and err:
        eprint_red(f"del_owners: {err}")

    # owners 追加
    if ml.owners:
        try:
            tmp = mktemp_with_content(prefix="sympa_owners_", suffix=".txt")
            tmp.write_text("\n".join(ml.owners) + "\n", encoding="utf-8")
            ok, _, err = add_owners(listname, tmp)
            tmp.unlink(missing_ok=True)
            if not ok:
                eprint_red(str(err))
                _ = restore_ml(listname, backup_dir)
                rm_tree(backup_dir)
                return False, "ADD_OWNERS_FAILED"
        except Exception as e:
            eprint_red(f"Failed to materialize owners file: {e}")
            _ = restore_ml(listname, backup_dir)
            rm_tree(backup_dir)
            return False, "ADD_OWNERS_IO_FAILED"

    # members 追加
    if ml.members:
        try:
            tmp = mktemp_with_content(prefix="sympa_members_", suffix=".txt")
            tmp.write_text("\n".join(ml.members) + "\n", encoding="utf-8")
            ok, _, err = add_members(listname, tmp)
            tmp.unlink(missing_ok=True)
            if not ok:
                eprint_red(str(err))
                _ = restore_ml(listname, backup_dir)
                rm_tree(backup_dir)
                return False, "ADD_MEMBERS_FAILED"
        except Exception as e:
            eprint_red(f"Failed to materialize members file: {e}")
            _ = restore_ml(listname, backup_dir)
            rm_tree(backup_dir)
            return False, "ADD_MEMBERS_IO_FAILED"

    # editors 追加
    if ml.editors:
        try:
            tmp = mktemp_with_content(prefix="sympa_editors_", suffix=".txt")
            tmp.write_text("\n".join(ml.editors) + "\n", encoding="utf-8")
            ok, _, err = add_editor(listname, tmp)
            tmp.unlink(missing_ok=True)
            if not ok:
                eprint_red(str(err))
                _ = restore_ml(listname, backup_dir)
                rm_tree(backup_dir)
                return False, "ADD_EDITORS_FAILED"
        except Exception as e:
            eprint_red(f"Failed to materialize editors file: {e}")
            _ = restore_ml(listname, backup_dir)
            rm_tree(backup_dir)
            return False, "ADD_EDITORS_IO_FAILED"

    rm_tree(backup_dir)
    print(f"OK REPLACE {listname}")
    return True, "OK"


def handle_remove(listname: str) -> tuple[bool, str]:

    ok, exists, err = list_exists(listname)
    if not ok:
        eprint_red(str(err))
        return False, "LIST_EXISTS_FAILED"

    if not exists:
        print(f"SKIP REMOVE (list not found): {listname}")
        return True, "SKIPPED"

    # バックアップ（失敗したらスキップ）
    ok, backup_dir, err = backup_ml(listname)
    if not ok:
        eprint_red(str(err))
        return False, "BACKUP_FAILED"

    ok, _, err = purge_list(listname)
    if not ok:
        eprint_red(str(err))
        _ = restore_ml(listname, backup_dir)
        rm_tree(backup_dir)
        return False, "PURGE_FAILED"

    rm_tree(backup_dir)
    print(f"OK REMOVE {listname}")
    return True, "OK"


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {Path(sys.argv[0]).name} <csv_file>", file=sys.stderr)
        return 1
    csv_path = Path(sys.argv[1])

    if not csv_path.exists() or not csv_path.is_file():
        eprint_red(f"CSV not found or not a file: {csv_path}")
        return 1

    try:
        f = csv_path.open("r", encoding="utf-8", newline="")
    except Exception as e:
        eprint_red(f"Failed to open CSV: {e}")
        return 1

    with f:
        reader = csv.reader(f)
        for idx, row in enumerate(reader, start=1):
            if not row or all((c or "").strip() == "" for c in row):
                continue
            if len(row) < 3:
                eprint_red(f"{idx}: invalid columns (need CMD,LISTNAME,DESCRIPTION)")
                return 1

            cmd = (row[0] or "").strip().upper()
            listname = (row[1] or "").strip()
            description = (row[2] or "").strip()

            if cmd not in {"CREATE", "REPLACE", "REMOVE"}:
                eprint_red(f"{idx}: invalid CMD '{cmd}'")
                return 1

            import re as _re
            if not _re.match(r"^[a-z0-9][a-z0-9.+_-]*$", listname):
                eprint_red(f"{idx}: invalid LISTNAME '{listname}'")
                return 1

            try:
                if cmd == "CREATE":
                    ok, _ = handle_create(listname, description)
                    if not ok:
                        continue
                elif cmd == "REPLACE":
                    ok, _ = handle_replace(listname, description)
                    if not ok:
                        continue
                elif cmd == "REMOVE":
                    ok, _ = handle_remove(listname)
                    if not ok:
                        continue
            except Exception as e:
                eprint_red(f"{idx}: unexpected error: {e}")
                continue

    return 0


if __name__ == "__main__":
    sys.exit(main())
