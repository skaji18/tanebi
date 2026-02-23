"""TANEBI Flow — ステートレスなリアクティブハンドラ集合

イベントログから現在の状態を判定し、次のアクションをトリガーする。
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from tanebi.event_store import emit_event, list_events


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------

def _read_plan(cmd_dir: Path, round: int) -> dict | None:
    """plan.round{N}.md または plan.md を読んで dict を返す。

    plan.round{N}.md が存在すればそれを使用、なければ plan.md にフォールバック。
    どちらも存在しないか YAML として解析できない場合は None を返す。
    """
    plan_path = cmd_dir / f"plan.round{round}.md"
    if not plan_path.exists():
        plan_path = cmd_dir / "plan.md"
    if not plan_path.exists():
        return None
    content = plan_path.read_text(encoding="utf-8")
    try:
        plan = yaml.safe_load(content)
    except yaml.YAMLError:
        return None
    return plan if isinstance(plan, dict) else None


def _load_config(cmd_dir: Path) -> dict:
    """TANEBI_ROOT の config.yaml を読んで tanebi セクション dict を返す。

    config.yaml が存在しない場合は空 dict を返す。
    """
    try:
        from tanebi.config import load_config
        cfg = load_config()
        return cfg.get("tanebi", {}) if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _get_checkpoint_subtasks(plan: dict | None) -> list[dict]:
    """plan から type=checkpoint のサブタスクリストを返す。"""
    if plan is None:
        return []
    subtasks = plan.get("subtasks", [])
    if not isinstance(subtasks, list):
        return []
    return [s for s in subtasks if isinstance(s, dict) and s.get("type") == "checkpoint"]


def _get_max_wave(plan: dict | None) -> int:
    """plan の checkpoint subtask を除いた通常サブタスクの最大 wave 番号を返す。"""
    if plan is None:
        return 1
    subtasks = plan.get("subtasks", [])
    if not isinstance(subtasks, list):
        return 1
    waves = [
        s.get("wave", 1)
        for s in subtasks
        if isinstance(s, dict) and s.get("type") != "checkpoint"
    ]
    return max(waves, default=1)


def _parse_verdict_from_output(output: str) -> str:
    """checkpoint worker の出力から verdict を抽出する。簡易実装。"""
    if not output:
        return "pass"
    output_lower = output.lower()
    if "verdict: fail" in output_lower or "verdict:fail" in output_lower:
        return "fail"
    return "pass"


def _aggregate_verdicts(
    checkpoint_results: list[dict],
    policy: str = "any_fail",
) -> tuple[str, list[dict]]:
    """Checkpoint worker の verdict を集約する。

    Returns
    -------
    (final_verdict, failed_subtasks)
    """
    fail_count = sum(1 for r in checkpoint_results if r.get("verdict") == "fail")
    total = len(checkpoint_results)

    if total == 0:
        return "pass", []

    if policy == "any_fail":
        is_fail = fail_count > 0
    elif policy == "majority":
        is_fail = fail_count > total / 2
    elif policy == "all_fail":
        is_fail = fail_count == total
    else:
        is_fail = fail_count > 0  # デフォルトは any_fail

    final_verdict = "fail" if is_fail else "pass"

    failed_subtasks: list[dict] = []
    for result in checkpoint_results:
        for sv in result.get("subtask_verdicts", []):
            if sv.get("verdict") == "fail":
                failed_subtasks.append(sv)

    return final_verdict, failed_subtasks


def _emit_checkpoint_completed(cmd_dir: Path, round: int) -> None:
    """checkpoint wave の全 worker.completed を収集して checkpoint.completed を発火する。"""
    events = list_events(cmd_dir)
    config = _load_config(cmd_dir)
    policy = config.get("checkpoint", {}).get("verdict_policy", "any_fail")

    # checkpoint.requested で checkpoint_wave を特定
    checkpoint_wave: int | None = None
    for e in events:
        if (
            e.get("event_type") == "checkpoint.requested"
            and e.get("payload", {}).get("round", 1) == round
        ):
            checkpoint_wave = e.get("payload", {}).get("wave")
            break

    # checkpoint workers の結果 (worker.completed) を収集
    checkpoint_results: list[dict] = []
    for e in events:
        if e.get("event_type") != "worker.completed":
            continue
        ep = e.get("payload", {})
        if ep.get("round", 1) != round:
            continue
        if ep.get("subtask_type") == "checkpoint" or (
            checkpoint_wave is not None and ep.get("wave") == checkpoint_wave
        ):
            output = ep.get("output", "")
            checkpoint_results.append({
                "checkpoint_id": ep.get("subtask_id", ""),
                "verdict": _parse_verdict_from_output(output),
                "subtask_verdicts": [],
                "summary": "",
            })

    final_verdict, failed_subtasks = _aggregate_verdicts(checkpoint_results, policy)
    fail_count = sum(1 for r in checkpoint_results if r.get("verdict") == "fail")
    total = len(checkpoint_results)
    summary = f"{fail_count}/{total} checkpoint worker(s) failed"

    emit_event(
        cmd_dir,
        "checkpoint.completed",
        {
            "task_id": cmd_dir.name,
            "round": round,
            "verdict": final_verdict,
            "failed_subtasks": failed_subtasks,
            "summary": summary,
        },
        round=round,
        validate=False,
    )


def _all_workers_complete(cmd_dir: Path, round: int, wave: int) -> bool:
    """(round, wave) ペアで worker の完了チェック。

    execute.requested と checkpoint.requested の合計数 (expected) と
    worker.completed と error.worker_failed の合計数 (actual) を比較する。
    actual >= expected かつ expected > 0 なら True を返す。
    """
    events = list_events(cmd_dir)
    expected = sum(
        1
        for e in events
        if e.get("event_type") in ("execute.requested", "checkpoint.requested")
        and e.get("payload", {}).get("wave") == wave
        and e.get("payload", {}).get("round", 1) == round
    )
    actual = sum(
        1
        for e in events
        if e.get("event_type") in ("worker.completed", "error.worker_failed")
        and e.get("payload", {}).get("wave") == wave
        and e.get("payload", {}).get("round", 1) == round
    )
    return expected > 0 and actual >= expected


# ---------------------------------------------------------------------------
# 状態判定
# ---------------------------------------------------------------------------

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
        round_num = events[-1].get("payload", {}).get("round", 1)
        if _all_workers_complete(cmd_dir, round_num, wave):
            return "wave_complete"
        return "executing"
    if last_type == "wave.completed":
        return "needs_next_wave_or_aggregate"
    if last_type == "checkpoint.requested":
        return "checkpoint_executing"
    if last_type == "checkpoint.completed":
        verdict = events[-1].get("payload", {}).get("verdict", "pass")
        if verdict == "pass":
            return "needs_aggregate"
        return "needs_redo"
    if last_type == "aggregate.requested":
        return "aggregating"
    if last_type == "task.aggregated":
        return "completed"
    return "unknown"


# ---------------------------------------------------------------------------
# イベントハンドラ
# ---------------------------------------------------------------------------

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
    wave = payload.get("wave", 1)
    round_num = payload.get("round", 1)
    if _all_workers_complete(cmd_dir, round_num, wave):
        emit_event(
            cmd_dir,
            "wave.completed",
            {
                "task_id": cmd_dir.name,
                "wave": wave,
                "round": round_num,
            },
            round=round_num,
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
    """wave.completed イベントに反応し、checkpoint または次 wave / aggregate に進む。

    - 最終 wave かつ checkpoint subtask が存在 → checkpoint.requested を発火
    - checkpoint wave 完了 → checkpoint.completed を発火
    - それ以外 → 次 wave の execute.requested または aggregate.requested を発火
    """
    cmd_dir = Path(cmd_dir)
    current_wave = payload.get("wave", 1)
    round_num = payload.get("round", 1)
    task_id = payload.get("task_id", cmd_dir.name)

    events = list_events(cmd_dir)
    success_count = sum(
        1 for e in events
        if e.get("event_type") == "worker.completed"
        and e.get("payload", {}).get("wave") == current_wave
        and e.get("payload", {}).get("round", 1) == round_num
    )
    failed_count = sum(
        1 for e in events
        if e.get("event_type") == "error.worker_failed"
        and e.get("payload", {}).get("wave") == current_wave
        and e.get("payload", {}).get("round", 1) == round_num
    )

    if success_count == 0 and failed_count > 0:
        raise RuntimeError(f"All workers failed in wave {current_wave}. Task: {task_id}")

    if failed_count > 0:
        logging.warning(
            "Partial failure in wave %d: %d failed, %d succeeded. Task: %s",
            current_wave, failed_count, success_count, task_id,
        )

    plan = _read_plan(cmd_dir, round_num)
    max_wave = _get_max_wave(plan)
    checkpoint_subtasks = _get_checkpoint_subtasks(plan)

    if current_wave == max_wave and checkpoint_subtasks:
        # 最終 wave 完了 → checkpoint wave に進む
        checkpoint_wave = max_wave + 1
        for subtask in checkpoint_subtasks:
            emit_event(
                cmd_dir,
                "checkpoint.requested",
                {
                    "task_id": task_id,
                    "round": round_num,
                    "subtask_id": subtask["id"],
                    "wave": checkpoint_wave,
                },
                round=round_num,
                validate=False,
            )
    elif current_wave == max_wave + 1 and checkpoint_subtasks:
        # checkpoint wave 完了 → verdict 集約
        _emit_checkpoint_completed(cmd_dir, round_num)
    else:
        # 通常の次 wave または aggregate
        next_wave = current_wave + 1
        # plan から次 wave のサブタスクを取得
        next_subtasks: list[dict] = []
        if plan is not None:
            all_subtasks = plan.get("subtasks", [])
            if isinstance(all_subtasks, list):
                next_subtasks = [
                    s for s in all_subtasks
                    if isinstance(s, dict) and s.get("wave") == next_wave
                ]
        if not next_subtasks:
            # payload["plan"] フォールバック（旧スタイルの呼び出し元向け）
            next_subtasks = _parse_wave_subtasks(cmd_dir, payload, next_wave)

        if next_subtasks:
            for subtask in next_subtasks:
                emit_event(
                    cmd_dir,
                    "execute.requested",
                    {
                        "task_id": task_id,
                        "subtask_id": subtask["id"],
                        "subtask_description": subtask.get("description", ""),
                        "wave": next_wave,
                        "round": round_num,
                    },
                    round=round_num,
                    validate=False,
                )
        else:
            results_dir = cmd_dir / "results" / f"round{round_num}"
            results_dir.mkdir(parents=True, exist_ok=True)
            emit_event(
                cmd_dir,
                "aggregate.requested",
                {
                    "task_id": task_id,
                    "results_dir": str(results_dir),
                    "report_path": str(cmd_dir / "report.md"),
                    "round": round_num,
                },
                round=round_num,
                validate=False,
            )


def on_checkpoint_completed(cmd_dir: Path, payload: dict) -> None:
    """checkpoint.completed イベントに反応し、pass → aggregate、fail → redo または best-effort aggregate。"""
    cmd_dir = Path(cmd_dir)
    task_id = payload.get("task_id", cmd_dir.name)
    round_num = payload.get("round", 1)
    verdict = payload.get("verdict", "pass")

    config = _load_config(cmd_dir)
    max_rounds = config.get("checkpoint", {}).get("max_rounds", 3)

    if verdict == "pass" or round_num >= max_rounds:
        if verdict != "pass":
            logging.warning(
                "Max rounds (%d) reached for task %s. Aggregating best effort.",
                max_rounds, task_id,
            )
        results_dir = cmd_dir / "results" / f"round{round_num}"
        results_dir.mkdir(parents=True, exist_ok=True)
        emit_event(
            cmd_dir,
            "aggregate.requested",
            {
                "task_id": task_id,
                "results_dir": str(results_dir),
                "report_path": str(cmd_dir / "report.md"),
                "round": round_num,
            },
            round=round_num,
            validate=False,
        )
    else:
        # fail → re-decompose with feedback
        next_round = round_num + 1
        emit_event(
            cmd_dir,
            "decompose.requested",
            {
                "task_id": task_id,
                "round": next_round,
                "request_path": str(cmd_dir / "request.md"),
                "persona_list": [],
                "plan_output_path": str(cmd_dir / f"plan.round{next_round}.md"),
                "checkpoint_feedback": {
                    "previous_round": round_num,
                    "failed_subtasks": payload.get("failed_subtasks", []),
                    "summary": payload.get("summary", ""),
                    "previous_plan_path": str(cmd_dir / f"plan.round{round_num}.md"),
                    "previous_results_dir": str(cmd_dir / "results" / f"round{round_num}"),
                },
            },
            round=next_round,
            validate=False,
        )
