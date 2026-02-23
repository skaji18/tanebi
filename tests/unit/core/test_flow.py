"""tanebi.core.flow のユニットテスト"""
from pathlib import Path

import pytest
import yaml

from tanebi.core.event_store import emit_event
from tanebi.core.flow import (
    determine_state,
    on_task_created,
    on_task_decomposed,
    on_wave_completed,
    on_worker_completed,
)


def _cmd_dir(tmp_tanebi_root: Path) -> Path:
    cmd_dir = tmp_tanebi_root / "work" / "cmd_001"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    (cmd_dir / "events").mkdir(exist_ok=True)
    return cmd_dir


def test_determine_state_unknown(tmp_tanebi_root):
    """events なし → 'unknown'"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    assert determine_state(cmd_dir) == "unknown"


def test_determine_state_needs_decompose(tmp_tanebi_root):
    """task.created が最後のイベント → 'needs_decompose'"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    emit_event(cmd_dir, "task.created", {"cmd_id": "cmd_001"}, validate=False)
    assert determine_state(cmd_dir) == "needs_decompose"


def test_determine_state_completed(tmp_tanebi_root):
    """task.aggregated が最後のイベント → 'completed'"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    emit_event(cmd_dir, "task.created", {"cmd_id": "cmd_001"}, validate=False)
    emit_event(cmd_dir, "task.aggregated", {"cmd_id": "cmd_001"}, validate=False)
    assert determine_state(cmd_dir) == "completed"


def test_on_task_created_emits_decompose_requested(tmp_tanebi_root):
    """on_task_created → decompose.requested が発火される"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    on_task_created(cmd_dir, {"cmd_id": "cmd_001"})
    events_dir = cmd_dir / "events"
    event_files = list(events_dir.glob("*.yaml"))
    assert len(event_files) == 1
    data = yaml.safe_load(event_files[0].read_text(encoding="utf-8"))
    assert data["event_type"] == "decompose.requested"
    assert data["payload"]["task_id"] == "cmd_001"
    assert data["payload"]["persona_list"] == []


def test_on_worker_completed_wave_complete(tmp_tanebi_root):
    """全worker完了 → wave.completed 発火"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    # execute.requested x2, worker.completed x2
    emit_event(cmd_dir, "execute.requested", {"subtask_id": "s1", "wave": 1}, validate=False)
    emit_event(cmd_dir, "execute.requested", {"subtask_id": "s2", "wave": 1}, validate=False)
    emit_event(cmd_dir, "worker.completed", {"subtask_id": "s1", "wave": 1}, validate=False)
    emit_event(cmd_dir, "worker.completed", {"subtask_id": "s2", "wave": 1}, validate=False)

    on_worker_completed(cmd_dir, {"wave": 1})

    events_dir = cmd_dir / "events"
    all_files = sorted(events_dir.glob("*.yaml"))
    last_data = yaml.safe_load(all_files[-1].read_text(encoding="utf-8"))
    assert last_data["event_type"] == "wave.completed"
    assert last_data["payload"]["wave"] == 1


def test_on_worker_completed_not_yet(tmp_tanebi_root):
    """未完了 → wave.completed 発火しない"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    emit_event(cmd_dir, "execute.requested", {"subtask_id": "s1", "wave": 1}, validate=False)
    emit_event(cmd_dir, "execute.requested", {"subtask_id": "s2", "wave": 1}, validate=False)
    emit_event(cmd_dir, "worker.completed", {"subtask_id": "s1", "wave": 1}, validate=False)
    # s2はまだ完了していない

    on_worker_completed(cmd_dir, {"wave": 1})

    events_dir = cmd_dir / "events"
    all_files = sorted(events_dir.glob("*.yaml"))
    last_data = yaml.safe_load(all_files[-1].read_text(encoding="utf-8"))
    assert last_data["event_type"] != "wave.completed"


def test_on_wave_completed_no_next_wave(tmp_tanebi_root):
    """次waveなし → aggregate.requested 発火"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    # plan.md に wave=1 のみ記述（wave=2 なし）
    plan = {
        "subtasks": [
            {"id": "s1", "description": "subtask 1", "wave": 1},
        ]
    }
    (cmd_dir / "plan.md").write_text(yaml.dump(plan), encoding="utf-8")

    on_wave_completed(cmd_dir, {"wave": 1})

    events_dir = cmd_dir / "events"
    all_files = sorted(events_dir.glob("*.yaml"))
    assert len(all_files) == 1
    data = yaml.safe_load(all_files[0].read_text(encoding="utf-8"))
    assert data["event_type"] == "aggregate.requested"
    assert data["payload"]["task_id"] == "cmd_001"


def test_on_wave_completed_all_failed_raises(tmp_tanebi_root):
    """全Worker失敗時にRuntimeError"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    plan = {
        "subtasks": [
            {"id": "s1", "description": "subtask 1", "wave": 1},
            {"id": "s2", "description": "subtask 2", "wave": 1},
        ]
    }
    (cmd_dir / "plan.md").write_text(yaml.dump(plan), encoding="utf-8")

    emit_event(cmd_dir, "error.worker_failed", {"subtask_id": "s1", "wave": 1}, validate=False)
    emit_event(cmd_dir, "error.worker_failed", {"subtask_id": "s2", "wave": 1}, validate=False)

    with pytest.raises(RuntimeError, match="All workers failed in wave 1"):
        on_wave_completed(cmd_dir, {"wave": 1, "task_id": "cmd_001"})


def test_on_wave_completed_partial_failure_continues(tmp_tanebi_root):
    """部分失敗は継続（例外なし）"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    plan = {
        "subtasks": [
            {"id": "s1", "description": "subtask 1", "wave": 1},
            {"id": "s2", "description": "subtask 2", "wave": 1},
        ]
    }
    (cmd_dir / "plan.md").write_text(yaml.dump(plan), encoding="utf-8")

    emit_event(cmd_dir, "worker.completed", {"subtask_id": "s1", "wave": 1}, validate=False)
    emit_event(cmd_dir, "error.worker_failed", {"subtask_id": "s2", "wave": 1}, validate=False)

    # 例外なしで継続
    on_wave_completed(cmd_dir, {"wave": 1, "task_id": "cmd_001"})


def test_on_wave_completed_all_success_continues(tmp_tanebi_root):
    """全成功は継続（例外なし）"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    plan = {
        "subtasks": [
            {"id": "s1", "description": "subtask 1", "wave": 1},
        ]
    }
    (cmd_dir / "plan.md").write_text(yaml.dump(plan), encoding="utf-8")

    emit_event(cmd_dir, "worker.completed", {"subtask_id": "s1", "wave": 1}, validate=False)

    # 例外なしで継続
    on_wave_completed(cmd_dir, {"wave": 1, "task_id": "cmd_001"})
