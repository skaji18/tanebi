"""Unit tests for tanebi.executor.listener"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tanebi.executor.listener import ExecutorListener, try_claim


# ---------------------------------------------------------------------------
# try_claim
# ---------------------------------------------------------------------------

def test_try_claim_success(tmp_path):
    """新規パス → True が返り、.claimed ファイルが作成される"""
    event_path = tmp_path / "001_decompose.requested.yaml"
    event_path.write_text("payload: {}", encoding="utf-8")

    result = try_claim(event_path)

    assert result is True
    claim_path = event_path.with_suffix(".claimed")
    assert claim_path.exists()


def test_try_claim_duplicate(tmp_path):
    """同じパスを2回 claim → 2回目は False"""
    event_path = tmp_path / "001_decompose.requested.yaml"
    event_path.write_text("payload: {}", encoding="utf-8")

    first = try_claim(event_path)
    second = try_claim(event_path)

    assert first is True
    assert second is False


# ---------------------------------------------------------------------------
# ExecutorListener.on_created
# ---------------------------------------------------------------------------

@pytest.fixture
def listener(tmp_path):
    """ExecutorListener with minimal config"""
    config = {"execution": {"max_parallel_workers": 2}}
    return ExecutorListener(tanebi_root=tmp_path, config=config)


def test_executor_listener_skip_non_requested(listener, tmp_path):
    """execute.requested でないファイル → スキップ（_dispatch 未呼び出し）"""
    event_path = tmp_path / "work" / "task_001" / "events" / "001_task.created.yaml"
    event_path.parent.mkdir(parents=True, exist_ok=True)
    event_path.write_text("payload: {}", encoding="utf-8")

    with patch.object(listener, "_dispatch") as mock_dispatch:
        listener.on_created(event_path)

    mock_dispatch.assert_not_called()


def test_executor_listener_dispatch_decompose(listener, tmp_path):
    """decompose.requested → _run_decompose が呼ばれる（モック）"""
    task_id = "task_001"
    events_dir = tmp_path / "work" / task_id / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    event_path = events_dir / "001_decompose.requested.yaml"
    event_path.write_text("payload:\n  request_path: work/task_001/request.md\n",
                          encoding="utf-8")

    with patch.object(listener, "_run_decompose") as mock_decompose:
        listener.on_created(event_path)

    mock_decompose.assert_called_once()
    call_args = mock_decompose.call_args
    assert call_args[0][1] == {"request_path": "work/task_001/request.md"}


def test_executor_listener_claim_before_dispatch(listener, tmp_path):
    """claim に失敗すると dispatch しない"""
    task_id = "task_002"
    events_dir = tmp_path / "work" / task_id / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    event_path = events_dir / "001_decompose.requested.yaml"
    event_path.write_text("payload: {}", encoding="utf-8")

    # 事前に .claimed を作成 → claim 失敗させる
    claim_path = event_path.with_suffix(".claimed")
    claim_path.write_text("claimed_at: '2026-01-01'", encoding="utf-8")

    with patch.object(listener, "_dispatch") as mock_dispatch:
        listener.on_created(event_path)

    mock_dispatch.assert_not_called()
