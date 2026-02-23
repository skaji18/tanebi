"""tanebi.config のユニットテスト"""
import pytest
from tanebi.config import validate_config, _reset_cache


@pytest.fixture(autouse=True)
def reset_config_cache():
    _reset_cache()
    yield
    _reset_cache()


def test_validate_config_ok():
    """Valid config with both required fields raises no error."""
    config = {"work_dir": "work", "persona_dir": "personas/active"}
    validate_config(config)  # should not raise


def test_validate_config_missing_work_dir():
    """Config without work_dir raises ValueError."""
    config = {"persona_dir": "personas/active"}
    with pytest.raises(ValueError, match="Missing required config field: work_dir"):
        validate_config(config)


def test_validate_config_missing_persona_dir():
    """Config without persona_dir raises ValueError."""
    config = {"work_dir": "work"}
    with pytest.raises(ValueError, match="Missing required config field: persona_dir"):
        validate_config(config)
