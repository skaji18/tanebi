"""TANEBI P4-6: 堅牢性テスト — エッジケースと異常系の動作確認"""
from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from tanebi import api
from tanebi.executor.listener import try_claim
from tanebi.executor.worker import run_claude_p


def test_submit_empty_request(tmp_tanebi_root):
    """空リクエスト（""）でsubmitした時の動作確認。

    submit は request の内容をバリデートしない仕様のため、正常に処理される。
    """
    task_id = api.submit("", project_dir=tmp_tanebi_root)
    assert isinstance(task_id, str)
    assert task_id.startswith("cmd_")
    # request.md が空ファイルとして作成される
    request_path = tmp_tanebi_root / "work" / task_id / "request.md"
    assert request_path.exists()
    assert request_path.read_text(encoding="utf-8") == ""


def test_status_nonexistent_task(tmp_tanebi_root):
    """存在しない task_id で api.status() を呼ぶ → not_found 応答"""
    s = api.status("cmd_999", project_dir=tmp_tanebi_root)
    assert s["task_id"] == "cmd_999"
    assert s["state"] == "not_found"
    assert s["event_count"] == 0
    assert s["last_event"] is None
    assert s["events"] == []


def test_worker_timeout(tmp_path):
    """subprocess.run が TimeoutExpired を発生させた場合、例外が伝播する。

    run_claude_p は TimeoutExpired を捕捉しないため、呼び出し元に伝播する。
    """
    timeout_exc = subprocess.TimeoutExpired(cmd=["claude", "-p"], timeout=30)
    with patch("subprocess.run", side_effect=timeout_exc):
        with pytest.raises(subprocess.TimeoutExpired):
            run_claude_p("system prompt", "user prompt", timeout=30)


def test_try_claim_prevents_duplicate_execution(tmp_path):
    """同一イベントに対して try_claim を2回呼ぶと、2回目は False を返す。

    これにより複数 Executor による重複実行が防止されることを保証する。
    """
    # ダミーのイベントファイルを作成
    event_path = tmp_path / "001_execute.requested.yaml"
    event_path.write_text("event_type: execute.requested\n", encoding="utf-8")

    # 1回目: claim に成功 → True
    assert try_claim(event_path) is True
    # .claimed ファイルが作成されている
    assert event_path.with_suffix(".claimed").exists()

    # 2回目: 既に claim 済み → False (重複実行を防止)
    assert try_claim(event_path) is False
