"""TANEBI CoreListener — watchdog コールバックで EventStore を監視する"""
from __future__ import annotations

from pathlib import Path

import yaml


class CoreListener:
    """EventStore を監視し *.completed に反応してフロー制御する"""

    def __init__(self, tanebi_root: Path):
        self.tanebi_root = tanebi_root

    def on_created(self, event_path: Path) -> None:
        """新しいイベントファイルを検知したときのコールバック"""
        if not event_path.suffix == ".yaml":
            return
        # task_id はパスから取得: work/{task_id}/events/{file}
        task_id = event_path.parent.parent.name
        from tanebi.config import get_rel_path
        cmd_dir = self.tanebi_root / get_rel_path("work_dir", "work") / task_id
        # ファイル名から event_type を取得
        stem = event_path.stem  # e.g. "001_task.created"
        event_type = "_".join(stem.split("_")[1:])  # "task.created"
        # YAML 読み込み
        with event_path.open() as f:
            event_data = yaml.safe_load(f)
        payload = event_data.get("payload", {})
        self._dispatch(task_id, cmd_dir, event_type, payload)

    def _dispatch(self, task_id: str, cmd_dir: Path, event_type: str, payload: dict) -> None:
        from tanebi.core import flow
        if event_type == "task.created":
            flow.on_task_created(cmd_dir, payload)
        elif event_type == "task.decomposed":
            flow.on_task_decomposed(cmd_dir, payload)
        elif event_type == "worker.completed":
            flow.on_worker_completed(cmd_dir, payload)
        elif event_type == "wave.completed":
            flow.on_wave_completed(cmd_dir, payload)
        elif event_type == "checkpoint.completed":
            flow.on_checkpoint_completed(cmd_dir, payload)
        elif event_type == "task.aggregated":
            flow.on_task_aggregated(cmd_dir, payload)
        elif event_type == "learn.completed":
            flow.on_learn_completed(cmd_dir, payload)
        # その他のイベントは無視
