"""tanebi.event_store のユニットテスト"""
import pytest
import yaml
from pathlib import Path

from tanebi.event_store import (
    emit_event,
    emit_feedback,
    validate_payload,
    next_task_id,
    create_task,
    list_events,
    get_task_summary,
)


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


# --- next_task_id ---

def test_next_task_id_empty(tmp_tanebi_root):
    """work_dir が空のとき "cmd_001" を返す"""
    work_dir = tmp_tanebi_root / "work"
    assert next_task_id(work_dir) == "cmd_001"


def test_next_task_id_with_existing(tmp_tanebi_root):
    """cmd_001 があれば "cmd_002" を返す"""
    work_dir = tmp_tanebi_root / "work"
    (work_dir / "cmd_001").mkdir()
    assert next_task_id(work_dir) == "cmd_002"


# --- create_task ---

def test_create_task_creates_structure(tmp_tanebi_root):
    """ディレクトリ・request.md・events/ が作られる"""
    work_dir = tmp_tanebi_root / "work"
    cmd_dir = create_task(work_dir, "cmd_001", "テスト依頼内容")
    assert cmd_dir.is_dir()
    assert (cmd_dir / "request.md").read_text(encoding="utf-8") == "テスト依頼内容"
    assert (cmd_dir / "events").is_dir()


def test_create_task_emits_event(tmp_tanebi_root):
    """task.created イベントが発火される"""
    work_dir = tmp_tanebi_root / "work"
    cmd_dir = create_task(work_dir, "cmd_001", "依頼")
    events = list(sorted((cmd_dir / "events").glob("*.yaml")))
    assert len(events) == 1
    data = yaml.safe_load(events[0].read_text(encoding="utf-8"))
    assert data["event_type"] == "task.created"
    assert data["payload"]["cmd_id"] == "cmd_001"


def test_create_task_duplicate_raises(tmp_tanebi_root):
    """同じ task_id で2回呼ぶと FileExistsError"""
    work_dir = tmp_tanebi_root / "work"
    create_task(work_dir, "cmd_001", "初回")
    with pytest.raises(FileExistsError):
        create_task(work_dir, "cmd_001", "重複")


# --- list_events ---

def test_list_events_empty(tmp_tanebi_root):
    """events/ なし → []"""
    cmd_dir = tmp_tanebi_root / "work" / "cmd_001"
    cmd_dir.mkdir(parents=True)
    assert list_events(cmd_dir) == []


def test_list_events_sorted(tmp_tanebi_root):
    """複数イベントが SEQ 昇順で返される"""
    cmd_dir = tmp_tanebi_root / "work" / "cmd_001"
    emit_event(cmd_dir, "task.created", {"cmd_id": "cmd_001"}, validate=False)
    emit_event(cmd_dir, "worker.started", {"cmd_id": "cmd_001"}, validate=False)
    emit_event(cmd_dir, "task.completed", {"cmd_id": "cmd_001"}, validate=False)
    events = list_events(cmd_dir)
    assert len(events) == 3
    types = [e["event_type"] for e in events]
    assert types == ["task.created", "worker.started", "task.completed"]


# --- get_task_summary ---

def test_get_task_summary(tmp_tanebi_root):
    """状態集計が正しい"""
    cmd_dir = tmp_tanebi_root / "work" / "cmd_042"
    emit_event(cmd_dir, "task.created", {"cmd_id": "cmd_042"}, validate=False)
    emit_event(cmd_dir, "worker.started", {"cmd_id": "cmd_042"}, validate=False)
    summary = get_task_summary(cmd_dir)
    assert summary["task_id"] == "cmd_042"
    assert summary["state"] == "worker.started"
    assert summary["event_count"] == 2
    assert summary["last_event"] == "worker.started"
    assert summary["events"] == ["task.created", "worker.started"]
