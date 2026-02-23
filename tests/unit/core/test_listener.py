"""CoreListener のユニットテスト"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from tanebi.core.listener import CoreListener


@pytest.fixture
def tmp_root(tmp_path):
    """作業ディレクトリを持つ一時的な tanebi_root"""
    task_dir = tmp_path / "work" / "cmd_test" / "events"
    task_dir.mkdir(parents=True)
    return tmp_path


def _write_event(events_dir: Path, filename: str, payload: dict) -> Path:
    event_path = events_dir / filename
    event_path.write_text(yaml.dump({"payload": payload}))
    return event_path


def test_core_listener_dispatches_task_created(tmp_root):
    """task.created イベント → flow.on_task_created が呼ばれる"""
    events_dir = tmp_root / "work" / "cmd_test" / "events"
    event_path = _write_event(events_dir, "001_task.created.yaml", {"key": "val"})

    listener = CoreListener(tmp_root)
    with patch("tanebi.core.flow.on_task_created") as mock_fn:
        listener.on_created(event_path)
        mock_fn.assert_called_once()
        call_args = mock_fn.call_args
        assert call_args[0][0] == tmp_root / "work" / "cmd_test"
        assert call_args[0][1] == {"key": "val"}


def test_core_listener_dispatches_worker_completed(tmp_root):
    """worker.completed イベント → flow.on_worker_completed が呼ばれる"""
    events_dir = tmp_root / "work" / "cmd_test" / "events"
    event_path = _write_event(events_dir, "002_worker.completed.yaml", {"wave": 1})

    listener = CoreListener(tmp_root)
    with patch("tanebi.core.flow.on_worker_completed") as mock_fn:
        listener.on_created(event_path)
        mock_fn.assert_called_once()
        call_args = mock_fn.call_args
        assert call_args[0][1] == {"wave": 1}


def test_core_listener_ignores_non_yaml(tmp_root):
    """非 YAML ファイル（.claimed 等）→ 何もしない（例外なし）"""
    claimed_path = tmp_root / "work" / "cmd_test" / "events" / "001_task.created.claimed"
    claimed_path.touch()

    listener = CoreListener(tmp_root)
    with patch("tanebi.core.flow.on_task_created") as mock_fn:
        listener.on_created(claimed_path)
        mock_fn.assert_not_called()


def test_core_listener_ignores_unknown_event(tmp_root):
    """未知のイベントタイプ → 例外なし（no-op）"""
    events_dir = tmp_root / "work" / "cmd_test" / "events"
    event_path = _write_event(events_dir, "003_unknown.event.yaml", {})

    listener = CoreListener(tmp_root)
    # 例外が発生しないことを確認
    listener.on_created(event_path)
