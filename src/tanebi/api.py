"""TANEBI Public API — submit / status / result"""
from __future__ import annotations
from pathlib import Path

import yaml

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
    """タスクの現在状態を返す。checkpoint round 情報も含む。"""
    if project_dir is None:
        project_dir = Path.cwd()
    cmd_dir = project_dir / "work" / task_id
    if not cmd_dir.exists():
        return {"task_id": task_id, "state": "not_found", "event_count": 0,
                "last_event": None, "events": []}

    summary = get_task_summary(cmd_dir)

    # Load checkpoint config from project config.yaml
    checkpoint_config: dict = {}
    config_path = project_dir / "config.yaml"
    if config_path.exists():
        try:
            with config_path.open(encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            checkpoint_config = (cfg or {}).get("tanebi", {}).get("checkpoint", {})
        except Exception:
            pass

    return {
        **summary,
        "max_rounds": checkpoint_config.get("max_rounds", 3),
        "checkpoint_mode": checkpoint_config.get("mode", "never"),
    }


def result(task_id: str, *, project_dir: Path | None = None) -> str | None:
    """完了していれば report.md の内容を返す。未完了なら None。"""
    if project_dir is None:
        project_dir = Path.cwd()
    report_path = project_dir / "work" / task_id / "report.md"
    if report_path.exists():
        return report_path.read_text(encoding="utf-8")
    return None
