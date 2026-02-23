"""tanebi.core.persona_ops のユニットテスト"""

import pytest
import yaml
from pathlib import Path

from tanebi.core.persona_ops import (
    copy_persona,
    list_personas,
    merge_personas,
    restore_persona,
    snapshot_persona,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_persona_yaml(tmp_path: Path, persona_id: str, **overrides) -> Path:
    """テスト用ダミーペルソナYAMLを tmp_path 内に作成して Path を返す。"""
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
                "speed_vs_quality": 0.3,
                "autonomy_preference": 0.5,
                "communication_density": 0.5,
            },
        }
    }
    # Apply overrides to persona dict
    data["persona"].update(overrides)
    persona_file = tmp_path / f"{persona_id}.yaml"
    persona_file.write_text(yaml.safe_dump(data, allow_unicode=True, default_flow_style=False))
    return persona_file


# ---------------------------------------------------------------------------
# list_personas
# ---------------------------------------------------------------------------

def test_list_personas_empty(tmp_tanebi_root):
    """ペルソナなしで空リストを返却する。"""
    personas_dir = tmp_tanebi_root / "personas" / "active"
    result = list_personas(personas_dir)
    assert result == []


def test_list_personas(tmp_tanebi_root):
    """ペルソナYAMLがある場合に正しくリスト化する。"""
    personas_dir = tmp_tanebi_root / "personas" / "active"
    _make_persona_yaml(personas_dir, "alpha")
    _make_persona_yaml(personas_dir, "beta")

    result = list_personas(personas_dir)

    assert len(result) == 2
    ids = {r["id"] for r in result}
    assert "alpha" in ids
    assert "beta" in ids

    # 各エントリに必要フィールドが存在する
    for entry in result:
        assert "id" in entry
        assert "name" in entry
        assert "total_tasks" in entry


# ---------------------------------------------------------------------------
# copy_persona
# ---------------------------------------------------------------------------

def test_copy_persona(tmp_tanebi_root):
    """コピー後に新ファイルが存在する。"""
    personas_dir = tmp_tanebi_root / "personas" / "active"
    _make_persona_yaml(personas_dir, "src_persona")

    dst_path = copy_persona("src_persona", "dst_persona", personas_dir)

    assert dst_path.exists()
    assert dst_path.name == "dst_persona.yaml"


def test_copy_persona_content(tmp_tanebi_root):
    """コピー後の内容が元と一致し、メタデータが更新されている。"""
    personas_dir = tmp_tanebi_root / "personas" / "active"
    _make_persona_yaml(personas_dir, "original")

    dst_path = copy_persona("original", "clone", personas_dir)

    with open(dst_path) as f:
        copied = yaml.safe_load(f)

    persona = copied["persona"]
    assert persona["id"] == "clone"
    assert persona["version"] == 1
    assert persona["parent_version"] == "original"
    assert persona["lineage"] == ["original"]
    assert persona["identity"]["origin"] == "copied"
    # performance/evolution セクションが除去されている
    assert "performance" not in persona
    assert "evolution" not in persona
    # task_count がリセットされている
    for domain in persona["knowledge"]["domains"]:
        assert domain["task_count"] == 0


def test_copy_persona_src_not_found(tmp_tanebi_root):
    """存在しないソースは FileNotFoundError。"""
    personas_dir = tmp_tanebi_root / "personas" / "active"
    with pytest.raises(FileNotFoundError):
        copy_persona("nonexistent", "dst", personas_dir)


def test_copy_persona_dst_exists(tmp_tanebi_root):
    """コピー先が既存なら ValueError。"""
    personas_dir = tmp_tanebi_root / "personas" / "active"
    _make_persona_yaml(personas_dir, "src")
    _make_persona_yaml(personas_dir, "dst")

    with pytest.raises(ValueError):
        copy_persona("src", "dst", personas_dir)


# ---------------------------------------------------------------------------
# snapshot_persona
# ---------------------------------------------------------------------------

def test_snapshot_persona(tmp_tanebi_root):
    """スナップショットファイルが作成される。"""
    personas_dir = tmp_tanebi_root / "personas" / "active"
    snapshots_dir = tmp_tanebi_root / "personas" / "history"
    _make_persona_yaml(personas_dir, "my_persona")

    snap_path = snapshot_persona("my_persona", personas_dir, snapshots_dir)

    assert snap_path.exists()
    assert snap_path.name == "my_persona_gen1.yaml"
    assert snapshots_dir.is_dir()


def test_snapshot_persona_increments_gen(tmp_tanebi_root):
    """複数スナップショットでgenが増分する。"""
    personas_dir = tmp_tanebi_root / "personas" / "active"
    snapshots_dir = tmp_tanebi_root / "personas" / "history"
    _make_persona_yaml(personas_dir, "my_persona")

    snap1 = snapshot_persona("my_persona", personas_dir, snapshots_dir)
    snap2 = snapshot_persona("my_persona", personas_dir, snapshots_dir)

    assert snap1.name == "my_persona_gen1.yaml"
    assert snap2.name == "my_persona_gen2.yaml"


def test_snapshot_persona_not_found(tmp_tanebi_root):
    """存在しないペルソナは FileNotFoundError。"""
    personas_dir = tmp_tanebi_root / "personas" / "active"
    snapshots_dir = tmp_tanebi_root / "personas" / "history"

    with pytest.raises(FileNotFoundError):
        snapshot_persona("ghost", personas_dir, snapshots_dir)
