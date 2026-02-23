"""tanebi.api のユニットテスト"""
import pytest
from pathlib import Path

from tanebi.api import submit, status, result


def test_submit_creates_task(tmp_tanebi_root):
    """submit後に work/cmd_001/ が作られる"""
    task_id = submit("テストリクエスト", project_dir=tmp_tanebi_root)
    cmd_dir = tmp_tanebi_root / "work" / task_id
    assert cmd_dir.exists()
    assert cmd_dir.is_dir()


def test_submit_returns_task_id(tmp_tanebi_root):
    """submit が task_id 文字列を返す"""
    task_id = submit("テストリクエスト", project_dir=tmp_tanebi_root)
    assert isinstance(task_id, str)
    assert task_id.startswith("cmd_")


def test_submit_sequential(tmp_tanebi_root):
    """2回 submit で cmd_001, cmd_002 が返る"""
    id1 = submit("最初のリクエスト", project_dir=tmp_tanebi_root)
    id2 = submit("2番目のリクエスト", project_dir=tmp_tanebi_root)
    assert id1 == "cmd_001"
    assert id2 == "cmd_002"


def test_status_not_found(tmp_tanebi_root):
    """存在しない task_id → state="not_found" """
    s = status("cmd_999", project_dir=tmp_tanebi_root)
    assert s["task_id"] == "cmd_999"
    assert s["state"] == "not_found"
    assert s["event_count"] == 0
    assert s["last_event"] is None
    assert s["events"] == []


def test_status_existing(tmp_tanebi_root):
    """submit後の status → state が "task.created" 等"""
    task_id = submit("テストリクエスト", project_dir=tmp_tanebi_root)
    s = status(task_id, project_dir=tmp_tanebi_root)
    assert s["task_id"] == task_id
    assert s["state"] == "task.created"
    assert s["event_count"] >= 1


def test_result_none(tmp_tanebi_root):
    """report.md なし → None"""
    task_id = submit("テストリクエスト", project_dir=tmp_tanebi_root)
    r = result(task_id, project_dir=tmp_tanebi_root)
    assert r is None


def test_result_with_report(tmp_tanebi_root):
    """report.md あり → 内容を返す"""
    task_id = submit("テストリクエスト", project_dir=tmp_tanebi_root)
    report_content = "# 完了報告\n\n作業が完了しました。"
    report_path = tmp_tanebi_root / "work" / task_id / "report.md"
    report_path.write_text(report_content, encoding="utf-8")
    r = result(task_id, project_dir=tmp_tanebi_root)
    assert r == report_content
