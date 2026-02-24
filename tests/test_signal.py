"""Tests for Learning Engine Wave 1: signal.py"""
import pytest
from pathlib import Path
from tanebi.core.signal import detect_signal, classify_signal, accumulate_signal


# ===== classify_signal のテスト =====

class TestClassifySignal:
    def test_green_success_returns_positive(self):
        sig_type, weight = classify_signal("GREEN", "success")
        assert sig_type == "positive"
        assert weight == 1.0

    def test_yellow_success_returns_weak_positive(self):
        sig_type, weight = classify_signal("YELLOW", "success")
        assert sig_type == "weak_positive"
        assert weight == 0.5

    def test_red_failure_returns_negative(self):
        sig_type, weight = classify_signal("RED", "failure")
        assert sig_type == "negative"
        assert weight == 1.0

    def test_unknown_returns_negative_fallback(self):
        sig_type, weight = classify_signal("UNKNOWN", "unknown")
        assert sig_type == "negative"
        assert weight <= 1.0


# ===== detect_signal のテスト =====

class TestDetectSignal:
    def test_worker_completed_positive(self):
        event = {
            "type": "worker.completed",
            "payload": {
                "domain": "coding",
                "task_id": "cmd_001",
                "subtask_id": "subtask_001a",
                "quality": "GREEN",
                "status": "success",
                "summary": "Python CLI tool implementation",
            }
        }
        signal = detect_signal(event)
        assert signal is not None
        assert signal["signal_type"] == "positive"
        assert signal["weight"] == 1.0
        assert signal["domain"] == "coding"
        assert signal["task_id"] == "cmd_001"

    def test_worker_completed_weak_positive(self):
        event = {
            "type": "worker.completed",
            "payload": {
                "domain": "testing",
                "quality": "YELLOW",
                "status": "success",
                "task_id": "cmd_002",
                "subtask_id": "subtask_002a",
                "summary": "Some test task",
            }
        }
        signal = detect_signal(event)
        assert signal is not None
        assert signal["signal_type"] == "weak_positive"
        assert signal["weight"] == 0.5

    def test_worker_completed_negative(self):
        event = {
            "type": "worker.completed",
            "payload": {
                "domain": "api_design",
                "quality": "RED",
                "status": "failure",
                "task_id": "cmd_003",
                "subtask_id": "subtask_003a",
                "summary": "API design failed",
            }
        }
        signal = detect_signal(event)
        assert signal is not None
        assert signal["signal_type"] == "negative"
        assert signal["weight"] == 1.0

    def test_checkpoint_completed_returns_checkpoint_feedback(self):
        event = {
            "type": "checkpoint.completed",
            "payload": {
                "domain": "coding",
                "task_id": "cmd_004",
                "subtask_id": "subtask_004a",
                "verdict": "PASS",
                "attribution": "execution",
                "round": 2,
                "summary": "Checkpoint passed",
            }
        }
        signal = detect_signal(event)
        assert signal is not None
        assert signal["signal_type"] == "checkpoint_feedback"
        assert signal["weight"] == 1.0
        assert signal["attribution"] == "execution"
        assert signal["round"] == 2

    def test_checkpoint_completed_fail(self):
        event = {
            "type": "checkpoint.completed",
            "payload": {
                "domain": "coding",
                "task_id": "cmd_005",
                "subtask_id": "subtask_005a",
                "verdict": "FAIL",
                "attribution": "input",
                "round": 1,
                "summary": "Checkpoint failed",
            }
        }
        signal = detect_signal(event)
        assert signal is not None
        assert signal["signal_type"] == "checkpoint_feedback"
        assert signal["quality"] == "RED"

    def test_unknown_event_returns_none(self):
        event = {"type": "execute.requested", "payload": {}}
        result = detect_signal(event)
        assert result is None

    def test_missing_domain_defaults_to_general(self):
        event = {
            "type": "worker.completed",
            "payload": {
                "quality": "GREEN",
                "status": "success",
                "task_id": "cmd_006",
                "subtask_id": "subtask_006a",
            }
        }
        signal = detect_signal(event)
        assert signal is not None
        assert signal["domain"] == "general"


# ===== accumulate_signal のテスト =====

class TestAccumulateSignal:
    def test_creates_signal_file_in_domain_dir(self, tmp_path):
        signal = {
            "domain": "coding",
            "task_id": "cmd_001",
            "subtask_id": "subtask_001a",
            "quality": "GREEN",
            "status": "success",
            "weight": 1.0,
            "signal_type": "positive",
            "abstracted_context": "Python CLI implementation",
            "observation": "",
        }
        filepath = accumulate_signal(signal, tmp_path)
        assert filepath.exists()
        assert filepath.parent.name == "coding"

    def test_signal_file_is_valid_yaml(self, tmp_path):
        import yaml
        signal = {
            "domain": "testing",
            "task_id": "cmd_002",
            "subtask_id": "subtask_002a",
            "quality": "YELLOW",
            "status": "success",
            "weight": 0.5,
            "signal_type": "weak_positive",
            "abstracted_context": "Testing task",
            "observation": "",
        }
        filepath = accumulate_signal(signal, tmp_path)
        content = yaml.safe_load(filepath.read_text())
        assert content["signal_type"] == "weak_positive"
        assert content["domain"] == "testing"
        assert "timestamp" in content

    def test_multiple_signals_same_domain_get_unique_names(self, tmp_path):
        signal = {
            "domain": "coding",
            "quality": "GREEN",
            "status": "success",
            "weight": 1.0,
            "signal_type": "positive",
            "task_id": "cmd_001",
            "subtask_id": "subtask_001a",
            "abstracted_context": "test",
            "observation": "",
        }
        path1 = accumulate_signal(signal, tmp_path)
        path2 = accumulate_signal(signal, tmp_path)
        assert path1 != path2
        assert path1.exists()
        assert path2.exists()

    def test_checkpoint_signal_includes_attribution_and_round(self, tmp_path):
        import yaml
        signal = {
            "domain": "coding",
            "quality": "GREEN",
            "status": "success",
            "weight": 1.0,
            "signal_type": "checkpoint_feedback",
            "task_id": "cmd_003",
            "subtask_id": "subtask_003a",
            "abstracted_context": "checkpoint test",
            "observation": "",
            "attribution": "execution",
            "round": 3,
        }
        filepath = accumulate_signal(signal, tmp_path)
        content = yaml.safe_load(filepath.read_text())
        assert content["attribution"] == "execution"
        assert content["round"] == 3

    def test_creates_domain_dir_if_not_exists(self, tmp_path):
        signal = {
            "domain": "new_domain_xyz",
            "quality": "GREEN",
            "status": "success",
            "weight": 1.0,
            "signal_type": "positive",
            "task_id": "cmd_001",
            "subtask_id": "subtask_001a",
            "abstracted_context": "",
            "observation": "",
        }
        filepath = accumulate_signal(signal, tmp_path)
        assert filepath.exists()
        assert (tmp_path / "signals" / "new_domain_xyz").is_dir()
