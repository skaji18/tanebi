"""tanebi.executor.worker のユニットテスト"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tanebi.executor.worker import WorkerError, read_template, run_claude_p


def test_run_claude_p_success():
    """subprocess.run をモックして正常系を検証。"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Hello, world!"

    with patch("tanebi.executor.worker.subprocess.run", return_value=mock_result) as mock_run:
        output = run_claude_p("sys prompt", "user prompt")

    assert output == "Hello, world!"
    mock_run.assert_called_once()


def test_run_claude_p_failure():
    """returncode=1 のとき WorkerError が送出されること。"""
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "error message"

    with patch("tanebi.executor.worker.subprocess.run", return_value=mock_result):
        with pytest.raises(WorkerError):
            run_claude_p("sys prompt", "user prompt")


def test_run_claude_p_removes_env():
    """CLAUDECODE / CLAUDE_CODE_ENTRYPOINT が env に含まれないことを確認。"""
    import os

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""

    with patch.dict(os.environ, {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "something"}):
        with patch("tanebi.executor.worker.subprocess.run", return_value=mock_result) as mock_run:
            run_claude_p("sys", "user")

    _, kwargs = mock_run.call_args
    passed_env = kwargs["env"]
    assert "CLAUDECODE" not in passed_env
    assert "CLAUDE_CODE_ENTRYPOINT" not in passed_env


def test_run_claude_p_stdin():
    """user_prompt が stdin (input=) で渡されることを確認。"""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""

    with patch("tanebi.executor.worker.subprocess.run", return_value=mock_result) as mock_run:
        run_claude_p("sys", "my user prompt")

    _, kwargs = mock_run.call_args
    assert kwargs["input"] == "my user prompt"


def test_read_template_not_found():
    """存在しないテンプレート → FileNotFoundError が送出されること。"""
    with pytest.raises(FileNotFoundError):
        read_template("nonexistent_template_xyz.md")
