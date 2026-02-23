"""共通テストフィクスチャ"""
import pytest
from pathlib import Path


@pytest.fixture
def tmp_tanebi_root(tmp_path):
    """一時的なTANEBI_ROOTディレクトリを作成するフィクスチャ"""
    root = tmp_path / "tanebi_test"
    (root / "work").mkdir(parents=True)
    (root / "personas" / "active").mkdir(parents=True)
    (root / "personas" / "library" / "templates").mkdir(parents=True)
    (root / "knowledge" / "few_shot_bank").mkdir(parents=True)
    (root / "plugins").mkdir(parents=True)
    (root / "events").mkdir(parents=True)
    return root


@pytest.fixture
def sample_config(tmp_tanebi_root):
    """テスト用config.yamlを作成するフィクスチャ"""
    config = {
        "tanebi": {
            "paths": {
                "work_dir": str(tmp_tanebi_root / "work"),
                "personas_dir": str(tmp_tanebi_root / "personas"),
            },
            "execution": {
                "max_parallel_workers": 3,
                "worker_max_turns": 50,
                "default_model": "claude-sonnet-4-5",
            },
            "plugins": {
                "enabled": [],
            },
        }
    }
    import yaml
    config_path = tmp_tanebi_root / "config.yaml"
    config_path.write_text(yaml.dump(config))
    return config_path
