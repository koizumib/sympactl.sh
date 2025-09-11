from __future__ import annotations

import csv
import re
import os
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Dict, Tuple, Any

# === 設定 ===
#  同ディレクトリ or パッケージ配下の config.py から読み込む
try:
    from .config import SYMPA_CMD, LISTDATA_DIR, DOMAIN  # type: ignore
except Exception:
    from config import SYMPA_CMD, LISTDATA_DIR, DOMAIN

assert isinstance(SYMPA_CMD, str)
assert isinstance(LISTDATA_DIR, (str, Path))
assert isinstance(DOMAIN, str)
LISTDATA_DIR = Path(LISTDATA_DIR)


# === 例外型 ===
class SympaError(RuntimeError):
    pass


# === Sympa コマンドの汎用実行関数 ===
# 返り値は (returncode, stdout, stderr)
# rc != 0 のときは stdout/stderr にエラーメッセージが入る（呼び出し側で err に整形）
def run_sympa(args: List[str], input_text: str | None = None) -> Tuple[int, str, str]:
    cmd = [SYMPA_CMD, *args]
    proc = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


# === 役割定義 ===
class Role(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"
    MEMBER = "member"


# === ヘルパー ===
def _ok(result: Any = None) -> Tuple[bool, Any, None]:
    return True, result, None

def _ng(message: str, *, cmd_desc: str | None = None) -> Tuple[bool, None, Exception]:
    prefix = f"[{cmd_desc}] " if cmd_desc else ""
    return False, None, SympaError(prefix + message)


# === 存在確認・一覧 ===
def list_exists(listname: str) -> Tuple[bool, bool, Exception | None]:
    rc, out, err = run_sympa(["export_list", DOMAIN])
    if rc != 0:
        return _ng(
            f"export_list 失敗 rc={rc}\nSTDOUT:\n{out}\nSTDERR:\n{err}",
            cmd_desc="export_list",
        )
    exists = any(line.strip() == listname for line in out.splitlines())
    return _ok(exists)

def get_all_lists() -> Tuple[bool, List[str], Exception | None]:
    rc, out, err = run_sympa(["export_list", DOMAIN])
    if rc != 0:
        return _ng(
            f"export_list 失敗 rc={rc}\nSTDOUT:\n{out}\nSTDERR:\n{err}",
            cmd_desc="export_list",
        )
    lists = [line.strip() for line in out.splitlines() if line.strip()]
    return _ok(lists)


# === メーリングリスト操作 ===
def purge_list(listname: str) -> Tuple[bool, None, Exception | None]:
    rc, out, err = run_sympa(["--purge_list", f"{listname}@{DOMAIN}"])
    if rc != 0:
        return _ng(
            f"purge_list 失敗 rc={rc}\nSTDOUT:\n{out}\nSTDERR:\n{err}",
            cmd_desc="purge_list",
        )
    return _ok()

def close_list(listname: str) -> Tuple[bool, None, Exception | None]:
    rc, out, err = run_sympa(["--close_list", f"{listname}@{DOMAIN}"])
    if rc != 0:
        return _ng(
            f"close_list 失敗 rc={rc}\nSTDOUT:\n{out}\nSTDERR:\n{err}",
            cmd_desc="close_list",
        )
    return _ok()

def create_list(xml_file: Path | str) -> Tuple[bool, str, Exception | None]:
    xml_file = str(xml_file)
    rc, out, err = run_sympa(["--create_list", "--robot", DOMAIN, "--input_file", xml_file])
    if rc != 0:
        return _ng(
            f"create_list 失敗 rc={rc}\nSTDOUT:\n{out}\nSTDERR:\n{err}",
            cmd_desc="create_list",
        )
    return _ok(out)

def _add_role_from_file(listname: str, role: Role, file_path: Path | str) -> Tuple[bool, None, Exception | None]:
    p = Path(file_path)
    if not p.exists():
        return _ng(f"ファイルが存在しません: {p}")
    input_text = p.read_text(encoding="utf-8")
    rc, out, err = run_sympa(
        ["add", "--quiet", f"--role={role.value}", f"{listname}@{DOMAIN}"],
        input_text=input_text,
    )
    if rc != 0:
        return _ng(
            f"add 失敗 role={role.value} rc={rc}\nSTDOUT:\n{out}\nSTDERR:\n{err}",
            cmd_desc="add",
        )
    return _ok()

def add_members(listname: str, member_file: Path | str) -> Tuple[bool, None, Exception | None]:
    return _add_role_from_file(listname, Role.MEMBER, member_file)

def add_editor(listname: str, editor_file: Path | str) -> Tuple[bool, None, Exception | None]:
    return _add_role_from_file(listname, Role.EDITOR, editor_file)

def add_owners(listname: str, owner_file: Path | str) -> Tuple[bool, None, Exception | None]:
    return _add_role_from_file(listname, Role.OWNER, owner_file)

def _del_role(listname: str, role: Role) -> Tuple[bool, None, Exception | None]:
    ok, emails, err = get_list_emails(listname, role.value)
    if not ok:
        return False, None, err
    if not emails:
        return _ok()
    input_text = "\n".join(emails) + "\n"
    rc, out, serr = run_sympa(
        ["del", "--quiet", f"--role={role.value}", f"{listname}@{DOMAIN}"],
        input_text=input_text,
    )
    if rc != 0:
        return _ng(
            f"del 失敗 role={role.value} rc={rc}\nSTDOUT:\n{out}\nSTDERR:\n{serr}",
            cmd_desc="del",
        )
    return _ok()

def del_members(listname: str) -> Tuple[bool, None, Exception | None]:
    return _del_role(listname, Role.MEMBER)

def del_editors(listname: str) -> Tuple[bool, None, Exception | None]:
    return _del_role(listname, Role.EDITOR)

def del_owners(listname: str) -> Tuple[bool, None, Exception | None]:
    return _del_role(listname, Role.OWNER)


# === dump/抽出 ===
def dump_list_roles(listname: str) -> Tuple[bool, None, Exception | None]:
    rc, out, err = run_sympa(["dump", "--roles=member,owner,editor", f"{listname}@{DOMAIN}"])
    if rc != 0:
        return _ng(
            f"dump 失敗 rc={rc}\nSTDOUT:\n{out}\nSTDERR:\n{err}",
            cmd_desc="dump",
        )
    return _ok()

def extract_emails_from_dump(file: Path | str) -> Tuple[bool, List[str], Exception | None]:
    p = Path(file)
    if not p.exists():
        return _ok([])
    emails: List[str] = []
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("email "):
                parts = line.strip().split()
                if len(parts) >= 2:
                    emails.append(parts[1])
    return _ok(emails)

def get_list_emails(listname: str, role: str) -> Tuple[bool, List[str], Exception | None]:
    ok, _, err = dump_list_roles(listname)
    if not ok:
        return False, None, err  # type: ignore[return-value]
    file = LISTDATA_DIR / listname / f"{role}.dump"
    return extract_emails_from_dump(file)

def parse_list_roles(listname: str) -> Tuple[bool, Dict[str, List[str]], Exception | None]:
    ok, _, err = dump_list_roles(listname)
    if not ok:
        return False, None, err  # type: ignore[return-value]
    listdir = LISTDATA_DIR / listname
    result: Dict[str, List[str]] = {"owner": [], "editor": [], "member": []}
    for role in ("owner", "editor", "member"):
        f = listdir / f"{role}.dump"
        ok2, emails, err2 = extract_emails_from_dump(f)
        if not ok2:
            return False, None, err2  # type: ignore[return-value]
        result[role] = emails
    return _ok(result)


# === バックアップ/リストア ===

def mktemp_with_content(prefix: str, suffix: str = "", content: str = "") -> Path:
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)  # 重要: fd を閉じる
    p = Path(path)
    p.write_text(content, encoding="utf-8")
    p.chmod(0o644)
    return p


