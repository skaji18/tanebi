"""TANEBI Public API — submit / status / result"""
from __future__ import annotations
from pathlib import Path
from tanebi.core.event_store import next_task_id, create_task, list_events, get_task_summary


def submit(request: str, *, project_dir: Path | None = None) -> str:
    """タスクを投入する。task_id を返す。"""
    if project_dir is None:
        project_dir = Path.cwd()
    work_dir = project_dir / "work"
    work_dir.mkdir(exist_ok=True)
    task_id = next_task_id(work_dir)
    create_task(work_dir, task_id, request)
    return task_id


def status(task_id: str, *, project_dir: Path | None = None) -> dict:
    """タスクの現在状態を返す。"""
    if project_dir is None:
        project_dir = Path.cwd()
    cmd_dir = project_dir / "work" / task_id
    if not cmd_dir.exists():
        return {"task_id": task_id, "state": "not_found", "event_count": 0,
                "last_event": None, "events": []}
    return get_task_summary(cmd_dir)


def result(task_id: str, *, project_dir: Path | None = None) -> str | None:
    """完了していれば report.md の内容を返す。未完了なら None。"""
    if project_dir is None:
        project_dir = Path.cwd()
    report_path = project_dir / "work" / task_id / "report.md"
    if report_path.exists():
        return report_path.read_text(encoding="utf-8")
    return None
