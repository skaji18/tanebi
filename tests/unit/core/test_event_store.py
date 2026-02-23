"""tanebi.core.event_store のユニットテスト"""
import pytest
import yaml
from pathlib import Path

from tanebi.core.event_store import emit_event, emit_feedback, validate_payload


def test_emit_event_creates_file(tmp_tanebi_root):
    """emit_event後にファイルが存在する"""
    cmd_dir = tmp_tanebi_root / "work" / "cmd_001"
    result = emit_event(cmd_dir, "task.created", {"cmd_id": "cmd_001"}, validate=False)
    assert result.exists()


def test_emit_event_naming(tmp_tanebi_root):
    """ファイル名が 001_task.created.yaml 形式"""
    cmd_dir = tmp_tanebi_root / "work" / "cmd_001"
    result = emit_event(cmd_dir, "task.created", {"cmd_id": "cmd_001"}, validate=False)
    assert result.name == "001_task.created.yaml"


def test_emit_event_sequential(tmp_tanebi_root):
    """2回発火で 001_... と 002_... になる"""
    cmd_dir = tmp_tanebi_root / "work" / "cmd_001"
    first = emit_event(cmd_dir, "task.created", {"cmd_id": "cmd_001"}, validate=False)
    second = emit_event(cmd_dir, "worker.started", {"cmd_id": "cmd_001"}, validate=False)
    assert first.name.startswith("001_")
    assert second.name.startswith("002_")


def test_emit_event_payload(tmp_tanebi_root):
    """ファイル内にpayloadが含まれる"""
    cmd_dir = tmp_tanebi_root / "work" / "cmd_001"
    payload = {"cmd_id": "cmd_001", "request_summary": "テスト依頼"}
    result = emit_event(cmd_dir, "task.created", payload, validate=False)
    data = yaml.safe_load(result.read_text(encoding="utf-8"))
    assert data["payload"]["cmd_id"] == "cmd_001"
    assert data["payload"]["request_summary"] == "テスト依頼"
    assert "timestamp" in data["payload"]  # 自動付与


def test_emit_feedback_creates_file(tmp_tanebi_root):
    """emit_feedback後にファイルが存在する"""
    cmd_dir = tmp_tanebi_root / "work" / "cmd_001"
    result = emit_feedback(cmd_dir, source="approval", content="承認します", feedback_type="approve_plan")
    assert result.exists()
    data = yaml.safe_load(result.read_text(encoding="utf-8"))
    assert data["source"] == "approval"
    assert data["content"] == "承認します"
    assert data["feedback_type"] == "approve_plan"


def test_validate_payload_missing_required():
    """必須フィールド欠落でValueError"""
    schema = {
        "events": {
            "task.created": {
                "payload": {
                    "cmd_id": "string",
                    "request_summary": "string",
                    "timestamp": "string",
                }
            }
        }
    }
    # cmd_id だけあり request_summary が欠落
    with pytest.raises(ValueError, match="request_summary"):
        validate_payload("task.created", {"cmd_id": "cmd_001", "timestamp": "2026-01-01T00:00:00Z"}, schema)
