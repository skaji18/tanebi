"""TANEBI Executor Listener — *.requested イベント監視・処理"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml


def try_claim(event_path: Path) -> bool:
    """イベントの claim を試みる。成功なら True。"""
    claim_path = event_path.with_suffix(".claimed")
    try:
        fd = os.open(str(claim_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as f:
            yaml.dump({"claimed_at": datetime.now(timezone.utc).isoformat()}, f)
        return True
    except OSError:
        return False  # 既に claim 済み


class ExecutorListener:
    """EventStore を監視し *.requested.yaml を処理する。

    watchdog Observer への登録は CLI 側（listener_cmd.py）が担当する。
    このクラスは on_created コールバックのみ実装する。
    """

    def __init__(self, tanebi_root: Path, config: dict | None = None):
        self.tanebi_root = tanebi_root
        # config は yaml.safe_load で直接読む（config.py の regex parser はネスト非対応）
        if config is None:
            cfg_path = tanebi_root / "config.yaml"
            with cfg_path.open() as f:
                cfg = yaml.safe_load(f)
            exec_cfg = cfg.get("tanebi", {}).get("execution", {})
        else:
            exec_cfg = config.get("execution", {})
        self.max_workers = exec_cfg.get("max_parallel_workers", 5)
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

    def on_created(self, event_path: Path) -> None:
        """新しい *.requested.yaml を検知したときのコールバック"""
        # yaml ファイル以外はスキップ
        if not event_path.suffix == ".yaml":
            return
        stem = event_path.stem  # e.g. "002_decompose.requested"
        if not stem.endswith(".requested"):
            return
        if not try_claim(event_path):
            return  # 他の Executor がすでに claim 済み
        # task_id はパスから取得: work/{task_id}/events/{file}
        task_id = event_path.parent.parent.name
        # event_type を stem から取得: "decompose.requested"
        event_type = "_".join(stem.split("_")[1:])
        # YAML 読み込み
        with event_path.open() as f:
            event_data = yaml.safe_load(f)
        payload = event_data.get("payload", {})
        self.executor.submit(self._dispatch, task_id, event_type, payload)

    def shutdown(self, wait: bool = True) -> None:
        """ThreadPoolExecutorをgraceful shutdown"""
        self.executor.shutdown(wait=wait)

    def _dispatch(self, task_id: str, event_type: str, payload: dict) -> None:
        from tanebi.executor.worker import run_claude_p  # noqa: F401
        from tanebi.core.event_store import emit_event  # noqa: F401
        cmd_dir = self.tanebi_root / "work" / task_id
        if event_type == "decompose.requested":
            self._run_decompose(cmd_dir, payload)
        elif event_type in ("execute.requested", "checkpoint.requested"):
            self._run_execute(cmd_dir, payload)
        elif event_type == "aggregate.requested":
            self._run_aggregate(cmd_dir, payload)

    def _run_decompose(self, cmd_dir: Path, payload: dict) -> None:
        """分解処理 — stub実装（実際の claude -p 呼び出し）"""
        from tanebi.executor.worker import run_claude_p, read_template, WorkerError
        from tanebi.core.event_store import emit_event
        try:
            try:
                system = read_template("decomposer.md")
            except FileNotFoundError:
                system = "You are a task decomposer."
            result = run_claude_p(system, f"Decompose: {payload.get('request_path', '')}")
            emit_event(cmd_dir, "task.decomposed", {
                "task_id": cmd_dir.name, "plan": {}
            }, validate=False)
        except (WorkerError, Exception) as e:
            print(f"Decompose error for {cmd_dir.name}: {e}", file=sys.stderr)

    def _run_execute(self, cmd_dir: Path, payload: dict) -> None:
        """実行処理 — stub実装"""
        from tanebi.executor.worker import run_claude_p, read_template, WorkerError
        from tanebi.core.event_store import emit_event
        try:
            subtask_type = payload.get("subtask_type", "normal")
            try:
                template_name = "checkpoint.md" if subtask_type == "checkpoint" else "worker_base.md"
                system = read_template(template_name)
            except FileNotFoundError:
                system = "You are a checkpoint reviewer." if subtask_type == "checkpoint" else "You are a worker."
            round_num = payload.get("round", 1)
            wave = payload.get("wave", 1)
            results_dir = cmd_dir / "results" / f"round{round_num}"
            results_dir.mkdir(parents=True, exist_ok=True)
            emit_event(cmd_dir, "worker.started", {
                "task_id": cmd_dir.name,
                "subtask_id": payload.get("subtask_id", ""),
                "wave": wave,
                "round": round_num,
            }, round=round_num, validate=False)
            result = run_claude_p(system, str(payload))
            # 結果ファイルを results/round{N}/ に書き出す
            subtask_id = payload.get("subtask_id", "unknown")
            result_file = results_dir / f"{subtask_id}.md"
            result_file.write_text(result, encoding="utf-8")
            emit_event(cmd_dir, "worker.completed", {
                "task_id": cmd_dir.name,
                "subtask_id": subtask_id,
                "subtask_type": subtask_type,
                "wave": wave,
                "round": round_num,
                "output": result,
            }, round=round_num, validate=False)
        except WorkerError as e:
            emit_event(cmd_dir, "error.worker_failed", {
                "task_id": cmd_dir.name,
                "worker_id": payload.get("subtask_id", ""),
                "error": str(e),
            }, validate=False)
            # 例外を再raiseしない（スレッドが死なないように）

    def _run_aggregate(self, cmd_dir: Path, payload: dict) -> None:
        """統合処理 — stub実装"""
        from tanebi.executor.worker import run_claude_p, read_template, WorkerError
        from tanebi.core.event_store import emit_event
        try:
            try:
                system = read_template("aggregator.md")
            except FileNotFoundError:
                system = "You are an aggregator."
            result = run_claude_p(system, str(payload))
            report_path = cmd_dir / "report.md"
            report_path.write_text(result, encoding="utf-8")
            emit_event(cmd_dir, "task.aggregated", {
                "task_id": cmd_dir.name,
                "report_path": str(report_path),
            }, validate=False)
        except (WorkerError, Exception) as e:
            print(f"Aggregate error for {cmd_dir.name}: {e}", file=sys.stderr)
