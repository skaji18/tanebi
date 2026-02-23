"""TANEBI fitness function: calculates and updates agent fitness scores.

Fitness = w1 * quality_score + w2 * completion_rate + w3 * efficiency + w4 * growth_rate

Uses a sliding window of the last N tasks (default 20).
Weights and window size are read from config.yaml via yaml.safe_load.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import yaml

from tanebi.event_store import list_events

__all__ = [
    "QUALITY_MAP",
    "DURATION_SCORE",
    "DEFAULT_WEIGHTS",
    "DEFAULT_WINDOW",
    "load_fitness_config",
    "collect_task_history",
    "collect_checkpoint_attributions",
    "calculate_fitness",
    "update_persona_fitness",
]

QUALITY_MAP: dict[str, float] = {
    "GREEN": 1.0,
    "YELLOW": 0.5,
    "RED": 0.0,
}

DURATION_SCORE: dict[str, float] = {
    "short": 1.0,
    "medium": 0.7,
    "long": 0.4,
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "quality_score": 0.35,
    "completion_rate": 0.30,
    "efficiency": 0.20,
    "growth_rate": 0.15,
}

DEFAULT_WINDOW: int = 20


def _default_tanebi_root() -> Path:
    """Locate TANEBI root: env var → parent of src/tanebi/core/."""
    if "TANEBI_ROOT" in os.environ:
        return Path(os.environ["TANEBI_ROOT"])
    # src/tanebi/core/fitness.py → 4 levels up = tanebi root
    return Path(__file__).parent.parent.parent.parent


def load_fitness_config(tanebi_root=None) -> tuple[dict, int]:
    """Load fitness weights and window size from config.yaml.

    Args:
        tanebi_root: Path to TANEBI root directory. Auto-detected if None.

    Returns:
        tuple[dict, int]: (weights dict, window size).
        Falls back to DEFAULT_WEIGHTS / DEFAULT_WINDOW on any error.
    """
    root = Path(tanebi_root) if tanebi_root is not None else _default_tanebi_root()
    config_path = root / "config.yaml"

    weights = dict(DEFAULT_WEIGHTS)
    window = DEFAULT_WINDOW

    try:
        with config_path.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        evo = cfg.get("tanebi", {}).get("evolution", {})
        fw = evo.get("fitness_weights", {})
        if fw:
            weights.update(fw)
        fv = evo.get("fitness_window", DEFAULT_WINDOW)
        if fv is not None:
            window = int(fv)
    except (IOError, OSError, AttributeError, TypeError, ValueError):
        pass

    return weights, window


def collect_task_history(
    persona_id: str,
    work_dir: Path | None = None,
) -> list[dict]:
    """Collect task results for a persona from the event store.

    Walks work_dir/cmd_*/ directories and reads events via event_store.list_events().
    Collects entries where worker.started.persona_id matches the given persona_id,
    then correlates with worker.completed events by subtask_id.

    Args:
        persona_id: The persona ID to filter by.
        work_dir: Path to the work/ directory. Auto-detected from config if None.

    Returns:
        list[dict]: Each entry has keys: status, quality, domain, duration_estimate.
                    Ordered by cmd_dir name (oldest first).
    """
    if work_dir is None:
        from tanebi.core.config import WORK_DIR
        work_dir = Path(WORK_DIR)
    else:
        work_dir = Path(work_dir)

    if not work_dir.exists():
        return []

    results: list[dict] = []

    for cmd_dir in sorted(work_dir.iterdir()):
        if not cmd_dir.is_dir() or not cmd_dir.name.startswith("cmd_"):
            continue

        events = list_events(cmd_dir)

        # Collect subtask_ids started by this persona
        started: dict[str, dict] = {}  # subtask_id → started event payload
        for ev in events:
            if ev.get("event_type") == "worker.started":
                payload = ev.get("payload", {})
                if payload.get("persona_id") == persona_id:
                    subtask_id = payload.get("subtask_id", "")
                    started[subtask_id] = payload

        if not started:
            continue

        # Index completed events by subtask_id
        completed: dict[str, dict] = {}
        for ev in events:
            if ev.get("event_type") == "worker.completed":
                payload = ev.get("payload", {})
                sid = payload.get("subtask_id", "")
                if sid in started:
                    completed[sid] = payload

        # Build result records
        for subtask_id in started:
            if subtask_id in completed:
                p = completed[subtask_id]
                status = p.get("status", "failed")
                # Normalize schema enum value 'failure' → 'failed'
                if status == "failure":
                    status = "failed"
                results.append({
                    "status": status,
                    "quality": p.get("quality", "RED"),
                    "domain": p.get("domain", ""),
                    "duration_estimate": "",
                    "round": p.get("round", 1),
                    "subtask_id": subtask_id,
                })
            else:
                # Started but never completed → treat as failed
                results.append({
                    "status": "failed",
                    "quality": "RED",
                    "domain": "",
                    "duration_estimate": "",
                    "round": started[subtask_id].get("round", 1),
                    "subtask_id": subtask_id,
                })

    return results


def calculate_fitness(
    persona_data: dict,
    task_history: list,
    weights: dict | None = None,
    window: int | None = None,
    *,
    checkpoint_attributions: dict | None = None,
) -> float:
    """Calculate fitness score from persona data and task history.

    Args:
        persona_data: Dict with persona fields (knowledge.domains, etc.).
        task_history: List of task result dicts from collect_task_history().
                      If empty, returns a base fitness derived from proficiency.
        weights: Fitness weight dict. Loaded from config if None.
        window: Sliding window size. Loaded from config if None.
        checkpoint_attributions: {round: {subtask_id: attribution}} for round-aware
            weighting. attribution in ("execution", "input", "partial").
            - execution: weight 1.0 (normal deduction, persona responsibility)
            - input: weight 0.0 (skipped, not persona's fault)
            - partial: weight 0.5 (half deduction)
            If None, all items use weight 1.0 (backward-compatible mode).

    Returns:
        float: Fitness score between 0.0 and 1.0.
    """
    if weights is None or window is None:
        _weights, _window = load_fitness_config()
        if weights is None:
            weights = _weights
        if window is None:
            window = _window

    if not task_history:
        domains = (persona_data.get("knowledge") or {}).get("domains") or []
        if domains:
            avg_prof = sum(d.get("proficiency", 0.5) for d in domains) / len(domains)
            return round(avg_prof * 0.5, 4)
        return 0.25

    recent = task_history[-window:]
    total = len(recent)

    # Per-item attribution weights (1.0 = full, 0.5 = partial, 0.0 = skip)
    item_weights = [1.0] * total
    if checkpoint_attributions:
        for i, r in enumerate(recent):
            if r.get("status") != "success":
                rnd = r.get("round")
                sid = r.get("subtask_id", "")
                if rnd is not None and rnd in checkpoint_attributions:
                    attr = checkpoint_attributions[rnd].get(sid, "execution")
                    if attr == "input":
                        item_weights[i] = 0.0
                    elif attr == "partial":
                        item_weights[i] = 0.5
                    # "execution" → keep 1.0

    effective_total = sum(item_weights)
    if effective_total == 0.0:
        # All items skipped — fall back to base score
        domains = (persona_data.get("knowledge") or {}).get("domains") or []
        if domains:
            avg_prof = sum(d.get("proficiency", 0.5) for d in domains) / len(domains)
            return round(avg_prof * 0.5, 4)
        return 0.25

    # 1. quality_score (weighted)
    quality_score = sum(
        item_weights[i] * QUALITY_MAP.get(recent[i].get("quality", ""), 0.5)
        for i in range(total)
    ) / effective_total

    # 2. completion_rate (weighted)
    completion_rate = sum(
        item_weights[i] * (1.0 if recent[i].get("status") == "success" else 0.0)
        for i in range(total)
    ) / effective_total

    # 3. efficiency (weighted)
    efficiency = sum(
        item_weights[i] * DURATION_SCORE.get(recent[i].get("duration_estimate", ""), 0.5)
        for i in range(total)
    ) / effective_total

    # 4. growth_rate: compare first-half vs second-half of non-skipped items
    active = [recent[i] for i in range(total) if item_weights[i] > 0]
    n_active = len(active)
    if n_active >= 4:
        half = n_active // 2
        first_q = sum(QUALITY_MAP.get(r.get("quality", ""), 0.5) for r in active[:half]) / half
        second_q = (
            sum(QUALITY_MAP.get(r.get("quality", ""), 0.5) for r in active[half:])
            / (n_active - half)
        )
        growth_rate = min(max((second_q - first_q + 1.0) / 2.0, 0.0), 1.0)
    else:
        growth_rate = 0.5

    fitness = (
        weights.get("quality_score", 0.35) * quality_score
        + weights.get("completion_rate", 0.30) * completion_rate
        + weights.get("efficiency", 0.20) * efficiency
        + weights.get("growth_rate", 0.15) * growth_rate
    )

    return round(min(max(fitness, 0.0), 1.0), 4)


def collect_checkpoint_attributions(
    cmd_dir: Path,
) -> tuple[dict, int, bool]:
    """Collect checkpoint attribution info from events in cmd_dir.

    Reads checkpoint.completed events to build attribution mapping.
    attribution values: "execution" (persona fault), "input" (not persona fault),
    "partial" (partial fault).

    Args:
        cmd_dir: Path to the task directory (e.g. work/cmd_001/).

    Returns:
        tuple: (checkpoint_attributions, final_round, final_round_success)
            - checkpoint_attributions: {round: {subtask_id: attribution}}
            - final_round: highest round number seen in events
            - final_round_success: True if last worker.completed status is success
    """
    events = list_events(Path(cmd_dir))

    checkpoint_attributions: dict = {}
    max_round = 1

    for ev in events:
        payload = ev.get("payload", {})
        rnd = payload.get("round")
        if rnd is not None:
            max_round = max(max_round, rnd)

        if ev.get("event_type") == "checkpoint.completed":
            failed_subtasks = payload.get("failed_subtasks", [])
            if failed_subtasks:
                round_dict = checkpoint_attributions.setdefault(rnd or 1, {})
                for item in failed_subtasks:
                    if isinstance(item, dict):
                        sid = item.get("subtask_id", "")
                        attr = item.get("attribution", "execution")
                        if sid:
                            round_dict[sid] = attr

    # Determine final_round_success from last worker.completed event
    final_round_success = False
    for ev in reversed(events):
        if ev.get("event_type") == "worker.completed":
            status = ev.get("payload", {}).get("status", "failed")
            if status == "failure":
                status = "failed"
            final_round_success = (status == "success")
            break

    return checkpoint_attributions, max_round, final_round_success


def update_persona_fitness(
    persona_path: Path,
    work_dir: Path | None = None,
    checkpoint_attributions: dict | None = None,
) -> float:
    """Update evolution.fitness_score in a persona YAML and return the score.

    Uses yaml.safe_load / yaml.safe_dump (M-015 compliant — no regex).

    Args:
        persona_path: Path to the persona YAML file.
        work_dir: Path to work/ directory. Auto-detected from config if None.
        checkpoint_attributions: {round: {subtask_id: attribution}} for round-aware
            weighting. Passed through to calculate_fitness(). None = legacy mode.

    Returns:
        float: The calculated fitness score.
    """
    persona_path = Path(persona_path)

    with persona_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        data = {}

    # Support both {persona: {...}} and flat persona dict
    if "persona" in data:
        persona = data["persona"]
    else:
        persona = data

    persona_id = (persona or {}).get("id", "")

    task_history = collect_task_history(persona_id, work_dir)
    fitness = calculate_fitness(
        persona or {},
        task_history,
        checkpoint_attributions=checkpoint_attributions,
    )

    if not isinstance(persona, dict):
        persona = {}
    if "evolution" not in persona or not isinstance(persona.get("evolution"), dict):
        persona["evolution"] = {}
    persona["evolution"]["fitness_score"] = fitness
    persona["evolution"]["last_updated"] = date.today().isoformat()

    if "persona" in data:
        data["persona"] = persona
    else:
        data = persona

    with persona_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)

    return fitness
