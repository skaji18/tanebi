"""TANEBI Evolution Engine — 6-step persona evolution flow.

evolve_persona() implements:
1. analyze  — read task summary from event store
2. evaluate — calculate fitness score
3. update   — update performance section (cumulative average, M-011)
4. few-shot — register GREEN results to few_shot_bank, update few_shot_refs (M-008)
5. snapshot — save persona snapshot
6. report   — return evolution summary dict
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

from tanebi.core.event_store import get_task_summary, list_events
from tanebi.core.fitness import update_persona_fitness
from tanebi.core.persona_ops import snapshot_persona

__all__ = ["evolve_persona"]


def _default_tanebi_root() -> Path:
    """Locate TANEBI root: env var → parent of src/tanebi/core/."""
    if "TANEBI_ROOT" in os.environ:
        return Path(os.environ["TANEBI_ROOT"])
    # src/tanebi/core/evolve.py → 4 levels up = tanebi root
    return Path(__file__).parent.parent.parent.parent


def _load_few_shot_max(tanebi_root: Path) -> int:
    """Read tanebi.evolution.few_shot_max_per_domain from config.yaml (C-002)."""
    config_path = tanebi_root / "config.yaml"
    try:
        with config_path.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return int(
            cfg.get("tanebi", {}).get("evolution", {}).get("few_shot_max_per_domain", 100)
        )
    except (IOError, OSError, AttributeError, TypeError, ValueError):
        return 100


def _get_task_result(cmd_dir: Path) -> dict:
    """Extract status/quality/domain from the last worker.completed event."""
    events = list_events(cmd_dir)
    for ev in reversed(events):
        if ev.get("event_type") == "worker.completed":
            payload = ev.get("payload", {})
            status = payload.get("status", "failed")
            if status == "failure":
                status = "failed"
            return {
                "status": status,
                "quality": payload.get("quality", "RED"),
                "domain": payload.get("domain", "general"),
                "subtask_id": payload.get("subtask_id", ""),
            }
    return {"status": "failed", "quality": "RED", "domain": "general", "subtask_id": ""}


def _register_few_shot(
    task_id: str,
    domain: str,
    subtask_id: str,
    persona_id: str,
    few_shot_bank_dir: Path,
    max_per_domain: int,
) -> str:
    """Register a GREEN result to few_shot_bank. Returns relative ref (no .md extension)."""
    domain_dir = few_shot_bank_dir / domain
    domain_dir.mkdir(parents=True, exist_ok=True)

    safe_sub = subtask_id.replace("/", "_").replace(" ", "_") if subtask_id else "task"
    filename = f"{task_id}_{safe_sub}.md"
    filepath = domain_dir / filename

    entry = (
        f"---\n"
        f"domain: {domain}\n"
        f"task_type: general\n"
        f"quality: GREEN\n"
        f"persona: {persona_id}\n"
        f'created_at: "{date.today().isoformat()}"\n'
        f'source_cmd: "{task_id}"\n'
        f'subtask_id: "{subtask_id}"\n'
        f"---\n\n"
        f"Evolution few-shot entry for {task_id} "
        f"(persona: {persona_id}, domain: {domain})\n"
    )
    filepath.write_text(entry, encoding="utf-8")

    # Enforce max entries — delete oldest by mtime, skip _format.md (C-002)
    entries = sorted(
        [e for e in domain_dir.glob("*.md") if e.name != "_format.md"],
        key=lambda p: p.stat().st_mtime,
    )
    while len(entries) > max_per_domain:
        entries.pop(0).unlink()

    return f"{domain}/{filename[:-3]}"  # strip .md extension


def _load_persona(persona_path: Path) -> tuple[dict, dict, bool]:
    """Load persona YAML. Returns (data, persona_dict, flat_flag)."""
    with persona_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        data = {}
    flat = "persona" not in data
    persona = data if flat else data.get("persona", {})
    if not isinstance(persona, dict):
        persona = {}
    return data, persona, flat


def _save_persona(persona_path: Path, data: dict, persona: dict, flat: bool) -> None:
    """Save persona YAML back to disk."""
    if flat:
        write_data = persona
    else:
        data["persona"] = persona
        write_data = data
    with persona_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(write_data, f, allow_unicode=True, default_flow_style=False)


def evolve_persona(
    task_id: str,
    persona_path: Path,
    tanebi_root: Optional[Path] = None,
) -> dict:
    """Evolve persona based on task execution results. Returns evolution report.

    Args:
        task_id: Command/task ID (e.g. "cmd_001"). Used to locate work/{task_id}/.
        persona_path: Path to the persona YAML file.
        tanebi_root: TANEBI root directory. Auto-detected if None.

    Returns:
        dict with keys: task_id, persona_id, fitness_score, success_rate,
                        total_tasks, few_shot_added, snapshot_path.
    """
    persona_path = Path(persona_path)
    root = Path(tanebi_root) if tanebi_root is not None else _default_tanebi_root()

    # ── 1. analyze ──────────────────────────────────────────────────────────
    cmd_dir = root / "work" / task_id
    if cmd_dir.exists():
        _task_summary = get_task_summary(cmd_dir)
        task_result = _get_task_result(cmd_dir)
    else:
        _task_summary = {
            "task_id": task_id, "state": "unknown",
            "event_count": 0, "last_event": None, "events": [],
        }
        task_result = {"status": "failed", "quality": "RED", "domain": "general", "subtask_id": ""}

    is_success = task_result["status"] == "success"
    is_green = task_result["quality"] == "GREEN"

    # ── 2. evaluate ─────────────────────────────────────────────────────────
    work_dir = root / "work"
    fitness_score = update_persona_fitness(
        persona_path,
        work_dir=work_dir if work_dir.exists() else None,
    )

    # ── 3. update (performance — cumulative average, M-011) ──────────────────
    data, persona, flat = _load_persona(persona_path)
    persona_id = persona.get("id", persona_path.stem)

    perf = persona.get("performance")
    if not isinstance(perf, dict):
        perf = {}

    total_tasks = int(perf.get("total_tasks", 0)) + 1
    success_count = int(perf.get("success_count", 0)) + (1 if is_success else 0)
    success_rate = round(success_count / total_tasks, 4)  # M-011: cumulative average

    perf["total_tasks"] = total_tasks
    perf["success_count"] = success_count
    perf["success_rate"] = success_rate
    persona["performance"] = perf
    _save_persona(persona_path, data, persona, flat)

    # ── 4. few-shot (M-008: auto-update few_shot_refs) ───────────────────────
    few_shot_added = False
    if is_green:
        few_shot_bank_dir = root / "knowledge" / "few_shot_bank"
        max_per_domain = _load_few_shot_max(root)
        domain = task_result.get("domain") or "general"
        subtask_id = task_result.get("subtask_id") or ""

        few_shot_ref = _register_few_shot(
            task_id, domain, subtask_id, persona_id, few_shot_bank_dir, max_per_domain
        )

        # M-008: Reload persona and append ref to few_shot_refs
        data, persona, flat = _load_persona(persona_path)
        knowledge = persona.get("knowledge")
        if not isinstance(knowledge, dict):
            knowledge = {}
        refs = knowledge.get("few_shot_refs")
        if not isinstance(refs, list):
            refs = []
        if few_shot_ref not in refs:
            refs.append(few_shot_ref)
        knowledge["few_shot_refs"] = refs
        persona["knowledge"] = knowledge
        _save_persona(persona_path, data, persona, flat)

        few_shot_added = True

    # ── 5. snapshot ─────────────────────────────────────────────────────────
    snapshots_dir = root / "personas" / "history"
    snapshot_path = snapshot_persona(
        persona_id,
        personas_dir=persona_path.parent,
        snapshots_dir=snapshots_dir,
    )

    # ── 6. report ────────────────────────────────────────────────────────────
    return {
        "task_id": task_id,
        "persona_id": persona_id,
        "fitness_score": fitness_score,
        "success_rate": success_rate,
        "total_tasks": total_tasks,
        "few_shot_added": few_shot_added,
        "snapshot_path": str(snapshot_path),
    }
