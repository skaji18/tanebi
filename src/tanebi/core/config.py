"""TANEBI 設定モジュール。config.yaml を読み取り、各パスを提供する。"""

import os
import re
from pathlib import Path

__all__ = [
    "load_config",
    "get_path",
    "TANEBI_ROOT",
    "PERSONA_DIR",
    "LIBRARY_DIR",
    "HISTORY_DIR",
    "WORK_DIR",
    "FEW_SHOT_DIR",
    "KNOWLEDGE_DIR",
    "EPISODE_DIR",
]


def _find_tanebi_root(start=None):
    """Locate TANEBI root by searching upward for config.yaml."""
    if 'TANEBI_ROOT' in os.environ:
        return Path(os.environ['TANEBI_ROOT'])
    # パッケージパスから逆算: src/tanebi/core/config.py → 4段上がる
    if start is None:
        start = Path(__file__).parent.parent.parent.parent
    return start


def load_config(tanebi_root=None):
    """Load config.yaml and return as dict (lightweight, no PyYAML needed)."""
    root = Path(tanebi_root) if tanebi_root else _find_tanebi_root()
    config_path = root / 'config.yaml'
    config = {'_root': str(root)}
    if config_path.exists():
        with open(config_path) as f:
            for line in f:
                m = re.match(r'^\s*(\w+):\s*(.+)', line)
                if m:
                    key = m.group(1).strip()
                    val = m.group(2).strip().strip('"').strip("'")
                    config[key] = val
    return config


def get_path(key, default=None, tanebi_root=None):
    """Get an absolute path from config (joins root + relative path)."""
    root = Path(tanebi_root) if tanebi_root else _find_tanebi_root()
    config = load_config(root)
    rel = config.get(key, default)
    if rel is None:
        return None
    return str(root / rel)


# 便利定数（他スクリプトが直接 import して使える）
_root = _find_tanebi_root()
_cfg = load_config(_root)

TANEBI_ROOT = str(_root)
PERSONA_DIR = str(_root / _cfg.get('persona_dir', 'personas/active'))
LIBRARY_DIR = str(_root / _cfg.get('library_dir', 'personas/library'))
HISTORY_DIR = str(_root / _cfg.get('history_dir', 'personas/history'))
WORK_DIR = str(_root / _cfg.get('work_dir', 'work'))
FEW_SHOT_DIR = str(_root / _cfg.get('few_shot_dir', 'knowledge/few_shot_bank'))
KNOWLEDGE_DIR = str(_root / _cfg.get('knowledge_dir', 'knowledge'))
EPISODE_DIR = str(_root / _cfg.get('episode_dir', 'knowledge/episodes'))
