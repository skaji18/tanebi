"""TANEBI 設定モジュール。yaml.safe_load ベース、1回読んでキャッシュ。"""

import os
from pathlib import Path
import yaml

__all__ = [
    "load_config", "get", "validate_config", "get_path", "_reset_cache",
    "TANEBI_ROOT", "WORK_DIR", "KNOWLEDGE_DIR", "EPISODE_DIR",
]

_cache: dict | None = None
_root_cache: Path | None = None


def _find_tanebi_root(start=None) -> Path:
    """Locate TANEBI root by searching upward for config.yaml."""
    if 'TANEBI_ROOT' in os.environ:
        return Path(os.environ['TANEBI_ROOT'])
    if start is None:
        # src/tanebi/config/__init__.py → 4段上がる
        start = Path(__file__).parent.parent.parent.parent
    return start


def load_config(tanebi_root=None) -> dict:
    """Load config.yaml and cache. Returns full dict."""
    global _cache, _root_cache
    if _cache is not None:
        return _cache
    root = Path(tanebi_root) if tanebi_root else _find_tanebi_root()
    _root_cache = root
    config_path = root / "config.yaml"
    _cache = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            _cache = yaml.safe_load(f) or {}
    _cache["_root"] = str(root)
    validate_config(_cache)
    return _cache


def get(key: str, default=None):
    """Dot-separated key access: get('tanebi.execution.timeout')."""
    cfg = load_config()
    parts = key.split(".")
    val = cfg
    for part in parts:
        if isinstance(val, dict):
            val = val.get(part)
        else:
            return default
        if val is None:
            return default
    return val


def validate_config(config: dict) -> None:
    """Validate required config fields."""
    tanebi = config.get("tanebi", {}) or {}
    paths = tanebi.get("paths", {}) or {}
    # flat or nested tanebi.paths.work_dir 形式でチェック
    work_dir = config.get("work_dir") or paths.get("work_dir")
    if not work_dir:
        raise ValueError("Missing required config field: work_dir")


def get_path(key: str, default=None, tanebi_root=None) -> str | None:
    """Get absolute path from config."""
    if tanebi_root:
        root = Path(tanebi_root)
    else:
        load_config()
        root = _root_cache or _find_tanebi_root()
    cfg = load_config(tanebi_root)
    rel = cfg.get(key, default)
    if rel is None:
        return None
    return str(root / rel)


def _reset_cache() -> None:
    """Reset config cache (for tests)."""
    global _cache, _root_cache
    _cache = None
    _root_cache = None


# パス定数（モジュールレベルで export）
def _init_paths():
    global TANEBI_ROOT, WORK_DIR, KNOWLEDGE_DIR, EPISODE_DIR
    root = _find_tanebi_root()
    cfg = load_config(root)
    TANEBI_ROOT = str(root)
    WORK_DIR = str(root / cfg.get("work_dir", "work"))
    KNOWLEDGE_DIR = str(root / cfg.get("knowledge_dir", "knowledge"))
    EPISODE_DIR = str(root / cfg.get("episode_dir", "knowledge/episodes"))


_init_paths()
