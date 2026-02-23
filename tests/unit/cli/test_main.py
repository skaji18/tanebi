"""Tests for tanebi CLI main entrypoint."""
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


def test_tanebi_help():
    """tanebi --help が正常に動作することを確認。"""
    result = subprocess.run(
        [sys.executable, "-m", "tanebi.cli.main", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "tanebi" in result.stdout


def test_tanebi_subcommands_registered():
    """listener / new / persona / status / config サブコマンドが --help に表示されることを確認。"""
    result = subprocess.run(
        [sys.executable, "-m", "tanebi.cli.main", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "listener" in result.stdout
    assert "new" in result.stdout
    assert "persona" in result.stdout
    assert "status" in result.stdout
    assert "config" in result.stdout


def test_tanebi_status_no_task_id(tmp_path):
    """status コマンドが正常終了する（work_dir空でも）"""
    import argparse
    from tanebi.cli.main import _status

    with patch("tanebi.config.WORK_DIR", str(tmp_path / "empty_work")):
        args = argparse.Namespace(task_id=None)
        _status(args)  # should not raise; work_dir does not exist → "(no work directory)"


def test_tanebi_config():
    """config コマンドが正常終了する"""
    result = subprocess.run(
        [sys.executable, "-m", "tanebi.cli.main", "config"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "=" in result.stdout  # キー=値 形式で何か出力されている
