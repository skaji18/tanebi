"""tanebi.core.evolve のユニットテスト"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tanebi.core.evolve import evolve_persona, _load_few_shot_max, _register_few_shot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_persona_yaml(personas_dir: Path, persona_id: str, **extra) -> Path:
    """テスト用ペルソナYAMLを作成して Path を返す。"""
    data = {
        "persona": {
            "id": persona_id,
            "base_model": "claude-sonnet-4-6",
            "version": 1,
            "created_at": "2026-01-01T00:00:00",
            "parent_version": None,
            "lineage": [],
            "identity": {
                "name": f"Test {persona_id}",
                "speech_style": "冷静",
                "archetype": "generalist",
                "origin": "seeded",
            },
            "knowledge": {
                "domains": [
                    {"name": "python", "proficiency": 0.8, "task_count": 5, "last_updated": "2026-01-01"},
                ],
                "few_shot_refs": [],
                "anti_patterns": [],
            },
            "behavior": {
                "risk_tolerance": 0.5,
                "detail_orientation": 0.7,
                "speed_vs_quality": 0.6,
                "autonomy_preference": 0.8,
                "communication_density": 0.4,
            },
            **extra,
        }
    }
    personas_dir.mkdir(parents=True, exist_ok=True)
    path = personas_dir / f"{persona_id}.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    return path


def _make_tanebi_root(tmp_path: Path, few_shot_max: int = 100) -> Path:
    """テスト用TANEBIルートを作成して Path を返す。"""
    root = tmp_path / "tanebi"
    (root / "work").mkdir(parents=True)
    (root / "personas" / "active").mkdir(parents=True)
    (root / "personas" / "history").mkdir(parents=True)
    (root / "knowledge" / "few_shot_bank").mkdir(parents=True)

    config = {
        "tanebi": {
            "evolution": {
                "few_shot_max_per_domain": few_shot_max,
                "fitness_window": 20,
                "fitness_weights": {
                    "quality_score": 0.35,
                    "completion_rate": 0.30,
                    "efficiency": 0.20,
                    "growth_rate": 0.15,
                },
            }
        }
    }
    (root / "config.yaml").write_text(yaml.dump(config), encoding="utf-8")
    return root


def _make_worker_completed_event(cmd_dir: Path, status: str, quality: str, domain: str = "python") -> None:
    """worker.completed イベントYAMLを作成する。"""
    events_dir = cmd_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    event = {
        "event_type": "worker.completed",
        "timestamp": "2026-01-01T00:00:00Z",
        "cmd_dir": str(cmd_dir),
        "payload": {
            "status": status,
            "quality": quality,
            "domain": domain,
            "subtask_id": "test_subtask",
        },
    }
    (events_dir / "001_worker.completed.yaml").write_text(
        yaml.dump(event, allow_unicode=True), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_evolve_persona_returns_report(tmp_path):
    """evolve結果dictに必須フィールドが含まれること。"""
    root = _make_tanebi_root(tmp_path)
    persona_path = _make_persona_yaml(root / "personas" / "active", "p001")

    report = evolve_persona("cmd_001", persona_path, tanebi_root=root)

    required_keys = {"task_id", "persona_id", "fitness_score", "success_rate", "total_tasks", "few_shot_added", "snapshot_path"}
    assert required_keys.issubset(report.keys()), f"Missing keys: {required_keys - report.keys()}"
    assert report["task_id"] == "cmd_001"
    assert report["persona_id"] == "p001"
    assert isinstance(report["fitness_score"], float)
    assert isinstance(report["success_rate"], float)
    assert isinstance(report["total_tasks"], int)
    assert isinstance(report["few_shot_added"], bool)
    assert isinstance(report["snapshot_path"], str)


def test_evolve_updates_performance(tmp_path):
    """evolve後にPersona YAMLのtotal_tasks/success_count/success_rateが更新されること。"""
    root = _make_tanebi_root(tmp_path)
    persona_path = _make_persona_yaml(root / "personas" / "active", "p002")

    # successステータスのイベントを作成
    cmd_dir = root / "work" / "cmd_002"
    _make_worker_completed_event(cmd_dir, status="success", quality="GREEN")

    evolve_persona("cmd_002", persona_path, tanebi_root=root)

    with persona_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    perf = data["persona"]["performance"]

    assert perf["total_tasks"] == 1
    assert perf["success_count"] == 1
    assert perf["success_rate"] == pytest.approx(1.0)


def test_evolve_few_shot_added_to_persona(tmp_path):
    """GREEN品質タスクの場合、few_shot_refsがPersona YAMLに自動追加されること（M-008）。"""
    root = _make_tanebi_root(tmp_path)
    persona_path = _make_persona_yaml(root / "personas" / "active", "p003")

    cmd_dir = root / "work" / "cmd_003"
    _make_worker_completed_event(cmd_dir, status="success", quality="GREEN", domain="python")

    report = evolve_persona("cmd_003", persona_path, tanebi_root=root)

    assert report["few_shot_added"] is True

    with persona_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    refs = data["persona"]["knowledge"]["few_shot_refs"]

    assert len(refs) >= 1
    assert any("python" in ref for ref in refs), f"Expected python domain ref, got: {refs}"


def test_evolve_success_rate_cumulative(tmp_path):
    """success_rateが累積平均で算出されること（M-011）。"""
    root = _make_tanebi_root(tmp_path)
    persona_path = _make_persona_yaml(root / "personas" / "active", "p004")

    # 1回目: success → total=1, success=1, rate=1.0
    cmd_dir_1 = root / "work" / "cmd_004a"
    _make_worker_completed_event(cmd_dir_1, status="success", quality="GREEN")
    evolve_persona("cmd_004a", persona_path, tanebi_root=root)

    with persona_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["persona"]["performance"]["total_tasks"] == 1
    assert data["persona"]["performance"]["success_rate"] == pytest.approx(1.0)

    # 2回目: failed → total=2, success=1, rate=0.5
    cmd_dir_2 = root / "work" / "cmd_004b"
    _make_worker_completed_event(cmd_dir_2, status="failed", quality="RED")
    evolve_persona("cmd_004b", persona_path, tanebi_root=root)

    with persona_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    perf = data["persona"]["performance"]
    assert perf["total_tasks"] == 2
    assert perf["success_count"] == 1
    # 累積平均: 1/2 = 0.5
    assert perf["success_rate"] == pytest.approx(0.5)


def test_few_shot_respects_config_limit(tmp_path):
    """C-002: few_shot_max_per_domainがconfig.yamlから読み取られ、上限超過時に古いエントリが削除されること。"""
    root = _make_tanebi_root(tmp_path, few_shot_max=3)
    few_shot_dir = root / "knowledge" / "few_shot_bank" / "python"
    few_shot_dir.mkdir(parents=True, exist_ok=True)

    # 既存エントリを3個作成（上限ちょうど）
    import time
    for i in range(3):
        p = few_shot_dir / f"old_entry_{i:02d}.md"
        p.write_text(f"old entry {i}", encoding="utf-8")
        time.sleep(0.01)  # mtimeに差をつける

    # max_per_domain=3 なので、新規1件追加すると合計4件 → 最古が削除される
    max_val = _load_few_shot_max(root)
    assert max_val == 3, f"Expected 3, got {max_val}"

    _register_few_shot(
        task_id="cmd_999",
        domain="python",
        subtask_id="new_task",
        persona_id="p_test",
        few_shot_bank_dir=root / "knowledge" / "few_shot_bank",
        max_per_domain=max_val,
    )

    remaining = list(few_shot_dir.glob("*.md"))
    assert len(remaining) == 3, f"Expected 3 entries after limit enforcement, got {len(remaining)}"
    # 最も新しいファイル（new entry）が残っていること
    names = {f.name for f in remaining}
    assert "cmd_999_new_task.md" in names, f"New entry not found in {names}"
