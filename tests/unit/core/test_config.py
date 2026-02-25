"""tanebi.config のユニットテスト"""
import pytest
from tanebi.config import validate_config, _reset_cache


@pytest.fixture(autouse=True)
def reset_config_cache():
    _reset_cache()
    yield
    _reset_cache()


def test_validate_config_ok():
    """Valid config with required field raises no error."""
    config = {"work_dir": "work"}
    validate_config(config)  # should not raise


def test_validate_config_missing_work_dir():
    """Config without work_dir raises ValueError."""
    config = {}
    with pytest.raises(ValueError, match="Missing required config field: work_dir"):
        validate_config(config)
