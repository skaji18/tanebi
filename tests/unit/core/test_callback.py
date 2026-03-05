"""tanebi.core.callback のユニットテスト"""

import pytest
from pathlib import Path
from unittest.mock import patch

from tanebi.core.callback import (
    handle_callback,
    parse_callback_args,
    resolve_cmd_dir,
)


def test_parse_callback_args():
    """"key=value" リストが正しく dict になる"""
    args = ["event_type=worker.completed", "status=GREEN", "cmd_id=cmd_042"]
    result = parse_callback_args(args)
    assert result == {
        "event_type": "worker.completed",
        "status": "GREEN",
        "cmd_id": "cmd_042",
    }


def test_resolve_cmd_dir_exists(tmp_path):
    """存在する cmd_dir が正しく解決される"""
    work_dir = tmp_path / "work"
    cmd_dir = work_dir / "cmd_042"
    cmd_dir.mkdir(parents=True)

    result = resolve_cmd_dir("cmd_042", work_dir)
    assert result == cmd_dir


def test_resolve_cmd_dir_not_found(tmp_path):
    """存在しない場合 FileNotFoundError"""
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        resolve_cmd_dir("cmd_999", work_dir)


def test_handle_callback_creates_event(tmp_path):
    """handle_callback 後にイベントファイルが作成される（emit_event をモック）"""
    work_dir = tmp_path / "work"
    cmd_dir = work_dir / "cmd_042"
    cmd_dir.mkdir(parents=True)

    mock_event_file = cmd_dir / "events" / "001_worker.completed.yaml"

    with patch("tanebi.core.callback.emit_event") as mock_emit:
        mock_emit.return_value = mock_event_file

        result = handle_callback(
            cmd_id="cmd_042",
            work_dir=work_dir,
            kwargs={
                "event_type": "worker.completed",
                "status": "GREEN",
                "subtask_id": "subtask_001",
            },
        )

    mock_emit.assert_called_once_with(
        cmd_dir,
        "worker.completed",
        {"status": "GREEN", "subtask_id": "subtask_001", "task_id": "cmd_042"},
        validate=True,
    )
    assert result == mock_event_file
