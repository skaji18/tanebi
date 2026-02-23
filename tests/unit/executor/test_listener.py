"""Unit tests for tanebi.executor.listener"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

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
        listener.executor.shutdown(wait=True)

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


# ---------------------------------------------------------------------------
# 並列実行テスト
# ---------------------------------------------------------------------------

def test_parallel_execution_submit_called_multiple_times(tmp_path):
    """複数の execute.requested イベントを登録すると executor.submit が複数回呼ばれる"""
    config = {"execution": {"max_parallel_workers": 3}}
    lst = ExecutorListener(tanebi_root=tmp_path, config=config)

    n_events = 3
    with patch.object(lst.executor, "submit") as mock_submit:
        for i in range(n_events):
            task_id = f"task_{i:03d}"
            events_dir = tmp_path / "work" / task_id / "events"
            events_dir.mkdir(parents=True, exist_ok=True)
            event_path = events_dir / "001_execute.requested.yaml"
            event_path.write_text(
                f"payload:\n  subtask_id: sub_{i}\n  wave: 1\n",
                encoding="utf-8",
            )
            lst.on_created(event_path)

    assert mock_submit.call_count == n_events


# ---------------------------------------------------------------------------
# graceful shutdown テスト
# ---------------------------------------------------------------------------

def test_shutdown_calls_executor_shutdown(tmp_path):
    """shutdown() を呼ぶと executor.shutdown(wait=True) が呼ばれる"""
    config = {"execution": {"max_parallel_workers": 2}}
    lst = ExecutorListener(tanebi_root=tmp_path, config=config)

    with patch.object(lst.executor, "shutdown") as mock_shutdown:
        lst.shutdown()

    mock_shutdown.assert_called_once_with(wait=True)


# ---------------------------------------------------------------------------
# WorkerError → error.worker_failed テスト
# ---------------------------------------------------------------------------

def test_run_execute_worker_error_emits_failed_event(tmp_path):
    """run_claude_p が WorkerError を raise すると error.worker_failed が emit され、例外が伝播しない"""
    from tanebi.executor.worker import WorkerError

    config = {"execution": {"max_parallel_workers": 2}}
    lst = ExecutorListener(tanebi_root=tmp_path, config=config)

    task_id = "task_001"
    cmd_dir = tmp_path / "work" / task_id
    cmd_dir.mkdir(parents=True, exist_ok=True)
    payload = {"subtask_id": "sub_001", "wave": 1}

    with patch("tanebi.executor.worker.run_claude_p", side_effect=WorkerError("test error")), \
         patch("tanebi.event_store.emit_event") as mock_emit:
        # 例外が伝播しないことを確認
        lst._run_execute(cmd_dir, payload)

    emitted_types = [c[0][1] for c in mock_emit.call_args_list]
    assert "error.worker_failed" in emitted_types


# ---------------------------------------------------------------------------
# スレッドセーフ採番テスト
# ---------------------------------------------------------------------------

def test_emit_event_thread_safe_no_duplicate_seq(tmp_path):
    """複数スレッドから emit_event を並列呼び出しても SEQ が重複しない"""
    from tanebi.event_store import emit_event

    cmd_dir = tmp_path / "work" / "task_001"
    n_threads = 10
    results: list[str] = []
    errors: list[Exception] = []

    def emit_once() -> None:
        try:
            path = emit_event(cmd_dir, "worker.started", {"cmd_id": "cmd_001"}, validate=False)
            results.append(path.name)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=emit_once) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Unexpected errors: {errors}"
    seqs = [name.split("_")[0] for name in results]
    assert len(seqs) == len(set(seqs)), f"Duplicate SEQs found: {seqs}"
