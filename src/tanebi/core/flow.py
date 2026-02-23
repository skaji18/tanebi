"""TANEBI Flow — ステートレスなリアクティブハンドラ集合

イベントログから現在の状態を判定し、次のアクションをトリガーする。
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from tanebi.core.event_store import emit_event, list_events


def _all_workers_complete(events: list[dict], wave: int) -> bool:
    """wave番号が一致するworkerの完了チェック。

    execute.requested の数（expected）と worker.completed の数（actual）を比較し、
    actual >= expected かつ expected > 0 なら True を返す。
    """
    expected = sum(
        1
        for e in events
        if e.get("event_type") == "execute.requested"
        and e.get("payload", {}).get("wave") == wave
    )
    actual = sum(
        1
        for e in events
        if e.get("event_type") in ("worker.completed", "error.worker_failed")
        and e.get("payload", {}).get("wave") == wave
    )
    return expected > 0 and actual >= expected


def determine_state(cmd_dir: Path) -> str:
    """イベントログから現在の状態を判定する。

    Returns
    -------
    str
        現在の状態を表す文字列。
    """
    cmd_dir = Path(cmd_dir)
    events = list_events(cmd_dir)
    if not events:
        return "unknown"

    last_type = events[-1].get("event_type", "")

    if last_type == "task.created":
        return "needs_decompose"
    if last_type == "decompose.requested":
        return "decomposing"
    if last_type == "task.decomposed":
        return "needs_execute"
    if last_type in ("execute.requested", "worker.started"):
        return "executing"
    if last_type == "worker.completed":
        wave = events[-1].get("payload", {}).get("wave", 1)
        if _all_workers_complete(events, wave):
            return "wave_complete"
        return "executing"
    if last_type == "wave.completed":
        return "needs_next_wave_or_aggregate"
    if last_type == "aggregate.requested":
        return "aggregating"
    if last_type == "task.aggregated":
        return "completed"
    return "unknown"


def on_task_created(cmd_dir: Path, payload: dict) -> None:
    """task.created イベントに反応し decompose.requested を発火する。"""
    cmd_dir = Path(cmd_dir)
    emit_event(
        cmd_dir,
        "decompose.requested",
        {
            "task_id": cmd_dir.name,
            "request_path": str(cmd_dir / "request.md"),
            "persona_list": [],
            "plan_output_path": str(cmd_dir / "plan.md"),
        },
        validate=False,
    )


def _parse_plan(cmd_dir: Path, payload: dict) -> list[dict]:
    """plan.md または payload["plan"] からサブタスクリストを取得する。

    planがない or wave=1タスクがなければ [] を返す。
    """
    # payload に plan キーがあればそれを優先
    plan = payload.get("plan")
    if plan is None:
        plan_path = cmd_dir / "plan.md"
        if not plan_path.exists():
            raise RuntimeError(f"plan.md not found: {plan_path}")
        content = plan_path.read_text(encoding="utf-8")
        # 最小限パース: YAMLブロックを試みる
        try:
            plan = yaml.safe_load(content)
        except yaml.YAMLError:
            plan = None

    if not isinstance(plan, dict):
        return []

    subtasks = plan.get("subtasks", [])
    if not isinstance(subtasks, list):
        return []

    return [s for s in subtasks if isinstance(s, dict) and s.get("wave") == 1]


def on_task_decomposed(cmd_dir: Path, payload: dict) -> None:
    """task.decomposed イベントに反応し wave=1 の execute.requested を発火する。"""
    cmd_dir = Path(cmd_dir)
    try:
        wave1_subtasks = _parse_plan(cmd_dir, payload)
    except RuntimeError:
        raise

    if not wave1_subtasks:
        return

    for subtask in wave1_subtasks:
        emit_event(
            cmd_dir,
            "execute.requested",
            {
                "task_id": cmd_dir.name,
                "subtask_id": subtask["id"],
                "subtask_description": subtask.get("description", ""),
                "wave": 1,
            },
            validate=False,
        )


def on_worker_completed(cmd_dir: Path, payload: dict) -> None:
    """worker.completed イベントに反応し、wave全体の完了を確認したら wave.completed を発火する。"""
    cmd_dir = Path(cmd_dir)
    events = list_events(cmd_dir)
    wave = payload.get("wave", 1)
    if _all_workers_complete(events, wave):
        emit_event(
            cmd_dir,
            "wave.completed",
            {
                "task_id": cmd_dir.name,
                "wave": wave,
            },
            validate=False,
        )


def _parse_wave_subtasks(cmd_dir: Path, payload: dict, wave: int) -> list[dict]:
    """plan から指定 wave のサブタスクリストを取得する。"""
    plan = payload.get("plan")
    if plan is None:
        plan_path = cmd_dir / "plan.md"
        if not plan_path.exists():
            return []
        content = plan_path.read_text(encoding="utf-8")
        try:
            plan = yaml.safe_load(content)
        except yaml.YAMLError:
            return []

    if not isinstance(plan, dict):
        return []

    subtasks = plan.get("subtasks", [])
    if not isinstance(subtasks, list):
        return []

    return [s for s in subtasks if isinstance(s, dict) and s.get("wave") == wave]


def on_wave_completed(cmd_dir: Path, payload: dict) -> None:
    """wave.completed イベントに反応し、Worker失敗チェック後、次waveのサブタスクがあれば execute.requested、なければ aggregate.requested を発火する。"""
    cmd_dir = Path(cmd_dir)
    current_wave = payload.get("wave", 1)
    task_id = payload.get("task_id", cmd_dir.name)
    next_wave = current_wave + 1

    events = list_events(cmd_dir)
    success_count = sum(
        1 for e in events
        if e.get("event_type") == "worker.completed"
        and e.get("payload", {}).get("wave") == current_wave
    )
    failed_count = sum(
        1 for e in events
        if e.get("event_type") == "error.worker_failed"
        and e.get("payload", {}).get("wave") == current_wave
    )

    if success_count == 0 and failed_count > 0:
        raise RuntimeError(f"All workers failed in wave {current_wave}. Task: {task_id}")

    if failed_count > 0:
        logging.warning(
            "Partial failure in wave %d: %d failed, %d succeeded. Task: %s",
            current_wave, failed_count, success_count, task_id,
        )

    next_subtasks = _parse_wave_subtasks(cmd_dir, payload, next_wave)

    if next_subtasks:
        for subtask in next_subtasks:
            emit_event(
                cmd_dir,
                "execute.requested",
                {
                    "task_id": cmd_dir.name,
                    "subtask_id": subtask["id"],
                    "subtask_description": subtask.get("description", ""),
                    "wave": next_wave,
                },
                validate=False,
            )
    else:
        emit_event(
            cmd_dir,
            "aggregate.requested",
            {
                "task_id": cmd_dir.name,
                "results_dir": str(cmd_dir / "results"),
                "report_path": str(cmd_dir / "report.md"),
            },
            validate=False,
        )