def backup_ml(listname: str) -> Tuple[bool, Path, Exception | None]:
    ok, _, err = dump_list_roles(listname)
    if not ok:
        return False, None, err  # type: ignore[return-value]
    src_dir = LISTDATA_DIR / listname
    backup_dir = mktemp_with_content(prefix=f"sympa_ml_backup_{listname}_")
    if src_dir.is_dir():
        for pat in ("*.dump", "config*"):
            for src in src_dir.glob(pat):
                (backup_dir / src.name).write_bytes(src.read_bytes())
    return _ok(backup_dir)

def restore_ml(listname: str, backup_dir: Path | str) -> Tuple[bool, None, Exception | None]:
    bdir = Path(backup_dir)
    if not bdir.is_dir():
        return _ng(f"Backup directory does not exist: {bdir}")
    ok, _, err = del_members(listname)
    if not ok:
        return False, None, err
    ok, _, err = del_editors(listname)
    if not ok:
        return False, None, err
    ok, _, err = del_owners(listname)
    if not ok:
        return False, None, err
    dst_dir = LISTDATA_DIR / listname
    dst_dir.mkdir(parents=True, exist_ok=True)
    for item in bdir.iterdir():
        if item.is_file():
            (dst_dir / item.name).write_bytes(item.read_bytes())
    rc, out, serr = run_sympa(["restore", "--roles=member,owner,editor", f"{listname}@{DOMAIN}"])
    if rc != 0:
        return _ng(
            f"restore 失敗 rc={rc}\nSTDOUT:\n{out}\nSTDERR:\n{serr}",
            cmd_desc="restore",
        )
    return _ok()


