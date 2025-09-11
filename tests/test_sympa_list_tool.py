# tests/test_sympa_list_tool.py
import sys
from types import ModuleType
from pathlib import Path
import pytest

# tests/conftest.py
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "/root/sympactl.dev"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

@pytest.fixture(autouse=True)
def fake_config(monkeypatch, tmp_path):
    """
    sympa_list_tool が import する config をテスト用に差し替える。
    LISTDATA_DIR は tmp_path/list_data を使う。
    """
    m = ModuleType("config")
    m.SYMPA_CMD = "/usr/sbin/sympa"  # 値は任意（subprocess をモックするため実行されない）
    m.LISTDATA_DIR = tmp_path / "list_data"
    m.LISTDATA_DIR.mkdir(parents=True, exist_ok=True)
    m.DOMAIN = "sympa.dg-verification.net"
    sys.modules["config"] = m
    yield

@pytest.fixture
def sut():
    """
    System Under Test: sympa_list_tool
    """
    import importlib
    return importlib.import_module("sympa_list_tool")

@pytest.fixture
def fake_subprocess(monkeypatch):
    """
    subprocess.run をモック。コマンドに応じて rc/stdout/stderr を返す。
    検証用に last_cmd/inputs を保持。
    """
    class Proc:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    state = {"last_cmd": None, "inputs": []}

    def fake_run(cmd, input=None, text=None, capture_output=None, check=None):
        state["last_cmd"] = cmd
        state["inputs"].append(input or "")
        # cmd = [SYMPA_CMD, <subcmd>, ...]
        subcmd = cmd[1] if len(cmd) >= 2 else ""

        if subcmd == "export_list":
            return Proc(0, stdout="listA\nlistB\n", stderr="")
        if subcmd == "dump":
            return Proc(0, stdout="", stderr="")
        if subcmd == "restore":
            return Proc(0, stdout="restored\n", stderr="")
        if subcmd == "add":
            return Proc(0, stdout="added\n", stderr="")
        if subcmd == "del":
            return Proc(0, stdout="deleted\n", stderr="")
        if subcmd == "--purge_list":
            return Proc(0, stdout="purged\n", stderr="")
        if subcmd == "--close_list":
            return Proc(0, stdout="closed\n", stderr="")
        if subcmd == "--create_list":
            return Proc(0, stdout="created\n", stderr="")

        return Proc(0, stdout="", stderr="")

    import subprocess
    monkeypatch.setattr(subprocess, "run", fake_run)
    return state

def test_run_sympa(sut, fake_subprocess):
    rc, out, err = sut.run_sympa(["export_list", "sympa.dg-verification.net"])
    assert rc == 0 and "listA" in out and err == ""
    assert fake_subprocess["last_cmd"][1] == "export_list"

def test_list_exists(sut):
    ok, exists, err = sut.list_exists("listA")
    assert ok and exists and err is None
    ok, exists, err = sut.list_exists("not-exists")
    assert ok and (exists is False) and err is None

def test_get_all_lists(sut):
    ok, lists, err = sut.get_all_lists()
    assert ok and lists == ["listA", "listB"] and err is None

def test_create_close_purge(sut, fake_subprocess, tmp_path):
    ok, out, err = sut.create_list(tmp_path / "dummy.xml")
    assert ok and "created" in out and err is None
    assert fake_subprocess["last_cmd"][1] == "--create_list"

    ok, _, err = sut.close_list("listA")
    assert ok and err is None
    assert fake_subprocess["last_cmd"][1] == "--close_list"
    assert fake_subprocess["last_cmd"][-1].endswith("@sympa.dg-verification.net")

    ok, _, err = sut.purge_list("listB")
    assert ok and err is None
    assert fake_subprocess["last_cmd"][1] == "--purge_list"
    assert fake_subprocess["last_cmd"][-1].endswith("@sympa.dg-verification.net")

def test_add_and_delete_members(sut, tmp_path):
    # 追加用ファイル
    members = tmp_path / "members.txt"
    members.write_text("alice@dg-verification.net\nbob@dg-verification.net\n", encoding="utf-8")
    ok, _, err = sut.add_members("team", members)
    assert ok and err is None

    # del 用 dump 準備
    list_dir = (tmp_path / "list_data" / "team")
    list_dir.mkdir(parents=True, exist_ok=True)
    (list_dir / "member.dump").write_text(
        "email alice@dg-verification.net\nemail bob@dg-verification.net\n", encoding="utf-8"
    )
    ok, _, err = sut.del_members("team")
    assert ok and err is None

