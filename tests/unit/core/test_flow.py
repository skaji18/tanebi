"""tanebi.core.flow のユニットテスト"""
from pathlib import Path

import pytest
import yaml

from tanebi.event_store import emit_event
from tanebi.core.flow import (
    determine_state,
    on_checkpoint_completed,
    on_learn_completed,
    on_task_aggregated,
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
    emit_event(cmd_dir, "task.created", {"task_id": "cmd_001", "request_summary": "テスト"})
    assert determine_state(cmd_dir) == "needs_decompose"


def test_determine_state_learn_requested(tmp_tanebi_root):
    """task.aggregated が最後のイベント → 'learn_requested'"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    emit_event(cmd_dir, "task.created", {"task_id": "cmd_001", "request_summary": "テスト"})
    emit_event(cmd_dir, "task.aggregated", {"task_id": "cmd_001", "report_path": "/tmp/report.md", "quality_summary": {}})
    assert determine_state(cmd_dir) == "learn_requested"


def test_determine_state_learning(tmp_tanebi_root):
    """learn.requested が最後のイベント → 'learning'"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    emit_event(cmd_dir, "task.aggregated", {"task_id": "cmd_001", "report_path": "/tmp/report.md", "quality_summary": {}})
    emit_event(cmd_dir, "learn.requested", {"task_id": "cmd_001", "cmd_dir": str(cmd_dir), "report_path": "/tmp/report.md"})
    assert determine_state(cmd_dir) == "learning"


def test_determine_state_completed(tmp_tanebi_root):
    """learn.completed が最後のイベント → 'completed'"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    emit_event(cmd_dir, "task.aggregated", {"task_id": "cmd_001", "report_path": "/tmp/report.md", "quality_summary": {}})
    emit_event(cmd_dir, "learn.completed", {"task_id": "cmd_001", "signals_created": 3, "domains": ["backend"], "distilled": False})
    assert determine_state(cmd_dir) == "completed"


def test_on_task_created_emits_decompose_requested(tmp_tanebi_root):
    """on_task_created → decompose.requested が発火される"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    on_task_created(cmd_dir, {"task_id": "cmd_001"})
    events_dir = cmd_dir / "events"
    event_files = list(events_dir.glob("*.yaml"))
    assert len(event_files) == 1
    data = yaml.safe_load(event_files[0].read_text(encoding="utf-8"))
    assert data["event_type"] == "decompose.requested"
    assert data["payload"]["task_id"] == "cmd_001"


def test_on_worker_completed_wave_complete(tmp_tanebi_root):
    """全worker完了 → wave.completed 発火"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    # execute.requested x2, worker.completed x2
    emit_event(cmd_dir, "execute.requested", {"task_id": "cmd_001", "subtask_id": "s1", "subtask_description": "desc", "wave": 1, "round": 1, "output_path": "results/round1/s1.md"})
    emit_event(cmd_dir, "execute.requested", {"task_id": "cmd_001", "subtask_id": "s2", "subtask_description": "desc", "wave": 1, "round": 1, "output_path": "results/round1/s2.md"})
    emit_event(cmd_dir, "worker.completed", {"task_id": "cmd_001", "subtask_id": "s1", "status": "success", "quality": "GREEN", "domain": "testing", "wave": 1, "round": 1})
    emit_event(cmd_dir, "worker.completed", {"task_id": "cmd_001", "subtask_id": "s2", "status": "success", "quality": "GREEN", "domain": "testing", "wave": 1, "round": 1})

    on_worker_completed(cmd_dir, {"wave": 1})

    events_dir = cmd_dir / "events"
    all_files = sorted(events_dir.glob("*.yaml"))
    last_data = yaml.safe_load(all_files[-1].read_text(encoding="utf-8"))
    assert last_data["event_type"] == "wave.completed"
    assert last_data["payload"]["wave"] == 1


def test_on_worker_completed_not_yet(tmp_tanebi_root):
    """未完了 → wave.completed 発火しない"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    emit_event(cmd_dir, "execute.requested", {"task_id": "cmd_001", "subtask_id": "s1", "subtask_description": "desc", "wave": 1, "round": 1, "output_path": "results/round1/s1.md"})
    emit_event(cmd_dir, "execute.requested", {"task_id": "cmd_001", "subtask_id": "s2", "subtask_description": "desc", "wave": 1, "round": 1, "output_path": "results/round1/s2.md"})
    emit_event(cmd_dir, "worker.completed", {"task_id": "cmd_001", "subtask_id": "s1", "status": "success", "quality": "GREEN", "domain": "testing", "wave": 1, "round": 1})
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

    emit_event(cmd_dir, "error.worker_failed", {"task_id": "cmd_001", "subtask_id": "s1", "error_detail": "failed", "wave": 1})
    emit_event(cmd_dir, "error.worker_failed", {"task_id": "cmd_001", "subtask_id": "s2", "error_detail": "failed", "wave": 1})

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

    emit_event(cmd_dir, "worker.completed", {"task_id": "cmd_001", "subtask_id": "s1", "status": "success", "quality": "GREEN", "domain": "testing", "wave": 1})
    emit_event(cmd_dir, "error.worker_failed", {"task_id": "cmd_001", "subtask_id": "s2", "error_detail": "failed", "wave": 1})

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

    emit_event(cmd_dir, "worker.completed", {"task_id": "cmd_001", "subtask_id": "s1", "status": "success", "quality": "GREEN", "domain": "testing", "wave": 1})

    # 例外なしで継続
    on_wave_completed(cmd_dir, {"wave": 1, "task_id": "cmd_001"})


# ---------------------------------------------------------------------------
# Checkpoint 関連テスト
# ---------------------------------------------------------------------------

def _write_checkpoint_config(tmp_tanebi_root: Path, max_rounds: int = 3) -> None:
    """テスト用 config.yaml (checkpoint セクション付き) を作成する。"""
    config = {
        "tanebi": {
            "checkpoint": {
                "mode": "auto",
                "max_rounds": max_rounds,
                "verdict_policy": "any_fail",
            }
        }
    }
    (tmp_tanebi_root / "config.yaml").write_text(yaml.dump(config), encoding="utf-8")


def test_on_checkpoint_completed_pass_emits_aggregate(tmp_tanebi_root):
    """verdict=pass → aggregate.requested が発火される"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    _write_checkpoint_config(tmp_tanebi_root)

    on_checkpoint_completed(cmd_dir, {
        "task_id": "cmd_001",
        "round": 1,
        "verdict": "pass",
        "failed_subtasks": [],
        "summary": "",
    })

    events_dir = cmd_dir / "events"
    event_files = sorted(events_dir.glob("*.yaml"))
    assert len(event_files) == 1
    data = yaml.safe_load(event_files[0].read_text(encoding="utf-8"))
    assert data["event_type"] == "aggregate.requested"
    assert data["payload"]["task_id"] == "cmd_001"
    assert data["payload"]["round"] == 1


def test_on_checkpoint_completed_fail_emits_redecompose(tmp_tanebi_root):
    """verdict=fail かつ round < max_rounds → decompose.requested(round=2) が発火される"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    _write_checkpoint_config(tmp_tanebi_root, max_rounds=3)

    on_checkpoint_completed(cmd_dir, {
        "task_id": "cmd_001",
        "round": 1,
        "verdict": "fail",
        "failed_subtasks": [{"subtask_id": "s1", "reason": "quality low"}],
        "summary": "1/1 checkpoint worker(s) failed",
    })

    events_dir = cmd_dir / "events"
    event_files = sorted(events_dir.glob("*.yaml"))
    assert len(event_files) == 1
    data = yaml.safe_load(event_files[0].read_text(encoding="utf-8"))
    assert data["event_type"] == "decompose.requested"
    assert data["payload"]["round"] == 2
    assert "checkpoint_feedback" in data["payload"]
    assert data["payload"]["checkpoint_feedback"]["previous_round"] == 1


def test_on_checkpoint_completed_max_rounds_emits_aggregate(tmp_tanebi_root):
    """round >= max_rounds → aggregate.requested が発火される（best effort）"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    _write_checkpoint_config(tmp_tanebi_root, max_rounds=3)

    on_checkpoint_completed(cmd_dir, {
        "task_id": "cmd_001",
        "round": 3,
        "verdict": "fail",
        "failed_subtasks": [],
        "summary": "still failing",
    })

    events_dir = cmd_dir / "events"
    event_files = sorted(events_dir.glob("*.yaml"))
    assert len(event_files) == 1
    data = yaml.safe_load(event_files[0].read_text(encoding="utf-8"))
    assert data["event_type"] == "aggregate.requested"
    assert data["payload"]["round"] == 3


def test_all_workers_complete_filters_by_round(tmp_tanebi_root):
    """異なる round のイベントが混在しても、指定 round のみ正しくカウントされる"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)

    # round=1 の execute.requested と worker.completed（未完了: 2リクエスト1完了）
    emit_event(cmd_dir, "execute.requested", {"task_id": "cmd_001", "subtask_id": "r1s1", "subtask_description": "desc", "wave": 1, "round": 1, "output_path": "results/round1/r1s1.md"})
    emit_event(cmd_dir, "execute.requested", {"task_id": "cmd_001", "subtask_id": "r1s2", "subtask_description": "desc", "wave": 1, "round": 1, "output_path": "results/round1/r1s2.md"})
    emit_event(cmd_dir, "worker.completed", {"task_id": "cmd_001", "subtask_id": "r1s1", "status": "success", "quality": "GREEN", "domain": "testing", "wave": 1, "round": 1})

    # round=2 の execute.requested と worker.completed（完了: 1リクエスト1完了）
    emit_event(cmd_dir, "execute.requested", {"task_id": "cmd_001", "subtask_id": "r2s1", "subtask_description": "desc", "wave": 1, "round": 2, "output_path": "results/round2/r2s1.md"})
    emit_event(cmd_dir, "worker.completed", {"task_id": "cmd_001", "subtask_id": "r2s1", "status": "success", "quality": "GREEN", "domain": "testing", "wave": 1, "round": 2})

    # round=2 の on_worker_completed → wave.completed が発火されるべき
    on_worker_completed(cmd_dir, {"wave": 1, "round": 2})

    events_dir = cmd_dir / "events"
    all_files = sorted(events_dir.glob("*.yaml"))
    # 最後のイベントが wave.completed であることを確認
    last_data = yaml.safe_load(all_files[-1].read_text(encoding="utf-8"))
    assert last_data["event_type"] == "wave.completed"
    assert last_data["payload"]["round"] == 2

    # round=1 の on_worker_completed → wave.completed は発火されないべき（r1s2 が未完了）
    events_before = len(list(events_dir.glob("*.yaml")))
    on_worker_completed(cmd_dir, {"wave": 1, "round": 1})
    events_after = len(list(events_dir.glob("*.yaml")))
    assert events_after == events_before  # 新しいイベントなし


# ---------------------------------------------------------------------------
# Learner 関連テスト
# ---------------------------------------------------------------------------

def test_on_task_aggregated_emits_learn_requested(tmp_tanebi_root):
    """on_task_aggregated → learn.requested が発火される"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)
    report_path = str(cmd_dir / "report.md")

    on_task_aggregated(cmd_dir, {"task_id": "cmd_001", "report_path": report_path, "quality_summary": {}})

    events_dir = cmd_dir / "events"
    event_files = list(events_dir.glob("*.yaml"))
    assert len(event_files) == 1
    data = yaml.safe_load(event_files[0].read_text(encoding="utf-8"))
    assert data["event_type"] == "learn.requested"
    assert data["payload"]["task_id"] == "cmd_001"
    assert data["payload"]["report_path"] == report_path
    assert "cmd_dir" in data["payload"]


def test_on_learn_completed_is_noop(tmp_tanebi_root):
    """on_learn_completed → 新たなイベントは発火されない（no-op）"""
    cmd_dir = _cmd_dir(tmp_tanebi_root)

    on_learn_completed(cmd_dir, {"task_id": "cmd_001", "signals_created": 2, "domains": ["backend"], "distilled": False})

    events_dir = cmd_dir / "events"
    event_files = list(events_dir.glob("*.yaml"))
    assert len(event_files) == 0  # 新規イベントなし
