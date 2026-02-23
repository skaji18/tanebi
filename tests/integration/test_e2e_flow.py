"""TANEBI P4-5: E2Eテスト — フルフロー (submit → decompose → execute → aggregate → status)

claude CLI はモック化し、実際の LLM 呼び出しは行わない。
ExecutorListener / Worker はモック (emit_event を直接呼ぶ) で代替する。
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from tanebi import api
from tanebi.core.event_store import emit_event, list_events
from tanebi.core.listener import CoreListener


@patch("tanebi.executor.worker.run_claude_p", return_value="mock output")
def test_full_flow_task_submit_to_execute(mock_run_claude, tmp_tanebi_root):
    """フルフロー: タスク投入から task.aggregated まで一貫して動作することを確認する。

    各ステップ:
    1. api.submit() → task.created イベント記録
    2. CoreListener が task.created を処理 → decompose.requested 発行
    3. モック Executor が decompose.requested を処理 → task.decomposed (plan付き) emit
    4. CoreListener が task.decomposed を処理 → execute.requested (wave=1) 発行
    5. モック Worker が execute.requested を処理 → worker.completed emit
    6. CoreListener が worker.completed を処理 → wave.completed 発行
    7. CoreListener が wave.completed を処理 → aggregate.requested 発行
    8. モックアグリゲータ → task.aggregated emit
    9. api.status() でタスク状態を確認
    """
    # 1. タスク投入 → EventStore に task.created が記録される
    task_id = api.submit("テストリクエスト", project_dir=tmp_tanebi_root)
    cmd_dir = tmp_tanebi_root / "work" / task_id

    events = list_events(cmd_dir)
    assert any(e["event_type"] == "task.created" for e in events), \
        "task.created イベントが記録されていない"

    # 2. CoreListener が task.created を処理 → decompose.requested 発行
    core_listener = CoreListener(tanebi_root=tmp_tanebi_root)
    task_created_path = next(
        p for p in sorted((cmd_dir / "events").glob("*.yaml"))
        if "task.created" in p.name
    )
    core_listener.on_created(task_created_path)

    events = list_events(cmd_dir)
    assert any(e["event_type"] == "decompose.requested" for e in events), \
        "decompose.requested イベントが発行されていない"

    # 3. モック Executor: decompose.requested を処理し task.decomposed を emit
    #    plan に wave=1 のサブタスクを含める (real executor は claude -p で plan を生成する)
    plan = {
        "subtasks": [
            {"id": "sub_001", "description": "テストサブタスク", "wave": 1},
        ]
    }
    emit_event(cmd_dir, "task.decomposed", {"task_id": task_id, "plan": plan}, validate=False)

    # 4. CoreListener が task.decomposed を処理 → wave=1 の execute.requested 発行
    task_decomposed_path = next(
        p for p in sorted((cmd_dir / "events").glob("*.yaml"))
        if "task.decomposed" in p.name
    )
    core_listener.on_created(task_decomposed_path)

    events = list_events(cmd_dir)
    execute_events = [e for e in events if e["event_type"] == "execute.requested"]
    assert len(execute_events) >= 1, "execute.requested イベントが発行されていない"
    assert execute_events[0]["payload"]["wave"] == 1, "wave=1 の execute.requested でない"

    # 5. モック Worker: execute.requested を処理し worker.completed を emit
    emit_event(
        cmd_dir,
        "worker.completed",
        {"task_id": task_id, "subtask_id": "sub_001", "wave": 1, "output": "mock output"},
        validate=False,
    )

    # 6. CoreListener が worker.completed を処理 → wave.completed 発行
    worker_completed_path = next(
        p for p in sorted((cmd_dir / "events").glob("*.yaml"))
        if "worker.completed" in p.name
    )
    core_listener.on_created(worker_completed_path)

    events = list_events(cmd_dir)
    assert any(e["event_type"] == "wave.completed" for e in events), \
        "wave.completed イベントが発行されていない"

    # 7. CoreListener が wave.completed を処理 → aggregate.requested 発行 (次 wave なし)
    wave_completed_path = next(
        p for p in sorted((cmd_dir / "events").glob("*.yaml"))
        if "wave.completed" in p.name
    )
    core_listener.on_created(wave_completed_path)

    events = list_events(cmd_dir)
    assert any(e["event_type"] == "aggregate.requested" for e in events), \
        "aggregate.requested イベントが発行されていない"

    # 8. モックアグリゲータ: task.aggregated を emit
    emit_event(
        cmd_dir,
        "task.aggregated",
        {"task_id": task_id, "report_path": str(cmd_dir / "report.md")},
        validate=False,
    )

    # 9. api.status() でタスク状態が確認できる
    s = api.status(task_id, project_dir=tmp_tanebi_root)
    assert s["task_id"] == task_id
    assert "task.aggregated" in s["events"], "task.aggregated がステータスに反映されていない"