# === .list ファイルパーサ ===
@dataclass
class MLFile:
    owners: List[str]
    editors: List[str]
    members: List[str]

_SECTION_RE = re.compile(r"^\[(owner|editor|member)\]\s*$")

def load_ml_file(path: Path | str) -> Tuple[bool, MLFile, Exception | None]:
    p = Path(path)
    if not p.exists():
        return _ng(f"ファイルが存在しません: {p}")
    if not p.exists() or not p.is_file():
        return _ng(f"ファイルが読み取れません: {p}")

    owners: List[str] = []
    editors: List[str] = []
    members: List[str] = []

    section: str | None = None
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.split("#", 1)[0].split(";", 1)[0].strip()
            if not line:
                continue
            m = _SECTION_RE.match(line)
            if m:
                section = m.group(1)
                continue
            if line.startswith("[") and line.endswith("]"):
                return _ng(f"不明なセクション: {line}")
            if not section:
                return _ng(f"セクション定義前に値があります: {line}")
            if section == "owner":
                owners.append(line)
            elif section == "editor":
                editors.append(line)
            elif section == "member":
                members.append(line)

    return _ok(MLFile(owners=owners, editors=editors, members=members))


# ---- CSV 書式チェック／パース ----
_CMD_SET = {"CREATE", "REPLACE", "REMOVE"}
_LISTNAME_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+$")

@dataclass
class CsvRecord:
    cmd: str
    listname: str

def parse_csv_with_validation(path: Path | str) -> Tuple[bool, List[CsvRecord], Exception | None]:
    p = Path(path)
    if not p.exists():
        return _ng(f"CSV が見つかりません: {p}")

    records: List[CsvRecord] = []
    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for lineno, row in enumerate(reader, start=1):
            if not row or all((col or "").strip() == "" for col in row):
                continue
            if len(row) < 2:
                return _ng(f"{lineno} 行目: カラム数が不足しています (期待: 2 以上, 実際: {len(row)})")
            cmd = (row[0] or "").strip().upper()
            listname = (row[1] or "").strip()
            if cmd not in _CMD_SET:
                return _ng(f"{lineno} 行目: 不正なコマンド '{cmd}'（許可: {sorted(_CMD_SET)}）")
            if not _LISTNAME_RE.match(listname):
                return _ng(f"{lineno} 行目: 不正なリスト名 '{listname}'")
            records.append(CsvRecord(cmd=cmd, listname=listname))

    return _ok(records)

def validate_csv_format(path: Path | str) -> Tuple[bool, None, Exception | None]:
    ok, _, err = parse_csv_with_validation(path)
    if not ok:
        return False, None, err
    return _ok()

def escape_xml(s: str) -> str:
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    s = s.replace("'", "&apos;")
    return s


def generate_list_xml(listname: str, subject: str, description: str, owners_csv: str, list_type: str) -> str:
    if not re.match(r"^[a-z0-9][a-z0-9.+_-]*$", listname):
        raise ValueError("listname must contain only alphanumeric/underscore/hyphen")

    seen = set()
    norm_owners: List[str] = []
    for x in owners_csv.split(","):
        x = x.strip()
        if not x:
            continue
        if x not in seen:
            norm_owners.append(x)
            seen.add(x)

    owners_xml = "\n".join(
        f"    <owner multiple=\"1\">\n        <email>{escape_xml(o)}</email>\n    </owner>"
        for o in norm_owners
    )

    return f"""<?xml version='1.0' encoding='utf-8'?>
<list>
    <listname>{escape_xml(listname)}</listname>
    <type>{escape_xml(list_type)}</type>
    <subject>{escape_xml(subject)}</subject>
    <description>{escape_xml(description)}</description>
    <status>open</status>
    <language>ja</language>
{owners_xml}
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
</list>"""


__all__ = [
    # 設定
    "SYMPA_CMD",
    "LISTDATA_DIR",
    "DOMAIN",
    # 例外
    "SympaError",
    # 汎用実行
    "run_sympa",
    # 存在確認・一覧
    "list_exists",
    "get_all_lists",
    # 役割 dump/抽出
    "dump_list_roles",
    "extract_emails_from_dump",
    "get_list_emails",
    "parse_list_roles",
    # 操作
    "purge_list",
    "close_list",
    "create_list",
    "add_members",
    "add_editor",
    "add_owners",
    "del_members",
    "del_editors",
    "del_owners",
    # バックアップ/リストア
    "backup_ml",
    "restore_ml",
    # .list
    "MLFile",
    "load_ml_file",
    # CSV
    "CsvRecord",
    "parse_csv_with_validation",
    "validate_csv_format",
    "generate_list_xml", 
    "mktemp_with_content", 
]
