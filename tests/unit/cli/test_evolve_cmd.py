"""tanebi.cli.evolve_cmd のユニットテスト"""
import subprocess
import sys


def test_evolve_subcommand_registered():
    """tanebi --help に evolve サブコマンドが表示されること。"""
    result = subprocess.run(
        [sys.executable, "-m", "tanebi.cli.main", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "evolve" in result.stdout, (
        f"'evolve' not found in --help output:\n{result.stdout}"
    )