def test_extract_emails_from_dump(sut, tmp_path):
    dumpf = tmp_path / "member.dump"
    dumpf.write_text("email a@dg-verification.net\nx\naaa\nemail b@dg-verification.net\n", encoding="utf-8")
    ok, emails, err = sut.extract_emails_from_dump(dumpf)
    assert ok and emails == ["a@dg-verification.net", "b@dg-verification.net"] and err is None

def test_get_list_emails_and_parse_list_roles(sut, tmp_path):
    # dump はモックで rc=0 を返す想定。dump 後に LISTDATA_DIR を読む。
    list_dir = (tmp_path / "list_data" / "dev")
    list_dir.mkdir(parents=True, exist_ok=True)
    (list_dir / "owner.dump").write_text("email o@dg-verification.net\n", encoding="utf-8")
    (list_dir / "editor.dump").write_text("email e1@dg-verification.net\nemail e2@dg-verification.net\n", encoding="utf-8")
    (list_dir / "member.dump").write_text("email m@dg-verification.net\n", encoding="utf-8")

    ok, emails, err = sut.get_list_emails("dev", "editor")
    assert ok and emails == ["e1@dg-verification.net", "e2@dg-verification.net"] and err is None

    ok, roles, err = sut.parse_list_roles("dev")
    assert ok and roles == {
        "owner": ["o@dg-verification.net"],
        "editor": ["e1@dg-verification.net", "e2@dg-verification.net"],
        "member": ["m@dg-verification.net"],
    } and err is None

def test_backup_and_restore(sut, tmp_path):
    # dump -> 0 はモック
    list_dir = tmp_path / "list_data" / "ops"
    list_dir.mkdir(parents=True, exist_ok=True)
    (list_dir / "member.dump").write_text("email x@dg-verification.net\n", encoding="utf-8")
    (list_dir / "config").write_text("k=v\n", encoding="utf-8")

    ok, backup_dir, err = sut.backup_ml("ops")
    assert ok and backup_dir.exists() and err is None
    assert (backup_dir / "member.dump").exists()
    assert (backup_dir / "config").exists()

    # 消してから restore
    for f in list_dir.iterdir():
        f.unlink()
    assert not any(list_dir.iterdir())

    ok, _, err = sut.restore_ml("ops", backup_dir)
    assert ok and err is None
    assert (list_dir / "member.dump").exists()
    assert (list_dir / "config").exists()

def test_load_ml_file(sut, tmp_path):
    p = tmp_path / "sample.list"
    p.write_text(
        """
        # comment
        [owner]
        owner1@dg-verification.net
        ; inline comment
        [editor]
        editor1@dg-verification.net
        [member]
        m1@dg-verification.net
        m2@dg-verification.net
        """,
        encoding="utf-8",
    )
    ok, ml, err = sut.load_ml_file(p)
    assert ok and err is None
    assert ml.owners == ["owner1@dg-verification.net"]
    assert ml.editors == ["editor1@dg-verification.net"]
    assert ml.members == ["m1@dg-verification.net", "m2@dg-verification.net"]

def test_parse_csv_with_validation_and_validate(sut, tmp_path):
    csvf = tmp_path / "ops.csv"
    csvf.write_text("CREATE,team\nREPLACE,dev\nREMOVE,old-team\n", encoding="utf-8")
    ok, records, err = sut.parse_csv_with_validation(csvf)
    assert ok and err is None
    assert [r.cmd for r in records] == ["CREATE", "REPLACE", "REMOVE"]
    assert [r.listname for r in records] == ["team", "dev", "old-team"]

    ok, _, err = sut.validate_csv_format(csvf)
    assert ok and err is None

def test_parse_csv_with_validation_bad(sut, tmp_path):
    csvf = tmp_path / "bad.csv"
    csvf.write_text("CREATE\n", encoding="utf-8")  # カラム不足
    ok, _, err = sut.parse_csv_with_validation(csvf)
    assert ok is False and isinstance(err, Exception)
