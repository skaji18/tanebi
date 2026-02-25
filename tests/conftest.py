"""共通テストフィクスチャ"""
import pytest
from pathlib import Path


@pytest.fixture
def tmp_tanebi_root(tmp_path):
    """一時的なTANEBI_ROOTディレクトリを作成するフィクスチャ"""
    root = tmp_path / "tanebi_test"
    (root / "work").mkdir(parents=True)
    (root / "plugins").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    return root
