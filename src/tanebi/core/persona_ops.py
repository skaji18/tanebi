"""TANEBI Persona Operations.

persona_ops.sh の5オペレーションをPythonで実装。
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml


def _resolve_personas_dir(personas_dir: Optional[Path]) -> Path:
    if personas_dir is not None:
        return Path(personas_dir)
    from tanebi.core.config import PERSONA_DIR
    return Path(PERSONA_DIR)


def _resolve_snapshots_dir(snapshots_dir: Optional[Path]) -> Path:
    if snapshots_dir is not None:
        return Path(snapshots_dir)
    from tanebi.core.config import HISTORY_DIR
    return Path(HISTORY_DIR)


def copy_persona(src_id: str, dst_id: str, personas_dir: Optional[Path] = None) -> Path:
    """ペルソナをコピーする (Portable granularity)。dst_id が既存なら ValueError。"""
    personas_dir = _resolve_personas_dir(personas_dir)
    src_file = personas_dir / f"{src_id}.yaml"
    dst_file = personas_dir / f"{dst_id}.yaml"

    if not src_file.exists():
        raise FileNotFoundError(f"Source persona not found: {src_file}")
    if dst_file.exists():
        raise ValueError(f"Target persona already exists: {dst_file}")

    with open(src_file) as f:
        data = yaml.safe_load(f)

    persona = data.get("persona", {})

    # Remove performance and evolution sections (Portable granularity)
    persona.pop("performance", None)
    persona.pop("evolution", None)

    # Update metadata
    persona["id"] = dst_id
    persona["version"] = 1
    persona["parent_version"] = src_id
    persona["lineage"] = [src_id]
    persona["created_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # Update identity.origin
    if "identity" in persona:
        persona["identity"]["origin"] = "copied"

    # Reset task_count in all domains
    if "knowledge" in persona:
        for domain in persona["knowledge"].get("domains", []) or []:
            if isinstance(domain, dict):
                domain["task_count"] = 0

    data["persona"] = persona

    with open(dst_file, "w") as f:
        yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)

    return dst_file


def merge_personas(
    base_id: str,
    donor_id: str,
    output_id: str,
    personas_dir: Optional[Path] = None,
    weights: dict | None = None,
) -> Path:
    """2つのペルソナをマージして新規ペルソナを生成。"""
    personas_dir = _resolve_personas_dir(personas_dir)
    base_file = personas_dir / f"{base_id}.yaml"
    donor_file = personas_dir / f"{donor_id}.yaml"
    dst_file = personas_dir / f"{output_id}.yaml"

    if not base_file.exists():
        raise FileNotFoundError(f"Base persona not found: {base_file}")
    if not donor_file.exists():
        raise FileNotFoundError(f"Donor persona not found: {donor_file}")
    if dst_file.exists():
        raise ValueError(f"Output persona already exists: {dst_file}")

    with open(base_file) as f:
        pa = yaml.safe_load(f).get("persona", {})
    with open(donor_file) as f:
        pb = yaml.safe_load(f).get("persona", {})

    weight_a = float((weights or {}).get("base", 0.5))
    weight_b = 1.0 - weight_a

    # Behavior: weighted average
    behavior_keys = [
        "risk_tolerance", "detail_orientation", "speed_vs_quality",
        "autonomy_preference", "communication_density",
    ]
    beh_a = pa.get("behavior", {})
    beh_b = pb.get("behavior", {})
    merged_behavior = {
        key: round(float(beh_a.get(key, 0.5)) * weight_a + float(beh_b.get(key, 0.5)) * weight_b, 2)
        for key in behavior_keys
    }

    # Domains: union with weighted proficiency for shared domains
    domains_a = pa.get("knowledge", {}).get("domains", []) or []
    domains_b = pb.get("knowledge", {}).get("domains", []) or []
    today = datetime.now().strftime("%Y-%m-%d")
    seen: set[str] = set()
    merged_domains = []

    for d in domains_a:
        name = d["name"]
        seen.add(name)
        prof_a = d.get("proficiency", 0.0)
        prof_b_val = next((db.get("proficiency", 0.0) for db in domains_b if db["name"] == name), None)
        if prof_b_val is not None:
            merged_prof = round(prof_a * weight_a + prof_b_val * weight_b, 2)
        else:
            merged_prof = prof_a
        merged_domains.append({"name": name, "proficiency": merged_prof, "task_count": 0, "last_updated": today})

    for d in domains_b:
        if d["name"] not in seen:
            merged_domains.append({"name": d["name"], "proficiency": d.get("proficiency", 0.0), "task_count": 0, "last_updated": today})

    # Few-shot refs: union
    refs_a = pa.get("knowledge", {}).get("few_shot_refs", []) or []
    refs_b = pb.get("knowledge", {}).get("few_shot_refs", []) or []
    merged_refs = sorted(set(refs_a + refs_b))

    # Identity: combine names and speech styles
    id_a = pa.get("identity", {})
    id_b = pb.get("identity", {})
    name_a = id_a.get("name", base_id)
    name_b = id_b.get("name", donor_id)
    speech_a = id_a.get("speech_style", "")
    speech_b = id_b.get("speech_style", "")
    if speech_a and speech_b and speech_a != speech_b:
        merged_speech = f"{speech_a}・{speech_b}"
    else:
        merged_speech = speech_a or speech_b or "冷静"

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    merged_data = {
        "persona": {
            "id": output_id,
            "base_model": pa.get("base_model", "claude-sonnet-4-6"),
            "version": 1,
            "created_at": now,
            "parent_version": None,
            "lineage": [base_id, donor_id],
            "identity": {
                "name": f"{name_a} x {name_b}",
                "speech_style": merged_speech,
                "archetype": "hybrid",
                "origin": "merged",
            },
            "knowledge": {
                "domains": merged_domains,
                "few_shot_refs": merged_refs,
                "anti_patterns": [],
            },
            "behavior": merged_behavior,
        }
    }

    with open(dst_file, "w") as f:
        yaml.safe_dump(merged_data, f, allow_unicode=True, default_flow_style=False)

    return dst_file


def snapshot_persona(persona_id: str, personas_dir: Optional[Path] = None, snapshots_dir: Optional[Path] = None) -> Path:
    """ペルソナのスナップショットを snapshots/ に保存。"""
    personas_dir = _resolve_personas_dir(personas_dir)
    snapshots_dir = _resolve_snapshots_dir(snapshots_dir)

    src_file = personas_dir / f"{persona_id}.yaml"
    if not src_file.exists():
        raise FileNotFoundError(f"Persona not found: {src_file}")

    snapshots_dir.mkdir(parents=True, exist_ok=True)

    existing = list(snapshots_dir.glob(f"{persona_id}_gen*.yaml"))
    gen = len(existing) + 1
    dst_file = snapshots_dir / f"{persona_id}_gen{gen}.yaml"

    shutil.copy2(src_file, dst_file)
    return dst_file


def list_personas(personas_dir: Optional[Path] = None) -> list[dict]:
    """利用可能なペルソナ一覧を返す（id, name, archetype, fitness_score, total_tasks）。"""
    personas_dir = _resolve_personas_dir(personas_dir)
    result = []

    for yaml_file in sorted(personas_dir.glob("*.yaml")):
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
        except Exception:
            continue

        if not isinstance(data, dict):
            continue

        persona = data.get("persona", {})
        if not isinstance(persona, dict):
            continue

        identity = persona.get("identity", {})
        performance = persona.get("performance", {}) or {}
        evolution = persona.get("evolution", {}) or {}
        domains = (persona.get("knowledge", {}) or {}).get("domains", []) or []

        total_tasks = performance.get("total_tasks")
        if total_tasks is None:
            total_tasks = sum(d.get("task_count", 0) for d in domains if isinstance(d, dict))

        result.append({
            "id": persona.get("id", yaml_file.stem),
            "name": identity.get("name", ""),
            "archetype": identity.get("archetype", ""),
            "fitness_score": evolution.get("fitness_score"),
            "total_tasks": total_tasks,
        })

    return result


def restore_persona(persona_id: str, snapshot_file: Path, personas_dir: Optional[Path] = None) -> Path:
    """スナップショットからペルソナを復元。"""
    personas_dir = _resolve_personas_dir(personas_dir)
    snapshot_file = Path(snapshot_file)

    if not snapshot_file.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_file}")

    dst_file = personas_dir / f"{persona_id}.yaml"
    shutil.copy2(snapshot_file, dst_file)
    return dst_file
