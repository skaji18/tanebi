"""Tests for tanebi CLI main entrypoint."""
import subprocess
import sys


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
    """listener と new サブコマンドが --help に表示されることを確認。"""
    result = subprocess.run(
        [sys.executable, "-m", "tanebi.cli.main", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "listener" in result.stdout
    assert "new" in result.stdout
